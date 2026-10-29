"""The details side panel: click a person, group or Chromebook in any results table and their
details and actions slide in from the right – your list and filters stay where they are.

Esc or ✕ closes it; clicking another row shows that one. Double-click still opens the full
page. Settings & Updates → Appearance can turn it off.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFormLayout, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ..settings import settings

DRAWER_KEY = "ui/drawer"
SKIP_FIELDS = {"thumbnailphotourl", "thumbnailphotoetag", "etag", "kind", "id"}


def enabled() -> bool:
    return bool(settings.get(DRAWER_KEY, True))


def classify(win, row: dict) -> tuple[str, str]:
    """('user'|'group'|'device'|'', key) for a table row."""
    from .app_actions import EMAIL_COLS, SERIAL_COLS
    heads = {(k or "").lower(): k for k in row}
    for c in SERIAL_COLS:
        if c in heads and row.get(heads[c]):
            return "device", row[heads[c]]
    for c in EMAIL_COLS:
        if c in heads and "@" in (row.get(heads[c]) or ""):
            e = row[heads[c]].strip()
            groups = {g["email"].lower() for g in getattr(win.directory, "groups", [])}
            return ("group" if e.lower() in groups else "user"), e
    return "", ""


class DetailDrawer(QFrame):
    WIDTH = 440

    def __init__(self, win):
        super().__init__(win, objectName="Drawer")
        self.win = win
        self.setAttribute(Qt.WA_StyledBackground, True)
        fx = QGraphicsDropShadowEffect(self)
        fx.setBlurRadius(28)
        fx.setOffset(-4, 0)
        fx.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(fx)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        head = QWidget(objectName="DrawerHead")
        head.setAttribute(Qt.WA_StyledBackground, True)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 18, 12, 14)
        hl.setSpacing(14)
        self.avatar = QLabel()
        self.avatar.setFixedSize(48, 48)
        self.avatar.setStyleSheet("background:transparent;")
        hl.addWidget(self.avatar, 0, Qt.AlignTop)
        tv = QVBoxLayout()
        tv.setSpacing(2)
        self.title = QLabel("", objectName="DrawerTitle")
        self.title.setWordWrap(True)
        self.title.setTextFormat(Qt.PlainText)
        self.sub = QLabel("", objectName="Muted")
        self.sub.setTextFormat(Qt.PlainText)
        self.sub.setWordWrap(True)
        self.sub.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tv.addWidget(self.title)
        tv.addWidget(self.sub)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        tv.addLayout(self.chips)
        hl.addLayout(tv, 1)
        close = QPushButton("✕", objectName="DrawerClose")
        close.setToolTip("Close (Esc)")
        close.setFixedSize(34, 34)
        close.clicked.connect(self.close_drawer)
        hl.addWidget(close, 0, Qt.AlignTop)
        outer.addWidget(head)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.NoFrame)
        body = QWidget(objectName="DrawerBody")
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(20, 14, 20, 20)
        self.body.setSpacing(12)
        sc.setWidget(body)
        outer.addWidget(sc, 1)
        self.anim = QPropertyAnimation(self, b"pos", self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.esc = QShortcut(QKeySequence("Esc"), win, activated=self.close_drawer)
        self.esc.setEnabled(False)
        self.key = ("", "")
        self.hide()

    # ------------------------------------------------------------ place ---
    def _geom(self):
        win = self.win
        top = 0
        try:
            bar = win.findChild(QWidget, "TopBar")
            if bar is not None and bar.isVisible():
                top = bar.mapTo(win, QPoint(0, bar.height())).y()
        except Exception:  # noqa: BLE001
            pass
        sb = win.statusBar().height() if win.statusBar() and win.statusBar().isVisible() else 0
        w = min(self.WIDTH, max(320, win.width() // 3))
        return w, top, max(200, win.height() - top - sb)

    def place(self):
        if not self.isVisible():
            return
        w, top, h = self._geom()
        self.resize(w, h)
        self.move(self.win.width() - w, top)

    # ------------------------------------------------------------- show ---
    def show_row(self, row: dict):
        kind, key = classify(self.win, row)
        if not kind:
            return False
        self.key = (kind, key)
        self._fill(kind, key, row)
        w, top, h = self._geom()
        self.resize(w, h)
        if not self.isVisible():
            self.move(self.win.width(), top)
            self.show()
            self.anim.stop()
            self.anim.setStartValue(QPoint(self.win.width(), top))
            self.anim.setEndValue(QPoint(self.win.width() - w, top))
            self.anim.start()
        else:
            self.move(self.win.width() - w, top)
        self.raise_()
        self.esc.setEnabled(True)
        return True

    def close_drawer(self):
        if not self.isVisible():
            return
        self.esc.setEnabled(False)
        self.anim.stop()
        self.hide()

    # ------------------------------------------------------------ build ---
    def _clear(self):
        while self.body.count():
            it = self.body.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        while self.chips.count():
            it = self.chips.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _chip(self, text, kind="info"):
        from .person_header import CHIP, CHIP_DARK
        from .theme import is_dark
        bg, fg = (CHIP_DARK if is_dark() else CHIP)[kind]
        lab = QLabel(text)
        lab.setTextFormat(Qt.PlainText)
        lab.setStyleSheet(f"background:{bg};color:{fg};border-radius:9px;padding:2px 8px;"
                          "font-size:8.5pt;font-weight:600;")
        self.chips.addWidget(lab)

    def _copy_button(self, value: str):
        from PySide6.QtWidgets import QApplication, QToolButton
        from .icons import set_icon
        b = QToolButton(objectName="CellCopy")
        set_icon(b, "copy", None, 16)
        b.setToolTip(f"Copy {value}")
        b.setAccessibleName("Copy")

        def go():
            QApplication.clipboard().setText(value)
            if hasattr(self.win, "toasts"):
                self.win.toasts.show(f"Copied {value}", "ok", ms=2500, remember=False)
        b.clicked.connect(go)
        return b

    def _section(self, title):
        lab = QLabel(title.upper(), objectName="DrawerSection")
        self.body.addWidget(lab)

    def _fill(self, kind, key, row):
        from .home_widgets import avatar_pixmap
        from .person_header import initials
        from .widgets import nice_header, button
        self._clear()
        d = self.win.directory
        if kind == "user":
            u = next((u for u in getattr(d, "users", []) or []
                      if (u.get("email") or "").lower() == key.lower()), {}) or {}
            name = u.get("name") or row.get("name.fullName") or row.get("Name") or key
            self.avatar.setPixmap(avatar_pixmap(initials(name, key), key, 48))
            self.title.setText(name)
            self.sub.setText(key)
            susp = u.get("suspended") if u else str(row.get("suspended", "")).lower() == "true"
            self._chip("Suspended" if susp else "Active", "bad" if susp else "good")
            ou = u.get("ou") or row.get("orgUnitPath", "")
            try:
                from .. import ou_map
                c = ou_map.classify(ou) if ou else {}
                if c.get("grade"):
                    from .pages.home import _grade
                    self._chip(_grade(c["grade"]))
                if c.get("school"):
                    self._chip(c["school"])
            except Exception:  # noqa: BLE001
                pass
            if u.get("last_login"):
                self._chip("Last sign-in " + str(u["last_login"])[:10])
            opener = ("Open in Student lookup", lambda: self.win.open_recent(
                {"kind": "user", "value": key}))
        elif kind == "group":
            g = next((g for g in getattr(d, "groups", []) or []
                      if (g.get("email") or "").lower() == key.lower()), {}) or {}
            self.avatar.setPixmap(avatar_pixmap("", key, 48, round_=False, icon_name="group"))
            self.title.setText(g.get("name") or key)
            self.sub.setText(key)
            self._chip("Group")
            opener = ("Open the group", lambda: self.win.open_group(key))
        else:
            self.avatar.setPixmap(avatar_pixmap("", key, 48, round_=False,
                                                icon_name="laptop"))
            low = {(k or "").lower(): v for k, v in row.items()}
            self.title.setText(key)
            self.sub.setText(" · ".join(x for x in (low.get("model", ""),
                                                    low.get("annotatedassetid", ""))
                                        if x) or "Chromebook")
            st = (low.get("status") or "").upper()
            if st:
                self._chip(st.title(), "good" if st == "ACTIVE" else "warn")
            if low.get("annotateduser"):
                self._chip(low["annotateduser"])
            opener = ("Open the Chromebook", lambda: self.win.open_device(key))
        self.chips.addStretch(1)
        top = button(opener[0], "primary", opener[1])
        self.body.addWidget(top)
        # actions (the same ones as right-click), most useful first
        try:
            acts = [a for a in self.win.context_actions([row]) if a[0] != "-" and a[1]]
        except Exception:  # noqa: BLE001
            acts = []
        acts = [a for a in acts if not a[0].startswith(("Open ", "Open group"))]
        if acts:
            self._section("Actions")
            from .widgets import ResultsTable
            short = ResultsTable._short
            grid = QWidget()
            gl = QVBoxLayout(grid)
            gl.setContentsMargins(0, 0, 0, 0)
            gl.setSpacing(6)
            for label, fn, risky in acts[:9]:
                b = button(short(label, 1).lstrip("★ "), "danger" if risky else "", fn)
                b.setToolTip(label)
                b.setStyleSheet("text-align:left;")
                gl.addWidget(b)
            self.body.addWidget(grid)
        # details from the row
        fields = [(k, v) for k, v in row.items()
                  if k and str(v).strip() and k.split(".")[-1].lower() not in SKIP_FIELDS]
        if fields:
            self._section("Details")
            box = QWidget()
            form = QFormLayout(box)
            form.setContentsMargins(0, 0, 0, 0)
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(6)
            from .friendly import enabled, friendly
            from .widgets import ResultsTable as _RT
            nice = enabled()                  # Settings → Appearance → friendly values
            for k, v in fields[:24]:
                lab = QLabel(nice_header(k).title(), objectName="Muted")
                shown = friendly(str(v)) if nice else str(v)
                val = QLabel(shown)
                val.setTextFormat(Qt.PlainText)   # values come from Google – never markup
                val.setWordWrap(True)
                val.setTextInteractionFlags(Qt.TextSelectableByMouse)
                if shown != str(v):
                    val.setToolTip(str(v))
                if "@" in str(v) or k.split(".")[-1].lower() in _RT.COPY_COLS:
                    holder = QWidget()
                    hl = QHBoxLayout(holder)
                    hl.setContentsMargins(0, 0, 0, 0)
                    hl.setSpacing(6)
                    hl.addWidget(val, 1)
                    hl.addWidget(self._copy_button(str(v)))
                    form.addRow(lab, holder)
                else:
                    form.addRow(lab, val)
            self.body.addWidget(box)
        self.body.addStretch(1)
