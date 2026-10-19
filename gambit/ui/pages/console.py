from __future__ import annotations

import csv

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QLabel, QLineEdit, QSpinBox,
)

from ...gam_runner import split_command
from ...settings import settings
from ..widgets import Page, ResultsTable, button

EXAMPLES = [
    ("Pick an example…", ""),
    ("Show GAM version", "gam version"),
    ("Info about a user", "gam info user someone@yourschool.org"),
    ("List org units", "gam print orgs"),
    ("List admins", "gam print admins"),
    ("Users in an OU", "gam print users query \"orgUnitPath='/Staff'\""),
    ("Licenses", "gam print licenses"),
    ("Shared drives", "gam print shareddrives"),
    ("Chromebooks not synced in 90 days",
     "gam print cros querytime1 -90d query \"sync:..#querytime1#\""),
]

BULK_TEMPLATES = [
    ("Pick a template…", ""),
    ("Create users (email, first, last, password, ou)",
     "create user ~email firstname ~first lastname ~last password ~password ou ~ou changepassword on"),
    ("Reset passwords (email, password)",
     "update user ~email password ~password changepassword on"),
    ("Suspend users (email)", "update user ~email suspended on"),
    ("Move users to OU (email, ou)", "update user ~email ou ~ou"),
    ("Add to groups (group, email)", "update group ~group add member user ~email"),
    ("Move Chromebooks (serial, ou)", "cros_sn ~serial update ou ~ou"),
    ("Set Chromebook asset IDs (serial, asset)", "cros_sn ~serial update assetid ~asset"),
]


class ConsolePage(Page):
    title = "Command Console"
    subtitle = ("Type any GAM command. Output appears in the log below. "
                "Commands that start with 'print' can show results as a table.")

    def build(self):
        box, form = self.group("Command")
        self.examples = QComboBox()
        for label, _ in EXAMPLES:
            self.examples.addItem(label)
        self.examples.currentIndexChanged.connect(
            lambda i: EXAMPLES[i][1] and self.cmd.setText(EXAMPLES[i][1]))
        self.cmd = QLineEdit(placeholderText="gam print users")
        self.cmd.returnPressed.connect(self.execute)
        self.cmd.installEventFilter(self)
        self.as_table = QCheckBox("Show 'print' output as a table")
        self.as_table.setChecked(True)
        form.addRow("Examples", self.examples)
        form.addRow("gam", self.row(self.cmd, button("Run", "primary", self.execute),
                                    button("Explain", slot=lambda: self.app.explain_command(
                                        self.cmd.text())),
                                    button("Stop", "danger", self.runner.stop), stretch=False))
        form.addRow("", self.as_table)
        self.body.addWidget(box)
        self.results = ResultsTable()
        self.body.addWidget(self.results, 1)
        self.history: list[str] = []
        self.hpos = 0

    def eventFilter(self, obj, event):
        if obj is self.cmd and event.type() == event.Type.KeyPress and self.history:
            if event.key() == Qt.Key_Up:
                self.hpos = max(0, self.hpos - 1)
                self.cmd.setText(self.history[self.hpos])
                return True
            if event.key() == Qt.Key_Down:
                self.hpos = min(len(self.history), self.hpos + 1)
                self.cmd.setText(self.history[self.hpos] if self.hpos < len(self.history) else "")
                return True
        return super().eventFilter(obj, event)

    def execute(self):
        text = self.cmd.text().strip()
        if not text:
            return
        try:
            args = split_command(text)
        except ValueError as exc:
            self.info(f"Could not read that command: {exc}")
            return
        if not args:
            return
        if not self.history or self.history[-1] != text:
            self.history.append(text)
        self.hpos = len(self.history)
        table = self.as_table.isChecked() and args[0].lower() == "print"
        if table:
            self.run(args, lambda c, out, _e: self.results.load_csv(out) if c == 0 else None,
                     quiet=True)
        else:
            self.run(args)


class BulkPage(Page):
    title = "Bulk (CSV)"
    subtitle = ("Run one GAM command for every row of a spreadsheet. Use ~column "
                "to insert a value from that column, e.g. update user ~email suspended on")

    def build(self):
        box, form = self.group("1. Choose a CSV file")
        self.path = QLineEdit(placeholderText="C:\\path\\to\\file.csv")
        self.path.setReadOnly(True)
        form.addRow("File", self.row(self.path, button("Browse…", slot=self.browse),
                                     stretch=False))
        self.cols = QLabel("", objectName="Muted")
        self.cols.setWordWrap(True)
        form.addRow("Columns", self.cols)
        self.body.addWidget(box)

        box, form = self.group("2. Command to run for each row")
        self.template_pick = QComboBox()
        for label, _ in BULK_TEMPLATES:
            self.template_pick.addItem(label)
        self.template_pick.currentIndexChanged.connect(
            lambda i: BULK_TEMPLATES[i][1] and self.template.setText(BULK_TEMPLATES[i][1]))
        self.template = QLineEdit(placeholderText="update user ~email suspended on")
        self.template.textChanged.connect(self.update_preview)
        self.preview = QLabel("", objectName="Muted")
        self.preview.setWordWrap(True)
        self.preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow("Templates", self.template_pick)
        form.addRow("gam", self.template)
        form.addRow("First row", self.preview)
        self.threads = QSpinBox()
        self.threads.setRange(1, 50)
        self.threads.setValue(int(settings.get("bulk/threads", 10) or 10))
        self.threads.setToolTip("How many rows GAM works on at the same time. 10–20 is a good "
                                "speed for big jobs; lower it if Google says “quota exceeded”.")
        self.threads.valueChanged.connect(lambda v: settings.set("bulk/threads", v))
        form.addRow("At the same time", self.row(self.threads, QLabel("rows (GAM's default is 5)",
                                                                      objectName="Muted")))
        form.addRow("", self.row(button("Try the first 3 rows", slot=lambda: self.execute(3)),
                                 button("Run for all rows", "primary", self.execute),
                                 button("Stop", "danger", self.runner.stop)))
        self.body.addWidget(box)

        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self._headers: list[str] = []
        self._first: list[str] = []

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose CSV", "", "CSV files (*.csv)")
        if path:
            self.load(path)

    def load(self, path: str):
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                rows = [r for r in csv.reader(fh) if r]
        except Exception as exc:  # noqa: BLE001
            self.info(f"Could not open that file:\n{exc}")
            return
        if not rows:
            self.info("That file is empty.")
            return
        self.path.setText(path)
        self._headers, self._first = rows[0], (rows[1] if len(rows) > 1 else [])
        self.cols.setText(", ".join(f"~{h}" for h in self._headers)
                          + f"   ({len(rows) - 1} rows)")
        self.table.set_rows(rows[0], rows[1:])
        self.update_preview()

    def update_preview(self):
        text = self.template.text()
        if not self._headers or not text:
            self.preview.setText("")
            return
        sample = text
        for h, v in sorted(zip(self._headers, self._first), key=lambda x: -len(x[0])):
            sample = sample.replace(f"~{h}", v)
        missing = [w for w in text.split() if w.startswith("~")
                   and w[1:] not in self._headers]
        note = f"   ⚠ Unknown column: {', '.join(missing)}" if missing else ""
        self.preview.setText(f"gam {sample}{note}")

    def execute(self, first: int = 0):
        if not isinstance(first, int) or isinstance(first, bool):
            first = 0
        if not self.path.text():
            self.info("Choose a CSV file first.")
            return
        try:
            cmd = split_command(self.template.text())
        except ValueError as exc:
            self.info(f"Could not read the command: {exc}")
            return
        if not cmd:
            self.info("Enter the command to run for each row.")
            return
        rows = self.table.row_count()
        from ...tools.more_tools import threaded
        if first:
            if self.confirm(f"Run this command for the first {first} row(s) only?\n\n"
                            f"gam {self.template.text()}"):
                self.run(["csv", self.path.text(), "maxrows", str(first), "gam", *cmd])
            return
        if self.confirm(f"Run this command for all {rows} rows, {self.threads.value()} at a "
                        f"time?\n\ngam {self.template.text()}"):
            self.run(threaded(["csv", self.path.text(), "gam", *cmd], self.threads.value()))
