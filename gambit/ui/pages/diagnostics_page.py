"""Diagnostics page: is GAM allowed to do everything GAMbit needs?"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QHeaderView, QLabel, QProgressBar, QTableWidget,
    QTableWidgetItem, QTextBrowser,
)

from ... import diagnostics, google_io
from ...settings import settings
from ..widgets import Page, Worker, button

ICON = {"ok": ("✔ Working", "#137333"), "warn": ("⚠ Check", "#9a6700"),
        "fail": ("✖ Not working", "#b42318"), "skip": ("– Skipped", "#57606a")}


class DiagnosticsPage(Page):
    title = "Diagnostics"
    subtitle = ("Checks that GAM can reach every part of Google Workspace GAMbit uses – "
                "Gmail, sending email, Drive, Sheets, Classroom, Chromebooks, Vault and more – "
                "and says how to fix anything that's missing. Every check is read-only.")

    def build(self):
        self.summary = QLabel("Click Run checks. It takes about a minute.")
        self.summary.setWordWrap(True)
        last = settings.get("diagnostics/last", "")
        if last:
            self.summary.setText(f"Last run {last.replace('T', ' ')}. Click Run checks to "
                                 "check again.")
        self.run_btn = button("Run checks", "primary", self.run_checks)
        self.copy_btn = button("Copy report", slot=self.copy)
        self.body.addLayout(self.row(self.run_btn, self.copy_btn,
                                     button("Report a problem…", slot=self.problem),
                                     button("GAMbit's Google key…", slot=self.google_key)))
        self.body.addWidget(self.summary)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        self.body.addWidget(self.bar)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Area", "What it's for", "Status", "Details"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for c, w in ((0, 110), (1, 340), (2, 120)):
            self.table.setColumnWidth(c, w)
        self.table.itemSelectionChanged.connect(self._show)
        self.body.addWidget(self.table, 2)
        self.fix = QTextBrowser()
        self.fix.setOpenExternalLinks(True)
        self.fix.setMaximumHeight(150)
        self.fix.setHtml("<p style='color:#57606a'>Select a row to see how to fix it.</p>")
        self.body.addWidget(self.fix)
        self.results: list[diagnostics.Result] = []

    def run_checks(self):
        self.run_btn.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setValue(0)
        self.summary.setText("Checking…")

        def progress(i, n):
            self.bar.setMaximum(n)
            self.bar.setValue(i)

        def done(results):
            self.run_btn.setEnabled(True)
            self.bar.setVisible(False)
            self.results = results
            self._fill()

        def failed(e):
            self.run_btn.setEnabled(True)
            self.bar.setVisible(False)
            self.summary.setText(f"Couldn't run the checks: {e}")
        Worker(diagnostics.run_all, google_io.admin_email(), on_done=done, on_error=failed,
               on_progress=progress, use_progress=True)

    def _fill(self):
        self.table.setRowCount(0)
        counts = {"ok": 0, "warn": 0, "fail": 0, "skip": 0}
        for r in self.results:
            counts[r.status] += 1
            row = self.table.rowCount()
            self.table.insertRow(row)
            label, color = ICON[r.status]
            for c, v in enumerate((r.area, r.what, label, r.detail)):
                it = QTableWidgetItem(v)
                it.setToolTip(v)
                if c == 2:
                    it.setForeground(QColor(color))
                if c == 0:
                    it.setData(Qt.UserRole, r)
                self.table.setItem(row, c, it)
        bad = counts["fail"] + counts["warn"]
        self.summary.setText(
            f"<b>{counts['ok']}</b> working · <b>{counts['warn']}</b> to check · "
            f"<b>{counts['fail']}</b> not working · {counts['skip']} skipped" +
            ("" if bad else " – everything GAMbit needs is set up. ✔"))
        first_bad = next((i for i, r in enumerate(self.results)
                          if r.status in ("fail", "warn")), None)
        if first_bad is not None:
            self.table.selectRow(first_bad)

    def _show(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            return
        r: diagnostics.Result = self.table.item(rows[0], 0).data(Qt.UserRole)
        html = f"<b>{r.what}</b> – {r.detail}"
        if r.fix and r.status in ("fail", "warn"):
            html += f"<p><b>How to fix:</b> {r.fix}</p>"
        elif r.status == "ok":
            html += "<p style='color:#137333'>Nothing to do.</p>"
        if r.command:
            html += f"<p style='color:#57606a'>Checked with <code>{r.command}</code></p>"
        self.fix.setHtml(html)

    def google_key(self):
        from .round13_tabs import GoogleKeyDialog
        GoogleKeyDialog(self).exec()

    def problem(self):
        from ... import support
        text = diagnostics.report_text(self.results) if self.results else ""
        support.ask_and_save(self, output_text=(text + "\n\n" + self.app.log.toPlainText()))

    def copy(self):
        if self.results:
            QApplication.clipboard().setText(diagnostics.report_text(self.results))
            self.info("Copied the report – paste it into an email or a support ticket.")
