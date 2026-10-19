"""Round 14 pages: Meet attendance, AI use, directory quality and cost per student."""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QLabel, QLineEdit, QSpinBox, QTabWidget,
)

from ..pickers import OUField, PersonField
from ..widgets import Page, ResultsTable, Worker, button
from .round11_pages import run_or_request
from .round13_pages import _steps
from .round13_tabs import _csv, fill


# ========================================================== Meet attendance ===
class MeetAttendancePage(Page):
    title = "Meet attendance"
    subtitle = ("For e-learning days: who joined a teacher's Google Meet and for how long, "
                "compared with the Classroom roster – plus the meeting's recordings and "
                "transcripts.")

    def build(self):
        self.teacher = PersonField(self.directory, "Teacher (meeting organizer)")
        self.day = QDateEdit(QDate.currentDate())
        self.day.setCalendarPopup(True)
        self.course = QComboBox()
        self.course.setEditable(True)
        self.course.setPlaceholderText("class (load the teacher's classes)")
        self.code = QComboBox()
        self.code.setEditable(True)
        self.mins = QSpinBox()
        self.mins.setRange(1, 240)
        self.mins.setValue(10)
        self.mins.setSuffix(" min = present")
        self.to = QLineEdit(placeholderText="attendance office email (optional)")
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(self.teacher, QLabel("Day"), self.day,
                                     button("Load classes and meetings", "primary",
                                            self.load), stretch=False))
        self.body.addLayout(self.row(QLabel("Class"), self.course, QLabel("Meeting"),
                                     self.code, self.mins,
                                     button("Take attendance", "primary", self.take),
                                     stretch=False))
        self.body.addLayout(self.row(self.to, button("Email it", slot=self.email),
                                     self.status))
        self.tabs = QTabWidget()
        self.table = ResultsTable()
        self.rec = ResultsTable()
        self.tabs.addTab(self.table, "Attendance")
        self.tabs.addTab(self.rec, "Recordings && transcripts")
        self.body.addWidget(self.tabs, 1)
        self.body.addLayout(self.row(button("Show recordings and transcripts for this meeting",
                                            slot=self.recordings)))
        self.rows, self.events = [], []

    def _day(self):
        return self.day.date().toPython()

    def load(self):
        from ... import meet_attendance as ma
        t = self.teacher.email()
        if "@" not in t:
            self.info("Choose the teacher.")
            return
        day = self._day()

        def work():
            run = _csv()
            c, courses, _e = run(["print", "courses", "teacher", t, "states", "active",
                                  "fields", "id,name,section"])
            c2, ev, e2 = run(ma.report_args(t, day))
            if c2 != 0:
                raise RuntimeError("Couldn't read the Meet log: " + (e2 or "")[-200:])
            return (courses if c == 0 else []), ev

        def done(res):
            courses, self.events = res
            self.course.clear()
            for r in courses:
                low = {(k or "").lower(): v for k, v in r.items()}
                self.course.addItem(" – ".join(x for x in (low.get("name"), low.get("section"))
                                               if x), low.get("id"))
            self.code.clear()
            for code, n in ma.codes(self.events):
                self.code.addItem(f"{code} ({n} people)", code)
            for cb in (self.course, self.code):
                if cb.count():
                    cb.setCurrentIndex(0)
            self.status.setText(f"{self.course.count()} class(es) · {self.code.count()} "
                                f"meeting(s) that day")
        self.status.setText("Reading classes and the Meet log…")
        Worker(work, on_done=done, on_error=lambda e: self.status.setText(str(e)))

    def take(self):
        from ... import meet_attendance as ma
        cid = self.course.currentData() or self.course.currentText().strip()
        code = self.code.currentData() or self.code.currentText().strip()
        if not cid or not self.events:
            self.info("Load the teacher's classes and meetings first.")
            return

        def done(res):
            c, rows, e = res
            if c != 0:
                self.status.setText((e or "")[-200:])
                return
            self.rows = ma.attendance(ma.roster(rows), ma.sessions(self.events, code),
                                      self.mins.value(), self.teacher.email())
            fill(self.table, self.rows, ["Status", "Name", "Student", "Minutes", "Joined",
                                         "Times joined"])
            self.status.setText(", ".join(f"{k}: {v}" for k, v in
                                          ma.summary(self.rows).items()))
        Worker(lambda: _csv()(ma.roster_args(cid)), on_done=done,
               on_error=lambda e: self.status.setText(str(e)))

    def email(self):
        from ... import google_io
        from ... import meet_attendance as ma
        to = self.to.text().strip()
        if not self.rows or "@" not in to:
            self.info("Take attendance first and fill in who gets it.")
            return
        Worker(google_io.send_email, to, f"Meet attendance – {self.course.currentText()}",
               ma.email_text(self.course.currentText(), self._day(), self.rows),
               on_done=lambda _r: self.status.setText("Sent."),
               on_error=lambda e: self.info(str(e)))

    def recordings(self):
        from ...tools import gam_extras2 as g2
        t = self.teacher.email()
        code = self.code.currentData() or self.code.currentText().strip()
        if "@" not in t or not code:
            self.info("Choose the teacher and a meeting.")
            return

        def work():
            run = _csv()
            c, confs, e = run(g2.conferences_args(t, code))
            if c != 0:
                raise RuntimeError((e or "")[-200:])
            out = []
            for conf in g2.conferences(confs)[:5]:
                for kind in ("meetrecordings", "meettranscripts"):
                    c2, rows, _e = run(g2.meet_items_args(t, kind, conf["name"]))
                    for f in g2.meet_files(rows if c2 == 0 else []):
                        out.append({"Meeting started": conf["Started"], **f,
                                    "Kind": "recording" if kind == "meetrecordings" else
                                    "transcript"})
            return out

        def done(rows):
            fill(self.rec, rows, ["Meeting started", "Kind", "State", "File", "Link"])
            self.tabs.setCurrentWidget(self.rec)
            self.status.setText(f"{len(rows)} recording(s)/transcript(s)")
        Worker(work, on_done=done, on_error=lambda e: self.status.setText(str(e)))


# ================================================================== AI use ===
class AIUsePage(Page):
    title = "AI use"
    subtitle = ("Gemini use from Google's audit log – by school, grade and week, what it's "
                "used for, and use from org units where your AI policy doesn't allow it.")

    def build(self):
        from ... import ai_usage as au
        o = au.options()
        self.days = QSpinBox()
        self.days.setRange(1, 180)
        self.days.setValue(int(o["days"]))
        self.days.setSuffix(" days")
        self.root = OUField(self.directory, "/Students")
        self.root.set_path(o["root"])
        self.banned = QLineEdit(o["not_allowed"])
        self.banned.setMinimumWidth(420)
        self.banned.setPlaceholderText("org units where AI isn't allowed, e.g. "
                                       "/Students/Elementary")
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(QLabel("Last"), self.days, QLabel("Students in"),
                                     self.root, button("Build", "primary", self.load)))
        self.body.addLayout(self.row(QLabel("Not allowed in"), self.banned))
        self.body.addWidget(self.status)
        self.tabs = QTabWidget()
        self.places, self.weeks, self.events, self.flags = (ResultsTable(), ResultsTable(),
                                                            ResultsTable(), ResultsTable())
        self.tabs.addTab(self.places, "By school and grade")
        self.tabs.addTab(self.weeks, "By week")
        self.tabs.addTab(self.events, "What it's used for")
        self.tabs.addTab(self.flags, "Outside the policy")
        self.body.addWidget(self.tabs, 1)

    def load(self):
        from ... import ai_usage as au
        o = {**au.options(), "days": self.days.value(), "root": self.root.path() or
             "/Students", "not_allowed": self.banned.text().strip()}
        au.save_options(o)
        users = self.directory.users

        def work():
            c, rows, e = _csv()(au.args(o["days"], o["app"]))
            if c != 0:
                raise RuntimeError("Couldn't read the Gemini log: " + (e or "")[-200:])
            return au.analyze(rows, users, o)

        def done(res):
            fill(self.places, res["places"], ["School", "Grade / group", "People", "Uses"])
            fill(self.weeks, res["weeks"], ["Week of", "Students", "Staff", "Uses"])
            fill(self.events, res["events"], ["What", "Count"])
            fill(self.flags, res["flagged"], ["Person", "Org unit", "Uses", "Last"])
            self.status.setText(f"{res['people']:,} people used Gemini · "
                                f"{len(res['flagged'])} outside the policy")
        self.status.setText("Reading the Gemini log…")
        Worker(work, on_done=done, on_error=lambda e: self.status.setText(str(e)))


# ======================================================= directory quality ===
class DirectoryQualityPage(Page):
    title = "Directory quality"
    subtitle = ("How complete your directory is, school by school – missing titles, "
                "departments, managers, phones and IDs – and accounts that look like "
                "duplicates.")

    def build(self):
        from ... import directory_quality as dq
        o = dq.options()
        self.staff = OUField(self.directory, "/Staff")
        self.staff.set_path(o["staff_root"])
        self.stu = OUField(self.directory, "/Students")
        self.stu.set_path(o["student_root"])
        self.checks = {}
        row = []
        for f in ("title", "department", "manager", "phone", "employee_id"):
            cb = QCheckBox(dq.LABEL[f])
            cb.setChecked(f in o["staff_fields"])
            self.checks[f] = cb
            row.append(cb)
        self.status = QLabel("", objectName="Muted")
        self.body.addLayout(self.row(QLabel("Staff"), self.staff, QLabel("Students"), self.stu,
                                     button("Check", "primary", self.load), stretch=False))
        self.body.addLayout(self.row(QLabel("Staff need:"), *row, self.status))
        self.tabs = QTabWidget()
        self.score, self.gaps, self.dups = ResultsTable(), ResultsTable(), ResultsTable()
        self.tabs.addTab(self.score, "Score by school")
        self.tabs.addTab(self.gaps, "What's missing")
        self.tabs.addTab(self.dups, "Possible duplicates")
        self.body.addWidget(self.tabs, 1)
        self.body.addLayout(self.row(button("Fix from the HR sheet (Users → Directory details)",
                                            slot=self.fix)))

    def load(self):
        from ... import directory_quality as dq
        o = {**dq.options(), "staff_root": self.staff.path() or "/Staff",
             "student_root": self.stu.path() or "/Students",
             "staff_fields": [f for f, cb in self.checks.items() if cb.isChecked()]}
        dq.save_options(o)

        def work():
            c, rows, e = _csv()(dq.USERS_ARGS)
            if c != 0:
                raise RuntimeError((e or "")[-200:])
            ppl = dq.people(rows)
            s, g = dq.score(ppl, o)
            return s, g, dq.duplicates(ppl, o)

        def done(res):
            s, g, d = res
            fill(self.score, s, ["Where", "People", "Score", "Most often missing"])
            fill(self.gaps, g, ["Person", "Name", "Org unit", "Missing"])
            fill(self.dups, d, ["Why", "Accounts", "Names"])
            self.status.setText(f"{len(g):,} people missing something · {len(d)} possible "
                                "duplicate(s)")
        self.status.setText("Reading the directory…")
        Worker(work, on_done=done, on_error=lambda e: self.status.setText(str(e)))

    def fix(self):
        from .insight_pages import goto
        goto(self.app, "Users", "Directory details")


# ========================================================== cost per student ===
class CostPerStudentPage(Page):
    title = "Cost per student"
    subtitle = ("Chromebooks (spread over their life), licenses and repairs per student, "
                "school by school – for budget season. Prices come from the Budget planner.")

    def build(self):
        from ... import cost_per_student as cp
        o = cp.options()
        self.cost = QDoubleSpinBox()
        self.cost.setRange(0, 5000)
        self.cost.setValue(float(o["device_cost"]))
        self.cost.setPrefix("$")
        self.cost.setSuffix(" per Chromebook")
        self.life = QSpinBox()
        self.life.setRange(1, 10)
        self.life.setValue(int(o["life_years"]))
        self.life.setSuffix(" year life")
        self.rep = QDoubleSpinBox()
        self.rep.setRange(0, 1000)
        self.rep.setValue(float(o["repair_cost"]))
        self.rep.setPrefix("$")
        self.rep.setSuffix(" per repair")
        self.droot = OUField(self.directory, "/Chromebooks")
        self.droot.set_path(o["device_root"])
        self.sroot = OUField(self.directory, "/Students")
        self.sroot.set_path(o["student_root"])
        self.status = QLabel("", objectName="Muted")
        self.body.addLayout(self.row(self.cost, self.life, self.rep))
        self.body.addLayout(self.row(QLabel("Chromebooks"), self.droot, QLabel("Students"),
                                     self.sroot, button("Calculate", "primary", self.load),
                                     self.status))
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)

    def load(self):
        from ... import cost_per_student as cp
        from ... import fleet
        from ...tools import budget
        o = {**cp.options(), "device_cost": self.cost.value(), "life_years": self.life.value(),
             "repair_cost": self.rep.value(), "device_root": self.droot.path() or "/",
             "student_root": self.sroot.path() or "/Students"}
        cp.save_options(o)
        users = self.directory.users

        def work():
            run = _csv()
            c, crows, e = run(["print", "cros", "fields", fleet.FIELDS])
            if c != 0:
                raise RuntimeError((e or "")[-200:])
            c2, lrows, _e = run(budget.USERS_ARGS)
            holders = budget.license_holders(lrows) if c2 == 0 else []
            repairs = fleet.load_list(fleet.data_dir(), "repairs.json")
            return cp.compute(fleet.devices(crows), holders, repairs, users, o)

        def done(rows):
            fill(self.table, rows, ["School", "Students", "Chromebooks", "Devices per student",
                                    "Devices / year", "Licenses / year", "Repairs (12 mo)",
                                    "Repairs cost", "Total / year", "Per student"])
            d = next((r for r in rows if r["School"] == "District"), None)
            self.status.setText(f"District: ${d['Per student']} per student a year" if d and
                                d["Per student"] != "" else "")
        self.status.setText("Reading Chromebooks and licenses…")
        Worker(work, on_done=done, on_error=lambda e: self.status.setText(str(e)))


def vault_queries(page, r: dict):
    """Records requests: save each corpus search in the Vault matter for later reuse."""
    from ...tools import gam_extras2 as g2
    if not r or not r.get("matter"):
        page.info("Start the request first (it needs a Vault matter).")
        return
    steps = [(f"Save {c} search", g2.vault_query_args(r["matter"], f"{r['email']} {c}", c,
                                                       [r["email"]])) for c in r["corpora"]]
    run_or_request(page, _steps(page), steps, "Save searches in Vault",
                   "Records request saved searches")


__all__ = ["MeetAttendancePage", "AIUsePage", "DirectoryQualityPage", "CostPerStudentPage",
           "vault_queries"]
