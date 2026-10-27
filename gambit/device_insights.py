"""Chromebook sharing report and device history, from data GAMbit already reads.

**Sharing** (Devices → Chromebook sharing): Google keeps the last few people who signed in
to each Chromebook (recentUsers). From that GAMbit finds
- students signing in to several Chromebooks,
- Chromebooks used by many different students (outside carts and loaners),
- Chromebooks assigned to one student but used by another (swaps).

**History** (Devices → Device history): every time GAMbit reads the fleet it remembers who
each Chromebook was assigned to, who used it and which org unit it was in. Together with
loaners, repairs and GAMbit's activity log, that gives the full story of a student's
Chromebooks (or a Chromebook's students) – handy for damage fees and parent calls.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import threading

SHARING_FIELDS = ("deviceid,serialnumber,annotatedassetid,annotateduser,annotatedlocation,"
                  "orgunitpath,status,lastsync,recentusers,model")
EVENTS_MAX = 60
_lock = threading.Lock()


def sharing_args(recent: int = 5, ou: str = "") -> list[str]:
    a = ["print", "cros"]
    if ou and ou != "/":
        a += ["cros_ou_and_children", ou]
    return a + ["fields", SHARING_FIELDS, "listlimit", str(max(1, recent))]


def _c(r: dict, *names) -> str:
    low = {(k or "").lower(): v for k, v in r.items()}
    for n in names:
        if low.get(n):
            return str(low[n]).strip()
    return ""


def recent_users(r: dict, domain: str = "") -> list[str]:
    """recentUsers.N.email in order (most recent first), only real accounts."""
    found = []
    for k, v in r.items():
        m = re.match(r"recentUsers\.(\d+)\.email$", k or "", re.I)
        if m and v:
            found.append((int(m.group(1)), v.strip().lower()))
    if not found:   # some GAM versions put them in one column
        raw = _c(r, "recentusers")
        found = [(i, e.strip().lower()) for i, e in enumerate(re.split(r"[\s,;]+", raw))
                 if "@" in e]
    out = [e for _i, e in sorted(found)]
    if domain:
        out = [e for e in out if e.endswith("@" + domain.lower()) or "." in e.split("@")[-1]]
    seen, uniq = set(), []
    for e in out:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    return uniq


def devices(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({"id": _c(r, "deviceid"), "serial": _c(r, "serialnumber"),
                    "asset": _c(r, "annotatedassetid"), "user": _c(r, "annotateduser").lower(),
                    "location": _c(r, "annotatedlocation"), "ou": _c(r, "orgunitpath") or "/",
                    "status": _c(r, "status"), "lastsync": _c(r, "lastsync")[:10],
                    "model": _c(r, "model"), "recent": recent_users(r)})
    return out


def _shared_place(d: dict, items=None) -> bool:
    """Carts, loaners, labs and libraries are meant to be shared."""
    from . import ou_map
    t = ou_map.classify(d["ou"], items)["type"]
    text = f"{d['ou']} {d['location']}".lower()
    return t in ("loaners", "repairs") or bool(re.search(r"\b(carts?|loaners?|labs?|librar(?:y|ies)|"
                                                          r"spares?|pool|shared|testing)\b",
                                                          text))


def sharing(devs: list[dict], students: set[str] | None = None, many: int = 3,
            items=None) -> list[dict]:
    """One row per finding. students: emails of student accounts (None = everyone)."""
    def is_student(e):
        return students is None or e in students

    out = []
    by_student: dict[str, list[dict]] = {}
    for d in devs:
        if d["status"] and d["status"].upper() not in ("ACTIVE", "PROVISIONED"):
            continue
        rec = [e for e in d["recent"] if is_student(e)]
        if rec:
            by_student.setdefault(rec[0], []).append(d)
        shared_ok = _shared_place(d, items)
        if len(rec) >= many and not shared_ok:
            out.append({"kind": "Many students", "serial": d["serial"], "asset": d["asset"],
                        "student": ", ".join(rec), "assigned": d["user"], "ou": d["ou"],
                        "detail": f"{len(rec)} different students signed in recently",
                        "fix": ""})
        if d["user"] and rec and rec[0] != d["user"] and not shared_ok and \
                is_student(d["user"]):
            out.append({"kind": "Used by someone else", "serial": d["serial"],
                        "asset": d["asset"], "student": rec[0], "assigned": d["user"],
                        "ou": d["ou"],
                        "detail": f"Assigned to {d['user']}, last used by {rec[0]}",
                        "fix": "assign"})
    for e, ds in by_student.items():
        mine = [d for d in ds if not _shared_place(d, items)]
        if len(mine) > 1:
            out.append({"kind": "Student on several Chromebooks", "serial":
                        ", ".join(d["serial"] for d in mine),
                        "asset": ", ".join(d["asset"] for d in mine if d["asset"]),
                        "student": e, "assigned": ", ".join(sorted({d["user"] for d in mine
                                                                    if d["user"]})),
                        "ou": ", ".join(sorted({d["ou"] for d in mine})),
                        "detail": f"Most recent user of {len(mine)} Chromebooks", "fix": ""})
    order = {"Used by someone else": 0, "Student on several Chromebooks": 1, "Many students": 2}
    out.sort(key=lambda r: (order.get(r["kind"], 9), r["student"]))
    return out


def assign_fix(rows: list[dict]) -> list[tuple[str, list]]:
    """Make the last signed-in student the assigned user."""
    return [(f"{r['serial']}: assigned user → {r['student']}",
             ["cros_sn", r["serial"], "update", "user", r["student"]])
            for r in rows if r.get("fix") == "assign" and r["serial"] and r["student"]]


# ============================================================== history ===
def _path() -> str:
    from . import fleet
    d = fleet.data_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "device-history.json")


def load_history() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_history(h: dict):
    p = _path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(h, fh)
    os.replace(tmp, p)


def remember(rows: list[dict], today: str = "") -> int:
    """Add what changed since the last read. Returns the number of new events."""
    today = today or datetime.date.today().isoformat()
    devs = devices(rows)
    if not devs:
        return 0
    added = 0
    with _lock:
        try:
            h = load_history()
        except Exception:  # noqa: BLE001
            h = {}
        for d in devs:
            key = d["serial"].upper() or d["id"]
            if not key:
                continue
            ent = h.setdefault(key, {"serial": d["serial"], "asset": d["asset"],
                                     "last": {}, "events": []})
            if d["asset"]:
                ent["asset"] = d["asset"]
            last = ent.get("last", {})
            now = {"user": d["user"], "ou": d["ou"],
                   "recent": d["recent"][0] if d["recent"] else ""}
            for k, kind in (("user", "Assigned to"), ("recent", "Used by"),
                            ("ou", "Org unit")):
                if now[k] and now[k] != last.get(k):
                    ent["events"].append({"date": today, "kind": kind, "value": now[k],
                                          "was": last.get(k, "")})
                    added += 1
                elif not now[k] and last.get(k) and k == "user":
                    ent["events"].append({"date": today, "kind": "Unassigned",
                                          "value": "", "was": last.get(k, "")})
                    added += 1
            if d["recent"] and len(d["recent"]) > 1 and not last:
                # first time we see it: older recent users, no dates known
                for e in d["recent"][1:]:
                    ent["events"].append({"date": "", "kind": "Used by (earlier)",
                                          "value": e, "was": ""})
                    added += 1
            ent["events"] = ent["events"][-EVENTS_MAX:]
            ent["last"] = {k: v for k, v in now.items() if v} or last
        if added:
            try:
                _save_history(h)
            except OSError:
                pass
    return added


def _matches(text: str, q: str) -> bool:
    return q in (text or "").lower()


def history_for(q: str, h: dict | None = None, loans=None, repairs=None,
                activity_entries=None) -> list[dict]:
    """q: a student's email, a serial or an asset ID → timeline rows (newest first)."""
    q = (q or "").strip().lower()
    if not q:
        return []
    h = load_history() if h is None else h
    if loans is None or repairs is None:
        from . import fleet
        loans = fleet.load_list(fleet.data_dir(), "loaners.json") if loans is None else loans
        repairs = fleet.load_list(fleet.data_dir(), "repairs.json") if repairs is None \
            else repairs
    is_person = "@" in q
    rows = []
    serials = set()
    for key, ent in h.items():
        dev_hit = q in (key.lower(), (ent.get("asset") or "").lower())
        for e in ent.get("events", []):
            if dev_hit or (is_person and e.get("value", "").lower() == q) or \
                    (is_person and e.get("was", "").lower() == q and e["kind"] in
                     ("Assigned to", "Unassigned")):
                rows.append({"date": e.get("date", ""), "serial": ent.get("serial", key),
                             "asset": ent.get("asset", ""), "what": e["kind"],
                             "detail": e.get("value") or f"(was {e.get('was')})",
                             "source": "Fleet reads"})
                serials.add(key.upper())
    for x in loans or []:
        if q in (x.get("serial", "").lower(), (x.get("user") or "").lower()):
            rows.append({"date": x.get("out", ""), "serial": x["serial"], "asset": "",
                         "what": "Loaner out", "detail": f"to {x.get('user')}, due "
                         f"{x.get('due', '')}", "source": "Loaners"})
            if x.get("returned"):
                rows.append({"date": x["returned"], "serial": x["serial"], "asset": "",
                             "what": "Loaner returned", "detail": x.get("user", ""),
                             "source": "Loaners"})
            serials.add(x["serial"].upper())
    for t in repairs or []:
        if q in (t.get("serial", "").lower(), (t.get("user") or "").lower()) or \
                t.get("serial", "").upper() in serials:
            for hh in t.get("history", []):
                rows.append({"date": hh.get("date", ""), "serial": t["serial"], "asset": "",
                             "what": f"Repair #{t.get('n')}: {hh.get('status')}",
                             "detail": hh.get("note", "") or t.get("problem", ""),
                             "source": "Repairs"})
    if activity_entries is None:
        try:
            from . import activity
            activity_entries = activity.load(days=730, team=True)
        except Exception:  # noqa: BLE001
            activity_entries = []
    for e in activity_entries:
        if not e.get("change") or e.get("code") not in (0, None):
            continue
        text = " ".join([e.get("command", ""), " ".join(e.get("devices", []) or []),
                         e.get("what", "")]).lower()
        if q in text or any(s.lower() in text for s in serials):
            rows.append({"date": e.get("time", "")[:10], "serial":
                         ", ".join(e.get("devices", []) or [])[:60], "asset": "",
                         "what": "GAMbit change", "detail": e.get("what") or
                         e.get("command", ""), "source": f"Activity log ({e.get('who', '')})"})
    rows.sort(key=lambda r: r["date"] or "0000", reverse=True)
    return rows
