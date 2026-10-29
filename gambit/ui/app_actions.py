"""App-wide helpers mixed into MainWindow: jump-to navigation, global search,
right-click actions, results pop-ups, help-desk mode and domain profiles."""

from __future__ import annotations

import hashlib
import re

from PySide6.QtCore import QObject, QStringListModel, Qt, QTimer
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


class _SearchLauncher(QObject):
    """Clicking or typing in the top search box opens the Ctrl+K window (with what you
    typed), which shows people, Chromebooks, pages and actions with icons."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        t = e.type()
        if t == QEvent.MouseButtonPress:
            QTimer.singleShot(0, lambda: self.win.open_palette(obj.text()))
            return True
        if t == QEvent.KeyPress and e.text() and e.text().isprintable() and \
                not e.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
            txt = obj.text() + e.text()
            obj.clear()
            QTimer.singleShot(0, lambda: self.win.open_palette(txt))
            return True
        return False


class AppActions:
    # ============================================================ top bar ===
    def build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(bar)
        h.setContentsMargins(24, 10, 24, 10)
        h.setSpacing(8)
        from .icons import icon, set_icon as _si
        self.back_btn = button("", slot=lambda: self.go_back())
        self.back_btn.setObjectName("Chip")
        _si(self.back_btn, "chevron-left")
        self.back_btn.setProperty("helpdesk_ok", True)
        self.back_btn.hide()
        h.addWidget(self.back_btn)
        self.gsearch = QLineEdit(placeholderText="Search people, Chromebooks, pages or "
                                                 "actions…    Ctrl+K")
        self.gsearch.setObjectName("GlobalSearch")
        self.gsearch.addAction(icon("search"), QLineEdit.LeadingPosition)
        self.gsearch.setMinimumWidth(260)
        self.gmodel = QStringListModel(self)
        comp = QCompleter(self.gmodel, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        comp.setMaxVisibleItems(14)
        comp.activated[str].connect(self.global_go)
        self.gsearch.setCompleter(comp)
        self.gsearch.returnPressed.connect(lambda: self.global_go(self.gsearch.text()))
        self._launcher = _SearchLauncher(self)
        self.gsearch.installEventFilter(self._launcher)
        h.addWidget(self.gsearch, 1)
        h.addSpacing(12)
        self.profile_box = QComboBox(objectName="DomainChip")
        self.profile_box.setMinimumWidth(150)
        self.profile_box.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.profile_box.setToolTip("Which Google Workspace domain (GAM profile) GAMbit "
                                    "works on. The dot shows the connection.")
        self.profile_box.activated.connect(lambda _i: self.switch_profile(
            self.profile_box.currentData() or self.profile_box.currentText()))
        h.addWidget(self.profile_box)
        self.ticket_box = QLineEdit()
        self.ticket_box.setPlaceholderText("Ticket (paste a link or number)")
        self.ticket_box.setToolTip("Link the help-desk ticket you're working on – GAMbit adds a "
                                   "note to it listing what it did.")
        self.ticket_box.setMinimumWidth(260)
        self.ticket_box.editingFinished.connect(self._ticket_changed)
        self.ticket_box.textChanged.connect(lambda _t: self._ticket_chip())
        h.addWidget(self._build_ticket_chip())
        self.refresh_ticket_box()
        self.dry_btn = button("Dry run", slot=lambda: self.set_dry_run(
            self.dry_btn.isChecked()))
        self.dry_btn.setCheckable(True)
        self.dry_btn.setProperty("helpdesk_ok", True)
        self.dry_btn.setToolTip("When on, changes aren't made – GAMbit lists the exact GAM "
                                "commands instead (look-ups still run).")
        h.addWidget(self.dry_btn)
        self.practice_btn = button("Practice", slot=lambda: self.set_practice(
            self.practice_btn.isChecked()))
        self.practice_btn.setCheckable(True)
        self.practice_btn.setProperty("helpdesk_ok", True)
        self.practice_btn.setToolTip("Practice mode for new techs: changes to the test account "
                                     "and test org unit run for real, everything else is a "
                                     "dry run (Settings → Testing).")
        h.addWidget(self.practice_btn)
        self.helper_btn = button("Helper", slot=lambda: self.helper.toggle())
        self.helper_btn.setProperty("helpdesk_ok", True)
        self.helper_btn.setToolTip("Ask GAMbit's offline Helper – plain English is fine "
                                   "(F2)")
        h.addWidget(self.helper_btn)
        self.hd_btn = button("Help-desk mode", slot=self.leave_helpdesk)
        self.hd_btn.setToolTip("Destructive actions are hidden. Click to unlock with the PIN.")
        self.hd_btn.setStyleSheet("background:#fff4ce;border-color:#f2d675;")
        h.addWidget(self.hd_btn)
        from .icons import set_icon
        for btn, ic in ((self.dry_btn, "flask"), (self.practice_btn, "graduation"),
                        (self.helper_btn, "chat"), (self.hd_btn, "lock")):
            set_icon(btn, ic)
            btn.setObjectName("Chip")
        for btn in (self.dry_btn, self.practice_btn, self.helper_btn):
            btn.setText("")              # icon only until switched on (tooltip says what)
            btn.setAccessibleName(btn.toolTip().split(" –")[0].split(":")[0])
        self.simple_btn = button("Leave simple mode", slot=lambda: self.set_simple(False))
        self.simple_btn.setObjectName("ChipGood")
        self.simple_btn.setToolTip("Show every page and the full Home again")
        self.simple_btn.setProperty("helpdesk_ok", True)
        from . import simple_mode as _sm
        self.simple_btn.setVisible(_sm.on())
        h.addWidget(self.simple_btn)
        from .jobs_chip import JobsChip
        self.jobs_chip = JobsChip(self)
        h.addWidget(self.jobs_chip.btn)
        self.bell_btn = button("", slot=self.show_notifications)
        self.bell_btn.setObjectName("Chip")
        set_icon(self.bell_btn, "bell")
        self.bell_btn.setToolTip("Notifications – alerts, finished jobs and pop-ups you missed")
        self.bell_btn.setProperty("helpdesk_ok", True)
        h.addWidget(self.bell_btn)
        self.install_session(h)
        self.refresh_profiles()
        self.directory.connection_changed.connect(lambda *_: self.refresh_profiles())
        for sig in (self.directory.users_changed, self.directory.groups_changed,
                    self.directory.ous_changed):
            sig.connect(self._refresh_search)
        self._refresh_search()
        return bar

    def _build_ticket_chip(self):
        """A ticket icon in the top bar; click it to paste a ticket link or number. Shows
        “#1234” once a ticket is linked."""
        from PySide6.QtWidgets import QMenu, QToolButton, QVBoxLayout, QWidget, QWidgetAction
        from .icons import set_icon
        self.ticket_btn = QToolButton(objectName="Chip")
        self.ticket_btn.setPopupMode(QToolButton.InstantPopup)
        self.ticket_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.ticket_btn.setProperty("helpdesk_ok", True)
        set_icon(self.ticket_btn, "ticket")
        menu = QMenu(self.ticket_btn)
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)
        self.ticket_lbl = QLabel("Link the ticket you're working on – GAMbit adds a note to "
                                 "it listing what it did.", objectName="Muted")
        self.ticket_lbl.setWordWrap(True)
        self.ticket_lbl.setMaximumWidth(300)
        v.addWidget(self.ticket_lbl)
        v.addWidget(self.ticket_box)
        row = QHBoxLayout()
        ok = button("Link", "primary", slot=lambda: (self._ticket_changed(), menu.close()))
        clear = button("Clear", slot=lambda: (self.ticket_box.clear(), menu.close()))
        row.addWidget(ok)
        row.addWidget(clear)
        row.addStretch(1)
        v.addLayout(row)
        act = QWidgetAction(menu)
        act.setDefaultWidget(box)
        menu.addAction(act)
        menu.aboutToShow.connect(lambda: QTimer.singleShot(0, self.ticket_box.setFocus))
        self.ticket_box.returnPressed.connect(menu.close)
        self.ticket_btn.setMenu(menu)
        self._ticket_chip()
        return self.ticket_btn

    def _ticket_chip(self):
        if not hasattr(self, "ticket_btn"):
            return
        from ..integrations import ticketing as tk
        tid = tk.ticket_id(self.ticket_box.text()) if self.ticket_box.text().strip() else ""
        self.ticket_btn.setText(f" #{tid}" if tid else "")
        self.ticket_btn.setToolTip(f"Linked ticket #{tid} – click to change or clear" if tid
                                   else "Link a help-desk ticket (GAMbit adds a note to it)")

    def refresh_ticket_box(self):
        from ..integrations import ticketing as tk
        on = tk.configured() and tk.can("note")
        if hasattr(self, "ticket_btn"):
            self.ticket_btn.setVisible(on)
        if on:
            self.ticket_box.setPlaceholderText(f"{tk.name()} ticket (link or number)")

    def _ticket_changed(self):
        from ..integrations import ticketing as tk
        tid = tk.ticket_id(self.ticket_box.text())
        if not tid or not tk.can("read"):
            return
        Worker(tk.get, tid,
               on_done=lambda t: (self.ticket_btn.setToolTip(
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
               on_done=lambda _r: self.log_line(f"Added a note to the {tk.name()} ticket."),
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
        self._chip_state(self.practice_btn, "ChipGood" if on else "Chip",
                         "Practice is ON" if on else "")
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

    def _chip_state(self, btn, name: str, text: str):
        from .icons import set_icon
        btn.setObjectName(name)
        btn.setText(text)
        btn.setStyleSheet("")
        color = None
        if name != "Chip":
            from .theme import tokens
            t = tokens()
            color = t["banner_warn_text"] if name == "ChipOn" else t["good_text"]
        set_icon(btn, btn.property("_gb_icon") or ("flask" if btn is self.dry_btn
                                                    else "graduation"), color)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def set_dry_run(self, on: bool):
        from .. import user_prefs as up
        if on:
            settings.set("onboard/dry_tried", True)    # the first-day checklist item
        if not on and up.practice_on():
            on = True                    # practice mode keeps dry run on
        settings.set("safety/dry_run", bool(on))
        self.dry_btn.setChecked(bool(on))
        self._chip_state(self.dry_btn, "ChipOn" if on else "Chip",
                         "Dry run is ON" if on else "")
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
        elif k == "view":
            self.open_view_favorite(f)

    def add_view_favorite(self, v: dict):
        favs = [f for f in self.favorites() if not (f["kind"] == "view" and
                                                    f.get("view") == v["id"])]
        favs.insert(0, {"kind": "view", "value": v["page"], "label": v["name"],
                        "view": v["id"], "table": v.get("table", 0),
                        "scope": v.get("scope") or v["page"]})
        self._save_favorites(favs[:40])
        self.statusBar().showMessage(f"Added the view {v['name']} to Home favorites", 5000)

    @staticmethod
    def _reveal(w):
        """Switch every tab between the page and `w` so it's on screen."""
        from PySide6.QtWidgets import QStackedWidget, QTabWidget
        child, par = w, w.parentWidget()
        while par is not None:
            if isinstance(par, QStackedWidget) and isinstance(par.parentWidget(), QTabWidget):
                tabs = par.parentWidget()
                i = tabs.indexOf(child)
                if i >= 0:
                    tabs.setCurrentIndex(i)
            child, par = par, par.parentWidget()

    def open_view_favorite(self, f: dict):
        page = f.get("value", "")
        self._go_safe(page)
        p = self.pages.get(page)
        if p is None:
            return
        scope = f.get("scope") or page
        tables = [t for t in p.findChildren(ResultsTable) if t._title() == scope]
        t = next((t for t in tables if t._table_index() == f.get("table", 0)), None)
        v = next((x for x in t._all_views() if x.get("id") == f.get("view")), None) \
            if t is not None else None
        if v is None:
            self.statusBar().showMessage("That saved view was deleted.", 5000)
            return
        self._reveal(t)
        t.apply_view(v)
        self.statusBar().showMessage(f"View “{v['name']}” – run the search to fill it if "
                                     "the table is empty.", 6000)

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
                        ["users", ",".join(emails), "update", "user", "suspended", "on"],
                        after=lambda: self._suspended_next(emails)), True))
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

    def _confirm_quick(self, question, args, after=None):
        if QMessageBox.question(self, "Please confirm", question) == QMessageBox.Yes:
            self.runner.run(args, (lambda c, *_: c == 0 and after()) if after else None)

    def _suspended_next(self, emails):
        """After suspending: a pop-up with the usual follow-ups."""
        from .next_steps import for_suspended, menu_for
        n = len(emails)
        if hasattr(self, "toasts"):
            self.toasts.show(f"Suspended {emails[0] if n == 1 else f'{n} accounts'}. "
                             "What's next?", "ok", "Next steps",
                             lambda: menu_for(self, for_suspended(self, emails)), ms=12000,
                             remember=False)

    def quick_reset(self, emails):
        from ..gam_runner import dry_run_on
        from .pages.users import random_password
        seen, todo = set(), []
        for e in emails or []:                  # one password per person, not one per row
            e = (e or "").strip()
            if "@" in e and e.lower() not in seen:
                seen.add(e.lower())
                todo.append(e)
        if not todo:
            return
        if QMessageBox.question(self, "Reset password",
                                f"Give {len(todo)} person(s) a new temporary password? "
                                "They'll choose their own at next sign-in.") != QMessageBox.Yes:
            return
        results = []
        dry = dry_run_on()

        def add(e, pw):
            results.append((e, pw))
            if len(results) == len(todo):
                self._show_pw(results, dry)

        def one(e):
            pw = random_password()
            args = ["update", "user", e, "password", pw, "changepassword", "on"]
            really = not self.runner.would_hold_back(args)
            ok = self.runner.run(args, lambda c, *_: add(
                e, (pw if really else "(dry run – not changed)") if c == 0 else "FAILED"))
            if not ok:
                add(e, "NOT RUN")
        for e in todo:
            one(e)

    def _show_pw(self, results, dry=False):
        if dry and all(not pw or pw.startswith("(") or pw in ("FAILED", "NOT RUN")
                       for _e, pw in results):
            QMessageBox.information(self, "New passwords", "Dry run – no passwords were "
                                    "changed. Turn off Dry run to reset them for real.")
            return
        text = "\n".join(f"{e}\t{pw}" for e, pw in results)
        box = QMessageBox(self)
        box.setWindowTitle("New passwords")
        box.setText("New temporary passwords (copied to the clipboard – it's cleared again in "
                    "a minute and kept out of clipboard history):\n\n" + text)
        from .secure_clip import copy_secret
        copy_secret(text)
        box.exec()

    # ========================================================== help-desk ===
    @staticmethod
    def _hash(pin: str) -> str:
        """Old (unsalted) PIN hash – only used to recognise PINs saved by older versions."""
        return hashlib.sha256(("gambit:" + pin).encode()).hexdigest()

    @staticmethod
    def pin_record(pin: str) -> str:
        import json as _j
        from ..auth import crypto
        return _j.dumps(crypto.hash_password(pin))

    def pin_ok(self, pin: str) -> bool:
        """Check the help-desk PIN (scrypt, salted); old SHA-256 PINs are upgraded."""
        import hmac
        import json as _j
        from ..auth import crypto
        saved = settings.get("helpdesk/pin", "") or ""
        if len(saved) == 64 and all(c in "0123456789abcdef" for c in saved):
            ok = hmac.compare_digest(saved, self._hash(pin))
            if ok:
                settings.set("helpdesk/pin", self.pin_record(pin))
            return ok
        try:
            return crypto.check_password(pin, _j.loads(saved))
        except (ValueError, TypeError):
            return False

    def enter_helpdesk(self):
        pin, ok = QInputDialog.getText(self, "Help-desk mode",
                                       "Choose a PIN of at least 6 characters (you'll need it "
                                       "to leave help-desk mode):", QLineEdit.Password)
        if not ok or not pin.strip():
            return
        if len(pin.strip()) < 6:
            QMessageBox.information(self, "Help-desk mode", "Use at least 6 characters.")
            return
        settings.set("helpdesk/pin", self.pin_record(pin.strip()))
        settings.set("helpdesk/fails", 0)
        settings.set("helpdesk/on", True)
        self.apply_helpdesk_mode()

    def leave_helpdesk(self):
        import time as _t
        locked = float(settings.get("helpdesk/locked_until", 0) or 0)
        if _t.time() < locked:
            QMessageBox.warning(self, "Help-desk mode", "Too many wrong PINs – try again in "
                                f"{int(locked - _t.time()) // 60 + 1} minute(s).")
            return
        pin, ok = QInputDialog.getText(self, "Leave help-desk mode", "PIN:", QLineEdit.Password)
        if not ok:
            return
        if not self.pin_ok(pin.strip()):
            fails = int(settings.get("helpdesk/fails", 0) or 0) + 1
            settings.set("helpdesk/fails", fails)
            if fails >= 5:          # 5, then 10, 20… minutes
                settings.set("helpdesk/locked_until",
                             _t.time() + 300 * 2 ** min(fails - 5, 6))
            QMessageBox.warning(self, "Help-desk mode", "That PIN isn't right.")
            return
        settings.set("helpdesk/fails", 0)
        settings.set("helpdesk/locked_until", 0)
        settings.set("helpdesk/on", False)
        self.apply_helpdesk_mode()

    def _user_hidden(self, page_name: str) -> bool:
        """Pages this person chose to hide, or advanced pages when those are switched off."""
        import json
        from .main_window import ADVANCED
        if page_name in ("Home", "Guide", "Settings & Updates"):
            return False
        from . import simple_mode
        if simple_mode.on() and page_name not in simple_mode.PAGES:
            return True
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
        self._apply_nav_visibility(on, role)
        for p in self.pages.values():
            if hasattr(p, "set_helpdesk"):
                p.set_helpdesk(on)
            if hasattr(p, "set_role"):
                p.set_role(role)
        current = next((n for n, p in self.pages.items() if p is self.current_page()), "")
        if (on and current in HELPDESK_HIDDEN) or not team.page_allowed(current, role):
            self.go("Home")
        if getattr(self, "_hd_shown", None) != on:   # say it when it changes, not every time
            if self._hd_shown_once() or on:
                self.statusBar().showMessage(
                    "Help-desk mode is on – destructive actions are hidden." if on else
                    "Help-desk mode is off.", 6000)
            self._hd_shown = on

    def _hd_shown_once(self) -> bool:
        return getattr(self, "_hd_shown", None) is not None

    def _apply_nav_visibility(self, on=None, role=None):
        """Hide rows of folded sections and pages this person can't (or chose not to) see."""
        if on is None:
            on = helpdesk_on()
        if role is None:
            role = team.my_role()
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
        rail = getattr(self, "rail", False)
        for row in range(self.nav.count()):
            it = self.nav.item(row)
            if row in headers:
                it.setHidden(rail or not seen_under.get(headers[row], False))
            elif row in base:
                it.setHidden(base[row] or (not rail and sections.get(row, "") in folded) or
                             (rail and sections.get(row, "") == "MY PAGES"))

    # =========================================================== profiles ===
    def refresh_profiles(self):
        self.profile_box.blockSignals(True)
        self.profile_box.clear()
        cur = profiles.current_name()
        d = getattr(self, "directory", None)
        for p in profiles.profiles():
            label = p["name"]
            if p["name"] == cur and d is not None and d.connected and d.domain:
                label = d.domain if p["name"].lower() == "default" else \
                    f"{p['name']} · {d.domain}"
            self.profile_box.addItem(label, p["name"])
        i = self.profile_box.findData(cur)
        self.profile_box.setCurrentIndex(max(0, i))
        self.profile_box.blockSignals(False)
        self.profile_box.setVisible(True)
        self._profile_dot()

    def _profile_dot(self, *_a):
        from .icons import icon
        d = getattr(self, "directory", None)
        ok = d.connected if d is not None else None
        col = {True: "#22C55E", False: "#EF4444"}.get(ok, "#9CA3AF")
        i = self.profile_box.currentIndex()
        for j in range(self.profile_box.count()):
            self.profile_box.setItemIcon(j, icon("dot-fill", col, 12) if j == i else icon(
                "dot-fill", "#9CA3AF", 12))

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
        _dir.INTERACTIVE = True
        self.runner.preflight = self._preflight
        self.runner.on_submit = self._on_submit
        self.runner.on_record = self._on_record

    # -- activity -------------------------------------------------------------
    def _on_submit(self, job):
        from .. import activity
        from ..directory import run_gam_csv
        job.meta["undo"] = None
        if not self._pending_undo_of:
            cap = activity.capture_undo(job.args, lambda a: run_gam_csv(a, 60))
            if cap and cap.get("none"):
                job.meta["undo"] = None          # looked: nothing would really change
            else:
                job.meta["undo"] = cap or activity.infer_undo(job.args, self.directory.users)
        if self._approved_request:
            job.meta["note"] = f"approved request {self._approved_request}"
        if self._pending_undo_of:
            job.meta["undo_of"] = self._pending_undo_of
            job.meta["undo"] = None
            self._pending_undo_of = ""

    def _on_record(self, job):
        from .. import activity
        undo_of = job.meta.get("undo_of", "")
        entry = activity.record(job.args, job.code if job.code is not None else -1,
                                job.status, job.meta.get("undo"), profiles.current_name(),
                                undo_of=undo_of, note=job.meta.get("note", ""))
        try:
            if activity.is_change(job.args) and hasattr(self, "toasts") and not undo_of:
                self.toasts.change_done(entry, job.code if job.code is not None else -1,
                                        job.display)
        except Exception:  # noqa: BLE001 – a pop-up must never break recording
            pass
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
        prof = (entry.get("profile") or "").strip()
        here = profiles.current_name() or "Default"
        known = {p["name"].lower() for p in profiles.profiles()}
        if prof and prof.lower() != here.lower() and prof.lower() in known:
            msg = (f"That change was made in the “{prof}” domain, but GAMbit is using "
                   f"“{here}” now. Switch to “{prof}” (top bar) and undo it from there.")
            self.log_line(f"✖ Undo not run – {msg}", "#ff8a80")
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Undo", msg)
            except Exception:  # noqa: BLE001
                pass
            return False
        from .. import activity as _act
        allowed, why = _act.undo_allowed(entry)
        if not allowed:
            self.log_line(f"✖ Undo not run – {why}", "#ff8a80")
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Undo", why)
            except Exception:  # noqa: BLE001
                pass
            return False
        steps = entry["undo"].get("steps") or [entry["undo"]["args"]]
        for args in steps:
            self._pending_undo_of = entry["id"]
            try:
                ok = self.runner.run(args)
            finally:
                # run() hands it to on_submit synchronously; if nothing was submitted (dry
                # run, refused, cancelled) it must not stick to the next, unrelated job
                self._pending_undo_of = ""
            if not ok:
                return False
        return True

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
            want = (role.get("gam_cfg_dir") or "").strip()
            if want:
                import os as _os
                have = settings.gam_cfg_dir or ""
                if _os.path.normcase(_os.path.abspath(have or ".")) != \
                        _os.path.normcase(_os.path.abspath(want)):
                    return (f"the GAM profile “{prof}” on this computer doesn't point at the "
                            "GAM settings folder your role requires (ask a GAMbit admin).")
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
        self.log_line("Sent to an admin for approval – see the Approvals page.", "#7cc4ff")
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
            label = f"Approvals ({n})" if n else "Approvals"
            if getattr(self, "rail", False):
                self.nav.item(row).setToolTip(label)
            else:
                self.nav.item(row).setText(label)
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
        dlg = BigChangeDialog(self, args, full[0], full[1])
        ok = dlg.exec() == QDialog.Accepted
        if dlg.later:
            self.queue_tonight(args, dlg.LATER_HOUR)
            return False
        return ok

    def queue_tonight(self, args, hour: int = 18):
        """Put a change in the Run later queue for this evening (or tomorrow evening)."""
        from .. import activity, change_queue
        when = change_queue.tonight(hour)
        title = activity.describe_any(list(args)) or " ".join(args[:4])
        try:
            change_queue.add([list(args)], when, title, team.me())
        except (change_queue.QueueRefused, TimeoutError) as exc:
            QMessageBox.information(self, "Run later", str(exc))
            return
        day = "tonight" if when[:10] == __import__("datetime").date.today().isoformat() \
            else "tomorrow evening"
        msg = f"Queued for {day} at {hour - 12 if hour > 12 else hour} " \
              f"{'PM' if hour >= 12 else 'AM'}: {title[:80]}"
        self.log_line(msg + " (it runs from GAMbit's background task – Schedules → Setup "
                      "& health).", "#7cc4ff")
        if hasattr(self, "toasts"):
            self.toasts.show(msg, "info", "View", lambda: self._go_safe("Run later & freezes"),
                             ms=9000)

    def daily_tasks(self):
        """Once-a-day background jobs after a successful connection."""
        import datetime
        from .. import activity
        from .widgets import Worker
        today = datetime.date.today().isoformat()
        if settings.get("tasks/last_inapp_daily", "") != today:
            settings.set("tasks/last_inapp_daily", today)
            from .. import offboard
            Worker(offboard.run_due, on_done=lambda lines: [self.log_line(ln)
                                                            for ln in lines],
                   on_error=lambda e: self.log_line(f"Offboarding follow-ups failed: {e}",
                                                    "#ff8a80"))
            if settings.get("selfservice/sheet_url", ""):
                from .. import selfservice
                Worker(selfservice.process, on_done=lambda n: n and self.log_line(
                    f"{n} new staff request(s) – see Approvals."),
                       on_error=lambda e: self.log_line(f"Couldn't read staff requests: {e}"))
        from .. import onboard
        if onboard.pending():
            Worker(onboard.run_retries, on_done=lambda lines: [self.log_line(ln)
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
        sc("Ctrl+K", self.open_palette)
        sc("Alt+Left", self.go_back)
        sc("Ctrl+Shift+Z", self.show_changes_today)
        order = ["Home", "Workflows", "Users", "Groups", "Classroom", "Email", "Google Drive",
                 "Chromebooks", "Command Builder"]
        for i, name in enumerate(order, start=1):
            sc(f"Ctrl+{i}", lambda n=name: self._go_safe(n))
        sc("Ctrl+B", lambda: self._go_safe("Command Builder"))
        sc("Ctrl+E", lambda: self.explain_command())
        sc("Ctrl+H", lambda: self._go_safe("Activity log"))
        sc("Ctrl+J", lambda: (self.toggle_output(True), self.bottom_tabs.setCurrentIndex(1)))
        sc("Ctrl+L", lambda: (self.toggle_output(True), self.bottom_tabs.setCurrentIndex(0)))
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

    def open_palette(self, text: str = ""):
        from .palette import CommandPalette
        dlg = CommandPalette(self)
        if text:
            dlg.input.setText(text)
        dlg.exec()

    def refresh_bell(self):
        n = self.notices.unread if hasattr(self, "notices") else 0
        self.bell_btn.setText(f" {n}" if n else "")
        self.bell_btn.setStyleSheet("QPushButton{color:#ffffff;background:#DC2626;"
                                    "border-color:#DC2626;font-weight:700;}" if n else "")
        from .icons import set_icon
        set_icon(self.bell_btn, "bell", "#FFFFFF" if n else None)

    def show_notifications(self):
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu
        from .icons import icon
        m = QMenu(self)
        m.addAction(icon("undo"), "Changes today (with Undo)…  Ctrl+Shift+Z",
                    self.show_changes_today)
        m.addSeparator()
        items = self.notices.items[:25]
        if not items:
            a = m.addAction("No notifications yet")
            a.setEnabled(False)
        icons = {"ok": "check-circle", "bad": "x-circle", "warn": "alert", "info": "bell"}
        for it in items:
            when = it["t"][11:16] if it["t"][:10] == __import__("datetime").date.today(
            ).isoformat() else it["t"][5:10]
            a = m.addAction(icon(icons.get(it.get("level"), "bell")),
                            f"{when}  {it['title']}" + (f" – {it['text']}" if it.get("text")
                                                       else ""))
            if it.get("page"):
                a.triggered.connect(lambda _=False, p=it["page"]: self._go_safe(p))
        if items:
            m.addSeparator()
            m.addAction("Clear all", self.notices.clear)
        self.notices.read_all()
        m.exec(QCursor.pos())

    def set_simple(self, on: bool):
        """Simple mode: a big-button Home and only the everyday pages in the sidebar."""
        from . import simple_mode
        settings.set(simple_mode.KEY, bool(on))
        self.simple_btn.setVisible(bool(on))
        self.build_nav()
        home = self.pages.get("Home")
        if home is not None and hasattr(home, "arrange"):
            home.arrange()
        self.go("Home")
        sp = self.pages.get("Settings & Updates") if self.pages.built("Settings & Updates") \
            else None
        if sp is not None and hasattr(sp, "simple_cb"):
            sp.simple_cb.blockSignals(True)
            sp.simple_cb.setChecked(bool(on))
            sp.simple_cb.blockSignals(False)
        self.statusBar().showMessage("Simple mode is on – the everyday jobs on Home." if on
                                     else "Simple mode is off.", 5000)

    def show_changes_today(self):
        from .changes_today import ChangesToday
        ChangesToday(self).exec()

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
        try:
            from . import icons, winstyle
            icons.refresh_icons()
            if hasattr(self, "build_nav"):
                self.build_nav()
            winstyle.apply(self)
            from .. import user_prefs as up
            dry = bool(settings.get("safety/dry_run", False))
            self._chip_state(self.dry_btn, "ChipOn" if dry else "Chip",
                             "Dry run is ON" if dry else "")
            pr = up.practice_on()
            self._chip_state(self.practice_btn, "ChipGood" if pr else "Chip",
                             "Practice is ON" if pr else "")
            if hasattr(self, "refresh_user_chip"):
                self.refresh_user_chip()
        except Exception:  # noqa: BLE001
            pass
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
            self.side.setFixedWidth(self._side_width())
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
        (None, "nav", "Your pages",
         "Everything is grouped here. Pages you pin (right-click → Pin) and use most sit at "
         "the top under My pages; click a section heading to fold it. The arrow at the "
         "bottom shrinks the sidebar to icons."),
        (None, "gsearch", "Find anything – Ctrl+K",
         "Click here or press Ctrl+K and type a person, Chromebook serial, group, org unit, "
         "page or a task like “reset password”. The actions for a person are listed right "
         "under their name."),
        ("Home", "lookup", "Quick look-up",
         "Type a student, staff member, serial or asset tag. Check everything looks for "
         "every common problem with a person and offers a fix for each."),
        ("Home", "tiles", "At a glance",
         "Key numbers for your domain, with trend lines once GAMbit has a few days of "
         "data. Click a tile for the list behind it."),
        ("Home", "customize", "Make Home yours",
         "Customize lets you drag boxes around, remove them or add others. Simple mode "
         "(Settings → Appearance) turns Home into six big buttons for everyday jobs."),
        ("Users", "table", "Tables",
         "Click a row for a details panel on the right; hover a row for quick buttons and a "
         "copy button. The list button at the end of the toolbar chooses columns, saves "
         "views and prints or saves a PDF."),
        (None, "dry", "Dry run and Practice",
         "Dry run lists the exact GAM commands without changing anything. Practice lets a "
         "new tech make real changes only to the test account and test org unit."),
        (None, "bell", "Alerts and Undo",
         "The bell keeps every alert and pop-up. Changes today (Ctrl+Shift+Z) lists today's "
         "changes with Undo. While commands run, a “running” chip appears next to it."),
        (None, "output", "Output",
         "The output panel starts hidden – pop-ups tell you what happened. Show output (or "
         "Ctrl+L) opens it when you want the details."),
        ("Workflows", "page", "Workflows",
         "Step-by-step jobs: new staff, staff leaving, year-end rollover. Each one ends with "
         "a Review step that lists exactly what will happen before anything runs."),
        (None, "profile", "Domains, help-desk mode and help",
         "The domain chip switches between domains (the dot shows the connection). "
         "Help-desk mode hides risky actions. F1 opens the Guide for the page you're on."),
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
        home = a.pages.get("Home") if hasattr(a, "pages") else None

        def users_table():
            u = a.pages.get("Users")
            return getattr(u, "results", None) if u is not None else None
        targets = {
            "nav": lambda: a.nav, "gsearch": lambda: a.gsearch,
            "bottom": lambda: a.bottom_tabs, "profile": lambda: a.profile_box,
            "tiles": lambda: home.t.get("accounts") if home is not None else None,
            "lookup": lambda: getattr(home, "q_person", None),
            "customize": lambda: getattr(home, "cust_btn", None),
            "table": users_table, "dry": lambda: a.dry_btn, "bell": lambda: a.bell_btn,
            "output": lambda: getattr(a, "out_toggle", None),
            "page": lambda: a.current_page()}
        fn = targets.get(key)
        try:
            return fn() if fn else None
        except Exception:  # noqa: BLE001
            return None

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
        if key == "table":                    # show a tab that has the results table
            u = self.app.pages.get("Users")
            from PySide6.QtWidgets import QTabWidget
            tw = u.findChild(QTabWidget) if u is not None else None
            if tw is not None:
                for i in range(tw.count()):
                    if tw.tabText(i) == "Find / list users":
                        tw.setCurrentIndex(i)
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
