"""The emergency admin: one break-glass sign-in per computer for when Google sign-in is
unavailable. Long password (scrypt-hashed) plus an authenticator-app code; the record is
encrypted for this Windows user (DPAPI) and never leaves this computer. Repeated failures
lock it for longer and longer. Every use is logged and alerted."""

from __future__ import annotations

import json
import os
import time

from . import crypto

USER = "emergency-admin"
MAX_FAILS = 5


def _path() -> str:
    from .access import _app_dir
    return os.path.join(_app_dir(), "keys", "emergency-admin.bin")


def configured() -> bool:
    return os.path.isfile(_path())


def _load() -> dict:
    try:
        return json.loads(crypto.read_secret(_path()).decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"The emergency admin on this computer can't be read ({exc}). "
                         "Remove it and set it up again.") from None


def _store(rec: dict):
    crypto.write_secret(_path(), json.dumps(rec).encode("utf-8"))


def computer() -> str:
    import platform
    return (platform.node() or "this-pc").lower()


def fingerprint(rec: dict | None = None) -> str:
    """Hash of the password hash and authenticator secret. A GAMbit admin records it in the
    signed access list, so a hand-made emergency record on this PC isn't accepted."""
    import hashlib
    rec = rec if rec is not None else _load()
    return hashlib.sha256(crypto.canonical({"pw": rec.get("pw"), "totp": rec.get("totp")}))\
        .hexdigest()


def registered_fingerprint(doc: dict | None) -> str:
    from .access import pinned
    if doc:
        return ((doc.get("emergency") or {}).get(computer()) or "")
    return (pinned().get("emergency") or {}).get(computer(), "")


def setup(password: str, totp_secret: str, code: str, by: str) -> None:
    probs = crypto.password_problems(password)
    if probs:
        raise ValueError("The password needs " + ", ".join(probs) + ".")
    step = crypto.totp_ok(totp_secret, code)
    if step < 0:
        raise ValueError("That authenticator code isn't right – check the phone's clock and "
                         "try the newest code.")
    _store({"pw": crypto.hash_password(password), "totp": totp_secret, "last_step": step,
            "fails": 0, "locked_until": 0, "set_by": by,
            "set": time.strftime("%Y-%m-%d %H:%M")})


def remove():
    try:
        os.remove(_path())
    except OSError:
        pass


def locked_for() -> int:
    if not configured():
        return 0
    try:
        return max(0, int(_load().get("locked_until", 0) - time.time()))
    except ValueError:
        return 0


def check(username: str, password: str, code: str, expected: str = "") -> bool:
    if not configured():
        raise ValueError("No emergency admin is set up on this computer.")
    rec = _load()
    if not expected or fingerprint(rec) != expected:
        raise ValueError("This computer's emergency admin isn't registered in the GAMbit "
                         "access list (or was changed by hand). A GAMbit admin must set it up "
                         "again from Users & access.")
    if rec.get("locked_until", 0) > time.time():
        mins = int((rec["locked_until"] - time.time()) // 60) + 1
        raise ValueError(f"Too many wrong tries – locked for {mins} more minute(s).")
    ok_pw = crypto.check_password(password, rec["pw"])        # always run (timing)
    step = crypto.totp_ok(rec["totp"], code, last_used=int(rec.get("last_step", -1)))
    if username.strip().lower() == USER and ok_pw and step >= 0:
        rec.update(fails=0, locked_until=0, last_step=step)
        _store(rec)
        return True
    rec["fails"] = int(rec.get("fails", 0)) + 1
    if rec["fails"] >= MAX_FAILS:
        rec["locked_until"] = time.time() + 15 * 60 * 2 ** min(rec["fails"] - MAX_FAILS, 5)
    _store(rec)
    return False
