"""Licenses: counts, who has what, assign and remove."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QLabel, QVBoxLayout

from ..pickers import TargetPicker
from ..widgets import Page, ResultsTable, button

# (friendly name, GAM SKU id)
SKUS = [
    ("Education Fundamentals", "1010070001"),
    ("Education Standard", "1010310005"),
    ("Education Standard (Staff)", "1010310006"),
    ("Education Standard (Extra Student)", "1010310007"),
    ("Teaching and Learning Upgrade", "1010370001"),
    ("Education Plus", "1010310008"),
    ("Education Plus (Staff)", "1010310009"),
    ("Education Plus (Extra Student)", "1010310010"),
    ("Endpoint Education Upgrade", "1010490001"),
    ("Education Fundamentals – Archived User", "1010340007"),
]


class LicensesPage(Page):
    title = "Licenses"
    subtitle = "See how many licenses you have, who has them, and assign or remove them."

    def build(self):
        top = QHBoxLayout()
        box, form = self.group("Overview")
        self.sku = QComboBox()
        self.sku.setEditable(True)
        for name, sku in SKUS:
            self.sku.addItem(f"{name}  ({sku})", sku)
        form.addRow("License", self.sku)
        form.addRow("", self.row(button("License totals", "primary", self.totals),
                                 button("Who has this license", slot=self.holders)))
        top.addWidget(box, 2)

        box = QGroupBox("Assign or remove")
        bl = QVBoxLayout(box)
        self.who = TargetPicker(self.directory)
        bl.addWidget(self.who)
        bl.addLayout(self.row(button("Assign license", "primary", self.assign),
                              button("Remove license", "danger", self.remove),
                              QLabel("Uses the license chosen on the left.", objectName="Muted")))
        top.addWidget(box, 3)
        self.body.addLayout(top)
        self.results = ResultsTable()
        self.body.addWidget(self.results, 1)

    def _sku(self) -> str:
        """SKU id from the chosen item, or whatever SKU/short name was typed."""
        import re
        txt = self.sku.currentText().strip()
        m = re.search(r"\(([^()]+)\)\s*$", txt)
        return m.group(1).strip() if m else txt

    def totals(self):
        self.run(["print", "licenses", "countsonly", "allskus"],
                 lambda c, out, _e: self.results.load_csv(out) if c == 0 else None, quiet=True)

    def holders(self):
        self.run(["print", "licenses", "skus", self._sku()],
                 lambda c, out, _e: self.results.load_csv(out) if c == 0 else None, quiet=True)

    def _go(self, verb):
        ents = self.who.entities()
        if not ents:
            self.info("Choose who this applies to.")
            return
        sku = self._sku()
        name = self.sku.currentText()
        word = "Assign" if verb == "add" else "Remove"
        if self.confirm(f"{word} {name} for {self.who.describe()}?"):
            self.run_many([e + [verb, "license", sku] for e in ents],
                          lambda _o: None, quiet=False)

    def assign(self):
        self._go("add")

    def remove(self):
        self._go("delete")
