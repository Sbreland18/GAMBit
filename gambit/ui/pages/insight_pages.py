"""Round 9 screens: Mismatch report, Withdrawn students' devices, Year-end checklist,
School reports, Unusual activity, Budget planner and the help-desk ticket queue."""

from __future__ import annotations

import os

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget,
)

from ... import team
from ...gam_runner import display_command
from ...settings import settings
from ..pickers import OUField
from ..steps import Step, StepList
from ..tools_base import ToolTab
from ..widgets import Page, ResultsTable, Worker, button


def goto(app, page: str, tab: str = ""):
    """Open a page (and one of its tabs, by title)."""
    if page not in getattr(app, "pages", {}):
        return None
    app.go(page)
    p = app.pages[page]
    tabs = getattr(p, "tabs", None)
    if tab and isinstance(tabs, QTabWidget) and tabs.count():
        for i in range(tabs.count()):
            if tabs.tabText(i).replace("&&", "&") == tab:
                tabs.setCurrentIndex(i)
                break
    return p


def _users(directory):
    if directory.users:
        return directory.users
    from ...directory import load_users
    return load_users()


def _csv_reader():
    from ...directory import run_gam_csv
    return lambda a: run_gam_csv(a, 3600)


def _send_or_run(page, steps_list, items: list[tuple[str, list[str]]], title: str,
                 reason: str):
    """Approval request when there's a team folder and the user wants it; else run."""
    if not items:
        page.info("Nothing selected that GAMbit can fix automatically.")
        return
    if team.folder() and page.confirm(f"Send {len(items)} change(s) for approval?\n\n" +
                                      "\n".join(display_command(a) for _l, a in items[:15])):
        team.new_request([a for _l, a in items], reason, title=title)
        if hasattr(page.app, "update_approvals_badge"):
            page.app.update_approvals_badge()
        page.info("Sent – see the Approvals page.")


# ============================================================ mismatches ===
class MismatchPage(Page):
    title = "Mismatch report"
    subtitle = ("ClassLink (or your roster), Google accounts and Chromebook assignments side "
                "by side: students with no device, devices assigned to students who left, "
                "people missing from Google, accounts in the wrong school.")

    def build(self):
        from ...tools import reconcile
        o = reconcile.options()
        self.profile = QComboBox()
        self.one = QCheckBox("Every student should have a Chromebook (1:1)")
        self.one.setChecked(bool(o.get("one_to_one", True)))
        self.go_btn = button("Build the report", "primary", self.build_report)
        self.status = QLabel("", objectName="Muted")
        self.body.addLayout(self.row(QLabel("Roster"), self.profile, self.one, self.go_btn,
                                     self.status, stretch=False))
        self.summary = ResultsTable()
        self.summary.setMaximumHeight(200)
        self.summary.row_clicked.connect(self._only)
        self.body.addWidget(self.summary)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.body.addLayout(self.row(
            button("Fix selected", "primary", self.fix),
            button("Send selected for approval", slot=self.send),
            button("Add selected devices to the collection list", slot=self.collect),
            button("Practice run of selected fixes", slot=self.practice),
            button("Show everything", slot=lambda: self._show(self.findings))))
        self.steps = StepList(self)
        self.steps.setMaximumHeight(150)
        self.body.addWidget(self.steps)
        self.findings: list[dict] = []
        from .round10_pages import autofix_box
        self.body.addWidget(autofix_box(self))
        self._profiles(o.get("profile", ""))

    def on_show(self):
        self._profiles(self.profile.currentData() or "")

    def _profiles(self, keep: str):
        from ... import rostersync_run
        self.profile.blockSignals(True)
        self.profile.clear()
        self.profile.addItem("(Chromebooks only – no roster)", "")
        for name in rostersync_run.all_profiles():
            self.profile.addItem(name, name)
        i = self.profile.findData(keep)
        self.profile.setCurrentIndex(i if i >= 0 else (1 if self.profile.count() > 1 else 0))
        self.profile.blockSignals(False)

    def build_report(self):
        from ...tools import reconcile
        o = {**reconcile.options(), "profile": self.profile.currentData() or "",
             "one_to_one": self.one.isChecked()}
        reconcile.save_options(o)
        self.go_btn.setEnabled(False)
        self.status.setText("Reading the roster, accounts and Chromebooks…")

        def work():
            return reconcile.build(o["profile"], _users(self.directory), _csv_reader(), o)

        def done(res):
            self.go_btn.setEnabled(True)
            self.findings, notes = res
            self.summary.set_rows(["Problem", "How many"], reconcile.summary(self.findings))
            self._show(self.findings)
            self.status.setText(f"{len(self.findings)} mismatch(es)" +
                                (" · " + " ".join(notes) if notes else ""))

        def fail(e):
            self.go_btn.setEnabled(True)
            self.status.setText("")
            self.info(str(e))
        Worker(work, on_done=done, on_error=fail)

    def _only(self, row: dict):
        prob = row.get("Problem", "")
        self._show([f for f in self.findings if f["Problem"] == prob])

    def _show(self, items):
        self.shown = items
        self.table.set_rows(["Problem", "Who", "Details", "Fix"],
                            [[f["Problem"], f["Who"], f["Details"], f["Fix"]] for f in items])

    def _selected(self) -> list[dict]:
        sel = self.table.selected_dicts()
        keys = {(s["Problem"], s["Who"], s["Details"]) for s in sel}
        return [f for f in getattr(self, "shown", []) if (f["Problem"], f["Who"],
                                                          f["Details"]) in keys]

    def _fixable(self):
        return [(f"{f['Who']}: {f['Problem']}", a) for f in self._selected() for a in f["args"]]

    def fix(self):
        items = self._fixable()
        if not items:
            self.info("Select rows that have “Run the fix” in the Fix column.")
            return
        if self.confirm(f"Run {len(items)} fix(es)?\n\n" +
                        "\n".join(display_command(a) for _l, a in items[:15])):
            self.steps.run([Step(label, a) for label, a in items],
                           lambda _s: self.info(self.steps.summary()))

    def practice(self):
        from .round10_pages import practice_run
        items = self._fixable() or [(f"{f['Who']}", a) for f in self.findings for a in f["args"]]
        if not items:
            self.info("Build the report first.")
            return
        practice_run(self, [a for _l, a in items], "mismatch fixes")

    def send(self):
        if not team.folder():
            self.info("Approvals need a team folder (Settings & Updates → Team).")
            return
        _send_or_run(self, self.steps, self._fixable(), f"Mismatch fixes ({len(self._fixable())})",
                     "Fixes from the mismatch report:\n" + "\n".join(
                         f"• {f['Who']} – {f['Problem']}: {f['Details']}"
                         for f in self._selected()[:50]))

    def collect(self):
        from ...tools import reconcile
        devs = [f for f in self._selected() if f["kind"] == "dev_withdrawn"]
        if not devs:
            self.info("Select “Chromebook assigned to a student who left” rows.")
            return
        items = reconcile.load_items()
        users = {u["email"].lower(): u for u in self.directory.users}
        found = []
        for f in devs:
            d, u = f["device"], users.get(f["student"].lower(), {"email": f["student"]})
            found.append({"serial": d["serial"], "asset": d["asset"], "user": f["student"],
                          "name": u.get("name", ""), "school": u.get("ou", ""),
                          "model": d["model"], "device_ou": d["ou"],
                          "disabled": d["status"] == "DISABLED"})
        new = reconcile.merge(items, found)
        reconcile.save_items(items)
        o = reconcile.collect_options()
        steps = [(f"{i['serial']}: mark for collection", a) for i in new
                 for a in reconcile.flag_commands(i, o)]
        msg = (f"Added {len(new)} device(s) to Chromebook fleet → Withdrawn students' "
               "devices.")
        if steps:
            self.steps.run([Step(label, a) for label, a in steps],
                           lambda _s: self.info(msg))
        else:
            self.info(msg)


# ================================================ withdrawn students' devices ===
class WithdrawnDevicesTab(ToolTab):
    intro = ("Chromebooks still assigned to students who have left (suspended, or moved to "
             "the withdrawn org unit). GAMbit can mark each device, open a help-desk "
             "ticket for the building, and close the loop when you scan it back in.")

    def build(self):
        from ...tools import reconcile
        o = reconcile.collect_options()
        box, form = self.page.group("Settings")
        self.root = OUField(self.directory, "/Students")
        self.root.set_path(o["student_root"])
        self.wd = OUField(self.directory, "/Students/Withdrawn")
        self.wd.set_path(o["withdrawn_ou"])
        self.note = QCheckBox("Write “COLLECT – student left” into the device notes")
        self.note.setChecked(bool(o["note"]))
        self.disable = QCheckBox("Disable the device until it's back (re-enabled on check-in)")
        self.disable.setChecked(bool(o["disable"]))
        self.ticket = QCheckBox("Open a help-desk ticket for each device")
        self.ticket.setChecked(bool(o["ticket"]))
        self.recent = QCheckBox("Also match the last person who signed in (unassigned "
                                "devices)")
        self.recent.setChecked(bool(o["use_recent"]))
        self.ret = OUField(self.directory, "optional, e.g. /Chromebooks/Returned")
        self.ret.set_path(o.get("return_ou", ""))
        form.addRow("Students are under", self.root)
        form.addRow("Students who left are in", self.wd)
        form.addRow("", self.note)
        form.addRow("", self.disable)
        form.addRow("", self.ticket)
        form.addRow("", self.recent)
        form.addRow("After check-in move to", self.ret)
        self.daily = QCheckBox("Check every morning (with the daily background task)")
        self.daily.setChecked(bool(settings.get("collect/enabled", False)))
        self.daily.toggled.connect(lambda on: settings.set("collect/enabled", on))
        form.addRow("", self.daily)
        form.addRow("", self.row(button("Find devices now", "primary", self.find),
                                 button("Save", slot=self._opts)))
        self.lay.addWidget(box)
        self.scan = QLineEdit(placeholderText="Scan or type a serial number / asset tag to "
                                              "check a device in, then Enter")
        self.scan.setStyleSheet("font-size:14pt;padding:6px;")
        self.scan.returnPressed.connect(self.check_in)
        self.lay.addWidget(self.scan)
        self.last = QLabel("")
        self.lay.addWidget(self.last)
        self.lay.addWidget(self.status)
        self.show_all = QCheckBox("Show collected and dismissed devices too")
        self.show_all.toggled.connect(self.refresh)
        self.lay.addWidget(self.show_all)
        self.table = ResultsTable()
        self.table.setMinimumHeight(260)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(button("Open tickets for selected", slot=self.tickets),
                                    button("Dismiss selected", slot=self.dismiss)))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.refresh()

    def _opts(self) -> dict:
        from ...tools import reconcile
        o = {"student_root": self.root.path() or "/Students",
             "withdrawn_ou": self.wd.path(), "note": self.note.isChecked(),
             "disable": self.disable.isChecked(), "ticket": self.ticket.isChecked(),
             "use_recent": self.recent.isChecked(), "return_ou": self.ret.path()}
        reconcile.save_collect_options(o)
        return o

    def refresh(self, *_):
        from ...tools import reconcile
        items = reconcile.load_items()
        if not self.show_all.isChecked():
            items = [i for i in items if i["status"] == "To collect"]
        self.table.set_rows(["Serial", "Asset tag", "Student", "School", "Flagged", "Status",
                             "Ticket", "Collected"],
                            [[i["serial"], i.get("asset", ""), i["user"], i.get("school", ""),
                              i.get("flagged", ""), i["status"],
                              "yes" if i.get("ticket") else "", i.get("collected", "")[:16]
                              .replace("T", " ")] for i in items])
        todo = sum(1 for i in reconcile.load_items() if i["status"] == "To collect")
        self.status.setText(f"{todo} device(s) to collect.")

    def find(self):
        from ...tools import reconcile
        o = self._opts()
        self.status.setText("Reading Chromebooks…")

        def work():
            code, cros, err = _csv_reader()(reconcile.COLLECT_ARGS)
            if code != 0:
                raise RuntimeError((err or "Couldn't list Chromebooks").strip()[-200:])
            items = reconcile.load_items()
            new = reconcile.merge(items, reconcile.find_withdrawn(_users(self.directory),
                                                                  cros, o))
            reconcile.save_items(items)
            return new

        def done(new):
            self.refresh()
            if not new:
                self.status.setText(self.status.text() + " Nothing new.")
                return
            steps = [(f"{i['serial']}: mark for collection", a) for i in new
                     for a in reconcile.flag_commands(i, o)]
            if o["ticket"]:
                self._open_tickets(new)
            if steps:
                self.run_steps(self.steps, steps, lambda _s: self.refresh())
            else:
                self.info(f"{len(new)} new device(s) to collect.")
        Worker(work, on_done=done, on_error=lambda e: (self.status.setText(""),
                                                       self.info(str(e))))

    def _open_tickets(self, items):
        from ...integrations import ticketing as tk
        from ...tools import reconcile
        if not (tk.configured() and tk.can("create")):
            self.info("Set up your help desk in Settings & Updates → Integrations to open "
                      "tickets.")
            return
        serials = [i["serial"] for i in items if not i.get("ticket")]

        def work():
            all_items = reconcile.load_items()
            n = 0
            for it in all_items:
                if it["serial"] in serials and not it.get("ticket"):
                    it["ticket"] = tk.create(*reconcile.ticket_text(it))
                    n += 1
            reconcile.save_items(all_items)
            return n
        Worker(work, on_done=lambda n: (self.refresh(), self.page.app.log_line(
            f"📝 Opened {n} {tk.name()} ticket(s).") if hasattr(self.page.app, "log_line")
            else None), on_error=lambda e: self.info(f"Couldn't open tickets:\n{e}"))

    def _sel_items(self):
        from ...tools import reconcile
        serials = set(self.table.selected_values("Serial"))
        items = reconcile.load_items()
        return items, [i for i in items if i["serial"] in serials]

    def tickets(self):
        _items, sel = self._sel_items()
        if sel:
            self._open_tickets(sel)

    def dismiss(self):
        from ...tools import reconcile
        items, sel = self._sel_items()
        if sel and self.confirm(f"Take {len(sel)} device(s) off the list?"):
            for i in sel:
                i["status"] = "Dismissed"
            reconcile.save_items(items)
            self.refresh()

    def check_in(self):
        from ...integrations import ticketing as tk
        from ...tools import reconcile
        code = self.scan.text()
        self.scan.clear()
        items = reconcile.load_items()
        it, cmds, msg = reconcile.check_in(items, code, team.me(), self._opts())
        self.last.setText(msg)
        if not it:
            return
        reconcile.save_items(items)
        self.refresh()
        if cmds:
            self.run_steps(self.steps, [(f"{it['serial']}: checked in", a) for a in cmds])
        if it.get("ticket") and tk.configured() and tk.can("note"):
            tid = tk.ticket_id(it["ticket"]) or it["ticket"]
            Worker(tk.note, tid, f"GAMbit: Chromebook {it['serial']} collected by "
                                      f"{team.me()} on {it['collected'][:10]}. It can be "
                                      "closed.", on_done=lambda _r: None,
                   on_error=lambda e: self.page.app.log_line(f"Ticket note failed: {e}", "#f85149")
                   if hasattr(self.page.app, "log_line") else None)


# ==================================================== year-end checklist ===
class YearEndTab(ToolTab):
    intro = ("Everything for the end of the school year in one dated checklist. Each step "
             "opens the right GAMbit screen; sign-off steps go to Approvals. Turn on "
             "reminders and the daily background task emails what's due.")

    def build(self):
        from ... import yearend
        self.plan = yearend.load()
        self.day = QDateEdit()
        self.day.setCalendarPopup(True)
        self.day.setDate(QDate(yearend.last_day(self.plan)))
        self.day.dateChanged.connect(self._day)
        self.remind = QCheckBox("Send reminders (overdue and due within 3 days)")
        self.remind.setChecked(bool(self.plan.get("reminders")))
        self.remind.toggled.connect(self._remind)
        self.bar = QProgressBar()
        self.bar.setMaximumWidth(260)
        self.lay.addLayout(self.row(QLabel("Last day of school"), self.day, self.remind,
                                    self.bar, stretch=False))
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Due", "Step", "Status", "Owner", "Where",
                                              "Done by"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setMinimumHeight(420)
        self.table.itemSelectionChanged.connect(self._detail)
        self.table.doubleClicked.connect(lambda *_: self.go_there())
        self.lay.addWidget(self.table, 1)
        self.what = QLabel("", objectName="Muted")
        self.what.setWordWrap(True)
        self.lay.addWidget(self.what)
        self.lay.addLayout(self.row(button("Go there", "primary", self.go_there),
                                    button("Mark done", slot=lambda: self._mark("Done")),
                                    button("Skip", slot=lambda: self._mark("Skipped")),
                                    button("Reopen", slot=lambda: self._mark("To do")),
                                    button("Ask for sign-off…", slot=self.signoff),
                                    button("Set owner…", slot=self.owner)))
        self.refresh()

    def on_show(self):
        self.refresh()

    def _day(self, d):
        from ... import yearend
        self.plan["last_day"] = d.toPython().isoformat()
        yearend.save(self.plan)
        self.refresh()

    def _remind(self, on):
        from ... import yearend
        self.plan["reminders"] = on
        yearend.save(self.plan)

    def refresh(self):
        from ... import yearend
        self.plan = yearend.load()
        self.rows = yearend.rows(self.plan)
        done, total = yearend.progress(self.rows)
        self.bar.setMaximum(total)
        self.bar.setValue(done)
        self.bar.setFormat(f"{done} of {total} done")
        colors = {"Overdue": "#cf222e", "Due this week": "#9a6700", "Done": "#1a7f37",
                  "Waiting for sign-off": "#0969da", "Skipped": "#57606a"}
        self.table.setRowCount(0)
        for r in self.rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            vals = [r["due"], r["title"] + ("  ✍" if r["signoff"] else ""), r["state"],
                    r["owner"], r["page"] + (f" → {r['tab']}" if r["tab"] else ""),
                    (r["done_by"] + " " + r["done_at"][:10]).strip()
                    if r["status"] != "To do" else ""]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 2 and r["state"] in colors:
                    from PySide6.QtGui import QColor
                    it.setForeground(QColor(colors[r["state"]]))
                self.table.setItem(i, c, it)

    def _cur(self):
        i = self.table.currentRow()
        return self.rows[i] if 0 <= i < len(self.rows) else None

    def _detail(self):
        r = self._cur()
        self.what.setText(r["what"] if r else "")

    def go_there(self):
        r = self._cur()
        if r:
            goto(self.page.app, r["page"], r["tab"])

    def _mark(self, status):
        from ... import yearend
        r = self._cur()
        if r:
            yearend.mark(self.plan, r["key"], status, team.me())
            self.refresh()

    def signoff(self):
        from ... import yearend
        r = self._cur()
        if not r:
            return
        if not team.folder():
            self.info("Sign-off requests need a team folder (Settings & Updates → Team).")
            return
        note, ok = QInputDialog.getMultiLineText(self, "Ask for sign-off",
                                                 f"{r['title']}\n\nAnything the approver "
                                                 "should know? (optional)")
        if ok:
            yearend.ask_signoff(self.plan, r["key"], note.strip())
            self.refresh()
            self.info("Sent to Approvals. The step is marked done when it's approved.")

    def owner(self):
        from ... import yearend
        r = self._cur()
        if not r:
            return
        who, ok = QInputDialog.getText(self, "Owner", f"Who's responsible for “{r['title']}”? "
                                       "(email – they get the reminders)", text=r["owner"])
        if ok:
            self.plan["owners"][r["key"]] = who.strip()
            yearend.save(self.plan)
            self.refresh()


# ======================================================== school reports ===
class SchoolReportsPage(Page):
    title = "School reports"
    subtitle = ("A weekly email to each principal with only their school: students who "
                "haven't signed in, missing guardians, Chromebooks in repair or past their "
                "update date, and Classroom use.")

    def build(self):
        from ... import school_reports as sr
        o = sr.options()
        box, form = self.group("Settings")
        self.root = OUField(self.directory, "/Students")
        self.root.set_path(o["root"])
        self.days = QSpinBox()
        self.days.setRange(3, 120)
        self.days.setValue(int(o["inactive_days"]))
        self.days.setSuffix(" days")
        self.principals = QPlainTextEdit(o["principals"])
        self.principals.setPlaceholderText("Lincoln Elementary = principal@…, secretary@…\n"
                                           "Hancock Middle = …")
        self.principals.setMaximumHeight(90)
        self.g = QCheckBox("Guardians")
        self.g.setChecked(bool(o["guardians"]))
        self.c = QCheckBox("Classroom use")
        self.c.setChecked(bool(o["classroom"]))
        self.d = QCheckBox("Chromebooks")
        self.d.setChecked(bool(o["devices"]))
        self.droot = OUField(self.directory, "optional – devices by org unit, e.g. /Chromebooks")
        self.droot.set_path(o.get("device_root", ""))
        self.district = QLineEdit(o.get("district_to", ""))
        self.district.setPlaceholderText("optional – all-schools summary to, e.g. you@…")
        form.addRow("Students are under", self.root)
        form.addRow("School = first level below. Principals", self.principals)
        form.addRow("“Not signed in lately” means", self.days)
        form.addRow("Include", self.row(self.g, self.c, self.d, stretch=True))
        form.addRow("Chromebooks without a student", self.droot)
        form.addRow("District summary", self.district)
        self.status = QLabel("", objectName="Muted")
        form.addRow("", self.row(button("Build the report", "primary", self.load),
                                 button("Preview the email for the selected school",
                                        slot=self.preview),
                                 button("Send now", slot=self.send),
                                 button("Every Monday…", slot=self.schedule), self.status))
        self.body.addWidget(box)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.stats = {}

    def _opts(self):
        from ... import school_reports as sr
        o = {**sr.options(), "root": self.root.path() or "/Students",
             "inactive_days": self.days.value(), "principals": self.principals.toPlainText(),
             "guardians": self.g.isChecked(), "classroom": self.c.isChecked(),
             "devices": self.d.isChecked(), "device_root": self.droot.path(),
             "district_to": self.district.text().strip()}
        sr.save_options(o)
        return o

    def load(self):
        from ... import school_reports as sr
        o = self._opts()
        self.status.setText("Reading Google (large districts take a few minutes)…")

        def done(stats):
            self.stats = stats
            h, rows = sr.table(stats)
            self.table.set_rows(h, rows)
            self.status.setText(f"{len(stats)} school(s)")
        Worker(sr.fetch, o, users=_users(self.directory), on_done=done,
               on_error=lambda e: (self.status.setText(""), self.info(str(e))))

    def preview(self):
        import tempfile
        from ... import school_reports as sr
        sel = self.table.selected_dicts()
        if not self.stats or not sel:
            self.info("Build the report and select a school first.")
            return
        s = sel[0]["School"]
        _subj, body = sr.render(s, self.stats[s], self._opts())
        path = os.path.join(tempfile.gettempdir(), "gambit_school_preview.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def send(self):
        from ... import school_reports as sr
        self._opts()
        if not self.confirm("Email every principal their school's report now?"):
            return
        lines = []
        Worker(sr.send, lines.append, users=_users(self.directory),
               on_done=lambda bad: self.info("\n".join(lines) or "Done.") if not bad else
               self.info("Some emails failed:\n" + "\n".join(lines)),
               on_error=lambda e: self.info(str(e)))

    def schedule(self):
        from ... import school_reports as sr
        from ... import tasks_health
        self._opts()
        settings.set("schoolreports/scheduled", True)
        try:
            tasks_health.create(dict(sr.TASK))
            self.info("The school reports will go out every Monday at 6:40 AM.")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Saved, but the task couldn't be created here:\n{exc}")


# ======================================================= unusual activity ===
class WatchdogTab(ToolTab):
    intro = ("Every night GAMbit reads the last day of Google's audit logs and flags mass "
             "downloads or deletes, risky sign-ins, new admin roles and external sharing "
             "spikes. Findings are sent to your alert channels (and your help desk if that's on).")

    def build(self):
        from ...tools import watchdog as wd
        o = wd.options()
        box, form = self.page.group("What counts as unusual (in one day)")
        self.dl = QSpinBox()
        self.rm = QSpinBox()
        self.sh = QSpinBox()
        for sp, key in ((self.dl, "downloads"), (self.rm, "deletes"), (self.sh, "shares")):
            sp.setRange(5, 100000)
            sp.setValue(int(o[key]))
        self.susp = QCheckBox("Google's suspicious sign-in warnings")
        self.susp.setChecked(bool(o["suspicious"]))
        self.adm = QCheckBox("New admin roles and privileges")
        self.adm.setChecked(bool(o["admin"]))
        self.tsv = QCheckBox("Someone turned off 2-Step Verification")
        self.tsv.setChecked(bool(o.get("tsv_off", True)))
        self.apps = QCheckBox("Someone allowed a risky app that isn't on the approved list")
        self.apps.setChecked(bool(o.get("risky_apps", True)))
        self.travel = QCheckBox("Impossible travel – sign-ins from two places too far apart "
                                "(staff org unit below)")
        self.travel.setChecked(bool(o.get("travel", True)))
        self.travel_ou = QLineEdit(o.get("travel_ou", "/Staff"))
        self.cc = QCheckBox("Sign-ins from countries other than")
        self.cc.setChecked(bool(o["check_countries"]))
        self.countries = QLineEdit(o["countries"])
        self.countries.setPlaceholderText("US, CA")
        self.ignore = QLineEdit(o.get("ignore", ""))
        self.ignore.setPlaceholderText("accounts to ignore, e.g. backup service accounts")
        form.addRow("Files downloaded by one person", self.dl)
        form.addRow("Files deleted by one person", self.rm)
        form.addRow("Files shared outside by one person", self.sh)
        form.addRow("", self.susp)
        form.addRow("", self.adm)
        form.addRow("", self.tsv)
        form.addRow("", self.apps)
        form.addRow("", self.row(self.travel, self.travel_ou, stretch=False))
        form.addRow("", self.row(self.cc, self.countries, stretch=False))
        form.addRow("Ignore", self.ignore)
        form.addRow("", self.row(button("Save", slot=self._opts),
                                 button("Check the last 24 hours now", "primary", self.check),
                                 button("Every night…", slot=self.schedule), self.status))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.auto = QCheckBox("When the nightly check finds a risky sign-in or mass download, "
                              "send a lock-down for approval straight away")
        self.auto.setChecked(bool(o.get("auto_respond")))
        self.auto.toggled.connect(lambda _on: self._opts())
        self.lay.addWidget(self.auto)
        self.lay.addLayout(self.row(button("Respond…", "primary", self.respond),
                                    button("Investigate selected", slot=self.investigate),
                                    button("Mark reviewed", slot=self.reviewed)))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.refresh()

    def _opts(self):
        from ...tools import watchdog as wd
        o = {**wd.options(), "downloads": self.dl.value(), "deletes": self.rm.value(),
             "shares": self.sh.value(), "suspicious": self.susp.isChecked(),
             "admin": self.adm.isChecked(), "check_countries": self.cc.isChecked(),
             "tsv_off": self.tsv.isChecked(), "risky_apps": self.apps.isChecked(),
             "travel": self.travel.isChecked(),
             "travel_ou": self.travel_ou.text().strip() or "/",
             "countries": self.countries.text().strip(), "ignore": self.ignore.text().strip(),
             "auto_respond": self.auto.isChecked() if hasattr(self, "auto") else
             wd.options().get("auto_respond", False)}
        wd.save_options(o)
        return o

    def refresh(self):
        from ...tools import watchdog as wd
        self.items = list(reversed(wd.load_findings()))[:1000]
        self.table.set_rows(["When", "Finding", "Who", "Details", "Status"],
                            [[f.get("When", "").replace("T", " "), f["Finding"], f["Who"],
                              f["Details"], f.get("Status", "New")] for f in self.items])

    def check(self):
        from ...tools import watchdog as wd
        self._opts()
        self.status.setText("Reading the audit logs…")
        Worker(wd.run, lambda _m: None, on_done=lambda found: (
            self.status.setText(f"{len(found)} finding(s)."), self.refresh()),
            on_error=lambda e: (self.status.setText(""), self.info(str(e))))

    def schedule(self):
        from ... import tasks_health
        from ...tools import watchdog as wd
        self._opts()
        settings.set("watchdog/scheduled", True)
        try:
            tasks_health.create(dict(wd.TASK))
            self.info("GAMbit will check for unusual activity every morning at 5:20 AM.")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Saved, but the task couldn't be created here:\n{exc}")

    def _sel(self):
        sel = self.table.selected_dicts()
        keys = {(s["When"], s["Who"], s["Details"]) for s in sel}
        return [f for f in self.items if (f.get("When", "").replace("T", " "), f["Who"],
                                          f["Details"]) in keys]

    def investigate(self):
        sel = self._sel()
        if not sel:
            self.info("Select a finding first.")
            return
        f = sel[0]
        act = getattr(self.page, "activity", None)
        if act is None:
            return
        self.page.tabs.setCurrentWidget(act)
        act.preset.setCurrentIndex(0)
        act.app.setCurrentIndex(max(0, act.app.findData(f.get("app", "drive"))))
        act.events.setText(f.get("events", ""))
        if "@" in f["Who"]:
            act.who.setText(f["Who"])
        act.days.setValue(3)
        act.search()

    TAB_ATTR = {("Workflows", "Hacked account"): "hacked_tab",
                ("Google Drive", "Fix sharing"): "fix_tab",
                ("Google Drive", "Restore files"): "restore_tab",
                ("Investigations", "Audit log"): "activity"}

    def respond(self):
        from ...tools import playbooks
        sel = self._sel()
        if not sel:
            self.info("Select a finding first.")
            return
        f = sel[0]
        acts = playbooks.actions(f)
        if not acts:
            self.info("There's no ready-made response for this one – use Investigate.")
            return
        labels = [f"{a['label']} – {a['why']}" for a in acts]
        choice, ok = QInputDialog.getItem(self, "Respond", f"{f['Finding']}: {f['Who']}",
                                          labels, 0, False)
        if not ok:
            return
        a = acts[labels.index(choice)]
        if a["kind"] == "steps":
            self._do_steps(a["steps"], f"{a['label']}: {f['Who']}",
                           f"{f['Finding']}: {f['Details']}")
        elif a["kind"] == "goto":
            p = goto(self.page.app, a["page"], a["tab"])
            tab = getattr(p, self.TAB_ATTR.get((a["page"], a["tab"]), ""), None)
            who = (a.get("prefill") or {}).get("who", "")
            if tab is not None and who and hasattr(tab, "who"):
                tab.who.setText(who)
                if a.get("call") and hasattr(tab, a["call"]):
                    getattr(tab, a["call"])()
        elif a["kind"] == "admins":
            def got(rows):
                if rows is None:
                    return
                items = playbooks.admin_rows(rows, a.get("role", ""))
                if not items:
                    self.info(f"{a['target']} has no admin roles now.")
                    return
                names = [f"{i['role']} ({i['scope'] or 'whole domain'})" for i in items]
                pick, ok2 = QInputDialog.getItem(self, "Remove an admin role",
                                                 f"{a['target']}'s admin roles", names, 0,
                                                 False)
                if ok2:
                    it = items[names.index(pick)]
                    self._do_steps(playbooks.remove_admin_steps([it], a["target"]),
                                   f"Remove {it['role']} from {a['target']}",
                                   f"{f['Finding']}: {f['Details']}")
            self.read(["print", "admins", "user", a["target"]], got)

    def _do_steps(self, steps, title, reason):
        from PySide6.QtWidgets import QMessageBox
        listing = "\n".join(f"• {lab}" for lab, _a in steps)
        mb = QMessageBox(self)
        mb.setWindowTitle("Respond")
        mb.setText(f"{title}\n\n{listing}")
        run = mb.addButton("Run now", QMessageBox.AcceptRole)
        send = mb.addButton("Send for approval", QMessageBox.ActionRole) if team.folder() \
            else None
        mb.addButton(QMessageBox.Cancel)
        mb.exec()
        clicked = mb.clickedButton()
        if clicked is None:
            clicked = run
        if send is not None and clicked == send:
            team.new_request([a for _l, a in steps], reason, title=title,
                             extra={"kind": "playbook"})
            self.info("Sent – see the Approvals page.")
        elif clicked == run:
            self.run_steps(self.steps, steps)

    def reviewed(self):
        from ...tools import watchdog as wd
        sel = self._sel()
        if not sel:
            return
        all_items = wd.load_findings()
        keys = {(f.get("When"), f["Who"], f["Details"]) for f in sel}
        for f in all_items:
            if (f.get("When"), f["Who"], f["Details"]) in keys:
                f["Status"] = f"Reviewed by {team.me()}"
        wd.save_findings(all_items)
        self.refresh()


# ========================================================== budget planner ===
class BudgetPage(Page):
    title = "Budget planner"
    subtitle = ("Licenses you could free (suspended, inactive or never-used accounts) and "
                "what they cost, plus Chromebook replacements by school and school year.")

    def build(self):
        from ...tools import budget
        o = budget.options()
        tabs = QTabWidget()
        self.tabs = tabs
        # licenses
        lic = ToolTabLike(self)
        self.inactive = QSpinBox()
        self.inactive.setRange(30, 1000)
        self.inactive.setValue(int(o["inactive_days"]))
        self.inactive.setSuffix(" days without sign-in")
        self.lic_status = QLabel("", objectName="Muted")
        lic.lay.addLayout(self.row(QLabel("Count as inactive after"), self.inactive,
                                   button("Load licenses", "primary", self.load_licenses),
                                   self.lic_status, stretch=False))
        self.lic = QTableWidget(0, 8)
        self.lic.setHorizontalHeaderLabels(["License", "Assigned", "Suspended", "Inactive",
                                            "Never used", "Could free", "Price / year",
                                            "Savings / year"])
        self.lic.verticalHeader().setVisible(False)
        self.lic.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.lic.setMinimumHeight(180)
        lic.lay.addWidget(self.lic)
        self.lic_total = QLabel("")
        lic.lay.addWidget(self.lic_total)
        self.detail = ResultsTable()
        self.detail.setMinimumHeight(240)
        lic.lay.addWidget(self.detail, 1)
        lic.lay.addLayout(self.row(button("Release selected licenses (send for approval)",
                                          slot=self.release)))
        self.steps = StepList(self)
        self.steps.setMaximumHeight(140)
        lic.lay.addWidget(self.steps)
        tabs.addTab(lic, "Licenses")
        # devices
        dev = ToolTabLike(self)
        self.cost = QDoubleSpinBox()
        self.cost.setRange(0, 5000)
        self.cost.setPrefix("$")
        self.cost.setValue(float(o["device_cost"]))
        self.years = QSpinBox()
        self.years.setRange(1, 10)
        self.years.setValue(int(o["years"]))
        self.years.setSuffix(" years")
        self.droot = OUField(self.directory, "/Chromebooks")
        self.droot.set_path(o.get("device_root", "/Chromebooks"))
        self.dev_status = QLabel("", objectName="Muted")
        dev.lay.addLayout(self.row(QLabel("Cost per device"), self.cost, QLabel("Plan"),
                                   self.years, QLabel("Devices are under"), self.droot,
                                   stretch=False))
        dev.lay.addLayout(self.row(button("Load Chromebooks", "primary", self.load_devices),
                                   self.dev_status))
        self.dev_sum = QLabel("")
        self.dev_sum.setWordWrap(True)
        dev.lay.addWidget(self.dev_sum)
        self.dev = ResultsTable()
        dev.lay.addWidget(self.dev, 1)
        tabs.addTab(dev, "Chromebook replacements")
        from .round10_pages import RepairsTab
        self.repairs_tab = RepairsTab(self)
        tabs.addTab(self.repairs_tab, "Repairs && loaners")
        from .round14_tabs import PremiumLicensesTab
        self.premium_tab = PremiumLicensesTab(self)
        tabs.addTab(self.premium_tab, "Premium licenses")
        from .round15_tabs import NextYearTab
        self.nextyear_tab = NextYearTab(self)
        tabs.addTab(self.nextyear_tab, "Next year")
        self.body.addWidget(tabs, 1)
        self.summary_rows, self.details = [], []

    def _save(self):
        from ...tools import budget
        o = budget.options()
        o.update(inactive_days=self.inactive.value(), device_cost=self.cost.value(),
                 years=self.years.value(), device_root=self.droot.path())
        budget.save_options(o)
        return o

    def load_licenses(self):
        from ...tools import budget
        o = self._save()
        self.lic_status.setText("Reading licenses (a minute or two for big domains)…")

        def work():
            code, rows, err = _csv_reader()(budget.USERS_ARGS)
            if code != 0:
                raise RuntimeError((err or "GAM failed").strip()[-200:])
            return budget.reclaimable(budget.license_holders(rows), o["inactive_days"],
                                      o["prices"])

        def done(res):
            self.summary_rows, self.details = res
            self._fill_lic()
            self.detail.set_rows(["Account", "License", "Why", "Org unit"],
                                 [[d["Account"], d["License"], d["Why"], d["Org unit"]]
                                  for d in self.details])
            self.lic_status.setText("")
        Worker(work, on_done=done, on_error=lambda e: (self.lic_status.setText(""),
                                                       self.info(str(e))))

    def _fill_lic(self):
        self.lic.blockSignals(True)
        self.lic.setRowCount(0)
        self._spins = []
        for r in self.summary_rows:
            i = self.lic.rowCount()
            self.lic.insertRow(i)
            for c, k in enumerate(["License", "Assigned", "Suspended", "Inactive",
                                   "Never used", "Could free"]):
                self.lic.setItem(i, c, QTableWidgetItem(str(r[k])))
            sp = QDoubleSpinBox()
            sp.setRange(0, 10000)
            sp.setPrefix("$")
            sp.setValue(float(r["Price / year"]))
            sp.valueChanged.connect(lambda v, sku=r["sku"]: self._price(sku, v))
            self.lic.setCellWidget(i, 6, sp)
            self.lic.setItem(i, 7, QTableWidgetItem(f"${r['Savings / year']:,.0f}"))
        self.lic.blockSignals(False)
        total = sum(r["Savings / year"] for r in self.summary_rows)
        free = sum(r["Could free"] for r in self.summary_rows)
        self.lic_total.setText(f"<b>{free} license(s) could be freed – about ${total:,.0f} a "
                               "year</b> at the prices you entered. Licenses held by suspended "
                               "accounts are usually the safest to release first.")

    def _price(self, sku, v):
        from ...tools import budget
        o = budget.options()
        o.setdefault("prices", {})[sku] = v
        budget.save_options(o)
        for r in self.summary_rows:
            if r["sku"] == sku:
                r["Price / year"] = v
                r["Savings / year"] = v * r["Could free"]
        total = sum(r["Savings / year"] for r in self.summary_rows)
        for i, r in enumerate(self.summary_rows):
            self.lic.setItem(i, 7, QTableWidgetItem(f"${r['Savings / year']:,.0f}"))
        free = sum(r["Could free"] for r in self.summary_rows)
        self.lic_total.setText(f"<b>{free} license(s) could be freed – about ${total:,.0f} a "
                               "year</b> at the prices you entered.")

    def release(self):
        sel = self.detail.selected_dicts()
        keys = {(s["Account"], s["License"]) for s in sel}
        items = [(f"{d['Account']}: release {d['License']}", d["args"]) for d in self.details
                 if (d["Account"], d["License"]) in keys]
        if not items:
            self.info("Select the accounts to release licenses from.")
            return
        if team.folder():
            why = {(d["Account"], d["License"]): d["Why"] for d in self.details}
            _send_or_run(self, self.steps, items, f"Release {len(items)} license(s)",
                         "From the budget planner:\n" + "\n".join(
                             f"• {a} – {lic} ({why[(a, lic)]})" for a, lic in sorted(keys))[:4000])
        elif self.confirm(f"Release {len(items)} license(s) now?"):
            self.steps.run([Step(lab, a) for lab, a in items],
                           lambda _s: self.info(self.steps.summary()))

    def load_devices(self):
        from ... import fleet
        from ...tools import budget
        o = self._save()
        self.dev_status.setText("Reading Chromebooks…")

        def work():
            code, rows, err = _csv_reader()(["print", "cros", "fields", fleet.FIELDS,
                                             "listlimit", "1"])
            if code != 0:
                raise RuntimeError((err or "GAM failed").strip()[-200:])
            us = budget.user_schools(_users(self.directory))
            return budget.device_plan(fleet.devices(rows), o, us)

        def done(res):
            head, rows, per_year = res
            self.dev.set_rows(head, rows)
            self.dev_status.setText("")
            self.dev_sum.setText("Budget by school year: " + " · ".join(
                f"<b>{k}</b> ${v:,.0f}" for k, v in per_year.items() if v) or
                "No devices reach their end of updates in this window.")
        Worker(work, on_done=done, on_error=lambda e: (self.dev_status.setText(""),
                                                       self.info(str(e))))


class ToolTabLike(ToolTab):
    """A plain scrolling tab with a layout (no intro)."""


# ============================================================ ticket queue ===
class TicketQueuePage(Page):
    title = "Ticket queue"
    subtitle = ("Open help-desk tickets about accounts and Chromebooks. “Work on it” links "
                "the ticket and opens the right GAMbit screen already filled in; what you do "
                "is added to the ticket as a note. Password tickets can be handled end to end.")

    def build(self):
        from ...tools import ticket_auto
        box, form = self.group("Which tickets")
        self.which = QLabel("")
        form.addRow("Help desk", self.which)
        self.query = QLineEdit(settings.get("ticketing/queue_query", "") or "")
        self.query.setPlaceholderText("optional filter in your help desk's own terms (JQL, "
                                      "ServiceNow query, Zendesk search…)")
        self.words = QLineEdit(settings.get("ticketing/queue_words", "") or
                               settings.get("iiq/queue_words", "") or "")
        self.words.setPlaceholderText("optional – only tickets mentioning e.g. password, "
                                      "chromebook, google")
        self.cat = QLineEdit(settings.get("iiq/queue_category", "") or "")
        self.cat.setPlaceholderText("optional – one Incident IQ issue category ID")
        form.addRow("Filter", self.query)
        form.addRow("Words", self.words)
        form.addRow("Category ID", self.cat)
        self._qform = form
        self.status = QLabel("", objectName="Muted")
        form.addRow("", self.row(button("Load open tickets", "primary", self.load),
                                 self.status))
        self.body.addWidget(box)
        o = ticket_auto.options()
        abox, af = self.group("Password tickets, end to end")
        self.auto_on = QCheckBox("Handle “forgot my password” tickets automatically (checked "
                                 "every 15 minutes by the staff requests task)")
        self.auto_on.setChecked(bool(o["enabled"]))
        self.auto_students = QCheckBox("Only for student accounts")
        self.auto_students.setChecked(bool(o["students_only"]))
        self.auto_root = OUField(self.directory, "/Students")
        self.auto_root.set_path(o["student_root"])
        self.auto_to = QLineEdit(o.get("send_to", ""))
        self.auto_to.setPlaceholderText("leave empty to email the person the ticket is for "
                                        "(never the locked-out account)")
        self.auto_resolve = QCheckBox("Resolve the ticket afterwards (where the help desk "
                                      "allows it)")
        self.auto_resolve.setChecked(bool(o["resolve"]))
        af.addRow("", self.auto_on)
        af.addRow("", self.auto_students)
        af.addRow("Students are under", self.auto_root)
        af.addRow("Send the new password to", self.auto_to)
        af.addRow("", self.auto_resolve)
        af.addRow("", QLabel("Your approval rules decide: if password resets are approved "
                             "automatically they run straight away, otherwise each ticket "
                             "waits on the Approvals page. Passwords are emailed, never "
                             "written into the ticket.", objectName="Muted", wordWrap=True))
        af.addRow("", self.row(button("Save", slot=self._save_auto),
                               button("Handle password tickets now", slot=self.handle_now)))
        self.body.addWidget(abox)
        self.table = ResultsTable()
        self.table.row_clicked.connect(self._detail)
        self.body.addWidget(self.table, 1)
        self.desc = QLabel("", objectName="Muted")
        self.desc.setWordWrap(True)
        self.desc.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body.addWidget(self.desc)
        self.body.addLayout(self.row(button("Work on it", "primary", self.work_on),
                                     button("Add a note…", slot=self.note),
                                     button("Resolve…", slot=self.resolve),
                                     button("Open in the help desk", slot=self.open_web)))
        self.tickets: list[dict] = []
        self.on_show()

    def _save_auto(self):
        from ...tools import ticket_auto
        o = {**ticket_auto.options(), "enabled": self.auto_on.isChecked(),
             "students_only": self.auto_students.isChecked(),
             "student_root": self.auto_root.path() or "/Students",
             "send_to": self.auto_to.text().strip(), "resolve": self.auto_resolve.isChecked()}
        ticket_auto.save_options(o)
        return o

    def on_show(self):
        from ...integrations import ticketing as tk
        self.which.setText(tk.name() if tk.provider() else "not set up")
        self._qform.setRowVisible(self.cat, tk.provider() == "iiq")
        if not tk.configured():
            self.status.setText("Set up your help desk in Settings & Updates → Integrations "
                                "first.")

    def load(self):
        from ...integrations import ticketing as tk
        settings.set("ticketing/queue_query", self.query.text().strip())
        settings.set("ticketing/queue_words", self.words.text().strip())
        settings.set("iiq/queue_category", self.cat.text().strip())
        if not tk.configured():
            self.on_show()
            return
        self.status.setText("Loading…")
        opts = {"query": self.query.text().strip(), "words": self.words.text().strip()}
        if tk.provider() == "iiq" and self.cat.text().strip():
            opts["category_id"] = self.cat.text().strip()

        def done(ts):
            self.tickets = ts
            kinds = {"account": "Account", "chromebook": "Chromebook", "other": "–"}
            self.table.set_rows(["#", "Opened", "For", "Subject", "Type", "Account / serial"],
                                [[t["number"], t["created"], t["for"], t["subject"],
                                  kinds.get(t["kind"], "–"), t["target"]] for t in ts])
            self.status.setText(f"{len(ts)} open ticket(s)")
        Worker(tk.list_open, opts, on_done=done,
               on_error=lambda e: (self.status.setText(""), self.info(str(e))))

    def handle_now(self):
        from ...tools import ticket_auto
        o = self._save_auto()
        if not self.tickets:
            self.info("Load the open tickets first.")
            return
        cands = ticket_auto.candidates(self.tickets, self.directory.users, o,
                                       ticket_auto.handled())
        if not cands:
            self.info("No password tickets GAMbit can handle in this list.")
            return
        ok = [c for c in cands if not c["why_not"]]
        lines = [f"#{c['ticket']['number']}: {c['email']} → password to {c['to']}"
                 for c in ok] + [f"#{c['ticket']['number']}: skipped – {c['why_not']}"
                                 for c in cands if c["why_not"]]
        if not ok or not self.confirm("Handle these password tickets?\n\n" +
                                      "\n".join(lines[:30])):
            if not ok:
                self.info("\n".join(lines))
            return
        o = {**o, "enabled": True}

        def work():
            out = []
            for c in ok:
                done, msg = ticket_auto.run_one(c, opts=o)
                ticket_auto.mark_handled(c["ticket"]["id"])
                out.append(f"#{c['ticket']['number']}: {msg}")
            return out
        Worker(work, on_done=lambda out: (self.info("\n".join(out)), self.load()),
               on_error=lambda e: self.info(str(e)))

    def _cur(self):
        sel = self.table.selected_dicts()
        if not sel:
            return None
        return next((t for t in self.tickets if t["number"] == sel[0]["#"]), None)

    def _detail(self, *_):
        t = self._cur()
        self.desc.setText((f"<b>{t['subject']}</b> · {t['category']} {t['issue']}<br>"
                           f"{t['description'][:600]}") if t else "")

    def work_on(self):
        t = self._cur()
        if not t:
            self.info("Select a ticket first.")
            return
        app = self.app
        if hasattr(app, "ticket_box"):
            app.ticket_box.setText(t["id"])
            app._ticket_changed()
        if t["kind"] == "chromebook":
            p = goto(app, "Chromebooks")
            if p is not None and hasattr(p, "sn"):
                if hasattr(p, "tabs"):
                    p.tabs.setCurrentIndex(0)
                p.sn.setText(t["target"])
                p.cros_info()
        elif t["kind"] == "account":
            p = goto(app, "Users", "Manage a user")
            if p is not None and hasattr(p, "m_email"):
                p.m_email.setText(t["target"])
                p.user_info()
        else:
            self.info("GAMbit couldn't tell what this ticket is about. It's linked in the top "
                      "bar, so notes still go to it.")

    def note(self):
        from ...integrations import ticketing as tk
        t = self._cur()
        if not t:
            return
        text, ok = QInputDialog.getMultiLineText(self, "Note", f"Note for ticket #{t['number']}")
        if ok and text.strip():
            Worker(tk.note, t["id"], text.strip(),
                   on_done=lambda _r: self.status.setText("Note added."),
                   on_error=lambda e: self.info(str(e)))

    def resolve(self):
        from ...integrations import ticketing as tk
        t = self._cur()
        if not t:
            return
        if not tk.can("resolve"):
            self.info(f"{tk.name()} doesn't let GAMbit resolve tickets – close it there.")
            return
        text, ok = QInputDialog.getMultiLineText(self, "Resolve",
                                                 f"Resolution note for #{t['number']}")
        if ok:
            Worker(tk.resolve, t["id"], text.strip() or "Resolved with GAMbit.",
                   on_done=lambda _r: (self.status.setText("Resolved."), self.load()),
                   on_error=lambda e: self.info(str(e)))

    def open_web(self):
        t = self._cur()
        if t and t.get("link"):
            QDesktopServices.openUrl(QUrl(t["link"]))


__all__ = ["MismatchPage", "WithdrawnDevicesTab", "YearEndTab", "SchoolReportsPage",
           "WatchdogTab", "BudgetPage", "TicketQueuePage", "goto"]
