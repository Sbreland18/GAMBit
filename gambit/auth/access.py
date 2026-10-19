"""The signed access list: who may sign in to GAMbit, with which role and org-unit scope.

File: <team folder>/access/access.json  (or GAMbit's app-data folder when there is no team
folder). Layout:

    {"doc": {...}, "key_id": "<signing key>", "sig": "<Ed25519 signature of doc>"}

doc = {format, serial, updated, updated_by, domain, google{client_id, client_secret},
       session{idle_minutes, max_hours}, admin_keys{key_id: {email, public, added}},
       roles{custom roles}, people{email: {role, ous[], enabled, name, added}},
       default_role}

Each PC pins (in its settings) the admin keys and serial of the newest list it accepted.
A list is accepted only when it's signed by a pinned key and its serial isn't lower than
the pinned one – so hand edits, forged files and old copies are all refused.
"""

from __future__ import annotations

import datetime
import json
import os
import uuid

from ..settings import settings
from . import crypto

FORMAT = 1
NO_ACCESS = "No access"


class AccessError(Exception):
    pass


# ================================================================== where ===
def folder() -> str:
    from .. import team
    base = os.path.join(team.folder(), "access") if team.folder() else os.path.join(
        _app_dir(), "access")
    return base


def _app_dir() -> str:
    from PySide6.QtCore import QStandardPaths
    return QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")


def path() -> str:
    return os.path.join(folder(), "access.json")


def exists() -> bool:
    return os.path.isfile(path())


def required() -> bool:
    """Sign-in is required once this PC has accepted an access list, or one exists."""
    return bool(pinned().get("keys")) or exists()


# ============================================================== pinning ===
def pinned() -> dict:
    try:
        return json.loads(settings.get("access/pinned", "") or "{}")
    except ValueError:
        return {}


def _pin(doc: dict):
    settings.set("access/pinned", json.dumps({
        "keys": {k: v["public"] for k, v in doc.get("admin_keys", {}).items()},
        "serial": int(doc.get("serial", 0)), "domain": doc.get("domain", ""),
        "emergency": dict(doc.get("emergency") or {}), "path": path()}))


def unpin():
    settings.set("access/pinned", "")


# ============================================================ read/verify ===
def read_raw(p: str | None = None) -> dict:
    try:
        with open(p or path(), encoding="utf-8") as fh:
            env = json.load(fh)
    except (OSError, ValueError) as exc:
        raise AccessError(f"Couldn't read the access list ({exc}). If the team folder is "
                          "still syncing, wait a minute and try again.") from None
    if not isinstance(env, dict):
        raise AccessError("The access list is damaged.")
    return env


def check_signature(env: dict, keys: dict[str, str]) -> dict:
    doc, kid, sig = env.get("doc"), env.get("key_id", ""), env.get("sig", "")
    if not isinstance(doc, dict) or kid not in keys:
        raise AccessError("The access list isn't signed by a GAMbit admin this computer "
                          "trusts.")
    try:
        ok = crypto.verify(crypto.unb64(keys[kid]), crypto.unb64(sig), crypto.canonical(doc))
        fmt = int(doc.get("format", 0))
        int(doc.get("serial", 0))
    except (ValueError, TypeError):
        ok, fmt = False, FORMAT
    if not ok:
        raise AccessError("The access list has been changed outside GAMbit (its signature "
                          "doesn't match). Ask your GAMbit admin to save it again.")
    if fmt != FORMAT:
        raise AccessError("This access list was made by a newer GAMbit. Update GAMbit.")
    if not signer_is_admin(doc, kid):
        raise AccessError("The access list was signed by someone who isn't a GAMbit admin "
                          "any more. Ask a current GAMbit admin to save it again.")
    return doc


def signer_is_admin(doc: dict, kid: str) -> bool:
    k = (doc.get("admin_keys") or {}).get(kid) or {}
    p = person(doc, k.get("email", ""))
    return bool(p and p["role"].get("admin"))


def local_signer(doc: dict, preferred: str = "") -> str:
    """An admin whose trusted key is stored on this computer (preferred person first)."""
    keys = doc.get("admin_keys") or {}
    for email in [preferred] + [k["email"] for k in keys.values()]:
        if not email:
            continue
        try:
            mine = my_key(email)
        except Exception:  # noqa: BLE001
            mine = None
        if mine and crypto.key_id(mine[1]) in keys and \
                signer_is_admin(doc, crypto.key_id(mine[1])):
            return email
    return ""


def keyed_admins(doc: dict) -> list[str]:
    """Admins who can still sign the list (enabled, admin role, trusted key)."""
    return sorted({k["email"] for kid, k in (doc.get("admin_keys") or {}).items()
                   if signer_is_admin(doc, kid)})


def prune_keys(doc: dict) -> dict:
    """Stop trusting keys whose owner is no longer an enabled admin."""
    doc = json.loads(json.dumps(doc))
    doc["admin_keys"] = {kid: k for kid, k in (doc.get("admin_keys") or {}).items()
                         if signer_is_admin(doc, kid)}
    return doc


def first_look() -> dict:
    """For trust-on-first-use: the unverified signer details of the current file."""
    env = read_raw()
    doc = env.get("doc") or {}
    kid = env.get("key_id", "")
    k = (doc.get("admin_keys") or {}).get(kid, {}) if isinstance(doc, dict) else {}
    pub = k.get("public", "")
    try:
        ok = bool(pub) and crypto.verify(crypto.unb64(pub), crypto.unb64(env.get("sig", "")),
                                         crypto.canonical(doc))
    except (ValueError, TypeError):
        ok = False
    if not ok or not signer_is_admin(doc, kid):
        raise AccessError("The access list in the team folder isn't validly signed.")
    return {"email": k.get("email", "?"), "fingerprint": crypto.fingerprint(crypto.unb64(pub)),
            "domain": doc.get("domain", ""), "serial": doc.get("serial", 0), "doc": doc}


def trust_first(doc: dict):
    _pin(doc)


def load() -> dict:
    """The verified access list. Raises AccessError when it can't be trusted."""
    pin = pinned()
    if not exists():
        if pin.get("keys"):
            raise AccessError("This computer requires GAMbit sign-in, but the access list "
                              f"is missing from {folder()}. Check the team folder.")
        raise AccessError("No access list yet.")
    if not pin.get("keys"):
        raise AccessError("NOT_PINNED")
    env = read_raw()
    doc = check_signature(env, pin["keys"])
    if int(doc.get("serial", 0)) < int(pin.get("serial", 0)):
        raise AccessError("The access list is older than one this computer has already "
                          "seen – someone may have put back an old copy. Ask your GAMbit "
                          "admin to save it again.")
    if pin.get("domain") and doc.get("domain") != pin.get("domain"):
        raise AccessError("The access list is for a different domain.")
    _pin(doc)          # follow key changes and the new serial
    return doc


# ================================================================ signing ===
def _key_dir() -> str:
    return os.path.join(_app_dir(), "keys")


def my_key_path(email: str) -> str:
    return os.path.join(_key_dir(), f"{email.lower().replace('@', '_at_')}.key")


def my_key(email: str) -> tuple[bytes, bytes] | None:
    p = my_key_path(email)
    if not os.path.isfile(p):
        return None
    raw = crypto.read_secret(p)
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    pub = Ed25519PrivateKey.from_private_bytes(raw).public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return raw, pub


def ensure_my_key(email: str) -> bytes:
    k = my_key(email)
    if k:
        return k[1]
    priv, pub = crypto.new_keypair()
    crypto.write_secret(my_key_path(email), priv)
    return pub


def save(doc: dict, email: str) -> dict:
    """Sign and write the list with this admin's key (which must be listed in it)."""
    k = my_key(email)
    if not k:
        raise AccessError("This computer has no GAMbit admin key for you.")
    priv, pub = k
    kid = crypto.key_id(pub)
    if kid not in doc.get("admin_keys", {}):
        raise AccessError("Your admin key isn't in the access list yet – another GAMbit "
                          "admin must approve it first (Users & access → Admin keys).")
    doc = prune_keys(doc)
    if kid not in doc.get("admin_keys", {}):
        raise AccessError("This change would remove your own admin rights while you sign "
                          "it. Ask another GAMbit admin to make it.")
    if not keyed_admins(doc):
        raise AccessError("At least one GAMbit admin with a trusted key must remain.")
    cur = pinned()
    doc = dict(doc)
    doc["format"] = FORMAT
    doc["serial"] = max(int(doc.get("serial", 0)), int(cur.get("serial", 0))) + 1
    doc["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    doc["updated_by"] = email
    env = {"doc": doc, "key_id": kid, "sig": crypto.b64(crypto.sign(priv,
                                                                     crypto.canonical(doc)))}
    os.makedirs(folder(), exist_ok=True)
    tmp = path() + f".{uuid.uuid4().hex[:6]}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(env, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path())
    _pin(doc)
    return doc


def new_list(admin_email: str, domain: str, client_id: str, client_secret: str) -> dict:
    """The first access list: the person setting it up is the only admin."""
    pub = ensure_my_key(admin_email)
    kid = crypto.key_id(pub)
    now = datetime.date.today().isoformat()
    doc = {"format": FORMAT, "serial": 0, "domain": domain.lower().strip(),
           "google": {"client_id": client_id.strip(), "client_secret": client_secret.strip()},
           "session": {"idle_minutes": 30, "max_hours": 10},
           "admin_keys": {kid: {"email": admin_email.lower(), "public": crypto.b64(pub),
                                "added": now}},
           "roles": {}, "people": {admin_email.lower(): {"role": "Full admin", "ous": [],
                                                          "enabled": True, "added": now}},
           "default_role": NO_ACCESS}
    return save(doc, admin_email)


# ============================================================= key requests ===
def request_admin_key(email: str) -> str:
    """A new admin asks for their key to be trusted; another admin approves it."""
    pub = ensure_my_key(email)
    d = os.path.join(folder(), "key_requests")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{crypto.key_id(pub)}.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"email": email.lower(), "public": crypto.b64(pub),
                   "fingerprint": crypto.fingerprint(pub),
                   "asked": datetime.datetime.now().isoformat(timespec="seconds")}, fh)
    return crypto.fingerprint(pub)


def key_requests() -> list[dict]:
    d = os.path.join(folder(), "key_requests")
    out = []
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                r = json.load(fh)
            pub = crypto.unb64(r["public"])
            r["fingerprint"] = crypto.fingerprint(pub)   # recompute – never trust the file
            r["key_id"] = crypto.key_id(pub)
            r["file"] = os.path.join(d, f)
            out.append(r)
        except (OSError, ValueError, KeyError):
            continue
    return out


def approve_key(doc: dict, req: dict) -> dict:
    doc = json.loads(json.dumps(doc))
    person = doc.get("people", {}).get(req["email"].lower(), {})
    roles = all_roles(doc)
    if not roles.get(person.get("role", ""), {}).get("admin"):
        raise AccessError(f"{req['email']} must have an admin role before their key can be "
                          "trusted.")
    doc.setdefault("admin_keys", {})[req["key_id"]] = {
        "email": req["email"].lower(), "public": req["public"],
        "added": datetime.date.today().isoformat()}
    return doc


def drop_request(req: dict):
    try:
        os.remove(req["file"])
    except OSError:
        pass


# ================================================================== people ===
def all_roles(doc: dict) -> dict:
    from .. import team
    roles = dict(team.BUILTIN_ROLES)
    roles[NO_ACCESS] = {"description": "Can't sign in.", "pages": [], "can": [], "ask": [],
                        "admin": False}
    roles.update(doc.get("roles", {}))
    return roles


def person(doc: dict, email: str) -> dict | None:
    """The person's entry merged with their role, or None if they may not sign in."""
    e = (email or "").lower()
    p = doc.get("people", {}).get(e)
    role_name = (p or {}).get("role") or doc.get("default_role", NO_ACCESS)
    if p is not None and p.get("enabled") is False:
        return None
    roles = all_roles(doc)
    role = roles.get(role_name)
    if not role or role_name == NO_ACCESS:
        return None
    ous = (p or {}).get("ous") or role.get("ous") or []
    return {"email": e, "role_name": role_name, "role": role, "ous": ous,
            "name": (p or {}).get("name", "")}


def admin_count(doc: dict) -> int:
    roles = all_roles(doc)
    return sum(1 for p in doc.get("people", {}).values()
               if p.get("enabled", True) and roles.get(p.get("role"), {}).get("admin"))
