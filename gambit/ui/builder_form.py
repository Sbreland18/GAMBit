"""Turns a parsed GAM grammar tree into a fill-in form.

Every widget has .args() -> list[str] (raising Missing for empty required
fields). Optional parts, alternatives and repeats are built lazily so even
very large commands open quickly.
"""

from __future__ import annotations

import shlex

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ..command_catalog import LEAF_REFS, Node, render
from .pickers import GroupField, OUField, PersonField, TargetPicker
from .widgets import button

MAX_DEPTH = 3
SYNONYM_PAIRS = {frozenset(p) for p in [("create", "add"), ("delete", "del"), ("org", "ou"),
                                        ("orgs", "ous"), ("signature", "sig"),
                                        ("update", "modify"), ("calendar", "calendars")]}


class Missing(Exception):
    pass


def looks_synonymous(options: list[str]) -> bool:
    if len(options) < 2:
        return True
    if len(options) == 2 and frozenset(options) in SYNONYM_PAIRS:
        return True
    base = min(options, key=len).rstrip("s")
    if len(base) >= 3 and all((o.startswith(base) or o.endswith(base)) and
                              len(o) - len(base) <= 8 for o in options):
        return True
    return False


class Ctx:
    def __init__(self, catalog, directory, changed):
        self.catalog, self.directory, self.changed = catalog, directory, changed
        self.targets: list["TargetW"] = []


# ================================================================ leaves ===
class Field(QWidget):
    def args(self) -> list[str]:
        return []


class LitW(Field):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def args(self):
        return [self.value]


class ChoiceW(Field):
    def __init__(self, options, ctx):
        super().__init__()
        self.options = options
        self.fixed = looks_synonymous(options)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if self.fixed:
            lay.addWidget(_chip(options[0]))
        else:
            self.combo = QComboBox()
            self.combo.addItems(options)
            self.combo.currentIndexChanged.connect(ctx.changed)
            lay.addWidget(self.combo)
        lay.addStretch(1)

    def args(self):
        return [self.options[0] if self.fixed else self.combo.currentText()]


class TextW(Field):
    def __init__(self, name, ctx, tooltip="", split=False, browse=False):
        super().__init__()
        self.name, self.split = name, split
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(_placeholder(name))
        if tooltip:
            self.edit.setToolTip(tooltip)
        self.edit.textChanged.connect(ctx.changed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.edit, 1)
        if browse:
            lay.addWidget(button("Browse…", slot=self._browse))

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose file")
        if path:
            self.edit.setText(path)

    def args(self):
        t = self.edit.text().strip()
        if not t:
            raise Missing(self.name)
        if self.split:
            try:
                return shlex.split(t)
            except ValueError:
                return t.split()
        return [t]


class PickW(Field):
    """Person / group / OU picker."""

    def __init__(self, name, ctx, kind):
        super().__init__()
        self.name = name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if kind == "ou":
            self.w = OUField(ctx.directory, _placeholder(name))
            self.w.changed.connect(ctx.changed)
        elif kind == "group":
            self.w = GroupField(ctx.directory, "Group email (start typing)…")
            self.w.textChanged.connect(ctx.changed)
        else:
            self.w = PersonField(ctx.directory, "Email (start typing a name)…",
                                 include_groups=True)
            self.w.textChanged.connect(ctx.changed)
        lay.addWidget(self.w, 1)

    def args(self):
        v = self.w.path() if isinstance(self.w, OUField) else self.w.email()
        if not v:
            raise Missing(self.name)
        return [v]


class BoolW(Field):
    def __init__(self, ctx):
        super().__init__()
        self.combo = QComboBox()
        self.combo.addItems(["true", "false"])
        self.combo.currentIndexChanged.connect(ctx.changed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.combo)
        lay.addStretch(1)

    def args(self):
        return [self.combo.currentText()]


class EnumW(Field):
    def __init__(self, options, ctx, editable=False):
        super().__init__()
        self.combo = QComboBox()
        self.combo.addItems(options)
        self.combo.setEditable(editable)
        self.combo.currentTextChanged.connect(ctx.changed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.combo)
        lay.addStretch(1)

    def args(self):
        return [self.combo.currentText()]


class TargetW(Field):
    """<UserTypeEntity>: people, org units, a group, or everyone."""

    def __init__(self, ctx):
        super().__init__()
        self.picker = TargetPicker(ctx.directory)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.picker)
        ctx.targets.append(self)
        for sig in (self.picker.people.list.model().rowsInserted,
                    self.picker.people.list.model().rowsRemoved):
            sig.connect(ctx.changed)
        self.picker.group.textChanged.connect(ctx.changed)
        for r in (self.picker.r_people, self.picker.r_ous, self.picker.r_group,
                  self.picker.r_all):
            r.toggled.connect(ctx.changed)
        self.picker.ous.label.textChanged.connect(ctx.changed)

    def all_entities(self):
        return self.picker.entities()

    def args(self):
        ents = self.picker.entities()
        if not ents:
            raise Missing("who this applies to")
        return ents[0]


# ============================================================ structure ===
class SeqW(Field):
    def __init__(self, children: list[Node], ctx, depth):
        super().__init__()
        self.parts: list[Field] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        pending: list[str] = []
        for child in children:
            w = build(child, ctx, depth)
            self.parts.append(w)
            if isinstance(w, LitW):
                pending.append(w.value)
                continue
            if isinstance(w, ChoiceW) and w.fixed:
                pending.append(w.options[0])
                continue
            row = QHBoxLayout()
            row.setSpacing(8)
            if pending:
                row.addWidget(_chip(" ".join(pending)))
                pending = []
            row.addWidget(w, 1)
            lay.addLayout(row)
        if pending:
            lay.addWidget(_chip(" ".join(pending)))

    def args(self):
        out = []
        for p in self.parts:
            out += p.args()
        return out


class OptW(Field):
    def __init__(self, node: Node, ctx, depth):
        super().__init__()
        self.node, self.ctx, self.depth = node, ctx, depth
        self.inner_node = node.children[0]
        self.child: Field | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        inner = self.inner_node
        self.mode = "check"
        if inner.kind == "lit" and not inner.repeat:
            self.check = QCheckBox(inner.value)
            self.check.toggled.connect(ctx.changed)
            lay.addWidget(self.check)
            self.mode = "flag"
        elif (inner.kind == "choice" or (inner.kind == "ref" and inner.value == "Boolean"
                                          and not inner.options)) and not inner.repeat:
            opts = inner.options if inner.kind == "choice" else ["true", "false"]
            self.combo = QComboBox()
            self.combo.addItem("(leave out)" if inner.kind == "choice" else
                               "(leave out – on/off)")
            self.combo.addItems(opts)
            self.combo.currentIndexChanged.connect(ctx.changed)
            row = QHBoxLayout()
            row.addWidget(self.combo)
            row.addStretch(1)
            lay.addLayout(row)
            self.mode = "choice"
        else:
            self.check = QCheckBox(_short(render(inner)))
            self.check.setToolTip(render(inner))
            self.check.toggled.connect(self._toggle)
            lay.addWidget(self.check)
            self.box = QFrame()
            self.box.setObjectName("OptBox")
            self.box.setStyleSheet("QFrame#OptBox{border-left:3px solid #dbe9fd;"
                                   "margin-left:8px;padding-left:8px;}")
            self.box_lay = QVBoxLayout(self.box)
            self.box_lay.setContentsMargins(6, 2, 0, 2)
            self.box.hide()
            lay.addWidget(self.box)

    def _toggle(self, on):
        if on and self.child is None:
            self.child = build(self.inner_node, self.ctx, self.depth)
            self.box_lay.addWidget(self.child)
        self.box.setVisible(on)
        self.ctx.changed()

    def args(self):
        if self.mode == "flag":
            return [self.inner_node.value] if self.check.isChecked() else []
        if self.mode == "choice":
            return [self.combo.currentText()] if self.combo.currentIndex() > 0 else []
        if not self.check.isChecked() or self.child is None:
            return []
        return self.child.args()


class AltW(Field):
    def __init__(self, branches: list[Node], ctx, depth):
        super().__init__()
        self.branches, self.ctx, self.depth = branches, ctx, depth
        self.built: dict[int, Field] = {}
        self.combo = QComboBox()
        for b in branches:
            self.combo.addItem(_short(render(b), 70))
        self.combo.setToolTip("Pick one of these forms")
        self.stack = QStackedWidget()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(self.combo)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(self.stack)
        self.combo.currentIndexChanged.connect(self._pick)
        self._pick(0)

    def _pick(self, i):
        if i not in self.built:
            w = build(self.branches[i], self.ctx, self.depth)
            self.built[i] = w
            holder = QWidget()
            hl = QVBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(w)
            self.stack.addWidget(holder)
            w._holder = holder
        self.stack.setCurrentWidget(self.built[i]._holder)
        self.ctx.changed()

    def args(self):
        return self.built[self.combo.currentIndex()].args()


class RepeatW(Field):
    def __init__(self, node: Node, ctx, depth, minimum):
        super().__init__()
        self.node, self.ctx, self.depth = node, ctx, depth
        self.items: list[tuple[QWidget, Field]] = []
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.minimum = minimum
        self.add_btn = button(f"+ Add {_short(render(self._single()), 40)}", slot=self.add)
        row = QHBoxLayout()
        row.addWidget(self.add_btn)
        row.addStretch(1)
        self.lay.addLayout(row)
        for _ in range(minimum):
            self.add()

    def _single(self) -> Node:
        n = Node(self.node.kind, self.node.value, list(self.node.options),
                 list(self.node.children), "")
        return n

    def add(self):
        holder = QWidget()
        h = QHBoxLayout(holder)
        h.setContentsMargins(0, 0, 0, 0)
        single = self._single()
        if single.kind == "opt":   # "[x]*" – each added copy is simply included
            single = single.children[0]
        w = build(single, self.ctx, self.depth)
        h.addWidget(w, 1)
        rm = button("✕", slot=lambda: self.remove(holder))
        rm.setFixedWidth(34)
        h.addWidget(rm)
        self.lay.insertWidget(self.lay.count() - 1, holder)
        self.items.append((holder, w))
        self.ctx.changed()

    def remove(self, holder):
        if len(self.items) <= self.minimum:
            return
        self.items = [(h, w) for h, w in self.items if h is not holder]
        holder.deleteLater()
        self.ctx.changed()

    def args(self):
        out = []
        for _h, w in self.items:
            out += w.args()
        return out


# ================================================================ build ===
def build(node: Node, ctx: Ctx, depth: int = 0) -> Field:
    if node.repeat:
        return RepeatW(node, ctx, depth, 1 if node.repeat == "+" else 0)
    k = node.kind
    if k == "lit":
        if node.value.startswith('"') and "<" in node.value:
            # a quoted list such as "<Thing>(,<Thing>)*" – one comma-separated value
            inner = node.value.strip('"')
            name = inner.split(">")[0].lstrip("<") + " list"
            w = TextW(name, ctx, tooltip=inner)
            w.edit.setPlaceholderText(f"One or more {inner.split('>')[0].lstrip('<')}, "
                                      "separated by commas")
            return w
        return LitW(node.value)
    if k == "choice":
        return ChoiceW(node.options, ctx)
    if k == "seq":
        return SeqW(node.children, ctx, depth)
    if k == "group":
        return build(node.children[0], ctx, depth)
    if k == "opt":
        return OptW(node, ctx, depth)
    if k == "alt":
        return AltW(node.children, ctx, depth)
    w = ref_widget(node.value, ctx, depth)
    if node.options:                       # fixed prefix such as "user:"
        return PrefixW(node.options[0], w)
    return w


class PrefixW(Field):
    def __init__(self, prefix, inner: Field):
        super().__init__()
        self.prefix, self.inner = prefix, inner
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(_chip(prefix))
        lay.addWidget(inner, 1)

    def args(self):
        return [self.prefix + "".join(self.inner.args())]


def ref_widget(name: str, ctx: Ctx, depth: int) -> Field:
    low = name.lower().replace(" ", "")
    if low == "usertypeentity":
        return TargetW(ctx)
    if low == "boolean":
        return BoolW(ctx)
    if "orgunit" in low and "id" not in low:
        return PickW(name, ctx, "ou")
    if low.startswith("group") and any(s in low for s in ("item", "entity", "list")) \
            or low in ("groupemail",):
        return PickW(name, ctx, "group")
    if low in ("useritem", "emailaddress", "emailaddressentity", "userentity", "useremail",
               "emailaddresslist", "userlist", "recipiententity", "emailitem",
               "studentitem", "teacheritem") or low.endswith("emailaddress"):
        return PickW(name, ctx, "person")
    if "filename" in low:
        return TextW(name, ctx, browse=True)
    enum = ctx.catalog.enum_options(name)
    if enum:
        return EnumW(enum, ctx)
    tree = ctx.catalog.definition(name)
    body = ctx.catalog.defs.get(name, "")
    tip = f"<{name}> ::= {body}" if body else f"<{name}>"
    if tree is not None and low not in LEAF_REFS and depth < MAX_DEPTH \
            and len(body) < 260 and tree.kind in ("alt", "seq", "group", "choice", "opt"):
        return build(tree, ctx, depth + 1)
    split = bool(body) and low not in LEAF_REFS and len(body) >= 260
    return TextW(name, ctx, tooltip=tip, split=split)


# ============================================================== helpers ===
def _chip(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet("background:#eef3fb;color:#0b3d91;border-radius:6px;padding:3px 8px;"
                      "font-family:Consolas,'Cascadia Mono',monospace;")
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lab


def _short(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _placeholder(name: str) -> str:
    low = name.lower()
    if "date" in low or low in ("time",) or low.endswith("time"):
        return f"{name}: YYYY-MM-DD, or relative like -7d / today"
    if "courseid" in low:
        return "Course ID, or d:ALIAS"
    if "query" in low:
        return f"{name} (search text)"
    return f"<{name}>"
