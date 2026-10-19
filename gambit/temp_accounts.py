"""Time-limited accounts: substitutes, student teachers, contractors and summer-school
accounts get an end date. A week before it the account and its sponsor get a reminder;
after it the daily task suspends the account (and optionally moves it). Sponsors can ask for
more time; an admin extends it here."""

from __future__ import annotations

import datetime
import json

from .settings import settings

KINDS = ["Substitute", "Student teacher", "Contractor / vendor", "Summer school", "Volunteer",
         "Other"]


def options() -> dict:
    try:
        o = json.loads(settings.get("tempaccounts/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"warn_days": 7, "expired_ou": "", "default_ou": "/Staff/Temporary", **o}


def save_options(o: dict):
    settings.set("tempaccounts/options", json.dumps(o))


def load() -> list[dict]:
    from . import team
    if team.folder():
        d = team.read_shared("temp_accounts.json")
        if d:
            return d.get("accounts", [])
    try:
        return json.loads(settings.get("tempaccounts/list", "[]") or "[]")
    except ValueError:
        return []


def save(items: list[dict]):
    from . import team
    if team.folder():
        team.write_shared("temp_accounts.json", {"accounts": items})
    settings.set("tempaccounts/list", json.dumps(items))


def add(items: list[dict], email: str, kind: str, sponsor: str, end: str, who: str,
        note: str = "") -> dict:
    email = email.strip().lower()
    items[:] = [i for i in items if i["email"] != email]
    rec = {"email": email, "kind": kind, "sponsor": sponsor.strip().lower(), "end": end,
           "created": datetime.date.today().isoformat(), "by": who, "note": note,
           "status": "active", "warned": "", "history": [f"{datetime.date.today()} added by "
                                                         f"{who}, ends {end}"]}
    items.append(rec)
    return rec


def extend(rec: dict, new_end: str, who: str):
    rec["history"].append(f"{datetime.date.today()} extended by {who}: {rec['end']} → {new_end}")
    rec["end"] = new_end
    rec["warned"] = ""
    if rec["status"] == "expired":
        rec["status"] = "active"


def create_args(email: str, first: str, last: str, ou: str, password: str) -> list[str]:
    return ["create", "user", email, "firstname", first or "-", "lastname", last or "-",
            "password", password, "changepassword", "on", "ou", ou]


def expire_args(rec: dict, opts: dict) -> list[list[str]]:
    a = ["update", "user", rec["email"], "suspended", "on"]
    if opts.get("expired_ou"):
        a += ["ou", opts["expired_ou"]]
    return [a]


def reactivate_args(rec: dict, ou: str = "") -> list[list[str]]:
    a = ["update", "user", rec["email"], "suspended", "off"]
    if ou:
        a += ["ou", ou]
    return [a]


def due(items: list[dict], opts: dict, today: datetime.date | None = None):
    """→ (to warn, to expire)"""
    today = today or datetime.date.today()
    warn_from = (today + datetime.timedelta(days=int(opts.get("warn_days", 7) or 7))).isoformat()
    t = today.isoformat()
    warn = [i for i in items if i["status"] == "active" and not i.get("warned") and
            t <= i["end"] <= warn_from]
    expire = [i for i in items if i["status"] == "active" and i["end"] < t]
    return warn, expire


def warning_text(rec: dict) -> str:
    return (f"The Google account {rec['email']} ({rec['kind'].lower()}) is set to end on "
            f"{rec['end']}. After that it will be suspended and can't be used to sign in.\n\n"
            "If it's still needed, reply to this email with the new end date and the "
            "technology department will extend it.\n\nPlease save anything important from "
            "this account before then.")


def run(log=print, run_text=None, today: datetime.date | None = None) -> list[str]:
    """Daily task: reminders and suspensions."""
    from . import activity, google_io
    from .directory import run_gam_text
    run_text = run_text or run_gam_text
    opts = options()
    items = load()
    warn, expire = due(items, opts, today)
    lines = []
    for rec in warn:
        to = ",".join(x for x in (rec["email"], rec.get("sponsor", "")) if "@" in x)
        c, _o = run_text(google_io.email_args(to, f"Your account ends on {rec['end']}",
                                              warning_text(rec)), 120)
        if c == 0:
            rec["warned"] = datetime.date.today().isoformat()
            lines.append(f"Reminded {to} – {rec['email']} ends {rec['end']}.")
    dry = settings.get("safety/dry_run", False)
    for rec in expire:
        if dry:
            lines.append(f"Dry run – would suspend {rec['email']} (ended {rec['end']}).")
            continue
        ok = True
        for cmd in expire_args(rec, opts):
            c, _o = run_text(cmd, 120)
            activity.record(cmd, c, "done" if c == 0 else "failed", None,
                            settings.get("profile/current", "") or "Default",
                            note=f"time-limited account ended {rec['end']}")
            ok = ok and c == 0
        if ok:
            rec["status"] = "expired"
            rec["history"].append(f"{datetime.date.today()} suspended (ended {rec['end']})")
            lines.append(f"Suspended {rec['email']} – ended {rec['end']}.")
        else:
            lines.append(f"Couldn't suspend {rec['email']}.")
    save(items)
    for ln in lines:
        log(ln)
    return lines
