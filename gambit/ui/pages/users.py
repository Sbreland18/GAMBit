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
        from PySide6.QtWidgets import QComboBox as _CB
        from ..pickers import PeoplePicker
        from ..stepper import Stepper, scroll
        from .licenses import SKUS
        # step 1 – details
        d = QWidget()
        dl = QVBoxLayout(d)
        dl.setContentsMargins(0, 0, 0, 0)
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
        dl.addWidget(box)
        dl.addStretch(1)
        # step 2 – groups & license (optional)
        g = QWidget()
        gl = QVBoxLayout(g)
        gl.setContentsMargins(0, 0, 0, 0)
        box, form = self.group("Groups and license (optional)")
        self.c_license = _CB()
        self.c_license.addItem("Don't assign a license", "")
        for name, sku in SKUS:
            self.c_license.addItem(name, sku)
        form.addRow("License", self.c_license)
        form.addRow(QLabel("Add to groups:"))
        self.c_groups = PeoplePicker(self.directory, include_groups=True)
        self.c_groups.search.setPlaceholderText("Search groups (e.g. All Staff)…")
        form.addRow(self.c_groups)
        gl.addWidget(box)
        gl.addStretch(1)
        self.c_stepper = Stepper(
            [("Details", d), ("Groups & license", g)], self._c_review, "Create user",
            self.create_user, validate={0: self._c_valid})
        from ..unsaved import track
        track(self, self.c_stepper, "a new user account", self.c_stepper.finish_btn)
        return scroll(self.c_stepper)

    def _c_valid(self) -> bool:
        return self.need(("a first name", self.c_first), ("a last name", self.c_last),
                         ("an email address", self.c_email), emails=[self.c_email])

    def _c_plan(self, pw: str):
        from ...gam_runner import display_command
        email = self.c_email.text().strip()
        args = ["create", "user", email,
                "firstname", self.c_first.text().strip(),
                "lastname", self.c_last.text().strip(),
                "password", pw]
        if self.c_change.isChecked():
            args += ["changepassword", "on"]
        if self.c_ou.path():
            args += ["ou", self.c_ou.path()]
        where = self.c_ou.path() or "/"
        plan = [(f"Create {email} in {where}" + (" – they choose a new password at first "
                                                 "sign-in" if self.c_change.isChecked()
                                                 else ""), args)]
        if self.c_license.currentData():
            plan.append((f"Assign {self.c_license.currentText()}",
                         ["user", email, "add", "license", self.c_license.currentData()]))
        for grp in self.c_groups.emails():
            plan.append((f"Add to {grp}", ["update", "group", grp, "add", "member", "user",
                                           email]))
        return [(what, a, display_command(a)) for what, a in plan]

    def _c_review(self):
        pw = self.c_pw.text().strip() or "(a generated password)"
        return [(what, cmd) for what, _a, cmd in self._c_plan(pw)]

    def create_user(self):
        if not self._c_valid():
            self.c_stepper.go(0)
            return
        pw = self.c_pw.text().strip() or random_password()
        self.c_pw.setText(pw)
        email = self.c_email.text().strip()
        plan = self._c_plan(pw)
        first, rest = plan[0], plan[1:]

        def extras_done(codes, _outs):
            bad = [plan[1 + n][0] for n, c in enumerate(codes) if c != 0]
            note = ("\n\nThese didn't work: " + "; ".join(bad)) if bad else ""
            self.info(f"Created {email}.\n\nTemporary password: {pw}{note}", "User created")
            self._c_reset()

        def done(code, _o, _e):
            if code != 0:
                return
            if rest:
                self.run_many([a for _w, a, _c in rest], extras_done, with_codes=True)
            else:
                self.info(f"Created {email}.\n\nTemporary password: {pw}", "User created")
                self._c_reset()
        self.run(first[1], done)

    def _c_reset(self):
        for w in (self.c_first, self.c_last, self.c_email, self.c_pw):
            w.clear()
        self.c_groups.clear()
        self.c_license.setCurrentIndex(0)
        self.c_stepper.reset()

    # ----------------------------------------------------------- list ---
    def _list_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box, form = self.group("Search")
        self.l_mode = QComboBox()
        self.l_mode.addItems(["Everyone", "In org unit(s)", "Name or email contains",
                              "Suspended users only", "Custom query", "Custom field"])
        self.l_value = QLineEdit(placeholderText="e.g. /Students/2031")
        self.l_mode.currentIndexChanged.connect(self._mode_changed)
        self.l_ous = OUMultiField(self.directory)
        self.cf_field = QComboBox()
        self.cf_field.setMinimumWidth(220)
        self.cf_op = QComboBox()
        from ... import custom_fields as _cf
        for k, lab in _cf.OPS.items():
            self.cf_op.addItem(lab, k)
        self.cf_op.currentIndexChanged.connect(lambda *_: self._mode_changed(
            self.l_mode.currentIndex()))
        form.addRow("Show", self.row(self.l_mode, self.cf_field, self.cf_op, self.l_value,
                                     self.l_ous, stretch=False))
        self.cf_note = QLabel("", objectName="Muted")
        self.cf_note.setWordWrap(True)
        form.addRow("", self.cf_note)
        form.addRow("", self.row(
            button("Search", "primary", self.list_users),
            button("Custom fields…", slot=self.choose_custom_fields),
            button("☆ Save this search", slot=self.save_search),
            button("Suspend selected", "danger", lambda: self.bulk_suspend(True)),
            button("Unsuspend selected", slot=lambda: self.bulk_suspend(False))))
        self.saved = QComboBox()
        self.saved.setMinimumWidth(260)
        self.saved.currentIndexChanged.connect(self._saved_picked)
        self.saved_run = button("▶ Run", "primary", lambda: self.run_saved())
        self.saved_upd = button("Update with the search above", slot=self.update_saved)
        self.saved_ren = button("Rename…", slot=self.rename_saved)
        self.saved_del = button("Delete", "danger", self.delete_saved)
        self.saved_sheet = button("Google Sheet…", slot=self.sheet_saved)
        self.saved_sheet.setToolTip("Keep a Google Sheet up to date with this search every "
                                    "night (custom fields included)")
        form.addRow("Saved", self.row(self.saved, self.saved_run, self.saved_upd,
                                      self.saved_ren, self.saved_del, self.saved_sheet,
                                      stretch=False))
        self.saved_note = QLabel("", objectName="Muted")
        self.saved_note.setWordWrap(True)
        form.addRow("", self.saved_note)
        lay.addWidget(box)
        self.results = ResultsTable()
        lay.addWidget(self.results, 1)
        self._mode_changed(0)
        self.refresh_saved()
        from ..unsaved import remember_field
        remember_field(self.l_mode, "users/mode")     # last search comes back next time
        remember_field(self.l_value, "users/value")
        return w

    # ------------------------------------------------------ saved searches ---
    def form_spec(self) -> dict:
        return {"mode": self.l_mode.currentText(), "value": self.l_value.text().strip(),
                "ous": self.l_ous.paths(), "children": self.l_ous.include_children(),
                "cf_field": self.cf_field.currentData() or "",
                "cf_op": self.cf_op.currentData() or "is"}

    def apply_spec(self, spec: dict):
        """Put a saved search back on the form (without running it)."""
        i = self.l_mode.findText(spec["mode"])
        self.l_mode.setCurrentIndex(max(0, i))
        self.l_value.setText(spec.get("value", ""))
        self.l_ous.set_paths(spec.get("ous") or [])
        self.l_ous.set_include_children(spec.get("children", True))
        self.cf_op.setCurrentIndex(max(0, self.cf_op.findData(spec.get("cf_op", "is"))))
        self._mode_changed(self.l_mode.currentIndex())
        if spec.get("cf_field"):
            if self.cf_field.findData(spec["cf_field"]) < 0:
                self.cf_field.addItem(spec["cf_field"], spec["cf_field"])
            self.cf_field.setCurrentIndex(self.cf_field.findData(spec["cf_field"]))

    def _spec_problem(self, spec: dict) -> str:
        m = spec["mode"]
        if m == "In org unit(s)" and not spec["ous"]:
            return "Click Choose… and tick one or more org units first."
        if m in ("Name or email contains", "Custom query") and not spec["value"]:
            return "Type what to search for first."
        if m == "Custom field" and not spec["cf_field"]:
            return "Pick a custom field first."
        return ""

    def _searches(self) -> list[dict]:
        return [f for f in self.app.favorites() if f.get("kind") == "search"]

    def refresh_saved(self, select_key: str = ""):
        from ... import saved_searches as ss
        cur = select_key or self.saved.currentData() or ""
        self.saved.blockSignals(True)
        self.saved.clear()
        self.saved.addItem("Saved searches…", "")
        for f in self._searches():
            from ..icons import icon as _ic
            self.saved.addItem(_ic("search"), f["label"], f["value"])
            self.saved.setItemData(self.saved.count() - 1, ss.tooltip(f), 3)  # tooltip
        i = self.saved.findData(cur) if cur else 0
        self.saved.setCurrentIndex(max(0, i))
        self.saved.blockSignals(False)
        has = self.saved.count() > 1
        for b in (self.saved, self.saved_run, self.saved_upd, self.saved_ren, self.saved_del,
                  self.saved_sheet):
            b.setEnabled(has)
        self._saved_picked()

    def _current_saved(self) -> dict | None:
        key = self.saved.currentData()
        return next((f for f in self._searches() if f["value"] == key), None) if key else None

    def _saved_picked(self, *_):
        f = self._current_saved()
        on = f is not None
        for b in (self.saved_run, self.saved_upd, self.saved_ren, self.saved_del,
                  self.saved_sheet):
            b.setEnabled(on)
        if on:
            from ... import saved_searches as ss
            self.apply_spec(ss.spec_of(f))
            sheet = (f.get("sheet") or {})
            extra = ""
            if sheet.get("url"):
                extra = (" · keeps a Google Sheet up to date" +
                         (f" (last {sheet['last'].replace('T', ' ')})" if sheet.get("last")
                          else "") + (" – last refresh FAILED" if sheet.get("error") else ""))
            self.saved_note.setText(ss.describe(ss.spec_of(f)) + extra + " – change the "
                                    "search above and click Update to save the change.")
        else:
            self.saved_note.setText("")

    def run_saved(self, fav: dict | None = None):
        from ... import saved_searches as ss
        f = fav or self._current_saved()
        if not f:
            return
        if fav:
            self.refresh_saved(f["value"])
        self.apply_spec(ss.spec_of(f))
        self.list_users()

    def save_search(self):
        from PySide6.QtWidgets import QInputDialog
        from ... import saved_searches as ss
        spec = self.form_spec()
        why = self._spec_problem(spec)
        if why:
            self.info(why)
            return
        name, ok = QInputDialog.getText(self, "Save this search", "Name it (e.g. All "
                                        "schools – students):", text=ss.describe(spec)[:60])
        if not ok or not name.strip():
            return
        key = ss.new_key()
        favs = self.app.favorites()
        favs.insert(0, {"kind": "search", "value": key, "label": name.strip(), "spec": spec})
        self.app._save_favorites(favs[:40])
        self.app.statusBar().showMessage(f"★ Saved the search “{name.strip()}”", 4000)
        self.refresh_saved(key)

    def update_saved(self):
        from ... import saved_searches as ss
        f = self._current_saved()
        if not f:
            return
        spec = self.form_spec()
        why = self._spec_problem(spec)
        if why:
            self.info(why)
            return
        if not self.confirm(f"Save the search on the form as “{f['label']}”?\n\n"
                            f"Was: {ss.describe(ss.spec_of(f))}\nNow: {ss.describe(spec)}"):
            return
        self.app.update_favorite(f, {**f, "spec": spec})
        self.refresh_saved(f["value"])

    def rename_saved(self):
        from PySide6.QtWidgets import QInputDialog
        f = self._current_saved()
        if not f:
            return
        name, ok = QInputDialog.getText(self, "Rename saved search", "New name:",
                                        text=f["label"])
        if ok and name.strip():
            self.app.update_favorite(f, {**f, "label": name.strip()})
            self.refresh_saved(f["value"])

    def sheet_saved(self):
        f = self._current_saved()
        if not f:
            return
        from .round25_data import SearchSheetDialog
        if SearchSheetDialog(self, f).exec():
            self.refresh_saved(f["value"])

    def delete_saved(self):
        f = self._current_saved()
        if f and self.confirm(f"Delete the saved search “{f['label']}”?"):
            self.app.remove_favorite(f)
            self.refresh_saved()

    def _mode_changed(self, idx):
        hints = {2: "smith", 4: "orgUnitPath='/Staff' isAdmin=false", 5: "e.g. 7th Grade"}
        op = self.cf_op.currentData()
        self.l_value.setVisible(idx in (2, 4) or (idx == 5 and op not in ("empty",
                                                                          "notempty")))
        self.l_value.setPlaceholderText(hints.get(idx, ""))
        self.l_ous.setVisible(idx in (1, 5))
        self.cf_field.setVisible(idx == 5)
        self.cf_op.setVisible(idx == 5)
        if idx == 5:
            self._fill_cf_fields()
        self._cf_note(idx)

    def _fill_cf_fields(self):
        from ... import custom_fields as cf
        cur = self.cf_field.currentData()
        self.cf_field.blockSignals(True)
        self.cf_field.clear()
        cfg = cf.config()
        chosen = cf.columns()
        allf = [f"{s}.{f['name']}" for s, x in cfg.get("schemas", {}).items()
                for f in x.get("fields", [])]
        for c in chosen + [c for c in allf if c not in chosen]:
            self.cf_field.addItem(c, c)
        if cur:
            self.cf_field.setCurrentIndex(max(0, self.cf_field.findData(cur)))
        self.cf_field.blockSignals(False)

    def _cf_note(self, idx=None):
        from ... import custom_fields as cf
        idx = self.l_mode.currentIndex() if idx is None else idx
        if idx == 5 and not self.cf_field.count():
            self.cf_note.setText("Set up your custom fields first: click “Custom fields…” "
                                 "and “Read schemas from Google”.")
        elif idx == 5:
            self.cf_note.setText("Pick org unit(s) to search only there (faster). Exact "
                                 "matches on searchable fields are found by Google; other "
                                 "searches load the users and check each one.")
        elif cf.active():
            self.cf_note.setText(f"Custom fields in the results: "
                                 f"{', '.join(cf.label(c) for c in cf.columns()[:6])}"
                                 f"{' …' if len(cf.columns()) > 6 else ''}")
        else:
            self.cf_note.setText("")

    def choose_custom_fields(self):
        from ..custom_fields_dialog import CustomFieldsDialog
        if CustomFieldsDialog(self).exec():
            self._mode_changed(self.l_mode.currentIndex())

    def list_users(self):
        """Every kind of search goes through saved_searches.build, so a saved search run
        later (or into a Google Sheet at night) gives exactly the same list."""
        from ... import saved_searches as ss
        spec = self.form_spec()
        if spec["mode"] == "Custom field" and not spec["cf_field"]:
            self.choose_custom_fields()
            return
        if spec["mode"] == "Custom field" and spec["cf_op"] in ("is", "contains", "starts") \
                and not spec["value"]:
            self.info("Type what to look for.")
            return
        if spec["mode"] == "In org unit(s)" and not spec["ous"]:
            self.info("Click Choose… and tick one or more org units.")
            return
        if spec["mode"] != "Custom field":
            spec["ous"] = spec["ous"] if spec["mode"] == "In org unit(s)" else []
        cmds, keep = ss.build(spec, USER_FIELDS)

        def done(outs):
            self.results.load_csv_many(outs, keep)
            if spec["mode"] == "Custom field":
                from ... import custom_fields as cf
                op, val, col = spec["cf_op"], spec["value"], spec["cf_field"]
                sq = cf.server_query(col, op, val)
                self.cf_note.setText(
                    f"{self.results.row_count()} user(s) where {col} {cf.OPS[op]}" +
                    (f" “{val}”" if op in ("is", "contains", "starts") else "") +
                    (" (searched by Google)" if sq else " (checked by GAMbit)") + ".")
        self.run_many(cmds, done)

    @staticmethod
    def _cf(cmd):
        from ... import custom_fields
        return custom_fields.with_custom(cmd)

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
