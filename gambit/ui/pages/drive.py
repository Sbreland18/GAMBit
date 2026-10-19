"""Google Drive: ownership transfers, file/sharing audits, shared drives, storage."""

from __future__ import annotations

import datetime

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QSplitter,
    QTabWidget, QVBoxLayout, QWidget,
)

from ..pickers import PeoplePicker, PersonField
from ..widgets import Page, ResultsTable, button

FILE_FIELDS = "id,name,mimetype,owners.emailaddress,modifiedtime,size,webviewlink"
DRIVE_ROLES = [("Manager", "organizer"), ("Content manager", "fileorganizer"),
               ("Contributor", "writer"), ("Commenter", "commenter"), ("Viewer", "reader")]


def _find(row: dict, *parts) -> str:
    for k, v in row.items():
        kl = (k or "").lower()
        if all(p in kl for p in parts):
            return v or ""
    return ""


class DrivePage(Page):
    title = "Google Drive"
    subtitle = ("Hand off a departing person's files, audit sharing, manage shared drives "
                "and check storage.")

    def build(self):
        self.tabs = QTabWidget()
        self.tabs.addTab(self._transfer_tab(), "Transfer files")
        self.tabs.addTab(self._files_tab(), "A person's files && sharing")
        self.tabs.addTab(self._shared_tab(), "Shared drives")
        self.tabs.addTab(self._storage_tab(), "Storage && trash")
        from .misc_tabs import LabelsTab, OrphansTab
        self.orphans_tab, self.labels_tab = OrphansTab(self), LabelsTab(self)
        self.tabs.addTab(self.orphans_tab, "Orphaned files")
        self.tabs.addTab(self.labels_tab, "Labels")
        from .more_tabs import KeepTab, SharedDriveMoveTab
        from .security_tabs import FixSharingTab
        self.fix_tab, self.move_tab, self.keep_tab = (FixSharingTab(self),
                                                      SharedDriveMoveTab(self), KeepTab(self))
        self.tabs.addTab(self.fix_tab, "Fix sharing")
        self.tabs.addTab(self.move_tab, "Move && copy folders")
        self.tabs.addTab(self.keep_tab, "Keep notes")
        from .recovery_tabs import RestoreFilesTab
        self.restore_tab = RestoreFilesTab(self)
        self.tabs.addTab(self.restore_tab, "Restore files")
        from .round13_tabs import EmptyFoldersTab, SharedDriveSettingsTab, SharingExposureTab
        self.exposure_tab, self.sd_settings_tab, self.empty_tab = (
            SharingExposureTab(self), SharedDriveSettingsTab(self), EmptyFoldersTab(self))
        self.tabs.addTab(self.exposure_tab, "Sharing exposure")
        self.tabs.addTab(self.sd_settings_tab, "Shared drive settings")
        self.tabs.addTab(self.empty_tab, "Empty folders")
        from .round14_tabs import FolderToolsTab
        self.folder_tab = FolderToolsTab(self)
        self.tabs.addTab(self.folder_tab, "Folder tools")
        self.body.addWidget(self.tabs, 1)

    def _user(self, field: PersonField, what="Choose a person first."):
        u = field.email()
        if "@" not in u:
            self.info(what)
            return None
        return u

    # ====================================================== transfer ===
    def _transfer_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        box, form = self.group("Give one person's Drive files to someone else")
        self.t_from = PersonField(self.directory, "Person leaving (current owner)")
        self.t_to = PersonField(self.directory, "Person receiving the files")
        self.t_private = QCheckBox("Include files they never shared (private files)")
        self.t_private.setChecked(True)
        form.addRow("From", self.t_from)
        form.addRow("To", self.t_to)
        form.addRow("", self.t_private)
        form.addRow("", self.row(button("Start transfer…", "primary", self.transfer),
                                 button("Check transfer status", slot=self.transfer_status)))
        note = QLabel("Google moves the files into a folder named after the old owner in the "
                      "receiver's My Drive. Big drives can take hours. Do this before you "
                      "delete the old account.", objectName="Muted")
        note.setWordWrap(True)
        form.addRow("", note)
        lay.addWidget(box)
        self.t_results = ResultsTable()
        lay.addWidget(self.t_results, 1)
        return w

    def transfer(self):
        a = self._user(self.t_from, "Choose whose files to transfer.")
        b = a and self._user(self.t_to, "Choose who should receive the files.")
        if not (a and b):
            return
        if a.lower() == b.lower():
            self.info("Pick two different people.")
            return
        privacy = "private,shared" if self.t_private.isChecked() else "shared"
        if self.confirm(f"Transfer ownership of {a}'s Drive files to {b}?"):
            self.run(["create", "datatransfer", a, "gdrive", b, "privacy_level", privacy],
                     lambda *_: self.transfer_status())

    def transfer_status(self):
        args = ["print", "datatransfers"]
        if "@" in self.t_from.email():
            args += ["olduser", self.t_from.email()]
        self.run(args, lambda c, out, _e: self.t_results.load_csv(out) if c == 0 else None,
                 quiet=True)

    # ========================================================= files ===
    def _files_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        box, form = self.group("Search a person's Drive")
        self.f_user = PersonField(self.directory, "Whose Drive?")
        self.f_mode = QComboBox()
        self.f_mode.addItems(["All files they own",
                              "Shared with ANYONE who has the link",
                              "Shared with people outside our organization",
                              "Name contains…",
                              "Changed in the last … days",
                              "Custom Drive query"])
        self.f_value = QLineEdit()
        self.f_value.setVisible(False)
        self.f_mode.currentIndexChanged.connect(self._f_mode)
        form.addRow("Person", self.f_user)
        form.addRow("Show", self.row(self.f_mode, self.f_value, stretch=False))
        form.addRow("", self.row(button("Search", "primary", self.files_search),
                                 button("Count files && size", slot=self.file_counts),
                                 button("Open selected in browser", slot=self.open_selected)))
        lay.addWidget(box)
        self.f_results = ResultsTable()
        self.f_results.hidden_columns = {"id"}
        self.f_results.table.doubleClicked.connect(lambda *_: self.open_selected())
        lay.addWidget(self.f_results, 1)
        return w

    def _f_mode(self, i):
        hint = {3: "budget", 4: "30", 5: "mimeType = 'application/pdf'"}.get(i)
        self.f_value.setVisible(hint is not None)
        self.f_value.setPlaceholderText(hint or "")

    def files_search(self):
        u = self._user(self.f_user, "Choose whose Drive to search.")
        if not u:
            return
        i, v = self.f_mode.currentIndex(), self.f_value.text().strip()
        args = ["user", u, "print", "filelist", "fields", FILE_FIELDS]
        if i == 1:
            args += ["pm", "type", "anyone", "em"]
        elif i == 2:
            dom = self.directory.domain or u.split("@", 1)[1]
            args += ["pm", "type", "user", "notrole", "owner", "notdomainlist", dom, "em"]
        elif i == 3:
            if not v:
                self.info("Type part of the file name.")
                return
            args += ["query", "name contains '" + v.replace("'", "\\'") + "'"]
        elif i == 4:
            days = int(v) if v.isdigit() else 30
            since = (datetime.datetime.utcnow() - datetime.timedelta(days=days))
            args += ["query", f"modifiedTime > '{since.strftime('%Y-%m-%dT%H:%M:%S')}'"]
        elif i == 5 and v:
            args += ["query", v]
        self.run(args, lambda c, out, _e: self.f_results.load_csv(out) if c == 0 else None,
                 quiet=True)

    def file_counts(self):
        if u := self._user(self.f_user, "Choose whose Drive to count."):
            self.run(["user", u, "print", "filecounts", "showsize", "summary", "only"],
                     lambda c, out, _e: self.f_results.load_csv(out) if c == 0 else None,
                     quiet=True)

    def open_selected(self):
        links = self.f_results.selected_values("webViewLink")
        for link in links[:10]:
            QDesktopServices.openUrl(QUrl(link))
        if not links:
            self.info("Search first, then select a file.")

    # ================================================== shared drives ===
    def _shared_tab(self):
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 6, 6, 0)
        self.sd_list = ResultsTable()
        self.sd_list.hidden_columns = {"id"}
        self.sd_list.row_clicked.connect(self._open_drive)
        lv.addWidget(self.sd_list, 1)
        lv.addLayout(self.row(button("Load shared drives", "primary", self.load_drives)))
        new = QHBoxLayout()
        self.sd_new = QLineEdit(placeholderText="New shared drive name")
        new.addWidget(self.sd_new, 1)
        new.addWidget(button("Create", slot=self.create_drive))
        lv.addLayout(new)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 6, 0, 0)
        self.sd_title = QLabel("<span style='font-size:13pt;font-weight:600'>"
                               "Pick a shared drive on the left</span>")
        rv.addWidget(self.sd_title)
        self.sd_members = ResultsTable()
        rv.addWidget(self.sd_members, 1)
        sel = QHBoxLayout()
        sel.addWidget(QLabel("Selected members:"))
        sel.addWidget(button("Remove", "danger", self.remove_members))
        self.sd_role_change = QComboBox()
        for label, val in DRIVE_ROLES:
            self.sd_role_change.addItem(f"Make {label}", val)
        sel.addWidget(self.sd_role_change)
        sel.addWidget(button("Change access", slot=self.change_members))
        sel.addStretch(1)
        rv.addLayout(sel)
        box = QGroupBox("Add people or groups")
        bv = QVBoxLayout(box)
        self.sd_people = PeoplePicker(self.directory, include_groups=True)
        bv.addWidget(self.sd_people)
        ar = QHBoxLayout()
        ar.addWidget(QLabel("Access"))
        self.sd_role = QComboBox()
        for label, val in DRIVE_ROLES:
            self.sd_role.addItem(label, val)
        self.sd_role.setCurrentIndex(2)
        ar.addWidget(self.sd_role)
        ar.addWidget(button("Add", "primary", self.add_members))
        ar.addStretch(1)
        bv.addLayout(ar)
        rv.addWidget(box)
        self.sd_right = right
        right.setEnabled(False)

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([380, 620])
        self.sd_id = ""
        return split

    def load_drives(self):
        self.run(["print", "shareddrives", "fields", "id,name,createdtime"],
                 lambda c, out, _e: self.sd_list.load_csv(out) if c == 0 else None, quiet=True)

    def create_drive(self):
        name = self.sd_new.text().strip()
        if not name:
            self.info("Type a name for the new shared drive.")
            return
        self.run(["create", "shareddrive", name],
                 lambda c, *_: (c == 0 and self.sd_new.clear(), self.load_drives()))

    def _open_drive(self, row: dict):
        self.sd_id = row.get("id", "")
        if not self.sd_id:
            return
        self.sd_title.setText(f"<span style='font-size:13pt;font-weight:600'>"
                              f"{row.get('name', '')}</span>")
        self.sd_right.setEnabled(True)
        self.load_members()

    def load_members(self):
        def done(code, out, _e):
            import csv
            import io
            if code != 0:
                return
            rows = []
            for r in csv.DictReader(io.StringIO(out or "")):
                who = _find(r, "emailaddress") or _find(r, "domain") or _find(r, "type")
                role = _find(r, "role")
                label = next((lab for lab, v in DRIVE_ROLES if v == role), role)
                rows.append([who, _find(r, "displayname"), label, _find(r, "type")])
            self.sd_members.set_rows(["email", "Name", "Access", "Type"], rows)
        self.run(["print", "drivefileacls", "shareddriveid", self.sd_id, "oneitemperrow"],
                 done, quiet=True)

    def add_members(self):
        people = self.sd_people.emails()
        if not people:
            self.info("Search for people or groups and add them to the list first.")
            return
        groups = {g["email"].lower() for g in self.directory.groups}
        role = self.sd_role.currentData()
        cmds = [["add", "drivefileacl", "shareddriveid", self.sd_id,
                 "group" if p.lower() in groups else "user", p, "role", role] for p in people]
        self.run_many(cmds, lambda _o: (self.sd_people.clear(), self.load_members()),
                      quiet=False)

    def _selected(self):
        emails = [e for e in self.sd_members.selected_values("email") if "@" in e]
        if not emails:
            self.info("Select one or more members in the list.")
        return emails

    def remove_members(self):
        emails = self._selected()
        if emails and self.confirm(f"Remove {len(emails)} member(s) from this shared drive?"):
            self.run_many([["delete", "drivefileacl", "shareddriveid", self.sd_id, e]
                           for e in emails], lambda _o: self.load_members(), quiet=False)

    def change_members(self):
        emails = self._selected()
        if emails:
            role = self.sd_role_change.currentData()
            self.run_many([["update", "drivefileacl", "shareddriveid", self.sd_id, e,
                            "role", role] for e in emails],
                          lambda _o: self.load_members(), quiet=False)

    # ======================================================= storage ===
    def _storage_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        box, form = self.group("Storage")
        self.s_user = PersonField(self.directory, "Whose storage?")
        form.addRow("Person", self.s_user)
        form.addRow("", self.row(button("Show storage used", "primary", self.storage),
                                 button("Empty their Drive trash…", "danger", self.empty_trash)))
        note = QLabel("Emptying the trash permanently deletes those files. It can't be undone.",
                      objectName="Muted")
        form.addRow("", note)
        lay.addWidget(box)
        self.s_results = ResultsTable()
        lay.addWidget(self.s_results, 1)
        return w

    def storage(self):
        if u := self._user(self.s_user):
            self.run(["user", u, "print", "drivesettings", "fields",
                      "usage,usageindrive,usageindrivetrash,limit"],
                     lambda c, out, _e: self.s_results.load_csv(out) if c == 0 else None,
                     quiet=True)

    def empty_trash(self):
        u = self._user(self.s_user)
        if u and self.confirm(f"Permanently delete everything in {u}'s Drive trash?"):
            self.run(["user", u, "empty", "drivetrash"], lambda *_: self.storage())
