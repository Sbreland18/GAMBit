"""Student lookup: everything the front office needs about one account, on one screen."""

from __future__ import annotations

import csv
import io

import json

from PySide6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from ...selfservice import _password as friendly_password
from ...settings import settings
from ..pickers import PersonField
from ..widgets import Page, ResultsTable, button


def student_ous(ous: list[str] | None = None) -> list[str]:
    from ... import ou_map
    return ou_map.student_roots(ous)


def is_student_ou(ou: str, roots: list[str]) -> bool:
    o = (ou or "/").rstrip("/").lower() + "/"
    return any(o.startswith(r.rstrip("/").lower() + "/") or r.strip() == "/" for r in roots)


class LookupPage(Page):
    title = "Student lookup"
    subtitle = ("Look up a student (or anyone): account status, their Chromebook, their "
                "classes – and reset the password or sign them out from the same screen.")

    def build(self):
        from ..pickers import OUMultiField
        self.who = PersonField(self.directory, "Type a student's name or email, then Enter",
                               user_filter=self._is_student)
        self.who.returnPressed.connect(self.lookup)
        self.everyone = QCheckBox("Include staff")
        self.everyone.setToolTip("Normally only accounts in the student org units are "
                                 "suggested and looked up.")
        self.everyone.toggled.connect(lambda _v: self.who.set_user_filter(
            None if self.everyone.isChecked() else self._is_student))
        self.body.addLayout(self.row(self.who, button("Look up", "primary", self.lookup),
                                     button("☆ Favorite", slot=lambda: self.app.add_favorite(
                                         self.who.email())), self.everyone, stretch=False))
        from ... import ou_map
        self.ous = OUMultiField(self.directory)
        self.ous.set_paths(student_ous(self.directory.ous))
        if ou_map.configured():
            self.body.addWidget(QLabel("Students are in: " + ", ".join(student_ous()) +
                                       " (from Settings & Updates → Org units & schools)",
                                       objectName="Muted"))
        else:
            self.body.addLayout(self.row(QLabel("Students are in"), self.ous,
                                         button("Save", slot=self._save_ous),
                                         stretch=False))
        self.card = QLabel("")
        self.card.setWordWrap(True)
        self.card.setStyleSheet("font-size:11pt;")
        self.body.addWidget(self.card)
        acts = QHBoxLayout()
        self.reset_btn = button("Reset password", "primary", self.reset)
        self.reset_btn.setProperty("helpdesk_ok", True)
        for b in (self.reset_btn,
                  button("Sign out everywhere", slot=self.signout),
                  button("Require a new password", slot=self.require_change),
                  button("Unsuspend", slot=self.unsuspend),
                  button("Timeline", slot=lambda: self.app.open_timeline(self.who.email())),
                  button("Flags", slot=self.flags),
                  button("Open in Users", slot=lambda: self.app.open_user(self.who.email()))):
            acts.addWidget(b)
        acts.addStretch(1)
        self.body.addLayout(acts)
        self.pw = QLabel("")
        self.pw.setStyleSheet("font-size:16pt;font-family:Consolas,monospace;color:#137333;")
        self.pw.setTextInteractionFlags(self.pw.textInteractionFlags())
        self.body.addWidget(self.pw)
        row = QHBoxLayout()
        for title, attr in (("Chromebooks", "cros"), ("Classes", "classes")):
            box = QGroupBox(title)
            v = QVBoxLayout(box)
            t = ResultsTable()
            setattr(self, attr, t)
            v.addWidget(t)
            row.addWidget(box, 1)
        w = QWidget()
        w.setLayout(row)
        self.body.addWidget(w, 1)

    def _is_student(self, u: dict) -> bool:
        from ... import ou_map
        return ou_map.is_student(u.get("ou", ""), self.directory.ous)

    def _save_ous(self, *_):
        paths = [p for p in self.ous.paths() if p]
        settings.set("lookup/student_ous", json.dumps(paths or ["/Students"]))
        self.who.set_user_filter(None if self.everyone.isChecked() else self._is_student)
        self.app.statusBar().showMessage("Saved the student org units", 4000) \
            if hasattr(self.app, "statusBar") else None

    def on_show(self):
        self.who.setFocus()

    def _email(self) -> str:
        e = self.who.email()
        if "@" not in e:
            self.info("Choose a person first.")
            return ""
        return e

    def lookup(self):
        e = self._email()
        if not e:
            return
        self.pw.setText("")
        self.card.setText("Looking up…")

        def got_user(code, out, _err):
            rows = list(csv.DictReader(io.StringIO(out or ""))) if code == 0 else []
            if not rows:
                self.card.setText(f"<b>{e}</b> wasn't found in Google.")
                return
            r = {k.lower(): v for k, v in rows[0].items()}
            from ... import ou_map
            if not self.everyone.isChecked() and not ou_map.is_student(
                    r.get("orgunitpath", ""), self.directory.ous):
                self.card.setText(f"<b>{e}</b> isn't in a student org unit "
                                  f"({r.get('orgunitpath', '/')}). Tick <i>Include staff</i> "
                                  "to look up staff here, or use the Staff card page.")
                self.cros.set_rows([], [])
                self.classes.set_rows([], [])
                return
            susp = (r.get("suspended", "") or "").lower() == "true"
            state = ("<span style='color:#b42318'>✖ Suspended</span>" +
                     (f" ({r.get('suspensionreason')})" if r.get("suspensionreason") else "")
                     if susp else "<span style='color:#137333'>✔ Active</span>")
            tsv = "on" if (r.get("isenrolledin2sv", "") or "").lower() == "true" else "off"
            last = (r.get("lastlogintime") or "never")[:16].replace("T", " ")
            if last.startswith("1970"):
                last = "never"
            self.card.setText(
                f"<b style='font-size:13pt'>{r.get('name.fullname', '')}</b> &lt;{e}&gt;<br>"
                f"{state} · org unit <b>{r.get('orgunitpath', '/')}</b> · last sign-in {last} · "
                f"2-step {tsv} · created {(r.get('creationtime') or '')[:10]}" +
                _custom_line(rows[0]))
            self.runner.run(["print", "cros", "query", f"user:{e}", "fields",
                             "serialnumber,annotatedassetid,annotatedlocation,status,lastsync,"
                             "model"], lambda c, o, _e: self.cros.load_csv(o if c == 0 else ""),
                            quiet_stdout=True)
            self.runner.run(["print", "courses", "student", e, "states", "active", "owneremail",
                             "fields", "id,name,section,ownerid"],
                            lambda c, o, _e: self.classes.load_csv(o if c == 0 else ""),
                            quiet_stdout=True)
        from ... import custom_fields
        self.runner.run(custom_fields.with_custom(
            ["print", "users", "query", f"email:{e}", "fields",
             "primaryemail,name,suspended,ou,lastlogintime,isenrolledin2sv,creationtime"]),
            got_user, quiet_stdout=True)


    def flags(self):
        e = self._email()
        if e:
            from .round15_tabs import StudentFlagsDialog
            StudentFlagsDialog(self, e).exec()

    def reset(self):
        e = self._email()
        if not e:
            return
        pw = friendly_password()
        if not self.confirm(f"Reset the password for {e}?\n\nNew password: {pw}\n\nThey'll "
                            "choose their own when they sign in."):
            return

        def done(code, _o, _e):
            if code == 0:
                self.pw.setText(f"New password for {e}:  {pw}")
        self.runner.run(["update", "user", e, "password", pw, "changepassword", "on"], done)

    def signout(self):
        e = self._email()
        if e:
            self.runner.run(["user", e, "signout"])

    def require_change(self):
        e = self._email()
        if e:
            self.runner.run(["update", "user", e, "changepassword", "on"])

    def unsuspend(self):
        e = self._email()
        if e and self.confirm(f"Unsuspend {e}?"):
            self.runner.run(["update", "user", e, "suspended", "off"],
                            lambda *_: self.lookup())


def _custom_line(row: dict) -> str:
    """The chosen custom fields on the user card (Settings → Custom user fields)."""
    import html
    try:
        from ... import custom_fields
        vals = custom_fields.tidy_dict(row) if custom_fields.active() else []
    except Exception:  # noqa: BLE001
        vals = []
    vals = [(k, v) for k, v in vals if str(v).strip()]
    if not vals:
        return ""
    return "<br>" + " · ".join(f"{html.escape(k)} <b>{html.escape(str(v))}</b>"
                               for k, v in vals)
