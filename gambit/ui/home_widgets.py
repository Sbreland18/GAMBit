"""The pieces of the modern Home page: number tiles with a trend line or a meter, the big
look-up box, and recently-viewed rows with avatars."""

from __future__ import annotations

import datetime

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QVBoxLayout, QWidget,
)

from .theme import is_dark, tokens

# status → (light text, dark text)
STATUS_TEXT = {"good": ("#15803D", "#86EFAC"), "warn": ("#B45309", "#FDE68A"),
               "bad": ("#B91C1C", "#FCA5A5"), None: (None, None)}
# tile icon tint (light bg, light fg, dark bg, dark fg)
TINT = {"blue": ("#E8F0FE", "#1D4ED8", "#1B2A44", "#93C5FD"),
        "green": ("#E7F7EE", "#15803D", "#14301F", "#86EFAC"),
        "amber": ("#FEF6E4", "#B45309", "#3A2A06", "#FDE68A"),
        "red": ("#FDECEC", "#B91C1C", "#3B1C1C", "#FCA5A5"),
        "violet": ("#F1EBFE", "#6D28D9", "#2A1F45", "#C4B5FD"),
        "slate": ("#EEF2F7", "#334155", "#1F2937", "#CBD5E1")}


def tint(name: str) -> tuple[str, str]:
    lb, lf, db, df = TINT.get(name, TINT["slate"])
    return (db, df) if is_dark() else (lb, lf)


def status_color(status) -> str:
    light, dark = STATUS_TEXT.get(status, (None, None))
    return (dark if is_dark() else light) or tokens()["muted"]


class Spark(QWidget):
    """A thin trend line (the last 30 days of one number). Hidden with < 2 points."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points: list[float] = []
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_points(self, pts):
        self.points = [float(p) for p in (pts or [])][-30:]
        self.setVisible(len(self.points) >= 2)
        self.update()

    def paintEvent(self, _e):
        if len(self.points) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        lo, hi = min(self.points), max(self.points)
        span = (hi - lo) or 1
        n = len(self.points)
        pts = [QPointF(2 + i * (w - 4) / (n - 1), h - 3 - (v - lo) / span * (h - 6))
               for i, v in enumerate(self.points)]
        path = QPainterPath(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        pen = QPen(QColor(tokens()["accent_text"] if is_dark() else tokens()["accent"]), 2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)
        p.setBrush(pen.color())
        p.drawEllipse(pts[-1], 3, 3)
        p.end()


class Meter(QWidget):
    """A rounded progress meter (licenses used of what you bought)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frac = 0.0
        self.setFixedHeight(8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.hide()

    def set_frac(self, frac):
        if frac is None:
            self.hide()
            return
        self.frac = max(0.0, min(1.0, float(frac)))
        self.show()
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        r = QRectF(0, 0, self.width(), self.height())
        p.setBrush(QColor(tokens()["surface2"] if not is_dark() else "#253041"))
        p.drawRoundedRect(r, 4, 4)
        col = "#F59E0B" if self.frac >= 0.9 else tokens()["accent"]
        p.setBrush(QColor(col))
        p.drawRoundedRect(QRectF(0, 0, max(8.0, self.width() * self.frac), self.height()),
                          4, 4)
        p.end()


class StatTile(QFrame):
    """A clickable number: label and icon on top, the number, a trend line or meter, and a
    coloured status line."""

    clicked = Signal()

    def __init__(self, label: str, hint: str = "", icon_name: str = "chart",
                 color: str = "blue"):
        super().__init__(objectName="Card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(hint)
        self.icon_name, self.color = icon_name, color
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.label = QLabel(label, objectName="TileLabel")
        self.label.setWordWrap(True)
        top.addWidget(self.label, 1, Qt.AlignTop)
        self.badge = QLabel()
        self.badge.setFixedSize(32, 32)
        self.badge.setAlignment(Qt.AlignCenter)
        top.addWidget(self.badge, 0, Qt.AlignTop)
        v.addLayout(top)
        self.value = QLabel("—", objectName="TileValue")
        v.addWidget(self.value)
        self.spark = Spark()
        self.spark.hide()
        v.addWidget(self.spark)
        self.meter = Meter()
        v.addWidget(self.meter)
        self.sub = QLabel("", objectName="TileSub")
        self.sub.setWordWrap(True)
        v.addWidget(self.sub)
        v.addStretch(1)
        self.status = None
        self.restyle()

    def restyle(self):
        from .icons import icon
        bg, fg = tint(self.color)
        self.badge.setStyleSheet(f"background:{bg};border-radius:9px;")
        self.badge.setPixmap(icon(self.icon_name, fg, 18).pixmap(18, 18))
        self.sub.setStyleSheet(f"color:{status_color(self.status)};"
                               f"{'font-weight:normal;' if self.status is None else ''}")

    def set(self, value, sub: str = "", status=None, trend=None, meter=None):
        self.value.setText(f"{value:,}" if isinstance(value, int) else str(value))
        self.status = status
        self.sub.setText(sub)
        self.sub.setVisible(bool(sub))
        if trend is not None:
            self.spark.set_points(trend)
        self.meter.set_frac(meter)
        if meter is not None:
            self.spark.hide()
        self.restyle()

    def mousePressEvent(self, e):
        self.clicked.emit()
        super().mousePressEvent(e)


class BigSearch(QFrame):
    """The large rounded look-up field from the mock-up (icon + borderless line edit)."""

    def __init__(self, editor: QLineEdit, parent=None):
        super().__init__(parent, objectName="BigSearch")
        self.setAttribute(Qt.WA_StyledBackground, True)
        from .icons import icon
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 2, 10, 2)
        h.setSpacing(8)
        mark = QLabel()
        mark.setStyleSheet("background:transparent;")
        mark.setPixmap(icon("search", tokens()["muted"], 20).pixmap(20, 20))
        h.addWidget(mark)
        self.editor = editor
        editor.setFrame(False)
        h.addWidget(editor, 1)


def avatar_pixmap(text: str, key: str, size: int = 34, round_: bool = True,
                  icon_name: str = "") -> QPixmap:
    from .person_header import avatar_colors
    from .icons import icon
    if icon_name:
        bg, fg = tint("slate")
    else:
        bg, fg = avatar_colors(key)
        if is_dark():
            bg, fg = "#1E3A8A", "#DBEAFE"
    from PySide6.QtWidgets import QApplication
    dpr = QApplication.instance().devicePixelRatio() if QApplication.instance() else 1.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(bg))
    r = QRectF(0, 0, size, size)
    if round_:
        p.drawEllipse(r)
    else:
        p.drawRoundedRect(r, 9, 9)
    if icon_name:
        s = int(size * 0.55)
        p.drawPixmap(int((size - s) / 2), int((size - s) / 2),
                     icon(icon_name, fg, s).pixmap(s, s))
    else:
        f = QFont()
        f.setBold(True)
        f.setPixelSize(int(size * 0.38))
        p.setFont(f)
        p.setPen(QColor(fg))
        p.drawText(r, Qt.AlignCenter, text)
    p.end()
    return pm


def ago(when: str) -> str:
    try:
        t = datetime.datetime.fromisoformat(when)
    except (TypeError, ValueError):
        return ""
    mins = int((datetime.datetime.now() - t).total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    if mins < 24 * 60:
        return f"{mins // 60} hr ago"
    days = mins // (24 * 60)
    return "yesterday" if days == 1 else f"{days} days ago"


class RecentRow(QFrame):
    """One recently-viewed item: avatar (or icon), name, what it is, and when."""

    clicked = Signal()

    KIND_ICON = {"group": "group", "ou": "building", "device": "laptop", "serial": "laptop",
                 "asset": "laptop",
                 "search": "search"}

    def __init__(self, title: str, sub: str, key: str, kind: str, when: str = ""):
        super().__init__(objectName="RecentRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setMinimumHeight(54)
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 6, 10, 6)
        h.setSpacing(12)
        av = QLabel()
        av.setStyleSheet("background:transparent;")
        from .person_header import initials
        if kind == "user":
            av.setPixmap(avatar_pixmap(initials(title, key), key))
        else:
            av.setPixmap(avatar_pixmap("", key, round_=False,
                                       icon_name=self.KIND_ICON.get(kind, "star")))
        av.setFixedSize(QSize(34, 34))
        av.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        h.addWidget(av)
        v = QVBoxLayout()
        v.setSpacing(0)
        t = QLabel(title, objectName="RowTitle")
        s = QLabel(sub, objectName="RowSub")
        for lab in (t, s):
            lab.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        v.addWidget(t)
        v.addWidget(s)
        h.addLayout(v, 1)
        w = QLabel(ago(when), objectName="RowSub")
        w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        h.addWidget(w)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(e)
