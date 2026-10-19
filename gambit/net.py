"""Small HTTP helpers built on urllib (no extra dependencies to bundle)."""

from __future__ import annotations

import json
import re
import ssl
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


def get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                 "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_context()) as resp:
        return json.loads(resp.read().decode("utf-8-sig"))


def download(url: str, dest: str,
             progress: Optional[Callable[[int, int], None]] = None,
             cancelled: Optional[Callable[[], bool]] = None) -> str:
    """Download url to dest, reporting (bytes_done, bytes_total)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60, context=_context()) as resp:
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
    return dest


def parse_version(text: str) -> tuple:
    """'v7.48.26' -> (7, 48, 26). Missing/garbage parts become 0."""
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(remote: str, local: str) -> bool:
    r, l = list(parse_version(remote)), list(parse_version(local))
    width = max(len(r), len(l))
    r += [0] * (width - len(r))
    l += [0] * (width - len(l))
    return r > l


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
        with urllib.request.urlopen(req, timeout=timeout, context=_context()) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() if hasattr(e, "read") else b""
