"""First-run Setup Wizard: gets a brand-new admin from zero to a working GAM."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QProgressBar, QRadioButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import gam_setup, updaters
from ..settings import IS_WINDOWS, default_gam_dir, settings
from ..version import APP_NAME
from .widgets import Worker, button

STEPS = ["Welcome", "Install GAM", "Create Google project", "Sign GAM in",
         "Allow GAM access", "All done"]


def _label(html: str, muted=False) -> QLabel:
    lab = QLabel(html)
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.RichText)
    lab.setOpenExternalLinks(True)
    lab.setTextInteractionFlags(Qt.TextBrowserInteraction)
    if muted:
        lab.setObjectName("Muted")
    return lab


class StatusPill(QLabel):
    def set(self, ok: bool | None, text: str):
        color = {True: ("#e6f4ea", "#137333"), False: ("#fdecea", "#b42318"),
                 None: ("#eef1f4", "#57606a")}[ok]
        icon = {True: "✔", False: "✖", None: "•"}[ok]
        self.setText(f"{icon}  {text}")
        self.setStyleSheet(f"background:{color[0]}; color:{color[1]}; border-radius:8px;"
                           "padding:8px 12px; font-weight:600;")


class SetupWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} – GAM Setup")
        self.resize(940, 640)
        self.setModal(True)
        self.release = None

        self.steps = QListWidget(objectName="Nav")
        self.steps.setFixedWidth(230)
        self.steps.setFocusPolicy(Qt.NoFocus)
        for s in STEPS:
            QListWidgetItem(s, self.steps)
        self.steps.currentRowChanged.connect(self._goto)

        self.stack = QStackedWidget()
        self.stack.setObjectName("Page")
        for build in (self._p_welcome, self._p_install, self._p_project, self._p_oauth,
                      self._p_delegation, self._p_done):
            page = QWidget(objectName="Page")
            lay = QVBoxLayout(page)
            lay.setContentsMargins(28, 22, 28, 10)
            lay.setSpacing(12)
            build(lay)
            lay.addStretch(1)
            self.stack.addWidget(page)

        self.back_btn = button("Back", slot=lambda: self._move(-1))
        self.next_btn = button("Next", "primary", lambda: self._move(1))
        self.skip_lbl = QLabel("You can close this and come back any time from "
                               "Settings & Updates → Setup wizard.", objectName="Muted")
        nav = QHBoxLayout()
        nav.setContentsMargins(28, 6, 28, 16)
        nav.addWidget(self.skip_lbl, 1)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(self.stack, 1)
        right.addLayout(nav)
        rw = QWidget(objectName="Page")
        rw.setLayout(right)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        side = QVBoxLayout()
        side.setSpacing(0)
        side.addWidget(QLabel("GAM Setup", objectName="Brand"))
        side.addWidget(QLabel("About 15 minutes, one time", objectName="BrandSub"))
        side.addWidget(self.steps, 1)
        sw = QWidget()
        sw.setLayout(side)
        sw.setStyleSheet("background:#0f2741;")
        root.addWidget(sw)
        root.addWidget(rw, 1)

        self.timer = QTimer(self, interval=2000, timeout=self.refresh)
        self.timer.start()
        self.steps.setCurrentRow(0)
        self.refresh()

    # ============================================================ pages ===
    def _title(self, lay, title, sub=""):
        lay.addWidget(QLabel(title, objectName="PageTitle"))
        if sub:
            lay.addWidget(_label(sub, muted=True))

    def _card(self, lay) -> QVBoxLayout:
        f = QFrame(objectName="Card")
        v = QVBoxLayout(f)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        lay.addWidget(f)
        return v

    # -- 0 welcome --------------------------------------------------------
    def _p_welcome(self, lay):
        self._title(lay, "Let's get GAM ready",
                    "GAMbit will install GAM and walk you through connecting it to your "
                    "Google Workspace. Most of it is automatic. Google needs you to "
                    "sign in and click <b>Allow</b> a few times.")
        c = self._card(lay)
        c.addWidget(_label("<b>Before you start, you need:</b><br>"
                           "• A <b>Super Admin</b> account for your Google Workspace<br>"
                           "• To be able to sign in to that account in your web browser<br>"
                           "• About 15 minutes"))
        form = QFormLayout()
        self.admin = QLineEdit(settings.get("gam/admin", ""))
        self.admin.setPlaceholderText("you@yourschool.org (your super admin account)")
        self.admin.textChanged.connect(lambda t: settings.set("gam/admin", t.strip()))
        form.addRow("Admin email", self.admin)
        c.addLayout(form)

        c = self._card(lay)
        self.mode_new = QRadioButton("Set up GAM for me (recommended for new users)")
        self.mode_existing = QRadioButton("I already use GAM on this computer – just find it")
        self.mode_new.setChecked(True)
        c.addWidget(self.mode_new)
        c.addWidget(self.mode_existing)
        self.existing_box = QWidget()
        ef = QFormLayout(self.existing_box)
        ef.setContentsMargins(24, 0, 0, 0)
        self.ex_gam = QLineEdit(settings.gam_dir)
        self.ex_cfg = QLineEdit(settings.gam_cfg_dir or gam_setup.effective_cfg_dir())
        ef.addRow("GAM program folder", self._browse_row(self.ex_gam))
        ef.addRow("GAM config folder", self._browse_row(self.ex_cfg))
        ef.addRow("", button("Use these folders", "primary", self._use_existing))
        c.addWidget(self.existing_box)
        self.existing_box.setVisible(False)
        self.mode_existing.toggled.connect(self.existing_box.setVisible)

    def _browse_row(self, edit):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit)

        def pick():
            d = QFileDialog.getExistingDirectory(self, "Choose folder", edit.text())
            if d:
                edit.setText(os.path.normpath(d))
        h.addWidget(button("Browse…", slot=pick))
        return w

    def _use_existing(self):
        settings.gam_dir = self.ex_gam.text().strip()
        settings.gam_cfg_dir = self.ex_cfg.text().strip()
        self.refresh()
        if not settings.gam_path():
            QMessageBox.warning(self, "GAM not found",
                                "gam.exe isn't in that folder. Check the path, or choose "
                                "'Set up GAM for me'.")
            return
        # jump to the first unfinished step
        if not gam_setup.has_project():
            self.steps.setCurrentRow(2)
        elif not gam_setup.has_oauth():
            self.steps.setCurrentRow(3)
        else:
            self.steps.setCurrentRow(4)

    # -- 1 install --------------------------------------------------------
    def _p_install(self, lay):
        self._title(lay, "Install GAM",
                    "GAMbit downloads the latest GAM from its official GitHub page and "
                    "sets up the folders. No admin rights needed.")
        c = self._card(lay)
        form = QFormLayout()
        self.in_gam = QLineEdit(settings.get("gam/dir", "") or default_gam_dir())
        self.in_cfg = QLineEdit(settings.gam_cfg_dir or gam_setup.default_cfg_dir())
        form.addRow("Install GAM to", self._browse_row(self.in_gam))
        form.addRow("Keep GAM settings in", self._browse_row(self.in_cfg))
        c.addLayout(form)
        self.in_path = QCheckBox("Also let me type 'gam' in any Command Prompt "
                                 "(adds GAM to PATH and sets GAMCFGDIR)")
        self.in_path.setChecked(IS_WINDOWS)
        self.in_path.setVisible(IS_WINDOWS)
        c.addWidget(self.in_path)
        self.in_btn = button("Install GAM", "primary", self._install)
        self.in_progress = QProgressBar()
        self.in_progress.hide()
        c.addWidget(self.in_btn, 0, Qt.AlignLeft)
        c.addWidget(self.in_progress)
        self.in_status = StatusPill()
        lay.addWidget(self.in_status)
        self.in_log = QPlainTextEdit(objectName="Log")
        self.in_log.setReadOnly(True)
        self.in_log.setFixedHeight(120)
        lay.addWidget(self.in_log)

    def _install(self):
        settings.gam_dir = self.in_gam.text().strip()
        settings.gam_cfg_dir = self.in_cfg.text().strip()
        self.in_btn.setEnabled(False)
        self.in_log.appendPlainText("Finding the latest GAM release…")

        def got_release(rel):
            self.release = rel
            self.in_progress.setValue(0)
            self.in_progress.show()
            Worker(updaters.install_gam, rel, settings.gam_dir, use_progress=True,
                   use_log=True, on_progress=self._prog,
                   on_message=self.in_log.appendPlainText,
                   on_done=lambda _: self._after_install(), on_error=fail)

        def fail(err):
            self.in_progress.hide()
            self.in_btn.setEnabled(True)
            self.in_log.appendPlainText(f"Problem: {err}")
            self.in_status.set(False, "Install didn't finish – see the message above")

        Worker(updaters.latest_gam_release, on_done=got_release, on_error=fail)

    def _prog(self, done, total):
        if total:
            self.in_progress.setMaximum(100)
            self.in_progress.setValue(int(done * 100 / total))
            self.in_progress.setFormat(f"Downloading… {done / 1e6:.0f} of {total / 1e6:.0f} MB")

    def _after_install(self):
        self.in_progress.hide()
        self.in_log.appendPlainText("Setting up the config folder…")

        def finish(notes):
            for n in notes:
                self.in_log.appendPlainText(n)
            self.in_btn.setEnabled(True)
            self.refresh()
            if self.parent() and hasattr(self.parent(), "pages"):
                self.parent().pages["Settings & Updates"].refresh_installed()

        def work():
            notes = gam_setup.prepare_config_dir(self.admin.text().strip())
            if self.in_path.isChecked():
                try:
                    notes.append(gam_setup.set_windows_user_env(settings.gam_dir,
                                                                settings.gam_cfg_dir))
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"Could not update PATH: {exc}")
            return notes

        Worker(work, on_done=finish, on_error=lambda e: finish([f"Problem: {e}"]))

    # -- 2 project --------------------------------------------------------
    def _p_project(self, lay):
        self._title(lay, "Create your Google Cloud project",
                    "GAM needs its own small project in Google Cloud. It's free. GAM creates "
                    "almost all of it for you. You copy two values once.")
        c = self._card(lay)
        c.addWidget(_label(
            "When you click <b>Start</b>, a window opens. Here's what happens:<ol>"
            "<li>Your browser opens. <b>Sign in with your super admin</b> and click <b>Allow</b>.</li>"
            "<li>Wait about a minute while GAM turns on Google's APIs (it counts to 23/23).</li>"
            "<li>GAM shows a link. Open it, choose <b>Application type: Desktop app</b>, "
            "name it <b>GAM</b>, and click <b>Create</b>.</li>"
            "<li>Copy the <b>Client ID</b>, paste it into the window "
            "(right-click pastes), and press Enter.</li>"
            "<li>Copy the <b>Client secret</b>, paste it, and press Enter.</li>"
            "<li>When you see <i>“That's it! Your GAM Project is created”</i>, you're done "
            "with this step.</li></ol>"))
        self.pr_btn = button("Start", "primary", self._start_project)
        c.addWidget(self.pr_btn, 0, Qt.AlignLeft)
        self.pr_status = StatusPill()
        lay.addWidget(self.pr_status)
        lay.addWidget(_label("GAMbit watches for the finished files and ticks this step off "
                             "by itself.", muted=True))

    def _need_admin(self) -> str | None:
        email = self.admin.text().strip()
        if "@" not in email:
            QMessageBox.information(self, "Admin email", "Enter your super admin email on "
                                    "the Welcome step first.")
            self.steps.setCurrentRow(0)
            self.admin.setFocus()
            return None
        if not settings.gam_path():
            QMessageBox.information(self, "Install GAM", "Install GAM first.")
            self.steps.setCurrentRow(1)
            return None
        return email

    def _console(self, args, title, intro):
        msg = gam_setup.launch_console(args, title, intro)
        if msg:
            QMessageBox.information(self, title, msg)

    def _start_project(self):
        if email := self._need_admin():
            self._console(["create", "project", "admin", email], "Create Google project", [
                "1. Sign in with your super admin in the browser and click Allow.",
                "2. Wait while GAM enables APIs (1/23 ... 23/23).",
                "3. Open the link GAM shows: choose Desktop app, name it GAM, click Create.",
                "4. Paste the Client ID, press Enter. Then paste the Client secret, press Enter.",
                "   (Right-click inside this window to paste.)"])

    # -- 3 oauth ----------------------------------------------------------
    def _p_oauth(self, lay):
        self._title(lay, "Sign GAM in to your admin account",
                    "This lets GAM do admin tasks (users, groups, Chromebooks…) as you.")
        c = self._card(lay)
        c.addWidget(_label(
            "Click <b>Start</b>. In the window that opens:<ol>"
            "<li>You'll see a long list of permissions. The right ones are already "
            "selected. <b>Type&nbsp;c and press Enter.</b></li>"
            "<li>Your browser opens. Sign in as your super admin and click <b>Allow</b>.</li>"
            "<li>When the window says <i>“The authentication flow has completed”</i>, "
            "you're done.</li></ol>"
            "<span style='color:#57606a'>If Google shows an error about the link being "
            "too long, run it again and turn off a few scopes you don't use.</span>"))
        self.oa_btn = button("Start", "primary", self._start_oauth)
        c.addWidget(self.oa_btn, 0, Qt.AlignLeft)
        self.oa_status = StatusPill()
        lay.addWidget(self.oa_status)

    def _start_oauth(self):
        if email := self._need_admin():
            self._console(["oauth", "create", "admin", email], "Sign GAM in", [
                "1. At the permissions list, type  c  and press Enter.",
                "2. Sign in with your super admin in the browser and click Allow."])

    # -- 4 delegation -----------------------------------------------------
    def _p_delegation(self, lay):
        self._title(lay, "Allow GAM to work with user data",
                    "Some features (Drive, Gmail settings, calendars) need one more "
                    "approval in the Google Admin console.")
        c = self._card(lay)
        c.addWidget(_label(
            "<ol><li>Click <b>Open approval window</b>. Type <b>c</b> and press Enter at the "
            "permissions list.</li>"
            "<li>GAM prints a link. Open it while signed in as your admin. It goes to "
            "<i>Security → API controls → Domain-wide delegation</i> with everything filled in.</li>"
            "<li>Make sure <b>Overwrite existing client ID</b> is checked, then click "
            "<b>Authorize</b>.</li>"
            "<li>Come back here and click <b>Check</b>. Google can take a few minutes "
            "to catch up. If it still fails, wait and check again.</li></ol>"))
        row = QHBoxLayout()
        row.addWidget(button("Open approval window", "primary", self._start_delegation))
        row.addWidget(button("Open Admin console page", slot=lambda: gam_setup.open_url(
            getattr(self, "dw_url", "https://admin.google.com/ac/owl/domainwidedelegation"))))
        self.dw_check_btn = button("Check", slot=self._check_delegation)
        row.addWidget(self.dw_check_btn)
        row.addStretch(1)
        c.addLayout(row)
        self.dw_status = StatusPill()
        self.dw_status.set(None, "Not checked yet")
        lay.addWidget(self.dw_status)
        self.dw_log = QPlainTextEdit(objectName="Log")
        self.dw_log.setReadOnly(True)
        self.dw_log.setFixedHeight(130)
        lay.addWidget(self.dw_log)

    def _start_delegation(self):
        if email := self._need_admin():
            self._console(["user", email, "update", "serviceaccount"], "Allow GAM access", [
                "1. At the permissions list, type  c  and press Enter.",
                "2. Open the link GAM shows (signed in as your admin).",
                "3. Check 'Overwrite existing client ID' and click AUTHORIZE.",
                "4. Go back to GAMbit and click Check."])

    def _check_delegation(self):
        email = self._need_admin()
        if not email:
            return
        self.dw_check_btn.setEnabled(False)
        self.dw_status.set(None, "Checking with Google…")
        Worker(gam_setup.run_gam, ["user", email, "check", "serviceaccount"],
               on_done=self._delegation_result,
               on_error=lambda e: (self.dw_check_btn.setEnabled(True),
                                   self.dw_status.set(False, str(e))))

    def _delegation_result(self, result):
        code, out = result
        self.dw_check_btn.setEnabled(True)
        self.dw_log.setPlainText(out.strip())
        info = gam_setup.parse_service_account_check(out)
        self.dw_url = info["url"]
        if info["fail"] == 0 and info["pass"] > 0:
            settings.set("gam/delegation_ok", True)
            self.dw_status.set(True, f"All {info['pass']} checks passed – GAM is fully authorized")
        elif info["pass"] or info["fail"]:
            self.dw_status.set(False, f"{info['fail']} not authorized yet. Click Authorize "
                               "in the Admin console, wait a few minutes, then Check again.")
        else:
            self.dw_status.set(False, "Couldn't run the check. Finish the earlier steps first.")
        self._mark()

    # -- 5 done -----------------------------------------------------------
    def _p_done(self, lay):
        self._title(lay, "You're all set",
                    "Let's make sure GAMbit can talk to your Google Workspace.")
        c = self._card(lay)
        self.test_btn = button("Test connection", "primary", self._test)
        c.addWidget(self.test_btn, 0, Qt.AlignLeft)
        self.done_status = StatusPill()
        self.done_status.set(None, "Not tested yet")
        c.addWidget(self.done_status)
        self.summary = _label("")
        lay.addWidget(self.summary)

    def _test(self):
        self.test_btn.setEnabled(False)
        self.done_status.set(None, "Testing…")

        def done(result):
            code, out = result
            self.test_btn.setEnabled(True)
            dom = next((ln.split(":", 1)[1].strip() for ln in out.splitlines()
                        if ln.strip().lower().startswith("primary domain")), "")
            if code == 0:
                self.done_status.set(True, f"Connected to {dom or 'your domain'}")
            else:
                self.done_status.set(False, "Not connected: " + out.strip().splitlines()[-1][:160]
                                     if out.strip() else "Not connected")
        Worker(gam_setup.run_gam, ["info", "domain"], on_done=done)

    # ========================================================= status ===
    def refresh(self):
        installed = bool(settings.gam_path())
        if installed:
            self.in_status.set(True, f"GAM is installed in {os.path.dirname(settings.gam_path())}")
            self.in_btn.setText("Reinstall / update GAM")
        else:
            self.in_status.set(None, "GAM is not installed yet")
        self.pr_status.set(True if gam_setup.has_project() else None,
                           "Project created" if gam_setup.has_project()
                           else f"Waiting… (looking in {gam_setup.effective_cfg_dir()})")
        self.oa_status.set(True if gam_setup.has_oauth() else None,
                           "GAM is signed in" if gam_setup.has_oauth() else "Waiting…")
        self._mark()

    def _mark(self):
        done = [self.admin.text().count("@") == 1,
                bool(settings.gam_path()),
                gam_setup.has_project(),
                gam_setup.has_oauth(),
                bool(settings.get("gam/delegation_ok", False)),
                False]
        for i, ok in enumerate(done):
            self.steps.item(i).setText(("✔  " if ok else "     ") + STEPS[i])

    def _goto(self, row):
        self.stack.setCurrentIndex(row)
        self.back_btn.setEnabled(row > 0)
        self.next_btn.setText("Finish" if row == len(STEPS) - 1 else "Next")
        self.refresh()
        if row == len(STEPS) - 1:
            self.summary.setText(
                "<b>Status</b><br>"
                f"{'✔' if settings.gam_path() else '✖'} GAM installed<br>"
                f"{'✔' if gam_setup.has_project() else '✖'} Google project created<br>"
                f"{'✔' if gam_setup.has_oauth() else '✖'} GAM signed in<br>"
                f"{'✔' if settings.get('gam/delegation_ok', False) else '–'} "
                "User-data access (only needed for Drive, Gmail and Calendar features)")

    def _move(self, delta):
        row = self.steps.currentRow() + delta
        if row >= len(STEPS):
            self.accept()
            return
        if delta > 0 and self.steps.currentRow() == 0 and "@" not in self.admin.text():
            QMessageBox.information(self, "Admin email",
                                    "Please enter your super admin email address.")
            return
        self.steps.setCurrentRow(max(0, row))

    def done(self, r):
        self.timer.stop()
        settings.set("setup/seen", True)
        super().done(r)
