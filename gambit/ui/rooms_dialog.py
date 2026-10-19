"""Import rooms and resources from a spreadsheet (More services → Calendar)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)

from .. import rooms
from .steps import Step, StepList
from .widgets import ResultsTable, Worker, button

LABEL = {"building": "Building", "create": "New", "update": "Update", "same": "No change",
         "problem": "⚠ Problem"}


class RoomsImportDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Import rooms and resources")
        self.resize(980, 680)
        self.actions: list[rooms.Action] = []
        v = QVBoxLayout(self)
        intro = QLabel("Use a CSV file or a Google Sheet with the columns <b>Building, Floor, "
                       "Name, ID, Capacity, Kind, Type, Description</b>. ID is optional – "
                       "GAMbit makes one from the building and name. New buildings are created "
                       "first. Nothing changes until you click Apply.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        h = QHBoxLayout()
        self.src = QLineEdit(placeholderText="CSV file, or a Google Sheet link")
        h.addWidget(self.src, 1)
        h.addWidget(button("Browse…", slot=self._browse))
        h.addWidget(button("Save a blank template…", slot=self._template))
        h.addWidget(button("Preview", "primary", self.preview))
        v.addLayout(h)
        self.status = QLabel("", objectName="Muted")
        v.addWidget(self.status)
        self.table = ResultsTable()
        v.addWidget(self.table, 1)
        self.steps = StepList(page)
        self.steps.setMaximumHeight(160)
        v.addWidget(self.steps)
        self.apply_btn = button("Apply changes", "primary", self.apply)
        self.apply_btn.setEnabled(False)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(self.apply_btn)
        h.addWidget(button("Close", slot=self.reject))
        v.addLayout(h)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Rooms spreadsheet", "", "CSV (*.csv)")
        if path:
            self.src.setText(path)

    def _template(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save template", "rooms.csv", "CSV (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(rooms.TEMPLATE)
            self.src.setText(path)

    def preview(self):
        src = self.src.text().strip()
        if not src:
            QMessageBox.information(self, "Rooms", "Choose a CSV file or paste a Sheet link.")
            return
        self.status.setText("Reading the sheet and what's already in Google…")
        self.apply_btn.setEnabled(False)

        def work():
            from .. import google_io
            from ..directory import run_gam_csv
            path = google_io.download_sheet(src) if src.startswith("http") else src
            with open(path, encoding="utf-8-sig") as fh:
                rms = rooms.rooms_from_rows(rooms.read_rows(fh.read()))
            cb, buildings, eb = run_gam_csv(["print", "buildings"], 300)
            cr, resources, er = run_gam_csv(["print", "resources", "allfields"], 300)
            if cb != 0 or cr != 0:
                raise RuntimeError((eb or er or "GAM couldn't list buildings/resources")
                                   .strip().splitlines()[-1])
            return rms, rooms.plan(rms, buildings, resources)
        Worker(work, on_done=self._show,
               on_error=lambda e: self.status.setText(f"Couldn't read it: {e}"))

    def _show(self, result):
        rms, self.actions = result
        self.table.set_rows(["Change", "Room / building", "Details"],
                            [[LABEL[a.action], a.target, a.details] for a in self.actions])
        n = {k: sum(a.action == k for a in self.actions) for k in LABEL}
        self.status.setText(f"{len(rms)} row(s): {n['building']} building change(s), "
                            f"{n['create']} new, {n['update']} to update, {n['same']} "
                            f"already right" + (f", {n['problem']} problem(s)"
                                                if n["problem"] else ""))
        self.apply_btn.setEnabled(any(a.commands for a in self.actions))

    def apply(self):
        todo = [a for a in self.actions if a.commands]
        if not todo or QMessageBox.question(
                self, "Apply", f"Make {len(todo)} change(s) in Google?") != QMessageBox.Yes:
            return
        self.apply_btn.setEnabled(False)
        steps = [Step(f"{LABEL[a.action]}: {a.target}", cmd,
                      required=(a.action == "building")) for a in todo for cmd in a.commands]

        def finished(_s):
            QMessageBox.information(self, "Rooms and resources", self.steps.summary())
        self.steps.run(steps, finished)
