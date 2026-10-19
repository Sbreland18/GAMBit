"""Chromebook history and repair hotspots.

timeline()  – everything GAMbit knows about one device in date order: GAMbit changes,
              assignments, repairs, loaners, collections, devices-to-collect and tickets.
hotspots()  – which models and schools break most (repairs per 100 devices, days to fix).
loaners()   – how many loaners each school really needs, from loan and repair history.
"""

from __future__ import annotations

import datetime
import math
from collections import defaultdict

CLOSED = ("Fixed", "Replaced", "Can't be fixed")


def _d(text: str):
    try:
        return datetime.date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def timeline(serial: str, activity: list[dict], repairs: list[dict], loans: list[dict],
             withdrawn: list[dict], collection: dict | None = None,
             tickets: list[dict] | None = None) -> list[dict]:
    sn = (serial or "").strip().upper()
    out = []

    def add(when, what, details, source):
        out.append({"When": (when or "")[:16].replace("T", " "), "What": what,
                    "Details": details, "Source": source})
    for e in activity:
        cmd = e.get("command", "")
        if sn and sn in cmd.upper() and e.get("change", True):
            ok = e.get("code") == 0
            add(e.get("time", ""), "Changed with GAMbit" if ok else "GAMbit change failed",
                f"{cmd}  ({e.get('who', '')})", "Activity log")
    for t in repairs:
        if (t.get("serial") or "").upper() != sn:
            continue
        for h in t.get("history", []):
            add(h.get("date", ""), f"Repair #{t.get('n')}: {h.get('status')}",
                f"{h.get('note', '')} ({h.get('by', '')})".strip(), "Repairs")
    for ln in loans:
        if (ln.get("serial") or "").upper() != sn:
            continue
        add(ln.get("out", ""), "Loaned out", f"to {ln.get('user')} – due {ln.get('due')}",
            "Loaners")
        if ln.get("returned"):
            add(ln["returned"], "Loaner returned", ln.get("user", ""), "Loaners")
    for w in withdrawn:
        if (w.get("serial") or "").upper() != sn:
            continue
        add(w.get("flagged", ""), "Flagged to collect", f"{w.get('user')} left", "Withdrawn")
        if w.get("collected"):
            add(w["collected"], "Collected", f"by {w.get('by', '')}", "Withdrawn")
    if collection and sn in (collection.get("collected") or {}):
        c = collection["collected"][sn]
        add(c.get("time", ""), "Summer collection: checked in",
            f"{collection.get('name', '')} – by {c.get('by', '')}", "Collection")
    for t in tickets or []:
        if (t.get("serial") or "").upper() == sn or sn in (t.get("subject", "") +
                                                           t.get("description", "")).upper():
            add(t.get("created", ""), f"Ticket #{t.get('number')}", t.get("subject", ""),
                "Help desk")
    out.sort(key=lambda r: r["When"], reverse=True)
    return out


def hotspots(devs: list[dict], repairs: list[dict], by: str = "model",
             school_of=None, months: int = 12,
             today: datetime.date | None = None) -> list[dict]:
    """Repairs per 100 devices by model or by school (school_of(device) → name)."""
    today = today or datetime.date.today()
    since = today - datetime.timedelta(days=30 * months)
    key = (lambda d: d.get("model") or "Unknown model") if by == "model" else \
        (lambda d: (school_of(d) if school_of else d.get("ou", "")) or "(unknown)")
    devices = defaultdict(int)
    dev_key = {}
    for d in devs:
        if d.get("status", "ACTIVE") != "ACTIVE":
            continue
        k = key(d)
        devices[k] += 1
        dev_key[d["serial"].upper()] = k
    rep = defaultdict(lambda: {"n": 0, "open": 0, "days": [], "serials": set()})
    for t in repairs:
        opened = _d(t.get("opened", ""))
        if not opened or opened < since:
            continue
        k = dev_key.get((t.get("serial") or "").upper())
        if k is None:
            k = (t.get("model") or "Unknown model") if by == "model" else "(not in fleet)"
        r = rep[k]
        r["n"] += 1
        r["serials"].add(t.get("serial"))
        if t.get("status") not in CLOSED:
            r["open"] += 1
        elif _d(t.get("closed", "")):
            r["days"].append((_d(t["closed"]) - opened).days)
    rows = []
    for k in sorted(set(devices) | set(rep)):
        n, r = devices.get(k, 0), rep.get(k, {"n": 0, "open": 0, "days": [], "serials": set()})
        rows.append({"Group": k, "Devices": n, "Repairs": r["n"],
                     "Per 100 devices": round(100 * r["n"] / n, 1) if n else None,
                     "Devices repaired": len(r["serials"]), "Open now": r["open"],
                     "Avg days to fix": round(sum(r["days"]) / len(r["days"]), 1)
                     if r["days"] else None})
    rows.sort(key=lambda x: -(x["Per 100 devices"] or 0))
    return rows


def peak_out(loans: list[dict], today: datetime.date | None = None) -> int:
    """Most loaners out at the same time."""
    today = today or datetime.date.today()
    ev = []
    for ln in loans:
        a = _d(ln.get("out", ""))
        if not a:
            continue
        b = _d(ln.get("returned", "")) or today
        ev += [(a, 1), (b + datetime.timedelta(days=1), -1)]
    cur = peak = 0
    for _d0, delta in sorted(ev):
        cur += delta
        peak = max(peak, cur)
    return peak


def avg_open_repairs(repairs: list[dict], weeks: int = 26,
                     today: datetime.date | None = None) -> float:
    today = today or datetime.date.today()
    total = 0
    for w in range(weeks):
        day = today - datetime.timedelta(days=7 * w)
        for t in repairs:
            a, b = _d(t.get("opened", "")), _d(t.get("closed", "")) or today
            if a and a <= day <= b:
                total += 1
    return total / weeks if weeks else 0.0


def loaners(loans: list[dict], repairs: list[dict], school_of_serial=None,
            school_of_user=None, today: datetime.date | None = None) -> list[dict]:
    """Per school: peak loaners out, average devices in repair, recommended pool."""
    school_of_serial = school_of_serial or (lambda s: "")
    school_of_user = school_of_user or (lambda u: "")
    by_l, by_r = defaultdict(list), defaultdict(list)
    for ln in loans:
        s = school_of_user(ln.get("user", "")) or school_of_serial(ln.get("serial", "")) or \
            "(unknown)"
        by_l[s].append(ln)
    for t in repairs:
        s = school_of_serial(t.get("serial", "")) or school_of_user(t.get("user", "")) or \
            "(unknown)"
        by_r[s].append(t)
    rows = []
    for s in sorted(set(by_l) | set(by_r)):
        pk = peak_out(by_l[s], today)
        avg = avg_open_repairs(by_r[s], today=today)
        out_now = sum(1 for ln in by_l[s] if not ln.get("returned"))
        rows.append({"School": s, "Loaners out now": out_now, "Most out at once": pk,
                     "Avg in repair": round(avg, 1),
                     "Suggested loaner pool": max(1, math.ceil(max(pk, avg) * 1.2))})
    return rows
