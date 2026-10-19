from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QLabel, QLineEdit, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from ..pickers import OUField, OUMultiField, PersonField
from ..widgets import Page, ResultsTable, button

CROS_FIELDS = ("serialnumber,status,orgunitpath,model,osversion,lastsync,"
               "annotatedassetid,annotatedlocation,annotateduser,autoupdateexpiration,"
               "deviceid")

# Adds the most recent signed-in user and their latest active day to "print cros"
LAST_USER_FIELDS = ",recentusers,activetimeranges"
LAST_USER_OPTS = ["reverselists", "activetimeranges", "listlimit", "1"]


def last_user_summary(row: dict) -> tuple[str, str, str]:
    """(last user, last active date, last sync) from a print cros CSV row."""
    def find(*parts):
        for k, v in row.items():
            kl = (k or "").lower()
            if all(p in kl for p in parts) and v:
                return v
        return ""
    return (find("recentusers", "email") or "(no one / guest)",
            find("activetimeranges", "date"),
            find("lastsync").replace("T", " ").split(".")[0].rstrip("Z"))


# Friendly column order for device lists: (heading, CSV column(s))
LIST_COLUMNS = [("Serial", ["serialNumber"]), ("Asset ID", ["annotatedAssetId"]),
                ("Assigned user", ["annotatedUser"]), ("Location", ["annotatedLocation"]),
                ("Status", ["status"]), ("Org unit", ["orgUnitPath"]), ("Model", ["model"]),
                ("OS version", ["osVersion"]), ("Last sync", ["lastSync"]),
                ("End of updates", ["autoUpdateExpiration"]), ("deviceId", ["deviceId"])]


def asset_query(asset: str) -> str:
    """Admin console search for an asset ID (quoted so spaces and dashes work)."""
    a = (asset or "").strip().replace('"', "")
    return f'asset_id:"{a}"' if any(c in a for c in " :") else f"asset_id:{a}"


def split_items(text: str, ids: bool = True) -> list[str]:
    """Several values typed or pasted into one box: split on commas, semicolons and new lines.
    For IDs (asset tags, serials) a space-separated list works too, when every piece has a
    digit in it (so an asset ID like "Cart 3" with one space still stays whole)."""
    t = (text or "").strip()
    if re.search(r"[,;\n\t]", t):
        parts = re.split(r"[,;\n\t]+", t)
    elif ids and " " in t and all(any(c.isdigit() for c in p) for p in t.split()) \
            and len(t.split()) > 1 and not re.fullmatch(r"\S+ \d+", t):
        parts = t.split()
    else:
        parts = [t]
    return list(dict.fromkeys(p.strip() for p in parts if p.strip()))


def query_args(queries: list[str]) -> list[str]:
    """`query X` for one search, `queries "X","Y"` for several (GAM runs each and merges)."""
    if len(queries) == 1:
        return ["query", queries[0]]
    return ["queries", ",".join(q if "," not in q and '"' not in q else
                                "'" + q.replace("'", "") + "'" for q in queries)]


def shape_rows(rows: list[dict]) -> tuple[list[str], list[list[str]]]:
    """print cros CSV rows → friendly columns (asset ID next to the serial)."""
    heads = [h for h, _c in LIST_COLUMNS[:-1]] + ["Last user", "Last active", "deviceId"]
    out = []
    for r in rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        vals = [next((low.get(c.lower(), "") for c in cols if low.get(c.lower())), "")
                for _h, cols in LIST_COLUMNS[:-1]]
        user, day, _sync = last_user_summary(r)
        vals[8] = vals[8].replace("T", " ").split(".")[0].rstrip("Z")
        out.append(vals + [user, day, low.get("deviceid", "")])
    return heads, out


DEPROVISION = {
    "Retiring device": "deprovision_retiring_device",
    "Same model replacement": "deprovision_same_model_replace",
    "Different model replacement": "deprovision_different_model_replace",
    "Upgrade transfer": "deprovision_upgrade_transfer",
}


class DevicesPage(Page):
    title = "Chromebooks"
    subtitle = "Find ChromeOS devices by serial number and take action on them."

    def build(self):
        self.tabs = QTabWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        dev = self._device_tab()
        dev.setObjectName("Page")
        scroll.setWidget(dev)
        self.tabs.addTab(scroll, "One device")
        self.tabs.addTab(self._list_tab(), "Find / list devices")
        from .chrome_tabs import CommandsTab
        self.commands_tab = CommandsTab(self)
        self.tabs.addTab(self.commands_tab, "Send a command")
        self.body.addWidget(self.tabs)

    # --------------------------------------------------------- single ---
    def _device_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box, form = self.group("Device")
        self.sn = QLineEdit(placeholderText="Serial number(s), comma separated")
        form.addRow("Serial number", self.row(
            self.sn, button("Show info", "primary", self.cros_info),
            button("Last signed-in user", slot=self.last_user), stretch=False))
        self.find_asset = QLineEdit(placeholderText="Asset ID / tag, e.g. HMS-01234 (or several, "
                                                    "comma separated)")
        self.find_asset.returnPressed.connect(self.by_asset)
        form.addRow("…or asset ID", self.row(self.find_asset,
                                             button("Find by asset ID", slot=self.by_asset),
                                             stretch=False))
        self.last = QLabel("", objectName="Muted")
        self.last.setTextFormat(Qt.RichText)
        self.last.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.last.setWordWrap(True)
        form.addRow("", self.last)
        lay.addWidget(box)

        box, form = self.group("Update details")
        self.ou = OUField(self.directory, "Pick or type an org unit")
        self.asset = QLineEdit(placeholderText="Asset tag")
        self.loc = QLineEdit(placeholderText="Room 112")
        self.user = PersonField(self.directory, "Start typing a name or email…")
        form.addRow("Move to OU", self.row(self.ou, button("Move", slot=self.move), stretch=False))
        form.addRow("Asset ID", self.asset)
        form.addRow("Location", self.loc)
        form.addRow("Assigned user", self.user)
        form.addRow("", self.row(button("Save details", slot=self.save_details)))
        lay.addWidget(box)

        box, form = self.group("Actions")
        form.addRow(self.row(
            button("Disable", "danger", lambda: self.action("disable")),
            button("Re-enable", slot=lambda: self.action("reenable")),
            button("Reboot", slot=lambda: self.command("reboot")),
            button("Wipe user profiles…", "danger", lambda: self.command("wipe_users")),
            button("Powerwash…", "danger", lambda: self.command("remote_powerwash"))))
        self.deprov = QComboBox()
        self.deprov.addItems(DEPROVISION.keys())
        form.addRow("Deprovision", self.row(self.deprov,
                                            button("Deprovision…", "danger", self.deprovision)))
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def _serials(self):
        if not self.need(("a serial number", self.sn)):
            return None
        return ",".join(s.strip() for s in self.sn.text().replace(" ", ",").split(",") if s.strip())

    def cros_info(self):
        if s := self._serials():
            self.run(["info", "cros", "cros_sn", s, "fields", CROS_FIELDS],
                     lambda *_: self.last_user())

    def last_user(self):
        s = self._serials()
        if not s:
            return
        self.last.setText("Looking up the last signed-in user…")

        def done(code, out, _err):
            import csv
            import io
            rows = list(csv.DictReader(io.StringIO(out or "")))
            if code != 0 or not rows:
                # maybe they were asset IDs, not serials
                self.find_asset.setText(s)
                self.by_asset()
                return
            lines = []
            for r in rows:
                user, day, sync = last_user_summary(r)
                sn = r.get("serialNumber", "")
                tag = r.get("annotatedAssetId", "")
                lines.append(f"<b>{sn}</b>" + (f" (asset ID {tag})" if tag else "") +
                             f": last signed-in user <b>{user}</b>"
                             + (f", last active {day}" if day else "")
                             + (f" · device last synced {sync}" if sync else ""))
            self.last.setText("<br>".join(lines))
        self.run(["cros_sn", s, "print", "cros", "fields",
                  "serialnumber,annotatedassetid,lastsync" + LAST_USER_FIELDS, *LAST_USER_OPTS],
                 done, quiet=True)

    def by_asset(self):
        a = self.find_asset.text().strip()
        if not a:
            self.info("Type the asset ID first.")
            return
        self.last.setText(f"Looking for asset ID {a}…")

        def done(code, out, _err):
            import csv
            import io
            rows = list(csv.DictReader(io.StringIO(out or ""))) if code == 0 else []
            sns = [r.get("serialNumber", "") for r in rows if r.get("serialNumber")]
            if not sns:
                self.last.setText(f"No Chromebook has asset ID <b>{a}</b>.")
                return
            wanted = split_items(a)
            found = {(r.get("annotatedAssetId") or "").lower() for r in rows}
            missing = [x for x in wanted if x.lower() not in found]
            self.sn.setText(",".join(sns))
            self.last.setText("<br>".join(
                f"Asset ID <b>{r.get('annotatedAssetId', '')}</b> → serial "
                f"<b>{r.get('serialNumber', '')}</b> · {r.get('status', '')} · "
                f"{r.get('orgUnitPath', '')}" + (f" · assigned to {r['annotatedUser']}"
                                                 if r.get("annotatedUser") else "")
                for r in rows) + ("<br>More than one device has this asset ID – check "
                                  "which one you mean." if len(rows) > len(wanted) else "") +
                (f"<br>Not found: <b>{', '.join(missing)}</b>" if missing else ""))
        self.run(["print", "cros", *query_args([asset_query(x) for x in split_items(a)]),
                  "fields", "serialnumber,annotatedassetid,annotateduser,status,orgunitpath"],
                 done, quiet=True)

    def move(self):
        if (s := self._serials()) and self.need(("an OU path", self.ou)):
            self.run(["cros_sn", s, "update", "ou", self.ou.path()])

    def save_details(self):
        s = self._serials()
        if not s:
            return
        args = ["cros_sn", s, "update"]
        for key, edit in (("assetid", self.asset), ("location", self.loc),
                          ("user", self.user)):
            if edit.text().strip():
                args += [key, edit.text().strip()]
        if len(args) == 3:
            self.info("Fill in at least one of Asset ID, Location, or Assigned user.")
            return
        self.run(args)

    def action(self, act):
        s = self._serials()
        if s and (act != "disable" or self.confirm(f"Disable {s}?")):
            self.run(["cros_sn", s, "update", "action", act])

    def command(self, cmd):
        s = self._serials()
        if not s:
            return
        args = ["cros_sn", s, "issuecommand", "command", cmd]
        if cmd in ("wipe_users", "remote_powerwash"):
            what = "erase all user data on" if cmd == "wipe_users" else "factory reset"
            if not self.confirm(f"This will {what} {s}. Continue?", "Are you sure?"):
                return
            args.append("doit")
        self.run(args)

    def deprovision(self):
        s = self._serials()
        reason = self.deprov.currentText()
        if s and self.confirm(f"Deprovision {s} ({reason})?\n\nThe device will need "
                              "to be re-enrolled by hand to be managed again.",
                              "Deprovision device"):
            self.run(["cros_sn", s, "update", "action", DEPROVISION[reason],
                      "acknowledge_device_touch_requirement"])

    # ----------------------------------------------------------- list ---
    def _list_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box, form = self.group("Search")
        self.l_mode = QComboBox()
        self.l_mode.addItems(["In org unit(s)", "Search text",
                              "Not synced in 30+ days", "All devices", "Asset ID"])
        self.l_val = QLineEdit(placeholderText="serial, user, asset id… (separate several with "
                                                "commas)")
        self.l_ous = OUMultiField(self.directory)
        self.l_mode.currentIndexChanged.connect(
            lambda i: (self.l_val.setVisible(i in (1, 4)), self.l_ous.setVisible(i == 0),
                       self.l_val.setPlaceholderText(
                           "asset IDs, e.g. HS0116, HS0189" if i == 4 else
                           "serial, user, asset id… (separate several with commas)")))
        self.l_val.setVisible(False)
        form.addRow("Show", self.row(self.l_mode, self.l_val, self.l_ous, stretch=False))
        form.addRow("", self.row(button("Search", "primary", self.list_devices),
                                 button("Use selected serials ↑", slot=self.use_selected)))
        lay.addWidget(box)
        self.results = ResultsTable()
        self.results.hidden_columns = {"deviceId"}
        lay.addWidget(self.results, 1)
        return w

    def _show(self, texts: list[str]):
        import csv
        import io
        rows, seen = [], set()
        for t in texts:
            for r in csv.DictReader(io.StringIO((t or "").strip())):
                key = r.get("deviceId") or r.get("serialNumber")
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
        self.results.set_rows(*shape_rows(rows))

    def list_devices(self):
        i, v = self.l_mode.currentIndex(), self.l_val.text().strip()
        if i == 0:
            ous = self.l_ous.paths()
            if not ous:
                self.info("Click Choose… and tick one or more org units.")
                return
            how = "cros_ou_and_children" if self.l_ous.include_children() else "cros_ou"
            self.run_many([["print", "cros", how, ou, "fields", CROS_FIELDS + LAST_USER_FIELDS,
                            *LAST_USER_OPTS]
                           for ou in ous],
                          self._show)
            return
        args = ["print", "cros"]
        if i == 4:
            if not v:
                self.info("Type the asset ID.")
                return
            args += query_args([asset_query(x) for x in split_items(v)])
        elif i == 1 and v:
            args += query_args(split_items(v, ids=False))
        elif i == 2:
            args += ["querytime1", "-30d", "query", "sync:..#querytime1#"]
        args += ["fields", CROS_FIELDS + LAST_USER_FIELDS,
                            *LAST_USER_OPTS]
        self.run(args, lambda c, out, _e: self._show([out]) if c == 0 else None, quiet=True)

    def use_selected(self):
        sns = self.results.selected_values("Serial")
        if sns:
            self.sn.setText(",".join(sns))
            self.tabs.setCurrentIndex(0)
