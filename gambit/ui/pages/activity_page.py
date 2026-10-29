"""Activity log page: who did what and when, with undo, re-run and explain."""

from __future__ import annotations

from ... import csv_safe
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
)

from ... import activity
from ...settings import settings
from ..widgets import Page, Worker, button

RANGES = [("Today", 1), ("Last 7 days", 7), ("Last 30 days", 30), ("Last 90 days", 90),
          ("Everything", 0)]


class ActivityPage(Page):
    title = "Activity log"
    subtitle = ("Every command GAMbit has run – who ran it, when, and whether it worked. "
                "Undo changes, run them again, or search your history.")

    def build(self):
        bar = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Search commands, people, results…")
        self.search.textChanged.connect(self._filter)
        self.range = QComboBox()
        for label, days in RANGES:
            self.range.addItem(label, days)
        self.range.setCurrentIndex(1)
        self.range.currentIndexChanged.connect(self.refresh)
        self.only_changes = QCheckBox("Changes only")
        self.only_changes.setChecked(True)
        self.only_changes.toggled.connect(self._filter)
        self.team = QCheckBox("Whole team (shared folder)")
        self.team.toggled.connect(self.refresh)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.range)
        bar.addWidget(self.only_changes)
        bar.addWidget(self.team)
        bar.addWidget(button("Refresh", slot=self.refresh))
        self.body.addLayout(bar)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["When", "Who", "Domain", "What was done",
                                              "Command", "Result", "Undo", "Note"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for c, w in ((0, 140), (1, 90), (2, 90), (4, 360), (5, 80), (6, 180), (7, 120)):
            self.table.setColumnWidth(c, w)
        self.table.doubleClicked.connect(lambda *_: self.explain_selected())
        self.body.addWidget(self.table, 1)

        acts = QHBoxLayout()
        acts.addWidget(button("Undo selected…", "primary", self.undo))
        acts.addWidget(button("Run again", slot=self.rerun))
        acts.addWidget(button("Explain", slot=self.explain_selected))
        acts.addWidget(button("Copy command", slot=self.copy))
        acts.addWidget(button("Export…", slot=self.export))
        acts.addStretch(1)
        self.count = QLabel("", objectName="Muted")
        acts.addWidget(self.count)
        self.body.addLayout(acts)

        box, form = self.group("Where the log is kept")
        self.local_lbl = QLabel(activity.local_dir(), objectName="Muted")
        self.local_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow("On this PC", self.row(self.local_lbl, button(
            "Open", slot=lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(activity.local_dir())))))
        self.shared = QLineEdit(activity.shared_dir())
        self.shared.setPlaceholderText("Optional shared folder (e.g. a mapped drive or "
                                       "Google Drive for desktop folder) for the whole team")
        form.addRow("Also save to", self.row(self.shared, button("Browse…", slot=self._browse),
                                             button("Save", slot=self._save_shared),
                                             stretch=False))
        self.sheet = QLineEdit(activity.sheet_url())
        self.sheet.setPlaceholderText("Optional Google Sheet link – GAMbit copies the log "
                                      "there every day so anyone can search it")
        form.addRow("Google Sheet", self.row(self.sheet, button("Save", slot=self._save_sheet),
                                             button("Copy now", slot=self.push_sheet),
                                             stretch=False))
        self.sheet_status = QLabel(self._sheet_status(), objectName="Muted")
        form.addRow("", self.sheet_status)
        self.body.addWidget(box)
        self.entries: list[dict] = []

    def on_show(self):
        self.refresh()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Shared log folder", self.shared.text())
        if d:
            self.shared.setText(os.path.normpath(d))
            self._save_shared()

    def _save_shared(self):
        settings.set("activity/shared_dir", self.shared.text().strip())
        self.info("Saved. From now on, every command is also logged in that folder.")

    def _sheet_status(self):
        t = settings.get("activity/sheet_pushed", "")
        return f"Last copied {t.replace('T', ' ')}" if t else ""

    def _save_sheet(self):
        settings.set("activity/sheet_url", self.sheet.text().strip())
        if self.sheet.text().strip():
            self.info("Saved. GAMbit will copy the log to that sheet once a day "
                      "(Copy now does it straight away).")

    def push_sheet(self):
        self._save_sheet() if self.sheet.text().strip() != activity.sheet_url() else None
        if not activity.sheet_url():
            self.info("Paste the Google Sheet link first.")
            return
        self.sheet_status.setText("Copying…")
        Worker(activity.push_to_sheet,
               on_done=lambda tab: self.sheet_status.setText(
                   f"Copied to the “{tab}” tab · {self._sheet_status()}"),
               on_error=lambda e: (self.sheet_status.setText(""), self.info(str(e))))

    def refresh(self):
        _WHAT_CACHE.clear()          # device names may have been learned since
        from ... import device_names
        device_names.reload()
        self.entries = activity.load(self.range.currentData(), self.team.isChecked())
        self._filter()

    def _filter(self):
        text = self.search.text().lower().strip()
        rows = [e for e in self.entries
                if (not self.only_changes.isChecked() or e.get("change"))
                and (not text or text in " ".join(str(v) for v in e.values()).lower())]
        self.table.setRowCount(0)
        for e in rows[:3000]:
            r = self.table.rowCount()
            self.table.insertRow(r)
            ok = e.get("code") == 0
            res = "✔ Done" if ok else ("■ Cancelled" if e.get("status") == "cancelled"
                                       else f"✖ Failed ({e.get('code')})")
            undo = ""
            if e.get("undone"):
                undo = "↩ undone"
            elif e.get("undo"):
                undo = "↩ " + e["undo"].get("label", "available")
            note = e.get("note", "") or ("undo of an earlier change" if e.get("undo_of")
                                         else "")
            what, named, devices = _what(e)
            vals = [e.get("time", "").replace("T", " "), e.get("who", ""),
                    e.get("profile", ""), what, named, res, undo, note]
            tips = {3: what + (("\n\nChromebooks:\n" + "\n".join(devices[:60]) +
                                (f"\n…and {len(devices) - 60} more" if len(devices) > 60
                                 else "")) if len(devices) > 1 else ""),
                    4: e.get("command", "")}
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setToolTip(tips.get(c, v))
                if c == 0:
                    it.setData(Qt.UserRole, e)
                self.table.setItem(r, c, it)
        self.count.setText(f"{len(rows):,} entries")

    def _selected(self) -> list[dict]:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).data(Qt.UserRole) for r in rows]

    def undo(self):
        sel = [e for e in self._selected() if e.get("undo") and not e.get("undone")]
        if not sel:
            self.info("Select a change that shows “↩” in the Undo column.")
            return
        from ...gam_runner import display_command
        plan = "\n".join(f"• {e['undo']['label']}\n" + "\n".join(
            "    " + display_command(c) for c in (e["undo"].get("steps") or
                                                  [e["undo"]["args"]])) for e in sel)
        if not self.confirm(f"Undo {len(sel)} change(s)?\n\n{plan}", "Undo"):
            return
        for e in sel:
            self.app.run_undo(e)
        self.refresh()

    def rerun(self):
        for e in self._selected()[:10]:
            if "********" in " ".join(e.get("args", [])):
                self.info("Commands with passwords can't be re-run from the log.")
                continue
            if self.confirm(f"Run again?\n\n{e.get('command')}"):
                self.runner.run(e.get("args", []))

    def explain_selected(self):
        sel = self._selected()
        if sel:
            self.app.explain_command(sel[0].get("command", ""))

    def copy(self):
        QApplication.clipboard().setText("\n".join(e.get("command", "") for e in self._selected()))

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export activity", "gambit-activity.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv_safe.writer(fh)
            w.writerow(["time", "who", "computer", "domain", "what was done", "chromebooks",
                        "command", "result", "undone"])
            for e in self.entries:
                what, _named, devices = _what(e)
                w.writerow([e.get("time"), e.get("who"), e.get("computer"), e.get("profile"),
                            what, "; ".join(devices), e.get("command"), e.get("code"),
                            e.get("undone")])


_WHAT_CACHE: dict = {}


def _what(e: dict) -> tuple[str, str, list[str]]:
    key = (e.get("id"), tuple(e.get("args") or []))
    if key not in _WHAT_CACHE:
        if len(_WHAT_CACHE) > 20000:
            _WHAT_CACHE.clear()
        _WHAT_CACHE[key] = _what_uncached(e)
    return _WHAT_CACHE[key]


def _what_uncached(e: dict) -> tuple[str, str, list[str]]:
    """(what was done, command with serials, Chromebook names) – worked out again for
    older entries, so they show serials too once GAMbit has seen those devices."""
    from ... import activity
    args = e.get("args") or []
    what = e.get("what") or ""
    if args and (not what or "Chromebook" in what):   # re-done: serials may be known now
        what = activity.describe_any(args) or what
    devices = []
    try:
        t = activity._cros_target(activity.strip_config(list(args)))
        if t and t[0] != "ou":
            devices = activity.device_labels(t[0], t[1])
    except Exception:  # noqa: BLE001
        devices = e.get("devices") or []
    if not what:
        what = e.get("note") or ""
    named = activity.named_command(args) if args else e.get("command", "")
    return what or e.get("command", ""), named, devices
