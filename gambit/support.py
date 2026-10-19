"""Logging, crash handling and "Report a problem" zips."""

from __future__ import annotations

import datetime
import json
import logging
import logging.handlers
import os
import platform
import sys
import traceback
import zipfile

from .version import APP_NAME, __version__

SECRET_KEYS = ("token", "pin", "password", "secret", "webhook", "api_key")
log = logging.getLogger("gambit")


def logs_dir() -> str:
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    d = os.path.join(base, "logs")
    os.makedirs(d, exist_ok=True)
    return d


def setup_logging():
    if log.handlers:
        return
    h = logging.handlers.RotatingFileHandler(os.path.join(logs_dir(), "gambit.log"),
                                             maxBytes=1_000_000, backupCount=3,
                                             encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    log.info("%s %s starting (%s, Python %s)", APP_NAME, __version__, platform.platform(),
             platform.python_version())


def install_crash_handler():
    """Log every unhandled error and offer a problem report instead of vanishing."""
    setup_logging()
    try:
        from PySide6.QtCore import qInstallMessageHandler

        def qt_messages(mode, _ctx, msg):
            if "propagateSizeHints" not in msg:
                log.warning("Qt: %s", msg)
        qInstallMessageHandler(qt_messages)
    except Exception:  # noqa: BLE001
        pass

    def hook(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))
        log.error("Unhandled error:\n%s", text)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is None:
                return
            box = QMessageBox(QMessageBox.Warning, f"{APP_NAME} hit a problem",
                              f"Something went wrong:\n\n{value}\n\nGAMbit is still running, "
                              "but if this keeps happening, save a problem report and send it "
                              "to whoever looks after GAMbit.")
            save = box.addButton("Save a problem report…", QMessageBox.ActionRole)
            box.addButton(QMessageBox.Close)
            box.setDetailedText(text)
            box.exec()
            if box.clickedButton() is save:
                ask_and_save(None, f"Unhandled error:\n{text}")
        except Exception:  # noqa: BLE001
            pass
    sys.excepthook = hook


def _settings_dump() -> dict:
    from .settings import settings
    out = {}
    for k in settings._s.allKeys():
        if any(s in k.lower() for s in SECRET_KEYS):
            out[k] = "(hidden)"
            continue
        v = settings._s.value(k)
        out[k] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
    return out


def make_report(path: str, description: str = "", output_text: str = "") -> str:
    from . import activity
    from .gam_runner import gam_version_text
    from .settings import settings
    info = {"app": APP_NAME, "version": __version__,
            "frozen": bool(getattr(sys, "frozen", False)), "python": platform.python_version(),
            "os": platform.platform(), "when": datetime.datetime.now().isoformat(
                timespec="seconds"),
            "gam_path": settings.gam_path(), "gam_version": gam_version_text()}
    try:
        import PySide6
        info["pyside6"] = PySide6.__version__
    except Exception:  # noqa: BLE001
        pass
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", f"{APP_NAME} problem report\n\nWhat happened:\n"
                    f"{description or '(not described)'}\n")
        zf.writestr("system.json", json.dumps(info, indent=2))
        zf.writestr("settings.json", json.dumps(_settings_dump(), indent=2, default=str))
        for name in sorted(os.listdir(logs_dir())):
            p = os.path.join(logs_dir(), name)
            if os.path.isfile(p) and os.path.getsize(p) < 5_000_000:
                zf.write(p, f"logs/{name}")
        try:
            entries = activity.load(14)[:500]          # passwords are already masked
            zf.writestr("activity-last-14-days.json", json.dumps(entries, indent=1))
        except Exception as exc:  # noqa: BLE001
            zf.writestr("activity-error.txt", str(exc))
        if output_text:
            zf.writestr("output-panel.txt", output_text[-200_000:])
    return path


def default_report_path() -> str:
    from PySide6.QtCore import QStandardPaths
    desk = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation) or \
        os.path.expanduser("~")
    return os.path.join(desk, f"GAMbit-problem-report-{datetime.datetime.now():%Y%m%d-%H%M}.zip")


def ask_and_save(parent, description: str = "", output_text: str = ""):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox
    if not description:
        text, ok = QInputDialog.getMultiLineText(
            parent, "Report a problem", "What were you doing, and what went wrong?\n"
            "(The report includes GAMbit's logs, settings without passwords or tokens, and "
            "the last two weeks of the activity log – with passwords hidden.)")
        if not ok:
            return None
        description = text
    path, _ = QFileDialog.getSaveFileName(parent, "Save problem report", default_report_path(),
                                          "Zip (*.zip)")
    if not path:
        return None
    try:
        make_report(path, description, output_text)
    except Exception as exc:  # noqa: BLE001
        QMessageBox.warning(parent, "Report a problem", f"Couldn't save the report:\n{exc}")
        return None
    QMessageBox.information(parent, "Report a problem",
                            f"Saved:\n{path}\n\nAttach this file when you report the problem.")
    QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))
    return path
