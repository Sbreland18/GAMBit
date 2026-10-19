"""Google Classroom: courses, teachers & students, roster sync, guardians."""

from __future__ import annotations

import csv
import io

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QRadioButton, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from ..pickers import PeoplePicker, PersonField
from ..widgets import Page, ResultsTable, button

COURSE_FIELDS = "id,name,section,room,ownerid,coursestate,enrollmentcode,alternatelink"
STATES = [("Active", "active"), ("Archived", "archived"), ("Provisioned (not accepted yet)",
                                                          "provisioned"), ("All", "all")]


def _find(row: dict, *parts) -> str:
    for k, v in row.items():
        kl = (k or "").lower()
        if all(p in kl for p in parts):
            return v or ""
    return ""


class ClassroomPage(Page):
    title = "Classroom"
    subtitle = "Courses, teachers and students, roster syncing, and guardians."

    def build(self):
        self.course_id = ""
        self.tabs = QTabWidget()
        self.tabs.addTab(self._courses_tab(), "Courses")
        self.tabs.addTab(self._create_tab(), "Create a course")
        self.tabs.addTab(self._sync_tab(), "Roster sync (CSV)")
        self.tabs.addTab(self._guardian_tab(), "Guardians")
        from .classroom_year_tab import YearSetupTab
        self.year_tab = YearSetupTab(self)
        self.tabs.addTab(self.year_tab, "Yearly setup")
        from .guardian_sync_tab import GuardianSyncTab
        self.guardian_sync = GuardianSyncTab(self)
        self.tabs.addTab(self.guardian_sync, "Guardian sync")
        from .guardian_report_tab import GuardianReportTab
        self.guardian_report = GuardianReportTab(self)
        self.tabs.addTab(self.guardian_report, "Guardian report")
        from .misc_tabs import CourseworkTab
        self.coursework_tab = CourseworkTab(self)
        self.tabs.addTab(self.coursework_tab, "Coursework")
        from .recovery_tabs import ClassActivityTab, StudentGroupsTab
        self.activity_tab, self.sgroups_tab = ClassActivityTab(self), StudentGroupsTab(self)
        self.tabs.addTab(self.activity_tab, "Class activity")
        self.tabs.addTab(self.sgroups_tab, "Student groups")
        from .round12_pages import ClassroomSyncTab
        self.daily_sync_tab = ClassroomSyncTab(self)
        self.tabs.addTab(self.daily_sync_tab, "Daily roster sync")
        from .round13_tabs import ClassInvitesTab
        self.invites_tab = ClassInvitesTab(self)
        self.tabs.addTab(self.invites_tab, "Invitations && topics")
        from .round14_tabs import GuardianFollowupTab, TeacherStatusTab
        self.teacher_tab, self.gfollow_tab = TeacherStatusTab(self), GuardianFollowupTab(self)
        self.tabs.addTab(self.teacher_tab, "Teacher status")
        self.tabs.addTab(self.gfollow_tab, "Guardian follow-up")
        self.body.addWidget(self.tabs, 1)

    # ======================================================== courses ===
    def _courses_tab(self):
        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 6, 6, 0)
        f = QHBoxLayout()
        self.q_teacher = PersonField(self.directory, "Teacher (optional)")
        self.q_student = PersonField(self.directory, "Student (optional)")
        self.q_state = QComboBox()
        for label, val in STATES:
            self.q_state.addItem(label, val)
        f.addWidget(self.q_teacher)
        f.addWidget(self.q_student)
        lv.addLayout(f)
        lv.addLayout(self.row(self.q_state, button("Find courses", "primary", self.load_courses)))
        self.courses = ResultsTable()
        self.courses.hidden_columns = {"id", "ownerid", "alternatelink"}
        self.courses.row_clicked.connect(self.open_course)
        lv.addWidget(self.courses, 1)
        lv.addLayout(self.row(
            QLabel("Selected courses:"),
            button("Archive", slot=lambda: self.set_state("archived")),
            button("Make active", slot=lambda: self.set_state("active")),
            button("Delete…", "danger", self.delete_courses)))

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 6, 0, 0)
        head = QHBoxLayout()
        self.c_title = QLabel("<span style='font-size:13pt;font-weight:600'>"
                              "Pick a course on the left</span>")
        self.c_title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        head.addWidget(self.c_title, 1)
        self.open_btn = button("Open in Classroom", slot=self.open_in_browser)
        head.addWidget(self.open_btn)
        rv.addLayout(head)

        own = QHBoxLayout()
        self.new_owner = PersonField(self.directory, "New owner (teacher)…")
        own.addWidget(self.new_owner, 1)
        own.addWidget(button("Change owner", slot=self.change_owner))
        self.rename = QLineEdit(placeholderText="New course name")
        own.addWidget(self.rename, 1)
        own.addWidget(button("Rename", slot=self.rename_course))
        rv.addLayout(own)

        self.people = ResultsTable()
        rv.addWidget(self.people, 1)
        rv.addLayout(self.row(QLabel("Selected people:"),
                              button("Remove from course", "danger", self.remove_people)))
        box = QGroupBox("Add people")
        bv = QVBoxLayout(box)
        self.add_picker = PeoplePicker(self.directory, include_groups=False)
        bv.addWidget(self.add_picker)
        ar = QHBoxLayout()
        self.add_as = QComboBox()
        self.add_as.addItems(["students", "teachers"])
        ar.addWidget(QLabel("Add as"))
        ar.addWidget(self.add_as)
        ar.addWidget(button("Add to course", "primary", self.add_people))
        ar.addStretch(1)
        bv.addLayout(ar)
        rv.addWidget(box)
        self.detail = right
        right.setEnabled(False)

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([520, 560])
        return split

    def load_courses(self):
        args = ["print", "courses"]
        if "@" in self.q_teacher.email():
            args += ["teacher", self.q_teacher.email()]
        if "@" in self.q_student.email():
            args += ["student", self.q_student.email()]
        args += ["states", self.q_state.currentData(), "owneremail", "fields", COURSE_FIELDS]
        self.run(args, lambda c, out, _e: self.courses.load_csv(out) if c == 0 else None,
                 quiet=True)

    def open_course(self, row: dict):
        self.course_id = row.get("id", "")
        self._course_row = row
        if not self.course_id:
            return
        name = row.get("name", "")
        sec = row.get("section", "")
        owner = row.get("ownerEmail", "") or _find(row, "owner", "email")
        code = row.get("enrollmentCode", "")
        self.c_title.setText(
            f"<span style='font-size:13pt;font-weight:600'>{name}</span>"
            f"<br><span style='color:#57606a'>{sec + ' · ' if sec else ''}Owner {owner}"
            f"{' · Class code ' + code if code else ''} · {row.get('courseState', '')}</span>")
        self.detail.setEnabled(True)
        self.load_people()

    def load_people(self):
        def done(code, out, _e):
            if code != 0:
                return
            rows = []
            for r in csv.DictReader(io.StringIO(out or "")):
                rows.append([_find(r, "emailaddress"), _find(r, "fullname"),
                             _find(r, "userrole") or _find(r, "role")])
            rows.sort(key=lambda x: (x[2] != "TEACHER" and x[2].lower() != "teacher", x[1]))
            self.people.set_rows(["email", "Name", "Role"], rows)
        self.run(["print", "course-participants", "course", self.course_id], done, quiet=True)

    def _selected_courses(self):
        ids = self.courses.selected_values("id")
        if not ids:
            self.info("Select one or more courses in the list (Ctrl/Shift-click for several).")
        return ids

    def set_state(self, state):
        ids = self._selected_courses()
        if ids and self.confirm(f"Set {len(ids)} course(s) to {state}?"):
            self.run_many([["update", "course", i, "status", state] for i in ids],
                          lambda _o: self.load_courses(), quiet=False)

    def delete_courses(self):
        ids = self._selected_courses()
        if ids and self.confirm(f"Permanently delete {len(ids)} course(s)?\n\nCourses are "
                                "archived first, then deleted. This can't be undone.",
                                "Delete courses"):
            self.run_many([["delete", "course", i, "archived"] for i in ids],
                          lambda _o: self.load_courses(), quiet=False)

    def open_in_browser(self):
        link = getattr(self, "_course_row", {}).get("alternateLink", "")
        if link:
            QDesktopServices.openUrl(QUrl(link))

    def change_owner(self):
        o = self.new_owner.email()
        if "@" not in o:
            self.info("Choose the new owner.")
            return
        if self.confirm(f"Make {o} the owner of this course?\n\nThey're added as a co-teacher "
                        "first if needed."):
            self.run(["update", "course", self.course_id, "owner", o],
                     lambda *_: (self.load_people(), self.load_courses()))

    def rename_course(self):
        n = self.rename.text().strip()
        if n:
            self.run(["update", "course", self.course_id, "name", n],
                     lambda *_: (self.rename.clear(), self.load_courses()))

    def add_people(self):
        emails = self.add_picker.emails()
        if not emails:
            self.info("Search for people and add them to the list first.")
            return
        role = self.add_as.currentText()
        self.run(["courses", self.course_id, "add", role, "users", ",".join(emails)],
                 lambda c, *_: (c == 0 and self.add_picker.clear(), self.load_people()))

    def remove_people(self):
        sel_rows = sorted({i.row() for i in self.people.table.selectedIndexes()})
        if not sel_rows:
            self.info("Select people in the list first.")
            return
        teachers, students = [], []
        for r in sel_rows:
            d = self.people.row_dict(r)
            (teachers if "teacher" in d["Role"].lower() else students).append(d["email"])
        if not self.confirm(f"Remove {len(sel_rows)} person(s) from this course?"):
            return
        cmds = []
        if students:
            cmds.append(["courses", self.course_id, "remove", "students", "users",
                         ",".join(students)])
        if teachers:
            cmds.append(["courses", self.course_id, "remove", "teachers", "users",
                         ",".join(teachers)])
        self.run_many(cmds, lambda _o: self.load_people(), quiet=False)

    # ========================================================= create ===
    def _create_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        box, form = self.group("New course")
        self.n_name = QLineEdit(placeholderText="Biology")
        self.n_section = QLineEdit(placeholderText="Period 3")
        self.n_room = QLineEdit(placeholderText="Room 204")
        self.n_teacher = PersonField(self.directory, "Teacher who owns it")
        self.n_alias = QLineEdit(placeholderText="Optional ID for syncing, e.g. 2026-BIO-P3")
        self.n_active = QCheckBox("Make it active now (otherwise the teacher accepts it)")
        form.addRow("Name", self.n_name)
        form.addRow("Section", self.n_section)
        form.addRow("Room", self.n_room)
        form.addRow("Teacher", self.n_teacher)
        form.addRow("Alias", self.n_alias)
        form.addRow("", self.n_active)
        form.addRow("", self.row(button("Create course", "primary", self.create_course)))
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def create_course(self):
        name, t = self.n_name.text().strip(), self.n_teacher.email()
        if not name or "@" not in t:
            self.info("A course needs a name and a teacher.")
            return
        args = ["create", "course"]
        if self.n_alias.text().strip():
            args += ["alias", self.n_alias.text().strip()]
        args += ["name", name, "teacher", t,
                 "status", "active" if self.n_active.isChecked() else "provisioned"]
        if self.n_section.text().strip():
            args += ["section", self.n_section.text().strip()]
        if self.n_room.text().strip():
            args += ["room", self.n_room.text().strip()]
        self.run(args, lambda c, *_: c == 0 and (self.n_name.clear(), self.n_section.clear(),
                                                  self.n_room.clear(), self.n_alias.clear()))

    # =========================================================== sync ===
    def _sync_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        box, form = self.group("Sync class lists from a spreadsheet (e.g. a SIS export)")
        self.s_path = QLineEdit(placeholderText="CSV with one row per person per course")
        self.s_path.setReadOnly(True)
        form.addRow("CSV file", self.row(self.s_path, button("Browse…", slot=self._s_browse),
                                         stretch=False))
        self.s_course_col = QComboBox()
        self.s_email_col = QComboBox()
        form.addRow("Course column", self.s_course_col)
        form.addRow("Email column", self.s_email_col)
        self.s_role = QComboBox()
        self.s_role.addItems(["students", "teachers"])
        form.addRow("These people are", self.s_role)
        self.s_add = QRadioButton("Only add missing people (safe)")
        self.s_full = QRadioButton("Full sync – also remove people not in the file")
        self.s_add.setChecked(True)
        form.addRow("", self.s_add)
        form.addRow("", self.s_full)
        tip = QLabel("The course column can hold course IDs or aliases written as "
                     "d:ALIAS (e.g. d:2026-BIO-P3).", objectName="Muted")
        tip.setWordWrap(True)
        form.addRow("", tip)
        form.addRow("", self.row(button("Run sync", "primary", self.run_sync)))
        lay.addWidget(box)
        self.s_preview = ResultsTable()
        lay.addWidget(self.s_preview, 1)
        return w

    def _s_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose CSV", "", "CSV files (*.csv)")
        if not path:
            return
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = [r for r in csv.reader(fh) if r]
        if not rows:
            return
        self.s_path.setText(path)
        for cb in (self.s_course_col, self.s_email_col):
            cb.clear()
            cb.addItems(rows[0])
        for i, h in enumerate(rows[0]):
            hl = h.lower()
            if "course" in hl or "class" in hl or "section" in hl:
                self.s_course_col.setCurrentIndex(i)
            if "email" in hl:
                self.s_email_col.setCurrentIndex(i)
        self.s_preview.set_rows(rows[0], rows[1:])

    def run_sync(self):
        if not self.s_path.text():
            self.info("Choose a CSV file first.")
            return
        kc, ec = self.s_course_col.currentText(), self.s_email_col.currentText()
        role = self.s_role.currentText()
        args = ["courses", "csvkmd", self.s_path.text(), "keyfield", kc, "datafield", ec,
                "sync", role]
        if self.s_add.isChecked():
            args.append("addonly")
        args += ["csvdata", ec]
        verb = "add missing" if self.s_add.isChecked() else "FULLY SYNC (add and remove)"
        if self.confirm(f"{verb} {role} for every course in the file?"):
            self.run(args)

    # ====================================================== guardians ===
    def _guardian_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        box, form = self.group("Guardians (parents) for a student")
        self.g_student = PersonField(self.directory, "Student")
        form.addRow("Student", self.row(self.g_student,
                                        button("Show guardians && invitations", "primary",
                                               self.show_guardians), stretch=False))
        self.g_email = QLineEdit(placeholderText="parent@gmail.com")
        form.addRow("Invite guardian", self.row(self.g_email,
                                                button("Send invitation", slot=self.invite),
                                                stretch=False))
        form.addRow("", self.row(button("Remove selected guardian", "danger",
                                        self.remove_guardian)))
        note = QLabel("Guardians get a weekly or daily email summary of the student's "
                      "work. They must accept the invitation email.", objectName="Muted")
        note.setWordWrap(True)
        form.addRow("", note)
        lay.addWidget(box)
        self.g_table = ResultsTable()
        lay.addWidget(self.g_table, 1)
        return w

    def _student(self):
        s = self.g_student.email()
        if "@" not in s:
            self.info("Choose the student first.")
            return None
        return s

    def show_guardians(self):
        if s := self._student():
            self.run(["user", s, "print", "guardians", "all"],
                     lambda c, out, _e: self.g_table.load_csv(out) if c == 0 else None,
                     quiet=True)

    def invite(self):
        s, g = self._student(), self.g_email.text().strip()
        if s and "@" in g:
            self.run(["user", s, "create", "guardian", g],
                     lambda c, *_: (c == 0 and self.g_email.clear(), self.show_guardians()))
        elif s:
            self.info("Type the guardian's email address.")

    def remove_guardian(self):
        s = self._student()
        if not s:
            return
        col = next((h for h in self.g_table._headers
                    if "invitedemailaddress" in h.lower() or h.lower().endswith("emailaddress")),
                   None)
        emails = self.g_table.selected_values(col) if col else []
        if not emails:
            self.info("Show the guardians, then select the one to remove.")
            return
        if self.confirm(f"Remove {', '.join(emails)} as guardian of {s}?"):
            self.run(["user", s, "delete", "guardians", ",".join(emails), "all"],
                     lambda *_: self.show_guardians())
