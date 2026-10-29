"""Approve requests from a phone: each new approval request is emailed to the approvers,
who reply APPROVE or DENY. The background “staff requests” task (every 15 minutes) reads
the replies from the sending mailbox and acts on them.

No server is needed – it all goes through Gmail with GAM. Replies are read from each
approver's own *Sent* mail (so a message that only claims to come from an approver – a
forged From line – never counts), each reply is used once, and every email carries a
fingerprint of the exact commands: if the request is changed after the email went out, the
reply no longer matches and nothing runs.
"""

from __future__ import annotations

import datetime
import os
import re

from .settings import settings

SUBJECT_TAG = "GAMbit approval"
ID_RE = re.compile(r"\[GAMbit approval ([0-9A-Za-z-]+)(?: ([0-9a-f]{16}))?\]")
SPECIAL = ("offboard", "selfservice")


def approvers() -> list[str]:
    """Approver addresses. With GAMbit sign-in on, only GAMbit admins count."""
    raw = settings.get("approvals/emails", "") or ""
    out = [e.strip().lower() for e in re.split(r"[,;\s]+", raw)
           if re.fullmatch(r"[\w.+'-]+@[\w-]+(\.[\w-]+)+", e.strip())]
    from . import seal
    if seal.signin_required():
        doc = seal._doc()
        from .auth import access
        out = [e for e in out if doc and (access.person(doc, e) or {}).get("role", {})
               .get("admin")]
    return out


def enabled() -> bool:
    return bool(settings.get("approvals/email_on", False)) and bool(approvers())


def subject(req: dict) -> str:
    from . import seal
    title = re.sub(r"[\r\n]+", " ", str(req.get("title", "")))
    return (f"[{SUBJECT_TAG} {req['id']} {seal.commands_hash(req.get('commands', []))}] "
            f"{title}")[:200]


def body(req: dict) -> str:
    from .gam_runner import display_command
    cmds = "\n".join("  " + display_command(c) for c in req.get("commands", [])[:60])
    more = len(req.get("commands", [])) - 60
    return (f"{req.get('by', 'Someone')} asked GAMbit for approval:\n\n"
            f"{req.get('title', '')}\n{req.get('reason', '')}\n\n"
            + (f"Commands:\n{cmds}\n" + (f"  … and {more} more – open GAMbit → Approvals "
                                           "to see them all before approving\n"
                                           if more > 0 else "")
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


def replies_args(approver: str) -> list[str]:
    """Replies are read from the approver's own Sent mail – only their account can put a
    message there."""
    return ["user", approver, "print", "messages", "query",
            f'in:sent subject:"{SUBJECT_TAG}" newer_than:14d',
            "headers", "from,subject", "showbody", "max_to_print", "200"]


def _sender(from_header: str) -> str:
    from email.utils import getaddresses
    addrs = [a for _n, a in getaddresses([from_header or ""]) if "@" in a]
    return addrs[0].strip().lower() if len(addrs) == 1 else ""


def parse_reply(row: dict, mailbox: str = "") -> dict | None:
    low = {(k or "").lower(): (v or "") for k, v in row.items()}
    m = ID_RE.search(low.get("subject", ""))
    if not m:
        return None
    sender = _sender(low.get("from", ""))
    if mailbox and sender != mailbox.lower():
        return None                    # in their Sent folder but not from them
    text = (low.get("body", "") or low.get("snippet", "")).replace("\\r\\n", "\n") \
        .replace("\\n", "\n").strip()
    first = text.split("\n", 1)[0].strip()
    word = re.match(r"\W*(approve[ds]?|yes|deny|denied|no)\b", first, re.I)
    if not sender or not word:
        return None
    decision = "approve" if word.group(1).lower().startswith(("appro", "yes")) else "deny"
    note = first[word.end():].strip(" -:,.")
    mid = low.get("id", "")
    return {"id": m.group(1), "hash": m.group(2) or "", "from": sender,
            "decision": decision, "note": note,
            "message_id": f"{sender}:{mid}" if mid else ""}


def process(log=print, run_text=None, run_csv=None) -> list[str]:
    """Read replies and act on them. Returns lines for the log."""
    from . import activity, google_io, seal, secret_args, team
    from .directory import run_gam_csv, run_gam_text
    if not enabled() or not team.folder():
        return []
    run_text = run_text or run_gam_text
    run_csv = run_csv or (lambda a: run_gam_csv(a, 300))
    if "@" not in google_io.admin_email():
        return ["Email approvals: set the Google account in Settings → Google Sheets and email."]
    replies, lines = [], []
    for who in approvers():
        code, rows, err = run_csv(replies_args(who))
        if code != 0:
            lines.append(f"Email approvals: couldn't read {who}'s replies – "
                         f"{(err or '').strip()[-200:]}")
            continue
        replies += [r for r in (parse_reply(row, who) for row in rows) if r]
    done_ids = _processed()
    pending = {r["id"]: r for r in team.list_requests("pending")}
    allowed = set(approvers())
    for rep in replies:
        if not rep["message_id"] or rep["message_id"] in done_ids:
            continue
        _mark(rep["message_id"])
        req = pending.get(rep["id"])
        if not req:
            continue
        if rep["from"] not in allowed:
            lines.append(f"Ignored a reply from {rep['from']} – not an approver.")
            continue
        now_hash = seal.commands_hash(req.get("commands", []))
        if rep["hash"] != now_hash:
            lines.append(f"“{req.get('title', '')}”: the reply from {rep['from']} doesn't "
                         "match the request as it is now (it changed after the email went "
                         "out, or the email is from an older GAMbit) – nothing was run. "
                         "Approve it on the Approvals page.")
            continue
        note = f"by email from {rep['from']}" + (f": {rep['note']}" if rep["note"] else "")
        if rep["decision"] == "deny":
            team.update_request(req, "denied", note=note)
            lines.append(f"Denied “{req['title']}” ({note}).")
            continue
        from . import approval_policy
        ready, req = approval_policy.record_approval(req, rep["from"], via="email")
        pending[req["id"]] = req            # a second reply in this batch builds on this one
        if not ready:
            team.update_request(req, "pending", note=f"Approval {note} recorded – it needs "
                                                    "another approver.")
            lines.append(f"“{req['title']}”: approval from {rep['from']} recorded; it needs "
                         "a second person.")
            continue
        if req.get("kind") == "ticket_reset":
            from .tools import ticket_auto
            req = team.update_request(req, "approved", note=note)
            ok, msg = ticket_auto.run_request(req, run_text)
            team.update_request(req, "done" if ok else "failed", note=note, result=msg)
            lines.append(f"Approved by email: “{req['title']}” – {msg}.")
            pending.pop(req["id"], None)
            continue
        new_pw = any(secret_args.has_placeholder(c) for c in req.get("commands", []))
        if req.get("kind") in SPECIAL or new_pw:
            req["remote_approved_by"] = rep["from"]
            team.update_request(req, "pending", note=f"Approved {note} – open Approvals to "
                                                    "finish" + (" (a new password has to be "
                                                                "shown to someone)"
                                                                if new_pw else
                                                                " (it needs GAMbit)") + ".")
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
