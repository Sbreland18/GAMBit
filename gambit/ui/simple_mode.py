"""Simple mode: for staff who only do the everyday jobs. Home becomes one search box and six
big buttons, and the sidebar shows only a handful of pages. Turn it on in Settings &
Updates → Appearance (or the user menu); “Leave simple mode” in the top bar turns it off.
Combine it with Help-desk mode (PIN) if you also want destructive actions locked away."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QWidget,
)

from ..settings import settings

KEY = "ui/simple"
PAGES = ("Home", "Student lookup", "Chromebooks", "Ticket queue", "Guide",
         "Settings & Updates")


def on() -> bool:
    return bool(settings.get(KEY, False))


class AskDialog(QDialog):
    """“Who?” (a person) or “Which Chromebook?” in one box."""

    def __init__(self, parent, directory, title: str, device: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 14)
        lay.addWidget(QLabel(title, objectName="MsgTitle"))
        if device:
            self.box = QLineEdit(placeholderText="Serial number or asset tag")
        else:
            from .pickers import PersonField
            self.box = PersonField(directory, "Student or staff member – name or email")
        self.box.returnPressed.connect(self.accept)
        lay.addWidget(self.box)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Continue")
        bb.button(QDialogButtonBox.Ok).setProperty("kind", "primary")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.box.setFocus()

    def value(self) -> str:
        if hasattr(self.box, "email"):
            e = self.box.email() or self.box.text().strip()
            return e if "@" in e else ""
        return self.box.text().strip()


class SimplePanel(QWidget):
    TASKS = (("Reset a password", "key", "reset"),
             ("Unlock / unsuspend", "lock", "unsuspend"),
             ("Fix sign-in problems", "check-circle", "check"),
             ("Print an account card", "printer", "card"),
             ("Find a Chromebook", "laptop", "device"),
             ("Ticket queue", "ticket", "tickets"))

    def __init__(self, home):
        super().__init__()
        self.home = home
        self.app = home.app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        lay.addWidget(QLabel("What do you need to do?", objectName="SectionTitle"))
        grid = QGridLayout()
        grid.setSpacing(14)
        from .icons import set_icon
        self.buttons = {}
        for i, (label, ic, key) in enumerate(self.TASKS):
            b = QPushButton(label, objectName="SimpleTile")
            set_icon(b, ic, None, 28)
            b.setIconSize(QSize(28, 28))
            b.setMinimumHeight(86)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.do(k))
            self.buttons[key] = b
            grid.addWidget(b, i // 3, i % 3)
        lay.addLayout(grid)
        self.refresh()

    def refresh(self):
        from ..integrations import ticketing as tk
        self.buttons["tickets"].setVisible(tk.configured() and tk.can("list"))

    def _ask(self, title, device=False) -> str:
        dlg = AskDialog(self, self.app.directory, title, device)
        return dlg.value() if dlg.exec() else ""

    def do(self, key: str):
        app = self.app
        if key == "tickets":
            app._go_safe("Ticket queue")
            return
        if key == "device":
            v = self._ask("Which Chromebook?", device=True)
            if v:
                if any(c in v for c in "-_.#") or v.isdigit():
                    app.open_asset(v)
                else:
                    app.open_device(v.upper())
            return
        who = self._ask({"reset": "Whose password?", "unsuspend": "Who should be unlocked?",
                         "check": "Who can't sign in?", "card": "Whose account card?"}[key])
        if not who:
            return
        if key == "check":
            from .person_check_dialog import PersonCheckDialog
            PersonCheckDialog(self.home, who).exec()
            return
        app.open_lookup(who)
        p = app.pages.get("Student lookup")
        if p is None:
            return
        {"reset": p.reset, "unsuspend": p.unsuspend, "card": p.print_card}[key]()
