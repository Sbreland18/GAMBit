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


def cards_html(people: list[dict], title: str = "", lang: str | None = None,
               family: bool = False) -> str:
    """people: dicts with name, email, password, group (e.g. OU or homeroom)."""
    from ..printouts import default_lang, t
    lang = lang or default_lang()
    esc = html.escape
    head = esc(title) if title else t("cards_title", lang)
    fam = (f"<br><span style='font-size:8pt'>{t('family_note', lang)}</span>"
           if family else "")
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
                     f"{t('cards_count', lang, n=len(members))}</span></h3>")
        parts.append("<table cellspacing='6' width='100%'>")
        for i in range(0, len(members), 2):
            parts.append("<tr>")
            for p in members[i:i + 2]:
                parts.append(
                    "<td width='50%' style='border:1px dashed #9aa4ae;padding:10px'>"
                    f"<b style='font-size:12pt'>{esc(p.get('name', ''))}</b><br>"
                    f"<span style='color:#57606a'>{head}</span><br><br>"
                    f"{t('email', lang)}: <b>{esc(p.get('email', ''))}</b><br>"
                    f"{t('password', lang)}: <b style='font-family:Consolas,monospace;"
                    f"font-size:13pt'>{esc(p.get('password', ''))}</b><br>"
                    f"<span style='color:#57606a;font-size:8pt'>{t('cards_signin', lang)}"
                    f"</span>{fam}</td>")
            if len(members[i:i + 2]) == 1:
                parts.append("<td></td>")
            parts.append("</tr>")
        parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)


class CardsDialog(QDialog):
    def __init__(self, parent, people: list[dict], title=""):
        super().__init__(parent)
        self.setWindowTitle(f"Password cards – {len(people)} account(s)")
        self.resize(760, 640)
        self.people, self.title = people, ("" if title == "Google sign-in" else title)
        from PySide6.QtWidgets import QCheckBox, QLabel
        from ..printouts import lang_combo
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Language"))
        self.lang = lang_combo()
        top.addWidget(self.lang)
        self.family = QCheckBox("Add a note for families")
        top.addWidget(self.family)
        top.addStretch(1)
        lay.addLayout(top)
        self.view = QTextBrowser()
        lay.addWidget(self.view, 1)
        self.lang.currentIndexChanged.connect(self.render)
        self.family.toggled.connect(self.render)
        self.render()
        row = QHBoxLayout()
        row.addWidget(button("Print…", "primary", self.print_))
        row.addWidget(button("Save as PDF…", slot=self.pdf))
        row.addWidget(button("Copy as table", slot=self.copy))
        row.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay.addLayout(row)

    def render(self, *_a):
        self.html = cards_html(self.people, self.title, self.lang.currentData(),
                               self.family.isChecked())
        self.view.setHtml(self.html)

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
