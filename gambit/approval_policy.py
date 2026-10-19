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


def load() -> dict:
    from . import team
    d = team.read_shared("approval_policy.json") if team.folder() else {}
    if not d:
        try:
            d = json.loads(settings.get("approvals/policy", "{}") or "{}")
        except ValueError:
            d = {}
    return {**DEFAULT, **d}


def save(p: dict):
    from . import team
    if team.folder():
        team.write_shared("approval_policy.json", p)
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


def record_approval(req: dict, who: str, policy: dict | None = None) -> tuple[bool, dict]:
    """Add one person's approval. Returns (ready to run, request)."""
    from . import team
    who = (who or "").lower()
    req = dict(req)
    approvals = [a.lower() for a in req.get("approvals", [])]
    if who and who == (req.get("by") or "").lower() and needs_two(req, policy):
        return False, req                    # can't approve your own two-person request
    if who and who not in approvals:
        approvals.append(who)
    req["approvals"] = approvals
    ready = len(approvals) >= (2 if needs_two(req, policy) else 1)
    team.save_request(req)
    return ready, req


def approval_note(req: dict, policy: dict | None = None) -> str:
    if not needs_two(req, policy):
        return ""
    n = len(req.get("approvals", []))
    return f"{n} of 2 approvals" + (f" ({', '.join(req['approvals'])})" if n else "")


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
