"""Signed records for everything GAMbit keeps in shared places.

The team folder is a plain network share that every tech can write to, so nothing read from
it may be trusted just because it's there. Each record that can make GAMbit *do* something
(Run later items, approval requests and approvals, offboarding plans, temporary accounts,
policy plans, automatic group rules, the approval rules, shared workflow settings,
deployment files) carries a seal: an Ed25519 signature over its stable fields.

Who can sign, and how far a signature is trusted:

  admin   – a GAMbit admin's key listed in the signed access list (trusted everywhere)
  member  – any person's key an admin approved into the access list (trusted everywhere,
            with that person's role)
  local   – this computer's own key for this Windows user (trusted only here, or on PCs
            that chose to trust it in Settings → Team → Trusted computers)

Background tasks act only on records with a valid seal from someone allowed to run them.
A record whose stable fields were edited after it was signed fails the check, so editing
the JSON by hand (or by malware) is caught. Status fields that change while a record is
worked on (status, results, timestamps) are left out of the signature.
"""

from __future__ import annotations

import datetime
import getpass
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Iterable, Optional

from .auth import crypto
from .settings import settings

VERSION = 1
TRUSTED_KEY = "seal/trusted"          # {kid: {"public": b64, "label": str}} (this PC only)


@dataclass
class Verified:
    level: str          # "admin" | "member" | "local"
    who: str            # email (admin/member) or the signer's claimed name (local)
    kid: str
    at: str


# ============================================================ local key ===
def _app_dir() -> str:
    from .auth.access import _app_dir as base
    return base()


def _win_user() -> str:
    try:
        return getpass.getuser().lower()
    except Exception:  # noqa: BLE001
        return "user"


def _local_key_path() -> str:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in _win_user())
    return os.path.join(_app_dir(), "keys", f"local-{safe}.key")


_LOCAL: dict = {}


def local_key() -> tuple[bytes, bytes]:
    """This computer's own signing key for this Windows user (DPAPI-protected)."""
    p = _local_key_path()
    if _LOCAL.get("path") == p:
        return _LOCAL["priv"], _LOCAL["pub"]
    if os.path.isfile(p):
        raw = crypto.read_secret(p)
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        pub = Ed25519PrivateKey.from_private_bytes(raw).public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    else:
        raw, pub = crypto.new_keypair()
        crypto.write_secret(p, raw)
    _LOCAL.update(path=p, priv=raw, pub=pub)
    return raw, pub


def local_kid() -> str:
    return crypto.key_id(local_key()[1])


def local_fingerprint() -> str:
    return crypto.fingerprint(local_key()[1])


def publish_local_key():
    """Put this computer's public key in <team>/keys so another PC can choose to trust it
    (after comparing the code shown on both screens). Publishing grants nothing."""
    from . import team
    if not team.folder():
        return ""
    _priv, pub = local_key()
    kid = crypto.key_id(pub)
    d = os.path.join(team.folder(), "keys")
    os.makedirs(d, exist_ok=True)
    import platform
    rec = {"public": crypto.b64(pub), "computer": platform.node(), "user": _win_user(),
           "published": datetime.datetime.now().isoformat(timespec="seconds")}
    with open(os.path.join(d, f"{kid}.json"), "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    return kid


def published_keys() -> list[dict]:
    """Keys other computers published (fingerprints recomputed – never trust the file)."""
    from . import team
    d = os.path.join(team.folder(), "keys") if team.folder() else ""
    out = []
    for f in sorted(os.listdir(d)) if d and os.path.isdir(d) else []:
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                r = json.load(fh)
            pub = crypto.unb64(r["public"])
            if len(pub) != 32:
                continue
            out.append({"kid": crypto.key_id(pub), "public": r["public"],
                        "fingerprint": crypto.fingerprint(pub),
                        "label": f"{r.get('user', '?')} on {r.get('computer', '?')}",
                        "trusted": crypto.key_id(pub) in trusted_locals()})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def trusted_locals() -> dict:
    try:
        d = json.loads(settings.get(TRUSTED_KEY, "") or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def trust_local(public_b64: str, label: str, fingerprint_typed: str) -> str:
    """Trust another computer's key – only when the code typed matches the key itself."""
    pub = crypto.unb64(public_b64)
    norm = lambda t: "".join(c for c in (t or "").upper() if c.isalnum())  # noqa: E731
    if len(pub) != 32 or norm(fingerprint_typed) != norm(crypto.fingerprint(pub)):
        raise ValueError("The code doesn't match that key – not trusted.")
    d = trusted_locals()
    kid = crypto.key_id(pub)
    d[kid] = {"public": public_b64, "label": label,
              "added": datetime.date.today().isoformat()}
    settings.set(TRUSTED_KEY, json.dumps(d))
    return kid


def untrust_local(kid: str):
    d = trusted_locals()
    d.pop(kid, None)
    settings.set(TRUSTED_KEY, json.dumps(d))


# ======================================================== access list ===
def signin_required() -> bool:
    try:
        from .auth import access
        return access.required()
    except Exception:  # noqa: BLE001
        return False


_DOC_CACHE: dict = {}


def _doc() -> dict:
    """The verified access list ({} when sign-in isn't used or it can't be verified)."""
    import time
    from .auth import access, session
    d = session.doc()
    if d:
        return d
    if not signin_required():
        return {}
    hit = _DOC_CACHE.get("doc")
    if hit is not None and time.time() - _DOC_CACHE.get("at", 0) < 60:
        return hit
    try:
        d = access.load()
    except Exception:  # noqa: BLE001 – unverifiable = nothing is trusted from it
        d = {}
    _DOC_CACHE.update(doc=d, at=time.time())
    return d


def _trusted() -> dict[str, tuple[str, str, bytes]]:
    """kid → (level, who, public key)."""
    out: dict = {}
    doc = _doc()
    if doc:
        from .auth import access
        for kid, k in (doc.get("admin_keys") or {}).items():
            if access.signer_is_admin(doc, kid):
                out[kid] = ("admin", k.get("email", "").lower(), crypto.unb64(k["public"]))
        for kid, k in (doc.get("member_keys") or {}).items():
            if kid not in out and access.person(doc, k.get("email", "")):
                out[kid] = ("member", k.get("email", "").lower(), crypto.unb64(k["public"]))
    try:
        _priv, pub = local_key()
        out.setdefault(crypto.key_id(pub), ("local", "", pub))
    except Exception:  # noqa: BLE001
        pass
    for kid, k in trusted_locals().items():
        try:
            out.setdefault(kid, ("local", "", crypto.unb64(k["public"])))
        except (ValueError, KeyError, TypeError):
            continue
    return out


# ================================================================ signer ===
def _signer() -> tuple[str, bytes, str]:
    """(level, private key, identity) of whoever is signing on this computer now."""
    from .auth import session
    if session.active():
        email = session.email().lower()
        doc = session.doc() or {}
        try:
            from .auth import access
            mine = access.my_key(email)
        except Exception:  # noqa: BLE001
            mine = None
        if mine:
            kid = crypto.key_id(mine[1])
            if kid in (doc.get("admin_keys") or {}):
                from .auth import access
                if access.signer_is_admin(doc, kid):
                    return "admin", mine[0], email
            if kid in (doc.get("member_keys") or {}):
                return "member", mine[0], email
        priv, _pub = local_key()
        return "local", priv, email
    priv, _pub = local_key()
    from . import team
    return "local", priv, team.me()


def signer_level() -> str:
    try:
        return _signer()[0]
    except Exception:  # noqa: BLE001
        return ""


def _body(kind: str, rec: dict, fields: Optional[Iterable[str]], skip: Iterable[str]):
    skip = set(skip) | {"seal"}
    if fields is not None:
        b = {f: rec.get(f) for f in fields}
    else:
        b = {k: v for k, v in rec.items() if k not in skip}
    return b


def _bytes(kind: str, body) -> bytes:
    return crypto.canonical({"v": VERSION, "kind": kind, "body": body})


def seal_for(kind: str, body) -> dict:
    """A seal over `body` (any JSON value) by whoever is using GAMbit here."""
    level, priv, who = _signer()
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    pub = Ed25519PrivateKey.from_private_bytes(priv).public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {"v": VERSION, "kid": crypto.key_id(pub), "by": who, "level": level,
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
            "sig": crypto.b64(crypto.sign(priv, _bytes(kind, body)))}


def check_seal(kind: str, body, s) -> Optional[Verified]:
    """The verified signer of `body` under seal `s`, or None."""
    if not isinstance(s, dict) or s.get("v") != VERSION:
        return None
    t = _trusted().get(str(s.get("kid", "")))
    if not t:
        return None
    level, who, pub = t
    try:
        ok = crypto.verify(pub, crypto.unb64(str(s.get("sig", ""))), _bytes(kind, body))
    except (ValueError, TypeError):
        ok = False
    if not ok:
        return None
    if level == "local":
        who = str(s.get("by", "")).lower()       # asserted by a computer we trust
    return Verified(level, who, str(s.get("kid")), str(s.get("at", "")))


def sign(kind: str, rec: dict, fields: Optional[Iterable[str]] = None,
         skip: Iterable[str] = ()) -> dict:
    """Return rec with a fresh seal over its stable fields."""
    rec = {k: v for k, v in rec.items() if k != "seal"}
    rec["seal"] = seal_for(kind, _body(kind, rec, fields, skip))
    return rec


def check(kind: str, rec, fields: Optional[Iterable[str]] = None,
          skip: Iterable[str] = ()) -> Optional[Verified]:
    """The verified signer of rec, or None (no seal, unknown key, or edited since)."""
    if not isinstance(rec, dict):
        return None
    return check_seal(kind, _body(kind, rec, fields, skip), rec.get("seal"))


def describe(v: Optional[Verified]) -> str:
    if v is None:
        return "not signed (or changed since it was signed)"
    return {"admin": f"signed by GAMbit admin {v.who}",
            "member": f"signed by {v.who}",
            "local": f"signed on a trusted computer ({v.who or 'unknown'})"}[v.level]


# ========================================================= authority ===
def may_run(v: Optional[Verified], commands: list[list[str]], users=None) -> str:
    """'' if the signer may have these commands run without anyone watching, else why not.

    With GAMbit sign-in on, the signer must be a person in the access list whose role
    allows every command outright (not just 'ask'), inside their org units. Without
    sign-in there are no roles, so any valid seal is enough."""
    if v is None:
        return "it isn't signed by anyone GAMbit trusts (or it was changed after signing)"
    if not signin_required():
        return ""
    doc = _doc()
    if not doc:
        return "the access list can't be verified"
    from .auth import access
    p = access.person(doc, v.who)
    if p is None:
        return f"{v.who or 'the signer'} isn't allowed to use GAMbit"
    if v.level == "local" and v.kid != local_kid():
        return "it was signed on another computer by someone without a trusted key"
    from . import team
    from .auth import session
    for c in commands:
        ok, missing, _ask = team.check([str(a) for a in c], p["role"])
        if not ok:
            return f"{v.who}'s role doesn't allow it ({', '.join(sorted(missing))})"
        roots = [o for o in p.get("ous") or [] if o]
        if roots:
            by_email = {u["email"].lower(): u for u in (users or [])}
            why = session.scope_problem([str(a) for a in c], by_email, None, roots=roots)
            if why:
                return f"outside {v.who}'s org units: {why}"
    return ""


def commands_hash(commands) -> str:
    return hashlib.sha256(crypto.canonical([[str(a) for a in c] for c in commands or []]))\
        .hexdigest()[:16]


# ====================================================== shared files ===
def sign_file_data(kind: str, data: dict) -> dict:
    return sign(kind, data)


def check_file_data(kind: str, data: dict, need: str = "admin") -> Optional[Verified]:
    """A shared settings-like file: with sign-in on it must be signed by a GAMbit admin
    (need='admin'); without sign-in any trusted seal will do."""
    v = check(kind, data)
    if v is None:
        return None
    if signin_required() and need == "admin" and v.level != "admin":
        return None
    return v
