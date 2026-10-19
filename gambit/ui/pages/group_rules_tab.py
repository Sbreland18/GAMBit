"""Groups → Automatic groups: membership rules rebuilt from the user list."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget,
)

from ... import group_rules as gr
from ..pickers import GroupField, OUMultiField
from ..steps import Step, StepList
from ..widgets import ResultsTable, button


class GroupRulesTab(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.rules = gr.load()
        lay = QVBoxLayout(self)
        tip = QLabel("Keep mailing lists up to date automatically: pick who belongs by org unit, "
                     "job title or department. Plain members are added and removed to match – "
                     "owners and managers are never touched. Rules are shared through the "
                     "team folder.")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        dyn = button("New Google dynamic group…", slot=self.new_dynamic)
        dyn.setToolTip("A group Google keeps up to date by itself from a rule – no nightly "
                       "task needed.")
        lay.addLayout(page.row(QLabel("Or let Google keep it up to date:"), dyn))
        split = QSplitter()
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setMinimumWidth(240)
        self.list.currentRowChanged.connect(self._pick)
        lv.addWidget(self.list, 1)
        lv.addLayout(page.row(button("New rule", slot=self.new),
                              button("Delete", "danger", self.delete)))
        lv.addLayout(page.row(button("Run all rules now", slot=self.run_all),
                              button("Every night…", slot=self.schedule)))
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        box = QGroupBox("Rule")
        form = QFormLayout(box)
        self.group = GroupField(page.directory, "group@yourschool.org")
        self.name = QLineEdit(placeholderText="Name if GAMbit has to create the group")
        self.ous = OUMultiField(page.directory)
        self.title = QLineEdit(placeholderText="Optional, e.g. Teacher, Coach (any of these)")
        self.dept = QLineEdit(placeholderText="Optional, e.g. Science")
        self.exclude = OUMultiField(page.directory)
        self.exclude.sub.hide()
        self.mode = QComboBox()
        self.mode.addItem("Match exactly (add and remove)", "sync")
        self.mode.addItem("Only add people (never remove)", "addonly")
        self.susp = QCheckBox("Include suspended accounts")
        self.always = QPlainTextEdit()
        self.always.setPlaceholderText("Always include (one email per line), e.g. the principal")
        self.always.setFixedHeight(60)
        self.enabled = QCheckBox("Include in the nightly run")
        self.enabled.setChecked(True)
        for label, w in (("Group", self.group), ("Name", self.name), ("Org units", self.ous),
                         ("Job title", self.title),
                         ("Department", self.dept), ("Leave out org units", self.exclude),
                         ("Mode", self.mode), ("", self.susp), ("Always include", self.always),
                         ("", self.enabled)):
            form.addRow(label, w)
        rv.addWidget(box)
        rv.addLayout(page.row(button("Save rule", slot=self.save),
                              button("Preview", "primary", self.preview),
                              button("Apply this rule", slot=self.apply)))
        self.summary = QLabel("", objectName="Muted")
        self.summary.setWordWrap(True)
        rv.addWidget(self.summary)
        self.table = ResultsTable()
        rv.addWidget(self.table, 1)
        self.steps = StepList(page)
        self.steps.setMaximumHeight(120)
        rv.addWidget(self.steps)
        split.addWidget(right)
        split.setSizes([300, 900])
        lay.addWidget(split, 1)
        self.cur = None
        self.plan = None
        self._fill_list()

    # ------------------------------------------------------------- rules ---
    def _fill_list(self):
        self.list.blockSignals(True)
        self.list.clear()
        for r in self.rules:
            it = QListWidgetItem(f"{r['group'] or '(new rule)'}\n{gr.describe(r)}" +
                                 (f"\nlast run {r['last_run'].replace('T', ' ')}: "
                                  f"{r['last_result']}" if r.get("last_run") else ""))
            it.setData(Qt.UserRole, r["id"])
            self.list.addItem(it)
        self.list.blockSignals(False)
        if self.rules:
            self.list.setCurrentRow(0 if self.cur is None else max(
                0, next((i for i, r in enumerate(self.rules) if r["id"] == self.cur), 0)))

    def _rule(self):
        return next((r for r in self.rules if r["id"] == self.cur), None)

    def _pick(self, row):
        if row < 0 or row >= len(self.rules):
            return
        r = self.rules[row]
        self.cur = r["id"]
        self.group.setText(r["group"])
        self.name.setText(r.get("name", ""))
        self.ous.set_paths(r.get("ous", []))
        self.ous.sub.setChecked(r.get("children", True))
        self.title.setText(r.get("title", ""))
        self.dept.setText(r.get("department", ""))
        self.exclude.set_paths(r.get("exclude_ous", []))
        self.mode.setCurrentIndex(max(0, self.mode.findData(r.get("mode", "sync"))))
        self.susp.setChecked(r.get("suspended", False))
        self.always.setPlainText("\n".join(r.get("always", [])))
        self.enabled.setChecked(r.get("enabled", True))
        self.table.set_rows([], [])
        self.summary.setText(gr.describe(r))

    def _collect(self) -> dict | None:
        r = self._rule()
        if r is None:
            r = gr.new_rule()
            self.rules.append(r)
            self.cur = r["id"]
        g = self.group.email()
        if "@" not in g:
            self.page.info("Type the group's email address.")
            return None
        r.update(group=g.lower(), name=self.name.text().strip(), ous=self._paths(self.ous),
                 children=self.ous.include_children(), title=self.title.text().strip(),
                 department=self.dept.text().strip(), exclude_ous=self._paths(self.exclude),
                 mode=self.mode.currentData(), suspended=self.susp.isChecked(),
                 always=[x.strip() for x in self.always.toPlainText().splitlines()
                         if "@" in x], enabled=self.enabled.isChecked())
        return r

    @staticmethod
    def _paths(field) -> list[str]:
        return list(field.paths())

    def new_dynamic(self):
        from .misc_tabs import DynamicGroupDialog, run_dialog_steps
        run_dialog_steps(self.page, DynamicGroupDialog(self.page),
                         done=self.page.directory.refresh_groups)

    def new(self):
        r = gr.new_rule()
        self.rules.append(r)
        self.cur = r["id"]
        self._fill_list()
        self.list.setCurrentRow(len(self.rules) - 1)

    def save(self):
        if self._collect() is not None:
            gr.save(self.rules)
            self._fill_list()

    def delete(self):
        r = self._rule()
        if r and self.page.confirm(f"Delete the rule for {r['group'] or 'this group'}? "
                                   "(The group itself isn't deleted.)"):
            self.rules = [x for x in self.rules if x["id"] != r["id"]]
            self.cur = None
            gr.save(self.rules)
            self._fill_list()

    # ----------------------------------------------------------- preview ---
    def preview(self, then=None):
        r = self._collect()
        if r is None:
            return
        gr.save(self.rules)
        exists = any(g["email"].lower() == r["group"] for g in self.page.directory.groups)

        def done(code, out, _e):
            ex = code == 0
            adds, removes = gr.diff(r, self.page.directory.users, out if ex else "", ex)
            self.plan = (r, adds, removes, ex)
            self.table.set_rows(["Change", "Person"], [["Add", a] for a in adds] +
                                [["Remove", x] for x in removes])
            total = len(gr.members_for(r, self.page.directory.users))
            self.summary.setText(f"{gr.describe(r)} → {total:,} people should be in the group. "
                                 f"{len(adds):,} to add, {len(removes):,} to remove" +
                                 ("" if ex else " (the group will be created)") + ".")
            if callable(then):
                then()
        if exists:
            self.page.runner.run(["print", "group-members", "group", r["group"]], done,
                                 quiet_stdout=True)
        else:
            done(1, "", "")

    def apply(self):
        def go():
            r, adds, removes, ex = self.plan
            cmds = gr.commands(r, adds, removes, ex)
            if not cmds:
                self.page.info("The group already matches the rule.")
                return
            if not self.page.confirm(f"Update {r['group']}: add {len(adds):,}, remove "
                                     f"{len(removes):,}?"):
                return
            steps = [Step(" ".join(c[3:5]) if c[0] == "update" else "Create the group", c)
                     for c in cmds]

            def fin(_s):
                import datetime
                r["last_run"] = datetime.datetime.now().isoformat(timespec="minutes")
                r["last_result"] = f"+{len(adds)} −{len(removes)}"
                gr.save(self.rules)
                self._fill_list()
                self.page.info(self.steps.summary())
            self.steps.run(steps, fin)
        self.preview(then=go)

    def run_all(self):
        from ..widgets import Worker
        if not self.page.confirm("Rebuild every rule now?"):
            return
        self.summary.setText("Running every rule…")
        Worker(gr.run_all, on_done=lambda bad: (self._reload(),
                                               self.summary.setText(
                                                   "Done." + (f" {bad} rule(s) had failures."
                                                              if bad else ""))),
               on_error=lambda e: self.summary.setText(f"Failed: {e}"))

    def _reload(self):
        self.rules = gr.load()
        self._fill_list()

    def schedule(self):
        from ... import scheduler
        try:
            script = scheduler.build_app_task_script("GAMbit automatic groups",
                                                     ["--task", "groups"])
            scheduler.create_task("GAMbit automatic groups", script, "daily", "04:40")
        except Exception as exc:  # noqa: BLE001
            self.page.info(f"Couldn't schedule it:\n{exc}")
            return
        self.page.info("Every rule ticked “Include in the nightly run” will be rebuilt at "
                       "4:40 AM each day.")

