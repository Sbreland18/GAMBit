"""Small HTTP helpers built on urllib (no extra dependencies to bundle)."""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from typing import Callable, Optional

from .version import APP_NAME, __version__

USER_AGENT = f"{APP_NAME}/{__version__}"


def _context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:  # Use the Windows/macOS certificate store when available
        import truststore  # type: ignore

        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        pass
    return ctx


class NoDowngrade(urllib.request.HTTPRedirectHandler):
    """Follow redirects only to https:// – never from https down to plain http – and keep
    the headers of each redirect (Hugging Face puts a file's SHA-256 there)."""

    def __init__(self):
        super().__init__()
        self.seen: list[dict] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not str(newurl).lower().startswith("https://") and \
                str(req.full_url).lower().startswith("https://"):
            raise urllib.error.URLError(f"refused a redirect from https to {newurl[:80]}")
        self.seen.append({k.lower(): v for k, v in dict(headers or {}).items()})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(req, timeout: int):
    """urlopen with verified TLS and no https→http redirects. → (response, redirects)."""
    redirects = NoDowngrade()
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_context()),
                                         redirects)
    return opener.open(req, timeout=timeout), redirects


def get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                 "Cache-Control": "no-cache"},
    )
    resp, _r = _open(req, timeout)
    with resp:
        return json.loads(resp.read(8 * 1024 * 1024).decode("utf-8-sig"))


class IntegrityError(RuntimeError):
    pass


def sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: str,
             progress: Optional[Callable[[int, int], None]] = None,
             cancelled: Optional[Callable[[], bool]] = None,
             sha256: str = "", sha256_from_header: str = "") -> str:
    """Download url to dest, reporting (bytes_done, bytes_total). With sha256 (or a header
    of a redirect that carries it, e.g. 'x-linked-etag'), the file is checked and deleted
    if it doesn't match."""
    if not str(url).lower().startswith("https://"):
        raise IntegrityError("Downloads must use https.")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    resp, redirects = _open(req, 60)
    with resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as fh:
            while True:
                if cancelled and cancelled():
                    raise RuntimeError("Download cancelled")
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if sha256_from_header and not sha256:
            for h in redirects.seen + [{k.lower(): v for k, v in dict(resp.headers).items()}]:
                v = str(h.get(sha256_from_header.lower(), "")).strip('" ').lower()
                if re.fullmatch(r"[0-9a-f]{64}", v):
                    sha256 = v
                    break
            else:
                os.remove(dest)
                raise IntegrityError("The download didn't come with a checksum to verify.")
    if sha256:
        got = sha256_file(dest)
        if got.lower() != sha256.lower().removeprefix("sha256:"):
            os.remove(dest)
            raise IntegrityError("The download doesn't match its published checksum – it "
                                 "was deleted. Try again later.")
    return dest


def parse_version(text: str) -> tuple:
    """'v7.48.26' -> (7, 48, 26). Missing/garbage parts become 0."""
    m = re.search(r"\d+(?:\.\d+)*", text or "")
    nums = m.group(0).split(".")[:4] if m else []
    return tuple(int(n) for n in nums) or (0,)


_PRE = re.compile(r"^[-._+ ]?(alpha|beta|preview|pre|rc|dev|a|b)\.?(\d*)(?![a-z])", re.I)


def _version_key(text: str) -> tuple:
    """Sortable: (numbers…, release?, pre-release number). '1.5.0-beta2' sorts before
    '1.5.0', so a test build is never offered as an update to the release."""
    text = (text or "").strip()
    core = list(parse_version(text))
    core += [0] * (4 - len(core))
    m = re.search(r"\d+(?:\.\d+)*", text)
    tail = text[m.end():] if m else ""
    pre = _PRE.match(tail)
    if pre:
        return (*core, 0, int(pre.group(2) or 0))
    return (*core, 1, 0)


def is_newer(remote: str, local: str) -> bool:
    return _version_key(remote) > _version_key(local)


def request(method: str, url: str, headers: Optional[dict] = None, body=None,
            timeout: int = 60) -> tuple[int, dict, bytes]:
    """Generic HTTP call → (status, response headers, body bytes). JSON bodies are encoded.
    HTTP errors are returned, not raised, so callers can show the server's message."""
    import urllib.error
    data = None
    h = {"User-Agent": USER_AGENT, **(headers or {})}
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        else:
            data = body if isinstance(body, bytes) else str(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=h, method=method.upper())
    try:
        resp, _r = _open(req, timeout)
        with resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() if hasattr(e, "read") else b""
