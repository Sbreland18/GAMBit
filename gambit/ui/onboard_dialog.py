"""Settings for staff onboarding from the HR sheet."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QPlainTextEdit, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from .. import onboard, signature


SAMPLE = {"first": "Jordan", "last": "Sample", "name": "Jordan Sample",
          "email": "jordan.sample@yourschool.org", "title": "3rd Grade Teacher",
          "department": "Lincoln Elementary", "phone": ""}


class OnboardDialog(QDialog):
    def __init__(self, parent, directory=None):
        super().__init__(parent)
        self.setWindowTitle("New staff setup")
        self.resize(760, 620)
        o = onboard.options()
        v = QVBoxLayout(self)
        intro = QLabel("When a staff roster sync creates an account, these steps run for that "
                       "person straight after – the same as Workflows → New staff.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        self.enabled = QCheckBox("Turn on New staff setup for staff roster syncs")
        self.enabled.setChecked(bool(o["enabled"]))
        v.addWidget(self.enabled)
        tabs = QTabWidget()
        v.addWidget(tabs, 1)

        # --- groups & license
        w = QWidget()
        f = QFormLayout(w)
        self.license = QComboBox()
        self.license.addItem("Don't assign a license", "")
        from .pages.licenses import SKUS
        for name, sku in SKUS:
            self.license.addItem(name, sku)
        i = self.license.findData(o["license"])
        if i < 0 and o["license"]:
            self.license.addItem(o["license"], o["license"])
            i = self.license.count() - 1
        self.license.setCurrentIndex(max(0, i))
        f.addRow("License", self.license)
        self.groups = QPlainTextEdit(o["groups"])
        self.groups.setPlaceholderText("* = allstaff\nLincoln Elementary = lincoln-staff, "
                                       "k5-teachers\nHigh School = hs-staff\n"
                                       "Custodian = custodians")
        f.addRow("Groups", self.groups)
        help_ = QLabel("One line per rule: <b>building, school ID, department or job title = "
                       "group, group</b>. <b>*</b> means everyone. Group names without @ get "
                       "your domain added. Matching ignores upper/lower case.",
                       objectName="Muted")
        help_.setWordWrap(True)
        f.addRow("", help_)
        self.test_school = QLineEdit(placeholderText="Try a building or job title…")
        self.test_out = QLabel("", objectName="Muted")
        self.test_school.textChanged.connect(self._try)
        self.groups.textChanged.connect(self._try)
        f.addRow("Test", self.test_school)
        f.addRow("", self.test_out)
        tabs.addTab(w, "Groups and license")

        # --- signature
        w = QWidget()
        f = QVBoxLayout(w)
        self.sig = QCheckBox("Set the district signature (from Email → Signatures)")
        self.sig.setChecked(bool(o["signature"]))
        f.addWidget(self.sig)
        note = QLabel("If the new mailbox isn't ready yet, GAMbit tries again automatically "
                      "for the next few hours (background tasks or the next time it opens).",
                      objectName="Muted")
        note.setWordWrap(True)
        f.addWidget(note)
        f.addWidget(QLabel("Preview for a sample person:"))
        prev = QTextBrowser()
        prev.setHtml(signature.render(onboard.signature_template(), SAMPLE))
        f.addWidget(prev, 1)
        tabs.addTab(w, "Signature")

        # --- welcome email
        w = QWidget()
        f = QFormLayout(w)
        self.welcome = QCheckBox("Email the sign-in details to their supervisor")
        self.welcome.setChecked(bool(o["welcome"]))
        f.addRow(self.welcome)
        self.fallback = QLineEdit(o["welcome_fallback"])
        self.fallback.setPlaceholderText("e.g. hr@yourschool.org")
        f.addRow("No supervisor on the sheet? Send to", self.fallback)
        self.cc = QLineEdit(o["welcome_cc"])
        self.cc.setPlaceholderText("optional, e.g. helpdesk@yourschool.org")
        f.addRow("Copy to", self.cc)
        self.subject = QLineEdit(o["subject"])
        f.addRow("Subject", self.subject)
        self.body = QPlainTextEdit(o["body"])
        f.addRow("Message", self.body)
        tags = QLabel("Tags: {name} {first} {last} {email} {password} {title} {department} "
                      "{school} {supervisor}. The password is hidden in GAMbit's logs.",
                      objectName="Muted")
        tags.setWordWrap(True)
        f.addRow("", tags)
        tabs.addTab(w, "Welcome email")

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._try()

    def _try(self, *_):
        key = self.test_school.text().strip()
        if not key:
            self.test_out.setText("")
            return
        m = onboard.parse_groups(self.groups.toPlainText())
        g = onboard.groups_for({"school": key, "title": key}, m, "")
        self.test_out.setText("→ " + (", ".join(g) if g else "no groups"))

    def _save(self):
        onboard.save_options({
            "enabled": self.enabled.isChecked(), "license": self.license.currentData() or "",
            "groups": self.groups.toPlainText(), "signature": self.sig.isChecked(),
            "welcome": self.welcome.isChecked(),
            "welcome_fallback": self.fallback.text().strip(),
            "welcome_cc": self.cc.text().strip(), "subject": self.subject.text(),
            "body": self.body.toPlainText()})
        self.accept()
