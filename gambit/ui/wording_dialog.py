"""Settings → Printouts → Edit wording: change any phrase on the account cards and Welcome
sheet, in English and Spanish."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)


class WordingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        from .. import printouts as po
        self.po = po
        self.setWindowTitle("Printout wording")
        self.resize(980, 620)
        v = QVBoxLayout(self)
        lab = QLabel("Change any phrase on account cards, class card sets and the Welcome "
                     "sheet. Leave a cell as it is to keep GAMbit's wording. {name} and {n} "
                     "are filled in for you.", objectName="Muted")
        lab.setWordWrap(True)
        lab.setTextFormat(Qt.PlainText)
        v.addWidget(lab)
        self.table = QTableWidget(len(po.PHRASES), 2)
        self.table.setHorizontalHeaderLabels(["English", "Español (Spanish)"])
        self.table.setVerticalHeaderLabels([k for k, *_r in po.PHRASES])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setWordWrap(True)
        for r, (key, _kind, _en, _es) in enumerate(po.PHRASES):
            for c, lang in enumerate(("en", "es")):
                it = QTableWidgetItem(po.phrase(key, lang))
                it.setToolTip(f"GAMbit's wording: {po.DEFAULT[lang][key]}")
                self.table.setItem(r, c, it)
        self.table.resizeRowsToContents()
        v.addWidget(self.table, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.addButton("Back to GAMbit's wording", QDialogButtonBox.ResetRole).clicked.connect(
            self._reset)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _reset(self):
        for r, (key, *_rest) in enumerate(self.po.PHRASES):
            for c, lang in enumerate(("en", "es")):
                self.table.item(r, c).setText(self.po.DEFAULT[lang][key])

    def _save(self):
        d = {"en": {}, "es": {}}
        for r, (key, *_rest) in enumerate(self.po.PHRASES):
            for c, lang in enumerate(("en", "es")):
                d[lang][key] = self.table.item(r, c).text()
        self.po.save_custom(d)
        self.accept()
