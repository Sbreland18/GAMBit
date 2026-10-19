"""Ownership check: groups with no (active) owner, shared drives with no (active) manager,
Classroom classes owned by someone who has left, and suspended accounts still holding Drive
files – each with a one-click hand-off to the right person."""

from __future__ import annotations

import re

GROUPS_ARGS = ["print", "groups", "fields", "email,name,directmemberscount", "owners"]
COURSES_ARGS = ["print", "courses", "states", "active", "owneremail", "fields",
                "id,name,section,ownerid"]
STORAGE_ARGS = ["report", "users", "parameters", "accounts:drive_used_quota_in_mb"]


def drives_args(admin: str) -> list[str]:
    return ["user", admin, "print", "shareddriveacls", "asadmin", "roles", "organizer",
            "shownopermissionsdrives", "true", "oneitemperrow"]


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _emails(text: str) -> list[str]:
    return [e.lower() for e in re.findall(r"[\w.+'-]+@[\w.-]+\.\w+", text or "")]


def _active(email: str, users: dict) -> bool:
    u = users.get(email.lower())
    return bool(u) and not u.get("suspended")


_DOM: dict = {}


def _counts(email: str, users: dict) -> bool:
    """An owner counts if they're an active account here, or outside the district's domains
    (we can't see those, so assume they're fine)."""
    key = id(users)
    if _DOM.get("key") != key:
        _DOM.update(key=key, domains={e.split("@")[1] for e in users})
    domains = _DOM["domains"]
    return _active(email, users) or email.split("@")[-1] not in domains


def _f(kind, what, who, problem, fix_to="", args=None, item_id=""):
    return {"Kind": kind, "What": what, "Owner(s) now": who, "Problem": problem,
            "Hand to": fix_to, "args": args or [], "id": item_id}


def groups(rows: list[dict], users: dict, fallback: str = "") -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        g = low.get("email", "")
        if not g:
            continue
        owners = _emails(" ".join(v for k, v in low.items() if k.startswith("owners")
                                  and "count" not in k))
        active = [o for o in owners if _counts(o, users)]
        if not owners:
            out.append(_f("Group", g, "", "no owner", fallback,
                          [["update", "group", g, "add", "owner", "user", fallback]]
                          if fallback else [], g))
        elif not active:
            out.append(_f("Group", g, ", ".join(owners), "every owner has left", fallback,
                          [["update", "group", g, "add", "owner", "user", fallback]]
                          if fallback else [], g))
    return out


def shared_drives(rows: list[dict], users: dict, admin: str, fallback: str = "") -> list:
    drives: dict[str, dict] = {}
    for r in rows:
        low = _low(r)
        did = low.get("id", "")
        if not did:
            continue
        d = drives.setdefault(did, {"name": low.get("name", ""), "managers": []})
        e = low.get("permission.emailaddress", "")
        if e and low.get("permission.role", "organizer") == "organizer":
            d["managers"].append(e.lower())
    out = []
    for did, d in drives.items():
        active = [m for m in d["managers"] if _counts(m, users)]
        if not active:
            args = [["user", admin, "add", "drivefileacl", did, "user", fallback, "role",
                     "organizer", "asadmin"]] if fallback and admin else []
            out.append(_f("Shared drive", d["name"] or did, ", ".join(d["managers"]),
                          "no manager" if not d["managers"] else "every manager has left",
                          fallback, args, did))
    return out


def courses(rows: list[dict], users: dict, fallback_for=None) -> list[dict]:
    """fallback_for(owner_email) → who should own it (e.g. their supervisor)."""
    out = []
    for r in rows:
        low = _low(r)
        cid, owner = low.get("id", ""), low.get("owneremail", "").lower()
        if not cid or not owner or _active(owner, users):
            continue
        to = fallback_for(owner) if fallback_for else ""
        args = [["course", cid, "add", "teacher", to], ["update", "course", cid, "owner", to]] \
            if to else []
        name = low.get("name", "") + (f" ({low['section']})" if low.get("section") else "")
        out.append(_f("Classroom class", name, owner, "owner has left", to, args, cid))
    return out


def suspended_storage(rows: list[dict], users: dict, min_mb: int = 100,
                      fallback_for=None) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        e = low.get("email", "").lower()
        u = users.get(e)
        try:
            mb = float(low.get("accounts:drive_used_quota_in_mb") or 0)
        except ValueError:
            mb = 0
        if not u or not u.get("suspended") or mb < min_mb:
            continue
        to = fallback_for(e) if fallback_for else ""
        args = [["create", "datatransfer", e, "gdrive", to, "privacy_level", "shared,private"]] \
            if to else []
        out.append(_f("Drive files", f"{mb / 1024:.1f} GB", e, "suspended account still holds "
                      "files", to, args, e))
    return out


def supervisor_lookup(users: list[dict], offboard_records=None, default: str = ""):
    """Who should inherit: the supervisor saved when they were offboarded, else default."""
    sup = {}
    for rec in offboard_records or []:
        if rec.get("supervisor"):
            sup[rec.get("email", "").lower()] = rec["supervisor"].lower()
    return lambda e: sup.get(e.lower()) or default
