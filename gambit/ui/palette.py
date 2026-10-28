"""Ctrl+K: one box to jump to anything – people, groups, org units, Chromebooks, pages,
actions (“Reset John Doe's password”) – with the keyboard."""

from __future__ import annotations

import re

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QGraphicsDropShadowEffect, QLineEdit, QListWidget, QListWidgetItem,
    QVBoxLayout,
)

SERIAL_RE = re.compile(r"^[A-Za-z0-9]{6,20}$")


class CommandPalette(QDialog):
    def __init__(self, win):
        super().__init__(win, Qt.FramelessWindowHint | Qt.Dialog)
        self.win = win
        self.setObjectName("Palette")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        box = QFrame(objectName="PaletteBox")
        box.setAttribute(Qt.WA_StyledBackground, True)
        sh = QGraphicsDropShadowEffect(box)
        sh.setBlurRadius(48)
        sh.setOffset(0, 12)
        from PySide6.QtGui import QColor
        sh.setColor(QColor(16, 24, 40, 90))
        box.setGraphicsEffect(sh)
        outer.addWidget(box)
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.input = QLineEdit(objectName="PaletteInput")
        self.input.setPlaceholderText("Search people, Chromebooks, pages or actions…")
        from .icons import icon
        self.input.addAction(icon("search"), QLineEdit.LeadingPosition)
        self.input.textChanged.connect(self.refresh)
        self.input.installEventFilter(self)
        v.addWidget(self.input)
        self.list = QListWidget(objectName="PaletteList")
        from PySide6.QtCore import QSize
        self.list.setIconSize(QSize(18, 18))
        self.list.itemActivated.connect(self._run)
        self.list.itemClicked.connect(self._run)
        v.addWidget(self.list, 1)
        w = min(680, max(480, win.width() - 200))
        self.resize(w + 48, 520)
        g = win.geometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 70)
        self.refresh("")

    # ---------------------------------------------------------- results ---
    def _head(self, text):
        it = QListWidgetItem(text)
        it.setFlags(Qt.NoItemFlags)
        f = it.font()
        f.setPointSizeF(f.pointSizeF() * 0.8)
        f.setBold(True)
        it.setFont(f)
        self.list.addItem(it)

    def _add(self, text, fn, icon_name="dot", sub=""):
        from .icons import icon
        it = QListWidgetItem(icon(icon_name), text + (f"   ·  {sub}" if sub else ""))
        it.setData(Qt.UserRole, fn)
        self.list.addItem(it)

    def refresh(self, text: str):
        from .. import user_prefs as up
        from ..intents import INTENTS
        from .icons import PAGE
        from .main_window import PAGES
        q = (text or "").strip().lower()
        self.list.clear()
        w, d = self.win, self.win.directory
        if not q:
            rec = up.recent(6)
            if rec:
                self._head("RECENT")
                for r in rec:
                    self._add(r.get("label") or r["value"], lambda r=r: w.open_recent(r),
                              {"user": "user", "device": "laptop", "group": "group",
                               "ou": "tree"}[r["kind"]],
                              r["value"] if r.get("label") != r["value"] else "")
            self._head("PAGES")
            for n in (up.pinned() or ["Student lookup", "Users", "Chromebook fleet",
                                      "Approvals", "Schedules"])[:6]:
                self._add(n, lambda n=n: w._go_safe(n), PAGE.get(n, "dot"))
            self._select_first()
            return
        people = [u for u in d.users if q in u["email"].lower() or
                  q in (u.get("name") or "").lower()][:6]
        if people:
            self._head("PEOPLE")
            for u in people:
                self._add(u.get("name") or u["email"],
                          lambda u=u: w.open_recent({"kind": "user", "value": u["email"]}),
                          "user", f"{u['email']} · {u.get('ou', '')}")
            top = people[0]
            nm = top.get("name") or top["email"]
            self._head("ACTIONS")
            self._add(f"Check everything about {nm}",
                      lambda e=top["email"]: self._check(e), "check-circle")
            self._add(f"Reset {nm}'s password", lambda e=top["email"]: self._reset(e), "key")
            self._add(f"Print a card for {nm}", lambda e=top["email"]: self._card(e),
                      "printer")
            self._add(f"Timeline for {nm}", lambda e=top["email"]: w.open_timeline(e),
                      "history")
        groups = [g for g in d.groups if q in g["email"].lower() or
                  q in (g.get("name") or "").lower()][:3]
        if groups:
            self._head("GROUPS")
            for g in groups:
                self._add(g.get("name") or g["email"], lambda g=g: w.open_group(g["email"]),
                          "group", g["email"])
        ous = [o for o in d.ous if q in o.lower()][:3]
        if ous:
            self._head("ORG UNITS")
            for o in ous:
                self._add(o, lambda o=o: w.open_ou(o), "tree")
        raw = (text or "").strip()
        if SERIAL_RE.match(raw) and any(c.isdigit() for c in raw) and not people:
            self._head("CHROMEBOOK")
            self._add(f"Open Chromebook {raw.upper()}", lambda: w.open_device(raw.upper()),
                      "laptop")
        pages = [n for n, _c in PAGES if q in n.lower()][:6]
        acts = [it for it in INTENTS if q in it[0].lower() or q in it[1].lower()][:5]
        if pages:
            self._head("PAGES")
            for n in pages:
                self._add(n, lambda n=n: w._go_safe(n), PAGE.get(n, "dot"))
        if acts:
            self._head("DO SOMETHING")
            for it in acts:
                self._add(it[0], lambda it=it: w.do_intent(it), PAGE.get(it[2], "sparkle"),
                          it[2])
        if hasattr(w, "helper"):
            self._head("ASK")
            self._add(f"Ask the Helper: “{raw}”", lambda: (w.helper.show(), w.helper.ask(raw)),
                      "chat")
        self._select_first()

    def _select_first(self):
        for i in range(self.list.count()):
            if self.list.item(i).flags() & Qt.ItemIsEnabled:
                self.list.setCurrentRow(i)
                return

    # ------------------------------------------------------------ actions ---
    def _check(self, email):
        from .person_check_dialog import PersonCheckDialog
        PersonCheckDialog(self.win.pages["Home"], email).exec()

    def _reset(self, email):
        self.win.open_lookup(email)
        p = self.win.pages.get("Student lookup")
        if p is not None:
            p.reset()

    def _card(self, email):
        self.win.open_lookup(email)
        p = self.win.pages.get("Student lookup")
        if p is not None:
            p.print_card()

    def _run(self, it):
        fn = it.data(Qt.UserRole) if it else None
        if fn is None:
            return
        self.accept()
        fn()

    def _move(self, step):
        n = self.list.count()
        i = self.list.currentRow()
        for _ in range(n):
            i = (i + step) % n
            if self.list.item(i).flags() & Qt.ItemIsEnabled:
                self.list.setCurrentRow(i)
                return

    def eventFilter(self, obj, e):
        if obj is self.input and e.type() == QEvent.KeyPress:
            k = e.key()
            if k in (Qt.Key_Down, Qt.Key_Tab):
                self._move(1)
                return True
            if k in (Qt.Key_Up, Qt.Key_Backtab):
                self._move(-1)
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self._run(self.list.currentItem())
                return True
            if k == Qt.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(obj, e)
