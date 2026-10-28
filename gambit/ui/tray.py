"""GAMbit in the Windows taskbar tray, and desktop alerts.

- Closing the window keeps GAMbit running in the tray (Settings → Appearance), so long jobs
  keep going and alerts still arrive. Quit from the tray menu.
- Alerts: a long command finished while you were in another window, a background job
  failed, or new approval requests are waiting.
"""

from __future__ import annotations

import datetime
import time

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..settings import settings

TRAY_KEY, ALERTS_KEY = "ui/tray", "ui/desktop_alerts"
LONG_JOB = 20          # seconds: shorter commands don't get an alert


def tray_wanted() -> bool:
    return bool(settings.get(TRAY_KEY, True))


def alerts_wanted() -> bool:
    return bool(settings.get(ALERTS_KEY, True))


class Tray(QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.quitting = False
        self.told = False
        self.icon = None
        self._starts: dict[str, float] = {}
        self._approvals = None
        self._bg_since = datetime.datetime.now()
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        from ..resources import resource_path
        self.icon = QSystemTrayIcon(QIcon(resource_path("assets/gambit.ico")), win)
        self.icon.setToolTip("GAMbit")
        menu = QMenu()
        for text, fn in (("Open GAMbit", self.show_window),
                         ("Student lookup", lambda: self._open("Student lookup")),
                         ("Approvals", lambda: self._open("Approvals")),
                         ("Background jobs", lambda: self._open("Schedules"))):
            a = QAction(text, menu)
            a.triggered.connect(fn)
            menu.addAction(a)
        menu.addSeparator()
        q = QAction("Quit GAMbit", menu)
        q.triggered.connect(self.quit)
        menu.addAction(q)
        self._menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._activated)
        self.icon.messageClicked.connect(self.show_window)
        if tray_wanted():
            self.icon.show()
        win.runner.started.connect(self._started)
        win.runner.finished.connect(self._finished)
        self.timer = QTimer(self, interval=5 * 60 * 1000, timeout=self.check_background)
        self.timer.start()

    @property
    def active(self) -> bool:
        return self.icon is not None and tray_wanted()

    def apply_setting(self):
        if self.icon is not None:
            self.icon.setVisible(tray_wanted())

    # ---------------------------------------------------------------- window ---
    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()

    def show_window(self):
        self.win.showNormal()
        self.win.raise_()
        self.win.activateWindow()

    def _open(self, page):
        self.show_window()
        try:
            self.win._go_safe(page)
        except Exception:  # noqa: BLE001
            pass

    def quit(self):
        self.quitting = True
        from PySide6.QtWidgets import QApplication
        self.win.close()
        QApplication.quit()

    def closing(self, event) -> bool:
        """MainWindow.closeEvent: True when the window should only hide."""
        if self.quitting or not self.active:
            return False
        event.ignore()
        self.win.hide()
        if not self.told:
            self.told = True
            self.notify("GAMbit is still running",
                        "It's in the taskbar tray – jobs keep going and alerts still come. "
                        "Right-click the tray icon to quit.")
        return True

    # ---------------------------------------------------------------- alerts ---
    def notify(self, title: str, text: str, warn: bool = False):
        notices = getattr(self.win, "notices", None)
        if notices is not None:
            notices.add(title, text, "warn" if warn else "info")
        if self.icon is None or not self.icon.isVisible() or not alerts_wanted():
            return
        self.icon.showMessage(title, text, QSystemTrayIcon.Warning if warn else
                              QSystemTrayIcon.Information, 8000)

    def _away(self) -> bool:
        return not self.win.isVisible() or not self.win.isActiveWindow() or \
            self.win.isMinimized()

    def _started(self, cmd: str):
        self._starts[cmd] = time.time()

    def _finished(self, code: int, cmd: str):
        t = self._starts.pop(cmd, None)
        if t is None or time.time() - t < LONG_JOB or not self._away():
            return
        short = cmd if len(cmd) < 90 else cmd[:87] + "…"
        if code == 0:
            self.notify("Finished", short)
        elif code != -2:
            self.notify("Finished with a problem", f"{short}\nExit code {code} – see the "
                        "Output panel.", warn=True)

    def approvals(self, n: int):
        if self._approvals is not None and n > self._approvals:
            self.notify("Approval needed", f"{n} request(s) waiting on the Approvals page.")
        self._approvals = n

    def check_background(self):
        try:
            from .. import tasks_health
            runs = tasks_health.runs_since(self._bg_since)
        except Exception:  # noqa: BLE001
            return
        self._bg_since = datetime.datetime.now()
        bad = [r for r in runs if not r.get("ok") and not r.get("skipped")]
        if bad:
            names = ", ".join(sorted({tasks_health.label_for(r["key"]) for r in bad}))
            self.notify("A background job failed", f"{names} – see Home → Background jobs.",
                        warn=True)
