"""Settings → Team → Signatures & trust: check and sign shared items, and pair computers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from .widgets import ResultsTable


class TrustCenter(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Signatures & trust")
        self.resize(980, 640)
        v = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._items_tab(), "Shared items")
        tabs.addTab(self._computers_tab(), "Trusted computers")
        v.addWidget(tabs, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.refresh()

    # ------------------------------------------------------------- items ---
    def _items_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        lab = QLabel("Anything in the team folder that can make GAMbit act on its own is "
                     "signed by the person who made it. Background tasks skip items that "
                     "aren't signed (made before this version, or changed in the folder by "
                     "hand). Check each one's exact commands and sign it if it's right.")
        lab.setTextFormat(Qt.PlainText)
        lab.setWordWrap(True)
        v.addWidget(lab)
        from .. import trust
        self.key_lab = QLabel()
        self.key_lab.setTextFormat(Qt.PlainText)
        self.key_lab.setWordWrap(True)
        self.key_lab.setText(trust.my_key_status())
        v.addWidget(self.key_lab)
        self.table = ResultsTable()
        self.table.no_drawer = True
        self.table.no_row_actions = True
        self.table.row_clicked.connect(lambda *_: self._show())
        v.addWidget(self.table, 2)
        self.detail = QPlainTextEdit(readOnly=True)
        self.detail.setMinimumHeight(140)
        v.addWidget(self.detail, 1)
        row = QHBoxLayout()
        for text, slot in (("Sign selected…", self._sign), ("Refresh", self.refresh)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        return w

    def refresh(self):
        from .. import trust
        self.items = trust.items()
        self.table.set_rows(["#", "Kind", "Item", "Signature"],
                            [[str(i), it.kind, it.label, ("✔ " if it.ok else "⚠ ") + it.signed]
                             for i, it in enumerate(self.items)])
        self.table.hidden_columns = {"#"}
        self._fill_keys()

    def _sel(self):
        rows = self.table.selected_dicts()
        out = []
        for r in rows:
            try:
                out.append(self.items[int(r["#"])])
            except (KeyError, ValueError, IndexError):
                continue
        return out

    def _show(self):
        sel = self._sel()
        self.detail.setPlainText(sel[0].detail if sel else "")

    def _sign(self):
        sel = [it for it in self._sel() if not it.ok]
        if not sel:
            QMessageBox.information(self, "Sign", "Select an item that isn't signed yet.")
            return
        for it in sel:
            if QMessageBox.question(
                    self, "Sign this?", f"{it.kind}: {it.label}\n\nIt will be trusted exactly "
                    f"as it is now:\n\n{it.detail[:6000]}") != QMessageBox.Yes:
                continue
            try:
                it.sign()
            except Exception as exc:  # noqa: BLE001
                QMessageBox.information(self, "Not signed", str(exc))
        self.refresh()

    # --------------------------------------------------------- computers ---
    def _computers_tab(self):
        from .. import seal
        w = QWidget()
        v = QVBoxLayout(w)
        lab = QLabel("Without GAMbit sign-in, each computer trusts only what it signed itself. "
                     "To let one computer act on another's signed items (for example the "
                     "server that runs the background tasks), publish this computer's key, "
                     "then on the other computer trust it – after checking the code shown here "
                     "matches. With sign-in on, people's keys are approved in Users & access "
                     "instead.")
        lab.setTextFormat(Qt.PlainText)
        lab.setWordWrap(True)
        v.addWidget(lab)
        mine = QLabel()
        mine.setTextFormat(Qt.PlainText)
        mine.setTextInteractionFlags(Qt.TextSelectableByMouse)
        mine.setText(f"This computer's code: {seal.local_fingerprint()}")
        v.addWidget(mine)
        self.keys = ResultsTable()
        self.keys.no_drawer = True
        self.keys.no_row_actions = True
        v.addWidget(self.keys, 1)
        row = QHBoxLayout()
        for text, slot in (("Publish this computer's key", self._publish),
                           ("Trust selected…", self._trust),
                           ("Stop trusting selected", self._untrust)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        return w

    def _fill_keys(self):
        from .. import seal
        if not hasattr(self, "keys"):
            return
        self.pub = seal.published_keys()
        known = {p["kid"] for p in self.pub}
        rows = [[p["kid"], p["label"], p["fingerprint"],
                 "this computer" if p["kid"] == seal.local_kid() else
                 ("trusted" if p["trusted"] else "not trusted")] for p in self.pub]
        rows += [[kid, k.get("label", ""), "", "trusted (no longer published)"]
                 for kid, k in seal.trusted_locals().items() if kid not in known]
        self.keys.set_rows(["key", "Computer", "Code", "Here"], rows)
        self.keys.hidden_columns = {"key"}

    def _publish(self):
        from .. import seal, team
        if not team.folder():
            QMessageBox.information(self, "Publish", "Set a team folder first.")
            return
        seal.publish_local_key()
        self._fill_keys()

    def _sel_key(self):
        rows = self.keys.selected_dicts()
        if not rows:
            return None
        return next((p for p in self.pub if p["kid"] == rows[0]["key"]), {"kid": rows[0]["key"]})

    def _trust(self):
        from .. import seal
        p = self._sel_key()
        if not p or "public" not in p or p["kid"] == seal.local_kid():
            return
        code, ok = QInputDialog.getText(self, "Trust a computer",
                                        f"On {p['label']}, open Signatures & trust and read "
                                        "the code it shows. Type it here:")
        if not ok:
            return
        try:
            seal.trust_local(p["public"], p["label"], code)
        except ValueError as exc:
            QMessageBox.warning(self, "Not trusted", str(exc))
            return
        self._fill_keys()

    def _untrust(self):
        from .. import seal
        p = self._sel_key()
        if p:
            seal.untrust_local(p["kid"])
            self._fill_keys()
