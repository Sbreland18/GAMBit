"""Help-desk tickets handled end to end: for “forgot my password” tickets GAMbit resets
the password, emails it to the person who asked (never into the ticket), adds a note and
resolves the ticket. Your approval rules decide whether that happens straight away or the
ticket waits on the Approvals page first."""

from __future__ import annotations

import json
import os

from ..settings import settings

PASSWORD_WORDS = ("password", "locked out", "can't log in", "cant log in", "can't sign in",
                  "cant sign in", "forgot", "reset my", "won't let me sign", "sign in")


def options() -> dict:
    try:
        o = json.loads(settings.get("ticketing/auto", "{}") or "{}")
    except ValueError:
        o = {}
    return {"enabled": False, "resolve": True, "students_only": True,
            "student_root": "/Students", "send_to": "", "max_per_run": 25, **o}


def save_options(o: dict):
    settings.set("ticketing/auto", json.dumps(o))


def _under(ou: str, root: str) -> bool:
    ou, root = (ou or "/").rstrip("/").lower(), (root or "/").rstrip("/").lower()
    return not root or ou == root or ou.startswith(root + "/")


def is_password_ticket(t: dict) -> bool:
    text = " ".join((t.get("subject", ""), t.get("category", ""), t.get("issue", ""),
                     t.get("description", "")[:400])).lower()
    return t.get("kind") == "account" and any(w in text for w in PASSWORD_WORDS)


def recipient(t: dict, target: str, opts: dict) -> str:
    """Who gets the new password: a fixed address, or whoever the ticket is for – but never
    the locked-out account itself."""
    fixed = (opts.get("send_to") or "").strip()
    if "@" in fixed:
        return fixed
    who = (t.get("for_email") or "").lower()
    return who if who and who != target.lower() else ""


def candidates(tickets: list[dict], users: list[dict], opts: dict,
               done: set[str] = frozenset()) -> list[dict]:
    """Password tickets GAMbit can handle → [{ticket, email, to, why_not}]"""
    by = {u["email"].lower(): u for u in users}
    out = []
    for t in tickets:
        if t["id"] in done or not is_password_ticket(t):
            continue
        email = (t.get("target") or "").lower()
        u = by.get(email)
        why = ""
        if not u:
            why = "account not found"
        elif u.get("suspended"):
            why = "account is suspended"
        elif opts.get("students_only", True) and not _under(u.get("ou"),
                                                            opts.get("student_root")):
            why = "not a student – staff resets stay with a person"
        to = recipient(t, email, opts)
        if not why and not to:
            why = "no one to send the new password to (set a fixed address)"
        out.append({"ticket": t, "email": email, "to": to, "why_not": why})
    return out


def _done_path() -> str:
    from .. import team
    if team.folder():
        d = os.path.join(team.folder(), "tickets")
    else:
        from ..support import logs_dir
        d = os.path.join(os.path.dirname(logs_dir()), "tickets")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "handled.txt")


def handled() -> set[str]:
    try:
        with open(_done_path(), encoding="utf-8") as fh:
            return {ln.strip() for ln in fh if ln.strip()}
    except OSError:
        return set()


def mark_handled(tid: str):
    with open(_done_path(), "a", encoding="utf-8") as fh:
        fh.write(tid + "\n")


def run_one(c: dict, run_text=None, hd=None, opts: dict | None = None,
            note_by: str = "GAMbit") -> tuple[bool, str]:
    """Reset, email, note, resolve. c = {ticket, email, to}."""
    from .. import activity, selfservice
    from ..directory import run_gam_text
    run_text = run_text or run_gam_text
    if hd is None:
        from ..integrations import ticketing as hd
    opts = opts or options()
    t, email, to = c["ticket"], c["email"], c["to"]
    if settings.get("safety/dry_run", False):
        return False, "dry run is on – nothing changed"
    pw = selfservice._password()
    args = selfservice.reset_args(email, pw)
    code, out = run_text(args, 120)
    activity.record(args, code, "done" if code == 0 else "failed", None,
                    settings.get("profile/current", "") or "Default",
                    note=f"help-desk ticket {t.get('number') or t['id']}")
    if code != 0:
        msg = (out or "").strip().splitlines()[-1:] or ["GAM failed"]
        try:
            hd.note(t["id"], f"{note_by}: couldn't reset the password for {email} – "
                             f"{msg[0][:200]}. A person needs to look at this.", False)
        except Exception:  # noqa: BLE001
            pass
        return False, msg[0]
    selfservice._tell_password(to, email, pw)
    text = (f"{note_by} reset the password for {email} and emailed the temporary password "
            f"to {to}. They'll choose a new one when they sign in.")
    try:
        if opts.get("resolve", True) and hd.can("resolve"):
            hd.resolve(t["id"], text)
        elif hd.can("note"):
            hd.note(t["id"], text, False)
    except Exception as exc:  # noqa: BLE001
        return True, f"reset and emailed, but the ticket update failed: {exc}"
    return True, "reset, emailed and " + ("resolved" if opts.get("resolve", True) and
                                          hd.can("resolve") else "noted")


def process(log=print, tickets=None, users=None, run_text=None, hd=None) -> list[str]:
    """Background: handle new password tickets (approval rules decide if a person must OK it)."""
    from .. import approval_policy, selfservice, team
    from ..directory import load_users
    if hd is None:
        from ..integrations import ticketing as hd
    opts = options()
    if not opts.get("enabled") or not hd.configured() or not hd.can("list"):
        return []
    tickets = tickets if tickets is not None else hd.list_open({})
    users = users if users is not None else load_users()
    done = handled()
    lines = []
    for c in candidates(tickets, users, opts, done)[:int(opts.get("max_per_run", 25) or 25)]:
        t = c["ticket"]
        label = f"#{t.get('number') or t['id']}"
        if c["why_not"]:
            mark_handled(t["id"])
            lines.append(f"{label}: left for a person ({c['why_not']}).")
            continue
        rule = approval_policy.auto_rule(selfservice.reset_args(c["email"], "x"), users)
        if not rule:
            if team.folder():
                team.new_request([], f"Help-desk ticket {label}: reset the password for "
                                     f"{c['email']} and email it to {c['to']}.\n"
                                     f"“{t.get('subject', '')}”",
                                 title=f"Ticket {label}: password reset for {c['email']}",
                                 extra={"kind": "ticket_reset", "ticket": t, "email": c["email"],
                                        "to": c["to"]})
                lines.append(f"{label}: sent to Approvals (your approval rules need a person).")
            else:
                lines.append(f"{label}: needs approval but there's no team folder – skipped.")
            mark_handled(t["id"])
            continue
        ok, msg = run_one(c, run_text, hd, opts)
        mark_handled(t["id"])
        lines.append(f"{label}: {c['email']} – {msg}.")
    for ln in lines:
        log(ln)
    return lines


def run_request(req: dict, run_text=None, hd=None) -> tuple[bool, str]:
    """An approved “ticket_reset” request (from the Approvals page or an email reply)."""
    return run_one({"ticket": req["ticket"], "email": req["email"], "to": req["to"]},
                   run_text, hd, note_by="GAMbit (approved)")


__all__ = ["process", "run_one", "candidates", "is_password_ticket"]
