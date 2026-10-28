"""Customize Home in place: each box gets a small bar (drag handle, ↑, ↓, ✕); drag boxes to
reorder them, add boxes from “Add a box”, and click Done. Quick actions, number tiles,
links and notes are still chosen in “More options…”."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QMimeData, QObject, Qt, QTimer
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton

MIME = "application/x-gambit-home-box"


class _Handle(QLabel):
    def __init__(self, editor, key):
        super().__init__("⠿")
        self.editor, self.key = editor, key
        self.setObjectName("EditHandle")
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("Drag to move this box")
        self._press = None

    def mousePressEvent(self, e):
        self._press = e.position().toPoint()

    def mouseMoveEvent(self, e):
        if self._press is None or (e.position().toPoint() - self._press).manhattanLength() < 6:
            return
        drag = QDrag(self)
        md = QMimeData()
        md.setData(MIME, self.key.encode())
        drag.setMimeData(md)
        w = self.editor.page.sections.get(self.key)
        if w is not None:
            pm = w.grab().scaledToWidth(min(360, w.width()), Qt.SmoothTransformation)
            drag.setPixmap(pm)
        self._press = None
        drag.exec(Qt.MoveAction)
        self.editor.hide_marker()


class _Bar(QFrame):
    def __init__(self, editor, key, host):
        super().__init__(host, objectName="EditBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(self)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(2)
        from .. import home_layout as hl
        name = QLabel(hl.SECTIONS.get(key, key), objectName="EditName")
        h.addWidget(_Handle(editor, key))
        h.addWidget(name)
        for text, tip, fn in (("↑", "Move up", lambda: editor.move(key, -1)),
                              ("↓", "Move down", lambda: editor.move(key, 1)),
                              ("✕", "Remove this box from Home", lambda: editor.remove(key))):
            b = QPushButton(text, objectName="EditBtn")
            b.setToolTip(tip)
            b.setFixedSize(28, 28)
            b.clicked.connect(fn)
            h.addWidget(b)
        self.adjustSize()


class HomeEditor(QObject):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.on = False
        self.bars: dict[str, _Bar] = {}
        self.marker = QFrame(page.col, objectName="DropMarker")
        self.marker.setFixedHeight(4)
        self.marker.hide()
        page.col.setAcceptDrops(True)
        page.col.installEventFilter(self)

    # ------------------------------------------------------------ order ---
    def _layout(self):
        from .. import home_layout as hl
        return hl.layout(self.page._admin())

    def _save(self, items):
        from .. import home_layout as hl
        hl.save_layout(items)
        self.page.arrange()
        if self.on:
            QTimer.singleShot(0, self.refresh_bars)

    def visible_keys(self) -> list[str]:
        return [x["id"] for x in self._layout() if x["on"]]

    def move(self, key, step):
        items = self._layout()
        on = [x for x in items if x["on"]]
        i = next((n for n, x in enumerate(on) if x["id"] == key), None)
        if i is None:
            return
        j = max(0, min(len(on) - 1, i + step))
        on.insert(j, on.pop(i))
        self._save(on + [x for x in items if not x["on"]])

    def move_to(self, key, index):
        items = self._layout()
        on = [x for x in items if x["on"]]
        cur = next((x for x in on if x["id"] == key), None)
        if cur is None:
            return
        i = on.index(cur)
        on.pop(i)
        if index > i:
            index -= 1
        on.insert(max(0, min(len(on), index)), cur)
        self._save(on + [x for x in items if not x["on"]])

    def remove(self, key):
        items = self._layout()
        for x in items:
            if x["id"] == key:
                x["on"] = False
        self._save(items)

    def add(self, key):
        items = self._layout()
        for x in items:
            if x["id"] == key:
                x["on"] = True
        on = [x for x in items if x["on"] and x["id"] != key] + \
            [x for x in items if x["id"] == key]
        self._save(on + [x for x in items if not x["on"]])
        w = self.page.sections.get(key)
        if w is not None:
            QTimer.singleShot(50, lambda: self.page.scroll.ensureWidgetVisible(w))

    def add_menu(self, btn):
        from .. import home_layout as hl
        m = QMenu(btn)
        off = [x["id"] for x in self._layout() if not x["on"]]
        for k in off:
            m.addAction(hl.SECTIONS[k], lambda k=k: self.add(k))
        if not off:
            a = m.addAction("Every box is already on Home")
            a.setEnabled(False)
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    # ------------------------------------------------------------- mode ---
    def set_on(self, on: bool):
        self.on = on
        if on:
            self.refresh_bars()
        else:
            for b in self.bars.values():
                b.deleteLater()
            self.bars = {}
            self.hide_marker()

    def refresh_bars(self):
        for b in self.bars.values():
            b.deleteLater()
        self.bars = {}
        for k in self.visible_keys():
            w = self.page.sections.get(k)
            if w is None or not w.isVisibleTo(self.page):
                continue
            bar = _Bar(self, k, w)
            w.installEventFilter(self)
            self.bars[k] = bar
            self._place(k)
            bar.show()
            bar.raise_()

    def _place(self, k):
        bar, w = self.bars.get(k), self.page.sections.get(k)
        if bar is None or w is None:
            return
        bar.adjustSize()
        x = w.width() - bar.width() - 10
        # don't cover the box's own buttons along its top edge (e.g. Refresh now)
        from PySide6.QtWidgets import QAbstractButton
        for b in w.findChildren(QAbstractButton):
            if b.parent() is bar or bar.isAncestorOf(b) or not b.isVisible():
                continue
            from PySide6.QtCore import QPoint, QRect
            r = QRect(b.mapTo(w, QPoint(0, 0)), b.size())
            if r.top() < 8 + bar.height() and r.right() > x:
                x = min(x, r.left() - bar.width() - 8)
        bar.move(max(0, x), 8)
        bar.raise_()

    # ------------------------------------------------------- drag & drop ---
    def _index_at(self, y: int) -> tuple[int, int]:
        """(insert index among visible boxes, y of the gap) for a drop at y in col."""
        keys = [k for k in self.visible_keys() if k in self.page.sections and
                self.page.sections[k].isVisible()]
        col = self.page.col
        for n, k in enumerate(keys):
            w = self.page.sections[k]
            top = w.mapTo(col, w.rect().topLeft()).y()
            if y < top + w.height() / 2:
                return n, top - 9
        if keys:
            w = self.page.sections[keys[-1]]
            return len(keys), w.mapTo(col, w.rect().bottomLeft()).y() + 5
        return 0, 0

    def hide_marker(self):
        self.marker.hide()

    def eventFilter(self, obj, e):
        t = e.type()
        if obj is not self.page.col:
            if t == QEvent.Resize and self.on:
                k = next((k for k, w in self.page.sections.items() if w is obj), None)
                if k:
                    self._place(k)
            return False
        if not self.on:
            return False
        if t in (QEvent.DragEnter, QEvent.DragMove) and e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()
            _i, y = self._index_at(e.position().toPoint().y())
            self.marker.setGeometry(8, max(0, y), self.page.col.width() - 30, 4)
            self.marker.show()
            self.marker.raise_()
            return True
        if t == QEvent.DragLeave:
            self.hide_marker()
            return False
        if t == QEvent.Drop and e.mimeData().hasFormat(MIME):
            key = bytes(e.mimeData().data(MIME)).decode()
            i, _y = self._index_at(e.position().toPoint().y())
            e.acceptProposedAction()
            self.hide_marker()
            self.move_to(key, i)
            return True
        return False
