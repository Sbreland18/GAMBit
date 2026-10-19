"""Manage custom roles and who has which role (saved in the team folder)."""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QMessageBox,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

from .. import team


class RolesDialog(QDialog):
    def __init__(self, parent, page_names: list[str], workflow_tabs: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Team roles")
        self.resize(980, 720)
        self.data = copy.deepcopy(team.load_roles())
        self.page_names = page_names
        self.workflow_tabs = workflow_tabs
        lay = QVBoxLayout(self)
        intro = QLabel("Roles decide which pages a person sees and what GAMbit lets them run. "
                       "Anything a role can <i>ask for</i> becomes an approval request that a "
                       "Full admin approves on the Approvals page. Roles are guard rails in "
                       "GAMbit – GAM itself still has the admin access it was set up with on "
                       "each PC.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        tabs = QTabWidget()
        tabs.addTab(self._roles_tab(), "Roles")
        self.signed = bool(self.data.get("signed"))
        people = self._people_tab()
        if not self.signed:        # with GAMbit sign-in, people are on Users & access
            tabs.addTab(people, "People")
        lay.addWidget(tabs, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._load_role(self.roles.currentItem().text() if self.roles.currentItem() else "")

    # ------------------------------------------------------------- roles ---
    def _roles_tab(self):
        w = QWidget()
        h = QHBoxLayout(w)
        left = QVBoxLayout()
        self.roles = QListWidget()
        self.roles.addItems(sorted(self.data["roles"]))
        self.roles.currentTextChanged.connect(self._switch_role)
        left.addWidget(self.roles, 1)
        row = QHBoxLayout()
        for text, slot in (("New…", self._new_role), ("Copy…", self._copy_role),
                           ("Delete", self._delete_role)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        left.addLayout(row)
        h.addLayout(left, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        right = QWidget(objectName="Page")
        r = QVBoxLayout(right)
        form = QFormLayout()
        self.r_desc = QLineEdit()
        form.addRow("Description", self.r_desc)
        self.r_admin = QCheckBox("Full admin rights – manage roles and approve requests")
        form.addRow("", self.r_admin)
        self.r_ous = QLineEdit()
        self.r_ous.setPlaceholderText("optional, e.g. /Students/Lincoln, /Staff/Lincoln – "
                                      "everyone in the role only sees and changes these")
        form.addRow("Org units", self.r_ous)
        self.r_profile = QComboBox()
        self.r_profile.addItem("(any – their choice)", "")
        try:
            from .. import profiles
            for pr in profiles.profiles():
                self.r_profile.addItem(pr["name"], pr["name"])
        except Exception:  # noqa: BLE001
            pass
        self.r_profile.setToolTip("Tie the role to a GAM profile (a gam.cfg section signed in "
                                  "as a delegated admin with matching Google admin rights).")
        form.addRow("GAM profile", self.r_profile)
        r.addLayout(form)

        pages = QGroupBox("Pages they see (and pages they can only view)")
        g = QGridLayout(pages)
        self.r_pages: dict[str, QComboBox] = {}
        self.r_all_pages = QCheckBox("All pages (set view-only pages below)")
        g.addWidget(self.r_all_pages, 0, 0, 1, 3)
        for i, name in enumerate(self.page_names):
            cb = QComboBox()
            cb.addItems(["Hidden", "View only", "Full"])
            if name in ("Home", "Guide"):
                cb.setCurrentIndex(2)
                cb.setEnabled(False)
            self.r_pages[name] = cb
            row, col = 1 + i // 3, (i % 3) * 2
            g.addWidget(QLabel(name.replace("&", "&&")), row, col)
            g.addWidget(cb, row, col + 1)
        self.r_all_pages.toggled.connect(lambda on: [
            c.setCurrentIndex(max(c.currentIndex(), 2) if on else c.currentIndex())
            for c in self.r_pages.values()])
        r.addWidget(pages)

        wf = QGroupBox("Workflow tabs (if they see Workflows)")
        g = QHBoxLayout(wf)
        self.r_wf: dict[str, QCheckBox] = {}
        for name in self.workflow_tabs:
            cb = QCheckBox(name)
            self.r_wf[name] = cb
            g.addWidget(cb)
        r.addWidget(wf)

        perms = QGroupBox("What they can do")
        g = QGridLayout(perms)
        g.addWidget(QLabel("<b>Action</b>"), 0, 0)
        g.addWidget(QLabel("<b>Allowed</b>"), 0, 1)
        g.addWidget(QLabel("<b>Can ask for approval</b>"), 0, 2)
        self.r_can: dict[str, QCheckBox] = {}
        self.r_ask: dict[str, QCheckBox] = {}
        for i, (key, text) in enumerate(team.CATEGORIES.items(), start=1):
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            can, ask = QCheckBox(), QCheckBox()
            can.toggled.connect(lambda on, a=ask: a.setEnabled(not on))
            if key == "read":
                can.setChecked(True)
            self.r_can[key], self.r_ask[key] = can, ask
            g.addWidget(lbl, i, 0)
            g.addWidget(can, i, 1, Qt.AlignCenter)
            g.addWidget(ask, i, 2, Qt.AlignCenter)
        g.setColumnStretch(0, 1)
        r.addWidget(perms)
        r.addStretch(1)
        scroll.setWidget(right)
        h.addWidget(scroll, 3)
        self._current = None
        if self.roles.count():
            self.roles.setCurrentRow(0)
        return w

    def _store_current(self):
        name = self._current
        if not name or name not in self.data["roles"]:
            return
        pages = ["*"] if self.r_all_pages.isChecked() else \
            [n for n, cb in self.r_pages.items() if cb.currentIndex() > 0]
        view_only = [n for n, cb in self.r_pages.items() if cb.currentIndex() == 1]
        ous = [o.strip() for o in self.r_ous.text().split(",") if o.strip().startswith("/")]
        self.data["roles"][name] = {
            "view_only": view_only, "ous": ous,
            "gam_profile": self.r_profile.currentData() or "",
            "description": self.r_desc.text().strip(),
            "admin": self.r_admin.isChecked(),
            "pages": pages,
            "workflows": [n for n, cb in self.r_wf.items() if cb.isChecked()],
            "can": [k for k, cb in self.r_can.items() if cb.isChecked()],
            "ask": [k for k, cb in self.r_ask.items()
                    if cb.isChecked() and not self.r_can[k].isChecked()],
        }

    def _switch_role(self, name):
        self._store_current()
        self._load_role(name)

    def _load_role(self, name):
        self._current = name
        role = self.data["roles"].get(name)
        if not role:
            return
        self.r_desc.setText(role.get("description", ""))
        self.r_admin.setChecked(bool(role.get("admin")))
        pages = role.get("pages", ["*"])
        vo = set(role.get("view_only", []))
        self.r_all_pages.blockSignals(True)
        self.r_all_pages.setChecked("*" in pages)
        self.r_all_pages.blockSignals(False)
        for n, cb in self.r_pages.items():
            shown = n in ("Home", "Guide") or "*" in pages or n in pages
            cb.setCurrentIndex(0 if not shown else 1 if n in vo else 2)
        self.r_ous.setText(", ".join(role.get("ous", [])))
        i = self.r_profile.findData(role.get("gam_profile", ""))
        self.r_profile.setCurrentIndex(max(i, 0))
        wfs = role.get("workflows")
        for n, cb in self.r_wf.items():
            cb.setChecked(wfs is None or not wfs or n in wfs)
        for k in team.CATEGORIES:
            self.r_can[k].setChecked(k in role.get("can", []))
            self.r_ask[k].setChecked(k in role.get("ask", []))
            self.r_ask[k].setEnabled(k not in role.get("can", []))

    def _new_role(self, _=False, base=None):
        name, ok = QInputDialog.getText(self, "New role", "Role name (e.g. Library aide):")
        name = name.strip()
        if not ok or not name:
            return
        if name in self.data["roles"]:
            QMessageBox.information(self, "Roles", "There's already a role with that name.")
            return
        self._store_current()
        self.data["roles"][name] = copy.deepcopy(base) if base else {
            "description": "", "pages": ["Home"], "can": ["read"], "ask": [], "admin": False}
        self.roles.addItem(name)
        self.roles.setCurrentRow(self.roles.count() - 1)
        self._refresh_role_choices()

    def _copy_role(self):
        self._store_current()
        if self._current:
            self._new_role(base=self.data["roles"][self._current])

    def _delete_role(self):
        name = self._current
        if not name:
            return
        if name in team.BUILTIN_ROLES:
            QMessageBox.information(self, "Roles", "Built-in roles can't be deleted, but you "
                                    "can change them.")
            return
        if QMessageBox.question(self, "Roles", f"Delete the role “{name}”?") != QMessageBox.Yes:
            return
        self.data["roles"].pop(name, None)
        self._current = None
        self.roles.takeItem(self.roles.currentRow())
        self._refresh_role_choices()

    # ------------------------------------------------------------ people ---
    def _people_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Match people by their Windows sign-in name (what the Activity log "
                           f"shows in Who). You are <b>{team.me()}</b>."))
        form = QFormLayout()
        self.default_role = QComboBox()
        form.addRow("Everyone not listed gets", self.default_role)
        v.addLayout(form)
        self.people = QTableWidget(0, 2)
        self.people.setHorizontalHeaderLabels(["Windows user name", "Role"])
        self.people.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.people.setColumnWidth(1, 260)
        self.people.verticalHeader().setVisible(False)
        v.addWidget(self.people, 1)
        row = QHBoxLayout()
        add = QPushButton("Add person")
        add.clicked.connect(lambda: self._add_person("", ""))
        rem = QPushButton("Remove selected")
        rem.clicked.connect(lambda: [self.people.removeRow(r) for r in sorted(
            {i.row() for i in self.people.selectedIndexes()}, reverse=True)])
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        v.addLayout(row)
        self._refresh_role_choices()
        for user, role in sorted(self.data["people"].items()):
            self._add_person(user, role)
        if not self.data["people"]:
            self._add_person(team.me(), "Full admin")
        return w

    def _role_combo(self, current=""):
        cb = QComboBox()
        cb.addItems(sorted(self.data["roles"]))
        if current in self.data["roles"]:
            cb.setCurrentText(current)
        return cb

    def _add_person(self, user, role):
        r = self.people.rowCount()
        self.people.insertRow(r)
        self.people.setItem(r, 0, QTableWidgetItem(user))
        self.people.setCellWidget(r, 1, self._role_combo(role or "Help desk"))

    def _refresh_role_choices(self):
        if not hasattr(self, "default_role"):
            return
        cur = self.default_role.currentText() or self.data.get("default_role", "Full admin")
        self.default_role.clear()
        self.default_role.addItems(sorted(self.data["roles"]))
        self.default_role.setCurrentText(cur if cur in self.data["roles"] else "Full admin")
        for r in range(self.people.rowCount()):
            old = self.people.cellWidget(r, 1)
            self.people.setCellWidget(r, 1, self._role_combo(old.currentText() if old else ""))

    # -------------------------------------------------------------- save ---
    def _save(self):
        self._store_current()
        people = {}
        for r in range(self.people.rowCount()):
            it = self.people.item(r, 0)
            user = (it.text() if it else "").strip().lower()
            if user:
                people[user] = self.people.cellWidget(r, 1).currentText()
        if self.signed:
            self.data["people"] = {}
            self.data["default_role"] = self.data.get("default_role", "No access")
            try:
                team.save_roles(self.data)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Roles", f"Couldn't save:\n{exc}")
                return
            self.accept()
            return
        self.data["people"] = people
        self.data["default_role"] = self.default_role.currentText()
        mine = people.get(team.me(), self.data["default_role"])
        if not self.data["roles"].get(mine, {}).get("admin"):
            if QMessageBox.question(
                    self, "Roles", "You won't be a Full admin any more, so you won't be able "
                    "to change roles again. Save anyway?") != QMessageBox.Yes:
                return
        try:
            team.save_roles(self.data)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Roles", f"Couldn't save to the team folder:\n{exc}")
            return
        self.accept()
