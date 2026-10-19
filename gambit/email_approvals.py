"""Approve requests from a phone: each new approval request is emailed to the approvers,
who reply APPROVE or DENY. The background “staff requests” task (every 15 minutes) reads
the replies from the sending mailbox and acts on them.

No server is needed – it all goes through Gmail with GAM. Only replies from the approver
addresses listed in Settings count, and each reply is used once.
"""

from __future__ import annotations

import datetime
import os
import re

from .settings import settings

SUBJECT_TAG = "GAMbit approval"
ID_RE = re.compile(r"\[GAMbit approval ([0-9A-Za-z-]+)\]")
SPECIAL = ("offboard", "selfservice")


def approvers() -> list[str]:
    raw = settings.get("approvals/emails", "") or ""
    return [e.strip().lower() for e in re.split(r"[,;\s]+", raw) if "@" in e]


def enabled() -> bool:
    return bool(settings.get("approvals/email_on", False)) and bool(approvers())


def subject(req: dict) -> str:
    return f"[{SUBJECT_TAG} {req['id']}] {req.get('title', '')}"[:200]


def body(req: dict) -> str:
    from .gam_runner import display_command
    cmds = "\n".join("  " + display_command(c) for c in req.get("commands", [])[:30])
    more = len(req.get("commands", [])) - 30
    return (f"{req.get('by', 'Someone')} asked GAMbit for approval:\n\n"
            f"{req.get('title', '')}\n{req.get('reason', '')}\n\n"
            + (f"Commands:\n{cmds}\n" + (f"  … and {more} more\n" if more > 0 else "")
               if cmds else "")
            + "\nReply to this email with APPROVE or DENY as the first word "
              "(you can add a note after it).\n"
              "Replies are picked up within about 15 minutes.\n")


def send_request(req: dict, run_text=None) -> bool:
    if not enabled():
        return False
    from . import google_io
    from .directory import run_gam_text
    run_text = run_text or run_gam_text
    code, _out = run_text(google_io.email_args(",".join(approvers()), subject(req), body(req)),
                          120)
    return code == 0


def _processed_path() -> str:
    from . import team
    d = os.path.join(team.folder(), "approvals")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "email_processed.txt")


def _processed() -> set[str]:
    try:
        with open(_processed_path(), encoding="utf-8") as fh:
            return {ln.strip() for ln in fh if ln.strip()}
    except OSError:
        return set()


def _mark(mid: str):
    with open(_processed_path(), "a", encoding="utf-8") as fh:
        fh.write(mid + "\n")


def replies_args(mailbox: str) -> list[str]:
    return ["user", mailbox, "print", "messages", "query",
            f'subject:"{SUBJECT_TAG}" newer_than:14d -from:me',
            "headers", "from,subject", "showbody", "max_to_print", "200"]


def parse_reply(row: dict) -> dict | None:
    low = {(k or "").lower(): (v or "") for k, v in row.items()}
    m = ID_RE.search(low.get("subject", ""))
    if not m:
        return None
    sender = re.search(r"[\w.+'-]+@[\w.-]+", low.get("from", ""))
    text = (low.get("body", "") or low.get("snippet", "")).replace("\\r\\n", "\n") \
        .replace("\\n", "\n").strip()
    first = text.split("\n", 1)[0].strip()
    word = re.match(r"\W*(approve[ds]?|yes|deny|denied|no)\b", first, re.I)
    if not sender or not word:
        return None
    decision = "approve" if word.group(1).lower().startswith(("appro", "yes")) else "deny"
    note = first[word.end():].strip(" -:,.")
    return {"id": m.group(1), "from": sender.group(0).lower(), "decision": decision,
            "note": note, "message_id": low.get("id", "")}


def process(log=print, run_text=None, run_csv=None) -> list[str]:
    """Read replies and act on them. Returns lines for the log."""
    from . import activity, google_io, team
    from .directory import run_gam_csv, run_gam_text
    if not enabled() or not team.folder():
        return []
    run_text = run_text or run_gam_text
    run_csv = run_csv or (lambda a: run_gam_csv(a, 300))
    mailbox = google_io.admin_email()
    if "@" not in mailbox:
        return ["Email approvals: set the Google account in Settings → Google Sheets and email."]
    code, rows, err = run_csv(replies_args(mailbox))
    if code != 0:
        return [f"Email approvals: couldn't read replies – {(err or '').strip()[-200:]}"]
    done_ids = _processed()
    pending = {r["id"]: r for r in team.list_requests("pending")}
    allowed = set(approvers())
    lines = []
    for row in rows:
        rep = parse_reply(row)
        if not rep or not rep["message_id"] or rep["message_id"] in done_ids:
            continue
        _mark(rep["message_id"])
        req = pending.get(rep["id"])
        if not req:
            continue
        if rep["from"] not in allowed:
            lines.append(f"Ignored a reply from {rep['from']} – not an approver.")
            continue
        note = f"by email from {rep['from']}" + (f": {rep['note']}" if rep["note"] else "")
        if rep["decision"] == "deny":
            team.update_request(req, "denied", note=note)
            lines.append(f"Denied “{req['title']}” ({note}).")
            continue
        from . import approval_policy
        ready, req = approval_policy.record_approval(req, rep["from"])
        pending[req["id"]] = req            # a second reply in this batch builds on this one
        if not ready:
            team.update_request(req, "pending", note=f"First approval {note} – waiting for a "
                                                    "second approver.")
            lines.append(f"“{req['title']}”: first approval from {rep['from']}; it needs a "
                         "second person.")
            continue
        if req.get("kind") == "ticket_reset":
            from .tools import ticket_auto
            req = team.update_request(req, "approved", note=note)
            ok, msg = ticket_auto.run_request(req, run_text)
            team.update_request(req, "done" if ok else "failed", note=note, result=msg)
            lines.append(f"Approved by email: “{req['title']}” – {msg}.")
            pending.pop(req["id"], None)
            continue
        if req.get("kind") in SPECIAL:
            req["remote_approved_by"] = rep["from"]
            team.update_request(req, "pending", note=f"Approved {note} – open Approvals to "
                                                    "finish (it needs GAMbit).")
            lines.append(f"“{req['title']}” approved by email – finish it on the Approvals page.")
            continue
        req = team.update_request(req, "approved", note=note)
        codes = []
        for cmd in req.get("commands", []):
            c, out = run_text(cmd, 600)
            codes.append(c)
            activity.record(cmd, c, "done" if c == 0 else "failed", None,
                            settings.get("profile/current", "") or "Default",
                            note=f"approved by email by {rep['from']} (request {req['id']})")
        ok = all(c == 0 for c in codes)
        team.update_request(req, "done" if ok else "failed", note=note,
                            result="all commands worked" if ok else
                            f"{sum(c != 0 for c in codes)} command(s) failed")
        lines.append(f"Approved by email and ran “{req['title']}”: "
                     f"{'done' if ok else 'some commands failed'}.")
        pending.pop(req["id"], None)
    if lines:
        settings.set("approvals/email_last", datetime.datetime.now().isoformat(
            timespec="minutes"))
    return lines
