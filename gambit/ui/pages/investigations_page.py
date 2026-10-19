"""Investigations: audit logs, Meet usage and third-party app access."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QSpinBox, QTabWidget

from ...tools import investigate as inv
from ..pickers import OUField, PersonField
from ..tools_base import ToolTab
from ..widgets import Page, ResultsTable, button


class ActivityTab(ToolTab):
    intro = ("Search Google's audit logs. Pick a question below, or choose the log yourself. "
             "Google keeps about six months of most logs; very recent events can take a few "
             "hours to show up.")

    def build(self):
        box, form = self.page.group("What do you want to know?")
        self.preset = QComboBox()
        self.preset.addItem("Choose the log myself", None)
        for p in inv.PRESETS:
            self.preset.addItem(p[0], p)
        self.preset.currentIndexChanged.connect(self._preset)
        self.app = QComboBox()
        for label, val in inv.APPS:
            self.app.addItem(label, val)
        self.who = PersonField(self.directory, "Anyone (leave empty) – or a person")
        self.ou = OUField(self.directory, "or an org unit")
        self.doc = QLineEdit(placeholderText="Paste a Google Drive / Docs link (Drive only)")
        self.events = QLineEdit(placeholderText="optional, e.g. view,download")
        self.days = QSpinBox()
        self.days.setRange(1, 180)
        self.days.setValue(30)
        self.days.setSuffix(" days")
        self.hint = QLabel("", objectName="Muted")
        form.addRow("Question", self.preset)
        form.addRow("", self.hint)
        form.addRow("Log", self.app)
        form.addRow("Person", self.who)
        form.addRow("Org unit", self.ou)
        form.addRow("File", self.doc)
        form.addRow("Events", self.events)
        form.addRow("Look back", self.days)
        form.addRow("", self.row(button("Search", "primary", self.search), self.status))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(360)
        self.lay.addWidget(self.table, 1)

    def _preset(self, *_):
        p = self.preset.currentData()
        if not p:
            self.hint.setText("")
            return
        _label, app, events, why = p
        self.app.setCurrentIndex(self.app.findData(app))
        self.events.setText(events)
        self.hint.setText(why)

    def search(self):
        app = self.app.currentData()
        who = self.who.email()
        doc = inv.doc_id(self.doc.text()) if app == "drive" else ""
        if self.doc.text().strip() and app == "drive" and not doc:
            self.info("That doesn't look like a Drive link.")
            return
        p = self.preset.currentData()
        admin_target = who if (app == "admin" and p and p[1] == "admin") else ""
        args = inv.report_args(app, "" if admin_target else who, self.ou.path(),
                               self.days.value(), self.events.text().strip(), doc,
                               admin_target)

        def done(rows):
            if rows is None:
                return
            heads, data = inv.tidy(rows)
            self.table.set_rows(heads, data)
            self.status.setText(f"{len(data):,} event(s)" if data else "Nothing found.")
        self.read(args, done, "Searching the audit log (this can take a minute)…")


class MeetTab(ToolTab):
    intro = ("How much Google Meet is used, grouped by the organizer's org unit – meetings, "
             "participants and hours. Uses Google's Meet audit log.")

    def build(self):
        self.days = QSpinBox()
        self.days.setRange(1, 180)
        self.days.setValue(30)
        self.days.setSuffix(" days")
        self.depth = QSpinBox()
        self.depth.setRange(1, 4)
        self.depth.setValue(2)
        self.lay.addLayout(self.row(QLabel("Last"), self.days, QLabel("Group by org-unit level"),
                                    self.depth, button("Build the report", "primary", self.load),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(360)
        self.lay.addWidget(self.table, 1)

    def load(self):
        def done(rows):
            if rows is None:
                return
            u = inv.meet_usage(rows, self.directory.users, self.depth.value())
            heads = list(u[0].keys()) if u else ["(no meetings)"]
            self.table.set_rows(heads, [[r[h] for h in heads] for r in u])
            self.status.setText(f"{len(rows):,} participant session(s)")
        self.read(inv.meet_args(self.days.value()), done,
                  "Reading the Meet log (large districts: a few minutes)…")


class AppAccessTab(ToolTab):
    intro = ("Third-party apps people have signed in to with their Google account, and what "
             "they can reach. Select one and remove its access from everyone in the org unit "
             "at once. To stop people signing in to it again, also block it in the Admin "
             "console (Security → API controls).")

    def build(self):
        self.ou = OUField(self.directory, "/Students")
        self.ou.set_path("/Students")
        self.lay.addLayout(self.row(QLabel("People under"), self.ou,
                                    button("List apps", "primary", self.load),
                                    button("Remove selected app from everyone…", "danger",
                                           self.revoke), stretch=False))
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(360)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def load(self):
        def done(rows):
            if rows is None:
                return
            t = inv.token_rows(rows)
            heads = ["App", "People", "Can reach", "Client ID"]
            self.table.set_rows(heads, [[r[h] for h in heads] for r in t])
            self.status.setText(f"{len(t):,} app(s)")
        self.read(inv.tokens_args(self.ou.path() or "/"), done,
                  "Reading app access for everyone (large org units take a while)…")

    def revoke(self):
        sel = self.table.selected_dicts()
        if not sel:
            self.info("Select an app first.")
            return
        app = sel[0]
        ou = self.ou.path() or "/"
        if not self.confirm(f"Remove “{app['App']}” from everyone under {ou}?\n\n"
                            f"{app['People']} person(s) use it. They'll be signed out of it and "
                            "can sign in again unless you block it in the Admin console."):
            return
        self.run_steps(self.steps, [(f"Remove {app['App']} from {ou}",
                                     inv.revoke_args(ou, app["Client ID"]))],
                       lambda _s: self.load())


class InvestigationsPage(Page):
    title = "Investigations"
    subtitle = ("Who opened, downloaded or shared a file; suspicious sign-ins; admin changes; "
                "Meet usage; and third-party apps with access to accounts.")

    def build(self):
        self.tabs = QTabWidget()
        self.activity = ActivityTab(self)
        self.meet = MeetTab(self)
        self.apps = AppAccessTab(self)
        self.tabs.addTab(self.activity, "Audit log")
        self.tabs.addTab(self.meet, "Meet usage")
        self.tabs.addTab(self.apps, "App access")
        from .insight_pages import WatchdogTab
        self.watchdog = WatchdogTab(self)
        self.tabs.addTab(self.watchdog, "Unusual activity")
        from .round11_pages import ApprovedAppsTab, PhishingTab
        self.phishing_tab = PhishingTab(self)
        self.apps_check_tab = ApprovedAppsTab(self)
        self.tabs.addTab(self.phishing_tab, "Phishing clean-up")
        self.tabs.addTab(self.apps_check_tab, "Approved apps")
        from .round13_tabs import AppPasswordsTab, FileActivityTab
        self.file_activity_tab, self.asps_tab = FileActivityTab(self), AppPasswordsTab(self)
        self.tabs.addTab(self.file_activity_tab, "File activity")
        self.tabs.addTab(self.asps_tab, "App passwords")
        from .round14_tabs import PublicAppsTab, SharedPasswordsTab
        self.public_apps_tab, self.shared_tab = PublicAppsTab(self), SharedPasswordsTab(self)
        self.tabs.addTab(self.public_apps_tab, "Public apps list")
        self.tabs.addTab(self.shared_tab, "Shared passwords")
        self.body.addWidget(self.tabs, 1)
