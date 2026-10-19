"""Guardian follow-up: re-send guardian invitations nobody answered in N days, cancel
invitations to addresses that look wrong (typos like gmial.com), and track acceptance by
school and by teacher. Can run every week from the daily task."""

from __future__ import annotations

import datetime
import json
import re
from collections import defaultdict

from .settings import settings

TASK_NOTE = "guardian follow-up"
TYPO_DOMAINS = {"gmial.com", "gmai.com", "gmal.com", "gamil.com", "gmail.co", "gnail.com",
                "yahooo.com", "yaho.com", "hotmial.com", "hotmai.com", "outlok.com",
                "iclod.com", "icould.com", "gmail.con", "yahoo.con", "hotmail.con"}


def options() -> dict:
    try:
        o = json.loads(settings.get("guardianfu/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"root": "/Students", "days": 14, "max_resends": 2, "weekly": False, **o}


def save_options(o: dict):
    settings.set("guardianfu/options", json.dumps(o))


def looks_wrong(email: str) -> str:
    e = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", e):
        return "not a valid email address"
    dom = e.split("@", 1)[1]
    if dom in TYPO_DOMAINS:
        return f"probable typo ({dom})"
    return ""


def _resent() -> dict:
    try:
        return json.loads(settings.get("guardianfu/resent", "{}") or "{}")
    except ValueError:
        return {}


def plan(current: list[dict], days: int, today: datetime.date | None = None,
         max_resends: int = 2) -> tuple[list[dict], list[dict]]:
    """→ (resend [{student, guardian, since, args}], cancel [{… why, args}])"""
    from .tools.gam_extras2 import cancel_guardian_args
    today = today or datetime.date.today()
    cut = (today - datetime.timedelta(days=days)).isoformat()
    accepted = {(c["student"], c["guardian"]) for c in current if c["kind"] == "guardian"}
    sent = _resent()
    resend, cancel = [], []
    for c in current:
        if c["kind"] != "invitation" or c["state"] != "PENDING":
            continue
        if (c["student"], c["guardian"]) in accepted:
            continue
        bad = looks_wrong(c["guardian"])
        if bad:
            cancel.append({"Student": c["student"], "Guardian": c["guardian"], "Why": bad,
                           "args": [cancel_guardian_args(c["id"], c["student"])]})
            continue
        if c["since"] and c["since"] <= cut:
            key = f"{c['student']}|{c['guardian']}"
            if sent.get(key, 0) >= max_resends:
                continue
            resend.append({"Student": c["student"], "Guardian": c["guardian"],
                           "Invited": c["since"], "Times re-sent": sent.get(key, 0),
                           "args": [cancel_guardian_args(c["id"], c["student"]),
                                    ["user", c["student"], "create", "guardian",
                                     c["guardian"]]]})
    return resend, cancel


def note_resent(items: list[dict]):
    sent = _resent()
    for i in items:
        key = f"{i['Student']}|{i['Guardian']}"
        sent[key] = sent.get(key, 0) + 1
    settings.set("guardianfu/resent", json.dumps(sent))


def acceptance(current: list[dict], users: list[dict], root: str,
               teachers: dict | None = None, students_of: dict | None = None) -> tuple:
    """→ (by school rows, by teacher rows)"""
    from .parent_report import school_of
    stu = {u["email"].lower(): u.get("ou", "") for u in users if not u.get("suspended")}
    rl = root.rstrip("/").lower()
    stu = {e: ou for e, ou in stu.items() if ou.lower().startswith(rl + "/")}
    has = defaultdict(lambda: {"accepted": False, "pending": False})
    for c in current:
        h = has[c["student"]]
        if c["kind"] == "guardian":
            h["accepted"] = True
        elif c["state"] == "PENDING":
            h["pending"] = True

    def tally(group):
        n = len(group)
        a = sum(1 for e in group if has[e]["accepted"])
        p = sum(1 for e in group if not has[e]["accepted"] and has[e]["pending"])
        return {"Students": n, "Accepted": a, "Waiting": p, "None invited": n - a - p,
                "Accepted %": round(100 * a / n) if n else 0}
    schools = defaultdict(list)
    for e, ou in stu.items():
        schools[school_of(ou, root)].append(e)
    by_school = [{"School": s, **tally(g)} for s, g in sorted(schools.items())]
    by_teacher = []
    for t, cids in (teachers or {}).items():
        group = sorted({s for c in cids for s in (students_of or {}).get(c, []) if s in stu})
        if group:
            by_teacher.append({"Teacher": t, **tally(group)})
    by_teacher.sort(key=lambda x: x["Accepted %"])
    return by_school, by_teacher


def run(log=print, run_text=None, today=None) -> list[str]:
    """Weekly (from the daily task, Mondays): re-send and cancel automatically."""
    from . import activity, guardians
    from .directory import run_gam_text
    o = options()
    today = today or datetime.date.today()
    if not o.get("weekly") or today.weekday() != 0:
        return []
    run_text = run_text or run_gam_text
    c, out = run_text(["ou_and_children", o["root"], "print", "guardians", "all",
                       "showstudentemails"], 3600)
    if c != 0:
        log("Guardian follow-up: couldn't read guardians.")
        return []
    resend, cancel = plan(guardians.parse_current(out), int(o["days"]), today,
                          int(o["max_resends"]))
    prof = settings.get("profile/current", "") or "Default"
    sent = []
    for item in cancel + resend:
        ok = True
        for a in item["args"]:          # cancel first; only re-invite if that worked
            if not ok:
                break
            code, _o = run_text(a, 300)
            activity.record(a, code, "done" if code == 0 else "failed", None, prof,
                            note=TASK_NOTE)
            ok = code == 0
        if ok and item in resend:
            sent.append(item)
    note_resent(sent)
    lines = [f"Guardian follow-up: re-sent {len(sent)} of {len(resend)}, cancelled "
             f"{len(cancel)}."]
    for ln in lines:
        log(ln)
    return lines
