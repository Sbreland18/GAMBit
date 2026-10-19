"""Stale content to archive: shared drives nobody has changed in years, Classroom classes
with no posts or assignments this school year, and empty groups. Every clean-up goes
through Approvals (or runs, if you're allowed) with one click."""

from __future__ import annotations

import datetime
import json

from ..settings import settings

COURSES_ARGS = ["print", "courses", "states", "active", "fields",
                "id,name,section,owneremail,creationtime,updatetime"]


def options() -> dict:
    try:
        o = json.loads(settings.get("stale/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"drive_years": 2, "keep": "", "check_drives": True, "check_classes": True,
            "check_groups": True, "as_user": "", **o}


def save_options(o: dict):
    settings.set("stale/options", json.dumps(o))


def year_start(today: datetime.date | None = None) -> datetime.date:
    today = today or datetime.date.today()
    return datetime.date(today.year if today.month >= 7 else today.year - 1, 7, 1)


def lastmod_args(user: str, drive_id: str) -> list[str]:
    return ["user", user, "print", "drivelastmodification", "select", drive_id]


def counts_args(kind: str, start: datetime.date) -> list[str]:
    return ["print", kind, "states", "active", "timefilter", "updatetime", "start",
            start.isoformat(), "countsonly"]


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _d(t):
    try:
        return datetime.date.fromisoformat((t or "")[:10])
    except ValueError:
        return None


def _keep(name: str, keep: str) -> bool:
    words = [w.strip().lower() for w in (keep or "").split(",") if w.strip()]
    return any(w in (name or "").lower() for w in words)


def stale_drives(drives: list[dict], lastmod: dict[str, str], years: int, keep: str = "",
                 today: datetime.date | None = None) -> list[dict]:
    today = today or datetime.date.today()
    cut = today - datetime.timedelta(days=int(365 * years))
    out = []
    for d in drives:
        if _keep(d["Name"], keep):
            continue
        last = _d(lastmod.get(d["id"], ""))
        created = _d(d.get("Created"))
        if last is None and lastmod.get(d["id"], "") == "?":
            continue            # couldn't check
        if (last and last < cut) or (last is None and created and created < cut):
            out.append({"Kind": "Shared drive", "Name": d["Name"],
                        "Last change": last.isoformat() if last else "never",
                        "Why": f"nothing changed for {years}+ years",
                        "Action": "Hide it (it can be un-hidden)",
                        "args": ["hide", "shareddrive", d["id"]], "id": d["id"]})
    return out


def stale_classes(courses: list[dict], works: list[dict], posts: list[dict],
                  today: datetime.date | None = None, keep: str = "") -> list[dict]:
    start = year_start(today)
    busy = set()
    for rows, col in ((works, "coursework"), (posts, "courseannouncements")):
        for r in rows:
            low = _low(r)
            n = next((v for k, v in low.items() if k.startswith(col) or k.endswith("count")),
                     "0")
            try:
                if int(float(n or 0)) > 0:
                    busy.add(low.get("courseid", ""))
            except ValueError:
                pass
    out = []
    for c in courses:
        low = _low(c)
        cid = low.get("id", "")
        created = _d(low.get("creationtime"))
        name = " – ".join(x for x in (low.get("name"), low.get("section")) if x)
        if not cid or cid in busy or _keep(name, keep):
            continue
        if created and created >= start:
            continue            # made this year – give it time
        out.append({"Kind": "Classroom class", "Name": name,
                    "Last change": (low.get("updatetime") or "")[:10],
                    "Why": f"no posts or assignments since {start:%b %Y}; owner "
                           f"{low.get('owneremail', '?')}",
                    "Action": "Archive it (students keep read-only access)",
                    "args": ["update", "course", cid, "state", "archived"], "id": cid})
    return out


def empty_groups(groups: list[dict], keep: str = "") -> list[dict]:
    out = []
    for g in groups:
        try:
            n = int(g.get("members") or 0)
        except ValueError:
            continue
        if n == 0 and not _keep(g["email"] + " " + g.get("name", ""), keep):
            out.append({"Kind": "Group", "Name": g["email"], "Last change": "",
                        "Why": "no members", "Action": "Delete the group",
                        "args": ["delete", "group", g["email"]], "id": g["email"]})
    return out


def lastmod_value(rows: list[dict]) -> str:
    for r in rows:
        low = _low(r)
        if low.get("lastmodifiedtime"):
            return low["lastmodifiedtime"][:10]
    return ""


def scan(run_csv, groups: list[dict], opts: dict, admin: str,
         today: datetime.date | None = None) -> tuple[list[dict], list[str]]:
    from .gam_extras import SHARED_DRIVES_ARGS, shared_drives
    out, probs = [], []
    if opts.get("check_drives", True):
        c, rows, e = run_csv(SHARED_DRIVES_ARGS)
        if c == 0:
            drives = shared_drives(rows)
            lm = {}
            who = opts.get("as_user") or admin
            for d in drives:
                c2, r2, _e = run_csv(lastmod_args(who, d["id"]))
                lm[d["id"]] = lastmod_value(r2) if c2 == 0 else "?"
            bad = sum(1 for v in lm.values() if v == "?")
            if bad:
                probs.append(f"{bad} shared drive(s) couldn't be checked ({who} isn't a "
                             "member) – add them as a manager or use Ownership check.")
            out += stale_drives(drives, lm, int(opts.get("drive_years", 2) or 2),
                                opts.get("keep", ""), today)
        else:
            probs.append("shared drives: " + (e or "").strip()[-120:])
    if opts.get("check_classes", True):
        st = year_start(today)
        c, courses, e = run_csv(COURSES_ARGS)
        if c == 0:
            c1, works, e1 = run_csv(counts_args("course-works", st))
            c2, posts, e2 = run_csv(counts_args("course-announcements", st))
            if c1 == 0 and c2 == 0:
                out += stale_classes(courses, works, posts, today, opts.get("keep", ""))
            else:   # without activity counts every class would look unused
                probs.append("classes skipped – couldn't count Classroom posts: " +
                             ((e1 if c1 else e2) or "").strip()[-120:])
        else:
            probs.append("classes: " + (e or "").strip()[-120:])
    if opts.get("check_groups", True):
        out += empty_groups(groups, opts.get("keep", ""))
    return out, probs
