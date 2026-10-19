"""Classroom → Guardian sync tab."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QGroupBox, QLabel, QLineEdit, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from ... import guardians as gd
from ...settings import settings
from ..pickers import OUField
from ..steps import Step, StepList
from ..widgets import ResultsTable, button


class GuardianSyncTab(QScrollArea):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget(objectName="Page")
        lay = QVBoxLayout(inner)
        self.setWidget(inner)
        tip = QLabel("Invite every guardian listed in the SIS to get Classroom summaries, keep "
                     "the list in step, and find students nobody has been invited for. "
                     "ClassLink: use the OneRoster users.csv (or the .zip) – guardians are "
                     "linked to students by agentSourcedIds. Other systems: a CSV with a "
                     "Student email column and one or more Guardian/Parent email columns.")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.src = QLineEdit(settings.get("guardians/src", "") or "")
        self.src.setPlaceholderText("users.csv, oneroster.zip, or guardians.csv")
        from ..widgets import classlink_button
        lay.addLayout(page.row(self.src, button("Browse…", slot=self._browse),
                               classlink_button(self.src, parent=self), stretch=False))
        self.root = OUField(page.directory, "/Students")
        self.root.set_path(settings.get("guardians/root", "") or "/Students")
        lay.addLayout(page.row(QLabel("Students are under"), self.root, stretch=False))
        self.remove = QCheckBox("Also remove guardians and invitations the SIS no longer lists")
        lay.addWidget(self.remove)
        lay.addLayout(page.row(button("Preview", "primary", self.preview),
                               button("Send the invitations", slot=self.apply)))
        self.info = QLabel("", objectName="Muted")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.table = ResultsTable()
        self.table.setMinimumHeight(220)
        lay.addWidget(self.table)
        self.steps = StepList(page)
        self.steps.setMaximumHeight(150)
        lay.addWidget(self.steps)

        box = QGroupBox("Who's missing")
        v = QVBoxLayout(box)
        self.days = QSpinBox()
        self.days.setRange(1, 365)
        self.days.setValue(14)
        self.days.setSuffix(" days")
        v.addLayout(page.row(button("Find students with no guardian invited",
                                    slot=lambda: self.report("nobody")),
                             button("Find invitations not answered in", slot=lambda:
                                    self.report("stale")), self.days))
        self.missing = ResultsTable()
        self.missing.setMinimumHeight(220)
        v.addWidget(self.missing)
        lay.addWidget(box)
        self.invites, self.removals, self.current = [], [], []

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Guardian source", "",
                                           "SIS files (*.csv *.zip);;All files (*)")
        if p:
            self.src.setText(os.path.normpath(p))

    def _students(self) -> list[dict]:
        root = (self.root.path() or "/Students").rstrip("/")
        return [u for u in self.page.directory.users if not u.get("suspended") and
                ((u.get("ou") or "") == root or (u.get("ou") or "").startswith(root + "/"))]

    def _load_current(self, then):
        root = self.root.path() or "/Students"
        settings.set("guardians/root", root)

        def done(code, out, _e):
            if code != 0:
                self.info.setText("Couldn't list current guardians – see the Output panel.")
                return
            self.current = gd.parse_current(out)
            then()
        self.info.setText("Reading current guardians and invitations from Google…")
        self.page.runner.run(["ou_and_children", root, "print", "guardians", "all",
                              "showstudentemails"], done, quiet_stdout=True)

    def preview(self):
        p = self.src.text().strip()
        if not os.path.isfile(p):
            self.page.info("Choose the SIS file first.")
            return
        settings.set("guardians/src", p)
        try:
            links, how = gd.load_links(p)
        except Exception as exc:  # noqa: BLE001
            self.page.info(f"Couldn't read that file:\n{exc}")
            return

        def go():
            students = {u["email"].lower() for u in self._students()}
            self.invites, self.removals = gd.plan(links, self.current, students,
                                                  self.remove.isChecked())
            rows = [["Invite", i["student"], i["guardian"]] for i in self.invites] + \
                   [["Remove", r["student"], r["guardian"]] for r in self.removals]
            self.table.set_rows(["Change", "Student", "Guardian"], rows)
            outside = sum(1 for s, _g in links if s not in students)
            self.info.setText(f"{len(links):,} student–guardian pairs in the SIS ({how}) · "
                              f"{len(self.invites):,} to invite · {len(self.removals):,} to "
                              f"remove" + (f" · {outside} skipped (student not under the "
                                           "student org unit)" if outside else ""))
        self._load_current(go)

    def apply(self):
        todo = self.invites + self.removals
        if not todo:
            self.page.info("Nothing to do – preview first.")
            return
        if not self.page.confirm(f"Send {len(self.invites):,} invitation(s)" +
                                 (f" and remove {len(self.removals):,}" if self.removals else "")
                                 + "?\n\nGuardians get an email from Google asking them to "
                                   "accept."):
            return
        steps = [Step(("Invite " if x in self.invites else "Remove ") +
                      f"{x['guardian']} for {x['student']}", x["args"]) for x in todo]
        self.steps.run(steps, lambda _s: self.page.info(self.steps.summary()))

    def report(self, which):
        def go():
            nobody, stale = gd.missing_report(self._students(), self.current, self.days.value())
            if which == "nobody":
                self.missing.set_rows(["Student", "Name", "Org unit"],
                                      [[s["email"], s.get("name", ""), s.get("ou", "")]
                                       for s in nobody])
                self.info.setText(f"{len(nobody):,} student(s) have no guardian and no "
                                  "invitation.")
            else:
                self.missing.set_rows(["Student", "Guardian invited", "Invited on"],
                                      [[c["student"], c["guardian"], c["since"]] for c in stale])
                self.info.setText(f"{len(stale):,} invitation(s) waiting longer than "
                                  f"{self.days.value()} days. Google lets an invitation stay "
                                  "open for 120 days; after that you can invite again.")
        self._load_current(go)
