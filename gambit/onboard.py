"""Staff onboarding from the HR sheet: when a staff roster sync creates an account, give
that person the full “New staff” setup – license, building groups, email signature and
a welcome email to their supervisor with the sign-in details.

Signatures often fail for a few minutes after an account is made (the mailbox isn't
ready yet), so a failed signature is queued and retried by the background tasks.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Optional

from .settings import settings

WELCOME_SUBJECT = "New account for {name}"
WELCOME_BODY = (
    "Hello,\n\n"
    "{name} ({title}) now has a district Google account.\n\n"
    "Email: {email}\n"
    "Temporary password: {password}\n\n"
    "They'll be asked to choose their own password the first time they sign in at "
    "https://accounts.google.com.\n"
    "Please pass this on to them privately.\n\n"
    "Thanks,\nTechnology Department")

DEFAULTS = {
    "enabled": False,
    "license": "",
    "groups": "* = allstaff\n",           # "Building/school/department = g1, g2"
    "signature": True,
    "welcome": True,
    "welcome_fallback": "",                # when the sheet has no supervisor
    "welcome_cc": "",
    "subject": WELCOME_SUBJECT,
    "body": WELCOME_BODY,
}


def options() -> dict:
    try:
        saved = json.loads(settings.get("onboard/options", "{}") or "{}")
    except ValueError:
        saved = {}
    return {**DEFAULTS, **saved}


def save_options(opts: dict):
    settings.set("onboard/options", json.dumps({k: opts.get(k, v)
                                                for k, v in DEFAULTS.items()}))


# ------------------------------------------------------------ group map ---
def parse_groups(text: str) -> dict[str, list[str]]:
    """'Lincoln Elementary = lincoln-staff, k5-staff' lines → {key: [groups]}."""
    out: dict[str, list[str]] = {}
    for ln in (text or "").splitlines():
        ln = ln.split("#", 1)[0].strip()
        if "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        groups = [g.strip() for g in v.replace(";", ",").split(",") if g.strip()]
        if k.strip() and groups:
            out.setdefault(k.strip().lower(), []).extend(groups)
    return out


def groups_for(person: dict, mapping: dict[str, list[str]], domain: str = "") -> list[str]:
    keys = {"*"} | {str(person.get(k, "")).strip().lower()
                    for k in ("school", "school_name", "department", "title")
                    if person.get(k)}
    ou = (person.get("ou") or "").strip().lower()
    if ou:
        keys.add(ou)
    out = []
    for k, groups in mapping.items():
        if k in keys:
            for g in groups:
                g = g if "@" in g or not domain else f"{g}@{domain}"
                if g.lower() not in (x.lower() for x in out):
                    out.append(g)
    return out


# ---------------------------------------------------------------- steps ---
def _fill(text: str, vals: dict) -> str:
    for k, v in vals.items():
        text = text.replace("{" + k + "}", v or "")
    return text.replace("()", "").replace("  ", " ")


def welcome_to(person: dict, opts: dict) -> str:
    sup = (person.get("manager") or "").strip()
    if "@" not in sup:
        sup = (opts.get("welcome_fallback") or "").strip()
    return sup


def welcome_email(email: str, password: str, person: dict, opts: dict,
                  sender: str = "") -> Optional[list[str]]:
    to = welcome_to(person, opts)
    if not opts.get("welcome") or "@" not in to:
        return None
    vals = {"name": f"{person.get('first', '')} {person.get('last', '')}".strip(),
            "first": person.get("first", ""), "last": person.get("last", ""),
            "email": email, "password": password, "title": person.get("title", ""),
            "department": person.get("department", ""),
            "school": person.get("school_name") or person.get("school", ""),
            "supervisor": to}
    from . import google_io
    args = google_io.email_args(to, _fill(opts.get("subject") or WELCOME_SUBJECT, vals),
                                _fill(opts.get("body") or WELCOME_BODY, vals), sender=sender)
    if (opts.get("welcome_cc") or "").strip():
        args += ["cc", opts["welcome_cc"].strip()]
    return args


def signature_template() -> str:
    from . import team
    from .signature import SIGNATURE_TEMPLATE
    return team.setting("email/signature", "") or SIGNATURE_TEMPLATE


def steps(email: str, password: str, person: dict, opts: dict,
          domain: str = "") -> list[tuple[str, list[str]]]:
    """(label, gam args) to run after the account is created."""
    out: list[tuple[str, list[str]]] = []
    if opts.get("license"):
        out.append((f"Assign license {opts['license']}",
                    ["user", email, "add", "license", opts["license"]]))
    for g in groups_for(person, parse_groups(opts.get("groups", "")), domain):
        out.append((f"Add to {g}", ["update", "group", g, "add", "member", "user", email]))
    if opts.get("signature"):
        from .signature import gam_args
        out.append(("Set email signature", gam_args(email, signature_template())))
    w = welcome_email(email, password, person, opts)
    if w:
        out.append((f"Email sign-in details to {welcome_to(person, opts)}", w))
    return out


def describe(person: dict, opts: dict, domain: str = "") -> str:
    """Short text for the roster sync preview."""
    bits = []
    if opts.get("license"):
        bits.append("license")
    g = groups_for(person, parse_groups(opts.get("groups", "")), domain)
    if g:
        bits.append(f"{len(g)} group(s)")
    if opts.get("signature"):
        bits.append("signature")
    to = welcome_to(person, opts)
    if opts.get("welcome"):
        bits.append(f"welcome email to {to}" if "@" in to else "⚠ no supervisor to email")
    return "+ " + ", ".join(bits) if bits else ""


def expand(changes, opts: dict, domain: str = ""):
    """Add the onboarding steps to every 'create' change (staff syncs)."""
    if not opts.get("enabled"):
        return changes
    for c in changes:
        if c.action != "create" or not c.commands:
            continue
        extra = steps(c.email, c.password, c.person, opts, domain)
        c.commands = [c.commands[0]] + [a for _l, a in extra]
        d = describe(c.person, opts, domain)
        if d:
            c.details += f"  {d}"
    return changes


# ----------------------------------------------------- signature retries ---
def _queue_path() -> str:
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "onboarding_retry.json")


def _load_queue() -> list[dict]:
    try:
        with open(_queue_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _save_queue(q: list[dict]):
    with open(_queue_path(), "w", encoding="utf-8") as fh:
        json.dump(q, fh, indent=2)


def queue_retry(email: str, args: list[str], label: str):
    q = [x for x in _load_queue() if not (x["email"] == email and x["args"] == args)]
    q.append({"email": email, "args": args, "label": label, "tries": 0,
              "added": datetime.datetime.now().isoformat(timespec="minutes")})
    _save_queue(q)


def pending() -> list[dict]:
    return _load_queue()


def is_retryable(args: list[str]) -> bool:
    return len(args) > 2 and args[0] == "user" and args[2] == "signature"


def run_retries(log=print, run_text=None, max_tries: int = 12) -> list[str]:
    """Try queued signatures again (called by the background tasks)."""
    from . import activity
    from .directory import run_gam_text
    run_text = run_text or run_gam_text
    q = _load_queue()
    if not q or settings.get("safety/dry_run", False):
        return []
    keep, lines = [], []
    for item in q:
        code, out = run_text(item["args"], 120)
        activity.record(item["args"], code, "done" if code == 0 else "failed", None,
                        settings.get("profile/current", "") or "Default",
                        note=f"onboarding retry for {item['email']}")
        if code == 0:
            lines.append(f"{item['email']}: {item['label']} – done on retry.")
            continue
        item["tries"] = item.get("tries", 0) + 1
        if item["tries"] >= max_tries:
            lines.append(f"{item['email']}: {item['label']} still failing after "
                         f"{item['tries']} tries – gave up. Set it from Email → Signatures.")
        else:
            keep.append(item)
    _save_queue(keep)
    return lines
