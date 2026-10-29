"""Background tasks: are the nightly jobs actually running?"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QPlainTextEdit, QTableWidget, QTableWidgetItem,
)

from ... import scheduler, tasks_health
from ...settings import IS_WINDOWS, settings
from ..widgets import Page, Worker, button

LOOK = {"ok": ("✔ Working", "#137333"), "failed": ("✖ Failed", "#b42318"),
        "never run": ("○ Not run yet", "#57606a"), "not scheduled": ("– Not set up", "#9a6700")}


class TasksPage(Page):
    title = "Background tasks"
    subtitle = ("Everything GAMbit runs with nobody at the PC – roster syncs, offboarding "
                "follow-ups, automatic groups, staff requests, the digest and scheduled reports "
                "– with when it last ran and whether it worked.")

    def build(self):
        if not IS_WINDOWS:
            warn = QLabel("Background tasks use Windows Task Scheduler, so this list is only "
                          "complete on Windows.", objectName="Banner")
            warn.setWordWrap(True)
            self.body.addWidget(warn)
        how = QLabel(
            "<b>Do I need to leave GAMbit open?</b> No. Every scheduled job is a Windows Task "
            "Scheduler task that starts its own copy of GAMbit with no window, does the job "
            "and exits – so it runs whether GAMbit is open, minimized or closed. What it "
            "does need: this PC turned on and you signed in to Windows (a locked screen is "
            "fine; signing out stops them). A job missed because the PC was asleep or off "
            "runs as soon as the PC is back, and jobs run on battery too. For jobs that must "
            "never be missed, use an always-on PC (see <i>Server kit…</i>).")
        how.setWordWrap(True)
        how.setObjectName("Banner")
        self.body.addWidget(how)
        from PySide6.QtWidgets import QCheckBox
        from ...settings import settings as _st
        self.wake = QCheckBox("Wake this PC from sleep to run scheduled jobs")
        self.wake.setChecked(bool(_st.get("tasks/wake", False)))
        self.wake.toggled.connect(self._wake_changed)
        self.body.addLayout(self.row(self.wake, stretch=True))
        self.body.addLayout(self.row(
            button("Refresh", slot=self.refresh),
            button("Set up the standard tasks", "primary", self.setup_missing),
            button("Run now (Task Scheduler)", slot=self.run_now),
            button("Run here now", slot=self.run_here),
            button("Remove", "danger", self.remove),
            button("Open the task log", slot=self.open_log),
            button("Server kit…", slot=self.server_kit)))
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Task", "What it does", "Status", "Last run",
                                              "Next run", "Schedule"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for c, w in ((0, 240), (2, 120), (3, 150), (4, 150), (5, 110)):
            self.table.setColumnWidth(c, w)
        self.table.itemSelectionChanged.connect(self._show_log)
        self.body.addWidget(self.table, 2)
        self.body.addWidget(QLabel("Last run's log:"))
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setStyleSheet("font-family:Consolas,'Cascadia Mono',monospace;")
        self.body.addWidget(self.log, 1)
        self.items: list[dict] = []

    def on_show(self):
        self.refresh()

    def refresh(self):
        def done(items):
            self.items = items
            self.table.setRowCount(0)
            for d in items:
                r = self.table.rowCount()
                self.table.insertRow(r)
                label, color = LOOK.get(d["state"], (d["state"], "#57606a"))
                if d["freq"] == "weekly":
                    from ..schedule_edit import describe
                    sched = describe(d["time"], (d.get("days") or "MON").split(","))
                else:
                    sched = {"daily": f"daily {d['time']}",
                             "every15": "every 15 min"}.get(d["freq"], d["freq"])
                for c, v in enumerate([d["name"], d["what"], label, d["last"], d["next"],
                                       sched]):
                    it = QTableWidgetItem(v)
                    it.setToolTip(v)
                    if c == 2:
                        it.setForeground(QColor(color))
                    if c == 0:
                        it.setData(Qt.UserRole, d)
                    self.table.setItem(r, c, it)
            self._show_log()
        Worker(tasks_health.rows, on_done=done, on_error=lambda e: self.info(str(e)))

    def _sel(self) -> list[dict]:
        return [self.table.item(r, 0).data(Qt.UserRole)
                for r in sorted({i.row() for i in self.table.selectedIndexes()})]

    def _show_log(self):
        sel = self._sel()
        self.log.setPlainText("\n".join(sel[0]["log"]) if sel and sel[0]["log"] else
                              ("(nothing logged yet)" if sel else ""))

    def setup_missing(self):
        missing = [d for d in self.items if d.get("standard") and not d["scheduled"]]
        if not missing:
            self.info("The standard tasks are already set up.")
            return
        if not self.confirm("Set up these tasks on this PC?\n\n" +
                            "\n".join(f"• {d['name']} – {d['what']}" for d in missing) +
                            "\n\nThey run while this PC is on and you're signed in. For an "
                            "always-on server, use “Server kit…”."):
            return
        errs = []
        for d in missing:
            try:
                tasks_health.create(d)
            except Exception as exc:  # noqa: BLE001
                errs.append(f"{d['name']}: {exc}")
        if errs:
            self.info("Some tasks couldn't be created:\n\n" + "\n".join(errs))
        self.refresh()

    def run_now(self):
        for d in self._sel():
            if not d["scheduled"]:
                self.info(f"“{d['name']}” isn't scheduled on this PC – use Run here now.")
                continue
            try:
                scheduler.run_now(d["name"])
            except Exception as exc:  # noqa: BLE001
                self.info(str(exc))
        self.refresh()

    def run_here(self):
        sel = [d for d in self._sel() if d["args"]]
        if not sel:
            self.info("Select a GAMbit task (scheduled report jobs run from Task Scheduler).")
            return
        d = sel[0]
        from ... import user_prefs
        if settings.get("safety/dry_run", False) or user_prefs.practice_on():
            self.info("Dry run or Practice mode is on. Background tasks make real changes, so "
                      "they don't run from here until both are off.")
            return
        if not self.confirm(f"Run “{d['name']}” now, inside GAMbit?"):
            return
        self.log.setPlainText("Running…")
        Worker(tasks_health.run_here, d["args"],
               on_done=lambda code: (self.refresh(), self.app.log_line(
                   f"Background task “{d['name']}” finished "
                   f"({'OK' if code == 0 else 'with problems'}).")),
               on_error=lambda e: self.info(str(e)))

    def remove(self):
        sel = [d for d in self._sel() if d["scheduled"]]
        if sel and self.confirm("Remove from Task Scheduler?\n\n" +
                                "\n".join(d["name"] for d in sel)):
            for d in sel:
                try:
                    scheduler.delete_task(d["name"])
                except Exception as exc:  # noqa: BLE001
                    self.info(str(exc))
            self.refresh()

    def open_log(self):
        p = tasks_health._log_path()
        if not os.path.exists(p):
            open(p, "a").close()
        QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def server_kit(self):
        from ..server_kit import ServerKitDialog
        ServerKitDialog(self).exec()

    def _wake_changed(self, on: bool):
        from ... import scheduler
        from ...settings import settings as _st
        _st.set("tasks/wake", bool(on))
        n = scheduler.tune_all()
        self.app.statusBar().showMessage(
            f"Updated {n} scheduled job(s)." if n else "Saved – it applies to jobs as "
            "they're scheduled.", 5000)
