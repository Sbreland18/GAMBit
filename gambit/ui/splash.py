"""The start-up screen: shows as soon as Qt is up, says what GAMbit is doing, and goes away
when the main window appears."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

W, H = 520, 300


class Splash(QSplashScreen):
    def __init__(self, version: str = ""):
        self.version = version
        self.msg = "Starting…"
        self.pct = 0
        super().__init__(self._draw())
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def _draw(self) -> QPixmap:
        from ..resources import resource_path
        ratio = 1.0
        try:
            ratio = QApplication.primaryScreen().devicePixelRatio()
        except Exception:  # noqa: BLE001
            pass
        pm = QPixmap(int(W * ratio), int(H * ratio))
        pm.setDevicePixelRatio(ratio)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, W, H), 16, 16)
        g = QLinearGradient(0, 0, W, H)
        g.setColorAt(0, QColor("#0f2a4a"))
        g.setColorAt(1, QColor("#16467a"))
        p.fillPath(path, g)
        logo = QPixmap(resource_path("assets/gambit.png"))
        if not logo.isNull():
            p.drawPixmap(QRectF(36, 44, 84, 84), logo, QRectF(logo.rect()))
        p.setPen(QColor("#ffffff"))
        f = QFont()
        f.setPointSizeF(30)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(140, 46, W - 160, 50), Qt.AlignLeft | Qt.AlignVCenter, "GAMbit")
        f.setPointSizeF(11)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor("#b9cde4"))
        p.drawText(QRectF(142, 96, W - 160, 26), Qt.AlignLeft | Qt.AlignVCenter,
                   "GAM made friendly" + (f"  ·  version {self.version}" if self.version
                                          else ""))
        # progress
        bar = QRectF(36, H - 82, W - 72, 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(bar, 4, 4)
        done = QRectF(bar.x(), bar.y(), bar.width() * max(0.04, min(self.pct, 100) / 100),
                      bar.height())
        p.setBrush(QColor("#5fb3ff"))
        p.drawRoundedRect(done, 4, 4)
        p.setPen(QColor("#e8f1fb"))
        f.setPointSizeF(10.5)
        p.setFont(f)
        p.drawText(QRectF(36, H - 66, W - 72, 26), Qt.AlignLeft | Qt.AlignVCenter, self.msg)
        p.setPen(QColor("#7f9bbd"))
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.drawText(QRectF(36, H - 36, W - 72, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   "A friendly front end for GAM, the Google Workspace admin tool")
        p.end()
        return pm

    def step(self, msg: str, pct: int):
        self.msg, self.pct = msg, pct
        self.setPixmap(self._draw())
        QApplication.processEvents()

    def mousePressEvent(self, e):   # a click shouldn't hide it before the window is ready
        e.ignore()
