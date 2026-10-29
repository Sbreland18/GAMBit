"""In-window pop-up messages (bottom right) – “Suspended 3 accounts · Undo” – and the
notification history behind the 🔔 button in the top bar."""

from __future__ import annotations

import datetime
import json

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton,
)

from ..settings import settings

HIST_KEY = "notify/history"
HIST_MAX = 60


class NotifyCenter(QObject):
    """Every alert and pop-up, newest first, so nothing is lost when a pop-up closes."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        try:
            self.items = json.loads(settings.get(HIST_KEY, "[]") or "[]")
        except ValueError:
            self.items = []
        self.unread = 0

    def add(self, title: str, text: str = "", level: str = "info", page: str = ""):
        self.items.insert(0, {"t": datetime.datetime.now().isoformat(timespec="minutes"),
                              "title": title, "text": text, "level": level, "page": page})
        del self.items[HIST_MAX:]
        self.unread += 1
        try:
            settings.set(HIST_KEY, json.dumps(self.items))
        except Exception:  # noqa: BLE001
            pass
        self.changed.emit()

    def clear(self):
        self.items, self.unread = [], 0
        settings.set(HIST_KEY, "[]")
        self.changed.emit()

    def read_all(self):
        self.unread = 0
        self.changed.emit()


class Toast(QFrame):
    def __init__(self, host, text: str, level: str = "ok", action: str = "", fn=None,
                 ms: int = 6000):
        super().__init__(host.win, objectName="Toast")
        self.host = host
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(10)
        from .icons import icon
        mark = QLabel()
        mark.setPixmap(icon({"ok": "check-circle", "bad": "x-circle", "warn": "alert",
                             "info": "bell"}.get(level, "bell"),
                            {"ok": "#4ADE80", "bad": "#F87171", "warn": "#FBBF24",
                             "info": "#93C5FD"}.get(level, "#93C5FD")).pixmap(20, 20))
        lay.addWidget(mark)
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setMaximumWidth(380)
        lay.addWidget(lab, 1)
        if action and fn:
            b = QPushButton(action)

            def act(_=False, b=b):
                if getattr(self, "_acted", False):
                    return                 # a double-click must not Undo twice
                self._acted = True
                b.setEnabled(False)
                try:
                    fn()
                finally:
                    self.close_now()
            b.clicked.connect(act)
            lay.addWidget(b)
        x = QPushButton("✕")
        x.setToolTip("Dismiss")
        x.setFixedWidth(34)
        x.clicked.connect(self.close_now)
        lay.addWidget(x)
        self.fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fx)
        self.fx.setOpacity(0.0)
        self.anim = QPropertyAnimation(self.fx, b"opacity", self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.timer = QTimer(self, singleShot=True, interval=ms, timeout=self.close_now)
        self.adjustSize()
        self.show()
        self.raise_()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.timer.start()

    def enterEvent(self, e):          # keep it while the mouse is on it
        self.timer.stop()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.timer.start(2500)
        super().leaveEvent(e)

    def close_now(self):
        if getattr(self, "_closing", False):
            return
        self._closing = True
        self.anim.stop()
        self.anim.setStartValue(self.fx.opacity())
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self._gone)
        self.anim.start()

    def _gone(self):
        self.host.remove(self)
        self.deleteLater()


class ToastHost(QObject):
    """Stacks toasts in the window's bottom-right corner and groups quick bursts of
    changes into one message (“5 changes done · Undo”)."""

    def __init__(self, win, center: NotifyCenter):
        super().__init__(win)
        self.win, self.center = win, center
        self.toasts: list[Toast] = []
        self._batch: list[dict] = []
        self._failed: list[str] = []
        self._timer = QTimer(self, singleShot=True, interval=1200, timeout=self._flush)

    def show(self, text: str, level: str = "ok", action: str = "", fn=None, ms: int = 6000,
             remember: bool = True):
        if remember:
            self.center.add(text, "", level)
        if not settings.get("ui/toasts", True):
            return None
        t = Toast(self, text, level, action, fn, ms)
        self.toasts.append(t)
        while len(self.toasts) > 4:
            self.toasts[0].close_now()
            self.toasts.pop(0)
        self.place()
        return t

    def remove(self, t):
        if t in self.toasts:
            self.toasts.remove(t)
        self.place()

    def place(self):
        try:
            sb = self.win.statusBar().height() if self.win.statusBar() else 0
        except Exception:  # noqa: BLE001
            sb = 0
        y = self.win.height() - sb - 16
        for t in reversed(self.toasts):
            t.adjustSize()
            y -= t.height()
            t.move(self.win.width() - t.width() - 22, y)
            t.raise_()
            y -= 10

    def _see_output(self):
        if hasattr(self.win, "toggle_output"):
            self.win.toggle_output(True)
        if hasattr(self.win, "bottom_tabs"):
            self.win.bottom_tabs.setCurrentIndex(0)

    # ---------------------------------------------- after GAMbit runs a change ---
    def change_done(self, entry: dict | None, code: int, display: str):
        if code == 0 and entry:
            self._batch.append(entry)
        elif code not in (0, -2):
            self._failed.append(display)
        self._timer.start()

    def _flush(self):
        batch, failed = self._batch, self._failed
        self._batch, self._failed = [], []
        if failed:
            what = failed[0] if len(failed) == 1 else f"{len(failed)} changes"
            self.show(f"Failed: {what[:110]}", "bad", "See output",
                      self._see_output, ms=9000)
        if not batch:
            return
        if len(batch) == 1:
            text = batch[0].get("what") or batch[0].get("command", "Done")
        else:
            text = f"{len(batch)} changes done"
        undoable = [e for e in batch if e.get("undo")]
        if undoable and hasattr(self.win, "run_undo"):
            def undo():
                for e in reversed(undoable):
                    self.win.run_undo(e)
            self.show(text[:140], "ok", "Undo", undo, ms=10000)
        else:
            self.show(text[:140], "ok")
