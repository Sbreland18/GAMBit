"""Modern message windows: GAMbit's confirmations and messages as rounded cards with a title,
the message, and clear buttons (red for risky actions) instead of plain Windows boxes.

`install()` (called once at start-up from main.py) routes QMessageBox.question /
information / warning / critical through ModernMessage, so every existing call keeps working
and gets the new look. The return values are the usual QMessageBox buttons.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

SB = QMessageBox.StandardButton
ORDER = [SB.Ok, SB.Save, SB.SaveAll, SB.Open, SB.Yes, SB.YesToAll, SB.Retry, SB.Apply,
         SB.Ignore, SB.No, SB.NoToAll, SB.Discard, SB.Abort, SB.Reset, SB.RestoreDefaults,
         SB.Help, SB.Close, SB.Cancel]
LABEL = {SB.Ok: "OK", SB.Save: "Save", SB.SaveAll: "Save all", SB.Open: "Open",
         SB.Yes: "Yes", SB.YesToAll: "Yes to all", SB.Retry: "Try again", SB.Apply: "Apply",
         SB.Ignore: "Ignore", SB.No: "No", SB.NoToAll: "No to all", SB.Discard: "Don't save",
         SB.Abort: "Stop", SB.Reset: "Reset", SB.RestoreDefaults: "Restore defaults",
         SB.Help: "Help", SB.Close: "Close", SB.Cancel: "Cancel"}
POSITIVE = {SB.Ok, SB.Save, SB.SaveAll, SB.Open, SB.Yes, SB.YesToAll, SB.Retry, SB.Apply}
ESCAPE = [SB.Cancel, SB.No, SB.Close, SB.Abort, SB.Ok]
RISKY = re.compile(r"\b(delete|remove|suspend|wipe|disable|deprovision|transfer|erase|"
                   r"permanently|can't be undone|cannot be undone|sign (them|everyone) out|"
                   r"reset .*password|move .* org unit)\b", re.I)
PROBLEM = re.compile(r"\b(couldn't|could not|failed|error|not installed|can't|cannot)\b", re.I)
GENERIC_TITLES = {"", "gambit", "please confirm"}


def _plain(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


class ModernMessage(QDialog):
    def __init__(self, parent, kind: str, title: str, text: str, buttons=SB.Ok,
                 default=SB.NoButton):
        super().__init__(parent)
        self.setObjectName("ModernMsg")
        self.setWindowTitle(title or "GAMbit")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setMaximumWidth(680)
        self.result_button = SB.NoButton
        plain = _plain(text)
        if kind == "info" and PROBLEM.search(plain[:240]):
            kind = "warn"
        from .icons import icon
        from .home_widgets import tint
        ic, colr = {"question": ("help", "blue"), "info": ("check-circle", "blue"),
                    "warn": ("alert", "amber"), "error": ("x-circle", "red")}[kind]
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        body = QWidget(objectName="MsgBody")
        body.setAttribute(Qt.WA_StyledBackground, True)
        bl = QHBoxLayout(body)
        bl.setContentsMargins(24, 22, 24, 18)
        bl.setSpacing(16)
        badge = QLabel()
        badge.setFixedSize(40, 40)
        badge.setAlignment(Qt.AlignCenter)
        bg, fg = tint(colr)
        badge.setStyleSheet(f"background:{bg};border-radius:20px;")
        badge.setPixmap(icon(ic, fg, 22).pixmap(22, 22))
        bl.addWidget(badge, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(8)
        from .safe_html import open_link, set_label
        if (title or "").strip().lower() not in GENERIC_TITLES:
            head = QLabel(objectName="MsgTitle")
            head.setTextFormat(Qt.PlainText)
            head.setText(title)
            head.setWordWrap(True)
            col.addWidget(head)
        self.text_label = QLabel()
        set_label(self.text_label, text)        # values from Google can't inject markup
        self.text_label.setObjectName("MsgText")
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse |
                                                Qt.LinksAccessibleByMouse)
        self.text_label.setOpenExternalLinks(False)
        self.text_label.linkActivated.connect(open_link)
        if len(plain) > 900 or plain.count("\n") > 16:
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setFrameShape(QScrollArea.NoFrame)
            sc.setWidget(self.text_label)
            sc.setMinimumHeight(260)
            sc.setMaximumHeight(440)
            col.addWidget(sc)
        else:
            col.addWidget(self.text_label)
        bl.addLayout(col, 1)
        root.addWidget(body, 1)

        foot = QWidget(objectName="MsgFoot")
        foot.setAttribute(Qt.WA_StyledBackground, True)
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(24, 12, 24, 14)
        fl.addStretch(1)
        chosen = [b for b in ORDER if int(buttons) & int(b)] or [SB.Ok]
        if default == SB.NoButton or default not in chosen:
            default = next((b for b in chosen if b in POSITIVE), chosen[0])
        risky = kind == "question" and bool(RISKY.search(plain))
        # cancel-type buttons first, the main action last (Windows 11 order)
        for b in sorted(chosen, key=lambda x: x in POSITIVE):
            btn = QPushButton(LABEL.get(b, "OK"))
            if b in POSITIVE:
                btn.setProperty("kind", "danger" if risky and b in (SB.Yes, SB.Ok)
                                else "primary")
            btn.setAutoDefault(b == default)
            btn.setDefault(b == default)
            btn.clicked.connect(lambda _=False, b=b: self._choose(b))
            fl.addWidget(btn)
            if b == default:
                btn.setFocus()
        root.addWidget(foot)
        self._escape = next((b for b in ESCAPE if b in chosen), chosen[-1])

    def _choose(self, b):
        self.result_button = b
        self.accept() if b in POSITIVE else self.reject()

    def reject(self):
        if self.result_button == SB.NoButton:
            self.result_button = self._escape
        super().reject()

    def run(self):
        try:
            self.exec()
            return self.result_button if self.result_button != SB.NoButton else self._escape
        finally:
            self.deleteLater()      # messages can hold passwords – don't keep them around


def _make(kind, default_buttons):
    def fn(parent, title, text, buttons=default_buttons, defaultButton=SB.NoButton):
        return ModernMessage(parent, kind, title, text, buttons, defaultButton).run()
    return staticmethod(fn)


_installed = False


def install():
    """Route the standard message boxes through ModernMessage (start-up only)."""
    global _installed
    if _installed:
        return
    _installed = True
    QMessageBox.question = _make("question", SB.Yes | SB.No)
    QMessageBox.information = _make("info", SB.Ok)
    QMessageBox.warning = _make("warn", SB.Ok)
    QMessageBox.critical = _make("error", SB.Ok)
