"""Persistent user settings (stored by Qt in the registry / an ini file)."""

from __future__ import annotations

import os
import shutil
import sys

from PySide6.QtCore import QSettings

from .version import APP_NAME

IS_WINDOWS = sys.platform.startswith("win")
GAM_EXE = "gam.exe" if IS_WINDOWS else "gam"


def default_gam_dir() -> str:
    if IS_WINDOWS:
        return r"C:\GAM7"
    return os.path.join(os.path.expanduser("~"), "bin", "gam7")


class Settings:
    def __init__(self):
        ini = os.environ.get("GAMBIT_SETTINGS_INI", "")
        # tests (and portable setups) can keep settings in an .ini file instead
        self._s = QSettings(ini, QSettings.IniFormat) if ini else QSettings(APP_NAME, APP_NAME)
        # in-memory values that win over saved ones (used by scheduled tasks so they
        # can use another domain profile without changing what the app shows)
        self.override: dict = {}

    # --- generic -----------------------------------------------------
    def get(self, key: str, default=None):
        val = self.override[key] if key in self.override else self._s.value(key, default)
        if isinstance(val, str) and val.startswith("enc:v1:"):
            from .secrets_store import unseal
            val = unseal(val)
        if isinstance(default, bool) and isinstance(val, str):
            return val.lower() in ("1", "true", "yes")
        return val

    def set(self, key: str, value):
        from .secrets_store import is_secret, seal
        if is_secret(key) and isinstance(value, str) and value:
            value = seal(value)          # encrypted for this Windows user (DPAPI)
        self._s.setValue(key, value)
        self._s.sync()

    def fresh(self, key: str, default=None):
        """get() after re-reading what other GAMbit processes (scheduled tasks) saved."""
        try:
            self._s.sync()
        except Exception:  # noqa: BLE001
            pass
        return self.get(key, default)

    # --- GAM locations -------------------------------------------------
    @property
    def gam_dir(self) -> str:
        return self.get("gam/dir", "") or default_gam_dir()

    @gam_dir.setter
    def gam_dir(self, value: str):
        self.set("gam/dir", value)

    @property
    def gam_cfg_dir(self) -> str:
        """Optional GAMCFGDIR override. Blank = GAM's default (~/.gam)."""
        return self.get("gam/cfgdir", "") or ""

    @gam_cfg_dir.setter
    def gam_cfg_dir(self, value: str):
        self.set("gam/cfgdir", value)

    def gam_path(self) -> str | None:
        """Best guess at the gam executable, or None if not found."""
        candidate = os.path.join(self.gam_dir, GAM_EXE)
        if os.path.isfile(candidate):
            return candidate
        found = shutil.which("gam")
        return found

    # --- update preferences ----------------------------------------------
    @property
    def check_updates_on_start(self) -> bool:
        return self.get("updates/on_start", True)

    @check_updates_on_start.setter
    def check_updates_on_start(self, value: bool):
        self.set("updates/on_start", bool(value))


settings = Settings()
