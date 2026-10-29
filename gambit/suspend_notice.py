"""Warn people before an inactive account is suspended.

A "Suspend accounts nobody has signed in to" clean-up rule can give notice first: the
person (and, for staff, their manager from the directory) gets an email N days before, and
an optional summary goes to HR or the principal. Anyone who signs in during that time drops
off the list by themselves; only people still inactive when the notice runs out go to
Approvals.
"""

from __future__ import annotations

import datetime
import json
import os

from .settings import settings

STATE_FILE = "cleanup_notices.json"     # {rule: {email: {"warned": date, "login": str}}}
SUBJECT = "Your Google account will be suspended on {date}"
MESSAGE = ("Hello {name},\n\nNobody has signed in to {email} for {days} days, so it will be "
           "suspended on {date}.\n\nIf you still need it, just sign in before then at "
           "https://accounts.google.com – nothing else to do.\n\nQuestions? Contact "
           "{contact}.\n\nThank you!")
MANAGER_MESSAGE = ("Hello,\n\n{name} ({email}) hasn't signed in for {days} days, so their "
                   "Google account will be suspended on {date}.\n\nIf they still need it "
                   "(for example they're on leave), ask them to sign in before then, or "
                   "contact {contact}.\n\nThank you!")


def _fill(text: str, **values) -> str:
    """Plain replacement – wording typed in a rule can't reach into Python objects."""
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def _path() -> str:
    from . import team
    base = team.folder()
    if not base:
        from PySide6.QtCore import QStandardPaths
        base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
            os.path.expanduser("~")
    return os.path.join(base, STATE_FILE)


def load_state() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(d: dict):
    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1)
    os.replace(tmp, p)


def managers(run_csv, emails: set[str]) -> dict[str, str]:
    """{person: manager email} from the directory's 'manager' relation."""
    if not emails:
        return {}
    code, rows, _e = run_csv(["print", "users", "fields", "primaryemail,relations"])
    if code != 0:
        return {}
    out = {}
    for r in rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        e = low.get("primaryemail", "").lower()
        if e not in emails:
            continue
        for k, v in low.items():
            if k.startswith("relations.") and k.endswith(".type") and v.lower() == "manager":
                m = low.get(k[:-len("type")] + "value", "").strip().lower()
                if "@" in m and m != e:
                    out[e] = m
                    break
    return out


def split(rule: dict, found: list[dict], users: list[dict], today: datetime.date,
          state: dict) -> tuple[list[dict], list[dict], list[str], dict]:
    """→ (warn now, notice ran out – suspend, signed in since – dropped, new state)."""
    days = int(rule.get("warn_days", 0) or 0)
    name = rule.get("name", "")
    mine = dict(state.get(name, {}))
    by = {u["email"].lower(): u for u in users}
    found_by = {f["email"]: f for f in found}
    dropped = [e for e in mine if e not in found_by]
    for e in dropped:
        mine.pop(e)
    warn, due = [], []
    for e, f in found_by.items():
        rec = mine.get(e)
        login = str(by.get(e, {}).get("last_login", ""))
        if rec and rec.get("login", "") != login:          # signed in, then went quiet again
            rec = None
        if not rec:
            warn.append(f)
            mine[e] = {"warned": today.isoformat(), "login": login,
                       "suspend_on": (today + datetime.timedelta(days=days)).isoformat()}
            continue
        if datetime.date.fromisoformat(rec["warned"]) + datetime.timedelta(days=days) <= today:
            due.append(f)
    new = dict(state)
    new[name] = mine
    return warn, due, dropped, new


def send(rule: dict, warn: list[dict], users: list[dict], today: datetime.date, log=print,
         run_text=None, run_csv=None) -> int:
    """Email each person (and their manager); a summary to the rule's 'also tell' list."""
    from . import google_io
    from .directory import run_gam_csv, run_gam_text
    if not warn:
        return 0
    run_text = run_text or (lambda a: run_gam_text(a, 120))
    run_csv = run_csv or (lambda a: run_gam_csv(a, 1800))
    days = int(rule.get("warn_days", 0) or 0)
    date = (today + datetime.timedelta(days=days)).strftime("%B %d, %Y")
    contact = (rule.get("warn_contact") or settings.get("google/admin_email", "") or
               "your school's tech office").strip()
    by = {u["email"].lower(): u for u in users}
    mgr = managers(run_csv, {f["email"] for f in warn}) if rule.get("warn_manager") else {}
    if settings.get("safety/dry_run", False):
        log(f"Dry run: would warn {len(warn)} person(s) that their account will be "
            f"suspended on {date}.")
        return 0
    sent = 0
    subject = _fill(rule.get("warn_subject") or SUBJECT, date=date)
    for f in warn:
        e = f["email"]
        u = by.get(e, {})
        vals = dict(name=u.get("name") or e.split("@")[0], email=e, date=date,
                    days=rule.get("days", ""), contact=contact)
        code, out = run_text(google_io.email_args(
            e, subject, _fill(rule.get("warn_message") or MESSAGE, **vals)))
        sent += code == 0
        if code != 0:
            log(f"Couldn't email {e}: {(out or '').strip()[-120:]}")
        if e in mgr:
            run_text(google_io.email_args(mgr[e], f"{vals['name']}'s Google account will be "
                                                  f"suspended on {date}",
                                          _fill(MANAGER_MESSAGE, **vals)))
    also = [x.strip() for x in (rule.get("warn_also") or "").replace(";", ",").split(",")
            if "@" in x]
    if also:
        body = (f"These accounts haven't been used and will be suspended on {date} unless "
                "they sign in first:\n\n" + "\n".join(f"• {f['email']} – {f['why']}"
                                                      for f in warn))
        for to in also:
            run_text(google_io.email_args(to, f"{len(warn)} account(s) to be suspended on "
                                              f"{date}", body))
    log(f"Warned {sent} of {len(warn)} person(s): suspension on {date} unless they sign in.")
    return sent
