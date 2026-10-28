"""“2 running” in the top bar while GAM commands are working. Click it for each job's
progress, how long it's been going, and a Stop button – no need to open the Output panel."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QToolButton, QVBoxLayout, QWidget,
)


def _elapsed(sec: float) -> str:
    sec = int(sec)
    return f"{sec}s" if sec < 60 else f"{sec // 60}m {sec % 60:02d}s"


class _Popup(QFrame):
    """A plain pop-up panel (not a menu): it opens without blocking GAMbit, so the job list
    can update every second while it's open."""

    def __init__(self, chip):
        super().__init__(chip.win, Qt.Popup)
        self.chip = chip
        self.setObjectName("JobsPopup")
        self.setAttribute(Qt.WA_StyledBackground, True)

    def hideEvent(self, e):
        self.chip._closed_at = __import__("time").time()
        super().hideEvent(e)


class JobsChip(QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.btn = QToolButton(objectName="JobsChip")
        self.btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn.setProperty("helpdesk_ok", True)
        from .icons import set_icon
        set_icon(self.btn, "activity")
        self.menu = _Popup(self)          # kept as .menu for older callers
        self.box = self.menu
        self.lay = QVBoxLayout(self.menu)
        self.lay.setContentsMargins(14, 12, 14, 12)
        self.lay.setSpacing(10)
        self.btn.clicked.connect(self.toggle)
        self.btn.hide()
        self._rows = {}
        self._closed_at = 0.0
        self.live = QTimer(self, interval=1000, timeout=self._tick)
        self.soon = QTimer(self, singleShot=True, interval=250, timeout=self.refresh)
        r = win.runner
        for sig in (r.job_added, r.job_changed):
            sig.connect(lambda *_: self.soon.start() if not self.soon.isActive() else None)
        r.finished.connect(lambda *_: self.soon.start())

    def toggle(self):
        import time
        if self.menu.isVisible():
            self.menu.hide()
            return
        if time.time() - self._closed_at < 0.25:
            return                    # the click that closed the pop-up also hit the button
        self.fill()
        self.menu.adjustSize()
        pos = self.btn.mapToGlobal(self.btn.rect().bottomRight())
        x = pos.x() - self.menu.width()
        scr = self.btn.screen().availableGeometry() if self.btn.screen() else None
        if scr is not None:
            x = max(scr.left() + 8, x)
        self.menu.move(x, pos.y() + 6)
        self.menu.show()

    def active(self):
        return [j for j in self.win.runner.jobs if j.status in ("running", "queued")]

    def refresh(self):
        jobs = self.active()
        if not jobs:
            self.btn.hide()
            self.live.stop()
            if self.menu.isVisible():
                self.fill()                       # "Nothing is running" …
                QTimer.singleShot(2000, lambda: not self.active() and self.menu.hide())
            return
        running = [j for j in jobs if j.status == "running"]
        queued = len(jobs) - len(running)
        text = f" {len(running)} running" + (f" · {queued} waiting" if queued else "")
        if len(jobs) == 1 and jobs[0].progress[1]:
            d, t = jobs[0].progress
            text = f" {round(100 * d / t)}%  {d:,} of {t:,}"
        self.btn.setText(text)
        self.btn.setToolTip("GAM commands running now – click for progress and Stop")
        self.btn.show()
        if not self.live.isActive():
            self.live.start()
        if self.menu.isVisible():
            if {j.id for j in jobs[:8]} == set(self._rows):
                self._update_rows()
            else:
                self.fill()

    def _update_rows(self):
        for j in self.active()[:8]:
            parts = self._rows.get(j.id)
            if not parts:
                continue
            state, bar = parts
            try:
                state.setText("waiting" if j.status == "queued" else _elapsed(j.elapsed()))
                d, t = j.progress
                if t:
                    bar.setRange(0, t)
                    bar.setValue(d)
            except RuntimeError:
                continue

    def _tick(self):
        self.refresh()

    def fill(self):
        self._rows = {}
        while self.lay.count():
            it = self.lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
            elif it.layout() is not None:
                _clear_layout(it.layout())
        jobs = self.active()
        head = QLabel("Running now" if jobs else "Nothing is running", objectName="SectionTitle")
        self.lay.addWidget(head)
        for j in jobs[:8]:
            self.lay.addWidget(self._row(j))
        if len(jobs) > 8:
            self.lay.addWidget(QLabel(f"…and {len(jobs) - 8} more", objectName="Muted"))
        foot = QHBoxLayout()
        out = QPushButton("Show output")
        out.clicked.connect(lambda: (self.menu.close(), self.win.toggle_output(True)))
        foot.addWidget(out)
        if len(jobs) > 1:
            stop = QPushButton("Stop all")
            stop.setProperty("kind", "danger")
            stop.clicked.connect(self.stop_all)
            foot.addWidget(stop)
        foot.addStretch(1)
        self.lay.addLayout(foot)
        self.menu.setMinimumWidth(460)
        if self.menu.isVisible():
            self.menu.adjustSize()

    def stop_all(self):
        for j in list(self.active()):
            self.win.runner.cancel(j)
        self.menu.close()
        self.soon.start()

    def _row(self, j):
        w = QWidget(objectName="JobRow")
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        top = QHBoxLayout()
        cmd = j.display if len(j.display) < 70 else j.display[:67] + "…"
        lab = QLabel(cmd)
        lab.setToolTip(j.display)
        top.addWidget(lab, 1)
        state = QLabel("waiting" if j.status == "queued" else _elapsed(j.elapsed()),
                       objectName="Muted")
        top.addWidget(state)
        stop = QPushButton("Stop")
        stop.setToolTip("Stop this command")
        stop.clicked.connect(lambda _=False, j=j: (self.win.runner.cancel(j), self.soon.start()))
        top.addWidget(stop)
        v.addLayout(top)
        bar = QProgressBar()
        d, t = j.progress
        if t:
            bar.setRange(0, t)
            bar.setValue(d)
            bar.setFormat(f"{d:,} of {t:,}")
        else:
            bar.setRange(0, 0)                 # busy, no count yet
        bar.setTextVisible(False)
        v.addWidget(bar)
        self._rows[j.id] = (state, bar)
        return w


def _clear_layout(lay):
    while lay.count():
        it = lay.takeAt(0)
        if it.widget() is not None:
            it.widget().hide()
            it.widget().deleteLater()
        elif it.layout() is not None:
            _clear_layout(it.layout())
