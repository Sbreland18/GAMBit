"""Pick-don't-type widgets: org units, people and groups from the cached directory."""

from __future__ import annotations

import re

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .widgets import button

EMAIL_RE = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")


def _completer(parent, model) -> QCompleter:
    c = QCompleter(model, parent)
    c.setCaseSensitivity(Qt.CaseInsensitive)
    c.setFilterMode(Qt.MatchContains)
    c.setCompletionMode(QCompleter.PopupCompletion)
    c.setMaxVisibleItems(12)
    return c


# ============================================================ org units ===
class OUDialog(QDialog):
    """Tree of org units. Single-select, or checkboxes when multi=True."""

    def __init__(self, directory, multi=False, selected=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose org units" if multi else "Choose an org unit")
        self.resize(460, 560)
        self.d, self.multi = directory, multi
        self.selected = set(selected)

        self.search = QLineEdit(placeholderText="Type to filter…")
        self.search.textChanged.connect(self._filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(lambda *_: (not multi) and self.accept())
        self.info = QLabel("", objectName="Muted")
        refresh = button("Refresh list", slot=self._refresh)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(self.search)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        row.addWidget(self.info, 1)
        row.addWidget(refresh)
        lay.addLayout(row)
        lay.addWidget(buttons)
        self.d.ous_changed.connect(self._build)
        self._build()

    def _refresh(self):
        self.info.setText("Loading org units…")
        self.d.refresh_ous(on_done=lambda ok: self.info.setText(
            "" if ok else "Couldn't load – test the connection in Settings."))

    def _build(self):
        self.tree.clear()
        items: dict[str, QTreeWidgetItem] = {}
        paths = self.d.ous or ["/"]
        for path in sorted(set(paths) | {"/"}, key=lambda p: (p.count("/"), p.lower())):
            if path == "/":
                item = QTreeWidgetItem(self.tree, ["/  (whole domain)"])
            else:
                parent_path = path.rsplit("/", 1)[0] or "/"
                parent = items.get(parent_path) or items["/"]
                item = QTreeWidgetItem(parent, [path.rsplit("/", 1)[1]])
            item.setData(0, Qt.UserRole, path)
            item.setToolTip(0, path)
            if self.multi:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Checked if path in self.selected else Qt.Unchecked)
            items[path] = item
        self.tree.expandToDepth(0)
        for p in self.selected:
            if p in items:
                self.tree.scrollToItem(items[p])
                if not self.multi:
                    self.tree.setCurrentItem(items[p])
        if not self.d.ous:
            self.info.setText("No org units loaded yet. Click Refresh list.")
        else:
            self.info.setText(f"{len(self.d.ous)} org units · loaded {self.d.age_text('org units')}")

    def _filter(self, text):
        text = text.lower().strip()

        def walk(item) -> bool:
            path = item.data(0, Qt.UserRole).lower()
            child_match = any([walk(item.child(i)) for i in range(item.childCount())])
            match = not text or text in path or child_match
            item.setHidden(not match)
            if text and child_match:
                item.setExpanded(True)
            return match
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def paths(self) -> list[str]:
        if not self.multi:
            item = self.tree.currentItem()
            return [item.data(0, Qt.UserRole)] if item else []
        out = []

        def walk(item):
            if item.checkState(0) == Qt.Checked:
                out.append(item.data(0, Qt.UserRole))
            for i in range(item.childCount()):
                walk(item.child(i))
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out


def ou_label(path: str, counts: dict | None = None) -> str:
    """'7th Grade' + '· Hancock Middle School · 124 people' – what the org unit is."""
    name = path.rsplit("/", 1)[-1] if path != "/" else "Whole domain"
    bits = []
    try:
        from .. import ou_map
        c = ou_map.classify(path) if path != "/" else {}
        kind = {"students": "Students", "staff": "Staff", "devices": "Chromebooks"}.get(
            c.get("type", ""), "")
        if c.get("school") and c["school"].lower() != name.lower():
            bits.append(c["school"])
        if kind and kind.lower() not in name.lower():
            bits.append(kind)
    except Exception:  # noqa: BLE001
        pass
    if counts is not None and counts.get(path.lower()):
        n = counts[path.lower()]
        bits.append(f"{n:,} {'person' if n == 1 else 'people'}")
    return name + ("   ·  " + " · ".join(bits) if bits else "")


def ou_counts(directory) -> dict:
    """People directly in each org unit (lower-case path → count)."""
    out: dict = {}
    for u in getattr(directory, "users", []) or []:
        p = (u.get("ou") or "").lower()
        if p:
            out[p] = out.get(p, 0) + 1
    return out


class OUPopup(QWidget):
    """The drop-down tree under an org unit box: search, schools and grades labelled,
    how many people are in each, recently used ones on top."""

    picked = Signal(str)
    RECENT_KEY = "ou/recent"

    def __init__(self, directory, current: str = "", parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("OUPopup")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.d = directory
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        self.search = QLineEdit(placeholderText="Search org units, schools or grades…")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._choose)
        self.tree.itemActivated.connect(self._choose)
        lay.addWidget(self.tree, 1)
        self.info = QLabel("", objectName="Muted")
        lay.addWidget(self.info)
        self._build(current)
        self.search.setFocus()

    def recent(self) -> list[str]:
        import json
        from ..settings import settings
        try:
            r = json.loads(settings.get(self.RECENT_KEY, "[]") or "[]")
        except ValueError:
            r = []
        have = set(self.d.ous or [])
        return [p for p in r if isinstance(p, str) and (p in have or not have)][:5]

    @classmethod
    def remember(cls, path: str):
        import json
        from ..settings import settings
        try:
            r = json.loads(settings.get(cls.RECENT_KEY, "[]") or "[]")
        except ValueError:
            r = []
        r = [path] + [p for p in r if p != path]
        settings.set(cls.RECENT_KEY, json.dumps(r[:8]))

    def _build(self, current: str):
        from .icons import icon
        self.tree.clear()
        counts = ou_counts(self.d)
        rec = self.recent()
        if rec:
            top = QTreeWidgetItem(self.tree, ["Recently used"])
            top.setFlags(Qt.ItemIsEnabled)
            top.setData(0, Qt.UserRole, None)
            for p in rec:
                it = QTreeWidgetItem(top, [ou_label(p, counts)])
                it.setData(0, Qt.UserRole, p)
                it.setToolTip(0, p)
                it.setIcon(0, icon("history"))
            top.setExpanded(True)
        items: dict[str, QTreeWidgetItem] = {}
        paths = self.d.ous or []
        root = QTreeWidgetItem(self.tree, [ou_label("/", counts)])
        root.setData(0, Qt.UserRole, "/")
        root.setIcon(0, icon("globe"))
        items["/"] = root
        for path in sorted(set(paths), key=lambda p: (p.count("/"), p.lower())):
            if path == "/":
                continue
            parent = items.get(path.rsplit("/", 1)[0] or "/") or root
            it = QTreeWidgetItem(parent, [ou_label(path, counts)])
            it.setData(0, Qt.UserRole, path)
            it.setToolTip(0, path)
            it.setIcon(0, icon("building" if path.count("/") <= 2 else "tree"))
            items[path] = it
        root.setExpanded(True)
        for i in range(root.childCount()):
            root.child(i).setExpanded(len(paths) < 60)
        if current and current in items:
            self.tree.setCurrentItem(items[current])
            self.tree.scrollToItem(items[current])
        self.info.setText(f"{len(paths):,} org units" if paths else
                          "No org units loaded yet – Settings & Updates → Refresh lists.")

    def _filter(self, text):
        text = text.lower().strip()

        def walk(item) -> bool:
            path = (item.data(0, Qt.UserRole) or "")
            hay = (path + " " + item.text(0)).lower()
            kids = [walk(item.child(i)) for i in range(item.childCount())]
            match = not text or text in hay or any(kids)
            item.setHidden(not match)
            if text and any(kids):
                item.setExpanded(True)
            return match
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def _choose(self, item, *_a):
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        self.remember(path)
        self.picked.emit(path)
        self.close()


class OUField(QWidget):
    """Single org unit: type with suggestions, or browse the tree."""

    changed = Signal(str)

    def __init__(self, directory, placeholder="/Students", parent=None):
        super().__init__(parent)
        self.d = directory
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        self.combo.lineEdit().setPlaceholderText(placeholder)
        self.combo.setMinimumWidth(260)
        self.model = QStringListModel(self)
        self.combo.setModel(self.model)
        self.combo.setCompleter(_completer(self, self.model))
        self.combo.setCurrentIndex(-1)
        self.combo.currentTextChanged.connect(self.changed)
        browse = button("Choose…", slot=self._browse)
        from .icons import set_icon
        set_icon(browse, "tree")
        browse.setToolTip("Pick from the list of org units, schools and grades")
        self.browse_btn = browse
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.combo, 1)
        lay.addWidget(browse)
        self.d.ous_changed.connect(self._reload)
        self._reload()

    def _reload(self):
        cur = self.path()
        self.model.setStringList(self.d.ous)
        self.combo.setEditText(cur)

    def _browse(self):
        pop = OUPopup(self.d, self.path(), self)
        pop.picked.connect(self.set_path)
        w = max(self.width(), 460)
        pop.resize(w, 420)
        pos = self.mapToGlobal(self.rect().bottomLeft())
        scr = self.screen().availableGeometry() if self.screen() else None
        if scr is not None and pos.y() + 420 > scr.bottom():
            pos = self.mapToGlobal(self.rect().topLeft())
            pos.setY(pos.y() - 420)
        pop.move(pos)
        pop.show()
        self._popup = pop

    def path(self) -> str:
        return self.combo.currentText().strip()

    def set_path(self, p: str):
        self.combo.setEditText(p)
        if p:
            self.combo.setToolTip(ou_label(p))

    def text(self) -> str:  # so Page.need() works like a QLineEdit
        return self.path()

    def setFocus(self):
        self.combo.setFocus()


class OUMultiField(QWidget):
    """One or more org units, chosen from the tree."""

    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.d = directory
        self._paths: list[str] = []
        self.label = QLineEdit(placeholderText="Click Choose… to pick org units")
        self.label.setReadOnly(True)
        self.sub = QCheckBox("Include sub-OUs")
        self.sub.setChecked(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.label, 1)
        lay.addWidget(button("Choose…", slot=self._choose))
        lay.addWidget(self.sub)

    def _choose(self):
        dlg = OUDialog(self.d, multi=True, selected=self._paths, parent=self)
        if dlg.exec():
            self.set_paths(dlg.paths())

    def set_paths(self, paths):
        self._paths = list(paths)
        if not paths:
            self.label.setText("")
        elif len(paths) <= 3:
            self.label.setText(", ".join(paths))
        else:
            self.label.setText(f"{len(paths)} org units: " + ", ".join(paths[:3]) + "…")
        self.label.setToolTip("\n".join(paths))

    def paths(self) -> list[str]:
        return list(self._paths)

    def include_children(self) -> bool:
        return self.sub.isChecked()

    def set_include_children(self, on: bool):
        self.sub.setChecked(bool(on))


# =============================================================== people ===
def _person_label(u: dict) -> str:
    name = u.get("name") or ""
    tag = " (suspended)" if u.get("suspended") else ""
    return f"{name}  <{u['email']}>{tag}" if name else f"{u['email']}{tag}"


def _group_label(g: dict) -> str:
    return f"[Group] {g.get('name') or g['email']}  <{g['email']}>"


class PersonField(QLineEdit):
    """A single email box that suggests matching people as you type."""

    def __init__(self, directory, placeholder="Start typing a name or email…",
                 include_groups=False, parent=None, user_filter=None):
        super().__init__(parent)
        self.d, self.include_groups = directory, include_groups
        self.user_filter = user_filter
        self.setPlaceholderText(placeholder)
        self.model = QStringListModel(self)
        comp = _completer(self, self.model)
        comp.activated[str].connect(self._chosen)
        self.setCompleter(comp)
        self.d.users_changed.connect(self._reload)
        self.d.groups_changed.connect(self._reload)
        self._reload()

    def set_user_filter(self, fn):
        self.user_filter = fn
        self._reload()

    def _reload(self):
        users = self.d.users
        if self.user_filter is not None:
            users = [u for u in users if self.user_filter(u)]
        items = [_person_label(u) for u in users]
        if self.include_groups:
            items += [_group_label(g) for g in self.d.groups]
        self.model.setStringList(items)

    def _chosen(self, text):
        m = EMAIL_RE.search(text)
        if m:
            # defer so the completer doesn't overwrite our text
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.setText(m.group(0)))

    def email(self) -> str:
        m = EMAIL_RE.search(self.text())
        return m.group(0) if m else self.text().strip()


class GroupField(PersonField):
    """Like PersonField but suggests groups."""

    def _reload(self):
        self.model.setStringList([_group_label(g) for g in self.d.groups])


class PeoplePicker(QWidget):
    """Search box + list of chosen people. Paste a list of emails too."""

    def __init__(self, directory, include_groups=True, parent=None):
        super().__init__(parent)
        self.d = directory
        self.search = PersonField(directory, "Search by name or email, then press Enter "
                                  "(you can paste a list too)", include_groups)
        self.search.completer().activated[str].connect(self._add_text)
        self.search.returnPressed.connect(lambda: self._add_text(self.search.text()))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setFixedHeight(96)
        self.hint = QLabel("", objectName="Muted")

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.search, 1)
        top.addWidget(button("Add to list", slot=lambda: self._add_text(self.search.text())))
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.addWidget(self.hint, 1)
        bottom.addWidget(button("Remove from list", slot=self._remove_selected))
        bottom.addWidget(button("Clear", slot=self.clear))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top)
        lay.addWidget(self.list)
        lay.addLayout(bottom)
        self._update_hint()
        self.d.users_changed.connect(self._update_hint)

    def _update_hint(self):
        if not self.d.users:
            self.hint.setText("Tip: suggestions appear once the user list is loaded "
                              "(Settings → Refresh lists).")
        else:
            self.hint.setText(f"{self.list.count()} selected")

    def _add_text(self, text):
        emails = EMAIL_RE.findall(text or "")
        if not emails and text.strip():
            # A name with no email – take the single best match if there is one
            t = text.strip().lower()
            hits = [u["email"] for u in self.d.users
                    if t in (u.get("name") or "").lower() or t in u["email"].lower()]
            if len(hits) == 1:
                emails = hits
            else:
                self.hint.setText(f"{len(hits)} matches – pick one from the suggestions"
                                  if hits else "No match found")
                return
        existing = set(self.emails())
        for e in emails:
            if e.lower() not in {x.lower() for x in existing}:
                label = next((_person_label(u) for u in self.d.users
                              if u["email"].lower() == e.lower()), None) or \
                    next((_group_label(g) for g in self.d.groups
                          if g["email"].lower() == e.lower()), e)
                it = QListWidgetItem(label)
                it.setData(Qt.UserRole, e)
                self.list.addItem(it)
                existing.add(e)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.search.clear)
        self._update_hint()

    def _remove_selected(self):
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))
        self._update_hint()

    def clear(self):
        self.list.clear()
        self._update_hint()

    def emails(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]


# ============================================================== targets ===
class TargetPicker(QWidget):
    """Choose who a command applies to: people, org units, a group, or everyone.

    entities() returns a list of GAM <UserTypeEntity> argument lists – one
    command is run per entry (e.g. one per org unit).
    """

    def __init__(self, directory, allow_everyone=True, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QRadioButton, QStackedWidget

        self.d = directory
        self.r_people = QRadioButton("Specific people")
        self.r_ous = QRadioButton("Org unit(s)")
        self.r_group = QRadioButton("Members of a group")
        self.r_all = QRadioButton("Everyone in the domain")
        self.r_people.setChecked(True)
        radios = QHBoxLayout()
        radios.setContentsMargins(0, 0, 0, 0)
        for r in (self.r_people, self.r_ous, self.r_group, self.r_all):
            radios.addWidget(r)
        radios.addStretch(1)
        self.r_all.setVisible(allow_everyone)

        self.people = PeoplePicker(directory, include_groups=False)
        self.ous = OUMultiField(directory)
        self.group = GroupField(directory, "Start typing a group name or email…")
        self.everyone = QLabel("Every user account in your domain. This can take a while "
                               "on large domains.", objectName="Muted")
        self.stack = QStackedWidget()
        for w in (self.people, self.ous, self.group, self.everyone):
            holder = QWidget()
            v = QVBoxLayout(holder)
            v.setContentsMargins(0, 0, 0, 0)
            v.addWidget(w)
            v.addStretch(1)
            self.stack.addWidget(holder)
        for i, r in enumerate((self.r_people, self.r_ous, self.r_group, self.r_all)):
            r.toggled.connect(lambda on, i=i: on and self.stack.setCurrentIndex(i))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(radios)
        lay.addWidget(self.stack)
        self.stack.setFixedHeight(160)

    def mode(self) -> str:
        return ("people" if self.r_people.isChecked() else "ous" if self.r_ous.isChecked()
                else "group" if self.r_group.isChecked() else "all")

    def entities(self) -> list[list[str]]:
        m = self.mode()
        if m == "people":
            emails = self.people.emails()
            return [["users", ",".join(emails)]] if emails else []
        if m == "ous":
            kw = "ou_and_children" if self.ous.include_children() else "ou"
            return [[kw, p] for p in self.ous.paths()]
        if m == "group":
            g = self.group.email()
            return [["group", g]] if "@" in g else []
        return [["all", "users"]]

    def describe(self) -> str:
        m = self.mode()
        if m == "people":
            n = len(self.people.emails())
            return f"{n} person" if n == 1 else f"{n} people"
        if m == "ous":
            return "org unit(s): " + ", ".join(self.ous.paths())
        if m == "group":
            return f"members of {self.group.email()}"
        return "EVERYONE in the domain"

    def is_everyone(self) -> bool:
        return self.mode() == "all"
