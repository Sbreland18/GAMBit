"""AI use dashboard: Gemini activity from Google's audit log, by school, grade and week, and
use from org units where your AI policy says it shouldn't happen."""

from __future__ import annotations

import datetime
import json
from collections import defaultdict

from .settings import settings


def options() -> dict:
    try:
        o = json.loads(settings.get("aiuse/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"days": 30, "root": "/Students", "not_allowed": "", "app": "gemini", **o}


def save_options(o: dict):
    settings.set("aiuse/options", json.dumps(o))


def args(days: int, app: str = "gemini") -> list[str]:
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    return ["report", app, "user", "all", "start", start]


def _under(ou: str, roots: list[str]) -> bool:
    ou = (ou or "").rstrip("/").lower()
    return any(ou == r or ou.startswith(r + "/") for r in roots)


def analyze(rows: list[dict], users: list[dict], opts: dict) -> dict:
    from .parent_report import school_of
    ou_of = {u["email"].lower(): u.get("ou", "") for u in users}
    root = opts.get("root", "/Students")
    rl = root.rstrip("/").lower()
    banned = [x.strip().rstrip("/").lower() for x in (opts.get("not_allowed") or "").split(",")
              if x.strip()]
    by_place = defaultdict(lambda: {"events": 0, "people": set()})
    by_week = defaultdict(lambda: {"Students": set(), "Staff": set(), "events": 0})
    by_event = defaultdict(int)
    flagged = defaultdict(lambda: {"events": 0, "last": ""})
    for r in rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        who = (low.get("actor.email") or "").lower()
        if not who:
            continue
        ou = ou_of.get(who, "")
        student = ou.lower().startswith(rl + "/") or ou.lower() == rl
        place = school_of(ou, root) if student else "Staff and others"
        parts = [p for p in ou[len(root):].split("/") if p] if student else []
        grade = parts[1] if len(parts) > 1 else ""
        key = (place, grade)
        by_place[key]["events"] += 1
        by_place[key]["people"].add(who)
        t = low.get("id.time", "")[:10]
        try:
            d = datetime.date.fromisoformat(t)
            wk = (d - datetime.timedelta(days=d.weekday())).isoformat()
        except ValueError:
            wk = "?"
        by_week[wk]["Students" if student else "Staff"].add(who)
        by_week[wk]["events"] += 1
        by_event[low.get("name", "") or "(event)"] += 1
        if banned and _under(ou, banned):
            f = flagged[who]
            f["events"] += 1
            f["last"] = max(f["last"], low.get("id.time", "")[:16].replace("T", " "))
            f["ou"] = ou
    places = [{"School": k[0], "Grade / group": k[1], "People": len(v["people"]),
               "Uses": v["events"]} for k, v in by_place.items()]
    places.sort(key=lambda x: (x["School"], x["Grade / group"]))
    weeks = [{"Week of": k, "Students": len(v["Students"]), "Staff": len(v["Staff"]),
              "Uses": v["events"]} for k, v in sorted(by_week.items())]
    events = [{"What": k.replace("_", " "), "Count": v} for k, v in
              sorted(by_event.items(), key=lambda x: -x[1])]
    flags = [{"Person": k, "Org unit": v.get("ou", ""), "Uses": v["events"], "Last": v["last"]}
             for k, v in sorted(flagged.items(), key=lambda x: -x[1]["events"])]
    return {"places": places, "weeks": weeks, "events": events, "flagged": flags,
            "people": len({r.get("actor.email", "").lower() for r in rows if
                           r.get("actor.email")})}
