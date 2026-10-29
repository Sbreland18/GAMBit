"""Temporary files (CSV uploads, previews, downloaded sheets): in a folder only this
Windows user can open, made fresh for each GAMbit run (unpredictable name), and removed
afterwards – they often hold names and email addresses."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import time

_DIR: dict = {}


def folder() -> str:
    d = _DIR.get("path")
    if d and os.path.isdir(d):
        return d
    cleanup_old()
    d = tempfile.mkdtemp(prefix="GAMbit-")          # 0700, random name
    _DIR["path"] = d
    atexit.register(lambda: shutil.rmtree(d, ignore_errors=True))
    return d


def cleanup_old(hours: float = 24):
    """Leftovers from runs that ended without cleaning up (and the old shared folder)."""
    base = tempfile.gettempdir()
    cut = time.time() - hours * 3600
    try:
        names = os.listdir(base)
    except OSError:
        return
    for n in names:
        p = os.path.join(base, n)
        if not (n.startswith("GAMbit-") or n == "GAMbit"):
            continue
        try:
            if os.path.isdir(p) and os.path.getmtime(p) < cut:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            continue
