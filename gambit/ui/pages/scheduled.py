"""Scheduled jobs: run a saved template on a schedule with Windows Task Scheduler."""

from __future__ import annotations

import os

from PySide6.QtCore import QTime, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QTimeEdit,
)

from ... import builder_store, scheduler
from ...settings import IS_WINDOWS, settings
from ..widgets import Page, ResultsTable, Worker, button

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


class ScheduledPage(Page):
    title = "Scheduled jobs"
    subtitle = ("Run a saved template automatically – for example a weekly inactive-accounts "
                "report emailed to principals, or a nightly cleanup. Results are saved as CSV "
                "files, and you can get an email if a job fails.")

    def build(self):
        if not IS_WINDOWS:
            warn = QLabel("Scheduled jobs use Windows Task Scheduler, so they only work when "
                          "GAMbit runs on Windows.", objectName="Banner")
            warn.setWordWrap(True)
            self.body.addWidget(warn)

        box, form = self.group("New scheduled job")
        self.tpl = QComboBox()
        self.tpl.setMinimumWidth(340)
        form.addRow("Template", self.row(self.tpl, button("Manage templates…",
                                                          slot=lambda: self.app.go(
                                                              "Command Builder"))))
        self.freq = QComboBox()
        for label, val in (("Every day", "daily"), ("Every week", "weekly"),
                           ("Every month", "monthly"), ("Once", "once")):
            self.freq.addItem(label, val)
        self.freq.currentIndexChanged.connect(self._freq)
        self.time = QTimeEdit(QTime(6, 30))
        self.time.setDisplayFormat("h:mm AP")
        form.addRow("How often", self.row(self.freq, QLabel("at"), self.time))
        self.days = []
        drow = QHBoxLayout()
        for d in DAYS:
            cb = QCheckBox(d.title())
            cb.setChecked(d == "MON")
            self.days.append(cb)
            drow.addWidget(cb)
        drow.addStretch(1)
        form.addRow("On", drow)
        self.dom = QSpinBox()
        self.dom.setRange(1, 28)
        form.addRow("Day of month", self.row(self.dom))
        self.out = QLineEdit(settings.get("schedule/out", "") or scheduler.default_output_dir())
        form.addRow("Save results in", self.row(self.out, button("Browse…", slot=self._browse),
                                                stretch=False))
        self.email_to = QLineEdit(settings.get("schedule/email_to", "") or "")
        self.email_to.setPlaceholderText("Optional – e.g. principal@yourschool.org, "
                                         "office@yourschool.org")
        self.email_when = QComboBox()
        self.email_when.addItem("only when there's something in the report", "rows")
        self.email_when.addItem("every time", "always")
        form.addRow("Email the results to", self.row(self.email_to, self.email_when,
                                                     stretch=False))
        self.alert = QCheckBox("Email me if a step fails")
        self.alert.setChecked(bool(settings.get("schedule/alert", True)))
        self.alert_to = QLineEdit(settings.get("alerts/email", "") or "")
        self.alert_to.setPlaceholderText("tech@yourschool.org")
        form.addRow("", self.row(self.alert, self.alert_to, stretch=False))
        form.addRow("", self.row(button("Create scheduled job", "primary", self.create)))
        note = QLabel("Jobs run as you, while you're signed in to Windows, using the GAM "
                      "settings GAMbit is using right now (including the current domain "
                      "profile).", objectName="Muted")
        note.setWordWrap(True)
        form.addRow("", note)
        self.body.addWidget(box)

        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.body.addLayout(self.row(
            button("Refresh", slot=self.refresh),
            button("Run selected now", slot=self.run_now),
            button("Delete selected", "danger", self.delete),
            button("Open results folder", slot=lambda: self._open(self.out.text())),
            button("Open scripts folder", slot=lambda: self._open(scheduler.scripts_dir()))))
        self._freq()

    def on_show(self):
        self._templates()
        self.refresh()

    def prefill(self, template_name: str):
        self._templates()
        i = self.tpl.findText(template_name)
        if i >= 0:
            self.tpl.setCurrentIndex(i)

    def _templates(self):
        cur = self.tpl.currentText()
        self.tpl.clear()
        for t in builder_store.templates():
            self.tpl.addItem(t["name"], t)
        if cur:
            i = self.tpl.findText(cur)
            if i >= 0:
                self.tpl.setCurrentIndex(i)

    def _freq(self):
        f = self.freq.currentData()
        for cb in self.days:
            cb.setEnabled(f == "weekly")
        self.dom.setEnabled(f == "monthly")

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Save results in", self.out.text())
        if d:
            self.out.setText(os.path.normpath(d))

    @staticmethod
    def _open(path):
        os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def refresh(self):
        def done(rows):
            heads = ["Name", "Schedule", "Next run", "Last run", "Last result", "Status"]
            self.table.set_rows(heads, [[r.get(h, "") for h in heads] for r in rows])
        Worker(scheduler.list_tasks, on_done=done)

    def create(self):
        t = self.tpl.currentData()
        if not t:
            self.info("Save a template in the Command Builder first (Templates tab).")
            return
        lines = builder_store.template_lines(t)
        if not lines:
            self.info("That template has no commands.")
            return
        out = self.out.text().strip()
        settings.set("schedule/out", out)
        from ... import google_io
        email_to = self.email_to.text().strip()
        alert_to = self.alert_to.text().strip() if self.alert.isChecked() else ""
        settings.set("schedule/email_to", email_to)
        settings.set("schedule/alert", self.alert.isChecked())
        if alert_to:
            settings.set("alerts/email", alert_to)
        if (email_to or alert_to) and not google_io.admin_email():
            self.info("Set the Google account GAMbit sends email from in Settings & Updates → "
                      "Google Sheets and email first.")
            return
        if self.alert.isChecked() and "@" not in alert_to:
            self.info("Type the address failure alerts should go to.")
            return
        days = ",".join(d for d, cb in zip(DAYS, self.days) if cb.isChecked()) or "MON"
        try:
            from ... import alerts
            script = scheduler.build_script(t["name"], lines, out, email_to,
                                            self.email_when.currentData(), alert_to,
                                            google_io.admin_email(), alerts.webhook_url())
            scheduler.create_task(t["name"], script, self.freq.currentData(),
                                  self.time.time().toString("HH:mm"), days, self.dom.value())
        except Exception as exc:  # noqa: BLE001
            self.info(f"Couldn't create the scheduled job:\n\n{exc}\n\nThe script was saved "
                      f"in the scripts folder, so you can schedule it yourself.")
            return
        self.info(f"Scheduled “{t['name']}”. Results will be saved in:\n{out}")
        self.refresh()

    def _sel(self):
        names = self.table.selected_values("Name")
        if not names:
            self.info("Select a job in the list.")
        return names

    def run_now(self):
        for n in self._sel():
            try:
                scheduler.run_now(n)
            except Exception as exc:  # noqa: BLE001
                self.info(str(exc))
        self.refresh()

    def delete(self):
        names = self._sel()
        if names and self.confirm(f"Delete {len(names)} scheduled job(s)?"):
            for n in names:
                try:
                    scheduler.delete_task(n)
                except Exception as exc:  # noqa: BLE001
                    self.info(str(exc))
            self.refresh()
