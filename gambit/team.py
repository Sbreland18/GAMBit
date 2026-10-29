"""Team features: a shared team folder with custom roles, approval requests and
shared templates.

The team folder is any folder every tech can reach – a mapped drive, a file
share, or a Google Drive for desktop folder. Layout:

    <team>/roles.json                 roles + who has which role
    <team>/requests/<id>.json         approval requests (one file each)
    <team>/templates/builder.json     shared Command Builder favorites/templates
    <team>/templates/workflows.json   shared workflow settings
    <team>/activity/                  team activity log (if not set separately)

Roles are guard rails inside GAMbit, not a security boundary: GAM itself still
runs with the admin access it was set up with on that PC.
"""

from __future__ import annotations

import datetime
import getpass
import json
import os
import uuid
from typing import Optional

from .settings import settings

# ------------------------------------------------------------- categories ---
CATEGORIES = {
    "read": "Look things up (print, show, info, reports)",
    "passwords": "Reset passwords and require password changes",
    "users": "Create users and change user details (name, org unit, aliases)",
    "groups": "Change group members and settings",
    "chromebooks": "Update Chromebooks (move, assign, notes, re-enable)",
    "email": "Email settings (out-of-office, signatures, delegates, filters, forwarding)",
    "drive": "Google Drive (sharing, ownership, shared drives)",
    "classroom": "Classroom (courses, teachers, students)",
    "suspend": "Suspend accounts and disable Chromebooks",
    "delete": "Delete, wipe, deprovision and transfer data",
    "everyone": "Commands aimed at the whole domain or a whole org unit",
    "other": "Everything else (licenses, Vault, calendars, admin roles …)",
}
ALL_CATEGORIES = list(CATEGORIES)

READ = {"print", "show", "info", "report", "check", "version", "help", "checkconnection",
        "get", "download"}
DESTRUCTIVE = {"delete", "del", "purge", "wipe_users", "remote_powerwash", "deprovision",
               "deprov", "empty", "clear", "cancel", "datatransfer", "transfer", "wipe",
               "undelete", "turnoff2sv", "trash"}
EMAIL = {"vacation", "signature", "delegate", "delegates", "filter", "filters", "forward",
         "forwardingaddress", "forwardingaddresses", "imap", "pop", "sendas", "label",
         "labels", "messages", "message", "sendemail"}
DRIVE = {"drivefile", "drivefileacl", "drivefileacls", "shareddrive", "shareddrives",
         "drivefileowner", "filelist", "drivesettings", "transferdrive", "teamdrive"}


TRUE_WORDS = {"on", "true", "yes", "enabled", "1"}       # every way GAM says “yes”
# what a command GAMbit can't follow (a batch file, odd wrapper options) needs: everything
UNKNOWN = {"delete", "everyone", "other", "suspend"}


def categorize(args: list[str]) -> set[str]:
    """Which permission categories a GAM command needs. The real command behind GAM's
    wrappers (select, config, redirect, csv … gam) is what counts, and only its action
    word decides whether it's a look-up – an unknown action counts as a change."""
    from .activity import (MODIFY_VERBS, READ_EXTRA, READ_VERBS, is_change, unwrap,
                           verb_index)
    inner, understood, cfg = unwrap([str(a) for a in args])
    if not understood:
        return set(UNKNOWN)
    low = [a.lower() for a in inner]
    cats: set[str] = set()
    if cfg:
        cats.add("other")                      # it rewrites GAM's own settings
    if not low:
        return cats or {"read"}
    vi = verb_index(low)
    verb = low[vi] if vi < len(low) else ""
    looks_read = (verb in READ_VERBS or verb in READ_EXTRA) and verb not in MODIFY_VERBS \
        and not is_change(inner)
    # whole domain / whole OU targets
    if (low[0] == "all" and len(low) > 1 and low[1] in ("users", "users_ns", "cros")) or \
            low[0] in ("ou", "ou_and_children", "ous", "ous_and_children", "ou_ns",
                       "ou_and_children_ns"):
        if not looks_read:
            cats.add("everyone")
    for i, a in enumerate(low):
        nxt = low[i + 1] if i + 1 < len(low) else ""
        if a in DESTRUCTIVE and not looks_read:
            cats.add("delete")
        if a in ("suspended", "suspend") and (nxt in TRUE_WORDS or (
                a == "suspend" and i == vi)):
            cats.add("suspend")
        if a == "command" and nxt in ("remote_powerwash", "wipe_users"):
            cats.add("delete")
        if a == "tokens" and low[i - 1:i] == ["delete"]:
            cats.add("everyone" if low[0] in ("all", "ou_and_children") else "other")
        if a == "action" and (nxt == "disable" or nxt.startswith("deprovision")):
            cats.add("suspend" if nxt == "disable" else "delete")
    wrapper = [str(a).lower() for a in args][:max(0, len(args) - len(low))]
    if not looks_read and any(w in ("csv", "loop", "csvtest") for w in wrapper):
        cats.add("everyone")                   # once per row of a file: a bulk change
    if looks_read:
        return cats or {"read"}
    joined = set(low)
    if "password" in joined or "changepassword" in joined or "signout" in joined or \
            "turnoff2sv" in joined or "backupcodes" in joined:
        cats.add("passwords")
    if joined & {"cros", "cros_sn", "crosfile", "cros_ou", "cros_ou_and_children",
                 "issuecommand", "crostelemetry", "printer", "chromepolicy"}:
        cats.add("chromebooks")
    if joined & {"group", "groups", "group_ns", "cigroup", "cigroups"}:
        cats.add("groups")
    if joined & EMAIL:
        cats.add("email")
    if joined & DRIVE:
        cats.add("drive")
    if {"course", "courses", "course-participants", "classroominvitation"} & joined:
        cats.add("classroom")
    if {"calendars", "event", "events"} & joined or ("sendas" in joined):
        cats.add("email")
    if {"orphans", "filedrivelabels"} & joined:
        cats.add("drive")
    if ({"user", "users", "alias", "aliases", "photo"} & joined) and not (
            cats & {"passwords", "groups", "email", "drive", "classroom", "chromebooks",
                    "suspend", "delete"}):
        cats.add("users")
    if low[:2] in (["create", "user"], ["add", "user"]):
        cats.add("users")
    # update user X ... password + other attrs: needs users too
    if low[:2] == ["update", "user"] and any(
            a in ("firstname", "lastname", "ou", "org", "email", "primaryemail")
            for a in low[3:]):
        cats.add("users")
    if not cats:
        cats.add("other")
    return cats


# -------------------------------------------------------------- built-ins ---
BUILTIN_ROLES = {
    "Full admin": {
        "description": "Everything, plus managing roles and approving requests.",
        "pages": ["*"], "can": ALL_CATEGORIES, "ask": [], "admin": True},
    "Help desk": {
        "description": "Day-to-day account help. Suspends and deletes need approval.",
        "pages": ["Home", "Workflows", "Users", "Student lookup", "Account timeline",
                  "Groups", "Classroom", "Email",
                  "Google Drive", "Chromebooks", "Chromebook fleet", "Reports",
                  "Activity log", "Approvals", "Settings & Updates"],
        "can": ["read", "passwords", "users", "groups", "chromebooks", "email", "drive",
                "classroom"],
        "ask": ["suspend", "delete", "everyone", "other"], "admin": False},
    "Chromebook tech": {
        "description": "Chromebooks and check-in/out only.",
        "pages": ["Home", "Chromebooks", "Chromebook fleet", "Workflows", "Activity log",
                  "Approvals"],
        "workflows": ["Chromebook check-in/out"],
        "can": ["read", "chromebooks"], "ask": ["suspend"], "admin": False},
    "Office manager": {
        "description": "Reset passwords and manage group members.",
        "pages": ["Home", "Student lookup", "Users", "Groups", "Account timeline",
                  "Activity log", "Approvals"],
        "can": ["read", "passwords", "groups"], "ask": ["suspend", "users"],
        "admin": False},
}


LOOKUP_ONLY = "Look things up only"
LOOKUP_ONLY_ROLE = {"description": "Used when a role can't be found: look-ups only.",
                    "pages": ["Home", "Student lookup", "Account timeline"], "can": ["read"],
                    "ask": [], "admin": False}


# ----------------------------------------------------------------- folder ---
def folder() -> str:
    return (settings.get("team/folder", "") or "").strip()


def _path(*parts) -> str:
    return os.path.join(folder(), *parts)


def me() -> str:
    from .auth import session
    if session.active():
        return session.email()
    try:
        return getpass.getuser().lower()
    except Exception:  # noqa: BLE001
        return "unknown"


def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{uuid.uuid4().hex[:6]}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


# ------------------------------------------------------------------ roles ---
def load_roles() -> dict:
    """{"roles": {...}, "people": {user: role}, "default_role": name}"""
    from .auth import session
    d = session.doc()
    if d:                      # signed access list (GAMbit sign-in is on)
        from .auth.access import all_roles
        return {"roles": all_roles(d),
                "people": {e.lower(): p.get("role", "") for e, p in d.get("people", {}).items()
                           if p.get("enabled", True)},
                "default_role": d.get("default_role", "No access"), "signed": True}
    if not folder():
        return {"roles": dict(BUILTIN_ROLES), "people": {}, "default_role": "Full admin"}
    data = _read_json(_path("roles.json"), {})
    roles = dict(BUILTIN_ROLES)
    roles.update(data.get("roles", {}))
    return {"roles": roles, "people": {k.lower(): v for k, v in
                                       data.get("people", {}).items()},
            "default_role": data.get("default_role", "Full admin")}


def save_roles(data: dict):
    from .auth import session
    d = session.doc()
    if d:
        from .auth import access
        new = dict(d)
        new["roles"] = {k: v for k, v in data["roles"].items()
                        if k != access.NO_ACCESS and (k not in BUILTIN_ROLES or
                                                      v != BUILTIN_ROLES[k])}
        people = dict(d.get("people", {}))
        for e, role in data.get("people", {}).items():
            people.setdefault(e, {"enabled": True,
                                  "added": datetime.date.today().isoformat()})["role"] = role
        new["people"] = people
        new["default_role"] = data.get("default_role", access.NO_ACCESS)
        signer = access.local_signer(new, me()) or me()
        session.set_doc(access.save(new, signer))
        return
    if not folder():
        raise RuntimeError("Choose a team folder first.")
    custom = {k: v for k, v in data["roles"].items()
              if k not in BUILTIN_ROLES or v != BUILTIN_ROLES[k]}
    _write_json(_path("roles.json"), {"roles": custom, "people": data.get("people", {}),
                                      "default_role": data.get("default_role", "Full admin"),
                                      "updated_by": me(),
                                      "updated": datetime.datetime.now().isoformat(
                                          timespec="seconds")})


def my_role_name(data: Optional[dict] = None) -> str:
    from .auth import session
    if session.active():
        return session.current().get("role_name", "No access")
    data = data or load_roles()
    name = data["people"].get(me()) or data.get("default_role", "Full admin")
    # a role name that doesn't exist (a typo, or an edited roles file) gets the least,
    # never the most
    return name if name in data["roles"] else LOOKUP_ONLY


def my_role(data: Optional[dict] = None) -> dict:
    from .auth import session
    if session.active():
        return session.current().get("role") or {"pages": [], "can": [], "ask": []}
    data = data or load_roles()
    name = my_role_name(data)
    return data["roles"].get(name) or LOOKUP_ONLY_ROLE


def is_admin() -> bool:
    return bool(my_role().get("admin"))


def page_allowed(page: str, role: Optional[dict] = None) -> bool:
    role = role or my_role()
    pages = role.get("pages", ["*"])
    if page in MERGED and page not in pages:   # roles saved before pages were combined
        if any(p in pages for p in MERGED[page]):
            return True
    return "*" in pages or page in pages or page in ("Home", "Guide", "Settings & Updates", "")


# pages that were combined into one (old roles list the old names)
MERGED = {"Schedules": ("Background tasks", "Scheduled jobs")}


def page_view_only(page: str, role: Optional[dict] = None) -> bool:
    """The role may open this page but not change anything from it."""
    role = role or my_role()
    return page in set(role.get("view_only", []))


def check(args: list[str], role: Optional[dict] = None) -> tuple[bool, set, bool]:
    """(allowed, missing categories, can ask for approval)."""
    role = role or my_role()
    can = set(role.get("can", ALL_CATEGORIES))
    missing = categorize(args) - can
    if not missing:
        return True, set(), False
    return False, missing, missing <= set(role.get("ask", []))


# --------------------------------------------------------------- requests ---
# Fields that change while a request is handled. Everything else is signed when the
# request is made, so nobody can edit what it does (or who asked) in the team folder.
REQUEST_MUTABLE = {"status", "decided_by", "note", "decided", "result", "approvals",
                   "escalated", "updated", "remote_approved_by", "seal", "tracked"}


def _request_body(req: dict, fields=None) -> dict:
    fields = sorted(k for k in req if k not in REQUEST_MUTABLE) if fields is None else fields
    return {"fields": list(fields), "values": {k: req.get(k) for k in fields}}


def sign_request(req: dict) -> dict:
    from . import seal
    body = _request_body(req)
    req["seal"] = {**seal.seal_for("request", body), "fields": body["fields"]}
    return req


def verify_request(req: dict):
    """Who really made this request (Verified), or None if it can't be told."""
    from . import seal
    s = req.get("seal") if isinstance(req, dict) else None
    if not isinstance(s, dict) or not isinstance(s.get("fields"), list):
        return None
    fields = [str(f) for f in s["fields"]]
    if set(k for k in req if k not in REQUEST_MUTABLE) != set(fields):
        return None               # a field was added or removed after signing
    v = seal.check_seal("request", _request_body(req, fields), s)
    by = str(req.get("by", "")).lower()
    if v is not None and v.level != "local" and "@" in by and by != v.who:
        return None               # signed by someone other than the person named
    return v


def new_request(commands: list[list[str]], reason: str, title: str = "", by: str = "",
                extra: Optional[dict] = None, notify: bool = True, dedupe: str = "") -> dict:
    """dedupe: nightly jobs pass a key so they refresh their open request instead of
    filing a new one every night."""
    if not folder():
        raise RuntimeError("Approval requests need a team folder (Settings → Team).")
    from . import secret_args
    from .activity import mask
    from .gam_runner import display_command
    # a waiting request never holds a password: a new one is made when it's approved
    # and shown to whoever runs it
    commands = [secret_args.without_passwords(c) for c in commands]
    final = (extra or {}).get("status", "pending") in FINAL_REQUEST_STATES
    if final:
        commands = [mask(list(c)) for c in commands]
    rid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    if dedupe:
        old = next((r for r in list_requests("pending") if r.get("dedupe") == dedupe and
                    verify_request(r) is not None), None)
        if old:
            # rebuilt from scratch – nothing else from the old file is carried over
            rid = old["id"] if _safe_id(old.get("id", "")) else rid
    req = {"id": rid,
           "time": datetime.datetime.now().isoformat(timespec="seconds"),
           "by": by or me(), "title": title or (display_command(commands[0]) if commands
                                                else "Request"),
           "commands": commands, "reason": reason, "status": "pending",
           "profile": settings.get("profile/current", "") or "Default"}
    req.update(extra or {})
    if dedupe:
        req["dedupe"] = dedupe
        req["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    sign_request(req)
    _write_json(_path("requests", f"{req['id']}.json"), req)
    if not notify or req.get("status") != "pending":
        return req
    try:
        from . import email_approvals
        if email_approvals.enabled():
            email_approvals.send_request(req)
    except Exception:  # noqa: BLE001
        pass
    return req


def _safe_id(rid: str) -> bool:
    import re
    return bool(re.fullmatch(r"[0-9A-Za-z-]{6,40}", rid or ""))


def list_requests(status: str = "") -> list[dict]:
    d = _path("requests")
    if not folder() or not os.path.isdir(d):
        return []
    out = []
    for name in os.listdir(d):
        if name.endswith(".json"):
            r = _read_json(os.path.join(d, name), None)
            if not isinstance(r, dict) or not _safe_id(str(r.get("id", ""))) or \
                    name != f"{r['id']}.json":
                continue                      # not a request GAMbit wrote
            if not isinstance(r.get("commands", []), list):
                continue
            if not status or r.get("status") == status:
                out.append(r)
    out.sort(key=lambda r: r.get("time", ""), reverse=True)
    return out


FINAL_REQUEST_STATES = {"done", "failed", "denied", "cancelled", "rejected", "expired"}


def update_request(req: dict, status: str, note: str = "", result: str = ""):
    req = dict(req)
    req.update(status=status, decided_by=me(), note=note,
               decided=datetime.datetime.now().isoformat(timespec="seconds"))
    if status in FINAL_REQUEST_STATES and isinstance(req.get("commands"), list):
        # finished – the team folder doesn't need to keep any password in it
        from .activity import mask
        req["commands"] = [mask([str(a) for a in c]) if isinstance(c, list) else c
                           for c in req["commands"]]
    if result:
        req["result"] = result
    _write_json(_path("requests", f"{req['id']}.json"), req)
    return req


def save_request(req: dict):
    _write_json(_path("requests", f"{req['id']}.json"), req)


def pending_count() -> int:
    return len(list_requests("pending")) if folder() else 0


# -------------------------------------------------------------- templates ---
def shared_templates_path(name: str) -> str:
    """Path to a shared template file (builder.json / workflows.json), or ''."""
    return _path("templates", name) if folder() else ""


def read_shared(name: str) -> dict:
    p = shared_templates_path(name)
    return _read_json(p, {}) if p else {}


def write_shared(name: str, data: dict):
    p = shared_templates_path(name)
    if not p:
        raise RuntimeError("Choose a team folder first.")
    _write_json(p, data)


def write_shared_signed(name: str, kind: str, data: dict):
    """Write a shared settings file signed by whoever is using GAMbit here."""
    from . import seal
    write_shared(name, seal.sign(kind, {k: v for k, v in data.items() if k != "seal"}))


def read_shared_verified(name: str, kind: str) -> tuple[dict, object]:
    """(data without its seal, Verified or None). With GAMbit sign-in on, only a GAMbit
    admin's signature counts; without it, any computer this one trusts."""
    from . import seal
    d = read_shared(name)
    if not d:
        return {}, None
    v = seal.check_file_data(kind, d)
    return {k: x for k, x in d.items() if k != "seal"}, v


def can_write_shared() -> bool:
    """Only GAMbit admins write the shared settings when sign-in is on (anyone else's
    signature wouldn't be accepted – and would hide the admin-signed values)."""
    from . import seal
    return not seal.signin_required() or seal.signer_level() == "admin"


# ------------------------------------------------- shared workflow settings ---
SHARED_KEYS = ("workflow/leaving_ou", "workflow/rollover", "email/signature",
               "safety/threshold")


def _share_settings() -> bool:
    return bool(folder()) and bool(settings.get("team/share_settings", True))


def setting(key: str, default=""):
    """A workflow setting – from the team folder when sharing is on."""
    if _share_settings() and key in SHARED_KEYS:
        d, v = read_shared_verified("workflows.json", "workflows")
        if v is not None and key in d:      # unsigned / edited values are ignored
            return d[key]
    return settings.get(key, default)


def set_setting(key: str, value):
    settings.set(key, value)
    if _share_settings() and key in SHARED_KEYS and can_write_shared():
        try:
            d, v = read_shared_verified("workflows.json", "workflows")
            d = d if v is not None else {}  # never carry unverified values forward
            d[key] = value
            write_shared_signed("workflows.json", "workflows", d)
        except OSError:
            pass
