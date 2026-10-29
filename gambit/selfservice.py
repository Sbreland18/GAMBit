"""Staff self-service: teachers ask for a student password reset (or sign-out)
through a Google Form; GAMbit reads the form's response sheet, checks the request,
and puts it on the Approvals page – or runs it straight away if you allow that.
The new password is emailed back to the teacher who asked.

Suggested form (Settings → Responses → Collect email addresses: Verified):
    Student's school email      short answer
    What do you need?           Reset password / Sign out of all devices / Something else
    Details                     paragraph (optional)
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import re

from . import google_io, team
from .directory import run_gam_csv, run_gam_text
from .settings import settings

COLS = {
    "time": ["Timestamp"],
    # only the address Google Forms collects and verifies ("Collect email addresses") –
    # never a column people type into, or anyone could ask in a teacher's name
    "requester": ["Email Address", "Email address"],
    "student": ["Student's school email", "Student email", "Student", "Student account",
                "Account", "Whose account"],
    "action": ["What do you need?", "What do you need", "Request", "Request type", "Type"],
    "notes": ["Details", "Notes", "Anything else", "Comments"],
}
ACTIONS = {"reset": "Reset password", "signout": "Sign out of all devices",
           "other": "Something else"}


def opts() -> dict:
    return {
        "sheet_url": settings.get("selfservice/sheet_url", "") or "",
        "tab": settings.get("selfservice/tab", "") or "",
        "staff_root": settings.get("selfservice/staff_root", "/Staff") or "/Staff",
        "student_root": settings.get("selfservice/student_root", "/Students") or "/Students",
        "require_teacher": bool(settings.get("selfservice/require_teacher", True)),
        "auto_reset": bool(settings.get("selfservice/auto_reset", False)),
    }


def _norm(h):
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def _find(headers: list[str], key: str) -> str:
    norm = {_norm(h): h for h in headers}
    for c in COLS[key]:
        if _norm(c) in norm:
            return norm[_norm(c)]
    # loose match ("Student's email address" etc.)
    for h in headers:
        hl = h.lower()
        if key == "student" and "student" in hl:
            return h
        if key == "action" and ("need" in hl or "request" in hl):
            return h
    return ""


def classify(text: str) -> str:
    t = (text or "").lower()
    if "sign" in t and "out" in t or "logged in" in t or "log out" in t:
        return "signout"
    if "password" in t or "reset" in t or "forgot" in t or "locked" in t:
        return "reset"
    return "other"


def _under(ou: str, root: str) -> bool:
    ou, root = (ou or "/").rstrip("/") or "/", (root or "/").rstrip("/") or "/"
    return root == "/" or ou == root or ou.startswith(root + "/")


# --------------------------------------------------------- processed rows ---
def _state_path() -> str:
    if team.folder():
        d = os.path.join(team.folder(), "selfservice")
    else:
        from PySide6.QtCore import QStandardPaths
        d = os.path.join(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or
                         os.path.expanduser("~"), "selfservice")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "processed.json")


def _load_state() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"done": {}}


def _save_state(st: dict):
    tmp = _state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1)
    os.replace(tmp, _state_path())


def _key(row: dict, cols: dict) -> str:
    return "|".join((row.get(cols[k]) or "").strip().lower()
                    for k in ("time", "requester", "student", "action") if cols.get(k))


# ---------------------------------------------------------------- process ---
def read_rows() -> tuple[list[dict], dict]:
    o = opts()
    if not o["sheet_url"]:
        raise RuntimeError("Set the request form's response sheet first.")
    path = google_io.download_sheet(o["sheet_url"], o["tab"])
    with open(path, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    headers = list(rows[0].keys()) if rows else []
    cols = {k: _find(headers, k) for k in COLS}
    if rows and (not cols["student"] or not cols["requester"]):
        raise RuntimeError("The sheet needs the teacher's email (turn on “Collect email "
                           "addresses” in the form) and a student email question.")
    return rows, cols


def check(requester: str, student: str, users: dict, o: dict) -> str:
    """'' when the request is OK, otherwise why not."""
    r, s = users.get(requester.lower()), users.get(student.lower())
    if not r:
        return f"{requester} isn't an account in your domain."
    if r.get("suspended") or not _under(r.get("ou"), o["staff_root"]):
        return f"{requester} isn't active staff (under {o['staff_root']})."
    if not s:
        return f"{student} isn't an account in your domain."
    if not _under(s.get("ou"), o["student_root"]):
        return f"{student} isn't a student (under {o['student_root']}) – staff accounts " \
               "go to IT directly."
    if o["require_teacher"]:
        code, rows, _ = run_gam_csv(["print", "courses", "teacher", requester, "student",
                                     student, "states", "active", "fields", "id,name"], 120)
        if code != 0:
            return "Couldn't check Classroom for a shared class."
        if not rows:
            return f"{requester} doesn't teach {student} in any active Classroom class."
    return ""


def process(log=print) -> int:
    """Read new form responses; returns how many became requests (or ran)."""
    from .directory import load_users
    o = opts()
    rows, cols = read_rows()
    state = _load_state()
    users = {u["email"].lower(): u for u in load_users()} if rows else {}
    new = 0
    for row in rows:
        key = _key(row, cols)
        if not key or key in state["done"]:
            continue
        requester = (row.get(cols["requester"]) or "").strip()
        student = (row.get(cols["student"]) or "").strip().lower()
        action = classify(row.get(cols["action"], "") if cols["action"] else "reset")
        notes = (row.get(cols["notes"]) or "").strip() if cols["notes"] else ""
        problem = check(requester, student, users, o) if "@" in student else \
            "No student email given."
        entry = {"time": datetime.datetime.now().isoformat(timespec="seconds"),
                 "requester": requester, "student": student, "action": action,
                 "result": "started"}
        state["done"][key] = entry
        _save_state(state)              # saved before acting, so a crash can't repeat it
        if problem:
            entry["result"] = "refused: " + problem
            _tell(requester, f"Your GAMbit request for {student or 'a student'} wasn't "
                             "sent", f"Your request couldn't be accepted: {problem}\n\n"
                                     "Contact the tech office if you think this is wrong.")
            log(f"Refused {requester} → {student}: {problem}")
        elif action == "reset" and o["auto_reset"]:
            ok, msg = run_reset(requester, student)
            entry["result"] = "reset" if ok else "failed: " + msg
            log(f"Auto reset {student} for {requester}: {'ok' if ok else msg}")
        elif team.folder():
            req = team.new_request(
                [], f"{requester} asked: {ACTIONS[action]} for {student}." +
                (f"\nDetails: {notes}" if notes else ""),
                title=f"{ACTIONS[action]}: {student} (asked by {requester})",
                by=requester, extra={"kind": "selfservice", "requester": requester,
                                     "student": student, "action": action, "notes": notes})
            entry["result"] = f"request {req['id']}"
            log(f"Request from {requester}: {ACTIONS[action]} for {student}")
        else:
            entry["result"] = "skipped: no team folder for approvals"
        state["done"][key] = entry
        _save_state(state)
        new += 1
    _save_state(state)
    settings.set("selfservice/last_check", datetime.datetime.now().isoformat(
        timespec="minutes"))
    return new


def describe(r: dict) -> str:
    return f"{ACTIONS.get(r.get('action'), r.get('action'))} for {r.get('student')} " \
           f"(asked by {r.get('requester')})"


def _password() -> str:
    from .secret_args import readable_password
    return readable_password()


def reset_args(student: str, pw: str) -> list[str]:
    return ["update", "user", student, "password", pw, "changepassword", "on"]


def run_reset(requester: str, student: str) -> tuple[bool, str]:
    """Unattended reset (auto mode): run it and email the teacher."""
    from . import activity
    pw = _password()
    args = reset_args(student, pw)
    code, out = run_gam_text(args, 120)
    activity.record(args, code, "done" if code == 0 else "failed", None,
                    settings.get("profile/current", "") or "Default",
                    note=f"self-service request from {requester}")
    if code != 0:
        return False, out.strip().splitlines()[-1] if out.strip() else str(code)
    _tell_password(requester, student, pw)
    return True, ""


def _tell(to: str, subject: str, body: str):
    try:
        if "@" in to:
            google_io.send_email(to, subject, body)
    except Exception:  # noqa: BLE001
        pass


def _tell_password(requester: str, student: str, pw: str):
    _tell(requester, f"New password for {student}",
          f"The password for {student} has been reset.\n\nTemporary password: {pw}\n\n"
          "They'll be asked to choose a new one when they sign in. Please don't forward "
          "this email.")


def approve(page, r: dict):
    """Approvals page: run an approved self-service request through the runner."""
    from .gam_runner import dry_run_on
    action, student, requester = r.get("action"), r.get("student"), r.get("requester")
    # check again now – the request file could have been changed since it was made, and
    # the teacher or student may have moved on
    from .directory import load_users
    try:
        users = {u["email"].lower(): u for u in (page.directory.users or load_users())}
    except Exception:  # noqa: BLE001
        users = {}
    problem = check(str(requester or ""), str(student or ""), users, opts()) \
        if "@" in str(student or "") else "no student account"
    if problem:
        page.info(f"Not run: {problem}")
        return
    if dry_run_on():
        page.info("Dry run is on, so this request wasn't run (and stays waiting).")
        team.update_request(r, "pending")
        return
    if action == "reset":
        pw = _password()
        args = reset_args(student, pw)
    elif action == "signout":
        pw, args = "", ["user", student, "signout"]
    else:
        team.update_request(r, "done", result="handled by hand (something else)")
        page.info(f"“Something else” requests aren't automatic – contact {requester} about:\n\n"
                  f"{r.get('notes') or r.get('reason')}")
        page.refresh()
        return

    def done(code, _o, err):
        if code == 0:
            if pw:
                _tell_password(requester, student, pw)
            else:
                _tell(requester, f"{student} was signed out",
                      f"{student} has been signed out of all devices.")
            team.update_request(r, "done", result="done – the teacher was emailed")
        else:
            team.update_request(r, "failed", result=(err or "").strip()[-200:])
        page.refresh()
    page.app._approved_request = r["id"]
    try:
        if not page.runner.run(args, on_done=done):
            team.update_request(r, "failed", result="not started")
    finally:
        page.app._approved_request = ""


def denied(r: dict, note: str):
    _tell(r.get("requester", ""), f"Your request for {r.get('student')}",
          f"Your request ({describe(r)}) wasn't approved." +
          (f"\n\nNote from IT: {note}" if note else ""))
