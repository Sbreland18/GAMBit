"""Roster sync: keep student or staff accounts in step with a roster (SIS export,
HR export, or a Google Sheet)."""

from __future__ import annotations

import dataclasses
import json
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QPlainTextEdit,
    QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

from ... import google_io, sis
from ...settings import settings
from ..cards import CardsDialog
from ..pickers import OUField
from ..steps import Step, StepList
from ..widgets import Page, ResultsTable, Worker, button

ACTION_LABEL = {"create": "New account", "reactivate": "Returning",
                "update": "✎ Update", "withdraw": "⛔ Leaving", "info": "ℹ Note"}
FIELD_LABEL = {"sis_id": "Student ID", "first": "First name", "last": "Last name",
               "email": "Email (optional)", "grade": "Grade", "school": "School",
               "status": "Status (optional)", "password": "Password (optional)",
               "role": "Role (OneRoster)", "enabled": "Enabled (OneRoster)",
               "username": "Username (optional)", "title": "Job title (staff)",
               "department": "Department (staff)", "manager": "Supervisor email (staff)"}
STAFF_LABEL = {"sis_id": "Employee ID", "grade": "Grade (not used)",
               "status": "Status (active / inactive)", "school": "Building / location"}


def _scroll(w):
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QScrollArea.NoFrame)
    w.setObjectName("Page")
    s.setWidget(w)
    return s


class RosterSyncPage(Page):
    title = "Roster sync"
    subtitle = ("Keep student or staff accounts matching your roster – an SIS export or a "
                "Google Sheet: newcomers get accounts, moves are applied, and people who "
                "leave are suspended. You always see the changes before anything happens.")

    def build(self):
        self.export = None
        self.changes: list[sis.Change] = []
        top = QHBoxLayout()
        self.profile = QComboBox()
        self.profile.setMinimumWidth(220)
        self.profile.activated.connect(lambda _i: self.load_profile(self.profile.currentText()))
        top.addWidget(QLabel("Saved sync:"))
        top.addWidget(self.profile)
        top.addWidget(button("Save settings as…", slot=self.save_profile))
        top.addWidget(button("Delete", slot=self.delete_profile))
        top.addWidget(button("Schedule…", slot=self.schedule))
        top.addSpacing(24)
        top.addWidget(QLabel("Roster of:"))
        self.kind = QComboBox()
        self.kind.addItem("Students", "students")
        self.kind.addItem("Staff", "staff")
        self.kind.currentIndexChanged.connect(self._kind_changed)
        top.addWidget(self.kind)
        top.addStretch(1)
        self.body.addLayout(top)

        self.tabs = QTabWidget()
        self.tabs.addTab(_scroll(self._file_tab()), "1. Roster")
        self.tabs.addTab(_scroll(self._rules_tab()), "2. Rules")
        self.tabs.addTab(self._preview_tab(), "3. Preview && apply")
        self.body.addWidget(self.tabs, 1)
        self._profiles()
        self._kind_changed(apply_defaults=False)
        last = settings.get("sis/last_profile", "")
        if last:
            self.load_profile(last)

    # ================================================================ file ===
    def _file_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box, form = self.group("Where the roster comes from")
        self.source = QComboBox()
        self.source.addItem("A file on this PC (CSV or OneRoster .zip)", "file")
        self.source.addItem("A Google Sheet", "sheet")
        self.source.addItem("Live from your SIS (ClassLink, Clever, PowerSchool, Infinite Campus, …)",
                            "oneroster")
        self.source.currentIndexChanged.connect(self._source_changed)
        form.addRow("Source", self.source)
        self.fmt = QComboBox()
        self.fmt.addItems(list(sis.FORMATS))
        self.fmt.currentIndexChanged.connect(self._remap)
        form.addRow("SIS / format", self.fmt)
        self.path = QLineEdit(placeholderText="users.csv, students.csv, or the OneRoster .zip")
        self.file_row = self.row(self.path, button("Browse…", slot=self._browse),
                                 button("Load", "primary", self.load_file), stretch=False)
        form.addRow("Export file", self.file_row)
        self.schools_path = QLineEdit(placeholderText="Optional: orgs.csv / schools.csv "
                                                      "(found automatically next to the file)")
        self.schools_row = self.row(self.schools_path,
                                    button("Browse…", slot=self._browse_schools), stretch=False)
        form.addRow("Schools file", self.schools_row)
        self.sheet_url = QLineEdit(placeholderText="Paste the Google Sheet link "
                                                   "(https://docs.google.com/spreadsheets/d/…)")
        self.sheet_row = self.row(self.sheet_url, button("Load", "primary", self.load_file),
                                  stretch=False)
        form.addRow("Google Sheet", self.sheet_row)
        self.sheet_tab = QLineEdit(placeholderText="Tab name – leave blank for the first tab")
        form.addRow("Tab", self.sheet_tab)
        self.sheet_user = QLineEdit(google_io.admin_email())
        self.sheet_user.setPlaceholderText("Google account that can open the sheet")
        form.addRow("Open it as", self.sheet_user)
        self.api_row = self.row(QLabel("Uses the SIS connection in Settings → "
                                       "Integrations."),
                                button("Download now", "primary", self.load_file))
        form.addRow("Live roster", self.api_row)
        self._source_rows = {"file": [self.file_row, self.schools_row],
                             "sheet": [self.sheet_row, self.sheet_tab, self.sheet_user],
                             "oneroster": [self.api_row]}
        self._form = form
        self.roles = QLineEdit("student")
        form.addRow("Roles to include", self.roles)
        tip = QLabel("ClassLink: use the OneRoster export (users.csv + orgs.csv, or the "
                     ".zip) – only rows whose role is listed above are used. A Google Sheet "
                     "needs a header row; a Status column with values like Active / "
                     "Inactive marks who has left.", objectName="Muted")
        tip.setWordWrap(True)
        form.addRow("", tip)
        self.file_info = QLabel("", objectName="Muted")
        form.addRow("", self.file_info)
        lay.addWidget(box)

        self.map_box = QGroupBox("Column mapping (filled in automatically – change if needed)")
        self.map_form = QFormLayout(self.map_box)
        self.map: dict[str, QComboBox] = {}
        for key in sis.CANONICAL:
            cb = QComboBox()
            self.map[key] = cb
            self.map_form.addRow(FIELD_LABEL[key], cb)
        lay.addWidget(self.map_box)
        self._source_changed()
        self.raw = ResultsTable()
        self.raw.setMinimumHeight(220)
        lay.addWidget(QLabel("<b>File preview</b>"))
        lay.addWidget(self.raw)
        return w

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "SIS export", "",
                                              "SIS exports (*.csv *.zip);;All files (*)")
        if path:
            self.path.setText(os.path.normpath(path))
            self.load_file()

    def _browse_schools(self):
        path, _ = QFileDialog.getOpenFileName(self, "Schools file", "", "CSV (*.csv)")
        if path:
            self.schools_path.setText(os.path.normpath(path))

    def _set_row_visible(self, item, on):
        self._form.setRowVisible(item, on)

    def _source_changed(self, *_):
        src = self.source.currentData()
        for key, items in self._source_rows.items():
            for it in items:
                self._set_row_visible(it, key == src)

    def load_file(self, then=None):
        """Load the roster. Google Sheets download in the background; `then` runs after."""
        if self.source.currentData() == "oneroster":
            from ...integrations import sis_api
            if not sis_api.configured():
                self.info("Set up your SIS connection in Settings → Integrations first.")
                return False
            self.fmt.setCurrentText("ClassLink / OneRoster")
            name = sis_api.provider_name()
            self.file_info.setText(f"Downloading the roster from {name}…")

            def done_api(path):
                if self._read(path, source=f"{name} (live)") and then:
                    then()
            Worker(sis_api.download, on_done=done_api,
                   on_error=lambda e: (self.file_info.setText(""), self.info(str(e))))
            return None
        if self.source.currentData() == "sheet":
            url = self.sheet_url.text().strip()
            if not url:
                self.info("Paste the Google Sheet link first.")
                return False
            user = self.sheet_user.text().strip()
            if "@" in user and not google_io.admin_email():
                google_io.set_admin_email(user)
            self.file_info.setText("Downloading the sheet from Google…")

            def done(path):
                if self._read(path, source=f"Google Sheet {self.sheet_tab.text() or ''}"):
                    if then:
                        then()

            def failed(e):
                self.file_info.setText("")
                self.info(str(e))
            Worker(google_io.download_sheet, url, self.sheet_tab.text().strip(), user,
                   on_done=done, on_error=failed)
            return None
        p = self.path.text().strip()
        if not p or not os.path.isfile(p):
            self.info("Choose the roster file first.")
            return False
        ok = self._read(p)
        if ok and then:
            then()
        return ok

    def _read(self, p, source=""):
        try:
            self.export = sis.load_export(p, self.fmt.currentText(),
                                          self.schools_path.text().strip()
                                          if self.source.currentData() == "file" else "")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Couldn't read that roster:\n{exc}")
            return False
        guess = sis.detect_format(self.export.headers)
        cur_score = sum(1 for v in sis.guess_mapping(self.export.headers,
                                                     self.fmt.currentText()).values() if v)
        new_score = sum(1 for v in sis.guess_mapping(self.export.headers, guess).values() if v)
        if guess != self.fmt.currentText() and not self._loading_profile and \
                new_score > cur_score:
            self.fmt.setCurrentText(guess)
        self._remap()
        self.raw.set_rows(self.export.headers,
                          [[r.get(h, "") for h in self.export.headers]
                           for r in self.export.rows[:500]])
        self.file_info.setText(f"{len(self.export.rows):,} rows" +
                               (f" · {len(self.export.schools)} schools found"
                                if self.export.schools else "") +
                               (f" · from {source}" if source else ""))
        if self.export.schools and not self.schools_text.toPlainText().strip():
            self.schools_text.setPlainText("\n".join(
                f"{k} = {v}" for k, v in sorted(self.export.schools.items())))
        return True

    _loading_profile = False

    def _remap(self, *_):
        headers = self.export.headers if self.export else []
        guess = sis.guess_mapping(headers, self.fmt.currentText())
        saved = getattr(self, "_saved_mapping", {}) or {}
        for key, cb in self.map.items():
            cur = saved.get(key) or guess.get(key, "")
            cb.clear()
            cb.addItem("(not in file)", "")
            for h in headers:
                cb.addItem(h, h)
            i = cb.findData(cur)
            cb.setCurrentIndex(max(0, i))

    def mapping(self) -> dict:
        return {k: cb.currentData() or "" for k, cb in self.map.items()}

    # =============================================================== rules ===
    def _rules_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box, form = self.group("Email addresses")
        self.domain = QLineEdit(placeholderText="yourschool.org")
        self.use_sis_email = QCheckBox("Use the email in the SIS file when there is one")
        self.use_sis_email.setChecked(True)
        self.email_tpl = QLineEdit("{first}.{last}{gradyear2}@{domain}")
        self.email_eg = QLabel("", objectName="Muted")
        form.addRow("Domain", self.domain)
        form.addRow("", self.use_sis_email)
        form.addRow("Otherwise build it as", self.email_tpl)
        form.addRow("", self.email_eg)
        lay.addWidget(box)

        box, form = self.group("Where accounts go")
        self.ou_tpl = QLineEdit("/Students/{school}/Grade {grade}")
        self.ou_eg = QLabel("", objectName="Muted")
        form.addRow("Org unit", self.ou_tpl)
        form.addRow("", self.ou_eg)
        self.schools_text = QPlainTextEdit()
        self.schools_text.setPlaceholderText("School ID = Name used in org units, one per line\n"
                                             "e.g. 101 = Hancock Middle")
        self.schools_text.setFixedHeight(90)
        form.addRow("School names", self.schools_text)
        self.year_end = QSpinBox()
        self.year_end.setRange(0, 2100)
        self.year_end.setSpecialValueText("Automatic")
        form.addRow("School year ends in", self.year_end)
        self._year_form = form
        tags = QLabel("Tags: {first} {last} {First} {Last} {f} {l} {id} {id4} {grade} {grade2} "
                      "{gradyear} {gradyear2} {school} {schoolid} {domain} {rand4} {title} {department}",
                      objectName="Muted")
        tags.setWordWrap(True)
        form.addRow("", tags)
        lay.addWidget(box)

        box, form = self.group("Students who leave")
        self.leave_box = box
        self.root = OUField(self.directory, "/Students")
        self.root.set_path("/Students")
        self.missing = QCheckBox("Students missing from the export count as withdrawn "
                                 "(use with full exports only)")
        self.missing.setChecked(True)
        self.w_action = QComboBox()
        for label, val in (("Suspend and move to the org unit below", "suspend_move"),
                           ("Suspend only", "suspend"), ("Just list them – change nothing",
                                                         "report")):
            self.w_action.addItem(label, val)
        self.w_ou = OUField(self.directory, "/Students/Withdrawn")
        self.w_ou.set_path("/Students/Withdrawn")
        form.addRow("Accounts managed under", self.root)
        form.addRow("", self.missing)
        self.inactive_vals = QLineEdit(sis.DEFAULT_INACTIVE)
        form.addRow("When they leave", self.w_action)
        form.addRow("Move them to", self.w_ou)
        form.addRow("Status values that mean “left”", self.inactive_vals)
        lay.addWidget(box)

        box, form = self.group("Passwords and updates")
        self.pw_mode = QComboBox()
        for label, val in (("Random, easy to read", "random"), ("Pattern", "pattern"),
                           ("From the SIS file", "column")):
            self.pw_mode.addItem(label, val)
        self.pw_pattern = QLineEdit("{First}{id4}{rand4}!")
        self.change_first = QCheckBox("Make students choose a new password at first sign-in")
        self.update_names = QCheckBox("Update names when the SIS changes them")
        self.move_ou = QCheckBox("Move students when their grade or school changes")
        self.store_id = QCheckBox("Save the SIS student ID on the account (best for matching)")
        self.update_job = QCheckBox("Keep job title and department in step with the roster")
        for cb in (self.change_first, self.update_names, self.move_ou, self.store_id,
                   self.update_job):
            cb.setChecked(True)
        form.addRow("New passwords", self.row(self.pw_mode, self.pw_pattern, stretch=False))
        form.addRow("", self.change_first)
        form.addRow("", self.update_names)
        form.addRow("", self.move_ou)
        form.addRow("", self.store_id)
        form.addRow("", self.update_job)
        self._pw_form = form
        lay.addWidget(box)

        box, form = self.group("New staff setup (onboarding)")
        self.onboard_box = box
        from ... import onboard
        self.onboard_on = QCheckBox("Give each new hire the full New staff setup")
        self.onboard_on.setToolTip("License, groups by building, the district signature and a "
                                   "welcome email to their supervisor.")
        self.onboard_on.setChecked(bool(onboard.options().get("enabled")))
        self.onboard_on.toggled.connect(self._onboard_toggled)
        self.onboard_sum = QLabel("", objectName="Muted")
        self.onboard_sum.setWordWrap(True)
        form.addRow(self.onboard_on)
        form.addRow(self.row(button("Choose groups, license and email…",
                                    slot=self._onboard_setup), self.onboard_sum))
        lay.addWidget(box)
        self._onboard_summary()
        lay.addStretch(1)
        for wdg in (self.email_tpl, self.ou_tpl, self.domain):
            wdg.textChanged.connect(self._examples)
        self.year_end.valueChanged.connect(self._examples)
        self._examples()
        return w

    def rules(self) -> sis.Rules:
        names = {}
        for ln in self.schools_text.toPlainText().splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                names[k.strip()] = v.strip()
        dom = self.domain.text().strip() or self.directory.domain
        return sis.Rules(
            kind=self.kind.currentData(), inactive_values=self.inactive_vals.text(),
            update_job=self.update_job.isChecked(),
            domain=dom, use_sis_email=self.use_sis_email.isChecked(),
            email_template=self.email_tpl.text().strip(),
            ou_template=self.ou_tpl.text().strip(),
            managed_root=self.root.path() or "/Students",
            withdrawn_action=self.w_action.currentData(),
            withdrawn_ou=self.w_ou.path(), missing_means_withdrawn=self.missing.isChecked(),
            password_mode=self.pw_mode.currentData(),
            password_pattern=self.pw_pattern.text(),
            change_at_first=self.change_first.isChecked(),
            update_names=self.update_names.isChecked(), move_ou=self.move_ou.isChecked(),
            store_sis_id=self.store_id.isChecked(), roles=self.roles.text().strip(),
            school_names=names, year_end=self.year_end.value())

    def _examples(self):
        r = self.rules()
        p = sis.Person("123456", "Ann-Marie", "O'Hara", "", "6", "101", "Hancock Middle",
                       title="Teacher", department="Science")
        self.email_eg.setText(f"Example: {sis._fill(r.email_template, p, r).lower()}")
        self.ou_eg.setText(f"Example: {sis._fill(r.ou_template, p, r)}")

    # ============================================================= preview ===
    def _preview_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        self.refresh_first = QCheckBox("Reload the Google user list first (recommended)")
        self.refresh_first.setChecked(True)
        row.addWidget(button("Build preview", "primary", self.build_preview))
        row.addWidget(self.refresh_first)
        row.addStretch(1)
        lay.addLayout(row)
        self.summary = QLabel("Load the export, check the rules, then build the preview.")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        lay.addWidget(self.summary)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Do it", "Change", "Account", "Name", "Details"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 54)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 260)
        self.table.setColumnWidth(3, 170)
        lay.addWidget(self.table, 1)
        sel = QHBoxLayout()
        sel.addWidget(QLabel("Tick:"))
        for label, act in (("All", None), ("New", "create"), ("Updates", "update"),
                           ("Returning", "reactivate"), ("Leaving", "withdraw")):
            sel.addWidget(button(label, slot=lambda _=False, a=act: self._tick(a, True)))
        sel.addWidget(button("None", slot=lambda: self._tick(None, False)))
        sel.addStretch(1)
        lay.addLayout(sel)
        sel = QHBoxLayout()
        self.dry = QCheckBox("Dry run (list the commands, change nothing)")
        self.dry.setChecked(bool(settings.get("safety/dry_run", False)))
        self.dry.toggled.connect(lambda on: self.app.set_dry_run(on))
        sel.addWidget(self.dry)
        self.test_mode = QCheckBox("Test mode")
        self.test_mode.setToolTip("Only touch accounts in the test org unit (Settings → "
                                  "Testing), create at most 3 new accounts there, and skip "
                                  "everyone else.")
        self.test_mode.toggled.connect(lambda _on: self._plan() if self.changes else None)
        sel.addWidget(self.test_mode)
        sel.addStretch(1)
        sel.addWidget(button("Export preview…", slot=self.export_preview))
        self.apply_btn = button("Apply ticked changes", "primary", self.apply)
        sel.addWidget(self.apply_btn)
        lay.addLayout(sel)
        self.steps = StepList(self)
        self.steps.setMaximumHeight(160)
        lay.addWidget(self.steps)
        self.cards_btn = button("Print password cards for new accounts…", slot=self.cards)
        self.cards_btn.setEnabled(False)
        lay.addLayout(self.row(self.cards_btn))
        self._created: list[dict] = []
        return w

    def build_preview(self):
        if not self.export:
            if self.load_file(then=self.build_preview) is False:
                return
            if not self.export:
                return
        if self.refresh_first.isChecked():
            self.summary.setText("Reloading the Google user list…")
            self.directory.refresh_users(on_done=lambda ok: self._plan() if ok else
                                         self.summary.setText("Couldn't load users from "
                                                              "Google. Test the connection."),
                                         log=self.app.log_line)
        else:
            self._plan()

    def _plan(self):
        rules = self.rules()
        if not rules.domain:
            self.info("Type your email domain on the Rules tab.")
            return
        people = sis.people_from_export(self.export, self.mapping(), rules)
        if not people:
            self.info("No people found in the roster. Check the column mapping and the "
                      "roles to include.")
            return
        self.changes = sis.plan(people, self.directory.users, rules)
        if rules.kind == "staff":
            from ... import onboard
            onboard.expand(self.changes, onboard.options(), rules.domain)
        if self.test_mode.isChecked():
            test_ou = (settings.get("safety/test_ou", "") or "").strip()
            if not test_ou:
                self.info("Set a test org unit in Settings & Updates → Testing first.")
                self.test_mode.setChecked(False)
            else:
                self.changes = sis.limit_to_test_ou(self.changes, self.directory.users,
                                                    test_ou)
        self._fill_table()
        s = sis.summarize(self.changes)
        managed = sum(1 for a in self.directory.users if sis._under(a.get("ou"),
                                                                    rules.managed_root))
        warn = ""
        wd = s.get("withdraw", 0)
        if managed and wd > max(25, managed * 0.1):
            warn = (f"<br><span style='color:#b42318'><b>⚠ {wd} people leaving is a lot "
                    f"({wd * 100 // managed}% of accounts under {rules.managed_root}).</b> "
                    "Make sure the roster includes everyone. Leavers are "
                    "un-ticked for safety.</span>")
            self._tick("withdraw", False)
        self.summary.setText(
            f"<b>{len(people):,}</b> {'staff' if rules.kind == 'staff' else 'students'} on "
            f"the roster · "
            f"<b>{s.get('create', 0)}</b> new · <b>{s.get('update', 0)}</b> updates · "
            f"<b>{s.get('reactivate', 0)}</b> back again · <b>{wd}</b> leaving"
            + (f" · {s.get('info', 0)} notes" if s.get("info") else "") + warn)
        self.tabs.setCurrentIndex(2)

    def _fill_table(self):
        self.table.setRowCount(0)
        for c in self.changes:
            r = self.table.rowCount()
            self.table.insertRow(r)
            chk = QTableWidgetItem()
            if c.commands:
                chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                chk.setCheckState(Qt.Checked if c.selected else Qt.Unchecked)
            else:
                chk.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(r, 0, chk)
            for col, val in ((1, ACTION_LABEL[c.action]), (2, c.email), (3, c.name),
                             (4, c.details)):
                it = QTableWidgetItem(val)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                it.setToolTip(val)
                self.table.setItem(r, col, it)

    def _tick(self, action, on):
        for r, c in enumerate(self.changes):
            if c.commands and (action is None or c.action == action):
                self.table.item(r, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def _ticked(self) -> list[sis.Change]:
        return [c for r, c in enumerate(self.changes)
                if c.commands and self.table.item(r, 0).checkState() == Qt.Checked]

    def apply(self):
        todo = self._ticked()
        if not todo:
            self.info("Nothing is ticked.")
            return
        s = sis.summarize(todo)
        if not self.confirm("Apply these changes in Google?\n\n" +
                            "\n".join(f"• {ACTION_LABEL[k]}: {v}" for k, v in s.items())):
            return
        self._created = []
        steps = []
        ou_of = {}
        offboards = []
        for c in todo:
            label = f"{ACTION_LABEL[c.action]}  {c.email}"
            if c.commands and c.commands[0][:1] == ["offboard"]:
                rec = self._offboard_plan(c)
                if rec is None:
                    continue
                offboards.append(rec)
                for st in rec["stages"][0]["steps"]:
                    def odone(code, _o, _e, rec=rec, sid=st["id"]):
                        rec.setdefault("_results", {})[sid] = code
                    steps.append(Step(f"{label}: {st['label']}", st["args"], on_done=odone))
                continue
            if c.action == "create":
                ou = c.commands[0][c.commands[0].index("ou") + 1]
                ou_of[c.email] = ou

                def done(code, _o, _e, c=c, ou=ou):
                    if code == 0:
                        self._created.append({"name": c.name, "email": c.email,
                                              "password": c.password, "group": ou})
                create = Step(label, c.commands[0], on_done=done)
                steps.append(create)
                for st in self._onboard_steps(c):
                    st.after = create            # no setup steps for a create that failed
                    steps.append(st)
            else:
                for cmd in c.commands:
                    steps.append(Step(label, cmd))
        self.apply_btn.setEnabled(False)

        def finished(_s):
            from ... import offboard
            from ...gam_runner import dry_run_on
            if not dry_run_on():
                for rec in offboards:
                    results = rec.pop("_results", {})
                    offboard.save(rec, sign_it=True)
                    offboard.mark(rec, "today", results)
            self.apply_btn.setEnabled(True)
            self.cards_btn.setEnabled(bool(self._created))
            settings.set("sis/last_run", __import__("datetime").datetime.now().isoformat(
                timespec="minutes"))
            self.info(self.steps.summary() + (f"\n\n{len(self._created)} new account(s) – "
                                              "print their password cards below."
                                              if self._created else ""))
            self.directory.refresh_users()
        self.steps.run(steps, finished)

    def _onboard_steps(self, c) -> list:
        """Onboarding steps after a create (license, groups, signature, welcome)."""
        from ... import onboard
        out = []
        for cmd in c.commands[1:]:
            label = f"   ↳ {c.email}: " + (
                "set signature" if onboard.is_retryable(cmd) else
                f"add to {cmd[2]}" if cmd[:2] == ["update", "group"] else
                "assign license" if "license" in cmd else
                "welcome email to " + cmd[2] if cmd[:1] == ["sendemail"] else "setup")

            def odone(code, _o, _e, cmd=cmd, email=c.email):
                from ...gam_runner import dry_run_on
                if code and onboard.is_retryable(cmd) and not dry_run_on():
                    onboard.queue_retry(email, cmd, "email signature")
                    self.app.log_line(f"Signature for {email} will be tried again "
                                      "automatically (the mailbox may not be ready yet).")
            out.append(Step(label, cmd, on_done=odone))
        return out

    def _onboard_toggled(self, on):
        from ... import onboard
        o = onboard.options()
        o["enabled"] = bool(on)
        onboard.save_options(o)
        self._onboard_summary()

    def _onboard_summary(self):
        from ... import onboard
        o = onboard.options()
        if not o.get("enabled"):
            self.onboard_sum.setText("Off – new accounts are just created.")
            return
        n = len(onboard.parse_groups(o.get("groups", "")))
        self.onboard_sum.setText(
            f"License: {o.get('license') or 'none'} · {n} group rule(s) · signature "
            f"{'on' if o.get('signature') else 'off'} · welcome email "
            f"{'on' if o.get('welcome') else 'off'}")

    def _onboard_setup(self):
        from ..onboard_dialog import OnboardDialog
        if OnboardDialog(self, self.directory).exec():
            from ... import onboard
            self.onboard_on.blockSignals(True)
            self.onboard_on.setChecked(bool(onboard.options().get("enabled")))
            self.onboard_on.blockSignals(False)
            self._onboard_summary()

    def _offboard_plan(self, c):
        from ... import offboard
        from ...directory import run_gam_csv
        from .users import random_password
        before = offboard.capture(c.email, lambda a: run_gam_csv(a, 120))
        return offboard.build(c.email, c.supervisor, before, offboard.options(),
                              random_password)

    def cards(self):
        if self._created:
            CardsDialog(self, self._created).exec()

    def export_preview(self):
        if not self.changes:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export preview", "roster-sync-preview.csv",
                                              "CSV (*.csv)")
        if path:
            from ... import csv_safe
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv_safe.writer(fh)
                w.writerow(["Change", "Account", "Name", "Details"])
                for c in self.changes:
                    w.writerow([c.action, c.email, c.name, c.details])

    def dry_changed(self, on: bool):
        self.dry.blockSignals(True)
        self.dry.setChecked(on)
        self.dry.blockSignals(False)

    # ================================================================ kind ===
    def _kind_changed(self, *_, apply_defaults=True):
        staff = self.kind.currentData() == "staff"
        if apply_defaults and not self._loading_profile:
            d = sis.Rules.for_staff() if staff else sis.Rules()
            self.roles.setText(d.roles)
            self.email_tpl.setText(d.email_template)
            self.ou_tpl.setText(d.ou_template)
            self.root.set_path(d.managed_root)
            self.w_ou.set_path(d.withdrawn_ou)
            self.missing.setChecked(d.missing_means_withdrawn)
            self.move_ou.setChecked(d.move_ou)
            off = self.w_action.findData("offboard")
            if staff and off < 0:
                self.w_action.addItem("Full offboarding (Workflows → Staff leaving steps)",
                                      "offboard")
            elif not staff and off >= 0:
                if self.w_action.currentIndex() == off:
                    self.w_action.setCurrentIndex(0)
                self.w_action.removeItem(off)
            if staff and not self.fmt.currentText().startswith("ClassLink"):
                self.fmt.setCurrentText("Staff sheet / HR export")
            elif not staff and self.fmt.currentText().startswith("Staff"):
                self.fmt.setCurrentText("ClassLink / OneRoster")
        who = "staff" if staff else "students"
        self.leave_box.setTitle("Staff who leave" if staff else "Students who leave")
        self.onboard_box.setVisible(staff)
        self.missing.setText(f"{who.title()} missing from the roster have left "
                             "(full exports only)")
        self.missing.setToolTip("Leave this off for a running sheet that only lists some "
                                "people, such as new hires.")
        self.change_first.setText(f"Make new {who} choose a new password at first sign-in")
        self.move_ou.setText("Move staff when their building changes" if staff else
                             "Move students when their grade or school changes")
        self.store_id.setText("Save the employee ID on the account (best for matching)"
                              if staff else
                              "Save the SIS student ID on the account (best for matching)")
        self._year_form.setRowVisible(self.year_end, not staff)
        self._pw_form.setRowVisible(self.update_job, staff)
        for key, cb in self.map.items():
            lbl = self.map_form.labelForField(cb)
            if lbl:
                lbl.setText((STAFF_LABEL.get(key) if staff else None) or FIELD_LABEL[key])
            hide = (staff and key == "grade") or \
                (not staff and key in ("title", "department", "manager"))
            self.map_form.setRowVisible(cb, not hide)
        self._examples()

    # ============================================================ profiles ===
    def _all_profiles(self) -> dict:
        try:
            return json.loads(settings.get("sis/profiles", "{}") or "{}")
        except ValueError:
            return {}

    def _profiles(self):
        cur = self.profile.currentText()
        self.profile.clear()
        names = sorted(self._all_profiles())
        self.profile.addItems(names or ["(none saved yet)"])
        if cur in names:
            self.profile.setCurrentText(cur)

    def save_profile(self):
        name, ok = QInputDialog.getText(self, "Save sync settings", "Name (e.g. ClassLink "
                                        "students):", text=self.profile.currentText()
                                        if self._all_profiles() else "ClassLink students")
        if not ok or not name.strip():
            return
        data = self._all_profiles()
        data[name.strip()] = {
            "format": self.fmt.currentText(), "path": self.path.text(),
            "kind": self.kind.currentData(), "source": self.source.currentData(),
            "sheet_url": self.sheet_url.text(), "sheet_tab": self.sheet_tab.text(),
            "sheet_user": self.sheet_user.text(),
            "schools_path": self.schools_path.text(), "roles": self.roles.text(),
            "mapping": self.mapping(), "schools": self.schools_text.toPlainText(),
            "rules": {k: v for k, v in dataclasses.asdict(self.rules()).items()
                      if k not in ("school_names",)},
        }
        settings.set("sis/profiles", json.dumps(data))
        settings.set("sis/last_profile", name.strip())
        self._profiles()
        self.profile.setCurrentText(name.strip())

    def load_profile(self, name):
        p = self._all_profiles().get(name)
        if not p:
            return
        self._loading_profile = True
        self.kind.setCurrentIndex(max(0, self.kind.findData(p.get("kind", "students"))))
        self.source.setCurrentIndex(max(0, self.source.findData(p.get("source", "file"))))
        self.sheet_url.setText(p.get("sheet_url", ""))
        self.sheet_tab.setText(p.get("sheet_tab", ""))
        self.sheet_user.setText(p.get("sheet_user", "") or google_io.admin_email())
        self.fmt.setCurrentText(p.get("format", self.fmt.currentText()))
        self.path.setText(p.get("path", ""))
        self.schools_path.setText(p.get("schools_path", ""))
        self.roles.setText(p.get("roles", "student"))
        self.schools_text.setPlainText(p.get("schools", ""))
        r = p.get("rules", {})
        self.domain.setText(r.get("domain", ""))
        self.use_sis_email.setChecked(r.get("use_sis_email", True))
        self.email_tpl.setText(r.get("email_template", self.email_tpl.text()))
        self.ou_tpl.setText(r.get("ou_template", self.ou_tpl.text()))
        self.root.set_path(r.get("managed_root", "/Students"))
        self.missing.setChecked(r.get("missing_means_withdrawn", True))
        self.w_action.setCurrentIndex(max(0, self.w_action.findData(
            r.get("withdrawn_action", "suspend_move"))))
        self.w_ou.set_path(r.get("withdrawn_ou", ""))
        self.pw_mode.setCurrentIndex(max(0, self.pw_mode.findData(r.get("password_mode",
                                                                          "random"))))
        self.pw_pattern.setText(r.get("password_pattern", "{First}{id4}{rand4}!"))
        self.change_first.setChecked(r.get("change_at_first", True))
        self.update_names.setChecked(r.get("update_names", True))
        self.move_ou.setChecked(r.get("move_ou", True))
        self.store_id.setChecked(r.get("store_sis_id", True))
        self.year_end.setValue(r.get("year_end", 0))
        self.inactive_vals.setText(r.get("inactive_values", sis.DEFAULT_INACTIVE))
        self.update_job.setChecked(r.get("update_job", True))
        self._saved_mapping = p.get("mapping", {})
        if self.source.currentData() == "file" and self.path.text() and \
                os.path.isfile(self.path.text()):
            self.load_file()
        else:
            self._remap()
        self._loading_profile = False
        self.profile.setCurrentText(name)
        settings.set("sis/last_profile", name)

    def schedule(self):
        name = self.profile.currentText()
        data = self._all_profiles()
        if name not in data:
            self.info("Save these settings first (Save settings as…), then schedule them.")
            return
        from ... import scheduler
        clash = [n for n in data if n != name and data[n].get("schedule") and
                 scheduler.slug(n).lower() == scheduler.slug(name).lower()]
        if clash:   # both would share one Windows task, and one would silently replace the other
            self.info(f"“{name}” is too close to the scheduled sync “{clash[0]}” – Windows "
                      "would treat them as the same task. Save these settings under a more "
                      "different name first.")
            return
        from .rostersync_schedule import ScheduleDialog
        dlg = ScheduleDialog(self, name, data[name].get("schedule", {}))
        if dlg.exec():
            data = self._all_profiles()
            data[name]["schedule"] = dlg.result_opts()
            settings.set("sis/profiles", json.dumps(data))
            try:
                dlg.create_task()
            except Exception as exc:  # noqa: BLE001
                self.info(f"Saved, but couldn't create the Windows scheduled task:\n{exc}")
                return
            self.info(f"“{name}” will run every day at {dlg.time.time().toString('h:mm AP')}. "
                      "New accounts and updates are applied; anyone leaving goes to the "
                      "Approvals page. Results are emailed if you set an address.")

    def delete_profile(self):
        name = self.profile.currentText()
        data = self._all_profiles()
        if name in data and self.confirm(f"Delete the saved sync “{name}”?"):
            data.pop(name)
            settings.set("sis/profiles", json.dumps(data))
            self._profiles()
