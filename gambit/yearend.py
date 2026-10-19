"""Year-end rollover in one place: a dated checklist that ties the graduation, Classroom,
guardian, device-collection and clean-up tools together, with sign-off requests through
Approvals and reminders from the daily background task."""

from __future__ import annotations

import datetime
import json

from .settings import settings

# key, title, days relative to the last day of school, page, tab, what to do, sign-off
STEPS = [
    ("collect_plan", "Plan the summer Chromebook collection", -21, "Chromebook fleet",
     "Summer collection", "Start a collection list for each school so scanning can begin on "
     "the last week.", False),
    ("withdrawn", "Collect devices from students who left during the year", -14,
     "Chromebook fleet", "Withdrawn students' devices",
     "Clear the “to collect” list before families leave for the summer.", False),
    ("signoff_grad", "Principals confirm the graduating seniors", -7, "Workflows",
     "Graduation", "Send the senior list for sign-off before anything changes.", True),
    ("collect", "Summer Chromebook collection", 0, "Chromebook fleet", "Summer collection",
     "Scan devices in; email the “not returned” list to each school.", False),
    ("graduation", "Graduate the seniors", 3, "Workflows", "Graduation",
     "Run the graduation workflow (alumni org unit, data transfer, later deletion).", False),
    ("archive", "Archive last year's Classroom classes", 7, "Classroom", "Yearly setup",
     "Archive the old classes so teachers start clean.", False),
    ("signoff_move", "Sign-off: move students up a grade", 10, "Workflows",
     "Year-end rollover", "Ask for approval before the grade move runs.", True),
    ("move_up", "Move students up a grade", 14, "Workflows", "Year-end rollover",
     "Run the grade move (bottom row first).", False),
    ("cleanup", "Run the clean-up rules", 21, "Clean-up rules", "",
     "Check all rules – long-inactive and leftover suspended accounts go to Approvals.",
     False),
    ("budget", "Review licenses and the device budget", 28, "Budget planner", "",
     "Free licenses from leavers and plan next year's Chromebook replacements.", False),
    ("roster", "Load next year's roster", 50, "Roster sync", "",
     "Run roster sync with the new-year SIS data (new students, new schools).", False),
    ("classes", "Create the new school year's classes", 55, "Classroom", "Yearly setup",
     "Create classes from the SIS sections.", False),
    ("guardians", "Refresh guardian invitations", 58, "Classroom", "Guardian sync",
     "Invite parents for the new classes.", False),
    ("assign", "Hand out Chromebooks and run the assignment sync", 60, "Chromebook fleet",
     "Assignment sync", "Match devices to students for the new year.", False),
]
STATUS = ("To do", "Done", "Skipped")


def _shared():
    from . import team
    return team.folder()


def load() -> dict:
    from . import team
    d = team.read_shared("yearend.json") if _shared() else {}
    if not d:
        try:
            d = json.loads(settings.get("yearend/plan", "{}") or "{}")
        except ValueError:
            d = {}
    return {"last_day": "", "items": {}, "owners": {}, **d}


def save(plan: dict):
    from . import team
    if _shared():
        team.write_shared("yearend.json", plan)
    settings.set("yearend/plan", json.dumps(plan))


def default_last_day(today: datetime.date | None = None) -> datetime.date:
    today = today or datetime.date.today()
    year = today.year if today.month <= 6 else today.year + 1
    d = datetime.date(year, 5, 31)
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d


def last_day(plan: dict) -> datetime.date:
    try:
        return datetime.date.fromisoformat(plan.get("last_day", ""))
    except ValueError:
        return default_last_day()


def rows(plan: dict, today: datetime.date | None = None) -> list[dict]:
    from . import team
    today = today or datetime.date.today()
    base = last_day(plan)
    reqs = {r["id"]: r for r in team.list_requests()} if _shared() else {}
    out = []
    for key, title, off, page, tab, what, signoff in STEPS:
        st = plan["items"].get(key, {})
        due = base + datetime.timedelta(days=off)
        status = st.get("status", "To do")
        req = reqs.get(st.get("request", ""))
        if signoff and req and status == "To do":
            if req.get("status") in ("approved", "done"):
                status = "Done"
            elif req.get("status") == "denied":
                status = "To do"
        state = status
        if status == "To do":
            if req and req.get("status") == "pending":
                state = "Waiting for sign-off"
            elif due < today:
                state = "Overdue"
            elif due <= today + datetime.timedelta(days=7):
                state = "Due this week"
        out.append({"key": key, "title": title, "due": due.isoformat(), "page": page,
                    "tab": tab, "what": what, "signoff": signoff, "status": status,
                    "state": state, "owner": plan["owners"].get(key, ""),
                    "done_by": st.get("by", ""), "done_at": st.get("at", ""),
                    "request": st.get("request", ""),
                    "request_status": (req or {}).get("status", "")})
    return out


def progress(rs: list[dict]) -> tuple[int, int]:
    return sum(1 for r in rs if r["status"] in ("Done", "Skipped")), len(rs)


def mark(plan: dict, key: str, status: str, who: str):
    plan["items"][key] = {**plan["items"].get(key, {}), "status": status, "by": who,
                          "at": datetime.datetime.now().isoformat(timespec="minutes")}
    save(plan)


def ask_signoff(plan: dict, key: str, details: str = "") -> dict:
    from . import team
    step = next(s for s in STEPS if s[0] == key)
    req = team.new_request([], f"Year-end sign-off: {step[1]}.\n{step[5]}" +
                           (f"\n\n{details}" if details else ""),
                           title=f"Year-end: {step[1]}", extra={"kind": "yearend",
                                                                 "step": key})
    plan["items"][key] = {**plan["items"].get(key, {}), "request": req["id"]}
    save(plan)
    return req


def reminders(plan: dict, today: datetime.date | None = None) -> list[str]:
    """Lines for anything overdue or due in the next 3 days."""
    today = today or datetime.date.today()
    soon = (today + datetime.timedelta(days=3)).isoformat()
    out = []
    for r in rows(plan, today):
        if r["status"] != "To do" or r["state"] == "Waiting for sign-off":
            continue
        if r["due"] <= soon:
            late = "OVERDUE" if r["due"] < today.isoformat() else "due"
            out.append(f"• {r['title']} – {late} {r['due']}" +
                       (f" ({r['owner']})" if r["owner"] else "") +
                       f" → GAMbit: {r['page']}" + (f" → {r['tab']}" if r["tab"] else ""))
    return out


def send_reminders(log=print, today: datetime.date | None = None) -> int:
    """Daily task: one alert/email listing what's due. Sent once per day at most."""
    today = today or datetime.date.today()
    plan = load()
    if not plan.get("reminders"):
        return 0
    base = last_day(plan)
    if not (base - datetime.timedelta(days=30) <= today <= base + datetime.timedelta(days=75)):
        return 0
    if settings.get("yearend/last_reminder", "") == today.isoformat():
        return 0
    lines = reminders(plan, today)
    if not lines:
        return 0
    from . import alerts
    owners = sorted({o for o in plan["owners"].values() if "@" in o})
    text = "Year-end checklist – needs attention:\n" + "\n".join(lines)
    alerts.notify(text, "GAMbit year-end checklist")
    if owners:
        try:
            from . import google_io
            google_io.send_email(",".join(owners), "GAMbit year-end checklist", text)
        except Exception as exc:  # noqa: BLE001
            log(f"Couldn't email the owners: {exc}")
    settings.set("yearend/last_reminder", today.isoformat())
    log(f"Year-end reminder sent ({len(lines)} item(s)).")
    return len(lines)
