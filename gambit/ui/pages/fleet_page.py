"""Chromebook fleet: carts & classrooms, bulk import, summer collection, AUE planning."""

from __future__ import annotations

from ... import tempfiles as _tf
import csv
import os

from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ... import fleet, team
from ...directory import run_gam_csv
from ...settings import settings
from ..widgets import Page, ResultsTable, Worker, button


def _data_dir() -> str:
    return fleet.data_dir()


def _load_devices():
    """One read of every field the fleet tabs need; shared through fleet_cache."""
    from ... import fleet_cache
    fleet_cache.clear()                 # “Load Chromebooks” always asks Google afresh
    code, rows, err = run_gam_csv(list(fleet_cache.ARGS), timeout=1800)
    if code != 0:
        raise RuntimeError(err.strip().splitlines()[-1] if err.strip() else "GAM failed")
    fleet_cache.store(rows)
    return fleet.devices(rows)


class FleetPage(Page):
    title = "Chromebook fleet"
    subtitle = ("Carts and classrooms at a glance, bulk asset-tag and location updates, "
                "summer collection, and planning for devices that stop getting updates.")

    def build(self):
        self.devs: list[dict] = []
        top = QHBoxLayout()
        self.load_btn = button("Load Chromebooks", "primary", self.load)
        from ... import fleet_cache
        self.runner.finished.connect(lambda _code, cmd: fleet_cache.changed(str(cmd)))
        self.loaded = QLabel("Not loaded yet. Large fleets take a minute or two.",
                             objectName="Muted")
        top.addWidget(self.load_btn)
        top.addWidget(self.loaded, 1)
        self.body.addLayout(top)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._inventory_tab(), "Carts && classrooms")
        self.tabs.addTab(self._import_tab(), "Bulk update from a spreadsheet")
        self.tabs.addTab(self._collection_tab(), "Summer collection")
        self.tabs.addTab(self._aue_tab(), "End of updates planning")
        self.tabs.addTab(self._loaner_tab(), "Loaners")
        self.tabs.addTab(self._repair_tab(), "Repairs")
        self.tabs.addTab(self._labels_tab(), "Labels")
        from .chrome_tabs import AppsTab, HealthTab, PrintersTab
        self.health_tab, self.apps_tab, self.printers_tab = (HealthTab(self), AppsTab(self),
                                                             PrintersTab(self))
        self.tabs.addTab(self.health_tab, "Health")
        self.tabs.addTab(self.apps_tab, "Apps && extensions")
        self.tabs.addTab(self.printers_tab, "Printers")
        from .more_tabs import VersionsTab
        self.versions_tab = VersionsTab(self)
        self.tabs.addTab(self.versions_tab, "OS versions")
        from .automation_tabs import AssignSyncTab
        self.assign_tab = AssignSyncTab(self)
        self.tabs.addTab(self.assign_tab, "Assignment sync")
        from .round19_tabs import AssignedUsersTab
        self.assigned_tab = AssignedUsersTab(self)
        self.tabs.addTab(self.assigned_tab, "Assigned users")
        from .insight_pages import WithdrawnDevicesTab
        self.withdrawn_tab = WithdrawnDevicesTab(self)
        self.tabs.addTab(self.withdrawn_tab, "Withdrawn students' devices")
        from .round10_pages import DeviceHistoryTab
        self.history_tab = DeviceHistoryTab(self)
        self.tabs.addTab(self.history_tab, "Device history")
        from .round12_pages import LostDevicesTab
        self.lost_tab = LostDevicesTab(self)
        self.tabs.addTab(self.lost_tab, "Lost && stolen")
        from .round13_tabs import RedistributeTab
        self.redistribute_tab = RedistributeTab(self)
        self.tabs.addTab(self.redistribute_tab, "Redistribution")
        from .round14_tabs import BatteryForecastTab, DeviceToolsTab, RepeatDamageTab
        self.battery_tab, self.damage_tab, self.devtools_tab = (
            BatteryForecastTab(self), RepeatDamageTab(self), DeviceToolsTab(self))
        self.tabs.addTab(self.battery_tab, "Battery forecast")
        self.tabs.addTab(self.damage_tab, "Repeat damage")
        self.tabs.addTab(self.devtools_tab, "Device tools")
        from .round15_tabs import AssetRegisterTab
        self.asset_tab = AssetRegisterTab(self)
        self.tabs.addTab(self.asset_tab, "Asset register")
        self.body.addWidget(self.tabs, 1)

    def load(self, then=None):
        self.load_btn.setEnabled(False)
        self.loaded.setText("Loading Chromebooks from Google…")

        def done(devs):
            import time as _t
            self.devs = devs
            self.load_btn.setEnabled(True)
            self.loaded.setText(
                f"{len(devs):,} Chromebooks loaded at {_t.strftime('%I:%M %p').lstrip('0')} "
                "– every tab on this page uses this list (Assigned users, Assignment sync, "
                "Redistribution, Asset register, Withdrawn students' devices…), so they "
                "don't need to load again. Load again for the latest.")
            self.show_inventory()
            self.show_aue()
            for i in range(self.tabs.count()):
                tab = self.tabs.widget(i)
                if hasattr(tab, "on_fleet_loaded"):
                    try:
                        tab.on_fleet_loaded()
                    except Exception:  # noqa: BLE001
                        pass
            if callable(then):
                then()

        def failed(e):
            self.load_btn.setEnabled(True)
            self.loaded.setText(f"Couldn't load Chromebooks: {e}")
        Worker(_load_devices, on_done=done, on_error=failed)

    def _need(self, then) -> bool:
        if self.devs:
            return True
        self.load(then)
        return False

    # ---------------------------------------------------------- inventory ---
    def _inventory_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.group_by = QComboBox()
        self.group_by.addItem("Cart / classroom (the device's Location)", "location")
        self.group_by.addItem("Org unit", "ou")
        self.group_by.currentIndexChanged.connect(self.show_inventory)
        self.stale = QSpinBox()
        self.stale.setRange(1, 365)
        self.stale.setValue(30)
        self.stale.setSuffix(" days")
        self.stale.valueChanged.connect(self.show_inventory)
        bar.addWidget(QLabel("Group by"))
        bar.addWidget(self.group_by)
        bar.addWidget(QLabel("Not seen in"))
        bar.addWidget(self.stale)
        bar.addWidget(button("How many should each cart have?…", slot=self._expected))
        bar.addStretch(1)
        lay.addLayout(bar)
        self.inv = ResultsTable()
        self.inv.row_clicked.connect(self._inv_detail)
        lay.addWidget(self.inv, 2)
        lay.addWidget(QLabel("Devices in the selected cart / classroom:"))
        self.inv_devs = ResultsTable()
        lay.addWidget(self.inv_devs, 3)
        return w

    def _expected(self):
        text, ok = QInputDialog.getMultiLineText(
            self, "Expected devices", "One per line, e.g.  Cart 12 = 30",
            settings.get("fleet/expected", "") or "")
        if ok:
            settings.set("fleet/expected", text)
            self.show_inventory()

    def show_inventory(self, *_):
        if not self.devs:
            return
        rows = fleet.inventory(self.devs, self.group_by.currentData(), self.stale.value(),
                               fleet.parse_expected(settings.get("fleet/expected", "") or ""))
        heads = ["Cart / classroom" if self.group_by.currentData() == "location" else
                 "Org unit", "Devices", "Active", "Disabled", "Not seen recently",
                 "Marked missing", "Expected", "Short by"]
        keys = ["group", "devices", "active", "disabled", "not_seen", "marked_missing",
                "expected", "short"]
        self.inv.set_rows(heads, [[str(r[k]) for k in keys] for r in rows])

    def _inv_detail(self, row: dict):
        key = next(iter(row.values()), "")
        by = self.group_by.currentData()
        ds = [d for d in self.devs if ((d["location"] if by == "location" else d["ou"])
                                       or "(not set)") == key]
        self._show_devs(self.inv_devs, ds)

    @staticmethod
    def _show_devs(table, ds):
        heads = ["Serial", "Asset tag", "Location", "Assigned user", "Last user", "Status",
                 "Last seen", "Updates end", "Model", "Org unit", "Notes"]
        table.set_rows(heads, [[d["serial"], d["asset"], d["location"], d["user"],
                                d["recent_user"], d["status"],
                                d["last_sync"].isoformat() if d["last_sync"] else "",
                                d["aue"].isoformat() if d["aue"] else "", d["model"], d["ou"],
                                d["notes"]] for d in ds])

    # ------------------------------------------------------------- import ---
    def _import_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        tip = QLabel("Pick a CSV (Save As → CSV from Excel or Google Sheets) with a Serial "
                     "column plus any of: Asset tag, Location / Cart / Room, Assigned user, "
                     "Notes, Org unit. GAMbit shows what will change first.")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.imp_path = QLineEdit(placeholderText="inventory.csv")
        lay.addLayout(self.row(self.imp_path, button("Browse…", slot=self._imp_browse),
                               button("Preview", "primary", self.imp_preview), stretch=False))
        self.imp_table = ResultsTable()
        lay.addWidget(self.imp_table, 1)
        self.imp_info = QLabel("", objectName="Muted")
        lay.addLayout(self.row(button("Apply the changes", "primary", self.imp_apply),
                               self.imp_info))
        self.imp_plan: list[dict] = []
        return w

    def _imp_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Inventory spreadsheet", "",
                                              "CSV (*.csv);;All files (*)")
        if path:
            self.imp_path.setText(os.path.normpath(path))
            self.imp_preview()

    def imp_preview(self):
        if not self._need(self.imp_preview):
            return
        p = self.imp_path.text().strip()
        if not os.path.isfile(p):
            self.info("Choose the spreadsheet (CSV) first.")
            return
        with open(p, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            self.info("That file has no rows.")
            return
        mapping = fleet.import_mapping(list(rows[0].keys()))
        if not mapping["serial"]:
            self.info("Couldn't find a Serial column.")
            return
        known = {d["serial"].upper(): d for d in self.devs}
        self.imp_plan = fleet.import_commands(rows, mapping, known)
        self.imp_table.set_rows(["Serial", "Changes", "Problem"],
                                [[x["serial"], x["changes"], x["problem"]]
                                 for x in self.imp_plan])
        n = sum(1 for x in self.imp_plan if x["args"] and not x["problem"])
        cols = ", ".join(f"{k} ← “{v}”" for k, v in mapping.items() if v)
        self.imp_info.setText(f"{n} device(s) will be updated. Columns used: {cols}")

    def imp_apply(self):
        todo = [x for x in self.imp_plan if x["args"] and not x["problem"]]
        if not todo:
            self.info("Nothing to change – preview first.")
            return
        if self.confirm(f"Update {len(todo)} Chromebook(s)?"):
            self.run_many([x["args"] for x in todo],
                          lambda codes, _outs: self.info(
                              f"{sum(1 for c in codes if c == 0)} of {len(todo)} updated."),
                          with_codes=True)

    # --------------------------------------------------------- collection ---
    def _collection_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        tip = QLabel("1. Start a collection for an org unit (or everything assigned). "
                     "2. Scan each Chromebook's serial number or asset tag into the box – "
                     "a USB barcode scanner works, it types and presses Enter. "
                     "3. The “Not returned” list shows who still has a device. "
                     "The collection is saved as you go" +
                     (" in the team folder, so several people can scan." if team.folder()
                      else "."))
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.c_status = QLabel("No collection open.")
        lay.addLayout(self.row(button("Start a new collection…", slot=self.c_new),
                               button("Open the current one", slot=self.c_open),
                               self.c_status))
        self.scan = QLineEdit(placeholderText="Scan or type a serial number / asset tag, "
                                              "then Enter")
        self.scan.setStyleSheet("font-size:16pt;padding:8px;")
        self.scan.returnPressed.connect(self.c_scan)
        lay.addWidget(self.scan)
        self.c_last = QLabel("")
        self.c_last.setStyleSheet("font-size:13pt;")
        lay.addWidget(self.c_last)
        from PySide6.QtWidgets import QCheckBox
        self.c_note = QCheckBox("Also write “Collected <date>” into the device's notes")
        self.c_note.setChecked(True)
        lay.addWidget(self.c_note)
        lay.addWidget(QLabel("<b>Not returned yet</b>"))
        self.c_missing = ResultsTable()
        lay.addWidget(self.c_missing, 1)
        lay.addLayout(self.row(button("Email the list…", slot=self.c_email)))
        self.coll = None
        self.c_path = fleet.collection_path(_data_dir())
        return w

    def c_new(self):
        if not self._need(self.c_new):
            return
        scope, ok = QInputDialog.getItem(
            self, "New collection", "Which Chromebooks?",
            ["Everything with an assigned or recent user"] +
            sorted({d["ou"] for d in self.devs if d["ou"]}), 0, False)
        if not ok:
            return
        if scope.startswith("Everything"):
            ds = [d for d in self.devs if d["status"] == "ACTIVE" and
                  (d["user"] or d["recent_user"])]
        else:
            ds = [d for d in self.devs if d["status"] == "ACTIVE" and
                  (d["ou"] == scope or d["ou"].startswith(scope.rstrip("/") + "/"))]
        old = fleet.load_collection(self.c_path)
        if old and not self.confirm(f"Replace the open collection “{old['name']}” "
                                    f"({len(old['collected'])} scanned)?"):
            return
        import datetime
        name = f"Collection {datetime.date.today():%B %Y} – {scope}"
        self.coll = fleet.new_collection(name, ds, scope)
        fleet.save_collection(self.c_path, self.coll)
        self._c_refresh()
        self.scan.setFocus()

    def c_open(self):
        self.coll = fleet.load_collection(self.c_path)
        if not self.coll:
            self.info("There's no collection yet – start one.")
            return
        self._c_refresh()
        self.scan.setFocus()

    def c_scan(self):
        text = self.scan.text()
        self.scan.clear()
        if not self.coll:
            self.coll = fleet.load_collection(self.c_path)
            if not self.coll:
                self.info("Start a collection first.")
                return
        latest = fleet.load_collection(self.c_path) or self.coll   # others may be scanning
        latest["collected"].update(self.coll.get("collected", {}))
        self.coll = latest
        status, msg, serial = fleet.scan(self.coll, text, team.me())
        color = {"ok": "#137333", "again": "#9a6700", "unknown": "#b42318"}.get(status, "")
        self.c_last.setText(f"<span style='color:{color}'>{msg}</span>")
        if status == "ok":
            fleet.save_collection(self.c_path, self.coll)
            if self.c_note.isChecked():
                import datetime
                self.runner.run(["cros_sn", serial, "update", "notes",
                                 f"Collected {datetime.date.today().isoformat()}"])
        elif status == "unknown":
            fleet.save_collection(self.c_path, self.coll)
        self._c_refresh()

    def _c_refresh(self):
        c = self.coll
        if not c:
            return
        missing = fleet.not_returned(c)
        self.c_status.setText(f"<b>{c['name']}</b> · {len(c['collected'])} of "
                              f"{len(c['expected'])} back · {len(missing)} still out")
        self.c_missing.set_rows(["Serial", "Who has it", "Asset tag", "Location"],
                                [[m["serial"], m.get("user", ""), m.get("asset", ""),
                                  m.get("location", "")] for m in missing])

    def c_email(self):
        if not self.coll:
            return
        to, ok = QInputDialog.getText(self, "Email the list", "Send the not-returned list to:",
                                      text=settings.get("alerts/email", "") or "")
        if not ok or "@" not in to:
            return
        from ... import google_io
        path = os.path.join(_tf.folder(), "not-returned.csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            fh.write(fleet.to_csv(fleet.not_returned(self.coll)))
        n = len(fleet.not_returned(self.coll))

        def send():
            args = google_io.email_args(to, f"{self.coll['name']}: {n} not returned",
                                        f"Attached: the {n} Chromebook(s) not returned yet.")
            from ...directory import run_gam_text
            code, out = run_gam_text(args + ["attach", path], 120)
            if code:
                raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else "failed")
        Worker(send, on_done=lambda _r: self.info(f"Sent to {to}."),
               on_error=lambda e: self.info(str(e)))

    # ---------------------------------------------------------------- AUE ---
    def _aue_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.cost = QDoubleSpinBox()
        self.cost.setRange(0, 5000)
        self.cost.setPrefix("$")
        self.cost.setValue(float(settings.get("fleet/cost", 300) or 300))
        self.cost.valueChanged.connect(lambda v: (settings.set("fleet/cost", v),
                                                  self.show_aue()))
        bar.addWidget(QLabel("Replacement cost per device"))
        bar.addWidget(self.cost)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.aue_sum = QLabel("", objectName="Muted")
        self.aue_sum.setWordWrap(True)
        lay.addWidget(self.aue_sum)
        self.aue = ResultsTable()
        self.aue.row_clicked.connect(self._aue_detail)
        lay.addWidget(self.aue, 1)
        self.aue_devs = ResultsTable()
        lay.addWidget(self.aue_devs, 1)
        return w

    def show_aue(self, *_):
        if not self.devs:
            return
        rows = fleet.aue_plan(self.devs, self.cost.value())
        self.aue.set_rows(["School year updates end", "Active devices", "Replacement cost",
                           "Most common models"],
                          [[r["year"], str(r["devices"]), f"${r['cost']:,.0f}", r["models"]]
                           for r in rows])
        total = sum(r["cost"] for r in rows)
        self.aue_sum.setText(f"Replacing every active Chromebook in this list would cost about "
                             f"${total:,.0f} at ${self.cost.value():,.0f} each. Click a year "
                             "to see the devices.")

    def _aue_detail(self, row: dict):
        import datetime
        label = next(iter(row.values()), "")
        today = datetime.date.today()
        ds = []
        for d in self.devs:
            if d["status"] != "ACTIVE" or not d["aue"]:
                continue
            y = d["aue"].year if d["aue"].month <= 6 else d["aue"].year + 1
            lab = "Already expired" if d["aue"] < today else f"{y - 1}-{str(y)[-2:]} school year"
            if lab == label:
                ds.append(d)
        self._show_devs(self.aue_devs, ds)

    # ------------------------------------------------------------ loaners ---
    def _loaner_tab(self):
        from PySide6.QtCore import QDate
        from PySide6.QtWidgets import QDateEdit
        from ..pickers import PersonField
        w = QWidget()
        lay = QVBoxLayout(w)
        tip = QLabel("Check a loaner out to a student or teacher with a due date. GAMbit "
                     "assigns the device to them in Google and notes the due date; overdue "
                     "loaners get a reminder email (now, or every morning from the daily "
                     "background task).")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.l_serial = QLineEdit(placeholderText="Serial number or asset tag (scan it)")
        self.l_user = PersonField(self.directory, "Who gets it")
        self.l_due = QDateEdit(QDate.currentDate().addDays(7))
        self.l_due.setCalendarPopup(True)
        self.l_due.setDisplayFormat("MMM d, yyyy")
        self.l_note = QLineEdit(placeholderText="Note (optional), e.g. their own is in repair")
        lay.addLayout(self.row(self.l_serial, self.l_user, QLabel("due"), self.l_due,
                               stretch=False))
        lay.addLayout(self.row(self.l_note, button("Check out", "primary", self.loan_out),
                               button("Check in", slot=self.loan_in), stretch=False))
        from PySide6.QtWidgets import QCheckBox
        self.l_auto = QCheckBox("Email overdue reminders automatically every morning")
        self.l_auto.setChecked(bool(settings.get("fleet/loaner_reminders", False)))
        self.l_auto.toggled.connect(lambda on: settings.set("fleet/loaner_reminders", on))
        lay.addLayout(self.row(button("Email reminders for overdue loaners now",
                                      slot=self.loan_remind), self.l_auto))
        self.l_table = ResultsTable()
        lay.addWidget(self.l_table, 1)
        self._loan_refresh()
        return w

    def _serial_for(self, text: str) -> str:
        code = text.strip().upper()
        d = next((d for d in self.devs if d["serial"].upper() == code or
                  (d["asset"] or "").upper() == code), None)
        return d["serial"] if d else code

    def _loan_refresh(self):
        loans = fleet.load_list(_data_dir(), "loaners.json")
        late = {id(x) for x in fleet.overdue(loans)}
        rows = [[x["serial"], x["user"], x["out"], x["due"],
                 x["returned"] or ("OVERDUE" if id(x) in late else "out"), x.get("note", ""),
                 x.get("by", "")] for x in reversed(loans)]
        self.l_table.set_rows(["Serial", "Who has it", "Out", "Due", "Returned", "Note",
                               "Checked out by"], rows)

    def loan_out(self):
        serial = self._serial_for(self.l_serial.text())
        user = self.l_user.email()
        if not serial or "@" not in user:
            self.info("Scan the loaner and choose who gets it.")
            return
        loans = fleet.load_list(_data_dir(), "loaners.json")
        if any(x["serial"] == serial.upper() and not x["returned"] for x in loans):
            self.info(f"{serial} is already checked out – check it in first.")
            return
        _rec, cmds = fleet.loaner_out(loans, serial, user,
                                      self.l_due.date().toString("yyyy-MM-dd"), team.me(),
                                      self.l_note.text().strip())

        def done(codes, _o):
            if all(c == 0 for c in codes):
                fleet.save_list(_data_dir(), "loaners.json", loans)
                self.l_serial.clear()
                self.l_note.clear()
            self._loan_refresh()
        self.run_many(cmds, done, with_codes=True)

    def loan_in(self):
        serial = self._serial_for(self.l_serial.text())
        loans = fleet.load_list(_data_dir(), "loaners.json")
        rec, cmds = fleet.loaner_in(loans, serial)
        if not rec:
            self.info(f"{serial or 'That device'} isn't checked out.")
            return

        def done(codes, _o):
            if all(c == 0 for c in codes):
                fleet.save_list(_data_dir(), "loaners.json", loans)
                self.l_serial.clear()
            self._loan_refresh()
        self.run_many(cmds, done, with_codes=True)

    def loan_remind(self):
        late = fleet.overdue(fleet.load_list(_data_dir(), "loaners.json"))
        if not late:
            self.info("No overdue loaners. ✔")
            return
        from ... import google_io
        if not self.confirm(f"Email {len(late)} reminder(s)?"):
            return
        self.run_many([fleet.reminder_args(x, google_io.email_args) for x in late],
                      lambda codes, _o: self.info(f"{sum(1 for c in codes if c == 0)} reminder(s) "
                                                  "sent."), with_codes=True)

    # ------------------------------------------------------------ repairs ---
    def _repair_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.r_serial = QLineEdit(placeholderText="Serial number or asset tag")
        self.r_problem = QLineEdit(placeholderText="What's wrong, e.g. cracked screen")
        lay.addLayout(self.row(self.r_serial, self.r_problem,
                               button("Open a repair ticket", "primary", self.repair_open),
                               stretch=False))
        self.r_status = QComboBox()
        self.r_status.addItems(fleet.REPAIR_STATES)
        self.r_note = QLineEdit(placeholderText="Note, e.g. sent to vendor, RMA 12345")
        lay.addLayout(self.row(QLabel("Selected ticket:"), self.r_status, self.r_note,
                               button("Update", slot=self.repair_update),
                               button("History", slot=self.repair_history), stretch=False))
        from PySide6.QtWidgets import QCheckBox
        self.r_open_only = QCheckBox("Open tickets only")
        self.r_open_only.setChecked(True)
        self.r_open_only.toggled.connect(self._repair_refresh)
        lay.addWidget(self.r_open_only)
        self.r_table = ResultsTable()
        lay.addWidget(self.r_table, 2)
        lay.addWidget(QLabel("<b>Repairs by model</b>"))
        self.r_stats = ResultsTable()
        lay.addWidget(self.r_stats, 1)
        self._repair_refresh()
        return w

    def _repair_refresh(self, *_):
        tickets = fleet.load_list(_data_dir(), "repairs.json")
        shown = [t for t in reversed(tickets) if not self.r_open_only.isChecked()
                 or not t.get("closed")]
        self.r_table.set_rows(["#", "Serial", "Model", "User", "Opened", "Status", "Problem"],
                              [[str(t["n"]), t["serial"], t.get("model", ""), t.get("user", ""),
                                t["opened"], t["status"], t["problem"]] for t in shown])
        self.r_stats.set_rows(["Model", "Tickets", "Still open", "Devices"],
                              [[x["model"], str(x["tickets"]), str(x["open"]),
                                str(x["devices"])] for x in fleet.repair_stats(tickets)])

    def repair_open(self):
        serial = self._serial_for(self.r_serial.text())
        problem = self.r_problem.text().strip()
        if not serial or not problem:
            self.info("Scan the device and describe the problem.")
            return
        tickets = fleet.load_list(_data_dir(), "repairs.json")
        dev = next((d for d in self.devs if d["serial"].upper() == serial.upper()), None)
        t, cmds = fleet.repair_open(tickets, serial, problem, team.me(), dev)
        fleet.save_list(_data_dir(), "repairs.json", tickets)
        self.r_serial.clear()
        self.r_problem.clear()
        self.run_many(cmds, lambda *_: self._repair_refresh())
        self.info(f"Opened repair #{t['n']} for {serial}.")

    def _repair_selected(self):
        rows = self.r_table.selected_dicts()
        if not rows:
            self.info("Select a ticket.")
            return None, None
        tickets = fleet.load_list(_data_dir(), "repairs.json")
        t = next((x for x in tickets if str(x["n"]) == rows[0].get("#")), None)
        return tickets, t

    def repair_update(self):
        tickets, t = self._repair_selected()
        if not t:
            return
        cmds = fleet.repair_update(t, self.r_status.currentText(), self.r_note.text().strip(),
                                   team.me())
        fleet.save_list(_data_dir(), "repairs.json", tickets)
        self.r_note.clear()
        if cmds:
            self.run_many(cmds, lambda *_: self._repair_refresh())
        self._repair_refresh()

    def repair_history(self):
        _tickets, t = self._repair_selected()
        if t:
            self.info("\n".join(f"{h['date']}  {h['status']}  ({h['by']})  {h['note']}"
                                for h in t["history"]), f"Repair #{t['n']} – {t['serial']}")

    # ------------------------------------------------------------- labels ---
    def _labels_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        tip = QLabel("Print labels with a barcode for each Chromebook (or every device in a cart). "
                     "The barcode is the serial number, so the Summer collection scan box and "
                     "the Loaners tab can read it.")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.lb_filter = QLineEdit(placeholderText="Only devices whose location, org unit or "
                                                   "serial contains… (blank = all loaded)")
        self.lb_code = QComboBox()
        self.lb_code.addItem("Barcode: serial number", "serial")
        self.lb_code.addItem("Barcode: asset tag", "asset")
        self.lb_title = QLineEdit(placeholderText="Small heading, e.g. Hancock Schools")
        lay.addLayout(self.row(self.lb_filter, self.lb_code, self.lb_title, stretch=False))
        lay.addLayout(self.row(button("Make labels", "primary", self.make_labels)))
        lay.addStretch(1)
        return w

    def make_labels(self):
        if not self._need(self.make_labels):
            return
        f = self.lb_filter.text().strip().lower()
        ds = [d for d in self.devs if not f or f in (d["location"] or "").lower() or
              f in (d["ou"] or "").lower() or f in d["serial"].lower()]
        if not ds:
            self.info("No devices match.")
            return
        if self.lb_code.currentData() == "asset":
            ds = [d for d in ds if d["asset"]] or ds
        from ..labels import LabelsDialog
        LabelsDialog(self, ds, self.lb_code.currentData(), self.lb_title.text().strip()).exec()
