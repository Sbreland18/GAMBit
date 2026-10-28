"""Student lookup → Check everything: every problem with one person, each with a fix."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from .steps import Step, StepList
from .widgets import Worker, button

ICON = {"bad": ("✖", "#cf222e"), "warn": ("⚠", "#9a6700"), "ok": ("✔", "#1a7f37")}


class PersonCheckDialog(QDialog):
    def __init__(self, page, email: str, ticket_id: str = ""):
        super().__init__(page)
        self.page, self.email, self.ticket_id = page, email, ticket_id
        self.findings: list[dict] = []
        self.fixed: list[str] = []
        self.setWindowTitle(f"Check everything – {email}")
        self.resize(820, 600)
        v = QVBoxLayout(self)
        self.head = QLabel(f"Checking <b>{email}</b>…")
        self.head.setWordWrap(True)
        v.addWidget(self.head)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        v.addWidget(self.area, 1)
        self.sl = StepList(page)
        self.sl.setMaximumHeight(120)
        v.addWidget(self.sl)
        row = QHBoxLayout()
        self.fix_all = button("Fix everything GAMbit can", "primary", self.fix_everything)
        row.addWidget(self.fix_all)
        row.addWidget(button("Check again", slot=self.run))
        self.note_btn = button("Add this to the ticket", slot=self.add_note)
        self.note_btn.setVisible(bool(ticket_id))
        row.addWidget(self.note_btn)
        row.addStretch(1)
        row.addWidget(button("Close", slot=self.accept))
        v.addLayout(row)
        self.run()

    def run(self):
        from .. import person_check as pc
        self.head.setText(f"Checking <b>{self.email}</b>…")
        Worker(pc.run, self.email, on_done=self._show,
               on_error=lambda e: self.head.setText(f"Couldn't check: {e}"))

    def _show(self, findings):
        self.findings = findings
        bad = sum(f["level"] == "bad" for f in findings)
        warn = sum(f["level"] == "warn" for f in findings)
        self.head.setText(f"<b>{self.email}</b> – " + (
            "everything looks right." if not bad and not warn else
            f"<span style='color:#cf222e'>{bad} problem(s)</span>, "
            f"<span style='color:#9a6700'>{warn} thing(s) to look at</span>."))
        w = QWidget()
        lay = QVBoxLayout(w)
        for f in findings:
            card = QFrame(objectName="Card")
            h = QHBoxLayout(card)
            icon, col = ICON[f["level"]]
            ic = QLabel(f"<span style='font-size:16pt;color:{col}'>{icon}</span>")
            ic.setFixedWidth(30)
            h.addWidget(ic)
            txt = QLabel(f"<b>{f['problem']}</b>" + (f"<br><span style='color:#57606a'>"
                                                     f"{f['detail']}</span>"
                                                     if f["detail"] else ""))
            txt.setWordWrap(True)
            txt.setTextInteractionFlags(Qt.TextSelectableByMouse)
            h.addWidget(txt, 1)
            if f["problem"] in self.fixed:
                h.addWidget(QLabel("<span style='color:#1a7f37'>Fixed</span>"))
            elif f["commands"] or f["special"]:
                h.addWidget(button(f["fix"] or "Fix", "primary",
                                   lambda _=False, f=f: self.fix([f])))
            lay.addWidget(card)
        lay.addStretch(1)
        self.area.setWidget(w)
        self.fix_all.setEnabled(any(f["commands"] for f in findings
                                    if f["problem"] not in self.fixed))

    def fix(self, items: list[dict]):
        specials = [f for f in items if f["special"] == "reset"]
        if specials and hasattr(self.page, "reset"):
            self.page.reset()
            self.fixed += [f["problem"] for f in specials]
        steps = [(f["fix"] or f["problem"], a) for f in items for a in f["commands"]]
        if not steps:
            self._show(self.findings)
            return
        listing = "\n".join(f"• {lab}" for lab, _a in steps)
        if not self.page.confirm(f"Fix for {self.email}:\n\n{listing}"):
            return

        def done(_s):
            self.fixed += [f["problem"] for f in items if f["commands"]]
            self.run()
        self.sl.run([Step(lab, [str(x) for x in a]) for lab, a in steps], done)

    def fix_everything(self):
        self.fix([f for f in self.findings if f["commands"] and
                  f["problem"] not in self.fixed])

    def add_note(self):
        from .. import person_check as pc
        from ..integrations import ticketing as tk
        if not self.ticket_id:
            return
        text = pc.summary(self.email, self.findings, self.fixed)
        Worker(tk.note, self.ticket_id, text,
               on_done=lambda _r: self.head.setText(self.head.text() + "  ✓ Added to the "
                                                    "ticket."),
               on_error=lambda e: self.page.info(f"Couldn't add the note: {e}"))
