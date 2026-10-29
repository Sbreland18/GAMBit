"""Users & access: turn on GAMbit sign-in, choose who may sign in with which role and org
units, approve admin keys, set up the emergency admin and read the sign-in log."""

from __future__ import annotations

import copy
import datetime
import webbrowser

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .. import team
from ..auth import access, crypto, local_admin, session
from ..auth.google_sso import SignInError, sign_in
from .widgets import ResultsTable, Worker

SETUP_HELP = (
    "<b>One-time Google setup</b> (about 5 minutes, in the Google Cloud project GAM uses or a "
    "new one):<ol>"
    "<li>Open <i>console.cloud.google.com → APIs &amp; Services → OAuth consent screen</i>. "
    "Choose <b>Internal</b> (only your district's accounts), app name “GAMbit”, and only the "
    "<i>openid, email, profile</i> scopes.</li>"
    "<li><i>Credentials → Create credentials → OAuth client ID</i>, application type "
    "<b>Desktop app</b>, name “GAMbit sign-in”.</li>"
    "<li>Copy the <b>Client ID</b> and <b>Client secret</b> here. (Google treats a desktop "
    "app's secret as public; it only identifies the app.)</li></ol>"
    "Sign-in uses Google's own page, so your 2-Step Verification and sign-in rules apply. "
    "GAMbit never sees passwords and keeps no Google tokens.")


class QrWidget(QWidget):
    def __init__(self, text: str):
        super().__init__()
        import qrcode
        qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(text)
        qr.make(fit=True)
        self.m = qr.get_matrix()
        self.setFixedSize(220, 220)

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        n = len(self.m)
        cell = min(self.width(), self.height()) / n
        p.fillRect(self.rect(), QColor("white"))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("black"))
        for y, row in enumerate(self.m):
            for x, on in enumerate(row):
                if on:
                    p.drawRect(QRectF(x * cell, y * cell, cell + 0.5, cell + 0.5))
        p.end()


class EmergencySetupDialog(QDialog):
    def __init__(self, parent, by: str):
        super().__init__(parent)
        self.by = by
        self.setWindowTitle("Emergency admin for this computer")
        self.secret = crypto.new_totp_secret()
        v = QVBoxLayout(self)
        tip = QLabel("For when Google sign-in is down. It works only on <b>this computer</b> "
                     "and for this Windows user. Use a long password stored somewhere safe "
                     "(a sealed envelope or your password manager), and add the code below to "
                     "an authenticator app (Google Authenticator, Microsoft Authenticator…).")
        tip.setWordWrap(True)
        v.addWidget(tip)
        h = QHBoxLayout()
        h.addWidget(QrWidget(crypto.otpauth_uri(self.secret, f"{local_admin.USER}")))
        f = QFormLayout()
        key = QLineEdit(" ".join(self.secret[i:i + 4] for i in range(0, len(self.secret), 4)))
        key.setReadOnly(True)
        key.setMinimumWidth(300)
        f.addRow("Or type this key", key)
        self.pw1, self.pw2 = QLineEdit(), QLineEdit()
        for w in (self.pw1, self.pw2):
            w.setEchoMode(QLineEdit.Password)
        self.code = QLineEdit(placeholderText="code from the app")
        f.addRow("Password", self.pw1)
        f.addRow("Again", self.pw2)
        f.addRow("Code", self.code)
        self.msg = QLabel("At least 14 characters with three of: lowercase, uppercase, digits, "
                          "symbols.", objectName="Muted", wordWrap=True)
        f.addRow(self.msg)
        hw = QWidget()
        hw.setLayout(f)
        h.addWidget(hw, 1)
        v.addLayout(h)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _save(self):
        if self.pw1.text() != self.pw2.text():
            self.msg.setText("The passwords don't match.")
            return
        try:
            local_admin.setup(self.pw1.text(), self.secret, self.code.text(), self.by)
        except ValueError as exc:
            self.msg.setText(str(exc))
            return
        session.log("emergency admin set up", who=self.by)
        self.accept()


class AccessDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.app = parent
        self.setWindowTitle("Users & access")
        self.resize(1040, 720)
        self.doc = copy.deepcopy(session.doc()) if session.doc() else None
        v = QVBoxLayout(self)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)
        self.tabs.addTab(self._signin_tab(), "Sign-in")
        self.tabs.addTab(self._people_tab(), "People")
        self.tabs.addTab(self._roles_tab(), "Roles")
        self.tabs.addTab(self._keys_tab(), "Keys")
        self.tabs.addTab(self._log_tab(), "Sign-in log")
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._refresh()

    # ===================================================== helpers ===
    def _me(self) -> str:
        return session.email() if session.active() else ""

    def _signer(self) -> str:
        """Whose key on this computer signs changes: the signed-in admin's, or – for the
        emergency admin – any trusted GAMbit admin key stored on this PC."""
        if not self.doc:
            return ""
        if session.current().get("method") == "google":
            return self._me()
        return access.local_signer(self.doc)

    def _can_edit(self) -> bool:
        return bool(self.doc) and session.active() and \
            bool((session.current().get("role") or {}).get("admin")) and bool(self._signer())

    def _save_doc(self, doc: dict, what: str) -> bool:
        try:
            saved = access.save(doc, self._signer())
        except access.AccessError as exc:
            QMessageBox.warning(self, "Users & access", str(exc))
            return False
        except OSError as exc:
            QMessageBox.warning(self, "Users & access", f"Couldn't write the access list:\n{exc}")
            return False
        self.doc = copy.deepcopy(saved)
        session.set_doc(saved)
        session.log(f"access list changed: {what}")
        self._refresh()
        return True

    # ===================================================== sign-in ===
    def _signin_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.state = QLabel("", wordWrap=True)
        v.addWidget(self.state)
        f = QFormLayout()
        self.domain = QLineEdit(placeholderText="district.org")
        self.cid = QLineEdit(placeholderText="…apps.googleusercontent.com")
        self.csec = QLineEdit()
        self.csec.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.idle = QSpinBox()
        self.idle.setRange(5, 240)
        self.idle.setSuffix(" minutes idle → lock")
        self.maxh = QSpinBox()
        self.maxh.setRange(1, 24)
        self.maxh.setSuffix(" hours → sign in again")
        f.addRow("Google domain", self.domain)
        f.addRow("OAuth client ID", self.cid)
        f.addRow("OAuth client secret", self.csec)
        f.addRow("Lock after", self.idle)
        f.addRow("Sign-in lasts", self.maxh)
        v.addLayout(f)
        row = QHBoxLayout()
        self.test_btn = QPushButton("Test Google sign-in")
        self.test_btn.clicked.connect(lambda: self._google(test=True))
        self.on_btn = QPushButton("Turn on GAMbit sign-in…")
        self.on_btn.setProperty("kind", "primary")
        self.on_btn.clicked.connect(lambda: self._google(test=False))
        self.save_btn = QPushButton("Save sign-in settings")
        self.save_btn.clicked.connect(self._save_signin)
        for b in (self.test_btn, self.on_btn, self.save_btn):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.g_status = QLabel("", objectName="Muted", wordWrap=True)
        v.addWidget(self.g_status)
        help_l = QLabel(SETUP_HELP)
        help_l.setWordWrap(True)
        help_l.setTextFormat(Qt.RichText)
        v.addWidget(help_l)
        em = QHBoxLayout()
        self.em_state = QLabel("", wordWrap=True)
        em.addWidget(self.em_state, 1)
        self.em_set = QPushButton("Set up emergency admin…")
        self.em_set.clicked.connect(self._emergency)
        self.em_del = QPushButton("Remove it")
        self.em_del.clicked.connect(self._emergency_remove)
        em.addWidget(self.em_set)
        em.addWidget(self.em_del)
        v.addLayout(em)
        v.addStretch(1)
        return w

    def _google(self, test: bool):
        dom, cid, sec = (self.domain.text().strip().lower(), self.cid.text().strip(),
                         self.csec.text().strip())
        if not dom or not cid or not sec:
            QMessageBox.information(self, "Sign-in", "Fill in the domain, client ID and "
                                    "client secret first.")
            return
        self.g_status.setText("Finish signing in in your web browser…")

        def done(who):
            if test:
                self.g_status.setText(f"✔ Google sign-in works – you signed in as "
                                      f"{who['email']}.")
                return
            self._turn_on(who, dom, cid, sec)
        Worker(sign_in, cid, sec, dom, webbrowser.open, "", 180, None, on_done=done,
               on_error=lambda e: self.g_status.setText(f"✖ {e}"))

    def _turn_on(self, who: dict, dom: str, cid: str, sec: str):
        if access.exists():
            QMessageBox.warning(self, "Sign-in", "There's already an access list in the team "
                                f"folder ({access.path()}). Restart GAMbit to sign in with it.")
            return
        if QMessageBox.question(
                self, "Turn on GAMbit sign-in",
                f"You'll be the first GAMbit admin ({who['email']}).\n\nAfter this, everyone "
                "using this team folder must sign in with Google, and only people you add on "
                "the People tab can use GAMbit. Continue?") != QMessageBox.Yes:
            return
        try:
            doc = access.new_list(who["email"], dom, cid, sec)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Sign-in", f"Couldn't create the access list:\n{exc}")
            return
        doc["session"] = {"idle_minutes": self.idle.value(), "max_hours": self.maxh.value()}
        if local_admin.configured():
            try:
                doc.setdefault("emergency", {})[local_admin.computer()] = \
                    local_admin.fingerprint()
            except ValueError:
                pass
        session.set_doc(doc)
        p = access.person(doc, who["email"])
        p["name"] = who.get("name", "")
        session.start(p, "google", doc)
        doc = access.save(doc, who["email"])
        session.set_doc(doc)
        self.doc = copy.deepcopy(doc)
        session.log("turned on GAMbit sign-in")
        if hasattr(self.app, "start_session_ui"):
            self.app.start_session_ui()
        self._refresh()
        QMessageBox.information(
            self, "Sign-in is on",
            "GAMbit sign-in is on.\n\nNext:\n• People tab – add your team and their roles.\n"
            "• Set up the emergency admin on this computer.\n• On each tech's PC, GAMbit "
            "will ask them to confirm this code once:\n\n    " + self._my_fingerprint())

    def _save_signin(self):
        if not self._can_edit():
            return
        d = copy.deepcopy(self.doc)
        d["google"] = {"client_id": self.cid.text().strip(),
                       "client_secret": self.csec.text().strip()}
        d["session"] = {"idle_minutes": self.idle.value(), "max_hours": self.maxh.value()}
        if self.domain.text().strip().lower() != d.get("domain"):
            QMessageBox.information(self, "Sign-in", "The domain can't be changed once sign-in "
                                    "is on.")
            self.domain.setText(d.get("domain", ""))
        self._save_doc(d, "sign-in settings")

    def _my_fingerprint(self) -> str:
        k = access.my_key(self._me()) if self._me() else None
        return crypto.fingerprint(k[1]) if k else "(no admin key on this computer)"

    def _emergency(self):
        if not self._can_edit():
            QMessageBox.information(self, "Emergency admin", "Turn on GAMbit sign-in first, "
                                    "and be signed in with Google as a GAMbit admin.")
            return
        who = self._me() or team.me()
        if EmergencySetupDialog(self, who).exec() == QDialog.Accepted:
            d = copy.deepcopy(self.doc)
            d.setdefault("emergency", {})[local_admin.computer()] = local_admin.fingerprint()
            if self._save_doc(d, f"emergency admin registered for {local_admin.computer()}"):
                QMessageBox.information(self, "Emergency admin", "Saved. Keep the password and "
                                        "the authenticator somewhere safe – both are needed.")
        self._refresh()

    def _emergency_remove(self):
        if QMessageBox.question(self, "Emergency admin", "Remove the emergency admin from this "
                                "computer?") == QMessageBox.Yes:
            local_admin.remove()
            session.log("emergency admin removed")
            if self._can_edit() and (self.doc.get("emergency") or {}).get(
                    local_admin.computer()):
                d = copy.deepcopy(self.doc)
                d["emergency"].pop(local_admin.computer(), None)
                self._save_doc(d, f"emergency admin removed for {local_admin.computer()}")
            self._refresh()

    # ====================================================== people ===
    def _people_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Only the people listed here can sign in. Org units limit what "
                           "they see and change (blank = everything their role allows)."))
        f = QHBoxLayout()
        f.addWidget(QLabel("Anyone else in the domain:"))
        self.default_role = QComboBox()
        f.addWidget(self.default_role)
        f.addStretch(1)
        v.addLayout(f)
        self.people = QTableWidget(0, 6)
        self.people.setHorizontalHeaderLabels(["Email", "Name", "Role", "Org units (comma)",
                                               "Can sign in", "Added"])
        self.people.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.people.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.people.setColumnWidth(2, 200)
        self.people.verticalHeader().setVisible(False)
        v.addWidget(self.people, 1)
        row = QHBoxLayout()
        for text, slot in (("Add person…", self._add_person), ("Remove selected",
                                                               self._remove_people),
                           ("Save people", self._save_people)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        return w

    def _role_names(self):
        return sorted(access.all_roles(self.doc or {}))

    def _fill_people(self):
        self.people.setRowCount(0)
        names = self._role_names()
        self.default_role.clear()
        self.default_role.addItems(names)
        if self.doc:
            dr = self.doc.get("default_role", access.NO_ACCESS)
            self.default_role.setCurrentText(dr if self.default_role.findText(dr) >= 0
                                             else access.NO_ACCESS)
        for e, p in sorted((self.doc or {}).get("people", {}).items()):
            self._person_row(e, p)

    def _person_row(self, e, p):
        r = self.people.rowCount()
        self.people.insertRow(r)
        it = QTableWidgetItem(e)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        self.people.setItem(r, 0, it)
        self.people.setItem(r, 1, QTableWidgetItem(p.get("name", "")))
        cb = QComboBox()
        cb.addItems(self._role_names())
        role = p.get("role", "Help desk")
        if cb.findText(role) < 0:        # a role that no longer exists – don't guess
            role = access.NO_ACCESS
        cb.setCurrentText(role)
        self.people.setCellWidget(r, 2, cb)
        self.people.setItem(r, 3, QTableWidgetItem(", ".join(p.get("ous", []))))
        chk = QCheckBox()
        chk.setChecked(p.get("enabled", True))
        self.people.setCellWidget(r, 4, chk)
        add = QTableWidgetItem(p.get("added", ""))
        add.setFlags(add.flags() & ~Qt.ItemIsEditable)
        self.people.setItem(r, 5, add)

    def _add_person(self):
        dom = (self.doc or {}).get("domain", "")
        e, ok = QInputDialog.getText(self, "Add person", f"Their @{dom} email address:")
        e = e.strip().lower()
        if not ok or not e:
            return
        if "@" not in e or (dom and not e.endswith("@" + dom)):
            QMessageBox.information(self, "Add person", f"Use an @{dom} address.")
            return
        self._person_row(e, {"role": "Help desk", "enabled": True,
                             "added": datetime.date.today().isoformat()})

    def _remove_people(self):
        for r in sorted({i.row() for i in self.people.selectedIndexes()}, reverse=True):
            self.people.removeRow(r)

    def _save_people(self):
        if not self._can_edit():
            QMessageBox.information(self, "People", "Sign in with Google as a GAMbit admin to "
                                    "change who has access.")
            return
        old = (self.doc or {}).get("people", {})
        people = {}
        for r in range(self.people.rowCount()):
            e = self.people.item(r, 0).text().strip().lower()
            ous = [o.strip() for o in (self.people.item(r, 3).text() if self.people.item(r, 3)
                                       else "").split(",") if o.strip()]
            bad = [o for o in ous if not o.startswith("/")]
            if bad:
                QMessageBox.information(self, "People", f"Org units start with “/”: {bad[0]}")
                return
            people[e] = {**old.get(e, {}), "name": self.people.item(r, 1).text().strip()
                         if self.people.item(r, 1) else "",
                         "role": self.people.cellWidget(r, 2).currentText(), "ous": ous,
                         "enabled": self.people.cellWidget(r, 4).isChecked(),
                         "added": old.get(e, {}).get("added",
                                                     datetime.date.today().isoformat())}
        d = copy.deepcopy(self.doc)
        d["people"] = people
        d["default_role"] = self.default_role.currentText()
        if not access.keyed_admins(d):
            QMessageBox.warning(self, "People", "Keep at least one GAMbit admin whose key is "
                                "trusted (see Keys) – otherwise nobody could change "
                                "access again.")
            return
        signer = self._signer()
        sk = next((kid for kid, k in d.get("admin_keys", {}).items() if k["email"] == signer),
                  "")
        if sk and not access.signer_is_admin(d, sk):
            QMessageBox.information(self, "People", "You can't remove your own admin rights – "
                                    "ask another GAMbit admin to do it.")
            return
        self._save_doc(d, "people")

    # ======================================================= roles ===
    def _roles_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        lab = QLabel("Roles set which pages people see, which pages are <b>view only</b>, what "
                     "they can change (or ask approval for), an optional org-unit limit for "
                     "everyone in the role, and an optional GAM profile – a gam.cfg section "
                     "signed in as a Google admin with only the matching admin role, so GAM "
                     "itself can't do more than the role allows.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        b = QPushButton("Edit roles…")
        b.clicked.connect(self._edit_roles)
        v.addWidget(b, 0, Qt.AlignLeft)
        self.roles_view = ResultsTable()
        v.addWidget(self.roles_view, 1)
        return w

    def _edit_roles(self):
        if not self._can_edit():
            QMessageBox.information(self, "Roles", "Sign in with Google as a GAMbit admin first.")
            return
        from .main_window import PAGES
        from .roles_dialog import RolesDialog
        wf = []
        try:
            wf = self.app.pages["Workflows"].tab_names()
        except Exception:  # noqa: BLE001
            pass
        if RolesDialog(self, [n for n, _c in PAGES], wf).exec() == QDialog.Accepted:
            self.doc = copy.deepcopy(session.doc())
            self._refresh()

    def _fill_roles(self):
        rows = []
        for name, r in sorted(access.all_roles(self.doc or {}).items()):
            rows.append([name, "yes" if r.get("admin") else "",
                         "all" if "*" in r.get("pages", []) else str(len(r.get("pages", []))),
                         str(len(r.get("view_only", []))), ", ".join(r.get("can", [])),
                         ", ".join(r.get("ous", [])), r.get("gam_profile", ""),
                         r.get("description", "")])
        self.roles_view.set_rows(["Role", "Admin", "Pages", "View-only pages", "Can",
                                  "Org units", "GAM profile", "Description"], rows)

    # ==================================================== admin keys ===
    def _keys_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        lab = QLabel("Changes to the access list are signed with a GAMbit admin's key, which "
                     "lives only on that admin's computer. Each tech's GAMbit checks the "
                     "signature, so nobody can hand-edit the list. Everyone else's key signs "
                     "what they ask for (Run later items, requests, approvals), so other "
                     "computers and the background tasks know who really made it. GAMbit asks "
                     "for a key when someone signs in; an admin checks the code with them and "
                     "approves it.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        self.my_fp = QLabel("")
        self.my_fp.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.my_fp)
        self.keys = ResultsTable()
        v.addWidget(self.keys, 1)
        row = QHBoxLayout()
        for text, slot in (("Ask to trust my key", self._ask_key),
                           ("Approve selected request", self._approve_key),
                           ("Reject selected request", self._reject_key),
                           ("Stop trusting selected key", self._remove_key),
                           ("Lock sign-in on this computer…", self._lock_pc)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        return w

    def _fill_keys(self):
        rows = []
        for kid, k in (self.doc or {}).get("admin_keys", {}).items():
            rows.append(["trusted", k["email"], crypto.fingerprint(crypto.unb64(k["public"])),
                         k.get("added", ""), kid])
        for kid, k in (self.doc or {}).get("member_keys", {}).items():
            rows.append(["trusted (member)", k["email"],
                         crypto.fingerprint(crypto.unb64(k["public"])), k.get("added", ""),
                         kid])
        if self.doc:
            known = set(self.doc.get("admin_keys", {})) | set(self.doc.get("member_keys", {}))
            for r in access.key_requests():
                if r["key_id"] not in known:
                    rows.append(["waiting for approval", r["email"], r["fingerprint"],
                                 r.get("asked", "")[:10], r["key_id"]])
        self.keys.set_rows(["Status", "Person", "Code", "Date", "key"], rows)
        self.my_fp.setText(f"Your key code on this computer: <b>{self._my_fingerprint()}</b>"
                           if self._me() else "")

    def _ask_key(self):
        if not self._me():
            return
        fp = access.request_admin_key(self._me())
        session.log("asked for admin key", fingerprint=fp)
        QMessageBox.information(self, "Admin key", f"Asked. Give another GAMbit admin this "
                                f"code so they can check it before approving:\n\n{fp}")
        self._fill_keys()

    def _selected_key(self):
        rows = self.keys.selected_dicts()
        return rows[0] if rows else None

    def _approve_key(self):
        if not self._can_edit():
            return
        sel = self._selected_key()
        if not sel or sel.get("Status") != "waiting for approval":
            return
        req = next((r for r in access.key_requests() if r["key_id"] == sel["key"]), None)
        if not req:
            return
        code, ok = QInputDialog.getText(self, "Approve key",
                                        f"Ask {req['email']} to read you the code GAMbit shows "
                                        "them, and type it here:")
        if not ok:
            return
        norm = lambda t: "".join(c for c in t.upper() if c.isalnum())  # noqa: E731
        if norm(code) != norm(req["fingerprint"]):
            QMessageBox.warning(self, "Admin key", "The code doesn't match – not approved. "
                                "Someone may have put a fake request in the team folder.")
            return
        try:
            d = access.approve_key(self.doc, req)
        except access.AccessError as exc:
            QMessageBox.information(self, "Admin key", str(exc))
            return
        if self._save_doc(d, f"trusted admin key for {req['email']}"):
            access.drop_request(req)
            self._fill_keys()

    def _reject_key(self):
        sel = self._selected_key()
        req = next((r for r in access.key_requests() if sel and r["key_id"] == sel["key"]),
                   None)
        if req:
            access.drop_request(req)
            self._fill_keys()

    def _remove_key(self):
        if not self._can_edit():
            return
        sel = self._selected_key()
        if not sel or not str(sel.get("Status", "")).startswith("trusted"):
            return
        d = copy.deepcopy(self.doc)
        if sel.get("Status") == "trusted (member)":
            d.get("member_keys", {}).pop(sel["key"], None)
            self._save_doc(d, f"stopped trusting a key of {sel['Person']}")
            return
        d["admin_keys"].pop(sel["key"], None)
        if not access.keyed_admins(d):
            QMessageBox.information(self, "Admin key", "That would leave no GAMbit admin with a "
                                    "trusted key.")
            return
        if sel["key"] in (crypto.key_id(k[1]) for k in [access.my_key(self._signer())] if k):
            QMessageBox.information(self, "Admin key", "You can't stop trusting your own key – "
                                    "ask another GAMbit admin.")
            return
        self._save_doc(d, f"stopped trusting a key of {sel['Person']}")

    def _lock_pc(self):
        """Machine-wide: sign-in can't be switched off by clearing settings, and only lists
        signed by today's admin keys are accepted (asks for Windows admin rights)."""
        if not self._can_edit():
            return
        kids = sorted((self.doc or {}).get("admin_keys", {}))
        if not kids:
            return
        if QMessageBox.question(
                self, "Lock sign-in", "Keep GAMbit sign-in required on this computer for "
                "every Windows user, and accept only access lists signed by the current admin "
                "keys? Windows will ask for administrator rights.\n\nIf the admin keys change "
                "later, lock again on each computer.") != QMessageBox.Yes:
            return
        try:
            access.write_machine_lock(kids)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.information(self, "Lock sign-in", str(exc))
            return
        session.log("locked sign-in on this computer", keys=",".join(kids))
        QMessageBox.information(self, "Lock sign-in", "Done – sign-in is locked on for this "
                                "computer.")

    # ========================================================== log ===
    def _log_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.log_t = ResultsTable()
        v.addWidget(self.log_t, 1)
        return w

    def _fill_log(self):
        rows = session.read_log(1000)
        self.log_t.set_rows(["Time", "Who", "What", "Computer", "Details"],
                            [[r.get("time", ""), r.get("who", ""), r.get("event", ""),
                              r.get("computer", ""),
                              ", ".join(f"{k}={v}" for k, v in r.items()
                                        if k not in ("time", "who", "event", "computer"))]
                             for r in rows])

    # ====================================================== refresh ===
    def _refresh(self):
        on = bool(self.doc)
        edit = self._can_edit()
        d = self.doc or {}
        self.domain.setText(d.get("domain", self.domain.text() or _guess_domain(self.app)))
        g = d.get("google", {})
        if on:
            self.cid.setText(g.get("client_id", ""))
            self.csec.setText(g.get("client_secret", ""))
        s = d.get("session", {})
        self.idle.setValue(int(s.get("idle_minutes", 30)))
        self.maxh.setValue(int(s.get("max_hours", 10)))
        self.domain.setReadOnly(on)
        self.on_btn.setVisible(not on)
        self.save_btn.setVisible(on)
        self.save_btn.setEnabled(edit)
        if on:
            self.state.setText(f"<b>GAMbit sign-in is on</b> for {d.get('domain')}. Access list: "
                               f"{access.path()} (version {d.get('serial')}, saved by "
                               f"{d.get('updated_by')} {d.get('updated', '')[:16]})."
                               + ("" if edit else "<br><i>Only GAMbit admins signed in with "
                                  "Google can change it.</i>"))
        else:
            self.state.setText("<b>GAMbit sign-in is off.</b> Anyone who can open GAMbit on a "
                               "PC can use it. Fill in the Google details and click <i>Turn on"
                               "</i> – you'll sign in with Google and become the first admin.")
        em = local_admin.configured()
        self.em_state.setText("Emergency admin on this computer: <b>"
                              + ("set up" if em else "not set up") + "</b>"
                              + (f" (locked for {local_admin.locked_for() // 60 + 1} min)"
                                 if em and local_admin.locked_for() else ""))
        self.em_set.setText("Change emergency admin…" if em else "Set up emergency admin…")
        self.em_set.setEnabled(edit or not on)
        self.em_del.setEnabled(em and (edit or not on))
        for i in range(1, 5):
            self.tabs.setTabEnabled(i, on)
        self._fill_people()
        self._fill_roles()
        self._fill_keys()
        self._fill_log()


def _guess_domain(app) -> str:
    try:
        d = getattr(app.directory, "domain", "") or ""
        if d:
            return d
        u = (app.directory.all_users or app.directory.users or [{}])[0].get("email", "")
        return u.split("@")[-1] if "@" in u else ""
    except Exception:  # noqa: BLE001
        return ""


__all__ = ["AccessDialog", "EmergencySetupDialog", "SignInError"]
