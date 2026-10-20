"""Home → Background jobs: what ran since you were last here, what failed, what didn't run."""

from __future__ import annotations

import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ..settings import settings
from .widgets import button

GREEN, RED, AMBER, GRAY = "#1a7f37", "#cf222e", "#9a6700", "#57606a"


def since_last_visit(now: datetime.datetime | None = None) -> datetime.datetime:
    """The earlier of: when GAMbit was last opened, and 24 hours ago (so a weekend or a
    day off still shows everything since you left)."""
    now = now or datetime.datetime.now()
    try:
        prev = datetime.datetime.fromisoformat(settings.get("home/last_open", "") or "")
    except ValueError:
        prev = now
    return min(prev, now - datetime.timedelta(hours=24))


def _nice(iso: str) -> str:
    try:
        t = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return iso
    today = datetime.date.today()
    day = ("Today" if t.date() == today else "Yesterday" if t.date() == today -
           datetime.timedelta(days=1) else t.strftime("%a %b %d"))
    return f"{day} {t.strftime('%I:%M %p').lstrip('0')}"


class JobsBox(QGroupBox):
    def __init__(self, page):
        super().__init__("Background jobs")
        self.page = page
        self.since = since_last_visit()
        self.days = 0                     # 0 = since last visit, else the last N days
        v = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        v.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "Job", "When", "What happened"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        for c, w in ((0, 34), (1, 280), (2, 150)):
            self.table.setColumnWidth(c, w)
        self.table.setMaximumHeight(230)
        self.table.doubleClicked.connect(lambda *_: self._open("Background tasks"))
        v.addWidget(self.table)
        row = QHBoxLayout()
        self.more = button("Last 7 days", slot=self._toggle_range)
        row.addWidget(self.more)
        row.addWidget(button("Refresh", slot=self.refresh))
        row.addStretch(1)
        row.addWidget(button("Open Schedules", slot=lambda: self._open("Schedules")))
        row.addWidget(button("Logs (Background tasks)",
                             slot=lambda: self._open("Background tasks")))
        v.addLayout(row)
        self.refresh()

    def _open(self, page: str):
        app = self.page.app
        if page in getattr(app, "pages", {}):
            app.go(page)

    def _toggle_range(self):
        self.days = 0 if self.days else 7
        self.more.setText("Since my last visit" if self.days else "Last 7 days")
        self.refresh()

    def refresh(self):
        from .. import tasks_health
        since = datetime.datetime.now() - datetime.timedelta(days=self.days) if self.days \
            else self.since
        try:
            runs = tasks_health.runs_since(since)
            missed = tasks_health.missed_jobs(since)
        except Exception:  # noqa: BLE001
            runs, missed = [], []
        rows = []
        for m in missed:
            rows.append(("⚠", AMBER, m["name"], _nice(m["due"]),
                         "Didn't run – was the PC off or signed out? See Schedules.", 0))
        for r in runs:
            if r.get("skipped"):
                icon, col, what = "–", GRAY, "Skipped while GAMbit was updating"
            elif r.get("ok"):
                icon, col, what = "✔", GREEN, r.get("summary") or "Finished"
            else:
                icon, col = "✖", RED
                what = r.get("summary") or f"Failed (exit code {r.get('code')})"
            rows.append((icon, col, tasks_health.label_for(r["key"]), _nice(r["ended"]),
                         what, 1 if r.get("ok") or r.get("skipped") else -1))
        rows.sort(key=lambda x: x[5])          # failures first, then didn't-run, then OK
        self.table.setRowCount(0)
        for icon, col, name, when, what, _k in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            for c, val in enumerate((icon, name, when, what)):
                it = QTableWidgetItem(val)
                it.setToolTip(val)
                if c == 0:
                    it.setForeground(QColor(col))
                    it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, c, it)
        ok = sum(1 for r in runs if r.get("ok"))
        bad = sum(1 for r in runs if not r.get("ok") and not r.get("skipped"))
        when = (f"the last {self.days} days" if self.days else
                f"you were last here ({_nice(since.isoformat(timespec='minutes'))})")
        if not rows:
            self.summary.setText(f"No background jobs have run since {when}. "
                                 "Set some up on Automation → Schedules.")
            self.table.hide()
            return
        self.table.show()
        parts = [f"<span style='color:{GREEN}'>✔ {ok} succeeded</span>"]
        if bad:
            parts.append(f"<span style='color:{RED}'><b>✖ {bad} failed</b></span>")
        if missed:
            parts.append(f"<span style='color:{AMBER}'><b>⚠ {len(missed)} didn't run"
                         "</b></span>")
        self.summary.setText(f"Since {when}: " + " · ".join(parts) +
                             ". Double-click a row for its log.")
