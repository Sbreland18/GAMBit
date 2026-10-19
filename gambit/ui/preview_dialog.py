"""'Big change' check: shows exactly who a command will affect before it runs."""

from __future__ import annotations

import csv

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QLabel, QLineEdit, QListWidget, QVBoxLayout,
)

from ..gam_runner import display_command


class BigChangeDialog(QDialog):
    def __init__(self, parent, args, count: int, emails: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Big change – please check")
        self.resize(620, 520)
        self.emails = emails
        lay = QVBoxLayout(self)
        head = QLabel(f"<h3 style='margin:0'>This will affect {count:,} account(s)</h3>")
        lay.addWidget(head)
        cmd = QLabel(f"<code>{display_command(args)}</code>")
        cmd.setWordWrap(True)
        lay.addWidget(cmd)
        if emails:
            self.find = QLineEdit(placeholderText=f"Search the {len(emails):,} accounts…")
            self.find.textChanged.connect(self._filter)
            lay.addWidget(self.find)
            self.list = QListWidget()
            self.list.addItems(emails)
            lay.addWidget(self.list, 1)
        strict = count >= 100
        note = QLabel("The list comes from GAMbit's saved user list (refresh it in Settings if "
                      "it might be out of date)." +
                      (" Type the number of accounts to confirm." if strict else ""),
                      objectName="Muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.confirm = QLineEdit(placeholderText=f"Type {count} to continue")
        self.confirm.textChanged.connect(lambda t: self.ok.setEnabled(t.strip() == str(count)))
        lay.addWidget(self.confirm)
        self.confirm.setVisible(strict)
        bb = QDialogButtonBox()
        self.ok = bb.addButton(f"Change {count:,} accounts", QDialogButtonBox.AcceptRole)
        self.ok.setProperty("kind", "danger")
        self.ok.setEnabled(not strict)
        if emails:
            save = bb.addButton("Save list…", QDialogButtonBox.ActionRole)
            save.clicked.connect(self._save)
        bb.addButton(QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.confirm.setFocus()

    def _filter(self, text):
        t = text.lower().strip()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(t) and t not in it.text().lower())

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save list", "affected-accounts.csv",
                                              "CSV (*.csv)")
        if path:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["email"])
                w.writerows([e] for e in self.emails)
