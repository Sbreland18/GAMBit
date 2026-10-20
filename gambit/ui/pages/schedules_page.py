"""Automation → Schedules: every scheduled GAMbit job in one place – saved jobs you can edit,
duplicate, turn on/off and run, plus GAMbit's other background tasks (time, days, on/off)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QRadioButton,
    QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ... import saved_jobs
from ...settings import IS_WINDOWS
from ..pickers import OUField, OUMultiField
from ..schedule_edit import ScheduleEdit, describe
from ..widgets import Page, Worker, button

COLS = ["Name", "Type", "What it does", "When", "On", "Last run", "Next run", "Result"]
# which page owns each kind of built-in task (for “Open its page”)
OWNER = {"sync": "Roster sync", "daily": "Workflows", "groups": "Groups",
         "requests": "Approvals", "digest": "Settings & Updates", "devicesync": "Chromebook fleet",
         "devicemove": "Chromebook fleet", "deviceassign": "Chromebook fleet",
         "cleanup": "Clean-up rules", "classroomsync": "Classroom", "baseline":
         "Security baseline", "goingquiet": "Students going quiet", "timemachine":
         "Account time machine", "auditreport": "Audit report", "teacherlists": "Teacher lists",
         "schoolreports": "School reports", "scorecard": "Home", "watchdog": "Settings watch"}


def _task_key(args: list[str]) -> str:
    return args[args.index("--task") + 1] if "--task" in (args or []) else ""


# ================================================================ dialog ===
class JobDialog(QDialog):
    """Edit everything about one saved job."""

    def __init__(self, parent, directory, job: dict):
        super().__init__(parent)
        self.job = dict(job)
        self.d = directory
        o = dict(job.get("opts", {}))
        self.setWindowTitle(f"Scheduled job – {saved_jobs.KINDS[job['kind']]['label']}")
        self.resize(820, 720)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        f = QFormLayout(inner)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        self.name = QLineEdit(job["name"])
        f.addRow("Name", self.name)
        self.enabled = QCheckBox("On – run at the times below")
        self.enabled.setChecked(bool(job.get("enabled", True)))
        f.addRow("", self.enabled)
        self.when = ScheduleEdit(job.get("time") or "05:45", job.get("days"))
        f.addRow("When", self.when)
        self.all = QRadioButton("All Chromebooks")
        self.some = QRadioButton("Only these org units:")
        self.ous = OUMultiField(directory)
        self.ous.set_paths(job.get("scope_ous") or [])
        (self.some if job.get("scope_ous") else self.all).setChecked(True)
        self.ous.sub.hide()           # saved jobs always include the org units below
        h = QHBoxLayout()
        h.addWidget(self.all)
        h.addWidget(self.some)
        h.addStretch(1)
        f.addRow("Which Chromebooks", h)
        f.addRow("", self.ous)
        self.ous.setEnabled(self.some.isChecked())
        self.some.toggled.connect(self.ous.setEnabled)

        self.w: dict = {}
        if job["kind"] == "assigned":
            self._assigned_fields(f, o)
        else:
            self._move_fields(f, o)
        self.ignore = QLineEdit(o.get("ignore", ""))
        self.ignore.setPlaceholderText("never use these accounts, e.g. tech*, helpdesk@")
        f.addRow("Ignore", self.ignore)
        self.max_days = QSpinBox()
        self.max_days.setRange(0, 3650)
        self.max_days.setSpecialValueText("any time")
        self.max_days.setSuffix(" days")
        self.max_days.setValue(int(o.get("max_days", 0) or 0))
        f.addRow("Last sign-in within", self.max_days)

        row = QHBoxLayout()
        row.addWidget(button("Preview in Assigned users", slot=self.preview))
        row.addStretch(1)
        row.addWidget(button("Cancel", slot=self.reject))
        row.addWidget(button("Save", "primary", self.accept))
        outer.addLayout(row)
        self.want_preview = False

    def _assigned_fields(self, f, o):
        self.w["sched_stale"] = QCheckBox("Blank the assigned user when nobody has used the "
                                          "Chromebook in")
        self.w["sched_stale"].setChecked(bool(o.get("sched_stale")))
        self.w["stale_days"] = QSpinBox()
        self.w["stale_days"].setRange(1, 3650)
        self.w["stale_days"].setSuffix(" days")
        self.w["stale_days"].setValue(int(o.get("stale_days", 60) or 60))
        h = QHBoxLayout()
        h.addWidget(self.w["sched_stale"])
        h.addWidget(self.w["stale_days"])
        h.addStretch(1)
        f.addRow("Job", h)
        self.w["stale_never"] = QCheckBox("Also blank ones Google has no usage date for")
        self.w["stale_never"].setChecked(bool(o.get("stale_never")))
        f.addRow("", self.w["stale_never"])
        self.w["sched_set"] = QCheckBox("Set the assigned user to the student who last "
                                        "signed in")
        self.w["sched_set"].setChecked(bool(o.get("sched_set", True)))
        f.addRow("", self.w["sched_set"])
        self.w["blank_only"] = QComboBox()
        self.w["blank_only"].addItems(["Only where it's blank", "Also replace a different user"])
        self.w["blank_only"].setCurrentIndex(0 if o.get("blank_only", True) else 1)
        f.addRow("Setting", self.w["blank_only"])
        self.w["students_only"] = QCheckBox("Only students (Settings → Org units & schools)")
        self.w["students_only"].setChecked(bool(o.get("students_only", True)))
        f.addRow("", self.w["students_only"])

    def _move_fields(self, f, o):
        self.w["who"] = QComboBox()
        self.w["who"].addItem("the student who last signed in", "last")
        self.w["who"].addItem("the assigned user", "assigned")
        self.w["who"].setCurrentIndex(max(0, self.w["who"].findData(o.get("who", "last"))))
        f.addRow("Based on", self.w["who"])
        self.w["source"] = QComboBox()
        self.w["source"].addItem("the org unit map (Settings → Org units & schools)", "map")
        self.w["source"].addItem("a pattern with {school}", "pattern")
        self.w["source"].setCurrentIndex(max(0, self.w["source"].findData(
            o.get("source", "map"))))
        f.addRow("Chromebook org unit from", self.w["source"])
        self.w["student_root"] = OUField(self.d, "/Students")
        self.w["student_root"].set_path(o.get("student_root", "/Students"))
        f.addRow("Students are under", self.w["student_root"])
        self.w["school_depth"] = QSpinBox()
        self.w["school_depth"].setRange(1, 3)
        self.w["school_depth"].setValue(int(o.get("school_depth", 1) or 1))
        f.addRow("School = org-unit level", self.w["school_depth"])
        self.w["ou_template"] = QLineEdit(o.get("ou_template", "/Chromebooks/{school}"))
        f.addRow("Device org unit pattern", self.w["ou_template"])
        self.w["skip_ous"] = QLineEdit(o.get("skip_ous", ""))
        self.w["skip_ous"].setPlaceholderText("don't move devices in, e.g. /Chromebooks/Loaners")
        f.addRow("Don't move", self.w["skip_ous"])
        self.w["only_active"] = QCheckBox("Only active devices")
        self.w["only_active"].setChecked(bool(o.get("only_active", True)))
        f.addRow("", self.w["only_active"])

    def result_job(self) -> dict:
        o = dict(self.job.get("opts", {}))
        for k, w in self.w.items():
            if isinstance(w, QCheckBox):
                o[k] = w.isChecked()
            elif isinstance(w, QSpinBox):
                o[k] = w.value()
            elif isinstance(w, QComboBox):
                o[k] = (w.currentIndex() == 0) if k == "blank_only" else w.currentData()
            elif isinstance(w, OUField):
                o[k] = w.path() or "/Students"
            else:
                o[k] = w.text().strip()
        o["ignore"] = self.ignore.text().strip()
        o["max_days"] = self.max_days.value()
        return {**self.job, "name": self.name.text().strip() or self.job["name"],
                "enabled": self.enabled.isChecked(), "time": self.when.time_hhmm(),
                "days": self.when.days(), "opts": o,
                "scope_ous": self.ous.paths() if self.some.isChecked() else []}

    def preview(self):
        self.want_preview = True
        self.accept()

    def accept(self):
        if not self.when.days():
            QMessageBox.information(self, "Scheduled job", "Tick at least one day.")
            return
        if self.some.isChecked() and not self.ous.paths():
            QMessageBox.information(self, "Scheduled job", "Choose the org units, or pick "
                                    "All Chromebooks.")
            return
        if self.job["kind"] == "assigned" and not (self.w["sched_stale"].isChecked() or
                                                   self.w["sched_set"].isChecked()):
            QMessageBox.information(self, "Scheduled job", "Tick at least one job to do.")
            return
        super().accept()


# ================================================================== page ===
class SchedulesPage(Page):
    title = "Schedules"
    subtitle = ("Every job GAMbit runs on a schedule – your saved jobs and GAMbit's own "
                "background tasks. Edit, duplicate, turn on or off, change the time and days, "
                "or run one now. Jobs run through Windows Task Scheduler, so GAMbit doesn't "
                "need to be open.")

    def build(self):
        if not IS_WINDOWS:
            warn = QLabel("Schedules use Windows Task Scheduler. Saved jobs are kept here, but "
                          "they only run when GAMbit is installed on Windows.",
                          objectName="Banner")
            warn.setWordWrap(True)
            self.body.addWidget(warn)
        new = button("+ New job ▾", "primary")
        menu = QMenu(new)
        for kind, k in saved_jobs.KINDS.items():
            menu.addAction(k["label"], lambda kd=kind: self.new_job(kd))
        new.setMenu(menu)
        self.body.addLayout(self.row(
            new, button("Edit…", slot=self.edit), button("Duplicate", slot=self.duplicate),
            button("Turn on / off", slot=self.toggle),
            button("Change time && days…", slot=self.change_when),
            button("Run now", slot=self.run_now), button("Open its page", slot=self.open_page),
            button("Delete", "danger", self.delete), button("Refresh", slot=self.refresh)))
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for c, w in ((0, 260), (1, 150), (3, 170), (4, 50), (5, 140), (6, 140), (7, 90)):
            self.table.setColumnWidth(c, w)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        self.body.addWidget(self.table, 2)
        self.status = QLabel("", objectName="Muted")
        self.body.addWidget(self.status)
        self.body.addWidget(QLabel("Last run's log:"))
        self.log = QPlainTextEdit(readOnly=True)
        self.body.addWidget(self.log, 1)
        self.table.itemSelectionChanged.connect(self._show_log)
        self.rows: list[dict] = []

    def on_show(self):
        try:
            made = saved_jobs.migrate_legacy()
            if made:
                self.app.log_line("Moved your Assigned users schedules into saved jobs: " +
                                  ", ".join(j["name"] for j in made), "#7cc4ff")
        except Exception:  # noqa: BLE001
            pass
        self.refresh()

    # ------------------------------------------------------------ table ---
    def refresh(self):
        def load():
            from ... import tasks_health
            return tasks_health.rows()

        def done(task_rows):
            by_name = {r["name"]: r for r in task_rows}
            out = []
            for j in saved_jobs.jobs():
                t = by_name.pop(saved_jobs.task_name(j), {})
                out.append({"kind": "job", "job": j, "name": j["name"],
                            "type": "Saved job", "what": saved_jobs.describe(j),
                            "when": saved_jobs.when(j), "on": j.get("enabled", True),
                            "last": t.get("last") or (j.get("last_run") or "").replace("T", " "),
                            "next": t.get("next", ""), "result": self._result(t, j),
                            "task": saved_jobs.task_name(j), "log": t.get("log") or [],
                            "args": ["--task", "job", "--name", j["id"]]})
            for r in task_rows:
                if r.get("job_id") or r["name"] not in by_name or not r.get("scheduled"):
                    continue
                days = (r.get("days") or "MON").split(",") if r.get("freq") == "weekly" \
                    else []
                when = describe(r.get("time", ""), days) if r.get("freq") in (
                    "daily", "weekly") else (r.get("freq") or "")
                out.append({"kind": "task", "name": r["name"], "type": "GAMbit task",
                            "what": r.get("what", ""), "when": when,
                            "on": r.get("status", "").lower() != "disabled",
                            "last": r.get("last", ""), "next": r.get("next", ""),
                            "result": self._result(r, None), "task": r["name"],
                            "args": r.get("args") or [], "log": r.get("log") or []})
            self.rows = out
            self._fill()
        Worker(load, on_done=done, on_error=lambda e: (setattr(self, "rows", []),
                                                       self._fallback(str(e))))

    def _fallback(self, err: str):
        self.rows = [{"kind": "job", "job": j, "name": j["name"], "type": "Saved job",
                      "what": saved_jobs.describe(j), "when": saved_jobs.when(j),
                      "on": j.get("enabled", True), "last": "", "next": "", "result": "",
                      "task": saved_jobs.task_name(j),
                      "args": ["--task", "job", "--name", j["id"]]} for j in saved_jobs.jobs()]
        self._fill()
        self.status.setText(f"Couldn't read Windows Task Scheduler: {err}")

    @staticmethod
    def _result(t: dict, job: dict | None) -> str:
        if t.get("state") == "failed" or (job and job.get("last_code")):
            return "✖ failed"
        if t.get("state") == "ok":
            return "✔ ok"
        if not t.get("scheduled"):
            return "not scheduled" if not IS_WINDOWS or job else ""
        return "—"

    def _fill(self):
        self.table.setRowCount(0)
        for r in self.rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            vals = [r["name"], r["type"], r["what"], r["when"], "✔" if r["on"] else "off",
                    r["last"], r["next"], r["result"]]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setToolTip(str(v))
                if not r["on"]:
                    it.setForeground(Qt.gray)
                self.table.setItem(i, c, it)
        jobs = sum(1 for r in self.rows if r["kind"] == "job")
        self.status.setText(f"{jobs} saved job(s) · {len(self.rows) - jobs} other GAMbit "
                            "task(s). Double-click a saved job to edit it.")

    def _sel(self) -> dict | None:
        rows = {i.row() for i in self.table.selectedIndexes()}
        return self.rows[min(rows)] if rows and min(rows) < len(self.rows) else None

    def _show_log(self):
        r = self._sel()
        if not r:
            self.log.setPlainText("")
            return
        text = "\n".join(str(x).rstrip() for x in (r.get("log") or []))
        self.log.setPlainText(text or "(no log yet)")

    def _need(self, kind: str | None = None) -> dict | None:
        r = self._sel()
        if not r:
            self.info("Pick a row first.")
            return None
        if kind and r["kind"] != kind:
            self.info("That's one of GAMbit's own tasks – change it on its page "
                      "(Open its page), or use Change time & days / Turn on / off here.")
            return None
        return r

    # ---------------------------------------------------------- actions ---
    def new_job(self, kind: str):
        from ...tools import assigned_users as au
        base = au.options() if kind == "assigned" else au.move_options()
        job = {"id": "", "kind": kind, "name": saved_jobs.KINDS[kind]["label"],
               "enabled": True, "time": "05:45" if kind == "assigned" else "05:50",
               "days": ["MON", "TUE", "WED", "THU", "FRI"], "scope_ous": [],
               "opts": saved_jobs._clean(kind, base)}
        dlg = JobDialog(self, self.directory, job)
        if not dlg.exec():
            return
        r = dlg.result_job()
        made = saved_jobs.new(kind, r["name"], r["opts"], r["scope_ous"], r["time"],
                              r["days"], r["enabled"])
        self._schedule(made)
        if dlg.want_preview:
            self._preview(made)

    def edit(self):
        r = self._need("job")
        if not r:
            return
        old_task = saved_jobs.task_name(r["job"])
        dlg = JobDialog(self, self.directory, r["job"])
        if not dlg.exec():
            return
        job = saved_jobs.update(dlg.result_job())
        self._schedule(job, old_task)
        if dlg.want_preview:
            self._preview(job)

    def _schedule(self, job: dict, old_task: str = ""):
        try:
            saved_jobs.schedule(job, old_task)
            self.app.statusBar().showMessage(
                f"Saved “{job['name']}” – {saved_jobs.when(job)}"
                + ("" if job.get("enabled", True) else " (turned off)"), 6000)
        except Exception as exc:  # noqa: BLE001
            if IS_WINDOWS:
                self.info(f"Saved “{job['name']}”, but Windows didn't accept the schedule:"
                          f"\n{exc}")
            else:
                self.app.statusBar().showMessage(
                    f"Saved “{job['name']}” – it's scheduled when GAMbit runs on Windows.",
                    6000)
        self.refresh()

    def _preview(self, job: dict):
        from .insight_pages import goto
        page = goto(self.app, "Chromebook fleet", "Assigned users")
        tab = getattr(page, "assigned_tab", None)
        if tab is not None:
            tab.load_job(job)

    def duplicate(self):
        r = self._need("job")
        if r:
            j = saved_jobs.duplicate(r["job"]["id"])
            self._schedule(j)
            self.info(f"Made “{j['name']}” (turned off). Edit it – for example to pick "
                      "other org units – then turn it on.")

    def toggle(self):
        r = self._need()
        if not r:
            return
        on = not r["on"]
        from ... import scheduler
        try:
            if r["kind"] == "job":
                job = saved_jobs.update({**r["job"], "enabled": on})
                if IS_WINDOWS:
                    try:
                        scheduler.set_enabled(saved_jobs.task_name(job), on)
                    except Exception:  # noqa: BLE001 – not scheduled yet: schedule it now
                        saved_jobs.schedule(job)
            else:
                scheduler.set_enabled(r["task"], on)
            self.app.statusBar().showMessage(f"{r['name']}: {'on' if on else 'off'}", 5000)
        except Exception as exc:  # noqa: BLE001
            self.info(f"Couldn't change it: {exc}")
        self.refresh()

    def change_when(self):
        r = self._need()
        if not r:
            return
        if r["kind"] == "job":
            self.edit()
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"When – {r['name']}")
        v = QVBoxLayout(dlg)
        t = r["when"]
        ed = ScheduleEdit("05:45")
        import re
        m = re.search(r"(\d{1,2}):(\d\d) (AM|PM)", t)
        if m:
            hh = int(m.group(1)) % 12 + (12 if m.group(3) == "PM" else 0)
            ed.set(f"{hh:02d}:{m.group(2)}", ed.days())
        v.addWidget(QLabel(f"Now: {t}"))
        v.addWidget(ed)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Cancel", slot=dlg.reject))
        row.addWidget(button("Save", "primary", dlg.accept))
        v.addLayout(row)
        if not dlg.exec():
            return
        from ... import scheduler
        try:
            scheduler.set_schedule(r["task"], ed.time_hhmm(), ed.days())
            self.app.statusBar().showMessage(f"{r['name']}: {ed.text()}", 6000)
        except Exception as exc:  # noqa: BLE001
            self.info(f"Couldn't change it: {exc}")
        self.refresh()

    def run_now(self):
        r = self._need()
        if not r or not r["args"]:
            if r:
                self.info("This task runs a template – run it from Scheduled jobs.")
            return
        if not self.confirm(f"Run “{r['name']}” now, here?"):
            return
        self.status.setText(f"Running {r['name']}…")
        lines: list[str] = []

        def work(log=None):
            if r["kind"] == "job":
                return saved_jobs.run(r["job"]["id"], log=log, force=True)
            from ... import tasks_health
            return tasks_health.run_here(r["args"])

        def done(code):
            self.log.setPlainText("\n".join(lines) or "(finished)")
            self.status.setText(f"{r['name']}: {'✔ done' if code == 0 else '✖ see the log'}")
            self.refresh()
        Worker(work, on_done=done, on_message=lines.append, use_log=True,
               on_error=lambda e: self.status.setText(f"✖ {e}"))

    def open_page(self):
        r = self._need()
        if not r:
            return
        from .insight_pages import goto
        if r["kind"] == "job":
            k = saved_jobs.KINDS[r["job"]["kind"]]
            goto(self.app, k["page"], k["tab"])
        else:
            goto(self.app, OWNER.get(_task_key(r["args"]), "Background tasks"))

    def delete(self):
        r = self._need()
        if not r or not self.confirm(f"Delete “{r['name']}”? It stops running."):
            return
        from ... import scheduler
        if r["kind"] == "job":
            saved_jobs.unschedule(r["job"])
            saved_jobs.remove(r["job"]["id"])
        else:
            try:
                scheduler.delete_task(r["task"])
            except Exception as exc:  # noqa: BLE001
                self.info(f"Couldn't delete it: {exc}")
        self.refresh()

