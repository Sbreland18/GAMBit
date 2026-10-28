"""The person card at the top of Student lookup: avatar, name, email and status chips."""

from __future__ import annotations

import hashlib

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

CHIP = {"good": ("#DCFCE7", "#166534"), "bad": ("#FEE2E2", "#991B1B"),
        "warn": ("#FEF3C7", "#92400E"), "info": ("#EEF2F7", "#334155")}
CHIP_DARK = {"good": ("#14351F", "#86EFAC"), "bad": ("#3B1C1C", "#FCA5A5"),
             "warn": ("#3A2A06", "#FDE68A"), "info": ("#1F2937", "#CBD5E1")}
AVATAR = [("#DBEAFE", "#1E3A8A"), ("#DCFCE7", "#14532D"), ("#FCE7F3", "#831843"),
          ("#EDE9FE", "#4C1D95"), ("#FFEDD5", "#7C2D12"), ("#CCFBF1", "#134E4A")]


def initials(name: str, email: str = "") -> str:
    parts = [p for p in (name or "").replace(".", " ").split() if p[:1].isalpha()]
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    base = parts[0] if parts else (email.split("@")[0] if email else "?")
    return base[:2].upper()


def avatar_colors(key: str) -> tuple[str, str]:
    h = int(hashlib.md5((key or "").lower().encode()).hexdigest()[:4], 16)
    return AVATAR[h % len(AVATAR)]


class PersonHeader(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent, objectName="Card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(self)
        h.setContentsMargins(20, 16, 20, 16)
        h.setSpacing(16)
        self.avatar = QLabel()
        self.avatar.setFixedSize(60, 60)
        self.avatar.setAlignment(Qt.AlignCenter)
        h.addWidget(self.avatar, 0, Qt.AlignTop)
        v = QVBoxLayout()
        v.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.name = QLabel("")
        self.name.setStyleSheet("font-size:17pt;font-weight:700;")
        self.email = QLabel("", objectName="Muted")
        self.email.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top.addWidget(self.name)
        top.addWidget(self.email)
        top.addStretch(1)
        v.addLayout(top)
        self.chips_w = QWidget()
        self.chips = QHBoxLayout(self.chips_w)
        self.chips.setContentsMargins(0, 0, 0, 0)
        self.chips.setSpacing(6)
        v.addWidget(self.chips_w)
        self.extra = QLabel("", objectName="Muted")
        self.extra.setWordWrap(True)
        v.addWidget(self.extra)
        h.addLayout(v, 1)
        self.message("Type a student's name or email above and press Enter.")

    def _clear(self):
        while self.chips.count():
            it = self.chips.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def message(self, text: str):
        self._clear()
        self.avatar.hide()
        self.name.setText("")
        self.email.setText("")
        self.extra.setText(text)

    def set_person(self, name: str, email: str, chips: list[tuple[str, str]], extra: str = ""):
        from .theme import is_dark
        self._clear()
        bg, fg = avatar_colors(email)
        self.avatar.setText(initials(name, email))
        self.avatar.setStyleSheet(f"background:{bg};color:{fg};border-radius:30px;"
                                  "font-size:16pt;font-weight:700;")
        self.avatar.show()
        self.name.setText(name or email)
        self.email.setText(email if name else "")
        pal = CHIP_DARK if is_dark() else CHIP
        for text, kind in chips[:9]:
            b, f = pal.get(kind, pal["info"])
            c = QLabel(text)
            c.setStyleSheet(f"background:{b};color:{f};border-radius:10px;padding:3px 10px;"
                            "font-weight:600;font-size:8.5pt;")
            self.chips.addWidget(c)
        self.chips.addStretch(1)
        self.extra.setText(extra)

    def text(self) -> str:          # older code asked the card label for its text
        return " ".join(x for x in (self.name.text(), self.email.text(), self.extra.text())
                        if x)

    def setText(self, text: str):
        self.message(text)
