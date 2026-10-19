"""Account timeline: everything that happened to one account, in one place."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLabel, QSpinBox

from ... import timeline
from ..pickers import PersonField
from ..widgets import Page, ResultsTable, Worker, button


class TimelinePage(Page):
    title = "Account timeline"
    subtitle = ("Why can't this student sign in? Everything that happened to one account – "
                "GAMbit changes, offboarding, Admin console changes and sign-ins – newest first.")

    def build(self):
        self.who = PersonField(self.directory, "Start typing a name or email…")
        self.who.returnPressed.connect(self.show_for)
        self.days = QSpinBox()
        self.days.setRange(1, 180)
        self.days.setValue(30)
        self.days.setSuffix(" days")
        self.google = QCheckBox("Include Google's admin and sign-in logs")
        self.google.setChecked(True)
        self.body.addLayout(self.row(self.who, QLabel("Last"), self.days, self.google,
                                     button("Show", "primary", self.show_for), stretch=False))
        self.card = QLabel("")
        self.card.setWordWrap(True)
        self.body.addWidget(self.card)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)

    def open_for(self, email: str):
        self.who.setText(email)
        self.show_for()

    def show_for(self):
        e = self.who.email()
        if "@" not in e:
            self.info("Choose a person.")
            return
        u = next((x for x in self.directory.users if x["email"].lower() == e.lower()), None)
        if u:
            state = "<span style='color:#b42318'>✖ Suspended</span>" if u.get("suspended") \
                else "<span style='color:#137333'>✔ Active</span>"
            self.card.setText(f"<b>{u.get('name', '')}</b> &lt;{u['email']}&gt; · {state} · "
                              f"org unit {u.get('ou', '/')} · last sign-in "
                              f"{(u.get('last_login') or 'never')[:16].replace('T', ' ')}")
        else:
            self.card.setText(f"<b>{e}</b> isn't in GAMbit's user list (deleted, or the list "
                              "needs a refresh).")
        self.table.set_rows(["When", "Where", "Who", "What", "Details"],
                            [["…", "", "", "Loading…", ""]])

        def done(res):
            events, problems = res
            self.table.set_rows(["When", "Where", "Who", "What", "Details"],
                                [[x["time"], x["source"], x["who"], x["what"], x["detail"]]
                                 for x in events])
            if problems:
                self.card.setText(self.card.text() + "<br><span style='color:#9a6700'>" +
                                  "; ".join(problems) + "</span>")
        Worker(timeline.gather, e, self.days.value(), self.google.isChecked(), on_done=done,
               on_error=lambda ex: self.card.setText(f"Couldn't build the timeline: {ex}"))
