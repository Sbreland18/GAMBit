from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from ...directory import run_gam_text
from ...group_settings import PRESETS, SETTINGS, parse_settings, to_args
from ..pickers import GroupField, PeoplePicker
from ..widgets import Page, ResultsTable, Worker, button

ROLES = ["member", "manager", "owner"]
MEMBER_FIELDS = "email,name,role,type,status"


# ======================================================= settings form ===
class GroupSettingsForm(QWidget):
    """One dropdown per permission, in plain English."""

    def __init__(self, parent=None, keep_label="Leave as is"):
        super().__init__(parent)
        self.combos: dict[str, QComboBox] = {}
        self.original: dict[str, str] = {}
        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setContentsMargins(0, 0, 0, 0)
        for attr, _api, question, options in SETTINGS:
            cb = QComboBox()
            cb.addItem(keep_label, "")
            for value, label in options:
                cb.addItem(label, value)
            self.combos[attr] = cb
            form.addRow(question, cb)

    def set_values(self, values: dict, as_original=False):
        for attr, cb in self.combos.items():
            idx = cb.findData(values.get(attr, ""))
            cb.setCurrentIndex(max(0, idx))
        if as_original:
            self.original = dict(values)

    def values(self) -> dict:
        return {a: cb.currentData() for a, cb in self.combos.items() if cb.currentData()}

    def changed_values(self) -> dict:
        return {a: v for a, v in self.values().items() if self.original.get(a) != v}


class GroupSettingsDialog(QDialog):
    """Load a group's current permissions, edit them, save only what changed."""

    def __init__(self, page: Page, group: str):
        super().__init__(page)
        self.page, self.group = page, group
        self.setWindowTitle(f"Permissions – {group}")
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{group}</b>"))
        self.status = QLabel("Loading current settings…", objectName="Muted")
        lay.addWidget(self.status)

        preset_row = QHBoxLayout()
        self.preset = QComboBox()
        self.preset.addItem("Apply a preset…", None)
        for name in PRESETS:
            if PRESETS[name]:
                self.preset.addItem(name, name)
        self.preset.currentIndexChanged.connect(self._apply_preset)
        preset_row.addWidget(self.preset, 1)
        lay.addLayout(preset_row)

        self.form = GroupSettingsForm(keep_label="(unknown – leave as is)")
        self.form.setEnabled(False)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form)
        scroll.setFrameShape(QScrollArea.NoFrame)
        lay.addWidget(scroll, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setEnabled(False)
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

        Worker(run_gam_text, ["info", "group", group, "nousers", "formatjson"],
               on_done=self._loaded, on_error=lambda e: self.status.setText(f"Couldn't load: {e}"))

    def _loaded(self, result):
        code, out = result
        values = parse_settings(out)
        if code != 0 or not values:
            self.status.setText("Couldn't read the current settings. You can still choose "
                                "new ones – only the ones you change will be saved.")
        else:
            self.status.setText("Change what you need. Only changed settings are saved.")
        self.form.set_values(values, as_original=True)
        self.form.setEnabled(True)
        self.buttons.button(QDialogButtonBox.Save).setEnabled(True)

    def _apply_preset(self):
        name = self.preset.currentData()
        if name:
            current = self.form.values()
            current.update(PRESETS[name])
            self.form.set_values(current)

    def _save(self):
        changes = self.form.changed_values()
        if not changes:
            self.reject()
            return
        self.page.run(["update", "group", self.group, *to_args(changes)])
        self.accept()


class GroupAliasDialog(QDialog):
    """See, add and remove a group's alternate addresses."""

    def __init__(self, page: Page, group: str):
        super().__init__(page)
        self.page, self.group = page, group
        self.setWindowTitle(f"Aliases – {group}")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Other addresses that deliver to <b>{group}</b>:"))
        self.table = ResultsTable()
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.new = QLineEdit(placeholderText="another-name@yourschool.org")
        row.addWidget(self.new, 1)
        row.addWidget(button("Add alias", "primary", self.add))
        row.addWidget(button("Remove selected", "danger", self.remove))
        lay.addLayout(row)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        lay.addWidget(close)
        self.load()

    def load(self):
        self.page.run(["print", "aliases", "group", self.group, "shownoneditable"],
                      lambda c, out, _e: self.table.load_csv(out) if c == 0 else None,
                      quiet=True)

    def add(self):
        a = self.new.text().strip()
        if "@" not in a:
            self.page.info("Type the full alias address.")
            return
        self.page.run(["create", "alias", a, "group", self.group],
                      lambda c, *_: (c == 0 and self.new.clear(), self.load()))

    def remove(self):
        sel = self.table.selected_values("Alias")
        if sel and self.page.confirm(f"Remove {', '.join(sel)}?"):
            self.page.run_many([["delete", "alias", a] for a in sel],
                               lambda _o: self.load(), quiet=False)


# ================================================================ page ===
class GroupsPage(Page):
    title = "Groups"
    subtitle = "Click a group to see and manage its members and permissions."

    def build(self):
        self.current = ""
        self.tabs = QTabWidget()
        self.tabs.addTab(self._browse_tab(), "Browse groups")
        self.tabs.addTab(self._create_tab(), "Create a group")
        from .group_rules_tab import GroupRulesTab
        self.rules_tab = GroupRulesTab(self)
        self.tabs.addTab(self.rules_tab, "Automatic groups")
        from .round13_tabs import GroupSuggestTab, GroupTreeTab
        self.suggest_tab, self.tree_tab = GroupSuggestTab(self), GroupTreeTab(self)
        self.tabs.addTab(self.suggest_tab, "Suggested automatic groups")
        self.tabs.addTab(self.tree_tab, "Why do they get this?")
        from .round15_tabs import GroupHygieneTab
        self.hygiene_tab = GroupHygieneTab(self)
        self.tabs.addTab(self.hygiene_tab, "Group clean-up")
        self.body.addWidget(self.tabs)
        self.directory.groups_changed.connect(self._fill_groups)
        self._fill_groups()

    def on_show(self):
        d = self.directory
        if not d.groups and d.connected and not d.is_loading("groups"):
            self.reload_groups()

    # ------------------------------------------------------- browse tab ---
    def _browse_tab(self):
        split = QSplitter(Qt.Horizontal)

        # left: list of groups
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 6, 6, 0)
        find = QHBoxLayout()
        self.find = GroupField(self.directory, "Go to a group by name or email…")
        self.find.returnPressed.connect(lambda: self.open_group(self.find.email()))
        self.find.completer().activated[str].connect(
            lambda _t: self.open_group(self.find.email()))
        find.addWidget(self.find, 1)
        find.addWidget(button("Open", slot=lambda: self.open_group(self.find.email())))
        lv.addLayout(find)
        self.groups_table = ResultsTable()
        self.groups_table.row_clicked.connect(lambda r: self.open_group(r.get("Email", "")))
        lv.addWidget(self.groups_table, 1)
        foot = QHBoxLayout()
        self.groups_age = QLabel("", objectName="Muted")
        foot.addWidget(self.groups_age, 1)
        foot.addWidget(button("Reload groups", slot=self.reload_groups))
        lv.addLayout(foot)

        # right: selected group
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 6, 0, 0)
        head = QHBoxLayout()
        self.g_title = QLabel("<span style='font-size:13pt; font-weight:600'>"
                              "Pick a group on the left</span>")
        self.g_title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        head.addWidget(self.g_title, 1)
        self.perm_btn = button("Permissions…", slot=self.edit_permissions)
        self.alias_btn = button("Aliases…", slot=self.edit_aliases)
        self.info_btn = button("Details", slot=lambda: self.run(
            ["info", "group", self.current, "nousers"]))
        self.del_btn = button("Delete group…", "danger", self.delete_group)
        self.everyone_btn = button("Everyone who gets it…", slot=self.everyone)
        self.everyone_btn.setToolTip("Expands groups inside the group to list every person "
                                     "who receives its email.")
        for b in (self.everyone_btn, self.perm_btn, self.alias_btn, self.info_btn,
                  self.del_btn):
            head.addWidget(b)
        rv.addLayout(head)

        self.members = ResultsTable()
        self.members.hidden_columns = {"group"}
        rv.addWidget(self.members, 1)

        sel = QHBoxLayout()
        sel.addWidget(QLabel("Selected members:"))
        self.rm_btn = button("Remove from group", "danger", self.remove_selected)
        self.role_pick = QComboBox()
        self.role_pick.addItems([f"Make {r}" for r in ROLES])
        self.role_btn = button("Change role", slot=self.change_role)
        sel.addWidget(self.rm_btn)
        sel.addSpacing(12)
        sel.addWidget(self.role_pick)
        sel.addWidget(self.role_btn)
        sel.addStretch(1)
        sel.addWidget(QLabel("Tip: Ctrl/Shift-click to pick several", objectName="Muted"))
        rv.addLayout(sel)

        add = QGroupBox("Add people")
        av = QVBoxLayout(add)
        self.add_people = PeoplePicker(self.directory)
        av.addWidget(self.add_people)
        ar = QHBoxLayout()
        ar.addWidget(QLabel("Add them as"))
        self.add_role = QComboBox()
        self.add_role.addItems(ROLES)
        ar.addWidget(self.add_role)
        self.add_btn = button("Add to group", "primary", self.add_members)
        ar.addWidget(self.add_btn)
        ar.addStretch(1)
        av.addLayout(ar)
        rv.addWidget(add)

        self.detail = right
        self._enable_detail(False)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([440, 600])
        return split

    def _enable_detail(self, on: bool):
        for w in (self.perm_btn, self.alias_btn, self.info_btn, self.del_btn, self.rm_btn, self.role_btn,
                  self.role_pick, self.add_btn, self.add_people, self.add_role):
            w.setEnabled(on)

    def _fill_groups(self):
        d = self.directory
        rows = [[g.get("name") or g["email"], g["email"], g.get("members", "")]
                for g in d.groups]
        self.groups_table.set_rows(["Name", "Email", "Members"], rows)
        self.groups_table.table.setColumnWidth(0, 170)
        if d.groups:
            self.groups_age.setText(f"Loaded {d.age_text('groups')}")
        else:
            self.groups_age.setText("Click Reload groups to load the list.")

    def reload_groups(self):
        self.groups_age.setText("Loading groups…")
        self.directory.refresh_groups(
            on_done=lambda ok: None if ok else self.groups_age.setText(
                "Couldn't load groups – test the connection in Settings."),
            log=self.app.log_line)

    def open_group(self, email: str):
        email = (email or "").strip()
        if "@" not in email:
            return
        self.current = email
        g = next((x for x in self.directory.groups if x["email"].lower() == email.lower()), {})
        name = g.get("name") or ""
        self.g_title.setText(
            f"<span style='font-size:13pt; font-weight:600'>{name or email}</span>"
            + (f"<br><span style='color:#57606a'>{email}</span>" if name else ""))
        self._enable_detail(True)
        self.load_members()

    def load_members(self):
        if not self.current:
            return
        self.members.set_rows([], [])
        self.run(["print", "group-members", "group", self.current, "fields", MEMBER_FIELDS],
                 lambda c, out, _e: self.members.load_csv(out) if c == 0 else None, quiet=True)

    def _selected_members(self):
        emails = self.members.selected_values("email")
        if not emails:
            self.info("Click one or more members in the list first.")
        return emails

    def remove_selected(self):
        emails = self._selected_members()
        if emails and self.confirm(f"Remove {len(emails)} member(s) from {self.current}?\n\n"
                                   + "\n".join(emails[:15])
                                   + ("\n…" if len(emails) > 15 else "")):
            self.run(["update", "group", self.current, "remove", "users", ",".join(emails)],
                     lambda c, *_: self.load_members())

    def change_role(self):
        emails = self._selected_members()
        if emails:
            role = ROLES[self.role_pick.currentIndex()]
            self.run(["update", "group", self.current, "update", role,
                      "users", ",".join(emails)], lambda c, *_: self.load_members())

    def add_members(self):
        people = self.add_people.emails()
        if not people:
            self.info("Search for people and add them to the list first.")
            return
        self.run(["update", "group", self.current, "add", self.add_role.currentText(),
                  "users", ",".join(people)],
                 lambda c, *_: (self.add_people.clear() if c == 0 else None,
                                self.load_members()))

    def edit_permissions(self):
        if self.current:
            GroupSettingsDialog(self, self.current).exec()

    def edit_aliases(self):
        if self.current:
            GroupAliasDialog(self, self.current).exec()

    def everyone(self):
        if not self.current:
            self.info("Pick a group first.")
            return
        from .more_tabs import EveryoneDialog
        EveryoneDialog(self, self.current).exec()

    def delete_group(self):
        g = self.current
        if g and self.confirm(f"Permanently delete the group {g}?\n\nThis can't be undone.",
                              "Delete group"):
            def done(code, *_):
                if code == 0:
                    self.current = ""
                    self.members.set_rows([], [])
                    self._enable_detail(False)
                    self.g_title.setText("Group deleted.")
                    self.reload_groups()
            self.run(["delete", "group", g], done)

    # ------------------------------------------------------- create tab ---
    def _create_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        scroll.setWidget(w)

        box, form = self.group("New group")
        self.n_email = QLineEdit(placeholderText="robotics-club@yourschool.org")
        self.n_name = QLineEdit(placeholderText="Robotics Club")
        self.n_desc = QLineEdit()
        form.addRow("Group email", self.n_email)
        form.addRow("Display name", self.n_name)
        form.addRow("Description", self.n_desc)
        lay.addWidget(box)

        box = QGroupBox("Permissions")
        bv = QVBoxLayout(box)
        self.n_preset = QComboBox()
        for name in PRESETS:
            self.n_preset.addItem(name, name)
        self.n_preset.setCurrentIndex(1)
        bv.addWidget(QLabel("Start from a preset, then fine-tune below if you like:"))
        bv.addWidget(self.n_preset)
        self.n_settings = GroupSettingsForm(keep_label="Google's default")
        bv.addWidget(self.n_settings)
        self.n_preset.currentIndexChanged.connect(
            lambda _i: self.n_settings.set_values(PRESETS[self.n_preset.currentData()]))
        self.n_settings.set_values(PRESETS[self.n_preset.currentData()])
        lay.addWidget(box)

        box = QGroupBox("Members (optional)")
        bv = QVBoxLayout(box)
        self.n_people = PeoplePicker(self.directory)
        bv.addWidget(self.n_people)
        r = QHBoxLayout()
        r.addWidget(QLabel("Add them as"))
        self.n_role = QComboBox()
        self.n_role.addItems(ROLES)
        r.addWidget(self.n_role)
        r.addStretch(1)
        bv.addLayout(r)
        lay.addWidget(box)

        lay.addLayout(self.row(button("Create group", "primary", self.create_group)))
        lay.addStretch(1)
        return scroll

    def create_group(self):
        if not self.need(("the group email", self.n_email)):
            return
        email = self.n_email.text().strip()
        args = ["create", "group", email]
        if self.n_name.text().strip():
            args += ["name", self.n_name.text().strip()]
        if self.n_desc.text().strip():
            args += ["description", self.n_desc.text().strip()]
        args += to_args(self.n_settings.values())
        people = self.n_people.emails()

        def after_members(_outs):
            self.n_email.clear()
            self.n_name.clear()
            self.n_desc.clear()
            self.n_people.clear()
            self.directory.refresh_groups(log=self.app.log_line)
            self.tabs.setCurrentIndex(0)
            self.open_group(email)

        def created(code, *_):
            if code != 0:
                return
            if people:
                self.run_many([["update", "group", email, "add", self.n_role.currentText(),
                                "users", ",".join(people)]], after_members, quiet=False)
            else:
                after_members([])
        self.run(args, created)
