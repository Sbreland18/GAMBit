"""Approval rules: approve low-risk requests automatically (e.g. password resets for
students), require two different people for deletes and other big changes, and escalate
requests nobody has answered after a set number of hours."""

from __future__ import annotations

import datetime
import json
import re

from .settings import settings

DEFAULT = {"auto": [{"category": "passwords", "students_only": True}],
           "two_person": ["delete"], "escalate_hours": 24, "escalate_to": "",
           "student_root": "/Students", "on": False}
ENTITY_WORDS = {"ou", "ou_and_children", "ous", "ous_and_children", "group", "groups",
                "all", "query", "csv", "file", "csvfile", "course", "courses", "cros_ou",
                "cros_ou_and_children", "ou_ns", "ou_and_children_ns", "group_ns"}


# What applies when the shared rules can't be trusted (edited in the team folder, or not
# signed by a GAMbit admin): nothing is approved automatically and deletes need two people.
STRICT = {**DEFAULT, "auto": [], "on": True, "escalate_hours": 0, "unverified": True}


def load() -> dict:
    from . import team
    if team.folder():
        d = team.read_shared("approval_policy.json")
        if d:
            d, v = team.read_shared_verified("approval_policy.json", "approvalpolicy")
            if v is None:
                return dict(STRICT)
            return {**DEFAULT, **d}
    try:
        d = json.loads(settings.get("approvals/policy", "{}") or "{}")
    except ValueError:
        d = {}
    if team.folder() and d:
        return dict(STRICT) if d.get("on") or d.get("auto") else {**DEFAULT, **d}
    return {**DEFAULT, **(d if isinstance(d, dict) else {})}


def save(p: dict):
    from . import team
    p = {k: v for k, v in p.items() if k not in ("seal", "unverified")}
    if team.folder():
        if not team.is_admin():
            raise PermissionError("Only a GAMbit admin can change the approval rules.")
        team.write_shared_signed("approval_policy.json", "approvalpolicy", p)
    settings.set("approvals/policy", json.dumps(p))


def _under(ou: str, root: str) -> bool:
    ou, root = (ou or "/").rstrip("/").lower(), (root or "/").rstrip("/").lower()
    return not root or ou == root or ou.startswith(root + "/")


def targets(args: list[str]) -> list[str]:
    return [a.lower() for a in args if re.fullmatch(r"[\w.+'-]+@[\w.-]+\.\w+", a or "")]


def auto_rule(args: list[str], users: list[dict], policy: dict | None = None) -> str:
    """If a request for these args is approved automatically, the rule that allows it."""
    from . import team
    p = policy or load()
    if not p.get("on"):
        return ""
    cats = team.categorize(args) - {"read"}
    if not cats:
        return ""
    rules = {r["category"]: r for r in p.get("auto", []) if r.get("category")}
    if not cats <= set(rules):
        return ""
    if any(rules[c].get("students_only") for c in cats):
        low = [a.lower() for a in args]
        if set(low) & ENTITY_WORDS:
            return ""
        emails = targets(args)
        by = {u["email"].lower(): u for u in users}
        if not emails or not all(e in by and _under(by[e].get("ou"), p.get("student_root"))
                                 for e in emails):
            return ""
    return "automatic approval: " + ", ".join(sorted(team.CATEGORIES.get(c, c).split(" (")[0]
                                                     for c in cats))


def needs_two(req: dict, policy: dict | None = None) -> bool:
    from . import team
    p = policy or load()
    if not p.get("on"):
        return False
    two = set(p.get("two_person", []))
    if req.get("kind") == "offboard" and "delete" in two:
        return True
    def risky(c):
        low = [a.lower() for a in c]
        if "license" in low and "delete" in low:       # releasing a license isn't destructive
            return False
        return bool(team.categorize(c) & two)
    return any(risky(c) for c in req.get("commands", []))


APPROVAL_FIELDS = ("request", "who", "decision", "hash", "at", "via")


def _approval_body(a: dict) -> dict:
    return {k: a.get(k) for k in APPROVAL_FIELDS}


def make_approval(req: dict, who: str, via: str = "app") -> dict:
    """One person's approval of these exact commands, signed on this computer."""
    from . import seal
    a = {"request": req.get("id", ""), "who": (who or "").lower(), "decision": "approve",
         "hash": seal.commands_hash(req.get("commands", [])),
         "at": datetime.datetime.now().isoformat(timespec="seconds"), "via": via}
    a["seal"] = seal.seal_for("approval", _approval_body(a))
    return a


def valid_approvers(req: dict, policy: dict | None = None) -> list[str]:
    """People whose approval of the request *as it is now* checks out: signed, for these
    exact commands, by the approver themselves (or recorded by a computer this one
    trusts), allowed to approve, and – for two-person requests – not the requester."""
    from . import seal, team
    h = seal.commands_hash(req.get("commands", []))
    claimed = (req.get("by") or "").lower()
    vreq = team.verify_request(req)
    requesters = {claimed} | ({vreq.who} if vreq and vreq.who else set())
    two = needs_two(req, policy)
    doc = seal._doc() if seal.signin_required() else {}
    out: list[str] = []
    for a in req.get("approvals", []) or []:
        if not isinstance(a, dict):
            continue                          # approvals saved before they were signed
        v = seal.check_seal("approval", _approval_body(a), a.get("seal"))
        who = str(a.get("who", "")).lower()
        if v is None or a.get("decision") != "approve" or a.get("hash") != h or \
                a.get("request") != req.get("id") or not who:
            continue
        if v.level in ("admin", "member") and v.who != who:
            continue                          # someone signing on another's behalf
        if seal.signin_required():
            from .auth import access
            p = access.person(doc, who) if doc else None
            if not p or not p["role"].get("admin"):
                continue
        if two and who in requesters:
            continue
        if who not in out:
            out.append(who)
    return out


def record_approval(req: dict, who: str, policy: dict | None = None,
                    via: str = "app") -> tuple[bool, dict]:
    """Add one person's (signed) approval. Returns (ready to run, request)."""
    from . import team
    who = (who or "").lower()
    req = dict(req)
    approvals = [a for a in req.get("approvals", []) or [] if isinstance(a, dict)]
    if who and who not in valid_approvers({**req, "approvals": approvals}, policy):
        approvals.append(make_approval(req, who, via))
    req["approvals"] = approvals
    have = valid_approvers(req, policy)
    ready = len(have) >= (2 if needs_two(req, policy) else 1)
    team.save_request(req)
    return ready, req


def approval_note(req: dict, policy: dict | None = None) -> str:
    if not needs_two(req, policy):
        return ""
    have = valid_approvers(req, policy)
    n = len(have)
    return f"{n} of 2 approvals" + (f" ({', '.join(have)})" if n else "")


def overdue(reqs: list[dict], hours: int, now: datetime.datetime | None = None) -> list[dict]:
    now = now or datetime.datetime.now()
    cut = (now - datetime.timedelta(hours=hours)).isoformat(timespec="seconds")
    return [r for r in reqs if r.get("status") == "pending" and r.get("time", "") <= cut
            and not r.get("escalated")]


def escalate(log=print, now=None) -> int:
    from . import alerts, team
    p = load()
    if not p.get("on") or not int(p.get("escalate_hours", 0) or 0) or not team.folder():
        return 0
    late = overdue(team.list_requests("pending"), int(p["escalate_hours"]), now)
    if not late:
        return 0
    text = (f"{len(late)} approval request(s) have waited more than {p['escalate_hours']} "
            "hours:\n" + "\n".join(f"• {r.get('title', '')} – asked by {r.get('by', '')} on "
                                   f"{r.get('time', '')[:16].replace('T', ' ')}"
                                   for r in late[:30]) +
            "\n\nOpen GAMbit → Approvals, or reply to the original approval email.")
    alerts.notify(text, "GAMbit: approvals waiting")
    to = (p.get("escalate_to") or "").strip()
    if "@" in to:
        try:
            from . import google_io
            google_io.send_email(to, "GAMbit: approvals waiting", text)
        except Exception as exc:  # noqa: BLE001
            log(f"Couldn't email the escalation: {exc}")
    stamp = datetime.datetime.now().isoformat(timespec="minutes")
    for r in late:
        r["escalated"] = stamp
        team.save_request(r)
    log(f"Escalated {len(late)} waiting request(s).")
    return len(late)


def log_auto(args: list[str], rule: str) -> dict:
    """Keep an audit record of an automatically approved request."""
    from . import team
    req = team.new_request([list(args)], rule, title="", extra={
        "status": "done", "decided_by": "approval rules", "auto": True,
        "decided": datetime.datetime.now().isoformat(timespec="seconds"), "note": rule},
        notify=False)
    return req
