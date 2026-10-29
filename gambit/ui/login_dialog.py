"""GAMbit sign-in: the window shown before GAMbit opens (and when it locks), the
first-time "trust this access list" check, and the emergency admin sign-in."""

from __future__ import annotations

import platform
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ..auth import access, local_admin, session
from ..auth.google_sso import sign_in
from .widgets import Worker


def emergency_person() -> dict:
    from .. import team
    return {"email": f"{local_admin.USER}@{platform.node().lower() or 'this-pc'}",
            "role_name": "Full admin", "role": team.BUILTIN_ROLES["Full admin"], "ous": [],
            "name": "Emergency admin"}


class TrustDialog(QDialog):
    """First time this PC sees the team's access list: check the admin's code."""

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trust this GAMbit access list?")
        v = QVBoxLayout(self)
        lab = QLabel(
            f"<h3>This team requires GAMbit sign-in</h3>"
            f"<p>The access list in the team folder was signed by <b>{info['email']}</b> "
            f"for <b>{info['domain']}</b>.</p>"
            f"<p>Before trusting it, check this code with your GAMbit admin (it's shown on "
            f"their Users &amp; access screen):</p>"
            f"<p style='font-size:20pt;font-family:Consolas,monospace'>"
            f"{info['fingerprint']}</p>"
            "<p>If the code doesn't match, choose <b>Don't trust</b> and tell your admin – "
            "someone may have replaced the file.</p>")
        lab.setWordWrap(True)
        v.addWidget(lab)
        h = QHBoxLayout()
        h.addStretch(1)
        no = QPushButton("Don't trust")
        no.clicked.connect(self.reject)
        yes = QPushButton("The code matches – trust it")
        yes.setProperty("kind", "primary")
        yes.clicked.connect(self.accept)
        h.addWidget(no)
        h.addWidget(yes)
        v.addLayout(h)


class LoginDialog(QDialog):
    def __init__(self, doc: dict | None, parent=None, lock_email: str = "",
                 problem: str = ""):
        super().__init__(parent)
        self.doc = doc or {}
        self.lock_email = lock_email
        self.person = None
        self._cancel = False
        self.setWindowTitle("Sign in to GAMbit")
        self.setMinimumWidth(460)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        v = QVBoxLayout(self)
        head = QLabel("<h2 style='margin:0'>GAMbit</h2>")
        v.addWidget(head)
        self.stack = QStackedWidget()
        v.addWidget(self.stack)
        # -------------------------------------------------- Google ---
        g = QWidget()
        gv = QVBoxLayout(g)
        dom = self.doc.get("domain", "")
        msg = (f"GAMbit locked for <b>{lock_email}</b>. Sign in again to continue."
               if lock_email else
               f"Sign in with your <b>@{dom}</b> Google account." if dom else
               "Sign in with your district Google account.")
        self.g_msg = QLabel(msg)
        self.g_msg.setWordWrap(True)
        gv.addWidget(self.g_msg)
        self.g_btn = QPushButton("  Sign in with Google  ")
        self.g_btn.setProperty("kind", "primary")
        self.g_btn.setMinimumHeight(40)
        self.g_btn.clicked.connect(self.google)
        gv.addWidget(self.g_btn)
        self.g_cancel = QPushButton("Cancel waiting for the browser")
        self.g_cancel.clicked.connect(self._stop)
        self.g_cancel.setVisible(False)
        gv.addWidget(self.g_cancel)
        self.status = QLabel(problem, objectName="Muted")
        self.status.setWordWrap(True)
        gv.addWidget(self.status)
        links = QHBoxLayout()
        self.em_link = QPushButton("Emergency admin sign-in…")
        self.em_link.setFlat(True)
        self.em_link.setVisible(local_admin.configured())
        self.em_link.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        links.addWidget(self.em_link)
        links.addStretch(1)
        quit_b = QPushButton("Quit")
        quit_b.clicked.connect(self.reject)
        links.addWidget(quit_b)
        gv.addLayout(links)
        self.stack.addWidget(g)
        # ----------------------------------------------- emergency ---
        e = QWidget()
        f = QFormLayout(e)
        note = QLabel("For when Google sign-in isn't working. Only works on this computer; "
                      "every use is logged and your GAMbit admins are alerted.")
        note.setWordWrap(True)
        f.addRow(note)
        self.e_user = QLineEdit(local_admin.USER)
        self.e_pw = QLineEdit()
        self.e_pw.setEchoMode(QLineEdit.Password)
        self.e_code = QLineEdit(placeholderText="6-digit code from the authenticator app")
        self.e_code.setMaxLength(7)
        self.e_code.returnPressed.connect(self.emergency)
        f.addRow("User name", self.e_user)
        f.addRow("Password", self.e_pw)
        f.addRow("Code", self.e_code)
        self.e_status = QLabel("", objectName="Muted")
        self.e_status.setWordWrap(True)
        f.addRow(self.e_status)
        row = QHBoxLayout()
        back = QPushButton("Back")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        go = QPushButton("Sign in")
        go.setProperty("kind", "primary")
        go.clicked.connect(self.emergency)
        row.addWidget(back)
        row.addStretch(1)
        row.addWidget(go)
        f.addRow(row)
        self.stack.addWidget(e)
        if not self.doc.get("google", {}).get("client_id"):
            self.g_btn.setEnabled(False)
            self.status.setText(problem or "Google sign-in isn't set up for this team yet.")

    # ------------------------------------------------------------ google ---
    def _stop(self):
        self._cancel = True

    def google(self):
        gcfg = self.doc.get("google", {})
        self._cancel = False
        self.g_btn.setEnabled(False)
        self.g_cancel.setVisible(True)
        self.status.setText("Finish signing in in your web browser…")

        def done(who):
            self.g_btn.setEnabled(True)
            self.g_cancel.setVisible(False)
            email = who["email"]
            if self.lock_email and email != self.lock_email.lower():
                self.status.setText(f"GAMbit is locked for {self.lock_email}. Sign in as that "
                                    "account, or quit and start GAMbit again to switch.")
                session.log("sign-in refused (different account while locked)", who=email)
                return
            p = access.person(self.doc, email)
            if p is None:
                session.log("sign-in refused (not allowed)", who=email)
                self.status.setText(f"{email} isn't allowed to use GAMbit. Ask a GAMbit "
                                    "admin to add you (Users & access).")
                return
            p["name"] = p.get("name") or who.get("name", "")
            self.person = (p, "google")
            self.accept()

        def failed(err):
            self.g_btn.setEnabled(True)
            self.g_cancel.setVisible(False)
            session.log("sign-in failed", who=self.lock_email, error=str(err)[:200])
            self.status.setText(str(err))
        Worker(sign_in, gcfg.get("client_id", ""), gcfg.get("client_secret", ""),
               self.doc.get("domain", ""), webbrowser.open, self.lock_email, 180,
               lambda: self._cancel, on_done=done, on_error=failed)

    # --------------------------------------------------------- emergency ---
    def emergency(self):
        try:
            ok = local_admin.check(self.e_user.text(), self.e_pw.text(), self.e_code.text(),
                                   local_admin.registered_fingerprint(self.doc))
        except ValueError as exc:
            self.e_status.setText(str(exc))
            return
        finally:
            self.e_pw.clear()
        if not ok:
            session.log("emergency sign-in FAILED", who=local_admin.USER)
            self.e_status.setText("That didn't work. After 5 wrong tries the emergency "
                                  "sign-in locks for 15 minutes or more.")
            self.e_code.clear()
            return
        p = emergency_person()
        if self.lock_email and self.lock_email != p["email"]:
            # the emergency admin may unlock anyone's locked window – it's logged
            session.log("emergency admin unlocked a locked session", who=p["email"],
                        locked=self.lock_email)
        self.person = (p, "emergency")
        try:
            from .. import alerts
            alerts.notify(f"The GAMbit emergency admin was used on {platform.node()}. If this "
                          "wasn't expected, check the sign-in log right away.",
                          "GAMbit emergency sign-in")
        except Exception:  # noqa: BLE001
            pass
        self.accept()

    def done(self, r):  # noqa: D401 – Quit, Esc, accept and close all end here
        self._cancel = True
        super().done(r)


def gate(parent=None) -> bool:
    """Before the main window: sign in if this PC/team requires it. False = quit."""
    if not access.required():
        session.set_doc(None)
        return True
    doc, problem = None, ""
    try:
        doc = access.load()
    except access.AccessError as exc:
        if str(exc) == "NOT_PINNED":
            try:
                info = access.first_look()
            except access.AccessError as e2:
                problem = str(e2)
            else:
                if TrustDialog(info, parent).exec() == QDialog.Accepted:
                    access.trust_first(info["doc"])
                    session.log("trusted the access list", who="",
                                fingerprint=info["fingerprint"])
                    try:
                        doc = access.load()
                    except access.AccessError as e3:
                        problem = str(e3)
                else:
                    return False
        else:
            problem = str(exc)
    if doc is None and not local_admin.configured():
        QMessageBox.critical(parent, "GAMbit sign-in",
                             f"{problem}\n\nGAMbit can't open until this is fixed.")
        return False
    dlg = LoginDialog(doc, parent, problem=problem)
    if dlg.exec() != QDialog.Accepted or not dlg.person:
        return False
    p, method = dlg.person
    session.set_doc(doc)
    session.start(p, method, doc)
    try:      # a personal signing key, so what this person asks for can be verified
        if doc:
            access.ask_key_if_needed(doc, session.email())
    except Exception:  # noqa: BLE001 – never block signing in over it
        pass
    return True


def relock(parent) -> bool:
    """The session timed out or the user locked GAMbit: sign in again as the same person."""
    who = session.email()
    session.log("locked")
    doc, problem = session.doc(), ""
    try:
        doc = access.load()
    except access.AccessError as exc:
        problem = str(exc)
    dlg = LoginDialog(doc, parent, lock_email=who, problem=problem)
    if dlg.exec() != QDialog.Accepted or not dlg.person:
        return False
    p, method = dlg.person
    session.set_doc(doc)
    session.start(p, method, doc)
    return True
