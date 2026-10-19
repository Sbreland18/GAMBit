"""Security & compliance reports page."""

from __future__ import annotations

import csv
import io

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QSpinBox, QSplitter, QTimeEdit, QVBoxLayout, QWidget,
)

from ... import compliance, scheduler
from ...gam_runner import display_command
from ...settings import IS_WINDOWS, settings
from ..pickers import OUField
from ..widgets import Page, ResultsTable, button


class CompliancePage(Page):
    title = "Security reports"
    subtitle = ("One-click reports for audits, student-privacy agreements and storage "
                "clean-up – each can be emailed every month to the people who need it.")

    def build(self):
        split = QSplitter()
        self.list = QListWidget()
        group = None
        for r in compliance.REPORTS:
            if r.group != group:
                group = r.group
                head = QListWidgetItem(group.upper())
                head.setFlags(Qt.NoItemFlags)
                self.list.addItem(head)
            it = QListWidgetItem("   " + r.title)
            it.setData(Qt.UserRole, r.key)
            self.list.addItem(it)
        self.list.currentItemChanged.connect(self._pick)
        split.addWidget(self.list)

        right = QWidget()
        v = QVBoxLayout(right)
        v.setContentsMargins(8, 0, 0, 0)
        self.r_title = QLabel("", objectName="PageTitle")
        self.r_title.setStyleSheet("font-size:14pt;font-weight:600;")
        self.r_why = QLabel("")
        self.r_why.setWordWrap(True)
        v.addWidget(self.r_title)
        v.addWidget(self.r_why)
        self.scope_lbl = QLabel("")
        self.scope = OUField(self.directory, "/")
        v.addLayout(self.row(self.scope_lbl, self.scope, stretch=False))
        self.cmd = QLabel("", objectName="Muted")
        self.cmd.setWordWrap(True)
        self.cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.cmd)
        self.run_btn = button("Run report", "primary", self.run_report)
        self.count = QLabel("", objectName="Muted")
        v.addLayout(self.row(self.run_btn, button("Email this every month…",
                                                  slot=self.schedule), self.count))
        self.table = ResultsTable()
        v.addWidget(self.table, 1)
        split.addWidget(right)
        split.setSizes([300, 900])
        self.body.addWidget(split, 1)
        self.scope.changed.connect(self._show_cmd)
        self.list.setCurrentRow(1)

    def _report(self) -> compliance.Report:
        it = self.list.currentItem()
        key = it.data(Qt.UserRole) if it else None
        return compliance.BY_KEY.get(key, compliance.REPORTS[0])

    def _pick(self, *_):
        r = self._report()
        self.r_title.setText(r.title)
        self.r_why.setText(r.why + ("  <i>(This one can take a while.)</i>" if r.slow else ""))
        self.scope_lbl.setText(r.scope_label or "")
        self.scope_lbl.setVisible(bool(r.scope_label))
        self.scope.setVisible(bool(r.scope_label))
        self.scope.set_path(settings.get(f"compliance/scope/{r.key}", "") or r.default_scope)
        self.table.set_rows([], [])
        self.count.setText("")
        self._show_cmd()

    def _args(self) -> list[str]:
        r = self._report()
        return r.build(self.scope.path() or "/", self.directory.domain or "yourschool.org")

    def _show_cmd(self, *_):
        self.cmd.setText("Runs: " + display_command(self._args()))

    def run_report(self):
        r = self._report()
        settings.set(f"compliance/scope/{r.key}", self.scope.path())
        self._show_cmd()
        self.run_btn.setEnabled(False)
        self.count.setText("Running…")

        def done(code, out, err):
            self.run_btn.setEnabled(True)
            if code != 0:
                self.count.setText("The report failed – see the Output panel.")
                return
            rows = list(csv.DictReader(io.StringIO(out or "")))
            if r.keep:
                rows = [x for x in rows if r.keep(x)]
            if r.post:
                rows = r.post(rows, self.directory.domain or "")
            heads = list(rows[0].keys()) if rows else []
            self.table.set_rows(heads, [[x.get(h, "") or "" for h in heads] for x in rows])
            self.count.setText(f"{len(rows):,} row(s)" + ("" if rows else " – nothing found ✔"))
        if not self.runner.run(self._args(), done, quiet_stdout=True):
            self.run_btn.setEnabled(True)
            self.count.setText("")

    def schedule(self):
        r = self._report()
        dlg = QDialog(self)
        dlg.setWindowTitle("Email this report every month")
        form = QFormLayout(dlg)
        to = QLineEdit(settings.get(f"compliance/email/{r.key}", "") or
                       settings.get("alerts/email", "") or "")
        to.setPlaceholderText("e.g. principal@yourschool.org, tech@yourschool.org")
        day = QSpinBox()
        day.setRange(1, 28)
        when = QTimeEdit(QTime(6, 45))
        when.setDisplayFormat("h:mm AP")
        only = QCheckBox("Only send when the report finds something")
        only.setChecked(r.key != "admins")
        form.addRow("Send to", to)
        form.addRow("Day of the month", day)
        form.addRow("At", when)
        form.addRow("", only)
        if r.keep:
            note = QLabel("The emailed file lists every suspended account with its license "
                          "column – sort by the license column to see the ones to release.",
                          objectName="Muted")
            note.setWordWrap(True)
            form.addRow("", note)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if not dlg.exec():
            return
        if "@" not in to.text():
            self.info("Type at least one email address.")
            return
        if not IS_WINDOWS:
            self.info("Scheduled emails use Windows Task Scheduler, so they only work on "
                      "Windows.")
            return
        from ... import google_io, alerts
        settings.set(f"compliance/email/{r.key}", to.text().strip())
        name = f"Monthly - {r.title}"
        out = settings.get("schedule/out", "") or scheduler.default_output_dir()
        line = " ".join(f'"{a}"' if " " in a or "'" in a else a for a in self._args())
        try:
            script = scheduler.build_script(
                name, [line], out, to.text().strip(), "rows" if only.isChecked() else "always",
                settings.get("alerts/email", "") or "", google_io.admin_email(),
                alerts.webhook_url())
            scheduler.create_task(name, script, "monthly", when.time().toString("HH:mm"), "",
                                  day.value())
        except Exception as exc:  # noqa: BLE001
            self.info(f"Couldn't schedule it:\n{exc}")
            return
        self.info(f"“{r.title}” will be emailed to {to.text().strip()} on day {day.value()} "
                  "of every month. Manage it on Tools → Scheduled jobs.")
