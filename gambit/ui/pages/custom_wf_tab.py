"""Workflows → My workflows: run, build and share your own step-by-step jobs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QSplitter, QVBoxLayout, QWidget,
)

from ... import custom_workflows as cw
from ...gam_runner import display_command
from ..tools_base import ToolTab
from ..widgets import button


class EditDialog(QDialog):
    def __init__(self, parent, wf: dict | None):
        super().__init__(parent)
        self.setWindowTitle("Edit workflow" if wf else "New workflow")
        self.resize(860, 640)
        wf = wf or {"name": "", "description": "", "fields": [], "steps": []}
        f = QFormLayout(self)
        self.name = QLineEdit(wf["name"])
        self.desc = QLineEdit(wf.get("description", ""))
        fields, steps = cw.to_text(wf)
        self.fields = QPlainTextEdit(fields)
        self.fields.setPlaceholderText("email = New email\nfirst = First name\nou = Org unit = "
                                       "/Staff")
        self.steps = QPlainTextEdit(steps)
        self.steps.setPlaceholderText("Create the account | create user {email} firstname "
                                      "{first} ou {ou}\nAdd to group | update group staff add "
                                      "member user {email}")
        f.addRow("Name", self.name)
        f.addRow("What it does", self.desc)
        f.addRow("Fields", self.fields)
        f.addRow("", QLabel("One per line: key = Label [= default]. Use {key} in the steps. "
                            "{password} (a new random password) and {today} are always "
                            "available.", objectName="Muted", wordWrap=True))
        f.addRow("Steps", self.steps)
        f.addRow("", QLabel("One per line: Label | gam command. Steps run in order; each one "
                            "goes through dry run, roles and the activity log.",
                            objectName="Muted", wordWrap=True))
        self.err = QLabel("", objectName="Muted", wordWrap=True)
        f.addRow("", self.err)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.result_wf = None

    def _ok(self):
        wf = cw.from_text(self.name.text(), self.desc.text(), self.fields.toPlainText(),
                          self.steps.toPlainText())
        bad = cw.problems(wf)
        if bad:
            self.err.setText("⚠ " + " ".join(bad))
            return
        self.result_wf = wf
        self.accept()


class CustomWorkflowsTab(ToolTab):
    intro = ("Build your own step-by-step jobs from GAM commands with fill-in fields, and share "
             "them with the team (they're saved in the team folder).")

    def build(self):
        split = QSplitter()
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._pick)
        lv.addWidget(self.list, 1)
        lv.addLayout(self.row(button("New…", slot=self.new), button("Edit…", slot=self.edit),
                              button("Delete", "danger", self.delete)))
        split.addWidget(left)
        right = QWidget()
        self.rv = QVBoxLayout(right)
        self.title = QLabel("", objectName="PageTitle")
        self.title.setStyleSheet("font-size:13pt;font-weight:600;")
        self.desc = QLabel("", wordWrap=True)
        self.form = QFormLayout()
        self.rv.addWidget(self.title)
        self.rv.addWidget(self.desc)
        self.rv.addLayout(self.form)
        self.preview_lbl = QLabel("", objectName="Muted", wordWrap=True)
        self.preview_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.rv.addLayout(self.row(button("Preview", slot=self.preview),
                                   button("Run", "primary", self.run_it)))
        self.rv.addWidget(self.preview_lbl)
        self.rv.addStretch(1)
        split.addWidget(right)
        split.setSizes([260, 700])
        split.setMinimumHeight(380)
        self.lay.addWidget(split, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.inputs: dict[str, QLineEdit] = {}
        self.reload()

    def reload(self):
        self.wfs = cw.load()
        self.list.clear()
        for w in self.wfs:
            QListWidgetItem(w["name"] + ("  (example)" if w.get("example") else ""), self.list)
        if self.wfs:
            self.list.setCurrentRow(0)

    def _cur(self):
        i = self.list.currentRow()
        return self.wfs[i] if 0 <= i < len(self.wfs) else None

    def _pick(self, *_):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.inputs = {}
        wf = self._cur()
        self.preview_lbl.setText("")
        if not wf:
            self.title.setText("")
            self.desc.setText("")
            return
        self.title.setText(wf["name"])
        self.desc.setText(wf.get("description", "") + f"  ({len(wf['steps'])} step(s))")
        for f in wf.get("fields", []):
            e = QLineEdit(f.get("default", ""))
            self.inputs[f["key"]] = e
            self.form.addRow(f["label"], e)

    def _values(self):
        return {k: e.text().strip() for k, e in self.inputs.items()}

    def _build(self):
        from .users import random_password
        wf = self._cur()
        if not wf:
            return None
        self._pw = getattr(self, "_pw", "") or random_password()
        try:
            return cw.build(wf, self._values(), self._pw)
        except ValueError as exc:
            self.info(str(exc))
            return None

    def preview(self):
        steps = self._build()
        if steps:
            self.preview_lbl.setText("<br>".join(f"<b>{label}</b>: {display_command(a)}"
                                                 for label, a in steps))

    def run_it(self):
        steps = self._build()
        if not steps:
            return
        if self.confirm(f"Run “{self._cur()['name']}” ({len(steps)} steps)?\n\n" +
                        "\n".join(display_command(a) for _l, a in steps)):
            pw = self._pw

            def done(_s):
                self._pw = ""
                if "{password}" in str(self._cur()):
                    self.info(f"The new password used was: {pw}")
            self.run_steps(self.steps, steps, done)

    def _save_all(self):
        try:
            cw.save([w for w in self.wfs if not w.get("example")])
        except Exception as exc:  # noqa: BLE001
            self.info(f"Couldn't save:\n{exc}")
        self.reload()

    def new(self):
        d = EditDialog(self, None)
        if d.exec() and d.result_wf:
            self.wfs = [w for w in self.wfs if not w.get("example")] + [d.result_wf]
            self._save_all()

    def edit(self):
        wf = self._cur()
        if not wf:
            return
        d = EditDialog(self, wf)
        if d.exec() and d.result_wf:
            i = self.list.currentRow()
            self.wfs[i] = d.result_wf
            self._save_all()

    def delete(self):
        wf = self._cur()
        if wf and not wf.get("example") and self.confirm(f"Delete “{wf['name']}” for everyone?"):
            self.wfs.remove(wf)
            self._save_all()
