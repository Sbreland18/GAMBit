"""Shared test setup: isolated settings, offscreen Qt, and a fake GAM.

Run from the project folder:   python -m pytest -q
"""

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="gambit-tests-")
os.environ["GAMBIT_SETTINGS_INI"] = os.path.join(_TMP, "settings.ini")

from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
_app = QApplication.instance() or QApplication([])
_app.setApplicationName("GAMbitTests")
_app.setOrganizationName("GAMbitTests")

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fakegam", "fake_gam.py")


@pytest.fixture
def qapp():
    return _app


@pytest.fixture
def fake_gam(tmp_path, monkeypatch):
    """Point GAMbit at a fake gam that answers from canned data and logs every call."""
    from gambit.settings import settings
    log = tmp_path / "calls.log"
    if sys.platform.startswith("win"):
        wrapper = tmp_path / "gam.bat"
        wrapper.write_text(f'@"{sys.executable}" "{FAKE}" %*\n')
    else:
        wrapper = tmp_path / "gam"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
        wrapper.chmod(0o755)
    monkeypatch.setenv("FAKEGAM_LOG", str(log))
    monkeypatch.setattr(type(settings), "gam_path", lambda self: str(wrapper))

    class Fake:
        path = str(wrapper)

        @staticmethod
        def calls() -> list[str]:
            return log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return Fake


@pytest.fixture
def team_dir(tmp_path):
    from gambit.settings import settings
    d = tmp_path / "team"
    d.mkdir()
    settings.set("team/folder", str(d))
    yield d
    settings.set("team/folder", "")
