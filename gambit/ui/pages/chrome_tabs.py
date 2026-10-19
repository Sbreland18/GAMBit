"""Chromebooks → Send a command;  Chromebook fleet → Health, Apps & extensions, Printers;
Policies by org unit → Change or copy policies."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPlainTextEdit, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from ...settings import settings
from ...tools import chrome
from ..pickers import OUField
from ..tools_base import ToolTab
from ..widgets import ResultsTable, button


# ======================================================== remote commands ===
class CommandsTab(ToolTab):
    intro = ("Send a command to one Chromebook, a list of serial numbers, or every "
             "Chromebook in an org unit (a cart, a classroom, a school).")

    def build(self):
        box, form = self.page.group("Which Chromebooks")
        self.serials = QPlainTextEdit()
        self.serials.setPlaceholderText("Serial numbers, one per line (or scan them with a "
                                        "barcode scanner)… – or leave empty and pick an org "
                                        "unit below")
        self.serials.setMaximumHeight(110)
        self.ou = OUField(self.directory, "/Devices/Lincoln/Cart 3")
        self.kids = QCheckBox("Include sub-org units")
        self.kids.setChecked(True)
        form.addRow("Serial numbers", self.serials)
        form.addRow("Or org unit", self.row(self.ou, self.kids, stretch=False))
        self.lay.addWidget(box)

        box, form = self.page.group("Command")
        self.cmd = QComboBox()
        for label, val, _why in chrome.COMMANDS:
            self.cmd.addItem(label, val)
        self.why = QLabel("", objectName="Muted")
        self.why.setWordWrap(True)
        self.vol = QSpinBox()
        self.vol.setRange(0, 100)
        self.vol.setValue(50)
        self.vol.setSuffix(" %")
        self.cmd.currentIndexChanged.connect(self._pick)
        form.addRow("Send", self.cmd)
        form.addRow("Volume", self.vol)
        form.addRow("", self.why)
        form.addRow("", self.row(button("Send command", "primary", self.send)))
        self._form = form
        self.lay.addWidget(box)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.lay.addStretch(1)
        self._pick()

    def _pick(self, *_):
        val = self.cmd.currentData()
        self.why.setText(next(w for _l, v, w in chrome.COMMANDS if v == val))
        self._form.setRowVisible(self.vol, val == "set_volume")

    def send(self):
        serials = self.serials.toPlainText().split()
        if not serials and not self.ou.path():
            self.info("Type serial numbers or pick an org unit.")
            return
        ent = chrome.target(serials, self.ou.path(), self.kids.isChecked())
        val = self.cmd.currentData()
        what = f"{len(serials)} Chromebook(s)" if serials else f"every Chromebook in " \
            f"{self.ou.path()}" + (" and below" if self.kids.isChecked() else "")
        warn = "\n\nThis ERASES the device(s)." if val == "remote_powerwash" else \
            "\n\nEveryone's local data on the device(s) is removed." if val == "wipe_users" else ""
        if not self.confirm(f"{self.cmd.currentText()} on {what}?{warn}"):
            return
        self.run_steps(self.steps, [(f"{self.cmd.currentText()}: {what}",
                                     chrome.command_args(ent, val, self.vol.value()))])


# ================================================================= health ===
class HealthTab(ToolTab):
    intro = ("Battery health, storage and update status from each Chromebook's last report. "
             "Devices that need attention are listed first – handy for ordering batteries "
             "before summer. (Needs Chrome device telemetry reporting turned on.)")

    def build(self):
        self.ou = OUField(self.directory, "/Devices")
        self.ou.set_path(settings.get("fleet/health_ou", "") or "/")
        self.batt = QSpinBox()
        self.batt.setRange(10, 100)
        self.batt.setValue(int(settings.get("fleet/battery_warn", 70) or 70))
        self.batt.setSuffix(" %")
        self.lay.addLayout(self.row(QLabel("Chromebooks under"), self.ou,
                                    QLabel("Flag batteries below"), self.batt,
                                    button("Check health", "primary", self.load),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(380)
        self.lay.addWidget(self.table, 1)

    def load(self):
        settings.set("fleet/health_ou", self.ou.path())
        settings.set("fleet/battery_warn", self.batt.value())

        def done(rows):
            if rows is None:
                return
            h = chrome.health(rows, self.batt.value())
            heads = list(h[0].keys()) if h else ["Serial"]
            self.table.set_rows(heads, [[r[k] for k in heads] for r in h])
            bad = sum(1 for r in h if r["Needs attention"])
            self.status.setText(f"{len(h):,} Chromebook(s) · {bad:,} need attention")
        self.read(chrome.telemetry_args(self.ou.path() or "/"), done,
                  "Reading device reports from Google (can take a few minutes)…")


# ======================================================= apps & extensions ===
class AppsTab(ToolTab):
    intro = ("Every extension and app installed on your Chromebooks, most-installed first. "
             "Names with words like VPN, proxy or unblock are flagged. Select one to see which "
             "devices have it.")

    def build(self):
        self.ou = OUField(self.directory, "/Students")
        self.ou.set_path(settings.get("fleet/apps_ou", "") or "/")
        self.lay.addLayout(self.row(QLabel("Devices and users under"), self.ou,
                                    button("List apps and extensions", "primary", self.load),
                                    button("Which devices have the selected one?",
                                           slot=self.devices), stretch=False))
        self.lay.addWidget(self.status)
        split = QSplitter(Qt.Vertical)
        self.table = ResultsTable()
        self.table.hidden_columns = {"App ID"}
        self.dev = ResultsTable()
        split.addWidget(self.table)
        split.addWidget(self.dev)
        split.setMinimumHeight(460)
        self.lay.addWidget(split, 1)
        hint = QLabel("To block one, copy its App ID and block it in the Admin console under "
                      "Devices → Chrome → Apps & extensions for that org unit.",
                      objectName="Muted")
        hint.setWordWrap(True)
        self.lay.addWidget(hint)

    def load(self):
        settings.set("fleet/apps_ou", self.ou.path())

        def done(rows):
            if rows is None:
                return
            a = chrome.apps(rows)
            heads = ["App", "Type", "How installed", "Installs", "Look at this", "App ID"]
            self.table.set_rows(heads, [[r[h] for h in heads] for r in a])
            flagged = sum(1 for r in a if r["Look at this"])
            self.status.setText(f"{len(a):,} app(s) and extension(s) · {flagged} flagged")
        self.read(chrome.apps_args(self.ou.path() or "/"), done)

    def devices(self):
        sel = self.table.selected_dicts()
        if not sel:
            self.info("Select an app first.")
            return

        def done(rows):
            if rows is not None:
                heads = list(rows[0].keys()) if rows else ["(no devices)"]
                self.dev.set_rows(heads, [[r.get(h, "") for h in heads] for r in rows])
                self.status.setText(f"“{sel[0]['App']}” is on {len(rows):,} device(s)")
        self.read(chrome.app_devices_args(self.ou.path() or "/", sel[0]["App ID"]), done)


# =============================================================== printers ===
class PrintersTab(ToolTab):
    intro = ("Set up building printers for Chromebooks from a spreadsheet: Name, Address "
             "(IP or ipp:// link), Org unit, Description, Make and model (leave empty for "
             "modern “driverless” printers). Everyone in that org unit and below gets them.")

    def build(self):
        self.src = QLineEdit(placeholderText="printers.csv")
        self.lay.addLayout(self.row(self.src, button("Browse…", slot=self._browse),
                                    button("Save a blank template…", slot=self._template),
                                    button("Preview", "primary", self.preview),
                                    button("List current printers", slot=self.list_now),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.apply_btn = button("Apply changes", "primary", self.apply)
        self.apply_btn.setEnabled(False)
        self.lay.addLayout(self.row(self.apply_btn))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.plan = []

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Printers spreadsheet", "", "CSV (*.csv)")
        if p:
            self.src.setText(p)

    def _template(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save template", "printers.csv", "CSV (*.csv)")
        if p:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(chrome.PRINTER_TEMPLATE)
            self.src.setText(p)

    def list_now(self):
        self.read(["print", "printers"], lambda rows: rows is not None and self.table.set_rows(
            list(rows[0].keys()) if rows else ["(no printers yet)"],
            [list(r.values()) for r in rows]))

    def preview(self):
        try:
            with open(self.src.text().strip(), encoding="utf-8-sig") as fh:
                wanted = chrome.printers_from_csv(fh.read())
        except OSError:
            self.info("Choose the printers spreadsheet first.")
            return
        if not wanted:
            self.info("No printers found – the sheet needs Name and Address columns.")
            return

        def done(rows):
            if rows is None:
                return
            self.plan = chrome.printer_plan(wanted, rows)
            self.table.set_rows(["Change", "Printer", "Details"],
                                [[p["action"], p["name"], p["details"]] for p in self.plan])
            n = sum(1 for p in self.plan if p["args"])
            self.status.setText(f"{len(self.plan)} printer(s) · {n} to create or update")
            self.apply_btn.setEnabled(n > 0)
        self.read(["print", "printers"], done)

    def apply(self):
        todo = [p for p in self.plan if p["args"]]
        if todo and self.confirm(f"Create or update {len(todo)} printer(s)?"):
            self.run_steps(self.steps, [(f"{p['action'].title()} {p['name']}", p["args"])
                                        for p in todo])


# =============================================================== policies ===
class PolicyDialog(QDialog):
    """Change one Chrome policy for an org unit, or copy every policy set directly on one
    org unit to another."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Change or copy Chrome policies")
        self.resize(1000, 720)
        self.schemas: list[dict] = []
        v = QVBoxLayout(self)
        from PySide6.QtWidgets import QTabWidget
        tabs = QTabWidget()
        v.addWidget(tabs, 1)
        tabs.addTab(self._change(), "Change a policy")
        tabs.addTab(self._copy(), "Copy policies to another org unit")
        from ..steps import StepList
        self.steps = StepList(page)
        self.steps.setMaximumHeight(150)
        v.addWidget(self.steps)
        self.status = QLabel("", objectName="Muted")
        v.addWidget(self.status)

    # ---- change
    def _change(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.find = QLineEdit(placeholderText="Search policies, e.g. url, incognito, "
                                              "wallpaper, screen lock, printing…")
        self.find.returnPressed.connect(self._search)
        v.addLayout(self.page.row(self.find, button("Search", "primary", self._search),
                                  stretch=False))
        split = QSplitter()
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._pick)
        split.addWidget(self.list)
        right = QWidget()
        self.form = QFormLayout(right)
        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        self.form.addRow(self.desc)
        split.addWidget(right)
        split.setSizes([360, 620])
        v.addWidget(split, 1)
        self.ou = OUField(self.page.directory, "/Students")
        v.addLayout(self.page.row(QLabel("Apply to org unit"), self.ou,
                                  button("Show current value", slot=self._current),
                                  button("Set policy", "primary", self._apply),
                                  stretch=False))
        self.inputs: dict[str, QWidget] = {}
        return w

    def _search(self):
        text = self.find.text().strip().lower()

        def show():
            self.list.clear()
            for s in self.schemas:
                blob = (s["schema"] + " " + s["description"]).lower()
                if not text or all(t in blob for t in text.split()):
                    it = QListWidgetItem(s["schema"].replace("chrome.", ""))
                    it.setToolTip(s["description"])
                    it.setData(Qt.UserRole, s)
                    self.list.addItem(it)
            self.status.setText(f"{self.list.count()} policies")
        if self.schemas:
            show()
            return
        self.status.setText("Downloading Google's list of Chrome policies…")

        def done(code, out, _e):
            if code != 0:
                self.status.setText("Couldn't list policies – see the Output panel.")
                return
            import csv
            import io
            self.schemas = chrome.parse_schemas(list(csv.DictReader(io.StringIO(out))))
            show()
        self.page.runner.run(chrome.schemas_args(), done, quiet_stdout=True)

    def _pick(self, it, _prev=None):
        while self.form.rowCount() > 1:
            self.form.removeRow(1)
        self.inputs = {}
        if not it:
            return
        s = it.data(Qt.UserRole)
        self.desc.setText(f"<b>{s['schema']}</b><br>{s['description']}")
        for f in s["fields"]:
            if f["values"]:
                w = QComboBox()
                w.addItem("(leave as is)", "")
                for val, text in f["values"]:
                    w.addItem(f"{val} – {text}"[:110], val)
            else:
                w = QLineEdit()
                w.setPlaceholderText("leave empty to skip · lists: a,b,c · true/false")
            w.setToolTip(f["description"])
            self.inputs[f["name"]] = w
            self.form.addRow(f["name"], w)

    def _values(self) -> dict:
        out = {}
        for k, w in self.inputs.items():
            v = w.currentData() if isinstance(w, QComboBox) else w.text().strip()
            if v:
                out[k] = v
        return out

    def _current(self):
        it = self.list.currentItem()
        if not it or not self.ou.path():
            self.page.info("Pick a policy and an org unit.")
            return
        self.page.runner.run(["print", "chromepolicies", "ou", self.ou.path(), "filter",
                              it.data(Qt.UserRole)["schema"]],
                             lambda c, o, e: self.status.setText(
                                 (o or "").strip().replace("\n", " · ")[:400] or
                                 "Not set here (uses Google's default)."), quiet_stdout=True)

    def _apply(self):
        it = self.list.currentItem()
        vals = self._values()
        if not it or not vals or not self.ou.path():
            self.page.info("Pick a policy, fill in at least one setting and choose an org unit.")
            return
        args = chrome.policy_args(it.data(Qt.UserRole)["schema"], vals, self.ou.path())
        if self.page.confirm(f"Set {it.text()} for {self.ou.path()}?\n\n" +
                             "\n".join(f"{k} = {v}" for k, v in vals.items())):
            from ..steps import Step
            self.steps.run([Step(f"{it.text()} → {self.ou.path()}", args)],
                lambda _s: self.page.info(self.steps.summary()))

    # ---- copy
    def _copy(self):
        w = QWidget()
        v = QVBoxLayout(w)
        tip = QLabel("Copies every Chrome policy set <b>directly</b> on the first org unit "
                     "(not ones it inherits) to the second. Handy when you add a new school or "
                     "grade. Review the list before applying.")
        tip.setWordWrap(True)
        v.addWidget(tip)
        self.src = OUField(self.page.directory, "/Students/Lincoln Elementary")
        self.dst = OUField(self.page.directory, "/Students/New School")
        h = QHBoxLayout()
        h.addWidget(QLabel("From"))
        h.addWidget(self.src)
        h.addWidget(QLabel("to"))
        h.addWidget(self.dst)
        h.addWidget(button("Preview", "primary", self._copy_preview))
        v.addLayout(h)
        self.copy_t = ResultsTable()
        v.addWidget(self.copy_t, 1)
        self.copy_note = QLabel("", objectName="Muted")
        self.copy_note.setWordWrap(True)
        v.addWidget(self.copy_note)
        self.copy_btn = button("Copy these policies", "primary", self._copy_apply)
        self.copy_btn.setEnabled(False)
        v.addLayout(self.page.row(self.copy_btn))
        self.copy_plan = []
        return w

    def _copy_preview(self):
        if not self.src.path() or not self.dst.path() or self.src.path() == self.dst.path():
            self.page.info("Pick two different org units.")
            return

        def done(code, out, _e):
            if code != 0:
                self.status.setText("Couldn't read the policies – see the Output panel.")
                return
            import csv
            import io
            self.copy_plan, skipped = chrome.copy_plan(list(csv.DictReader(io.StringIO(out))),
                                                       self.dst.path())
            self.copy_t.set_rows(["Policy", "Settings"],
                                 [[p["schema"], ", ".join(f"{k}={v}" for k, v in
                                                          p["values"].items())[:300]]
                                  for p in self.copy_plan])
            self.copy_note.setText(("Not copied (complex values): " + "; ".join(skipped))
                                   if skipped else "")
            self.copy_btn.setEnabled(bool(self.copy_plan))
            self.status.setText(f"{len(self.copy_plan)} policies to copy")
        self.page.runner.run(chrome.direct_policies_args(self.src.path()), done,
                             quiet_stdout=True)

    def _copy_apply(self):
        from ..steps import Step
        if self.copy_plan and self.page.confirm(
                f"Copy {len(self.copy_plan)} policies to {self.dst.path()}?"):
            self.steps.run([Step(p["schema"], p["args"]) for p in self.copy_plan],
                           lambda _s: self.page.info(self.steps.summary()))
