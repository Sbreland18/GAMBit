"""Round 25 pages built on data GAMbit already has: custom field check and SIS fill,
Chromebook sharing, device history, senior checkout, clean-up by school – plus the
“keep a Google Sheet up to date” dialog for saved searches."""

from __future__ import annotations

import datetime

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QLineEdit, QPlainTextEdit, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from ..pickers import OUField
from ..schedule_edit import ScheduleEdit
from ..tools_base import ToolTab
from ..widgets import Page, ResultsTable, Worker, button
from .round11_pages import run_or_request
from .round13_pages import _steps
from .round13_tabs import _csv, fill


def _date(days: int = 0, iso: str = "") -> QDateEdit:
    d = QDateEdit()
    d.setCalendarPopup(True)
    try:
        d.setDate(QDate(datetime.date.fromisoformat(iso)))
    except ValueError:
        d.setDate(QDate.currentDate().addDays(days))
    return d


def _iso(d: QDateEdit) -> str:
    return d.date().toPython().isoformat()


def _work(page, fn, done, status: QLabel | None = None, what: str = "Reading from Google…"):
    if status is not None:
        status.setText(what)

    def ok(res):
        if status is not None:
            status.setText("")
        done(res)

    def bad(e):
        if status is not None:
            status.setText("")
        page.info(str(e))
    Worker(fn, on_done=ok, on_error=bad)


def _need_rows(page, rows) -> bool:
    if not rows:
        page.info("Select one or more rows first.")
        return False
    return True


def _field_combo() -> QComboBox:
    from ... import custom_fields as cf
    c = QComboBox()
    c.setMinimumWidth(240)
    c.addItem("", "")
    for s, x in cf.config().get("schemas", {}).items():
        for f in x.get("fields", []):
            c.addItem(f"{s}.{f['name']}", f"{s}.{f['name']}")
    return c


# =================================================== custom field check ===
class FieldVsOUTab(ToolTab):
    intro = ("Compare students' custom fields with the org unit they're in, using "
             "Settings → Org units & schools. For example: Grade says 8th Grade but the "
             "student is in the 7th Grade org unit, or Current_School doesn't match their "
             "school. Fix each one by moving the student, or by correcting the field.")

    def build(self):
        from ... import field_check as fc
        box, form = self.page.group("What to compare")
        self.rule_rows = []
        rules = fc.rules() or fc.guess_rules()
        for kind in ("grade", "school"):
            combo = _field_combo()
            have = next((r["field"] for r in rules if r["against"] == kind), "")
            if have:
                i = combo.findData(have)
                combo.setCurrentIndex(i if i >= 0 else 0)
            form.addRow(f"Field for the {kind}", combo)
            self.rule_rows.append((kind, combo))
        self.ou = OUField(self.directory, "Limit to an org unit (blank = all students)")
        form.addRow("Where", self.ou)
        self.style = QComboBox()
        for k, lab in (("ordinal", "7th Grade"), ("number", "7"), ("grade n", "Grade 7"),
                       ("ordinal short", "7th")):
            self.style.addItem(lab, k)
        form.addRow("Write grades like", self.style)
        form.addRow("", self.row(button("Check", "primary", self.check),
                                 button("Set up custom fields…", slot=self._setup)))
        self.lay.addWidget(box)
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(
            button("Move selected students to the field's org unit", "primary",
                   lambda: self.fix("move")),
            button("Correct the field to match the org unit", slot=lambda: self.fix("field"))))
        self.sl = self.steps_list()
        self.lay.addWidget(self.sl)
        self.rows = []

    def _setup(self):
        from ..custom_fields_dialog import CustomFieldsDialog
        CustomFieldsDialog(self).exec()

    def _rules(self):
        return [{"field": c.currentData(), "against": k} for k, c in self.rule_rows
                if c.currentData()]

    def check(self):
        from ... import field_check as fc
        from ... import ou_map
        rules = self._rules()
        if not rules:
            self.info("Pick the custom field that holds the grade and/or the school. "
                      "(Set up custom fields first if the lists are empty.)")
            return
        if not ou_map.configured():
            self.info("Set up Settings → Org units & schools first, so GAMbit knows each org "
                      "unit's school and grade.")
            return
        fc.save_rules(rules)
        root = self.ou.path()
        roots = [root] if root else (ou_map.roots("students") or ["/"])
        cols = [r["field"] for r in rules]

        def work():
            run = _csv()
            users = []
            for r in roots:
                code, rows, err = run(fc.users_args(cols, r))
                if code != 0:
                    raise RuntimeError("Couldn't read users: " + (err or "")[-200:])
                users += rows
            return fc.check(users, rules)

        def done(rows):
            self.rows = rows
            fill(self.table, [{**r, "suggested move": r["move_to"] or "—",
                               "field value": r["field_value"], "org unit says":
                               r["ou_value"]} for r in rows],
                 ["email", "name", "ou", "problem", "field value", "org unit says",
                  "suggested move"])
            self.status.setText(f"{len(rows)} mismatch(es)." if rows else
                                "Every student's fields match their org unit.")
        _work(self.page, work, done, self.status, "Reading students and their fields…")

    def _selected(self):
        emails = {e.lower() for e in self.table.selected_values("email")}
        return [r for r in self.rows if r["email"].lower() in emails]

    def fix(self, how):
        from ... import field_check as fc
        rows = self._selected()
        if not _need_rows(self.page, rows):
            return
        steps = fc.fix_commands(rows, how, self.style.currentData())
        skipped = len(rows) - len(steps)
        title = ("Move students to the org unit their fields point at" if how == "move"
                 else "Correct custom fields to match the org unit")
        if skipped and how == "move":
            self.info(f"{skipped} selected row(s) have no clear org unit to move to (the "
                      "field is empty, or the map has no org unit for that school and "
                      "grade) – they're left out.")
        run_or_request(self.page, self.sl, steps, title, "Custom field check",
                       lambda _s: self.check())


class FillFromSISTab(ToolTab):
    intro = ("Copy values from your roster (a saved Roster sync) into custom fields – Student "
             "ID, grade, school, graduation year, anything in the export – so the fields "
             "never go stale. Preview shows every change; the background task keeps them in "
             "step each night, and stops if far more than usual would change.")

    def build(self):
        from ... import field_check as fc, rostersync_run
        cfg = fc.fill_config()
        box, form = self.page.group("Roster")
        self.profile = QComboBox()
        self.profile.addItems(sorted(rostersync_run.all_profiles()))
        if cfg["profile"]:
            self.profile.setCurrentText(cfg["profile"])
        form.addRow("Saved roster sync", self.row(self.profile, button(
            "Read its columns", slot=self.read_columns), stretch=False))
        self.match = _field_combo()
        if cfg["match_field"]:
            self.match.setCurrentIndex(max(0, self.match.findData(cfg["match_field"])))
        form.addRow("Also match by", self.row(self.match, QLabel(
            "(the custom field holding the student ID – for people whose email changed)"),
            stretch=False))
        self.lay.addWidget(box)
        box, v = self.page.group("Which roster column goes into which field")
        self.grid = QTableWidget(0, 3)
        self.grid.setHorizontalHeaderLabels(["Custom field", "Roster column", "Write it as"])
        from PySide6.QtWidgets import QHeaderView
        gh = self.grid.horizontalHeader()
        gh.setSectionResizeMode(0, QHeaderView.Stretch)   # readable field and column names
        gh.setSectionResizeMode(1, QHeaderView.Stretch)
        gh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.grid.setMinimumHeight(200)
        v.addRow(self.grid)
        self.clear_blank = QCheckBox("Blank the field when the roster has no value")
        self.clear_blank.setChecked(cfg["clear_blank"])
        self.limit = QSpinBox()
        self.limit.setRange(1, 100000)
        self.limit.setValue(cfg["max_changes"])
        v.addRow(self.row(self.clear_blank, QLabel("Background task stops above"), self.limit,
                          QLabel("people"), stretch=False))
        self.lay.addWidget(box)
        self.sched = ScheduleEdit("04:45", [])
        self.lay.addLayout(self.row(
            button("Save", slot=self.save), button("Preview changes", "primary", self.preview),
            button("Apply selected", slot=self.apply), stretch=False))
        self.lay.addWidget(QLabel("Keep the fields in step automatically:"))
        self.lay.addWidget(self.sched)
        self.lay.addLayout(self.row(button("Schedule the background task", slot=self.schedule)))
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.lay.addWidget(self.table, 1)
        self.sl = self.steps_list()
        self.lay.addWidget(self.sl)
        self.headers = []
        self.plan = []
        self._fill_grid(cfg["fields"])

    def _sources(self):
        from ... import field_check as fc
        return list(fc.PERSON_FIELDS.items()) + [(h, f"Column: {h}") for h in self.headers]

    def _fill_grid(self, fields: dict):
        from ... import custom_fields as cf, field_check as fc
        cols = [f"{s}.{f['name']}" for s, x in cf.config().get("schemas", {}).items()
                for f in x.get("fields", [])]
        self.grid.setRowCount(0)
        for col in cols:
            i = self.grid.rowCount()
            self.grid.insertRow(i)
            self.grid.setItem(i, 0, QTableWidgetItem(col))
            src = QComboBox()
            src.addItem("(don't fill)", "")
            for k, lab in self._sources():
                src.addItem(lab, k)
            want = (fields.get(col) or {})
            if want.get("source"):
                j = src.findData(want["source"])
                if j < 0:
                    src.addItem(f"Column: {want['source']}", want["source"])
                    j = src.count() - 1
                src.setCurrentIndex(j)
            fmt = QComboBox()
            for k, lab in fc.FORMATS.items():
                fmt.addItem(lab, k)
            fmt.setCurrentIndex(max(0, fmt.findData(want.get("format", "as is"))))
            self.grid.setCellWidget(i, 1, src)
            self.grid.setCellWidget(i, 2, fmt)
        if not cols:
            self.status.setText("Set up custom fields first (Settings → Custom user fields).")

    def _cfg(self) -> dict:
        fields = {}
        for i in range(self.grid.rowCount()):
            src = self.grid.cellWidget(i, 1).currentData()
            if src:
                fields[self.grid.item(i, 0).text()] = {
                    "source": src, "format": self.grid.cellWidget(i, 2).currentData()}
        return {"profile": self.profile.currentText(), "fields": fields,
                "clear_blank": self.clear_blank.isChecked(), "max_changes": self.limit.value(),
                "match_field": self.match.currentData() or ""}

    def save(self):
        from ... import field_check as fc
        fc.save_fill_config(self._cfg())
        self.status.setText("Saved.")

    def read_columns(self):
        from ... import field_check as fc
        name = self.profile.currentText()
        if not name:
            self.info("Save a roster sync first (People → Roster sync).")
            return
        keep = self._cfg()["fields"]

        def done(res):
            self.headers = list(res[3])
            self._fill_grid(keep)
            self.status.setText(f"{len(res[0])} people and {len(self.headers)} columns in "
                                "the roster.")
        _work(self.page, lambda: fc.roster(name), done, self.status, "Reading the roster…")

    def preview(self):
        from ... import field_check as fc
        cfg = self._cfg()
        if not cfg["profile"] or not cfg["fields"]:
            self.info("Pick the roster and at least one field to fill.")
            return
        fc.save_fill_config(cfg)

        def work():
            people, raws, root, headers = fc.roster(cfg["profile"])
            code, users, err = _csv()(fc.users_args(
                list(cfg["fields"]) + ([cfg["match_field"]] if cfg["match_field"] else []),
                root))
            if code != 0:
                raise RuntimeError("Couldn't read users: " + (err or "")[-200:])
            return fc.fill_plan(people, raws, users, cfg), headers

        def done(res):
            self.plan, headers = res
            if headers and not self.headers:
                self.headers = list(headers)
            fill(self.table, self.plan, ["email", "field", "old", "new"])
            n = len({c["email"] for c in self.plan})
            self.status.setText(f"{len(self.plan)} field change(s) for {n} people." if
                                self.plan else "Every field already matches the roster.")
        _work(self.page, work, done, self.status, "Reading the roster and users…")

    def apply(self):
        from ... import field_check as fc
        emails = {e.lower() for e in self.table.selected_values("email")}
        plan = [c for c in self.plan if c["email"].lower() in emails] if emails else []
        if not plan:
            self.info("Preview, then select the rows to apply (Ctrl+A for all).")
            return
        run_or_request(self.page, self.sl, fc.fill_commands(plan),
                       "Fill custom fields from the roster", "Custom fields from SIS",
                       lambda _s: self.preview())

    def schedule(self):
        from ... import field_check as fc, tasks_health
        from ..schedule_edit import task_for
        self.save()
        try:
            tasks_health.create(task_for(fc.FILL_TASK, self.sched.time_hhmm(),
                                         self.sched.days()))
            self.info("Scheduled. It shows on Automation → Schedules, and Home → Background "
                      "jobs says how each run went.")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Saved, but the task couldn't be created here:\n{exc}")


class FieldCheckPage(Page):
    title = "Custom field check"
    subtitle = ("Keep custom fields (grade, school, student ID…) right: compare them with "
                "the org unit map, and fill them from your roster.")

    def build(self):
        tabs = QTabWidget()
        tabs.addTab(FieldVsOUTab(self), "Field vs org unit")
        tabs.addTab(FillFromSISTab(self), "Fill from the SIS")
        self.body.addWidget(tabs, 1)


# ================================================ saved search → sheet ===
class SearchSheetDialog(QDialog):
    """Users → Find / list users → Google Sheet… for the chosen saved search."""

    def __init__(self, parent, fav: dict):
        super().__init__(parent)
        from ... import search_sheets as sh, saved_searches as ss
        from ...settings import settings
        self.fav = fav
        self.setWindowTitle(f"Google Sheet – {fav['label']}")
        self.resize(640, 380)
        v = QVBoxLayout(self)
        lab = QLabel(f"<b>{fav['label']}</b> – {ss.tooltip(fav)}<br>GAMbit runs this search "
                     "on a schedule (custom fields included) and rewrites one tab of the "
                     "sheet. The sheet keeps its link, sharing and formatting.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        form = QFormLayout()
        sheet = fav.get("sheet") or {}
        self.url = QLineEdit(sheet.get("url", ""))
        self.url.setPlaceholderText("blank = make a new sheet now")
        self.tab = QLineEdit(sheet.get("tab", "") or "GAMbit")
        self.on = QCheckBox("Refresh it on the schedule")
        self.on.setChecked(sheet.get("on", True))
        form.addRow("Sheet link", self.url)
        form.addRow("Tab", self.tab)
        form.addRow("", self.on)
        days = [d for d in (settings.get(sh.DAYS_KEY, "") or "").split(",") if d]
        self.sched = ScheduleEdit(settings.get(sh.TIME_KEY, "") or "05:30", days)
        form.addRow("All saved search sheets run", self.sched)
        last = sheet.get("last", "")
        self.state = QLabel((f"Last refreshed {last.replace('T', ' ')}" +
                             (f" – {sheet.get('last_rows', 0)} people" if not
                              sheet.get("error") else f" – failed: {sheet['error']}"))
                            if last else "Not refreshed yet.", objectName="Muted")
        self.state.setWordWrap(True)
        form.addRow("", self.state)
        v.addLayout(form)
        bb = QDialogButtonBox()
        self.now_btn = bb.addButton("Save && refresh now", QDialogButtonBox.AcceptRole)
        unlink = bb.addButton("Stop updating a sheet", QDialogButtonBox.DestructiveRole)
        bb.addButton(QDialogButtonBox.Cancel)
        self.now_btn.clicked.connect(self.save_now)
        unlink.clicked.connect(self.unlink)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def unlink(self):
        from ... import search_sheets as sh
        sh.set_sheet(self.fav["value"], None)
        self.accept()

    def save_now(self):
        from ... import search_sheets as sh
        url, tab = self.url.text().strip(), self.tab.text().strip() or "GAMbit"
        self.now_btn.setEnabled(False)
        self.state.setText("Running the search and writing the sheet…")
        fav = dict(self.fav)

        def work():
            link = url
            if not link:
                link = sh.create_sheet(fav)
                n = -1
            else:
                fav["sheet"] = {"url": link, "tab": tab}
                n = sh.refresh(fav)
            return link, n

        def done(res):
            link, n = res
            now = datetime.datetime.now().isoformat(timespec="minutes")
            sh.set_sheet(self.fav["value"], {"url": link, "tab": tab if url else "GAMbit",
                                             "on": self.on.isChecked(), "last": now,
                                             "error": "", **({"last_rows": n} if n >= 0 else {})})
            try:
                sh.schedule(self.sched.time_hhmm(), self.sched.days())
                sched = "The background task is scheduled (Automation → Schedules)."
            except Exception as exc:  # noqa: BLE001
                sched = f"Saved, but the background task couldn't be created here: {exc}"
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            if link.startswith("http"):
                QDesktopServices.openUrl(QUrl(link))
            self.parent().info(f"The sheet is up to date.\n{link}\n\n{sched}") \
                if hasattr(self.parent(), "info") else None
            self.accept()

        def bad(e):
            self.now_btn.setEnabled(True)
            self.state.setText(f"Failed: {e}")
        Worker(work, on_done=done, on_error=bad)


# ===================================================== Chromebook sharing ===
class SharingPage(Page):
    title = "Chromebook sharing"
    subtitle = ("From the people who signed in to each Chromebook recently: students on "
                "several Chromebooks, Chromebooks used by many students, and Chromebooks "
                "assigned to one student but used by another. Carts, loaners, labs and "
                "libraries are left out.")

    def build(self):
        self.ou = OUField(self.directory, "Chromebook org unit (blank = all)")
        self.recent = QSpinBox()
        self.recent.setRange(2, 10)
        self.recent.setValue(5)
        self.recent.setPrefix("look at the last ")
        self.recent.setSuffix(" users")
        self.many = QSpinBox()
        self.many.setRange(2, 10)
        self.many.setValue(3)
        self.many.setPrefix("“many” = ")
        self.many.setSuffix("+ students")
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(self.ou, self.recent, self.many,
                                     button("Find sharing", "primary", self.load),
                                     stretch=False))
        self.body.addWidget(self.status)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.body.addLayout(self.row(
            button("Make the last user the assigned user (selected swaps)", "primary",
                   self.assign),
            button("Open device history for the selected student", slot=self.history)))
        self.rows = []

    def load(self):
        from ... import device_insights as di, ou_map
        args = di.sharing_args(self.recent.value(), self.ou.path())
        users = self.directory.users

        def work():
            code, rows, err = _csv()(args)
            if code != 0:
                raise RuntimeError("Couldn't read Chromebooks: " + (err or "")[-200:])
            di.remember(rows)
            studs = {u["email"].lower() for u in users
                     if ou_map.is_student(u.get("ou", ""), self.directory.ous)} if users \
                else None
            return di.sharing(di.devices(rows), studs or None, self.many.value())

        def done(rows):
            self.rows = rows
            fill(self.table, rows, ["kind", "student", "serial", "asset", "assigned", "ou",
                                    "detail"])
            self.status.setText(f"{len(rows)} finding(s)." if rows else "No sharing found.")
        _work(self, work, done, self.status, "Reading Chromebooks and recent users…")

    def assign(self):
        from ... import device_insights as di
        serials = set(self.table.selected_values("serial"))
        rows = [r for r in self.rows if r["serial"] in serials and r["fix"] == "assign"]
        if not rows:
            self.info("Select rows of kind “Used by someone else”.")
            return
        run_or_request(self, _steps(self), di.assign_fix(rows),
                       "Assign Chromebooks to the student using them", "Chromebook sharing",
                       lambda _s: self.load())

    def history(self):
        st = self.table.selected_values("student")
        if st:
            self.app.go("Device history")
            p = self.app.pages.get("Device history")
            if p is not None:
                p.q.setText(st[0].split(",")[0].strip())
                p.show_history()


# ========================================================= device history ===
class DeviceHistoryPage(Page):
    title = "Device history"
    subtitle = ("Every Chromebook a student has had – or every student a Chromebook has had – "
                "with loaners, repairs and GAMbit's changes. Built up each time GAMbit reads "
                "the fleet, so it gets richer over time.")

    def build(self):
        self.q = QLineEdit(placeholderText="student email, serial number or asset ID")
        self.q.returnPressed.connect(self.show_history)
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(self.q, button("Show history", "primary",
                                                    self.show_history),
                                     button("Read the fleet now (adds today's picture)",
                                            slot=self.read_fleet), stretch=False))
        self.body.addWidget(self.status)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)

    def show_history(self):
        from ... import device_insights as di
        q = self.q.text().strip()
        if not q:
            self.info("Type a student's email, a serial number or an asset ID.")
            return

        def done(rows):
            fill(self.table, rows, ["date", "what", "serial", "asset", "detail", "source"])
            self.status.setText(f"{len(rows)} event(s) for {q}." if rows else
                                f"Nothing recorded for {q} yet. Click “Read the fleet now”, "
                                "or load Chromebook fleet – history builds up from there.")
        _work(self, lambda: di.history_for(q), done, self.status, "Collecting history…")

    def read_fleet(self):
        from ... import device_insights as di

        def work():
            code, rows, err = _csv()(di.sharing_args(5))
            if code != 0:
                raise RuntimeError("Couldn't read Chromebooks: " + (err or "")[-200:])
            return di.remember(rows), len(rows)

        def done(res):
            self.status.setText(f"Read {res[1]} Chromebooks – {res[0]} new event(s) saved.")
            if self.q.text().strip():
                self.show_history()
        _work(self, work, done, self.status, "Reading the fleet…")


# ========================================================= senior checkout ===
class SeniorCheckoutPage(Page):
    title = "Senior checkout"
    subtitle = ("End of year for a graduating class, from the graduation-year custom field "
                "(or an org unit): Takeout reminder, Chromebook collection, move to the "
                "graduates org unit, then suspend and free licenses later. Dated steps go to "
                "Run later & freezes.")

    def build(self):
        from ... import senior_checkout as sc
        d = sc.default_dates()
        box, form = self.group("The class")
        self.field = _field_combo()
        g = sc.guess_field()
        if g:
            self.field.setCurrentIndex(max(0, self.field.findData(g)))
        self.year = QLineEdit(d["year"])
        self.year.setMaximumWidth(90)
        self.ou = OUField(self.directory, "or seniors' org unit (optional with a field)")
        form.addRow("Graduation year field", self.row(self.field, QLabel("="), self.year,
                                                      stretch=False))
        form.addRow("Org unit", self.ou)
        form.addRow("", self.row(button("Find the class", "primary", self.load)))
        self.body.addWidget(box)
        box, form = self.group("Checklist")
        self.takeout = QCheckBox("Email each senior a Takeout reminder now")
        self.takeout.setChecked(True)
        self.collect = QCheckBox("Note their Chromebooks “Collect – Class of …” and start a "
                                 "collection (Chromebook fleet → Collections)")
        self.collect.setChecked(True)
        self.collect_by = _date(iso=d["collect_by"])
        self.grad_ou = OUField(self.directory, "/Graduates")
        self.grad_ou.set_path(sc.graduates_ou())
        self.move_on = _date(iso=d["move_on"])
        self.suspend = QCheckBox("Suspend on")
        self.suspend.setChecked(True)
        self.suspend_on = _date(iso=d["suspend_on"])
        self.sku = QLineEdit(placeholderText="license SKU to free, e.g. 1010310008 (optional)")
        form.addRow(self.takeout)
        form.addRow(self.row(self.collect, QLabel("Return by"), self.collect_by,
                             stretch=False))
        form.addRow("Move to", self.row(self.grad_ou, QLabel("on"), self.move_on,
                                        stretch=False))
        form.addRow(self.row(self.suspend, self.suspend_on, self.sku, stretch=False))
        form.addRow("", self.row(button("Review && run the checklist", "primary", self.go)))
        self.body.addWidget(box)
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addWidget(self.status)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.students, self.by_user = [], {}

    def load(self):
        from ... import saved_searches as ss, senior_checkout as sc
        field, year, ou = self.field.currentData(), self.year.text().strip(), self.ou.path()
        if not (field and year) and not ou:
            self.info("Pick the graduation-year field and the year, or the seniors' org unit.")
            return
        cmds, keep = sc.student_args(field if year else "", year, ou)

        def work():
            run = _csv()
            parts = []
            for c in cmds:
                code, rows, err = run(c)
                if code != 0:
                    raise RuntimeError("Couldn't read students: " + (err or "")[-200:])
                parts.append(rows)
            h, rows = ss.merge_rows(parts, keep)
            code, cros, _e = run(["print", "cros", "fields", "serialnumber,annotateduser,"
                                  "annotatedassetid,annotatedlocation,orgunitpath,status,"
                                  "recentusers", "listlimit", "1"])
            return h, rows, sc.devices_by_user(cros if code == 0 else [])

        def done(res):
            h, rows, self.by_user = res
            ix = {k.lower(): i for i, k in enumerate(h)}
            self.students = []
            out = []
            for r in rows:
                e = r[ix["primaryemail"]] if "primaryemail" in ix else ""
                if not e:
                    continue
                devs = self.by_user.get(e.lower(), [])
                self.students.append({"email": e})
                out.append({"email": e, "name": r[ix["name.fullname"]] if "name.fullname" in ix
                            else "", "ou": r[ix["orgunitpath"]] if "orgunitpath" in ix
                            else "", "chromebooks": ", ".join(d["serial"] for d in devs)})
            fill(self.table, out, ["email", "name", "ou", "chromebooks"])
            nd = sum(1 for x in out if x["chromebooks"])
            self.status.setText(f"{len(out)} senior(s), {nd} with an assigned Chromebook.")
        _work(self, work, done, self.status, "Finding the class and their Chromebooks…")

    def go(self):
        from ... import change_queue as cq, senior_checkout as sc, team
        if not self.students:
            self.info("Find the class first.")
            return
        sel = {e.lower() for e in self.table.selected_values("email")}
        studs = [s for s in self.students if s["email"].lower() in sel] or self.students
        o = {"year": self.year.text().strip(), "takeout": self.takeout.isChecked(),
             "collect_note": self.collect.isChecked(), "collect_by": _iso(self.collect_by),
             "grad_ou": self.grad_ou.path(), "move_on": _iso(self.move_on),
             "suspend_on": _iso(self.suspend_on) if self.suspend.isChecked() else "",
             "sku": self.sku.text().strip()}
        p = sc.plan(studs, self.by_user, o)
        later = "\n".join(f"• {w[:10]}: {t}" for w, t, _c in p["later"]) or "• (none)"
        if not self.confirm(f"Checklist for {len(studs)} senior(s):\n\nNow: {len(p['now'])} "
                            f"step(s) (emails and Chromebook notes)\n\nLater (Run later & "
                            f"freezes):\n{later}\n\nContinue?"):
            return
        try:
            for _w, _t, cmds in p["later"]:
                cq.check_can_queue(cmds)
            for when, title, cmds in p["later"]:
                cq.add(cmds, when, title, team.me())
        except (cq.QueueRefused, TimeoutError) as exc:
            self.info(str(exc))
            return
        if p["devices"] and o["collect_note"]:
            try:
                sc.start_collection(o["year"], p["devices"])
            except Exception as exc:  # noqa: BLE001
                self.info(f"Couldn't start the collection: {exc}")
        if p["now"]:
            run_or_request(self, _steps(self), p["now"], f"Class of {o['year']}: reminders "
                           "and Chromebook notes", "Senior checkout")
        else:
            self.info("The dated steps are on Automation → Run later & freezes.")


# ======================================================= clean-up by school ===
class SchoolCleanupPage(Page):
    title = "Clean-up by school"
    subtitle = ("One to-do list per building: accounts nobody uses, suspended accounts left "
                "in school org units, Chromebooks not seen in weeks, and Chromebooks "
                "assigned to suspended accounts – each with a fix. Email each school's list "
                "to its tech.")

    def build(self):
        from ... import school_cleanup as scu
        self.days = QSpinBox()
        self.days.setRange(14, 730)
        self.days.setValue(60)
        self.days.setPrefix("accounts idle ")
        self.days.setSuffix(" days")
        self.cdays = QSpinBox()
        self.cdays.setRange(7, 365)
        self.cdays.setValue(45)
        self.cdays.setPrefix("Chromebooks unseen ")
        self.cdays.setSuffix(" days")
        self.school = QComboBox()
        self.school.addItem("All schools", "")
        self.school.currentIndexChanged.connect(self._show)
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(self.days, self.cdays, button("Build the lists", "primary",
                                                                   self.load),
                                     QLabel("School"), self.school, stretch=False))
        self.body.addWidget(self.status)
        self.tabs = QTabWidget()
        self.summary = ResultsTable()
        self.table = ResultsTable()
        self.tabs.addTab(self.table, "To-do")
        self.tabs.addTab(self.summary, "By school")
        self.body.addWidget(self.tabs, 1)
        self.body.addLayout(self.row(button("Fix selected", "primary", self.fix),
                                     button("Email each school its list", slot=self.email)))
        self.contacts = QPlainTextEdit()
        self.contacts.setPlaceholderText("One per line: Hancock High School = tech@…")
        self.contacts.setMaximumHeight(70)
        self.contacts.setPlainText("\n".join(f"{k} = {v}" for k, v in scu.contacts().items()))
        self.body.addWidget(QLabel("School techs (for the emails):"))
        self.body.addWidget(self.contacts)
        self.rows = []

    def load(self):
        from ... import ou_map, school_cleanup as scu
        if not ou_map.configured():
            self.info("Set up Settings → Org units & schools first, so GAMbit knows which "
                      "org units belong to which school.")
            return
        days, cdays = self.days.value(), self.cdays.value()

        def work():
            run = _csv()
            c1, users, e1 = run(scu.USERS_ARGS)
            if c1 != 0:
                raise RuntimeError("Couldn't read users: " + (e1 or "")[-200:])
            c2, cros, _e2 = run(scu.CROS_ARGS)
            return scu.build(users, cros if c2 == 0 else [], days, cdays)

        def done(rows):
            self.rows = rows
            cur = self.school.currentData()
            self.school.blockSignals(True)
            self.school.clear()
            self.school.addItem("All schools", "")
            for s in sorted({r["school"] for r in rows}, key=str.lower):
                self.school.addItem(s, s)
            self.school.setCurrentIndex(max(0, self.school.findData(cur)))
            self.school.blockSignals(False)
            sm = scu.summary(rows)
            cols = ["school", "total"] + sorted({k for s in sm for k in s} - {"school",
                                                                                 "total"})
            fill(self.summary, sm, cols)
            self._show()
        _work(self, work, done, self.status, "Reading accounts and Chromebooks…")

    def _visible(self):
        s = self.school.currentData()
        return [r for r in self.rows if not s or r["school"] == s]

    def _show(self, *_):
        from ... import school_cleanup as scu
        rows = self._visible()
        fill(self.table, [{**r, "fix": scu.FIXES.get(r["fix"], r["fix"])} for r in rows],
             ["school", "problem", "item", "detail", "fix"])
        self.status.setText(f"{len(rows)} item(s)" + (f" at {self.school.currentData()}"
                                                      if self.school.currentData() else
                                                      f" across {self.school.count() - 1} "
                                                      "school(s)") + ".")

    def fix(self):
        from ... import school_cleanup as scu
        items = set(self.table.selected_values("item"))
        rows = [r for r in self._visible() if r["item"] in items]
        if not _need_rows(self, rows):
            return
        run_or_request(self, _steps(self), scu.commands(rows), "Clean-up by school",
                       "Clean-up by school", lambda _s: self.load())

    def email(self):
        from ... import google_io, school_cleanup as scu
        who = scu.save_contacts(self.contacts.toPlainText())
        if not self.rows:
            self.info("Build the lists first.")
            return
        by = {}
        for r in self.rows:
            by.setdefault(r["school"], []).append(r)
        targets = [(s, who[s], rs) for s, rs in by.items() if who.get(s)]
        if not targets:
            self.info("Type each school's tech below, like “Hancock High School = "
                      "tech@hancockschools.net”.")
            return
        if not self.confirm("Email:\n" + "\n".join(f"• {s} ({len(rs)} items) → {e}"
                                                   for s, e, rs in targets)):
            return
        steps = [(f"Email {s} list to {e}", google_io.email_args(
            e, f"GAMbit clean-up list – {s}", scu.email_text(s, rs)))
            for s, e, rs in targets]
        from ..steps import Step
        _steps(self).run([Step(lab, a) for lab, a in steps], lambda _s: self.info("Sent."))


__all__ = ["FieldCheckPage", "SharingPage", "DeviceHistoryPage", "SeniorCheckoutPage",
           "SchoolCleanupPage", "SearchSheetDialog"]
