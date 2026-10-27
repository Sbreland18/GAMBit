"""“Show before → after”: each field as it is in Google now, and as the change will leave it."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from .widgets import ResultsTable, Worker


class ChangePreviewDialog(QDialog):
    def __init__(self, parent, commands: list[list[str]], title: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Before → after" + (f" – {title}" if title else ""))
        self.resize(880, 480)
        v = QVBoxLayout(self)
        self.msg = QLabel("Reading the current values from Google…", wordWrap=True)
        v.addWidget(self.msg)
        self.table = ResultsTable()
        v.addWidget(self.table, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        v.addWidget(bb)
        from .. import change_preview as cp
        Worker(cp.preview, [list(map(str, c)) for c in commands],
               on_done=self._show, on_error=lambda e: self.msg.setText(f"Couldn't read: {e}"))

    def _show(self, rows):
        self.table.set_rows(["Who / what", "Field", "Now", "After", ""],
                            [[r["target"], r["field"], r["before"], r["after"],
                              "no change" if r["same"] else ""] for r in rows])
        changing = sum(1 for r in rows if not r["same"])
        self.msg.setText(f"{changing} field change(s)" + (
            f", {len(rows) - changing} already as wanted" if len(rows) - changing else "") +
            ". Nothing has been changed yet.")
