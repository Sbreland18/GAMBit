"""Round 14 tabs and dialogs on existing pages: form responses, Chromebook Wi-Fi networks,
device tools (serial checks, device counts, app details, device files, printer models),
replace someone in meetings, folder tools, teacher status, guardian follow-up, trusted
domains, Vault saved searches, photo export, Chat moderation, Gmail language, premium
licenses, public apps list, shared passwords, battery forecast and repeat damage."""

from __future__ import annotations

from ... import tempfiles as _tf
import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QLabel, QLineEdit,
    QPlainTextEdit, QSpinBox, QVBoxLayout,
)

from ...settings import settings
from ...tools import gam_extras2 as g2
from ..pickers import OUField, PersonField
from ..tools_base import ToolTab
from ..widgets import ResultsTable, Worker, button
from .round11_pages import run_or_request
from .round13_tabs import _csv, _text, fill


def _scope(ou: OUField, person: PersonField | None = None) -> list[str]:
    if person is not None and "@" in person.email():
        return ["user", person.email()]
    p = ou.path() or "/"
    return ["all", "users"] if p == "/" else ["ou_and_children", p]


def _admin() -> str:
    from ... import google_io
    return google_io.admin_email()


def _spin(lo, hi, val, suffix=""):
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(int(val))
    s.setSuffix(suffix)
    return s


def _dicts(rows):
    return list(rows[0].keys()) if rows else ["(nothing found)"]


# ================================================================ Forms ===
class FormResponsesTab(ToolTab):
    intro = ("Read a Google Form's responses straight from Google – no linked Sheet needed. "
             "Choose the form's owner and paste the form link.")

    def build(self):
        self.owner = PersonField(self.directory, "Form owner")
        self.form = QLineEdit(placeholderText="form link or ID")
        self.lay.addLayout(self.row(self.owner, self.form,
                                    button("Show responses", "primary", self.load),
                                    button("Count only", slot=lambda: self.load(True)),
                                    self.status))
        self.table = ResultsTable()
        self.table.setMinimumHeight(360)
        self.lay.addWidget(self.table, 1)

    def load(self, counts=False):
        o, f = self.owner.email(), self.form.text().strip()
        if "@" not in o or not f:
            self.info("Choose the owner and the form.")
            return

        def got(rows):
            if rows is None:
                return
            items = rows if counts else g2.form_responses(rows)
            fill(self.table, items, _dicts(items))
            self.status.setText(f"{len(items):,} row(s)")
        self.read(g2.form_responses_args(o, f, counts), got)


# =============================================================== Wi-Fi ===
class WifiDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Chromebook Wi-Fi networks")
        self.resize(900, 620)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Wi-Fi networks pushed to Chromebooks in an org unit – for example a "
                           "testing site or a new wireless name. Check on a test org unit "
                           "first.", wordWrap=True))
        self.ou = OUField(page.directory, "/Chromebooks")
        self.status = QLabel("", objectName="Muted")
        v.addLayout(page.row(QLabel("Org unit"), self.ou, button("Show networks", slot=self.load),
                             self.status))
        self.table = ResultsTable()
        v.addWidget(self.table, 1)
        v.addLayout(page.row(button("Remove selected", "danger", self.remove)))
        box, form = page.group("Add a network")
        self.name = QLineEdit(placeholderText="e.g. District Testing")
        self.ssid = QLineEdit(placeholderText="network name (SSID)")
        self.sec = QComboBox()
        for label, val in g2.SECURITY.items():
            self.sec.addItem(label, val)
        self.pw = QLineEdit(placeholderText="password")
        self.pw.setEchoMode(QLineEdit.Password)
        self.auto = QCheckBox("Connect automatically")
        self.auto.setChecked(True)
        self.hidden = QCheckBox("Hidden network")
        self.js = QPlainTextEdit()
        self.js.setToolTip("The password is included here – it's hidden in the Output panel "
                           "and the activity log.")
        self.js.setMaximumHeight(90)
        for w in (self.ssid, self.pw):
            w.textChanged.connect(self._json)
        self.sec.currentIndexChanged.connect(self._json)
        self.auto.toggled.connect(self._json)
        self.hidden.toggled.connect(self._json)
        form.addRow("Name in the Admin console", self.name)
        form.addRow("SSID", self.ssid)
        form.addRow("Security", page.row(self.sec, self.pw, stretch=False))
        form.addRow("", page.row(self.auto, self.hidden))
        form.addRow("Settings (you can edit)", self.js)
        form.addRow("", page.row(button("Add network", "primary", self.add)))
        v.addWidget(box)
        self.items = []
        self._json()

    def _json(self, *_):
        self.js.setPlainText(g2.wifi_json(self.ssid.text().strip(), self.sec.currentData(),
                                          self.pw.text(), self.auto.isChecked(),
                                          self.hidden.isChecked()))

    def load(self):
        ou = self.ou.path() or "/"

        def done(res):
            c, rows, e = res
            self.items = g2.networks(rows) if c == 0 else []
            fill(self.table, self.items, ["Name", "SSID", "Security", "Org unit",
                                          "Network ID"])
            self.status.setText(f"{len(self.items)} network(s)" if c == 0 else
                                (e or "")[-160:])
        Worker(lambda: _csv()(g2.networks_args(ou)), on_done=done,
               on_error=lambda e: self.status.setText(str(e)))

    def add(self):
        ou, name = self.ou.path(), self.name.text().strip() or self.ssid.text().strip()
        if not ou or not self.ssid.text().strip():
            self.status.setText("Choose the org unit and fill in the SSID.")
            return
        if not self.page.confirm(f"Add Wi-Fi “{self.ssid.text()}” to Chromebooks in {ou}?"):
            return
        args = g2.network_create_args(ou, name, self.js.toPlainText())
        self.page.run(args, lambda *_: self.load())

    def remove(self):
        ids = self.table.selected_values("Network ID")
        ou = self.ou.path()
        if ids and self.page.confirm(f"Remove {len(ids)} network(s) from {ou}?"):
            self.page.run_many([g2.network_delete_args(ou, i) for i in ids],
                               lambda _o: self.load(), quiet=False)


# ======================================================== device tools ===
class DeviceToolsTab(ToolTab):
    intro = ("Check serial numbers before new Chromebooks arrive, see how many devices are "
             "active, look up what an app or extension can do, download a device's log "
             "files, and find printer models.")

    def build(self):
        box, form = self.page.group("Check serial numbers")
        self.sns = QPlainTextEdit()
        self.sns.setPlaceholderText("serial numbers, one per line or separated by commas")
        self.sns.setMaximumHeight(70)
        form.addRow(self.sns)
        form.addRow("", self.row(button("Check", "primary", self.check_serials),
                                 button("Active device counts", slot=self.counts)))
        self.lay.addWidget(box)
        box, form = self.page.group("App or extension details")
        self.app = QLineEdit(placeholderText="extension/app ID (32 letters) or Play package")
        self.kind = QComboBox()
        self.kind.addItems(["chrome", "android", "web"])
        form.addRow("App", self.row(self.app, self.kind, button("Look up", slot=self.app_info),
                                    stretch=False))
        self.lay.addWidget(box)
        box, form = self.page.group("Device log files")
        self.dsn = QLineEdit(placeholderText="serial number")
        form.addRow("Chromebook", self.row(self.dsn, button("Download files…",
                                                            slot=self.files), stretch=False))
        self.lay.addWidget(box)
        box, form = self.page.group("Printer models")
        self.make = QLineEdit(placeholderText="manufacturer, e.g. HP (optional)")
        form.addRow("", self.row(self.make, button("List models", slot=self.models),
                                 stretch=False))
        self.lay.addWidget(box)
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(280)
        self.lay.addWidget(self.table, 1)

    def _show(self, rows, cols=None):
        if rows is not None:
            fill(self.table, rows, cols or _dicts(rows))
            self.status.setText(f"{len(rows):,} row(s)")

    def check_serials(self):
        import re
        sns = [s.upper() for s in re.split(r"[\s,;]+", self.sns.toPlainText()) if s]
        if sns:
            self.read(g2.snvalidity_args(sns), lambda rows: self._show(
                g2.snvalidity(rows) if rows is not None else None,
                ["Serial", "Result", "Exact", "Similar"]))

    def counts(self):
        self.read(g2.device_counts_args("active"), self._show)

    def app_info(self):
        a = self.app.text().strip()
        if not a:
            return

        def done(res):
            c, out = res
            perms = g2.app_permissions(out)
            self.info((out or "")[:2500] + ("\n\nCan reach: " + ", ".join(perms) if perms
                                            else ""))
        Worker(lambda: _text()(g2.app_info_args(a, self.kind.currentText())), on_done=done,
               on_error=lambda e: self.info(str(e)))

    def files(self):
        sn = self.dsn.text().strip().upper()
        if not sn:
            return
        folder = QFileDialog.getExistingDirectory(self, "Save the device files in")
        if folder:
            self.page.run(g2.devicefile_args(sn, folder), lambda *_: QDesktopServices.openUrl(
                QUrl.fromLocalFile(folder)))

    def models(self):
        self.read(g2.printer_models_args(self.make.text().strip()), self._show)


# ===================================================== replace in meetings ===
def replace_box(tab, lay):
    box, form = tab.page.group("Replace someone in meetings")
    old = PersonField(tab.directory, "Who is leaving")
    new = PersonField(tab.directory, "Who takes their place")
    org = QLineEdit(placeholderText="whose meetings – organizers' emails, comma separated "
                                    "(e.g. the principal and the team leads)")
    form.addRow("Replace", old)
    form.addRow("With", new)
    form.addRow("In meetings organized by", org)

    def go():
        o, n = old.email(), new.email()
        orgs = [x.strip() for x in org.text().split(",") if "@" in x]
        if "@" not in o or "@" not in n or not orgs:
            tab.info("Fill in both people and at least one organizer.")
            return
        if tab.confirm(f"Replace {o} with {n} in every future meeting organized by "
                       f"{', '.join(orgs)}?"):
            tab.run_steps(tab.steps, [(f"Replace {o} with {n}",
                                       g2.replace_attendee_args(orgs, o, n))])
    form.addRow("", tab.row(button("Replace in future meetings", slot=go)))
    lay.addWidget(box)


# ============================================================ folder tools ===
class FolderToolsTab(ToolTab):
    intro = ("One folder or file at a time: hand it to someone else (instead of the whole "
             "Drive), see where it lives, read its comments (including deleted ones), how big "
             "a folder is, and find broken shortcuts.")

    def build(self):
        box, form = self.page.group("Folder or file")
        self.owner = PersonField(self.directory, "Current owner")
        self.item = QLineEdit(placeholderText="folder or file link / ID")
        form.addRow("Owner", self.owner)
        form.addRow("Item", self.item)
        form.addRow("", self.row(button("Where is it?", slot=self.path),
                                 button("Comments", slot=self.comments),
                                 button("Size", slot=self.size),
                                 button("Broken shortcuts", slot=self.shortcuts)))
        self.lay.addWidget(box)
        box, form = self.page.group("Hand it to someone else")
        self.new = PersonField(self.directory, "New owner")
        self.keep = QCheckBox("Old owner keeps edit access (when the new owner claims it)")
        self.keep.setChecked(True)
        form.addRow("New owner", self.new)
        form.addRow("", self.keep)
        form.addRow("", self.row(button("Preview", slot=lambda: self.transfer(True)),
                                 button("Transfer (old owner gives it)", "primary",
                                        self.transfer),
                                 button("Claim (new owner takes it)", slot=self.claim)))
        self.lay.addWidget(box)
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(260)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def _ok(self):
        if "@" not in self.owner.email() or not self.item.text().strip():
            self.info("Choose the owner and paste the folder or file link.")
            return False
        return True

    def _rows(self, args, conv=None):
        def got(rows):
            if rows is not None:
                items = conv(rows) if conv else rows
                fill(self.table, items, _dicts(items))
                self.status.setText(f"{len(items):,} row(s)")
        self.read(args, got)

    def path(self):
        if self._ok():
            self._rows(g2.filepath_args(self.owner.email(), self.item.text()))

    def comments(self):
        if self._ok():
            self._rows(g2.comments_args(self.owner.email(), self.item.text()), g2.comments)

    def size(self):
        if self._ok():
            self._rows(g2.diskusage_args(self.owner.email(), self.item.text()))

    def shortcuts(self):
        if self._ok():
            self._rows(g2.shortcut_args(self.owner.email(), self.item.text()))

    def transfer(self, preview=False):
        if not self._ok() or "@" not in self.new.email():
            return
        a = g2.transfer_args(self.owner.email(), self.item.text(), self.new.email(), preview)
        if preview:
            self._rows(a)
        elif self.confirm(f"Give {self.new.email()} ownership of this item and everything "
                          "in it?"):
            self.run_steps(self.steps, [("Transfer ownership", a)])

    def claim(self):
        if not self._ok() or "@" not in self.new.email():
            return
        if self.confirm(f"{self.new.email()} takes ownership of this item and everything "
                        "in it?"):
            self.run_steps(self.steps, [("Claim ownership", g2.claim_args(
                self.new.email(), self.item.text(), self.keep.isChecked()))])


# =========================================================== teacher status ===
class TeacherStatusTab(ToolTab):
    intro = ("Which teachers are verified in Classroom and can create classes, and how many "
             "active classes each teacher or student has.")

    def build(self):
        self.ou = OUField(self.directory, "/Staff")
        self.ou.set_path("/Staff")
        self.lay.addLayout(self.row(QLabel("Teachers in"), self.ou,
                                    button("Check teachers", "primary", self.profiles),
                                    button("Classes per teacher",
                                           slot=lambda: self.counts("teachers")),
                                    button("Classes per student",
                                           slot=lambda: self.counts("students")),
                                    self.status))
        self.table = ResultsTable()
        self.table.setMinimumHeight(360)
        self.lay.addWidget(self.table, 1)

    def profiles(self):
        self.read(g2.classroom_profile_args(_scope(self.ou)), lambda rows: rows is not None
                  and (fill(self.table, g2.teacher_status(rows), ["Person", "Verified teacher",
                                                                 "Can create classes"]),
                       self.status.setText(f"{len(rows):,} people")))

    def counts(self, kind):
        self.read(g2.course_counts_args(kind), lambda rows: rows is not None and (
            fill(self.table, g2.course_counts(rows), ["Person", "Active classes"]),
            self.status.setText(f"{len(rows):,} people")))


# ========================================================= guardian follow-up ===
class GuardianFollowupTab(ToolTab):
    intro = ("Re-send guardian invitations nobody answered, cancel ones sent to addresses that "
             "look wrong, and see acceptance by school and by teacher.")

    def build(self):
        from ... import guardian_followup as gf
        o = gf.options()
        self.root = OUField(self.directory, "/Students")
        self.root.set_path(o["root"])
        self.days = _spin(3, 120, o["days"], " days without an answer")
        self.weekly = QCheckBox("Do this automatically every Monday")
        self.weekly.setChecked(bool(o["weekly"]))
        self.lay.addLayout(self.row(QLabel("Students in"), self.root, self.days,
                                    button("Check", "primary", self.check)))
        self.lay.addLayout(self.row(self.weekly, self.status))
        self.plan_t = ResultsTable()
        self.plan_t.setMinimumHeight(200)
        self.lay.addWidget(self.plan_t)
        self.lay.addLayout(self.row(button("Re-send and cancel the selected (or all)",
                                           "primary", self.apply)))
        self.schools = ResultsTable()
        self.schools.setMinimumHeight(160)
        self.lay.addWidget(self.schools)
        self.teachers = ResultsTable()
        self.teachers.setMinimumHeight(160)
        self.lay.addWidget(self.teachers)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.items = []

    def check(self):
        from ... import guardian_followup as gf
        from ... import guardians, teacher_lists
        o = {**gf.options(), "root": self.root.path() or "/Students",
             "days": self.days.value(), "weekly": self.weekly.isChecked()}
        gf.save_options(o)
        users = self.directory.users

        def work():
            c, out = _text()(["ou_and_children", o["root"], "print", "guardians", "all",
                              "showstudentemails"], 3600)
            if c != 0:
                raise RuntimeError((out or "")[-200:])
            cur = guardians.parse_current(out)
            c2, parts, _e = _csv()(teacher_lists.PARTICIPANTS_ARGS)
            t, s, _n = teacher_lists.rosters(parts) if c2 == 0 else ({}, {}, {})
            resend, cancel = gf.plan(cur, o["days"], max_resends=int(o["max_resends"]))
            return resend, cancel, gf.acceptance(cur, users, o["root"], t, s)

        def done(res):
            resend, cancel, (bys, byt) = res
            self.items = [{**r, "Action": "Re-send"} for r in resend] + \
                [{**c, "Action": "Cancel"} for c in cancel]
            fill(self.plan_t, self.items, ["Action", "Student", "Guardian", "Invited",
                                           "Why"])
            fill(self.schools, bys, ["School", "Students", "Accepted", "Waiting",
                                     "None invited", "Accepted %"])
            fill(self.teachers, byt, ["Teacher", "Students", "Accepted", "Waiting",
                                      "None invited", "Accepted %"])
            self.status.setText(f"{len(resend)} to re-send · {len(cancel)} to cancel")
        self.status.setText("Reading guardians and rosters…")
        Worker(work, on_done=done, on_error=lambda e: (self.status.setText(""),
                                                       self.info(str(e))))

    def apply(self):
        from ... import guardian_followup as gf
        sel = self.plan_t.selected_dicts()
        keys = {(r["Student"], r["Guardian"]) for r in sel}
        items = [i for i in self.items if not keys or (i["Student"], i["Guardian"]) in keys]
        steps = [(f"{i['Action']}: {i['Guardian']} for {i['Student']}", a) for i in items
                 for a in i["args"]]
        if steps and self.confirm(f"Run {len(steps)} step(s)?"):
            self.run_steps(self.steps, steps, lambda _s: gf.note_resent(
                [i for i in items if i["Action"] == "Re-send"]))


# ========================================================== trusted domains ===
class TrustedDomainsTab(ToolTab):
    intro = ("Domains your users may share with and join classes from (allowlisted domains) – "
             "for example a neighboring district or a dual-credit college. Sharing settings "
             "in the Admin console decide who can use the list.")

    def build(self):
        self.lay.addLayout(self.row(button("Show", "primary", self.load), self.status))
        self.table = ResultsTable()
        self.table.setMinimumHeight(240)
        self.lay.addWidget(self.table, 1)
        self.new = QLineEdit(placeholderText="partner.edu, college.edu")
        self.lay.addLayout(self.row(self.new, button("Add", slot=self.add),
                                    button("Remove selected", "danger", self.remove)))

    def load(self):
        self.read(g2.ALLOWLIST_ARGS, lambda rows: rows is not None and (
            fill(self.table, g2.allowlist(rows), ["Domain", "id"]),
            self.status.setText(f"{len(rows)} domain(s)")))

    def add(self):
        doms = [d.strip() for d in self.new.text().split(",") if "." in d]
        if doms and self.confirm(f"Trust {', '.join(doms)}?"):
            self.page.run(g2.allowlist_add_args(doms), lambda *_: self.load())

    def remove(self):
        ids = self.table.selected_values("id")
        if ids and self.confirm(f"Remove {len(ids)} domain(s)?"):
            self.page.run(g2.allowlist_delete_args(ids), lambda *_: self.load())


# ============================================================== photo export ===
class PhotoExportTab(ToolTab):
    intro = ("Save everyone's profile photo as <email>.jpg – for an ID-card, library or "
             "yearbook system.")

    def build(self):
        self.ou = OUField(self.directory, "/Students")
        self.lay.addLayout(self.row(QLabel("People in"), self.ou,
                                    button("Choose folder and export…", "primary", self.go),
                                    self.status))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def go(self):
        folder = QFileDialog.getExistingDirectory(self, "Save photos in")
        if folder:
            self.run_steps(self.steps, [("Export photos", g2.photo_export_args(
                _scope(self.ou), folder))], lambda _s: QDesktopServices.openUrl(
                QUrl.fromLocalFile(folder)))


# ============================================================ chat moderation ===
class ChatModerationTab(ToolTab):
    intro = ("Every Chat space in the district (as an admin): who is in it, whether outsiders "
             "are allowed, remove someone, or delete a space.")

    def build(self):
        self.lay.addLayout(self.row(button("List spaces", "primary", self.load),
                                    button("Members of selected", slot=self.members),
                                    self.status))
        self.table = ResultsTable()
        self.table.setMinimumHeight(240)
        self.lay.addWidget(self.table, 1)
        self.who = PersonField(self.directory, "Person to remove from the selected space")
        self.lay.addLayout(self.row(self.who, button("Remove from space", slot=self.remove),
                                    button("Delete selected space…", "danger",
                                           self.delete)))
        self.members_t = ResultsTable()
        self.members_t.setMinimumHeight(180)
        self.lay.addWidget(self.members_t)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def load(self):
        self.read(g2.chat_spaces_admin_args(_admin()), lambda rows: rows is not None and (
            fill(self.table, g2.chat_spaces(rows), ["Space", "Type", "External", "Members",
                                                   "Created", "name"]),
            self.status.setText(f"{len(rows)} space(s)")))

    def _space(self):
        s = self.table.selected_values("name")
        if not s:
            self.info("Select a space.")
        return s[0] if s else ""

    def members(self):
        sp = self._space()
        if sp:
            self.read(g2.chat_members_admin_args(_admin(), sp), lambda rows: rows is not None
                      and fill(self.members_t, rows, _dicts(rows)))

    def remove(self):
        sp, who = self._space(), self.who.email()
        if sp and "@" in who and self.confirm(f"Remove {who} from this space?"):
            self.run_steps(self.steps, [(f"Remove {who}",
                                         g2.chat_remove_member_args(_admin(), sp, who))])

    def delete(self):
        sp = self._space()
        if sp:
            run_or_request(self.page, self.steps, [(f"Delete {sp}", g2.chat_delete_space_args(
                _admin(), sp))], "Delete a Chat space", "Chat moderation")


# ============================================================ gmail language ===
class GmailLanguageTab(ToolTab):
    intro = "Set the language Gmail shows its menus in – for one person or a whole org unit."

    def build(self):
        self.person = PersonField(self.directory, "One person (or leave empty)")
        self.ou = OUField(self.directory, "…or an org unit")
        self.lang = QComboBox()
        for label, code in g2.LANGUAGES:
            self.lang.addItem(label, code)
        self.lay.addLayout(self.row(self.person, self.ou, stretch=False))
        self.lay.addLayout(self.row(self.lang, button("Set language", "primary", self.set),
                                    button("Show current", slot=self.show), self.status))
        self.table = ResultsTable()
        self.table.setMinimumHeight(260)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def set(self):
        sc = _scope(self.ou, self.person)
        if self.confirm(f"Set Gmail to {self.lang.currentText()} for {' '.join(sc)}?"):
            self.run_steps(self.steps, [("Set language", g2.language_args(
                sc, self.lang.currentData()))])

    def show(self):
        self.read(g2.language_show_args(_scope(self.ou, self.person)),
                  lambda rows: rows is not None and fill(self.table, rows, _dicts(rows)))


# ========================================================= premium licenses ===
class PremiumLicensesTab(ToolTab):
    intro = ("Who holds Teaching and Learning or Education Plus licenses and whether they used "
             "a premium feature lately (Meet over 100 people, live streams, originality "
             "reports). Holders who didn't can be released – through Approvals.")

    def build(self):
        from ... import license_rightsize as lr
        o = lr.options()
        self.days = _spin(14, 365, o["days"], " days")
        self.big = _spin(25, 1000, o["big_meeting"], " people = big meeting")
        self.keep = QLineEdit(o["keep"])
        self.keep.setPlaceholderText("always keep (emails, comma separated)")
        self.lay.addLayout(self.row(QLabel("Look back"), self.days, self.big,
                                    button("Check", "primary", self.check)))
        self.lay.addLayout(self.row(QLabel("Keep"), self.keep, self.status))
        self.summary = ResultsTable()
        self.summary.setMinimumHeight(120)
        self.lay.addWidget(self.summary)
        self.table = ResultsTable()
        self.table.setMinimumHeight(260)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(button("Release selected (send for approval)", "primary",
                                           self.release)))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.rows = []

    def check(self):
        from ... import license_rightsize as lr
        from ...tools import budget
        o = {**lr.options(), "days": self.days.value(), "big_meeting": self.big.value(),
             "keep": self.keep.text()}
        lr.save_options(o)

        def work():
            run = _csv()
            c, users, e = run(budget.USERS_ARGS)
            if c != 0:
                raise RuntimeError((e or "")[-200:])
            _c, meet, _e = run(lr.meet_args(o["days"]))
            _c2, cls, _e2 = run(lr.classroom_args(o["days"]))
            use = lr.premium_use(meet if _c == 0 else [], cls if _c2 == 0 else [],
                                 o["big_meeting"])
            return lr.suggest(budget.license_holders(users), use, o)

        def done(res):
            summ, self.rows = res
            fill(self.summary, summ, ["License", "Held", "Used premium features",
                                      "Could release"])
            fill(self.table, self.rows, ["Person", "Org unit", "License", "Last sign-in",
                                         "Premium use"])
            self.status.setText(f"{len(self.rows)} could be released")
        self.status.setText("Reading licenses and usage…")
        Worker(work, on_done=done, on_error=lambda e: (self.status.setText(""),
                                                       self.info(str(e))))

    def release(self):
        sel = {(r["Person"], r["License"]) for r in self.table.selected_dicts()}
        steps = [(f"Release {r['License']} from {r['Person']}", r["args"]) for r in self.rows
                 if (r["Person"], r["License"]) in sel]
        run_or_request(self.page, self.steps, steps, "Release premium licenses",
                       "No premium feature use seen")


# ========================================================== public apps list ===
class PublicAppsTab(ToolTab):
    intro = ("A parent-facing list of the apps students sign in to with their school account, "
             "with approval and data-privacy agreement status from your approved list "
             "(add Purpose, DPA and Privacy columns to it). Publish it as a Google Sheet or a "
             "web page for the district website.")

    def build(self):
        from ... import apps_public as ap
        o = ap.options()
        self.root = OUField(self.directory, "/Students")
        self.root.set_path(o["root"])
        self.min = _spin(1, 1000, o["min_students"], " or more students")
        self.denied = QCheckBox("Include apps that aren't approved (marked as being removed)")
        self.denied.setChecked(bool(o["include_denied"]))
        self.title = QLineEdit(o["title"])
        self.contact = QLineEdit(o["contact"])
        self.contact.setPlaceholderText("contact for questions, e.g. privacy@district.org")
        box, form = self.page.group("Settings")
        form.addRow("Students in", self.root)
        form.addRow("Apps used by", self.min)
        form.addRow("", self.denied)
        form.addRow("Title", self.title)
        form.addRow("Contact", self.contact)
        form.addRow("", self.row(button("Build the list", "primary", self.build_list),
                                 button("Save as a web page…", slot=self.save_html),
                                 button("Make a Google Sheet", slot=self.sheet), self.status))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.rows = []

    def _opts(self):
        from ... import apps_public as ap
        o = {**ap.options(), "root": self.root.path() or "/Students",
             "min_students": self.min.value(), "include_denied": self.denied.isChecked(),
             "title": self.title.text().strip() or "Apps used with student accounts",
             "contact": self.contact.text().strip()}
        ap.save_options(o)
        return o

    def build_list(self):
        from ... import apps_public as ap
        from ...tools import app_vetting as av
        o = self._opts()
        users = self.directory.users

        def got(rows):
            if rows is None:
                return
            approved = av.load_list()
            self.rows = ap.build(av.summarize(rows, approved, users, o["root"]), approved, o)
            fill(self.table, self.rows, ap.COLUMNS)
            self.status.setText(f"{len(self.rows)} app(s)")
        self.read(av.tokens_args("ou", o["root"]), got, "Reading connected apps…")

    def save_html(self):
        from ... import apps_public as ap
        if not self.rows:
            self.info("Build the list first.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Save", "student-apps.html", "*.html")
        if p:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(ap.to_html(self.rows, self._opts(),
                                    settings.get("auditreport/district", "") or ""))
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def sheet(self):
        from ... import apps_public as ap
        from ... import google_io
        if not self.rows:
            self.info("Build the list first.")
            return
        path = os.path.join(_tf.folder(), "student-apps.csv")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(ap.to_csv(self.rows))
        Worker(google_io.upload_csv_as_sheet, path, self._opts()["title"],
               on_done=lambda url: (self.status.setText("Sheet made – share it view-only."),
                                    url and QDesktopServices.openUrl(QUrl(url))),
               on_error=lambda e: self.info(str(e)))


# ========================================================== shared passwords ===
class SharedPasswordsTab(ToolTab):
    intro = ("Student accounts signed in on many Chromebooks, on several networks in one day, "
             "or from different places minutes apart – a sign the password is shared (or "
             "stolen). Carts and loaners are ignored.")

    def build(self):
        from ...tools import shared_accounts as sa
        o = sa.options()
        self.root = OUField(self.directory, "/Students")
        self.root.set_path(o["root"])
        self.devs = _spin(2, 50, o["devices"], " or more Chromebooks")
        self.ips = _spin(2, 50, o["ips"], " or more networks a day")
        self.ignore = QLineEdit(o["ignore_ous"])
        box, form = self.page.group("What counts")
        form.addRow("Students in", self.root)
        form.addRow("Signed in on", self.devs)
        form.addRow("Signed in from", self.ips)
        form.addRow("Ignore devices whose org unit/location has", self.ignore)
        form.addRow("", self.row(button("Check the last 7 days", "primary", self.check),
                                 self.status))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(button("Require a new password for selected", "primary",
                                           self.reset)))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def check(self):
        from ...tools import shared_accounts as sa
        o = {**sa.options(), "root": self.root.path() or "/Students",
             "devices": self.devs.value(), "ips": self.ips.value(),
             "ignore_ous": self.ignore.text()}
        sa.save_options(o)
        users = self.directory.users

        def work():
            run = _csv()
            c, drows, e = run(sa.DEVICES_ARGS)
            if c != 0:
                raise RuntimeError((e or "")[-200:])
            c2, lrows, _e = run(sa.login_args(o["days"]))
            return sa.flag(users, sa.device_spread(drows, o),
                           sa.login_spread(lrows if c2 == 0 else [], o["window_min"]), o)

        def done(rows):
            fill(self.table, rows, ["Student", "Org unit", "Signs", "What we see",
                                    "Chromebooks"])
            self.status.setText(f"{len(rows)} student(s)")
        self.status.setText("Reading Chromebooks and sign-ins…")
        Worker(work, on_done=done, on_error=lambda e: (self.status.setText(""),
                                                       self.info(str(e))))

    def reset(self):
        sel = self.table.selected_values("Student")
        if sel and self.confirm(f"Require {len(sel)} student(s) to choose a new password at "
                                "next sign-in?"):
            self.run_steps(self.steps, [(f"New password needed: {e}",
                                         ["update", "user", e, "changepassword", "on"])
                                        for e in sel])


# ========================================================== battery forecast ===
class BatteryForecastTab(ToolTab):
    intro = ("Predicts when each Chromebook's battery falls below your replacement level, "
             "from the trend in its battery reports – then builds an order list by school and "
             "model. (Needs Chrome device telemetry reporting turned on.)")

    def build(self):
        from ...tools import battery_forecast as bf
        o = bf.options()
        self.ou = OUField(self.directory, "/Chromebooks")
        self.ou.set_path(o["ou"])
        self.at = _spin(30, 95, o["replace_at"], " % = replace")
        self.by = QLineEdit(o["by"])
        self.by.setPlaceholderText("replace by (YYYY-MM-DD, default end of school year)")
        self.cost = QDoubleSpinBox()
        self.cost.setRange(0, 1000)
        self.cost.setValue(float(o["battery_cost"]))
        self.cost.setPrefix("$")
        self.cost.setSuffix(" per battery")
        self.lay.addLayout(self.row(QLabel("Chromebooks under"), self.ou, self.at, self.by,
                                    self.cost))
        self.lay.addLayout(self.row(button("Forecast", "primary", self.run), self.status))
        self.order = ResultsTable()
        self.order.setMinimumHeight(150)
        self.lay.addWidget(self.order)
        self.table = ResultsTable()
        self.table.setMinimumHeight(260)
        self.lay.addWidget(self.table, 1)

    def run(self):
        from ...tools import battery_forecast as bf
        o = {**bf.options(), "ou": self.ou.path() or "/", "replace_at": self.at.value(),
             "by": self.by.text().strip(), "battery_cost": self.cost.value()}
        bf.save_options(o)

        def got(res):
            rows, cros = res
            if not rows:
                self.status.setText("No battery reports came back – check the org unit and "
                                    "the Output panel.")
                return
            fc = bf.forecast(bf.add_models(rows, cros), o)
            fill(self.order, bf.order_list(fc, o), ["School", "Model", "Batteries",
                                                    "Estimated cost"])
            fill(self.table, fc, ["Serial", "Model", "Org unit", "Battery now",
                                  "Change per month", "Below the line", "Replace by"])
            self.status.setText(f"{sum(1 for f in fc if f['due'])} of {len(fc)} need a "
                                "battery by then")
        self.read_many([bf.args(o["ou"], int(o["reports"])), bf.models_args(o["ou"])], got,
                       "Reading battery reports (can take a few minutes)…")


# ============================================================ repeat damage ===
class RepeatDamageTab(ToolTab):
    intro = ("Students with several Chromebook repairs over the years, from GAMbit's repair "
             "tickets and assignment history – for fee, insurance and loaner decisions.")

    def build(self):
        self.min = _spin(2, 20, 2, " or more repairs")
        self.years = _spin(1, 10, 4, " years")
        self.dmg = QCheckBox("Only damage (screens, spills, keyboards…)")
        self.dmg.setChecked(True)
        self.lay.addLayout(self.row(self.min, QLabel("in the last"), self.years, self.dmg,
                                    button("Build", "primary", self.run), self.status,
                                    stretch=False))
        self.schools = ResultsTable()
        self.schools.setMinimumHeight(130)
        self.lay.addWidget(self.schools)
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)

    def run(self):
        from ... import activity, fleet
        from ...tools import repeat_damage as rd
        tickets = fleet.load_list(fleet.data_dir(), "repairs.json")
        hist = rd.assignment_history(activity.load(3650, team=True))
        rows = rd.report(tickets, self.directory.users, self.min.value(),
                         self.dmg.isChecked(), self.years.value(), hist)
        fill(self.schools, rd.by_school(rows), ["School", "Students", "Repairs"])
        fill(self.table, rows, ["Student", "Name", "Org unit", "Repairs", "Devices", "Last",
                                "What happened", "Left"])
        self.status.setText(f"{len(rows)} student(s) from {len(tickets)} repair ticket(s)")


__all__ = ["FormResponsesTab", "WifiDialog", "DeviceToolsTab", "replace_box",
           "FolderToolsTab", "TeacherStatusTab", "GuardianFollowupTab", "TrustedDomainsTab",
           "PhotoExportTab", "ChatModerationTab", "GmailLanguageTab", "PremiumLicensesTab",
           "PublicAppsTab", "SharedPasswordsTab", "BatteryForecastTab", "RepeatDamageTab"]
