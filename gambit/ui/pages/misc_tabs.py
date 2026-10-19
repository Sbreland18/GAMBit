"""Classroom → Coursework;  Google Drive → Orphaned files, Labels;
More services → Calendar in bulk;  Groups → Google dynamic group."""

from __future__ import annotations

import datetime

from PySide6.QtCore import QDate, QDateTime, QTime
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QLabel, QLineEdit, QPlainTextEdit, QRadioButton, QVBoxLayout,
)

from ...tools import calendar_class as cc
from ...tools import drive_extra as dx
from ...tools import people
from ..pickers import OUField, OUMultiField, PersonField, TargetPicker
from ..tools_base import ToolTab
from ..widgets import ResultsTable, button


# ============================================================ coursework ===
class CourseworkTab(ToolTab):
    intro = ("Missing work: assignments past their due date that students haven't turned in. "
             "Pick one class (its ID, or d:alias) or a teacher to see all their active classes. "
             "You can also copy assignments, materials and topics from one class to other "
             "sections.")

    def build(self):
        box, form = self.page.group("Missing work")
        self.teacher = PersonField(self.directory, "Teacher (all their active classes)")
        self.course = QLineEdit(placeholderText="or one class ID / d:alias")
        form.addRow("Teacher", self.teacher)
        form.addRow("Class", self.course)
        self.view = QComboBox()
        self.view.addItems(["Every missing assignment", "Count per student"])
        form.addRow("Show", self.view)
        form.addRow("", self.row(button("Find missing work", "primary", self.missing),
                                 self.status))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(320)
        self.lay.addWidget(self.table, 1)

        box, form = self.page.group("Copy coursework to other sections")
        self.src = QLineEdit(placeholderText="Class to copy from (ID or d:alias)")
        self.dst = QPlainTextEdit()
        self.dst.setPlaceholderText("Classes to copy into – one ID or d:alias per line")
        self.dst.setMaximumHeight(90)
        self.drafts = QCheckBox("Copy as drafts so the teacher can review before students see "
                                "them")
        self.drafts.setChecked(True)
        form.addRow("From", self.src)
        form.addRow("To", self.dst)
        form.addRow("", self.drafts)
        form.addRow("", self.row(button("Copy", "primary", self.copy)))
        self.lay.addWidget(box)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def missing(self):
        course, teacher = self.course.text().strip(), self.teacher.email()
        if not course and "@" not in teacher:
            self.info("Pick a teacher or type a class ID.")
            return
        sc = cc.scope(course, teacher if not course else "")

        def done(res):
            works, courses, subs = res
            rows = cc.missing(subs, works, courses)
            if self.view.currentIndex() == 1:
                rows = cc.by_student(rows)
            heads = list(rows[0].keys()) if rows else ["(nothing missing)"]
            self.table.set_rows(heads, [[r[h] for h in heads] for r in rows])
            self.status.setText(f"{len(rows):,} row(s)" if rows else "Nothing missing ✔")
        self.read_many([cc.coursework_args(sc), cc.courses_args(sc), cc.missing_args(sc)],
                       done, "Reading Classroom (a teacher with many classes takes a while)…")

    def copy(self):
        src = self.src.text().strip()
        dst = [x.strip() for x in self.dst.toPlainText().split() if x.strip()]
        if not src or not dst:
            self.info("Fill in the class to copy from and at least one class to copy into.")
            return
        if not self.confirm(f"Copy assignments, materials and topics from {src} into "
                            f"{len(dst)} class(es)? Students and teachers aren't changed."):
            return
        self.run_steps(self.steps, [(f"Copy {src} → {d}", cc.copy_args(src, d,
                                                                       self.drafts.isChecked()))
                                    for d in dst])


# ======================================================== orphaned files ===
class OrphansTab(ToolTab):
    intro = ("“Orphaned” files are files someone owns that aren't in any folder, so they're "
             "easy to lose – common before an account is deleted. This gathers each person's "
             "orphaned files into one folder in their My Drive. Preview first.")

    def build(self):
        self.who = PersonField(self.directory, "One person…")
        self.ou = OUField(self.directory, "…or everyone in an org unit, e.g. /Former Staff")
        self.folder = QLineEdit("#user# orphaned files")
        self.short = QCheckBox("Add shortcuts instead of moving the files")
        box, form = self.page.group("Whose files")
        form.addRow("Person", self.who)
        form.addRow("Org unit", self.ou)
        form.addRow("Folder name", self.folder)
        form.addRow("", self.short)
        form.addRow("", self.row(button("Preview", "primary", lambda: self.go(True)),
                                 button("Collect them", slot=lambda: self.go(False)),
                                 self.status))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(320)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def go(self, preview: bool):
        who, ou = self.who.email(), self.ou.path()
        if "@" not in who and not ou:
            self.info("Pick a person or an org unit.")
            return
        ent = dx.entity(who, ou if "@" not in who else "")
        args = dx.orphans_args(ent, self.folder.text().strip() or "#user# orphaned files",
                               preview, self.short.isChecked())
        if preview:
            def done(rows):
                if rows is not None:
                    heads = list(rows[0].keys()) if rows else ["(no orphaned files)"]
                    self.table.set_rows(heads, [[r.get(h, "") for h in heads] for r in rows])
                    self.status.setText(f"{len(rows):,} orphaned file(s)")
            self.read(args, done)
        elif self.confirm("Collect the orphaned files into a folder for "
                          f"{who if '@' in who else 'everyone under ' + ou}?"):
            self.run_steps(self.steps, [("Collect orphaned files", args)])


# ================================================================= labels ===
class LabelsTab(ToolTab):
    intro = ("Apply a Drive label (for example “Confidential” or “Student record”) to files in "
             "bulk. Labels are made in the Admin console (Apps → Drive → Labels); this lists "
             "the published ones.")

    def build(self):
        self.labels: list[dict] = []
        self.label = QComboBox()
        self.label.currentIndexChanged.connect(self._fields)
        self.field = QComboBox()
        self.field.currentIndexChanged.connect(self._choices)
        self.choice = QComboBox()
        self.owner = PersonField(self.directory, "The files' owner (or an editor)")
        self.files = QPlainTextEdit()
        self.files.setPlaceholderText("File links or IDs, one per line – or one folder link")
        self.files.setMaximumHeight(110)
        self.is_folder = QCheckBox("It's a folder – label every file directly inside it")
        box, form = self.page.group("Label")
        form.addRow("", self.row(button("Load labels", "primary", self.load), self.status))
        form.addRow("Label", self.label)
        form.addRow("Field (optional)", self.field)
        form.addRow("Value", self.choice)
        form.addRow("Owner", self.owner)
        form.addRow("Files", self.files)
        form.addRow("", self.is_folder)
        form.addRow("", self.row(button("Apply label", "primary", lambda: self.apply(False)),
                                 button("Remove label", slot=lambda: self.apply(True)),
                                 button("Who can apply it?…", slot=self.perms)))
        self.lay.addWidget(box)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.lay.addStretch(1)

    def load(self):
        def done(rows):
            if rows is None:
                return
            self.labels = dx.parse_labels(rows)
            self.label.clear()
            for lb in self.labels:
                self.label.addItem(lb["title"], lb)
            self.status.setText(f"{len(self.labels)} published label(s)")
        self.read(dx.LABELS_ARGS, done)

    def perms(self):
        lb = self.label.currentData()
        if not lb:
            self.page.info("Load the labels and choose one first.")
            return
        from .round15_tabs import LabelPermissionsDialog
        LabelPermissionsDialog(self.page, lb).exec()

    def _fields(self, *_):
        self.field.clear()
        self.field.addItem("(just the label)", None)
        lb = self.label.currentData()
        for f in (lb or {}).get("fields", []):
            if f["kind"] == "selection":
                self.field.addItem(f["name"], f)

    def _choices(self, *_):
        self.choice.clear()
        f = self.field.currentData()
        for cid, name in (f or {}).get("choices", []):
            self.choice.addItem(name, cid)

    def apply(self, remove: bool):
        lb = self.label.currentData()
        ids = dx.file_ids(self.files.toPlainText())
        owner = self.owner.email()
        if not lb or not ids or "@" not in owner:
            self.info("Load the labels, pick one, and fill in the owner and the files.")
            return
        f = self.field.currentData()
        args = dx.label_args(owner, ids if not self.is_folder.isChecked() else ids[:1], lb["id"],
                             f["id"] if f else "", self.choice.currentData() or "",
                             self.is_folder.isChecked(), remove)
        what = "every file in the folder" if self.is_folder.isChecked() else f"{len(ids)} file(s)"
        if self.confirm(f"{'Remove' if remove else 'Apply'} “{lb['title']}” on {what}?"):
            self.run_steps(self.steps, [(f"{'Remove' if remove else 'Apply'} {lb['title']}",
                                         args)])


# ============================================================== calendar ===
class EventDialog(QDialog):
    """Add one event to many people's calendars (e.g. the school calendar)."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Add an event to many calendars")
        self.resize(820, 720)
        v = QVBoxLayout(self)
        box = QGroupBox("Whose calendars")
        bl = QVBoxLayout(box)
        self.who = TargetPicker(page.directory)
        bl.addWidget(self.who)
        v.addWidget(box)
        form = QFormLayout()
        self.summary = QLineEdit(placeholderText="e.g. No school – Teacher work day")
        self.allday = QRadioButton("All day")
        self.timed = QRadioButton("At a time")
        self.allday.setChecked(True)
        self.date = QDateEdit(QDate.currentDate().addDays(7))
        self.date.setCalendarPopup(True)
        self.start = QDateTimeEdit(QDateTime(QDate.currentDate().addDays(7), QTime(15, 30)))
        self.end = QDateTimeEdit(QDateTime(QDate.currentDate().addDays(7), QTime(16, 30)))
        for w in (self.start, self.end):
            w.setCalendarPopup(True)
            w.setDisplayFormat("ddd MMM d yyyy  h:mm AP")
        self.where = QLineEdit(placeholderText="optional")
        self.desc = QPlainTextEdit()
        self.desc.setMaximumHeight(80)
        self.busy = QCheckBox("Show them as busy")
        form.addRow("Title", self.summary)
        form.addRow("", page.row(self.allday, self.timed))
        form.addRow("Date", self.date)
        form.addRow("Starts", self.start)
        form.addRow("Ends", self.end)
        form.addRow("Where", self.where)
        form.addRow("Details", self.desc)
        form.addRow("", self.busy)
        v.addLayout(form)
        note = QLabel("Each person gets their own copy (no invitations are emailed). GAMbit "
                      "remembers the batch so you can remove it again from the Calendar tab.",
                      objectName="Muted")
        note.setWordWrap(True)
        v.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Add the event")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.result_steps = []

    def _ok(self):
        ents = self.who.entities()
        if not ents or not self.summary.text().strip():
            self.page.info("Pick whose calendars and type a title.")
            return
        batch = cc.new_batch()
        kw = dict(location=self.where.text().strip(), description=self.desc.toPlainText().strip(),
                  busy=self.busy.isChecked(), batch=batch)
        if self.allday.isChecked():
            d = self.date.date().toPython()
            kw["allday"] = d
            when = d.isoformat()
        else:
            s, e = self.start.dateTime().toPython(), self.end.dateTime().toPython()
            if e <= s:
                self.page.info("The end has to be after the start.")
                return
            kw["start"], kw["end"] = s, e
            when = s.strftime("%Y-%m-%d %H:%M")
        if not self.page.confirm(f"Add “{self.summary.text().strip()}” ({when}) to the "
                                 f"calendars of {self.who.describe()}?"):
            return
        self.result_steps = [(f"Add event for {' '.join(e)}",
                              cc.event_args(e, self.summary.text().strip(), **kw)) for e in ents]
        for e in ents:
            cc.save_batch(batch, self.summary.text().strip(), e, when)
        self.accept()


class SubscribeDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Add a calendar to people's calendar lists")
        self.resize(760, 480)
        v = QVBoxLayout(self)
        self.who = TargetPicker(page.directory)
        v.addWidget(self.who)
        self.cal = QLineEdit(placeholderText="Calendar ID, e.g. c_abc123@group.calendar.google.com "
                                             "or a room's resource email")
        v.addWidget(QLabel("Calendar"))
        v.addWidget(self.cal)
        self.remove = QCheckBox("Remove it from their lists instead")
        v.addWidget(self.remove)
        note = QLabel("People also need permission to see the calendar – share it with them "
                      "(or the domain) from the Calendar tab first.", objectName="Muted")
        note.setWordWrap(True)
        v.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.result_steps = []

    def _ok(self):
        ents, cal = self.who.entities(), self.cal.text().strip()
        if not ents or "@" not in cal:
            self.page.info("Pick the people and type the calendar ID.")
            return
        f = cc.unsubscribe_args if self.remove.isChecked() else cc.subscribe_args
        self.result_steps = [(f"{'Remove' if self.remove.isChecked() else 'Add'} {cal} for "
                              f"{' '.join(e)}", f(e, cal)) for e in ents]
        self.accept()


class LeaverMeetingsDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Cancel someone's future meetings")
        self.resize(820, 560)
        v = QVBoxLayout(self)
        tip = QLabel("For someone who has left: cancels the meetings they organize from now on, "
                     "so rooms are freed and guests aren't left waiting. Meetings in the past "
                     "and meetings other people organize are not touched.")
        tip.setWordWrap(True)
        v.addWidget(tip)
        self.who = PersonField(page.directory, "Who left?")
        self.notify = QCheckBox("Email the guests that the meeting is cancelled")
        self.notify.setChecked(True)
        v.addLayout(page.row(self.who, button("Show their future meetings", "primary",
                                              self._preview), stretch=False))
        self.table = ResultsTable()
        v.addWidget(self.table, 1)
        v.addWidget(self.notify)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Cancel these meetings")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.result_steps = []

    def _preview(self):
        u = self.who.email()
        if "@" not in u:
            return
        import csv
        import io

        def done(code, out, _e):
            if code == 0:
                rows = cc.meetings(list(csv.DictReader(io.StringIO(out or ""))))
                self.table.set_rows(["Meeting", "Starts", "Guests"],
                                    [[r["Meeting"], r["Starts"], r["Guests"]] for r in rows])
        self.page.runner.run(cc.future_meetings_args(u), done, quiet_stdout=True)

    def _ok(self):
        u = self.who.email()
        if "@" not in u or not self.page.confirm(f"Cancel every future meeting {u} organizes?"):
            return
        self.result_steps = [(f"Cancel future meetings of {u}",
                              cc.cancel_future_args(u, self.notify.isChecked()))]
        self.accept()


class BatchesDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Events added by GAMbit")
        self.resize(760, 420)
        v = QVBoxLayout(self)
        self.table = ResultsTable()
        v.addWidget(self.table, 1)
        self._fill()
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        rm = bb.addButton("Remove the selected event from everyone",
                          QDialogButtonBox.DestructiveRole)
        rm.clicked.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.result_steps = []

    def _fill(self):
        b = cc.batches()
        self.table.set_rows(["Event", "When", "Who", "Added", "Batch"],
                            [[x["summary"], x["when"], " ".join(x["entity"]), x["added"], x["id"]]
                             for x in b])

    def _ok(self):
        sel = self.table.selected_dicts()
        if not sel or not self.page.confirm(f"Remove “{sel[0]['Event']}” from every calendar it "
                                            "was added to?"):
            return
        bid = sel[0]["Batch"]
        self.result_steps = [(f"Remove {x['summary']} for {' '.join(x['entity'])}",
                              cc.remove_batch_args(x["entity"], bid))
                             for x in cc.batches() if x["id"] == bid]
        self._forget = bid
        self.accept()


# ====================================================== dynamic groups ===
class DynamicGroupDialog(QDialog):
    """Create a Google-managed dynamic group from a membership rule."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("New Google dynamic group")
        self.resize(820, 600)
        v = QVBoxLayout(self)
        tip = QLabel("Google keeps a dynamic group's members up to date by itself, usually "
                     "within a few minutes – no GAMbit task needed. Members can't be added by "
                     "hand. Some Google editions don't include dynamic groups; Google will say "
                     "so if yours doesn't.")
        tip.setWordWrap(True)
        v.addWidget(tip)
        form = QFormLayout()
        self.email = QLineEdit(placeholderText="hs-teachers@yourschool.org")
        self.name = QLineEdit(placeholderText="High School Teachers")
        self.ous = OUMultiField(page.directory)
        self.ous.sub.hide()
        self.title = QLineEdit(placeholderText="optional, exact job title, e.g. Teacher")
        self.dept = QLineEdit(placeholderText="optional, exact department")
        self.susp = QCheckBox("Leave out suspended accounts")
        self.susp.setChecked(True)
        self.custom = QLineEdit(placeholderText="optional extra rule in Google's query language")
        self.query = QPlainTextEdit()
        self.query.setReadOnly(True)
        self.query.setMaximumHeight(90)
        form.addRow("Group email", self.email)
        form.addRow("Name", self.name)
        form.addRow("People in org units (and below)", self.ous)
        form.addRow("Job title", self.title)
        form.addRow("Department", self.dept)
        form.addRow("", self.susp)
        form.addRow("Extra rule", self.custom)
        form.addRow("", page.row(button("Build the rule", slot=self._build)))
        form.addRow("Rule", self.query)
        v.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Create group")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.result_steps = []
        self._ids: dict[str, str] = {}

    def _build(self, then=None):
        paths = self.ous.paths()

        def make():
            missing = [p for p in paths if p not in self._ids]
            if missing:
                self.page.info("Couldn't find these org units: " + ", ".join(missing))
                return
            q = people.build_query([self._ids[p] for p in paths], self.title.text().strip(),
                                   self.dept.text().strip(), self.susp.isChecked(),
                                   self.custom.text())
            self.query.setPlainText(q)
            if then:
                then()
        if paths and any(p not in self._ids for p in paths):
            import csv
            import io

            def done(code, out, _e):
                if code == 0:
                    self._ids = people.ou_ids(list(csv.DictReader(io.StringIO(out or ""))))
                    make()
            self.page.runner.run(["print", "ous", "fields", "orgunitpath,orgunitid"], done,
                                 quiet_stdout=True)
        else:
            make()

    def _ok(self):
        if "@" not in self.email.text() or not self.name.text().strip():
            self.page.info("Type the group's email and name.")
            return

        def go():
            q = self.query.toPlainText().strip()
            if not q:
                self.page.info("Add at least one rule (an org unit, job title or department).")
                return
            self.result_steps = [(f"Create dynamic group {self.email.text().strip()}",
                                  people.dynamic_group_args(self.email.text().strip(),
                                                            self.name.text().strip(), q))]
            self.accept()
        self._build(go)


def run_dialog_steps(page, dlg, steplist=None, done=None):
    """exec() a dialog that fills result_steps, then run them on the page's StepList."""
    from ..steps import Step, StepList
    if not dlg.exec() or not dlg.result_steps:
        return
    sl = steplist or StepList(page)

    def finished(_s):
        page.info(sl.summary())
        if done:
            done()
    sl.run([Step(label, args) for label, args in dlg.result_steps], finished)


__all__ = ["CourseworkTab", "OrphansTab", "LabelsTab", "EventDialog", "SubscribeDialog",
           "LeaverMeetingsDialog", "BatchesDialog", "DynamicGroupDialog", "run_dialog_steps",
           "datetime"]
