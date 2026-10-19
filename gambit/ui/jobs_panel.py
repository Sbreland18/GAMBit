"""Jobs panel: every GAM command as a background job you can watch, cancel or re-run."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
    QPlainTextEdit, QProgressBar, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .widgets import button

STATUS = {"queued": "⏳ Waiting", "running": "◐ Running", "done": "✔ Done",
          "failed": "✖ Failed", "cancelled": "■ Cancelled"}


class JobsPanel(QWidget):
    def __init__(self, runner, parent=None):
        super().__init__(parent)
        self.runner = runner
        self.rows: dict[int, int] = {}
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "Command", "Status", "Progress", "Time"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideMiddle)
        for c, w in ((0, 46), (2, 110), (3, 150), (4, 70)):
            self.table.setColumnWidth(c, w)
        self.table.doubleClicked.connect(lambda *_: self.show_output())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        from .widgets import ElideLabel
        self.summary = ElideLabel("No jobs yet", objectName="Muted")
        row.addWidget(self.summary, 1)
        cancel = button("Cancel selected", slot=self.cancel)
        cancel.setProperty("helpdesk_ok", True)
        row.addWidget(cancel)
        row.addWidget(button("Re-run", slot=self.rerun))
        row.addWidget(button("Show output", slot=self.show_output))
        row.addWidget(button("Clear finished", slot=self.clear_finished))
        lay.addLayout(row)
        lay.addWidget(self.table)

        runner.job_added.connect(self.add)
        runner.job_changed.connect(self.update)
        self.timer = QTimer(self, interval=1000, timeout=self._tick)
        self.timer.start()

    def _job(self, row):
        jid = int(self.table.item(row, 0).text())
        return next((j for j in self.runner.jobs if j.id == jid), None)

    def selected_jobs(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [j for j in (self._job(r) for r in rows) if j]

    def add(self, job):
        self.table.insertRow(0)
        self.table.setItem(0, 0, QTableWidgetItem(str(job.id)))
        it = QTableWidgetItem(job.display)
        it.setToolTip(job.display)
        self.table.setItem(0, 1, it)
        self.table.setItem(0, 2, QTableWidgetItem(""))
        bar = QProgressBar()
        bar.setMaximumHeight(16)
        bar.setTextVisible(True)
        self.table.setCellWidget(0, 3, bar)
        self.table.setItem(0, 4, QTableWidgetItem(""))
        self._reindex()
        self.update(job)

    def _reindex(self):
        self.rows = {int(self.table.item(r, 0).text()): r for r in range(self.table.rowCount())}

    def update(self, job):
        r = self.rows.get(job.id)
        if r is None:
            return
        self.table.item(r, 2).setText(STATUS.get(job.status, job.status))
        bar: QProgressBar = self.table.cellWidget(r, 3)
        done, total = job.progress
        if job.status == "running" and total:
            bar.setRange(0, total)
            bar.setValue(done)
            bar.setFormat(f"{done:,} of {total:,}")
        elif job.status == "running":
            bar.setRange(0, 0)          # busy indicator
        elif job.status in ("done", "failed", "cancelled"):
            bar.setRange(0, 1)
            bar.setValue(1 if job.status == "done" else 0)
            bar.setFormat("")
        self.table.item(r, 4).setText(self._fmt(job.elapsed()) if job.started_at else "")
        self._summary()

    def _tick(self):
        for j in self.runner.jobs:
            if j.status == "running":
                r = self.rows.get(j.id)
                if r is not None:
                    self.table.item(r, 4).setText(self._fmt(j.elapsed()))

    @staticmethod
    def _fmt(sec: float) -> str:
        sec = int(sec)
        return f"{sec // 60}:{sec % 60:02d}"

    def _summary(self):
        running = sum(j.status == "running" for j in self.runner.jobs)
        queued = sum(j.status == "queued" for j in self.runner.jobs)
        failed = sum(j.status == "failed" for j in self.runner.jobs)
        parts = []
        if running:
            parts.append(f"{running} running")
        if queued:
            parts.append(f"{queued} waiting")
        if failed:
            parts.append(f"{failed} failed")
        self.summary.setText(", ".join(parts) or "All jobs finished")
        tabs = self.parent()
        while tabs is not None and not hasattr(tabs, "setTabText"):
            tabs = tabs.parent()
        if tabs is not None:
            label = f"Jobs ({running + queued})" if running + queued else "Jobs"
            idx = tabs.indexOf(self) if hasattr(tabs, "indexOf") else -1
            if idx >= 0:
                tabs.setTabText(idx, label)

    def cancel(self):
        for j in self.selected_jobs():
            self.runner.cancel(j)

    def rerun(self):
        for j in self.selected_jobs():
            self.runner.rerun(j)

    def clear_finished(self):
        keep = [j for j in self.runner.jobs if j.status in ("running", "queued")]
        self.runner.jobs = keep
        for r in range(self.table.rowCount() - 1, -1, -1):
            if int(self.table.item(r, 0).text()) not in {j.id for j in keep}:
                self.table.removeRow(r)
        self._reindex()
        self._summary()

    def show_output(self):
        jobs = self.selected_jobs()
        if not jobs:
            return
        j = jobs[0]
        d = QDialog(self)
        d.setWindowTitle(f"Job #{j.id}")
        d.resize(820, 520)
        v = QVBoxLayout(d)
        v.addWidget(QLabel(f"<b>{j.display}</b><br>{STATUS.get(j.status)} · exit code "
                           f"{j.code if j.code is not None else '—'} · "
                           f"{self._fmt(j.elapsed())}"))
        txt = QPlainTextEdit(objectName="Log")
        from .widgets import wrap_log
        wrap_log(txt)
        txt.setReadOnly(True)
        txt.setPlainText("".join(j.stdout) + ("\n--- messages ---\n" + "".join(j.stderr)
                                              if j.stderr else ""))
        v.addWidget(txt, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        d.exec()

