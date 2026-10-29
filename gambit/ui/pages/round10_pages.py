"""Round 10 screens: practice runs, nightly mismatch fix settings, Chromebook history,
repair hotspots and loaner needs, the monthly audit report and teacher follow-up lists."""

from __future__ import annotations

from ... import tempfiles as _tf
import datetime
import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QSpinBox, QTabWidget,
    QVBoxLayout,
)

from ...settings import settings
from ..tools_base import ToolTab
from ..widgets import Page, ResultsTable, Worker, button


# ============================================================ practice run ===
class PracticeRunDialog(QDialog):
    def __init__(self, parent, title: str, result: dict):
        super().__init__(parent)
        self.setWindowTitle(f"Practice run – {title}")
        self.resize(1000, 700)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("<b>Nothing was changed.</b> This is what would happen, played "
                           "against today's accounts, automatic groups and Chromebooks."))
        summ = ResultsTable()
        summ.set_rows(["", "How many"], [[k, str(n)] for k, n in result["summary"]])
        summ.setMinimumHeight(300)
        summ.setMaximumHeight(330)
        v.addWidget(summ)
        tabs = QTabWidget()
        for name, rows, head in (
                ("People", result["people"], ["Account", "Before", "After", "What happens"]),
                ("Org unit moves", result["moves"], ["From", "To", "Accounts"]),
                ("Automatic groups", result["groups"], ["Group", "Joins", "Leaves",
                                                        "Examples"]),
                ("Chromebooks", result["devices"], ["Serial", "Student", "What happens"])):
            t = ResultsTable()
            t.set_rows(head, [[str(r.get(h, "")) for h in head] for r in rows])
            tabs.addTab(t, f"{name} ({len(rows)})")
        if result["unsupported"]:
            t = ResultsTable()
            t.set_rows(["Command (not simulated – check it yourself)"],
                       [[c] for c in result["unsupported"]])
            tabs.addTab(t, f"Not simulated ({len(result['unsupported'])})")
        v.addWidget(tabs, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        v.addWidget(bb)


def practice_run(page, commands: list[list[str]], title: str, devices: bool = True):
    """Simulate commands and show the dialog (reads Chromebooks in the background)."""
    from ... import group_rules, whatif
    from ...tools import automation
    users = page.directory.users
    if not users:
        page.info("Load the user list first (Settings → refresh lists).")
        return

    def work():
        devs = None
        if devices:
            from ...directory import run_gam_csv
            from ...tools import reconcile
            code, rows, _e = run_gam_csv(reconcile.COLLECT_ARGS, 1800)
            devs = reconcile.devices(rows) if code == 0 else None
        return whatif.simulate(commands, users, group_rules.load(), devs,
                               automation.options())

    def done(res):
        PracticeRunDialog(page, title, res).exec()
    Worker(work, on_done=done, on_error=lambda e: page.info(f"Practice run failed:\n{e}"))


def rollover_commands(pairs, suspend_last: bool) -> list[list[str]]:
    from ...next_year import rollover_plan
    steps, problem = rollover_plan(pairs, suspend_last)
    if problem:
        raise ValueError(problem)
    return [args for _label, args, _req in steps]


def graduation_commands(students: list[dict], opts: dict, year: int) -> list[list[str]]:
    from ... import offboard
    cmds = []
    for u in students:
        rec = offboard.build_graduate(u["email"], {"groups": [], "licenses": [],
                                                   "ou": u.get("ou", ""),
                                                   "name": u.get("name", ""), "gal": True},
                                      opts, year)
        for st in rec["stages"]:
            cmds += [s["args"] for s in st["steps"]]
    return cmds


# ===================================================== nightly mismatch fix ===
def autofix_box(page):
    from ...tools import reconcile
    o = reconcile.autofix_options()
    box, form = page.group("Every night")
    on = QCheckBox("Build this report every night (5:50 AM), fix the safe ones and send the "
                   "rest to Approvals as one request")
    on.setChecked(bool(o["enabled"]))
    form.addRow(on)
    checks = {}
    for k, label in reconcile.AUTO_CHOICES.items():
        cb = QCheckBox(f"Fix automatically: {label}")
        cb.setChecked(k in o["auto"])
        checks[k] = cb
        form.addRow("", cb)
    cap = QSpinBox()
    cap.setRange(1, 5000)
    cap.setValue(int(o["max_auto"]))
    form.addRow("If more than this many, a person decides", cap)

    def save():
        reconcile.save_autofix_options({**o, "enabled": on.isChecked(), "max_auto": cap.value(),
                                        "auto": [k for k, cb in checks.items()
                                                 if cb.isChecked()]})
        if on.isChecked():
            from ... import tasks_health
            try:
                tasks_health.create(dict(reconcile.AUTOFIX_TASK))
                page.info("The mismatch report will run every night at 5:50 AM.")
            except Exception as exc:  # noqa: BLE001
                page.info(f"Saved, but the task couldn't be created here:\n{exc}")
    form.addRow("", page.row(button("Save", slot=save)))
    return box


# ======================================================== device history ===
class DeviceHistoryTab(ToolTab):
    intro = ("Everything GAMbit knows about one Chromebook, newest first: who it was assigned "
             "to, repairs, loaners, collections, changes made with GAMbit and help-desk "
             "tickets.")

    def build(self):
        self.sn = QLineEdit(placeholderText="Serial number or asset tag")
        self.sn.returnPressed.connect(self.show_history)
        self.lay.addLayout(self.row(self.sn, button("Show history", "primary",
                                                    self.show_history),
                                    stretch=False))
        self.head = QLabel("")
        self.head.setWordWrap(True)
        self.lay.addWidget(self.head)
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(380)
        self.lay.addWidget(self.table, 1)

    def show_history(self):
        from ... import activity, fleet
        from ...tools import device_history as dh, reconcile
        code = self.sn.text().strip().upper()
        if not code:
            return
        loans = fleet.load_list(fleet.data_dir(), "loaners.json")
        repairs = fleet.load_list(fleet.data_dir(), "repairs.json")
        wd = reconcile.load_items()
        coll = fleet.load_collection(fleet.collection_path(fleet.data_dir()))
        serial = code
        for src in (wd, repairs):
            for x in src:
                if (x.get("asset") or "").upper() == code:
                    serial = x["serial"].upper()

        def got(rows):
            info = {}
            if rows:
                d = fleet.devices(rows)
                info = d[0] if d else {}
            sn = (info.get("serial") or serial).upper()
            tickets = getattr(self.page.app.pages.get("Ticket queue"), "tickets", []) or []
            tl = dh.timeline(sn, activity.load(3650, team=True), repairs, loans, wd, coll,
                             tickets)
            self.table.set_rows(["When", "What", "Details", "Source"],
                                [[r["When"], r["What"], r["Details"], r["Source"]] for r in tl])
            if info:
                self.head.setText(
                    f"<b>{sn}</b> · {info.get('model') or 'model unknown'} · assigned to "
                    f"{info.get('user') or info.get('recent_user') or 'nobody'} · "
                    f"{info.get('ou')} · {info.get('status')} · updates end "
                    f"{info.get('aue') or '?'} · last seen {info.get('last_sync') or '?'}")
            else:
                self.head.setText(f"<b>{sn}</b> – not found in Google (history from GAMbit's "
                                  "own records only).")
        args = ["cros_sn", serial, "print", "cros", "fields", fleet.FIELDS, "listlimit", "1"] \
            if serial.isalnum() else ["print", "cros", "query", f"asset_id:{code}", "fields",
                                      fleet.FIELDS, "listlimit", "1"]
        self.read(args, got)


# ==================================================== repairs and loaners ===
class RepairsTab(ToolTab):
    intro = ("Which models and schools break most, and how many loaners each school really "
             "needs – from your repair and loaner history. Use it next to the replacement plan.")

    def build(self):
        self.by = QComboBox()
        self.by.addItem("By model", "model")
        self.by.addItem("By school", "school")
        self.months = QSpinBox()
        self.months.setRange(1, 60)
        self.months.setValue(12)
        self.months.setSuffix(" months")
        self.lay.addLayout(self.row(self.by, QLabel("over the last"), self.months,
                                    button("Load", "primary", self.load), self.status,
                                    stretch=False))
        self.hot = ResultsTable()
        self.hot.setMinimumHeight(240)
        self.lay.addWidget(self.hot)
        self.lay.addWidget(QLabel("<b>Loaners each school needs</b>"))
        self.loan = ResultsTable()
        self.loan.setMinimumHeight(200)
        self.lay.addWidget(self.loan, 1)

    def load(self):
        from ... import fleet
        from ...tools import budget, device_history as dh

        def work():
            from ...directory import run_gam_csv
            code, rows, err = run_gam_csv(["print", "cros", "fields", fleet.FIELDS,
                                           "listlimit", "1"], 1800)
            if code != 0:
                raise RuntimeError((err or "GAM failed").strip()[-200:])
            return fleet.devices(rows)

        def done(devs):
            o = budget.options()
            us = budget.user_schools(self.page.directory.users)
            school = lambda d: budget.school_of_device(  # noqa: E731
                d, o.get("device_root", ""), int(o.get("school_depth", 1) or 1), us)
            repairs = fleet.load_list(fleet.data_dir(), "repairs.json")
            loans = fleet.load_list(fleet.data_dir(), "loaners.json")
            rows = dh.hotspots(devs, repairs, self.by.currentData(), school,
                               self.months.value())
            head = ["Group", "Devices", "Repairs", "Per 100 devices", "Devices repaired",
                    "Open now", "Avg days to fix"]
            self.hot.set_rows(head, [["" if r[h] is None else str(r[h]) for h in head]
                                     for r in rows])
            by_serial = {d["serial"].upper(): school(d) for d in devs}
            lrows = dh.loaners(loans, repairs, lambda s: by_serial.get((s or "").upper(), ""),
                               lambda u: us.get((u or "").lower(), ""))
            lh = ["School", "Loaners out now", "Most out at once", "Avg in repair",
                  "Suggested loaner pool"]
            self.loan.set_rows(lh, [[str(r[h]) for h in lh] for r in lrows])
            self.status.setText(f"{len(devs)} Chromebooks, {len(repairs)} repair ticket(s), "
                                f"{len(loans)} loan(s)")
        self.status.setText("Reading Chromebooks…")
        Worker(work, on_done=done, on_error=lambda e: (self.status.setText(""),
                                                       self.info(str(e))))


# ============================================================ audit report ===
class AuditReportPage(Page):
    title = "Audit report"
    subtitle = ("One monthly report for your director or board: what changed and who approved "
                "it, settings changes, unusual activity and how it was handled, and the "
                "license and device numbers.")

    def build(self):
        from ... import audit_report as ar
        o = ar.options()
        box, form = self.group("Report")
        self.month = QComboBox()
        today = datetime.date.today().replace(day=1)
        d = today
        for _ in range(13):
            self.month.addItem(d.strftime("%B %Y"), (d.year, d.month))
            d = (d - datetime.timedelta(days=1)).replace(day=1)
        self.month.setCurrentIndex(1)
        self.district = QLineEdit(o.get("district", ""))
        self.district.setPlaceholderText("District name for the title")
        self.to = QLineEdit(o.get("to", ""))
        self.to.setPlaceholderText("superintendent@…, director@…")
        form.addRow("Month", self.month)
        form.addRow("District", self.district)
        form.addRow("Email to", self.to)
        self.status = QLabel("", objectName="Muted")
        form.addRow("", self.row(button("Build and open", "primary", self.build_open),
                                 button("Email it now", slot=self.email),
                                 button("Every month…", slot=self.schedule), self.status))
        self.body.addWidget(box)
        self.summary = ResultsTable()
        self.body.addWidget(self.summary, 1)

    def _save(self):
        from ... import audit_report as ar
        ar.save_options({**ar.options(), "district": self.district.text().strip(),
                         "to": self.to.text().strip()})

    def build_open(self):
        from ... import audit_report as ar
        self._save()
        y, m = self.month.currentData()

        def work():
            d = ar.build(y, m)
            return d, ar.save_html(d)

        def done(res):
            d, path = res
            self.summary.set_rows(["", "Count"], [
                ["Changes made", str(d["changes"])], ["Failed changes", str(d["failed"])],
                ["Approval requests", str(d["requests"])],
                ["Approved automatically", str(d["auto"])],
                ["Approved by email", str(d["by_email"])],
                ["Settings changed", str(len(d["settings_changes"]))],
                ["Unusual-activity findings", str(d["findings"])],
                ["Findings reviewed", str(d["f_reviewed"])]])
            self.status.setText(f"Saved: {path}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        Worker(work, on_done=done, on_error=lambda e: self.info(str(e)))

    def email(self):
        from ... import audit_report as ar
        self._save()
        y, m = self.month.currentData()
        lines = []
        Worker(ar.send, lines.append, "", y, m,
               on_done=lambda bad: self.info("\n".join(lines)),
               on_error=lambda e: self.info(str(e)))

    def schedule(self):
        from ... import audit_report as ar, tasks_health
        self._save()
        settings.set("auditreport/scheduled", True)
        try:
            tasks_health.create(dict(ar.TASK))
            self.info("Last month's audit report will be emailed on the 1st of each month.")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Saved, but the task couldn't be created here:\n{exc}")


# =========================================================== teacher lists ===
class TeacherListsPage(Page):
    title = "Teacher lists"
    subtitle = ("Each teacher gets only their own students who need a nudge: not signing in, "
                "no guardian invited, no Chromebook, or an overdue loaner – from the Classroom "
                "rosters.")

    def build(self):
        from ... import teacher_lists as tl
        o = tl.options()
        box, form = self.group("Settings")
        self.days = QSpinBox()
        self.days.setRange(3, 120)
        self.days.setValue(int(o["inactive_days"]))
        self.days.setSuffix(" days")
        self.g = QCheckBox("No guardian invited")
        self.g.setChecked(bool(o["guardians"]))
        self.d = QCheckBox("No Chromebook assigned")
        self.d.setChecked(bool(o["devices"]))
        self.ln = QCheckBox("Overdue loaner")
        self.ln.setChecked(bool(o["loaners"]))
        self.only = QLineEdit(o.get("only", ""))
        self.only.setPlaceholderText("optional – only these teachers (try it with a few "
                                     "first)")
        form.addRow("“Not signing in” means", self.days)
        form.addRow("Also flag", self.row(self.g, self.d, self.ln, stretch=True))
        form.addRow("Only", self.only)
        self.status = QLabel("", objectName="Muted")
        form.addRow("", self.row(button("Build the lists", "primary", self.load),
                                 button("Preview the selected teacher's email",
                                        slot=self.preview),
                                 button("Send now", slot=self.send),
                                 button("Every Monday…", slot=self.schedule), self.status))
        self.body.addWidget(box)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.lists = {}

    def _opts(self):
        from ... import teacher_lists as tl
        o = {**tl.options(), "inactive_days": self.days.value(), "guardians": self.g.isChecked(),
             "devices": self.d.isChecked(), "loaners": self.ln.isChecked(),
             "only": self.only.text().strip()}
        tl.save_options(o)
        return o

    def load(self):
        from ... import teacher_lists as tl
        o = self._opts()
        self.status.setText("Reading Classroom rosters (a few minutes for big districts)…")

        def done(res):
            self.lists, _u = res
            rows = []
            for t, per in sorted(self.lists.items()):
                n = len({s for r in per.values() for s, _n, _f in r})
                rows.append([t, str(len(per)), str(n),
                             "; ".join(f"{c} ({len(r)})" for c, r in list(per.items())[:4])])
            self.table.set_rows(["Teacher", "Classes", "Students to follow up", "Classes"],
                                rows)
            self.status.setText(f"{len(rows)} teacher(s) have someone to follow up on")
        Worker(tl.fetch, o, users=self.directory.users or None, on_done=done,
               on_error=lambda e: (self.status.setText(""), self.info(str(e))))

    def preview(self):
        from ... import teacher_lists as tl
        sel = self.table.selected_dicts()
        if not sel or sel[0]["Teacher"] not in self.lists:
            self.info("Build the lists and select a teacher first.")
            return
        _s, body = tl.render(sel[0]["Teacher"], self.lists[sel[0]["Teacher"]], self._opts())
        path = os.path.join(_tf.folder(), "gambit_teacher_preview.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def send(self):
        from ... import teacher_lists as tl
        self._opts()
        if not self.confirm("Email every teacher on the list now?"):
            return
        lines = []
        Worker(tl.send, lines.append, users=self.directory.users or None,
               on_done=lambda bad: self.info("\n".join(lines[-20:])),
               on_error=lambda e: self.info(str(e)))

    def schedule(self):
        from ... import tasks_health, teacher_lists as tl
        self._opts()
        settings.set("teacherlists/scheduled", True)
        try:
            tasks_health.create(dict(tl.TASK))
            self.info("Teacher lists will go out every Monday at 6:45 AM.")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Saved, but the task couldn't be created here:\n{exc}")
