"""Chromebook fleet → Assignment sync;  Automation → Clean-up rules page."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel,
    QLineEdit, QSpinBox,
)

from ...settings import settings
from ...tools import automation as am
from ..pickers import OUField
from ..tools_base import ToolTab
from ..widgets import Page, ResultsTable, Worker, button


class AssignSyncTab(ToolTab):
    intro = ("Keep each Chromebook's assigned student – and its org unit – in step with your "
             "assignment list (an export from your asset system or a Google Sheet with Serial "
             "and Student email/ID columns, optional Asset tag). The device moves to its "
             "student's school, e.g. /Chromebooks/Lincoln Elementary.")

    def build(self):
        o = am.options()
        box, form = self.page.group("Settings")
        self.src = QLineEdit(o["source"])
        self.src.setPlaceholderText("assignments.csv, or a Google Sheet link")
        self.root = OUField(self.directory, "/Students")
        self.root.set_path(o["student_root"])
        self.depth = QSpinBox()
        self.depth.setRange(1, 3)
        self.depth.setValue(int(o["school_depth"]))
        self.tpl = QLineEdit(o["ou_template"])
        self.move = QCheckBox("Move the device to its student's school org unit")
        self.move.setChecked(bool(o["move_ou"]))
        self.asset = QCheckBox("Set the asset tag from the list")
        self.asset.setChecked(bool(o["set_asset"]))
        form.addRow("Assignment list", self.row(self.src, button("Browse…", slot=self._browse),
                                                stretch=False))
        form.addRow("Students are under", self.root)
        form.addRow("School = org-unit level", self.depth)
        form.addRow("Device org unit", self.tpl)
        form.addRow("", self.move)
        form.addRow("", self.asset)
        form.addRow("", self.row(button("Preview", "primary", self.preview),
                                 button("Apply changes", slot=self.apply),
                                 button("Every morning…", slot=self.schedule)))
        self.lay.addWidget(box)
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(320)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.plan = []

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Assignment list", "", "CSV (*.csv)")
        if p:
            self.src.setText(p)

    def _opts(self) -> dict:
        o = {"source": self.src.text().strip(), "student_root": self.root.path() or "/Students",
             "school_depth": self.depth.value(), "ou_template": self.tpl.text().strip()
             or "/Chromebooks/{school}", "move_ou": self.move.isChecked(),
             "set_asset": self.asset.isChecked()}
        am.save_options(o)
        return o

    def preview(self):
        o = self._opts()
        src = o["source"]
        if not src:
            self.info("Choose the assignment list.")
            return

        def got_text(text):
            def done(rows):
                if rows is None:
                    return
                self.plan = am.assign_plan(am.read_assignments(text), rows,
                                           self.directory.users, o)
                self.table.set_rows(["Serial", "Student", "Change"],
                                    [[p["Serial"], p["Student"], p["Change"]] for p in self.plan])
                n = sum(1 for p in self.plan if p["args"])
                self.status.setText(f"{len(self.plan)} assignment(s) · {n} to update")
            self.read(am.CROS_ARGS, done, "Reading Chromebooks…")
        if src.startswith("http"):
            from ... import google_io

            def dl():
                with open(google_io.download_sheet(src), encoding="utf-8-sig") as fh:
                    return fh.read()
            Worker(dl, on_done=got_text, on_error=lambda e: self.info(str(e)))
        elif os.path.isfile(src):
            with open(src, encoding="utf-8-sig") as fh:
                got_text(fh.read())
        else:
            self.info("That file isn't there.")

    def apply(self):
        todo = [p for p in self.plan if p["args"]]
        if not todo:
            self.info("Preview first – nothing to change yet.")
            return
        if self.confirm(f"Update {len(todo)} Chromebook(s)?"):
            self.run_steps(self.steps, [(f"{p['Serial']}: {p['Change'][:60]}", p["args"])
                                        for p in todo])

    def schedule(self):
        self._opts()
        from ... import tasks_health
        settings.set("assign/scheduled", True)
        try:
            tasks_health.create(dict(am.ASSIGN_TASK))
            self.info("The assignment sync will run every morning at 5:40 AM. If it finds an "
                      "unusually large number of changes it stops and waits for you.")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Saved, but the task couldn't be created here:\n{exc}")


class RuleDialog(QDialog):
    def __init__(self, parent, directory, rule: dict | None):
        super().__init__(parent)
        self.setWindowTitle("Clean-up rule")
        r = rule or {"name": "", "kind": "inactive", "ou": "/Students", "days": 180,
                     "enabled": True, "max": 200, "except": "", "include_never": False}
        f = QFormLayout(self)
        self.name = QLineEdit(r["name"])
        self.kind = QComboBox()
        for k, label in am.RULE_KINDS.items():
            self.kind.addItem(label, k)
        self.kind.setCurrentIndex(max(0, self.kind.findData(r["kind"])))
        self.ou = OUField(directory, "/Students")
        self.ou.set_path(r["ou"])
        self.days = QSpinBox()
        self.days.setRange(1, 3650)
        self.days.setValue(int(r.get("days", 180)))
        self.days.setSuffix(" days")
        self.never = QCheckBox("Include accounts that have never signed in")
        self.never.setChecked(bool(r.get("include_never")))
        self.max = QSpinBox()
        self.max.setRange(1, 100000)
        self.max.setValue(int(r.get("max", 200)))
        self.exc = QLineEdit(r.get("except", ""))
        self.exc.setPlaceholderText("accounts to always skip, comma separated")
        self.on = QCheckBox("Rule is on")
        self.on.setChecked(bool(r.get("enabled", True)))
        f.addRow("Name", self.name)
        f.addRow("Does", self.kind)
        f.addRow("Accounts under", self.ou)
        f.addRow("No sign-in for", self.days)
        f.addRow("", self.never)
        f.addRow("Stop if more than", self.max)
        f.addRow("Never touch", self.exc)
        f.addRow("", self.on)
        f.addRow("", QLabel("Rules never change anything by themselves – each finding becomes an "
                            "approval request.", objectName="Muted", wordWrap=True))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def rule(self) -> dict:
        return {"name": self.name.text().strip() or self.kind.currentText(),
                "kind": self.kind.currentData(), "ou": self.ou.path() or "/",
                "days": self.days.value(), "include_never": self.never.isChecked(),
                "max": self.max.value(), "except": self.exc.text().strip(),
                "enabled": self.on.isChecked()}


class CleanupPage(Page):
    title = "Clean-up rules"
    subtitle = ("Rules that find accounts to tidy up – long-inactive accounts, old suspended "
                "accounts, licenses on suspended accounts. Findings always go to Approvals; "
                "nothing is changed without a person saying yes.")

    def build(self):
        self.table = ResultsTable()
        self.body.addLayout(self.row(button("New rule…", "primary", self.new),
                                     button("Edit…", slot=self.edit),
                                     button("Delete", "danger", self.delete),
                                     button("Preview selected rule", slot=self.preview),
                                     button("Practice run", slot=self.practice),
                                     button("Check all rules now (send for approval)",
                                            slot=self.run_now),
                                     button("Every Monday…", slot=self.schedule)))
        self.body.addWidget(self.table)
        self.status = QLabel("", objectName="Muted")
        self.body.addWidget(self.status)
        self.found = ResultsTable()
        self.body.addWidget(self.found, 1)
        self.refresh()

    def on_show(self):
        self.refresh()

    def refresh(self):
        self.rs = am.rules()
        self.table.set_rows(["Rule", "Does", "Under", "Days", "On"],
                            [[r["name"], am.RULE_KINDS.get(r["kind"], r["kind"]), r["ou"],
                              str(r.get("days", "")), "yes" if r.get("enabled", True) else "no"]
                             for r in self.rs])

    def _sel(self):
        s = self.table.selected_dicts()
        return next((r for r in self.rs if s and r["name"] == s[0]["Rule"]), None)

    def new(self):
        d = RuleDialog(self, self.directory, None)
        if d.exec():
            am.save_rules(self.rs + [d.rule()])
            self.refresh()

    def edit(self):
        r = self._sel()
        if not r:
            self.info("Select a rule first.")
            return
        d = RuleDialog(self, self.directory, r)
        if d.exec():
            self.rs[self.rs.index(r)] = d.rule()
            am.save_rules(self.rs)
            self.refresh()

    def delete(self):
        r = self._sel()
        if r and self.confirm(f"Delete the rule “{r['name']}”?"):
            self.rs.remove(r)
            am.save_rules(self.rs)
            self.refresh()

    def preview(self):
        r = self._sel()
        if not r:
            self.info("Select a rule first.")
            return

        def show(lic):
            f = am.evaluate(r, self.directory.users, lic)
            self.found.set_rows(["Account", "Why", "Would run"],
                                [[x["email"], x["why"], " ".join(x["args"])] for x in f])
            self.status.setText(f"“{r['name']}” would find {len(f)} account(s).")
        if r["kind"] == "release":
            import csv
            import io

            def done(code, out, _e):
                show(list(csv.DictReader(io.StringIO(out or ""))) if code == 0 else [])
            self.runner.run(am.LICENSE_ARGS, done, quiet_stdout=True)
        else:
            show(None)

    def practice(self):
        from .round10_pages import practice_run
        r = self._sel()
        if not r:
            self.info("Select a rule first.")
            return
        if r["kind"] == "release":
            self.info("Use Preview for license rules – they don't move or suspend anyone.")
            return
        cmds = [x["args"] for x in am.evaluate(r, self.directory.users, None)]
        if not cmds:
            self.info(f"“{r['name']}” wouldn't change anything today.")
            return
        practice_run(self, cmds, r["name"])

    def run_now(self):
        if not self.confirm("Check every rule now and send what they find to Approvals?"):
            return
        Worker(am.run_cleanup, users=self.directory.users,
               on_done=lambda lines: (self.info("\n".join(lines)),
                                      self.app.update_approvals_badge()
                                      if hasattr(self.app, "update_approvals_badge") else None),
               on_error=lambda e: self.info(str(e)))

    def schedule(self):
        from ... import tasks_health
        settings.set("cleanup/scheduled", True)
        try:
            tasks_health.create(dict(am.CLEANUP_TASK))
            self.info("Clean-up rules will be checked every Monday at 6:30 AM.")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Saved, but the task couldn't be created here:\n{exc}")
