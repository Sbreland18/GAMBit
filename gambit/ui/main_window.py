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
from .pages.classroom import ClassroomPage
from .pages.console import BulkPage, ConsolePage
from .pages.devices import DevicesPage
from .pages.drive import DrivePage
from .pages.email import EmailPage
from .pages.groups import GroupsPage
from .pages.home import HomePage
from .pages.licenses import LicensesPage
from .pages.orgunits import OrgUnitsPage
from .pages.reports import ReportsPage
from .pages.settings_page import SettingsPage
from .pages.users import UsersPage
from .pages.workflows import WorkflowsPage
from .app_actions import AppActions, MoreActions
from .jobs_panel import JobsPanel
from .pages.activity_page import ActivityPage
from .pages.approvals import ApprovalsPage
from .pages.diagnostics_page import DiagnosticsPage
from .pages.livetest_page import LiveTestPage
from .pages.tasks_page import TasksPage
from .pages.fleet_page import FleetPage
from .pages.compliance_page import CompliancePage
from .pages.investigations_page import InvestigationsPage
from .pages.more_tabs import StaffDevicesPage, UsagePage
from .pages.recovery_tabs import SettingsWatchPage
from .pages.ask_page import AskPage
from .pages.insight_pages import (BudgetPage, MismatchPage, SchoolReportsPage,
                                  TicketQueuePage)
from .pages.round10_pages import AuditReportPage, TeacherListsPage
from .pages.round11_pages import (OwnershipPage, PolicyRolloutsPage, TimeMachinePage,
                                   TwoStepPage)
from .pages.round12_pages import BaselinePage, ChangeCalendarPage, RecordsPage
from .pages.guide_page import GuidePage
from .pages.round15_pages import (BackToSchoolPage, MailboxAccessPage, OutsideChangesPage,
                                  RecoveryCoveragePage, StaffCardPage)
from .pages.round14_pages import (AIUsePage, CostPerStudentPage, DirectoryQualityPage,
                                   MeetAttendancePage)
from .pages.round13_pages import (AccessReviewPage, AccountTimingPage, GoingQuietPage,
                                   StaleContentPage, StorageForecastPage)
from .pages.automation_tabs import CleanupPage
from .pages.policies_page import PoliciesPage
from .pages.timeline_page import TimelinePage
from .pages.lookup_page import LookupPage
from .pages.builder import BuilderPage
from .pages.rostersync import RosterSyncPage
from .pages.scheduled import ScheduledPage
from .pages.services import ServicesPage
from .widgets import button

# Sidebar: strings are section headings, tuples are pages.
NAV = [
    ("Home", HomePage),
    ("Guide", GuidePage),
    ("Workflows", WorkflowsPage), ("Back to school", BackToSchoolPage),
    "PEOPLE",
    ("Users", UsersPage),
    ("Student lookup", LookupPage), ("Staff card", StaffCardPage),
    ("Groups", GroupsPage),
    ("Classroom", ClassroomPage),
    ("Roster sync", RosterSyncPage), ("Mismatch report", MismatchPage),
    ("Account timeline", TimelinePage), ("Account time machine", TimeMachinePage),
    ("Directory quality", DirectoryQualityPage),
    "DEVICES",
    ("Chromebooks", DevicesPage),
    ("Chromebook fleet", FleetPage), ("Staff devices", StaffDevicesPage),
    "SERVICES",
    ("Email", EmailPage),
    ("Google Drive", DrivePage),
    ("More services", ServicesPage),
    "ADMIN",
    ("Org units", OrgUnitsPage),
    ("Licenses", LicensesPage), ("Budget planner", BudgetPage),
    ("Policies by org unit", PoliciesPage), ("Policy rollouts", PolicyRolloutsPage),
    ("2-Step Verification", TwoStepPage), ("Ownership check", OwnershipPage),
    ("Security baseline", BaselinePage), ("Records requests", RecordsPage),
    ("Access review", AccessReviewPage), ("Cost per student", CostPerStudentPage),
    ("Mailbox access review", MailboxAccessPage), ("Account recovery", RecoveryCoveragePage),
    "REPORTS",
    ("Reports", ReportsPage), ("School reports", SchoolReportsPage),
    ("Teacher lists", TeacherListsPage), ("Audit report", AuditReportPage),
    ("Students going quiet", GoingQuietPage), ("Account timing", AccountTimingPage),
    ("Storage forecast", StorageForecastPage), ("Meet attendance", MeetAttendancePage),
    ("AI use", AIUsePage),
    ("Security reports", CompliancePage), ("Investigations", InvestigationsPage), ("Usage", UsagePage),
    ("Settings watch", SettingsWatchPage), ("Changes outside GAMbit", OutsideChangesPage),
    ("Activity log", ActivityPage),
    "AUTOMATION",
    ("Approvals", ApprovalsPage), ("Ticket queue", TicketQueuePage),
    ("Scheduled jobs", ScheduledPage), ("Run later & freezes", ChangeCalendarPage),
    ("Stale content", StaleContentPage),
    ("Background tasks", TasksPage), ("Clean-up rules", CleanupPage),
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
        self._stack_pages: list = []
        self.pages = {}
        self._row_page: dict[int, int] = {}
        for entry in NAV:
            if isinstance(entry, str):
                head = QListWidgetItem(entry, self.nav)
                head.setFlags(Qt.NoItemFlags)
                head.setData(Qt.UserRole, "header")
                f = head.font()
                f.setPointSizeF(f.pointSizeF() * 0.8)
                f.setBold(True)
                head.setFont(f)
                head.setForeground(QColor("#6f87a3"))
                continue
            name, cls = entry
            page = cls(self)
            self.pages[name] = page
            self._row_page[self.nav.count()] = self.stack.count()
            # each page sits in a scroll area so no page can force the window to be bigger
            # than the screen (small laptops); pages scroll instead
            holder = QScrollArea()
            holder.setWidgetResizable(True)
            holder.setFrameShape(QScrollArea.NoFrame)
            holder.setWidget(page)
            self._stack_pages.append(page)
            self.stack.addWidget(holder)
            QListWidgetItem(name, self.nav)
        self.nav.currentRowChanged.connect(self._switch)
        self.nav.setContextMenuPolicy(Qt.CustomContextMenu)
        self.nav.customContextMenuRequested.connect(self._nav_menu)

        # output + jobs panel
        log_box = QWidget()
        lv = QVBoxLayout(log_box)
        lv.setContentsMargins(24, 4, 24, 12)
        head = QHBoxLayout()
        self.status = QLabel("Ready", objectName="Muted")
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
        self.setCentralWidget(root)

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
        QTimer.singleShot(300, self._startup)

    # ---------------------------------------------------------- startup ---
    def _startup(self):
        from .. import deploy
        for line in deploy.apply_on_start():
            self.log_line("📦 " + line, "#7cc4ff")
        self.start_session_ui()
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
    def _nav_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        it = self.nav.itemAt(pos)
        if not it or it.data(Qt.UserRole) == "header":
            return
        name = it.text().split(" (")[0]
        menu = QMenu(self)
        if name not in ("Home", "Settings & Updates"):
            menu.addAction(f"Hide “{name}” from my sidebar", lambda: self.hide_page(name))
        menu.addAction("Show all hidden pages", self.show_all_pages)
        menu.exec(self.nav.viewport().mapToGlobal(pos))

    def hide_page(self, name: str):
        import json
        hidden = set(json.loads(settings.get("ui/hidden_pages", "[]") or "[]"))
        hidden.add(name)
        settings.set("ui/hidden_pages", json.dumps(sorted(hidden)))
        self.apply_role()
        self.statusBar().showMessage(f"Hid {name}. Right-click the sidebar to bring it back.")

    def show_all_pages(self):
        settings.set("ui/hidden_pages", "[]")
        settings.set("ui/show_advanced", True)
        self.apply_role()

    def page_at(self, idx: int):
        return self._stack_pages[idx]

    def current_page(self):
        i = self.stack.currentIndex()
        return self._stack_pages[i] if 0 <= i < len(self._stack_pages) else None

    def go(self, name: str):
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
        if name and not team.page_allowed(name):
            self.statusBar().showMessage(f"Your GAMbit role can't open {name}.", 5000)
            home = next(r for r, i in self._row_page.items() if i == 0)
            if row != home:
                self.nav.setCurrentRow(home)
            return
        self.stack.setCurrentIndex(self._row_page[row])
        self.current_page().on_show()

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
