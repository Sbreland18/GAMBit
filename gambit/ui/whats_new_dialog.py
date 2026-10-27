"""What's new – once after an update, and any time from Help (Ctrl+Shift+N)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from ..version import __version__
from .widgets import button


class WhatsNewDialog(QDialog):
    def __init__(self, win, items: list[dict]):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(f"What's new in GAMbit {__version__}")
        self.resize(640, 560)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"<b style='font-size:14pt'>What's new in GAMbit {__version__}</b>"))
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        for e in items:
            card = QFrame(objectName="Card")
            h = QHBoxLayout(card)
            t = QLabel(f"<b>{e['title']}</b><br>{e['text']}")
            t.setWordWrap(True)
            h.addWidget(t, 1)
            if e.get("page") and e["page"] in getattr(win, "pages", {}):
                h.addWidget(button("Open", slot=lambda _=False, p=e["page"]: self._open(p)))
            lay.addWidget(card)
        lay.addStretch(1)
        area.setWidget(inner)
        v.addWidget(area, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Ctrl+Shift+N shows this again.", objectName="Muted"))
        row.addStretch(1)
        row.addWidget(button("Got it", "primary", self.accept))
        v.addLayout(row)

    def _open(self, page):
        self.accept()
        self.win._go_safe(page)
