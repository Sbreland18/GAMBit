"""Single sign-on → Certificates: when each sign-in provider's certificate expires, whether
Google has the provider's current one, and uploading a new one."""

from __future__ import annotations

import datetime
import os

from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QVBoxLayout, QWidget,
)

from ..widgets import ResultsTable, button

LEVEL = {"bad": "✖ Fix now", "warn": "⚠ Soon", "info": "ℹ Set up", "ok": "✔ OK"}


class CertificatesTab(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.profiles: list[dict] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        intro = QLabel("Google can't tell GAMbit when a sign-in provider's certificate "
                       "expires, so GAMbit reads it from the provider (its SAML metadata "
                       "link, or a certificate file). The daily background task checks it and "
                       "alerts you 30, 14 and 3 days before it expires – and when the "
                       "provider starts using a certificate Google doesn't have yet.",
                       objectName="Muted")
        intro.setWordWrap(True)
        v.addWidget(intro)
        box = QGroupBox("Where to read each provider's certificate")
        form = QFormLayout(box)
        self.prof = QComboBox()
        self.prof.setMinimumWidth(320)
        self.prof.currentIndexChanged.connect(self._show_source)
        self.src = QLineEdit(placeholderText="https://… SAML metadata link from ClassLink, "
                                             "Clever, ADFS or Entra ID – or choose a file")
        h = QHBoxLayout()
        h.addWidget(self.src, 1)
        h.addWidget(button("Choose file…", slot=self._pick_file))
        form.addRow("Provider", self.prof)
        form.addRow("Metadata link or file", h)
        h2 = QHBoxLayout()
        h2.addWidget(button("Save", slot=self._save))
        h2.addWidget(button("Check certificates now", "primary", self.check_now))
        h2.addWidget(button("Upload the provider's current certificate to Google…",
                            slot=self._upload))
        h2.addStretch(1)
        form.addRow("", h2)
        self.last = QLabel("", objectName="Muted")
        self.last.setWordWrap(True)
        form.addRow("", self.last)
        v.addWidget(box)
        self.table = ResultsTable()
        v.addWidget(self.table, 1)
        self._show_last()

    # ------------------------------------------------------------ helpers ---
    def _show_last(self):
        from ... import sso_watch
        d = sso_watch.last()
        if d.get("at"):
            self.last.setText(f"Last checked {d['at'].replace('T', ' ')}"
                              + (f" – {d['error']}" if d.get("error") else ""))
        rows = [[LEVEL.get(f.get("level"), ""), f.get("profile", ""), f.get("text", ""),
                 f.get("fix", "")] for f in d.get("findings", [])]
        self.table.set_rows(["Status", "Provider", "What GAMbit found", "What to do"], rows)

    def set_profiles(self, profiles: list[dict]):
        cur = self.prof.currentData()
        self.profiles = profiles
        self.prof.blockSignals(True)
        self.prof.clear()
        for p in profiles:
            self.prof.addItem(f"{p['label']}  ({p['entity'] or p['name']})", p["name"])
        i = self.prof.findData(cur)
        self.prof.setCurrentIndex(max(0, i))
        self.prof.blockSignals(False)
        self._show_source()

    def _show_source(self, *_a):
        from ... import sso_watch
        s = sso_watch.sources().get(self.prof.currentData() or "", {})
        self.src.setText(s.get("value", ""))

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Provider certificate or metadata", "",
                                              "Certificates and metadata (*.pem *.cer *.crt "
                                              "*.der *.xml);;All files (*)")
        if path:
            self.src.setText(path)

    def _source(self) -> dict | None:
        name = self.prof.currentData()
        if not name:
            self.page.info("Load the providers first (Load assignments and profiles).")
            return None
        v = self.src.text().strip()
        return {"kind": "url" if v.lower().startswith(("https://", "http://")) else "file",
                "value": v}

    def _save(self):
        from ... import sso_watch
        s = self._source()
        if s is None:
            return
        try:
            sso_watch.set_source(self.prof.currentData(), s["kind"], s["value"],
                                 self.prof.currentText())
        except ValueError as exc:
            self.page.info(str(exc))
            return
        self.check_now()

    # ------------------------------------------------------------- actions ---
    def check_now(self):
        from ... import sso_watch
        from .round13_tabs import _csv
        from .round25_data import _work

        def work():
            profiles, creds = sso_watch.load_google(_csv())
            findings = sso_watch.check(profiles, creds)
            sso_watch.save_last(findings)
            return profiles

        def done(profiles):
            if not self.profiles:
                self.set_profiles(profiles)
            self._show_last()
        _work(self.page, work, done, self.page.status, "Checking sign-in certificates…")

    def _upload(self):
        from ... import sso_watch, team
        from .round11_pages import run_or_request
        from .round13_pages import _steps
        from .round25_data import _work
        s = self._source()
        if s is None:
            return
        if not s["value"]:
            self.page.info("Add the provider's metadata link or certificate file first.")
            return
        name, label = self.prof.currentData(), self.prof.currentText()

        def work():
            certs = sso_watch.read_source(s)
            now = datetime.datetime.now(datetime.timezone.utc)
            signing = [c for c in certs if c.use in ("", "signing")] or certs
            live = [c for c in signing if c.not_before <= now and c.days_left(now) >= 0]
            if not live:
                raise ValueError("The provider has no certificate that's valid today.")
            return max(live, key=lambda c: c.not_after)

        def go(cert):
            base = os.path.join(team.folder(), "sso-certificates") if team.folder() else \
                os.path.join(os.path.expanduser("~"), "GAMbit", "sso-certificates")
            os.makedirs(base, exist_ok=True)
            path = os.path.join(base, f"{cert.sha256[:16]}.pem")
            with open(path, "w", encoding="ascii") as fh:     # a public certificate
                fh.write(cert.pem())
            if not self.page.confirm(
                    f"Upload this certificate to Google for {label}?\n\n"
                    f"{cert.subject}\nValid {cert.not_before:%b %d, %Y} – "
                    f"{cert.not_after:%b %d, %Y}\nFingerprint {cert.short_fp()}\n\n"
                    "Google keeps up to two certificates per provider, so sign-in keeps "
                    "working with the old one until the provider switches. If Google already "
                    "has two, remove the expired one in the Admin console first."):
                return
            run_or_request(self.page, _steps(self.page),
                           [(f"Upload sign-in certificate for {label}",
                             sso_watch.upload_args(name, path))],
                           "Upload sign-in certificate", "Single sign-on",
                           lambda _s: self.check_now())
        _work(self.page, work, go, self.page.status, "Reading the provider's certificate…")
