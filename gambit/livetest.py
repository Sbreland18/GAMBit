"""Live test checklist: try each part of GAMbit for real on the test account / test org
unit, record what worked, and bundle the results into a problem report.

Automatic items only read, or change the *test account* (and temporary test groups /
org units they create and remove again). Manual items tell you what to click and you
mark them passed or failed.
"""

from __future__ import annotations

import datetime
import json
import os
import secrets
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Optional

from .settings import settings


@dataclass
class Item:
    key: str
    area: str
    title: str
    how: str
    steps: Optional[Callable[[dict], list[list[str]]]] = None   # ctx -> gam commands
    check: Optional[Callable[[list[tuple[int, str]]], str]] = None  # outputs -> problem or ''
    needs_user: bool = True
    manual: bool = False
    extra: dict = field(default_factory=dict)


def _all_ok(results):
    bad = [(i, out) for i, (code, out) in enumerate(results) if code != 0]
    if not bad:
        return ""
    i, out = bad[0]
    last = [ln for ln in out.strip().splitlines() if ln.strip()]
    return f"step {i + 1} failed: {last[-1] if last else 'no message'}"


def _has_rows(results):
    p = _all_ok(results)
    if p:
        return p
    return "" if len([ln for ln in results[-1][1].splitlines() if ln.strip()]) >= 2 else \
        "GAM answered, but returned no rows"


ITEMS = [
    Item("connect", "Basics", "GAM can reach your domain",
         "Runs `gam info domain`.", lambda c: [["info", "domain"]], _all_ok, needs_user=False),
    Item("users", "Basics", "Read the user list",
         "Runs `gam print users` for the test org unit.",
         lambda c: [["print", "users", "query", f"orgUnitPath='{c['ou']}'", "fields",
                     "primaryemail"]], _has_rows),
    Item("testuser", "Basics", "The test account exists",
         "Looks the test account up.",
         lambda c: [["print", "users", "query", f"email:{c['user']}", "fields",
                     "primaryemail,ou,suspended"]], _has_rows),
    Item("name", "Users", "Change a name and put it back",
         "Renames the test account's first name, then sets it back to GAMbit.",
         lambda c: [["update", "user", c["user"], "firstname", "GAMbitCheck"],
                    ["update", "user", c["user"], "firstname", "GAMbit"]], _all_ok),
    Item("password", "Users", "Reset a password",
         "Gives the test account a new random password (and requires a change).",
         lambda c: [["update", "user", c["user"], "password", secrets.token_urlsafe(14),
                     "changepassword", "on"]], _all_ok),
    Item("suspend", "Users", "Suspend and unsuspend",
         "Suspends the test account, then unsuspends it.",
         lambda c: [["update", "user", c["user"], "suspended", "on"],
                    ["update", "user", c["user"], "suspended", "off"]], _all_ok),
    Item("ou", "Org units", "Create, move into and remove an org unit",
         "Creates <test OU>/GAMbit Check, moves the test account there and back, then "
         "deletes it.",
         lambda c: [["create", "ou", f"{c['ou'].rstrip('/')}/GAMbit Check"],
                    ["update", "user", c["user"], "ou", f"{c['ou'].rstrip('/')}/GAMbit Check"],
                    ["update", "user", c["user"], "ou", c["ou"]],
                    ["delete", "ou", f"{c['ou'].rstrip('/')}/GAMbit Check"]], _all_ok),
    Item("group", "Groups", "Create a group, add and remove a member",
         "Creates a temporary group, adds and removes the test account, deletes the group.",
         lambda c: [["create", "group", c["group"], "name", "GAMbit live test"],
                    ["update", "group", c["group"], "add", "member", c["user"]],
                    ["print", "group-members", "group", c["group"]],
                    ["update", "group", c["group"], "remove", "member", c["user"]],
                    ["delete", "group", c["group"]]], _all_ok),
    Item("vacation", "Gmail", "Out-of-office on and off",
         "Turns the test account's auto-reply on, then off (needs user-data access).",
         lambda c: [["user", c["user"], "vacation", "on", "subject", "GAMbit test",
                     "message", "Test"], ["user", c["user"], "vacation", "off"]], _all_ok),
    Item("signature", "Gmail", "Read a signature",
         "Shows the test account's signature.",
         lambda c: [["user", c["user"], "show", "signature"]], _all_ok),
    Item("drive", "Drive", "Read Drive settings",
         "Shows the test account's Drive settings.",
         lambda c: [["user", c["user"], "show", "drivesettings"]], _all_ok),
    Item("classroom", "Classroom", "Read Classroom",
         "Lists courses (none is fine).",
         lambda c: [["print", "courses", "teacher", c["admin"], "fields", "id"]], _all_ok,
         needs_user=False),
    Item("cros", "Chromebooks", "Read Chromebooks",
         "Searches Chromebooks (none found is fine).",
         lambda c: [["print", "cros", "query", "id:GAMBITLIVETEST", "fields", "deviceid"]],
         _all_ok, needs_user=False),
    Item("email", "Email", "Send an email",
         "Sends “GAMbit live test” to the GAMbit Google account. Check it arrives, then "
         "mark this passed.",
         lambda c: [["sendemail", "to", c["admin"], "subject", "GAMbit live test",
                     "message", "If you can read this, GAMbit can send email."]], _all_ok,
         needs_user=False, extra={"confirm": "Did the email arrive?"}),
    Item("sheet", "Sheets", "Make a Google Sheet",
         "Uploads a tiny table as a new Google Sheet in the GAMbit account's Drive.",
         None, None, needs_user=False, extra={"special": "sheet",
                                              "confirm": "Did the sheet open?"}),
    Item("m_dry", "Safety", "Dry run lists commands",
         "Turn on 🧪 Dry run, open Workflows → New staff, click Fill in the test account, run "
         "it, and check the Dry run tab lists the commands. Turn dry run off.", manual=True),
    Item("m_roster", "Roster sync", "Roster sync in Test mode",
         "Open Roster sync, load your real export, tick Test mode and Build preview. Check "
         "the changes look right (nothing outside the test org unit).", manual=True),
    Item("m_offboard", "Workflows", "Offboard the test account",
         "Workflows → Staff leaving → Fill in the test account, supervisor = you, Start "
         "offboarding. Then “Undo everything” and check the account is back.", manual=True),
    Item("m_undo", "Activity log", "Undo from the Activity log",
         "Suspend the test account from Users, then Activity log → select it → Undo.",
         manual=True),
    Item("m_tasks", "Background tasks", "A background task runs",
         "Tools → Background tasks → Run now on “GAMbit daily follow-ups” and check its "
         "result turns ✔.", manual=True),
]


def context() -> dict:
    from . import google_io
    user = (settings.get("safety/test_user", "") or "").strip()
    dom = user.split("@", 1)[1] if "@" in user else ""
    return {"user": user, "ou": (settings.get("safety/test_ou", "") or "").strip() or "/",
            "admin": google_io.admin_email(),
            "group": f"gambit-live-test-{secrets.token_hex(3)}@{dom}" if dom else ""}


def run_item(item: Item, ctx: dict) -> tuple[str, str]:
    """Returns (status, detail)."""
    from .directory import run_gam_text
    if item.needs_user and "@" not in ctx["user"]:
        return "skipped", "Set a test account in Settings & Updates → Testing."
    if item.extra.get("special") == "sheet":
        from . import google_io
        path = os.path.join(tempfile.gettempdir(), "GAMbit", "livetest.csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("check,result\nGAMbit live test,ok\n")
        link = google_io.upload_csv_as_sheet(path, "GAMbit live test")
        return "check", f"Created {link or 'the sheet'} – open it to confirm."
    results = []
    for args in item.steps(ctx):
        code, out = run_gam_text(args, 300)
        results.append((code, out))
        if code != 0:
            break
    problem = item.check(results) if item.check else _all_ok(results)
    if problem:
        return "failed", problem
    return ("check" if item.extra.get("confirm") else "passed",
            item.extra.get("confirm", "Worked."))


def load_results() -> dict:
    try:
        return json.loads(settings.get("livetest/results", "{}") or "{}")
    except ValueError:
        return {}


def save_result(key: str, status: str, detail: str):
    r = load_results()
    r[key] = {"status": status, "detail": detail,
              "when": datetime.datetime.now().isoformat(timespec="minutes")}
    settings.set("livetest/results", json.dumps(r))


def report_text() -> str:
    r = load_results()
    lines = [f"GAMbit live test – {datetime.datetime.now():%Y-%m-%d %H:%M}", ""]
    for it in ITEMS:
        x = r.get(it.key, {})
        lines.append(f"[{x.get('status', 'not run'):8}] {it.area} – {it.title}"
                     + (f": {x['detail']}" if x.get("detail") else ""))
    return "\n".join(lines)
