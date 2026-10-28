"""Main-window side of GAMbit sign-in: the signed-in badge, idle lock, sign out, picking up
access-list changes while GAMbit is open, and the Users & access screen."""

from __future__ import annotations

import sys
import time

from PySide6.QtCore import QEvent, QObject, QProcess, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QToolButton

from ..auth import access, session


class _ActivityFilter(QObject):
    """Any key press or click counts as activity (resets the idle timer)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last = 0.0

    def eventFilter(self, _obj, ev):  # noqa: N802
        if ev.type() in (QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.Wheel):
            now = time.time()
            if now - self._last > 5:
                self._last = now
                session.touch()
        return False


class SessionActions:
    def install_session(self, topbar_layout):
        self.user_btn = QToolButton()
        self.user_btn.setPopupMode(QToolButton.InstantPopup)
        self.user_btn.setVisible(False)
        topbar_layout.addWidget(self.user_btn)

    def refresh_user_chip(self):
        """Avatar with initials and the first name; email and role in the tooltip/menu."""
        if not session.active():
            return
        from PySide6.QtCore import QSize
        from .home_widgets import avatar_pixmap
        from .person_header import initials
        from PySide6.QtGui import QIcon
        cur = session.current()
        email = cur.get("email", "")
        name = cur.get("name") or email.split("@")[0].replace(".", " ")
        first = (name.split() or [email])[0].title()
        self.user_btn.setIcon(QIcon(avatar_pixmap(initials(name, email), email, 28)))
        self.user_btn.setIconSize(QSize(28, 28))
        self.user_btn.setText(f" {first}")
        self.user_btn.setToolTip(f"{email} · {cur.get('role_name', '')}")
        self.user_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

    def start_session_ui(self):
        if not session.active():
            return
        cur = session.current()
        self.user_btn.setVisible(True)
        self.user_btn.setObjectName("UserChip")
        self.refresh_user_chip()
        m = QMenu(self.user_btn)
        who = m.addAction(f"{cur.get('email', '')}  ·  {cur.get('role_name', '')}")
        who.setEnabled(False)
        m.addSeparator()
        m.addAction("Lock GAMbit now", self.lock_now)
        m.addAction("Sign out", self.sign_out)
        if cur.get("role", {}).get("admin"):
            m.addSeparator()
            m.addAction("Users && access…", self.open_access)
        if session.scope():
            m.addSeparator()
            act = m.addAction("You look after: " + ", ".join(session.scope()))
            act.setEnabled(False)
        self.user_btn.setMenu(m)
        self.directory.apply_scope()
        self._apply_role_profile()
        if not hasattr(self, "_act_filter"):
            self._act_filter = _ActivityFilter(self)
            QApplication.instance().installEventFilter(self._act_filter)
            self._sess_timer = QTimer(self, interval=20 * 1000, timeout=self._session_tick)
            self._sess_timer.start()
            self._doc_timer = QTimer(self, interval=3 * 60 * 1000, timeout=self._reload_access)
            self._doc_timer.start()
        if cur.get("method") == "emergency":
            fixable = bool(access.local_signer(session.doc())) if session.doc() else False
            self.pages["Home"].show_banner(
                "You're signed in as the EMERGENCY ADMIN – this sign-in is logged. " +
                ("Fix Google sign-in (Users & access → Sign-in) and sign out as soon as you can."
                 if fixable else "This computer has no GAMbit admin key, so the access list "
                 "can't be changed here – fix Google sign-in from a GAMbit admin's computer."))

    def _apply_role_profile(self):
        """A role can tie people to a GAM profile (a gam.cfg section with a limited admin)."""
        from .. import profiles
        prof = (session.current().get("role") or {}).get("gam_profile", "")
        if prof:
            if prof in [p["name"] for p in profiles.profiles()]:
                if profiles.current_name() != prof:
                    self.switch_profile(prof)
            else:
                self.pages["Home"].show_banner(
                    f"Your GAMbit role uses the GAM profile “{prof}”, which isn't set up on "
                    "this computer, so GAMbit won't run GAM commands. Ask a GAMbit admin.")
            self.profile_box.setEnabled(False)
            self.profile_box.setToolTip("Your GAMbit role uses this GAM profile.")
        else:
            self.profile_box.setEnabled(True)
            self.profile_box.setToolTip("")

    def _session_tick(self):
        why = session.expired()
        if why:
            self.lock_now(why)

    def lock_now(self, why: str = ""):
        if getattr(self, "_locking", False) or not session.active():
            return
        self._locking = True
        from .login_dialog import relock
        cw = self.centralWidget()
        cw.setVisible(False)
        if why:
            self.statusBar().showMessage(f"GAMbit {why}.")
        try:
            ok = relock(self)
        finally:
            self._locking = False
        if not ok:
            session.end("closed GAMbit while locked")
            QApplication.instance().quit()
            return
        cw.setVisible(True)
        self._after_access_change()

    def sign_out(self):
        if QMessageBox.question(self, "Sign out", "Sign out of GAMbit? It will close and "
                                "open the sign-in window again.") != QMessageBox.Yes:
            return
        session.end("signed out")
        QProcess.startDetached(sys.executable, sys.argv[1:] if getattr(sys, "frozen", False)
                               else sys.argv)
        QApplication.instance().quit()

    def _reload_access(self):
        """Pick up role changes, or a removal, made by an admin while GAMbit is open."""
        if not session.active() or session.current().get("method") == "emergency":
            return
        try:
            doc = access.load()
        except access.AccessError as exc:
            session.log("access list problem while signed in", error=str(exc)[:200])
            self.log_line(f"⚠ {exc}", "#ff8a80")
            return
        session.set_doc(doc)
        p = access.person(doc, session.email())
        if p is None:
            session.end("removed by an admin")
            QMessageBox.information(self, "GAMbit", "A GAMbit admin has removed your access. "
                                    "GAMbit will close.")
            QApplication.instance().quit()
            return
        cur = session.current()
        if (p["role_name"], p["ous"], p["role"]) != (cur.get("role_name"), cur.get("ous"),
                                                     cur.get("role")):
            cur.update(role_name=p["role_name"], role=p["role"], ous=p["ous"])
            self._after_access_change()
            self.statusBar().showMessage(f"Your GAMbit access changed: {p['role_name']}", 8000)

    def _after_access_change(self):
        cur = session.current()
        p = access.person(session.doc(), cur.get("email", "")) if cur.get("method") != \
            "emergency" and session.doc() else None
        if p:
            cur.update(role_name=p["role_name"], role=p["role"], ous=p["ous"])
        self.start_session_ui()
        self.apply_helpdesk_mode()
        sp = self.pages.get("Settings & Updates")
        if sp is not None and hasattr(sp, "_team_text"):
            sp._team_text()

    def open_access(self):
        from .access_dialog import AccessDialog
        AccessDialog(self).exec()
        if session.active():
            self._after_access_change()
