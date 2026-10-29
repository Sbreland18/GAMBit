"""Server kit: run GAMbit's background tasks from an always-on PC or server instead of a
laptop. Makes a folder with a deployment file, a PowerShell script that registers the
tasks under a service account, and step-by-step instructions."""

from __future__ import annotations

import json
import re
import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel, QLineEdit,
    QVBoxLayout,
)

from .. import deploy, tasks_health
from .widgets import button

README = """GAMbit server kit
=================

Runs GAMbit's background tasks on an always-on Windows PC or server, under one Windows
account, whether or not anyone is signed in.

1. Install GAMbit on the server. Run the installer and choose "Install for all users"
   (or use your usual software deployment). GAM must be installed too (GAMbit's Setup
   wizard can install it).

2. GAM's sign-in. The tasks run as {account}. That account needs a working GAM setup:
   - easiest: sign in to the server as {account} once, open GAMbit and finish the Setup
     wizard (or "Use the shared project on this PC" in Settings → Rolling out), or
   - point it at a GAM config folder that already works (Settings → GAM config folder)
     and make sure {account} can read it.

3. Copy this folder to the server and run, in an elevated PowerShell:
       powershell -ExecutionPolicy Bypass -File install-tasks.ps1
   It copies gambit-deploy.json to C:\\ProgramData\\GAMbit\\ (GAMbit applies it the
   first time a task runs) and registers the tasks under \\GAMbit\\ in Task Scheduler.
   You'll be asked for {account}'s password.

4. On the server, open Task Scheduler → GAMbit and "Run" one task to test it. The log is
   in %APPDATA%\\GAMbit\\logs\\tasks.log of {account} (GAMbit → Background tasks shows it
   when you sign in as that account).

5. Turn the same tasks off on your own PC (GAMbit → Background tasks → Remove) so they
   don't run twice.

Tasks included:
{tasks}
"""


def ps1(exe: str, account: str, tasks: list[dict]) -> str:
    def q(v: str) -> str:              # a PowerShell single-quoted string
        return "'" + str(v).replace("\r", " ").replace("\n", " ").replace("'", "''") + "'"
    lines = [
        "# GAMbit server kit – registers GAMbit's background tasks (run as administrator)",
        "$ErrorActionPreference = 'Stop'",
        f"$Exe = {q(exe)}",
        f"$Account = {q(account)}",
        "if (-not (Test-Path $Exe)) { throw \"GAMbit isn't at $Exe – edit `$Exe at the top "
        "of this script.\" }",
        "$Here = Split-Path -Parent $MyInvocation.MyCommand.Path",
        "New-Item -ItemType Directory -Force -Path \"$env:ProgramData\\GAMbit\" | Out-Null",
        "Copy-Item -Force (Join-Path $Here 'gambit-deploy.json') "
        "\"$env:ProgramData\\GAMbit\\gambit-deploy.json\"",
        "# only administrators may change the settings file the tasks read",
        "icacls \"$env:ProgramData\\GAMbit\\gambit-deploy.json\" /inheritance:r /grant:r "
        "'*S-1-5-32-544:F' '*S-1-5-18:F' '*S-1-5-32-545:R' | Out-Null",
        "$Cred = Get-Credential -UserName $Account -Message 'Password for the account the "
        "GAMbit tasks run as'",
        "$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit "
        "(New-TimeSpan -Hours 4) -MultipleInstances IgnoreNew",
        "",
    ]
    for t in tasks:
        arg = " ".join(f'"{a}"' if " " in a else a for a in t["args"]).replace("'", "''")
        hh, mm = (t.get("time") or "06:00").split(":")
        at = f"{int(hh):02d}:{mm}"
        if t["freq"] == "weekly":
            trig = f"New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At '{at}'"
        elif t["freq"] == "every15":
            trig = (f"New-ScheduledTaskTrigger -Once -At '{at}' -RepetitionInterval "
                    "(New-TimeSpan -Minutes 15)")
        else:
            trig = f"New-ScheduledTaskTrigger -Daily -At '{at}'"
        name = t["name"].replace("'", "''")
        lines += [
            "# " + re.sub(r"[\r\n]+", " ", str(t["what"])),
            f"$Action = New-ScheduledTaskAction -Execute $Exe -Argument '{arg}'",
            f"Register-ScheduledTask -TaskPath '\\GAMbit\\' -TaskName '{name}' -Action $Action "
            f"-Trigger ({trig}) -Settings $Settings -User $Cred.UserName "
            "-Password $Cred.GetNetworkCredential().Password -RunLevel Limited -Force | Out-Null",
            f"Write-Host 'Registered {name}'",
            "",
        ]
    lines.append("Write-Host 'Done. Open Task Scheduler → GAMbit to test a task.'")
    return "\r\n".join(lines) + "\r\n"


class ServerKitDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Server kit")
        self.resize(640, 520)
        lay = QVBoxLayout(self)
        intro = QLabel("Run the background tasks from an always-on PC or server, so they don't "
                       "stop when a laptop is closed. GAMbit makes a folder with everything "
                       "needed: a deployment file with this PC's settings, a PowerShell script "
                       "that registers the tasks under a service account, and instructions.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        self.account = QLineEdit(placeholderText=r"e.g. HANCOCK\svc-gambit")
        self.exe = QLineEdit(r"C:\Program Files\GAMbit\GAMbit.exe")
        form.addRow("Run tasks as", self.account)
        form.addRow("GAMbit on the server", self.exe)
        lay.addLayout(form)
        lay.addWidget(QLabel("Tasks to include:"))
        self.boxes = []
        for d in tasks_health.rows():
            if not d["args"]:
                continue
            cb = QCheckBox(f"{d['name']} – {d['what']}")
            cb.setChecked(d["standard"] or "Roster sync" in d["name"])
            cb.setProperty("task", d)
            self.boxes.append(cb)
            lay.addWidget(cb)
        note = QLabel("Scheduled report jobs (from Tools → Scheduled jobs) are .cmd scripts on "
                      "this PC – recreate them on the server from the same templates.",
                      objectName="Muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)
        bb = QDialogButtonBox()
        bb.addButton(button("Make the kit…", "primary", self.make), QDialogButtonBox.AcceptRole)
        bb.addButton(QDialogButtonBox.Cancel)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def make(self):
        account = self.account.text().strip()
        if not account:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Server kit", "Type the Windows account the tasks "
                                    "should run as.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Where should the kit go?")
        if not folder:
            return
        out = os.path.join(folder, "GAMbit server kit")
        os.makedirs(out, exist_ok=True)
        tasks = [cb.property("task") for cb in self.boxes if cb.isChecked()]
        data = deploy.build_deploy([g for g in deploy.GROUPS if g != "helpdesk"], overwrite=True,
                                   note=f"server kit – tasks run as {account}")
        with open(os.path.join(out, "gambit-deploy.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        with open(os.path.join(out, "install-tasks.ps1"), "w", encoding="utf-8-sig") as fh:
            fh.write(ps1(self.exe.text().strip(), account, tasks))
        with open(os.path.join(out, "README.txt"), "w", encoding="utf-8") as fh:
            fh.write(README.format(account=account, tasks="\n".join(
                f"  - {t['name']}: {t['what']}" for t in tasks)))
        QDesktopServices.openUrl(QUrl.fromLocalFile(out))
        self.accept()
