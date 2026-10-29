"""Round 25 pages for GAM features GAMbit didn't cover yet: single sign-on by org unit,
Windows/Mac/phones, shared drives by school, Chat posts, staff calendar status, and the
smaller extras (domain aliases, contact delegates, Tasks, Chrome browser profiles and
enrollment tokens)."""

from __future__ import annotations

import datetime

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QLabel, QLineEdit, QPlainTextEdit, QSpinBox, QTabWidget,
    QTimeEdit,
)

from ..pickers import OUField, PersonField, TargetPicker
from ..tools_base import ToolTab
from ..widgets import Page, ResultsTable, button
from .round11_pages import run_or_request
from .round13_pages import _steps
from .round13_tabs import _csv, _text, fill
from .round25_data import _need_rows, _work


def _x():
    from ...tools import workspace_extras
    return workspace_extras


def _admin(page) -> str:
    from ... import google_io
    a = google_io.admin_email()
    if "@" not in a:
        page.info("Set the Google admin account in Settings & Updates → Google Sheets and "
                  "email first.")
    return a


def _load(page, table: ResultsTable, args: list[str], status=None, then=None):
    def done(code, out, _err):
        if code == 0:
            table.load_csv(out)
        if status is not None:
            status.setText("" if code == 0 else "GAM reported a problem – see the Output "
                           "panel.")
        if then:
            then(code)
    if status is not None:
        status.setText("Reading from Google…")
    page.run([str(a) for a in args], done, quiet=True)


def _col(table: ResultsTable, *names) -> list[str]:
    for n in names:
        v = table.selected_values(n)
        if v:
            return v
    return []


def _day(days: int = 0) -> QDateEdit:
    d = QDateEdit(QDate.currentDate().addDays(days))
    d.setCalendarPopup(True)
    return d


# ========================================================== single sign-on ===
class SSOPage(Page):
    title = "Single sign-on"
    subtitle = ("Which org units and groups sign in through ClassLink, Clever or another "
                "provider, and which use Google passwords. Change one org unit at a time – "
                "for a pilot school, or Google passwords during state testing.")

    def build(self):
        x = _x()
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.tabs = QTabWidget()
        self.assign_t = ResultsTable()
        self.prof_t = ResultsTable()
        self.tabs.addTab(self.assign_t, "Assignments")
        self.tabs.addTab(self.prof_t, "Profiles")
        from .sso_certs import CertificatesTab
        self.certs = CertificatesTab(self)
        self.tabs.addTab(self.certs, "Certificates")
        self.body.addLayout(self.row(button("Load assignments and profiles", "primary",
                                            self.load), self.status))
        box, form = self.group("Set sign-in for an org unit or group")
        self.ou = OUField(self.directory, "/Students/Hancock High School")
        self.group_e = QLineEdit(placeholderText="…or a group email (pilot groups)")
        self.rank = QSpinBox()
        self.rank.setRange(1, 1000)
        self.rank.setPrefix("rank ")
        form.addRow("Org unit", self.ou)
        form.addRow("Group", self.row(self.group_e, self.rank, stretch=False))
        self.mode = QComboBox()
        for k, lab in x.SSO_MODES.items():
            self.mode.addItem(lab, k)
        self.profile = QComboBox()
        self.profile.setEditable(True)
        self.profile.setMinimumWidth(320)
        self.profile.lineEdit().setPlaceholderText("profile (load profiles first)")
        self.never = QCheckBox("Never redirect to the provider from Google's sign-in page")
        form.addRow("Sign in with", self.row(self.mode, self.profile, stretch=False))
        form.addRow("", self.never)
        form.addRow("", self.row(button("Set it", "primary", self.set_it),
                                 button("Remove this assignment (inherit again)", "danger",
                                        self.remove)))
        self.body.addWidget(box)
        self.body.addWidget(self.tabs, 1)

    def load(self):
        def got_profiles(code):
            if code != 0:
                return
            self.profile.clear()
            from ... import sso_watch
            rows = [self.prof_t.row_dict(i) for i in range(self.prof_t.row_count())]
            self.certs.set_profiles([
                {"name": sso_watch._pick(r, "name"),
                 "label": sso_watch._pick(r, "displayName") or sso_watch._pick(r, "name"),
                 "entity": sso_watch._pick(r, "idpConfig.entityId")}
                for r in rows if sso_watch._pick(r, "name")])
            for r in rows:
                name = r.get("name") or ""
                if name:
                    self.profile.addItem(f"{r.get('displayName', '')}  ({name})", name)
        _load(self, self.assign_t, ["print", "inboundssoassignments"], self.status,
              lambda _c: _load(self, self.prof_t, ["print", "inboundssoprofiles"],
                               self.status, got_profiles))

    def _target(self):
        g, ou = self.group_e.text().strip(), self.ou.path()
        if not g and not ou:
            self.info("Pick an org unit (or type a group).")
            return None
        return ou, g

    def set_it(self):
        x = _x()
        t = self._target()
        if not t:
            return
        ou, g = t
        mode = self.mode.currentData()
        prof = self.profile.currentData() or self.profile.currentText().strip()
        try:
            x.sso_mode_args(mode, prof)
        except ValueError as e:
            self.info(str(e))
            return
        what = g or ou
        if not self.confirm(f"Set sign-in for {what} to:\n{self.mode.currentText()}"
                            + (f"\n{prof}" if mode in ("saml_sso", "oidc_sso") else "") +
                            "\n\nPeople there sign in this way from their next sign-in."):
            return
        never = self.never.isChecked()

        def work():
            code, out = _text()(x.sso_info(ou, g))
            name = x.assignment_name(out) if code == 0 else ""
            return (x.sso_update(name, mode, prof, never) if name else
                    x.sso_create(ou, mode, prof, g, self.rank.value(), never))

        def go(args):
            run_or_request(self, _steps(self), [(f"Sign-in for {what}", args)],
                           "Change single sign-on", "Single sign-on", lambda _s: self.load())
        _work(self, work, go, self.status, "Checking the current assignment…")

    def remove(self):
        x = _x()
        t = self._target()
        if t and self.confirm(f"Remove the assignment for {t[1] or t[0]}? It then follows "
                              "the org unit above it (or the domain setting)."):
            run_or_request(self, _steps(self), [(f"Remove SSO assignment for {t[1] or t[0]}",
                                                 x.sso_delete(t[0], t[1]))],
                           "Remove single sign-on assignment", "Single sign-on",
                           lambda _s: self.load())


# ===================================================== Windows, Mac, phones ===
class EndpointsPage(Page):
    title = "Windows, Mac & phones"
    subtitle = ("Staff laptops, Macs, iPads and phones in Google endpoint management: list "
                "them with their users, approve or block a person's device, wipe a lost one, "
                "and find devices that haven't checked in.")

    def build(self):
        x = _x()
        self.kind = QComboBox()
        for k, lab in x.DEVICE_TYPES.items():
            self.kind.addItem(lab, k)
        self.owner = QComboBox()
        for k, lab in (("all", "Company and personal"), ("company", "Company-owned"),
                       ("personal", "Personal (BYOD)")):
            self.owner.addItem(lab, k)
        self.query = QLineEdit(placeholderText="search, e.g. serial:C02XL or user:jdoe")
        self.stale = QSpinBox()
        self.stale.setRange(0, 720)
        self.stale.setValue(0)
        self.stale.setSpecialValueText("all devices")
        self.stale.setPrefix("not seen ")
        self.stale.setSuffix(" days")
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(self.kind, self.owner, self.query, self.stale,
                                     button("List devices", "primary", self.load),
                                     stretch=False))
        self.body.addWidget(self.status)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.body.addLayout(self.row(
            button("Approve person on device", slot=lambda: self.act("approve", True)),
            button("Block person on device", "danger", lambda: self.act("block", True)),
            button("Wipe account from device", "danger", lambda: self.act("wipe", True)),
            button("Wipe whole device", "danger", lambda: self.act("wipe", False)),
            button("Cancel wipe", slot=lambda: self.act("cancelwipe", False)),
            button("Delete device", "danger", lambda: self.act("delete", False))))

    def load(self):
        x = _x()
        args = x.devices_args(self.kind.currentData(), self.owner.currentData(),
                              self.query.text())
        days = self.stale.value()

        def work():
            code, rows, err = _csv()(args)
            if code != 0:
                raise RuntimeError("Couldn't list devices: " + (err or "")[-300:])
            return x.stale_devices(rows, days) if days else rows

        def done(rows):
            cols = []
            for r in rows:
                for k in r:
                    if k not in cols:
                        cols.append(k)
            fill(self.table, rows, cols)
            self.status.setText(f"{len(rows)} device row(s)" + (f" not seen for {days}+ days"
                                                                 if days else "") + ".")
        _work(self, work, done, self.status, "Reading devices…")

    def act(self, action, user_level):
        x = _x()
        rows = self.table.selected_dicts()
        if not _need_rows(self, rows):
            return
        steps = []
        for r in rows:
            low = {k.lower(): v for k, v in r.items()}
            name = (low.get("users.0.name") or low.get("deviceusers.0.name") or
                    low.get("user.name") or "") if user_level else ""
            if user_level and not name:
                name = next((v for k, v in low.items() if "deviceusers/" in str(v)), "")
            if not user_level:
                name = low.get("name", "")
            try:
                steps.append((f"{action} {low.get('serialnumber') or name}",
                              x.device_action(action, name)))
            except ValueError as e:
                self.info(str(e))
                return
        run_or_request(self, _steps(self), steps, f"{action.title()} {len(steps)} device(s)",
                       "Windows, Mac & phones", lambda _s: self.load())


# =================================================== shared drives by school ===
class SharedDrivesPage(Page):
    title = "Shared drives by school"
    subtitle = ("Shared drives belong to org units too. List each school's drives, find "
                "drives with no manager, members outside the district or anyone-with-the-link "
                "sharing, add a manager, and move drives between org units.")

    def build(self):
        self.ou = OUField(self.directory, "org unit (blank = all for the checks)")
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(
            self.ou, button("Drives in this org unit", "primary", self.in_ou),
            button("No manager", slot=self.no_manager),
            button("Outside members", slot=self.outside),
            button("Anyone with the link", slot=self.anyone), stretch=False))
        self.body.addWidget(self.status)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.to_ou = OUField(self.directory, "move selected drives to…")
        self.mgr = PersonField(self.directory, "add this person as manager…")
        self.body.addLayout(self.row(self.to_ou, button("Move selected", slot=self.move),
                                     self.mgr, button("Add manager to selected",
                                                      slot=self.add_mgr)))

    def in_ou(self):
        if not self.ou.path():
            self.info("Pick the org unit.")
            return
        _load(self, self.table, _x().ou_drives_args(self.ou.path()), self.status)

    def no_manager(self):
        _load(self, self.table, _x().no_manager_args(self.ou.path()), self.status)

    def outside(self):
        dom = self.directory.domain or ""
        if not dom:
            self.info("Connect to Google first (GAMbit needs your domain).")
            return
        _load(self, self.table, _x().outside_args(dom, self.ou.path()), self.status)

    def anyone(self):
        _load(self, self.table, _x().anyone_link_args(self.ou.path()), self.status)

    def _ids(self):
        return sorted(set(_col(self.table, "id", "driveId", "Drive ID", "shareddriveid")))

    def move(self):
        a, ids = _admin(self), self._ids()
        if "@" not in a or not ids or not self.to_ou.path():
            if not ids:
                self.info("Select drives (with an id column) and pick the org unit.")
            return
        run_or_request(self, _steps(self), [(f"Move drive {i} to {self.to_ou.path()}",
                                            _x().move_drive_args(a, i, self.to_ou.path()))
                                           for i in ids],
                       "Move shared drives", "Shared drives by school")

    def add_mgr(self):
        a, ids, who = _admin(self), self._ids(), self.mgr.email()
        if "@" not in a:
            return
        if not ids or "@" not in who:
            self.info("Select drives and choose the person.")
            return
        run_or_request(self, _steps(self), [(f"{who} manages drive {i}",
                                            _x().add_manager_args(a, i, who)) for i in ids],
                       "Add a shared drive manager", "Shared drives by school")


# =============================================================== Chat posts ===
class ChatPostsPage(Page):
    title = "Chat posts"
    subtitle = ("Post an announcement into staff Google Chat spaces (“Chromebook carts are "
                "due back Friday”), or read a space's messages for an investigation. Posts "
                "go out as the person you choose.")

    def build(self):
        from ... import google_io
        self.who = PersonField(self.directory, "post / read as (blank = GAMbit's admin)")
        self.who.setText(google_io.admin_email())
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(self.who, button("Load their spaces", "primary",
                                                      self.spaces), stretch=False))
        self.spaces_t = ResultsTable()
        self.spaces_t.setMaximumHeight(220)
        self.body.addWidget(self.spaces_t)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Message to post in the selected space(s)…")
        self.text.setMaximumHeight(110)
        self.body.addWidget(self.text)
        self.start, self.end = _day(-7), _day(0)
        self.body.addLayout(self.row(button("Post to selected spaces", "primary", self.post),
                                     QLabel("Read messages from"), self.start, QLabel("to"),
                                     self.end, button("Read selected space", slot=self.read),
                                     stretch=False))
        self.body.addWidget(self.status)
        self.msgs = ResultsTable()
        self.body.addWidget(self.msgs, 1)

    def _who(self):
        w = self.who.email() or self.who.text().strip()
        if "@" not in w:
            self.info("Choose who to post or read as.")
        return w

    def spaces(self):
        w = self._who()
        if "@" in w:
            _load(self, self.spaces_t, _x().spaces_args(w), self.status)

    def _sel(self):
        return _col(self.spaces_t, "name")

    def post(self):
        w, sp, text = self._who(), self._sel(), self.text.toPlainText().strip()
        if "@" not in w:
            return
        if not sp or not text:
            self.info("Select space(s) and type the message.")
            return
        try:
            steps = [(f"Post in {s}", _x().post_args(w, s, text)) for s in sp]
        except ValueError as e:
            self.info(str(e))
            return
        run_or_request(self, _steps(self), steps, f"Post to {len(sp)} Chat space(s)",
                       "Chat posts")

    def read(self):
        w, sp = self._who(), self._sel()
        if "@" not in w:
            return
        if len(sp) != 1:
            self.info("Select one space.")
            return
        s, e = self.start.date().toPython(), self.end.date().toPython()
        _load(self, self.msgs, _x().messages_args(w, sp[0], s.isoformat(),
                                                  (e + datetime.timedelta(days=1)).isoformat()),
              self.status)


# ===================================================== staff calendar status ===
class CalendarStatusPage(Page):
    title = "Staff calendar status"
    subtitle = ("Set out-of-office, focus time or working location for many staff at once – "
                "a whole building on a PD day, a department at a conference – and see or "
                "remove what's set.")

    def build(self):
        x = _x()
        self.target = TargetPicker(self.directory, allow_everyone=False)
        self.body.addWidget(self.target)
        box, form = self.group("What to set")
        self.kind = QComboBox()
        for k, lab in x.STATUS.items():
            self.kind.addItem(lab, k)
        self.kind.currentIndexChanged.connect(self._kind)
        self.d1, self.d2 = _day(1), _day(1)
        self.timed = QCheckBox("Only part of the day")
        self.t1, self.t2 = QTimeEdit(QTime(8, 0)), QTimeEdit(QTime(15, 0))
        for t in (self.t1, self.t2):
            t.setDisplayFormat("h:mm AP")
        self.summary = QLineEdit(placeholderText="title, e.g. PD day")
        self.message = QLineEdit(placeholderText="decline message for new invitations")
        self.decline = QComboBox()
        for k, lab in (("new", "Decline new invitations"), ("all", "Decline all"),
                       ("none", "Don't decline")):
            self.decline.addItem(lab, k)
        self.where = QComboBox()
        for k, lab in (("home", "Home"), ("office", "Office"), ("custom", "Somewhere else")):
            self.where.addItem(lab, k)
        self.where_text = QLineEdit(placeholderText="building / place")
        form.addRow("Status", self.kind)
        form.addRow("Days", self.row(self.d1, QLabel("to"), self.d2, self.timed, self.t1,
                                     QLabel("–"), self.t2, stretch=False))
        form.addRow("Title", self.summary)
        form.addRow("Invitations", self.row(self.decline, self.message, stretch=False))
        form.addRow("Where", self.row(self.where, self.where_text, stretch=False))
        form.addRow("", self.row(button("Set it", "primary", self.set_it),
                                 button("Show what's set", slot=self.show),
                                 button("Remove for these days", "danger", self.remove)))
        self.body.addWidget(box)
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addWidget(self.status)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self._kind()

    def _kind(self, *_):
        k = self.kind.currentData()
        for w in (self.decline, self.message):
            w.setEnabled(k != "workinglocation")
        for w in (self.where, self.where_text):
            w.setEnabled(k == "workinglocation")

    def _days(self):
        return self.d1.date().toPython().isoformat(), self.d2.date().toPython().isoformat()

    def set_it(self):
        x = _x()
        ents = self.target.entities()
        if not ents:
            self.info("Choose who it's for.")
            return
        d1, d2 = self._days()
        t1 = self.t1.time().toString("HH:mm") if self.timed.isChecked() else ""
        t2 = self.t2.time().toString("HH:mm") if self.timed.isChecked() else ""
        steps = [(f"{self.kind.currentText()} for {' '.join(e)}",
                  x.status_create(e, self.kind.currentData(), d1, d2, t1, t2,
                                  self.message.text().strip(), self.summary.text().strip(),
                                  self.decline.currentData(), self.where.currentData(),
                                  self.where_text.text().strip())) for e in ents]
        run_or_request(self, _steps(self), steps,
                       f"{self.kind.currentText()} for {self.target.describe()}",
                       "Staff calendar status")

    def show(self):
        ents = self.target.entities()
        if not ents:
            self.info("Choose who to look at.")
            return
        d1, d2 = self._days()
        _load(self, self.table, _x().status_print(ents[0], self.kind.currentData(), d1, d2),
              self.status)

    def remove(self):
        x = _x()
        ents = self.target.entities()
        if not ents:
            self.info("Choose who it's for.")
            return
        d1, d2 = self._days()
        run_or_request(self, _steps(self), [(f"Remove {self.kind.currentText()} for "
                                             f"{' '.join(e)}",
                                             x.status_delete(e, self.kind.currentData(), d1,
                                                             d2)) for e in ents],
                       f"Remove {self.kind.currentText()} {d1} – {d2}", "Staff calendar status")


# ================================================================ extras ===
class DomainAliasTab(ToolTab):
    intro = ("Domain aliases give everyone a second address at another domain (for "
             "example @hancock.k12.ms.us as well as @hancockschools.net).")

    def build(self):
        self.table = ResultsTable()
        self.alias = QLineEdit(placeholderText="alias domain, e.g. hancock.k12.ms.us")
        self.lay.addLayout(self.row(button("List domain aliases", "primary", lambda: _load(
            self.page, self.table, ["print", "domainaliases"], self.status)),
            self.alias, button("Add alias", slot=self.add),
            button("Remove selected", "danger", self.remove), stretch=False))
        self.lay.addWidget(self.status)
        self.lay.addWidget(self.table, 1)
        self.sl = self.steps_list()
        self.lay.addWidget(self.sl)

    def add(self):
        a, dom = self.alias.text().strip(), self.directory.domain
        if not a or not dom:
            self.info("Type the alias domain (and connect to Google first).")
            return
        run_or_request(self.page, self.sl, [(f"Add domain alias {a}",
                                             _x().domain_alias_create(a, dom))],
                       "Add a domain alias", "Domain aliases")

    def remove(self):
        names = _col(self.table, "domainAliasName")
        if names and self.confirm("Remove " + ", ".join(names) + "? Addresses at those "
                                  "domains stop working."):
            run_or_request(self.page, self.sl, [(f"Remove {n}", ["delete", "domainalias", n])
                                                for n in names],
                           "Remove domain aliases", "Domain aliases")


class ContactDelegatesTab(ToolTab):
    intro = ("Let someone manage another person's contacts (a secretary for a principal). "
             "Useful when offboarding too – see who can still manage someone's contacts.")

    def build(self):
        self.user = PersonField(self.directory, "Whose contacts")
        self.delegate = PersonField(self.directory, "Who can manage them")
        self.table = ResultsTable()
        self.lay.addLayout(self.row(self.user, button("List delegates", "primary", self.list_),
                                    stretch=False))
        self.lay.addLayout(self.row(self.delegate, button("Add", slot=lambda: self.change(True)),
                                    button("Remove", "danger", lambda: self.change(False)),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.lay.addWidget(self.table, 1)
        self.sl = self.steps_list()
        self.lay.addWidget(self.sl)

    def list_(self):
        u = self.user.email()
        if "@" in u:
            _load(self.page, self.table, ["user", u, "print", "contactdelegates", "shownames"],
                  self.status)

    def change(self, add):
        u, d = self.user.email(), self.delegate.email()
        if "@" not in u or "@" not in d:
            self.info("Choose both people.")
            return
        run_or_request(self.page, self.sl, [(f"{'Add' if add else 'Remove'} {d} for {u}",
                                             _x().contact_delegate(u, d, add))],
                       "Contact delegates", "Contact delegates", lambda _s: self.list_())


class TasksTab(ToolTab):
    intro = ("A person's Google Tasks lists and tasks – for records requests or before an "
             "account is deleted. Export them with Export CSV.")

    def build(self):
        self.user = PersonField(self.directory, "Person")
        self.table = ResultsTable()
        self.lay.addLayout(self.row(self.user, button("Task lists", slot=lambda: self.go(False)),
                                    button("All tasks", "primary", lambda: self.go(True)),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.lay.addWidget(self.table, 1)

    def go(self, tasks):
        u = self.user.email()
        if "@" in u:
            _load(self.page, self.table, (_x().tasks_args(u) if tasks else
                                          _x().tasklists_args(u)), self.status)


class BrowserProfilesTab(ToolTab):
    intro = ("Chrome browser profiles managed by your district (staff signing in to Chrome on "
             "Windows and Macs): browser versions, extensions, last activity. Remove profiles "
             "nobody has used in months.")

    def build(self):
        self.stale = QSpinBox()
        self.stale.setRange(0, 720)
        self.stale.setSpecialValueText("all profiles")
        self.stale.setPrefix("inactive ")
        self.stale.setSuffix(" days")
        self.table = ResultsTable()
        self.lay.addLayout(self.row(self.stale, button("List profiles", "primary", lambda: _load(
            self.page, self.table, _x().profiles_args(self.stale.value()), self.status)),
            button("Delete selected", "danger", self.delete), stretch=False))
        self.lay.addWidget(self.status)
        self.lay.addWidget(self.table, 1)
        self.sl = self.steps_list()
        self.lay.addWidget(self.sl)

    def delete(self):
        names = _col(self.table, "name")
        if not names:
            self.info("Select profiles first.")
            return
        run_or_request(self.page, self.sl, [(f"Delete profile {n}", ["delete", "chromeprofile",
                                                                     n]) for n in names],
                       f"Delete {len(names)} Chrome profile(s)", "Chrome browser profiles")


class BrowserTokensTab(ToolTab):
    intro = ("Enrollment tokens enroll Chrome browsers (not Chromebooks) into an org unit – "
             "for lab PCs or staff laptops. Create one, list them, revoke old ones.")

    def build(self):
        self.ou = OUField(self.directory, "/Staff/Laptops")
        self.days = QSpinBox()
        self.days.setRange(0, 3650)
        self.days.setSpecialValueText("never expires")
        self.days.setPrefix("expires in ")
        self.days.setSuffix(" days")
        self.table = ResultsTable()
        self.lay.addLayout(self.row(self.ou, self.days, button("Create token", "primary",
                                                               self.create),
                                    stretch=False))
        self.lay.addLayout(self.row(button("List tokens", slot=lambda: _load(
            self.page, self.table, ["print", "browsertokens"], self.status)),
            button("Revoke selected", "danger", self.revoke)))
        self.lay.addWidget(self.status)
        self.lay.addWidget(self.table, 1)
        self.sl = self.steps_list()
        self.lay.addWidget(self.sl)

    def create(self):
        run_or_request(self.page, self.sl, [(f"New browser enrollment token for "
                                             f"{self.ou.path() or 'the top org unit'}",
                                             _x().token_create(self.ou.path(),
                                                               self.days.value()))],
                       "Create a browser enrollment token", "Browser tokens")

    def revoke(self):
        ids = _col(self.table, "tokenPermanentId")
        if ids and self.confirm(f"Revoke {len(ids)} token(s)? Browsers already enrolled stay "
                                "enrolled."):
            run_or_request(self.page, self.sl, [(f"Revoke {i}", ["revoke", "browsertoken", i])
                                                for i in ids],
                           "Revoke browser tokens", "Browser tokens")


class ExtrasPage(Page):
    title = "Domain & extras"
    subtitle = ("Email security for your domains (SPF, DKIM, DMARC), domain aliases, contact "
                "delegates, Google Tasks, Chrome browser profiles and browser enrollment "
                "tokens.")

    def build(self):
        tabs = QTabWidget()
        from .maildns_tab import EmailSecurityTab
        tabs.addTab(EmailSecurityTab(self), "Email security")
        tabs.addTab(DomainAliasTab(self), "Domain aliases")
        tabs.addTab(ContactDelegatesTab(self), "Contact delegates")
        tabs.addTab(TasksTab(self), "Google Tasks")
        tabs.addTab(BrowserProfilesTab(self), "Chrome browser profiles")
        tabs.addTab(BrowserTokensTab(self), "Browser enrollment tokens")
        self.body.addWidget(tabs, 1)


__all__ = ["SSOPage", "EndpointsPage", "SharedDrivesPage", "ChatPostsPage",
           "CalendarStatusPage", "ExtrasPage"]
