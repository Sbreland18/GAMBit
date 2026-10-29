"""Domain & extras → Email security: SPF, DKIM, DMARC and MX for every domain."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ..widgets import ResultsTable, button

LEVEL = {"bad": "✖ Fix", "warn": "⚠ Improve", "info": "ℹ Note", "ok": "✔ OK"}


class EmailSecurityTab(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page = page
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        intro = QLabel("These public DNS records decide whether someone can send mail that "
                       "looks like it's from the district – to parents, staff or vendors – "
                       "and whether your own mail lands in spam. GAMbit checks every domain "
                       "and alias (the daily background task does it too) and says what to "
                       "change at your DNS host. Only domain names are looked up.",
                       objectName="Muted")
        intro.setWordWrap(True)
        v.addWidget(intro)
        h = QHBoxLayout()
        h.addWidget(button("Check my domains", "primary", self.check))
        self.dom = QLineEdit(placeholderText="domain")
        self.dom.setMaximumWidth(220)
        self.sel = QLineEdit(placeholderText="DKIM selector (google)")
        self.sel.setMaximumWidth(200)
        h.addSpacing(16)
        h.addWidget(QLabel("Different DKIM selector:"))
        h.addWidget(self.dom)
        h.addWidget(self.sel)
        h.addWidget(button("Save", slot=self._save_sel))
        h.addStretch(1)
        v.addLayout(h)
        self.status = QLabel("", objectName="Muted")
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        self.table = ResultsTable()
        v.addWidget(self.table, 1)
        self._show()

    def _show(self):
        from ... import maildns
        d = maildns.last()
        order = {"bad": 0, "warn": 1, "info": 2, "ok": 3}
        fs = sorted(d.get("findings", []), key=lambda f: (f.get("domain", ""),
                                                          order.get(f.get("level"), 9)))
        self.table.set_rows(["Status", "Domain", "Record", "What GAMbit found", "What to do"],
                            [[LEVEL.get(f.get("level"), ""), f.get("domain", ""),
                              f.get("check", ""), f.get("text", ""), f.get("fix", "")]
                             for f in fs])
        if d.get("at"):
            bad = sum(1 for f in fs if f.get("level") == "bad")
            self.status.setText(f"Last checked {d['at'].replace('T', ' ')} – "
                                + (f"{bad} problem(s) to fix." if bad else "no problems.")
                                + (f" {d['error']}" if d.get("error") else ""))

    def _save_sel(self):
        from ... import maildns
        dom = self.dom.text().strip().lower()
        if not dom:
            self.page.info("Type the domain the selector is for.")
            return
        try:
            maildns.set_selector(dom, self.sel.text())
        except ValueError as exc:
            self.page.info(str(exc))
            return
        self.status.setText(f"DKIM selector for {dom} saved.")

    def check(self):
        from ... import maildns
        from .round13_tabs import _csv
        from .round25_data import _work

        def work():
            fs = maildns.run_all(run_csv=_csv())
            maildns.save_last(fs)
            return fs
        _work(self.page, work, lambda _fs: self._show(), self.status,
              "Looking up your domains' email records…")
