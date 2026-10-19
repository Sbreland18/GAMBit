"""Dialog: run a saved roster sync every night with Windows Task Scheduler."""

from __future__ import annotations

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QSpinBox,
    QTimeEdit, QVBoxLayout,
)

from ... import profiles, scheduler, team
from ...settings import settings


class ScheduleDialog(QDialog):
    def __init__(self, parent, name: str, opts: dict):
        super().__init__(parent)
        self.name = name
        self.setWindowTitle(f"Schedule “{name}”")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        intro = QLabel("GAMbit will run this sync every day with nobody at the PC. Safe "
                       "changes are applied automatically; anyone leaving becomes one request "
                       "on the Approvals page" + ("" if team.folder() else
                                                  " (set a team folder for that – without "
                                                  "one they're only listed in the email)") +
                       ". If the roster looks broken (far more new or leaving people than "
                       "usual), nothing is applied and you get an alert.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        self.time = QTimeEdit(QTime.fromString(opts.get("time", "05:30"), "HH:mm"))
        self.time.setDisplayFormat("h:mm AP")
        form.addRow("Every day at", self.time)
        apply = set(opts.get("apply", ["create", "update", "reactivate"]))
        self.a_create = QCheckBox("Create new accounts")
        self.a_update = QCheckBox("Apply updates (moves, names, job details)")
        self.a_back = QCheckBox("Unsuspend people who are back")
        for cb, key in ((self.a_create, "create"), (self.a_update, "update"),
                        (self.a_back, "reactivate")):
            cb.setChecked(key in apply)
            form.addRow("" if key != "create" else "Apply automatically", cb)
        self.max_new = QSpinBox()
        self.max_new.setRange(1, 100000)
        self.max_new.setValue(int(opts.get("max_new", 200)))
        form.addRow("Stop if more new accounts than", self.max_new)
        self.email_to = QLineEdit(opts.get("email_to", settings.get("alerts/email", "") or ""))
        self.email_to.setPlaceholderText("tech@yourschool.org")
        form.addRow("Email the summary to", self.email_to)
        self.email_pw = QCheckBox("Attach new accounts' temporary passwords (CSV)")
        self.email_pw.setChecked(bool(opts.get("email_passwords", False)))
        form.addRow("", self.email_pw)
        note = QLabel("Passwords and printable cards are always saved in your reports "
                      "folder → Roster sync.", objectName="Muted")
        note.setWordWrap(True)
        form.addRow("", note)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def result_opts(self) -> dict:
        apply = [k for cb, k in ((self.a_create, "create"), (self.a_update, "update"),
                                 (self.a_back, "reactivate")) if cb.isChecked()]
        return {"time": self.time.time().toString("HH:mm"), "apply": apply,
                "max_new": self.max_new.value(), "email_to": self.email_to.text().strip(),
                "email_passwords": self.email_pw.isChecked(),
                "domain_profile": profiles.current_name()}

    def task_name(self) -> str:
        return f"Roster sync - {scheduler.slug(self.name)}"

    def create_task(self):
        script = scheduler.build_app_task_script(self.task_name(),
                                                 ["--task", "sync", "--name", self.name])
        scheduler.create_task(self.task_name(), script, "daily",
                              self.time.time().toString("HH:mm"))
