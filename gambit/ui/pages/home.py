from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout,
    QWidget,
)

from ... import dashboard
from ...version import APP_NAME, __version__
from ..widgets import Page, Worker, button

STATUS = {"good": ("✔", "#137333"), "warn": ("⚠", "#9a6700"), "bad": ("✖", "#b42318"),
          None: ("", "#57606a")}


class StatTile(QFrame):
    """A clickable hero number with a label and an optional status line."""

    clicked = Signal()

    def __init__(self, label: str, hint: str = ""):
        super().__init__(objectName="Card")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(hint)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(2)
        self.label = QLabel(label, objectName="Muted")
        self.value = QLabel("—", objectName="CardValue")
        self.sub = QLabel("", objectName="Small")
        self.sub.setWordWrap(True)
        v.addWidget(self.label)
        v.addWidget(self.value)
        v.addWidget(self.sub)

    def set(self, value, sub: str = "", status=None):
        self.value.setText(f"{value:,}" if isinstance(value, int) else str(value))
        icon, color = STATUS[status]
        self.sub.setText(f"<span style='color:{color}'>{icon}</span> {sub}" if icon else sub)

    def mousePressEvent(self, e):
        self.clicked.emit()
        super().mousePressEvent(e)


class HomePage(Page):
    title = f"Welcome to {APP_NAME}"
    subtitle = "A friendly front end for GAM, the Google Workspace admin tool."

    def build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget(objectName="Page")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(0, 0, 8, 0)
        scroll.setWidget(inner)
        head = QHBoxLayout()
        head.addStretch(1)
        head.addWidget(button("⚙ Customize Home…", slot=self.customize))
        self.body.addLayout(head)
        self.body.addWidget(scroll)

        self.banner = QLabel("", objectName="Banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        self.lay.addWidget(self.banner)
        self.sections: dict[str, QWidget] = {}
        self._builders = {
            "status": self._w_status, "lookup": self._w_lookup, "jobs": self._w_jobs,
            "approvals": self._w_approvals, "glance": self._w_glance,
            "favorites": self._w_favorites, "recent": self._w_recent, "quick": self._w_quick,
            "tickets": self._w_tickets, "notes": self._w_notes, "links": self._w_links,
            "whatsnew": self._w_whatsnew, "scorecard": self._w_scorecard,
            "started": self._w_started}
        # always build the parts other code talks to (cards, tiles, favorites, jobs)
        for k in ("status", "glance", "favorites", "jobs"):
            self.sections[k] = self._builders[k]()
        self._stretch = None
        self.arrange()
        self.app.directory.connection_changed.connect(
            lambda ok, text: self.set_connection(ok, text if ok else "Not connected"))
        self.app.directory.users_changed.connect(self._account_tiles)
        self._busy = False
        self.show_dashboard(dashboard.load_cached())

    # ------------------------------------------------------- layout ---
    def _admin(self) -> bool:
        try:
            from ... import team
            return team.is_admin() or not team.folder()
        except Exception:  # noqa: BLE001
            return True

    def arrange(self):
        """Lay the boxes out in the order (and with the ones) chosen in Customize Home."""
        from ... import home_layout as hl
        for w in self.sections.values():
            self.lay.removeWidget(w)
            w.hide()
        if self._stretch is not None:
            self.lay.removeItem(self._stretch)
        self._on = {x["id"] for x in hl.layout(self._admin()) if x["on"]}
        for item in hl.layout(self._admin()):
            if not item["on"]:
                continue
            k = item["id"]
            if k not in self.sections:
                self.sections[k] = self._builders[k]()
            w = self.sections[k]
            self.lay.addWidget(w)
            w.show()
            if k == "favorites":
                self.show_favorites()
        self.lay.addStretch(1)
        self._stretch = self.lay.itemAt(self.lay.count() - 1)
        self.apply_tiles()

    def customize(self):
        from ..home_customize import HomeCustomizeDialog
        if HomeCustomizeDialog(self).exec():
            for k in ("quick", "links"):          # rebuilt with the new choices
                w = self.sections.pop(k, None)
                if w is not None:
                    w.deleteLater()
            self.arrange()

    def refresh_widget(self, key: str):
        if key == "recent" and "recent" in self.sections:
            self._fill_recent()

    # ------------------------------------------------------- the boxes ---
    def _w_status(self):
        w = QWidget()
        grid = QGridLayout(w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        self.gam_card = self._card("GAM version", "…")
        self.app_card = self._card(f"{APP_NAME} version", __version__)
        self.domain_card = self._card("Connection", "Not tested")
        grid.addWidget(self.gam_card[0], 0, 0)
        grid.addWidget(self.app_card[0], 0, 1)
        grid.addWidget(self.domain_card[0], 0, 2)
        return w

    def _w_jobs(self):
        from ..jobs_box import JobsBox
        self.jobs_box = JobsBox(self)
        return self.jobs_box

    def _w_glance(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(QLabel("<b style='font-size:12pt'>At a glance</b>"))
        self.updated = QLabel("", objectName="Muted")
        head.addWidget(self.updated, 1)
        self.refresh_btn = button("Refresh now", slot=self.refresh_dashboard)
        head.addWidget(self.refresh_btn)
        v.addLayout(head)
        self.tiles_grid = QGridLayout()
        self.tiles_grid.setSpacing(12)
        self.t = {}
        spec = [
            ("accounts", "Active accounts", "Open Users", lambda: self._users(0)),
            ("suspended", "Suspended", "List suspended accounts", lambda: self._users(3)),
            ("inactive", "No sign-in for 90+ days", "Open the inactive accounts report",
             self._inactive),
            ("never", "Never signed in", "Open the inactive accounts report", self._inactive),
            ("licenses", "Licenses assigned", "Open Licenses",
             lambda: self.app.go("Licenses")),
            ("cros", "Active Chromebooks", "Open Chromebooks",
             lambda: self.app.go("Chromebooks")),
            ("expiring", "Chromebooks losing updates", "Open the end-of-updates report",
             self._aue),
            ("stale", "Chromebooks not seen in 30 days", "List them", self._stale),
            ("alerts", "Security alerts (7 days)", "Open alerts", self._alerts),
            ("jobs", "Scheduled jobs", "Open Schedules",
             lambda: self.app.go("Schedules")),
        ]
        for key, label, hint, fn in spec:
            tile = StatTile(label, hint)
            tile.clicked.connect(fn)
            self.t[key] = tile
        v.addLayout(self.tiles_grid)
        return w

    def apply_tiles(self):
        from ... import home_layout as hl
        if not hasattr(self, "tiles_grid"):
            return
        for t in self.t.values():
            self.tiles_grid.removeWidget(t)
            t.hide()
        for i, key in enumerate(hl.tiles()):
            t = self.t.get(key)
            if t is not None:
                self.tiles_grid.addWidget(t, i // 5, i % 5)
                t.show()

    def _w_scorecard(self):
        from .scorecard_box import scorecard_box
        self.score_box = scorecard_box(self)
        return self.score_box

    def _w_favorites(self):
        self.fav_box, fform = self.group("★ Favorites")
        self.fav_row = QHBoxLayout()
        self.fav_row.setSpacing(8)
        fw = QWidget()
        fw.setLayout(self.fav_row)
        fform.addRow(fw)
        self.show_favorites()
        return self.fav_box

    def _w_quick(self):
        from ... import home_layout as hl
        box, form = self.group("Quick actions")
        names = hl.quick()
        rows = [names[i:i + 6] for i in range(0, len(names), 6)]
        for chunk in rows:
            form.addRow(self.row(*[button(n, "primary" if i == 0 and chunk is rows[0] else "",
                                          lambda _=False, n=n: self._quick(n))
                                   for i, n in enumerate(chunk)]))
        return box

    def _quick(self, name: str):
        from ... import home_layout as hl
        what = hl.QUICK.get(name, "")
        if what.startswith("page:"):
            self.app._go_safe(what[5:])
        elif what == "action:helper" and hasattr(self.app, "helper"):
            self.app.helper.toggle()
        elif what == "action:test":
            self.app.test_connection()
        elif what == "action:refresh":
            self.app.refresh_everything()

    def _w_lookup(self):
        from ..pickers import PersonField
        box, form = self.group("Quick look-up")
        self.q_person = PersonField(self.app.directory, "A person's name or email, then Enter")
        self.q_person.returnPressed.connect(self._q_person)
        self.q_dev = QLineEdit(placeholderText="Chromebook serial or asset ID")
        self.q_dev.returnPressed.connect(self._q_device)
        form.addRow("Person", self.row(self.q_person, button("Look up", "primary",
                                                             self._q_person),
                                       button("✅ Check everything", slot=self._q_check),
                                       stretch=False))
        form.addRow("Chromebook", self.row(self.q_dev, button("Find", slot=self._q_device),
                                           stretch=False))
        return box

    def _q_email(self):
        e = self.q_person.email() or self.q_person.text().strip()
        return e if "@" in e else ""

    def _q_person(self):
        e = self._q_email()
        if e:
            self.app.open_recent({"kind": "user", "value": e})

    def _q_check(self):
        e = self._q_email()
        if not e:
            self.info("Type the person first.")
            return
        from ..person_check_dialog import PersonCheckDialog
        PersonCheckDialog(self, e).exec()

    def _q_device(self):
        t = self.q_dev.text().strip()
        if not t:
            return
        if any(c in t for c in "-_.#") or t.isdigit():
            self.app.open_asset(t)
        else:
            self.app.open_device(t.upper())

    def _w_recent(self):
        box, form = self.group("🕘 Recently viewed")
        self.recent_wrap = QWidget()
        self.recent_grid = QGridLayout(self.recent_wrap)
        self.recent_grid.setContentsMargins(0, 0, 0, 0)
        form.addRow(self.recent_wrap)
        self._fill_recent()
        return box

    def _fill_recent(self):
        from ... import user_prefs as up
        while self.recent_grid.count():
            it = self.recent_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        items = up.recent(12)
        if not items:
            self.recent_grid.addWidget(QLabel("People, Chromebooks, groups and org units you "
                                              "open show up here.", objectName="Muted"), 0, 0)
            return
        for i, r in enumerate(items):
            b = button(up.recent_label(r)[2:].split("  <")[0],
                       slot=lambda _=False, r=r: self.app.open_recent(r))
            b.setToolTip(f"{r['value']} – opened {r.get('when', '').replace('T', ' ')}")
            self.recent_grid.addWidget(b, i // 4, i % 4)

    def _w_approvals(self):
        box, form = self.group("Waiting for approval")
        self.appr_lbl = QLabel("", wordWrap=True)
        form.addRow(self.appr_lbl)
        form.addRow(self.row(button("Open Approvals", slot=lambda: self.app._go_safe(
            "Approvals"))))
        self._fill_approvals()
        return box

    def _fill_approvals(self):
        if not hasattr(self, "appr_lbl"):
            return
        try:
            from ... import team
            if not team.folder():
                self.appr_lbl.setText("Approvals use the team folder (Settings → Team).")
                return
            mine = team.me().lower()
            pend = team.list_requests("pending")
            if team.is_admin():
                txt = (f"<b>{len(pend)}</b> request(s) waiting for you: " +
                       "; ".join(r.get("title", "")[:50] for r in pend[:4]) +
                       ("…" if len(pend) > 4 else "")) if pend else "Nothing waiting."
            else:
                own = [r for r in team.list_requests() if (r.get("by") or "").lower() == mine]
                waiting = [r for r in own if r.get("status") == "pending"]
                done = [r for r in own if r.get("status") in ("approved", "done", "rejected")]
                txt = (f"{len(waiting)} of your request(s) waiting" +
                       (f" · latest decision: {done[0].get('title', '')[:50]} – "
                        f"{done[0].get('status')}" if done else ""))
            self.appr_lbl.setText(txt)
        except Exception as exc:  # noqa: BLE001
            self.appr_lbl.setText(f"Couldn't read approvals: {exc}")

    def _w_tickets(self):
        box, form = self.group("My open tickets")
        self.tk_table = None
        from ...integrations import ticketing as tk
        if not (tk.configured() and tk.can("list")):
            form.addRow(QLabel("Connect your help desk in Settings → Integrations to see "
                               "open tickets here.", objectName="Muted", wordWrap=True))
            return box
        from ..widgets import ResultsTable
        self.tk_table = ResultsTable()
        self.tk_table.setMinimumHeight(160)
        self.tk_status = QLabel("", objectName="Muted")
        form.addRow(self.row(button("Load", slot=self._load_tickets),
                             button("Open Ticket queue", slot=lambda: self.app._go_safe(
                                 "Ticket queue")), self.tk_status))
        form.addRow(self.tk_table)
        return box

    def _load_tickets(self):
        from ...integrations import ticketing as tk
        self.tk_status.setText("Loading…")

        def done(rows):
            cols = ["number", "subject", "for", "kind", "target"]
            self.tk_table.set_rows(cols, [[str(r.get(c, "")) for c in cols]
                                          for r in rows[:50]])
            self.tk_status.setText(f"{len(rows)} open")
        Worker(tk.list_open, on_done=done,
               on_error=lambda e: self.tk_status.setText(str(e)[:120]))

    def _w_notes(self):
        from PySide6.QtWidgets import QPlainTextEdit
        from ... import home_layout as hl
        from ...settings import settings
        box, form = self.group("📝 My notes")
        self.notes = QPlainTextEdit(settings.get(hl.NOTES_KEY, "") or "")
        self.notes.setPlaceholderText("Anything you want to remember – saved as you type, "
                                      "only on this PC.")
        self.notes.setMaximumHeight(140)
        self.notes.textChanged.connect(lambda: settings.set(hl.NOTES_KEY,
                                                            self.notes.toPlainText()))
        form.addRow(self.notes)
        return box

    def _w_links(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from ... import home_layout as hl
        box, form = self.group("🔗 My links")
        links = hl.links()
        if not links:
            form.addRow(QLabel("Add links in Customize Home → Links (Admin console, your "
                               "help desk, the district SIS…).", objectName="Muted",
                               wordWrap=True))
            return box
        bs = [button(n, slot=lambda _=False, u=u: QDesktopServices.openUrl(
            QUrl.fromLocalFile(u) if u.startswith("\\\\") else QUrl(u))) for n, u in links]
        for i in range(0, len(bs), 6):
            form.addRow(self.row(*bs[i:i + 6]))
        return box

    def _w_whatsnew(self):
        from ... import whats_new
        box, form = self.group("What's new")
        n = len(whats_new.unseen())
        top = ", ".join(e["title"] for e in whats_new.ENTRIES[:4])
        form.addRow(QLabel((f"<b>{n} new thing(s)</b> since you last looked. " if n else "") +
                           f"Lately: {top}…", wordWrap=True))
        form.addRow(self.row(button("See what's new", slot=lambda: self.app.show_whats_new(
            force=True))))
        return box

    def _w_started(self):
        box, form = self.group("Getting started")
        steps = QLabel(
            "New to GAM? The <b>Setup wizard</b> installs GAM and connects it to Google "
            "Workspace one step at a time.<br>Already use GAM? It can find your existing "
            "setup too.")
        form.addRow(steps)
        form.addRow(self.row(button("Open setup wizard", "primary", self.app.open_setup),
                             button("Take the tour", slot=self.app.start_tour)))
        return box

    # ---------------------------------------------------------- tiles ---
    def _account_tiles(self):
        users = self.app.directory.users
        if not users:
            return
        s = dashboard.account_stats(users)
        self.t["accounts"].set(s["active"], f"{s['accounts']:,} accounts in total")
        self.t["suspended"].set(s["suspended"], "")
        if s["has_login_data"]:
            self.t["inactive"].set(s["inactive"], "worth a look" if s["inactive"] else
                                   "everyone has signed in recently",
                                   "warn" if s["inactive"] else "good")
            self.t["never"].set(s["never"], "")
        else:
            self.t["inactive"].set("—", "refresh lists in Settings to calculate")
            self.t["never"].set("—", "")

    def show_dashboard(self, d: dict):
        self._account_tiles()
        if not d:
            self.updated.setText("Not loaded yet – click Refresh now")
            return
        age = int((time.time() - d.get("time", 0)) / 60)
        self.updated.setText("updated just now" if age < 2 else
                             f"updated {age} min ago" if age < 120 else
                             f"updated {age // 60} hr ago")
        if "licenses" in d:
            top = sorted(d.get("license_breakdown", {}).items(), key=lambda x: -x[1])[:2]
            self.t["licenses"].set(d["licenses"], " · ".join(f"{k}: {v:,}" for k, v in top))
        if "cros" in d:
            self.t["cros"].set(d.get("cros_active", 0),
                               f"{d['cros']:,} total · {d.get('cros_disabled', 0):,} disabled")
            exp, soon = d.get("cros_expired", 0), d.get("cros_expiring", 0)
            self.t["expiring"].set(soon, f"within 12 months · {exp:,} already expired",
                                   "warn" if soon or exp else "good")
            stale = d.get("cros_stale", 0)
            self.t["stale"].set(stale, "missing or unused?" if stale else "all checking in",
                                "warn" if stale else "good")
        if "alerts" in d:
            a = d["alerts"]
            self.t["alerts"].set(a, "review them" if a else "nothing new",
                                 "bad" if a else "good")
        if "jobs" in d:
            f = d.get("jobs_failed", 0)
            self.t["jobs"].set(d["jobs"], f"{f} failed last run" if f else "all ran fine",
                               "bad" if f else ("good" if d["jobs"] else None))

    def refresh_dashboard(self):
        if self._busy:
            return
        self._busy = True
        self.refresh_btn.setEnabled(False)
        self.updated.setText("Refreshing…")

        def done(d):
            self._busy = False
            self.refresh_btn.setEnabled(True)
            self.show_dashboard(d)

        def failed(e):
            self._busy = False
            self.refresh_btn.setEnabled(True)
            self.updated.setText(f"Couldn't refresh: {e}")
        Worker(dashboard.gather, list(self.app.directory.users), on_done=done, on_error=failed)

    def auto_refresh(self):
        """Called after a successful connection test: refresh if older than a day."""
        d = dashboard.load_cached()
        if not d or time.time() - d.get("time", 0) > 24 * 3600:
            self.refresh_dashboard()

    # ------------------------------------------------------ click-through ---
    def _users(self, mode):
        self.app.go("Users")
        p = self.app.pages["Users"]
        from PySide6.QtWidgets import QTabWidget
        t = p.findChild(QTabWidget)
        if t:
            t.setCurrentIndex(2)
        p.l_mode.setCurrentIndex(mode)
        if mode:
            p.list_users()

    def _inactive(self):
        self.app.go("Reports")
        from PySide6.QtWidgets import QTabWidget
        self.app.pages["Reports"].findChild(QTabWidget).setCurrentIndex(0)
        self.app.pages["Reports"].inactive()

    def _aue(self):
        self.app.go("Reports")
        from PySide6.QtWidgets import QTabWidget
        self.app.pages["Reports"].findChild(QTabWidget).setCurrentIndex(2)
        self.app.pages["Reports"].aue()

    def _stale(self):
        self.app.go("Chromebooks")
        p = self.app.pages["Chromebooks"]
        p.tabs.setCurrentIndex(1)
        p.l_mode.setCurrentIndex(2)
        p.list_devices()

    def _alerts(self):
        self.app.go("More services")
        p = self.app.pages["More services"]
        p.tabs.setCurrentIndex(5)
        p.list_alerts()

    # ----------------------------------------------------------- misc ---
    def _card(self, label, value):
        f = QFrame(objectName="Card")
        v = QVBoxLayout(f)
        v.setContentsMargins(16, 12, 16, 12)
        v.addWidget(QLabel(label, objectName="Muted"))
        val = QLabel(value, objectName="CardValue")
        v.addWidget(val)
        return f, val

    def set_gam_version(self, ver):
        self.gam_card[1].setText(ver or "Not installed")
        if not ver:
            self.show_banner("GAM isn't installed yet (or GAMbit can't find it). "
                             "Open Settings & Updates to install it.")
        else:
            self.banner.hide()

    def show_banner(self, text):
        self.banner.setText(text)
        self.banner.show()

    def set_connection(self, ok, text):
        self.domain_card[1].setText(text)
        color = {True: "#137333", False: "#b42318", None: "#57606a"}[ok]
        self.domain_card[1].setStyleSheet(f"color:{color};")

    def on_show(self):
        if hasattr(self, "recent_grid") and "recent" in self.sections:
            self._fill_recent()
        self._fill_approvals()
        if hasattr(self, "jobs_box"):
            self.jobs_box.refresh()
        if hasattr(self, "score_box"):
            self.score_box.refresh_scorecard()
        d = self.app.directory
        if d.connected is not None:
            self.set_connection(d.connected, d.domain if d.connected else "Not connected")

    def _fav_menu(self, f: dict, b):
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu
        m = QMenu(b)
        m.addAction("Open" if f.get("kind") != "search" else "▶ Run",
                    lambda: self.app.open_favorite(f))
        if f.get("kind") == "search":
            m.addAction("Edit the search…", lambda: self.app.edit_saved_search(f))
        m.addAction("Rename…", lambda: self.app.rename_favorite(f))
        m.addSeparator()
        m.addAction("Remove from favorites", lambda: self.app.remove_favorite(f)
                    if self.confirm(f"Remove {f['label']} from favorites?") else None)
        m.exec(QCursor.pos())

    def show_favorites(self):
        while self.fav_row.count():
            it = self.fav_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        favs = self.app.favorites() if hasattr(self.app, "favorites") else []
        self.fav_box.setVisible(bool(favs) and "favorites" in getattr(self, "_on",
                                                                       {"favorites"}))
        for f in favs[:12]:
            b = button(self.app.fav_label(f)[2:].split("  <")[0],
                       slot=lambda _=False, f=f: self.app.open_favorite(f))
            tip = f["value"]
            if f.get("kind") == "search":
                from ... import saved_searches
                tip = saved_searches.tooltip(f)
            b.setToolTip(f"{tip} – right-click to edit, rename or remove")
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(
                lambda _p, f=f, b=b: self._fav_menu(f, b))
            self.fav_row.addWidget(b)
        self.fav_row.addStretch(1)
