"""Small GAM wrappers for Google Sheets and email.

Everything here runs GAM as a Google account (the "GAMbit account") that can
open the sheets you import from and owns the sheets GAMbit creates. Defaults
to the admin you signed GAM in with.

Commands used (GAM7):
  gam user U get drivefile <id> csvsheet <tab> targetfolder D targetname N overwrite
  gam user U get drivefile <id> format csv targetfolder D targetname N overwrite
  gam user U create drivefile localfile F drivefilename T mimetype gsheet returnlinkonly
  gam user U update drivefile <id> localfile F csvsheet <tab>
  gam sendemail to A,B [from U] subject S message M [attach F]
"""

from __future__ import annotations

import os
import re
import tempfile

from . import profiles
from .directory import run_gam_text
from .settings import settings


def _key() -> str:
    return f"google/admin_email/{profiles.slug(profiles.current_name())}"


def admin_email() -> str:
    return (settings.get(_key(), "") or settings.get("google/admin_email", "") or
            settings.get("gam/admin", "") or "").strip()


def set_admin_email(email: str):
    settings.set(_key(), email.strip())
    if not settings.get("google/admin_email", ""):
        settings.set("google/admin_email", email.strip())


def detect_admin_email() -> str:
    """Ask GAM who it is signed in as (gam oauth info)."""
    code, out = run_gam_text(["oauth", "info"], timeout=60)
    if code != 0:
        return ""
    for ln in out.splitlines():
        if "admin" in ln.lower() or "user" in ln.lower():
            m = re.search(r"[\w.+'-]+@[\w-]+\.[\w.-]+", ln)
            if m:
                return m.group(0)
    m = re.search(r"[\w.+'-]+@[\w-]+\.[\w.-]+", out)
    return m.group(0) if m else ""


def file_id(url_or_id: str) -> str:
    """Accept a Sheets/Drive link or a bare ID."""
    s = (url_or_id or "").strip()
    for pat in (r"/d/([A-Za-z0-9_-]{20,})", r"[?&]id=([A-Za-z0-9_-]{20,})",
                r"/files/([A-Za-z0-9_-]{20,})"):
        m = re.search(pat, s)
        if m:
            return m.group(1)
    return s


def _user(user: str = "") -> str:
    u = (user or admin_email()).strip()
    if "@" not in u:
        raise RuntimeError("Set the Google account GAMbit uses for Sheets in Settings "
                           "(Settings & Updates → Google Sheets and email).")
    return u


def _last_error(out: str) -> str:
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else "GAM didn't say why."


def download_sheet(url_or_id: str, tab: str = "", user: str = "") -> str:
    """Download one tab of a Google Sheet as CSV; returns the local file path."""
    fid = file_id(url_or_id)
    if not fid:
        raise RuntimeError("Paste the Google Sheet link first.")
    folder = os.path.join(tempfile.gettempdir(), "GAMbit")
    os.makedirs(folder, exist_ok=True)
    name = f"sheet_{fid[:12]}.csv"
    target = os.path.join(folder, name)
    if os.path.exists(target):
        os.remove(target)
    args = ["user", _user(user), "get", "drivefile", fid]
    args += ["csvsheet", tab] if tab.strip() else ["format", "csv"]
    args += ["targetfolder", folder, "targetname", name, "overwrite"]
    code, out = run_gam_text(args, timeout=300)
    if code != 0 or not os.path.isfile(target):
        raise RuntimeError("Couldn't download the sheet: " + _last_error(out) +
                           "\n\nCheck the link, the tab name, and that "
                           f"{_user(user)} can open the sheet.")
    return target


def upload_csv_as_sheet(path: str, title: str, user: str = "") -> str:
    """Upload a CSV as a new Google Sheet; returns its link."""
    code, out = run_gam_text(["user", _user(user), "create", "drivefile", "localfile", path,
                              "drivefilename", title, "mimetype", "gsheet",
                              "returnlinkonly"], timeout=300)
    if code != 0:
        raise RuntimeError("Couldn't create the sheet: " + _last_error(out))
    m = re.search(r"https://\S+", out)
    return m.group(0) if m else ""


def replace_sheet_tab(url_or_id: str, tab: str, path: str, user: str = ""):
    """Replace one tab of an existing sheet with the CSV's contents."""
    base = ["user", _user(user), "update", "drivefile", file_id(url_or_id), "localfile", path]
    code, out = run_gam_text(base + ["csvsheet", tab], timeout=300)
    if code != 0:   # the tab may not exist yet
        code, out = run_gam_text(base + ["addsheet", tab], timeout=300)
    if code != 0:
        raise RuntimeError("Couldn't update the sheet: " + _last_error(out))


def email_args(to: str, subject: str, body: str, attach: str = "", sender: str = "") -> list:
    args = ["sendemail", "to", to]
    if sender or admin_email():
        args += ["from", sender or admin_email()]
    args += ["subject", subject, "message", body]
    if attach:
        args += ["attach", attach]
    return args


def send_email(to: str, subject: str, body: str, attach: str = "", sender: str = ""):
    code, out = run_gam_text(email_args(to, subject, body, attach, sender), timeout=120)
    if code != 0:
        raise RuntimeError("Couldn't send the email: " + _last_error(out))


def write_tab_in_place(url_or_id: str, tab: str, rows: list[list], user: str = "") -> bool:
    """Write rows into an existing tab with `update sheetrange` so the sheet keeps its
    formatting, charts and links. Leftover rows from a longer earlier write are blanked.
    Returns False (without raising) when the tab doesn't exist yet or GAM refuses."""
    import json as _json
    from .settings import settings
    from .tools import gam_extras3 as g3
    fid = file_id(url_or_id)
    key = f"sheetrange/rows/{fid}/{tab}"
    try:
        prev = _json.loads(settings.get(key, "[0, 0]") or "[0, 0]")
    except ValueError:
        prev = [0, 0]
    width = max([len(r) for r in rows] + [int(prev[1] or 0), 1])
    body = g3.pad(rows, int(prev[0] or 0), width)
    rng = "'" + tab.replace("'", "''") + "'!A1"
    try:
        code, _out = run_gam_text(g3.sheetrange_args(_user(user), fid, rng, body), timeout=300)
    except Exception:  # noqa: BLE001
        return False
    if code != 0:
        return False
    settings.set(key, _json.dumps([len(rows), max((len(r) for r in rows), default=1)]))
    return True
