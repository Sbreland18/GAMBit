"""Run a list of GAM commands one after another with a live checklist."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

ICONS = {"pending": "○", "running": "◐", "ok": "✔", "fail": "✖", "skip": "–", "dry": "◇"}
COLORS = {"pending": "#57606a", "running": "#1a73e8", "ok": "#137333", "fail": "#b42318",
          "skip": "#9aa4ae", "dry": "#9a6700"}


@dataclass
class Step:
    label: str
    args: list[str]
    required: bool = False          # stop everything after this if it fails
    on_done: Optional[Callable[[int, str, str], None]] = None
    status: str = field(default="pending")


class StepList(QListWidget):
    """Shows each step with a status icon and runs them through the GamRunner."""

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.steps: list[Step] = []
        self.setFocusPolicy(Qt.NoFocus)
        self.setMinimumHeight(140)
        self._finished: Optional[Callable[[list[Step]], None]] = None

    def set_steps(self, steps: list[Step]):
        self.steps = steps
        self.clear()
        for s in steps:
            QListWidgetItem("", self)
        self._paint()

    def _paint(self):
        for i, s in enumerate(self.steps):
            it = self.item(i)
            it.setText(f"{ICONS[s.status]}  {s.label}")
            from PySide6.QtGui import QColor
            it.setForeground(QColor(COLORS[s.status]))

    def run(self, steps: list[Step], finished: Optional[Callable[[list[Step]], None]] = None):
        # The person already approved the whole plan, so don't ask again per step
        app = getattr(self.page, "app", None)
        if app is not None:
            app._batch_ok = True

        def done(s):
            if app is not None:
                app._batch_ok = False
                if hasattr(app, "flush_blocked_batch"):
                    app.flush_blocked_batch()
                if hasattr(app, "ticket_note"):
                    try:
                        app.ticket_note(s)
                    except Exception:  # noqa: BLE001
                        pass
            if finished:
                finished(s)
        self.set_steps(steps)
        self._finished = done
        self._next(0)

    def _next(self, i: int):
        if i >= len(self.steps):
            if self._finished:
                self._finished(self.steps)
            return
        step = self.steps[i]
        step.status = "running"
        self._paint()
        self.scrollToItem(self.item(i))

        from ..gam_runner import dry_run_on, is_change
        dry = dry_run_on() and is_change([str(a) for a in step.args])

        def done(code, out, err):
            step.status = ("dry" if dry else "ok") if code == 0 else "fail"
            if step.on_done:
                step.on_done(code, out, err)
            if code != 0 and step.required:
                for s in self.steps[i + 1:]:
                    s.status = "skip"
                self._paint()
                if self._finished:
                    self._finished(self.steps)
                return
            self._paint()
            self._next(i + 1)

        if not self.page.runner.run([str(a) for a in step.args], done):
            done(-1, "", "")

    def summary(self) -> str:
        dry = sum(s.status == "dry" for s in self.steps)
        if dry:
            return (f"Dry run: {dry} change(s) were not made – see the Dry run tab for the "
                    f"exact GAM commands. {sum(s.status == 'ok' for s in self.steps)} "
                    "look-up step(s) ran normally.")
        ok = sum(s.status == "ok" for s in self.steps)
        bad = [s.label for s in self.steps if s.status == "fail"]
        skipped = sum(s.status == "skip" for s in self.steps)
        text = f"{ok} of {len(self.steps)} steps finished."
        if bad:
            text += "\n\nThese didn't work (see the Output panel for details):\n• " + \
                    "\n• ".join(bad)
        if skipped:
            text += f"\n\n{skipped} step(s) were skipped because an earlier required step failed."
        return text
