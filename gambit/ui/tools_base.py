"""Shared base for the extra tool tabs (Photos, Health, Coursework, …)."""

from __future__ import annotations

import csv
import io

from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from .steps import Step, StepList


class ToolTab(QScrollArea):
    """A scrolling tab that belongs to a Page (uses its runner, directory and dialogs)."""

    intro = ""

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget(objectName="Page")
        self.lay = QVBoxLayout(inner)
        self.setWidget(inner)
        if self.intro:
            tip = QLabel(self.intro)
            tip.setWordWrap(True)
            self.lay.addWidget(tip)
        self.status = QLabel("", objectName="Muted")
        self.status.setWordWrap(True)
        try:
            self.build()
        except Exception as exc:  # noqa: BLE001
            from .widgets import build_failed
            build_failed(self.lay, self, exc)

    def build(self):  # override
        pass

    # ---------------------------------------------------------- helpers ---
    @property
    def directory(self):
        return self.page.directory

    def row(self, *w, stretch=True):
        return self.page.row(*w, stretch=stretch)

    def info(self, text):
        self.page.info(text)

    def confirm(self, text) -> bool:
        return self.page.confirm(text)

    def read(self, args: list[str], then, what: str = "Reading from Google…"):
        """Run a read-only gam command; then(rows) gets the CSV rows (or None on failure)."""
        try:   # the Chromebook fleet list loaded at the top of the page
            from .. import fleet_cache
            cached = fleet_cache.get([str(a) for a in args])
            if cached is not None:
                then(cached)
                return
        except Exception:  # noqa: BLE001
            pass
        self.status.setText(what)

        def done(code, out, _err):
            if code != 0:
                self.status.setText("GAM reported a problem – see the Output panel.")
                then(None)
                return
            self.status.setText("")
            then(list(csv.DictReader(io.StringIO(out or ""))))
        if not self.page.runner.run([str(a) for a in args], done, quiet_stdout=True):
            self.status.setText("")

    def read_many(self, arg_lists: list[list[str]], then, what: str = "Reading from Google…"):
        """Run several reads one after another; then(list of row lists)."""
        results: list = []
        todo = list(arg_lists)

        def nxt():
            if not todo:
                then(results)
                return
            self.read(todo.pop(0), lambda rows: (results.append(rows or []), nxt()), what)
        nxt()

    def steps_list(self) -> StepList:
        sl = StepList(self.page)
        sl.setMaximumHeight(170)
        return sl

    def run_steps(self, sl: StepList, steps: list[tuple[str, list[str]]], done=None):
        def finished(_s):
            self.info(sl.summary())
            if done:
                done(_s)
        sl.run([Step(label, [str(a) for a in args]) for label, args in steps], finished)


__all__ = ["ToolTab", "Step"]
