"""Chromebook fleet → Assigned users: blank the Assigned user field, set it to the person
who last signed in, or move each Chromebook to that student's school org unit – previewed
first, filtered, backed up, and undoable."""

from __future__ import annotations

import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QLabel, QLineEdit, QSpinBox, QVBoxLayout,
)

from ...tools import assigned_users as au
from ..pickers import OUField, OUMultiField
from ..tools_base import ToolTab
from ..widgets import ResultsTable, Worker, button
from .round11_pages import run_or_request
from .round13_tabs import _csv

COLS = ["Serial", "Asset ID", "Org unit", "Assigned user", "Last signed-in user",
        "Last used", "Plan", "Why", "deviceId"]
MOVE_COLS = ["Serial", "Asset ID", "Org unit", "Move to", "Based on", "Last used", "Plan", "Why",
             "deviceId"]
SCOPES = [("All Chromebooks", "all"), ("Org unit(s)", "ou"),
          ("Serial numbers", "serial"), ("Asset IDs", "asset")]


class AssignedUsersTab(ToolTab):
    intro = ("Clean up the <b>Assigned user</b> field on Chromebooks. Load the devices, then "
             "either blank the field, or set it to the person who last signed in. You see "
             "every change before it runs, the old values are saved first, and "
             "<b>Undo last change</b> puts them back. You can also move each Chromebook to "
             "the school org unit of the student who uses it. Clearing or setting the "
             "assigned user doesn't remove anyone's profile or wipe the device.")

    def build(self):
        from .devices import split_items
        self._split = split_items
        self.devs: list[dict] = []
        self.rows: list[dict] = []
        o = au.options()

        self.scope = QComboBox()
        for label, key in SCOPES:
            self.scope.addItem(label, key)
        self.ous = OUMultiField(self.directory)
        self.items = QLineEdit(placeholderText="serials or asset IDs, separated by commas")
        self.scope.currentIndexChanged.connect(self._scope_changed)
        self.lay.addLayout(self.row(QLabel("Which Chromebooks"), self.scope, self.ous,
                                    self.items, button("Load", "primary", self.load)))
        self._scope_changed()
        self.lay.addWidget(self.status)

        box = QGroupBox("Set it to the last signed-in user")
        bl = QVBoxLayout(box)
        self.blank_only = QComboBox()
        self.blank_only.addItems(["Only where it's blank", "Also replace a different user"])
        self.blank_only.setCurrentIndex(0 if o["blank_only"] else 1)
        self.students = QCheckBox("Only students (the last user must be in a student org "
                                  "unit – set them on Student lookup)")
        self.students.setChecked(bool(o["students_only"]))
        self.ignore = QLineEdit(o["ignore"])
        self.ignore.setPlaceholderText("never assign these, e.g. tech*, helpdesk@, "
                                       "jdoe@hancockschools.net")
        self.max_days = QSpinBox()
        self.max_days.setRange(0, 3650)
        self.max_days.setValue(int(o["max_days"]))
        self.max_days.setSpecialValueText("any time")
        self.max_days.setSuffix(" days")
        bl.addLayout(self.row(self.blank_only, QLabel("Last used within"), self.max_days))
        bl.addWidget(self.students)
        bl.addLayout(self.row(QLabel("Ignore"), self.ignore, stretch=False))
        bl.addLayout(self.row(button("Preview", slot=self.preview),
                              button("Set assigned users", "primary", self.apply_set)))
        self.lay.addWidget(box)
        self._move_box()

        self.table = ResultsTable()
        self.table.hidden_columns = {"deviceId"}
        self.table.setMinimumHeight(320)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(
            button("Blank the assigned user…", "danger", self.apply_clear),
            button("Undo last change", slot=self.undo),
            button("Save CSV…", slot=self.export),
            button("Open backups", slot=lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(au.backup_dir())))))
        self.hint = QLabel("Tip: select rows to act on just those; with nothing selected, "
                           "the buttons use every device in the list.", objectName="Muted")
        self.lay.addWidget(self.hint)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def _move_box(self):
        m = au.move_options()
        box = QGroupBox("Move it to the student's school org unit")
        bl = QVBoxLayout(box)
        self.m_who = QComboBox()
        self.m_who.addItem("the student who last signed in", "last")
        self.m_who.addItem("the assigned user", "assigned")
        self.m_who.setCurrentIndex(max(0, self.m_who.findData(m["who"])))
        self.m_root = OUField(self.directory, "/Students")
        self.m_root.set_path(m["student_root"])
        self.m_depth = QSpinBox()
        self.m_depth.setRange(1, 3)
        self.m_depth.setValue(int(m["school_depth"]))
        self.m_tpl = QLineEdit(m["ou_template"])
        self.m_tpl.setPlaceholderText("/Chromebooks/{school}")
        self.m_tpl.setMinimumWidth(280)
        self.m_skip = QLineEdit(m["skip_ous"])
        self.m_skip.setPlaceholderText("don't move devices in, e.g. /Chromebooks/Loaners, "
                                       "/Chromebooks/Repairs, /Chromebooks/Lost")
        self.m_active = QCheckBox("Only active devices (leave disabled and deprovisioned ones "
                                  "alone)")
        self.m_active.setChecked(bool(m["only_active"]))
        self.m_example = QLabel(objectName="Muted")
        for w in (self.m_depth, self.m_tpl, self.m_root):
            sig = getattr(w, "valueChanged", None) or getattr(w, "textChanged", None) or \
                getattr(w, "changed", None)
            if sig is not None:
                sig.connect(self._example)
        bl.addLayout(self.row(QLabel("Based on"), self.m_who, QLabel("Students are under"),
                              self.m_root))
        bl.addLayout(self.row(QLabel("School = org-unit level"), self.m_depth,
                              QLabel("Device org unit"), self.m_tpl))
        bl.addWidget(self.m_example)
        bl.addLayout(self.row(QLabel("Don't move"), self.m_skip, stretch=False))
        bl.addWidget(self.m_active)
        bl.addWidget(QLabel("The Ignore list and “Last used within” above apply here too. "
                            "Org units that don't exist yet are skipped, not created.",
                            objectName="Muted"))
        bl.addLayout(self.row(button("Preview moves", slot=self.preview_move),
                              button("Move Chromebooks", "primary", self.apply_move),
                              button("Every morning…", slot=self.schedule_move)))
        self.lay.addWidget(box)
        self._example()

    def _move_opts(self) -> dict:
        o = {**au.move_options(), "who": self.m_who.currentData(),
             "student_root": self.m_root.path() or "/Students",
             "school_depth": self.m_depth.value(),
             "ou_template": self.m_tpl.text().strip() or "/Chromebooks/{school}",
             "skip_ous": self.m_skip.text().strip(), "only_active": self.m_active.isChecked(),
             "ignore": self.ignore.text().strip(), "max_days": self.max_days.value()}
        if self.scope.currentData() == "ou":
            o["scope_ous"] = self.ous.paths()
        elif self.scope.currentData() == "all":
            o["scope_ous"] = []
        au.save_move_options(o)
        return o

    def _example(self, *_a):
        root = (self.m_root.path() or "/Students").rstrip("/")
        sample = root + "/" + "/".join(["Hancock High School", "9th Grade", "Homeroom"]
                                       [:self.m_depth.value() + 1])
        o = {"student_root": root, "school_depth": self.m_depth.value(),
             "ou_template": self.m_tpl.text().strip() or "/Chromebooks/{school}"}
        self.m_example.setText(f"Example: a student in {sample} → the Chromebook moves to "
                               f"{au.target_for(sample, o) or '(no school found)'}")

    def preview_move(self, quiet=False):
        if not self.devs:
            if not quiet:
                self.info("Load the Chromebooks first.")
            return
        self.mode = "move"
        users = self.directory.users or []
        self.rows = au.plan_move(self.devs, users, self._move_opts(),
                                 getattr(self.directory, "ous", None) or [])
        self.table.set_rows(MOVE_COLS, [[r["serial"], r["asset"], r["ou"], r["target"],
                                         r["who"], r["last_day"] or r["last_sync"][:10],
                                         r["plan"], r["why"], r["deviceId"]]
                                        for r in self.rows])
        n = sum(1 for r in self.rows if r["plan"] == "Move")
        note = "" if users else (" The people list isn't loaded yet – Preview moves again in "
                                 "a moment.")
        self.status.setText(f"{n:,} of {len(self.rows):,} would move.{note}")

    def apply_move(self):
        self.preview_move(quiet=True)
        rows = [r for r in self._chosen() if r.get("plan") == "Move"]
        if not rows:
            self.info("Nothing to move – load the Chromebooks and check the Plan column.")
            return
        path = au.backup(rows, "move")
        run_or_request(self.page, self.steps, au.move_steps(rows),
                       f"Move {len(rows):,} Chromebook(s) to their students' schools",
                       f"Chromebook follows its student's school (backup: "
                       f"{os.path.basename(path)})", done=lambda _s: self._after())

    def schedule_move(self):
        o = self._move_opts()
        from ... import tasks_health
        try:
            tasks_health.create(dict(au.MOVE_TASK))
            where = ", ".join(o["scope_ous"]) if o.get("scope_ous") else "every Chromebook"
            self.info("Every morning at 5:50 AM GAMbit will move Chromebooks to the school of "
                      f"the student who last signed in ({where}), with these settings. If it "
                      "finds an unusually large number of moves it stops and waits for you. "
                      "Each run saves a backup, so Undo last change works for it too.")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Saved, but the task couldn't be created here:\n{exc}")

    # ------------------------------------------------------------ loading ---
    def _scope_changed(self, *_a):
        key = self.scope.currentData()
        self.ous.setVisible(key == "ou")
        self.items.setVisible(key in ("serial", "asset"))
        self.items.setPlaceholderText("asset IDs, e.g. HS0116, HS0189" if key == "asset"
                                      else "serial numbers, separated by commas")

    def load(self):
        key = self.scope.currentData()
        vals = self.ous.paths() if key == "ou" else self._split(self.items.text())
        if key != "all" and not vals:
            self.info("Choose the org unit(s) or type the serials / asset IDs first.")
            return
        cmds = au.load_args(key, vals, self.ous.include_children() if key == "ou" else True)
        self.status.setText("Loading Chromebooks and who last signed in…")
        if not self.directory.users:
            self.directory.refresh_users()      # needed for the student / district checks

        def work():
            rows = []
            for a in cmds:
                c, r, e = _csv()(a)
                if c != 0:
                    raise RuntimeError(((e or "").strip().splitlines() or ["GAM failed"])[-1])
                rows += r
            return au.devices(rows)

        def done(devs):
            self.devs = devs
            if getattr(self, "mode", "set") == "move":
                self.preview_move(quiet=True)
            else:
                self.preview(quiet=True)
            blank = sum(1 for d in devs if not d["assigned"])
            self.status.setText(f"{len(devs):,} Chromebook(s) · {len(devs) - blank:,} have an "
                                f"assigned user · {blank:,} blank. The Plan column shows what "
                                "“Set assigned users” would do.")
        Worker(work, on_done=done, on_error=lambda e: self.status.setText(f"✖ {e}"))

    # ------------------------------------------------------------ preview ---
    def _opts(self) -> dict:
        o = {"blank_only": self.blank_only.currentIndex() == 0,
             "students_only": self.students.isChecked(),
             "ignore": self.ignore.text().strip(), "max_days": self.max_days.value()}
        au.save_options(o)
        return o

    def preview(self, quiet=False):
        if not self.devs:
            if not quiet:
                self.info("Load the Chromebooks first.")
            return
        from .lookup_page import student_ous
        self.mode = "set"
        users = self.directory.users or []
        self.rows = au.plan_set(self.devs, users, student_ous(), self._opts())
        self.table.set_rows(COLS, [[r["serial"], r["asset"], r["ou"], r["assigned"], r["last"],
                                    r["last_day"] or r["last_sync"][:10], r["plan"], r["why"],
                                    r["deviceId"]] for r in self.rows])
        n = sum(1 for r in self.rows if r["plan"] == "Set")
        note = "" if users else (" (the people list isn't loaded yet, so the student and "
                                 "district checks were skipped – Preview again in a moment)")
        if not quiet:
            self.status.setText(f"{n:,} of {len(self.rows):,} would be set.{note}")

    def _chosen(self) -> list[dict]:
        sel = set(self.table.selected_values("deviceId"))
        return [r for r in self.rows if r["deviceId"] in sel] if sel else list(self.rows)

    # ------------------------------------------------------------ actions ---
    def apply_set(self):
        self.preview(quiet=True)
        rows = [r for r in self._chosen() if r["plan"] == "Set"]
        if not rows:
            self.info("Nothing to set – load the Chromebooks and check the Plan column.")
            return
        replacing = sum(1 for r in rows if r["assigned"])
        if replacing and not self.confirm(
                f"{replacing:,} of these already have a different assigned user, which will "
                "be replaced by whoever signed in last. That can be a teacher or technician "
                "rather than the student. Continue?"):
            return
        path = au.backup(rows, "set")
        run_or_request(self.page, self.steps, au.set_steps(rows),
                       f"Set the assigned user on {len(rows):,} Chromebook(s)",
                       f"Assigned user = last signed-in user (backup: {os.path.basename(path)})",
                       done=lambda _s: self._after())

    def apply_clear(self):
        rows = [r for r in self._chosen() if r["assigned"]]
        if not rows:
            self.info("None of these Chromebooks has an assigned user.")
            return
        every = len(rows) == len([r for r in self.rows if r["assigned"]]) and \
            self.scope.currentData() == "all"
        if not self.confirm(f"Blank the Assigned user on {len(rows):,} Chromebook(s)"
                            + (" – every Chromebook in the district" if every else "") +
                            "?\n\nThe current values are saved first, so Undo can put them "
                            "back."):
            return
        path = au.backup(rows, "clear")
        run_or_request(self.page, self.steps, au.clear_steps(rows),
                       f"Blank the assigned user on {len(rows):,} Chromebook(s)",
                       f"Clear Chromebook assigned users (backup: {os.path.basename(path)})",
                       done=lambda _s: self._after())

    def undo(self):
        path = au.latest_backup()
        if not path:
            self.info("There's no saved change to undo yet.")
            return
        steps = au.undo_steps(path)
        if not steps or not self.confirm(
                ("Move the Chromebooks back to the org units they were in before "
                 if path.endswith("-move.csv") else
                 "Put the assigned users back as they were before ") +
                f"{os.path.basename(path)[:15].replace('-', ' at ', 1)}?"):
            return
        run_or_request(self.page, self.steps, steps, "Undo the last change",
                       f"Restore from {os.path.basename(path)}",
                       done=lambda _s: (os.replace(path, path + ".undone"), self._after()))

    def _after(self):
        if self.devs:
            self.load()

    def export(self):
        if not self.rows:
            self.info("Load the Chromebooks first.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Save", "assigned-users.csv", "CSV (*.csv)")
        if p:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(au.to_csv(self.rows, ["serial", "asset", "ou", "assigned", "last",
                                               "last_day", "plan", "why", "deviceId"]))
