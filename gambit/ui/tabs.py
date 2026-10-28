"""Tabs that don't fit: a “More ▾” button at the end of the tab strip lists every tab
(the hidden ones first), so nothing is lost behind the little scroll arrows."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QMenu, QTabWidget, QToolButton


class _TabMore(QObject):
    def __init__(self, tabs: QTabWidget):
        super().__init__(tabs)
        self.tabs = tabs
        self.btn = QToolButton(tabs, objectName="TabMore")
        self.btn.setText("More ▾")
        self.btn.setToolTip("All tabs on this page")
        self.btn.setPopupMode(QToolButton.InstantPopup)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.menu = QMenu(self.btn)
        self.menu.aboutToShow.connect(self._fill)
        self.btn.setMenu(self.menu)
        tabs.setCornerWidget(self.btn, Qt.TopRightCorner)
        self.btn.hide()
        tabs.tabBar().installEventFilter(self)
        tabs.installEventFilter(self)
        tabs.currentChanged.connect(lambda _i: self.check())
        QTimer.singleShot(0, self.check)

    def hidden_tabs(self) -> list[int]:
        bar = self.tabs.tabBar()
        w = bar.width()
        return [i for i in range(bar.count()) if bar.isTabVisible(i) and
                (bar.tabRect(i).right() > w or bar.tabRect(i).left() < 0)]

    def overflow(self) -> bool:
        bar = self.tabs.tabBar()
        need = sum(bar.tabSizeHint(i).width() for i in range(bar.count())
                   if bar.isTabVisible(i))
        room = self.tabs.width() - (self.btn.sizeHint().width() if self.btn.isVisible() else 0)
        return need > room - 8

    def check(self):
        try:
            show = self.overflow()
        except RuntimeError:
            return
        if show != self.btn.isVisible():
            self.btn.setVisible(show)          # (a hidden corner widget takes no room)

    def _fill(self):
        self.menu.clear()
        hidden = set(self.hidden_tabs())
        bar = self.tabs.tabBar()
        order = sorted(range(bar.count()), key=lambda i: (i not in hidden, i))
        for n, i in enumerate(order):
            if not bar.isTabVisible(i):
                continue
            if n and i not in hidden and order[n - 1] in hidden:
                self.menu.addSeparator()
            a = self.menu.addAction(self.tabs.tabText(i).replace("&&", "&"))
            a.setCheckable(True)
            a.setChecked(i == self.tabs.currentIndex())
            a.triggered.connect(lambda _=False, i=i: self.tabs.setCurrentIndex(i))

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
            QTimer.singleShot(0, self.check)
        return False


def enhance(root) -> int:
    """Give every tab strip under `root` the More ▾ button (once). Returns how many."""
    n = 0
    for tw in root.findChildren(QTabWidget):
        if tw.property("_gb_more"):
            continue
        tw.setProperty("_gb_more", True)
        tw._gb_more = _TabMore(tw)
        n += 1
    return n
