"""Printable Chromebook / cart labels with Code 39 barcodes (any barcode scanner reads
them, so they work with the Summer collection scan box)."""

from __future__ import annotations

import html

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QTextDocument
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QTextBrowser, QVBoxLayout,
)

from ..fleet import code39_bars
from .widgets import button


def barcode_image(text: str, unit: int = 3, height: int = 60) -> QImage:
    bars = code39_bars(text)
    width = sum(w for _b, w in bars) * unit + 20
    img = QImage(width, height, QImage.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    x = 10
    for is_bar, w in bars:
        if is_bar:
            p.fillRect(x, 0, w * unit, height, Qt.black)
        x += w * unit
    p.end()
    return img


def labels_html(devs: list[dict], code_field: str = "serial", per_row: int = 3,
                title: str = "") -> str:
    esc = html.escape
    parts = ["<html><body style='font-family:Arial,sans-serif'><table cellspacing='8' "
             "cellpadding='6' width='100%'>"]
    for i in range(0, len(devs), per_row):
        parts.append("<tr>")
        for d in devs[i:i + per_row]:
            code = d.get(code_field) or d.get("serial", "")
            parts.append(
                "<td style='border:1px dashed #9aa4ae' align='center' width='33%'>"
                + (f"<div style='font-size:8pt;color:#57606a'>{esc(title)}</div>" if title else "")
                + f"<div style='font-size:14pt;font-weight:bold'>{esc(d.get('asset') or code)}"
                  "</div>"
                + f"<img src='bc://{esc(code)}'><br>"
                + f"<span style='font-family:Consolas,monospace;font-size:9pt'>{esc(code)}</span>"
                + (f"<br><span style='font-size:9pt'>{esc(d['location'])}</span>"
                   if d.get("location") else "")
                + "</td>")
        parts.append("</tr>")
    parts.append("</table></body></html>")
    return "".join(parts)


class LabelsDialog(QDialog):
    def __init__(self, parent, devs: list[dict], code_field="serial", title=""):
        super().__init__(parent)
        self.setWindowTitle(f"Labels – {len(devs)}")
        self.resize(780, 640)
        self.devs, self.code_field = devs, code_field
        self.html = labels_html(devs, code_field, title=title)
        self.view = QTextBrowser()
        self._add_images(self.view.document())
        self.view.setHtml(self.html)
        lay = QVBoxLayout(self)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addWidget(button("Print…", "primary", self.print_))
        row.addWidget(button("Save as PDF…", slot=self.pdf))
        row.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay.addLayout(row)

    def _add_images(self, doc: QTextDocument):
        for d in self.devs:
            code = d.get(self.code_field) or d.get("serial", "")
            doc.addResource(QTextDocument.ImageResource, QUrl(f"bc://{code}"),
                            barcode_image(code))

    def _doc(self):
        d = QTextDocument()
        self._add_images(d)
        d.setHtml(self.html)
        return d

    def print_(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        p = QPrinter()
        if QPrintDialog(p, self).exec():
            self._doc().print_(p)

    def pdf(self):
        from PySide6.QtPrintSupport import QPrinter
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "chromebook-labels.pdf",
                                              "PDF (*.pdf)")
        if path:
            p = QPrinter()
            p.setOutputFormat(QPrinter.PdfFormat)
            p.setOutputFileName(path)
            self._doc().print_(p)
