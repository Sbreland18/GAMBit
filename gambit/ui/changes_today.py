"""“Changes today”: every change GAMbit made today on this PC (and the team's, when a team
folder is set), newest first, each with Undo when GAMbit knows how to put it back."""

from __future__ import annotations

import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)


def todays_changes(team: bool = False) -> list[dict]:
    from .. import activity
    today = datetime.date.today().isoformat()
    return [e for e in activity.load(days=1, team=team)
            if e.get("change") and e.get("time", "")[:10] == today and not e.get("undo_of")]


class ChangesToday(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Changes today")
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(QLabel("Changes today", objectName="MsgTitle"))
        head.addStretch(1)
        self.team_cb = QCheckBox("Include the team's changes")
        from .. import team
        self.team_cb.setVisible(bool(team.folder()))
        self.team_cb.toggled.connect(lambda _on: self.fill())
        head.addWidget(self.team_cb)
        lay.addLayout(head)
        lay.addWidget(QLabel("Undo puts back what GAMbit saved before the change (org unit, "
                             "suspended, group membership…). Undo is only offered when GAMbit "
                             "knows the earlier state.", objectName="Muted", wordWrap=True))
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.NoFrame)
        self.box = QWidget(objectName="Page")
        self.rows = QVBoxLayout(self.box)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(6)
        sc.setWidget(self.box)
        lay.addWidget(sc, 1)
        foot = QHBoxLayout()
        log = QPushButton("Open the activity log")
        log.clicked.connect(lambda: (self.accept(), win._go_safe("Activity log")))
        foot.addWidget(log)
        foot.addStretch(1)
        close = QPushButton("Close")
        close.setProperty("kind", "primary")
        close.clicked.connect(self.accept)
        foot.addWidget(close)
        lay.addLayout(foot)
        self.fill()

    def fill(self):
        while self.rows.count():
            it = self.rows.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        items = todays_changes(self.team_cb.isChecked())
        if not items:
            self.rows.addWidget(QLabel("No changes yet today.", objectName="Muted"))
        for e in items[:200]:
            self.rows.addWidget(self._row(e))
        self.rows.addStretch(1)

    def _row(self, e: dict):
        w = QWidget(objectName="ChangeRow")
        w.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(w)
        h.setContentsMargins(12, 8, 8, 8)
        h.setSpacing(12)
        t = QLabel(e.get("time", "")[11:16], objectName="Muted")
        t.setFixedWidth(44)
        h.addWidget(t)
        v = QVBoxLayout()
        v.setSpacing(0)
        what = QLabel(e.get("what") or e.get("command", ""), objectName="RowTitle")
        what.setWordWrap(True)
        what.setToolTip(e.get("command", ""))
        v.addWidget(what)
        ok = e.get("code") == 0
        bits = [e.get("who", "")]
        if not ok:
            bits.append("didn't work")
        if e.get("undone"):
            bits.append("undone")
        v.addWidget(QLabel(" · ".join(b for b in bits if b), objectName="RowSub"))
        h.addLayout(v, 1)
        b = QPushButton("Undo")
        can = bool(e.get("undo")) and ok and not e.get("undone") and \
            e.get("integrity") != "bad"
        b.setEnabled(can)
        b.setToolTip("Put it back the way it was" if can else
                     "This log entry was changed outside GAMbit" if e.get("integrity") == "bad"
                     else
                     "Already undone" if e.get("undone") else
                     "GAMbit doesn't know the earlier state for this one")
        b.clicked.connect(lambda _=False, e=e, b=b: self._undo(e, b))
        h.addWidget(b)
        return w

    def _undo(self, e, b):
        from PySide6.QtWidgets import QMessageBox
        from ..gam_runner import display_command
        steps = e["undo"].get("steps") or [e["undo"]["args"]]
        # the exact commands – log entries can come from other computers' log files
        cmds = "\n".join("    " + display_command(c) for c in steps)
        if QMessageBox.question(self, "Undo this change?",
                                f"Undo: {e.get('what') or e.get('command')}?\n\n"
                                f"GAMbit will run:\n{cmds}") != QMessageBox.Yes:
            return
        self.win.run_undo(e)
        b.setEnabled(False)
        b.setText("Undoing…")
