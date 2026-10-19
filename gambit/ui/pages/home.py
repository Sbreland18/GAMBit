from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout,
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
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 8, 0)
        scroll.setWidget(inner)
        self.body.addWidget(scroll)

        self.banner = QLabel("", objectName="Banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        lay.addWidget(self.banner)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.gam_card = self._card("GAM version", "…")
        self.app_card = self._card(f"{APP_NAME} version", __version__)
        self.domain_card = self._card("Connection", "Not tested")
        grid.addWidget(self.gam_card[0], 0, 0)
        grid.addWidget(self.app_card[0], 0, 1)
        grid.addWidget(self.domain_card[0], 0, 2)
        lay.addLayout(grid)

        # ---------------------------------------------------- dashboard ---
        head = QHBoxLayout()
        head.addWidget(QLabel("<b style='font-size:12pt'>At a glance</b>"))
        self.updated = QLabel("", objectName="Muted")
        head.addWidget(self.updated, 1)
        self.refresh_btn = button("Refresh now", slot=self.refresh_dashboard)
        head.addWidget(self.refresh_btn)
        lay.addLayout(head)
        tiles = QGridLayout()
        tiles.setSpacing(12)
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
            ("jobs", "Scheduled jobs", "Open scheduled jobs",
             lambda: self.app.go("Scheduled jobs")),
        ]
        for i, (key, label, hint, fn) in enumerate(spec):
            tile = StatTile(label, hint)
            tile.clicked.connect(fn)
            self.t[key] = tile
            tiles.addWidget(tile, i // 5, i % 5)
        lay.addLayout(tiles)
        from .scorecard_box import scorecard_box
        self.score_box = scorecard_box(self)
        lay.addWidget(self.score_box)

        self.fav_box, fform = self.group("★ Favorites")
        self.fav_row = QHBoxLayout()
        self.fav_row.setSpacing(8)
        fw = QWidget()
        fw.setLayout(self.fav_row)
        fform.addRow(fw)
        lay.addWidget(self.fav_box)
        self.show_favorites()

        box, form = self.group("Quick actions")
        form.addRow(self.row(
            button("Find a user", "primary", lambda: self.app.go("Users")),
            button("New staff / staff leaving", slot=lambda: self.app.go("Workflows")),
            button("Roster sync", slot=lambda: self.app.go("Roster sync")),
            button("Group members", slot=lambda: self.app.go("Groups")),
            button("Out-of-office reply", slot=lambda: self.app.go("Email")),
            button("Look up a Chromebook", slot=lambda: self.app.go("Chromebooks")),
            button("Test connection", slot=self.app.test_connection)))
        lay.addWidget(box)

        box, form = self.group("Getting started")
        steps = QLabel(
            "New to GAM? The <b>Setup wizard</b> installs GAM and connects it to Google "
            "Workspace one step at a time.<br>Already use GAM? It can find your existing "
            "setup too.")
        form.addRow(steps)
        form.addRow(self.row(button("Open setup wizard", "primary", self.app.open_setup),
                             button("Take the tour", slot=self.app.start_tour)))
        lay.addWidget(box)
        lay.addStretch(1)
        self.app.directory.connection_changed.connect(
            lambda ok, text: self.set_connection(ok, text if ok else "Not connected"))
        self.app.directory.users_changed.connect(self._account_tiles)
        self._busy = False
        self.show_dashboard(dashboard.load_cached())

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
        if hasattr(self, "score_box"):
            self.score_box.refresh_scorecard()
        d = self.app.directory
        if d.connected is not None:
            self.set_connection(d.connected, d.domain if d.connected else "Not connected")

    def show_favorites(self):
        while self.fav_row.count():
            it = self.fav_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        favs = self.app.favorites() if hasattr(self.app, "favorites") else []
        self.fav_box.setVisible(bool(favs))
        for f in favs[:12]:
            b = button(self.app.fav_label(f)[2:].split("  <")[0],
                       slot=lambda _=False, f=f: self.app.open_favorite(f))
            b.setToolTip(f"{f['value']} – right-click to remove")
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(
                lambda _p, f=f: self.app.remove_favorite(f)
                if self.confirm(f"Remove {f['label']} from favorites?") else None)
            self.fav_row.addWidget(b)
        self.fav_row.addStretch(1)
