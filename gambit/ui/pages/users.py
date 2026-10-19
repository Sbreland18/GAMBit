from __future__ import annotations

import secrets
import string

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QLabel, QLineEdit, QScrollArea, QTabWidget, QVBoxLayout,
    QWidget,
)

from ..pickers import OUField, OUMultiField, PersonField
from ..widgets import Page, ResultsTable, button

USER_FIELDS = "primaryemail,name,suspended,ou,lastlogintime,creationtime"


def random_password(length: int = 14) -> str:
    # No look-alike characters (O/0, l/1/I) so passwords are easy to read off a sheet
    alphabet = "".join(c for c in string.ascii_letters + string.digits
                       if c not in "O0oIl1") + "!@#$%*?"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.isdigit() for c in pw) and any(c.isupper() for c in pw)
                and any(c.islower() for c in pw)):
            return pw


def _scroll(w: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QScrollArea.NoFrame)
    w.setObjectName("Page")
    s.setWidget(w)
    return s


class UsersPage(Page):
    title = "Users"
    subtitle = "Look up, create, and manage Google Workspace accounts."

    def build(self):
        tabs = QTabWidget()
        tabs.addTab(self._manage_tab(), "Manage a user")
        tabs.addTab(self._create_tab(), "Create a user")
        tabs.addTab(self._list_tab(), "Find / list users")
        from .people_tabs import DeletedTab, PhotosTab
        self.photos_tab = PhotosTab(self)
        self.deleted_tab = DeletedTab(self)
        tabs.addTab(self.photos_tab, "Photos")
        tabs.addTab(self.deleted_tab, "Recently deleted")
        from .more_tabs import DirectoryDetailsTab
        self.dir_tab = DirectoryDetailsTab(self)
        tabs.addTab(self.dir_tab, "Directory details")
        from .round11_pages import TempAccountsTab
        self.temp_tab = TempAccountsTab(self)
        tabs.addTab(self.temp_tab, "Time-limited accounts")
        from .round13_tabs import PersonalAccountsTab
        self.personal_tab = PersonalAccountsTab(self)
        tabs.addTab(self.personal_tab, "Personal Google accounts")
        from .round14_tabs import PhotoExportTab
        self.photo_export_tab = PhotoExportTab(self)
        tabs.addTab(self.photo_export_tab, "Photo export")
        self.tabs = tabs
        self.body.addWidget(tabs)

    # --------------------------------------------------------- manage ---
    def _manage_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)

        box, form = self.group("Which user?")
        self.m_email = PersonField(self.directory, "Start typing a name or email…")
        form.addRow("Email", self.row(self.m_email,
                                     button("Show info", "primary", self.user_info),
                                     stretch=False))
        lay.addWidget(box)

        sub = QTabWidget()
        sub.addTab(_scroll(self._account_section()), "Account")
        sub.addTab(self._aliases_section(), "Email addresses && aliases")
        sub.addTab(self._security_section(), "Security")
        lay.addWidget(sub, 1)
        return w

    def _account_section(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box, form = self.group("Account status")
        form.addRow(self.row(
            button("Suspend", "danger", lambda: self.suspend(True)),
            button("Unsuspend", slot=lambda: self.suspend(False)),
            button("Sign out of all sessions", slot=self.signout)))
        lay.addWidget(box)

        box, form = self.group("Password")
        self.m_pw = QLineEdit(placeholderText="Leave blank to generate one")
        self.m_pw_change = QCheckBox("Require change at next sign-in")
        self.m_pw_change.setChecked(True)
        form.addRow("New password", self.row(
            self.m_pw, button("Generate", slot=lambda: self.m_pw.setText(random_password())),
            stretch=False))
        form.addRow("", self.m_pw_change)
        form.addRow("", self.row(button("Reset password", "primary", self.reset_pw)))
        form.addRow("Keep current password", self.row(
            button("Require change at next sign-in", slot=lambda: self.force_change(True)),
            button("Cancel that requirement", slot=lambda: self.force_change(False))))
        lay.addWidget(box)

        box, form = self.group("Move to organizational unit")
        self.m_ou = OUField(self.directory, "Pick or type an org unit")
        form.addRow("New OU", self.row(self.m_ou, button("Move", slot=self.move_ou),
                                       stretch=False))
        lay.addWidget(box)

        box, form = self.group("Danger zone")
        form.addRow(self.row(button("Delete user…", "danger", self.delete_user)))
        lay.addWidget(box)
        self.danger_box = box
        lay.addStretch(1)
        return w

    # ---------------------------------------------------- aliases ---
    def _aliases_section(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        box, form = self.group("Change their email address")
        self.r_new = QLineEdit(placeholderText="new.name@yourschool.org")
        form.addRow("New primary address", self.row(
            self.r_new, button("Rename…", slot=self.rename_user), stretch=False))
        note = QLabel("Google keeps the old address as an alias, so mail sent to it still "
                      "arrives.", objectName="Muted")
        form.addRow("", note)
        lay.addWidget(box)

        box, form = self.group("Alternate addresses (aliases)")
        self.a_new = QLineEdit(placeholderText="nickname@yourschool.org")
        form.addRow("Add alias", self.row(self.a_new, button("Add", "primary", self.add_alias),
                                          stretch=False))
        form.addRow("", self.row(
            button("Show this user's aliases", slot=self.list_aliases),
            button("Remove selected alias", "danger", self.remove_alias),
            button("Export ALL aliases in the domain", slot=self.export_aliases)))
        lay.addWidget(box)
        self.aliases = ResultsTable()
        lay.addWidget(self.aliases, 1)
        return w

    def rename_user(self):
        e = self._email()
        new = self.r_new.text().strip()
        if not e:
            return
        if "@" not in new:
            self.info("Type the full new email address.")
            return
        if self.confirm(f"Change {e} to {new}?\n\nThey'll sign in with the new address "
                        "from now on. The old one keeps working as an alias."):
            self.run(["update", "user", e, "email", new],
                     lambda c, *_: (c == 0 and (self.m_email.setText(new),
                                                self.r_new.clear(),
                                                self.directory.refresh_users())))

    def add_alias(self):
        e = self._email()
        a = self.a_new.text().strip()
        if e and "@" in a:
            self.run(["create", "alias", a, "user", e],
                     lambda c, *_: (c == 0 and self.a_new.clear(), self.list_aliases()))
        elif e:
            self.info("Type the full alias address, e.g. nickname@yourschool.org")

    def list_aliases(self):
        if e := self._email():
            self.run(["print", "aliases", "user", e, "shownoneditable"],
                     lambda c, out, _e: self.aliases.load_csv(out) if c == 0 else None,
                     quiet=True)

    def remove_alias(self):
        sel = self.aliases.selected_values("Alias")
        if not sel:
            self.info("Click Show this user's aliases, then select the alias to remove.")
            return
        if self.confirm(f"Remove alias {', '.join(sel)}?\n\nMail sent to it will bounce."):
            self.run_many([["delete", "alias", a] for a in sel],
                          lambda _o: self.list_aliases(), quiet=False)

    def export_aliases(self):
        self.run(["print", "aliases"],
                 lambda c, out, _e: self.aliases.load_csv(out) if c == 0 else None,
                 quiet=True)
        self.info("Loading every alias in the domain. Use Export CSV… above the table "
                  "to save it.")

    # --------------------------------------------------- security ---
    def _security_section(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        box, form = self.group("Apps connected to this account")
        form.addRow(self.row(button("Show connected apps", "primary", self.show_tokens),
                             button("Remove access for selected app", "danger",
                                    self.revoke_token)))
        lay.addWidget(box)
        box, form = self.group("2-Step Verification backup codes")
        form.addRow(self.row(button("Show available codes", slot=self.show_codes),
                             button("Generate new codes…", "primary", self.new_codes)))
        note = QLabel("Generating new codes cancels any old ones. Each code works once.",
                      objectName="Muted")
        form.addRow("", note)
        lay.addWidget(box)
        self.sec = ResultsTable()
        lay.addWidget(self.sec, 1)
        return w

    def show_tokens(self):
        if e := self._email():
            self.run(["user", e, "print", "tokens", "orderby", "displaytext"],
                     lambda c, out, _e: self.sec.load_csv(out) if c == 0 else None, quiet=True)

    def revoke_token(self):
        e = self._email()
        ids = self.sec.selected_values("clientId")
        if not e:
            return
        if not ids:
            self.info("Click Show connected apps, then select the app(s) to remove.")
            return
        names = self.sec.selected_values("displayText") or ids
        if self.confirm(f"Remove access for {', '.join(names)}?\n\nThe app will need "
                        "permission again the next time it's used."):
            self.run_many([["user", e, "delete", "token", "clientid", i] for i in ids],
                          lambda _o: self.show_tokens(), quiet=False)

    def show_codes(self):
        if e := self._email():
            self.run(["user", e, "print", "backupcodes"],
                     lambda c, out, _e: self.sec.load_csv(out) if c == 0 else None, quiet=True)

    def new_codes(self):
        e = self._email()
        if e and self.confirm(f"Generate new backup codes for {e}?\n\nTheir old codes "
                              "will stop working."):
            self.run(["user", e, "update", "backupcodes"], lambda c, *_: self.show_codes())

    def force_change(self, on: bool):
        if e := self._email():
            self.run(["update", "user", e, "changepassword", "on" if on else "off"],
                     lambda c, *_: c == 0 and self.info(
                         f"{e} will be asked to choose a new password next time they sign in."
                         if on else f"{e} no longer has to change their password."))

    def set_helpdesk(self, on: bool):
        self.danger_box.setVisible(not on)

    def _email(self):
        return self.m_email.email() if self.need(("the user's email", self.m_email)) else None

    def user_info(self):
        if e := self._email():
            self.run(["info", "user", e])

    def suspend(self, on: bool):
        if e := self._email():
            if on and not self.confirm(f"Suspend {e}? They will not be able to sign in."):
                return
            self.run(["update", "user", e, "suspended", "on" if on else "off"])

    def signout(self):
        if e := self._email():
            self.run(["user", e, "signout"])

    def reset_pw(self):
        e = self._email()
        if not e:
            return
        pw = self.m_pw.text().strip() or random_password()
        self.m_pw.setText(pw)
        args = ["update", "user", e, "password", pw]
        if self.m_pw_change.isChecked():
            args += ["changepassword", "on"]

        def done(code, _o, _e):
            if code == 0:
                self.info(f"Password for {e} was reset.\n\nNew password: {pw}",
                          "Password reset")
        self.run(args, done)

    def move_ou(self):
        if (e := self._email()) and self.need(("the new OU path", self.m_ou)):
            self.run(["update", "user", e, "ou", self.m_ou.path()])

    def delete_user(self):
        e = self._email()
        if e and self.confirm(f"Permanently delete {e}?\n\nYou can restore a deleted "
                              "user from the Admin console for about 20 days.",
                              "Delete user"):
            self.run(["delete", "user", e])

    # --------------------------------------------------------- create ---
    def _create_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box, form = self.group("New account")
        self.c_first = QLineEdit()
        self.c_last = QLineEdit()
        self.c_email = QLineEdit(placeholderText="first.last@yourschool.org")
        self.c_pw = QLineEdit(placeholderText="Leave blank to generate one")
        self.c_ou = OUField(self.directory, "Pick an org unit (blank = /)")
        self.c_change = QCheckBox("Require password change at first sign-in")
        self.c_change.setChecked(True)
        form.addRow("First name", self.c_first)
        form.addRow("Last name", self.c_last)
        form.addRow("Email", self.c_email)
        form.addRow("Password", self.row(
            self.c_pw, button("Generate", slot=lambda: self.c_pw.setText(random_password())),
            stretch=False))
        form.addRow("Org unit", self.c_ou)
        form.addRow("", self.c_change)
        form.addRow("", self.row(button("Create user", "primary", self.create_user)))
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def create_user(self):
        if not self.need(("a first name", self.c_first), ("a last name", self.c_last),
                         ("an email address", self.c_email)):
            return
        pw = self.c_pw.text().strip() or random_password()
        self.c_pw.setText(pw)
        email = self.c_email.text().strip()
        args = ["create", "user", email,
                "firstname", self.c_first.text().strip(),
                "lastname", self.c_last.text().strip(),
                "password", pw]
        if self.c_change.isChecked():
            args += ["changepassword", "on"]
        if self.c_ou.path():
            args += ["ou", self.c_ou.path()]

        def done(code, _o, _e):
            if code == 0:
                self.info(f"Created {email}.\n\nTemporary password: {pw}", "User created")
        self.run(args, done)

    # ----------------------------------------------------------- list ---
    def _list_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box, form = self.group("Search")
        self.l_mode = QComboBox()
        self.l_mode.addItems(["Everyone", "In org unit(s)", "Name or email contains",
                              "Suspended users only", "Custom query"])
        self.l_value = QLineEdit(placeholderText="e.g. /Students/2031")
        self.l_mode.currentIndexChanged.connect(self._mode_changed)
        self.l_ous = OUMultiField(self.directory)
        form.addRow("Show", self.row(self.l_mode, self.l_value, self.l_ous, stretch=False))
        form.addRow("", self.row(
            button("Search", "primary", self.list_users),
            button("☆ Save this search", slot=self.save_search),
            button("Suspend selected", "danger", lambda: self.bulk_suspend(True)),
            button("Unsuspend selected", slot=lambda: self.bulk_suspend(False))))
        lay.addWidget(box)
        self.results = ResultsTable()
        lay.addWidget(self.results, 1)
        self._mode_changed(0)
        return w

    def save_search(self):
        from PySide6.QtWidgets import QInputDialog
        idx, val = self.l_mode.currentIndex(), self.l_value.text().strip()
        q = {2: val, 3: "isSuspended=true", 4: val}.get(idx, "")
        if idx == 1:
            ous = self.l_ous.paths()
            q = " ".join(f"orgUnitPath='{o}'" for o in ous[:1])
        if not q:
            self.info("Saved searches use “Name or email contains”, “Suspended users only”, "
                      "a single org unit, or a Custom query.")
            return
        name, ok = QInputDialog.getText(self, "Save this search", "Name it (e.g. Staff without "
                                        "2-step):", text=q)
        if ok and name.strip():
            self.app.add_favorite(q, "search", name.strip())

    def _mode_changed(self, idx):
        hints = {2: "smith", 4: "orgUnitPath='/Staff' isAdmin=false"}
        self.l_value.setVisible(idx in (2, 4))
        self.l_value.setPlaceholderText(hints.get(idx, ""))
        self.l_ous.setVisible(idx == 1)

    def list_users(self):
        idx, val = self.l_mode.currentIndex(), self.l_value.text().strip()
        if idx == 1:
            ous = self.l_ous.paths()
            if not ous:
                self.info("Click Choose… and tick one or more org units.")
                return
            cmds = []
            for ou in ous:
                q = ["print", "users"]
                if ou != "/":
                    q += ["query", f"orgUnitPath='{ou}'"]
                cmds.append(q + ["fields", USER_FIELDS])
            keep = None
            if not self.l_ous.include_children():  # only people directly in the chosen OUs
                wanted = {o.lower() for o in ous}
                keep = lambda r: (r.get("orgUnitPath") or "/").lower() in wanted  # noqa: E731
            self.run_many(cmds, lambda outs: self.results.load_csv_many(outs, keep))
            return
        args = ["print", "users"]
        if idx == 2 and val:
            args += ["query", val]
        elif idx == 3:
            args += ["query", "isSuspended=true"]
        elif idx == 4 and val:
            args += ["query", val]
        args += ["fields", USER_FIELDS]
        self.run(args, lambda c, out, _e: self.results.load_csv(out) if c == 0 else None,
                 quiet=True)

    def bulk_suspend(self, on: bool):
        emails = self.results.selected_values("primaryEmail")
        if not emails:
            self.info("Select one or more rows in the results first.")
            return
        verb = "Suspend" if on else "Unsuspend"
        if not self.confirm(f"{verb} {len(emails)} user(s)?"):
            return
        self.run(["users", ",".join(emails), "update", "user",
                  "suspended", "on" if on else "off"])
