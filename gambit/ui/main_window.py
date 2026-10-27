from __future__ import annotations

import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QTextCharFormat, QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QPlainTextEdit, QScrollArea, QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from .. import gam_setup
from ..directory import Directory
from ..gam_runner import GamRunner
from ..resources import resource_path
from ..settings import settings
from ..version import APP_NAME, __version__
from .session_actions import SessionActions
from .app_actions import AppActions, MoreActions
from .jobs_panel import JobsPanel
from .widgets import button


class _P:
    """A page class imported only when the page is first opened, so GAMbit starts fast."""

    def __init__(self, module: str, name: str):
        self.module, self.__name__ = module, name

    @property
    def cls(self):
        import importlib
        return getattr(importlib.import_module(self.module, __package__), self.__name__)

    def __call__(self, app):
        return self.cls(app)


ClassroomPage = _P(".pages.classroom", "ClassroomPage")
BulkPage = _P(".pages.console", "BulkPage")
ConsolePage = _P(".pages.console", "ConsolePage")
DevicesPage = _P(".pages.devices", "DevicesPage")
DrivePage = _P(".pages.drive", "DrivePage")
EmailPage = _P(".pages.email", "EmailPage")
GroupsPage = _P(".pages.groups", "GroupsPage")
HomePage = _P(".pages.home", "HomePage")
LicensesPage = _P(".pages.licenses", "LicensesPage")
OrgUnitsPage = _P(".pages.orgunits", "OrgUnitsPage")
ReportsPage = _P(".pages.reports", "ReportsPage")
SettingsPage = _P(".pages.settings_page", "SettingsPage")
UsersPage = _P(".pages.users", "UsersPage")
WorkflowsPage = _P(".pages.workflows", "WorkflowsPage")
ActivityPage = _P(".pages.activity_page", "ActivityPage")
ApprovalsPage = _P(".pages.approvals", "ApprovalsPage")
DiagnosticsPage = _P(".pages.diagnostics_page", "DiagnosticsPage")
LiveTestPage = _P(".pages.livetest_page", "LiveTestPage")
SchedulesPage = _P(".pages.schedules_page", "SchedulesPage")
FleetPage = _P(".pages.fleet_page", "FleetPage")
CompliancePage = _P(".pages.compliance_page", "CompliancePage")
InvestigationsPage = _P(".pages.investigations_page", "InvestigationsPage")
StaffDevicesPage = _P(".pages.more_tabs", "StaffDevicesPage")
UsagePage = _P(".pages.more_tabs", "UsagePage")
SettingsWatchPage = _P(".pages.recovery_tabs", "SettingsWatchPage")
AskPage = _P(".pages.ask_page", "AskPage")
BudgetPage = _P(".pages.insight_pages", "BudgetPage")
MismatchPage = _P(".pages.insight_pages", "MismatchPage")
SchoolReportsPage = _P(".pages.insight_pages", "SchoolReportsPage")
TicketQueuePage = _P(".pages.insight_pages", "TicketQueuePage")
AuditReportPage = _P(".pages.round10_pages", "AuditReportPage")
TeacherListsPage = _P(".pages.round10_pages", "TeacherListsPage")
OwnershipPage = _P(".pages.round11_pages", "OwnershipPage")
PolicyRolloutsPage = _P(".pages.round11_pages", "PolicyRolloutsPage")
TimeMachinePage = _P(".pages.round11_pages", "TimeMachinePage")
TwoStepPage = _P(".pages.round11_pages", "TwoStepPage")
BaselinePage = _P(".pages.round12_pages", "BaselinePage")
ChangeCalendarPage = _P(".pages.round12_pages", "ChangeCalendarPage")
RecordsPage = _P(".pages.round12_pages", "RecordsPage")
GuidePage = _P(".pages.guide_page", "GuidePage")
BackToSchoolPage = _P(".pages.round15_pages", "BackToSchoolPage")
MailboxAccessPage = _P(".pages.round15_pages", "MailboxAccessPage")
OutsideChangesPage = _P(".pages.round15_pages", "OutsideChangesPage")
RecoveryCoveragePage = _P(".pages.round15_pages", "RecoveryCoveragePage")
StaffCardPage = _P(".pages.round15_pages", "StaffCardPage")
AIUsePage = _P(".pages.round14_pages", "AIUsePage")
CostPerStudentPage = _P(".pages.round14_pages", "CostPerStudentPage")
DirectoryQualityPage = _P(".pages.round14_pages", "DirectoryQualityPage")
MeetAttendancePage = _P(".pages.round14_pages", "MeetAttendancePage")
AccessReviewPage = _P(".pages.round13_pages", "AccessReviewPage")
AccountTimingPage = _P(".pages.round13_pages", "AccountTimingPage")
GoingQuietPage = _P(".pages.round13_pages", "GoingQuietPage")
StaleContentPage = _P(".pages.round13_pages", "StaleContentPage")
StorageForecastPage = _P(".pages.round13_pages", "StorageForecastPage")
CleanupPage = _P(".pages.automation_tabs", "CleanupPage")
PoliciesPage = _P(".pages.policies_page", "PoliciesPage")
TimelinePage = _P(".pages.timeline_page", "TimelinePage")
LookupPage = _P(".pages.lookup_page", "LookupPage")
BuilderPage = _P(".pages.builder", "BuilderPage")
RosterSyncPage = _P(".pages.rostersync", "RosterSyncPage")
ServicesPage = _P(".pages.services", "ServicesPage")
DeviceHistoryPage = _P(".pages.round25_data", "DeviceHistoryPage")
FieldCheckPage = _P(".pages.round25_data", "FieldCheckPage")
SchoolCleanupPage = _P(".pages.round25_data", "SchoolCleanupPage")
SeniorCheckoutPage = _P(".pages.round25_data", "SeniorCheckoutPage")
SharingPage = _P(".pages.round25_data", "SharingPage")
CalendarStatusPage = _P(".pages.round25_gam", "CalendarStatusPage")
ChatPostsPage = _P(".pages.round25_gam", "ChatPostsPage")
EndpointsPage = _P(".pages.round25_gam", "EndpointsPage")
ExtrasPage = _P(".pages.round25_gam", "ExtrasPage")
SSOPage = _P(".pages.round25_gam", "SSOPage")
SharedDrivesPage = _P(".pages.round25_gam", "SharedDrivesPage")

# Sidebar: strings are section headings, tuples are pages.
NAV = [
    ("Home", HomePage),
    ("Guide", GuidePage),
    ("Workflows", WorkflowsPage), ("Back to school", BackToSchoolPage),
    ("Senior checkout", SeniorCheckoutPage),
    "PEOPLE",
    ("Users", UsersPage),
    ("Student lookup", LookupPage), ("Staff card", StaffCardPage),
    ("Groups", GroupsPage),
    ("Classroom", ClassroomPage),
    ("Roster sync", RosterSyncPage), ("Mismatch report", MismatchPage),
    ("Account timeline", TimelinePage), ("Account time machine", TimeMachinePage),
    ("Directory quality", DirectoryQualityPage), ("Custom field check", FieldCheckPage),
    "DEVICES",
    ("Chromebooks", DevicesPage),
    ("Chromebook fleet", FleetPage), ("Staff devices", StaffDevicesPage),
    ("Chromebook sharing", SharingPage), ("Device history", DeviceHistoryPage),
    ("Windows, Mac & phones", EndpointsPage),
    "SERVICES",
    ("Email", EmailPage),
    ("Google Drive", DrivePage),
    ("Shared drives by school", SharedDrivesPage), ("Chat posts", ChatPostsPage),
    ("Staff calendar status", CalendarStatusPage),
    ("More services", ServicesPage),
    "ADMIN",
    ("Org units", OrgUnitsPage),
    ("Licenses", LicensesPage), ("Budget planner", BudgetPage),
    ("Policies by org unit", PoliciesPage), ("Policy rollouts", PolicyRolloutsPage),
    ("2-Step Verification", TwoStepPage), ("Ownership check", OwnershipPage),
    ("Security baseline", BaselinePage), ("Records requests", RecordsPage),
    ("Access review", AccessReviewPage), ("Cost per student", CostPerStudentPage),
    ("Mailbox access review", MailboxAccessPage), ("Account recovery", RecoveryCoveragePage),
    ("Single sign-on", SSOPage), ("Domain & extras", ExtrasPage),
    "REPORTS",
    ("Reports", ReportsPage), ("School reports", SchoolReportsPage),
    ("Teacher lists", TeacherListsPage), ("Audit report", AuditReportPage),
    ("Students going quiet", GoingQuietPage), ("Account timing", AccountTimingPage),
    ("Storage forecast", StorageForecastPage), ("Meet attendance", MeetAttendancePage),
    ("AI use", AIUsePage), ("Clean-up by school", SchoolCleanupPage),
    ("Security reports", CompliancePage), ("Investigations", InvestigationsPage), ("Usage", UsagePage),
    ("Settings watch", SettingsWatchPage), ("Changes outside GAMbit", OutsideChangesPage),
    ("Activity log", ActivityPage),
    "AUTOMATION",
    ("Approvals", ApprovalsPage), ("Ticket queue", TicketQueuePage),
    ("Run later & freezes", ChangeCalendarPage),
    ("Stale content", StaleContentPage),
    ("Schedules", SchedulesPage), ("Clean-up rules", CleanupPage),
    "TOOLS",
    ("Command Builder", BuilderPage),
    ("Bulk (CSV)", BulkPage),
    ("Command Console", ConsolePage),
    ("Diagnostics", DiagnosticsPage),
    ("Live test", LiveTestPage), ("Ask GAMbit", AskPage),
    ("Settings & Updates", SettingsPage),
]
# Hidden unless Settings → "Show advanced pages" is ticked
ADVANCED = {"More services", "Policies by org unit", "Command Builder", "Bulk (CSV)",
            "Command Console", "Live test"}
PAGES = [n for n in NAV if not isinstance(n, str)]
# old page names → (page, tab) now that they live inside another page
PAGE_ALIASES = {"Background tasks": ("Schedules", "Setup & health"),
                "Scheduled jobs": ("Schedules", "Report & command jobs")}


class LazyPages(dict):
    """name → page. Pages are built the first time they're asked for; values() and items()
    only list pages that exist already (everything else gets the current state when it's
    built)."""

    def __init__(self, win):
        super().__init__()
        self._win = win
        self._classes: dict = {}
        self._building: set = set()

    def register(self, name, cls):
        self._classes[name] = cls

    def built(self, name) -> bool:
        return dict.__contains__(self, name)

    def __contains__(self, name):
        return name in self._classes

    def __getitem__(self, name):
        if not dict.__contains__(self, name):
            if name not in self._classes:
                raise KeyError(name)
            page = self._classes[name](self._win)
            dict.__setitem__(self, name, page)
            self._win._page_built(name, page)
        return dict.__getitem__(self, name)

    def get(self, name, default=None):
        return self[name] if name in self._classes else default

    def keys(self):
        return list(self._classes)

    def __iter__(self):
        return iter(list(self._classes))

    def __len__(self):
        return len(self._classes)


class MainWindow(AppActions, MoreActions, SessionActions, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setWindowIcon(QIcon(resource_path("assets/gambit.ico")))
        self.resize(1180, 800)

        self.runner = GamRunner(self)
        self.runner.started.connect(self._cmd_started)
        self.runner.output.connect(self._cmd_output)
        self.runner.finished.connect(self._cmd_finished)
        self.runner.busy_changed.connect(self._busy)

        # Shared cache of OUs / users / groups + connection state
        self.directory = Directory(self)
        self.directory.busy_changed.connect(
            lambda m: self.statusBar().showMessage(m or "Ready"))

        # sidebar
        side = QWidget()
        self.side = side
        side.setFixedWidth(int(220 * max(1.0, float(settings.get('ui/text_scale', 1.0) or 1.0))))
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)
        sv.addWidget(QLabel(APP_NAME, objectName="Brand"))
        sv.addWidget(QLabel("GAM made friendly", objectName="BrandSub"))
        self.nav = QListWidget(objectName="Nav")
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sv.addWidget(self.nav, 1)
        self.side_footer = QLabel(f"v{__version__}", objectName="BrandSub")
        self.side_footer.setWordWrap(True)
        sv.addWidget(self.side_footer)

        # pages
        self.stack = QStackedWidget()
        self._holders: list = []
        self.pages = LazyPages(self)
        self._row_page: dict[int, int] = {}
        self._row_section: dict[int, str] = {}
        self._header_row: dict[int, str] = {}
        for entry in NAV:
            if isinstance(entry, str):
                continue
            name, cls = entry
            self.pages.register(name, cls)
            # each page sits in a scroll area so no page can force the window to be bigger
            # than the screen (small laptops); pages scroll instead. The page itself is
            # built the first time it's needed (or in the background after start-up).
            holder = QScrollArea()
            holder.setWidgetResizable(True)
            holder.setFrameShape(QScrollArea.NoFrame)
            self._holders.append(holder)
            self.stack.addWidget(holder)
        self._nav_built = False
        self.build_nav(select=False)
        self.nav.itemClicked.connect(self._nav_clicked)
        self.nav.currentRowChanged.connect(self._switch)
        self.nav.setContextMenuPolicy(Qt.CustomContextMenu)
        self.nav.customContextMenuRequested.connect(self._nav_menu)

        # output + jobs panel
        log_box = QWidget()
        lv = QVBoxLayout(log_box)
        lv.setContentsMargins(24, 4, 24, 12)
        head = QHBoxLayout()
        from .widgets import ElideLabel, wrap_log
        self.status = ElideLabel("Ready", objectName="Muted")
        head.addWidget(self.status, 1)
        self.stop_btn = button("Stop", "danger", self.runner.stop)
        self.stop_btn.setProperty("helpdesk_ok", True)
        self.stop_btn.setToolTip("Stop the most recent running command")
        self.stop_btn.setEnabled(False)
        head.addWidget(self.stop_btn)
        head.addWidget(button("Clear", slot=lambda: self.log.clear()))
        self.bottom_tabs = QTabWidget()
        out_w = QWidget()
        ov = QVBoxLayout(out_w)
        ov.setContentsMargins(0, 4, 0, 0)
        ov.addLayout(head)
        self.log = QPlainTextEdit(objectName="Log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(20000)
        wrap_log(self.log)
        ov.addWidget(self.log)
        self.bottom_tabs.addTab(out_w, "Output")
        self.jobs_panel = JobsPanel(self.runner)
        self.bottom_tabs.addTab(self.jobs_panel, "Jobs")
        from .dryrun_panel import DryRunPanel
        self.dry_panel = DryRunPanel(self)
        self.bottom_tabs.addTab(self.dry_panel, "Dry run")
        lv.addWidget(self.bottom_tabs)

        main_col = QWidget()
        mc = QVBoxLayout(main_col)
        mc.setContentsMargins(0, 0, 0, 0)
        mc.setSpacing(0)
        mc.addWidget(self.build_topbar())
        mc.addWidget(self.stack, 1)

        split = QSplitter(Qt.Vertical)
        split.addWidget(main_col)
        split.addWidget(log_box)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([560, 220])

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(side)
        h.addWidget(split, 1)
        # Safety net: nothing inside may ever push the window past the screen – if the
        # window is smaller than the content needs, the content scrolls instead.
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QScrollArea.NoFrame)
        outer.setWidget(root)
        self.setCentralWidget(outer)

        from .helper_panel import HelperDock
        self.helper = HelperDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.helper)
        self.helper.hide()
        self.install_activity_hooks()
        self.install_shortcuts()
        self.directory.connection_changed.connect(
            lambda ok, _t: ok and (self.pages["Home"].auto_refresh(), self.daily_tasks()))
        self.nav.setCurrentRow(0)
        self.statusBar().showMessage("Ready  ·  Press F1 for help")
        from .tray import Tray
        self.tray = Tray(self)
        if self.tray.active:
            from PySide6.QtWidgets import QApplication
            QApplication.instance().setQuitOnLastWindowClosed(False)
        QTimer.singleShot(300, self._startup)

    def closeEvent(self, event):
        """With the tray on, closing only hides GAMbit (quit from the tray menu)."""
        tray = getattr(self, "tray", None)
        if tray is not None and tray.closing(event):
            return
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None and not app.quitOnLastWindowClosed():
            app.setQuitOnLastWindowClosed(True)
            QTimer.singleShot(0, app.quit)
        super().closeEvent(event)

    def tray_notify_approvals(self, n: int):
        tray = getattr(self, "tray", None)
        if tray is not None:
            tray.approvals(n)

    # ---------------------------------------------------------- startup ---
    def _unfinished_update(self, info: dict):
        """The last update was started but GAMbit is still the old version."""
        import os
        from PySide6.QtWidgets import QMessageBox
        from .. import updaters
        log = updaters.update_log_tail()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("The update didn't finish")
        box.setText("GAMbit started installing an update, but it's still the old version – "
                    "the installer stopped before it finished. Nothing was changed.")
        box.setInformativeText(
            "Run the installer again with its own window so you can see any message it "
            "shows. Pick “Install for me only” if it asks. Your settings are kept.")
        if log:
            box.setDetailedText(f"Installer log ({info['log']}):\n\n{log}")
        installer = info.get("installer") or ""
        run = box.addButton("Run the installer", QMessageBox.AcceptRole) \
            if installer and os.path.exists(installer) else None
        get = box.addButton("Check for updates", QMessageBox.ActionRole)
        box.addButton("Not now", QMessageBox.RejectRole)
        box.exec()
        if run is not None and box.clickedButton() is run:
            try:
                updaters.launch_installer(installer, silent=False)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Couldn't start the installer", str(exc))
                return
            from PySide6.QtWidgets import QApplication
            QApplication.quit()
        elif box.clickedButton() is get and "Settings & Updates" in self.pages:
            self.go("Settings & Updates")

    def _startup(self):
        from .. import deploy
        for line in deploy.apply_on_start():
            self.log_line("📦 " + line, "#7cc4ff")
        try:
            from .. import updaters
            unfinished = updaters.unfinished_update()
        except Exception:  # noqa: BLE001
            unfinished = None
        settings.set("update/in_progress", 0)     # we're running, so any update finished
        if unfinished:
            QTimer.singleShot(800, lambda: self._unfinished_update(unfinished))
        import datetime as _dt
        settings.set("home/last_open", _dt.datetime.now().isoformat(timespec="seconds"))
        try:   # the single morning jobs from earlier versions become saved jobs
            from .. import saved_jobs
            for j in saved_jobs.migrate_legacy():
                self.log_line(f"Your schedule is now the saved job “{j['name']}” "
                              "(Automation → Schedules).", "#7cc4ff")
        except Exception:  # noqa: BLE001
            pass
        self.start_session_ui()
        self.preload_pages()          # the rest of the pages, quietly in the background
        self.install_practice()
        try:
            from .. import whats_new
            whats_new.first_run_check()
            if whats_new.unseen() and gam_setup.is_fully_set_up() and \
                    not settings.get("whatsnew/off", False):
                QTimer.singleShot(2500, self.show_whats_new)
        except Exception:  # noqa: BLE001
            pass
        self.apply_helpdesk_mode()
        self.set_dry_run(bool(settings.get("safety/dry_run", False)))
        self.update_approvals_badge()
        self._approvals_timer = QTimer(self, interval=5 * 60 * 1000,
                                       timeout=self.update_approvals_badge)
        self._approvals_timer.start()
        from .. import team
        if team.folder():
            self.statusBar().showMessage(f"Signed in to GAMbit as {team.me()} "
                                         f"({team.my_role_name()})  ·  Press F1 for "
                                         "help")
        sp: SettingsPage = self.pages["Settings & Updates"]
        sp.refresh_installed()
        if not gam_setup.is_fully_set_up():
            if not settings.get("setup/seen", False):
                self.open_setup()
            else:
                self.pages["Home"].show_banner(
                    "GAM setup isn't finished yet. Click 'Open setup wizard' below to pick "
                    "up where you left off.")
        elif settings.get("connection/auto_test", True):
            self.test_connection()
        from .. import ou_map
        if gam_setup.is_fully_set_up() and not ou_map.configured() and \
                not settings.get("oumap/reminded", False):
            settings.set("oumap/reminded", True)
            self.pages["Home"].show_banner(
                "Tip: tell GAMbit which org units are students, staff, schools and "
                "Chromebooks – Settings & Updates → Org units & schools (✨ Find them for me "
                "does most of it).")
        if gam_setup.is_fully_set_up() and not settings.get("tour/seen", False) \
                and not settings.get("helpdesk/on", False):
            QTimer.singleShot(1500, self.start_tour)
        if settings.check_updates_on_start:
            sp.check_app(False)
            sp.check_gam(quiet=True)
        self._release_check()

    def _release_check(self):
        """First start after an update: run the release checks again."""
        from .. import release_check
        from .widgets import Worker
        if not release_check.pending_for(__version__) or not gam_setup.is_fully_set_up():
            return
        self.log_line("🔎 Checking this new version against your domain…", "#7cc4ff")

        def done(res):
            _after, bad = res
            if not bad:
                self.log_line("✔ Release check passed – everything that worked before still "
                              "works.", "#7ee787")
                return
            from PySide6.QtWidgets import QMessageBox
            from .. import updaters
            text = "\n".join(f"• {b['Check']}: {b['Detail'] or 'failed'}" for b in bad)
            prev = updaters.rollback_target()
            self.log_line("✖ Release check: " + "; ".join(b["Check"] for b in bad), "#ff8a80")
            sp = self.pages["Settings & Updates"]
            if prev and settings.get("release/auto_rollback", False):
                self.log_line(f"Going back to GAMbit {prev} automatically…", "#ff8a80")
                sp.rollback(ask=False)
            elif prev and QMessageBox.question(
                    self, "Release check", f"Something that worked before this update now "
                    f"fails:\n\n{text}\n\nGo back to GAMbit {prev}?") == QMessageBox.Yes:
                sp.rollback(ask=False)
        Worker(release_check.after_update, on_done=done,
               on_error=lambda e: self.log_line(f"Release check couldn't run: {e}", "#ff8a80"))

    def open_setup(self):
        from .setup_wizard import SetupWizard
        SetupWizard(self).exec()
        self.pages["Settings & Updates"].refresh_installed()
        if gam_setup.is_fully_set_up():
            self.pages["Home"].banner.hide()
            self.test_connection()

    def test_connection(self):
        """One shared test used by Home, Settings and the wizard."""
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        self._append(f"\n[{stamp}] > gam info domain\n", "#7cc4ff")
        self.pages["Home"].set_connection(None, "Testing…")
        self.directory.test_connection(log=self.log_line)

    # -------------------------------------------------------------- nav ---
    # ------------------------------------------------------------ sidebar ---
    MY = "MY PAGES"

    def build_nav(self, select: bool = True):
        """The sidebar: My pages (pinned + most used) on top, then every section. Sections
        fold with a click on their heading."""
        from .. import team, user_prefs as up
        names = [n for n, _c in PAGES]
        cur = self.stack.currentIndex() if select else 0
        self.nav.blockSignals(True)
        self.nav.clear()
        self._row_page, self._row_section, self._header_row = {}, {}, {}
        avail = [n for n in names if team.page_allowed(n) and not self._user_hidden(n)
                 and n not in ("Home",)]
        pins, freq = up.my_pages(avail)
        folded = up.collapsed()

        def header(key):
            it = QListWidgetItem(("▸ " if key in folded else "▾ ") + key.title()
                                 if key != self.MY else ("▸ " if key in folded else "▾ ") +
                                 "My pages", self.nav)
            it.setFlags(Qt.ItemIsEnabled)
            it.setData(Qt.UserRole, "header")
            it.setData(Qt.UserRole + 1, key)
            it.setToolTip("Click to fold or unfold this section")
            f = it.font()
            f.setPointSizeF(f.pointSizeF() * 0.8)
            f.setBold(True)
            it.setFont(f)
            it.setForeground(QColor("#6f87a3"))
            self._header_row[self.nav.count() - 1] = key

        def item(name, section, tip=""):
            self._row_page[self.nav.count()] = names.index(name)
            self._row_section[self.nav.count()] = section
            it = QListWidgetItem(name, self.nav)
            if tip:
                it.setToolTip(tip)
        section = ""
        for entry in NAV:
            if isinstance(entry, str):
                if not section and (pins or freq):
                    header(self.MY)
                    for n in pins:
                        item(n, self.MY, "Pinned – right-click to unpin")
                    for n in freq:
                        item(n, self.MY, "One of the pages you use most")
                section = entry
                header(entry)
                continue
            item(entry[0], section)
        self.nav.blockSignals(False)
        self._nav_built = True
        if hasattr(self, "hd_btn"):            # not during the first build in __init__
            self.apply_helpdesk_mode()
            self.update_approvals_badge()
        if select:
            row = next((r for r, i in self._row_page.items() if i == cur and
                        self._row_section.get(r) != self.MY), None)
            if row is not None:
                self.nav.blockSignals(True)
                self.nav.setCurrentRow(row)
                self.nav.blockSignals(False)

    def _nav_clicked(self, it):
        if it is None or it.data(Qt.UserRole) != "header":
            return
        from .. import user_prefs as up
        key = it.data(Qt.UserRole + 1)
        folded = up.toggle_section(key)
        label = "My pages" if key == self.MY else key.title()
        it.setText(("▸ " if folded else "▾ ") + label)
        self.apply_helpdesk_mode()

    def fold_all(self, fold: bool):
        from .. import user_prefs as up
        keys = set(self._header_row.values())
        up.set_collapsed(keys if fold else set())
        self.build_nav()

    def toggle_pin(self, name: str):
        from .. import user_prefs as up
        on = up.toggle_pin(name)
        self.build_nav()
        self.statusBar().showMessage(f"Pinned {name} to My pages." if on else
                                     f"Unpinned {name}.", 4000)

    def _nav_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        it = self.nav.itemAt(pos)
        if not it or it.data(Qt.UserRole) == "header":
            return
        name = it.text().split(" (")[0]
        menu = QMenu(self)
        from .. import user_prefs as up
        if name != "Home":
            menu.addAction("Unpin from My pages" if name in up.pinned() else
                           "📌 Pin to My pages", lambda: self.toggle_pin(name))
        if name not in ("Home", "Settings & Updates"):
            menu.addAction(f"Hide “{name}” from my sidebar", lambda: self.hide_page(name))
        menu.addAction("Show all hidden pages", self.show_all_pages)
        menu.addSeparator()
        menu.addAction("Fold all sections", lambda: self.fold_all(True))
        menu.addAction("Unfold all sections", lambda: self.fold_all(False))
        menu.addAction("Hide my most-used pages" if up.show_frequent() else
                       "Show my most-used pages", self._toggle_frequent)
        menu.exec(self.nav.viewport().mapToGlobal(pos))

    def _toggle_frequent(self):
        from .. import user_prefs as up
        settings.set(up.FREQUENT_KEY, not up.show_frequent())
        self.build_nav()

    def hide_page(self, name: str):
        import json
        hidden = set(json.loads(settings.get("ui/hidden_pages", "[]") or "[]"))
        hidden.add(name)
        settings.set("ui/hidden_pages", json.dumps(sorted(hidden)))
        self.build_nav()
        self.statusBar().showMessage(f"Hid {name}. Right-click the sidebar to bring it back.")

    def show_all_pages(self):
        settings.set("ui/hidden_pages", "[]")
        settings.set("ui/show_advanced", True)
        self.build_nav()

    def page_at(self, idx: int):
        return self.pages[PAGES[idx][0]]

    def page_name_at(self, idx: int) -> str:
        return PAGES[idx][0] if 0 <= idx < len(PAGES) else ""

    def current_page(self):
        i = self.stack.currentIndex()
        return self.pages[PAGES[i][0]] if 0 <= i < len(PAGES) else None

    def _page_built(self, name: str, page):
        """Put a newly built page in its place and give it the window's current state."""
        idx = [n for n, _c in PAGES].index(name)
        self._holders[idx].setWidget(page)
        try:
            from .widgets import apply_helpdesk
            from ..gam_runner import helpdesk_on
            from .. import team
            on = helpdesk_on()
            apply_helpdesk(on)
            if hasattr(page, "set_helpdesk"):
                page.set_helpdesk(on)
            if hasattr(page, "set_role"):
                page.set_role(team.my_role())
            if hasattr(page, "dry_changed"):
                page.dry_changed(bool(settings.get("safety/dry_run", False)))
            from . import theme
            if theme.is_dark():
                theme.polish_tree(page)
        except Exception:  # noqa: BLE001 – the page still works without these touches
            pass

    def preload_pages(self):
        """Build the pages nobody has opened yet, one at a time while GAMbit is idle, so
        opening them later is instant."""
        todo = [n for n, _c in PAGES if not self.pages.built(n)]
        if not todo:
            return

        def step():
            if not todo:
                return
            n = todo.pop(0)
            try:
                self.pages[n]
            except Exception:  # noqa: BLE001
                pass
            if todo:
                busy = getattr(self.runner, "busy", False)
                busy = busy() if callable(busy) else busy
                QTimer.singleShot(600 if busy else 120, step)
        QTimer.singleShot(4000, step)

    def go(self, name: str):
        alias = PAGE_ALIASES.get(name)
        if alias:                      # pages that became tabs of another page
            page, tab = alias
            self.go(page)
            p = self.pages.get(page)
            if p is not None and hasattr(p, "show_tab"):
                p.show_tab(tab)
            return
        idx = [n for n, _ in PAGES].index(name)
        row = next(r for r, i in self._row_page.items() if i == idx)
        self.nav.setCurrentRow(row)

    def _switch(self, row):
        if row not in self._row_page:
            return
        from .. import team
        idx = self._row_page[row]
        name = [n for n, _ in PAGES][idx] if idx < len(PAGES) else ""
        self._current_page_name = name if name and team.page_allowed(name) else "Home"
        from . import theme
        if theme.is_dark() and 0 <= idx < len(PAGES) and self.pages.built(PAGES[idx][0]):
            theme.polish_tree(self.pages[PAGES[idx][0]])
        if name and not team.page_allowed(name):
            self.statusBar().showMessage(f"Your GAMbit role can't open {name}.", 5000)
            home = next(r for r, i in self._row_page.items() if i == 0)
            if row != home:
                self.nav.setCurrentRow(home)
            return
        self.stack.setCurrentIndex(self._row_page[row])
        self.current_page().on_show()
        try:
            from .. import user_prefs
            user_prefs.bump(name)
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------- shared hooks ---
    def set_gam_version(self, ver):
        self.pages["Home"].set_gam_version(ver)
        self._gam_ver = ver
        self.side_footer.setText(f"GAMbit v{__version__}\nGAM {ver or 'not found'}")

    def notify(self, text: str):
        self.statusBar().showMessage(text)
        self.pages["Home"].show_banner(text + " — see Settings & Updates.")
        item = self.nav.item(self.nav.count() - 1)
        item.setText("Settings & Updates  ●")

    def log_line(self, text: str, color: str | None = None):
        self._append(text.rstrip("\n") + "\n", color)

    # -------------------------------------------------------- runner ---
    def _append(self, text, color=None):
        cur = self.log.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(QColor(color))
        cur.insertText(text, fmt)
        self.log.setTextCursor(cur)
        self.log.ensureCursorVisible()

    def _cmd_started(self, cmd):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        self._append(f"\n[{stamp}] > {cmd}\n", "#7cc4ff")
        self.status.setText(f"Running: {cmd}")

    def _cmd_output(self, text, is_error):
        self._append(text, "#ff8a80" if is_error else None)

    def _cmd_finished(self, code, cmd):
        ok = code == 0
        msg = ("✔ Done" if ok else "■ Cancelled" if code == -2
               else f"✖ Finished with exit code {code}")
        if len(self.runner.running) or cmd.startswith("[#"):
            msg += f"  ({cmd[:70]})"
        self._append(msg + "\n", "#7ee787" if ok else "#ff8a80")
        self.status.setText("Ready" if ok else f"Last command failed (exit code {code})")

    def _busy(self, busy):
        self.stop_btn.setEnabled(bool(self.runner.running))
