"""Users → Photos and Recently deleted;  Email → Send as."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QLabel, QLineEdit, QVBoxLayout,
)

from ...settings import settings
from ...tools import people, photos
from ..pickers import OUField, PeoplePicker
from ..tools_base import ToolTab
from ..widgets import ResultsTable, button


class PhotosTab(ToolTab):
    intro = ("Upload profile photos for many people at once – for example a picture-day "
             "export. Name each file after the person's email, username or SIS / employee ID "
             "(jdoe@school.org.jpg, jdoe.jpg or 104522.jpg). JPG or PNG, under 5 MB.")

    def build(self):
        self.folder = QLineEdit(settings.get("photos/folder", "") or "")
        self.folder.setPlaceholderText("Folder with the photos")
        self.by = QComboBox()
        for label, val in (("Work it out (email, ID, then username)", "auto"),
                           ("Email address", "email"), ("SIS / employee ID", "id"),
                           ("Username (before the @)", "username")):
            self.by.addItem(label, val)
        self.lay.addLayout(self.row(self.folder, button("Browse…", slot=self._browse),
                                    QLabel("Files are named by"), self.by,
                                    button("Match files to people", "primary", self.preview),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.apply_btn = button("Upload matched photos", "primary", self.apply)
        self.apply_btn.setEnabled(False)
        self.lay.addLayout(self.row(self.apply_btn))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.matches = []

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Photos folder", self.folder.text())
        if d:
            self.folder.setText(d)

    def preview(self):
        d = self.folder.text().strip()
        if not os.path.isdir(d):
            self.info("Choose the folder with the photos.")
            return
        settings.set("photos/folder", d)
        if not self.directory.users:
            self.info("The user list hasn't loaded yet – try again in a moment.")
            return
        self.matches = photos.match(photos.scan(d), self.directory.users,
                                    self.by.currentData())
        self.table.set_rows(["File", "Account", "Matched by", "Problem"],
                            [[os.path.basename(m.path), m.email, m.how, m.problem]
                             for m in self.matches])
        ok = len(photos.commands(self.matches))
        self.status.setText(f"{len(self.matches)} file(s): {ok} ready, "
                            f"{len(self.matches) - ok} can't be used.")
        self.apply_btn.setEnabled(ok > 0)

    def apply(self):
        cmds = photos.commands(self.matches)
        if not cmds or not self.confirm(f"Upload {len(cmds)} photo(s)? Each replaces that "
                                        "person's current photo."):
            return
        self.run_steps(self.steps, [(f"Photo for {c[1]}", c) for c in cmds])


class DeletedTab(ToolTab):
    intro = ("Accounts deleted in the last 20 days can still be restored with their email, "
             "Drive files and settings. After that Google removes them for good.")

    def build(self):
        self.lay.addLayout(self.row(button("List recently deleted accounts", "primary",
                                           self.load), self.status))
        self.table = ResultsTable()
        self.table.hidden_columns = {"id"}
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.ou = OUField(self.directory, "Leave empty to restore to the top org unit")
        self.unsuspend = QCheckBox("Unsuspend them after restoring")
        self.lay.addLayout(self.row(QLabel("Restore into"), self.ou, self.unsuspend,
                                    button("Restore selected", "primary", self.restore),
                                    stretch=False))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def load(self):
        def done(rows):
            if rows is None:
                return
            d = people.deleted(rows)
            heads = ["Email", "Name", "Org unit", "Deleted", "Time left to restore", "ID"]
            self.table.set_rows(heads, [[r[h] for h in heads] for r in d])
            self.status.setText(f"{len(d)} deleted account(s)" if d else
                                "No accounts were deleted recently ✔")
        self.read(people.DELETED_ARGS, done)

    def restore(self):
        rows = [r for r in self.table.selected_dicts() if r.get("ID")]
        if not rows:
            self.info("Select the account(s) to restore first.")
            return
        late = [r["Email"] for r in rows if r.get("Time left to restore") == "too late"]
        if late:
            self.info("These can't be restored any more: " + ", ".join(late))
            rows = [r for r in rows if r not in late and r["Email"] not in late]
        if not rows or not self.confirm(f"Restore {len(rows)} account(s)?"):
            return
        steps = []
        for r in rows:
            steps.append((f"Restore {r['Email']}", people.undelete_args(r["ID"],
                                                                         self.ou.path())))
            if self.unsuspend.isChecked():
                steps.append((f"Unsuspend {r['Email']}",
                              ["update", "user", r["Email"], "suspended", "off"]))
        self.run_steps(self.steps, steps, lambda _s: (self.directory.refresh_users(),
                                                      self.load()))


class SendAsTab(ToolTab):
    intro = ("Let people send email as a shared address – for example the front office "
             "sending as frontoffice@. The address must be a group or alias in your domain. "
             "Replies go to that address, so make sure they're in the group to see them.")

    def build(self):
        box = QGroupBox("Who")
        v = QVBoxLayout(box)
        self.who = PeoplePicker(self.directory, include_groups=False)
        v.addWidget(self.who)
        self.lay.addWidget(box)
        box, form = self.page.group("Send as")
        self.addr = QLineEdit(placeholderText="frontoffice@yourschool.org")
        self.name = QLineEdit(placeholderText="Lincoln Elementary Front Office")
        self.reply = QLineEdit(placeholderText="optional – where replies go")
        self.default = QCheckBox("Make it their default From address")
        form.addRow("Address", self.addr)
        form.addRow("Name people see", self.name)
        form.addRow("Reply-to", self.reply)
        form.addRow("", self.default)
        form.addRow("", self.row(button("Add this address", "primary", self.add),
                                 button("Remove it", slot=self.remove),
                                 button("Show their addresses", slot=self.show)))
        self.lay.addWidget(box)
        self.lay.addWidget(self.status)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.table = ResultsTable()
        self.lay.addWidget(self.table, 1)

    def _ok(self) -> bool:
        if not self.who.emails():
            self.info("Pick the people first.")
            return False
        if "@" not in self.addr.text():
            self.info("Type the shared address.")
            return False
        return True

    def add(self):
        if not self._ok():
            return
        cmds = people.sendas_args(self.who.emails(), self.addr.text().strip(),
                                  self.name.text().strip() or self.addr.text().strip(),
                                  self.reply.text().strip(), self.default.isChecked())
        self.run_steps(self.steps, [(f"{c[1]} can send as {c[4]}", c) for c in cmds])

    def remove(self):
        if not self._ok() or not self.confirm(f"Remove {self.addr.text().strip()} from "
                                              f"{len(self.who.emails())} person(s)?"):
            return
        cmds = people.remove_sendas_args(self.who.emails(), self.addr.text().strip())
        self.run_steps(self.steps, [(f"{c[1]}: remove {c[4]}", c) for c in cmds])

    def show(self):
        emails = self.who.emails()
        if not emails:
            self.info("Pick the people first.")
            return
        self.read(["users", ",".join(emails), "print", "sendas"],
                  lambda rows: rows is not None and self.table.set_rows(
                      list(rows[0].keys()) if rows else [],
                      [list(r.values()) for r in rows]))
