"""Cached lists of org units, users and groups, plus the shared connection test.

Lists are loaded in the background after a successful connection test and
saved to disk, so pickers work instantly the next time GAMbit starts.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import time

from PySide6.QtCore import QObject, QStandardPaths, Signal

from .gam_runner import gam_environment, gam_prefix
from .settings import IS_WINDOWS, settings


# Set by the main window while someone is signed in: guard(args) -> '' or why not.
# Background workers call GAM directly, so changes are checked here too.
LOW_LEVEL_GUARD = None


# True inside the GAMbit window (not the background tasks): help-desk mode applies to
# GAM calls made by background workers too, not just to the runner.
INTERACTIVE = False


def _refused(args: list[str]) -> str:
    from .secret_args import masked_secret
    if masked_secret(args):
        return "the saved password was removed after it ran – set a new one instead"
    if INTERACTIVE:
        from .gam_runner import blocked_reason
        why = blocked_reason(list(args))
        if why:
            return why[0].lower() + why[1:].rstrip(".")
    g = LOW_LEVEL_GUARD
    if g is None:
        return ""
    try:
        return g(list(args)) or ""
    except Exception as exc:  # noqa: BLE001
        return f"access check failed: {exc}"


def run_gam_csv(args: list[str], timeout: int = 900) -> tuple[int, list[dict], str]:
    """Run a `gam print …` command; returns (code, rows as dicts, stderr)."""
    why = _refused(args)
    if why:
        return 77, [], f"Not run – {why}"
    try:   # the whole fleet was just loaded on Chromebook fleet: use that list
        from . import fleet_cache
        cached = fleet_cache.get(args)
        if cached is not None:
            return 0, cached, ""
    except Exception:  # noqa: BLE001
        pass
    gam = settings.gam_path()
    if not gam:
        return -1, [], "GAM is not installed."
    try:
        p = _run(gam, args, timeout)
    except subprocess.TimeoutExpired:
        return 124, [], f"GAM didn't finish within {timeout} seconds."
    except OSError as exc:
        return 126, [], f"Couldn't start GAM: {exc}"
    rows = list(csv.DictReader(io.StringIO(p.stdout or "")))
    if p.returncode == 0 and [str(a) for a in args[:2]] == ["print", "cros"]:
        try:   # so the activity log can show serials instead of device IDs
            from . import device_names
            device_names.remember(rows)
        except Exception:  # noqa: BLE001
            pass
    return p.returncode, rows, p.stderr or ""


def _run(gam: str, args: list[str], timeout: int):
    flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
    from .secret_args import fill_here
    return subprocess.run([gam, *gam_prefix(), *fill_here(args)], capture_output=True, text=True,
                          timeout=timeout, env=gam_environment(), creationflags=flags,
                          encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)


def run_gam_text(args: list[str], timeout: int = 120) -> tuple[int, str]:
    why = _refused(args)
    if why:
        return 77, f"Not run – {why}"
    gam = settings.gam_path()
    if not gam:
        return -1, "GAM is not installed."
    try:
        p = _run(gam, args, timeout)
    except subprocess.TimeoutExpired:
        return 124, f"GAM didn't finish within {timeout} seconds."
    except OSError as exc:
        return 126, f"Couldn't start GAM: {exc}"
    try:
        from . import fleet_cache
        fleet_cache.changed(" ".join(str(a) for a in args))
    except Exception:  # noqa: BLE001
        pass
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _pick(row: dict, *names) -> str:
    low = {k.lower(): v for k, v in row.items() if k}
    for n in names:
        if low.get(n.lower()):
            return low[n.lower()]
    return ""


# ------------------------------------------------------------- loaders ---
def load_ous() -> list[str]:
    code, rows, err = run_gam_csv(["print", "orgs", "fields", "orgunitpath"])
    if code != 0:
        raise RuntimeError(err.strip().splitlines()[-1] if err.strip() else "Could not load OUs")
    paths = {_pick(r, "orgUnitPath") for r in rows}
    paths.discard("")
    paths.add("/")
    return sorted(paths, key=str.lower)


def _org(row: dict, field: str) -> str:
    """Title/department from the primary organization (or the first one)."""
    first = ""
    for k, v in row.items():
        m = re.match(r"organizations\.(\d+)\.primary", k or "", re.I)
        if m and (v or "").lower() == "true":
            return row.get(f"organizations.{m.group(1)}.{field}", "") or ""
    first = row.get(f"organizations.0.{field}", "") or first
    return first


_ORG_FIELDS = ("name", "title", "department", "location", "costCenter", "description",
               "domain", "symbol", "fullTimeEquivalent", "type", "customType", "primary")


def _multi(row: dict, prefix: str, fields) -> list[dict]:
    """[{field: value}] from flattened CSV columns like organizations.0.title."""
    by_n: dict[int, dict] = {}
    low = {f.lower(): f for f in fields}
    for k, v in row.items():
        m = re.match(rf"{prefix}\.(\d+)\.(\w+)$", k or "", re.I)
        if m and m.group(2).lower() in low and v not in (None, ""):
            by_n.setdefault(int(m.group(1)), {})[low[m.group(2).lower()]] = v
    return [by_n[n] for n in sorted(by_n)]


def load_users() -> list[dict]:
    code, rows, err = run_gam_csv(["print", "users", "fields",
                                   "primaryemail,name,suspended,ou,lastlogintime,externalids,"
                                   "organizations"])
    if code != 0:
        raise RuntimeError(err.strip().splitlines()[-1] if err.strip() else "Could not load users")
    out = []
    for r in rows:
        email = _pick(r, "primaryEmail")
        if not email:
            continue
        name = _pick(r, "name.fullName") or " ".join(
            x for x in (_pick(r, "name.givenName"), _pick(r, "name.familyName")) if x)
        sis_id = ""
        for k, v in r.items():   # externalIds.N.type / externalIds.N.value
            m = re.match(r"externalIds\.(\d+)\.type", k or "", re.I)
            if m and (v or "").lower() == "organization":
                sis_id = r.get(f"externalIds.{m.group(1)}.value", "") or sis_id
        out.append({"email": email, "name": name, "ou": _pick(r, "orgUnitPath"),
                    "suspended": _pick(r, "suspended").lower() == "true",
                    "last_login": _pick(r, "lastLoginTime"), "sis_id": sis_id,
                    "title": _org(r, "title"), "department": _org(r, "department"),
                    # every ID and organization, so updates can keep the ones GAMbit
                    # doesn't manage (GAM replaces the whole list)
                    "ext_ids": _multi(r, "externalIds", ("type", "customType", "value")),
                    "orgs": _multi(r, "organizations", _ORG_FIELDS)})
    return out


def load_groups() -> list[dict]:
    code, rows, err = run_gam_csv(["print", "groups", "fields",
                                   "email,name,description,directmemberscount"])
    if code != 0:
        raise RuntimeError(err.strip().splitlines()[-1] if err.strip() else "Could not load groups")
    return [{"email": _pick(r, "email"), "name": _pick(r, "name"),
             "description": _pick(r, "description"),
             "members": _pick(r, "directMembersCount")} for r in rows if _pick(r, "email")]


def test_domain() -> tuple[bool, str, str]:
    """Returns (ok, primary domain or error, full output)."""
    code, out = run_gam_text(["info", "domain"])
    if code == 0:
        dom = next((ln.split(":", 1)[1].strip() for ln in out.splitlines()
                    if ln.strip().lower().startswith("primary domain")), "")
        return True, dom or "Connected", out
    last = out.strip().splitlines()[-1] if out.strip() else "No response from GAM"
    return False, last, out


# --------------------------------------------------------------- cache ---
class Directory(QObject):
    """Holds the cached lists. Widgets connect to the *_changed signals."""

    connection_changed = Signal(bool, str)   # ok, domain-or-error
    ous_changed = Signal()
    users_changed = Signal()
    groups_changed = Signal()
    busy_changed = Signal(str)               # human message, "" when idle

    def __init__(self, parent=None):
        super().__init__(parent)
        self.connected: bool | None = None
        self.domain = ""
        self.ous: list[str] = []
        self.users: list[dict] = []
        self.all_users: list[dict] = []      # before org-unit scope filtering
        self.groups: list[dict] = []
        self.loaded_at: dict[str, float] = {}
        self._loading: set[str] = set()
        self._set_path()
        self._read_cache()

    def _set_path(self):
        from . import profiles
        name = profiles.slug(profiles.current_name())
        fname = "directory_cache.json" if name == "default" else f"directory_cache_{name}.json"
        self._path = os.path.join(
            QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or
            os.path.expanduser("~"), fname)

    @staticmethod
    def _scoped(users: list[dict]) -> list[dict]:
        """Only the people inside the signed-in person's org units (if they're limited)."""
        from .auth import session
        roots = session.scope()
        if not roots:
            return list(users)
        return [u for u in users if session.in_scope(u.get("ou", ""), roots)]

    def apply_scope(self):
        self.users = self._scoped(self.all_users or self.users)
        self.users_changed.emit()

    def reload_for_profile(self):
        """Switch to the cached lists for the newly selected domain profile."""
        self.connected, self.domain = None, ""
        self.ous, self.users, self.groups, self.loaded_at = [], [], [], {}
        self.all_users = []
        self._set_path()
        self._read_cache()
        for sig in (self.ous_changed, self.users_changed, self.groups_changed):
            sig.emit()

    # disk cache ----------------------------------------------------------
    def _read_cache(self):
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.ous = data.get("ous", [])
            self.all_users = data.get("users", [])
            self.users = self._scoped(self.all_users)
            self.groups = data.get("groups", [])
            self.loaded_at = data.get("loaded_at", {})
        except Exception:
            pass

    def _write_cache(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump({"ous": self.ous, "users": self.all_users or self.users,
                           "groups": self.groups,
                           "loaded_at": self.loaded_at}, fh)
        except Exception:
            pass

    def age_text(self, kind: str) -> str:
        t = self.loaded_at.get(kind)
        if not t:
            return "not loaded yet"
        mins = int((time.time() - t) / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins} min ago"
        if mins < 1440:
            return f"{mins // 60} hr ago"
        return f"{mins // 1440} days ago"

    # background refresh ----------------------------------------------------
    def _refresh(self, kind, fn, attr, signal, on_done=None, log=None):
        from .ui.widgets import Worker  # avoid import cycle

        if kind in self._loading:
            return
        self._loading.add(kind)
        self.busy_changed.emit(f"Loading {kind}…")

        def done(result):
            self._loading.discard(kind)
            if attr == "users":
                self.all_users = result
                result = self._scoped(result)
            setattr(self, attr, result)
            self.loaded_at[kind] = time.time()
            self._write_cache()
            signal.emit()
            self.busy_changed.emit("")
            if log:
                log(f"Loaded {len(result)} {kind}.")
            if on_done:
                on_done(True)

        def failed(err):
            self._loading.discard(kind)
            self.busy_changed.emit("")
            if log:
                log(f"Could not load {kind}: {err}", "#ff8a80")
            if on_done:
                on_done(False)

        Worker(fn, on_done=done, on_error=failed)

    def refresh_ous(self, on_done=None, log=None):
        self._refresh("org units", load_ous, "ous", self.ous_changed, on_done, log)

    def refresh_users(self, on_done=None, log=None):
        self._refresh("users", load_users, "users", self.users_changed, on_done, log)

    def refresh_groups(self, on_done=None, log=None):
        self._refresh("groups", load_groups, "groups", self.groups_changed, on_done, log)

    def is_loading(self, kind: str) -> bool:
        return kind in self._loading

    # connection ---------------------------------------------------------------
    def test_connection(self, on_done=None, log=None):
        from .ui.widgets import Worker

        self.busy_changed.emit("Testing connection…")

        def done(result):
            ok, text, out = result
            self.connected, self.domain = ok, (text if ok else "")
            self.busy_changed.emit("")
            if log:
                log(out.strip(), None if ok else "#ff8a80")
            self.connection_changed.emit(ok, text)
            if ok:
                # Refresh lists that are missing or older than a day
                day = 24 * 3600
                if not self.ous or time.time() - self.loaded_at.get("org units", 0) > day:
                    self.refresh_ous(log=log)
                if not self.groups or time.time() - self.loaded_at.get("groups", 0) > day:
                    self.refresh_groups(log=log)
                if not self.users or time.time() - self.loaded_at.get("users", 0) > day:
                    self.refresh_users(log=log)
            if on_done:
                on_done(ok, text)

        Worker(test_domain, on_done=done,
               on_error=lambda e: done((False, str(e), str(e))))
