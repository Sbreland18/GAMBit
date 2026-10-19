"""Calendar in bulk (events on many calendars, subscriptions, a leaver's future meetings)
and Classroom coursework (missing work, copying assignments between sections)."""

from __future__ import annotations

import datetime
import json
import uuid

from ..settings import settings


# ============================================================ calendar ===
def _iso(dt: datetime.datetime) -> str:
    return dt.astimezone().isoformat(timespec="seconds")


def event_args(entity: list[str], summary: str, *, allday: datetime.date | None = None,
               start: datetime.datetime | None = None, end: datetime.datetime | None = None,
               location: str = "", description: str = "", busy: bool = False,
               batch: str = "") -> list[str]:
    a = [*entity, "create", "event", "primary", "summary", summary]
    if allday:
        a += ["allday", allday.isoformat()]
    else:
        a += ["start", _iso(start), "end", _iso(end)]
    if location:
        a += ["location", location]
    if description:
        a += ["description", description]
    a += ["transparency", "opaque" if busy else "transparent", "noreminders"]
    if batch:
        a += ["privateproperty", "gambitbatch", batch]
    return a


def new_batch() -> str:
    return datetime.date.today().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6]


def remove_batch_args(entity: list[str], batch: str) -> list[str]:
    return [*entity, "delete", "events", "primary", "privateextendedproperty",
            f"gambitbatch={batch}", "doit"]


def batches() -> list[dict]:
    try:
        return json.loads(settings.get("calendar/batches", "[]") or "[]")
    except ValueError:
        return []


def save_batch(batch: str, summary: str, entity: list[str], when: str):
    b = [x for x in batches() if x["id"] != batch]
    b.insert(0, {"id": batch, "summary": summary, "entity": entity, "when": when,
                 "added": datetime.datetime.now().isoformat(timespec="minutes")})
    settings.set("calendar/batches", json.dumps(b[:50]))


def forget_batch(batch: str):
    settings.set("calendar/batches", json.dumps([x for x in batches() if x["id"] != batch]))


def subscribe_args(entity: list[str], calendar_id: str) -> list[str]:
    return [*entity, "add", "calendars", calendar_id, "selected", "true"]


def unsubscribe_args(entity: list[str], calendar_id: str) -> list[str]:
    return [*entity, "delete", "calendars", calendar_id]


def future_meetings_args(user: str) -> list[str]:
    return ["user", user, "print", "events", "primary", "after", _iso(datetime.datetime.now()),
            "matchfield", "organizerself", "true", "singleevents",
            "fields", "summary,start,attendees"]


def cancel_future_args(user: str, notify: bool = True) -> list[str]:
    a = ["user", user, "delete", "events", "primary", "after", _iso(datetime.datetime.now()),
         "matchfield", "organizerself", "true", "singleevents", "doit"]
    return a + (["notifyattendees"] if notify else ["sendupdates", "none"])


def meetings(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = {(k or "").lower(): v or "" for k, v in r.items()}
        start = low.get("start.datetime") or low.get("start.date") or ""
        n = sum(1 for k in low if k.startswith("attendees.") and k.endswith(".email") and low[k])
        out.append({"Meeting": low.get("summary", ""), "Starts": start.replace("T", " ")[:16],
                    "Guests": str(n)})
    return out


# ============================================================ classroom ===
def scope(course: str = "", teacher: str = "") -> list[str]:
    if course:
        return ["course", course]
    return ["teacher", teacher, "states", "active"]


def coursework_args(sc: list[str]) -> list[str]:
    return ["print", "course-works", *sc, "workstates", "published",
            "fields", "id,title,duedate,courseid"]


def missing_args(sc: list[str]) -> list[str]:
    return ["print", "course-submissions", *sc, "submissionstates", "new,created", "late",
            "showuserprofile"]


def courses_args(sc: list[str]) -> list[str]:
    if sc[0] == "course":
        return ["print", "courses", "course", sc[1], "fields", "id,name,section"]
    return ["print", "courses", "teacher", sc[1], "states", "active",
            "fields", "id,name,section"]


def _date(low: dict) -> str:
    y, m, d = low.get("duedate.year"), low.get("duedate.month"), low.get("duedate.day")
    return f"{y}-{int(m):02d}-{int(d):02d}" if y and m and d else ""


def missing(subs: list[dict], works: list[dict], courses: list[dict]) -> list[dict]:
    wk = {}
    for w in works:
        low = {(k or "").lower(): v or "" for k, v in w.items()}
        wk[(low.get("courseid", ""), low.get("id", ""))] = (low.get("title", ""), _date(low))
    cn = {}
    for c in courses:
        low = {(k or "").lower(): v or "" for k, v in c.items()}
        cn[low.get("id", "")] = " – ".join(x for x in (low.get("name"), low.get("section")) if x)
    out = []
    for s in subs:
        low = {(k or "").lower(): v or "" for k, v in s.items()}
        cid, wid = low.get("courseid", ""), low.get("courseworkid", "")
        title, due = wk.get((cid, wid), ("", ""))
        student = (low.get("profile.emailaddress") or low.get("profile.name.fullname")
                   or low.get("userid", ""))
        out.append({"Class": cn.get(cid, cid), "Student": student,
                    "Name": low.get("profile.name.fullname", ""),
                    "Assignment": title or wid, "Due": due})
    out.sort(key=lambda x: (x["Class"], x["Student"], x["Due"]))
    return out


def by_student(rows: list[dict]) -> list[dict]:
    counts: dict[tuple, int] = {}
    for r in rows:
        k = (r["Student"], r["Name"])
        counts[k] = counts.get(k, 0) + 1
    return [{"Student": s, "Name": n, "Missing": str(c)}
            for (s, n), c in sorted(counts.items(), key=lambda x: -x[1])]


def copy_args(source: str, target: str, drafts: bool = True) -> list[str]:
    a = ["update", "course", target, "copyfrom", source, "workstates", "published,draft",
         "materialstates", "published,draft", "copytopics", "true",
         "individualstudentassignments", "maptoall", "members", "none"]
    if drafts:
        a += ["markpublishedasdraft", "true"]
    return a
