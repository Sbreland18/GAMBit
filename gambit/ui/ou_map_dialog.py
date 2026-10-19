"""Settings & Updates → Org units & schools: tell GAMbit what each org unit is."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from .. import ou_map
from .widgets import ResultsTable, button

GRAY = QBrush(QColor("#7b8794"))


class OUMapDialog(QDialog):
    def __init__(self, parent, directory):
        super().__init__(parent)
        self.d = directory
        self.setWindowTitle("Org units & schools")
        self.resize(1180, 740)
        self.items: dict[str, dict] = {e["path"].lower(): dict(e) for e in ou_map.entries()}
        self.nodes: dict[str, QTreeWidgetItem] = {}

        v = QVBoxLayout(self)
        intro = QLabel(
            "Tell GAMbit what your org units are. Mark the <b>top</b> org unit of each kind "
            "(for example /StudentAccounts = Students, /Chrome Devices = Chromebooks), then "
            "give each school's org units the school's name – everything under an org unit "
            "inherits from it (gray). Grades are picked up from names like “9th Grade”. "
            "<b>Find them for me</b> makes a first guess for you to check.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        top = QHBoxLayout()
        top.addWidget(button("✨ Find them for me", "primary", self.guess))
        self.filter = QLineEdit(placeholderText="Filter org units…")
        self.filter.textChanged.connect(self._filter)
        top.addWidget(self.filter, 1)
        top.addWidget(button("Expand all", slot=lambda: self.tree.expandAll()))
        top.addWidget(button("Collapse", slot=lambda: self.tree.collapseAll()))
        v.addLayout(top)

        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)

        # ---- tab 1: the tree + editor
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        split = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Org unit", "What it is", "School", "Grade"])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 170)
        self.tree.setColumnWidth(2, 190)
        self.tree.itemSelectionChanged.connect(self._load_selected)
        split.addWidget(self.tree)

        side = QGroupBox("Selected org unit(s)")
        f = QFormLayout(side)
        self.sel_lbl = QLabel("Pick one or more org units on the left.")
        self.sel_lbl.setWordWrap(True)
        f.addRow(self.sel_lbl)
        self.kind = QComboBox()
        for key, label in ou_map.TYPES.items():
            self.kind.addItem(label, key)
        self.school = QComboBox()
        self.school.setEditable(True)
        self.school.lineEdit().setPlaceholderText("(inherit)")
        self.grade = QLineEdit(placeholderText="(inherit) e.g. 9, K, PK")
        f.addRow("What it is", self.kind)
        f.addRow("School", self.school)
        f.addRow("", button("School = the org unit's own name", slot=self.name_as_school))
        f.addRow("Grade", self.grade)
        f.addRow("", self._row(button("Apply", "primary", self.apply),
                               button("Clear (inherit everything)", slot=self.clear_sel)))
        self.check = QLabel("", objectName="Muted")
        self.check.setWordWrap(True)
        f.addRow(self.check)
        split.addWidget(side)
        split.setSizes([760, 340])
        h.addWidget(split)
        self.tabs.addTab(w, "Org units")

        # ---- tab 2: schools summary
        w2 = QWidget()
        v2 = QVBoxLayout(w2)
        self.problems = QLabel("")
        self.problems.setWordWrap(True)
        v2.addWidget(self.problems)
        self.sum_table = ResultsTable()
        v2.addWidget(self.sum_table, 1)
        self.tabs.addTab(w2, "Schools")
        self.tabs.currentChanged.connect(lambda _i: self._summary())

        bottom = QHBoxLayout()
        self.status = QLabel("", objectName="Muted")
        bottom.addWidget(self.status, 1)
        bottom.addWidget(button("Cancel", slot=self.reject))
        bottom.addWidget(button("Save", "primary", self.save))
        v.addLayout(bottom)

        self._build_tree()
        if not self.d.ous and hasattr(self.d, "refresh_ous"):
            self.status.setText("Loading the org unit list from Google…")
            self.d.ous_changed.connect(self._build_tree)
            self.d.refresh_ous()

    @staticmethod
    def _row(*ws):
        h = QHBoxLayout()
        for x in ws:
            h.addWidget(x)
        h.addStretch(1)
        return h

    # -------------------------------------------------------------- tree ---
    def _entries(self) -> list[dict]:
        return [e for e in self.items.values() if e["type"] or e["school"] or e["grade"]]

    def _build_tree(self, *_a):
        self.tree.clear()
        self.nodes = {}
        paths = sorted({ou_map.norm_path(p) for p in list(self.d.ous or []) +
                        [e["path"] for e in self.items.values()]},
                       key=lambda p: (p.count("/"), p.lower()))
        for p in paths:
            if p == "/":
                continue
            parent_path = p.rsplit("/", 1)[0] or "/"
            parent = self.nodes.get(parent_path.lower())
            it = QTreeWidgetItem([p.rsplit("/", 1)[-1], "", "", ""])
            it.setData(0, Qt.UserRole, p)
            it.setToolTip(0, p)
            (parent.addChild(it) if parent is not None else self.tree.addTopLevelItem(it))
            self.nodes[p.lower()] = it
        self._paint()
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setExpanded(True)
        self.status.setText(f"{len(self.nodes):,} org units · {len(self._entries()):,} "
                            "marked")
        self.school.clear()
        self.school.addItems([""] + ou_map.schools(self._entries()))

    def _paint(self):
        ents = self._entries()
        bold = QFont()
        bold.setBold(True)
        for key, it in self.nodes.items():
            p = it.data(0, Qt.UserRole)
            own = self.items.get(key, {})
            c = ou_map.classify(p, ents)
            vals = [ou_map.TYPES.get(c["type"], "") if c["type"] else "", c["school"],
                    c["grade"]]
            owns = [bool(own.get("type")), bool(own.get("school")), bool(own.get("grade"))]
            for col, (val, mine) in enumerate(zip(vals, owns), start=1):
                it.setText(col, val)
                it.setForeground(col, QBrush() if mine else GRAY)
                it.setFont(col, bold if mine else QFont())

    def _filter(self, text):
        t = text.lower().strip()
        for key, it in self.nodes.items():
            hit = not t or t in key or any(t in it.text(c).lower() for c in (1, 2, 3))
            it.setHidden(not hit)
            if hit:
                p = it.parent()
                while p is not None:
                    p.setHidden(False)
                    p.setExpanded(bool(t))
                    p = p.parent()

    def _selected(self) -> list[str]:
        return [it.data(0, Qt.UserRole) for it in self.tree.selectedItems()]

    def _load_selected(self):
        sel = self._selected()
        if not sel:
            self.sel_lbl.setText("Pick one or more org units on the left.")
            self.check.setText("")
            return
        self.sel_lbl.setText(sel[0] if len(sel) == 1 else f"{len(sel)} org units")
        own = self.items.get(sel[0].lower(), {})
        self.kind.setCurrentIndex(max(0, self.kind.findData(own.get("type", ""))))
        self.school.setEditText(own.get("school", ""))
        self.grade.setText(own.get("grade", ""))
        c = ou_map.classify(sel[0], self._entries())
        self.check.setText("GAMbit sees it as: " + (" · ".join(x for x in (
            ou_map.TYPES.get(c["type"], "") if c["type"] else "not marked",
            c["school"] and f"school {c['school']}", c["grade"] and f"grade {c['grade']}")
            if x)) + (f" (from {c['mapped_at']})" if c["mapped_at"] and
                      c["mapped_at"].lower() != sel[0].lower() else ""))

    # ------------------------------------------------------------ editing ---
    def _set(self, path: str, **vals):
        key = path.lower()
        e = self.items.setdefault(key, {"path": path, "type": "", "school": "", "grade": ""})
        e.update(vals)
        if not (e["type"] or e["school"] or e["grade"]):
            self.items.pop(key, None)

    def apply(self):
        sel = self._selected()
        if not sel:
            return
        for p in sel:
            self._set(p, type=self.kind.currentData() or "",
                      school=self.school.currentText().strip(), grade=self.grade.text().strip())
        self._after_edit()

    def clear_sel(self):
        for p in self._selected():
            self.items.pop(p.lower(), None)
        self._after_edit()

    def name_as_school(self):
        for p in self._selected():
            self._set(p, school=p.rsplit("/", 1)[-1])
        self._after_edit()

    def _after_edit(self):
        self._paint()
        self._load_selected()
        cur = self.school.currentText()
        self.school.clear()
        self.school.addItems([""] + ou_map.schools(self._entries()))
        self.school.setEditText(cur)
        self.status.setText(f"{len(self.nodes):,} org units · {len(self._entries()):,} "
                            "marked · not saved yet")

    def guess(self):
        if not self.d.ous:
            QMessageBox.information(self, "Org units", "The org unit list isn't loaded yet – "
                                    "wait a moment and try again.")
            return
        sug = ou_map.suggest(self.d.ous)
        before = len(self._entries())
        merged = ou_map.merge(self._entries(), sug)
        self.items = {e["path"].lower(): e for e in merged}
        self._after_edit()
        self.status.setText(f"Added {len(self._entries()) - before:,} guesses – check them "
                            "(bold = set here, gray = inherited), fix anything wrong, then Save.")
        self.tabs.setCurrentIndex(1)
        self._summary()

    # ----------------------------------------------------------- summary ---
    def _summary(self):
        ents = self._entries()
        rows = ou_map.summary(ents)
        self.sum_table.set_rows(["School", "Students", "Staff", "Chromebooks", "Grades"],
                                [[r["School"], r["Students"], r["Staff"], r["Chromebooks"],
                                  r["Grades"]] for r in rows])
        notes = []
        if not ou_map.roots("students", ents):
            notes.append("No org unit is marked <b>Students</b> yet.")
        if not ou_map.roots("staff", ents):
            notes.append("No org unit is marked <b>Staff</b> yet.")
        if not ou_map.roots("devices", ents):
            notes.append("No org unit is marked <b>Chromebooks / devices</b> yet.")
        missing = [r["School"] for r in rows if r["Students"] and not r["Chromebooks"]]
        if missing:
            notes.append("These schools have students but no Chromebook org unit, so "
                         "Chromebooks can't be moved to them: " + ", ".join(missing) +
                         ". Mark the school's Chromebook org unit with the same school name.")
        self.problems.setText("<br>".join(f"⚠ {n}" for n in notes) or
                              "✔ Students, staff and Chromebooks are mapped for every school.")

    def save(self):
        ou_map.save(self._entries())
        self.accept()

