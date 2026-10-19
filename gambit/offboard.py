"""Staff offboarding done properly: a plan in stages, every step undoable where
Google allows it, and follow-ups that run by themselves.

    Today        lock the account, auto-reply, forward mail and share the mailbox with
                 the supervisor, transfer Drive + Calendar, leave groups, hide from the
                 directory, move to the leavers' org unit
    Day 30       stop forwarding and the auto-reply, remove mailbox access, release
                 licenses, suspend
    Day 90       delete the account – never automatic: it becomes an approval request /
                 a button you press

Each person gets a record (JSON) in <team folder>/offboarding, or AppData when
there's no team folder, holding what their account looked like before so the
whole thing can be put back.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import uuid
from typing import Callable, Optional

from .settings import settings

DEFAULTS = {
    "forward_days": 30,
    "delete_days": 90,
    "ou": "/Former Staff",
    "message": ("Thank you for your email. {name} is no longer with the district. "
                "Please contact {supervisor} for help."),
    "steps": ["lock", "vacation", "forward", "delegate", "transfer", "groups", "gal", "ou",
              "later_forward_off", "later_licenses", "later_suspend", "delete_reminder"],
}

STEP_INFO = {
    # key: (when, label)
    "lock": ("today", "Sign them out everywhere and change their password"),
    "deprov": ("today", "Remove app passwords, backup codes and connected apps"),
    "vacation": ("today", "Auto-reply pointing people to the supervisor (ends on its own)"),
    "forward": ("today", "Forward new email to the supervisor"),
    "delegate": ("today", "Let the supervisor open the mailbox"),
    "transfer": ("today", "Transfer their Drive files and Calendar to the supervisor"),
    "looker": ("today", "Give the supervisor editor access to their Looker Studio reports"),
    "groups": ("today", "Remove them from every group (roles saved so it can be undone)"),
    "gal": ("today", "Hide them from the staff directory"),
    "ou": ("today", "Move them to the leavers' org unit"),
    "later_forward_off": ("later", "Stop forwarding, the auto-reply and mailbox access"),
    "archive": ("later", "Copy their email into the archive group (set below)"),
    "later_licenses": ("later", "Release their licenses"),
    "later_suspend": ("later", "Suspend the account"),
    "delete_reminder": ("delete", "Ask an admin to delete the account"),
}


# ----------------------------------------------------------------- storage ---
def folder() -> str:
    from . import team
    if team.folder():
        d = os.path.join(team.folder(), "offboarding")
    else:
        from PySide6.QtCore import QStandardPaths
        base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
            os.path.expanduser("~")
        d = os.path.join(base, "offboarding")
    os.makedirs(d, exist_ok=True)
    return d


def _file(email: str) -> str:
    return os.path.join(folder(), re.sub(r"[^a-z0-9@._-]", "_", email.lower()) + ".json")


def save(rec: dict):
    rec["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    path = _file(rec["email"])
    tmp = path + f".{uuid.uuid4().hex[:6]}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2)
    os.replace(tmp, path)


def load_all() -> list[dict]:
    out = []
    for name in os.listdir(folder()):
        if name.endswith(".json"):
            try:
                with open(os.path.join(folder(), name), encoding="utf-8") as fh:
                    out.append(json.load(fh))
            except (OSError, ValueError):
                continue
    out.sort(key=lambda r: r.get("started", ""), reverse=True)
    return out


def get(email: str) -> Optional[dict]:
    try:
        with open(_file(email), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def options() -> dict:
    try:
        saved = json.loads(settings.get("offboard/options", "{}") or "{}")
    except ValueError:
        saved = {}
    from . import team
    ou = team.setting("workflow/leaving_ou", "") or saved.get("ou") or DEFAULTS["ou"]
    return {**DEFAULTS, **saved, "ou": ou}


def save_options(opts: dict):
    from . import team
    settings.set("offboard/options", json.dumps(opts))
    if opts.get("ou"):
        team.set_setting("workflow/leaving_ou", opts["ou"])


# ----------------------------------------------------------------- capture ---
def _col(row: dict, *names) -> str:
    low = {(k or "").lower(): v for k, v in row.items()}
    for n in names:
        if low.get(n.lower()):
            return low[n.lower()]
    return ""


def capture(email: str, run_csv) -> dict:
    """What the account looks like now: groups + roles, licenses, OU, name."""
    before = {"groups": [], "licenses": [], "ou": "", "name": "", "gal": True}
    code, rows, _ = run_csv(["user", email, "print", "groups"])
    if code == 0:
        for r in rows:
            g = _col(r, "group", "groupemail", "email")
            if g and g.lower() != email.lower():
                before["groups"].append([g, (_col(r, "role") or "member").lower()])
    code, rows, _ = run_csv(["user", email, "print", "users", "fields",
                             "primaryemail,name,orgunitpath,includeinglobaladdresslist",
                             "licenses"])
    if code == 0 and rows:
        r = rows[0]
        before["ou"] = _col(r, "orgUnitPath")
        before["name"] = _col(r, "name.fullName") or " ".join(
            x for x in (_col(r, "name.givenName"), _col(r, "name.familyName")) if x)
        before["gal"] = _col(r, "includeInGlobalAddressList").lower() != "false"
        skus = []
        for k, v in r.items():
            kl = (k or "").lower()
            if kl.startswith("licen") and "display" not in kl and v:
                skus += [x for x in re.split(r"[\s,;]+", v) if re.fullmatch(r"[\w-]{4,}", x)]
        before["licenses"] = list(dict.fromkeys(skus))
    return before


# -------------------------------------------------------------------- plan ---
def _step(key, label, args, undo=None, note=""):
    return {"id": uuid.uuid4().hex[:8], "key": key, "label": label, "args": args,
            "undo": undo, "status": "pending", "note": note}


def build(email: str, supervisor: str, before: dict, opts: dict,
          random_password: Callable[[int], str]) -> dict:
    today = datetime.date.today()
    fwd_days = int(opts.get("forward_days", 30))
    del_days = int(opts.get("delete_days", 90))
    later = (today + datetime.timedelta(days=fwd_days)).isoformat()
    on = set(opts.get("steps", DEFAULTS["steps"]))
    sup = supervisor if "@" in (supervisor or "") else ""
    name = before.get("name") or email.split("@")[0]
    msg = opts.get("message", DEFAULTS["message"]).replace("{name}", name).replace(
        "{supervisor}", sup or "the main office")
    s0, s1, notes = [], [], []

    if "lock" in on:
        s0.append(_step("lock", "Change password", ["update", "user", email, "password",
                                                     random_password(20)],
                        note="can't be undone – set a new password if they come back"))
        s0.append(_step("lock", "Sign out of all devices", ["user", email, "signout"]))
    if "deprov" in on:
        s0.append(_step("deprov", "Remove app passwords, backup codes and app access",
                        ["user", email, "deprovision"], note="can't be undone"))
    if "vacation" in on:
        s0.append(_step("vacation", f"Auto-reply until {later}",
                        ["user", email, "vacation", "on", "subject",
                         "No longer with the district", "message", msg, "start", "Started",
                         "end", later],
                        undo=["user", email, "vacation", "off"]))
    if sup and "forward" in on:
        s0.append(_step("forward", f"Add {sup} as a forwarding address",
                        ["user", email, "add", "forwardingaddress", sup]))
        s0.append(_step("forward", f"Forward new email to {sup}",
                        ["user", email, "forward", "on", "keep", sup],
                        undo=["user", email, "forward", "off"]))
    if sup and "delegate" in on:
        s0.append(_step("delegate", f"Let {sup} open the mailbox",
                        ["user", email, "add", "delegate", sup],
                        undo=["user", email, "delete", "delegate", sup]))
    if sup and "transfer" in on:
        s0.append(_step("transfer", f"Transfer Drive and Calendar to {sup}",
                        ["create", "datatransfer", email, "drive,calendar", sup, "all",
                         "release_resources"],
                        note="can't be undone – files stay with the supervisor"))
    if sup and "looker" in on:
        s0.append(_step("looker", f"Looker Studio: make {sup} an editor",
                        ["user", email, "add", "datastudiopermissions", "assettype", "all",
                         "owner", email, "role", "editor", f"user:{sup}"],
                        undo=["user", email, "delete", "datastudiopermissions", "assettype",
                              "all", "owner", email, "role", "any", f"user:{sup}"]))
    if "groups" in on:
        for g, role in before.get("groups", []):
            s0.append(_step("groups", f"Leave {g}", ["update", "group", g, "remove", email],
                            undo=["update", "group", g, "add", role or "member", email]))
    if "gal" in on and before.get("gal", True):
        s0.append(_step("gal", "Hide from the directory",
                        ["update", "user", email, "gal", "off"],
                        undo=["update", "user", email, "gal", "on"]))
    if "ou" in on and opts.get("ou"):
        s0.append(_step("ou", f"Move to {opts['ou']}",
                        ["update", "user", email, "ou", opts["ou"]],
                        undo=["update", "user", email, "ou", before.get("ou") or "/"]))
    if not sup and any(k in on for k in ("forward", "delegate", "transfer")):
        notes.append("No supervisor, so forwarding, mailbox access and the Drive/Calendar "
                     "transfer were left out.")

    if "later_forward_off" in on:
        if sup and "forward" in on:
            s1.append(_step("later_forward_off", "Stop forwarding",
                            ["user", email, "forward", "off"]))
        if "vacation" in on:
            s1.append(_step("later_forward_off", "Turn off the auto-reply",
                            ["user", email, "vacation", "off"]))
        if sup and "delegate" in on:
            s1.append(_step("later_forward_off", f"Remove {sup}'s mailbox access",
                            ["user", email, "delete", "delegate", sup],
                            undo=["user", email, "add", "delegate", sup]))
    arch = (opts.get("archive_group") or "").strip()
    if "archive" in on and "@" in arch:
        s1.append(_step("archive", f"Copy their email into {arch}",
                        ["user", email, "archive", "messages", arch, "query",
                         "-in:chats -in:spam -in:trash", "doit"],
                        note="copies – the mailbox itself isn't changed"))
    elif "archive" in on:
        notes.append("No archive group is set, so the email archive step was left out.")
    if "later_licenses" in on:
        for sku in before.get("licenses", []):
            s1.append(_step("later_licenses", f"Release license {sku}",
                            ["user", email, "delete", "license", sku],
                            undo=["user", email, "add", "license", sku]))
    if "later_suspend" in on:
        s1.append(_step("later_suspend", "Suspend the account",
                        ["update", "user", email, "suspended", "on"],
                        undo=["update", "user", email, "suspended", "off"]))

    stages = [{"key": "today", "title": "Today", "due": today.isoformat(), "auto": True,
               "done": None, "steps": s0}]
    if s1:
        stages.append({"key": "later", "title": f"After {fwd_days} days", "due": later,
                       "auto": True, "done": None, "steps": s1})
    if "delete_reminder" in on:
        stages.append({"key": "delete", "title": f"After {del_days} days",
                       "due": (today + datetime.timedelta(days=del_days)).isoformat(),
                       "auto": False, "done": None,
                       "steps": [_step("delete", "Delete the account",
                                       ["delete", "user", email],
                                       note="Google keeps deleted accounts restorable for "
                                            "about 20 days")]})
    return {"email": email, "name": name, "supervisor": sup, "status": "active",
            "started": datetime.datetime.now().isoformat(timespec="seconds"),
            "by": _me(), "before": before, "stages": stages, "notes": notes,
            "options": {k: opts.get(k) for k in ("forward_days", "delete_days", "ou",
                                                 "archive_group")}}


def _me() -> str:
    from . import team
    return team.me()


def next_stage(rec: dict) -> Optional[dict]:
    return next((s for s in rec.get("stages", []) if not s.get("done")), None)


def describe(rec: dict) -> str:
    st = next_stage(rec)
    if rec.get("status") == "undone":
        return "Undone – account put back"
    if rec.get("status") == "deleted":
        return "Account deleted"
    if not st:
        return "Finished"
    return f"{st['title']}: due {st['due']}" + ("" if st.get("auto") else " (needs an admin)")


def mark(rec: dict, stage_key: str, results: dict):
    """results: step id -> exit code."""
    for st in rec["stages"]:
        if st["key"] != stage_key:
            continue
        for step in st["steps"]:
            if step["id"] in results:
                step["status"] = "done" if results[step["id"]] == 0 else "failed"
        if all(s["status"] in ("done", "skipped") for s in st["steps"]) or not st["steps"]:
            st["done"] = datetime.datetime.now().isoformat(timespec="minutes")
        elif all(s["status"] != "pending" for s in st["steps"]):
            st["done"] = datetime.datetime.now().isoformat(timespec="minutes") + " (some failed)"
    if stage_key == "delete" and all(s["status"] == "done"
                                     for st in rec["stages"] if st["key"] == "delete"
                                     for s in st["steps"]):
        rec["status"] = "deleted"
    save(rec)


def undo_steps(rec: dict) -> list[dict]:
    """Steps that put things back, newest first."""
    out = []
    for st in reversed(rec.get("stages", [])):
        for step in reversed(st["steps"]):
            if step["status"] == "done" and step.get("undo"):
                out.append({"id": step["id"], "label": "Undo: " + step["label"],
                            "args": step["undo"]})
    return out


def cannot_undo(rec: dict) -> list[str]:
    return [step["label"] for st in rec.get("stages", []) for step in st["steps"]
            if step["status"] == "done" and not step.get("undo")]


# --------------------------------------------------------- unattended runs ---
def run_due(log=print, run_text=None) -> list[str]:
    """Run 'later' stages that are due; turn due deletions into approval requests."""
    from . import activity, team
    from .directory import run_gam_text
    run_text = run_text or run_gam_text
    today = datetime.date.today().isoformat()
    lines = []
    for rec in load_all():
        if rec.get("status") != "active":
            continue
        try:
            lines += _run_one(rec, today, run_text, activity, team)
        except Exception as exc:  # noqa: BLE001  – one bad record mustn't stop the rest
            lines.append(f"{rec.get('email', '?')}: follow-up failed – {exc}")
    return lines


def _run_one(rec: dict, today: str, run_text, activity, team) -> list[str]:
    lines: list[str] = []
    st = next_stage(rec)
    if not st or st["due"] > today:
        return lines
    if st.get("auto"):
        if settings.get("safety/dry_run", False):
            lines.append(f"{rec['email']}: {st['title']} is due (dry run is on – not run).")
            return lines
        results = {}
        for step in st["steps"]:
            if step["status"] != "pending":
                continue
            code, out = run_text(step["args"], 7200 if "archive" in step["args"] else 300)
            activity.record(step["args"], code, "done" if code == 0 else "failed",
                            {"args": step["undo"], "label": "Undo: " + step["label"]}
                            if step.get("undo") else None,
                            settings.get("profile/current", "") or "Default",
                            note=f"offboarding follow-up for {rec['email']}")
            results[step["id"]] = code
        mark(rec, st["key"], results)
        bad = sum(1 for c in results.values() if c)
        lines.append(f"{rec['email']}: {st['title']} – {len(results) - bad} step(s) done"
                     + (f", {bad} failed" if bad else ""))
    elif not st.get("requested"):
        if team.folder():
            req = team.new_request(
                [step["args"] for step in st["steps"]],
                f"{rec['email']} left on {rec['started'][:10]}. Their offboarding "
                f"reached “{st['title']}”.", title=f"Delete {rec['email']}",
                by="offboarding", extra={"kind": "offboard-delete",
                                         "email": rec["email"]})
            st["requested"] = req["id"]
            save(rec)
            lines.append(f"{rec['email']}: deletion is due – sent to Approvals.")
        else:
            lines.append(f"{rec['email']}: deletion is due – open Workflows → Staff "
                         "leaving to delete the account.")
    return lines


# --------------------------------------------------------------- graduation ---
GRAD_DEFAULTS = {
    "alumni_ou": "/Alumni/Class of {year}",
    "keep_days": 60,
    "delete_days": 120,
    "message": ("Congratulations, graduate! This school account closes on {close}. "
                "Please use your personal email from now on."),
    "takeout": True,
    "groups": False,
    "gal": True,
    "licenses": True,
}

TAKEOUT_TEXT = (
    "Congratulations on graduating!\n\n"
    "Your school Google account ({email}) will be closed on {close}. Before then, please "
    "save anything you want to keep:\n\n"
    "1. Go to https://takeout.google.com while signed in to your school account.\n"
    "2. Choose what to download (Drive, Gmail, Photos …) and click Create export.\n"
    "3. Google emails you a link to download the files.\n\n"
    "If your school allows it, you can also copy everything straight into a personal "
    "Google account with https://takeout.google.com/transfer.\n\n"
    "After {close} the account and its files will be gone.")


def grad_options() -> dict:
    try:
        saved = json.loads(settings.get("graduation/options", "{}") or "{}")
    except ValueError:
        saved = {}
    return {**GRAD_DEFAULTS, **saved}


def build_graduate(email: str, before: dict, opts: dict, year: int) -> dict:
    today = datetime.date.today()
    keep = int(opts.get("keep_days", 60))
    close = today + datetime.timedelta(days=keep)
    ou = opts.get("alumni_ou", GRAD_DEFAULTS["alumni_ou"]).replace("{year}", str(year))
    name = before.get("name") or email.split("@")[0]
    s0, s1 = [], []
    s0.append(_step("ou", f"Move to {ou}", ["update", "user", email, "ou", ou],
                    undo=["update", "user", email, "ou", before.get("ou") or "/"]))
    if opts.get("message"):
        msg = opts["message"].replace("{name}", name).replace("{close}", close.isoformat())
        s0.append(_step("vacation", f"Auto-reply until {close}",
                        ["user", email, "vacation", "on", "subject", "Graduated",
                         "message", msg, "start", "Started", "end", close.isoformat()],
                        undo=["user", email, "vacation", "off"]))
    if opts.get("takeout"):
        s0.append(_step("takeout", "Email them how to download their files",
                        ["sendemail", "to", email, "subject",
                         f"Save your school files before {close:%B %d}",
                         "message", TAKEOUT_TEXT.format(email=email,
                                                        close=close.strftime("%B %d, %Y"))],
                        note="can't be unsent"))
    if opts.get("groups"):
        for g, role in before.get("groups", []):
            s0.append(_step("groups", f"Leave {g}", ["update", "group", g, "remove", email],
                            undo=["update", "group", g, "add", role or "member", email]))
    if opts.get("gal"):
        s0.append(_step("gal", "Hide from the directory",
                        ["update", "user", email, "gal", "off"],
                        undo=["update", "user", email, "gal", "on"]))
    if opts.get("message"):
        s1.append(_step("later_forward_off", "Turn off the auto-reply",
                        ["user", email, "vacation", "off"]))
    if opts.get("licenses"):
        for sku in before.get("licenses", []):
            s1.append(_step("later_licenses", f"Release license {sku}",
                            ["user", email, "delete", "license", sku],
                            undo=["user", email, "add", "license", sku]))
    s1.append(_step("later_suspend", "Suspend the account",
                    ["update", "user", email, "suspended", "on"],
                    undo=["update", "user", email, "suspended", "off"]))
    stages = [{"key": "today", "title": "Graduation day", "due": today.isoformat(),
               "auto": True, "done": None, "steps": s0},
              {"key": "later", "title": f"After {keep} days", "due": close.isoformat(),
               "auto": True, "done": None, "steps": s1},
              {"key": "delete", "title": f"After {opts.get('delete_days', 120)} days",
               "due": (today + datetime.timedelta(days=int(opts.get("delete_days", 120))))
               .isoformat(), "auto": False, "done": None,
               "steps": [_step("delete", "Delete the account", ["delete", "user", email])]}]
    return {"email": email, "name": name, "supervisor": "", "status": "active",
            "kind": "graduate", "class_of": year,
            "started": datetime.datetime.now().isoformat(timespec="seconds"), "by": _me(),
            "before": before, "stages": stages, "notes": [],
            "options": {"keep_days": keep, "delete_days": opts.get("delete_days"), "ou": ou}}


# ----------------------------------------------------------- data transfers ---
def check_transfers(log=print, run_csv=None) -> list[str]:
    """For leavers whose Drive/Calendar transfer was started, check it finished.
    Saves the result on the record; failed transfers raise an alert."""
    from .directory import run_gam_csv
    from .tools.recovery import transfers, transfers_args
    run_csv = run_csv or (lambda a: run_gam_csv(a, 300))
    lines, failed = [], []
    for rec in load_all():
        if rec.get("status") != "active" or rec.get("transfer_checked") == "completed":
            continue
        started = any(s["key"] == "transfer" and s["status"] == "done"
                      for st in rec["stages"] for s in st["steps"])
        if not started:
            continue
        code, rows, _err = run_csv(transfers_args(rec["email"]))
        if code != 0:
            continue
        t = transfers(rows)
        if not t:
            continue
        states = {r["Status"] for r in t}
        state = "failed" if "failed" in states else "inprogress" if "inprogress" in states \
            else "completed" if states <= {"completed"} else ", ".join(sorted(states))
        if rec.get("transfer_checked") != state:
            rec["transfer_checked"] = state
            save(rec)
            lines.append(f"{rec['email']}: Drive/Calendar transfer {state}.")
            if state == "failed":
                failed.append(rec["email"])
    if failed:
        try:
            from . import alerts
            alerts.notify("Data transfer FAILED for: " + ", ".join(failed) +
                          ". Start it again from Workflows → Staff leaving.",
                          "GAMbit: data transfer failed")
        except Exception:  # noqa: BLE001
            pass
    return lines
