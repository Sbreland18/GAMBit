"""Round 22: the self-update installer that flashed and vanished."""

import os
import subprocess

from gambit import updaters
from gambit.settings import settings
from gambit.version import __version__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _launch(monkeypatch, silent, scope=""):
    calls = []
    monkeypatch.setattr(updaters, "IS_WINDOWS", True)
    monkeypatch.setattr(updaters, "install_scope_flag", lambda: scope)
    for n in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        monkeypatch.setattr(subprocess, n, 8, raising=False)
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    updaters.launch_installer("C:/t/GAMbit-Setup.exe", silent=silent)
    settings.set("update/in_progress", 0)
    return calls[0][0]


def test_silent_update_logs_and_keeps_scope(monkeypatch):
    args = _launch(monkeypatch, True, "/CURRENTUSER")
    assert "/SILENT" in args and "/CURRENTUSER" in args
    assert any(a.startswith("/LOG=") and a.endswith("GAMbit-update.log") for a in args)


def test_finishing_an_update_shows_the_installer(monkeypatch):
    args = _launch(monkeypatch, False)
    assert "/SILENT" not in args and "/VERYSILENT" not in args
    assert not any(a in ("/ALLUSERS", "/CURRENTUSER") for a in args)   # unknown: ask


def test_unfinished_update_detected_only_on_same_version():
    settings.set("update/in_progress", 123.0)
    settings.set("update/installer_path", "C:/t/x.exe")
    try:
        settings.set("update/from_version", __version__)
        info = updaters.unfinished_update()
        assert info and info["installer"] == "C:/t/x.exe"
        settings.set("update/from_version", "0.0.1")      # now newer: it worked
        assert updaters.unfinished_update() is None
        settings.set("update/in_progress", 0)
        settings.set("update/from_version", __version__)
        assert updaters.unfinished_update() is None
    finally:
        settings.set("update/in_progress", 0)


def test_installer_does_not_kill_itself():
    iss = open(os.path.join(ROOT, "installer", "GAMbit.iss"), encoding="utf-8").read()
    assert "'/F /IM GAMbit.exe'" in iss and "/T" not in iss.split("taskkill")[1][:60]
    assert "PrivilegesRequiredOverridesAllowed=commandline dialog" in iss
