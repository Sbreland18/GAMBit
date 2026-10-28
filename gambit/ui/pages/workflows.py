"""Guided workflows: new staff, staff leaving, year-end rollover, Chromebook check-in/out."""

from __future__ import annotations

import datetime
import html
import json
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QPlainTextEdit, QRadioButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget,
    QTextBrowser, QVBoxLayout, QWidget,
)

from ... import team
from ...settings import settings
from ..pickers import OUField, OUMultiField, PeoplePicker, PersonField
from ..steps import Step, StepList
from ..widgets import Page, ResultsTable, button
from .email import SIGNATURE_TEMPLATE, tag_replacements
from .licenses import SKUS
from .users import random_password


def _scroll(w: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QScrollArea.NoFrame)
    w.setObjectName("Page")
    s.setWidget(w)
    return s


def _natural(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


# =============================================================== welcome ===
class WelcomeSheet(QDialog):
    """Printable sign-in sheet for a new account."""

    def __init__(self, parent, name, email, password, change):
        super().__init__(parent)
        self.setWindowTitle(f"Welcome sheet – {name}")
        self.resize(620, 560)
        esc = html.escape
        self.html = f"""
        <h2 style="margin-bottom:2px">Welcome, {esc(name)}!</h2>
        <p style="color:#57606a;margin-top:0">Your Google Workspace account is ready.</p>
        <table cellpadding="6" style="font-size:12pt">
          <tr><td><b>Email / username</b></td><td>{esc(email)}</td></tr>
          <tr><td><b>Temporary password</b></td>
              <td style="font-family:Consolas,monospace;font-size:14pt">{esc(password)}</td></tr>
          <tr><td><b>Sign in at</b></td><td>https://accounts.google.com</td></tr>
        </table>
        <ol>
          <li>Go to <b>accounts.google.com</b> and sign in with the email above.</li>
          <li>Type the temporary password.</li>
          {"<li>Choose a new password you'll remember. Don't share it.</li>" if change else ""}
          <li>Open Gmail, Drive and Classroom from the app grid (the 9 dots, top right).</li>
        </ol>
        <p style="color:#57606a">Keep this sheet somewhere safe, or shred it once you've
        signed in.</p>"""
        view = QTextBrowser()
        view.setHtml(self.html)
        lay = QVBoxLayout(self)
        lay.addWidget(view, 1)
        row = QHBoxLayout()
        row.addWidget(button("Print…", "primary", self.print_))
        row.addWidget(button("Save as PDF…", slot=self.pdf))
        row.addWidget(button("Copy text", slot=lambda: QApplication.clipboard().setText(
            f"Email: {email}\nTemporary password: {password}\nSign in at accounts.google.com")))
        row.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        row.addWidget(close)
        lay.addLayout(row)
        self.email = email

    def _doc(self):
        d = QTextDocument()
        d.setHtml(self.html)
        return d

    def print_(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        p = QPrinter()
        if QPrintDialog(p, self).exec():
            self._doc().print_(p)

    def pdf(self):
        from PySide6.QtPrintSupport import QPrinter
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF",
                                              f"welcome-{self.email.split('@')[0]}.pdf",
                                              "PDF (*.pdf)")
        if path:
            p = QPrinter()
            p.setOutputFormat(QPrinter.PdfFormat)
            p.setOutputFileName(path)
            self._doc().print_(p)


# ================================================================== page ===
class WorkflowsPage(Page):
    title = "Workflows"
    subtitle = "Step-by-step helpers for the jobs you do over and over."

    def build(self):
        bar = QHBoxLayout()
        self.dry = QCheckBox("Dry run – list the GAM commands, change nothing")
        self.dry.setChecked(bool(settings.get("safety/dry_run", False)))
        self.dry.toggled.connect(lambda on: self.app.set_dry_run(on))
        bar.addWidget(self.dry)
        bar.addSpacing(16)
        self.test_btn = button("Fill in the test account", slot=self.use_test_account)
        self.test_btn.setToolTip("Try a workflow on the test account / test org unit from "
                                 "Settings → Testing before using it on a real person.")
        bar.addWidget(self.test_btn)
        bar.addStretch(1)
        self.body.addLayout(bar)
        self.tabs = QTabWidget()
        self.tabs.addTab(_scroll(self._new_staff()), "New staff")
        self.tabs.addTab(_scroll(self._leaving()), "Staff leaving")
        self.tabs.addTab(_scroll(self._rollover()), "Year-end rollover")
        from .insight_pages import YearEndTab
        self.yearend_tab = YearEndTab(self)
        self.tabs.addTab(self.yearend_tab, "Year-end checklist")
        self.tabs.addTab(self._checkout(), "Chromebook check-in/out")
        self.tabs.addTab(_scroll(self._graduation()), "Graduation")
        from .security_tabs import HackedAccountTab
        self.hacked_tab = HackedAccountTab(self)
        self.tabs.addTab(self.hacked_tab, "Hacked account")
        from .custom_wf_tab import CustomWorkflowsTab
        self.custom_tab = CustomWorkflowsTab(self)
        self.tabs.addTab(self.custom_tab, "My workflows")
        from .round12_pages import ReadinessTab
        self.readiness_tab = ReadinessTab(self)
        self.tabs.insertTab(1, self.readiness_tab, "Day-one readiness")
        self.body.addWidget(self.tabs, 1)

    def dry_changed(self, on: bool):
        self.dry.blockSignals(True)
        self.dry.setChecked(on)
        self.dry.blockSignals(False)

    def use_test_account(self):
        test_ou = (settings.get("safety/test_ou", "") or "").strip()
        test_user = (settings.get("safety/test_user", "") or "").strip()
        tab = self.tabs.tabText(self.tabs.currentIndex())
        if not test_ou and not test_user:
            self.info("Set a test org unit and test account in Settings & Updates → Testing.")
            return
        if tab == "New staff":
            self.ns_first.setText("GAMbit")
            import random
            self.ns_last.setText("Test" + "".join(random.choice("bcdfghjkmnpqrstvwxz")
                                                  for _ in range(4)))
            if test_ou:
                self.ns_ou.set_path(test_ou)
        elif tab == "Staff leaving":
            if "@" not in test_user:
                self.info("Set a test account in Settings & Updates → Testing.")
                return
            self.lv_user.setText(test_user)
        else:
            self.info("The test account fills in the New staff and Staff leaving tabs. For "
                      "the rollover, turn on Dry run first.")

    def set_helpdesk(self, on: bool):
        # Offboarding and rollover make big changes – hide them in help-desk mode
        self._hd = on
        self._tab_visibility()

    def set_role(self, role: dict):
        self._role_tabs = role.get("workflows") or []
        self._tab_visibility()

    def _tab_visibility(self):
        hd, allowed = getattr(self, "_hd", False), getattr(self, "_role_tabs", [])
        first = None
        for i in range(self.tabs.count()):
            name = self.tabs.tabText(i)
            vis = not (hd and name in ("Staff leaving", "Year-end rollover",
                                                 "Year-end checklist", "Graduation")) \
                and (not allowed or name in allowed)
            self.tabs.setTabVisible(i, vis)
            if vis and first is None:
                first = i
        if first is not None and not self.tabs.isTabVisible(self.tabs.currentIndex()):
            self.tabs.setCurrentIndex(first)

    def _domain(self) -> str:
        d = self.directory.domain
        if not d:
            admin = settings.get("gam/admin", "") or ""
            d = admin.split("@", 1)[1] if "@" in admin else ""
        return d

    # ============================================================ new staff ===
    def _new_staff(self):
        from ..stepper import Stepper
        w = QWidget()
        lay = QVBoxLayout(w)

        s1 = QWidget()
        l1 = QVBoxLayout(s1)
        l1.setContentsMargins(0, 0, 0, 0)
        box, form = self.group("About the person")
        self.ns_first = QLineEdit()
        self.ns_last = QLineEdit()
        self.ns_email = QLineEdit()
        self.ns_auto = True
        self.ns_email.textEdited.connect(lambda _t: setattr(self, "ns_auto", False))
        self.ns_first.textChanged.connect(self._ns_suggest)
        self.ns_last.textChanged.connect(self._ns_suggest)
        self.ns_title = QLineEdit(placeholderText="e.g. 3rd Grade Teacher")
        self.ns_dept = QLineEdit(placeholderText="e.g. Elementary")
        self.ns_ou = OUField(self.directory, "e.g. /Staff/Teachers")
        form.addRow("First name", self.ns_first)
        form.addRow("Last name", self.ns_last)
        form.addRow("Email", self.ns_email)
        form.addRow("Job title", self.ns_title)
        form.addRow("Department / school", self.ns_dept)
        form.addRow("Org unit", self.ns_ou)
        l1.addWidget(box)
        l1.addStretch(1)

        s2 = QWidget()
        l2 = QVBoxLayout(s2)
        l2.setContentsMargins(0, 0, 0, 0)
        box, form = self.group("Password, license, groups and signature")
        self.ns_pw = QLineEdit(random_password())
        form.addRow("Temporary password", self.row(
            self.ns_pw, button("New", slot=lambda: self.ns_pw.setText(random_password())),
            stretch=False))
        self.ns_change = QCheckBox("Make them choose a new password when they first sign in")
        self.ns_change.setChecked(True)
        form.addRow("", self.ns_change)
        self.ns_license = QComboBox()
        self.ns_license.addItem("Don't assign a license", "")
        for name, sku in SKUS:
            self.ns_license.addItem(name, sku)
        form.addRow("License", self.ns_license)
        self.ns_sig = QCheckBox("Apply the signature template from Email → Signatures")
        self.ns_sig.setChecked(True)
        form.addRow("", self.ns_sig)
        form.addRow(QLabel("Add to groups:"))
        self.ns_groups = PeoplePicker(self.directory, include_groups=True)
        self.ns_groups.search.setPlaceholderText("Search groups (e.g. All Staff)…")
        form.addRow(self.ns_groups)
        l2.addWidget(box)
        l2.addStretch(1)

        sheet = button("Print welcome sheet again", slot=self._ns_sheet)
        self.ns_stepper = Stepper(
            [("About the person", s1), ("What to set up", s2)], self._ns_review,
            "Create account and set everything up", lambda: self.ns_run(),
            validate={0: self._ns_valid_person, 1: self._ns_valid_setup},
            extra_buttons=(sheet,))
        lay.addWidget(self.ns_stepper)
        self.ns_steps = StepList(self)
        lay.addWidget(self.ns_steps)
        self._ns_last = None
        from ..unsaved import track
        track(self, self.ns_stepper, "a new staff account", self.ns_stepper.finish_btn)
        return w

    def _ns_valid_person(self) -> bool:
        return self.need(("a first name", self.ns_first), ("a last name", self.ns_last),
                         ("an email address", self.ns_email), emails=[self.ns_email])

    def _ns_valid_setup(self) -> bool:
        return self.need(("a temporary password", self.ns_pw))

    def _ns_review(self):
        from ...gam_runner import display_command
        return [(st.label.split(" (")[0], display_command(st.args))
                for st in self._ns_plan()]

    def _ns_suggest(self):
        if not self.ns_auto:
            return
        f = re.sub(r"[^a-z0-9]", "", self.ns_first.text().lower())
        last = re.sub(r"[^a-z0-9]", "", self.ns_last.text().lower())
        dom = self._domain()
        if f and last and dom:
            self.ns_email.setText(f"{f}.{last}@{dom}")

    def _ns_plan(self) -> list:
        first, last = self.ns_first.text().strip(), self.ns_last.text().strip()
        email, pw = self.ns_email.text().strip(), self.ns_pw.text().strip()
        create = ["create", "user", email, "firstname", first, "lastname", last,
                  "password", pw, "changepassword", "on" if self.ns_change.isChecked() else "off"]
        if self.ns_ou.path():
            create += ["ou", self.ns_ou.path()]
        if self.ns_title.text().strip() or self.ns_dept.text().strip():
            create += ["organization"]
            if self.ns_title.text().strip():
                create += ["title", self.ns_title.text().strip()]
            if self.ns_dept.text().strip():
                create += ["department", self.ns_dept.text().strip()]
            create += ["primary"]
        steps = [Step(f"Create {email}", create, required=True)]
        if self.ns_license.currentData():
            steps.append(Step(f"Assign {self.ns_license.currentText()}",
                              ["user", email, "add", "license", self.ns_license.currentData()]))
        for g in self.ns_groups.emails():
            steps.append(Step(f"Add to {g}", ["update", "group", g, "add", "member", "user",
                                               email]))
        if self.ns_sig.isChecked():
            sig = team.setting("email/signature", "") or SIGNATURE_TEMPLATE
            steps.append(Step("Set email signature (can fail if the mailbox isn't ready yet – "
                              "try again from Email → Signatures in a few minutes)",
                              ["user", email, "signature", sig, *tag_replacements(sig),
                               "html", "true"]))
        return steps

    def ns_run(self):
        """Runs the plan shown on the Review step."""
        if not (self._ns_valid_person() and self._ns_valid_setup()):
            self.ns_stepper.go(0 if not self.ns_email.text().strip() or
                               not self.ns_first.text().strip() else 1)
            return
        first, last = self.ns_first.text().strip(), self.ns_last.text().strip()
        email, pw = self.ns_email.text().strip(), self.ns_pw.text().strip()
        steps = self._ns_plan()
        self._ns_last = (f"{first} {last}", email, pw, self.ns_change.isChecked())

        def finished(_steps):
            ok = _steps[0].status == "ok"
            if not ok:
                self.info(self.ns_steps.summary(), "New staff")
            if ok:
                self.directory.refresh_users()
                from ..next_steps import NextSteps, for_new_account
                failed = [s.label for s in _steps if s.status == "fail"]
                note = ("<br><br>These didn't work: " + "; ".join(failed)) if failed else ""
                NextSteps(self, "New staff account ready",
                          f"<b>{email}</b> is set up ({len(_steps)} step(s)).<br>Temporary "
                          f"password: <b>{pw}</b>{note}",
                          for_new_account(self.app, email, sheet=self._ns_sheet) +
                          [("Set up another", lambda: self.ns_first.setFocus())],
                          copy_text=pw, ok=not failed).run()
                for wdg in (self.ns_first, self.ns_last, self.ns_email, self.ns_title,
                            self.ns_dept):
                    wdg.clear()
                self.ns_auto = True
                self.ns_pw.setText(random_password())
                self.ns_groups.clear()
                self.ns_stepper.reset()
        self.ns_steps.run(steps, finished)

    def _ns_sheet(self):
        if not self._ns_last:
            self.info("Create an account first.")
            return
        WelcomeSheet(self, *self._ns_last).exec()

    # ============================================================== leaving ===
    def _leaving(self):
        from ... import offboard
        opts = offboard.options()
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        box, form = self.group("Who")
        self.lv_user = PersonField(self.directory, "Person who is leaving")
        self.lv_mgr = PersonField(self.directory, "Supervisor (gets their mail and files)")
        form.addRow("Leaving", self.lv_user)
        form.addRow("Supervisor", self.lv_mgr)
        self.lv_msg = QPlainTextEdit(opts["message"])
        self.lv_msg.setFixedHeight(80)
        form.addRow("Auto-reply", self.lv_msg)
        form.addRow("", QLabel("{name} and {supervisor} are filled in for you.",
                               objectName="Muted"))
        self.lv_ou = OUField(self.directory, "/Former Staff")
        self.lv_ou.set_path(opts["ou"])
        form.addRow("Move to org unit", self.lv_ou)
        self.lv_fwd = QSpinBox()
        self.lv_fwd.setRange(1, 365)
        self.lv_fwd.setValue(int(opts["forward_days"]))
        self.lv_fwd.setSuffix(" days")
        form.addRow("Forward email for", self.lv_fwd)
        self.lv_del = QSpinBox()
        self.lv_del.setRange(1, 3650)
        self.lv_del.setValue(int(opts["delete_days"]))
        self.lv_del.setSuffix(" days")
        form.addRow("Offer to delete after", self.lv_del)
        self.lv_arch = QLineEdit(opts.get("archive_group", "") or "")
        self.lv_arch.setPlaceholderText("optional, e.g. staff-mail-archive@yourschool.org")
        form.addRow("Archive email to group", self.lv_arch)
        top.addWidget(box, 1)

        box = QGroupBox("Steps")
        bl = QVBoxLayout(box)
        self.lv = {}
        heads = {"today": "<b>Today</b>", "later": "<b>When forwarding ends</b>",
                 "delete": "<b>Later</b>"}
        shown = set()
        for key, (when, text) in offboard.STEP_INFO.items():
            if when not in shown:
                shown.add(when)
                bl.addWidget(QLabel(heads[when]))
            cb = QCheckBox(text)
            cb.setChecked(key in opts["steps"])
            self.lv[key] = cb
            bl.addWidget(cb)
        bl.addWidget(QLabel("Steps marked “when forwarding ends” run by themselves – while "
                            "GAMbit is open, or from the daily background task.",
                            objectName="Muted"))
        top.addWidget(box, 1)
        lay.addLayout(top)
        lay.addLayout(self.row(button("Preview the plan", slot=self.lv_preview),
                               button("Start offboarding", "primary", self.lv_run)))
        self.lv_steps = StepList(self)
        lay.addWidget(self.lv_steps)

        box = QGroupBox("People who have left")
        bl = QVBoxLayout(box)
        self.lv_table = QTableWidget(0, 5)
        self.lv_table.setHorizontalHeaderLabels(["Person", "Supervisor", "Started", "Next",
                                                 "Status"])
        self.lv_table.verticalHeader().setVisible(False)
        self.lv_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.lv_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.lv_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for c, wd in ((0, 240), (1, 220), (2, 110), (4, 110)):
            self.lv_table.setColumnWidth(c, wd)
        self.lv_table.setMinimumHeight(170)
        bl.addWidget(self.lv_table)
        bl.addLayout(self.row(button("Refresh", slot=self.lv_refresh),
                              button("Show details", slot=self.lv_details),
                              button("Other data…", slot=self.lv_other),
                              button("Run the next step now", slot=self.lv_run_next),
                              button("Undo everything…", slot=self.lv_undo),
                              button("Delete the account…", "danger", self.lv_delete)))
        lay.addWidget(box)
        self.lv_refresh()
        return w

    def _lv_opts(self) -> dict:
        from ... import offboard
        opts = {"forward_days": self.lv_fwd.value(), "delete_days": self.lv_del.value(),
                "ou": self.lv_ou.path(), "message": self.lv_msg.toPlainText(),
                "archive_group": self.lv_arch.text().strip(),
                "steps": [k for k, cb in self.lv.items() if cb.isChecked()]}
        offboard.save_options(opts)
        return opts

    def _lv_plan(self):
        from ... import offboard
        from ...directory import run_gam_csv
        u, m = self.lv_user.email(), self.lv_mgr.email()
        if "@" not in u:
            self.info("Choose the person who is leaving.")
            return None
        if u.lower() == m.lower():
            self.info("The supervisor can't be the person who is leaving.")
            return None
        opts = self._lv_opts()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            before = offboard.capture(u, lambda a: run_gam_csv(a, 120))
        finally:
            QApplication.restoreOverrideCursor()
        return offboard.build(u, m, before, opts, random_password)

    def lv_preview(self):
        rec = self._lv_plan()
        if not rec:
            return
        from ...gam_runner import display_command
        lines = []
        for st in rec["stages"]:
            lines.append(f"{st['title']} ({st['due']})")
            for step in st["steps"]:
                lines.append(f"   • {step['label']}" + (f"   [{step['note']}]" if step.get(
                    "note") else ""))
                lines.append(f"       {display_command(step['args'])}")
        lines += [""] + rec["notes"]
        b = rec["before"]
        lines += ["", f"Saved for undo: {len(b['groups'])} group(s), "
                      f"{len(b['licenses'])} license(s), org unit {b['ou'] or '/'}"]
        self.info("\n".join(lines), "Offboarding plan")

    def lv_run(self):
        from ... import offboard
        from ...gam_runner import dry_run_on
        rec = self._lv_plan()
        if not rec:
            return
        if offboard.get(rec["email"]) and offboard.get(rec["email"]).get("status") == "active":
            if not self.confirm(f"{rec['email']} is already being offboarded. Start again?"):
                return
        st = rec["stages"][0]
        plan = "\n".join(f"• {s['label']}" for s in st["steps"])
        later = "\n".join(f"{x['title']} ({x['due']}): " + ", ".join(
            s["label"] for s in x["steps"]) for x in rec["stages"][1:])
        if not self.confirm(f"Offboard {rec['email']}?\n\nToday:\n{plan}\n\n{later}",
                            "Staff leaving"):
            return
        dry = dry_run_on()
        results = {}
        steps = []
        for s in st["steps"]:
            def done(code, _o, _e, sid=s["id"]):
                results[sid] = code
            steps.append(Step(s["label"], s["args"], on_done=done))

        def finished(_s):
            if dry:
                self.info(self.lv_steps.summary(), "Staff leaving")
                return
            offboard.save(rec)
            offboard.mark(rec, "today", results)
            self._ensure_daily_task()
            self.lv_refresh()
            self.info(self.lv_steps.summary() + "\n\nThe rest of the plan runs by itself – "
                      "see “People who have left” below.", "Staff leaving")
        self.lv_steps.run(steps, finished)

    def _ensure_daily_task(self):
        from ... import scheduler
        from ...settings import IS_WINDOWS
        if not IS_WINDOWS or settings.get("tasks/daily_created", False):
            return
        try:
            script = scheduler.build_app_task_script("GAMbit daily follow-ups",
                                                     ["--task", "daily"])
            scheduler.create_task("GAMbit daily follow-ups", script, "daily", "06:15")
            settings.set("tasks/daily_created", True)
            self.app.log_line("Scheduled “GAMbit daily follow-ups” (6:15 AM) so offboarding "
                              "steps run even when GAMbit is closed.", "#7cc4ff")
        except Exception as exc:  # noqa: BLE001
            self.app.log_line(f"Couldn't schedule the daily follow-ups: {exc}", "#ff8a80")

    def lv_refresh(self):
        from ... import offboard
        self.lv_records = offboard.load_all()
        self.lv_table.setRowCount(0)
        for rec in self.lv_records:
            r = self.lv_table.rowCount()
            self.lv_table.insertRow(r)
            vals = [rec["email"], rec.get("supervisor", ""), rec.get("started", "")[:10],
                    offboard.describe(rec), rec.get("status", "")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setToolTip(v)
                self.lv_table.setItem(r, c, it)

    def _lv_selected(self):
        rows = sorted({i.row() for i in self.lv_table.selectedIndexes()})
        if not rows:
            self.info("Select a person in “People who have left”.")
            return None
        return self.lv_records[rows[0]]

    def lv_other(self):
        rec = self._lv_selected()
        if rec:
            from .recovery_tabs import OtherDataDialog
            OtherDataDialog(self, rec["email"]).exec()

    def lv_details(self):
        rec = self._lv_selected()
        if not rec:
            return
        icon = {"done": "✔", "failed": "✖", "pending": "○", "skipped": "–"}
        lines = [f"{rec['email']} – started {rec['started'].replace('T', ' ')} by "
                 f"{rec.get('by', '')}", ""]
        for st in rec["stages"]:
            lines.append(f"{st['title']} (due {st['due']})" +
                         (f" – done {st['done']}" if st.get("done") else ""))
            lines += [f"   {icon.get(s['status'], '?')} {s['label']}" for s in st["steps"]]
        self.info("\n".join(lines), "Offboarding")

    def _lv_run_steps(self, rec, stage_key, steps_spec, title, after=None):
        from ... import offboard
        from ...gam_runner import dry_run_on
        results = {}
        steps = []
        for s in steps_spec:
            def done(code, _o, _e, sid=s["id"]):
                results[sid] = code
            steps.append(Step(s["label"], s["args"], on_done=done))

        def finished(_s):
            if not dry_run_on():
                if stage_key:
                    offboard.mark(rec, stage_key, results)
                if after:
                    after(results)
            self.lv_refresh()
            self.info(self.lv_steps.summary(), title)
        self.lv_steps.run(steps, finished)

    def lv_run_next(self):
        from ... import offboard
        rec = self._lv_selected()
        if not rec:
            return
        st = offboard.next_stage(rec)
        if not st or rec.get("status") != "active":
            self.info("Nothing left to run for this person.")
            return
        if st["key"] == "delete":
            self.lv_delete()
            return
        todo = [s for s in st["steps"] if s["status"] != "done"]
        if self.confirm(f"Run “{st['title']}” for {rec['email']} now (due {st['due']})?\n\n" +
                        "\n".join(f"• {s['label']}" for s in todo)):
            self._lv_run_steps(rec, st["key"], todo, "Staff leaving")

    def lv_undo(self):
        from ... import offboard
        rec = self._lv_selected()
        if not rec:
            return
        steps = offboard.undo_steps(rec)
        if not steps:
            self.info("Nothing to undo yet.")
            return
        no = offboard.cannot_undo(rec)
        extra = ("\n\nThese can't be undone:\n• " + "\n• ".join(no)) if no else ""
        if not self.confirm(f"Put {rec['email']} back?\n\n" +
                            "\n".join(f"• {s['label']}" for s in steps) + extra +
                            "\n\nThey'll need a new password from Users → Reset password."):
            return

        def after(results):
            rec["status"] = "undone"
            rec["undone"] = datetime.datetime.now().isoformat(timespec="minutes")
            offboard.save(rec)
        self._lv_run_steps(rec, "", steps, "Undo offboarding", after)

    def lv_delete(self):
        rec = self._lv_selected()
        if not rec:
            return
        st = next((s for s in rec["stages"] if s["key"] == "delete"), None)
        due = st["due"] if st else ""
        if due and due > datetime.date.today().isoformat():
            if not self.confirm(f"{rec['email']} isn't due for deletion until {due}. "
                                "Delete now anyway?"):
                return
        if not self.confirm(f"Delete {rec['email']}?\n\nGoogle keeps a deleted account "
                            "restorable for about 20 days, then it's gone for good.",
                            "Delete account"):
            return
        spec = st["steps"] if st else [{"id": "del", "label": "Delete the account",
                                        "args": ["delete", "user", rec["email"]]}]
        self._lv_run_steps(rec, "delete" if st else "", spec, "Delete account")

    # =========================================================== graduation ===
    def _graduation(self):
        from ... import offboard
        o = offboard.grad_options()
        w = QWidget()
        lay = QVBoxLayout(w)
        tip = QLabel("Graduating seniors keep their account for a while so they can save their "
                     "files, then it's suspended and – after an admin approves – deleted. Each "
                     "student gets a record under Staff leaving → “People who have left”, so "
                     "everything except the email can be undone.")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        box, form = self.group("Who and when")
        self.gr_ou = OUField(self.directory, "/Students/High School/Grade 12")
        self.gr_ou.set_path(settings.get("graduation/ou", "") or "")
        self.gr_year = QSpinBox()
        self.gr_year.setRange(2000, 2100)
        self.gr_year.setValue(datetime.date.today().year if datetime.date.today().month < 9
                              else datetime.date.today().year + 1)
        self.gr_alumni = QLineEdit(o["alumni_ou"])
        self.gr_keep = QSpinBox()
        self.gr_keep.setRange(1, 3650)
        self.gr_keep.setValue(int(o["keep_days"]))
        self.gr_keep.setSuffix(" days")
        self.gr_del = QSpinBox()
        self.gr_del.setRange(1, 3650)
        self.gr_del.setValue(int(o["delete_days"]))
        self.gr_del.setSuffix(" days")
        self.gr_msg = QPlainTextEdit(o["message"])
        self.gr_msg.setFixedHeight(60)
        form.addRow("Seniors are in", self.gr_ou)
        form.addRow("Class of", self.gr_year)
        form.addRow("Move them to", self.gr_alumni)
        form.addRow("Keep the account open for", self.gr_keep)
        form.addRow("Offer to delete after", self.gr_del)
        form.addRow("Auto-reply ({close} = date)", self.gr_msg)
        lay.addWidget(box)
        box, form = self.group("Steps")
        self.gr_takeout = QCheckBox("Email each student how to download their files (Google "
                                    "Takeout)")
        self.gr_groups = QCheckBox("Remove them from groups")
        self.gr_gal = QCheckBox("Hide them from the directory")
        self.gr_lic = QCheckBox("Release their licenses when the account is suspended")
        for cb, k in ((self.gr_takeout, "takeout"), (self.gr_groups, "groups"),
                      (self.gr_gal, "gal"), (self.gr_lic, "licenses")):
            cb.setChecked(bool(o.get(k)))
            form.addRow("", cb)
        lay.addWidget(box)
        self.gr_info = QLabel("", objectName="Muted")
        lay.addLayout(self.row(button("Preview", slot=self.gr_preview),
                               button("Practice run", slot=self.gr_practice),
                               button("Start graduation", "primary", self.gr_run),
                               self.gr_info))
        self.gr_table = ResultsTable()
        self.gr_table.setMinimumHeight(200)
        lay.addWidget(self.gr_table)
        self.gr_steps = StepList(self)
        lay.addWidget(self.gr_steps)
        return w

    def _gr_opts(self) -> dict:
        opts = {"alumni_ou": self.gr_alumni.text().strip(), "keep_days": self.gr_keep.value(),
                "delete_days": self.gr_del.value(), "message": self.gr_msg.toPlainText(),
                "takeout": self.gr_takeout.isChecked(), "groups": self.gr_groups.isChecked(),
                "gal": self.gr_gal.isChecked(), "licenses": self.gr_lic.isChecked()}
        settings.set("graduation/options", json.dumps(opts))
        settings.set("graduation/ou", self.gr_ou.path())
        return opts

    def _gr_students(self) -> list[dict]:
        root = (self.gr_ou.path() or "").rstrip("/")
        if not root:
            return []
        return [u for u in self.directory.users if not u.get("suspended") and
                ((u.get("ou") or "") == root or (u.get("ou") or "").startswith(root + "/"))]

    def gr_preview(self):
        studs = self._gr_students()
        if not studs:
            self.info("Choose the seniors' org unit (the user list may need a refresh).")
            return
        opts = self._gr_opts()
        close = datetime.date.today() + datetime.timedelta(days=opts["keep_days"])
        self.gr_table.set_rows(["Student", "Name", "Now in", "Moves to"],
                               [[u["email"], u.get("name", ""), u.get("ou", ""),
                                 opts["alumni_ou"].replace("{year}", str(self.gr_year.value()))]
                                for u in studs])
        self.gr_info.setText(f"{len(studs):,} student(s) · accounts close {close:%B %d, %Y} · "
                             f"deletion offered after {opts['delete_days']} days")

    def gr_run(self):
        from ... import offboard
        from ...directory import run_gam_csv
        from ...gam_runner import dry_run_on
        studs = self._gr_students()
        if not studs:
            self.gr_preview()
            return
        opts = self._gr_opts()
        if not self.confirm(f"Start graduation for {len(studs):,} student(s)?"):
            return
        need_capture = opts["groups"] or opts["licenses"]
        recs, steps = [], []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for u in studs:
                before = (offboard.capture(u["email"], lambda a: run_gam_csv(a, 120))
                          if need_capture else {"groups": [], "licenses": [],
                                                "ou": u.get("ou", ""),
                                                "name": u.get("name", ""), "gal": True})
                rec = offboard.build_graduate(u["email"], before, opts, self.gr_year.value())
                recs.append(rec)
                for st in rec["stages"][0]["steps"]:
                    def done(code, _o, _e, rec=rec, sid=st["id"]):
                        rec.setdefault("_results", {})[sid] = code
                    steps.append(Step(f"{u['email']}: {st['label']}", st["args"],
                                      on_done=done))
        finally:
            QApplication.restoreOverrideCursor()
        dry = dry_run_on()

        def finished(_s):
            if not dry:
                for rec in recs:
                    res = rec.pop("_results", {})
                    offboard.save(rec)
                    offboard.mark(rec, "today", res)
                self._ensure_daily_task()
                self.lv_refresh()
            self.info(self.gr_steps.summary(), "Graduation")
        self.gr_steps.run(steps, finished)

    # ============================================================= rollover ===
    def _rollover(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        intro = QLabel("Do these in order at the end of the school year. Each part can be "
                       "run on its own.", objectName="Muted")
        lay.addWidget(intro)

        box = QGroupBox("1. Move students up a grade")
        bl = QVBoxLayout(box)
        bl.addWidget(QLabel("Each row moves everyone directly in the left org unit into the "
                            "right one. GAMbit runs the bottom row first so nobody gets "
                            "moved twice."))
        self.ro_table = QTableWidget(0, 3)
        self.ro_table.setHorizontalHeaderLabels(["Move students from", "To", "Students"])
        self.ro_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ro_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.ro_table.verticalHeader().setVisible(False)
        self.ro_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ro_table.setMinimumHeight(220)
        bl.addWidget(self.ro_table)
        bl.addLayout(self.row(
            button("Fill in from grade org units…", slot=self.ro_fill),
            button("Add row", slot=lambda: self.ro_add()),
            button("Remove row", slot=self.ro_remove),
            button("Count students", slot=self.ro_count)))
        self.ro_grad_suspend = QCheckBox("After moving, suspend everyone in the last row's "
                                         "\"To\" org unit (graduates)")
        bl.addWidget(self.ro_grad_suspend)
        bl.addLayout(self.row(button("Practice run", slot=self.ro_practice),
                              button("Move students", "primary", self.ro_run)))
        lay.addWidget(box)
        for f, t in json.loads(team.setting("workflow/rollover", "[]") or "[]"):
            self.ro_add(f, t)

        box = QGroupBox("2. Archive last year's Classroom courses")
        bl = QVBoxLayout(box)
        bl.addLayout(self.row(button("Load active courses", slot=self.ro_courses),
                              button("Select all", slot=lambda: self.ro_courses_tbl.table.selectAll()),
                              button("Archive selected", "primary", self.ro_archive)))
        self.ro_courses_tbl = ResultsTable()
        self.ro_courses_tbl.hidden_columns = {"id", "ownerid"}
        self.ro_courses_tbl.setMinimumHeight(200)
        bl.addWidget(self.ro_courses_tbl)
        lay.addWidget(box)

        box = QGroupBox("3. Ask students to choose new passwords")
        bl = QVBoxLayout(box)
        self.ro_pw_ous = OUMultiField(self.directory)
        bl.addWidget(self.ro_pw_ous)
        bl.addLayout(self.row(button("Require new password at next sign-in", slot=self.ro_pw)))
        lay.addWidget(box)

        self.ro_steps = StepList(self)
        lay.addWidget(self.ro_steps)
        return w

    def ro_add(self, src="", dst=""):
        r = self.ro_table.rowCount()
        self.ro_table.insertRow(r)
        a, b = OUField(self.directory, "From"), OUField(self.directory, "To")
        a.set_path(src)
        b.set_path(dst)
        self.ro_table.setCellWidget(r, 0, a)
        self.ro_table.setCellWidget(r, 1, b)
        self.ro_table.setCellWidget(r, 2, QLabel(""))
        self.ro_table.setRowHeight(r, 40)

    def ro_remove(self):
        rows = sorted({i.row() for i in self.ro_table.selectedIndexes()}, reverse=True) or \
            ([self.ro_table.rowCount() - 1] if self.ro_table.rowCount() else [])
        for r in rows:
            self.ro_table.removeRow(r)

    def _ro_pairs(self):
        out = []
        for r in range(self.ro_table.rowCount()):
            a = self.ro_table.cellWidget(r, 0).path()
            b = self.ro_table.cellWidget(r, 1).path()
            if a or b:
                out.append((a, b))
        return out

    def ro_fill(self):
        parent, ok = QInputDialog.getItem(self, "Grade org units",
                                          "Which org unit holds the grade-level org units?",
                                          sorted(self.directory.ous, key=_natural) or ["/"],
                                          0, True)
        if not ok:
            return
        kids = sorted([p for p in self.directory.ous
                       if p.rsplit("/", 1)[0] == parent.rstrip("/") and p != parent],
                      key=_natural)
        if len(kids) < 2:
            self.info("That org unit doesn't have at least two sub-units. Refresh the org "
                      "unit list in Settings if you just created them.")
            return
        self.ro_table.setRowCount(0)
        for a, b in zip(kids, kids[1:]):
            self.ro_add(a, b)
        self.ro_add(kids[-1], "")
        self.info("Check each row. The last row needs a \"To\" org unit for graduates "
                  "(for example /Students/Graduated), or remove it.")

    def ro_count(self):
        counts: dict[str, int] = {}
        for u in self.directory.users:
            counts[u.get("ou", "")] = counts.get(u.get("ou", ""), 0) + 1
        for r in range(self.ro_table.rowCount()):
            a = self.ro_table.cellWidget(r, 0).path()
            self.ro_table.cellWidget(r, 2).setText(f"  {counts.get(a, 0)}")
        self.info(f"Counts come from the saved user list (loaded "
                  f"{self.directory.age_text('users')}). Refresh lists in Settings for "
                  "up-to-the-minute numbers.")

    def ro_run(self):
        pairs = self._ro_pairs()
        if not pairs:
            self.info("Add at least one row.")
            return
        bad = [p for p in pairs if not (p[0] and p[1])]
        if bad:
            self.info("Every row needs both a From and a To org unit.")
            return
        team.set_setting("workflow/rollover", json.dumps(pairs))
        steps = [Step(f"{a}  →  {b}", ["update", "ou", b, "move", "ou", a])
                 for a, b in reversed(pairs)]
        if self.ro_grad_suspend.isChecked():
            grad = pairs[-1][1]
            steps.append(Step(f"Suspend everyone in {grad}",
                              ["ou", grad, "update", "user", "suspended", "on"]))
        plan = "\n".join(f"• {s.label}" for s in steps)
        if self.confirm(f"Run these moves (in this order)?\n\n{plan}", "Year-end rollover"):
            self.ro_steps.run(steps, lambda _s: (self.info(self.ro_steps.summary()),
                                                 self.directory.refresh_users()))

    def ro_practice(self):
        from .round10_pages import practice_run, rollover_commands
        pairs = [p for p in self._ro_pairs() if p[0] and p[1]]
        if not pairs:
            self.info("Add at least one row with both org units.")
            return
        practice_run(self, rollover_commands(pairs, self.ro_grad_suspend.isChecked()),
                     "move students up a grade")

    def gr_practice(self):
        from .round10_pages import graduation_commands, practice_run
        studs = self._gr_students()
        if not studs:
            self.info("Choose the seniors' org unit (the user list may need a refresh).")
            return
        practice_run(self, graduation_commands(studs, self._gr_opts(), self.gr_year.value()),
                     "graduation (every stage)")

    def ro_courses(self):
        self.run(["print", "courses", "states", "active", "owneremail", "fields",
                  "id,name,section,ownerid,creationtime"],
                 lambda c, out, _e: self.ro_courses_tbl.load_csv(out) if c == 0 else None,
                 quiet=True)

    def ro_archive(self):
        ids = self.ro_courses_tbl.selected_values("id")
        if not ids:
            self.info("Load the courses and select the ones to archive.")
            return
        if self.confirm(f"Archive {len(ids)} course(s)?\n\nTeachers and students can still "
                        "see archived courses but can't change them."):
            self.ro_steps.run([Step(f"Archive course {i}", ["update", "course", i,
                                                             "status", "archived"])
                               for i in ids],
                              lambda _s: (self.info(self.ro_steps.summary()), self.ro_courses()))

    def ro_pw(self):
        ous = self.ro_pw_ous.paths()
        if not ous:
            self.info("Choose the org units first.")
            return
        kw = "ou_and_children" if self.ro_pw_ous.include_children() else "ou"
        if self.confirm(f"Everyone in {', '.join(ous)} will have to choose a new password "
                        "the next time they sign in. Continue?"):
            self.ro_steps.run([Step(f"Require new password in {o}",
                                    [kw, o, "update", "user", "changepassword", "on"])
                               for o in ous], lambda _s: self.info(self.ro_steps.summary()))

    # ============================================================ checkout ===
    def _checkout(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        top = QHBoxLayout()

        box, form = self.group("Scan or type a serial number")
        self.co_out = QRadioButton("Check out to a student")
        self.co_in = QRadioButton("Check in")
        self.co_missing = QRadioButton("Mark missing")
        self.co_out.setChecked(True)
        form.addRow(self.row(self.co_out, self.co_in, self.co_missing))
        self.co_user = PersonField(self.directory, "Student / staff member")
        form.addRow("Assign to", self.co_user)
        self.co_loc = QLineEdit(placeholderText="e.g. Room 112, Cart 3, Tech office")
        form.addRow("Location", self.co_loc)
        self.co_ou = OUField(self.directory, "Leave blank to keep its org unit")
        form.addRow("Move to org unit", self.co_ou)
        self.co_disable = QCheckBox("Also disable missing devices (locks the screen)")
        form.addRow("", self.co_disable)
        self.co_sn = QLineEdit(placeholderText="Click here, then scan the barcode")
        self.co_sn.setStyleSheet("font-size:15pt; padding:8px;")
        self.co_sn.returnPressed.connect(self.co_apply)
        form.addRow("Serial number", self.co_sn)
        self.co_auto = QCheckBox("Apply as soon as a serial number is scanned "
                                 "(scanner sends Enter)")
        self.co_auto.setChecked(True)
        form.addRow("", self.co_auto)
        form.addRow("", self.row(button("Apply", "primary", lambda: self.co_apply(True)),
                                 button("Look up only", slot=self.co_lookup)))
        top.addWidget(box, 3)

        card = QFrame(objectName="Card")
        cv = QVBoxLayout(card)
        cv.addWidget(QLabel("<b>Device</b>"))
        self.co_card = QLabel("Scan a device to see it here.")
        self.co_card.setWordWrap(True)
        self.co_card.setTextFormat(Qt.RichText)
        self.co_card.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        cv.addWidget(self.co_card, 1)

        def mode():
            self.co_user.setEnabled(self.co_out.isChecked())
            self.co_disable.setEnabled(self.co_missing.isChecked())
        for r in (self.co_out, self.co_in, self.co_missing):
            r.toggled.connect(mode)
        mode()
        top.addWidget(card, 2)
        lay.addLayout(top)

        lay.addWidget(QLabel("<b>This session</b>"))
        self.co_log = ResultsTable()
        lay.addWidget(self.co_log, 1)
        self._co_rows: list[list[str]] = []
        return w

    def _co_sn(self):
        sn = re.sub(r"\s+", "", self.co_sn.text()).upper()
        if not sn:
            self.info("Scan or type a serial number.")
        return sn

    def co_lookup(self, then=None):
        sn = self._co_sn()
        if not sn:
            return
        import csv
        import io

        def done(code, out, _e):
            rows = list(csv.DictReader(io.StringIO(out or "")))
            if code != 0 or not rows:
                self.co_card.setText(f"<span style='color:#b42318'>No device found with "
                                     f"serial {html.escape(sn)}.</span>")
                if then:
                    then(None)
                return
            r = rows[0]

            def g(*parts):
                for k, v in r.items():
                    if all(p in (k or "").lower() for p in parts):
                        return v or ""
                return ""
            self.co_card.setText(
                f"<span style='font-size:13pt;font-weight:600'>{html.escape(sn)}</span><br>"
                f"{html.escape(g('model'))}<br>"
                f"Status: <b>{html.escape(g('status'))}</b><br>"
                f"Org unit: {html.escape(g('orgunitpath'))}<br>"
                f"Assigned to: {html.escape(g('annotateduser') or '—')}<br>"
                f"Location: {html.escape(g('annotatedlocation') or '—')}<br>"
                f"Last signed-in user: {html.escape(g('recentusers', 'email') or '—')}<br>"
                f"Notes: {html.escape(g('notes') or '—')}")
            if then:
                then(r)
        self.run(["cros_sn", sn, "print", "cros", "fields",
                  "serialnumber,model,status,orgunitpath,annotateduser,annotatedlocation,"
                  "notes,recentusers", "listlimit", "1"], done, quiet=True)

    def co_apply(self, force=False):
        if not (force or self.co_auto.isChecked()):
            self.co_lookup()
            return
        sn = self._co_sn()
        if not sn:
            return
        today = datetime.date.today().strftime("%Y-%m-%d")
        loc = self.co_loc.text().strip()
        ou = self.co_ou.path()
        if self.co_out.isChecked():
            who = self.co_user.email()
            if "@" not in who:
                self.info("Choose who the device is going to.")
                return
            action, detail = "Checked out", who
            args = ["cros_sn", sn, "update", "user", who,
                    "notes", f"Checked out to {who} on {today}"]
        elif self.co_in.isChecked():
            action, detail = "Checked in", loc or ""
            args = ["cros_sn", sn, "update", "user", "", "notes", f"Checked in on {today}"]
        else:
            action, detail = "Missing", ""
            args = ["cros_sn", sn, "update", "notes", f"MISSING since {today}"]
        if loc:
            args += ["location", loc]
        if ou:
            args += ["ou", ou]
        cmds = [args]
        if self.co_missing.isChecked() and self.co_disable.isChecked():
            cmds.append(["cros_sn", sn, "update", "action", "disable"])

        def logged(codes, _outs):
            ok = bool(codes) and all(c == 0 for c in codes)
            self._co_rows.insert(0, [datetime.datetime.now().strftime("%H:%M:%S"), sn,
                                     action, detail, ou or "", "✔" if ok else "check output"])
            self.co_log.set_rows(["Time", "Serial", "Action", "Who / where", "Org unit",
                                  "Result"], self._co_rows)
            self.co_lookup()
            self.co_sn.clear()
            self.co_sn.setFocus()
        self.run_many(cmds, logged, quiet=False, with_codes=True)
