"""Tabs that don't fit: a “More ▾” button at the end of the tab strip lists every tab
(the hidden ones first), so nothing is lost behind the little scroll arrows."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLayout, QListWidget, QListWidgetItem, QMenu, QScrollArea, QSplitter,
    QStackedWidget, QTabWidget, QToolButton, QWidget,
)


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
        if self.tabs.property("_gb_side_on"):
            self.btn.hide()                    # tabs are in the list down the left
            return
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


# ================================================= tabs down the left ===
SIDE_KEY = "ui/side_tabs"
_ALL: dict[int, "_SideTabs"] = {}        # every converted strip, until its widget goes
_TIMER = None


def side_on() -> bool:
    from ..settings import settings
    return bool(settings.get(SIDE_KEY, True))


def _find_in_layout(lay: QLayout, w: QWidget):
    for i in range(lay.count()):
        it = lay.itemAt(i)
        if it.widget() is w:
            return lay
        if it.layout() is not None:
            found = _find_in_layout(it.layout(), w)
            if found is not None:
                return found
    return None


def _swap(old: QWidget, new: QWidget) -> bool:
    """Put `new` exactly where `old` is (same layout slot, stretch, splitter or stack
    position). Returns False if it can't tell where `old` lives."""
    parent = old.parentWidget()
    if parent is None:
        return False
    if isinstance(parent, QSplitter):
        i = parent.indexOf(old)
        if i < 0:
            return False
        sizes = parent.sizes()
        parent.replaceWidget(i, new)
        parent.setSizes(sizes)
        return True
    if isinstance(parent, QStackedWidget):
        i = parent.indexOf(old)
        if i < 0:
            return False
        cur = parent.currentWidget() is old
        parent.removeWidget(old)
        parent.insertWidget(i, new)
        if cur:
            parent.setCurrentWidget(new)
        return True
    vp = parent.parentWidget()
    if isinstance(vp, QScrollArea) and vp.widget() is old:
        vp.takeWidget()
        vp.setWidget(new)
        return True
    lay = parent.layout()
    if lay is None:
        return False
    holder = _find_in_layout(lay, old)
    if holder is None:
        return False
    holder.replaceWidget(old, new)
    return True


def _tick():
    """One timer for all of them: the list follows tabs that are renamed ("Approvals
    (3)"), hidden by role or help-desk mode, or added later – only on pages being shown."""
    for key, st in list(_ALL.items()):
        try:
            if st.box.isVisible():
                st.sync()
        except RuntimeError:                  # widget already deleted
            _ALL.pop(key, None)


class _ShowFilter(QObject):
    """One shared filter: a list that's being shown fills in before it's painted."""

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Show:
            st = _ALL.get(obj.property("_gb_side_key") or 0)
            if st is not None:
                try:
                    st.sync()
                except RuntimeError:
                    pass
        return False


_FILTER = None


def _start_timer():
    global _TIMER, _FILTER
    if _FILTER is None:
        from PySide6.QtWidgets import QApplication
        _FILTER = _ShowFilter(QApplication.instance())
    if _TIMER is None:
        from PySide6.QtWidgets import QApplication
        _TIMER = QTimer(QApplication.instance())
        _TIMER.setInterval(500)
        _TIMER.timeout.connect(_tick)
        _TIMER.start()


class _SideTabs:
    """The tab strip of a page shown as a list down the left (like Settings & Updates).
    The QTabWidget stays as it is – only its tab bar is hidden – so everything that adds,
    renames, hides or switches tabs keeps working; the list follows it."""

    def __init__(self, tabs: QTabWidget, box: QWidget, lst: QListWidget):
        self.tabs, self.box, self.list = tabs, box, lst
        self._state = None
        lst.currentItemChanged.connect(self._picked)
        tabs.currentChanged.connect(self._changed)
        key = id(self)
        _ALL[key] = self
        tabs.destroyed.connect(lambda *_a, k=key: _ALL.pop(k, None))
        _start_timer()
        lst.setProperty("_gb_side_key", key)
        lst.installEventFilter(_FILTER)
        box.installEventFilter(_FILTER)
        box.setProperty("_gb_side_key", key)
        self.apply(side_on())

    def _changed(self, _i):
        try:
            self.sync()
        except RuntimeError:
            pass

    def apply(self, on: bool):
        self.tabs.setProperty("_gb_side_on", on)
        self.tabs.tabBar().setVisible(not on)
        self.list.setVisible(on)
        more = getattr(self.tabs, "_gb_more", None)
        if more is not None:
            more.check()
        self._state = None
        if on and (self.box.isVisible() or not self.list.count()):
            self.sync()          # hidden pages refill when they're next shown

    def _snapshot(self):
        t = self.tabs
        bar = t.tabBar()
        return (tuple((t.tabText(i), bar.isTabVisible(i), t.isTabEnabled(i),
                       t.tabIcon(i).cacheKey(), t.tabToolTip(i)) for i in range(t.count())),
                t.currentIndex())

    def sync(self):
        if not self.tabs.property("_gb_side_on"):
            return
        snap = self._snapshot()
        if snap == self._state:
            return
        tabs_state, cur = snap
        if self._state is None or self._state[0] != tabs_state:
            self.list.blockSignals(True)
            self.list.clear()
            for i, (text, vis, enabled, _k, tip) in enumerate(tabs_state):
                it = QListWidgetItem(self.tabs.tabIcon(i), text.replace("&&", "&"))
                it.setData(Qt.UserRole, i)
                if tip:
                    it.setToolTip(tip)
                if not enabled:
                    it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
                self.list.addItem(it)
                it.setHidden(not vis)
            self.list.blockSignals(False)
            self._fit_width()
        self.list.blockSignals(True)
        self.list.setCurrentRow(cur if 0 <= cur < self.list.count() else -1)
        self.list.blockSignals(False)
        self._state = snap

    def _fit_width(self):
        fm = self.list.fontMetrics()
        want = max([fm.horizontalAdvance(self.list.item(r).text())
                    for r in range(self.list.count())] or [100]) + 44
        self.list.setFixedWidth(max(150, min(230, want)))

    def _picked(self, item, _prev=None):
        if item is None:
            return
        i = item.data(Qt.UserRole)
        if isinstance(i, int) and i != self.tabs.currentIndex():
            self.tabs.setCurrentIndex(i)
            if self.tabs.currentIndex() != i:          # refused (unsaved changes, role)
                self.sync()


def _nested(tw: QTabWidget, root: QWidget) -> bool:
    p = tw.parentWidget()
    while p is not None and p is not root:
        if isinstance(p, QTabWidget):
            return True
        p = p.parentWidget()
    return False


def side_tabs(root: QWidget) -> int:
    """Show each top-level tab strip under `root` (a page) as a list down the left.
    Tabs inside another tab stay across the top. Returns how many were converted."""
    n = 0
    for tw in root.findChildren(QTabWidget):
        if tw.property("_gb_side") or _nested(tw, root) or tw.count() < 2 \
                or tw.property("keep_top_tabs"):
            continue
        box = QWidget()
        box.setObjectName("SideTabsBox")
        if not _swap(tw, box):
            box.deleteLater()
            continue
        tw.setProperty("_gb_side", True)
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)
        lst = QListWidget(objectName="SectionList")
        lst.setAccessibleName("Tabs on this page")
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        h.addWidget(lst, 0)
        h.addWidget(tw, 1)
        tw._gb_side = _SideTabs(tw, box, lst)
        n += 1
    return n


def set_side_tabs(on: bool):
    """Settings → Appearance: switch every page's tabs between the left and the top."""
    from ..settings import settings
    settings.set(SIDE_KEY, bool(on))
    for key, st in list(_ALL.items()):
        try:
            st.apply(bool(on))
        except RuntimeError:
            _ALL.pop(key, None)
