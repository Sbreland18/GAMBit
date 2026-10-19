"""Meet attendance for e-learning days: compare who joined a teacher's Google Meet (and for
how long) with the Classroom roster, from Google's Meet audit log (call_ended events carry
the participant's email, the meeting code and the minutes in the call)."""

from __future__ import annotations

import datetime
from collections import defaultdict

from .tools.gam_extras2 import meet_code


def report_args(organizer: str, day: datetime.date) -> list[str]:
    # local midnight → 6 AM next day, with this PC's UTC offset (the Reports API needs one)
    start = datetime.datetime.combine(day, datetime.time()).astimezone()
    end = datetime.datetime.combine(day + datetime.timedelta(days=1),
                                    datetime.time(6)).astimezone()
    return ["report", "meet", "user", "all", "start", start.isoformat(timespec="seconds"),
            "end", end.isoformat(timespec="seconds"), "events", "call_ended",
            "filter", f"organizer_email=={organizer}"]


def roster_args(course: str) -> list[str]:
    return ["print", "course-participants", "course", course, "show", "students"]


def _norm_code(c: str) -> str:
    return (c or "").replace("-", "").lower()


def sessions(rows: list[dict], code: str = "") -> dict[str, dict]:
    """email → {minutes, joins, first, last, name}; only this meeting code if given."""
    want = _norm_code(meet_code(code) or code)
    out: dict[str, dict] = defaultdict(lambda: {"minutes": 0.0, "joins": 0, "first": "",
                                                "last": "", "name": ""})
    for r in rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        if want and _norm_code(low.get("meeting_code", "")) != want:
            continue
        who = (low.get("identifier") or low.get("actor.email") or "").lower()
        if not who:
            who = "(guest) " + (low.get("display_name") or "unknown")
        try:
            secs = float(low.get("duration_seconds") or 0)
        except ValueError:
            secs = 0.0
        t = low.get("id.time", "")
        s = out[who]
        s["minutes"] += secs / 60
        s["joins"] += 1
        s["name"] = s["name"] or low.get("display_name", "")
        s["first"] = min(filter(None, [s["first"], t]), default=t)
        s["last"] = max(s["last"], t)
    return dict(out)


def codes(rows: list[dict]) -> list[tuple[str, int]]:
    """The meeting codes this organizer used that day, busiest first."""
    c: dict[str, set] = defaultdict(set)
    for r in rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        mc = low.get("meeting_code", "")
        if mc:
            c[mc].add((low.get("identifier") or low.get("display_name") or "").lower())
    return sorted(((k, len(v)) for k, v in c.items()), key=lambda x: -x[1])


def roster(rows: list[dict]) -> dict[str, str]:
    out = {}
    for r in rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        e = (low.get("profile.emailaddress") or "").lower()
        if e and low.get("userrole", "STUDENT").upper() == "STUDENT":
            out[e] = low.get("profile.name.fullname", "")
    return out


def attendance(students: dict[str, str], sess: dict[str, dict], min_minutes: int = 10,
               teacher: str = "") -> list[dict]:
    out = []
    for e, name in sorted(students.items(), key=lambda x: x[1] or x[0]):
        s = sess.get(e)
        mins = round(s["minutes"]) if s else 0
        status = "Absent" if not s else ("Present" if mins >= min_minutes else "Partial")
        out.append({"Student": e, "Name": name, "Status": status, "Minutes": mins,
                    "Joined": s["first"][11:16] if s and s["first"] else "",
                    "Times joined": s["joins"] if s else 0})
    extra = [e for e in sess if e not in students and e != teacher.lower()]
    for e in sorted(extra):
        s = sess[e]
        out.append({"Student": e, "Name": s["name"], "Status": "Not on the roster",
                    "Minutes": round(s["minutes"]), "Joined": s["first"][11:16],
                    "Times joined": s["joins"]})
    return out


def summary(rows: list[dict]) -> dict:
    c = defaultdict(int)
    for r in rows:
        c[r["Status"]] += 1
    return dict(c)


def email_text(class_name: str, day: datetime.date, rows: list[dict]) -> str:
    s = summary(rows)
    lines = [f"Meet attendance – {class_name} – {day:%A %B %d, %Y}",
             ", ".join(f"{k}: {v}" for k, v in s.items()), ""]
    for status in ("Absent", "Partial", "Present", "Not on the roster"):
        group = [r for r in rows if r["Status"] == status]
        if group:
            lines.append(f"{status}:")
            lines += [f"  • {r['Name'] or r['Student']} ({r['Student']})"
                      + (f" – {r['Minutes']} min" if r["Minutes"] else "") for r in group]
    return "\n".join(lines)
