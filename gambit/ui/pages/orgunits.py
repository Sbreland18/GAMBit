"""Org units: browse the tree, create, rename, move, describe, delete."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ..pickers import OUField
from ..widgets import Page, ResultsTable, button

USER_FIELDS = "primaryemail,name,suspended,ou,lastlogintime"


class OrgUnitsPage(Page):
    title = "Org units"
    subtitle = "Create, rename, move and delete organizational units, and see what's in them."

    def build(self):
        self.path = ""
        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 6, 0)
        self.filter = QLineEdit(placeholderText="Filter org units…")
        self.filter.textChanged.connect(self._filter)
        lv.addWidget(self.filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._picked)
        lv.addWidget(self.tree, 1)
        self.age = QLabel("", objectName="Muted")
        lv.addLayout(self.row(self.age, button("Refresh", slot=self.refresh),
                              button("People per org unit…", slot=self.counts)))

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        self.title_lbl = QLabel("<span style='font-size:13pt;font-weight:600'>"
                                "Pick an org unit</span>")
        self.title_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rv.addWidget(self.title_lbl)

        box, form = self.group("Inside this org unit")
        form.addRow(self.row(button("Count what's in it", slot=self.check),
                             button("List its users", slot=self.list_users),
                             button("List its Chromebooks", slot=self.list_cros)))
        rv.addWidget(box)

        box, form = self.group("Create a sub-unit here")
        self.new_name = QLineEdit(placeholderText="e.g. Grade 6")
        self.new_desc = QLineEdit(placeholderText="Description (optional)")
        form.addRow("Name", self.new_name)
        form.addRow("Description", self.new_desc)
        form.addRow("", self.row(button("Create", "primary", self.create)))
        rv.addWidget(box)

        box, form = self.group("Change this org unit")
        self.ren = QLineEdit(placeholderText="New name")
        form.addRow("Rename to", self.row(self.ren, button("Rename", slot=self.rename),
                                          stretch=False))
        self.parent_pick = OUField(self.directory, "New parent")
        form.addRow("Move under", self.row(self.parent_pick, button("Move", slot=self.move),
                                           stretch=False))
        self.desc = QLineEdit(placeholderText="Description")
        form.addRow("Description", self.row(self.desc, button("Save", slot=self.save_desc),
                                            stretch=False))
        form.addRow("", self.row(button("Delete org unit…", "danger", self.delete)))
        rv.addWidget(box)

        self.results = ResultsTable()
        rv.addWidget(self.results, 1)
        self.detail = right
        right.setEnabled(False)

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([330, 700])
        self.body.addWidget(split, 1)
        self.directory.ous_changed.connect(self._build)
        self._build()

    def on_show(self):
        if not self.directory.ous and self.directory.connected:
            self.refresh()

    # -------------------------------------------------------------- tree ---
    def _build(self):
        keep = self.path
        self.tree.clear()
        items = {}
        for p in sorted(set(self.directory.ous) | {"/"},
                        key=lambda x: (x.count("/"), x.lower())):
            if p == "/":
                it = QTreeWidgetItem(self.tree, ["/  (whole domain)"])
            else:
                parent = items.get(p.rsplit("/", 1)[0] or "/") or items["/"]
                it = QTreeWidgetItem(parent, [p.rsplit("/", 1)[1]])
            it.setData(0, Qt.UserRole, p)
            items[p] = it
        self.tree.expandToDepth(1)
        if keep in items:
            self.tree.setCurrentItem(items[keep])
        self.age.setText(f"{len(self.directory.ous)} OUs · loaded "
                         f"{self.directory.age_text('org units')}")

    def _filter(self, text):
        text = text.lower().strip()

        def walk(item):
            child = any([walk(item.child(i)) for i in range(item.childCount())])
            match = not text or text in item.data(0, Qt.UserRole).lower() or child
            item.setHidden(not match)
            if text and child:
                item.setExpanded(True)
            return match
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def _picked(self, item, _prev=None):
        if not item:
            return
        self.path = item.data(0, Qt.UserRole)
        self.title_lbl.setText(f"<span style='font-size:13pt;font-weight:600'>{self.path}</span>")
        self.detail.setEnabled(True)
        root = self.path == "/"
        for w in (self.ren, self.parent_pick, self.desc):
            w.setEnabled(not root)

    def counts(self):
        from .round13_tabs import user_counts_dialog
        user_counts_dialog(self)

    def refresh(self):
        self.age.setText("Loading…")
        self.directory.refresh_ous(log=self.app.log_line)

    # ----------------------------------------------------------- actions ---
    def _after(self, select=None):
        def done(code, *_):
            if code == 0:
                if select:
                    self.path = select
                self.refresh()
        return done

    def check(self):
        self.run(["check", "ou", self.path],
                 lambda c, out, _e: self.results.load_csv(out) if out.strip() else None,
                 quiet=True)

    def list_users(self):
        q = ["print", "users"]
        if self.path != "/":
            q += ["query", f"orgUnitPath='{self.path}'"]
        self.run(q + ["fields", USER_FIELDS],
                 lambda c, out, _e: self.results.load_csv(out) if c == 0 else None, quiet=True)

    def list_cros(self):
        self.run(["print", "cros", "cros_ou_and_children", self.path, "fields",
                  "serialnumber,model,orgunitpath,annotateduser,lastsync,status"],
                 lambda c, out, _e: self.results.load_csv(out) if c == 0 else None, quiet=True)

    def create(self):
        name = self.new_name.text().strip()
        if not name:
            self.info("Type a name for the new org unit.")
            return
        if "#" in name or "+" in name:
            self.info("Org unit names can't contain # or + (GAM can't manage those).")
            return
        new = (self.path.rstrip("/") + "/" + name) if self.path != "/" else "/" + name
        args = ["create", "ou", new]
        if self.new_desc.text().strip():
            args += ["description", self.new_desc.text().strip()]
        self.run(args, lambda c, *_: (c == 0 and (self.new_name.clear(), self.new_desc.clear()),
                                      self._after(new)(c)))

    def rename(self):
        n = self.ren.text().strip()
        if not n:
            return
        new = self.path.rsplit("/", 1)[0] + "/" + n
        if self.confirm(f"Rename {self.path} to {new}?\n\nEverything inside moves with it."):
            self.run(["update", "ou", self.path, "name", n],
                     lambda c, *_: (self.ren.clear(), self._after(new)(c)))

    def move(self):
        parent = self.parent_pick.path()
        if not parent:
            self.info("Choose the new parent org unit.")
            return
        if parent == self.path or parent.startswith(self.path + "/"):
            self.info("An org unit can't be moved inside itself.")
            return
        new = (parent.rstrip("/") + "/" + self.path.rsplit("/", 1)[1])
        if self.confirm(f"Move {self.path} under {parent}?\n\nUsers, devices and policies "
                        "inside it move too and pick up the new parent's settings."):
            self.run(["update", "ou", self.path, "parent", parent], self._after(new))

    def save_desc(self):
        self.run(["update", "ou", self.path, "description", self.desc.text().strip()])

    def delete(self):
        if self.path == "/":
            return
        if self.confirm(f"Delete {self.path}?\n\nIt must be empty – no users, devices, "
                        "shared drives or sub-units. Use 'Count what's in it' first.",
                        "Delete org unit"):
            parent = self.path.rsplit("/", 1)[0] or "/"
            self.run(["delete", "ou", self.path], self._after(parent))
