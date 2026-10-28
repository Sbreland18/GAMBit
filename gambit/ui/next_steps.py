"""“What's next?” after a job: the result, plus buttons for the usual follow-ups (print the
account card, open the person, add them to a class, transfer their files…) so you don't have
to hunt for the next page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class NextSteps(QDialog):
    def __init__(self, parent, title: str, text: str, actions=(), copy_text: str = "",
                 ok: bool = True):
        super().__init__(parent)
        self.setObjectName("ModernMsg")
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        self.chosen = None
        from .home_widgets import tint
        from .icons import icon
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        body = QWidget(objectName="MsgBody")
        body.setAttribute(Qt.WA_StyledBackground, True)
        bl = QHBoxLayout(body)
        bl.setContentsMargins(24, 22, 24, 16)
        bl.setSpacing(16)
        badge = QLabel()
        badge.setFixedSize(40, 40)
        badge.setAlignment(Qt.AlignCenter)
        bg, fg = tint("green" if ok else "amber")
        badge.setStyleSheet(f"background:{bg};border-radius:20px;")
        badge.setPixmap(icon("check-circle" if ok else "alert", fg, 22).pixmap(22, 22))
        bl.addWidget(badge, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(8)
        col.addWidget(QLabel(title, objectName="MsgTitle"))
        lab = QLabel(text, objectName="MsgText")
        lab.setWordWrap(True)
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        col.addWidget(lab)
        if copy_text:
            cp = QPushButton("Copy password")
            cp.clicked.connect(lambda: (QApplication.clipboard().setText(copy_text),
                                        cp.setText("Copied")))
            col.addWidget(cp, 0, Qt.AlignLeft)
        if actions:
            col.addSpacing(6)
            col.addWidget(QLabel("WHAT'S NEXT?", objectName="DrawerSection"))
            grid = QHBoxLayout()
            grid.setSpacing(8)
            for label, fn in actions:
                b = QPushButton(label)
                b.clicked.connect(lambda _=False, fn=fn: self._pick(fn))
                grid.addWidget(b)
            grid.addStretch(1)
            col.addLayout(grid)
        bl.addLayout(col, 1)
        root.addWidget(body, 1)
        foot = QWidget(objectName="MsgFoot")
        foot.setAttribute(Qt.WA_StyledBackground, True)
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(24, 12, 24, 14)
        fl.addStretch(1)
        done = QPushButton("Done")
        done.setProperty("kind", "primary")
        done.setDefault(True)
        done.clicked.connect(self.accept)
        fl.addWidget(done)
        root.addWidget(foot)

    def _pick(self, fn):
        self.chosen = fn
        self.accept()

    def run(self):
        self.exec()
        if self.chosen is not None:
            self.chosen()


def for_new_account(win, email: str, extra_note: str = "", sheet=None):
    """Follow-ups after creating an account."""
    def open_person():
        win.open_recent({"kind": "user", "value": email})

    def card():
        win.open_lookup(email)
        p = win.pages.get("Student lookup")
        if p is not None and hasattr(p, "print_card"):
            p.print_card()

    def to_class():
        win._go_safe("Classroom")
    acts = [("Open the person", open_person), ("Print account card", card)]
    if sheet is not None:
        acts.insert(1, ("Print welcome sheet", sheet))
    acts.append(("Add to a class", to_class))
    return acts


def for_suspended(win, emails: list[str]):
    """Follow-ups after suspending accounts (shown from the pop-up's “Next” button)."""
    one = emails[0] if len(emails) == 1 else ""

    def move():
        win._go_safe("Users")
        p = win.pages.get("Users")
        if p is not None and one and hasattr(p, "m_email"):
            try:
                p.m_email.setText(one)
                from PySide6.QtWidgets import QTabWidget
                p.findChild(QTabWidget).setCurrentIndex(0)
            except Exception:  # noqa: BLE001
                pass

    def transfer():
        win._go_safe("Google Drive")
        p = win.pages.get("Google Drive")
        if p is not None and hasattr(p, "tabs"):
            for i in range(p.tabs.count()):
                if p.tabs.tabText(i) == "Transfer files":
                    p.tabs.setCurrentIndex(i)
            if one and hasattr(p, "t_from"):
                p.t_from.setText(one)

    def sign_out():
        for e in emails:
            win.runner.run(["user", e, "signout"])
    acts = [("Move to another org unit", move), ("Sign out everywhere", sign_out)]
    if one:
        acts.insert(1, ("Transfer their files", transfer))
    return acts


def menu_for(win, actions, anchor=None):
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QMenu
    m = QMenu(win)
    for label, fn in actions:
        m.addAction(label, fn)
    m.exec(QCursor.pos() if anchor is None else anchor)
