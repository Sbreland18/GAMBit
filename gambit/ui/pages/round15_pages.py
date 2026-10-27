"""Round 15 pages: Staff card, Back-to-school readiness, Changes made outside GAMbit,
Account recovery coverage and the Mailbox & calendar access review."""

from __future__ import annotations

import datetime

from PySide6.QtWidgets import (
    QCheckBox, QInputDialog, QLabel, QLineEdit, QPlainTextEdit, QSpinBox, QTabWidget,
)

from ... import team
from ..pickers import OUField, PersonField
from ..widgets import Page, ResultsTable, Worker, button
from .round11_pages import run_or_request
from .round13_pages import _steps
from .round13_tabs import _csv, fill


# ================================================================== staff card ===
class StaffCardPage(Page):
    title = "Staff card"
    subtitle = ("One staff member's security and resources on one screen: 2-Step "
                "Verification, admin roles, storage, outside sharing, devices, licenses, app "
                "passwords, who can read their mail, forwarding and connected apps.")

    def build(self):
        self.who = PersonField(self.directory, "Staff member")
        self.who.returnPressed.connect(self.load)
        self.sharing = QCheckBox("Include file sharing counts (slower)")
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(self.who, button("Show card", "primary", self.load),
                                     self.sharing, stretch=False))
        self.body.addWidget(self.status)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.body.addLayout(self.row(
            button("Timeline", slot=lambda: self.app.open_timeline(self.who.email())),
            button("Open in Users", slot=lambda: self.app.open_user(self.who.email())),
            button("✅ Check everything", slot=self._check),
            button("🖨 Print card", slot=self._card)))

    def _check(self):
        e = self.who.email()
        if "@" not in e:
            self.info("Choose the person first.")
            return
        from ..person_check_dialog import PersonCheckDialog
        PersonCheckDialog(self, e).exec()

    def _card(self):
        e = self.who.email()
        if "@" not in e:
            self.info("Choose the person first.")
            return
        from ..print_card import PrintCardDialog
        u = next((x for x in self.directory.users if x["email"].lower() == e.lower()), {})
        PrintCardDialog(self, e, u.get("name", "")).exec()

    def load(self):
        from ... import staff_card as sc
        e = self.who.email()
        if "@" not in e:
            self.info("Choose a staff member.")
            return
        self.status.setText("Gathering (about a minute)…")

        def done(rows):
            fill(self.table, rows, ["Level", "Area", "Detail"])
            n = sum(1 for r in rows if r["Level"] in ("high", "medium"))
            self.status.setText(f"{e}: {n} thing(s) to look at" if n else
                                f"{e}: nothing to fix.")
        Worker(sc.gather, e, _csv(), self.sharing.isChecked(), on_done=done,
               on_error=lambda x: self.status.setText(str(x)))


# =============================================================== back to school ===
class BackToSchoolPage(Page):
    title = "Back to school"
    subtitle = ("August readiness by school: students signed in, Chromebooks assigned, "
                "guardians invited, Classroom teachers verified and this year's classes "
                "created – with a button to the screen that fixes each one.")

    def build(self):
        from ... import back_to_school as bts
        o = bts.options()
        self.sroot = OUField(self.directory, "/Students")
        self.sroot.set_path(o["student_root"])
        self.troot = OUField(self.directory, "/Staff")
        self.troot.set_path(o["staff_root"])
        self.goal = QSpinBox()
        self.goal.setRange(50, 100)
        self.goal.setValue(int(o["goal"]))
        self.goal.setSuffix("% goal")
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(QLabel("Students"), self.sroot, QLabel("Staff"),
                                     self.troot, self.goal,
                                     button("Check readiness", "primary", self.load)))
        self.body.addWidget(self.status)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        from .insight_pages import goto
        fixes = []
        for col, (page, tab) in bts.FIXES.items():
            fixes.append(button(f"Fix: {col.lower()}",
                                slot=lambda _=False, p=page, t=tab: goto(self.app, p, t)))
        self.body.addLayout(self.row(*fixes))

    def load(self):
        from ... import back_to_school as bts
        from ... import fleet, guardians
        from ...directory import run_gam_text
        from ...tools import gam_extras2 as g2
        users = self.directory.users
        if not users:
            self.info("Load users first (Users page or Refresh).")
            return
        o = {**bts.options(), "student_root": self.sroot.path() or "/Students",
             "staff_root": self.troot.path() or "/Staff", "goal": self.goal.value()}
        bts.save_options(o)
        today = datetime.date.today()
        ye = today.year + 1 if today.month >= 7 else today.year
        self.status.setText("Reading Chromebooks, guardians, teacher profiles and classes "
                            "(several minutes for big districts)…")

        def work():
            run = _csv()
            probs = []
            c, rows, _e = run(["print", "cros", "fields", "serialnumber,annotateduser,status"])
            devs = fleet.devices(rows) if c == 0 else None
            c2, out = run_gam_text(["ou_and_children", o["student_root"], "print", "guardians",
                                    "all", "showstudentemails"], 3600)
            gu = guardians.parse_current(out) if c2 == 0 else None
            c3, prof, _e = run(g2.classroom_profile_args(["ou_and_children", o["staff_root"]]))
            c4, courses, _e = run(bts.courses_args())
            for ok, what in ((devs is not None, "Chromebooks"), (gu is not None, "guardians"),
                             (c3 == 0, "teacher profiles"), (c4 == 0, "classes")):
                if not ok:
                    probs.append(f"couldn't read {what}")
            return bts.compute(users, devs, gu, prof if c3 == 0 else None,
                               courses if c4 == 0 else None, o, ye), probs

        def done(res):
            rows, probs = res
            fill(self.table, bts.display(rows), ["School", "Students", "Signed in",
                                                 "Chromebook assigned", "Guardian invited",
                                                 "Teachers verified", "Classes created",
                                                 "Needs work"])
            ready = sum(1 for r in rows if not r["Needs work"])
            self.status.setText(f"{ready} of {len(rows)} school(s) ready" +
                                (" · " + "; ".join(probs) if probs else ""))
        Worker(work, on_done=done, on_error=lambda e: self.status.setText(str(e)))


# ============================================================ outside changes ===
class OutsideChangesPage(Page):
    title = "Changes outside GAMbit"
    subtitle = ("Admin changes in Google's admin log that weren't made through GAMbit – "
                "Admin console clicks, other scripts or tools, or someone who shouldn't be "
                "making changes – with who made them.")

    def build(self):
        from ... import outside_changes as oc
        o = oc.options()
        self.days = QSpinBox()
        self.days.setRange(1, 180)
        self.days.setValue(int(o["days"]))
        self.days.setSuffix(" days")
        self.actors = QLineEdit(o["ignore_actors"])
        self.actors.setPlaceholderText("ignore these accounts (e.g. your SIS sync account)")
        self.events = QLineEdit(o["ignore_events"])
        self.events.setPlaceholderText("ignore these events, e.g. CHANGE_PASSWORD")
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(QLabel("Last"), self.days, self.actors, self.events,
                                     button("Compare", "primary", self.load)))
        self.body.addWidget(self.status)
        self.tabs = QTabWidget()
        self.table, self.who = ResultsTable(), ResultsTable()
        self.tabs.addTab(self.table, "Changes")
        self.tabs.addTab(self.who, "By person")
        self.body.addWidget(self.tabs, 1)
        self.body.addWidget(QLabel("GAMbit matches a change when its own activity log (on this "
                                   "computer, plus the team folder) has the same account, group "
                                   "or device within 15 minutes.", objectName="Muted",
                                   wordWrap=True))

    def load(self):
        from ... import activity
        from ... import outside_changes as oc
        o = {**oc.options(), "days": self.days.value(), "ignore_actors": self.actors.text(),
             "ignore_events": self.events.text()}
        oc.save_options(o)
        self.status.setText("Reading the admin log…")

        def work():
            c, rows, e = _csv()(oc.admin_args(o["days"]))
            if c != 0:
                raise RuntimeError((e or "")[-200:])
            return rows, oc.compare(rows, activity.load(o["days"] + 1, team=True), o)

        def done(res):
            rows, out = res
            fill(self.table, out, ["When", "Who", "What", "Target", "Details"])
            fill(self.who, oc.summary(out), ["Who", "Changes", "What"])
            self.status.setText(f"{len(rows):,} admin-log event(s) · {len(out):,} not made "
                                f"through GAMbit")
        Worker(work, on_done=done, on_error=lambda e: self.status.setText(str(e)))


# ============================================================ account recovery ===
class RecoveryCoveragePage(Page):
    title = "Account recovery"
    subtitle = ("Staff with no recovery phone or email can't reset a forgotten password "
                "themselves. See coverage by building and email the people missing it.")

    def build(self):
        from ... import recovery_coverage as rc
        o = rc.options()
        self.root = OUField(self.directory, "/Staff")
        self.root.set_path(o["root"])
        self.subject = QLineEdit(o["subject"])
        self.msg = QPlainTextEdit(o["message"])
        self.msg.setMaximumHeight(120)
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(QLabel("People in"), self.root,
                                     button("Check", "primary", self.load), self.status))
        self.tabs = QTabWidget()
        self.cov, self.miss = ResultsTable(), ResultsTable()
        self.tabs.addTab(self.cov, "By building")
        self.tabs.addTab(self.miss, "Missing")
        self.body.addWidget(self.tabs, 1)
        box, form = self.group("Reminder email")
        form.addRow("Subject", self.subject)
        form.addRow("Message", self.msg)
        form.addRow("", self.row(button("Email everyone missing it", "primary", self.remind),
                                 button("Email selected", slot=lambda: self.remind(True))))
        self.body.addWidget(box)
        self.missing = []

    def _opts(self):
        from ... import recovery_coverage as rc
        o = {**rc.options(), "root": self.root.path() or "/Staff",
             "subject": self.subject.text().strip(), "message": self.msg.toPlainText()}
        rc.save_options(o)
        return o

    def load(self):
        from ... import recovery_coverage as rc
        o = self._opts()

        def done(res):
            c, rows, e = res
            if c != 0:
                self.status.setText((e or "")[-200:])
                return
            ppl = rc.people(rows, o)
            cov = rc.coverage(ppl)
            self.missing = rc.missing(ppl)
            fill(self.cov, cov, ["Building", "People", "Covered", "Missing", "%", "Phone",
                                 "Email"])
            fill(self.miss, self.missing, ["Person", "Name", "Building"])
            if cov:
                self.status.setText(f"{cov[-1]['%']}% covered · {cov[-1]['Missing']:,} "
                                    f"missing")
        self.status.setText("Reading accounts…")
        Worker(lambda: _csv()(rc.USERS_ARGS), on_done=done,
               on_error=lambda e: self.status.setText(str(e)))

    def remind(self, selected=False):
        from ... import google_io
        from ... import recovery_coverage as rc
        o = self._opts()
        emails = (self.miss.selected_values("Person") if selected else
                  [m["Person"] for m in self.missing])
        if not emails:
            self.info("Check first (and select people for “Email selected”).")
            return
        cmds = rc.reminder_commands(emails, o, google_io.admin_email())
        run_or_request(self, _steps(self), [(f"Email {len(c[4].split(','))} people", c)
                                            for c in cmds],
                       "Account recovery reminder", "Recovery phone/email campaign")


# ===================================================== mailbox & calendar access ===
class MailboxAccessPage(Page):
    title = "Mailbox access review"
    subtitle = ("Who can read someone else's mail (delegates), send as them, or change their "
                "calendar. Flags access held by leavers, outsiders and people at another "
                "school. Mark Keep or Remove and sign off each quarter.")

    def build(self):
        from ... import delegation_review as dr
        o = dr.options()
        self.root = OUField(self.directory, "/Staff")
        self.root.set_path(o["root"])
        self.former = QLineEdit(o["former_root"])
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(QLabel("Mailboxes in"), self.root,
                                     QLabel("Leavers' org unit"), self.former,
                                     button("Load", "primary", self.load)))
        self.body.addWidget(self.status)
        self.table = ResultsTable()
        self.table.hidden_columns = {"key"}
        self.body.addWidget(self.table, 1)
        self.body.addLayout(self.row(
            button("Mark selected Keep", slot=lambda: self.mark("Keep")),
            button("Mark selected Remove", "danger", lambda: self.mark("Remove")),
            button("Sign off the review…", "primary", self.sign),
            button("Past reviews", slot=self.past)))
        self.rows, self.decisions = [], {}
        h = dr.history()
        self.status.setText(("Last review: " + h[-1]["date"] + " by " + h[-1]["by"]) if h
                            else "No review signed off yet.")

    def load(self):
        from ... import delegation_review as dr
        o = {**dr.options(), "root": self.root.path() or "/Staff",
             "former_root": self.former.text().strip()}
        dr.save_options(o)
        users = self.directory.users
        self.status.setText("Reading delegates, send-as addresses and calendar sharing for "
                            "every mailbox (several minutes)…")

        def work():
            data, probs = {}, []
            for k, a in dr.commands(o).items():
                c, rows, _e = _csv()(a)
                data[k] = rows if c == 0 else None
                if c != 0:
                    probs.append(f"couldn't read {k}")
            return dr.review(dr.entries(data), users, o), probs

        def done(res):
            self.rows, probs = res
            new = dr.new_since_last(self.rows)
            self.decisions = {}
            for r in self.rows:
                r["key"] = dr._key(r)
                r["New"] = "new" if r["key"] in new else ""
                self.decisions[r["key"]] = "Remove" if "left" in r["Flags"] or \
                    "suspended" in r["Flags"] or "outsider" in r["Flags"] else "Keep"
            self._show()
            self.status.setText(f"{len(self.rows):,} access entr(ies) · "
                                f"{sum(1 for r in self.rows if r['Flags'])} flagged · "
                                f"{len(new)} new since the last review" +
                                (" · " + "; ".join(probs) if probs else ""))
        Worker(work, on_done=done, on_error=lambda e: self.status.setText(str(e)))

    def _show(self):
        for r in self.rows:
            r["Decision"] = self.decisions.get(r["key"], "Keep")
        fill(self.table, self.rows, ["Decision", "Owner", "Who", "Access", "Flags", "New",
                                     "key"])

    def mark(self, how):
        for k in self.table.selected_values("key"):
            self.decisions[k] = how
        self._show()

    def sign(self):
        from ... import delegation_review as dr
        if not self.rows:
            self.info("Load first.")
            return
        rem = [r for r in self.rows if self.decisions.get(r["key"]) == "Remove"]
        note, ok = QInputDialog.getText(self, "Sign off", f"Signing off as {team.me()}.\n"
                                        f"{len(rem)} marked Remove. Note (optional):")
        if not ok:
            return
        dr.sign_off(self.rows, self.decisions, team.me(), note)
        self.status.setText(f"Signed off {datetime.date.today()} by {team.me()}.")
        if rem:
            run_or_request(self, _steps(self), [(f"{r['Owner']}: remove {r['Who']} "
                                                 f"({r['Access']})", dr.remove_args(r))
                                                for r in rem],
                           "Remove mailbox/calendar access", "Mailbox access review")

    def past(self):
        from ... import delegation_review as dr
        h = dr.history()
        if not h:
            self.info("No reviews yet.")
            return
        self.info("\n".join(f"{r['date']} – {r['by']}: {len(r['rows'])} entr(ies), "
                            f"{sum(1 for x in r['rows'] if x['Decision'] == 'Remove')} removed"
                            + (f" – {r['note']}" if r.get("note") else "")
                            for r in reversed(h[-12:])))
