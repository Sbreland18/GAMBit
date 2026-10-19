"""Approvals: limited roles ask for risky changes; a Full admin approves and runs them."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QPlainTextEdit, QTableWidget, QTableWidgetItem,
)

from ... import team
from ...gam_runner import display_command
from ..widgets import Page, Worker, button

STATUS = {"pending": "⏳ Waiting", "approved": "✔ Approved", "done": "✔ Done",
          "failed": "✖ Failed", "denied": "✖ Denied", "cancelled": "■ Cancelled"}


class ApprovalsPage(Page):
    title = "Approvals"
    subtitle = ("Changes someone has asked an admin to approve – suspensions, deletes and "
                "other actions their role can only request.")

    def build(self):
        bar = QHBoxLayout()
        self.who = QLabel("")
        bar.addWidget(self.who, 1)
        self.show_what = QComboBox()
        for label, val in (("Waiting for approval", "pending"), ("Everything", "")):
            self.show_what.addItem(label, val)
        self.show_what.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.show_what)
        bar.addWidget(button("Refresh", slot=self.refresh))
        bar.addWidget(button("Check email replies", slot=self.check_email))
        bar.addWidget(button("Email approvals…", slot=self.email_setup))
        bar.addWidget(button("Approval rules…", slot=self.rules_setup))
        self.body.addLayout(bar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Asked", "By", "What", "Why", "Status",
                                              "Decided by"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for c, w in ((0, 140), (1, 100), (3, 220), (4, 110), (5, 110)):
            self.table.setColumnWidth(c, w)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self.body.addWidget(self.table, 1)

        self.detail = QPlainTextEdit(readOnly=True)
        self.detail.setMaximumHeight(130)
        self.detail.setStyleSheet("font-family:Consolas,'Cascadia Mono',monospace;")
        self.body.addWidget(self.detail)

        acts = QHBoxLayout()
        self.approve_btn = button("Approve and run", "primary", self.approve)
        self.deny_btn = button("Deny…", "danger", self.deny)
        self.deny_btn.setProperty("helpdesk_ok", True)
        acts.addWidget(self.approve_btn)
        self.later_btn = button("Approve, run later…", slot=self.approve_later)
        acts.addWidget(self.later_btn)
        acts.addWidget(self.deny_btn)
        acts.addWidget(button("Cancel my request", slot=self.cancel_mine))
        acts.addWidget(button("Practice run", slot=self.practice))
        acts.addStretch(1)
        self.body.addLayout(acts)
        self.reqs: list[dict] = []
        self._form_box()

    def on_show(self):
        self.refresh()

    # ------------------------------------------------- staff request form ---
    def _form_box(self):
        from PySide6.QtWidgets import QCheckBox, QLineEdit
        from ... import selfservice
        from ...settings import settings
        from ..pickers import OUField
        o = selfservice.opts()
        box, form = self.group("Staff request form (Google Form → Sheet)")
        self.form_box = box
        help_ = QLabel(
            "Teachers ask for a student's password reset or sign-out with a Google Form. "
            "GAMbit checks each new response – the teacher must be active staff, the account "
            "a student, and (optionally) the teacher must teach them in Classroom – then it "
            "appears here for approval, or runs straight away if you allow it. The teacher "
            "gets the new password by email.<br><span style='color:#57606a'>Form questions: "
            "<i>Student's school email</i> · <i>What do you need?</i> (Reset password / Sign "
            "out of all devices / Something else) · <i>Details</i>. Turn on <i>Collect email "
            "addresses</i>, then link the responses to a Sheet.</span>")
        help_.setWordWrap(True)
        form.addRow(help_)
        self.f_url = QLineEdit(o["sheet_url"])
        self.f_url.setPlaceholderText("Response sheet link")
        self.f_tab = QLineEdit(o["tab"])
        self.f_tab.setPlaceholderText("Form Responses 1")
        form.addRow("Responses sheet", self.row(self.f_url, self.f_tab, stretch=False))
        self.f_staff = OUField(self.directory, "/Staff")
        self.f_staff.set_path(o["staff_root"])
        self.f_students = OUField(self.directory, "/Students")
        self.f_students.set_path(o["student_root"])
        form.addRow("Teachers are under", self.f_staff)
        form.addRow("Students are under", self.f_students)
        self.f_teacher = QCheckBox("Teacher must share an active Classroom class with the "
                                   "student")
        self.f_teacher.setChecked(o["require_teacher"])
        self.f_auto = QCheckBox("Run password resets straight away (no approval needed)")
        self.f_auto.setChecked(o["auto_reset"])
        form.addRow("", self.f_teacher)
        form.addRow("", self.f_auto)
        self.f_status = QLabel("", objectName="Muted")
        last = settings.get("selfservice/last_check", "")
        if last:
            self.f_status.setText(f"Last checked {last.replace('T', ' ')}")
        form.addRow("", self.row(button("Save", slot=self._form_save),
                                 button("Check for new requests now", slot=self._form_check),
                                 button("Check every 15 minutes…", slot=self._form_schedule),
                                 self.f_status))
        self.body.addWidget(box)

    def _form_save(self):
        from ...settings import settings
        settings.set("selfservice/sheet_url", self.f_url.text().strip())
        settings.set("selfservice/tab", self.f_tab.text().strip())
        settings.set("selfservice/staff_root", self.f_staff.path() or "/Staff")
        settings.set("selfservice/student_root", self.f_students.path() or "/Students")
        settings.set("selfservice/require_teacher", self.f_teacher.isChecked())
        settings.set("selfservice/auto_reset", self.f_auto.isChecked())

    def _form_check(self):
        from ... import selfservice
        from ..widgets import Worker
        self._form_save()
        if not self.f_url.text().strip():
            self.info("Paste the form's response sheet link first.")
            return
        self.f_status.setText("Checking…")
        Worker(selfservice.process,
               on_done=lambda n: (self.f_status.setText(f"{n} new request(s)."),
                                  self.refresh()),
               on_error=lambda e: (self.f_status.setText(""), self.info(str(e))))

    def _form_schedule(self):
        from ... import scheduler
        self._form_save()
        try:
            script = scheduler.build_app_task_script("GAMbit staff requests",
                                                     ["--task", "requests"])
            scheduler.create_task("GAMbit staff requests", script, "every15", "07:00")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Couldn't create the scheduled task:\n{exc}")
            return
        self.info("GAMbit will check the form every 15 minutes (starting 7:00 AM), even when "
                  "the app is closed.")

    def refresh(self):
        admin = team.is_admin()
        if not team.folder():
            self.who.setText("Approvals need a team folder – set one in Settings & Updates → "
                             "Team.")
        else:
            n = team.pending_count()
            self.who.setText(f"You are <b>{team.me()}</b> ({team.my_role_name()}). " +
                             (f"{n} request(s) waiting." if admin else
                              "An admin approves your requests here."))
        self.approve_btn.setVisible(admin)
        self.later_btn.setVisible(admin)
        self.deny_btn.setVisible(admin)
        if hasattr(self, "form_box"):
            self.form_box.setVisible(admin)
        self.reqs = team.list_requests(self.show_what.currentData())
        if not admin:
            self.reqs = [r for r in self.reqs if r.get("by") == team.me()]
        self.table.setRowCount(0)
        from ... import approval_policy as policy
        pol = policy.load()
        for r in self.reqs:
            row = self.table.rowCount()
            self.table.insertRow(row)
            vals = [r.get("time", "").replace("T", " "), r.get("by", ""),
                    r.get("title", "") + (f"  (+{len(r['commands']) - 1} more)"
                                          if len(r.get("commands", [])) > 1 else ""),
                    r.get("reason", ""), (STATUS.get(r.get("status"), r.get("status", "")) +
                     (f" – {policy.approval_note(r, pol)}" if r.get("status") == "pending"
                      and policy.approval_note(r, pol) else "") +
                     (" (automatic)" if r.get("auto") else "") +
                     (f" – approved by email ({r['remote_approved_by']})"
                      if r.get("remote_approved_by") and r.get("status") == "pending"
                      else "")),
                    r.get("decided_by", "")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setToolTip(v)
                if c == 0:
                    it.setData(Qt.UserRole, r)
                self.table.setItem(row, c, it)
        self._show_detail()
        if hasattr(self.app, "update_approvals_badge"):
            self.app.update_approvals_badge()

    def _selected(self) -> list[dict]:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).data(Qt.UserRole) for r in rows]

    def _show_detail(self):
        sel = self._selected()
        if not sel:
            self.detail.setPlainText("")
            return
        r = sel[0]
        lines = [f"Requested by {r.get('by')} on {r.get('time', '').replace('T', ' ')} "
                 f"(domain: {r.get('profile', '')})", f"Why: {r.get('reason', '')}", ""]
        lines += [display_command(c) for c in r.get("commands", [])]
        if r.get("note"):
            lines += ["", f"Admin note: {r['note']}"]
        if r.get("result"):
            lines += ["", f"Result: {r['result']}"]
        self.detail.setPlainText("\n".join(lines))

    def check_email(self):
        from ... import email_approvals
        if not email_approvals.enabled():
            self.email_setup()
            return
        Worker(email_approvals.process,
               on_done=lambda lines: (self.refresh(),
                                      self.info("\n".join(lines) or "No new replies.")),
               on_error=lambda e: self.info(f"Couldn't read replies:\n{e}"))

    def email_setup(self):
        from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit
        from ...settings import settings
        dlg = QDialog(self)
        dlg.setWindowTitle("Approve by email")
        f = QFormLayout(dlg)
        on = QCheckBox("Email each new request to the approvers; they reply APPROVE or DENY")
        on.setChecked(bool(settings.get("approvals/email_on", False)))
        who = QLineEdit(settings.get("approvals/emails", "") or "")
        who.setPlaceholderText("director@…, coordinator@…")
        f.addRow(on)
        f.addRow("Approvers", who)
        from ...google_io import admin_email
        f.addRow("", QLabel(f"Requests are sent from {admin_email() or 'the Google account in '}"
                            f"{'' if admin_email() else 'Settings'} and replies are read from that "
                            "mailbox by the “staff requests” background task (every 15 minutes) "
                            "or with “Check email replies”. Only replies from these addresses "
                            "count.", objectName="Muted", wordWrap=True))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        if dlg.exec():
            settings.set("approvals/email_on", on.isChecked())
            settings.set("approvals/emails", who.text().strip())

    def practice(self):
        from .round10_pages import practice_run
        sel = self._selected()
        cmds = [c for r in sel for c in r.get("commands", [])]
        if not cmds:
            self.info("Select a request that has commands.")
            return
        practice_run(self, cmds, sel[0].get("title", "request"))

    def rules_setup(self):
        from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
                                       QLineEdit, QSpinBox)
        from ... import approval_policy as policy
        from ..pickers import OUField
        p = policy.load()
        dlg = QDialog(self)
        dlg.setWindowTitle("Approval rules")
        f = QFormLayout(dlg)
        on = QCheckBox("Use these approval rules")
        on.setChecked(bool(p.get("on")))
        f.addRow(on)
        auto = {r["category"]: r for r in p.get("auto", [])}
        f.addRow(QLabel("<b>Approve automatically</b> (requests from limited roles run "
                        "straight away and are logged here)"))
        auto_boxes = {}
        for cat in ("passwords", "groups", "chromebooks", "users", "email", "classroom"):
            cb = QCheckBox(team.CATEGORIES[cat])
            cb.setChecked(cat in auto)
            auto_boxes[cat] = cb
            f.addRow("", cb)
        students_only = QCheckBox("…only when every account it changes is a student")
        students_only.setChecked(any(r.get("students_only") for r in auto.values()) or
                                 not auto)
        f.addRow("", students_only)
        root = OUField(self.directory, "/Students")
        root.set_path(p.get("student_root", "/Students"))
        f.addRow("Students are under", root)
        f.addRow(QLabel("<b>Need two different approvers</b>"))
        two_boxes = {}
        for cat in ("delete", "suspend", "everyone", "drive", "other"):
            cb = QCheckBox(team.CATEGORIES[cat])
            cb.setChecked(cat in p.get("two_person", []))
            two_boxes[cat] = cb
            f.addRow("", cb)
        hours = QSpinBox()
        hours.setRange(0, 720)
        hours.setSuffix(" hours (0 = never)")
        hours.setValue(int(p.get("escalate_hours", 24) or 0))
        esc = QLineEdit(p.get("escalate_to", ""))
        esc.setPlaceholderText("director@… (also posts to your alert channels)")
        f.addRow("Escalate after", hours)
        f.addRow("Escalate to", esc)
        f.addRow("", QLabel("Escalation is checked by the “staff requests” background task "
                            "every 15 minutes.", objectName="Muted", wordWrap=True))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        if dlg.exec():
            policy.save({"on": on.isChecked(), "student_root": root.path() or "/Students",
                         "auto": [{"category": c, "students_only": students_only.isChecked()}
                                  for c, cb in auto_boxes.items() if cb.isChecked()],
                         "two_person": [c for c, cb in two_boxes.items() if cb.isChecked()],
                         "escalate_hours": hours.value(), "escalate_to": esc.text().strip()})
            self.refresh()

    def approve(self):
        sel = [r for r in self._selected() if r.get("status") == "pending"]
        if not sel:
            self.info("Select a request that's waiting for approval.")
            return
        cmds = [c for r in sel for c in r["commands"]]
        special = [r for r in sel if r.get("kind") in ("offboard", "selfservice")]
        listing = "\n".join(display_command(c) for c in cmds[:20])
        for r in special:
            listing += "\n" + self._special_summary(r)
        if not self.confirm(f"Approve {len(sel)} request(s)?\n\n{listing}"):
            return
        from ... import approval_policy
        ready_sel, waiting = [], []
        for r in sel:
            ready, r2 = approval_policy.record_approval(r, team.me())
            (ready_sel if ready else waiting).append(r2)
        if waiting:
            self.info("These need a second person to approve before they run:\n\n" +
                      "\n".join(f"• {r.get('title', '')} – "
                                f"{approval_policy.approval_note(r) or 'you asked for it'}"
                                for r in waiting))
        sel = ready_sel
        special = [r for r in sel if r.get("kind") in ("offboard", "selfservice")]
        for r in special:
            self._approve_special(r)
        sel = [r for r in sel if r not in special]
        for r in [r for r in sel if r.get("kind") == "ticket_reset"]:
            self._approve_ticket(r)
        sel = [r for r in sel if r.get("kind") != "ticket_reset"]
        for r in [r for r in sel if not r.get("commands")]:
            team.update_request(r, "done", result="signed off")
        sel = [r for r in sel if r.get("commands")]
        for r in sel:
            r = team.update_request(r, "approved")
            results = []

            def done(code, _o, err, r=r, results=results, total=len(r["commands"])):
                results.append(code)
                if len(results) == total:
                    ok = all(c == 0 for c in results)
                    team.update_request(r, "done" if ok else "failed",
                                        result="all commands worked" if ok else
                                        f"{sum(c != 0 for c in results)} command(s) failed: "
                                        f"{(err or '').strip()[-200:]}")
                    if ok and r.get("kind") == "offboard-delete":
                        from ... import offboard
                        rec = offboard.get(r.get("email", ""))
                        if rec:
                            st = next((x for x in rec["stages"] if x["key"] == "delete"), None)
                            if st:
                                offboard.mark(rec, "delete", {s["id"]: 0 for s in st["steps"]})
                    self.refresh()
            for c in r["commands"]:
                self.app._approved_request = r["id"]
                if not self.runner.run(c, on_done=done):
                    done(1, "", "Not started")
                self.app._approved_request = ""
        self.refresh()

    def approve_later(self):
        """Approve now; the 15-minute background task runs it at the chosen time."""
        from ... import approval_policy, change_queue
        from .round12_pages import ask_when
        sel = [r for r in self._selected() if r.get("status") == "pending" and r.get("commands")
               and r.get("kind") not in ("offboard", "selfservice", "ticket_reset")]
        if not sel:
            self.info("Select a request that's waiting for approval (offboarding, self-service "
                      "and password tickets can only run now).")
            return
        when = ask_when(self)
        if not when:
            return
        queued, waiting = 0, []
        for r in sel:
            ready, r2 = approval_policy.record_approval(r, team.me())
            if not ready:
                waiting.append(r2)
                continue
            r2 = team.update_request(r2, "approved", result=f"runs {when.replace('T', ' ')}")
            change_queue.add(r2["commands"], when, r2.get("title", ""), team.me(), r2["id"])
            queued += 1
        msg = f"{queued} request(s) will run at {when.replace('T', ' ')}."
        if waiting:
            msg += f"\n{len(waiting)} still need a second approver."
        self.info(msg + "\n\nThe background “staff requests” task (every 15 minutes) runs them "
                  "– see Run later & freezes.")
        self.refresh()

    def _approve_ticket(self, r):
        from ...tools import ticket_auto
        r = team.update_request(r, "approved")

        def done(res):
            ok, msg = res
            team.update_request(r, "done" if ok else "failed", result=msg)
            self.refresh()
        Worker(ticket_auto.run_request, r, on_done=done,
               on_error=lambda e: (team.update_request(r, "failed", result=str(e)),
                                   self.refresh()))

    # ---------------------------------------------------- special requests ---
    def _special_summary(self, r) -> str:
        if r.get("kind") == "offboard":
            return "\n".join(f"• Full offboarding: {p['email']} (supervisor "
                             f"{p.get('supervisor') or 'none'})" for p in r.get("people", []))
        if r.get("kind") == "selfservice":
            from ... import selfservice
            return "• " + selfservice.describe(r)
        return ""

    def _approve_special(self, r):
        from ...gam_runner import dry_run_on
        if dry_run_on() and r.get("kind") == "offboard":
            self.info("Dry run is on, so the offboarding wasn't started (the request stays "
                      "waiting). Turn dry run off to approve it.")
            return
        r = team.update_request(r, "approved")
        if r.get("kind") == "offboard":
            from ... import offboard
            from ...directory import run_gam_csv
            from ..steps import Step, StepList
            from .users import random_password
            recs, steps = [], []
            for p in r.get("people", []):
                before = offboard.capture(p["email"], lambda a: run_gam_csv(a, 120))
                rec = offboard.build(p["email"], p.get("supervisor", ""), before,
                                     offboard.options(), random_password)
                recs.append(rec)
                for st in rec["stages"][0]["steps"]:
                    def done(code, _o, _e, rec=rec, sid=st["id"]):
                        rec.setdefault("_results", {})[sid] = code
                    steps.append(Step(f"{p['email']}: {st['label']}", st["args"],
                                      on_done=done))
            if not hasattr(self, "_steps"):
                self._steps = StepList(self)
                self._steps.setMaximumHeight(150)
                self.body.insertWidget(self.body.count() - 1, self._steps)

            def finished(_s):
                bad = 0
                for rec in recs:
                    res = rec.pop("_results", {})
                    bad += sum(1 for c in res.values() if c)
                    offboard.save(rec)
                    offboard.mark(rec, "today", res)
                team.update_request(r, "done" if not bad else "failed",
                                    result=f"offboarding started for {len(recs)} "
                                           f"person(s)" + (f"; {bad} step(s) failed"
                                                           if bad else ""))
                self.refresh()
            self.app._approved_request = r["id"]
            try:
                self._steps.run(steps, finished)
            finally:
                self.app._approved_request = ""
        elif r.get("kind") == "selfservice":
            from ... import selfservice
            selfservice.approve(self, r)

    def deny(self):
        sel = [r for r in self._selected() if r.get("status") == "pending"]
        if not sel:
            return
        note, ok = QInputDialog.getText(self, "Deny", "Note for the person who asked "
                                        "(optional):")
        if not ok:
            return
        for r in sel:
            team.update_request(r, "denied", note=note.strip())
            if r.get("kind") == "selfservice":
                from ... import selfservice
                selfservice.denied(r, note.strip())
        self.refresh()

    def cancel_mine(self):
        sel = [r for r in self._selected() if r.get("status") == "pending"
               and r.get("by") == team.me()]
        if not sel:
            self.info("Select one of your own requests that's still waiting.")
            return
        for r in sel:
            team.update_request(r, "cancelled")
        self.refresh()
