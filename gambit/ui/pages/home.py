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

from ..home_widgets import RecentRow, StatTile


SKU_NAMES = {"1010070001": "Education Fundamentals", "1010310005": "Education Standard",
             "1010310006": "Education Standard (staff)", "1010310008": "Education Plus",
             "1010310009": "Education Plus (staff)",
             "1010310010": "Education Plus (extra student)",
             "1010370001": "Teaching & Learning Upgrade"}


def _grade(g: str) -> str:
    """'7' → '7th Grade', 'K' → 'Kindergarten', '7th Grade' stays."""
    g = str(g).strip()
    if not g.isdigit():
        return {"k": "Kindergarten", "pk": "Pre-K"}.get(g.lower(), g)
    n = int(g)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf} Grade"


def _sku_name(k: str) -> str:
    return SKU_NAMES.get(str(k), str(k))


class HomePage(Page):
    title = ""          # Home has its own greeting
    subtitle = ""
    MAX_W = 1440        # wide screens: keep Home a readable width, centred

    def build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget(objectName="Page")
        outer = QHBoxLayout(inner)
        outer.setContentsMargins(0, 0, 0, 0)
        col = QWidget(objectName="Page")
        self.col, self.scroll = col, scroll
        col.setMaximumWidth(self.MAX_W)
        outer.addStretch(1)
        outer.addWidget(col, 100)
        outer.addStretch(1)
        self.lay = QVBoxLayout(col)
        self.lay.setContentsMargins(8, 6, 14, 28)
        self.lay.setSpacing(18)
        scroll.setWidget(inner)
        head = QHBoxLayout()
        greet = QVBoxLayout()
        greet.setSpacing(2)
        self.greeting = QLabel(self._greeting(), objectName="Greeting")
        self.summary = QLabel("", objectName="Muted")
        greet.addWidget(self.greeting)
        greet.addWidget(self.summary)
        head.addLayout(greet, 1)
        cust = button("Customize", slot=lambda: self.set_editing(True))
        from ..icons import set_icon
        set_icon(cust, "grid")
        cust.setToolTip("Move, add and remove the boxes on Home")
        self.cust_btn = cust
        self.add_btn = button("Add a box", slot=lambda: self.editor.add_menu(self.add_btn))
        set_icon(self.add_btn, "plus")
        self.more_btn = button("More options…", slot=self.customize)
        self.more_btn.setToolTip("Quick actions, number tiles, links and notes")
        self.done_btn = button("Done", "primary", lambda: self.set_editing(False))
        for b in (self.add_btn, self.more_btn, self.done_btn):
            b.hide()
            head.addWidget(b, 0, Qt.AlignBottom)
        head.addWidget(cust, 0, Qt.AlignBottom)
        self.body.addWidget(scroll)
        self.lay.addLayout(head)

        self.banner = QLabel("", objectName="Banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        self.lay.addWidget(self.banner)
        self.sections: dict[str, QWidget] = {}
        self._builders = {
            "attention": self._w_attention,
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
        from ..home_edit import HomeEditor
        self.editor = HomeEditor(self)

    # ------------------------------------------------------- greeting ---
    def _greeting(self) -> str:
        import datetime as _dt
        h = _dt.datetime.now().hour
        part = "morning" if h < 12 else "afternoon" if h < 17 else "evening"
        name = ""
        try:
            from ...auth import session
            if session.active():
                name = (session.current().get("name") or session.email() or "")
            if not name:
                from ... import team
                name = team.me()
        except Exception:  # noqa: BLE001
            name = ""
        name = (name.split("@")[0].replace(".", " ").split() or [""])[0].title() \
            if name else ""
        return f"Good {part}" + (f", {name}" if name else "")

    def _shadow(self, w):
        """A soft card shadow (Home only – few cards, so it stays fast)."""
        try:
            from PySide6.QtGui import QColor
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from ..theme import is_dark
            if is_dark():
                return
            fx = QGraphicsDropShadowEffect(w)
            fx.setBlurRadius(22)
            fx.setOffset(0, 3)
            fx.setColor(QColor(16, 24, 40, 22))
            w.setGraphicsEffect(fx)
        except Exception:  # noqa: BLE001
            pass

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
        from .. import simple_mode
        simple = simple_mode.on()
        if simple:
            if "simple" not in self.sections:
                self.sections["simple"] = simple_mode.SimplePanel(self)
            w = self.sections["simple"]
            w.refresh()
            self.lay.addWidget(w)
            w.show()
        layout_items = hl.layout(self._admin())
        try:
            from ... import onboarding
            if not simple and not onboarding.hidden() and not onboarding.complete(
                    onboarding.items(self.app.directory)):
                layout_items = [{"id": "started", "on": True}] + [
                    x for x in layout_items if x["id"] != "started"]
            elif onboarding.hidden():
                layout_items = [x if x["id"] != "started" else {"id": "started", "on": False}
                                for x in layout_items]
        except Exception:  # noqa: BLE001
            pass
        if simple:   # simple mode: the big buttons, then what you looked at lately
            layout_items = [{"id": "recent", "on": True}]
        if hasattr(self, "cust_btn"):
            self.cust_btn.setVisible(not simple)
            if simple:
                self.summary.setText("Pick a job below – GAMbit asks who or which Chromebook.")
        self._on = {x["id"] for x in layout_items if x["on"]}
        for item in layout_items:
            if not item["on"]:
                continue
            k = item["id"]
            if k not in self.sections:
                self.sections[k] = self._builders[k]()
            w = self.sections[k]
            if not w.property("_shadowed") and k not in ("status", "glance"):
                w.setProperty("_shadowed", True)
                self._shadow(w)
            self.lay.addWidget(w)
            w.show()
            if k == "favorites":
                self.show_favorites()
        self.lay.addStretch(1)
        self._stretch = self.lay.itemAt(self.lay.count() - 1)
        self.apply_tiles()

    def set_editing(self, on: bool):
        self.editor.set_on(on)
        self.cust_btn.setVisible(not on)
        for b in (self.add_btn, self.more_btn, self.done_btn):
            b.setVisible(on)
        self.summary.setText("Drag boxes by ⠿ to move them, or use ↑ ↓ ✕. Click Done when "
                             "you're finished." if on else self.summary.text())
        if not on:
            self._fill_attention()

    def customize(self):
        from ..home_customize import HomeCustomizeDialog
        if HomeCustomizeDialog(self).exec():
            for k in ("quick", "links"):          # rebuilt with the new choices
                w = self.sections.pop(k, None)
                if w is not None:
                    w.deleteLater()
            self.arrange()
            if getattr(self, "editor", None) is not None and self.editor.on:
                self.editor.refresh_bars()

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
        head.addWidget(QLabel("At a glance", objectName="SectionTitle"))
        head.addSpacing(8)
        self.updated = QLabel("", objectName="Muted")
        head.addWidget(self.updated, 1)
        self.refresh_btn = button("Refresh now", slot=self.refresh_dashboard)
        head.addWidget(self.refresh_btn)
        v.addLayout(head)
        self.tiles_grid = QGridLayout()
        self.tiles_grid.setSpacing(14)
        self.t = {}
        spec = [
            ("accounts", "Active accounts", "Open Users", lambda: self._users(0),
             "users", "blue"),
            ("suspended", "Suspended", "List suspended accounts", lambda: self._users(3),
             "user-x", "slate"),
            ("inactive", "No sign-in for 90+ days", "Open the inactive accounts report",
             self._inactive, "clock", "amber"),
            ("never", "Never signed in", "Open the inactive accounts report", self._inactive,
             "login", "violet"),
            ("licenses", "Licenses assigned", "Open Licenses",
             lambda: self.app.go("Licenses"), "id-card", "green"),
            ("cros", "Active Chromebooks", "Open Chromebooks",
             lambda: self.app.go("Chromebooks"), "laptop", "blue"),
            ("expiring", "Chromebooks losing updates", "Open the end-of-updates report",
             self._aue, "calendar-clock", "amber"),
            ("stale", "Chromebooks not seen in 30 days", "List them", self._stale,
             "alert", "amber"),
            ("alerts", "Security alerts (7 days)", "Open alerts", self._alerts,
             "shield", "red"),
            ("jobs", "Scheduled jobs", "Open Schedules",
             lambda: self.app.go("Schedules"), "calendar", "green"),
        ]
        for key, label, hint, fn, ic, colr in spec:
            tile = StatTile(label, hint, ic, colr)
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
        self.fav_box, fform = self.group("Favorites")
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
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, n in enumerate(names):
            b = button(n, slot=lambda _=False, n=n: self._quick(n))
            b.setObjectName("QuickTile")
            from ..icons import set_icon
            set_icon(b, hl.QUICK_ICONS.get(n, "sparkle"), None, 22)
            from PySide6.QtCore import QSize
            b.setIconSize(QSize(22, 22))
            b.setMinimumHeight(56)
            b.setStyleSheet("QPushButton#QuickTile{text-align:left;padding:10px 14px;"
                            "border-radius:12px;font-weight:600;}")
            grid.addWidget(b, i // 4, i % 4)
        w = QWidget()
        w.setLayout(grid)
        form.addRow(w)
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
        from ..home_widgets import BigSearch
        from ..icons import set_icon
        from ..pickers import PersonField
        box, form = self.group("Quick look-up")
        self.q_person = PersonField(self.app.directory,
                                    "A student, staff member, Chromebook serial or asset tag")
        self.q_person.returnPressed.connect(self._q_go)
        self.q_dev = self.q_person          # older code talks to q_dev
        form.addRow(BigSearch(self.q_person))
        look = button("Look up", "primary", self._q_go)
        chk = button("Check everything", slot=self._q_check)
        set_icon(chk, "check-circle")
        rst = button("Reset password", slot=self._q_reset)
        set_icon(rst, "key")
        hint = QLabel("Enter opens a person or Chromebook. Check everything looks for "
                      "problems and offers fixes.", objectName="Muted")
        hint.setWordWrap(True)
        form.addRow(self.row(look, chk, rst, hint))
        return box

    def _q_go(self):
        e = self._q_email()
        if e:
            self.app.open_recent({"kind": "user", "value": e})
            return
        t = self.q_person.text().strip()
        if t and " " not in t:
            self._q_device()
        elif t:
            if hasattr(self.app, "open_palette"):
                self.app.open_palette(t)

    def _q_reset(self):
        e = self._q_email()
        if not e:
            self.info("Type the person first.")
            return
        self.app.open_lookup(e)
        p = self.app.pages.get("Student lookup")
        if p is not None and hasattr(p, "reset"):
            p.reset()

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
        t = self.q_person.text().strip()
        if not t:
            return
        if any(c in t for c in "-_.#") or t.isdigit():
            self.app.open_asset(t)
        else:
            self.app.open_device(t.upper())

    def _w_recent(self):
        box, form = self.group("Recently viewed")
        self.recent_wrap = QWidget()
        self.recent_grid = QGridLayout(self.recent_wrap)
        self.recent_grid.setContentsMargins(0, 0, 0, 0)
        self.recent_grid.setHorizontalSpacing(12)
        self.recent_grid.setVerticalSpacing(2)
        form.addRow(self.recent_wrap)
        self._fill_recent()
        return box

    def _recent_sub(self, r: dict) -> str:
        kind, value = r.get("kind"), r.get("value", "")
        if kind == "user":
            u = next((u for u in getattr(self.app.directory, "users", []) or []
                      if (u.get("email") or "").lower() == value.lower()), None)
            if u:
                bits = []
                try:
                    from ... import ou_map
                    c = ou_map.classify(u.get("ou", "")) if u.get("ou") else {}
                    if c.get("grade"):
                        bits.append(_grade(c["grade"]))
                    if c.get("school"):
                        bits.append(c["school"])
                except Exception:  # noqa: BLE001
                    pass
                if not bits and u.get("ou"):
                    bits.append(u["ou"])
                if u.get("suspended"):
                    bits.insert(0, "Suspended")
                return " · ".join([value] + bits[:2])
            return value
        return {"group": f"Group · {value}", "ou": "Org unit", "device": "Chromebook",
                "serial": "Chromebook",
                "asset": "Chromebook (asset tag)"}.get(kind, value)

    def _fill_recent(self):
        from ... import user_prefs as up
        while self.recent_grid.count():
            it = self.recent_grid.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        items = up.recent(8)
        if not items:
            self.recent_grid.addWidget(QLabel("People, Chromebooks, groups and org units you "
                                              "open show up here.", objectName="Muted"), 0, 0)
            return
        for i, r in enumerate(items):
            title = r.get("label") or r["value"]
            row = RecentRow(title, self._recent_sub(r), r["value"], r.get("kind", ""),
                            r.get("when", ""))
            row.clicked.connect(lambda _=False, r=r: self.app.open_recent(r))
            row.setToolTip(f"{r['value']} – opened {r.get('when', '').replace('T', ' ')}")
            self.recent_grid.addWidget(row, i // 2, i % 2)

    def _w_attention(self):
        box, form = self.group("Needs your attention")
        self.att_wrap = QWidget()
        self.att_lay = QVBoxLayout(self.att_wrap)
        self.att_lay.setContentsMargins(0, 0, 0, 0)
        self.att_lay.setSpacing(8)
        form.addRow(self.att_wrap)
        self._fill_attention()
        return box

    def _attention_items(self) -> list[tuple[str, str, str, object]]:
        """(level, text, button, action) – failed jobs, approvals, unseen Chromebooks,
        alerts, licenses running low."""
        out = []
        try:
            import datetime as _dt
            from ... import tasks_health
            since = _dt.datetime.now() - _dt.timedelta(hours=24)
            bad = [r for r in tasks_health.runs_since(since)
                   if not r.get("ok") and not r.get("skipped")]
            for r in bad[:3]:
                out.append(("bad", f"<b>{tasks_health.label_for(r['key'])}</b> failed "
                            f"({r.get('ended', '')[11:16]})", "View log",
                            lambda: self.app._go_safe("Schedules")))
        except Exception:  # noqa: BLE001
            pass
        try:
            from ... import team
            if team.folder() and team.is_admin():
                n = team.pending_count()
                if n:
                    out.append(("info", f"<b>{n} approval request(s)</b> waiting for you",
                                "Review", lambda: self.app._go_safe("Approvals")))
        except Exception:  # noqa: BLE001
            pass
        for src, page, btn, head in (("gam_keys", "Settings & Updates", "Fix", "GAM's keys"),
                                     ("sso_watch", "Single sign-on", "Fix", "Sign-in"),
                                     ("maildns", "Domain & extras", "Fix", "Email security"),
                                     ("activity", "Activity log", "Check", "Activity log")):
            try:
                import html as _h
                import importlib
                mod = importlib.import_module(f"gambit.{src}")
                fn = mod.integrity_attention if src == "activity" else mod.attention
                for level, text in fn()[:3]:
                    # Qt hands a clicked button's `checked` to the slot – never let it land
                    # in the page name (that was “False is not in list”)
                    out.append(("bad" if level == "bad" else "warn",
                                f"<b>{_h.escape(head, quote=False)}:</b> "
                                f"{_h.escape(text, quote=False)}", btn,
                                lambda *_a, p=page, s=src: self._attention_fix(p, s)))
            except Exception:  # noqa: BLE001
                pass
        d = dashboard.load_cached() or {}
        if d.get("alerts"):
            out.append(("warn", f"<b>{d['alerts']} security alert(s)</b> in the last 7 days",
                        "Open", self._alerts))
        try:
            from ... import digest
            for name, used, total in digest.low_licenses(d.get("license_breakdown") or {}):
                out.append(("warn", f"<b>Licenses at {round(100 * used / total)}%</b> – "
                            f"{name}", "Open", lambda: self.app._go_safe("Licenses")))
        except Exception:  # noqa: BLE001
            pass
        return out

    def _attention_fix(self, page: str, src: str = ""):
        self.app._go_safe(page)
        if src == "gam_keys":            # straight to the fix, not just the page
            sp = self.app.pages.get(page) if hasattr(self.app.pages, "get") else None
            from ... import gam_keys
            if sp is not None and hasattr(sp, "_lock_keys") and \
                    any(lvl == "bad" for lvl, _t in gam_keys.attention()):
                sp._lock_keys()

    def _fill_attention(self):
        if not hasattr(self, "att_lay"):
            return
        while self.att_lay.count():
            it = self.att_lay.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        from ..icons import icon
        from ..theme import is_dark
        items = self._attention_items()
        tint = {"bad": ("#FEF2F2", "#B91C1C", "x-circle"),
                "warn": ("#FFFBEB", "#B45309", "alert"),
                "info": ("#F4F6FA", "#1D4ED8", "shield")}
        if is_dark():
            tint = {"bad": ("#3B1C1C", "#FCA5A5", "x-circle"),
                    "warn": ("#2B2310", "#FCD34D", "alert"),
                    "info": ("#1B2330", "#93C5FD", "shield")}
        for level, text, btn, fn in items:
            row = QFrame(objectName="AttRow")
            bg, fg, ic = tint[level]
            row.setAttribute(Qt.WA_StyledBackground, True)
            row.setStyleSheet(f"QFrame#AttRow{{background:{bg};border-radius:10px;}}")
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 8, 8, 8)
            mark = QLabel()
            mark.setPixmap(icon(ic, fg).pixmap(20, 20))
            h.addWidget(mark)
            lab = QLabel(text)
            lab.setWordWrap(True)
            lab.setStyleSheet("background:transparent;")
            mark.setStyleSheet("background:transparent;")
            h.addWidget(lab, 1)
            h.addWidget(button(btn, slot=fn))
            self.att_lay.addWidget(row)
        if not items:
            ok = QLabel("Nothing needs you right now – background jobs ran and nothing is "
                        "waiting.", objectName="Muted")
            ok.setWordWrap(True)
            self.att_lay.addWidget(ok)
        from .. import simple_mode
        if simple_mode.on():
            self.summary.setText("Pick a job below – GAMbit asks who or which Chromebook.")
            return
        self.summary.setText(f"{len(items)} thing(s) need your attention." if items else
                             "Everything is running smoothly.")

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
        box, form = self.group("My notes")
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
        box, form = self.group("My links")
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
        """The first-day checklist – each item ticks itself off when it's done."""
        box, form = self.group("First-day checklist")
        self.chk_head = QLabel("", objectName="Muted")
        self.chk_head.setWordWrap(True)
        form.addRow(self.chk_head)
        self.chk_wrap = QWidget()
        self.chk_lay = QVBoxLayout(self.chk_wrap)
        self.chk_lay.setContentsMargins(0, 0, 0, 0)
        self.chk_lay.setSpacing(6)
        form.addRow(self.chk_wrap)
        self.chk_hide = button("Hide the checklist", slot=self._hide_checklist)
        form.addRow(self.row(button("Take the tour", slot=self.app.start_tour),
                             self.chk_hide))
        self._tasks_checked = False
        self._fill_checklist()
        return box

    def _checklist_items(self):
        from ... import onboarding
        return onboarding.items(self.app.directory)

    def _fill_checklist(self):
        if not hasattr(self, "chk_lay"):
            return
        from ... import onboarding
        from ..icons import icon
        from ..theme import tokens
        while self.chk_lay.count():
            it = self.chk_lay.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        its = self._checklist_items()
        done, total = onboarding.progress(its)
        self.chk_head.setText(
            "All set – GAMbit is ready. You can hide this checklist." if
            onboarding.complete(its) else
            f"{done} of {total} done. Each item ticks itself off when GAMbit sees it's done.")
        t = tokens()
        for item in its:
            row = QFrame(objectName="CheckRow")
            row.setAttribute(Qt.WA_StyledBackground, True)
            h = QHBoxLayout(row)
            h.setContentsMargins(10, 6, 8, 6)
            h.setSpacing(10)
            mark = QLabel()
            mark.setStyleSheet("background:transparent;")
            mark.setPixmap(icon("check-circle" if item["done"] else "dot",
                                "#16A34A" if item["done"] else t["faint"], 20).pixmap(20, 20))
            h.addWidget(mark, 0, Qt.AlignTop)
            v = QVBoxLayout()
            v.setSpacing(0)
            title = QLabel(item["title"], objectName="RowTitle")
            if item["done"]:
                title.setStyleSheet(f"color:{t['muted']};background:transparent;")
            v.addWidget(title)
            if not item["done"]:
                why = QLabel(item["why"], objectName="RowSub")
                why.setWordWrap(True)
                v.addWidget(why)
            h.addLayout(v, 1)
            if not item["done"]:
                b = button(self.CHECK_ACTIONS.get(item["key"], ("Open", None))[0],
                           slot=lambda _=False, k=item["key"]: self._checklist_do(k))
                h.addWidget(b, 0, Qt.AlignTop)
                if item.get("optional"):
                    skip = button("Just me", slot=self._checklist_solo)
                    skip.setToolTip("I'm the only tech – skip this")
                    h.addWidget(skip, 0, Qt.AlignTop)
            self.chk_lay.addWidget(row)
        if not self._tasks_checked:            # Task Scheduler can be slow: check it once,
            self._tasks_checked = True         # in the background
            Worker(onboarding.tasks_installed,
                   on_done=lambda ok: ok and self._fill_checklist(), on_error=lambda e: None)

    CHECK_ACTIONS = {"gam": ("Open the setup wizard", None), "lists": ("Load them now", None),
                     "schools": ("Map my schools", None), "test": ("Set them", None),
                     "dry": ("Turn on Dry run", None), "pin": ("Show me", None),
                     "tasks": ("Set them up", None), "team": ("Set up a team folder", None)}

    def _checklist_do(self, key: str):
        app = self.app
        if key == "gam":
            app.open_setup()
        elif key == "lists":
            app.refresh_everything()
            self.info("Loading people, groups and org units in the background – this ticks "
                      "itself off when they arrive.")
        elif key == "schools":
            app._go_safe("Settings & Updates")
            sp = app.pages.get("Settings & Updates")
            if sp is not None and hasattr(sp, "open_ou_map"):
                sp.open_ou_map()
        elif key in ("test", "team"):
            app._go_safe("Settings & Updates")
            sp = app.pages.get("Settings & Updates")
            if sp is not None and hasattr(sp, "section_nav"):
                sp.section_nav.search.setText("Testing" if key == "test" else "team folder")
        elif key == "dry":
            app.set_dry_run(True)
        elif key == "pin":
            if hasattr(app, "toasts"):
                app.toasts.show("Right-click any page in the sidebar → Pin to My pages "
                                "(or press Ctrl+Shift+P on the page).", "info", ms=9000,
                                remember=False)
        elif key == "tasks":
            app._go_safe("Schedules")
            p = app.pages.get("Schedules")
            if p is not None and hasattr(p, "show_tab"):
                p.show_tab("Setup & health")
        self._fill_checklist()

    def _checklist_solo(self):
        from ... import onboarding
        from ...settings import settings
        settings.set(onboarding.SOLO_KEY, True)
        self._fill_checklist()

    def _hide_checklist(self):
        from ... import onboarding
        onboarding.set_hidden(True)
        self.arrange()
        if hasattr(self.app, "toasts"):
            self.app.toasts.show("Checklist hidden – Customize → Add a box → First-day "
                                 "checklist brings it back.", "info", ms=7000, remember=False)

    # ---------------------------------------------------------- tiles ---
    def _account_tiles(self):
        users = self.app.directory.users
        if not users:
            return
        s = dashboard.account_stats(users)
        h = dashboard.history
        self.t["accounts"].set(s["active"], f"{s['accounts']:,} accounts in total",
                               trend=h("active"))
        self.t["suspended"].set(s["suspended"], "", trend=h("suspended"))
        if s["has_login_data"]:
            self.t["inactive"].set(s["inactive"], "worth a look" if s["inactive"] else
                                   "everyone has signed in recently",
                                   "warn" if s["inactive"] else "good",
                                   trend=h("inactive"))
            self.t["never"].set(s["never"], "", trend=h("never"))
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
            self.t["licenses"].set(d["licenses"], *self._license_line(d))
        if "cros" in d:
            self.t["cros"].set(d.get("cros_active", 0),
                               f"{d['cros']:,} total · {d.get('cros_disabled', 0):,} disabled",
                               trend=dashboard.history("cros_active"))
            exp, soon = d.get("cros_expired", 0), d.get("cros_expiring", 0)
            self.t["expiring"].set(soon, f"within 12 months · {exp:,} already expired",
                                   "warn" if soon or exp else "good",
                                   trend=dashboard.history("cros_expiring"))
            stale = d.get("cros_stale", 0)
            self.t["stale"].set(stale, "missing or unused?" if stale else "all checking in",
                                "warn" if stale else "good",
                                trend=dashboard.history("cros_stale"))
        if "alerts" in d:
            a = d["alerts"]
            self.t["alerts"].set(a, "review them" if a else "nothing new",
                                 "bad" if a else "good", trend=dashboard.history("alerts"))
        if "jobs" in d:
            f = d.get("jobs_failed", 0)
            self.t["jobs"].set(d["jobs"], f"{f} failed last run" if f else "all ran fine",
                               "bad" if f else ("good" if d["jobs"] else None))

    def _license_line(self, d: dict):
        """(sub text, status, trend, meter) – a meter when you've entered what you bought."""
        from ... import digest
        by = d.get("license_breakdown", {}) or {}
        seats = digest.seats()
        bought = [(k, v, seats.get(str(k).strip().lower())) for k, v in by.items()]
        bought = [(k, v, t) for k, v, t in bought if t]
        if bought:
            used, total = sum(v for _k, v, _t in bought), sum(t for _k, _v, t in bought)
            frac = used / total if total else 0
            return (f"{round(100 * frac)}% of the {total:,} you bought",
                    "warn" if frac >= 0.95 else None, None, frac)
        top = sorted(by.items(), key=lambda x: -x[1])[:2]
        return (" · ".join(f"{_sku_name(k)}: {v:,}" for k, v in top), None,
                dashboard.history("licenses"), None)

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
        self.greeting.setText(self._greeting())
        self._fill_checklist()
        for t in getattr(self, "t", {}).values():
            t.restyle()
        self._fill_attention()
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
                it.widget().hide()
                it.widget().deleteLater()
        favs = self.app.favorites() if hasattr(self.app, "favorites") else []
        self.fav_box.setVisible(bool(favs) and "favorites" in getattr(self, "_on",
                                                                       {"favorites"}))
        for f in favs[:12]:
            b = button(f.get("label") or f["value"],
                       slot=lambda _=False, f=f: self.app.open_favorite(f))
            from ..icons import set_icon
            set_icon(b, {"user": "user", "group": "group", "ou": "building",
                         "serial": "laptop", "search": "search", "view": "table"}.get(
                f.get("kind"), "star"))
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
