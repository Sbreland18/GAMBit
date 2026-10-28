"""Loading placeholders and friendly empty states for result tables.

- While a list you asked for is loading, the table shows grey shimmering rows (or, if it
  already has rows, a thin moving line along the top) instead of sitting blank.
- An empty table says why: nothing loaded yet, nothing matched, or nothing matches the
  filter (with a Clear filter button).

Loading is noticed automatically: a GAM read command (print/show/info/report) or a
background job that starts within a moment of a click or key press shows the placeholder
on the tables you can see, until rows arrive or the work ends.
"""

from __future__ import annotations

import time
import weakref

from PySide6.QtCore import QEvent, QObject, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

READ_WORDS = (" print ", " show ", " info ", " report", " check ")


class _Hub(QObject):
    def __init__(self):
        super().__init__()
        self.tables: "weakref.WeakSet" = weakref.WeakSet()
        self.last_input = 0.0
        self.active = 0
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, _o, e):
        if e.type() in (QEvent.MouseButtonRelease, QEvent.KeyPress):
            self.last_input = time.time()
        return False

    def user_started(self) -> bool:
        return time.time() - self.last_input < 1.2

    def begin(self, cmd: str | None = None):
        if cmd is not None and not any(w in f" {cmd} " for w in READ_WORDS):
            return False
        if not self.user_started():
            return False
        self.active += 1
        for t in list(self.tables):
            try:
                if t.isVisible():
                    t.states.loading(True)
            except RuntimeError:
                continue
        return True

    def end(self):
        self.active = max(0, self.active - 1)
        if self.active:
            return
        for t in list(self.tables):
            try:
                QTimer.singleShot(200, lambda t=t: _safe_stop(t))
            except RuntimeError:
                continue


def _safe_stop(t):
    try:
        if hub().active == 0:
            t.states.loading(False)
    except RuntimeError:
        pass


_HUB = None


def hub() -> _Hub:
    global _HUB
    if _HUB is None:
        _HUB = _Hub()
    return _HUB


class TableStates(QWidget):
    """Lives over a ResultsTable's grid (below the header)."""

    def __init__(self, table):
        super().__init__(table.table.viewport())
        self.rt = table
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.mode = ""                 # "", "loading", "bar", "empty"
        self.phase = 0.0
        self.anim = QTimer(self, interval=40, timeout=self._tick)
        self.delay = QTimer(self, singleShot=True, interval=250, timeout=self._show_loading)
        self.safety = QTimer(self, singleShot=True, interval=120000,
                             timeout=lambda: self.loading(False))
        self.loaded_once = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(6)
        lay.addStretch(1)
        self.icon = QLabel(alignment=Qt.AlignCenter)
        self.title = QLabel(alignment=Qt.AlignCenter, objectName="EmptyTitle")
        self.hint = QLabel(alignment=Qt.AlignCenter, objectName="EmptyHint")
        self.hint.setWordWrap(True)
        self.clear_btn = QPushButton("Clear filter")
        self.clear_btn.clicked.connect(lambda: self.rt.filter.clear())
        for w in (self.icon, self.title, self.hint):
            w.setStyleSheet("background:transparent;")
            lay.addWidget(w)
        lay.addWidget(self.clear_btn, 0, Qt.AlignCenter)
        lay.addStretch(1)
        self.hide()
        self.rt.table.viewport().installEventFilter(self)

    # ------------------------------------------------------------ states ---
    def loading(self, on: bool):
        if on:
            if self.mode in ("loading", "bar") or self.delay.isActive():
                return
            self.delay.start()
            self.safety.start()
        else:
            self.delay.stop()
            self.safety.stop()
            if self.mode in ("loading", "bar"):
                self.mode = ""
                self.anim.stop()
            self.refresh()

    def _show_loading(self):
        self.mode = "bar" if self.rt.model.rowCount() else "loading"
        for w in (self.icon, self.title, self.hint, self.clear_btn):
            w.hide()
        self.anim.start()
        self._fit()
        self.show()
        self.raise_()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self.mode == "bar")

    def rows_arrived(self):
        self.loaded_once = True
        self.loading(False)

    def refresh(self):
        """Show the right empty message, or nothing when there are rows."""
        if self.mode in ("loading", "bar"):
            return
        rt = self.rt
        shown = rt.proxy.rowCount()
        if shown:
            self.mode = ""
            self.hide()
            return
        from .icons import icon
        from .theme import tokens
        t = tokens()
        has_rows = rt.model.rowCount() > 0
        if has_rows and rt.filter.text().strip():
            ic, title, hint = ("search", f"Nothing matches “{rt.filter.text().strip()}”",
                               "Try fewer letters, or clear the filter to see every row.")
        elif self.loaded_once or rt.model.columnCount():
            ic, title, hint = ("inbox", rt.empty_text[0] if rt.empty_text else "No results",
                               rt.empty_text[1] if rt.empty_text else
                               "Nothing matched. Try a wider search, another org unit or "
                               "different options above.")
        else:
            ic, title, hint = ("table", rt.start_text[0], rt.start_text[1])
        self.mode = "empty"
        small = self.height() < 130
        self.icon.setPixmap(icon(ic, t["faint"], 30).pixmap(30, 30))
        self.icon.setVisible(not small)
        self.title.setText(title)
        self.title.show()
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint) and self.height() >= 90)
        self.clear_btn.setVisible(has_rows and bool(rt.filter.text().strip()))
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not self.clear_btn.isVisible())
        self.anim.stop()
        self._fit()
        self.show()
        self.raise_()
        self.update()

    # ---------------------------------------------------------- drawing ---
    def _fit(self):
        vp = self.rt.table.viewport()
        self.setGeometry(0, 0, vp.width(), vp.height() if self.mode != "bar" else 4)

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Resize and self.isVisible():
            self._fit()
            if self.mode == "empty":
                QTimer.singleShot(0, self.refresh)
        return False

    def _tick(self):
        self.phase = (self.phase + 0.025) % 1.4
        self.update()

    def paintEvent(self, _e):
        if self.mode not in ("loading", "bar"):
            return
        from .theme import is_dark, tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = QColor("#1F2835" if is_dark() else "#EEF1F5")
        shine = QColor("#2B3646" if is_dark() else "#F8FAFC")
        w = self.width()
        x = (self.phase - 0.2) * w
        if self.mode == "bar":
            p.fillRect(self.rect(), QColor(tokens()["surface2"]))
            p.fillRect(QRectF(x, 0, w * 0.25, 4), QColor(tokens()["accent"]))
            p.end()
            return
        p.fillRect(self.rect(), QColor(tokens()["surface"]))
        g = QLinearGradient(x - w * 0.2, 0, x + w * 0.2, 0)
        g.setColorAt(0, base)
        g.setColorAt(0.5, shine)
        g.setColorAt(1, base)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        row_h = 34
        widths = (0.22, 0.16, 0.10, 0.26, 0.14)
        y = 12
        n = 0
        while y + 14 < self.height() and n < 14:
            xx = 12.0
            for k, f in enumerate(widths):
                ww = (w - 24) * f * (0.75 if (n + k) % 3 == 0 else 1.0)
                p.drawRoundedRect(QRectF(xx, y, ww, 12), 6, 6)
                xx += (w - 24) * f + 16
            y += row_h
            n += 1
        p.end()
