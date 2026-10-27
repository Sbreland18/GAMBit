"""Home → Customize Home: boxes and their order, quick actions, number tiles and links."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget,
)

from .. import home_layout as hl
from ..settings import settings
from .widgets import button


def _check_list(items: list[tuple[str, str, bool]], movable: bool = True):
    """(key, label, on) → a widget with a checkable list (and Move up / down)."""
    w = QWidget()
    v = QVBoxLayout(w)
    lst = QListWidget()
    for key, label, on in items:
        it = QListWidgetItem(label)
        it.setData(Qt.UserRole, key)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Checked if on else Qt.Unchecked)
        lst.addItem(it)
    v.addWidget(lst, 1)
    if movable:
        row = QHBoxLayout()

        def move(step):
            i = lst.currentRow()
            j = i + step
            if i < 0 or not 0 <= j < lst.count():
                return
            it = lst.takeItem(i)
            lst.insertItem(j, it)
            lst.setCurrentRow(j)
        row.addWidget(button("Move up", slot=lambda: move(-1)))
        row.addWidget(button("Move down", slot=lambda: move(1)))
        row.addStretch(1)
        v.addLayout(row)
    return w, lst


def _values(lst: QListWidget) -> list[tuple[str, bool]]:
    return [(lst.item(i).data(Qt.UserRole), lst.item(i).checkState() == Qt.Checked)
            for i in range(lst.count())]


class HomeCustomizeDialog(QDialog):
    def __init__(self, home):
        super().__init__(home)
        self.home = home
        self.setWindowTitle("Customize Home")
        self.resize(560, 580)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Choose what Home shows and in what order. This is just for you, "
                           "on this PC.", wordWrap=True))
        tabs = QTabWidget()
        w, self.boxes = _check_list([(x["id"], hl.SECTIONS[x["id"]], x["on"])
                                     for x in hl.layout(home._admin())])
        tabs.addTab(w, "Boxes")
        chosen = hl.quick()
        order = chosen + [k for k in hl.QUICK if k not in chosen]
        w, self.quick = _check_list([(k, k, k in chosen) for k in order])
        tabs.addTab(w, "Quick actions")
        tiles = hl.tiles()
        order = tiles + [k for k in hl.TILES if k not in tiles]
        w, self.tiles = _check_list([(k, hl.TILES[k], k in tiles) for k in order])
        tabs.addTab(w, "Numbers")
        lw = QWidget()
        lv = QVBoxLayout(lw)
        lv.addWidget(QLabel("One per line: name = web address (or a \\\\server\\share "
                            "folder).", wordWrap=True))
        self.links = QPlainTextEdit(settings.get(hl.LINKS_KEY, "") or hl.DEFAULT_LINKS)
        lv.addWidget(self.links, 1)
        tabs.addTab(lw, "Links")
        v.addWidget(tabs, 1)
        row = QHBoxLayout()
        row.addWidget(button("Reset to the default", slot=self._reset))
        row.addStretch(1)
        v.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _save(self):
        hl.save_layout([{"id": k, "on": on} for k, on in _values(self.boxes)])
        hl.save_quick([k for k, on in _values(self.quick) if on])
        hl.save_tiles([k for k, on in _values(self.tiles) if on])
        settings.set(hl.LINKS_KEY, self.links.toPlainText().strip())
        self.accept()

    def _reset(self):
        hl.reset()
        self.accept()
