"""Settings & Updates → Custom user fields: pick which custom schema fields GAMbit shows."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from .. import custom_fields as cf
from .widgets import Worker, button

TYPES = {"STRING": "text", "INT64": "number", "DOUBLE": "decimal", "BOOL": "yes/no",
         "DATE": "date", "EMAIL": "email", "PHONE": "phone"}


def _read_schemas():
    from ..directory import run_gam_text
    code, out = run_gam_text(["print", "schemas"], timeout=120)
    found = cf.parse_schemas(out) if code == 0 else {}
    return code, out, found


def _read_from_user(email: str):
    from ..directory import run_gam_text
    code, out = run_gam_text(["print", "users", "query", f"email:{email}", "fields",
                              "primaryemail", "custom", "all"], timeout=120)
    return code, out, (cf.schemas_from_users(out) if code == 0 else {})


class CustomFieldsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom user fields")
        self.resize(760, 640)
        self.cfg = dict(cf.config())
        v = QVBoxLayout(self)
        intro = QLabel(
            "Pick the custom fields (Google “custom schemas”, for example "
            "<b>Student_Information</b> → Grade, Student_ID) you want in user lists, CSV "
            "exports, Lookup and search. <b>Read schemas from Google</b> lists yours. "
            "Use Move up / Move down to change the column order.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        row = QHBoxLayout()
        self.load_btn = button("Read schemas from Google", "primary", self.load)
        row.addWidget(self.load_btn)
        self.person = QLineEdit(placeholderText="…or learn them from a person: "
                                "student@hancockschools.net")
        row.addWidget(self.person, 1)
        row.addWidget(button("Learn from this person", slot=self.learn))
        v.addLayout(row)
        self.status = QLabel("", objectName="Muted")
        self.status.setWordWrap(True)
        v.addWidget(self.status)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Field", "Type", "Searchable"])
        self.tree.setColumnWidth(0, 360)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        v.addWidget(self.tree, 1)
        row = QHBoxLayout()
        row.addWidget(button("Tick all", slot=lambda: self._tick_all(True)))
        row.addWidget(button("Untick all", slot=lambda: self._tick_all(False)))
        row.addStretch(1)
        row.addWidget(button("Move up", slot=lambda: self._move(-1)))
        row.addWidget(button("Move down", slot=lambda: self._move(1)))
        v.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Column names"))
        self.headers = QComboBox()
        self.headers.addItem("Friendly – Grade, Student ID", "friendly")
        self.headers.addItem("GAM style – Student_Information.Grade (ready to update with "
                             "GAM)", "gam")
        self.headers.setCurrentIndex(max(0, self.headers.findData(
            self.cfg.get("headers", "friendly"))))
        row.addWidget(self.headers, 1)
        v.addLayout(row)
        self.in_lists = QCheckBox("Add the ticked fields to user lists (Users → Find users, "
                                  "Org units, Inactive accounts) and Lookup")
        self.in_lists.setChecked(bool(self.cfg.get("in_lists", True)))
        v.addWidget(self.in_lists)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._fill()

    # ---------------------------------------------------------------- tree ---
    def _fill(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        chosen = [c.lower() for c in self.cfg.get("columns", [])]
        schemas = self.cfg.get("schemas") or {}
        for s, sch in schemas.items():
            top = QTreeWidgetItem([f"{s}" + (f"  ({sch['display']})" if sch.get("display")
                                             and sch["display"] != s else ""), "", ""])
            top.setData(0, Qt.UserRole, s)
            top.setFlags(top.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            self.tree.addTopLevelItem(top)
            fields = list(enumerate(sch.get("fields", [])))
            fields.sort(key=lambda p: chosen.index(f"{s}.{p[1]['name']}".lower())
                        if f"{s}.{p[1]['name']}".lower() in chosen else 1000 + p[0])
            for _i, f in fields:
                col = f"{s}.{f['name']}"
                name = f["name"] + (f"  ({f['display']})" if f.get("display") and
                                    f["display"] != f["name"] else "")
                it = QTreeWidgetItem([name, TYPES.get(f.get("type", ""), f.get("type", "")) +
                                      (", several values" if f.get("multi") else ""),
                                      "yes" if f.get("indexed") else "in GAMbit only"])
                it.setData(0, Qt.UserRole, col)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Checked if col.lower() in chosen else Qt.Unchecked)
                top.addChild(it)
            top.setExpanded(True)
        self.tree.blockSignals(False)
        n = sum(len(x.get("fields", [])) for x in schemas.values())
        if not schemas:
            self.status.setText("No schemas read yet – click “Read schemas from Google”.")
        else:
            when = self.cfg.get("loaded_at", "")
            self.status.setText(f"{len(schemas)} schema(s), {n} field(s)" +
                                (f" · read {when.replace('T', ' ')}" if when else "") +
                                ". “Searchable: yes” fields are searched by Google; the "
                                "others are searched by GAMbit after loading the users.")

    def _move(self, step: int):
        it = self.tree.currentItem()
        top = it.parent() if it else None
        if not top:
            return
        i = top.indexOfChild(it)
        j = i + step
        if 0 <= j < top.childCount():
            self.tree.blockSignals(True)
            top.takeChild(i)
            top.insertChild(j, it)
            self.tree.blockSignals(False)
            self.tree.setCurrentItem(it)

    def _tick_all(self, on: bool):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, Qt.Checked if on else Qt.Unchecked)

    def chosen(self) -> list[str]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                it = top.child(j)
                if it.checkState(0) == Qt.Checked and it.data(0, Qt.UserRole):
                    out.append(it.data(0, Qt.UserRole))
        return out

    # ------------------------------------------------------------- loading ---
    def _got(self, result, replace=True):
        self.load_btn.setEnabled(True)
        code, out, found = result
        if code != 0 or not found:
            msg = (out or "").strip().splitlines()[-1:] or [""]
            QMessageBox.warning(self, "Custom user fields",
                                "GAMbit couldn't read any custom schemas." +
                                (f"\n\nGAM said: {msg[0]}" if msg[0] else "") +
                                "\n\nIf your admin role can't read schemas, type a person who "
                                "has the fields filled in and click “Learn from this person”.")
            return
        keep = self.chosen()
        schemas = dict(found) if replace else {**self.cfg.get("schemas", {}), **found}
        self.cfg["schemas"] = schemas
        known = {f"{s}.{f['name']}".lower() for s, x in schemas.items() for f in x["fields"]}
        self.cfg["columns"] = [c for c in keep if c.lower() in known]
        import datetime
        self.cfg["loaded_at"] = datetime.datetime.now().isoformat(timespec="minutes")
        self._fill()

    def load(self):
        self.load_btn.setEnabled(False)
        self.status.setText("Reading schemas from Google…")
        Worker(_read_schemas, on_done=self._got,
               on_error=lambda e: (self.load_btn.setEnabled(True), self.status.setText(str(e))))

    def learn(self):
        e = self.person.text().strip()
        if "@" not in e:
            QMessageBox.information(self, "Custom user fields", "Type the person's email.")
            return
        self.status.setText(f"Reading {e}'s custom fields…")
        Worker(_read_from_user, e, on_done=lambda r: self._got(r, replace=False),
               on_error=lambda err: self.status.setText(str(err)))

    def save(self):
        self.cfg["columns"] = self.chosen()
        self.cfg["headers"] = self.headers.currentData()
        self.cfg["in_lists"] = self.in_lists.isChecked()
        cf.save(self.cfg)
        self.accept()


def summary() -> str:
    c = cf.config()
    cols = c.get("columns") or []
    if not cols:
        return ("None chosen yet." if c.get("schemas") else
                "Not set up – GAMbit doesn't add custom fields to user lists.")
    names = ", ".join(cf.label(x) for x in cols[:8]) + (" …" if len(cols) > 8 else "")
    where = "in user lists, exports and Lookup" if c.get("in_lists", True) else \
        "for search only (not added to lists)"
    return f"{len(cols)} field(s) {where}: {names}"
