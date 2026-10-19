"""Home → District scorecard: this week's numbers, last week's, and a small trend line."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QWidget,
)

from ..widgets import Worker, button


class Sparkline(QWidget):
    def __init__(self, series, good=None):
        super().__init__()
        self.series = series
        self.good = good
        self.setMinimumSize(120, 26)

    def paintEvent(self, _e):
        vals = [(i, v) for i, v in enumerate(self.series) if isinstance(v, (int, float))]
        if len(vals) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width() - 8, self.height() - 8
        lo = min(v for _i, v in vals)
        hi = max(v for _i, v in vals)
        span = (hi - lo) or 1
        n = max(1, len(self.series) - 1)
        pts = [QPointF(4 + w * i / n, 4 + h - h * (v - lo) / span) for i, v in vals]
        col = self.palette().color(self.foregroundRole())
        col.setAlpha(150)
        p.setPen(QPen(col, 2))
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)
        end = QColor("#1a7f37") if self.good is True else QColor("#cf222e") \
            if self.good is False else col
        p.setPen(Qt.NoPen)
        p.setBrush(end)
        p.drawEllipse(pts[-1], 3.5, 3.5)
        p.end()


def scorecard_box(page):
    from ... import scorecard
    box, form = page.group("District scorecard (week by week)")
    table = QTableWidget(0, 5)
    table.setHorizontalHeaderLabels(["", "This week", "Last week", "Change", "Last 12 weeks"])
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.NoSelection)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    table.setColumnWidth(4, 150)
    table.setMinimumHeight(120)
    empty = QLabel("No weekly numbers yet. Save this week's now, or turn on the Monday "
                   "snapshot – the school reports and the nightly mismatch fix add to it too.",
                   objectName="Muted", wordWrap=True)
    status = QLabel("", objectName="Muted")
    alert = QLabel("", wordWrap=True)
    alert.setStyleSheet("color:#b42318;")

    def fill():
        try:
            found = scorecard.trend_alerts()
        except Exception:  # noqa: BLE001
            found = []
        alert.setVisible(bool(found))
        alert.setText("⚠ Moved sharply this week: " + "; ".join(
            f"{f['Measure']} {f['This week']:,} (usually about {f['Usual']:,})"
            for f in found))
        rows = scorecard.trend_rows()
        table.setRowCount(0)
        empty.setVisible(not rows)
        table.setVisible(bool(rows))
        for r in rows:
            i = table.rowCount()
            table.insertRow(i)
            ch = r["Change"]
            vals = [r["Metric"], "" if r["Now"] is None else f"{r['Now']:,}",
                    "" if r["Last week"] is None else f"{r['Last week']:,}",
                    "" if ch is None else ("same" if ch == 0 else
                                           f"{'▲' if ch > 0 else '▼'} {abs(ch):,}")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 3 and r["good"] is not None:
                    it.setForeground(QColor("#1a7f37" if r["good"] else "#cf222e"))
                table.setItem(i, c, it)
            table.setCellWidget(i, 4, Sparkline(r["series"], r["good"]))
            table.setRowHeight(i, 30)
        table.setFixedHeight(min(40 + 30 * len(rows), 360))

    def save_now():
        status.setText("Gathering this week's numbers (a few minutes for big districts)…")
        Worker(scorecard.snapshot, lambda _m: None, users=page.directory.users or None,
               on_done=lambda _w: (status.setText("Saved."), fill()),
               on_error=lambda e: (status.setText(""), page.info(str(e))))

    def schedule():
        from ... import tasks_health
        from ...settings import settings
        settings.set("scorecard/scheduled", True)
        try:
            tasks_health.create(dict(scorecard.TASK))
            page.info("The scorecard will be saved every Monday at 6:20 AM.")
        except Exception as exc:  # noqa: BLE001
            page.info(f"Saved, but the task couldn't be created here:\n{exc}")
    form.addRow(alert)
    form.addRow(empty)
    form.addRow(table)
    def leader():
        from .round11_pages import LeaderSheetDialog
        LeaderSheetDialog(page).exec()
    form.addRow(page.row(button("Save this week's numbers now", slot=save_now),
                         button("Every Monday…", slot=schedule),
                         button("Leadership dashboard sheet…", slot=leader), status))
    fill()
    box.refresh_scorecard = fill
    return box
