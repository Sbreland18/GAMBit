"""Files that hold passwords (new-account lists, printable cards): readable only by the
person who made them, and not kept forever."""

from __future__ import annotations

import fnmatch
import os
import time

PASSWORD_PATTERNS = ("*_new_accounts.csv", "*_new_accounts_cards.html")
KEEP_DAYS = 30


def restrict(path: str):
    """Only this Windows user (and SYSTEM) may open the file. Best effort."""
    try:
        if os.name == "nt":
            import getpass
            import subprocess
            subprocess.run(["icacls", path, "/inheritance:r", "/grant:r",
                            f"{getpass.getuser()}:F", "*S-1-5-18:F"],
                           capture_output=True, timeout=20,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.chmod(path, 0o600)
    except Exception:  # noqa: BLE001
        pass


def purge_old(folder: str, patterns=PASSWORD_PATTERNS, days: int = KEEP_DAYS) -> int:
    """Delete password files older than `days`. Returns how many."""
    n = 0
    cut = time.time() - days * 86400
    try:
        names = os.listdir(folder)
    except OSError:
        return 0
    for f in names:
        if any(fnmatch.fnmatch(f, p) for p in patterns):
            p = os.path.join(folder, f)
            try:
                if os.path.isfile(p) and os.path.getmtime(p) < cut:
                    os.remove(p)
                    n += 1
            except OSError:
                continue
    return n


def synced_or_shared(folder: str) -> bool:
    """A folder OneDrive/Google Drive syncs, or on a network share."""
    low = os.path.abspath(folder).lower().replace("\\", "/")
    return low.startswith("//") or any(w in low for w in ("onedrive", "google drive",
                                                         "googledrive", "dropbox", "box/"))
