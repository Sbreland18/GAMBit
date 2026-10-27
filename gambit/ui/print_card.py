"""Printable account card (Student lookup / Staff card → Print card).

Name, email, an optional fresh temporary password (they choose their own at first
sign-in), their Chromebook and a QR code that opens Google sign-in with the email filled
in. Print it, or save it as a PDF.
"""

from __future__ import annotations

import base64
import html
import io

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QTextBrowser, QVBoxLayout,
)

SIGNIN = "https://accounts.google.com/AccountChooser?Email={email}&continue=https://myaccount.google.com"


def qr_png_b64(text: str) -> str:
    try:
        import qrcode
        img = qrcode.make(text, box_size=6, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001 – the card still prints without the code
        return ""


def card_html(name: str, email: str, password: str = "", chromebook: str = "",
              school: str = "", note: str = "", qr: bool = True, size: str = "half") -> str:
    e = html.escape
    code = qr_png_b64(SIGNIN.format(email=email)) if qr else ""
    img = f"<img width='120' height='120' src='data:image/png;base64,{code}'>" if code else ""
    big = "22pt" if size == "page" else "16pt"
    rows = [("Email", f"<b style='font-size:{big}'>{e(email)}</b>")]
    if password:
        rows.append(("Temporary password", f"<b style='font-size:{big};font-family:Consolas,"
                     f"monospace'>{e(password)}</b><br><span style='color:#57606a'>You'll "
                     "choose your own password when you sign in.</span>"))
    if chromebook:
        rows.append(("Chromebook", e(chromebook)))
    if school:
        rows.append(("School", e(school)))
    if note:
        rows.append(("", e(note)))
    trs = "".join(f"<tr><td style='color:#57606a;padding:6px 14px 6px 0;vertical-align:top'>"
                  f"{e(k)}</td><td style='padding:6px 0'>{v}</td></tr>" for k, v in rows)
    one = (f"<table width='100%' style='border:2px solid #1f3b5c;border-radius:8px'>"
           f"<tr><td style='padding:14px'><div style='font-size:{big};font-weight:bold'>"
           f"{e(name or email)}</div><table>{trs}</table>"
           f"<p style='color:#57606a;font-size:9pt'>Sign in at accounts.google.com – or scan "
           f"the code.</p></td><td width='130' align='center' style='padding:10px'>{img}"
           f"</td></tr></table>")
    if size == "half":
        cut = "<p style='text-align:center;color:#8c959f'>✂ – – – – – – – – – – – – – – – – –</p>"
        return one + cut + one
    return one


class PrintCardDialog(QDialog):
    def __init__(self, page, email: str, name: str = "", chromebook: str = "",
                 school: str = ""):
        super().__init__(page)
        self.page, self.email = page, email
        self.setWindowTitle(f"Print card – {email}")
        self.resize(760, 640)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(name)
        self.cb = QLineEdit(chromebook)
        self.school = QLineEdit(school)
        self.note = QLineEdit(placeholderText="optional, e.g. Bring your charger on Monday")
        self.newpw = QCheckBox("Reset the password now and print the temporary one")
        self.qr = QCheckBox("QR code for Google sign-in")
        self.qr.setChecked(True)
        self.size = QComboBox()
        self.size.addItem("Two per page (cut in half)", "half")
        self.size.addItem("One per page, large", "page")
        form.addRow("Name", self.name)
        form.addRow("Chromebook", self.cb)
        form.addRow("School", self.school)
        form.addRow("Note", self.note)
        form.addRow("", self.newpw)
        form.addRow("", self.qr)
        form.addRow("Layout", self.size)
        v.addLayout(form)
        self.view = QTextBrowser()
        v.addWidget(self.view, 1)
        self.msg = QLabel("", objectName="Muted", wordWrap=True)
        v.addWidget(self.msg)
        bb = QDialogButtonBox()
        bb.addButton("Print…", QDialogButtonBox.AcceptRole).clicked.connect(self.print_)
        bb.addButton("Save as PDF…", QDialogButtonBox.ActionRole).clicked.connect(self.pdf)
        bb.addButton(QDialogButtonBox.Close).clicked.connect(self.reject)
        v.addWidget(bb)
        self.password = ""
        for w in (self.name, self.cb, self.school, self.note):
            w.textChanged.connect(self.render)
        for w in (self.qr,):
            w.toggled.connect(self.render)
        self.size.currentIndexChanged.connect(self.render)
        self.render()

    def render(self, *_):
        self.html = card_html(self.name.text(), self.email,
                              self.password or ("(printed after the reset)" if
                                                self.newpw.isChecked() else ""),
                              self.cb.text(), self.school.text(), self.note.text(),
                              self.qr.isChecked(), self.size.currentData())
        self.view.setHtml(self.html)

    def _ready(self, then):
        """Reset the password first when asked (once), then print."""
        if not self.newpw.isChecked() or self.password:
            self.render()
            then()
            return
        from ..selfservice import _password
        pw = _password()
        if not self.page.confirm(f"Reset the password for {self.email}?\n\nNew temporary "
                                 f"password: {pw}\n\nThey'll choose their own when they sign "
                                 "in."):
            return

        def done(code, _o, _e):
            if code == 0:
                self.password = pw
                self.msg.setText("Password reset.")
                self.render()
                then()
            else:
                self.msg.setText("The reset didn't work – see the Output panel.")
        self.page.runner.run(["update", "user", self.email, "password", pw,
                              "changepassword", "on"], done)

    def _doc(self):
        from PySide6.QtGui import QTextDocument
        d = QTextDocument()
        d.setHtml(self.html)
        return d

    def print_(self):
        def go():
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
            pr = QPrinter(QPrinter.HighResolution)
            if QPrintDialog(pr, self).exec():
                self._doc().print_(pr)
        self._ready(go)

    def pdf(self):
        def go():
            from PySide6.QtPrintSupport import QPrinter
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(self, "Save card", f"{self.email}.pdf",
                                                  "PDF (*.pdf)")
            if not path:
                return
            pr = QPrinter(QPrinter.HighResolution)
            pr.setOutputFormat(QPrinter.PdfFormat)
            pr.setOutputFileName(path)
            self._doc().print_(pr)
            self.msg.setText(f"Saved {path}")
        self._ready(go)
