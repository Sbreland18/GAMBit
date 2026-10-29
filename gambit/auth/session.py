"""Who is signed in to GAMbit right now, plus the sign-in log and org-unit scope checks."""

from __future__ import annotations

import datetime
import json
import os
import platform
import time

_current: dict = {}


def current() -> dict:
    return _current


def active() -> bool:
    return bool(_current.get("email"))


def email() -> str:
    return _current.get("email", "")


def start(person: dict, method: str, doc: dict | None):
    _current.clear()
    _current.update(person)
    sess = (doc or {}).get("session", {})
    _current.update(method=method, started=time.time(), last=time.time(),
                    idle=int(sess.get("idle_minutes", 30) or 30) * 60,
                    max=int(sess.get("max_hours", 10) or 10) * 3600)
    log("signed in", method=method)


def end(reason: str = "signed out"):
    if _current:
        log(reason)
    _current.clear()


def touch():
    if _current:
        _current["last"] = time.time()


def expired(now: float | None = None) -> str:
    """'' while the session is fine, else why it ended."""
    if not _current:
        return ""
    now = now or time.time()
    if now - _current.get("last", now) > _current.get("idle", 1800):
        return "locked after being idle"
    if now - _current.get("started", now) > _current.get("max", 36000):
        return "the sign-in reached its time limit"
    return ""


# ===================================================================== log ===
def _log_paths() -> list[str]:
    from .access import _app_dir, folder
    month = datetime.date.today().strftime("%Y-%m")
    out = [os.path.join(_app_dir(), "signins", f"signins-{month}.jsonl")]
    try:
        out.append(os.path.join(folder(), "signins", f"{platform.node()}-{month}.jsonl"))
    except Exception:  # noqa: BLE001
        pass
    return out


def log(event: str, who: str = "", **extra):
    entry = {"time": datetime.datetime.now().isoformat(timespec="seconds"),
             "who": who or _current.get("email", ""), "event": event,
             "computer": platform.node(), **extra}
    for p in _log_paths():
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError:
            pass


def read_log(limit: int = 500) -> list[dict]:
    import glob
    from .access import folder
    files = glob.glob(os.path.join(folder(), "signins", "*.jsonl"))
    rows = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                for ln in fh:
                    try:
                        rows.append(json.loads(ln))
                    except ValueError:
                        continue
        except OSError:
            continue
    rows.sort(key=lambda r: r.get("time", ""), reverse=True)
    return rows[:limit]


# =================================================================== scope ===
def scope() -> list[str]:
    return [o for o in _current.get("ous", []) if o]


def in_scope(ou: str, roots: list[str] | None = None) -> bool:
    roots = scope() if roots is None else roots
    if not roots:
        return True
    o = (ou or "/").rstrip("/").lower() + "/"
    return any(r.strip() == "/" or o.startswith(r.rstrip("/").lower() + "/") for r in roots)


_USER_ATTR_DEST = ("ou", "org", "orgunitpath")


def targets(args: list[str]) -> list[tuple[str, str]]:
    """What a GAM command acts on: [("user", email) | ("ou", path) | ("cros", serial/id)
    | ("dest", ou) | ("everyone", "")]."""
    from ..activity import strip_config
    a = strip_config(list(args))
    if a[:1] == ["select"]:
        a = a[2:]
    low = [x.lower() for x in a]
    out: list[tuple[str, str]] = []
    if not low:
        return out
    k = low[0]
    if k == "all" and len(low) > 1 and low[1] in ("users", "users_ns", "cros", "devices"):
        out.append(("everyone", ""))
    elif k in ("ou", "ou_ns", "ou_and_children", "ou_and_children_ns", "cros_ou",
               "cros_ou_and_children") and len(a) > 1:
        out.append(("ou", a[1]))
    elif k in ("ous", "ous_and_children", "cros_ous", "cros_ous_and_children") and len(a) > 1:
        out += [("ou", p) for p in a[1].split(",") if p]
    elif k in ("user", "users") and len(a) > 1:
        out += [("user", e.lower()) for e in a[1].split(",") if e]
    elif k == "cros_sn" and len(a) > 1:
        out += [("cros", s) for s in a[1].split(",") if s]
    elif k == "cros" and len(a) > 1:
        out += [("crosid", s) for s in a[1].split(",") if s]
    if len(low) > 2 and low[0] in ("update", "delete", "undelete", "create", "add") and \
            low[1] in ("user", "users"):
        out += [("user", e.lower()) for e in a[2].split(",") if e]
    if len(low) > 2 and low[0] in ("update", "delete") and low[1] == "cros":
        out += [("crosid", s) for s in a[2].split(",") if s]
    if len(low) > 2 and low[0] in ("create", "update", "delete") and low[1] in ("ou", "org",
                                                                                  "ous"):
        out += [("ou", p) for p in a[2].split(",") if p]
    if len(low) > 3 and low[0] in ("create", "update", "delete") and low[1] in ("alias",
                                                                                  "aliases"):
        out += [("user", e.lower()) for e in a[3:] if "@" in e]
    if len(low) > 3 and low[0] == "update" and low[1] in ("group", "groups") and \
            low[3] in ("add", "remove", "delete", "update", "sync"):
        for x in a[4:]:
            if "@" in x:
                out += [("user", e.lower()) for e in x.split(",") if "@" in e]
    for i, x in enumerate(low[:-1]):
        if x in _USER_ATTR_DEST and i > 1 and low[0] != "print":
            out.append(("dest", a[i + 1]))
    return out


UNCHECKABLE = {"batch", "tbatch", "csv", "select", "loop", "redirect", "multiprocess"}


def scope_problem(args: list[str], users_by_email: dict, cros_ou=None,
                  change: bool = True, roots: list[str] | None = None) -> str:
    """'' if every target is inside the signed-in person's org units (or `roots`). For
    someone with a scope, a change GAMbit can't pin to a person, org unit or device is
    refused."""
    from ..activity import strip_config
    roots = scope() if roots is None else [r for r in roots if r]
    if not roots:
        return ""
    low = [x.lower() for x in strip_config(list(args))]
    if low and low[0] in UNCHECKABLE:
        return f"“{low[0]}” commands (GAMbit can't check them against your org units)"
    found = targets(args)
    # any known account mentioned anywhere in the command must be in scope too
    for x in args:
        for e in str(x).split(","):
            e = e.strip().lower()
            if "@" in e and e in users_by_email and ("user", e) not in found:
                found.append(("user", e))
    if change and not found:
        return "a change GAMbit can't match to people, org units or devices in your scope"
    if change and low[:2] == ["create", "user"] and not any(k == "dest" for k, _v in found):
        return "new accounts without an org unit (add “ou” inside your org units)"
    for kind, v in found:
        if kind == "everyone":
            return "commands for the whole domain"
        if kind in ("ou", "dest") and not in_scope(v, roots):
            return f"org unit {v}"
        if kind == "user":
            u = users_by_email.get(v)
            if u is None:
                if args and args[0].lower() == "create":
                    continue      # a new account – its destination OU is checked above
                return f"{v} (not in your org units)"
            if not in_scope(u.get("ou", ""), roots):
                return f"{v} ({u.get('ou', '')})"
        if kind in ("cros", "crosid"):
            ou = cros_ou(kind, v) if cros_ou else None
            if ou is None or not in_scope(ou, roots):
                return f"Chromebook {v}" + (f" ({ou})" if ou else "")
    return ""


# ============================================================ access list ===
_doc: dict = {}


def doc() -> dict:
    return _doc


def set_doc(d: dict | None):
    import copy
    d = copy.deepcopy(d) if d else {}      # d may be _doc itself
    _doc.clear()
    _doc.update(d)
