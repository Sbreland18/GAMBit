"""Live test checklist page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QInputDialog, QLabel, QTableWidget, QTableWidgetItem,
)

from ... import livetest
from ..widgets import Page, Worker, button

LOOK = {"passed": ("✔ Passed", "#137333"), "failed": ("✖ Failed", "#b42318"),
        "check": ("? Check it", "#9a6700"), "skipped": ("– Skipped", "#57606a"),
        "running": ("◐ Running…", "#1a73e8"), "": ("○ Not run", "#57606a")}


class LiveTestPage(Page):
    title = "Live test"
    subtitle = ("Try every part of GAMbit for real – safely, on your test account and test org "
                "unit – and keep a record of what works. Send the results with a problem report "
                "if something doesn't.")

    def build(self):
        self.ctx_lbl = QLabel("")
        self.ctx_lbl.setWordWrap(True)
        self.body.addWidget(self.ctx_lbl)
        self.body.addLayout(self.row(
            button("Run all automatic checks", "primary", self.run_all),
            button("Run selected", slot=self.run_selected),
            button("Mark selected passed", slot=lambda: self.mark("passed")),
            button("Mark selected failed…", slot=lambda: self.mark("failed")),
            button("Clear results", slot=self.clear),
            button("Save as a problem report…", slot=self.report)))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Area", "Check", "Result", "Details"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for c, w in ((0, 120), (1, 300), (2, 110)):
            self.table.setColumnWidth(c, w)
        self.table.itemSelectionChanged.connect(self._show_how)
        self.body.addWidget(self.table, 1)
        self.how = QLabel("")
        self.how.setWordWrap(True)
        self.how.setStyleSheet("padding:8px;background:#f6f8fa;border-radius:6px;")
        self.body.addWidget(self.how)
        self._queue = []
        self.fill()

    def on_show(self):
        self.fill()

    def fill(self):
        ctx = livetest.context()
        self.ctx_lbl.setText(
            f"Test account: <b>{ctx['user'] or 'not set'}</b> · test org unit: "
            f"<b>{ctx['ou']}</b> · GAMbit Google account: <b>{ctx['admin'] or 'not set'}</b>"
            + ("" if "@" in ctx["user"] else " – set them in Settings & Updates → Testing first."))
        res = livetest.load_results()
        self.table.setRowCount(0)
        for it in livetest.ITEMS:
            r = self.table.rowCount()
            self.table.insertRow(r)
            x = res.get(it.key, {})
            label, color = LOOK.get(x.get("status", ""), LOOK[""])
            vals = [it.area, ("✋ " if it.manual else "") + it.title, label,
                    x.get("detail", "") + (f"  ({x['when'].replace('T', ' ')})"
                                           if x.get("when") else "")]
            for c, v in enumerate(vals):
                cell = QTableWidgetItem(v)
                cell.setToolTip(v)
                if c == 2:
                    cell.setForeground(QColor(color))
                if c == 0:
                    cell.setData(Qt.UserRole, it.key)
                self.table.setItem(r, c, cell)

    def _items(self, selected=False):
        if not selected:
            return [it for it in livetest.ITEMS if not it.manual]
        keys = {self.table.item(i.row(), 0).data(Qt.UserRole)
                for i in self.table.selectedIndexes()}
        return [it for it in livetest.ITEMS if it.key in keys]

    def _show_how(self):
        its = self._items(True)
        if its:
            it = its[0]
            self.how.setText(f"<b>{it.title}</b> – {it.how}" +
                             ("<br><i>Manual check: do it, then mark it passed or failed.</i>"
                              if it.manual else ""))

    def run_all(self):
        self._start(self._items())

    def run_selected(self):
        its = [it for it in self._items(True) if not it.manual]
        if not its:
            self.info("Select automatic checks (manual ones are marked ✋).")
            return
        self._start(its)

    def _start(self, items):
        if not self.confirm(f"Run {len(items)} check(s)? Some change the test account (and "
                            "a temporary group / org unit they remove again)."):
            return
        self._queue = list(items)
        self._ctx = livetest.context()
        self._next()

    def _next(self):
        if not self._queue:
            self.fill()
            return
        it = self._queue.pop(0)
        livetest.save_result(it.key, "running", "")
        self.fill()

        def done(res):
            livetest.save_result(it.key, *res)
            self._next()

        def failed(e):
            livetest.save_result(it.key, "failed", str(e))
            self._next()
        Worker(livetest.run_item, it, self._ctx, on_done=done, on_error=failed)

    def mark(self, status):
        its = self._items(True)
        if not its:
            self.info("Select a check first.")
            return
        note = ""
        if status == "failed":
            note, ok = QInputDialog.getText(self, "What went wrong?", "Short note:")
            if not ok:
                return
        for it in its:
            livetest.save_result(it.key, status, note or "Checked by hand.")
        self.fill()

    def clear(self):
        if self.confirm("Clear all results?"):
            from ...settings import settings
            settings.set("livetest/results", "{}")
            self.fill()

    def report(self):
        from ... import support
        support.ask_and_save(self, "Live test results:\n\n" + livetest.report_text(),
                             self.app.log.toPlainText())
