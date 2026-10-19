"""Drive → Move to a shared drive, Keep notes;  Users → Directory details;  Staff devices
page;  Usage page;  Chromebook fleet → OS versions;  Email → Archive to a group;
More services → Shared contacts;  Groups → everyone who gets a group's mail."""

from __future__ import annotations

import csv
import io
import os

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QLabel, QLineEdit, QSpinBox, QTabWidget,
    QVBoxLayout,
)

from ...settings import settings
from ...tools import more_tools as mt
from ..pickers import GroupField, OUField, PersonField
from ..tools_base import ToolTab
from ..widgets import Page, ResultsTable, button


def _folder_id(text: str) -> str:
    from ...tools.drive_extra import file_ids
    ids = file_ids(text)
    return ids[0] if ids else ""


# ========================================================= shared drives ===
class SharedDriveMoveTab(ToolTab):
    intro = ("Move a folder from someone's My Drive into a shared drive (keeping its folders), "
             "or copy a whole folder tree to another person – for example a curriculum folder "
             "for a new teacher.")

    def build(self):
        box, form = self.page.group("Move a folder into a shared drive")
        self.m_user = PersonField(self.directory, "Who owns the folder?")
        self.m_folder = QLineEdit(placeholderText="Folder link or ID")
        self.m_drive = QComboBox()
        self.m_drive.setEditable(True)
        self.m_drive.setMinimumWidth(320)
        self.m_sub = QLineEdit(placeholderText="optional folder inside the shared drive")
        form.addRow("Owner", self.m_user)
        form.addRow("Folder", self.m_folder)
        form.addRow("Shared drive", self.row(self.m_drive, button(
            "Load shared drives", slot=self._drives), stretch=False))
        form.addRow("Into folder", self.m_sub)
        note = QLabel("The owner must be a Manager of the shared drive. Files they don't own "
                      "can't be moved – a shortcut is left in their place.", objectName="Muted")
        note.setWordWrap(True)
        form.addRow("", note)
        form.addRow("", self.row(button("Move it", "primary", self.move)))
        self.lay.addWidget(box)

        box, form = self.page.group("Copy a folder tree to someone")
        self.c_owner = PersonField(self.directory, "Who owns the folder?")
        self.c_folder = QLineEdit(placeholderText="Folder link or ID")
        self.c_to = PersonField(self.directory, "Copy to (they become the owner of the copy)")
        self.c_name = QLineEdit(placeholderText="optional new name, e.g. 3rd Grade Curriculum")
        self.c_share = QCheckBox("Let them view the original first (needed to copy it)")
        self.c_share.setChecked(True)
        form.addRow("Owner", self.c_owner)
        form.addRow("Folder", self.c_folder)
        form.addRow("Copy to", self.c_to)
        form.addRow("New name", self.c_name)
        form.addRow("", self.c_share)
        form.addRow("", self.row(button("Copy it", "primary", self.copy)))
        self.lay.addWidget(box)
        self.lay.addWidget(self.status)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.lay.addStretch(1)

    def _drives(self):
        def done(rows):
            if rows is None:
                return
            self.m_drive.clear()
            for name, did in mt.shared_drives(rows):
                self.m_drive.addItem(name, did)
            self.status.setText(f"{self.m_drive.count()} shared drive(s)")
        self.read(["print", "shareddrives", "fields", "id,name"], done)

    def move(self):
        user, fid = self.m_user.email(), _folder_id(self.m_folder.text())
        did = self.m_drive.currentData() or self.m_drive.currentText().strip()
        if "@" not in user or not fid or not did:
            self.info("Fill in the owner, the folder and the shared drive.")
            return
        if self.confirm(f"Move this folder into “{self.m_drive.currentText()}”?\n\nPeople who "
                        "had access keep it through the shared drive's members and the copied "
                        "folder sharing."):
            self.run_steps(self.steps, [("Move folder into shared drive",
                                         mt.move_to_shared_drive_args(user, fid, did,
                                                                      self.m_sub.text().strip()))])

    def copy(self):
        owner, fid, to = self.c_owner.email(), _folder_id(self.c_folder.text()), self.c_to.email()
        if "@" not in owner or not fid or "@" not in to:
            self.info("Fill in the owner, the folder and who to copy it to.")
            return
        if self.confirm(f"Copy the whole folder into {to}'s My Drive?"):
            self.run_steps(self.steps, mt.copy_folder_steps(owner, fid, to,
                                                            self.c_name.text().strip(),
                                                            self.c_share.isChecked()))


# ======================================================= directory details ===
class DirectoryDetailsTab(ToolTab):
    intro = ("Keep the staff directory right from your HR sheet: manager, work and mobile "
             "phone, building, floor and room, job title and department. Columns are matched "
             "by name (Email or Employee ID, Supervisor, Phone, Building, Floor, Room, Title, "
             "Department). Buildings must exist (More services → Calendar → rooms import).")

    def build(self):
        self.src = QLineEdit(settings.get("dir/src", "") or "")
        self.src.setPlaceholderText("HR export (.csv) or a Google Sheet link")
        self.lay.addLayout(self.row(self.src, button("Browse…", slot=self._browse),
                                    button("Compare with Google", "primary", self.preview),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(340)
        self.lay.addWidget(self.table, 1)
        self.apply_btn = button("Update the selected people (or everyone)", "primary",
                                self.apply)
        self.apply_btn.setEnabled(False)
        self.lay.addLayout(self.row(self.apply_btn))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.plan = []

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "HR export", "", "CSV (*.csv)")
        if p:
            self.src.setText(p)

    def preview(self):
        src = self.src.text().strip()
        if not src:
            self.info("Choose the HR export or paste a Google Sheet link.")
            return
        settings.set("dir/src", src)
        if src.startswith("http"):
            from ... import google_io
            from ..widgets import Worker
            self.status.setText("Downloading the sheet…")
            Worker(google_io.download_sheet, src, on_done=self._got_file,
                   on_error=lambda e: self.status.setText(f"Couldn't download it: {e}"))
        elif os.path.isfile(src):
            self._got_file(src)
        else:
            self.info("That file isn't there.")

    def _got_file(self, path):
        with open(path, encoding="utf-8-sig") as fh:
            sheet = list(csv.DictReader(fh))
        if not sheet:
            self.info("The sheet is empty.")
            return
        mapping = mt.dir_mapping(list(sheet[0].keys()))
        if not (mapping["email"] or mapping["id"]):
            self.info("The sheet needs an Email or Employee ID column.")
            return

        def done(res):
            users, buildings = res
            bids = {}
            for b in buildings:
                low = {(k or "").lower(): v for k, v in b.items()}
                if low.get("buildingid"):
                    bids[low.get("buildingname", "")] = low["buildingid"]
                    bids[low["buildingid"]] = low["buildingid"]
            self.plan = mt.dir_plan(sheet, mapping, mt.current_details(users),
                                    self.directory.domain or "", bids)
            self.table.set_rows(["Person", "Changes"], [[p["email"], p["changes"]]
                                                        for p in self.plan])
            n = sum(1 for p in self.plan if p["args"])
            used = ", ".join(f"{k}={v}" for k, v in mapping.items() if v)
            self.status.setText(f"{n} people to update · columns used: {used}")
            self.apply_btn.setEnabled(n > 0)
        self.read_many([["print", "users", "fields", ",".join(mt.DIR_FIELDS)],
                        ["print", "buildings"]], done, "Reading the directory…")

    def apply(self):
        sel = {r["Person"] for r in self.table.selected_dicts()}
        todo = [p for p in self.plan if p["args"] and (not sel or p["email"] in sel)]
        if todo and self.confirm(f"Update directory details for {len(todo)} people?"):
            self.run_steps(self.steps, [(f"{p['email']}: {p['changes'][:60]}", p["args"])
                                        for p in todo])


# ============================================================ staff devices ===
class StaffDevicesPage(Page):
    title = "Staff devices"
    subtitle = ("Windows laptops, Macs, iPhones and Android phones signed in to district "
                "accounts (Google endpoint management). Chromebooks are on their own pages.")

    def build(self):
        self.chromeos = QCheckBox("Include Chromebooks")
        self.status = QLabel("", objectName="Muted")
        self.body.addLayout(self.row(button("Load devices", "primary", self.load), self.chromeos,
                                     button("Chrome profiles on computers…",
                                            slot=self.chrome_profiles),
                                     button("Out-of-date Chrome…", slot=self.chrome_behind),
                                     self.status))
        self.table = ResultsTable()
        self.table.hidden_columns = {"Device", "Device user"}
        self.body.addWidget(self.table, 1)
        self.action = QComboBox()
        for label, val in (("Approve the account on it", "approve"),
                           ("Block the account on it", "block"),
                           ("Remove the district account from it (account wipe)", "wipeuser"),
                           ("Cancel an account wipe", "cancelwipeuser"),
                           ("Factory-reset the device (company-owned only)", "wipe"),
                           ("Cancel a device wipe", "cancelwipe"),
                           ("Remove it from the list", "delete")):
            self.action.addItem(label, val)
        self.body.addLayout(self.row(QLabel("For the selected devices:"), self.action,
                                     button("Do it", "danger", self.act)))
        from ..steps import StepList
        self.steps = StepList(self)
        self.steps.setMaximumHeight(150)
        self.body.addWidget(self.steps)

    def chrome_behind(self):
        from .round13_tabs import BrowserVersionsDialog
        BrowserVersionsDialog(self).exec()

    def chrome_profiles(self):
        from .recovery_tabs import ChromeProfilesDialog
        ChromeProfilesDialog(self).exec()

    def load(self):
        def done(code, out, _e):
            if code != 0:
                self.status.setText("GAM reported a problem – see the Output panel.")
                return
            rows = mt.devices(list(csv.DictReader(io.StringIO(out or ""))),
                              self.chromeos.isChecked())
            heads = ["Person", "Type", "Model", "Serial", "OS", "Owner", "Last sync", "Status",
                     "Encrypted", "Device", "Device user"]
            self.table.set_rows(heads, [[r[h] for h in heads] for r in rows])
            pend = sum(1 for r in rows if r["Status"] == "approval pending")
            self.status.setText(f"{len(rows):,} device(s)" + (f" · {pend} waiting for approval"
                                                               if pend else ""))
        self.status.setText("Loading devices…")
        self.runner.run(mt.DEVICE_ARGS, done, quiet_stdout=True)

    def act(self):
        rows = self.table.selected_dicts()
        if not rows:
            self.info("Select the device(s) first.")
            return
        a = self.action.currentData()
        if a in ("wipe",) and any(r["Owner"].lower() != "company" for r in rows):
            self.info("Only company-owned devices can be factory-reset. Use “Remove the "
                      "district account” for personal devices.")
            return
        if not self.confirm(f"{self.action.currentText()} for {len(rows)} device(s)?"):
            return
        from ..steps import Step
        steps = [Step(f"{self.action.currentText()}: {r['Person']} {r['Model']}",
                      mt.device_action_args(a, r)) for r in rows
                 if (r["Device user"] if a in ("approve", "block", "wipeuser", "cancelwipeuser")
                     else r["Device"])]
        self.steps.run(steps, lambda _s: (self.info(self.steps.summary()), self.load()))


# ===================================================================== usage ===
class TrendTab(ToolTab):
    intro = ("District-wide active users per app over the last months (weekly, from Google's "
             "usage reports, which run 2–3 days behind). Good for board reports and grants.")

    def build(self):
        self.months = QSpinBox()
        self.months.setRange(1, 12)
        self.months.setValue(6)
        self.months.setSuffix(" months")
        self.lay.addLayout(self.row(QLabel("Last"), self.months,
                                    button("Build", "primary", self.load), self.status,
                                    stretch=False))
        self.table = ResultsTable()
        self.table.setMinimumHeight(400)
        self.lay.addWidget(self.table, 1)

    def load(self):
        def got_params(rows):
            if rows is None:
                return
            params = mt.usage_params(rows)
            if not params:
                self.status.setText("Google didn't list any usage numbers.")
                return

            def done(rows2):
                if rows2 is not None:
                    h, data = mt.usage_table(rows2)
                    self.table.set_rows(h, data)
                    self.status.setText(f"{len(data)} week(s)")
            self.read(mt.usage_args(params, self.months.value()), done,
                      "Reading usage reports (a minute or two)…")
        self.read(["report", "usageparameters", "customer"], got_params)


class SchoolUsageTab(ToolTab):
    intro = ("The share of accounts at each school that signed in and used Gmail, Drive and "
             "Classroom in the last 30 days, plus Classroom activity per teacher.")

    def build(self):
        self.ou = OUField(self.directory, "/")
        self.ou.set_path("/")
        self.depth = QSpinBox()
        self.depth.setRange(1, 4)
        self.depth.setValue(2)
        self.lay.addLayout(self.row(QLabel("Accounts under"), self.ou,
                                    QLabel("Group by org-unit level"), self.depth,
                                    button("Build", "primary", self.load), stretch=False))
        self.lay.addWidget(self.status)
        self.t_school = ResultsTable()
        self.t_teach = ResultsTable()
        self.t_school.setMinimumHeight(220)
        self.t_teach.setMinimumHeight(260)
        self.lay.addWidget(QLabel("<b>By school</b>"))
        self.lay.addWidget(self.t_school)
        self.lay.addWidget(QLabel("<b>Classroom by teacher</b>"))
        self.lay.addWidget(self.t_teach, 1)

    def load(self):
        def done(rows):
            if rows is None:
                return
            s = mt.school_usage(rows, self.directory.users, self.depth.value())
            h = list(s[0].keys()) if s else ["(no data)"]
            self.t_school.set_rows(h, [[r[k] for k in h] for r in s])
            t = mt.teacher_classroom(rows)
            h = list(t[0].keys()) if t else ["(no teachers found)"]
            self.t_teach.set_rows(h, [[r[k] for k in h] for r in t])
            self.status.setText(f"{len(rows):,} account(s)")
        self.read(mt.users_report_args(self.ou.path() or "/"), done,
                  "Reading per-account usage (large districts: a few minutes)…")


class UsagePage(Page):
    title = "Usage"
    subtitle = "How much Google Workspace is used across the district and in each school."

    def build(self):
        self.tabs = QTabWidget()
        self.trend = TrendTab(self)
        self.schools = SchoolUsageTab(self)
        self.tabs.addTab(self.trend, "District trend")
        self.tabs.addTab(self.schools, "By school and teacher")
        self.body.addWidget(self.tabs, 1)


# ============================================================== OS versions ===
class VersionsTab(ToolTab):
    intro = ("Which ChromeOS versions your Chromebooks run, newest first – devices several "
             "versions behind usually need a restart, an update policy fix, or have reached "
             "their end of updates.")

    def build(self):
        self.ou = OUField(self.directory, "/")
        self.ou.set_path("/")
        self.lay.addLayout(self.row(QLabel("Chromebooks under"), self.ou,
                                    button("Show versions", "primary", self.load), self.status,
                                    stretch=False))
        self.table = ResultsTable()
        self.table.setMinimumHeight(360)
        self.lay.addWidget(self.table, 1)

    def load(self):
        def done(rows):
            if rows is not None:
                v = mt.versions(rows)
                h = ["Version", "Channel", "Devices", "Share", "Behind"]
                self.table.set_rows(h, [[r[k] for k in h] for r in v])
                self.status.setText(f"{len(v)} version(s)")
        self.read(mt.versions_args(self.ou.path() or "/"), done)


# ===================================================================== keep ===
class KeepTab(ToolTab):
    intro = ("Google Keep notes aren't moved by a Drive transfer. List a person's notes and "
             "share them with someone else (for example a leaver's supervisor).")

    def build(self):
        self.who = PersonField(self.directory, "Whose notes?")
        self.to = PersonField(self.directory, "Share with")
        self.lay.addLayout(self.row(self.who, button("List notes", "primary", self.load),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.hidden_columns = {"ID"}
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(QLabel("Share the selected notes (or all) with"), self.to,
                                    button("Share", "primary", self.share), stretch=False))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def load(self):
        u = self.who.email()
        if "@" not in u:
            self.info("Pick the person first.")
            return

        def done(rows):
            if rows is not None:
                n = mt.notes(rows)
                self.table.set_rows(["Note", "Updated", "ID"],
                                    [[x["Note"], x["Updated"], x["ID"]] for x in n])
                self.status.setText(f"{len(n)} note(s)")
        self.read(mt.notes_args(u), done)

    def share(self):
        u, to = self.who.email(), self.to.email()
        sel = self.table.selected_dicts() or [self.table.row_dict(i)
                                              for i in range(self.table.row_count())]
        names = [r["ID"] for r in sel if r.get("ID")]
        if "@" not in u or "@" not in to or not names:
            self.info("List the notes and pick who to share them with.")
            return
        if self.confirm(f"Share {len(names)} note(s) with {to}?"):
            self.run_steps(self.steps, [(f"Share {len(names)} note(s) with {to}",
                                         mt.share_notes_args(u, names, to))])


# =============================================================== archive mail ===
class ArchiveTab(ToolTab):
    intro = ("Copy someone's email into a Google Group's archive, so the department keeps the "
             "history after their account is deleted. The mailbox itself isn't changed. Large "
             "mailboxes take hours – this runs in the background.")

    def build(self):
        box, form = self.page.group("Archive")
        self.who = PersonField(self.directory, "Whose email?")
        self.group = GroupField(self.directory, "Archive group, e.g. staff-archive@…")
        self.query = QLineEdit("-in:chats")
        self.make = QCheckBox("Create the group first as an archive-only group (nobody can "
                              "email it; only managers can read it)")
        form.addRow("Mailbox", self.who)
        form.addRow("Into group", self.group)
        form.addRow("Which messages", self.query)
        form.addRow("", QLabel("Gmail search, e.g. “-in:chats after:2020/01/01” or "
                               "“label:IEP”.", objectName="Muted"))
        form.addRow("", self.make)
        form.addRow("", self.row(button("Copy into the group", "primary", self.go)))
        self.lay.addWidget(box)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.lay.addStretch(1)

    def go(self):
        u, g = self.who.email(), self.group.email()
        if "@" not in u or "@" not in g:
            self.info("Pick the mailbox and the archive group.")
            return
        steps = []
        if self.make.isChecked():
            steps.append((f"Create archive group {g}",
                          ["create", "group", g, "name", f"Mail archive – {u.split('@')[0]}",
                           "archiveonly", "true", "isarchived", "true",
                           "whocanviewgroup", "ALL_MANAGERS_CAN_VIEW",
                           "whocanpostmessage", "NONE_CAN_POST"]))
        steps.append((f"Copy {u}'s email into {g}",
                      ["user", u, "archive", "messages", g, "query",
                       self.query.text().strip() or "-in:chats", "doit"]))
        if self.confirm(f"Copy {u}'s email into {g}?"):
            self.run_steps(self.steps, steps)


# ========================================================== shared contacts ===
class ContactsTab(ToolTab):
    intro = ("Domain shared contacts appear in everyone's Gmail autocomplete and the "
             "directory – vendors, district offices, substitutes. Add them from a CSV "
             "(Name, Email, Phone, Organization, Title, Notes).")

    def build(self):
        self.src = QLineEdit(placeholderText="contacts.csv")
        self.lay.addLayout(self.row(self.src, button("Browse…", slot=self._browse),
                                    button("Save a blank template…", slot=self._template),
                                    button("Preview", "primary", self.preview),
                                    button("List current shared contacts", slot=self.list_now),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(320)
        self.lay.addWidget(self.table, 1)
        self.apply_btn = button("Add new contacts", "primary", self.apply)
        self.apply_btn.setEnabled(False)
        self.lay.addLayout(self.row(self.apply_btn))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.plan = []

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Contacts", "", "CSV (*.csv)")
        if p:
            self.src.setText(p)

    def _template(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save template", "contacts.csv", "CSV (*.csv)")
        if p:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(mt.CONTACT_TEMPLATE)
            self.src.setText(p)

    def list_now(self):
        self.read(mt.CONTACTS_ARGS, lambda rows: rows is not None and self.table.set_rows(
            list(rows[0].keys()) if rows else ["(no shared contacts)"],
            [list(r.values()) for r in rows]))

    def preview(self):
        try:
            with open(self.src.text().strip(), encoding="utf-8-sig") as fh:
                wanted = mt.contacts_from_csv(fh.read())
        except OSError:
            self.info("Choose the contacts file first.")
            return

        def done(rows):
            if rows is None:
                return
            self.plan = mt.contact_plan(wanted, rows)
            self.table.set_rows(["Change", "Contact"], [[p["action"], p["name"]]
                                                       for p in self.plan])
            n = sum(1 for p in self.plan if p["args"])
            self.status.setText(f"{len(self.plan)} contact(s) · {n} new")
            self.apply_btn.setEnabled(n > 0)
        self.read(mt.CONTACTS_ARGS, done)

    def apply(self):
        todo = [p for p in self.plan if p["args"]]
        if todo and self.confirm(f"Add {len(todo)} shared contact(s)?"):
            self.run_steps(self.steps, [(f"Add {p['name']}", p["args"]) for p in todo])


# ======================================================= group: everyone ===
class EveryoneDialog(QDialog):
    def __init__(self, page, group: str):
        super().__init__(page)
        self.setWindowTitle(f"Everyone who gets {group}'s email")
        self.resize(760, 560)
        v = QVBoxLayout(self)
        self.status = QLabel("Expanding groups inside groups…", objectName="Muted")
        v.addWidget(self.status)
        self.table = ResultsTable()
        v.addWidget(self.table, 1)

        def done(code, out, _e):
            if code != 0:
                self.status.setText("GAM reported a problem – see the Output panel.")
                return
            rows = list(csv.DictReader(io.StringIO(out or "")))
            heads = list(rows[0].keys()) if rows else ["(no members)"]
            self.table.set_rows(heads, [[r.get(h, "") for h in heads] for r in rows])
            people = {r.get("email", "").lower() for r in rows
                      if (r.get("type", "") or "").upper() == "USER"}
            self.status.setText(f"{len(people):,} people in total, counting nested groups")
        page.runner.run(mt.members_recursive_args(group), done, quiet_stdout=True)
