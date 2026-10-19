"""Classroom → Guardian report tab (for principals)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox, QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QScrollArea, QSplitter,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from ... import parent_report as pr
from ..pickers import OUField
from ..widgets import ResultsTable, Worker, button


class GuardianReportTab(QScrollArea):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget(objectName="Page")
        lay = QVBoxLayout(inner)
        self.setWidget(inner)
        o = pr.options()
        tip = QLabel("How many students at each school have a parent or guardian connected to "
                     "Google Classroom summaries, are waiting on an invitation, or have nobody "
                     "invited. Schools come from the org unit right under the students' org "
                     "unit. Click a school to see its students.")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.root = OUField(page.directory, "/Students")
        self.root.set_path(o["root"])
        self.go = button("Build the report", "primary", self.build)
        self.status = QLabel("", objectName="Muted")
        lay.addLayout(page.row(QLabel("Students are under"), self.root, self.go, self.status,
                               stretch=False))
        split = QSplitter(Qt.Vertical)
        self.sum_t = ResultsTable()
        self.det_t = ResultsTable()
        split.addWidget(self.sum_t)
        split.addWidget(self.det_t)
        split.setMinimumHeight(420)
        lay.addWidget(split, 1)
        self.sum_t.table.clicked.connect(self._pick)

        box = QGroupBox("Email principals")
        f = QFormLayout(box)
        self.princ = QPlainTextEdit(o["principals"])
        self.princ.setPlaceholderText("Lincoln Elementary = principal.lincoln@yourschool.org\n"
                                      "High School = hs.principal@yourschool.org, "
                                      "hs.office@yourschool.org")
        self.princ.setMaximumHeight(110)
        f.addRow("School = email(s)", self.princ)
        self.dist = QLineEdit(o["district_to"])
        self.dist.setPlaceholderText("optional – gets the all-schools summary")
        f.addRow("District summary to", self.dist)
        f.addRow("", page.row(button("Email them now", slot=self.send_now),
                              button("Email them on the 1st of every month…",
                                     slot=self.monthly)))
        lay.addWidget(box)
        self.detail = []

    def _save(self):
        pr.save_options({"root": self.root.path() or "/Students",
                         "principals": self.princ.toPlainText(),
                         "district_to": self.dist.text().strip()})

    def build(self):
        self._save()
        self.go.setEnabled(False)
        self.status.setText("Reading students and guardians from Google…")

        def done(res):
            self.go.setEnabled(True)
            self.detail, summ = res
            heads = ["School", "Students", "Connected", "Invited (waiting)", "Nobody invited",
                     "% connected"]
            self.sum_t.set_rows(heads, [[str(r[h]) for h in heads] for r in summ])
            self._show_detail(None)
            self.status.setText(f"{len(self.detail):,} students")

        def fail(e):
            self.go.setEnabled(True)
            self.status.setText(f"Couldn't build it: {e}")
        Worker(pr.build, root=self.root.path() or "/Students", on_done=done, on_error=fail)

    def _pick(self, index):
        row = self.sum_t.row_dict(index.row())
        self._show_detail(None if row.get("School") == "District total" else row.get("School"))

    def _show_detail(self, school):
        rows = [r for r in self.detail if school is None or r["School"] == school]
        heads = ["School", "Student", "Email", "Org unit", "Status", "Guardians"]
        self.det_t.set_rows(heads, [[r[h] for h in heads] for r in rows])

    def send_now(self):
        self._save()
        if not pr.parse_principals(self.princ.toPlainText()) and not self.dist.text().strip():
            self.page.info("Add at least one “School = email” line.")
            return
        if not self.page.confirm("Build the report and email each principal their school "
                                 "now?"):
            return
        self.status.setText("Sending…")
        lines = []
        Worker(pr.send, log=lines.append,
               on_done=lambda bad: (self.status.setText("Sent." if not bad else
                                                        f"{bad} email(s) failed."),
                                    self.page.info("\n".join(lines) or "Nothing to send.")),
               on_error=lambda e: self.status.setText(f"Couldn't send: {e}"))

    def monthly(self):
        self._save()
        from ... import tasks_health
        try:
            tasks_health.create(dict(pr.TASK))
        except Exception as exc:  # noqa: BLE001
            self.page.info(f"Saved, but the monthly task couldn't be created here:\n{exc}")
            return
        self.page.info("Principals will get their report on the 1st of every month at "
                       "6:50 AM. See Automation → Background tasks.")
