"""Quarterly admin access review: every Google admin role assignment with the person's
2-Step Verification, last sign-in and how many admin-console actions they took in the last
90 days. Flags people who have left, super admins without 2SV and admins who haven't used
their rights. A director marks each one Keep or Remove and signs off; the review is saved
in the team folder for audits and cyber insurance, and removals go through Approvals."""

from __future__ import annotations

import datetime
import json
from collections import Counter

from .settings import settings

ADMINS_ARGS = ["print", "admins"]
USERS_ARGS = ["print", "users", "fields",
              "primaryemail,name,ou,suspended,isenrolledin2sv,isenforcedin2sv,lastlogintime"]
DAYS = 90


def activity_args(days: int = DAYS) -> list[str]:
    return ["report", "admin", "user", "all", "start", f"-{days}d"]


def options() -> dict:
    try:
        o = json.loads(settings.get("accessreview/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"former_root": "/Former Staff", "idle_days": DAYS, "every_days": 90,
            "remind": "", **o}


def save_options(o: dict):
    settings.set("accessreview/options", json.dumps(o))


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _date(t: str):
    t = (t or "").strip()
    if not t or t.lower().startswith("never") or t.startswith("1970"):
        return None
    try:
        return datetime.date.fromisoformat(t[:10])
    except ValueError:
        return None


from .oupath import under  # noqa: E402


def review(admin_rows: list[dict], user_rows: list[dict], activity_rows: list[dict],
           opts: dict, today: datetime.date | None = None) -> list[dict]:
    today = today or datetime.date.today()
    users = {}
    for r in user_rows:
        low = _low(r)
        e = low.get("primaryemail", "").lower()
        if e:
            users[e] = low
    acts = Counter(_low(r).get("actor.email", "").lower() for r in activity_rows)
    former = (opts.get("former_root") or "").rstrip("/").lower()
    idle = int(opts.get("idle_days", DAYS) or DAYS)
    out = []
    for r in admin_rows:
        low = _low(r)
        who = (low.get("assignedtouser") or low.get("assignedtogroup") or
               low.get("assignedto", "")).lower()
        role = low.get("role", "") or low.get("roleid", "")
        u = users.get(who, {})
        last = _date(u.get("lastlogintime", ""))
        tsv = u.get("isenrolledin2sv", "").lower() == "true"
        ou = u.get("orgunitpath", "")
        flags = []
        if u and u.get("suspended", "").lower() == "true":
            flags.append("account suspended")
        if former and under(ou, former):
            flags.append("has left (in " + ou + ")")
        if u and not tsv:
            flags.append("no 2-Step Verification" + (" – SUPER ADMIN" if "super" in
                                                     role.lower() else ""))
        if acts.get(who, 0) == 0:
            flags.append(f"no admin actions in {DAYS} days")
        if last is None and u:
            flags.append("never signed in")
        elif last and (today - last).days > idle:
            flags.append(f"no sign-in for {(today - last).days} days")
        if not u and "@" in who:
            flags.append("not a user in this domain")
        out.append({"Admin": who or "(service account)", "Role": role,
                    "Scope": low.get("orgunit", "") or low.get("scopetype", ""),
                    "2SV": "yes" if tsv else ("no" if u else "?"),
                    "Last sign-in": last.isoformat() if last else ("never" if u else ""),
                    "Admin actions": acts.get(who, 0), "Flags": "; ".join(flags),
                    "id": low.get("roleassignmentid", ""), "risk": _risk(flags, role)})
    return sorted(out, key=lambda x: (-x["risk"], x["Admin"]))


def _risk(flags: list[str], role: str) -> int:
    score = 0
    for f in flags:
        score += 5 if ("left" in f or "suspended" in f or "SUPER" in f) else 2
    return score + (1 if "super" in role.lower() and flags else 0)


def remove_args(assignment_id: str) -> list[str]:
    return ["delete", "admin", assignment_id]


def _load() -> list[dict]:
    from . import team
    if team.folder():
        return team.read_shared("access_reviews.json").get("reviews", [])
    try:
        return json.loads(settings.get("accessreview/history", "[]") or "[]")
    except ValueError:
        return []


def history() -> list[dict]:
    return _load()


def sign_off(rows: list[dict], decisions: dict[str, str], who: str, note: str = "") -> dict:
    from . import team
    rec = {"date": datetime.date.today().isoformat(), "by": who, "note": note,
           "rows": [{k: r[k] for k in ("Admin", "Role", "Scope", "2SV", "Last sign-in",
                                       "Admin actions", "Flags", "id")} | {
               "Decision": decisions.get(r["id"], "Keep")} for r in rows]}
    items = _load() + [rec]
    if team.folder():
        team.write_shared("access_reviews.json", {"reviews": items[-40:]})
    settings.set("accessreview/history", json.dumps(items[-8:]))
    return rec


def due(today: datetime.date | None = None) -> bool:
    today = today or datetime.date.today()
    h = _load()
    if not h:
        return True
    try:
        last = datetime.date.fromisoformat(h[-1]["date"])
    except (KeyError, ValueError):
        return True
    return (today - last).days >= int(options().get("every_days", 90) or 90)


def reminder(log=print, today=None) -> str:
    """Daily task: remind once a week while the quarterly review is due."""
    o = options()
    if not o.get("remind") or not due(today):
        return ""
    today = today or datetime.date.today()
    key = f"accessreview/reminded/{today.isocalendar()[0]}-{today.isocalendar()[1]}"
    if settings.get(key, False):
        return ""
    from . import google_io
    msg = ("The quarterly Google admin access review is due. Open GAMbit → Admin → Access "
           "review, mark each admin Keep or Remove and sign off.")
    try:
        google_io.send_email(o["remind"], "GAMbit: admin access review due", msg)
    except Exception as exc:  # noqa: BLE001
        log(f"Couldn't email the access-review reminder: {exc}")
        return ""
    settings.set(key, True)
    log("Access review reminder sent.")
    return msg


def gather(run_csv=None) -> tuple[list[dict], list[str]]:
    from .directory import run_gam_csv
    run_csv = run_csv or (lambda a: run_gam_csv(a, 3600))
    probs = []
    c, admins, e = run_csv(ADMINS_ARGS)
    if c != 0:
        raise RuntimeError("Couldn't list admins: " + (e or "").strip()[-200:])
    c, users, e = run_csv(USERS_ARGS)
    if c != 0:
        probs.append("users: " + (e or "").strip()[-120:])
        users = []
    c, acts, e = run_csv(activity_args())
    if c != 0:
        probs.append("admin log: " + (e or "").strip()[-120:])
        acts = []
    return review(admins, users, acts, options()), probs
