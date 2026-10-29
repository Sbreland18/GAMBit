"""Reports: inactive accounts, activity logs, Chromebook end-of-updates, storage."""

from __future__ import annotations

from ... import queries as _q
import datetime

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QLabel, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ..pickers import OUField, OUMultiField, PersonField
from ..widgets import Page, ResultsTable, button

ACTIVITY_APPS = [
    ("Admin console changes", "admin"),
    ("Sign-ins", "login"),
    ("Drive activity", "drive"),
    ("Third-party app access (OAuth)", "token"),
    ("Groups changes", "groups"),
    ("Classroom", "classroom"),
    ("Chrome / ChromeOS", "chrome"),
    ("Account changes (password, 2SV)", "useraccounts"),
    ("Mobile devices", "mobile"),
    ("Meet", "meet"),
    ("Calendar", "calendar"),
    ("Chat", "chat"),
    ("Data protection rules (DLP)", "rules"),
    ("Gemini", "gemini"),
    ("Single sign-on (SAML)", "saml"),
    ("Context-aware access", "contextawareaccess"),
    ("Keep", "keep"),
    ("Vault", "vault"),
    ("Looker Studio", "datastudio"),
    ("Takeout", "takeout"),
    ("Assignments", "assignments"),
]
RANGES = [("Today", ["today"]), ("Yesterday", ["yesterday"]),
          ("Last 7 days", ["start", "-7d"]), ("Last 30 days", ["start", "-30d"]),
          ("This month", ["thismonth"])]


def parse_date(text: str) -> datetime.date | None:
    """GAM dates come as ISO strings or epoch milliseconds; 'Never' → None."""
    t = (text or "").strip()
    if not t or t.lower().startswith("never"):
        return None
    try:
        if t.isdigit():
            return datetime.datetime.utcfromtimestamp(int(t) / 1000).date()
        d = datetime.date.fromisoformat(t[:10])
        return None if d.year < 1980 else d
    except ValueError:
        return None


def _col(row: dict, name: str) -> str:
    low = name.lower()
    return next((v for k, v in row.items() if (k or "").lower() == low), "") or ""


class ReportsPage(Page):
    title = "Reports"
    subtitle = "Find inactive accounts, read audit logs, plan Chromebook replacements and spot storage hogs."

    def build(self):
        tabs = QTabWidget()
        tabs.addTab(self._inactive_tab(), "Inactive accounts")
        tabs.addTab(self._activity_tab(), "Activity logs")
        tabs.addTab(self._aue_tab(), "Chromebook end of updates")
        tabs.addTab(self._storage_tab(), "Storage")
        self.body.addWidget(tabs, 1)

    # ======================================================= inactive ===
    def _inactive_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        box, form = self.group("Accounts nobody has signed in to")
        self.i_days = QSpinBox()
        self.i_days.setRange(1, 3650)
        self.i_days.setValue(90)
        self.i_days.setSuffix(" days")
        self.i_ous = OUMultiField(self.directory)
        self.i_susp = QCheckBox("Include accounts that are already suspended")
        self.i_never = QCheckBox("Include accounts that have never signed in")
        self.i_never.setChecked(True)
        form.addRow("No sign-in for at least", self.i_days)
        form.addRow("Only in (optional)", self.i_ous)
        form.addRow("", self.i_susp)
        form.addRow("", self.i_never)
        form.addRow("", self.row(button("Find inactive accounts", "primary", self.inactive)))
        lay.addWidget(box)
        self.i_results = ResultsTable()
        lay.addWidget(self.i_results, 1)
        self.i_move = OUField(self.directory, "e.g. /Inactive")
        lay.addLayout(self.row(QLabel("Selected accounts:"),
                               button("Suspend", "danger", self.i_suspend),
                               self.i_move, button("Move to OU", slot=self.i_move_ou)))
        return w

    def inactive(self):
        days = self.i_days.value()
        cutoff = datetime.date.today() - datetime.timedelta(days=days)
        include_never = self.i_never.isChecked()
        base = ["print", "users"]
        fields = ["fields", "primaryemail,name,ou,lastlogintime,creationtime,suspended"]
        susp = [] if self.i_susp.isChecked() else ["isSuspended=false"]
        ous = self.i_ous.paths()
        cmds = []
        for ou in (ous or [None]):
            q = list(susp)
            if ou and ou != "/":
                q.append(_q.ou(ou))
            from ... import custom_fields
            cmds.append(custom_fields.with_custom(base + (["query", " ".join(q)] if q else []) +
                                                  fields))

        def keep(r):
            last = parse_date(_col(r, "lastLoginTime"))
            created = parse_date(_col(r, "creationTime"))
            if created and created > cutoff:
                return False  # brand-new account – give it time
            if last is None:
                return include_never
            return last <= cutoff
        self.run_many(cmds, lambda outs: (self.i_results.load_csv_many(outs, keep),
                                          self.info(f"{self.i_results.row_count()} account(s) "
                                                    f"with no sign-in since {cutoff:%b %d, %Y}.")))

    def _i_selected(self):
        emails = self.i_results.selected_values("primaryEmail")
        if not emails:
            self.info("Select accounts in the list first.")
        return emails

    def i_suspend(self):
        emails = self._i_selected()
        if emails and self.confirm(f"Suspend {len(emails)} account(s)?"):
            self.run(["users", ",".join(emails), "update", "user", "suspended", "on"])

    def i_move_ou(self):
        emails = self._i_selected()
        ou = self.i_move.path()
        if emails and not ou:
            self.info("Choose the org unit to move them to.")
        elif emails and self.confirm(f"Move {len(emails)} account(s) to {ou}?"):
            self.run(["update", "ou", ou, "move", "users", ",".join(emails)])

    # ======================================================= activity ===
    def _activity_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        box, form = self.group("Audit and activity logs")
        self.a_app = QComboBox()
        for label, val in ACTIVITY_APPS:
            self.a_app.addItem(label, val)
        self.a_user = PersonField(self.directory, "Everyone (or pick a person)")
        self.a_range = QComboBox()
        for label, val in RANGES:
            self.a_range.addItem(label, val)
        self.a_range.setCurrentIndex(2)
        self.a_event = QComboBox()
        self.a_event.setEditable(True)
        self.a_app.currentIndexChanged.connect(self._events)
        self.a_max = QSpinBox()
        self.a_max.setRange(10, 100000)
        self.a_max.setValue(1000)
        form.addRow("Log", self.a_app)
        form.addRow("Person", self.a_user)
        form.addRow("When", self.a_range)
        form.addRow("Only this event", self.a_event)
        form.addRow("At most", self.a_max)
        form.addRow("", self.row(button("Show activity", "primary", self.activity),
                                 button("Recent sharing changes in Drive",
                                        slot=self.sharing_activity)))
        lay.addWidget(box)
        self.a_results = ResultsTable()
        lay.addWidget(self.a_results, 1)
        self._events()
        return w

    def _events(self):
        common = {
            "login": ["", "login_failure", "login_success", "suspicious_login",
                      "logout", "account_disabled_password_leak"],
            "admin": ["", "CHANGE_PASSWORD", "CREATE_USER", "DELETE_USER", "SUSPEND_USER",
                      "MOVE_USER_TO_ORG_UNIT", "ASSIGN_ROLE"],
            "drive": ["", "change_user_access", "change_document_visibility", "download",
                      "delete", "trash"],
            "token": ["", "authorize", "revoke"],
        }
        self.a_event.clear()
        self.a_event.addItems(common.get(self.a_app.currentData(), [""]))
        self.a_event.lineEdit().setPlaceholderText("Any event (or type an event name)")

    def activity(self, events: str | None = None, app: str | None = None):
        args = ["report", app or self.a_app.currentData()]
        u = self.a_user.email()
        if "@" in u:
            args += ["user", u]
        args += self.a_range.currentData()
        ev = events if events is not None else self.a_event.currentText().strip()
        if ev:
            args += ["events", ev]
        args += ["maxactivities", str(self.a_max.value())]
        self.run(args, lambda c, out, _e: self.a_results.load_csv(out) if c == 0 else None,
                 quiet=True)

    def sharing_activity(self):
        self.activity("change_user_access,change_document_visibility", "drive")

    # ============================================================ AUE ===
    def _aue_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        box, form = self.group("Chromebooks that stop getting updates soon")
        self.u_months = QSpinBox()
        self.u_months.setRange(0, 120)
        self.u_months.setValue(12)
        self.u_months.setSuffix(" months")
        self.u_months.setSpecialValueText("Already expired")
        self.u_ous = OUMultiField(self.directory)
        self.u_active = QCheckBox("Only active (provisioned) devices")
        self.u_active.setChecked(True)
        form.addRow("Expiring within", self.u_months)
        form.addRow("Only in (optional)", self.u_ous)
        form.addRow("", self.u_active)
        form.addRow("", self.row(button("Find devices", "primary", self.aue)))
        lay.addWidget(box)
        self.u_results = ResultsTable()
        lay.addWidget(self.u_results, 1)
        return w

    def aue(self):
        fields = ["fields", "serialnumber,model,autoupdateexpiration,orgunitpath,annotateduser,"
                            "annotatedassetid,status,lastsync"]
        ous = self.u_ous.paths()
        how = "cros_ou_and_children" if self.u_ous.include_children() else "cros_ou"
        cmds = ([["print", "cros", how, ou] + fields for ou in ous] if ous
                else [["print", "cros"] + fields])
        today = datetime.date.today()
        months = self.u_months.value()
        limit = today + datetime.timedelta(days=int(months * 30.44))
        only_active = self.u_active.isChecked()

        def keep(r):
            if only_active and _col(r, "status").upper() not in ("ACTIVE", ""):
                return False
            d = parse_date(_col(r, "autoUpdateExpiration"))
            return d is not None and d <= limit
        self.run_many(cmds, lambda outs: (
            self.u_results.load_csv_many(outs, keep),
            self.u_results.sort_by(
                [h.lower() for h in self.u_results._headers].index("autoupdateexpiration"))
            if "autoupdateexpiration" in [h.lower() for h in self.u_results._headers] else None))

    # ======================================================== storage ===
    def _storage_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        box, form = self.group("Who is using the most storage")
        self.st_ou = OUField(self.directory, "Whole domain (or pick an org unit)")
        form.addRow("Org unit", self.st_ou)
        form.addRow("", self.row(button("Show storage use", "primary", self.storage)))
        note = QLabel("Google's usage numbers are usually 2–3 days behind. Click a column "
                      "header to sort.", objectName="Muted")
        form.addRow("", note)
        lay.addWidget(box)
        self.st_results = ResultsTable()
        lay.addWidget(self.st_results, 1)
        return w

    def storage(self):
        args = ["report", "users"]
        if self.st_ou.path() and self.st_ou.path() != "/":
            args += ["ou", self.st_ou.path()]
        args += ["parameters", "accounts:used_quota_in_mb,accounts:drive_used_quota_in_mb,"
                               "accounts:gmail_used_quota_in_mb,accounts:last_login_time"]

        def done(code, out, _e):
            if code != 0:
                return
            self.st_results.load_csv(out)
            hdr = [h.lower() for h in self.st_results._headers]
            col = next((i for i, h in enumerate(hdr) if h.endswith("used_quota_in_mb")
                        and "drive" not in h and "gmail" not in h), None)
            if col is not None:
                from PySide6.QtCore import Qt
                self.st_results.sort_by(col, Qt.DescendingOrder)
        self.run(args, done, quiet=True)
