"""Round 12 screens: security baseline, daily Classroom roster sync, records requests,
day-one readiness, lost & stolen Chromebooks, run later & change freezes, the request
catalog and the release check."""

from __future__ import annotations

import datetime
import os

from PySide6.QtCore import QDate, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QInputDialog, QLabel, QLineEdit, QSpinBox, QTabWidget,
)

from ... import team
from ...settings import settings
from ..pickers import OUField, PersonField
from ..steps import Step, StepList
from ..tools_base import ToolTab
from ..widgets import Page, ResultsTable, Worker, button
from .round11_pages import run_or_request


def _csv():
    from ...directory import run_gam_csv
    return lambda a: run_gam_csv(a, 3600)


def _text():
    from ...directory import run_gam_text
    return lambda a, t=300: run_gam_text(a, t)


def _schedule(page, key, task, msg):
    from ... import tasks_health
    settings.set(key, True)
    try:
        tasks_health.create(dict(task))
        page.info(msg)
    except Exception as exc:  # noqa: BLE001
        page.info(f"Saved, but the task couldn't be created here:\n{exc}")


# =========================================================== security baseline ===
class BaselinePage(Page):
    title = "Security baseline"
    subtitle = ("Your Google settings checked against a K-12 recommended baseline: student "
                "sharing, SafeSearch and YouTube, less-secure apps, 2-Step Verification, "
                "Chrome guest mode and more – with a score and a fix list.")

    def build(self):
        from ...tools import baseline as bl
        o = bl.options()
        box, form = self.group("Check these org units")
        self.stu = OUField(self.directory, "/Students")
        self.stu.set_path(o["students"])
        self.staff = OUField(self.directory, "/Staff")
        self.staff.set_path(o["staff"])
        self.dev = OUField(self.directory, "/ (Chromebooks)")
        self.dev.set_path(o["devices"])
        form.addRow("Students", self.stu)
        form.addRow("Staff", self.staff)
        form.addRow("Chromebooks", self.dev)
        self.score = QLabel("")
        self.score.setStyleSheet("font-size:20pt;font-weight:600;")
        self.status = QLabel("", objectName="Muted")
        form.addRow("", self.row(button("Check now", "primary", self.check),
                                 button("Every Monday…", slot=lambda: _schedule(
                                     self, "baseline/scheduled", bl.TASK,
                                     "The baseline is scored every Monday at 6:10 AM; you get "
                                     "an alert if the score drops.")),
                                 self.score, self.status))
        self.body.addWidget(box)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.body.addLayout(self.row(button("Fix selected (Chrome)", "primary", self.fix),
                                     button("Open the Admin console page", slot=self.console),
                                     button("Don't check this", slot=self.skip),
                                     button("Check everything again", slot=self.unskip)))
        self.steps = StepList(self)
        self.steps.setMaximumHeight(130)
        self.body.addWidget(self.steps)
        self.results = []

    def _opts(self):
        from ...tools import baseline as bl
        o = {**bl.options(), "students": self.stu.path() or "/Students",
             "staff": self.staff.path() or "/Staff", "devices": self.dev.path() or "/"}
        bl.save_options(o)
        return o

    def check(self):
        from ...tools import baseline as bl
        o = self._opts()
        self.status.setText("Reading your settings…")

        def done(res):
            self.results, sc = res
            self.score.setText(f"{sc}%")
            h = ["Check", "Org unit", "Result", "Now", "How to fix", "Why"]
            self.table.set_rows(h, [[r[k] for k in h] for r in sorted(
                self.results, key=lambda r: r["ok"])])
            n = sum(not r["ok"] for r in self.results)
            self.status.setText(f"{n} to fix of {len(self.results)} check(s)")
        Worker(bl.run, None, o, on_done=done,
               on_error=lambda e: (self.status.setText(""), self.info(str(e))))

    def _sel(self):
        keys = {(s["Check"], s["Org unit"]) for s in self.table.selected_dicts()}
        return [r for r in self.results if (r["Check"], r["Org unit"]) in keys]

    def fix(self):
        sel = [r for r in self._sel() if r["args"]]
        if not sel:
            self.info("Select Chrome checks marked “GAMbit can fix it”. Admin console settings "
                      "have to be changed there – use Open the Admin console page.")
            return
        run_or_request(self, self.steps, [(f"{r['Check']} – {r['Org unit']}", r["args"])
                                          for r in sel], "Fix security baseline",
                       "Security baseline fixes:\n" + "\n".join(f"• {r['Check']} "
                                                                f"({r['Org unit']})"
                                                                for r in sel),
                       lambda _s: self.check())

    def console(self):
        for r in self._sel()[:3]:
            if r["How to fix"].startswith("http"):
                QDesktopServices.openUrl(QUrl(r["How to fix"]))

    def skip(self):
        from ...tools import baseline as bl
        sel = self._sel()
        if sel and self.confirm("Stop checking: " + ", ".join(r["Check"] for r in sel) + "?"):
            o = bl.options()
            o["off"] = sorted(set(o.get("off", [])) | {r["id"] for r in sel})
            bl.save_options(o)
            self.check()

    def unskip(self):
        from ...tools import baseline as bl
        bl.save_options({**bl.options(), "off": []})
        self.check()


# =========================================================== classroom sync ===
class ClassroomSyncTab(ToolTab):
    intro = ("Keep the classes GAMbit created from the SIS matched to the SIS all year: "
             "students added as schedules change and (if you choose) removed when they drop. "
             "Preview first; the daily task stops if there are unusually many changes.")

    def build(self):
        from ...tools import classroom_sync as cs
        o = cs.options()
        box, form = self.page.group("Settings")
        self.src = QComboBox()
        self.src.addItem("Live from the SIS (Settings → Integrations)", "sis")
        self.src.addItem("A OneRoster .zip or sections file", "file")
        self.src.setCurrentIndex(max(0, self.src.findData(o["source"])))
        self.path = QLineEdit(o.get("path", ""))
        self.remove = QCheckBox("Also remove students who dropped the class")
        self.remove.setChecked(bool(o["remove"]))
        self.teach = QCheckBox("Add co-teachers")
        self.teach.setChecked(bool(o["teachers"]))
        self.cap = QSpinBox()
        self.cap.setRange(10, 100000)
        self.cap.setValue(int(o["max_changes"]))
        form.addRow("Enrollments from", self.src)
        form.addRow("File", self.row(self.path, button("Browse…", slot=self._browse),
                                     stretch=False))
        form.addRow("", self.remove)
        form.addRow("", self.teach)
        form.addRow("Stop if more than this many changes", self.cap)
        form.addRow("", self.row(button("Preview", "primary", self.preview),
                                 button("Apply", slot=self.apply),
                                 button("Every morning…", slot=self.schedule), self.status))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.plan = []

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Sections", "", "OneRoster or CSV (*.zip *.csv)")
        if p:
            self.path.setText(p)
            self.src.setCurrentIndex(1)

    def _opts(self):
        from ...tools import classroom_sync as cs
        o = {**cs.options(), "source": self.src.currentData(), "path": self.path.text().strip(),
             "remove": self.remove.isChecked(), "teachers": self.teach.isChecked(),
             "max_changes": self.cap.value()}
        cs.save_options(o)
        return o

    def preview(self):
        from ...tools import classroom_sync as cs
        o = self._opts()
        self.status.setText("Reading the SIS and Classroom rosters…")

        def done(p):
            self.plan = p
            t = cs.totals(p)
            self.table.set_rows(["Class", "Add", "Remove", "Co-teachers"],
                                [[x["class"], ", ".join(x["adds"][:6]) + (
                                    f" (+{len(x['adds']) - 6})" if len(x["adds"]) > 6 else ""),
                                  ", ".join(x["removes"][:6]), ", ".join(x["teacher_adds"])]
                                 for x in p])
            warn = " – ⚠ more than your limit; the daily task would stop" if cs.too_big(p, o) \
                else ""
            self.status.setText(f"{t['classes']} class(es) differ: +{t['adds']} / −{t['removes']}"
                                f" students, {t['teachers']} co-teacher(s){warn}")
        Worker(cs.build, o, _csv(), on_done=done,
               on_error=lambda e: (self.status.setText(""), self.info(str(e))))

    def apply(self):
        if not self.plan:
            self.info("Preview first.")
            return
        steps = [(f"{x['class']}: {c[2]} {c[3]} {c[4]}", c) for x in self.plan
                 for c in x["commands"]]
        if self.confirm(f"Make {len(steps)} change(s) to Classroom rosters?"):
            self.run_steps(self.steps, steps)

    def schedule(self):
        from ...tools import classroom_sync as cs
        self._opts()
        _schedule(self, "classroomsync/scheduled", cs.TASK,
                  "Classroom rosters will be synced every morning at 5:35 AM.")


# =========================================================== records requests ===
class RecordDialog(QDialog):
    def __init__(self, parent, directory):
        super().__init__(parent)
        from ... import records as rc
        self.setWindowTitle("New records request")
        f = QFormLayout(self)
        self.who = PersonField(directory, "whose records? (student or staff account)")
        self.kind = QComboBox()
        for k, (label, days) in rc.KINDS.items():
            self.kind.addItem(label + (f" – {days} days" if days else ""), k)
        self.by = QLineEdit(placeholderText="who asked (parent, attorney, HR…)")
        self.received = QDateEdit(QDate.currentDate())
        self.received.setCalendarPopup(True)
        self.corp = {}
        for k, label in rc.CORPORA.items():
            cb = QCheckBox(label)
            cb.setChecked(k in ("mail", "drive"))
            self.corp[k] = cb
        self.hold = QCheckBox("Place a Vault hold first (nothing can be deleted)")
        self.notes = QLineEdit(placeholderText="optional")
        f.addRow("Account", self.who)
        f.addRow("Kind", self.kind)
        f.addRow("Requested by", self.by)
        f.addRow("Received", self.received)
        f.addRow("Include", page_row(list(self.corp.values())))
        f.addRow("", self.hold)
        f.addRow("Notes", self.notes)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.kind.currentIndexChanged.connect(
            lambda *_: self.hold.setChecked(self.kind.currentData() == "legal"))

    def value(self, who: str) -> dict:
        from ... import records as rc
        return rc.new(self.who.email(), self.kind.currentData(), self.by.text(),
                      [k for k, cb in self.corp.items() if cb.isChecked()],
                      self.hold.isChecked(), self.notes.text().strip(),
                      self.received.date().toPython().isoformat(), who)


def page_row(widgets):
    from PySide6.QtWidgets import QHBoxLayout, QWidget
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        h.addWidget(x)
    h.addStretch(1)
    return w


class RecordsPage(Page):
    title = "Records requests"
    subtitle = ("FERPA, legal and public-records requests in one place: GAMbit creates the "
                "Vault matter, places a hold if needed, starts the exports, tracks the deadline "
                "and downloads the files – with a record of every step.")

    def build(self):
        self.body.addLayout(self.row(button("New request…", "primary", self.new),
                                     button("Start (matter, hold, exports)", slot=self.start),
                                     button("Check exports", slot=self.check),
                                     button("Download…", slot=self.download),
                                     button("Mark delivered", slot=self.delivered),
                                     button("Close the matter", "danger", self.close_matter),
                                     button("Open a ticket", slot=self.ticket),
                                     button("Save searches in Vault",
                                            slot=self.save_queries)))
        self.show_all = QCheckBox("Show closed requests too")
        self.show_all.toggled.connect(self.refresh)
        self.status = QLabel("", objectName="Muted")
        self.body.addLayout(self.row(self.show_all, self.status))
        self.table = ResultsTable()
        self.table.row_clicked.connect(lambda *_: self._detail())
        self.body.addWidget(self.table, 1)
        self.detail = QLabel("", wordWrap=True)
        self.body.addWidget(self.detail)
        self.refresh()

    def on_show(self):
        self.refresh()

    def refresh(self, *_):
        from ... import records as rc
        today = datetime.date.today().isoformat()
        items = rc.load()
        if not self.show_all.isChecked():
            items = [r for r in items if r["status"] != "closed"]
        self.table.set_rows(["#", "Account", "Kind", "Requested by", "Received", "Due",
                             "Status", "Exports"],
                            [[r["id"], r["email"], rc.KINDS.get(r["kind"], ("?",))[0],
                              r["requested_by"], r["received"],
                              (r["due"] + (" ⚠ overdue" if r["due"] and r["due"] < today and
                                           r["status"] not in ("delivered", "closed") else ""))
                              if r["due"] else "–", r["status"],
                              ", ".join(f"{e['corpus']}: {e['status'].lower()}"
                                        for e in r["exports"])] for r in items])

    def save_queries(self):
        from .round14_pages import vault_queries
        vault_queries(self, self._cur()[1])

    def _cur(self):
        from ... import records as rc
        ids = self.table.selected_values("#")
        items = rc.load()
        return items, next((r for r in items if ids and r["id"] == ids[0]), None)

    def _detail(self):
        _items, r = self._cur()
        self.detail.setText("<br>".join(r["log"][-10:]) + (f"<br>Vault matter: {r['matter']}"
                                                           if r.get("matter") else "")
                            if r else "")

    def _save(self, items):
        from ... import records as rc
        rc.save(items)
        self.refresh()

    def new(self):
        from ... import records as rc
        d = RecordDialog(self, self.directory)
        if d.exec():
            r = d.value(team.me())
            if "@" not in r["email"]:
                self.info("Choose the account.")
                return
            self._save(rc.load() + [r])

    def start(self):
        from ... import records as rc
        items, r = self._cur()
        if not r:
            self.info("Select a request.")
            return
        if not self.confirm(f"Create the Vault matter for {r['email']}" +
                            (", place the hold" if r["hold"] else "") +
                            f" and export {', '.join(rc.CORPORA[c] for c in r['corpora'])}?"):
            return
        self.status.setText("Working in Vault…")

        def done(probs):
            self._save(items)
            self.status.setText("")
            self.info("Started. Exports usually take from a few minutes to a few hours – use "
                      "Check exports." if not probs else "Some steps failed:\n" +
                      "\n".join(probs))
        Worker(rc.start, r, _text(), team.me(), on_done=done,
               on_error=lambda e: (self.status.setText(""), self.info(str(e))))

    def check(self):
        from ... import records as rc
        items, r = self._cur()
        if not r or not r.get("matter"):
            self.info("Select a request that has been started.")
            return

        def got(rows):
            if rows is None:
                return
            n = rc.update_status(r, rows)
            self._save(items)
            self.status.setText(f"{n} of {len(r['exports'])} export(s) finished")
        self.page_read(rc.status_args(r), got)

    def page_read(self, args, then):
        import csv
        import io

        def done(code, out, _e):
            then(list(csv.DictReader(io.StringIO(out or ""))) if code == 0 else None)
        self.runner.run(args, done, quiet_stdout=True)

    def download(self):
        from ... import records as rc
        items, r = self._cur()
        if not r or not any(e["status"] == "COMPLETED" for e in r["exports"]):
            self.info("Select a request whose exports have finished (Check exports).")
            return
        folder = QFileDialog.getExistingDirectory(self, "Save the export files in")
        if not folder:
            return
        folder = os.path.join(folder, f"{r['email']} {r['id']}")
        os.makedirs(folder, exist_ok=True)

        def finished(_s):
            rc._log(r, f"downloaded to {folder} by {team.me()}")
            r["status"] = "downloaded"
            self._save(items)
            self.info(self.steps_summary())
        steps = [Step(f"Download {e['corpus']}", rc.download_args(r, e["id"], folder))
                 for e in r["exports"] if e["status"] == "COMPLETED"]
        self._steps().run(steps, finished)

    def _steps(self):
        if not hasattr(self, "_sl"):
            self._sl = StepList(self)
            self._sl.setMaximumHeight(120)
            self.body.addWidget(self._sl)
        return self._sl

    def steps_summary(self):
        return self._steps().summary()

    def delivered(self):
        from ... import records as rc
        items, r = self._cur()
        if not r:
            return
        to, ok = QInputDialog.getText(self, "Delivered", "Delivered to (and how)?")
        if ok:
            r["status"] = "delivered"
            rc._log(r, f"delivered to {to.strip()} by {team.me()}")
            self._save(items)

    def close_matter(self):
        from ... import records as rc
        items, r = self._cur()
        if not r or not r.get("matter"):
            return
        if not self.confirm("Close the Vault matter? Any holds in it are released and the "
                            "exports are no longer kept."):
            return

        def finished(_s):
            r["status"] = "closed"
            rc._log(r, f"matter closed by {team.me()}")
            self._save(items)
        self._steps().run([Step(f"Close matter {r['matter']}", rc.close_args(r))], finished)

    def ticket(self):
        from ... import records as rc
        from ...integrations import ticketing as tk
        items, r = self._cur()
        if not r:
            return
        if not (tk.configured() and tk.can("create")):
            self.info("Set up your help desk in Settings → Integrations first.")
            return

        def done(tid):
            r["ticket"] = tid
            rc._log(r, f"ticket {tid} opened")
            self._save(items)
        Worker(tk.create, f"Records request: {r['email']}",
               f"{rc.KINDS.get(r['kind'], ('?',))[0]}\nRequested by {r['requested_by']} on "
               f"{r['received']}; due {r['due'] or '–'}.\nVault matter {r.get('matter') or '–'}.",
               on_done=done, on_error=lambda e: self.info(str(e)))


# =========================================================== day-one readiness ===
class ReadinessTab(ToolTab):
    intro = ("For staff whose accounts were created in the last few days: is the account "
             "active, licensed, in the right groups, with a signature, a Chromebook and "
             "Classroom teacher access? Fix the gaps in one go and let HR know.")

    def build(self):
        from ...tools import readiness as rd
        o = rd.options()
        box, form = self.page.group("Settings")
        self.root = OUField(self.directory, "/Staff")
        self.root.set_path(o["staff_root"])
        self.days = QSpinBox()
        self.days.setRange(1, 90)
        self.days.setValue(int(o["days"]))
        self.days.setSuffix(" days")
        self.cls = QLineEdit(o.get("classroom_group", ""))
        self.cls.setPlaceholderText("optional – e.g. classroom_teachers@ (Classroom teacher "
                                    "access)")
        self.dev = QCheckBox("Check a Chromebook is assigned")
        self.dev.setChecked(bool(o["device"]))
        self.hr = QLineEdit(o.get("hr_email", ""))
        self.hr.setPlaceholderText("optional – hr@… gets the readiness summary")
        form.addRow("New staff are under", self.root)
        form.addRow("Accounts created in the last", self.days)
        form.addRow("Classroom teachers group", self.cls)
        form.addRow("", self.dev)
        form.addRow("Email the summary to", self.hr)
        form.addRow("", self.row(button("Check now", "primary", self.check),
                                 button("Fix the gaps for selected", slot=self.fix),
                                 button("Email the summary", slot=self.email), self.status))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(260)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.people, self.results = [], {}

    def _opts(self):
        from ...tools import readiness as rd
        o = {**rd.options(), "staff_root": self.root.path() or "/Staff",
             "days": self.days.value(), "classroom_group": self.cls.text().strip(),
             "device": self.dev.isChecked(), "hr_email": self.hr.text().strip()}
        rd.save_options(o)
        return o

    def check(self):
        from ... import google_io, onboard
        from ...tools import readiness as rd
        o = self._opts()
        dom = google_io.admin_email().split("@")[-1]

        def work():
            run = _csv()
            c, rows, e = run(rd.USERS_ARGS)
            if c != 0:
                raise RuntimeError((e or "GAM failed").strip()[-200:])
            ppl = rd.new_staff(rows, o)
            groups, sigs, devs = rd.gather(ppl, run, o)
            oo = onboard.options()
            return ppl, {p["email"]: rd.checks(p, groups.get(p["email"], set()),
                                               sigs.get(p["email"]), devs.get(p["email"]), oo,
                                               o, dom) for p in ppl}

        def done(res):
            self.people, self.results = res
            self.table.set_rows(["Account", "Name", "Created", "Org unit", "Ready?", "Missing",
                                 "Signed in"], rd.summary(self.people, self.results))
            ready = sum(1 for p in self.people if all(c["ok"] or c.get("info") for c in
                                                      self.results[p["email"]]))
            self.status.setText(f"{ready} of {len(self.people)} new staff ready")
        self.status.setText("Checking new staff…")
        Worker(work, on_done=done, on_error=lambda e: (self.status.setText(""),
                                                       self.info(str(e))))

    def fix(self):
        sel = set(self.table.selected_values("Account")) or {p["email"] for p in self.people}
        steps = [(f"{e}: {lab}", a) for e in sel for c in self.results.get(e, [])
                 if not c["ok"] for lab, a in c["fix"]]
        if not steps:
            self.info("Nothing GAMbit can fix automatically for these people.")
            return
        if self.confirm(f"Run {len(steps)} fix(es)?"):
            self.run_steps(self.steps, steps, lambda _s: self.check())

    def email(self):
        from ... import google_io
        from ...tools import readiness as rd
        to = self.hr.text().strip()
        if "@" not in to or not self.people:
            self.info("Check first, and fill in who gets the summary.")
            return
        body = "\n\n".join(rd.email_text(p, self.results[p["email"]]) for p in self.people)
        Worker(google_io.send_email, to, f"New staff readiness – {len(self.people)} person(s)",
               body, on_done=lambda _r: self.status.setText("Summary sent."),
               on_error=lambda e: self.info(str(e)))


# ============================================================= lost devices ===
class LostDevicesTab(ToolTab):
    intro = ("Mark a Chromebook lost or stolen: GAMbit disables it (it shows your “return to” "
             "message – set it in the Admin console under Devices → Chrome → Settings → "
             "Device → Disabled device return instructions), records its last user, sign-in "
             "and network, opens a ticket and writes a report for insurance or the police.")

    def build(self):
        from ...tools import lost_devices as ld
        o = ld.options()
        box, form = self.page.group("Report a device")
        self.sn = QLineEdit(placeholderText="serial number")
        self.how = QComboBox()
        self.how.addItems(["Lost", "Stolen"])
        self.by = QLineEdit(placeholderText="who reported it")
        self.details = QLineEdit(placeholderText="where / when, police report number…")
        self.ou = OUField(self.directory, "optional – e.g. /Chromebooks/Lost")
        self.ou.set_path(o.get("lost_ou", ""))
        form.addRow("Serial", self.row(self.sn, button("Look up", slot=self.lookup),
                                       stretch=False))
        form.addRow("", self.status)
        form.addRow("It's", self.how)
        form.addRow("Reported by", self.by)
        form.addRow("Details", self.details)
        form.addRow("Move it to", self.ou)
        form.addRow("", self.row(button("Mark it", "danger", self.mark)))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(220)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(button("It's been found", "primary", self.found),
                                    button("Open the report", slot=self.report)))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.facts = None
        self.refresh()

    def refresh(self):
        from ...tools import lost_devices as ld
        self.table.set_rows(["Serial", "Asset", "How", "Date", "Last user", "Last check-in",
                             "Status", "Ticket"],
                            [[r.get("serial", ""), (r.get("facts") or {}).get("asset", ""),
                              r.get("how", ""), r.get("date", ""),
                              (r.get("facts") or {}).get("last_user") or
                              (r.get("facts") or {}).get("user", ""),
                              str((r.get("facts") or {}).get("last_sync", ""))[:16],
                              r.get("status", ""), "yes" if r.get("ticket") else ""]
                             for r in reversed(ld.load()) if isinstance(r, dict)])

    def lookup(self, then=None):
        from ...tools import lost_devices as ld
        sn = self.sn.text().strip().upper()
        if not sn:
            return

        def got(rows):
            if not rows:
                self.status.setText("Not found in Google.")
                return
            self.facts = ld.facts(rows[0])
            f = self.facts
            self.status.setText(f"{f['model']} · assigned to {f['user'] or '–'} · last user "
                                f"{f['last_user'] or '–'} · last check-in {f['last_sync'] or '–'}"
                                f" · {f['status']}")
            if then:
                then()
        self.read(ld.info_args(sn), got)

    def mark(self):
        if not self.facts or self.facts["serial"] != self.sn.text().strip().upper():
            self.lookup(self.mark)
            return
        from ...tools import lost_devices as ld
        o = {**ld.options(), "lost_ou": self.ou.path()}
        ld.save_options(o)
        how = self.how.currentText().lower()
        f = self.facts
        if not self.confirm(f"Mark {f['serial']} as {how}? It will be disabled" +
                            (f" and moved to {o['lost_ou']}" if o["lost_ou"] else "") + "."):
            return

        def finished(_s):
            rec = ld.record(f, how, self.by.text().strip(), self.details.text().strip(),
                            team.me())
            rec["moved"] = bool(o["lost_ou"])
            self._ticket_and_report(rec)
        self.steps.run([Step(f"{f['serial']}: {c[3]}", c) for c in ld.mark_commands(f, how, o)],
                       finished)

    def _ticket_and_report(self, rec):
        from ...integrations import ticketing as tk
        from ...tools import lost_devices as ld

        def save_and_open(_r=None):
            items = ld.load()
            for i in items:
                if i["serial"] == rec["serial"] and i["date"] == rec["date"]:
                    i.update(ticket=rec.get("ticket", ""), moved=rec.get("moved"))
            ld.save(items)
            self.refresh()
            self._open(rec)
        if tk.configured() and tk.can("create"):
            def done(tid):
                rec["ticket"] = tid
                save_and_open()
            Worker(tk.create, f"Chromebook {rec['serial']} {rec['how']}",
                   f"{rec['how'].title()} – reported by {rec['reported_by']}. "
                   f"{rec['details']}\nLast user {rec['facts'].get('last_user')}, last "
                   f"check-in {rec['facts'].get('last_sync')}. Disabled by GAMbit.",
                   on_done=done, on_error=lambda _e: save_and_open())
        else:
            save_and_open()

    def _open(self, rec):
        import tempfile
        from ...tools import lost_devices as ld
        p = os.path.join(tempfile.gettempdir(), f"chromebook_{rec['serial']}_report.html")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(ld.report_html(rec, settings.get("auditreport/district", "") or ""))
        QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def _sel(self):
        from ...tools import lost_devices as ld
        s = self.table.selected_values("Serial")
        items = ld.load()
        return items, next((i for i in reversed(items) if s and i["serial"] == s[0]), None)

    def found(self):
        from ...integrations import ticketing as tk
        from ...tools import lost_devices as ld
        items, rec = self._sel()
        if not rec or rec["status"] != "missing":
            self.info("Select a missing device.")
            return

        def finished(_s):
            rec["status"] = "found"
            rec["found"] = datetime.date.today().isoformat()
            ld.save(items)
            self.refresh()
            if rec.get("ticket") and tk.configured() and tk.can("note"):
                Worker(tk.note, rec["ticket"], f"Chromebook {rec['serial']} found and "
                                               "re-enabled.", False, on_done=lambda _r: None,
                       on_error=lambda _e: None)
        self.steps.run([Step(f"{rec['serial']}: {c[3]}", c) for c in ld.found_commands(rec)],
                       finished)

    def report(self):
        _items, rec = self._sel()
        if rec:
            self._open(rec)


# ===================================================== run later & freezes ===
class ChangeCalendarPage(Page):
    title = "Run later & freezes"
    subtitle = ("Changes queued to run tonight or on a date, and change freezes – windows when "
                "risky changes are paused (state testing, the first week of school…).")

    def build(self):
        tabs = QTabWidget()
        self.tabs = tabs
        q = ToolTab(self)
        q.lay.addLayout(self.row(button("Queue a command…", "primary", self.queue_cmd),
                                 button("Run selected now", slot=self.run_now),
                                 button("Cancel selected", "danger", self.cancel)))
        self.qtable = ResultsTable()
        q.lay.addWidget(self.qtable, 1)
        self.steps = StepList(self)
        self.steps.setMaximumHeight(120)
        q.lay.addWidget(self.steps)
        tabs.addTab(q, "Run later")
        fz = ToolTab(self)
        fz.lay.addLayout(self.row(button("New freeze…", "primary", self.new_freeze),
                                  button("Delete selected", "danger", self.del_freeze)))
        self.ftable = ResultsTable()
        fz.lay.addWidget(self.ftable, 1)
        fz.lay.addWidget(QLabel("During a freeze the chosen kinds of change are blocked. A Full "
                                "admin can override with a reason (logged in the activity log "
                                "and the audit report); queued changes wait until it ends.",
                                objectName="Muted", wordWrap=True))
        tabs.addTab(fz, "Change freezes")
        cat = ToolTab(self)
        catalog_box(self, cat.lay)
        tabs.addTab(cat, "Request catalog")
        self.body.addWidget(tabs, 1)
        self.refresh()

    def on_show(self):
        self.refresh()

    def refresh(self):
        from ... import change_queue as cq
        self.items = cq.queue()
        self.qtable.set_rows(["When", "What", "Commands", "By", "Status", "Result", "id"],
                             [[i["when"].replace("T", " "), i["title"], str(len(i["commands"])),
                               i["by"], i["status"], i.get("result", ""), i["id"]]
                              for i in sorted(self.items, key=lambda x: x["when"],
                                              reverse=True)])
        self.qtable.hidden_columns = {"id"}
        self.fz = cq.freezes()
        self.ftable.set_rows(["Name", "From", "Until", "Paused", "By", "id"],
                             [[f["name"], f["start"], f["end"], ", ".join(f["categories"]),
                               f["by"], f["id"]] for f in self.fz])
        self.ftable.hidden_columns = {"id"}

    def queue_cmd(self):
        from ... import change_queue as cq
        from ...gam_runner import split_command
        text, ok = QInputDialog.getMultiLineText(self, "Queue a command",
                                                 "GAM command(s), one per line (without gam):")
        if not ok or not text.strip():
            return
        cmds = [split_command(ln.strip()[4:] if ln.strip().startswith("gam ") else ln.strip())
                for ln in text.splitlines() if ln.strip()]
        when = ask_when(self)
        if when:
            cq.add(cmds, when, cmds[0][0] + " " + " ".join(cmds[0][1:4]), team.me())
            self.refresh()

    def _sel(self):
        ids = set(self.qtable.selected_values("id"))
        return [i for i in self.items if i["id"] in ids]

    def run_now(self):
        from ... import change_queue as cq
        sel = [i for i in self._sel() if i["status"] == "waiting"]
        if not sel:
            return

        def finished(_s):
            items = cq.queue()
            for it in items:
                if it["id"] in {x["id"] for x in sel}:
                    it["status"], it["result"] = "done", self.steps.summary()
            cq.save_queue(items)
            self.refresh()
        self.steps.run([Step(i["title"], c) for i in sel for c in i["commands"]], finished)

    def cancel(self):
        from ... import change_queue as cq
        ids = {i["id"] for i in self._sel()}
        items = cq.queue()
        for it in items:
            if it["id"] in ids and it["status"] == "waiting":
                it["status"] = "cancelled"
        cq.save_queue(items)
        self.refresh()

    def new_freeze(self):
        from ... import change_queue as cq
        d = QDialog(self)
        d.setWindowTitle("New change freeze")
        f = QFormLayout(d)
        name = QLineEdit(placeholderText="e.g. Spring state testing")
        a = QDateEdit(QDate.currentDate())
        b = QDateEdit(QDate.currentDate().addDays(5))
        for x in (a, b):
            x.setCalendarPopup(True)
        cats = {}
        for c in ("delete", "suspend", "everyone", "chromebooks", "passwords", "groups",
                  "users", "classroom", "drive", "email", "other"):
            cb = QCheckBox(team.CATEGORIES[c].split(" (")[0])
            cb.setChecked(c in cq.RISKY_DEFAULT)
            cats[c] = cb
        f.addRow("Name", name)
        f.addRow("From", a)
        f.addRow("Until (inclusive)", b)
        for c, cb in cats.items():
            f.addRow("" if c != "delete" else "Pause", cb)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec():
            cq.save_freezes(cq.freezes() + [cq.new_freeze(
                name.text().strip() or "Change freeze", a.date().toPython().isoformat(),
                b.date().toPython().isoformat(), [c for c, cb in cats.items() if cb.isChecked()],
                team.me())])
            self.refresh()

    def del_freeze(self):
        from ... import change_queue as cq
        ids = set(self.ftable.selected_values("id"))
        cq.save_freezes([f for f in self.fz if f["id"] not in ids])
        self.refresh()


def ask_when(parent) -> str:
    from ... import change_queue as cq
    d = QDialog(parent)
    d.setWindowTitle("Run later")
    f = QFormLayout(d)
    tonight = cq.tonight()
    dt = QDateTimeEdit(datetime.datetime.fromisoformat(tonight))
    dt.setCalendarPopup(True)
    f.addRow("Run at", dt)
    f.addRow("", QLabel("The “staff requests” background task (every 15 minutes) runs it, so "
                        "the PC with the tasks must be on.", objectName="Muted", wordWrap=True))
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    f.addRow(bb)
    if d.exec():
        return dt.dateTime().toPython().isoformat(timespec="minutes")
    return ""


# =========================================================== request catalog ===
def catalog_box(page, lay):
    from ... import request_catalog as rq
    o = rq.options()
    box, form = page.group("Request form for principals and secretaries")
    form.addRow(QLabel("Make a Google Form with a <b>What do you need?</b> question (Substitute "
                       "account · Group change · New Classroom class · Move a Chromebook · "
                       "Something else) and these optional questions: <i>First name, Last name, "
                       "End date, Group email, People to add, People to remove, Class name, "
                       "Section, Teacher email, Serial number, Move to, Details</i>. Turn on "
                       "<i>Collect email addresses</i> and link the responses to a Sheet. Each "
                       "response becomes an approval request (or runs straight away if your "
                       "approval rules allow it).", wordWrap=True))
    url = QLineEdit(o["sheet_url"])
    url.setPlaceholderText("Response sheet link")
    tab = QLineEdit(o["tab"])
    tab.setPlaceholderText("Form Responses 1")
    root = OUField(page.directory, "/Staff")
    root.set_path(o["staff_root"])
    sub_ou = OUField(page.directory, "/Staff/Temporary")
    sub_ou.set_path(o["sub_ou"])
    tpl = QLineEdit(o["sub_email"])
    days = QSpinBox()
    days.setRange(1, 365)
    days.setValue(int(o["sub_days"]))
    days.setSuffix(" days if no end date")
    form.addRow("Responses sheet", page.row(url, tab, stretch=False))
    form.addRow("Who can ask (staff under)", root)
    form.addRow("Substitute accounts go in", sub_ou)
    form.addRow("Substitute email", tpl)
    form.addRow("Substitute accounts last", days)
    status = QLabel(f"Last checked {settings.get('catalog/last', '') or 'never'}",
                    objectName="Muted")

    def save():
        rq.save_options({**rq.options(), "sheet_url": url.text().strip(),
                         "tab": tab.text().strip(), "staff_root": root.path() or "/Staff",
                         "sub_ou": sub_ou.path() or "/Staff/Temporary",
                         "sub_email": tpl.text().strip(), "sub_days": days.value()})

    def check():
        save()
        status.setText("Checking…")
        lines = []
        Worker(rq.process, lines.append, on_done=lambda _r: (
            settings.set("catalog/last", datetime.datetime.now().isoformat(timespec="minutes")),
            status.setText(f"{len(lines)} new"), page.info("\n".join(lines) or
                                                            "No new requests.")),
            on_error=lambda e: (status.setText(""), page.info(str(e))))
    form.addRow("", page.row(button("Save", slot=save), button("Check now", slot=check),
                             status))
    form.addRow("", QLabel("The “staff requests” background task checks this every 15 "
                           "minutes once it's set up.", objectName="Muted", wordWrap=True))
    lay.addWidget(box)
    lay.addStretch(1)


# ============================================================== release check ===
def release_check_dialog(page):
    from ... import release_check as rc

    def done(res):
        text = "\n".join(f"{'✔' if r['OK'] else '✖'} {r['Check']}" +
                         (f" – {r['Detail']}" if r["Detail"] else "") for r in res)
        page.info("Release check:\n\n" + text)
    Worker(rc.run, on_done=done, on_error=lambda e: page.info(str(e)))


__all__ = ["BaselinePage", "ClassroomSyncTab", "RecordsPage", "ReadinessTab",
           "LostDevicesTab", "ChangeCalendarPage", "ask_when", "release_check_dialog"]
