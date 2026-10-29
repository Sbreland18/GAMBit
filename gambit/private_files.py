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


SYNCED_NAMES = ("onedrive", "google drive", "googledrive", "my drive", "dropbox", "box",
                "icloud drive", "icloudrive", "sharepoint")


def synced_or_shared(folder: str) -> bool:
    """A folder OneDrive/Google Drive/Dropbox/Box syncs, or on a network share. Whole folder
    names are compared – a folder called “CodexSandbox” isn't Box."""
    raw = str(folder or "")
    low = os.path.abspath(raw).lower().replace("\\", "/")
    if raw.startswith(("\\\\", "//")) or low.startswith("//"):
        return True
    for part in low.split("/"):
        p = part.strip()
        if not p:
            continue
        if p in SYNCED_NAMES or p.startswith(("onedrive -", "onedrive-", "dropbox (",
                                               "box (", "google drive (")):
            return True
    return False
