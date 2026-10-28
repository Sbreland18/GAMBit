"""Step-by-step forms: Details → Groups & license → Review. The Review step lists exactly
what will happen (and the GAM commands, if you want to see them) before anything runs."""

from __future__ import annotations

import html
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout,
    QWidget,
)

from .widgets import button


class _Dot(QWidget):
    def __init__(self, n: int, title: str, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.num = QLabel(str(n), objectName="StepNum")
        self.num.setFixedSize(28, 28)
        self.num.setAlignment(Qt.AlignCenter)
        self.title = QLabel(title, objectName="StepTitle")
        h.addWidget(self.num)
        h.addWidget(self.title)

    def set_state(self, state: str):            # todo | current | done
        for w in (self.num, self.title):
            w.setProperty("state", state)
            w.style().unpolish(w)
            w.style().polish(w)
        if state == "done":
            self.num.setText("✓")


class Stepper(QWidget):
    finished = Signal()

    def __init__(self, steps: list[tuple[str, QWidget]], review: Callable[[], list],
                 finish_text: str, on_finish: Callable[[], None],
                 validate: dict | None = None, extra_buttons=(), parent=None):
        """steps: (title, widget). review() → list of (what, gam command text) pairs.
        validate: {step index: fn() → bool} checked before moving on."""
        super().__init__(parent)
        self.steps = list(steps) + [("Review", None)]
        self.review_fn, self.on_finish = review, on_finish
        self.validate = validate or {}
        self.i = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        head = QHBoxLayout()
        head.setSpacing(10)
        self.dots = []
        for n, (title, _w) in enumerate(self.steps, 1):
            if n > 1:
                line = QFrame(objectName="StepLine")
                line.setFixedHeight(2)
                line.setMinimumWidth(30)
                head.addWidget(line, 1)
            d = _Dot(n, title)
            d.mousePressEvent = lambda _e, k=n - 1: self._jump(k)
            d.setCursor(Qt.PointingHandCursor)
            self.dots.append(d)
            head.addWidget(d)
        head.addStretch(3)
        lay.addLayout(head)
        self.stack = QStackedWidget()
        for _title, w in steps:
            self.stack.addWidget(w)
        # review page
        rv = QWidget()
        rl = QVBoxLayout(rv)
        rl.setContentsMargins(0, 0, 0, 0)
        card = QFrame(objectName="Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(8)
        cl.addWidget(QLabel("What will happen", objectName="SectionTitle"))
        self.review_lbl = QLabel("")
        self.review_lbl.setWordWrap(True)
        self.review_lbl.setTextFormat(Qt.RichText)
        cl.addWidget(self.review_lbl)
        self.cmd_btn = QPushButton("Show the GAM commands")
        self.cmd_btn.setCheckable(True)
        self.cmd_btn.toggled.connect(self._toggle_cmds)
        cl.addWidget(self.cmd_btn, 0, Qt.AlignLeft)
        self.cmds = QLabel("", objectName="StepCmds")
        self.cmds.setWordWrap(True)
        self.cmds.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.cmds.hide()
        cl.addWidget(self.cmds)
        rl.addWidget(card)
        rl.addStretch(1)
        self.stack.addWidget(rv)
        lay.addWidget(self.stack)
        foot = QHBoxLayout()
        self.back_btn = button("Back", slot=lambda: self.go(self.i - 1))
        self.next_btn = button("Next", "primary", self.next)
        self.finish_btn = button(finish_text, "primary", self._finish)
        for b in extra_buttons:
            foot.addWidget(b)
        foot.addStretch(1)
        foot.addWidget(self.back_btn)
        foot.addWidget(self.next_btn)
        foot.addWidget(self.finish_btn)
        lay.addLayout(foot)
        lay.addStretch(1)
        self.go(0)

    # ---------------------------------------------------------------- move ---
    def _ok(self, k: int) -> bool:
        fn = self.validate.get(k)
        return bool(fn()) if fn else True

    def _jump(self, k: int):
        if k <= self.i:
            self.go(k)
            return
        for j in range(self.i, k):          # forward: every step on the way must be OK
            if not self._ok(j):
                self.go(j)
                return
        self.go(k)

    def next(self):
        if self._ok(self.i):
            self.go(self.i + 1)

    def go(self, k: int):
        k = max(0, min(len(self.steps) - 1, k))
        self.i = k
        from PySide6.QtWidgets import QSizePolicy
        for n in range(self.stack.count()):     # size to the step you're on, not the tallest
            pol = QSizePolicy.Preferred if n == k else QSizePolicy.Ignored
            self.stack.widget(n).setSizePolicy(pol, pol)
        self.stack.setCurrentIndex(k)
        self.stack.adjustSize()
        last = k == len(self.steps) - 1
        if last:
            self._fill_review()
        for n, d in enumerate(self.dots):
            d.set_state("done" if n < k else "current" if n == k else "todo")
            if n >= k:
                d.num.setText(str(n + 1))
        self.back_btn.setVisible(k > 0)
        self.next_btn.setVisible(not last)
        self.finish_btn.setVisible(last)

    def reset(self):
        self.cmd_btn.setChecked(False)
        self.go(0)

    # -------------------------------------------------------------- review ---
    def _fill_review(self):
        try:
            items = self.review_fn() or []
        except Exception as exc:  # noqa: BLE001
            items = [(f"Couldn't build the plan: {exc}", "")]
        rows = "".join(f"<li style='margin:4px 0'>{html.escape(what)}</li>"
                       for what, _c in items)
        self.review_lbl.setText(f"<ol style='margin:0 0 0 -18px'>{rows}</ol>" if rows else
                                "Nothing to do yet – go back and fill in the details.")
        cmds = [c for _w, c in items if c]
        self.cmds.setText("<br>".join(f"<code>{html.escape(c)}</code>" for c in cmds))
        self.cmd_btn.setVisible(bool(cmds))
        self.finish_btn.setEnabled(bool(items))

    def _toggle_cmds(self, on: bool):
        self.cmds.setVisible(on)
        self.cmd_btn.setText("Hide the GAM commands" if on else "Show the GAM commands")

    def _finish(self):
        self.on_finish()
        self.finished.emit()


def scroll(widget: QWidget) -> QScrollArea:
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QScrollArea.NoFrame)
    sc.setWidget(widget)
    return sc
