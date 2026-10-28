"""Bottom-panel tab listing the GAM commands that dry run held back."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget,
)

from .widgets import button


class DryRunPanel(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        head = QHBoxLayout()
        self.count = QLabel("Turn on Dry run at the top to see exactly which GAM commands "
                            "a workflow or roster sync would run, without running them.",
                            objectName="Muted")
        self.count.setWordWrap(True)
        head.addWidget(self.count, 1)
        head.addWidget(button("Copy", slot=self.copy))
        head.addWidget(button("Save…", slot=self.save))
        head.addWidget(button("Clear", slot=self.clear))
        lay.addLayout(head)
        self.text = QPlainTextEdit(objectName="Log")
        self.text.setReadOnly(True)
        from .widgets import wrap_log
        wrap_log(self.text)
        lay.addWidget(self.text)
        app.runner.dry_run.connect(self.add)

    def add(self, cmd: str):
        self.text.appendPlainText(cmd)
        n = self.text.blockCount()
        self.count.setText(f"{n:,} change(s) held back by dry run – nothing below was run.")
        tabs = self.app.bottom_tabs
        tabs.setTabText(tabs.indexOf(self), f"Dry run ({n})")

    def clear(self):
        self.text.clear()
        self.app.runner.dry_runs.clear()
        tabs = self.app.bottom_tabs
        tabs.setTabText(tabs.indexOf(self), "Dry run")
        self.count.setText("Cleared.")

    def copy(self):
        QApplication.clipboard().setText(self.text.toPlainText())

    def save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save commands", "dry-run.txt",
                                              "Text (*.txt);;GAM batch file (*.bat)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.text.toPlainText() + "\n")
