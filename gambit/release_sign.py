"""Checking (and, in the Builder, making) signed release information.

latest.json / release.json:
    {"version": "1.2.0", "url": "https://github.com/<repo>/releases/download/v1.2.0/…exe",
     "sha256": "<hex>", "notes": "…", "sig": "<Ed25519 over version, url and sha256>"}

An update is only installed when the download comes from GAMbit's own GitHub repository,
its SHA-256 matches, and – once this copy carries a release key – the signature checks out.
A changed latest.json, a swapped file on the network (an HTTPS-inspecting filter) or a
compromised download link can't make GAMbit run something else.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .auth import crypto

ALLOWED_HOSTS = {"github.com", "objects.githubusercontent.com",
                 "release-assets.githubusercontent.com"}


def _repo() -> str:
    from .version import GITHUB_REPO
    return GITHUB_REPO


def signed_part(meta: dict) -> bytes:
    return crypto.canonical({"version": str(meta.get("version", "")),
                             "url": str(meta.get("url", "")),
                             "sha256": str(meta.get("sha256", "")).lower()})


def url_ok(url: str) -> bool:
    u = urlparse(url or "")
    if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
        return False
    if u.hostname == "github.com":
        return u.path.lower().startswith(f"/{_repo().lower()}/releases/download/")
    return True


def keys() -> list[bytes]:
    try:
        from .release_keys import RELEASE_PUBKEYS
    except Exception:  # noqa: BLE001
        return []
    out = []
    for k in RELEASE_PUBKEYS:
        try:
            raw = crypto.unb64(k)
            if len(raw) == 32:
                out.append(raw)
        except (ValueError, TypeError):
            continue
    return out


def problem(meta: dict) -> str:
    """'' when the release information can be trusted, else why not."""
    if not url_ok(str(meta.get("url", ""))):
        return "the download isn't from GAMbit's GitHub repository"
    sha = str(meta.get("sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        return "it has no SHA-256 to check the download against"
    ks = keys()
    if ks:
        try:
            sig = crypto.unb64(str(meta.get("sig", "")))
        except (ValueError, TypeError):
            sig = b""
        if not any(crypto.verify(k, sig, signed_part(meta)) for k in ks):
            return "it isn't signed with GAMbit's release key"
    return ""


def sign(meta: dict, priv: bytes) -> dict:
    """Builder: add the signature."""
    return {**meta, "sig": crypto.b64(crypto.sign(priv, signed_part(meta)))}
