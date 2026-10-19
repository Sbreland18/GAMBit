"""Classroom → Yearly setup tab: archive last year, create this year from the SIS."""

from __future__ import annotations

import csv
import io
import os

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QDateEdit, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QScrollArea, QVBoxLayout, QWidget,
)

from ... import classroom_year as cy
from ...settings import settings
from ..steps import Step, StepList
from ..widgets import ResultsTable, button


class YearSetupTab(QScrollArea):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget(objectName="Page")
        lay = QVBoxLayout(inner)
        self.setWidget(inner)
        self.year_end, self.year_label = cy.school_year()

        # ---- 1. archive ----
        box = QGroupBox("1. Archive last year's classes")
        v = QVBoxLayout(box)
        tip = QLabel("Archived classes stay readable for teachers and students but drop off "
                     "everyone's Classroom home page. You can make them active again from "
                     "the Activity log (Undo).")
        tip.setWordWrap(True)
        v.addWidget(tip)
        h = QHBoxLayout()
        h.addWidget(QLabel("Active classes created before"))
        self.before = QDateEdit(QDate(self.year_end - 1, 7, 1))
        self.before.setCalendarPopup(True)
        self.before.setDisplayFormat("MMM d, yyyy")
        h.addWidget(self.before)
        h.addWidget(button("Find them", slot=self.find_old))
        h.addStretch(1)
        v.addLayout(h)
        self.old = ResultsTable()
        self.old.setMinimumHeight(200)
        v.addWidget(self.old)
        self.old_info = QLabel("", objectName="Muted")
        v.addLayout(page.row(button("Archive the selected classes (or all listed)", "primary",
                                    self.archive), self.old_info))
        lay.addWidget(box)

        # ---- 2. create ----
        box = QGroupBox(f"2. Create {self.year_label} classes from the SIS")
        v = QVBoxLayout(box)
        tip = QLabel("ClassLink: point at the OneRoster .zip (or its classes.csv). Other "
                     "systems: a CSV with one row per student – Section ID, Course, Period, "
                     "Subject, Room, Teacher email, Student email. Each class gets the alias "
                     f"d:<section>-{str(self.year_end)[-2:]}, so running this again only adds "
                     "anyone missing.")
        tip.setWordWrap(True)
        v.addWidget(tip)
        self.src = QLineEdit(settings.get("classroom/year_src", "") or "")
        self.src.setPlaceholderText("oneroster.zip, classes.csv, or sections.csv")
        from ..widgets import classlink_button
        v.addLayout(page.row(self.src, button("Browse…", slot=self._browse),
                             classlink_button(self.src, self.load, self),
                             button("Load", "primary", self.load), stretch=False))
        self.name_tpl = QLineEdit(settings.get("classroom/name_tpl", "") or
                                  "{period} {subject} – {teacher} {year}")
        self.sec_tpl = QLineEdit(settings.get("classroom/section_tpl", "") or "Period {period}")
        v.addLayout(page.row(QLabel("Class name"), self.name_tpl, QLabel("Section"),
                             self.sec_tpl, stretch=False))
        tags = QLabel("Tags: {course} {subject} {period} {room} {teacher} {teacher_email} "
                      "{section} {school} {year}", objectName="Muted")
        v.addWidget(tags)
        self.add_students = QCheckBox("Add students now (otherwise only teachers – useful if "
                                      "rosters aren't final yet)")
        self.add_students.setChecked(True)
        v.addWidget(self.add_students)
        v.addLayout(page.row(button("Preview", slot=self.preview)))
        self.new = ResultsTable()
        self.new.setMinimumHeight(240)
        v.addWidget(self.new)
        self.new_info = QLabel("", objectName="Muted")
        v.addLayout(page.row(button("Create the classes", "primary", self.create),
                             self.new_info))
        self.steps = StepList(page)
        self.steps.setMaximumHeight(170)
        v.addWidget(self.steps)
        lay.addWidget(box)
        lay.addStretch(1)
        self.sections: list[dict] = []
        self.planned: list[dict] = []
        self.old_ids: list[str] = []

    # ---- archive ----
    def find_old(self):
        cutoff = self.before.date().toString("yyyy-MM-dd")

        def done(code, out, _e):
            if code != 0:
                self.old_info.setText("Couldn't list classes – see the Output panel.")
                return
            rows = [r for r in csv.DictReader(io.StringIO(out or ""))
                    if (r.get("creationTime") or "")[:10] < cutoff]
            heads = ["id", "name", "section", "ownerEmail", "creationTime", "enrollmentCode"]
            self.old.set_rows(heads, [[r.get(h, "") for h in heads] for r in rows])
            self.old_ids = [r.get("id", "") for r in rows if r.get("id")]
            self.old_info.setText(f"{len(rows):,} active class(es) created before {cutoff}.")
        self.page.runner.run(["print", "courses", "states", "active", "owneremail", "fields",
                              "id,name,section,ownerid,creationtime,enrollmentcode"],
                             done, quiet_stdout=True)

    def archive(self):
        sel = [r.get("id") for r in self.old.selected_dicts() if r.get("id")]
        ids = sel or self.old_ids
        if not ids:
            self.page.info("Find last year's classes first.")
            return
        if not self.page.confirm(f"Archive {len(ids):,} class(es)?"):
            return
        steps = [Step(f"Archive {len(b[2].split(','))} class(es)", b)
                 for b in cy.archive_batches(ids)]
        self.steps.run(steps, lambda _s: (self.page.info(self.steps.summary()),
                                          self.find_old()))

    # ---- create ----
    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "SIS classes", "",
                                              "SIS files (*.zip *.csv);;All files (*)")
        if path:
            self.src.setText(os.path.normpath(path))
            self.load()

    def load(self):
        p = self.src.text().strip()
        if not os.path.exists(p):
            self.page.info("Choose the OneRoster export or the sections CSV first.")
            return False
        try:
            self.sections, how = cy.load_sections(p)
        except Exception as exc:  # noqa: BLE001
            self.page.info(f"Couldn't read that file:\n{exc}")
            return False
        settings.set("classroom/year_src", p)
        self.new_info.setText(f"{len(self.sections):,} classes with a teacher ({how}). "
                              "Click Preview.")
        return True

    def preview(self):
        if not self.sections and not self.load():
            return
        settings.set("classroom/name_tpl", self.name_tpl.text())
        settings.set("classroom/section_tpl", self.sec_tpl.text())
        self.new_info.setText("Checking which classes already exist…")

        def done(code, out, _e):
            aliases = set()
            if code == 0:
                for r in csv.DictReader(io.StringIO(out or "")):
                    for k, v in r.items():
                        if (k or "").lower().startswith("alias") and v:
                            for a in v.replace(",", " ").split():
                                aliases.add(a.lower().removeprefix("d:"))
            self.planned = cy.plan(self.sections, aliases, self.name_tpl.text(),
                                   self.sec_tpl.text(), self.year_end, self.year_label,
                                   self.add_students.isChecked())
            heads = ["Class name", "Section", "Teacher", "Co-teachers", "Students", "Alias",
                     "Status"]
            self.new.set_rows(heads, [[x["name"], x["section"], x["teacher"],
                                       str(x["co_teachers"]), str(x["students"]),
                                       "d:" + x["alias"], x["status"]] for x in self.planned])
            n = sum(1 for x in self.planned if x["status"] == "new")
            self.new_info.setText(f"{n:,} new class(es), {len(self.planned) - n:,} already "
                                  f"there · {sum(len(x['commands']) for x in self.planned):,} "
                                  "GAM command(s). Turn on 🧪 Dry run to see them all.")
        self.page.runner.run(["print", "courses", "states", "active,provisioned", "aliases",
                              "fields", "id,name"], done, quiet_stdout=True)

    def create(self):
        if not self.planned:
            self.page.info("Preview first.")
            return
        steps = [Step(f"{x['name']}: " + ("create" if c[0] == "create" else
                                          f"add {c[3]}"), c)
                 for x in self.planned for c in x["commands"]]
        if not steps:
            self.page.info("Everything is already there.")
            return
        if self.page.confirm(f"Run {len(steps):,} step(s) for {len(self.planned):,} class(es)?"):
            self.steps.run(steps, lambda _s: self.page.info(self.steps.summary()))

