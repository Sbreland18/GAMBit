"""Round 15 tabs and dialogs on existing pages: student flags (Student lookup), old Chrome
profile clean-up (Staff devices), room features and working locations (More services),
shared drive organizers (Google Drive), mailbox sizes (Storage forecast), Drive label
permissions (Email/Drive labels), asset register (Chromebook fleet), next-year forecast
(Budget planner) and group clean-up (Groups)."""

from __future__ import annotations

import datetime
import os

from PySide6.QtCore import QDate, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFileDialog, QLabel, QLineEdit,
    QPlainTextEdit, QSpinBox, QTabWidget, QVBoxLayout,
)

from ...settings import settings
from ...tools import gam_extras3 as g3
from ..pickers import OUField, PersonField
from ..steps import StepList
from ..tools_base import ToolTab
from ..widgets import ResultsTable, Worker, button
from .round11_pages import run_or_request
from .round13_tabs import _csv, fill


def _spin(lo, hi, val, suffix=""):
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(int(val))
    s.setSuffix(suffix)
    return s


def _gone(page) -> set[str]:
    from ...oupath import under
    from ...tools.group_hygiene import options
    former = (options().get("former_root") or "").rstrip("/").lower()
    return {u["email"].lower() for u in page.directory.users or []
            if u.get("suspended") or (former and under(u.get("ou") or "", former))}


class _Dialog(QDialog):
    def __init__(self, page, title, tip="", size=(980, 620)):
        super().__init__(page)
        self.page = page
        self.setWindowTitle(title)
        self.resize(*size)
        self.v = QVBoxLayout(self)
        if tip:
            t = QLabel(tip, wordWrap=True)
            self.v.addWidget(t)
        self.status = QLabel("", objectName="Muted", wordWrap=True)

    def steps(self) -> StepList:
        if not hasattr(self, "_sl"):
            self._sl = StepList(self.page)
            self._sl.setMaximumHeight(130)
            self.v.addWidget(self._sl)
        return self._sl


# ============================================================== student flags ===
class StudentFlagsDialog(_Dialog):
    def __init__(self, page, email: str):
        super().__init__(page, f"Flags – {email}",
                         "Everything GAMbit knows about this student on one card: sign-ins, "
                         "missing work, Chromebooks, shared-password signs, repairs, guardians, "
                         "apps, Meet time, AI use and open unusual-activity findings.",
                         (860, 520))
        self.table = ResultsTable()
        self.v.addWidget(self.status)
        self.v.addWidget(self.table, 1)
        self.status.setText("Checking (about a minute)…")
        user = next((u for u in page.directory.users or []
                     if u["email"].lower() == email.lower()), None)
        from ... import student_flags as sf

        def done(rows):
            fill(self.table, rows, ["Level", "Signal", "Detail"])
            hi = sum(1 for r in rows if r["Level"] == "high")
            self.status.setText(f"{hi} serious flag(s)" if hi else "Nothing serious.")
        Worker(sf.gather, email, _csv(), user, on_done=done,
               on_error=lambda e: self.status.setText(str(e)))


# ======================================================== old Chrome profiles ===
def old_profiles_button(page):
    return button("Clean up old profiles…", slot=lambda: OldProfilesDialog(page).exec())


class OldProfilesDialog(_Dialog):
    def __init__(self, page):
        super().__init__(page, "Old Chrome profiles",
                         "Managed Chrome profiles that haven't been used in a while, or belong "
                         "to people who left. Deleting one removes it from the Admin console "
                         "list and stops policies reaching it – nothing on the computer is "
                         "erased.")
        self.days = _spin(14, 1000, settings.get("oldprofiles/days", 90) or 90,
                          " days unused")
        self.v.addLayout(page.row(QLabel("Older than"), self.days,
                                  button("Find", "primary", self.load), self.status))
        self.table = ResultsTable()
        self.table.hidden_columns = {"name"}
        self.v.addWidget(self.table, 1)
        self.v.addLayout(page.row(button("Delete selected profiles", "danger", self.delete)))
        self.rows = []

    def load(self):
        settings.set("oldprofiles/days", self.days.value())
        self.status.setText("Reading Chrome profiles…")

        def done(res):
            c, rows, e = res
            if c != 0:
                self.status.setText((e or "")[-200:])
                return
            self.rows = g3.stale_profiles(rows, self.days.value(), self.page.directory.users)
            fill(self.table, self.rows, ["Person", "Computer", "OS", "Last used", "Why",
                                         "name"])
            self.status.setText(f"{len(self.rows):,} of {len(rows):,} profile(s) to clean up")
        Worker(lambda: _csv()(g3.PROFILES_ARGS), on_done=done,
               on_error=lambda e: self.status.setText(str(e)))

    def delete(self):
        names = self.table.selected_values("name")
        if not names:
            self.page.info("Select the profiles first.")
            return
        run_or_request(self.page, self.steps(), [(f"Delete Chrome profile {n.split('/')[-1]}",
                                                  g3.delete_profile_args(n)) for n in names],
                       "Delete old Chrome profiles", "Chrome profile clean-up")


# ============================================================== room features ===
class RoomFeaturesTab(ToolTab):
    intro = ("Room features (projector, doc camera, wheelchair access…) let staff search for "
             "the right room when booking. Create the list once, then add features to rooms.")

    def build(self):
        self.lay.addLayout(self.row(button("Load rooms and features", "primary", self.load),
                                    self.status))
        self.feat = QComboBox()
        self.feat.setEditable(True)
        self.feat.setMinimumWidth(220)
        self.new = QLineEdit(placeholderText="new feature, e.g. Projector")
        self.lay.addLayout(self.row(QLabel("Feature"), self.feat,
                                    button("Add to selected rooms", slot=lambda: self.change(True)),
                                    button("Remove from selected rooms",
                                           slot=lambda: self.change(False))))
        self.lay.addLayout(self.row(self.new, button("Create feature", slot=self.create),
                                    button("Rename chosen to this", slot=self.rename),
                                    button("Delete chosen feature", "danger", self.delete)))
        self.table = ResultsTable()
        self.table.setMinimumHeight(280)
        self.table.hidden_columns = {"id"}
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def load(self):
        def got(res):
            feats, rooms = res
            self.feat.clear()
            for f in g3.features(feats):
                self.feat.addItem(f)
            if self.feat.count():
                self.feat.setCurrentIndex(0)
            r = g3.resources(rooms)
            fill(self.table, r, ["Room", "Building", "Capacity", "Features", "id"])
            self.status.setText(f"{len(r)} room(s) · {self.feat.count()} feature(s)")
        self.read_many([g3.FEATURES_ARGS, g3.RESOURCES_ARGS], got)

    def _run(self, steps, title):
        run_or_request(self.page, self.steps, steps, title, "Room features",
                       done=lambda _s: self.load())

    def change(self, add: bool):
        f = self.feat.currentText().strip()
        ids = self.table.selected_values("id")
        if not f or not ids:
            self.info("Choose a feature and select rooms.")
            return
        fn = g3.resource_features_args if add else g3.resource_remove_features_args
        self._run([(f"{'Add' if add else 'Remove'} {f} – {i}", fn(i, [f])) for i in ids],
                  "Room features")

    def create(self):
        n = self.new.text().strip()
        if n:
            self._run([(f"Create feature {n}", g3.feature_create_args(n))], "Create feature")

    def rename(self):
        old, n = self.feat.currentText().strip(), self.new.text().strip()
        if old and n:
            self._run([(f"Rename {old} to {n}", g3.feature_rename_args(old, n))],
                      "Rename feature")

    def delete(self):
        f = self.feat.currentText().strip()
        if f and self.confirm(f"Delete the feature “{f}” from every room?"):
            self._run([(f"Delete feature {f}", g3.feature_delete_args(f))], "Delete feature")


# ========================================================= working locations ===
class WorkingLocationTab(ToolTab):
    intro = ("For itinerant staff (speech, OT, music, tech): set which building they're in "
             "each weekday so it shows on their Google Calendar and colleagues can find them.")

    def build(self):
        self.who = PersonField(self.directory, "Staff member")
        self.start = QDateEdit(QDate.currentDate())
        self.start.setCalendarPopup(True)
        self.weeks = _spin(1, 52, 18, " weeks")
        box, form = self.page.group("Weekly schedule")
        form.addRow("Person", self.who)
        self.days = {}
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):
            cb = QComboBox()
            cb.setEditable(True)
            cb.setMinimumWidth(240)
            self.days[d] = cb
            form.addRow(d, cb)
        form.addRow("Starting", self.row(self.start, QLabel("for"), self.weeks))
        form.addRow("", self.row(button("Load buildings", slot=self.load),
                                 button("Set working locations", "primary", self.apply),
                                 self.status))
        self.lay.addWidget(box)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.lay.addStretch(1)
        self.buildings: dict[str, str] = {}

    def load(self):
        def got(rows):
            if rows is None:
                return
            self.buildings = {}
            for r in rows:
                low = {(k or "").lower(): v for k, v in r.items()}
                if low.get("buildingname"):
                    self.buildings[low["buildingname"]] = low.get("buildingid", "")
            for cb in self.days.values():
                cur = cb.currentText()
                cb.clear()
                cb.addItem("")
                cb.addItems(sorted(self.buildings))
                cb.setEditText(cur)
            self.status.setText(f"{len(self.buildings)} building(s)")
        self.read(["print", "buildings", "fields", "buildingid,buildingname"], got)

    def apply(self):
        u = self.who.email()
        plan = {d: cb.currentText() for d, cb in self.days.items()}
        cmds = g3.schedule_commands(u, plan, self.start.date().toPython(), self.weeks.value(),
                                    self.buildings)
        if "@" not in u or not cmds:
            self.info("Choose the person and at least one day's building.")
            return
        run_or_request(self.page, self.steps,
                       [(f"{a[5]} every {datetime.date.fromisoformat(a[-2]):%A} from {a[-2]}",
                         a) for a in cmds], f"Working locations for {u}", "Itinerant schedule")


# ===================================================== shared drive organizers ===
class OrganizersDialog(_Dialog):
    def __init__(self, page):
        super().__init__(page, "Shared drive managers",
                         "Every shared drive with its managers. Drives at the top have no "
                         "manager left (everyone suspended or gone) – give each one a new "
                         "manager so files can still be looked after.")
        self.ou = OUField(page.directory, "/")
        self.v.addLayout(page.row(QLabel("Drives in"), self.ou,
                                  button("Load", "primary", self.load), self.status))
        self.table = ResultsTable()
        self.table.hidden_columns = {"id"}
        self.v.addWidget(self.table, 1)
        self.who = PersonField(page.directory, "New manager")
        self.v.addLayout(page.row(self.who, button("Add as manager of selected drives",
                                                   slot=self.add)))

    def load(self):
        self.status.setText("Reading shared drives (a few minutes for many drives)…")
        gone = _gone(self.page)

        def done(res):
            c, rows, e = res
            if c != 0:
                self.status.setText((e or "")[-200:])
                return
            self.rows = g3.organizers(rows, gone)
            fill(self.table, self.rows, ["Shared drive", "Org unit", "Active managers",
                                         "Managers", "Created", "id"])
            n = sum(1 for r in self.rows if not r["Active managers"])
            self.status.setText(f"{len(self.rows):,} drive(s) · {n} with no active manager")
        Worker(lambda: _csv()(g3.organizers_args(self.ou.path())), on_done=done,
               on_error=lambda e: self.status.setText(str(e)))

    def add(self):
        from ... import google_io
        ids, who = self.table.selected_values("id"), self.who.email()
        admin = google_io.admin_email()
        if not ids or "@" not in who or "@" not in admin:
            self.page.info("Select drives and choose the new manager (and set the GAMbit "
                           "Google account in Settings).")
            return
        run_or_request(self.page, self.steps(),
                       [(f"Make {who} manager of {i}", ["user", admin, "add", "drivefileacl", i,
                                                        "user", who, "role", "organizer",
                                                        "asadmin"]) for i in ids],
                       "Add shared drive managers", "Shared drives with no manager")


# ============================================================== mailbox sizes ===
class MailboxStatsDialog(_Dialog):
    def __init__(self, page):
        super().__init__(page, "Mailbox sizes",
                         "Message and conversation counts per mailbox – handy next to storage "
                         "numbers to find the mailboxes that need an archive or a clean-up "
                         "rule.", (760, 560))
        self.ou = OUField(page.directory, "/Staff")
        self.ou.set_path(settings.get("mailboxstats/ou", "/Staff") or "/Staff")
        self.v.addLayout(page.row(QLabel("People in"), self.ou,
                                  button("Count", "primary", self.load), self.status))
        self.table = ResultsTable()
        self.v.addWidget(self.table, 1)

    def load(self):
        p = self.ou.path() or "/"
        settings.set("mailboxstats/ou", p)
        who = ["all", "users"] if p == "/" else ["ou_and_children", p]
        self.status.setText("Counting (about a second per mailbox)…")

        def done(res):
            c, rows, e = res
            if c != 0:
                self.status.setText((e or "")[-200:])
                return
            st = g3.mailbox_stats(rows)
            fill(self.table, st, ["Person", "Messages", "Threads"])
            self.status.setText(f"{len(st):,} mailbox(es) · "
                                f"{sum(r['Messages'] for r in st):,} messages")
        Worker(lambda: _csv()(who + ["print", "gmailprofile"]), on_done=done,
               on_error=lambda e: self.status.setText(str(e)))


# ===================================================== Drive label permissions ===
class LabelPermissionsDialog(_Dialog):
    def __init__(self, page, label: dict):
        super().__init__(page, f"Who can use “{label.get('title', '')}”",
                         "People and groups allowed to apply or change this Drive label. "
                         "Usually: a staff group as Applier, the records office as Editor.",
                         (820, 520))
        self.label = label
        self.v.addWidget(self.status)
        self.table = ResultsTable()
        self.v.addWidget(self.table, 1)
        self.who = QLineEdit(placeholderText="group or person email")
        self.kind = QComboBox()
        self.kind.addItems(["group", "user"])
        self.role = QComboBox()
        for lab, val in (("Applier – can apply it", "applier"), ("Reader – can see it",
                                                                 "reader"),
                         ("Editor – can change the label", "editor"),
                         ("Organizer – can manage it", "organizer")):
            self.role.addItem(lab, val)
        self.v.addLayout(page.row(self.kind, self.who, self.role,
                                  button("Add", "primary", self.add),
                                  button("Remove selected", "danger", self.remove)))
        self.rows = []
        self.load()

    def load(self):
        self.status.setText("Reading…")

        def done(res):
            c, rows, e = res
            if c != 0:
                self.status.setText((e or "")[-200:])
                return
            self.rows = rows
            h = list(rows[0].keys()) if rows else ["(nobody yet)"]
            self.table.set_rows(h, [[r.get(k, "") for k in h] for r in rows])
            self.status.setText(f"{len(rows)} permission(s)")
        Worker(lambda: _csv()(g3.label_perms_args(self.label["id"])), on_done=done,
               on_error=lambda e: self.status.setText(str(e)))

    def add(self):
        w = self.who.text().strip()
        if "@" not in w:
            return
        run_or_request(self.page, self.steps(), [(f"Let {w} use the label",
                                                  g3.label_perm_add_args(
                                                      self.label["id"], w,
                                                      self.role.currentData(),
                                                      self.kind.currentText()))],
                       "Drive label permission", "Drive label access",
                       done=lambda _s: self.load())

    def remove(self):
        steps = []
        for r in self.table.selected_dicts():
            low = {(k or "").lower(): v for k, v in r.items()}
            e = low.get("email", "")
            if e:
                kind = "group" if low.get("group") else "user"
                steps.append((f"Remove {e}", g3.label_perm_remove_args(self.label["id"], e,
                                                                         kind)))
        run_or_request(self.page, self.steps(), steps, "Remove Drive label permission",
                       "Drive label access", done=lambda _s: self.load())


# ============================================================= asset register ===
class AssetRegisterTab(ToolTab):
    intro = ("Compare the finance office's fixed-asset list (a CSV with serial number, asset "
             "tag, purchase date, cost and school) with the Chromebooks Google knows about, "
             "and export one inventory with age, book value and end of updates for audits.")

    def build(self):
        from ... import asset_register as ar
        o = ar.options()
        self.path = QLineEdit(settings.get("assetreg/path", "") or "")
        self.path.setPlaceholderText("finance export (.csv)")
        self.life = _spin(1, 15, o["life_years"], " year life")
        self.lay.addLayout(self.row(self.path, button("Browse…", slot=self.browse),
                                    QLabel("Depreciate over"), self.life,
                                    button("Compare", "primary", self.compare)))
        self.lay.addWidget(self.status)
        self.tabs = QTabWidget()
        self.problems, self.inv = ResultsTable(), ResultsTable()
        self.tabs.addTab(self.problems, "Differences")
        self.tabs.addTab(self.inv, "Inventory")
        self.tabs.setMinimumHeight(340)
        self.lay.addWidget(self.tabs, 1)
        self.lay.addLayout(self.row(button("Copy finance asset tags into Google for selected",
                                           slot=self.fix_tags),
                                    button("Save inventory CSV…", slot=self.export)))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.rec, self.inventory, self.ids = [], [], {}

    def browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Finance asset list", "", "CSV (*.csv)")
        if p:
            self.path.setText(p)

    def compare(self):
        from ... import asset_register as ar
        from ... import fleet
        p = self.path.text().strip()
        if not os.path.isfile(p):
            self.info("Choose the finance CSV first.")
            return
        settings.set("assetreg/path", p)
        ar.save_options({**ar.options(), "life_years": self.life.value()})
        self.status.setText("Reading the finance list and every Chromebook…")

        def work():
            fin, m = ar.read_finance(p)
            if "serial" not in m:
                raise RuntimeError("Couldn't find a serial number column in the CSV.")
            c, rows, e = _csv()(ar.CROS_ARGS)
            if c != 0:
                raise RuntimeError((e or "")[-200:])
            ids = {(fleet._col(r, "serialNumber") or "").upper(): fleet._col(r, "deviceId")
                   for r in rows}
            devs = fleet.devices(rows)
            return fin, m, devs, ids

        def done(res):
            fin, m, devs, self.ids = res
            self.rec = ar.reconcile(fin, devs)
            self.inventory = ar.inventory(fin, devs)
            fill(self.problems, self.rec, ["Problem", "Serial", "Finance tag", "Google tag",
                                           "Finance location", "Google OU", "User"])
            cols = list(self.inventory[0].keys()) if self.inventory else ["Serial"]
            fill(self.inv, self.inventory, cols)
            t = ar.totals(self.inventory)
            self.status.setText(f"Finance list: {len(fin):,} · Google: {len(devs):,} · "
                                f"{len(self.rec):,} difference(s) · cost ${t['cost']:,.0f}, "
                                f"book value ${t['book']:,.0f} · {t['expired']:,} past end of "
                                f"updates · columns used: " +
                                ", ".join(f"{k}={v}" for k, v in m.items()))
        Worker(work, on_done=done, on_error=lambda e: self.status.setText(str(e)))

    def fix_tags(self):
        from ... import asset_register as ar
        sel = set(self.problems.selected_values("Serial"))
        steps = []
        for r in self.rec:
            if r["Serial"] in sel and r["Problem"].startswith("Asset tag"):
                a = ar.tag_fix_args(self.ids, r)
                if a:
                    steps.append((f"{r['Serial']}: asset tag {r['Finance tag']}", a))
        if not steps:
            self.info("Select rows with an asset tag difference.")
            return
        run_or_request(self.page, self.steps, steps, "Fix Chromebook asset tags",
                       "Asset register reconciliation")

    def export(self):
        from ... import fleet
        if not self.inventory:
            self.info("Compare first.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Save inventory", "chromebook-inventory.csv",
                                           "CSV (*.csv)")
        if p:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(fleet.to_csv(self.inventory))
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(p)))


# =================================================================== next year ===
class NextYearTab(ToolTab):
    intro = ("Next school year: every student moves up a grade, each school's top grade "
             "moves to the school it feeds (or graduates), plus a kindergarten estimate – "
             "then the Chromebooks and student licenses you'll need. Grades are read from "
             "student org units (Grade 5, 05, K or Class of 2031).")

    def build(self):
        from ... import next_year as ny
        o = ny.options()
        self.root = OUField(self.directory, "/Students")
        self.root.set_path(o["student_root"])
        self.feeds = QPlainTextEdit(o["feeds"])
        self.feeds.setPlaceholderText("where each school's top grade goes, one per line:\n"
                                      "Lincoln Elementary = Grant Middle")
        self.feeds.setMaximumHeight(90)
        self.kinder = QPlainTextEdit(o["kinder"])
        self.kinder.setPlaceholderText("optional kindergarten estimates:  Lincoln Elementary "
                                       "= 85  (otherwise this year's class size)")
        self.kinder.setMaximumHeight(70)
        self.ratio = QDoubleSpinBox()
        self.ratio.setRange(0.1, 2)
        self.ratio.setSingleStep(0.1)
        self.ratio.setValue(float(o["ratio"]))
        self.ratio.setSuffix(" device(s) per student")
        self.spare = _spin(0, 50, o["spare_pct"], "% spares")
        self.lic = _spin(0, 1000000, o["student_licenses"], " student licenses on hand")
        box, form = self.page.group("Settings")
        form.addRow("Students are under", self.root)
        form.addRow("Feeder schools", self.feeds)
        form.addRow("Kindergarten", self.kinder)
        form.addRow("Chromebooks", self.row(self.ratio, self.spare, self.lic))
        form.addRow("", self.row(button("Forecast", "primary", self.run), self.status))
        self.lay.addWidget(box)
        self.summary = QLabel("", wordWrap=True)
        self.lay.addWidget(self.summary)
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)

    def _opts(self):
        from ... import next_year as ny
        o = {**ny.options(), "student_root": self.root.path() or "/Students",
             "feeds": self.feeds.toPlainText(), "kinder": self.kinder.toPlainText(),
             "ratio": self.ratio.value(), "spare_pct": self.spare.value(),
             "student_licenses": self.lic.value()}
        ny.save_options(o)
        return o

    def run(self):
        from ... import fleet
        from ... import next_year as ny
        from ...tools import budget
        users = self.directory.users
        if not users:
            self.info("Load users first (Users page or Refresh).")
            return
        o = self._opts()
        ye = ny.school_year_end()
        self.status.setText("Reading Chromebooks…")

        def work():
            c, rows, e = _csv()(["print", "cros", "fields", "serialnumber,annotateduser,"
                                 "orgunitpath,status,autoupdateexpiration,model"])
            devs = fleet.devices(rows) if c == 0 else []
            rows_p, info = ny.project(users, o, ye)
            usable = ny.devices_next_year(devs, budget.user_schools(users, o["student_root"]),
                                          o, ye)
            return rows_p, info, usable, c == 0

        def done(res):
            rows_p, info, usable, ok = res
            cost = float(budget.options().get("device_cost", 300) or 300)
            p = ny.plan(rows_p, usable, o, cost)
            fill(self.table, p, ["School", "Grades", "This year", "Next year", "Change",
                                 "Moving on", "Chromebooks needed", "Still supported",
                                 "To buy", "Cost", "Note"])
            lic = ny.licenses(p, o)
            tot = p[-1] if p else {}
            self.summary.setText(
                f"<b>{ye}-{str(ye + 1)[-2:]}:</b> about {lic['students_next_year']:,} students"
                f" · {info['graduating']:,} graduating · buy about {tot.get('To buy', 0):,} "
                f"Chromebooks (${tot.get('Cost', 0):,})" +
                (f" · {lic['licenses_short']:,} more student licenses needed"
                 if lic["licenses_short"] else "") +
                (f" · {info['unknown_grade']:,} student(s) with no grade in their org unit"
                 if info["unknown_grade"] else "") +
                ("" if ok else " · couldn't read Chromebooks"))
            self.status.setText("")
        Worker(work, on_done=done, on_error=lambda e: self.status.setText(str(e)))


# ============================================================== group clean-up ===
class GroupHygieneTab(ToolTab):
    intro = ("Find suspended or former staff still in groups, outside addresses in staff "
             "groups, people who are in a group both directly and through a nested group, "
             "and staff in another school's group.")

    def build(self):
        from ...tools import group_hygiene as gh
        o = gh.options()
        self.former = QLineEdit(o["former_root"])
        self.pattern = QLineEdit(o["staff_pattern"])
        self.pattern.setToolTip("Group addresses containing this are treated as staff groups")
        self.schools = QPlainTextEdit(o["school_groups"])
        self.schools.setPlaceholderText("optional – school groups:  lincoln-staff@district.org "
                                        "= Lincoln Elementary")
        self.schools.setMaximumHeight(70)
        box, form = self.page.group("Settings")
        form.addRow("Leavers' org unit", self.former)
        form.addRow("Staff groups contain", self.pattern)
        form.addRow("School groups", self.schools)
        form.addRow("", self.row(button("Check all groups", "primary", self.check),
                                 self.status))
        self.lay.addWidget(box)
        self.tabs = QTabWidget()
        self.table, self.sum = ResultsTable(), ResultsTable()
        self.tabs.addTab(self.table, "Members to look at")
        self.tabs.addTab(self.sum, "By group")
        self.tabs.setMinimumHeight(320)
        self.lay.addWidget(self.tabs, 1)
        self.lay.addLayout(self.row(button("Remove selected from their groups", "danger",
                                           self.remove)))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.found = []

    def check(self):
        from ...tools import group_hygiene as gh
        o = {**gh.options(), "former_root": self.former.text().strip(),
             "staff_pattern": self.pattern.text().strip(),
             "school_groups": self.schools.toPlainText()}
        gh.save_options(o)
        users = self.directory.users

        def got(rows):
            if rows is None:
                return
            self.found = gh.check(rows, users, o)
            for i, f in enumerate(self.found):
                f["#"] = i
            fill(self.table, self.found, ["Level", "Group", "Member", "Problem", "Role", "#"])
            fill(self.sum, gh.summary(self.found), ["Group", "Issues", "What"])
            self.status.setText(f"{len(self.found):,} membership(s) to look at")
        self.read(gh.MEMBERS_ARGS, got, "Reading every group's members (a few minutes)…")

    def remove(self):
        idx = {int(i) for i in self.table.selected_values("#") if str(i).isdigit()}
        steps = [(f"Remove {f['Member']} from {f['Group']}", f["fix"])
                 for f in self.found if f["#"] in idx]
        run_or_request(self.page, self.steps, steps, "Group clean-up", "Group hygiene check")
