"""Small crypto helpers: canonical JSON, Ed25519 signing, Windows DPAPI, scrypt, TOTP."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import sys
import time


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(text: str) -> bytes:
    return base64.b64decode((text or "").encode("ascii"))


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)\
        .encode("utf-8")


# ================================================================== Ed25519 ===
def new_keypair() -> tuple[bytes, bytes]:
    """→ (private raw 32 bytes, public raw 32 bytes)"""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                           serialization.NoEncryption())
    pub = k.public_key().public_bytes(serialization.Encoding.Raw,
                                      serialization.PublicFormat.Raw)
    return priv, pub


def sign(priv: bytes, data: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(priv).sign(data)


def verify(pub: bytes, sig: bytes, data: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(pub).verify(sig, data)
        return True
    except (InvalidSignature, ValueError):
        return False


def key_id(pub: bytes) -> str:
    return hashlib.sha256(pub).hexdigest()[:16]


def fingerprint(pub: bytes) -> str:
    """Human-checkable code, e.g. 4F2A-91C0-77DE-0B13."""
    h = hashlib.sha256(pub).hexdigest()[:16].upper()
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


# ============================================================ secret storage ===
def protect(data: bytes) -> bytes:
    """Encrypt for the current Windows user (DPAPI). Elsewhere (tests, dev) the data is
    stored as-is and the caller relies on file permissions."""
    if not sys.platform.startswith("win"):
        return b"PLAIN" + data
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(blob_in), "GAMbit", None, None,
                                                  None, 0x01, ctypes.byref(blob_out)):
        raise OSError("Windows couldn't protect the secret")
    try:
        return b"DPAPI" + ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def unprotect(data: bytes) -> bytes:
    if data.startswith(b"PLAIN"):
        if sys.platform.startswith("win"):     # on Windows secrets must be DPAPI-protected
            raise ValueError("Unprotected secret refused")
        return data[5:]
    if not data.startswith(b"DPAPI") or not sys.platform.startswith("win"):
        raise ValueError("Unknown secret format")
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    raw = data[5:]
    buf = ctypes.create_string_buffer(raw, len(raw))
    blob_in = BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None,
                                                    None, 0x01, ctypes.byref(blob_out)):
        raise OSError("This secret belongs to another Windows user or computer")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def write_secret(path: str, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(protect(data))
    os.replace(tmp, path)


def read_secret(path: str) -> bytes:
    with open(path, "rb") as fh:
        return unprotect(fh.read())


# ==================================================================== scrypt ===
SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}


def hash_password(password: str, salt: bytes | None = None, params: dict | None = None) -> dict:
    salt = salt or secrets.token_bytes(16)
    p = params or SCRYPT
    h = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=p["n"], r=p["r"], p=p["p"],
                       maxmem=128 * 1024 * 1024, dklen=32)
    return {"salt": b64(salt), "hash": b64(h), **p}


def check_password(password: str, rec: dict) -> bool:
    try:
        h = hash_password(password, unb64(rec["salt"]),
                          {"n": int(rec["n"]), "r": int(rec["r"]), "p": int(rec["p"])})
    except (KeyError, ValueError):
        return False
    return hmac.compare_digest(h["hash"], rec.get("hash", ""))


def password_problems(pw: str) -> list[str]:
    out = []
    if len(pw) < 14:
        out.append("at least 14 characters")
    kinds = sum(bool(any(f(c) for c in pw)) for f in (str.islower, str.isupper, str.isdigit,
                                                      lambda c: not c.isalnum()))
    if kinds < 3:
        out.append("three of: lowercase, uppercase, digits, symbols")
    if pw.lower() in ("gambitgambit12", "password12345678") or len(set(pw)) < 6:
        out.append("not easy to guess")
    return out


# ====================================================================== TOTP ===
B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp(secret: str, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    counter = int((at if at is not None else time.time()) // step)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp_ok(secret: str, code: str, at: float | None = None, window: int = 1,
            last_used: int = -1) -> int:
    """→ the matching time step (to stop the same code being used twice), or -1."""
    code = "".join(c for c in (code or "") if c.isdigit())
    if len(code) != 6:
        return -1
    now = at if at is not None else time.time()
    for d in range(-window, window + 1):
        step = int(now // 30) + d
        if step > last_used and hmac.compare_digest(totp(secret, step * 30), code):
            return step
    return -1


def otpauth_uri(secret: str, account: str, issuer: str = "GAMbit") -> str:
    from urllib.parse import quote
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}"
            f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30")
