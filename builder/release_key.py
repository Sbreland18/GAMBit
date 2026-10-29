"""The Builder's release-signing key (Ed25519).

The private key lives only on the PC that builds GAMbit (DPAPI-protected, next to the
Builder's own settings) – never in the repository or on GitHub. Its public key is written
into gambit/release_keys.py before every build, so each installed GAMbit accepts only
updates whose latest.json / release.json carry this key's signature. Someone who gets into
the GitHub account (or a web filter that rewrites downloads) still can't push a fake
update without this file.

Back the key file up somewhere safe: without it, the next version can't be signed and
installed copies won't take updates automatically (people would install it by hand).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gambit.auth import crypto  # noqa: E402
from gambit import release_sign  # noqa: E402

KEYS_MODULE = os.path.join(ROOT, "gambit", "release_keys.py")


def key_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "GAMbit Builder", "release-signing.key")


def load_or_create() -> tuple[bytes, bytes]:
    p = key_path()
    if os.path.isfile(p):
        priv = crypto.read_secret(p)
    else:
        priv, _pub = crypto.new_keypair()
        crypto.write_secret(p, priv)
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    pub = Ed25519PrivateKey.from_private_bytes(priv).public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return priv, pub


def _current() -> tuple[list[str], list[str]]:
    ns: dict = {}
    try:
        exec(compile(open(KEYS_MODULE, encoding="utf-8").read(), KEYS_MODULE, "exec"), ns)
    except OSError:
        pass
    return list(ns.get("RELEASE_PUBKEYS", [])), list(ns.get("TRUSTED_SIGNER_THUMBPRINTS", []))


def write_keys_module(pub: bytes, thumbprint: str = ""):
    """Put this key (keeping earlier ones, so a key change doesn't strand installs) and the
    code-signing certificate's thumbprint into gambit/release_keys.py."""
    keys, thumbs = _current()
    b = crypto.b64(pub)
    if b not in keys:
        keys.append(b)
    t = re.sub(r"[^0-9A-Fa-f]", "", thumbprint or "").upper()
    if len(t) == 40 and t not in thumbs:
        thumbs.append(t)
    text = ('"""Public keys that sign GAMbit releases – written by the Builder before each '
            'build.\nInstalled copies only accept updates signed with one of these."""\n\n'
            f"RELEASE_PUBKEYS: list[str] = {json.dumps(keys, indent=4)}\n\n"
            "# SHA-1 thumbprints of the certificate(s) the installer must be signed with\n"
            f"TRUSTED_SIGNER_THUMBPRINTS: list[str] = {json.dumps(thumbs, indent=4)}\n")
    with open(KEYS_MODULE, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def signed_release(meta: dict, installer: str, priv: bytes) -> dict:
    """latest.json / release.json content: the installer's SHA-256 plus the signature."""
    return release_sign.sign({**meta, "sha256": sha256(installer)}, priv)


def fingerprint() -> str:
    return crypto.fingerprint(load_or_create()[1])
