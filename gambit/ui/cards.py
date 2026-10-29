"""Printable password cards (cut-apart sign-in slips), grouped by class/OU."""

from __future__ import annotations

import html
from itertools import groupby

from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QTextBrowser,
    QVBoxLayout,
)

from .widgets import button


def cards_html(people: list[dict], title: str = "Google sign-in") -> str:
    """people: dicts with name, email, password, group (e.g. OU or homeroom)."""
    esc = html.escape
    parts = ["<html><body style='font-family:Arial,sans-serif'>"]
    people = sorted(people, key=lambda p: (p.get("group", ""), p.get("name", "")))
    first = True
    for group, members in groupby(people, key=lambda p: p.get("group", "")):
        members = list(members)
        if not first:
            parts.append("<div style='page-break-before:always'></div>")
        first = False
        parts.append(f"<h3 style='margin:0 0 6px 0'>{esc(group or 'Accounts')}"
                     f" <span style='color:#57606a;font-weight:normal'>· "
                     f"{len(members)} card(s)</span></h3>")
        parts.append("<table cellspacing='6' width='100%'>")
        for i in range(0, len(members), 2):
            parts.append("<tr>")
            for p in members[i:i + 2]:
                parts.append(
                    "<td width='50%' style='border:1px dashed #9aa4ae;padding:10px'>"
                    f"<b style='font-size:12pt'>{esc(p.get('name', ''))}</b><br>"
                    f"<span style='color:#57606a'>{esc(title)}</span><br><br>"
                    f"Email: <b>{esc(p.get('email', ''))}</b><br>"
                    f"Password: <b style='font-family:Consolas,monospace;font-size:13pt'>"
                    f"{esc(p.get('password', ''))}</b><br>"
                    "<span style='color:#57606a;font-size:8pt'>Sign in at "
                    "accounts.google.com</span></td>")
            if len(members[i:i + 2]) == 1:
                parts.append("<td></td>")
            parts.append("</tr>")
        parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)


class CardsDialog(QDialog):
    def __init__(self, parent, people: list[dict], title="Google sign-in"):
        super().__init__(parent)
        self.setWindowTitle(f"Password cards – {len(people)} account(s)")
        self.resize(760, 640)
        self.people = people
        self.html = cards_html(people, title)
        view = QTextBrowser()
        view.setHtml(self.html)
        lay = QVBoxLayout(self)
        lay.addWidget(view, 1)
        row = QHBoxLayout()
        row.addWidget(button("Print…", "primary", self.print_))
        row.addWidget(button("Save as PDF…", slot=self.pdf))
        row.addWidget(button("Copy as table", slot=self.copy))
        row.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay.addLayout(row)

    def _doc(self):
        d = QTextDocument()
        d.setHtml(self.html)
        return d

    def print_(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        p = QPrinter()
        if QPrintDialog(p, self).exec():
            self._doc().print_(p)

    def pdf(self):
        from PySide6.QtPrintSupport import QPrinter
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "password-cards.pdf",
                                              "PDF (*.pdf)")
        if path:
            p = QPrinter()
            p.setOutputFormat(QPrinter.PdfFormat)
            p.setOutputFileName(path)
            self._doc().print_(p)

    def copy(self):
        rows = ["Group\tName\tEmail\tPassword"] + [
            f"{p.get('group', '')}\t{p.get('name', '')}\t{p.get('email', '')}\t"
            f"{p.get('password', '')}" for p in self.people]
        from .secure_clip import copy_secret
        copy_secret("\n".join(rows))
