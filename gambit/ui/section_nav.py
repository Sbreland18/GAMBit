"""A list of sections down the left of a long page (Settings & Updates), with a search box
that finds any option – “tray”, “accent”, “backup” – and hides the sections without it."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractButton, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget,
)


def _words(box: QGroupBox) -> str:
    parts = [box.title()]
    for w in box.findChildren(QWidget):
        if isinstance(w, (QLabel, QAbstractButton)):
            parts.append(w.text())
        tip = w.toolTip()
        if tip:
            parts.append(tip)
    return " ".join(parts).lower()


class SectionNav(QWidget):
    def __init__(self, scroll, inner: QWidget, parent=None):
        super().__init__(parent, objectName="SectionNav")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.scroll, self.inner = scroll, inner
        self.boxes = [b for b in inner.findChildren(QGroupBox)
                      if b.parentWidget() is inner and b.title()]
        self._words = {id(b): _words(b) for b in self.boxes}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.setSpacing(8)
        self.search = QLineEdit(placeholderText="Find a setting…")
        from .icons import icon
        self.search.addAction(icon("search"), QLineEdit.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.list = QListWidget(objectName="SectionList")
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for b in self.boxes:
            it = QListWidgetItem(b.title())
            it.setData(Qt.UserRole, id(b))
            self.list.addItem(it)
        self.list.itemClicked.connect(self._go)
        self.list.itemActivated.connect(self._go)
        lay.addWidget(self.list, 1)
        self.none = QLabel("No setting matches.", objectName="Muted")
        self.none.hide()
        lay.addWidget(self.none)
        self.setFixedWidth(230)
        scroll.verticalScrollBar().valueChanged.connect(self._follow)
        self._jumping = False

    def _box(self, key):
        return next((b for b in self.boxes if id(b) == key), None)

    def _go(self, item):
        b = self._box(item.data(Qt.UserRole))
        if b is None:
            return
        self._jumping = True
        self.scroll.verticalScrollBar().setValue(max(0, b.y() - 4))
        QTimer.singleShot(150, lambda: setattr(self, "_jumping", False))
        self.list.setCurrentItem(item)

    def _follow(self, value):
        if self._jumping:
            return
        cur = None
        for i, b in enumerate(self.boxes):
            if b.isVisible() and b.y() <= value + 40:
                cur = i
        if cur is not None:
            it = self.list.item(cur)
            if not it.isHidden():
                self.list.blockSignals(True)
                self.list.setCurrentItem(it)
                self.list.blockSignals(False)

    def _filter(self, text):
        q = text.lower().strip()
        shown = 0
        for i, b in enumerate(self.boxes):
            hit = not q or all(word in self._words[id(b)] for word in q.split())
            b.setVisible(hit)
            self.list.item(i).setHidden(not hit)
            shown += hit
        self.none.setVisible(shown == 0)
        if q:
            self.scroll.verticalScrollBar().setValue(0)


def install(page, scroll, inner) -> SectionNav:
    """Put a SectionNav to the left of `scroll` (which must be in page.body)."""
    page.body.removeWidget(scroll)
    row = QHBoxLayout()
    row.setSpacing(16)
    nav = SectionNav(scroll, inner)
    row.addWidget(nav)
    row.addWidget(scroll, 1)
    page.body.addLayout(row)
    return nav
