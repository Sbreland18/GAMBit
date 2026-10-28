"""Keyboard and screen-reader touches.

- A clear focus outline, but only when you move with the keyboard (Tab / Shift+Tab /
  arrow keys) – clicking with the mouse doesn't leave rings everywhere.
- Icon-only buttons get a spoken name from their tooltip.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget

NAV_KEYS = {int(Qt.Key_Tab), int(Qt.Key_Backtab), int(Qt.Key_Up), int(Qt.Key_Down),
            int(Qt.Key_Left), int(Qt.Key_Right)}
_KEY = int(QEvent.KeyPress)
_PRESS = int(QEvent.MouseButtonPress)
_RELEASE = int(QEvent.MouseButtonRelease)


class InputWatch(QObject):
    """One light watcher for the whole app: it sits on each window (not on every widget),
    so it only sees real key presses and clicks.

    - `last_input`: when you last clicked or pressed a key (used to show loading rows only
      for work you started).
    - Focus outline only after moving with the keyboard."""

    def __init__(self, app):
        super().__init__(app)
        self.last_input = 0.0
        self._kbd = 0.0
        self._marked = None
        self._windows = set()
        app.focusWindowChanged.connect(self._watch)
        app.focusChanged.connect(self._focus)
        for w in app.topLevelWindows():
            self._watch(w)

    def _watch(self, win):
        if win is None or id(win) in self._windows:
            return
        self._windows.add(id(win))
        win.installEventFilter(self)
        win.destroyed.connect(lambda *_a, k=id(win): self._windows.discard(k))

    def eventFilter(self, _obj, e):
        import time
        t = int(e.type())
        if t == _KEY:
            self.last_input = time.time()
            if int(e.key()) in NAV_KEYS:
                self._kbd = self.last_input
        elif t == _RELEASE:
            self.last_input = time.time()
        elif t == _PRESS and self._marked is not None:
            self._set(self._marked, False)
            self._marked = None
        return False

    def _set(self, w, on):
        try:
            if bool(w.property("kbdfocus")) == on:
                return
            w.setProperty("kbdfocus", on)
            w.style().unpolish(w)
            w.style().polish(w)
            w.update()
        except RuntimeError:
            pass

    def _focus(self, old, new):
        import time
        if self._marked is not None and self._marked is not new:
            self._set(self._marked, False)
            self._marked = None
        if new is not None and time.time() - self._kbd < 0.4:
            self._set(new, True)
            self._marked = new


_WATCH = None


def input_watch() -> InputWatch:
    global _WATCH
    if _WATCH is None:
        _WATCH = InputWatch(QApplication.instance())
    return _WATCH


def install_focus_ring():
    return input_watch()


def name_buttons(root) -> int:
    """Give icon-only buttons under `root` an accessible name (from the tooltip)."""
    n = 0
    for b in root.findChildren(QAbstractButton):
        if b.text().strip() or b.accessibleName():
            continue
        tip = (b.toolTip() or "").strip()
        if not tip:
            continue
        b.setAccessibleName(tip.split(" – ")[0].split(" (")[0][:60])
        n += 1
    return n
