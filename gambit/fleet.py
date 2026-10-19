"""Chromebook fleet: inventory by cart/classroom, bulk asset/location import, summer
collection, and auto-update-expiration (AUE) planning. Pure functions – the page
runs GAM and shows the results."""

from __future__ import annotations

import csv
import datetime
import io
import json
import os
import re
from collections import defaultdict

FIELDS = ("serialnumber,annotatedlocation,annotatedassetid,annotateduser,orgunitpath,"
          "status,lastsync,autoupdateexpiration,model,notes,recentusers")


def _col(row: dict, *names) -> str:
    low = {(k or "").lower(): v for k, v in row.items()}
    for n in names:
        if low.get(n.lower()):
            return low[n.lower()]
    return ""


def _date(text: str):
    t = (text or "").strip()
    if not t:
        return None
    try:
        if t.isdigit():
            return datetime.datetime.utcfromtimestamp(int(t) / 1000).date()
        return datetime.date.fromisoformat(t[:10])
    except ValueError:
        return None


def devices(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        sn = _col(r, "serialNumber")
        if not sn:
            continue
        recent = _col(r, "recentUsers.0.email", "recentUsers")
        out.append({
            "serial": sn, "location": _col(r, "annotatedLocation"),
            "asset": _col(r, "annotatedAssetId"), "user": _col(r, "annotatedUser"),
            "ou": _col(r, "orgUnitPath"), "status": _col(r, "status").upper(),
            "last_sync": _date(_col(r, "lastSync")), "aue": _date(_col(r, "autoUpdateExpiration")),
            "model": _col(r, "model"), "notes": _col(r, "notes"),
            "recent_user": recent.split()[0] if recent else "",
        })
    return out


# --------------------------------------------------------------- inventory ---
def inventory(devs: list[dict], group_by: str = "location", stale_days: int = 30,
              expected: dict | None = None) -> list[dict]:
    """One row per cart/classroom (location) or org unit."""
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=stale_days)
    groups = defaultdict(list)
    for d in devs:
        key = (d["location"] if group_by == "location" else d["ou"]) or "(not set)"
        groups[key].append(d)
    rows = []
    for key, ds in sorted(groups.items(), key=lambda kv: kv[0].lower()):
        active = [d for d in ds if d["status"] == "ACTIVE"]
        stale = [d for d in active if not d["last_sync"] or d["last_sync"] < cutoff]
        missing = [d for d in ds if "missing" in (d["notes"] or "").lower()]
        exp = (expected or {}).get(key)
        rows.append({
            "group": key, "devices": len(ds), "active": len(active),
            "disabled": sum(1 for d in ds if d["status"] == "DISABLED"),
            "not_seen": len(stale), "marked_missing": len(missing),
            "expected": exp or "",
            "short": (exp - len(active)) if isinstance(exp, int) and exp > len(active) else "",
        })
    return rows


def parse_expected(text: str) -> dict:
    """'Cart 12 = 30' lines → {'Cart 12': 30}"""
    out = {}
    for ln in (text or "").splitlines():
        if "=" in ln:
            k, v = ln.rsplit("=", 1)
            if v.strip().isdigit():
                out[k.strip()] = int(v.strip())
    return out


# ------------------------------------------------------------- bulk import ---
IMPORT_COLS = {
    "serial": ["serial", "serial number", "serialnumber", "sn", "serial #"],
    "asset": ["asset", "asset tag", "asset id", "assetid", "tag"],
    "location": ["location", "cart", "room", "classroom"],
    "user": ["user", "assigned user", "student", "assigned to", "email"],
    "notes": ["notes", "note"],
    "ou": ["ou", "org unit", "orgunit", "org unit path"],
}


def _norm(h):
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def import_mapping(headers: list[str]) -> dict:
    norm = {_norm(h): h for h in headers}
    return {k: next((norm[_norm(c)] for c in cands if _norm(c) in norm), "")
            for k, cands in IMPORT_COLS.items()}


def import_commands(rows: list[dict], mapping: dict, known: dict) -> list[dict]:
    """rows from the spreadsheet → [{serial, changes, args, problem}]"""
    out = []
    for r in rows:
        sn = (r.get(mapping.get("serial") or "") or "").strip()
        if not sn:
            continue
        cur = known.get(sn.upper())
        attrs, changes = [], []
        for key, gam_key, label in (("asset", "assetid", "asset tag"),
                                    ("location", "location", "location"),
                                    ("user", "user", "assigned user"),
                                    ("notes", "notes", "notes"), ("ou", "ou", "org unit")):
            col = mapping.get(key)
            if not col:
                continue
            val = (r.get(col) or "").strip()
            if not val:
                continue
            old = (cur or {}).get({"ou": "ou"}.get(key, key), "")
            if cur is not None and old == val:
                continue
            attrs += [gam_key, val]
            changes.append(f"{label}: {old or '–'} → {val}")
        out.append({"serial": sn, "changes": "; ".join(changes) or "no change",
                    "args": ["cros_sn", sn, "update", *attrs] if attrs else [],
                    "problem": "" if cur is not None else "serial not found in Google"})
    return out


# -------------------------------------------------------- summer collection ---
def collection_path(folder: str) -> str:
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "collection.json")


def new_collection(name: str, devs: list[dict], scope: str) -> dict:
    return {"name": name, "started": datetime.datetime.now().isoformat(timespec="minutes"),
            "scope": scope,
            "expected": {d["serial"].upper(): {"user": d["user"] or d["recent_user"],
                                               "asset": d["asset"],
                                               "location": d["location"]} for d in devs},
            "collected": {}}


def scan(coll: dict, text: str, who: str) -> tuple[str, str, str]:
    """Record one scan (serial or asset tag). Returns (status, message, serial)."""
    code = (text or "").strip().upper()
    if not code:
        return "empty", "", ""
    serial = code if code in coll["expected"] else next(
        (s for s, d in coll["expected"].items() if (d.get("asset") or "").upper() == code), "")
    if not serial:
        coll.setdefault("extra", {})[code] = datetime.datetime.now().isoformat(
            timespec="minutes")
        return "unknown", f"{code} isn't on this collection list (saved as an extra device)", ""
    if serial in coll["collected"]:
        return ("again", f"{serial} was already checked in at "
                f"{coll['collected'][serial]['time']}", serial)
    coll["collected"][serial] = {"time": datetime.datetime.now().isoformat(timespec="minutes"),
                                 "by": who}
    d = coll["expected"][serial]
    left = len(coll["expected"]) - len(coll["collected"])
    return "ok", f"✔ {serial}" + (f" ({d['user']})" if d.get("user") else "") + \
        f" – {left} to go", serial


def not_returned(coll: dict) -> list[dict]:
    return [{"serial": s, **d} for s, d in sorted(coll["expected"].items())
            if s not in coll["collected"]]


def save_collection(path: str, coll: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(coll, fh, indent=1)
    os.replace(tmp, path)


def load_collection(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------- AUE plan ---
def aue_plan(devs: list[dict], cost: float, years: int = 6) -> list[dict]:
    """Active devices grouped by the school year their updates end in."""
    today = datetime.date.today()
    by_year = defaultdict(lambda: {"count": 0, "models": defaultdict(int)})
    for d in devs:
        if d["status"] != "ACTIVE" or not d["aue"]:
            continue
        # school year ending in June: an AUE of 2027-03 belongs to "2026-27"
        y = d["aue"].year if d["aue"].month <= 6 else d["aue"].year + 1
        if d["aue"] < today:
            y = 0
        by_year[y]["count"] += 1
        by_year[y]["models"][d["model"] or "Unknown model"] += 1
    rows = []
    for y in sorted(by_year):
        if y and y > today.year + years:
            continue
        info = by_year[y]
        label = "Already expired" if y == 0 else f"{y - 1}-{str(y)[-2:]} school year"
        top = sorted(info["models"].items(), key=lambda kv: -kv[1])[:3]
        rows.append({"year": label, "devices": info["count"],
                     "cost": info["count"] * cost,
                     "models": ", ".join(f"{m} ({n})" for m, n in top)})
    return rows


def to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


# ----------------------------------------------------------------- loaners ---
def data_dir() -> str:
    from . import team
    if team.folder():
        return os.path.join(team.folder(), "fleet")
    from PySide6.QtCore import QStandardPaths
    return os.path.join(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or
                        os.path.expanduser("~"), "fleet")


def send_reminders(log=print) -> int:
    from . import google_io
    from .directory import run_gam_text
    n = 0
    for loan in overdue(load_list(data_dir(), "loaners.json")):
        code, _out = run_gam_text(reminder_args(loan, google_io.email_args), 120)
        n += code == 0
        log(f"Loaner reminder to {loan['user']} ({loan['serial']}): "
            f"{'sent' if code == 0 else 'failed'}")
    return n

def _store(folder: str, name: str) -> str:
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, name)


def load_list(folder: str, name: str) -> list[dict]:
    try:
        with open(_store(folder, name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def save_list(folder: str, name: str, items: list[dict]):
    p = _store(folder, name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=1)
    os.replace(tmp, p)


def loaner_out(loans: list[dict], serial: str, user: str, due: str, who: str,
               note: str = "") -> tuple[dict, list[list[str]]]:
    today = datetime.date.today().isoformat()
    rec = {"serial": serial.upper(), "user": user, "out": today, "due": due, "by": who,
           "note": note, "returned": ""}
    loans.append(rec)
    return rec, [["cros_sn", serial, "update", "user", user, "notes",
                  f"LOANER to {user} {today}, due {due}" + (f" – {note}" if note else "")]]


def loaner_in(loans: list[dict], serial: str) -> tuple:
    rec = next((x for x in reversed(loans) if x["serial"] == serial.upper() and
                not x["returned"]), None)
    if not rec:
        return None, []
    rec["returned"] = datetime.date.today().isoformat()
    return rec, [["cros_sn", serial, "update", "user", "", "notes",
                  f"Loaner returned {rec['returned']}"]]


def overdue(loans: list[dict]) -> list[dict]:
    today = datetime.date.today().isoformat()
    return [x for x in loans if not x["returned"] and x.get("due") and x["due"] < today]


REMINDER = ("Hello,\n\nThe loaner Chromebook ({serial}) checked out to you on {out} was due "
            "back on {due}. Please return it to the tech office or library as soon as you "
            "can.\n\nThank you!")


def reminder_args(loan: dict, sender_args) -> list[str]:
    return sender_args(loan["user"], f"Please return your loaner Chromebook ({loan['serial']})",
                       REMINDER.format(**loan))


# ----------------------------------------------------------------- repairs ---
REPAIR_STATES = ["Open", "Sent for repair", "Waiting for parts", "Fixed", "Replaced",
                 "Can't be fixed"]


def repair_open(tickets: list[dict], serial: str, problem: str, who: str,
                dev: dict | None = None) -> tuple[dict, list[list[str]]]:
    n = max([t.get("n", 0) for t in tickets] + [0]) + 1
    today = datetime.date.today().isoformat()
    t = {"n": n, "serial": serial.upper(), "opened": today, "status": "Open",
         "problem": problem, "model": (dev or {}).get("model", ""),
         "user": (dev or {}).get("user") or (dev or {}).get("recent_user", ""),
         "history": [{"date": today, "by": who, "status": "Open", "note": problem}]}
    tickets.append(t)
    return t, [["cros_sn", serial, "update", "notes",
                f"IN REPAIR #{n} since {today}: {problem}"[:500]]]


def repair_update(t: dict, status: str, note: str, who: str) -> list[list[str]]:
    today = datetime.date.today().isoformat()
    t["status"] = status
    t["history"].append({"date": today, "by": who, "status": status, "note": note})
    if status in ("Fixed", "Replaced", "Can't be fixed"):
        t["closed"] = today
        return [["cros_sn", t["serial"], "update", "notes",
                 f"Repair #{t['n']} {status.lower()} {today}" + (f": {note}" if note else "")]]
    return []


def repair_stats(tickets: list[dict]) -> list[dict]:
    by = defaultdict(lambda: {"tickets": 0, "open": 0, "devices": set()})
    for t in tickets:
        m = t.get("model") or "Unknown model"
        by[m]["tickets"] += 1
        by[m]["open"] += t["status"] not in ("Fixed", "Replaced", "Can't be fixed")
        by[m]["devices"].add(t["serial"])
    return [{"model": m, "tickets": v["tickets"], "open": v["open"],
             "devices": len(v["devices"])} for m, v in
            sorted(by.items(), key=lambda kv: -kv[1]["tickets"])]


# ------------------------------------------------------------------ labels ---
_C39 = {
    "0": "bwbWBwBwb", "1": "BwbWbwbwB", "2": "bwBWbwbwB", "3": "BwBWbwbwb",
    "4": "bwbWBwbwB", "5": "BwbWBwbwb", "6": "bwBWBwbwb", "7": "bwbWbwBwB",
    "8": "BwbWbwBwb", "9": "bwBWbwBwb", "A": "BwbwbWbwB", "B": "bwBwbWbwB",
    "C": "BwBwbWbwb", "D": "bwbwBWbwB", "E": "BwbwBWbwb", "F": "bwBwBWbwb",
    "G": "bwbwbWBwB", "H": "BwbwbWBwb", "I": "bwBwbWBwb", "J": "bwbwBWBwb",
    "K": "BwbwbwbWB", "L": "bwBwbwbWB", "M": "BwBwbwbWb", "N": "bwbwBwbWB",
    "O": "BwbwBwbWb", "P": "bwBwBwbWb", "Q": "bwbwbwBWB", "R": "BwbwbwBWb",
    "S": "bwBwbwBWb", "T": "bwbwBwBWb", "U": "BWbwbwbwB", "V": "bWBwbwbwB",
    "W": "BWBwbwbwb", "X": "bWbwBwbwB", "Y": "BWbwBwbwb", "Z": "bWBwBwbwb",
    "-": "bWbwbwBwB", ".": "BWbwbwBwb", " ": "bWBwbwBwb", "*": "bWbwBwBwb",
    "$": "bWbWbWbwb", "/": "bWbWbwbWb", "+": "bWbwbWbWb", "%": "bwbWbWbWb",
}


def code39_bars(text: str) -> list[tuple[bool, int]]:
    """[(is_bar, width_units)] for Code 39 (narrow=1, wide=3), with * start/stop."""
    out = []
    for ch in "*" + "".join(c for c in text.upper() if c in _C39 and c != "*") + "*":
        for i, sym in enumerate(_C39[ch]):
            out.append((i % 2 == 0, 3 if sym.isupper() else 1))
        out.append((False, 1))
    return out

