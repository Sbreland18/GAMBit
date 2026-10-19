"""Round 13 pages: admin access review, account timing, storage forecast, students going
quiet and stale content."""

from __future__ import annotations

import datetime

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QInputDialog, QLabel, QLineEdit, QPlainTextEdit,
    QSpinBox, QTabWidget,
)

from ... import team
from ...settings import settings
from ..steps import StepList
from ..widgets import Page, ResultsTable, Worker, button
from .round11_pages import run_or_request
from .round13_tabs import _csv, fill


def _steps(page) -> StepList:
    if not hasattr(page, "_sl"):
        page._sl = StepList(page)
        page._sl.setMaximumHeight(130)
        page.body.addWidget(page._sl)
    return page._sl


def _schedule(page, key, task, msg):
    from ... import tasks_health
    settings.set(key, True)
    try:
        tasks_health.create(dict(task))
        page.info(msg)
    except Exception as exc:  # noqa: BLE001
        page.info(f"Saved, but the task couldn't be created here:\n{exc}")


# ============================================================ access review ===
class AccessReviewPage(Page):
    title = "Access review"
    subtitle = ("Every Google admin role with 2-Step Verification, last sign-in and admin "
                "actions in the last 90 days. Mark each Keep or Remove and sign off – the "
                "review is saved for audits and cyber insurance.")

    def build(self):
        from ... import access_review as ar
        o = ar.options()
        self.former = QLineEdit(o["former_root"])
        self.remind = QLineEdit(o.get("remind", ""))
        self.remind.setPlaceholderText("optional – who is reminded each quarter")
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(button("Load admins", "primary", self.load),
                                     QLabel("Leavers' org unit"), self.former,
                                     QLabel("Remind"), self.remind,
                                     button("Save", slot=self._save)))
        self.body.addWidget(self.status)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.body.addLayout(self.row(button("Mark selected Keep", slot=lambda: self.mark("Keep")),
                                     button("Mark selected Remove", "danger",
                                            lambda: self.mark("Remove")),
                                     button("Sign off the review…", "primary", self.sign),
                                     button("Past reviews", slot=self.past)))
        self.rows, self.decisions = [], {}
        last = ar.history()
        self.status.setText(("Last review: " + last[-1]["date"] + " by " + last[-1]["by"])
                            if last else "No review signed off yet.")

    def _save(self):
        from ... import access_review as ar
        ar.save_options({**ar.options(), "former_root": self.former.text().strip(),
                         "remind": self.remind.text().strip()})

    def load(self):
        from ... import access_review as ar
        self._save()
        self.status.setText("Reading admin roles, accounts and 90 days of the admin log…")

        def done(res):
            self.rows, probs = res
            self.decisions = {r["id"]: ("Remove" if r["risk"] >= 5 else "Keep")
                              for r in self.rows}
            self._show()
            self.status.setText(f"{len(self.rows)} role assignment(s) · "
                                f"{sum(1 for r in self.rows if r['Flags'])} flagged" +
                                (" · " + "; ".join(probs) if probs else ""))
        Worker(ar.gather, on_done=done, on_error=lambda e: self.status.setText(str(e)))

    def _show(self):
        for r in self.rows:
            r["Decision"] = self.decisions.get(r["id"], "Keep")
        fill(self.table, self.rows, ["Decision", "Admin", "Role", "Scope", "2SV",
                                     "Last sign-in", "Admin actions", "Flags", "id"])

    def mark(self, how):
        for i in self.table.selected_values("id"):
            self.decisions[i] = how
        self._show()

    def sign(self):
        from ... import access_review as ar
        if not self.rows:
            self.info("Load the admins first.")
            return
        rem = [r for r in self.rows if self.decisions.get(r["id"]) == "Remove"]
        note, ok = QInputDialog.getText(self, "Sign off", f"Signing off as {team.me()}.\n"
                                        f"{len(rem)} role(s) marked Remove. Note (optional):")
        if not ok:
            return
        ar.sign_off(self.rows, self.decisions, team.me(), note)
        self.status.setText(f"Signed off {datetime.date.today()} by {team.me()}.")
        if rem:
            run_or_request(self, _steps(self), [(f"Remove {r['Role']} from {r['Admin']}",
                                                 ar.remove_args(r["id"])) for r in rem
                                                if r["id"]],
                           "Remove admin roles (access review)",
                           "Quarterly access review – marked Remove")

    def past(self):
        from ... import access_review as ar
        h = ar.history()
        if not h:
            self.info("No reviews yet.")
            return
        self.info("\n".join(f"{r['date']} – {r['by']}: {len(r['rows'])} role(s), "
                            f"{sum(1 for x in r['rows'] if x['Decision'] == 'Remove')} removed"
                            + (f" – {r['note']}" if r.get("note") else "")
                            for r in reversed(h[-12:])))


# ============================================================ account timing ===
class AccountTimingPage(Page):
    title = "Account timing"
    subtitle = ("How long it takes from a new account to its first sign-in, from leaving to "
                "being suspended, and to decide approvals. Medians go on the weekly "
                "scorecard.")

    def build(self):
        from ... import lifecycle as lc
        o = lc.options()
        self.on = QCheckBox("Track first sign-ins every night")
        self.on.setChecked(bool(settings.get("lifecycle/on", False)))
        self.on.toggled.connect(lambda v: settings.set("lifecycle/on", v))
        self.leavers = QLineEdit(o["leaver_ous"])
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(button("Refresh", "primary", self.refresh),
                                     button("Note sign-ins now", slot=self.observe), self.on,
                                     QLabel("Leavers' org units"), self.leavers))
        self.body.addWidget(self.status)
        self.tabs = QTabWidget()
        self.new_t, self.leave_t, self.appr_t = ResultsTable(), ResultsTable(), ResultsTable()
        self.tabs.addTab(self.new_t, "New accounts")
        self.tabs.addTab(self.leave_t, "Leavers")
        self.tabs.addTab(self.appr_t, "Approvals && offboarding")
        self.body.addWidget(self.tabs, 1)

    def observe(self):
        from ... import lifecycle as lc
        Worker(lc.run, lambda _m: None, on_done=lambda n: (
            self.status.setText(f"Tracking {n} new account(s)."), self.refresh()),
            on_error=lambda e: self.info(str(e)))

    def refresh(self):
        from ... import lifecycle as lc
        lc.save_options({**lc.options(), "leaver_ous": self.leavers.text().strip()})

        def done(s):
            late = int(lc.options()["late_days"])
            fill(self.new_t, s["new"], ["School", "New accounts", "Signed in",
                                        "Median days to first sign-in",
                                        f"Not signed in after {late} days"])
            fill(self.leave_t, s["leavers"], ["Account", "Moved to leavers", "Suspended",
                                              "Days"])
            a, ob = s["approvals"], s["offboarding"]
            rows = [{"What": "Approvals decided", "Median": f"{a['median_hours']} h"
                     if a["median_hours"] is not None else "–", "Count": a["count"]}]
            rows += [{"What": f"  {k}", "Median": f"{v} h", "Count": ""}
                     for k, v in a["by_category"].items()]
            rows.append({"What": "Waiting now", "Median": a["oldest_since"] and
                         f"oldest since {a['oldest_since']}", "Count": a["pending"]})
            rows.append({"What": "Offboarding: start → today's steps done",
                         "Median": f"{ob['median_hours']} h" if ob["median_hours"] is not None
                         else "–", "Count": ob["count"]})
            fill(self.appr_t, rows, ["What", "Median", "Count"])
            sv = lc.score_values(s)
            self.status.setText(" · ".join(f"{k.replace('_', ' ')}: {v}" for k, v in sv.items())
                                or "Not enough history yet – turn on nightly tracking.")
        Worker(lc.summary, on_done=done, on_error=lambda e: self.status.setText(str(e)))

    def on_show(self):
        if not getattr(self, "_shown", False):
            self._shown = True
            self.refresh()


# =========================================================== storage forecast ===
class StorageForecastPage(Page):
    title = "Storage forecast"
    subtitle = ("When the district's pooled storage runs out at today's rate, which schools "
                "are growing fastest, and how much leavers are holding.")

    def build(self):
        from ... import storage_forecast as sf
        o = sf.options()
        self.limit = QDoubleSpinBox()
        self.limit.setRange(1, 100000)
        self.limit.setValue(float(o["limit_tb"]))
        self.limit.setSuffix(" TB pooled storage")
        self.on = QCheckBox("Add a data point every week")
        self.on.setChecked(bool(settings.get("storage/on", False)))
        self.on.toggled.connect(lambda v: settings.set("storage/on", v))
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(QLabel("District has"), self.limit,
                                     button("Measure now", "primary", self.measure), self.on,
                                     button("Mailbox sizes…", slot=self.mailboxes)))
        self.headline = QLabel("", objectName="H2", wordWrap=True)
        self.body.addWidget(self.headline)
        self.body.addWidget(self.status)
        self.tabs = QTabWidget()
        self.trend, self.schools, self.top = ResultsTable(), ResultsTable(), ResultsTable()
        self.tabs.addTab(self.trend, "History")
        self.tabs.addTab(self.schools, "By school")
        self.tabs.addTab(self.top, "Biggest users")
        self.body.addWidget(self.tabs, 1)
        self.show_forecast()

    def _save(self):
        from ... import storage_forecast as sf
        sf.save_options({**sf.options(), "limit_tb": self.limit.value()})

    def mailboxes(self):
        from .round15_tabs import MailboxStatsDialog
        MailboxStatsDialog(self).exec()

    def show_forecast(self, usage: dict | None = None):
        from ... import storage_forecast as sf
        items = sf.history()
        f = sf.forecast(items, self.limit.value())
        if items:
            self.headline.setText(f"{f['now_tb']} TB used ({f['pct']}%) · growing "
                                  f"{round(f['per_month_tb'] * 1024)} GB a month" +
                                  (f" · full around {f['full_date']}" if f["full_date"] else
                                   ""))
        else:
            self.headline.setText("No measurements yet – click Measure now.")
        fill(self.trend, [{"Week": i["date"], "TB": round(i["total_mb"] / 1024 / 1024, 2)}
                          for i in reversed(items)], ["Week", "TB"])
        fill(self.schools, sf.school_trend(items), ["School", "Now (TB)",
                                                    "Growth per month (GB)"])
        if usage:
            fill(self.top, usage["top"], ["Person", "School", "GB", "Drive GB", "Gmail GB",
                                          "Leaver"])
            self.status.setText(f"Leavers and suspended accounts hold "
                                f"{round(usage['leavers_mb'] / 1024 / 1024, 2)} TB "
                                f"({usage['leavers']} accounts).")

    def measure(self):
        from ... import storage_forecast as sf
        self._save()
        users = self.directory.users

        def work():
            c, rows, e = _csv()(sf.REPORT_ARGS)
            if c != 0:
                raise RuntimeError((e or "").strip()[-200:])
            u = sf.usage(rows, users, sf.options())
            sf.save_history(sf.add_week(sf.history(), u))
            return u
        self.status.setText("Reading storage use (Google's numbers are 2–3 days behind)…")
        Worker(work, on_done=self.show_forecast, on_error=lambda e: self.status.setText(str(e)))


# ======================================================== students going quiet ===
class GoingQuietPage(Page):
    title = "Students going quiet"
    subtitle = ("Students whose activity has dropped off across Google sign-ins, Classroom "
                "work and Chromebooks – a weekly list for each school's counselors.")

    def build(self):
        from ... import going_quiet as gq
        o = gq.options()
        box, form = self.group("Settings")
        self.si = QSpinBox()
        self.si.setRange(3, 120)
        self.si.setValue(int(o["signin_days"]))
        self.si.setSuffix(" days without a sign-in")
        self.miss = QSpinBox()
        self.miss.setRange(1, 100)
        self.miss.setValue(int(o["missing"]))
        self.miss.setSuffix(" or more missing assignments")
        self.dev = QSpinBox()
        self.dev.setRange(3, 120)
        self.dev.setValue(int(o["device_days"]))
        self.dev.setSuffix(" days since their Chromebook was used")
        self.cls = QCheckBox("Classroom (slow in big districts)")
        self.cls.setChecked(bool(o["classroom"]))
        self.devs = QCheckBox("Chromebooks")
        self.devs.setChecked(bool(o["devices"]))
        self.min = QComboBox()
        self.min.addItem("Any one sign", 1)
        self.min.addItem("Two or more signs", 2)
        self.min.addItem("All three signs", 3)
        self.min.setCurrentIndex(max(0, self.min.findData(int(o["min_signals"]))))
        self.who = QPlainTextEdit(o["counselors"])
        self.who.setPlaceholderText("one school per line:  Lincoln Middle = counselor1@, "
                                    "counselor2@")
        self.who.setMaximumHeight(80)
        form.addRow("Sign 1", self.si)
        form.addRow("Sign 2", self.row(self.miss, self.cls, stretch=False))
        form.addRow("Sign 3", self.row(self.dev, self.devs, stretch=False))
        form.addRow("List students with", self.min)
        form.addRow("Counselors", self.who)
        self.status = QLabel("", objectName="Muted")
        form.addRow("", self.row(button("Find now", "primary", self.find),
                                 button("Email counselors now", slot=self.send),
                                 button("Every Monday…", slot=lambda: _schedule(
                                     self, "goingquiet/scheduled", gq.TASK,
                                     "Counselors will get their list every Monday at "
                                     "7:05 AM.")), self.status))
        self.body.addWidget(box)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)

    def _opts(self):
        from ... import going_quiet as gq
        o = {**gq.options(), "signin_days": self.si.value(), "missing": self.miss.value(),
             "device_days": self.dev.value(), "classroom": self.cls.isChecked(),
             "devices": self.devs.isChecked(), "min_signals": self.min.currentData(),
             "counselors": self.who.toPlainText()}
        gq.save_options(o)
        return o

    def find(self):
        from ... import going_quiet as gq
        o = self._opts()
        users = self.directory.users

        def done(rows):
            fill(self.table, rows, ["Student", "Name", "School", "Signals", "What we see",
                                    "Last sign-in"])
            self.status.setText(f"{len(rows):,} student(s)")
        self.status.setText("Reading sign-ins, Classroom and Chromebooks…")
        Worker(gq.fetch, o, None, users or None, on_done=done,
               on_error=lambda e: self.status.setText(str(e)))

    def send(self):
        from ... import going_quiet as gq
        self._opts()
        if not gq.counselors(self.who.toPlainText()):
            self.info("Add each school's counselors first.")
            return
        Worker(gq.send, lambda _m: None, on_done=lambda n: self.status.setText(
            f"{n} school email(s) sent."), on_error=lambda e: self.info(str(e)))


# ============================================================== stale content ===
class StaleContentPage(Page):
    title = "Stale content"
    subtitle = ("Shared drives nobody has changed in years, classes with no posts this "
                "school year and empty groups – clean them up through Approvals.")

    def build(self):
        from ...tools import stale as st
        o = st.options()
        self.years = QSpinBox()
        self.years.setRange(1, 10)
        self.years.setValue(int(o["drive_years"]))
        self.years.setSuffix(" years")
        self.keep = QLineEdit(o["keep"])
        self.keep.setPlaceholderText("never suggest names containing… (comma separated)")
        self.cd, self.cc, self.cg = (QCheckBox("Shared drives"), QCheckBox("Classes"),
                                     QCheckBox("Empty groups"))
        for cb, k in ((self.cd, "check_drives"), (self.cc, "check_classes"),
                      (self.cg, "check_groups")):
            cb.setChecked(bool(o[k]))
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        self.body.addLayout(self.row(self.cd, QLabel("unchanged for"), self.years, self.cc,
                                     self.cg, button("Scan", "primary", self.scan)))
        self.body.addLayout(self.row(QLabel("Keep"), self.keep))
        self.body.addWidget(self.status)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.body.addLayout(self.row(button("Clean up selected", "danger", self.clean)))
        self.found = []

    def scan(self):
        from ... import google_io
        from ...tools import stale as st
        o = {**st.options(), "drive_years": self.years.value(), "keep": self.keep.text(),
             "check_drives": self.cd.isChecked(), "check_classes": self.cc.isChecked(),
             "check_groups": self.cg.isChecked()}
        st.save_options(o)
        groups = list(self.directory.groups)

        def done(res):
            self.found, probs = res
            fill(self.table, self.found, ["Kind", "Name", "Last change", "Why", "Action",
                                          "id"])
            self.status.setText(f"{len(self.found)} item(s)" +
                                (" · " + " ".join(probs) if probs else ""))
        self.status.setText("Scanning…")
        Worker(st.scan, _csv(), groups, o, google_io.admin_email(), on_done=done,
               on_error=lambda e: self.status.setText(str(e)))

    def clean(self):
        ids = set(self.table.selected_values("id"))
        steps = [(f"{f['Action']}: {f['Name']}", f["args"]) for f in self.found
                 if f["id"] in ids]
        run_or_request(self, _steps(self), steps, "Clean up stale content",
                       "Stale content clean-up", lambda _s: self.scan())


__all__ = ["AccessReviewPage", "AccountTimingPage", "StorageForecastPage", "GoingQuietPage",
           "StaleContentPage"]
