"""Drive → Restore files;  Email → Restore deleted mail;  Security reports → Settings watch
page;  More services → Admin roles builder, Domains;  Classroom → Class activity, Student
groups;  Staff devices → Chrome profiles;  Staff leaving → Other data check."""

from __future__ import annotations

import csv
import io
import os
import tempfile

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QSpinBox, QTabWidget, QVBoxLayout,
)
from PySide6.QtCore import Qt

from ...settings import settings
from ...tools import recovery as rc
from ..pickers import OUField, PersonField
from ..tools_base import ToolTab
from ..widgets import Page, ResultsTable, button


def _rows(out: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(out or "")))


# ========================================================== drive restore ===
class RestoreFilesTab(ToolTab):
    intro = ("Bring back files someone moved to the trash, or put an earlier version of a file "
             "back. Trashed files stay restorable for 30 days; after that (up to 25 more days) "
             "use the Admin console's “Restore data”.")

    def build(self):
        box, form = self.page.group("Trashed files")
        self.who = PersonField(self.directory, "Whose files?")
        self.how = QComboBox()
        self.how.addItem("Files they trashed recently (from the audit log)", "audit")
        self.how.addItem("Everything in their trash right now", "trash")
        self.days = QSpinBox()
        self.days.setRange(1, 30)
        self.days.setValue(7)
        self.days.setSuffix(" days")
        form.addRow("Person", self.who)
        form.addRow("Show", self.row(self.how, QLabel("Last"), self.days, stretch=False))
        form.addRow("", self.row(button("Find trashed files", "primary", self.find),
                                 button("Restore selected (or all)", slot=self.restore)))
        self.lay.addWidget(box)
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.hidden_columns = {"ID"}
        self.table.setMinimumHeight(240)
        self.lay.addWidget(self.table)

        box, form = self.page.group("Earlier versions of a file")
        self.v_owner = PersonField(self.directory, "The file's owner")
        self.v_file = QLineEdit(placeholderText="File link or ID")
        form.addRow("Owner", self.v_owner)
        form.addRow("File", self.v_file)
        form.addRow("", self.row(button("Show versions", slot=self.versions),
                                 button("Put the selected version back", slot=self.put_back)))
        note = QLabel("Google Docs, Sheets and Slides: open the file and use File → Version "
                      "history → Restore (Google doesn't allow this from outside). Uploaded "
                      "files (PDF, Word, images…) can be put back from here.", objectName="Muted")
        note.setWordWrap(True)
        form.addRow("", note)
        self.lay.addWidget(box)
        self.v_table = ResultsTable()
        self.v_table.setMinimumHeight(200)
        self.lay.addWidget(self.v_table)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.mime = ""

    def find(self):
        u = self.who.email()
        if "@" not in u:
            self.info("Pick the person first.")
            return
        audit = self.how.currentData() == "audit"

        def done(rows):
            if rows is None:
                return
            f = rc.trashed_files(rows, audit)
            self.table.set_rows(["File", "When", "By", "ID"],
                                [[x["File"], x["When"], x["By"], x["ID"]] for x in f])
            self.status.setText(f"{len(f)} file(s)")
        self.read(rc.trashed_by_audit_args(u, self.days.value()) if audit
                  else rc.trash_list_args(u), done)

    def restore(self):
        u = self.who.email()
        sel = self.table.selected_dicts() or [self.table.row_dict(i)
                                              for i in range(self.table.row_count())]
        ids = [r["ID"] for r in sel if r.get("ID")]
        if "@" not in u or not ids:
            self.info("Find the trashed files first.")
            return
        if self.confirm(f"Restore {len(ids)} file(s) from {u}'s trash?"):
            self.run_steps(self.steps, [(f"Restore {len(ids)} file(s)", rc.untrash_args(u, ids))],
                           lambda _s: self.find())

    def _file(self):
        from ...tools.drive_extra import file_ids
        ids = file_ids(self.v_file.text())
        return ids[0] if ids else ""

    def versions(self):
        o, f = self.v_owner.email(), self._file()
        if "@" not in o or not f:
            self.info("Fill in the owner and the file.")
            return

        def done(rows):
            if rows is None:
                return
            v = rc.revisions(rows)
            self.mime = v[0]["Type"] if v else ""
            self.v_table.set_rows(["Version", "Saved", "By", "Type", "Size"],
                                  [[x[k] for k in ("Version", "Saved", "By", "Type", "Size")]
                                   for x in v])
            self.status.setText(f"{len(v)} version(s)")
        self.read(rc.revisions_args(o, f), done)

    def put_back(self):
        sel = self.v_table.selected_dicts()
        o, f = self.v_owner.email(), self._file()
        if not sel or not f:
            self.info("Show the versions and select one.")
            return
        if (sel[0].get("Type") or self.mime).startswith(rc.GOOGLE_NATIVE):
            self.info("This is a Google Docs/Sheets/Slides file – restore it from File → Version "
                      "history in the file itself.")
            return
        folder = tempfile.mkdtemp(prefix="gambit-rev-")
        name = f"{f}-{sel[0]['Version']}"
        if self.confirm(f"Put the version saved {sel[0]['Saved']} back as the current one? "
                        "(The current version stays in the history.)"):
            self.run_steps(self.steps, rc.restore_revision_steps(o, f, sel[0]["Version"], folder,
                                                                  name), lambda _s: self.versions())


# =========================================================== mail restore ===
class RestoreMailTab(ToolTab):
    intro = ("Bring back email that was deleted by mistake – for example after a “Find & remove "
             "messages” run. Deleted mail stays in the trash for 30 days.")

    def build(self):
        box, form = self.page.group("Restore")
        self.who = PersonField(self.directory, "Whose mailbox?")
        self.q = QLineEdit("in:trash newer_than:7d")
        form.addRow("Mailbox", self.who)
        form.addRow("Which messages", self.q)
        form.addRow("", QLabel("Gmail search – keep “in:trash”. Add e.g. from:principal@… or "
                               "subject:…", objectName="Muted"))
        form.addRow("", self.row(button("Preview", "primary", self.preview),
                                 button("Restore them", slot=self.restore), self.status))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def preview(self):
        u = self.who.email()
        if "@" not in u:
            self.info("Pick the mailbox first.")
            return

        def done(rows):
            if rows is not None:
                h = list(rows[0].keys()) if rows else ["(nothing found)"]
                self.table.set_rows(h, [[r.get(k, "") for k in h] for r in rows])
                self.status.setText(f"{len(rows)} message(s)")
        self.read(rc.trashed_mail_args(u, self.q.text().strip()), done)

    def restore(self):
        u = self.who.email()
        if "@" in u and self.confirm(f"Restore every message matching “{self.q.text()}” in "
                                     f"{u}'s mailbox?"):
            self.run_steps(self.steps, [("Restore messages",
                                         rc.untrash_mail_args(u, self.q.text().strip()))])


# =========================================================== settings watch ===
class SettingsWatchPage(Page):
    title = "Settings watch"
    subtitle = ("A copy of your Admin console and Chrome settings, saved every night, so you "
                "can see exactly what changed and when – and get an alert when something does.")

    def build(self):
        self.status = QLabel("", objectName="Muted")
        self.enable = QCheckBox("Check every night and alert me when a setting changes")
        self.enable.setChecked(bool(settings.get("watch/enabled", False)))
        self.enable.toggled.connect(self._toggle)
        self.drift = QCheckBox("Drift guard: when a setting changes outside GAMbit, ask "
                               "(in Approvals) to put it back")
        self.drift.setChecked(bool(settings.get("watch/drift_guard", False)))
        self.drift.toggled.connect(lambda on: settings.set("watch/drift_guard", bool(on)))
        self.body.addLayout(self.row(button("Take a snapshot now", "primary", self.snap_now),
                                     self.enable, self.status))
        self.body.addLayout(self.row(self.drift,
                                     button("Propose putting back the compared changes",
                                            slot=self.propose_revert)))
        self.a = QComboBox()
        self.b = QComboBox()
        self.body.addLayout(self.row(QLabel("Compare"), self.a, QLabel("with"), self.b,
                                     button("Compare", slot=self.compare), stretch=False))
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        note = QLabel("To see who made a change, use Investigations → Audit log → “Admin "
                      "changes” for that day.", objectName="Muted")
        self.body.addWidget(note)
        self._fill()

    def propose_revert(self):
        from ... import activity, team
        from ...tools import playbooks
        a, b = self.a.currentData(), self.b.currentData()
        if not a or not b or a == b:
            self.info("Choose two different snapshots (newer first).")
            return
        changes = rc.diff(rc.load_snapshot(b), rc.load_snapshot(a))
        if not changes:
            self.info("Nothing changed between these two snapshots.")
            return
        steps, manual = playbooks.revert_plan(changes, activity.load(90, team=True))
        if not steps and not manual:
            self.info("Nothing to put back – the changes were made with GAMbit.")
            return
        text = "\n".join(f"• {lab}" for lab, _a in steps) + \
            ("\n\nBy hand in the Admin console:\n" + "\n".join(manual[:20]) if manual else "")
        if not team.folder():
            self.info("Approvals need a team folder. What would be put back:\n\n" + text)
            return
        if self.confirm(f"Send this for approval?\n\n{text}"):
            playbooks.drift_request(changes, b[:-5].replace("_", " "),
                                    activity.load(90, team=True))
            self.info("Sent – see the Approvals page.")

    def _fill(self):
        snaps = rc.list_snapshots()
        for cb in (self.a, self.b):
            cb.clear()
            for s in snaps:
                cb.addItem(s[:-5].replace("_", " "), s)
        if len(snaps) > 1:
            self.b.setCurrentIndex(1)
        self.status.setText(f"{len(snaps)} snapshot(s) in {rc.snapshots_dir()}")

    def _toggle(self, on):
        settings.set("watch/enabled", bool(on))
        if on:
            from ... import tasks_health
            try:
                tasks_health.create(dict(rc.TASK))
                self.info("Settings will be checked every night at 5:05 AM. Alerts go to the "
                          "addresses in Settings → Google Sheets and email.")
            except Exception as exc:  # noqa: BLE001
                self.info(f"Saved, but the nightly task couldn't be created here:\n{exc}")

    def snap_now(self):
        out: dict = {}

        def got_ci(code, o, _e):
            out["ci"] = _rows(o) if code == 0 else []
            self.runner.run(rc.chrome_root_args("/"), got_chrome, quiet_stdout=True)

        def got_chrome(code, o, _e):
            snap = rc.snapshot(out["ci"], _rows(o) if code == 0 else [])
            prev = rc.list_snapshots()
            rc.save_snapshot(snap)
            self._fill()
            if prev:
                self.a.setCurrentIndex(0)
                self.b.setCurrentIndex(1)
                self.compare()
            self.status.setText(f"Saved {len(snap)} settings.")
        self.status.setText("Reading every Admin console and Chrome setting…")
        self.runner.run(rc.CI_ARGS, got_ci, quiet_stdout=True)

    def compare(self):
        a, b = self.a.currentData(), self.b.currentData()
        if not a or not b or a == b:
            self.info("Pick two different snapshots (take one now if there's only one).")
            return
        d = rc.diff(rc.load_snapshot(b), rc.load_snapshot(a))
        self.table.set_rows(["Change", "Setting", "Before", "Now"],
                            [[x["Change"], x["Setting"], x["Before"], x["Now"]] for x in d])
        self.status.setText(f"{len(d)} change(s)" if d else "No changes ✔")


# ============================================================== admin roles ===
class AdminRoleDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("New custom admin role")
        self.resize(820, 720)
        v = QVBoxLayout(self)
        tip = QLabel("Build a role with only the rights someone needs, then assign it for one "
                     "org unit – for example “reset passwords only at Lincoln”.")
        tip.setWordWrap(True)
        v.addWidget(tip)
        form = QFormLayout()
        self.name = QLineEdit(placeholderText="e.g. Lincoln building tech")
        self.desc = QLineEdit(placeholderText="optional")
        self.tpl = QComboBox()
        self.tpl.addItem("Start from scratch", None)
        for k in rc.ROLE_TEMPLATES:
            self.tpl.addItem(k, k)
        self.tpl.currentIndexChanged.connect(self._template)
        self.find = QLineEdit(placeholderText="Filter privileges, e.g. password, chrome, group…")
        self.find.textChanged.connect(self._filter)
        form.addRow("Role name", self.name)
        form.addRow("Description", self.desc)
        form.addRow("Start from", self.tpl)
        form.addRow("Find", self.find)
        v.addLayout(form)
        self.list = QListWidget()
        v.addWidget(self.list, 1)
        self.who = PersonField(page.directory, "optional – assign it to someone now")
        self.ou = OUField(page.directory, "Only for this org unit (leave empty for everywhere)")
        v.addLayout(page.row(QLabel("Assign to"), self.who, stretch=False))
        v.addLayout(page.row(QLabel("Scope"), self.ou, stretch=False))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Create role")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.result_steps = []
        page.runner.run(rc.PRIVILEGES_ARGS, self._loaded, quiet_stdout=True)

    def _loaded(self, code, out, _e):
        if code != 0:
            return
        for p in rc.privileges(_rows(out)):
            it = QListWidgetItem(f"{p['Service']}: {p['Privilege']}"
                                 + ("   (per org unit)" if p["Per org unit"] else ""))
            it.setData(Qt.UserRole, p["Privilege"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.list.addItem(it)

    def _items(self):
        return [self.list.item(i) for i in range(self.list.count())]

    def _template(self, *_):
        key = self.tpl.currentData()
        if not key:
            return
        avail = [it.data(Qt.UserRole) for it in self._items()]
        want = set(rc.template_matches(rc.ROLE_TEMPLATES[key], avail))
        for it in self._items():
            it.setCheckState(Qt.Checked if it.data(Qt.UserRole) in want else Qt.Unchecked)
        if not self.name.text():
            self.name.setText(key.split(" (")[0])

    def _filter(self, text):
        t = text.lower().strip()
        for it in self._items():
            it.setHidden(bool(t) and t not in it.text().lower())

    def _ok(self):
        privs = [it.data(Qt.UserRole) for it in self._items() if it.checkState() == Qt.Checked]
        name = self.name.text().strip()
        if not name or not privs:
            self.page.info("Give the role a name and tick at least one privilege.")
            return
        self.result_steps = [(f"Create role {name}", rc.create_role_args(name,
                                                                         self.desc.text().strip(),
                                                                         privs))]
        who = self.who.email()
        if "@" in who:
            self.result_steps.append((f"Give {who} the role" + (f" for {self.ou.path()}"
                                                               if self.ou.path() else ""),
                                      rc.assign_role_args(who, name, self.ou.path())))
        self.accept()


# ================================================================== domains ===
class DomainsTab(ToolTab):
    intro = "Your Google Workspace domains and alias domains (read only)."

    def build(self):
        self.lay.addLayout(self.row(button("Show domains", "primary", self.load), self.status))
        self.d = ResultsTable()
        self.a = ResultsTable()
        self.d.setMinimumHeight(200)
        self.a.setMinimumHeight(160)
        self.lay.addWidget(QLabel("<b>Domains</b>"))
        self.lay.addWidget(self.d)
        self.lay.addWidget(QLabel("<b>Alias domains</b>"))
        self.lay.addWidget(self.a, 1)

    def load(self):
        def done(res):
            for t, rows in zip((self.d, self.a), res):
                h = list(rows[0].keys()) if rows else ["(none)"]
                t.set_rows(h, [[r.get(k, "") for k in h] for r in rows])
        self.read_many([rc.DOMAIN_ARGS, rc.ALIAS_ARGS], done)


# ================================================================ classroom ===
class ClassActivityTab(ToolTab):
    intro = ("How many announcements, materials and assignments each class has – a quick way "
             "to spot classes that haven't been used yet.")

    def build(self):
        self.teacher = PersonField(self.directory, "Teacher (all their active classes)")
        self.lay.addLayout(self.row(self.teacher, button("Show activity", "primary", self.load),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(360)
        self.lay.addWidget(self.table, 1)

    def load(self):
        t = self.teacher.email()
        if "@" not in t:
            self.info("Pick a teacher.")
            return
        sc = ["teacher", t, "states", "active"]

        def done(res):
            rows = rc.class_activity(*res)
            h = ["Class", "Announcements", "Materials", "Assignments", "Note"]
            self.table.set_rows(h, [[r[k] for k in h] for r in rows])
            self.status.setText(f"{len(rows)} class(es)")
        self.read_many([rc.activity_args(k, sc) for k in ("course-announcements",
                                                          "course-materials", "course-works")],
                       done)


class StudentGroupsTab(ToolTab):
    intro = ("Create Classroom student groups (reading groups, lab groups, IEP supports) from a "
             "spreadsheet with Class (ID or d:alias), Group and Student email columns. Each group "
             "is created if needed and its members are set to match the sheet.")

    def build(self):
        self.src = QLineEdit(placeholderText="groups.csv")
        self.lay.addLayout(self.row(self.src, button("Browse…", slot=self._browse),
                                    button("Preview", "primary", self.preview),
                                    button("Create and fill the groups", slot=self.apply),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.wanted = {}

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Student groups", "", "CSV (*.csv)")
        if p:
            self.src.setText(p)

    def preview(self):
        try:
            with open(self.src.text().strip(), encoding="utf-8-sig") as fh:
                self.wanted = rc.studentgroup_rows(list(csv.DictReader(fh)))
        except OSError:
            self.info("Choose the spreadsheet first.")
            return
        self.table.set_rows(["Class", "Group", "Students"],
                            [[c, g, str(len(s))] for (c, g), s in sorted(self.wanted.items())])
        self.status.setText(f"{len(self.wanted)} group(s) in "
                            f"{len({c for c, _g in self.wanted})} class(es)")

    def _existing(self, then):
        """then({(class as typed, group title lower): (course id, group id)})"""
        classes = sorted({c for c, _g in self.wanted})

        def done(res):
            have = {}
            for c, rows in zip(classes, res):
                for (cid, title), gid in rc.existing_groups(rows).items():
                    have[(c, title)] = (cid, gid)
            then(have)
        self.read_many([["print", "course-studentgroups", "course", c] for c in classes], done)

    def apply(self):
        if not self.wanted:
            self.preview()
            if not self.wanted:
                return
        if not self.confirm(f"Create and fill {len(self.wanted)} student group(s)?"):
            return

        def fill(_s=None):
            def after(have):
                steps = []
                for (c, g), emails in sorted(self.wanted.items()):
                    if (c, g.lower()) in have:
                        cid, gid = have[(c, g.lower())]
                        steps.append((f"Set members of “{g}” in {c} ({len(emails)})",
                                      rc.sync_group_args(cid, gid, emails)))
                if steps:
                    self.run_steps(self.steps, steps)
            self._existing(after)

        def with_ids(have):
            create = [(f"Create “{g}” in {c}", rc.create_group_args(c, g))
                      for (c, g) in sorted(self.wanted) if (c, g.lower()) not in have]
            if create:
                self.run_steps(self.steps, create, fill)
            else:
                fill()
        self._existing(with_ids)


# ============================================================ chrome profiles ===
class ChromeProfilesDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.setWindowTitle("Managed Chrome profiles")
        self.resize(1000, 600)
        v = QVBoxLayout(self)
        tip = QLabel("People signed in to Chrome with their district account on Windows, Mac "
                     "and Linux computers (managed profiles), with Chrome version and last use.")
        tip.setWordWrap(True)
        v.addWidget(tip)
        self.status = QLabel("Loading…", objectName="Muted")
        v.addWidget(self.status)
        self.table = ResultsTable()
        v.addWidget(self.table, 1)
        from .round15_tabs import old_profiles_button
        v.addWidget(old_profiles_button(page), 0)

        def done(code, out, _e):
            if code != 0:
                self.status.setText("GAM reported a problem – see the Output panel.")
                return
            p = rc.profiles(_rows(out))
            h = ["Person", "Profile", "Computer", "Chrome", "Extensions", "Last used", "Note"]
            self.table.set_rows(h, [[r[k] for k in h] for r in p])
            self.status.setText(f"{len(p):,} profile(s)")
        page.runner.run(rc.PROFILES_ARGS, done, quiet_stdout=True)


# ============================================================ leaver: other data ===
class OtherDataDialog(QDialog):
    """Data a Drive/Calendar transfer doesn't cover: transfer status, YouTube, Keep, Looker."""

    def __init__(self, page, email: str):
        super().__init__(page)
        self.setWindowTitle(f"Other data – {email}")
        self.resize(900, 640)
        v = QVBoxLayout(self)
        tabs = QTabWidget()
        v.addWidget(tabs, 1)
        self.tables = {}
        for key, label in (("transfer", "Data transfer"), ("youtube", "YouTube channels"),
                           ("keep", "Keep notes"), ("tasks", "Google Tasks"),
                           ("looker", "Looker Studio")):
            t = ResultsTable()
            self.tables[key] = t
            tabs.addTab(t, label)
        self.status = QLabel("Checking…", objectName="Muted")
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        from ...tools import gam_extras3 as g3
        from ...tools.more_tools import notes, notes_args
        jobs = [("transfer", rc.transfers_args(email), rc.transfers),
                ("youtube", rc.youtube_args(email), rc.youtube),
                ("keep", notes_args(email), notes),
                ("tasks", g3.tasks_args(email), g3.tasks),
                ("looker", ["user", email, "print", "datastudioassets", "assettype", "all"], None)]
        self.summary: dict[str, str] = {}

        def run(i=0):
            if i >= len(jobs):
                self.status.setText(" · ".join(f"{k}: {v}" for k, v in self.summary.items()))
                return
            key, args, fn = jobs[i]

            def done(code, out, _e):
                rows = _rows(out) if code == 0 else []
                shaped = fn(rows) if fn else rows
                h = list(shaped[0].keys()) if shaped else ["(nothing)"]
                self.tables[key].set_rows(h, [[r.get(k, "") for k in h] for r in shaped])
                if key == "transfer":
                    st = {r["Status"] for r in shaped}
                    self.summary["transfer"] = ("none started" if not shaped else
                                                "FAILED" if "failed" in st else
                                                "in progress" if "inprogress" in st else
                                                "completed")
                else:
                    self.summary[key] = str(len(shaped)) if code == 0 else "couldn't check"
                run(i + 1)
            page.runner.run(args, done, quiet_stdout=True)
        run()
        v.addWidget(QLabel("YouTube channels can't be moved by an admin – ask the person to add "
                           "a colleague as a channel manager before they leave. Keep notes: "
                           "Google Drive → Keep notes. Looker Studio: the Staff leaving step "
                           "gives the supervisor editor access.", objectName="Muted"))


__all__ = ["RestoreFilesTab", "RestoreMailTab", "SettingsWatchPage", "AdminRoleDialog",
           "DomainsTab", "ClassActivityTab", "StudentGroupsTab", "ChromeProfilesDialog",
           "OtherDataDialog", "os"]
