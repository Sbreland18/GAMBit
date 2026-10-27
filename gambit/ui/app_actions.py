"""App-wide helpers mixed into MainWindow: jump-to navigation, global search,
right-click actions, results pop-ups, help-desk mode and domain profiles."""

from __future__ import annotations

import hashlib
import re

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QCompleter, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMessageBox, QTabWidget, QVBoxLayout, QWidget,
)

from .. import profiles, team
from ..gam_runner import helpdesk_on
from ..settings import settings
from .widgets import ResultsTable, Worker, apply_helpdesk, button

EMAIL_COLS = ["primaryemail", "email", "user", "owner", "owneremail", "profile.emailaddress",
              "emailaddress", "useremail", "invitedemailaddress", "delegateaddress",
              "actor.email", "permission.emailaddress", "studentemail", "target"]
SERIAL_COLS = ["serialnumber"]
SERIAL_RE = re.compile(r"^[A-Za-z0-9]{6,20}$")
ASSET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._#-]{1,30}$")   # asset tags like HMS-0123

# Pages hidden in help-desk mode
HELPDESK_HIDDEN = {"Diagnostics", "Live test", "Command Console", "Command Builder", "Bulk (CSV)", "Org units",
                   "Licenses", "Schedules", "Settings & Updates", "More services",
                   "Roster sync"}


class AppActions:
    # ============================================================ top bar ===
    def build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setStyleSheet("QWidget#TopBar{background:white;border-bottom:1px solid #dfe3e8;}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(24, 8, 24, 8)
        self.gsearch = QLineEdit(placeholderText="🔍  What do you want to do? Or jump to a "
                                                 "person, group, org unit or Chromebook…")
        self.gsearch.setMinimumWidth(260)
        self.gmodel = QStringListModel(self)
        comp = QCompleter(self.gmodel, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        comp.setMaxVisibleItems(14)
        comp.activated[str].connect(self.global_go)
        self.gsearch.setCompleter(comp)
        self.gsearch.returnPressed.connect(lambda: self.global_go(self.gsearch.text()))
        h.addWidget(self.gsearch, 1)
        h.addSpacing(16)
        h.addWidget(QLabel("Domain:", objectName="Muted"))
        self.profile_box = QComboBox()
        self.profile_box.setMinimumWidth(160)
        self.profile_box.activated.connect(lambda _i: self.switch_profile(
            self.profile_box.currentText()))
        h.addWidget(self.profile_box)
        self.ticket_box = QLineEdit()
        self.ticket_box.setPlaceholderText("Ticket (paste a link or number)")
        self.ticket_box.setToolTip("Link the help-desk ticket you're working on – GAMbit adds a "
                                   "note to it listing what it did.")
        self.ticket_box.setMaximumWidth(210)
        self.ticket_box.editingFinished.connect(self._ticket_changed)
        h.addWidget(self.ticket_box)
        self.refresh_ticket_box()
        self.dry_btn = button("🧪 Dry run", slot=lambda: self.set_dry_run(
            self.dry_btn.isChecked()))
        self.dry_btn.setCheckable(True)
        self.dry_btn.setProperty("helpdesk_ok", True)
        self.dry_btn.setToolTip("When on, changes aren't made – GAMbit lists the exact GAM "
                                "commands instead (look-ups still run).")
        h.addWidget(self.dry_btn)
        self.practice_btn = button("🎓 Practice", slot=lambda: self.set_practice(
            self.practice_btn.isChecked()))
        self.practice_btn.setCheckable(True)
        self.practice_btn.setProperty("helpdesk_ok", True)
        self.practice_btn.setToolTip("Practice mode for new techs: changes to the test account "
                                     "and test org unit run for real, everything else is a "
                                     "dry run (Settings → Testing).")
        h.addWidget(self.practice_btn)
        self.helper_btn = button("💬 Helper", slot=lambda: self.helper.toggle())
        self.helper_btn.setProperty("helpdesk_ok", True)
        self.helper_btn.setToolTip("Ask GAMbit's offline Helper – plain English is fine "
                                   "(F2)")
        h.addWidget(self.helper_btn)
        self.hd_btn = button("🔒 Help-desk mode", slot=self.leave_helpdesk)
        self.hd_btn.setToolTip("Destructive actions are hidden. Click to unlock with the PIN.")
        self.hd_btn.setStyleSheet("background:#fff4ce;border-color:#f2d675;")
        h.addWidget(self.hd_btn)
        self.install_session(h)
        self.refresh_profiles()
        for sig in (self.directory.users_changed, self.directory.groups_changed,
                    self.directory.ous_changed):
            sig.connect(self._refresh_search)
        self._refresh_search()
        return bar

    def refresh_ticket_box(self):
        from ..integrations import ticketing as tk
        on = tk.configured() and tk.can("note")
        self.ticket_box.setVisible(on)
        if on:
            self.ticket_box.setPlaceholderText(f"{tk.name()} ticket (link or number)")

    def _ticket_changed(self):
        from ..integrations import ticketing as tk
        tid = tk.ticket_id(self.ticket_box.text())
        if not tid or not tk.can("read"):
            return
        Worker(tk.get, tid,
               on_done=lambda t: (self.ticket_box.setToolTip(
                   f"Ticket {t['number']}: {t['subject']} – {t['for']}"),
                   self.statusBar().showMessage(f"Linked ticket {t['number']}: {t['subject']}",
                                                8000)),
               on_error=lambda e: self.log_line(f"{tk.name()}: {e}", "#ff8a80"))

    def ticket_note(self, steps):
        from ..integrations import ticketing as tk
        tid = tk.ticket_id(self.ticket_box.text()) if hasattr(self, "ticket_box") else ""
        if not tid or not tk.option("auto_note", True) or not tk.configured() or \
                not tk.can("note"):
            return
        if not any(s.status in ("ok", "fail", "dry") for s in steps):
            return
        Worker(tk.note, tid, tk.summary_note(steps),
               on_done=lambda _r: self.log_line(f"📝 Added a note to the {tk.name()} ticket."),
               on_error=lambda e: self.log_line(f"Couldn't add the ticket note: {e}",
                                                "#ff8a80"))

    def set_practice(self, on: bool):
        """Practice mode: dry run for everything except the test account and test org unit."""
        from .. import user_prefs as up
        ou, user = up.practice_target()
        if on and not (ou or user):
            QMessageBox.information(self, "Practice mode", "Set a test org unit or test "
                                    "account first (Settings & Updates → Testing). Practice "
                                    "changes run for real only there.")
            self.practice_btn.setChecked(False)
            return
        if on and not up.practice_on():
            settings.set("practice/prev_dry", bool(settings.get("safety/dry_run", False)))
        settings.set(up.PRACTICE_KEY, bool(on))
        self.practice_btn.setChecked(bool(on))
        self.practice_btn.setStyleSheet("background:#e7f5e9;border-color:#2da44e;"
                                        "font-weight:600;" if on else "")
        self.practice_btn.setText("🎓 Practice is ON" if on else "🎓 Practice")
        self.set_dry_run(True if on else bool(settings.get("practice/prev_dry", False)))
        if on:
            self.statusBar().showMessage(
                f"Practice mode: changes to {user or ''}{' and ' if ou and user else ''}"
                f"{ou or ''} run for real; everything else is a dry run.")

    def install_practice(self):
        from .. import user_prefs as up

        def ok(args):
            if not up.practice_on():
                return False
            d = self.directory
            by_email = {u["email"].lower(): u for u in (getattr(d, "all_users", None) or
                                                       d.users)}
            return up.practice_allows(args, by_email)
        self.runner.practice_ok = ok
        if up.practice_on():
            self.set_practice(True)

    def set_dry_run(self, on: bool):
        from .. import user_prefs as up
        if not on and up.practice_on():
            on = True                    # practice mode keeps dry run on
        settings.set("safety/dry_run", bool(on))
        self.dry_btn.setChecked(bool(on))
        self.dry_btn.setStyleSheet("background:#fff4ce;border-color:#d4a72c;font-weight:600;"
                                   if on else "")
        self.dry_btn.setText("🧪 Dry run is ON" if on else "🧪 Dry run")
        for p in self.pages.values():
            if hasattr(p, "refresh_help"):
                p.refresh_help()
            if hasattr(p, "dry_changed"):
                p.dry_changed(bool(on))
        self.statusBar().showMessage("Dry run is on – changes are listed, not made."
                                     if on else "Dry run is off – changes run for real.")

    # ----------------------------------------------------- favorites ---
    def favorites(self) -> list[dict]:
        import json
        try:
            return json.loads(settings.get("favorites", "[]") or "[]")
        except ValueError:
            return []

    def _save_favorites(self, favs):
        import json
        settings.set("favorites", json.dumps(favs))
        self._refresh_search()
        home = self.pages.get("Home") if hasattr(self, "pages") else None
        if home is not None and hasattr(home, "show_favorites"):
            home.show_favorites()
        users = self.pages.get("Users") if hasattr(self, "pages") else None
        if users is not None and hasattr(users, "refresh_saved"):
            try:
                users.refresh_saved()
            except Exception:  # noqa: BLE001
                pass

    def fav_label(self, f: dict) -> str:
        icon = {"user": "👤", "group": "👥", "ou": "🏢", "serial": "💻",
                "search": "🔎"}.get(f["kind"], "★")
        if f["kind"] in ("user", "group"):
            return f"★ {icon} {f['label']}  <{f['value']}>"
        return f"★ {icon} {f['label']}"

    def add_favorite(self, value: str, kind: str = "", label: str = ""):
        d = self.directory
        v = value.strip()
        if not kind:
            if any(g["email"].lower() == v.lower() for g in d.groups):
                kind = "group"
            elif "@" in v:
                kind = "user"
            elif v.startswith("/"):
                kind = "ou"
            else:
                kind = "serial"
        if not label:
            if kind == "user":
                u = next((x for x in d.users if x["email"].lower() == v.lower()), {})
                label = u.get("name") or v
            elif kind == "group":
                g = next((x for x in d.groups if x["email"].lower() == v.lower()), {})
                label = g.get("name") or v
            else:
                label = v
        favs = [f for f in self.favorites() if not (f["kind"] == kind and f["value"] == v)]
        favs.insert(0, {"kind": kind, "value": v, "label": label})
        self._save_favorites(favs[:40])
        self.statusBar().showMessage(f"★ Added {label} to favorites")

    def update_favorite(self, old: dict, new: dict):
        favs = self.favorites()
        for i, x in enumerate(favs):
            if x["kind"] == old["kind"] and x["value"] == old["value"]:
                favs[i] = new
                break
        self._save_favorites(favs)

    def rename_favorite(self, f: dict):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Rename favorite", "New name:", text=f["label"])
        if ok and name.strip():
            self.update_favorite(f, {**f, "label": name.strip()})

    def edit_saved_search(self, f: dict):
        """Open the saved search on Users → Find / list users without running it."""
        p = self._users_find_tab()
        if p is not None:
            p.refresh_saved(f["value"])

    def _users_find_tab(self):
        self._go_safe("Users")
        p = self.pages.get("Users")
        if p is None:
            return None
        for tabs in p.findChildren(QTabWidget):
            for i in range(tabs.count()):
                if tabs.tabText(i).startswith("Find"):
                    tabs.setCurrentIndex(i)
                    return p
        return p

    def remove_favorite(self, f: dict):
        self._save_favorites([x for x in self.favorites()
                              if not (x["kind"] == f["kind"] and x["value"] == f["value"])])

    def open_favorite(self, f: dict):
        k, v = f["kind"], f["value"]
        if k == "user":
            self.open_user(v)
        elif k == "group":
            self.open_group(v)
        elif k == "ou":
            self.open_ou(v)
        elif k == "serial":
            self.open_device(v)
        elif k == "search":
            self.open_saved_search(f)

    def do_intent(self, it):
        _label, _words, page, tab = it
        if _label == "Ask the Helper" and hasattr(self, "helper"):
            self.helper.show()
            self.helper.ensure_brain()
            self.helper.input.setFocus()
            return
        self.go(page)
        p = self.pages.get(page)
        if tab and p is not None:
            from PySide6.QtWidgets import QTabWidget
            for tw in p.findChildren(QTabWidget):
                for i in range(tw.count()):
                    if tw.tabText(i).replace("&&", "&") == tab:
                        tw.setCurrentIndex(i)
                        break
        if page == "Student lookup" and p is not None:
            p.who.setFocus()
        if it[0] == "Report a problem":
            from .. import support
            support.ask_and_save(self, output_text=self.log.toPlainText())

    def open_saved_search(self, fav):
        """Run a saved search exactly as it was saved (every org unit, field and option)."""
        if isinstance(fav, str):          # an old caller passing just the query
            fav = next((f for f in self.favorites() if f.get("kind") == "search" and
                        f["value"] == fav), {"kind": "search", "value": fav, "label": fav})
        p = self._users_find_tab()
        if p is not None:
            p.run_saved(fav)

    def _refresh_search(self):
        d = self.directory
        from ..intents import labels
        from .. import user_prefs as up
        favs = [up.recent_label(r) for r in up.recent(8)] + \
            [self.fav_label(f) for f in self.favorites()] + labels()
        items = favs + [f"👤 {u.get('name') or u['email']}  <{u['email']}>" for u in d.users]
        items += [f"👥 {g.get('name') or g['email']}  <{g['email']}>" for g in d.groups]
        items += [f"🏢 {p}" for p in d.ous]
        self.gmodel.setStringList(items)

    def global_go(self, text: str):
        text = (text or "").strip()
        if not text:
            return
        if text.startswith("➜"):
            from ..intents import match
            it = match(text)
            if it:
                self.do_intent(it)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.gsearch.clear)
            return
        if text.startswith("🕘"):
            from .. import user_prefs as up
            r = next((r for r in up.recent() if up.recent_label(r) == text), None)
            if r:
                self.open_recent(r)
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, self.gsearch.clear)
                return
            text = text.lstrip("🕘 ").strip()
        if text.startswith("★"):
            f = next((f for f in self.favorites() if self.fav_label(f) == text), None)
            if f:
                self.open_favorite(f)
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, self.gsearch.clear)
                return
            text = text.lstrip("★ ").strip()
        m = re.search(r"<([^>]+@[^>]+)>", text)
        if text.startswith("👤") and m:
            self.open_user(m.group(1))
        elif text.startswith("👥") and m:
            self.open_group(m.group(1))
        elif text.startswith("🏢"):
            self.open_ou(text[1:].strip())
        elif "@" in text:
            email = text.split()[0]
            if email.lower() in {g["email"].lower() for g in self.directory.groups}:
                self.open_group(email)
            else:
                self.open_user(email)
        elif text.startswith("/"):
            self.open_ou(text)
        elif SERIAL_RE.match(text) and any(c.isdigit() for c in text):
            self.open_device(text.upper())
        else:
            from ..intents import match
            it = match(text)
            if it:
                self.do_intent(it)
            elif ASSET_RE.match(text) and any(c.isdigit() for c in text) and \
                    any(c in "-_.#" for c in text):
                self.open_asset(text)
            elif len(text.split()) >= 3 and hasattr(self, "helper"):
                self.helper.ask(text)        # a sentence → the Helper understands it best
            else:
                self.open_builder(text)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.gsearch.clear)

    # ========================================================= navigation ===
    def remember(self, kind: str, value: str, label: str = ""):
        """Recently viewed (Home and the top of the search box)."""
        from .. import user_prefs as up
        if kind in ("user", "group") and not label:
            src = self.directory.users if kind == "user" else self.directory.groups
            hit = next((x for x in src if x.get("email", "").lower() == value.lower()), {})
            label = hit.get("name") or ""
        up.add_recent(kind, value, label)
        self._refresh_search()
        home = self.pages.get("Home") if self.pages.built("Home") else None
        if home is not None and hasattr(home, "refresh_widget"):
            home.refresh_widget("recent")

    def open_user(self, email: str):
        self.remember("user", email)
        self.go("Users")
        p = self.pages["Users"]
        tabs = p.findChild(QTabWidget)
        if tabs:
            tabs.setCurrentIndex(0)
        p.m_email.setText(email)
        p.user_info()

    def open_group(self, email: str):
        self.remember("group", email)
        self.go("Groups")
        p = self.pages["Groups"]
        p.tabs.setCurrentIndex(0)
        p.open_group(email)

    def open_ou(self, path: str):
        self.remember("ou", path)
        self.go("Org units")
        p = self.pages["Org units"]
        p.path = path
        p._build()

    def open_device(self, serial: str):
        self.remember("device", serial)
        self.go("Chromebooks")
        p = self.pages["Chromebooks"]
        p.tabs.setCurrentIndex(0)
        p.sn.setText(serial)
        p.cros_info()

    def open_asset(self, asset: str):
        self.go("Chromebooks")
        p = self.pages["Chromebooks"]
        p.tabs.setCurrentIndex(0)
        p.find_asset.setText(asset)
        p.by_asset()

    def open_recent(self, r: dict):
        k, v = r["kind"], r["value"]
        if k == "user":
            from .. import ou_map
            u = next((x for x in self.directory.users if x["email"].lower() == v.lower()), {})
            if u and ou_map.is_student(u.get("ou", ""), self.directory.ous):
                self.open_lookup(v)
            else:
                self.open_user(v)
        elif k == "group":
            self.open_group(v)
        elif k == "ou":
            self.open_ou(v)
        elif k == "device":
            self.open_device(v)

    def open_lookup(self, email: str):
        self._go_safe("Student lookup")
        p = self.pages.get("Student lookup")
        if p is not None:
            p.everyone.setChecked(True)
            p.who.setText(email)
            p.lookup()

    def open_builder(self, query: str = "", section: str = ""):
        self.go("Command Builder")
        self.pages["Command Builder"].show_query(query, section)

    def show_csv(self, text: str, title: str = "Results"):
        d = QDialog(self)
        d.setWindowTitle("Results")
        d.resize(1000, 600)
        v = QVBoxLayout(d)
        lab = QLabel(title)
        lab.setWordWrap(True)
        lab.setStyleSheet("font-family:Consolas,monospace;color:#57606a;")
        v.addWidget(lab)
        t = ResultsTable()
        t.load_csv(text)
        v.addWidget(t, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        d.show()

    # ======================================================= right-click ===
    def open_timeline(self, email: str):
        self._go_safe("Account timeline")
        p = self.pages.get("Account timeline")
        if p is not None:
            p.open_for(email)

    def context_actions(self, rows: list[dict]):
        """Actions offered when right-clicking rows in any results table."""
        if not rows:
            return []
        heads = {k.lower(): k for k in rows[0].keys() if k}
        out = []
        groups = {g["email"].lower() for g in self.directory.groups}
        ecol = next((heads[c] for c in EMAIL_COLS if c in heads
                     and "@" in (rows[0].get(heads[c]) or "")), None)
        scol = next((heads[c] for c in SERIAL_COLS if c in heads), None)
        hd = helpdesk_on()
        if ecol:
            emails = [r[ecol] for r in rows if "@" in (r.get(ecol) or "")]
            is_group = all(e.lower() in groups for e in emails)
            one = emails[0] if emails else ""
            if is_group:
                out.append((f"Open group {one}", lambda: self.open_group(one), False))
            else:
                out.append((f"Open {one}", lambda: self.open_user(one), False))
                out.append((f"Timeline for {one}", lambda: self.open_timeline(one), False))
                out.append(("★ Add to favorites", lambda: self.add_favorite(one), False))
                out.append((f"Reset password for {len(emails)} person(s)…",
                            lambda: self.quick_reset(emails), False))
                out.append(("Require password change at next sign-in",
                            lambda: self._quick(["users", ",".join(emails), "update", "user",
                                                 "changepassword", "on"]), False))
                out.append(("Sign out of all sessions",
                            lambda: self._quick_each(emails, ["signout"]), False))
                out.append(("Unsuspend",
                            lambda: self._quick(["users", ",".join(emails), "update", "user",
                                                 "suspended", "off"]), False))
                if not hd:
                    out.append(("Suspend…", lambda: self._confirm_quick(
                        f"Suspend {len(emails)} account(s)?",
                        ["users", ",".join(emails), "update", "user", "suspended", "on"]),
                        True))
            out.append(("Copy email addresses", lambda: self._copy("\n".join(emails)), False))
        if scol:
            sns = [r[scol] for r in rows if r.get(scol)]
            if ecol:
                out.append(("-", None, False))
            out.append((f"Open Chromebook {sns[0]}", lambda: self.open_device(sns[0]), False))
            out.append(("Re-enable", lambda: self._quick(["cros_sn", ",".join(sns), "update",
                                                          "action", "reenable"]), False))
            if not hd:
                out.append(("Disable…", lambda: self._confirm_quick(
                    f"Disable {len(sns)} device(s)?",
                    ["cros_sn", ",".join(sns), "update", "action", "disable"]), True))
        return out

    def _copy(self, text):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    def _quick(self, args):
        self.runner.run(args)

    def _quick_each(self, emails, rest):
        for e in emails:
            self.runner.run(["user", e, *rest])

    def _confirm_quick(self, question, args):
        if QMessageBox.question(self, "Please confirm", question) == QMessageBox.Yes:
            self.runner.run(args)

    def quick_reset(self, emails):
        from .pages.users import random_password
        if QMessageBox.question(self, "Reset password",
                                f"Give {len(emails)} person(s) a new temporary password? "
                                "They'll choose their own at next sign-in.") != QMessageBox.Yes:
            return
        results = []

        def one(e):
            pw = random_password()
            self.runner.run(["update", "user", e, "password", pw, "changepassword", "on"],
                            lambda c, *_: (results.append((e, pw if c == 0 else "FAILED")),
                                           len(results) == len(emails) and self._show_pw(results)))
        for e in emails:
            one(e)

    def _show_pw(self, results):
        text = "\n".join(f"{e}\t{pw}" for e, pw in results)
        box = QMessageBox(self)
        box.setWindowTitle("New passwords")
        box.setText("New temporary passwords (copied to the clipboard):\n\n" + text)
        self._copy(text)
        box.exec()

    # ========================================================== help-desk ===
    @staticmethod
    def _hash(pin: str) -> str:
        return hashlib.sha256(("gambit:" + pin).encode()).hexdigest()

    def enter_helpdesk(self):
        pin, ok = QInputDialog.getText(self, "Help-desk mode",
                                       "Choose a PIN (you'll need it to leave help-desk mode):",
                                       QLineEdit.Password)
        if not ok or not pin.strip():
            return
        settings.set("helpdesk/pin", self._hash(pin.strip()))
        settings.set("helpdesk/on", True)
        self.apply_helpdesk_mode()

    def leave_helpdesk(self):
        pin, ok = QInputDialog.getText(self, "Leave help-desk mode", "PIN:", QLineEdit.Password)
        if not ok:
            return
        if self._hash(pin.strip()) != settings.get("helpdesk/pin", ""):
            QMessageBox.warning(self, "Help-desk mode", "That PIN isn't right.")
            return
        settings.set("helpdesk/on", False)
        self.apply_helpdesk_mode()

    def _user_hidden(self, page_name: str) -> bool:
        """Pages this person chose to hide, or advanced pages when those are switched off."""
        import json
        from .main_window import ADVANCED
        if page_name in ("Home", "Guide", "Settings & Updates"):
            return False
        if page_name == "Ticket queue":
            from ..integrations import ticketing as tk
            if not (tk.configured() and tk.can("list")):
                return True
        try:
            hidden = set(json.loads(settings.get("ui/hidden_pages", "[]") or "[]"))
        except ValueError:
            hidden = set()
        return page_name in hidden or (page_name in ADVANCED and
                                       not settings.get("ui/show_advanced", True))

    def apply_helpdesk_mode(self):
        on = helpdesk_on()
        role = team.my_role()
        apply_helpdesk(on)
        self.hd_btn.setVisible(on)
        from .. import user_prefs as up
        folded = up.collapsed()
        base: dict[int, bool] = {}
        for row, idx in self._row_page.items():
            page_name = self.page_name_at(idx)
            base[row] = ((on and page_name in HELPDESK_HIDDEN) or
                         not team.page_allowed(page_name, role) or
                         self._user_hidden(page_name))
        headers = getattr(self, "_header_row", {})
        sections = getattr(self, "_row_section", {})
        # a heading shows when something under it could show (folded or not)
        seen_under: dict[str, bool] = {}
        for row, hidden in base.items():
            sec = sections.get(row, "")
            seen_under[sec] = seen_under.get(sec, False) or not hidden
        for row in range(self.nav.count()):
            it = self.nav.item(row)
            if row in headers:
                it.setHidden(not seen_under.get(headers[row], False))
            elif row in base:
                it.setHidden(base[row] or sections.get(row, "") in folded)
        for p in self.pages.values():
            if hasattr(p, "set_helpdesk"):
                p.set_helpdesk(on)
            if hasattr(p, "set_role"):
                p.set_role(role)
        current = next((n for n, p in self.pages.items() if p is self.current_page()), "")
        if (on and current in HELPDESK_HIDDEN) or not team.page_allowed(current, role):
            self.go("Home")
        self.statusBar().showMessage("Help-desk mode is on – destructive actions are hidden."
                                     if on else "Help-desk mode is off.")

    # =========================================================== profiles ===
    def refresh_profiles(self):
        self.profile_box.blockSignals(True)
        self.profile_box.clear()
        for p in profiles.profiles():
            self.profile_box.addItem(p["name"])
        self.profile_box.setCurrentText(profiles.current_name())
        self.profile_box.blockSignals(False)
        self.profile_box.setVisible(True)

    def switch_profile(self, name: str):
        if name == profiles.current_name():
            return
        profiles.switch(name)
        self.directory.reload_for_profile()
        sp = self.pages["Settings & Updates"]
        if hasattr(sp, "cfg_dir"):
            sp.cfg_dir.setText(settings.gam_cfg_dir)
        self.pages["Home"].set_connection(None, "Not tested")
        self.statusBar().showMessage(f"Switched to {name}")
        self.refresh_profiles()
        self.test_connection()


# ============================================================================
#  Activity log, undo, preview-before-big-changes, explain, shortcuts, tour
# ============================================================================
class MoreActions:
    def install_activity_hooks(self):
        self._pending_undo_of = ""
        self._approved_request = ""
        self._blocked_batch: list[list[str]] = []
        self.runner.guard = self._guard
        from .. import directory as _dir
        _dir.LOW_LEVEL_GUARD = self._low_level_guard
        self.runner.preflight = self._preflight
        self.runner.on_submit = self._on_submit
        self.runner.on_record = self._on_record

    # -- activity -------------------------------------------------------------
    def _on_submit(self, job):
        from .. import activity
        from ..directory import run_gam_csv
        job.meta["undo"] = None
        if not self._pending_undo_of:
            job.meta["undo"] = (activity.capture_undo(job.args, lambda a: run_gam_csv(a, 60))
                                or activity.infer_undo(job.args, self.directory.users))
        if self._approved_request:
            job.meta["note"] = f"approved request {self._approved_request}"
        if self._pending_undo_of:
            job.meta["undo_of"] = self._pending_undo_of
            job.meta["undo"] = None
            self._pending_undo_of = ""

    def _on_record(self, job):
        from .. import activity
        undo_of = job.meta.get("undo_of", "")
        activity.record(job.args, job.code if job.code is not None else -1, job.status,
                        job.meta.get("undo"), profiles.current_name(), undo_of=undo_of,
                        note=job.meta.get("note", ""))
        if undo_of and job.code == 0:
            activity.mark_undone(undo_of, job.display)
        if job.code == 0:
            self._patch_cache(job.args)

    def _patch_cache(self, args):
        """Keep the cached 'before' state current so later undos know where things were."""
        low = [a.lower() for a in args]
        if low[:2] != ["update", "user"] or len(args) < 5:
            return
        u = next((x for x in self.directory.users if x["email"].lower() == low[2]), None)
        if not u:
            return
        for i in range(3, len(args) - 1):
            if low[i] in ("ou", "org"):
                u["ou"] = args[i + 1]
            elif low[i] in ("suspended", "suspend"):
                u["suspended"] = low[i + 1] in ("on", "true")

    def run_undo(self, entry: dict):
        steps = entry["undo"].get("steps") or [entry["undo"]["args"]]
        for args in steps:
            self._pending_undo_of = entry["id"]
            if not self.runner.run(args):
                self._pending_undo_of = ""
                break

    # -- roles and approvals ---------------------------------------------------
    def _guard(self, args) -> bool:
        from .. import team
        from ..auth import session
        if session.active():
            session.touch()
            why = self._access_problem(list(args))
            if why:
                self.log_line(f"✖ Not run – {why}", "#ff8a80")
                if not getattr(self, "_batch_ok", False):
                    QMessageBox.information(self, "Not allowed", why[:1].upper() + why[1:])
                return False
        if self._approved_request:
            return True
        if not self._freeze_ok(list(args)):
            return False
        ok, missing, can_ask = team.check(args)
        if ok:
            return True
        if can_ask and team.folder():
            try:
                from .. import approval_policy
                rule = approval_policy.auto_rule(list(args), self.directory.users)
            except Exception:  # noqa: BLE001
                rule = ""
            if rule:
                try:
                    approval_policy.log_auto(list(args), rule)
                except Exception:  # noqa: BLE001
                    pass
                self.log_line(f"✔ Allowed by the approval rules ({rule}).", "#7cc4ff")
                return True
        what = "\n".join(f"• {team.CATEGORIES[m]}" for m in sorted(missing))
        role = team.my_role_name()
        if getattr(self, "_batch_ok", False):
            if can_ask and team.folder():
                self._blocked_batch.append(list(args))
            return False
        if not (can_ask and team.folder()):
            QMessageBox.information(self, "Not allowed",
                                    f"Your GAMbit role ({role}) can't do this:\n\n{what}\n\n"
                                    "Ask a Full admin if you need it.")
            return False
        self.request_approval([list(args)], what)
        return False

    def _low_level_guard(self, args) -> str:
        """Checks for GAM calls made from background workers (no dialogs here)."""
        from .. import team
        from ..activity import is_change
        from ..auth import session
        if not session.active() or not is_change(args):
            return ""
        if session.expired():
            return "your GAMbit sign-in has ended – sign in again."
        ok, missing, _ask = team.check(args)
        if not ok:
            return "your GAMbit role doesn't allow: " + ", ".join(
                team.CATEGORIES[m] for m in sorted(missing))
        return self._access_problem(args)

    def _access_problem(self, args) -> str:
        """Sign-in checks: view-only pages and org-unit scope ('' when fine)."""
        from .. import profiles, team
        from ..activity import is_change, strip_config
        from ..auth import session
        role = session.current().get("role") or {}
        prof = role.get("gam_profile", "")
        first = (strip_config(list(args))[:1] or [""])[0].lower()
        if prof:
            if profiles.current_name() != prof:
                return (f"your GAMbit role must use the GAM profile “{prof}”, which isn't set "
                        "up on this computer (ask a GAMbit admin).")
            if first in ("select", "config") or (args and str(args[0]).lower() in
                                                 ("select", "config")):
                return "your GAMbit role can't switch GAM settings or profiles."
        change = is_change(args)
        if not change and not session.scope():
            return ""
        page = getattr(self, "_current_page_name", "")
        if change and page and team.page_view_only(page):
            return f"your GAMbit role can only view the {page} page, not change things there."
        if not session.scope():
            return ""
        by_email = {u["email"].lower(): u for u in (self.directory.all_users or
                                                    self.directory.users)}
        cache: dict = {}

        def cros_ou(kind, v):
            if (kind, v) not in cache:
                from ..directory import run_gam_csv
                ent = ["cros_sn", v] if kind == "cros" else ["cros", v]
                try:
                    c, rows, _e = run_gam_csv(ent + ["print", "cros", "fields",
                                                     "orgunitpath"], 60)
                except Exception:  # noqa: BLE001
                    c, rows = 1, []
                cache[(kind, v)] = rows[0].get("orgUnitPath") if c == 0 and rows else None
            return cache[(kind, v)]
        what = session.scope_problem(args, by_email, cros_ou, change)
        if what:
            return (f"not allowed with your org units ({', '.join(session.scope())}): "
                    f"{what}.")
        return ""

    def _freeze_ok(self, args) -> bool:
        """Change freezes: block risky changes in a freeze window unless an admin overrides
        (once per freeze for 15 minutes, with a reason that's logged)."""
        import time
        from .. import change_queue, team
        try:
            f = change_queue.active_freeze(args)
        except Exception:  # noqa: BLE001
            return True
        if not f:
            return True
        ok_until = getattr(self, "_freeze_override", {}).get(f["id"], 0)
        if ok_until > time.time():
            change_queue.log_override(args, f, self._freeze_reason.get(f["id"], ""), team.me())
            return True
        if not team.is_admin():
            QMessageBox.information(self, "Change freeze",
                                    f"“{f['name']}” is on until {f['end']} – this kind of "
                                    "change is paused. Ask a Full admin, or queue it with "
                                    "Run later.")
            return False
        reason, ok = QInputDialog.getText(
            self, "Change freeze", f"“{f['name']}” is on until {f['end']}.\n\nThis change is "
            "normally paused. Why does it need to happen now? (Your reason is logged.)")
        if not ok or not reason.strip():
            self.log_line(f"Not run – change freeze “{f['name']}”.", "#ff8a80")
            return False
        if not hasattr(self, "_freeze_override"):
            self._freeze_override, self._freeze_reason = {}, {}
        self._freeze_override[f["id"]] = time.time() + 15 * 60
        self._freeze_reason[f["id"]] = reason.strip()
        change_queue.log_override(args, f, reason.strip(), team.me())
        return True

    def request_approval(self, commands: list[list[str]], what: str = ""):
        from .. import team
        from ..gam_runner import display_command
        listing = "\n".join(display_command(c) for c in commands[:8])
        more = f"\n…and {len(commands) - 8} more" if len(commands) > 8 else ""
        reason, ok = QInputDialog.getMultiLineText(
            self, "Ask an admin to approve",
            (f"Your role ({team.my_role_name()}) needs an admin's OK for:\n{what}\n\n"
             if what else "") +
            f"{listing}{more}\n\nWhy is this needed? (the admin sees this)")
        if not ok:
            return
        try:
            team.new_request(commands, reason.strip() or "(no reason given)")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Approval request", f"Couldn't save the request:\n{exc}")
            return
        self.log_line("📨 Sent to an admin for approval – see the Approvals page.", "#7cc4ff")
        QMessageBox.information(self, "Sent for approval",
                                "Sent. An admin will see it on their Approvals page, and you "
                                "can check its status on yours.")
        self.update_approvals_badge()

    def flush_blocked_batch(self):
        """After a multi-step run: one approval request for everything that was held back."""
        cmds, self._blocked_batch = self._blocked_batch, []
        if cmds:
            self.request_approval(cmds, "some steps of what you just ran")

    def update_approvals_badge(self):
        from .. import team
        from .main_window import PAGES
        names = [n for n, _ in PAGES]
        if "Approvals" not in names:
            return
        idx = names.index("Approvals")
        rows = [r for r, i in self._row_page.items() if i == idx]
        if not rows:
            return
        n = team.pending_count() if team.is_admin() else 0
        for row in rows:
            self.nav.item(row).setText(f"Approvals ({n})" if n else "Approvals")
        if hasattr(self, "tray_notify_approvals"):
            self.tray_notify_approvals(n)

    def apply_role(self):
        """Show only the pages this person's role allows."""
        self.apply_helpdesk_mode()

    def _preflight(self, args) -> bool:
        from .. import activity
        limit = int(team.setting("safety/threshold", 10) or 0)
        if not limit or getattr(self, "_batch_ok", False):
            return True
        res = activity.affected(args, self.directory.users, self.directory.groups)
        if not res or res[0] < limit:
            return True
        from ..directory import run_gam_csv
        from .preview_dialog import BigChangeDialog
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            full = activity.affected_list(args, self.directory.users, self.directory.groups,
                                          lambda a: run_gam_csv(a, 120)) or res
        finally:
            QApplication.restoreOverrideCursor()
        return BigChangeDialog(self, args, full[0], full[1]).exec() == QDialog.Accepted

    def daily_tasks(self):
        """Once-a-day background jobs after a successful connection."""
        import datetime
        from .. import activity
        from .widgets import Worker
        today = datetime.date.today().isoformat()
        if settings.get("tasks/last_inapp_daily", "") != today:
            settings.set("tasks/last_inapp_daily", today)
            from .. import offboard
            Worker(offboard.run_due, on_done=lambda lines: [self.log_line("🧹 " + ln)
                                                            for ln in lines],
                   on_error=lambda e: self.log_line(f"Offboarding follow-ups failed: {e}",
                                                    "#ff8a80"))
            if settings.get("selfservice/sheet_url", ""):
                from .. import selfservice
                Worker(selfservice.process, on_done=lambda n: n and self.log_line(
                    f"📨 {n} new staff request(s) – see Approvals."),
                       on_error=lambda e: self.log_line(f"Couldn't read staff requests: {e}"))
        from .. import onboard
        if onboard.pending():
            Worker(onboard.run_retries, on_done=lambda lines: [self.log_line("✉ " + ln)
                                                               for ln in lines],
                   on_error=lambda e: self.log_line(f"Signature retries failed: {e}"))
        last = settings.get("activity/sheet_pushed", "") or ""
        if activity.sheet_url() and (not last or datetime.datetime.now() -
                                     datetime.datetime.fromisoformat(last) >
                                     datetime.timedelta(hours=20)):
            Worker(activity.push_to_sheet, on_done=lambda t: None,
                   on_error=lambda e: self.log_line(f"Couldn't copy the activity log to "
                                                    f"the Google Sheet: {e}"))

    # -- explain ----------------------------------------------------------------
    def explain_command(self, text: str = ""):
        from ..command_catalog import Catalog
        from ..explain import explain
        from PySide6.QtWidgets import QTextBrowser
        if not text:
            text, ok = QInputDialog.getText(self, "Explain a command",
                                            "Paste or type a GAM command:")
            if not ok or not text.strip():
                return
        if not hasattr(self, "_catalog"):
            b = self.pages.get("Command Builder")
            self._catalog = b.catalog if b is not None and b.catalog else Catalog()
        d = QDialog(self)
        d.setWindowTitle("What does this command do?")
        d.resize(760, 560)
        v = QVBoxLayout(d)
        edit = QLineEdit(text)
        view = QTextBrowser()
        view.setHtml(explain(text, self._catalog))
        edit.returnPressed.connect(lambda: view.setHtml(explain(edit.text(), self._catalog)))
        v.addWidget(edit)
        v.addWidget(view, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        d.show()

    # -- shortcuts ---------------------------------------------------------------
    SHORTCUTS = [
        ("Ctrl+K", "Jump to anything (search box at the top)"),
        ("Ctrl+1 … Ctrl+9", "Home, Workflows, Users, Groups, Classroom, Email, Google Drive, "
                            "Chromebooks, Command Builder"),
        ("Ctrl+B", "Command Builder"),
        ("Ctrl+E", "Explain a GAM command"),
        ("Ctrl+H", "Activity log (history)"),
        ("Ctrl+J", "Show the Jobs list"),
        ("Ctrl+L", "Show the Output log"),
        ("Ctrl+.", "Stop the most recent command"),
        ("F5", "Refresh users, groups, org units and the dashboard"),
        ("Ctrl+Enter", "Run (in the Command Builder and Console)"),
        ("Ctrl+Shift+L", "Student lookup"),
        ("Ctrl+Shift+C", "Check everything about the person on Student lookup"),
        ("Ctrl+Shift+P", "Pin this page to My pages (or unpin it)"),
        ("Ctrl+Shift+N", "What's new"),
        ("Ctrl+= / Ctrl+-", "Bigger / smaller text"),
        ("F1", "Open the guide at this page"),
        ("Shift+F1 or Ctrl+/", "This list of shortcuts"),
    ]

    def install_shortcuts(self):
        from PySide6.QtGui import QKeySequence, QShortcut

        def sc(keys, fn):
            QShortcut(QKeySequence(keys), self, activated=fn)
        sc("Ctrl+K", lambda: (self.gsearch.setFocus(), self.gsearch.selectAll()))
        order = ["Home", "Workflows", "Users", "Groups", "Classroom", "Email", "Google Drive",
                 "Chromebooks", "Command Builder"]
        for i, name in enumerate(order, start=1):
            sc(f"Ctrl+{i}", lambda n=name: self._go_safe(n))
        sc("Ctrl+B", lambda: self._go_safe("Command Builder"))
        sc("Ctrl+E", lambda: self.explain_command())
        sc("Ctrl+H", lambda: self._go_safe("Activity log"))
        sc("Ctrl+J", lambda: self.bottom_tabs.setCurrentIndex(1))
        sc("Ctrl+L", lambda: self.bottom_tabs.setCurrentIndex(0))
        sc("Ctrl+.", self.runner.stop)
        sc("F5", self.refresh_everything)
        sc("F1", self.open_guide)
        sc("F2", lambda: self.helper.toggle())
        sc("Shift+F1", self.show_help)
        sc("Ctrl+/", self.show_help)
        sc("Ctrl+Shift+L", lambda: self._go_safe("Student lookup"))
        sc("Ctrl+Shift+C", self._check_current_person)
        sc("Ctrl+Shift+P", self._pin_current)
        sc("Ctrl+Shift+N", lambda: self.show_whats_new(force=True))
        sc("Ctrl+=", lambda: self._bump_text(+1))
        sc("Ctrl++", lambda: self._bump_text(+1))
        sc("Ctrl+-", lambda: self._bump_text(-1))
        b = self.pages.get("Command Builder")
        if b is not None:
            QShortcut(QKeySequence("Ctrl+Return"), b, activated=b.run_preview)
        c = self.pages.get("Command Console")
        if c is not None:
            QShortcut(QKeySequence("Ctrl+Return"), c, activated=c.execute)

    TEXT_SIZES = (0.9, 1.0, 1.15, 1.3, 1.5)

    def _bump_text(self, step: int):
        cur = float(settings.get("ui/text_scale", 1.0) or 1.0)
        i = min(range(len(self.TEXT_SIZES)), key=lambda k: abs(self.TEXT_SIZES[k] - cur))
        i = max(0, min(len(self.TEXT_SIZES) - 1, i + step))
        self.set_text_scale(self.TEXT_SIZES[i])
        self.statusBar().showMessage(f"Text size {int(self.TEXT_SIZES[i] * 100)}%", 3000)

    def _current_name(self) -> str:
        cur = self.current_page()
        return next((n for n, p in self.pages.items() if p is cur), "")

    def _pin_current(self):
        n = self._current_name()
        if n and n != "Home":
            self.toggle_pin(n)

    def _check_current_person(self):
        p = self.pages.get("Student lookup")
        if p is None:
            return
        if self._current_name() != "Student lookup":
            self._go_safe("Student lookup")
        if "@" in p.who.email():
            p.check_all()

    def show_whats_new(self, force: bool = False):
        from .. import whats_new
        from .whats_new_dialog import WhatsNewDialog
        items = whats_new.ENTRIES if force else whats_new.unseen()
        if items:
            WhatsNewDialog(self, items).exec()
            whats_new.mark_seen([e["id"] for e in items])

    def send_feedback(self):
        from .. import support
        support.send_feedback(self, output_text=self.log.toPlainText())

    def _go_safe(self, name):
        from .app_actions import HELPDESK_HIDDEN
        if (helpdesk_on() and name in HELPDESK_HIDDEN) or not team.page_allowed(name):
            return
        self.go(name)

    def refresh_everything(self):
        d = self.directory
        d.refresh_ous(log=self.log_line)
        d.refresh_users(log=self.log_line)
        d.refresh_groups(log=self.log_line)
        self.pages["Home"].refresh_dashboard()

    def open_guide(self, page_name: str = ""):
        """F1: the Guide, opened at the page you're on."""
        g = self.pages.get("Guide")
        if g is None:
            self.show_help()
            return
        cur = self.current_page()
        name = page_name or next((n for n, p in self.pages.items() if p is cur), "")
        self.go("Guide")
        g.show_page(name if name != "Guide" else "")

    def show_help(self):
        rows = "".join(f"<tr><td style='padding:4px 14px 4px 0'><b>{k}</b></td><td>{v}</td></tr>"
                       for k, v in self.SHORTCUTS)
        box = QMessageBox(self)
        box.setWindowTitle("Keyboard shortcuts")
        box.setTextFormat(Qt.RichText)
        box.setText(f"<table>{rows}</table><p>Tip: right-click any results table for "
                    "quick actions.</p>")
        tour = box.addButton("Take the tour", QMessageBox.ActionRole)
        new = box.addButton("What's new", QMessageBox.ActionRole)
        fb = box.addButton("Send feedback…", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if box.clickedButton() is tour:
            self.start_tour()
        elif box.clickedButton() is new:
            self.show_whats_new(force=True)
        elif box.clickedButton() is fb:
            self.send_feedback()

    # -- text size ------------------------------------------------------------------
    def set_theme(self, mode: str):
        """light | dark | system – switches right away."""
        from PySide6.QtWidgets import QApplication
        from .theme import apply_theme
        settings.set("ui/theme", mode)
        app = QApplication.instance()
        apply_theme(app)
        from PySide6.QtWidgets import QWidget
        for w in QApplication.allWidgets():
            try:
                w.style().unpolish(w)
                w.style().polish(w)
                QWidget.update(w)          # some widgets have their own update(…)
            except Exception:  # noqa: BLE001
                continue
        if hasattr(self, "pages") and "Home" in self.pages and \
                hasattr(self.pages["Home"], "on_show"):
            try:
                self.pages["Home"].on_show()
            except Exception:  # noqa: BLE001
                pass

    def set_text_scale(self, scale: float):
        from PySide6.QtWidgets import QApplication
        from .theme import apply_theme
        settings.set("ui/text_scale", scale)
        apply_theme(QApplication.instance(), scale)
        if hasattr(self, "side"):
            self.side.setFixedWidth(int(220 * max(1.0, scale)))
        # make every page re-measure its text at the new size
        for w in QApplication.allWidgets():
            w.style().unpolish(w)
            w.style().polish(w)
            w.updateGeometry()
            if w.layout():
                w.layout().invalidate()

    # -- guided tour ------------------------------------------------------------------
    def start_tour(self):
        Tour(self).start()


class Tour:
    STEPS = [
        (None, "nav", "Pages",
         "Everything is grouped here: People, Services, Admin and Tools. "
         "Ctrl+1 … Ctrl+9 jump to the most-used pages."),
        (None, "gsearch", "Jump to anything",
         "Type a name, group, org unit, Chromebook serial or asset ID and press Enter. Anything else "
         "searches every GAM command. Shortcut: Ctrl+K."),
        ("Home", "tiles", "Your dashboard",
         "Key numbers for your domain, refreshed daily. Click a tile to see the list behind it."),
        ("Workflows", "page", "Workflows",
         "Step-by-step helpers: new staff, staff leaving, year-end rollover and "
         "Chromebook check-in/out."),
        ("Roster sync", "page", "Roster sync",
         "Load your ClassLink (OneRoster) or other SIS export, preview the changes, then "
         "apply them and print password cards."),
        ("Command Builder", "page", "Command Builder",
         "Every GAM command as a fill-in form, with a live preview. Save favourites and "
         "templates, and schedule them."),
        (None, "bottom", "Output and Jobs",
         "Every command shows its output here. Jobs lists everything running in the "
         "background – cancel or re-run from there."),
        ("Activity log", "page", "Activity log",
         "A record of every change: who, when and whether it worked – with Undo for most "
         "changes."),
        (None, "profile", "Domains and help-desk mode",
         "Switch between domains here. Help-desk mode (in Settings) hides risky actions "
         "so office staff can use GAMbit safely."),
    ]

    def __init__(self, app):
        self.app, self.i, self._styled = app, 0, None
        from PySide6.QtWidgets import QDialog
        self.dlg = QDialog(app, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.dlg.setWindowTitle("GAMbit tour")
        self.dlg.setFixedWidth(380)
        v = QVBoxLayout(self.dlg)
        self.head = QLabel("")
        self.head.setStyleSheet("font-size:13pt;font-weight:600;")
        self.text = QLabel("")
        self.text.setWordWrap(True)
        self.pos = QLabel("", objectName="Muted")
        v.addWidget(self.head)
        v.addWidget(self.text)
        row = QHBoxLayout()
        row.addWidget(self.pos, 1)
        self.back = button("Back", slot=lambda: self.go(self.i - 1))
        self.next = button("Next", "primary", lambda: self.go(self.i + 1))
        row.addWidget(self.back)
        row.addWidget(self.next)
        v.addLayout(row)
        self.dlg.finished.connect(lambda *_: self._unstyle())

    def start(self):
        settings.set("tour/seen", True)
        self.go(0)
        self.dlg.show()

    def _target(self, key):
        a = self.app
        return {"nav": a.nav, "gsearch": a.gsearch, "bottom": a.bottom_tabs,
                "profile": a.profile_box,
                "tiles": a.pages["Home"].t.get("accounts") if "Home" in a.pages else None,
                "page": a.current_page()}.get(key)

    def _unstyle(self):
        if self._styled is not None:
            w, old = self._styled
            try:
                w.setStyleSheet(old)
            except RuntimeError:
                pass
            self._styled = None

    def go(self, i):
        if i >= len(self.STEPS):
            self.dlg.close()
            return
        self.i = max(0, i)
        page, key, title, text = self.STEPS[self.i]
        if page and page in self.app.pages:
            self.app.go(page)
        self._unstyle()
        w = self._target(key)
        if w is not None and key != "page":
            self._styled = (w, w.styleSheet())
            w.setStyleSheet(w.styleSheet() + "border:3px solid #f2b705;")
        self.head.setText(title)
        self.text.setText(text)
        self.pos.setText(f"{self.i + 1} of {len(self.STEPS)}")
        self.back.setEnabled(self.i > 0)
        self.next.setText("Finish" if self.i == len(self.STEPS) - 1 else "Next")
        if w is not None:
            g = w.mapToGlobal(w.rect().center())
            self.dlg.adjustSize()
            self.dlg.move(min(g.x() + 40, self.app.geometry().right() - 400),
                          max(self.app.geometry().top() + 40, g.y() - 60))
