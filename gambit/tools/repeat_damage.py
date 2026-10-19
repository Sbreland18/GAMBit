"""Repeat-damage report: students with several Chromebook repairs over the years, from
GAMbit's repair tickets and each device's assignment history – for fee, insurance and
loaner decisions."""

from __future__ import annotations

import datetime
from collections import defaultdict

DAMAGE_WORDS = ("crack", "broken", "screen", "drop", "liquid", "spill", "water", "keyboard",
                "hinge", "damage", "bent", "key", "lcd", "smash")


def is_damage(problem: str) -> bool:
    p = (problem or "").lower()
    return any(w in p for w in DAMAGE_WORDS)


def student_for(ticket: dict, history: dict[str, list[dict]]) -> str:
    """Who had the device when the ticket was opened (ticket user, else history)."""
    if ticket.get("user"):
        return ticket["user"].lower()
    for h in sorted(history.get(ticket.get("serial", "").upper(), []),
                    key=lambda x: x.get("date", ""), reverse=True):
        if h.get("date", "") <= ticket.get("opened", "") and h.get("user"):
            return h["user"].lower()
    return ""


def report(tickets: list[dict], users: list[dict], min_repairs: int = 2,
           damage_only: bool = True, years: int = 4, history=None,
           today: datetime.date | None = None) -> list[dict]:
    today = today or datetime.date.today()
    cut = (today - datetime.timedelta(days=365 * years)).isoformat()
    names = {u["email"].lower(): (u.get("name", ""), u.get("ou", ""), u.get("suspended"))
             for u in users}
    by = defaultdict(list)
    for t in tickets:
        if t.get("opened", "") < cut:
            continue
        if damage_only and not is_damage(t.get("problem", "")):
            continue
        who = student_for(t, history or {})
        if who:
            by[who].append(t)
    out = []
    for who, ts in by.items():
        if len(ts) < min_repairs:
            continue
        nm, ou, susp = names.get(who, ("", "", False))
        ts.sort(key=lambda t: t.get("opened", ""))
        out.append({"Student": who, "Name": nm, "Org unit": ou, "Repairs": len(ts),
                    "Last": ts[-1].get("opened", ""),
                    "Devices": len({t.get("serial") for t in ts}),
                    "What happened": "; ".join(f"{t.get('opened', '')}: "
                                               f"{(t.get('problem') or '')[:50]}" for t in ts),
                    "Left": "yes" if susp else ""})
    return sorted(out, key=lambda x: (-x["Repairs"], x["Student"]))


def by_school(rows: list[dict], root: str = "/Students") -> list[dict]:
    from ..parent_report import school_of
    by = defaultdict(lambda: {"Students": 0, "Repairs": 0})
    for r in rows:
        s = school_of(r["Org unit"], root) if r["Org unit"] else "(unknown)"
        by[s]["Students"] += 1
        by[s]["Repairs"] += r["Repairs"]
    return [{"School": k, **v} for k, v in sorted(by.items(), key=lambda x: -x[1]["Repairs"])]


def assignment_history(activity: list[dict]) -> dict[str, list[dict]]:
    """From GAMbit's activity log: serial → [{date, user}] assignments."""
    import re
    out = defaultdict(list)
    for a in activity:
        cmd = a.get("command", "") or ""
        m = re.search(r"cros_sn\s+(\S+)\s+update\b.*?\buser\s+(\S+@\S+)", cmd)
        if m and a.get("code", 0) == 0:
            out[m.group(1).upper()].append({"date": (a.get("time") or "")[:10],
                                            "user": m.group(2).strip("'\"")})
    return dict(out)
