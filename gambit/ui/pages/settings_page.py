from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from ... import team, updaters
from ...gam_runner import gam_environment, gam_version_text
from ...net import is_newer
from ...settings import IS_WINDOWS, settings
from ...version import APP_NAME, GITHUB_REPO, __version__
from ..widgets import Page, Worker, button


def _muted(text):
    lab = QLabel(text, objectName="Muted")
    lab.setWordWrap(True)
    return lab


class SettingsPage(Page):
    title = "Settings & Updates"
    subtitle = "Where GAM lives, and keeping GAM and GAMbit up to date."

    def build(self):
        self.gam_release = None
        self.app_update = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        inner.setObjectName("Page")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 8, 0)
        scroll.setWidget(inner)
        self.body.addWidget(scroll)

        # ---- GAM location ----
        self._admin_only: list = []      # locked for non-admins when GAMbit sign-in is on
        box, form = self.group("GAM location")
        self._admin_only.append(box)
        self.gam_dir = QLineEdit(settings.gam_dir)
        self.gam_dir.editingFinished.connect(self._save_dirs)
        self.cfg_dir = QLineEdit(settings.gam_cfg_dir)
        self.cfg_dir.setPlaceholderText("Optional – GAM's default is your user .gam folder")
        self.cfg_dir.editingFinished.connect(self._save_dirs)
        form.addRow("GAM program folder", self.row(
            self.gam_dir, button("Browse…", slot=lambda: self._browse(self.gam_dir)),
            stretch=False))
        form.addRow("GAM config folder (GAMCFGDIR)", self.row(
            self.cfg_dir, button("Browse…", slot=lambda: self._browse(self.cfg_dir)),
            stretch=False))
        form.addRow("", self.row(
            button("Open GAM folder", slot=lambda: self._open(settings.gam_dir)),
            button("Setup wizard", "primary", self.app.open_setup),
            button("Open setup terminal", slot=self.open_terminal),
            button("Test connection", slot=self.app.test_connection)))
        self.conn = QLabel("Not tested yet")
        form.addRow("Connection", self.conn)
        self.app.directory.connection_changed.connect(
            lambda ok, t: self.conn.setText(f"✔ Connected to {t}" if ok else f"✖ Not connected – {t}"))
        lay.addWidget(box)

        # ---- domain profiles ----
        box, form = self.group("Domains (profiles)")
        self._admin_only.append(box)
        form.addRow(_muted("Manage more than one Google Workspace domain? Give each its own "
                           "GAM config folder (run the Setup wizard with a new folder), or a "
                           "section name from gam.cfg. Switch with the Domain box at the top."))
        self.prof_table = QLabel("")
        self.prof_table.setWordWrap(True)
        form.addRow("Profiles", self.prof_table)
        self.p_name = QLineEdit(placeholderText="e.g. Hancock Staff, Test domain")
        self.p_dir = QLineEdit(placeholderText="GAM config folder for this domain")
        self.p_sec = QLineEdit(placeholderText="Optional gam.cfg section name")
        form.addRow("Name", self.p_name)
        form.addRow("Config folder", self.row(self.p_dir, button(
            "Browse…", slot=lambda: self._browse(self.p_dir, save=False)), stretch=False))
        form.addRow("gam.cfg section", self.p_sec)
        form.addRow("", self.row(button("Save profile", slot=self.save_profile),
                                 button("Remove profile", "danger", self.remove_profile)))
        lay.addWidget(box)
        self._profiles_text()

        # ---- appearance & safety ----
        box, form = self.group("Appearance and safety")
        self.text_size = QComboBox()
        for label, val in (("Small", 0.9), ("Normal", 1.0), ("Large", 1.15),
                           ("Extra large", 1.3)):
            self.text_size.addItem(label, val)
        cur = float(settings.get("ui/text_scale", 1.0) or 1.0)
        self.text_size.setCurrentIndex(min(range(4), key=lambda i: abs(
            self.text_size.itemData(i) - cur)))
        self.text_size.currentIndexChanged.connect(
            lambda _i: self.app.set_text_scale(self.text_size.currentData()))
        form.addRow("Text size", self.row(self.text_size, QLabel(
            "Changes right away; restart GAMbit if anything looks cramped.",
            objectName="Muted")))
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 100000)
        self.threshold.setSpecialValueText("Never ask")
        self.threshold.setValue(int(team.setting("safety/threshold", 10) or 0))
        self.threshold.valueChanged.connect(lambda v: team.set_setting("safety/threshold", v))
        form.addRow("Ask before changing more than", self.row(self.threshold,
                                                               QLabel("accounts at once")))
        self.adv = QCheckBox("Show advanced pages (Command Builder, Console, Bulk, More "
                             "services, Policies, Live test)")
        self.adv.setChecked(bool(settings.get("ui/show_advanced", True)))
        self.adv.toggled.connect(lambda on: (settings.set("ui/show_advanced", on),
                                             self.app.apply_role()))
        form.addRow("Sidebar", self.adv)
        form.addRow("", _muted("Right-click any page in the sidebar to hide it, or to show "
                               "everything again."))
        self.tips = QCheckBox("Show a short tip at the top of each page, with “Try it "
                              "safely”")
        self.tips.setChecked(bool(settings.get("ui/page_help", True)))
        self.tips.toggled.connect(lambda on: (settings.set("ui/page_help", on), [
            p.refresh_help() for p in self.app.pages.values()]))
        form.addRow("Page tips", self.tips)
        form.addRow("", self.row(button("Keyboard shortcuts (Shift+F1)", slot=self.app.show_help),
                                 button("Take the tour", slot=self.app.start_tour),
                                 button("Report a problem…", slot=self._report_problem)))
        lay.addWidget(box)

        # ---- testing ----
        box, form = self.group("Testing")
        self._admin_only.append(box)
        form.addRow(_muted("Try new workflows and roster sync safely: a test org unit and one "
                           "test account. Roster sync's Test mode only touches the test org "
                           "unit, and Workflows can fill in the test account for you. "
                           "🧪 Dry run (top bar) shows the GAM commands without running "
                           "them."))
        from ..pickers import OUField
        self.test_ou = OUField(self.app.directory, "/GAMbit Test")
        self.test_ou.set_path(settings.get("safety/test_ou", "") or "")
        self.test_user = QLineEdit(settings.get("safety/test_user", "") or "")
        self.test_user.setPlaceholderText("e.g. gambit.test@yourschool.org")
        form.addRow("Test org unit", self.test_ou)
        form.addRow("Test account", self.test_user)
        form.addRow("", self.row(button("Save", slot=self._save_testing),
                                 button("Create the test org unit and account",
                                        slot=self._create_testing)))
        lay.addWidget(box)

        # ---- help-desk mode ----
        box, form = self.group("Help-desk mode")
        form.addRow(_muted("Hand GAMbit to aides or office staff safely: delete, wipe, "
                           "suspend and other destructive actions are hidden and blocked, and "
                           "advanced pages are hidden. Leaving help-desk mode needs a PIN."))
        form.addRow("", self.row(button("Turn on help-desk mode…", slot=self.app.enter_helpdesk)))
        lay.addWidget(box)

        # ---- team ----
        box, form = self.group("Team")
        form.addRow(_muted("A folder every tech can reach (mapped drive, file share, or a "
                           "Google Drive for desktop folder). It holds custom roles, approval "
                           "requests, shared Command Builder templates, shared workflow "
                           "settings and the team activity log."))
        self.team_dir = QLineEdit(team.folder())
        self.team_dir.setPlaceholderText(r"e.g. G:\Shared drives\Tech\GAMbit")
        self.team_browse = button("Browse…", slot=self._browse_team)
        self.team_save = button("Save", slot=self._save_team)
        form.addRow("Team folder", self.row(self.team_dir, self.team_browse, self.team_save,
                                            stretch=False))
        self.share_settings = QCheckBox("Share workflow settings with the team (leaving OU, "
                                        "rollover steps, signature, big-change limit)")
        self.share_settings.setChecked(bool(settings.get("team/share_settings", True)))
        self.share_settings.toggled.connect(lambda on: settings.set("team/share_settings", on))
        form.addRow("", self.share_settings)
        self.my_role = QLabel("")
        form.addRow("You", self.my_role)
        self.roles_btn = button("Manage roles…", slot=self.manage_roles)
        self.access_btn = button("Users && access (sign-in)…", "primary",
                                 slot=lambda: self.app.open_access())
        self.access_btn.setToolTip("Require Google sign-in for GAMbit, choose who can use it, "
                                   "their roles and org units.")
        form.addRow("", self.row(self.roles_btn, self.access_btn))
        lay.addWidget(box)
        self._team_text()

        # ---- Google Sheets and email ----
        box, form = self.group("Google Sheets and email")
        self._admin_only.append(box)
        form.addRow(_muted("GAMbit uses this Google account to read roster sheets, create "
                           "sheets from tables, and send report and alert emails. It needs a "
                           "Gmail mailbox and access to the sheets you use."))
        from ... import google_io
        self.g_user = QLineEdit(google_io.admin_email())
        self.g_user.setPlaceholderText("admin@yourschool.org")
        self.g_user.editingFinished.connect(
            lambda: google_io.set_admin_email(self.g_user.text()))
        form.addRow("Google account", self.row(
            self.g_user, button("Detect", slot=self._detect_google), stretch=False))
        self.alert_to = QLineEdit(settings.get("alerts/email", "") or "")
        self.alert_to.setPlaceholderText("Where failure alerts go, e.g. tech@yourschool.org")
        self.alert_to.editingFinished.connect(
            lambda: settings.set("alerts/email", self.alert_to.text().strip()))
        form.addRow("Send alerts to", self.row(
            self.alert_to, button("Send a test email", slot=self._test_email), stretch=False))
        from ... import alerts
        self.webhook = QLineEdit(alerts.webhook_url())
        self.webhook.setPlaceholderText("Optional Teams / Slack / Google Chat incoming-webhook "
                                        "URL for alerts")
        self.webhook.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.webhook.editingFinished.connect(
            lambda: settings.set("alerts/webhook", self.webhook.text().strip()))
        form.addRow("Chat alerts", self.row(
            self.webhook, button("Send a test message", slot=self._test_webhook),
            stretch=False))
        self.chat_space = QLineEdit(settings.get("alerts/chat_space", "") or "")
        self.chat_space.setPlaceholderText("Google Chat space link or spaces/AAAA… (optional)")
        self.chat_space.editingFinished.connect(
            lambda: settings.set("alerts/chat_space", self.chat_space.text().strip()))
        self.chat_user = QLineEdit(settings.get("alerts/chat_user", "") or "")
        self.chat_user.setPlaceholderText("posted as (a member of the space)")
        self.chat_user.editingFinished.connect(
            lambda: settings.set("alerts/chat_user", self.chat_user.text().strip()))
        form.addRow("Google Chat space", self.row(
            self.chat_space, self.chat_user, button("Test", slot=self._test_chat),
            stretch=False))
        self.digest_to = QLineEdit(settings.get("digest/to", "") or "")
        self.digest_to.setPlaceholderText("Weekly digest to, e.g. tech@yourschool.org")
        self.digest_to.editingFinished.connect(
            lambda: settings.set("digest/to", self.digest_to.text().strip()))
        form.addRow("Weekly digest", self.row(
            self.digest_to, button("Send now", slot=self._digest_now),
            button("Every Monday…", slot=self._digest_schedule), stretch=False))
        form.addRow("", _muted("Teams: in the channel choose ⋯ → Workflows → “Post to a channel "
                               "when a webhook request is received”. Slack: an Incoming "
                               "Webhook app. Google Chat: space → Apps & integrations → "
                               "Webhooks. Alerts go out when a scheduled job, roster sync or "
                               "background task fails."))
        lay.addWidget(box)

        # ---- integrations ----
        from ..integrations_box import integrations_box
        lay.addWidget(integrations_box(self))

        # ---- rolling out ----
        box, form = self.group("Rolling out to the team")
        self._admin_only.append(box)
        form.addRow(_muted("Set up one PC, then hand the same settings to everyone: make a "
                           "deployment file, put it next to the installer, and install "
                           "silently (Intune, a login script or by hand). Back up this PC "
                           "before it's replaced."))
        form.addRow("", self.row(button("Make a deployment file…", slot=self._make_deploy),
                                 button("Back up settings…", slot=self._backup),
                                 button("Restore settings…", slot=self._restore)))
        cmd = QLineEdit("GAMbit-Setup-x.y.z.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART "
                        "/NOLAUNCH")
        cmd.setReadOnly(True)
        form.addRow("Silent install", cmd)
        form.addRow(_muted("Shared Google project: keep client_secrets.json and "
                           "oauth2service.json in a folder only techs can open. Each PC "
                           "points GAM at them and each person signs GAM in with their own "
                           "admin account – so their Google admin role limits what they can "
                           "change in the directory."))
        self.shared_proj = QLineEdit(settings.get("deploy/shared_project", "") or "")
        self.shared_proj.setPlaceholderText(r"e.g. \\server\tech$\GAM project")
        form.addRow("Shared project folder", self.row(
            self.shared_proj, button("Browse…", slot=lambda: self._browse(
                self.shared_proj, save=False)), stretch=False))
        form.addRow("", self.row(button("Share this PC's Google project", slot=self._publish_proj),
                                 button("Use the shared project on this PC…",
                                        slot=self._use_proj)))
        lay.addWidget(box)

        # ---- org unit map ----
        box, form = self.group("Org units & schools")
        self._admin_only.append(box)
        form.addRow(_muted("Tell GAMbit which org units hold students, staff, Chromebooks, "
                           "loaners and repairs, which school each belongs to and which "
                           "grade. Student lookup, Assigned users, Assignment sync and the "
                           "Helper use it."))
        self.oumap_lbl = QLabel("")
        self.oumap_lbl.setWordWrap(True)
        form.addRow("Now", self.oumap_lbl)
        form.addRow("", self.row(button("Set up org units & schools…", "primary",
                                        self.open_ou_map)))
        self._oumap_text()
        lay.addWidget(box)

        # ---- cached lists ----
        box, form = self.group("Org units, users and groups")
        form.addRow(_muted("GAMbit keeps a copy of these lists so you can pick from them "
                           "instead of typing. They refresh automatically once a day."))
        self.lists = QLabel("")
        form.addRow("Last loaded", self.lists)
        form.addRow("", self.row(button("Refresh lists now", slot=self.refresh_lists)))
        d = self.app.directory
        for sig in (d.ous_changed, d.users_changed, d.groups_changed):
            sig.connect(self._lists_text)
        self._lists_text()
        lay.addWidget(box)

        # ---- GAM updates ----
        box, form = self.group("GAM (command-line tool)")
        self._admin_only.append(box)
        self.gam_installed = QLabel("Checking…")
        self.gam_latest = QLabel("—")
        form.addRow("Installed version", self.gam_installed)
        form.addRow("Latest version", self.gam_latest)
        self.gam_install_btn = button("Install GAM", "primary", self.install_gam)
        self.gam_install_btn.setEnabled(False)
        form.addRow("", self.row(button("Check for GAM updates", slot=self.check_gam),
                                 self.gam_install_btn,
                                 button("Release notes", slot=self._gam_notes)))
        self.gam_progress = QProgressBar()
        self.gam_progress.hide()
        form.addRow("", self.gam_progress)
        lay.addWidget(box)

        # ---- GAMbit updates ----
        box, form = self.group(f"{APP_NAME} (this app)")
        form.addRow("Installed version", QLabel(__version__))
        self.channel = QComboBox()
        self.channel.addItem("Stable – the normal releases", "stable")
        self.channel.addItem("Beta – try new versions first (for testers)", "beta")
        self.channel.setCurrentIndex(1 if updaters.update_channel() == "beta" else 0)
        self.channel.currentIndexChanged.connect(
            lambda _i: settings.set("update/channel", self.channel.currentData()))
        form.addRow("Update channel", self.row(self.channel))
        self.app_status = QLabel("Not checked yet")
        self.app_status.setWordWrap(True)
        form.addRow("Status", self.app_status)
        self.app_notes = QLabel("")
        self.app_notes.setWordWrap(True)
        self.app_notes.setObjectName("Muted")
        form.addRow("", self.app_notes)
        self.app_install_btn = button("Download && install update", "primary",
                                      self.install_app_update)
        self.app_install_btn.setEnabled(False)
        form.addRow("", self.row(button(f"Check for {APP_NAME} updates",
                                        slot=lambda: self.check_app(True)),
                                 self.app_install_btn,
                                 button("GitHub project", slot=lambda: QDesktopServices.openUrl(
                                     QUrl(f"https://github.com/{GITHUB_REPO}")))))
        self.app_progress = QProgressBar()
        self.app_progress.hide()
        form.addRow("", self.app_progress)
        self.on_start = QCheckBox("Check for updates when GAMbit starts")
        self.on_start.setChecked(settings.check_updates_on_start)
        self.on_start.toggled.connect(
            lambda v: setattr(settings, "check_updates_on_start", v))
        form.addRow("", self.on_start)
        prev = updaters.rollback_target()
        self.rollback_btn = button(f"Go back to version {prev}" if prev else
                                   "Go back to the previous version", slot=self.rollback)
        self.rollback_btn.setEnabled(bool(prev))
        form.addRow("", self.row(self.rollback_btn,
                                 button("Restore settings from a backup…",
                                        slot=self.restore_update_backup)))
        self.auto_rb = QCheckBox("Release check: if something that worked before an update "
                                 "fails afterwards, go back automatically")
        self.auto_rb.setChecked(bool(settings.get("release/auto_rollback", False)))
        self.auto_rb.toggled.connect(lambda v: settings.set("release/auto_rollback", v))
        form.addRow("", self.auto_rb)
        form.addRow("", self.row(button("Run the release check now",
                                        slot=self._release_check_now)))
        form.addRow("", _muted("Before every update GAMbit saves a backup of its settings (with "
                               "passwords and keys) in AppData\\GAMbit\\backups. If an "
                               "update misbehaves, go back with one click."))
        lay.addWidget(box)
        lay.addStretch(1)

    def on_show(self):
        self.refresh_installed()
        self._lists_text()

    def _profiles_text(self):
        from ... import profiles
        cur = profiles.current_name()
        lines = []
        for p in profiles.profiles():
            mark = "● " if p["name"] == cur else "○ "
            extra = p.get("cfg_dir") or "GAM's default folder"
            if p.get("section"):
                extra += f" · section {p['section']}"
            lines.append(f"{mark}<b>{p['name']}</b> – {extra}")
        self.prof_table.setText("<br>".join(lines))

    def save_profile(self):
        from ... import profiles
        name = self.p_name.text().strip()
        if not name:
            self.info("Give the profile a name.")
            return
        profiles.save_profile(name, self.p_dir.text().strip(), self.p_sec.text().strip())
        self._profiles_text()
        self.app.refresh_profiles()
        self.info(f"Saved “{name}”. Pick it from the Domain box at the top to switch.")

    def remove_profile(self):
        from ... import profiles
        name = self.p_name.text().strip() or profiles.current_name()
        if len(profiles.profiles()) <= 1:
            self.info("You need at least one profile.")
            return
        if self.confirm(f"Remove the profile “{name}”? (GAM's files are not deleted.)"):
            profiles.remove_profile(name)
            self._profiles_text()
            self.app.refresh_profiles()

    def _lists_text(self):
        d = self.app.directory
        self.lists.setText(f"{len(d.ous)} org units ({d.age_text('org units')}) · "
                           f"{len(d.users)} users ({d.age_text('users')}) · "
                           f"{len(d.groups)} groups ({d.age_text('groups')})")

    def refresh_lists(self):
        d = self.app.directory
        d.refresh_ous(log=self.app.log_line)
        d.refresh_users(log=self.app.log_line)
        d.refresh_groups(log=self.app.log_line)

    # ------------------------------------------------------------ dirs ---
    def _report_problem(self):
        from ... import support
        support.ask_and_save(self, output_text=self.app.log.toPlainText())

    # ---- rolling out ----
    def _make_deploy(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout as V
        from ... import deploy
        dlg = QDialog(self)
        dlg.setWindowTitle("Make a deployment file")
        v = V(dlg)
        v.addWidget(QLabel("Copy these settings from this PC to every PC that installs "
                           "with the file:"))
        boxes = {}
        for key, (label, _keys) in deploy.GROUPS.items():
            cb = QCheckBox(label)
            cb.setChecked(key not in ("helpdesk", "roster"))
            boxes[key] = cb
            v.addWidget(cb)
        over = QCheckBox("Replace settings people have already changed (otherwise only fill "
                         "in what's empty)")
        v.addWidget(over)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if not dlg.exec():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save deployment file",
                                              "gambit-deploy.json", "JSON (*.json)")
        if not path:
            return
        deploy.write_deploy(path, [k for k, cb in boxes.items() if cb.isChecked()],
                            over.isChecked())
        self.info("Saved. Put gambit-deploy.json in the same folder as GAMbit-Setup.exe and "
                  "install with:\n\nGAMbit-Setup-x.y.z.exe /VERYSILENT /SUPPRESSMSGBOXES "
                  "/NORESTART /NOLAUNCH\n\nOr copy it to %ProgramData%\\GAMbit\\ or "
                  "<team folder>\\deploy\\ – GAMbit picks it up when it starts.\n\n"
                  "Each PC still signs GAM in once (Setup wizard), unless you copy the GAM "
                  "config folder too.")

    def _backup(self):
        from ... import deploy
        path, _ = QFileDialog.getSaveFileName(self, "Back up GAMbit settings",
                                              "gambit-backup.zip", "Zip (*.zip)")
        if not path:
            return
        secrets = QMessageBox.question(
            self, "Back up", "Include secrets (webhook URL, help-desk PIN hash)? Choose No "
            "if the backup will be stored somewhere others can read.") == QMessageBox.Yes
        deploy.backup(path, secrets)
        self.info(f"Backed up to {path}.")

    def _restore(self):
        from ... import deploy
        path, _ = QFileDialog.getOpenFileName(self, "Restore GAMbit settings", "",
                                              "Zip (*.zip)")
        if not path:
            return
        replace = QMessageBox.question(
            self, "Restore", "Replace settings that are already set on this PC? Choose No "
            "to only fill in what's missing.") == QMessageBox.Yes
        try:
            n, f = deploy.restore(path, replace)
        except Exception as exc:  # noqa: BLE001
            self.info(f"Couldn't restore:\n{exc}")
            return
        self.info(f"Restored {n} setting(s) and {f} file(s). Restart GAMbit to see "
                  "everything.")

    def _publish_proj(self):
        from ... import deploy
        d = self.shared_proj.text().strip()
        if not d:
            self.info("Choose the shared folder first.")
            return
        if not self.confirm("Copy this PC's client_secrets.json and oauth2service.json to "
                            f"{d}?\n\noauth2service.json is a key to your domain's data – "
                            "only tech staff should be able to open that folder."):
            return
        try:
            done = deploy.publish_project(d)
        except Exception as exc:  # noqa: BLE001
            self.info(str(exc))
            return
        settings.set("deploy/shared_project", d)
        self.info("Copied " + ", ".join(done) + ". On other PCs choose “Use the shared "
                  "project on this PC”.")

    def _use_proj(self):
        from ... import deploy, gam_setup
        d = self.shared_proj.text().strip()
        if not d:
            self.info("Choose the shared folder first.")
            return
        local = settings.gam_cfg_dir or gam_setup.default_cfg_dir()
        if not self.confirm(f"Use the Google project in {d}?\n\nThis PC's GAM settings stay "
                            f"in {local}. Next you'll sign GAM in with your own admin "
                            "account."):
            return
        try:
            notes = deploy.use_shared_project(d, local, settings.get("gam/admin", "") or "")
        except Exception as exc:  # noqa: BLE001
            self.info(str(exc))
            return
        self.cfg_dir.setText(settings.gam_cfg_dir)
        self.info("\n".join(notes) + "\n\nNow sign GAM in: Setup wizard → “Sign GAM in”.")
        self.app.open_setup()

    # ---- testing ----
    def _save_testing(self):
        settings.set("safety/test_ou", self.test_ou.path().strip())
        settings.set("safety/test_user", self.test_user.text().strip())

    def _create_testing(self):
        self._save_testing()
        ou, user = self.test_ou.path().strip(), self.test_user.text().strip()
        if not ou or "@" not in user:
            self.info("Type the test org unit (e.g. /GAMbit Test) and a test account email.")
            return
        from .users import random_password
        cmds = []
        if ou not in self.app.directory.ous:
            cmds.append(["create", "ou", ou])
        if not any(u["email"].lower() == user.lower() for u in self.app.directory.users):
            cmds.append(["create", "user", user, "firstname", "GAMbit", "lastname", "Test",
                         "password", random_password(16), "ou", ou])
        if not cmds:
            self.info("The test org unit and account already exist.")
            return
        self.run_many(cmds, lambda *_: (self.app.directory.refresh_ous(),
                                        self.app.directory.refresh_users()))

    # ---- team ----
    def _team_text(self):
        from ...auth import session as _s
        signed_user = _s.active() and not team.is_admin()
        for box in getattr(self, "_admin_only", []):
            box.setEnabled(not signed_user)
            box.setToolTip("Only GAMbit admins can change this." if signed_user else "")
        locked = (bool(team.folder()) or _s.active()) and not team.is_admin()
        for w in (self.team_dir, self.team_browse, self.team_save, self.share_settings):
            w.setEnabled(not locked)
        self.roles_btn.setEnabled(bool(team.folder()) and team.is_admin())
        self.access_btn.setEnabled(team.is_admin())
        if team.folder():
            self.my_role.setText(f"<b>{team.me()}</b> – {team.my_role_name()}"
                                 + ("" if not locked else " (only a Full admin can change the "
                                    "team settings)"))
        else:
            self.my_role.setText(f"<b>{team.me()}</b> – no team folder yet, so everyone is a "
                                 "Full admin")

    def _browse_team(self):
        from PySide6.QtWidgets import QFileDialog as FD
        d = FD.getExistingDirectory(self, "Team folder", self.team_dir.text())
        if d:
            self.team_dir.setText(os.path.normpath(d))
            self._save_team()

    def _save_team(self):
        path = self.team_dir.text().strip()
        if path and not os.path.isdir(path):
            try:
                os.makedirs(path, exist_ok=True)
            except OSError as exc:
                self.info(f"Can't use that folder:\n{exc}")
                return
        settings.set("team/folder", path)
        self._team_text()
        self.app.apply_role()
        self.app.update_approvals_badge()
        if path:
            self.info("Saved. Roles, approvals, shared templates and the team activity log "
                      "now use that folder. Set the same folder on each tech's PC.")

    def manage_roles(self):
        from ..main_window import PAGES
        from ..roles_dialog import RolesDialog
        wf = self.app.pages.get("Workflows")
        tabs = [wf.tabs.tabText(i) for i in range(wf.tabs.count())] if wf else []
        if RolesDialog(self, [n for n, _ in PAGES], tabs).exec():
            self._team_text()
            self.app.apply_role()

    # ---- google ----
    def _detect_google(self):
        from ... import google_io
        Worker(google_io.detect_admin_email,
               on_done=lambda e: (self.g_user.setText(e), google_io.set_admin_email(e))
               if e else self.info("GAM didn't say which account it uses – type it in."),
               on_error=lambda e: self.info(str(e)))

    def _digest_now(self):
        from ... import digest
        settings.set("digest/to", self.digest_to.text().strip())
        Worker(digest.send, self.digest_to.text().strip(),
               on_done=lambda subj: self.info(f"Sent: {subj}"),
               on_error=lambda e: self.info(str(e)))

    def _digest_schedule(self):
        from ... import scheduler
        settings.set("digest/to", self.digest_to.text().strip())
        if "@" not in self.digest_to.text():
            self.info("Type who gets the digest first.")
            return
        try:
            script = scheduler.build_app_task_script("GAMbit weekly digest",
                                                     ["--task", "digest"])
            scheduler.create_task("GAMbit weekly digest", script, "weekly", "07:10", "MON")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Couldn't schedule it:\n{exc}")
            return
        self.info("The digest will be emailed every Monday at 7:10 AM.")

    def _test_webhook(self):
        from ... import alerts
        url = self.webhook.text().strip()
        settings.set("alerts/webhook", url)
        if not url:
            self.info("Paste the webhook URL first.")
            return
        Worker(alerts.post_webhook, "This is a test alert from GAMbit. ✔", "GAMbit test", url,
               on_done=lambda _r: self.info(f"Sent a test message ({alerts.kind(url)})."),
               on_error=lambda e: self.info(f"Couldn't post to the webhook:\n{e}"))

    def _test_chat(self):
        from ... import alerts
        settings.set("alerts/chat_space", self.chat_space.text().strip())
        settings.set("alerts/chat_user", self.chat_user.text().strip())
        Worker(alerts.post_chat, "This is a test alert from GAMbit. ✔", "GAMbit test",
               on_done=lambda _r: self.info("Posted to the Chat space."),
               on_error=lambda e: self.info(f"Couldn't post to Chat:\n{e}\n\nThe person "
                                            "must be a member of the space, and GAM needs "
                                            "the Chat scopes for user access."))

    def _test_email(self):
        from ... import google_io
        to = self.alert_to.text().strip() or self.g_user.text().strip()
        if "@" not in to:
            self.info("Type an email address first.")
            return
        settings.set("alerts/email", self.alert_to.text().strip())
        google_io.set_admin_email(self.g_user.text())
        Worker(google_io.send_email, to, "GAMbit test email",
               "This is a test from GAMbit. Report and alert emails will look like this.",
               on_done=lambda _r: self.info(f"Sent a test email to {to}."),
               on_error=lambda e: self.info(str(e)))

    def _save_dirs(self):
        from ... import profiles
        settings.gam_dir = self.gam_dir.text().strip()
        settings.gam_cfg_dir = self.cfg_dir.text().strip()
        profiles.sync_current_from_settings()
        if hasattr(self, "prof_table"):
            self._profiles_text()
        self.refresh_installed()

    def _browse(self, edit: QLineEdit, save: bool = True):
        d = QFileDialog.getExistingDirectory(self, "Choose folder", edit.text())
        if d:
            edit.setText(os.path.normpath(d))
            if save:
                self._save_dirs()

    @staticmethod
    def _open(path):
        if os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_terminal(self):
        """Open a real console in the GAM folder for first-time setup."""
        gdir = settings.gam_dir
        if not os.path.isdir(gdir):
            self.info("Install GAM first (below), then open the setup terminal.")
            return
        steps = ("GAM first-time setup:  1) gam create project   "
                 "2) gam oauth create   3) gam user YOUR_ADMIN@domain check serviceaccount")
        if IS_WINDOWS:
            subprocess.Popen(["cmd.exe", "/K", f'cd /d "{gdir}" && echo {steps}'],
                             env=gam_environment(),
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            self.info(f"Open a terminal in {gdir} and run:\n\n" + steps.replace("   ", "\n"))

    # ------------------------------------------------------------- GAM ---
    def refresh_installed(self):
        self.gam_installed.setText("Checking…")
        Worker(gam_version_text, on_done=self._got_installed,
               on_error=lambda e: self.gam_installed.setText("Not found"))

    def _got_installed(self, ver):
        self.installed_version = ver
        self.gam_installed.setText(ver or "Not installed / not found")
        self.app.set_gam_version(ver)
        self._update_gam_button()

    def check_gam(self, quiet=False):
        self.gam_latest.setText("Checking GitHub…")
        Worker(updaters.latest_gam_release, on_done=self._got_gam_release,
               on_error=lambda e: (self.gam_latest.setText("Could not check"),
                                   None if quiet else self.info(f"Could not check for GAM updates:\n{e}")))

    def _got_gam_release(self, rel):
        self.gam_release = rel
        self.gam_latest.setText(f"{rel.version}   ({rel.asset_name})")
        self._update_gam_button()

    def _update_gam_button(self):
        installed = getattr(self, "installed_version", None)
        rel = self.gam_release
        if not installed:
            self.gam_install_btn.setText("Install GAM")
            self.gam_install_btn.setEnabled(rel is not None)
        elif rel and is_newer(rel.version, installed):
            self.gam_install_btn.setText(f"Update GAM to {rel.version}")
            self.gam_install_btn.setEnabled(True)
            self.app.notify(f"GAM {rel.version} is available")
        else:
            self.gam_install_btn.setText("GAM is up to date")
            self.gam_install_btn.setEnabled(False)

    def _gam_notes(self):
        url = self.gam_release.notes_url if self.gam_release else \
            "https://github.com/GAM-team/GAM/releases"
        QDesktopServices.openUrl(QUrl(url))

    def install_gam(self):
        if not self.gam_release:
            return
        if self.runner.busy:
            self.info("GAMbit is still running GAM commands – wait for them to finish (see "
                      "the Jobs tab), then update.")
            return
        target = settings.gam_dir
        if not self.confirm(f"Download GAM {self.gam_release.version} and install it into\n"
                            f"{target}?\n\nYour GAM settings and credentials are kept."):
            return
        self.gam_install_btn.setEnabled(False)
        self.gam_progress.setValue(0)
        self.gam_progress.show()
        Worker(updaters.install_gam, self.gam_release, target,
               use_progress=True, use_log=True,
               on_progress=lambda d, t: self._progress(self.gam_progress, d, t),
               on_message=lambda m: self.app.log_line(m),
               on_done=self._gam_installed, on_error=self._gam_failed)

    def _gam_installed(self, _exe):
        self.gam_progress.hide()
        self.info(f"GAM {self.gam_release.version} is installed.")
        self.refresh_installed()
        # Keep the Command Builder's command list in step with the new GAM
        from ...command_catalog import download

        def refreshed(_ref):
            b = self.app.pages.get("Command Builder")
            if b is not None:
                b.catalog = None   # reloads next time the page opens
            self.app.log_line(f"Command Builder updated for GAM {self.gam_release.version}.")
        Worker(download, self.gam_release.version, on_done=refreshed,
               on_error=lambda e: self.app.log_line(f"Command list not updated: {e}"))

    def _gam_failed(self, err):
        self.gam_progress.hide()
        self._update_gam_button()
        msg = str(err)
        if "WinError 32" in msg or "being used by another process" in msg:
            msg += ("\n\nAnother program has a GAM file open – usually a GAMbit background "
                    "task, a Command Prompt/PowerShell window running gam, or an antivirus "
                    "scan of the new download. Wait a minute (or close it) and click Update "
                    "again.")
        elif "Permission" in msg or "Access is denied" in msg:
            msg += ("\n\nGAMbit could not write to the GAM folder. Close any window "
                    "running GAM, or choose a folder you can write to.")
        QMessageBox.warning(self, "GAM install failed", msg)

    @staticmethod
    def _progress(bar: QProgressBar, done: int, total: int):
        if total:
            bar.setMaximum(100)
            bar.setValue(int(done * 100 / total))
            bar.setFormat(f"{done / 1e6:.1f} of {total / 1e6:.1f} MB")
        else:
            bar.setMaximum(0)

    # ---------------------------------------------------------- GAMbit ---
    def check_app(self, interactive=False):
        self.app_status.setText("Checking…")

        def failed(e):
            self.app_status.setText("Could not check for updates.")
            if interactive:
                self.info(f"Could not check for {APP_NAME} updates:\n{e}")

        Worker(updaters.check_app_update, on_done=lambda u: self._got_app(u, interactive),
               on_error=failed)

    def _got_app(self, update, interactive):
        self.app_update = update
        if not update:
            self.app_status.setText(f"You have the latest version ({__version__}).")
            self.app_notes.setText("")
            self.app_install_btn.setEnabled(False)
            if interactive:
                self.info(f"{APP_NAME} is up to date.")
            return
        self.app_status.setText(f"Version {update.version} is available.")
        self.app_notes.setText(update.notes)
        self.app_install_btn.setEnabled(True)
        self.app.notify(f"{APP_NAME} {update.version} is available")
        if interactive or settings.check_updates_on_start:
            ask = QMessageBox.question(
                self, "Update available",
                f"{APP_NAME} {update.version} is available (you have {__version__}).\n\n"
                f"{update.notes}\n\nInstall it now?")
            if ask == QMessageBox.Yes:
                self.install_app_update()

    def install_app_update(self):
        if not self.app_update:
            return
        if not IS_WINDOWS:
            QDesktopServices.openUrl(QUrl(self.app_update.url))
            return
        self.app_install_btn.setEnabled(False)
        self.app_progress.setValue(0)
        self.app_progress.show()
        Worker(updaters.download_app_update, self.app_update, use_progress=True,
               on_progress=lambda d, t: self._progress(self.app_progress, d, t),
               on_done=self._app_downloaded,
               on_error=lambda e: (self.app_progress.hide(),
                                   self.app_install_btn.setEnabled(True),
                                   QMessageBox.warning(self, "Update failed", str(e))))

    def _release_check_now(self):
        from .round12_pages import release_check_dialog
        release_check_dialog(self)

    def rollback(self, ask: bool = True):
        ver = updaters.rollback_target()
        if not ver or (ask and not self.confirm(f"Download GAMbit {ver} and install it over "
                                                "this version? Your settings stay as they "
                                                "are.")):
            return
        self.app_progress.setValue(0)
        self.app_progress.show()

        def done(path):
            self.app_progress.hide()
            try:
                updaters.launch_installer(path)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Couldn't go back", str(exc))
                return
            from PySide6.QtWidgets import QApplication
            QApplication.instance().quit()
        Worker(updaters.download_previous, use_progress=True,
               on_progress=lambda d, t: self._progress(self.app_progress, d, t),
               on_done=done,
               on_error=lambda e: (self.app_progress.hide(),
                                   QMessageBox.warning(self, "Couldn't go back", str(e))))

    def restore_update_backup(self):
        from PySide6.QtWidgets import QFileDialog
        from ... import deploy
        path, _ = QFileDialog.getOpenFileName(self, "Settings backup", updaters.backups_dir(),
                                              "Backups (*.zip)")
        if path and self.confirm("Replace the current settings with the ones in this backup?"):
            n, f = deploy.restore(path, replace=True)
            self.info(f"Restored {n} setting(s) and {f} file(s). Restart GAMbit to finish.")

    def _app_downloaded(self, path):
        self.app_progress.hide()
        try:
            from ... import release_check
            from PySide6.QtCore import Qt as _Qt
            QApplication.setOverrideCursor(_Qt.WaitCursor)
            try:
                release_check.before_update(getattr(self.app_update, "version", ""))
            finally:
                QApplication.restoreOverrideCursor()
        except Exception:  # noqa: BLE001
            pass
        try:
            updaters.prepare_for_update(getattr(self.app_update, "version", ""))
        except Exception as exc:  # noqa: BLE001
            if QMessageBox.question(self, "Backup failed",
                                    f"Couldn't back up your settings first:\n{exc}\n\n"
                                    "Install the update anyway?") != QMessageBox.Yes:
                return
        try:
            updaters.launch_installer(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Update failed", str(exc))
            return
        QApplication.quit()
        sys.exit(0)

    def _oumap_text(self):
        from ... import ou_map
        ou_map.reload()
        if not ou_map.configured():
            self.oumap_lbl.setText("Not set up yet – GAMbit assumes students are under "
                                   "/Students.")
            return
        sch = ou_map.schools()
        self.oumap_lbl.setText(
            f"Students: {', '.join(ou_map.roots('students')) or '—'} · Staff: "
            f"{', '.join(ou_map.roots('staff')) or '—'} · Chromebooks: "
            f"{', '.join(ou_map.roots('devices')) or '—'} · {len(sch)} school(s)")

    def open_ou_map(self):
        from ..ou_map_dialog import OUMapDialog
        if OUMapDialog(self, self.app.directory).exec():
            self._oumap_text()
            self.app.statusBar().showMessage("Saved the org unit map.", 4000)
