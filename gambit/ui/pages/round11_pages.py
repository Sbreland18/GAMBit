"""Round 11 screens: phishing clean-up, testing mode and staged rollouts, the 2-Step
Verification campaign, approved apps, time-limited accounts, the ownership check, the
account time machine, scheduled questions and the leadership dashboard sheet."""

from __future__ import annotations

import datetime

from PySide6.QtCore import QDate, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QSpinBox, QTabWidget,
)

from ... import team
from ...settings import settings
from ..pickers import OUField, OUMultiField, PersonField
from ..steps import Step, StepList
from ..tools_base import ToolTab
from ..widgets import Page, ResultsTable, Worker, button


def _csv():
    from ...directory import run_gam_csv
    return lambda a: run_gam_csv(a, 3600)


def run_or_request(page, steps_list: StepList, steps: list, title: str, reason: str,
                   done=None):
    """Ask: run now, or send for approval (when there's a team folder)."""
    if not steps:
        page.info("Nothing to change.")
        return
    listing = "\n".join(f"• {lab}" for lab, _a in steps[:25]) + \
        (f"\n…and {len(steps) - 25} more" if len(steps) > 25 else "")
    while True:
        mb = QMessageBox(page)
        mb.setWindowTitle(title)
        mb.setText(f"{title}\n\n{listing}")
        run = mb.addButton("Run now", QMessageBox.AcceptRole)
        send = mb.addButton("Send for approval", QMessageBox.ActionRole) if team.folder() \
            else None
        prev = mb.addButton("Show before → after…", QMessageBox.HelpRole)
        mb.addButton(QMessageBox.Cancel)
        mb.exec()
        clicked = mb.clickedButton() or run
        if clicked is not prev:
            break
        from ..change_preview_dialog import ChangePreviewDialog
        ChangePreviewDialog(page, [a for _l, a in steps], title).exec()
    if send is not None and clicked == send:
        team.new_request([a for _l, a in steps], reason, title=title)
        if hasattr(page.app, "update_approvals_badge"):
            page.app.update_approvals_badge()
        page.info("Sent – see the Approvals page.")
    elif clicked == run:
        steps_list.run([Step(lab, a) for lab, a in steps],
                       lambda s: (page.info(steps_list.summary()), done(s) if done else None))


def _date_edit(iso: str = "", days: int = 0) -> QDateEdit:
    d = QDateEdit()
    d.setCalendarPopup(True)
    try:
        d.setDate(QDate(datetime.date.fromisoformat(iso)))
    except ValueError:
        d.setDate(QDate(datetime.date.today() + datetime.timedelta(days=days)))
    return d


# ======================================================= phishing clean-up ===
class PhishingTab(ToolTab):
    intro = ("Pull a phishing email out of every mailbox: find which mailboxes got it, check "
             "who replied to the sender, then move every copy to the trash (people can still "
             "recover it for 30 days).")

    def build(self):
        box, form = self.page.group("The message")
        self.sender = QLineEdit(placeholderText="sender address or domain, e.g. "
                                                "payroll@paypa1-secure.com")
        self.subject = QLineEdit(placeholderText="subject (or part of it)")
        self.link = QLineEdit(placeholderText="a link from the message (optional)")
        self.days = QSpinBox()
        self.days.setRange(1, 90)
        self.days.setValue(7)
        self.days.setSuffix(" days")
        self.scope = QComboBox()
        self.scope.addItem("Everyone", "all")
        self.scope.addItem("One org unit", "ou")
        self.ou = OUField(self.directory, "/Staff")
        form.addRow("From", self.sender)
        form.addRow("Subject", self.subject)
        form.addRow("Link", self.link)
        form.addRow("Sent in the last", self.days)
        form.addRow("Mailboxes", self.row(self.scope, self.ou, stretch=False))
        self.query = QLabel("", objectName="Muted")
        form.addRow("Gmail search", self.query)
        form.addRow("", self.row(button("Find it", "primary", self.find),
                                 button("Who replied?", slot=self.replied),
                                 button("Move every copy to the trash", "danger", self.trash),
                                 button("Open a help-desk ticket", slot=self.ticket),
                                 self.status))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.found, self.repl = [], []

    def _q(self):
        from ...tools import phishing as ph
        try:
            q = ph.query(self.sender.text(), self.subject.text(), self.link.text(),
                         self.days.value())
        except ValueError as e:
            self.info(str(e))
            return None, None
        self.query.setText(q)
        return q, ph.entity(self.scope.currentData(), self.ou.path())

    def find(self):
        from ...tools import phishing as ph
        q, ent = self._q()
        if not q:
            return

        def got(rows):
            if rows is None:
                return
            self.found = ph.counts(rows)
            self.table.set_rows(["Mailbox", "Copies"], [[f["mailbox"], str(f["count"])]
                                                         for f in self.found])
            self.status.setText(f"{sum(f['count'] for f in self.found)} message(s) in "
                                f"{len(self.found)} mailbox(es)")
        self.read(ph.count_args(ent, q), got, "Searching every mailbox (a few minutes for big "
                                              "districts)…")

    def replied(self):
        from ...tools import phishing as ph
        q, ent = self._q()
        if not q or not self.sender.text().strip():
            self.info("Fill in the sender to check replies.")
            return

        def got(rows):
            if rows is None:
                return
            self.repl = ph.counts(rows)
            self.table.set_rows(["Replied to the sender", "Messages sent"],
                                [[r["mailbox"], str(r["count"])] for r in self.repl])
            self.status.setText(f"{len(self.repl)} person(s) replied – check those accounts "
                                "(Workflows → Hacked account).")
        self.read(ph.replies_args(ent, self.sender.text(), self.days.value()), got)

    def trash(self):
        from ...tools import phishing as ph
        q, ent = self._q()
        if not q:
            return
        if not self.found and not self.confirm("You haven't run Find it yet. Trash every "
                                               "match anyway?"):
            return
        steps = [(f"Trash “{q}” in {self.scope.currentText().lower()}",
                  ph.trash_args(ent, q))]
        run_or_request(self.page, self.steps, steps, "Remove the phishing email",
                       ph.incident_text(q, self.found, self.repl),
                       lambda _s: ph.record(q, self.found, self.repl, "trashed", team.me()))

    def ticket(self):
        from ...integrations import ticketing as tk
        from ...tools import phishing as ph
        q, _ent = self._q()
        if not q:
            return
        if not (tk.configured() and tk.can("create")):
            self.info("Set up your help desk in Settings → Integrations first.")
            return
        Worker(tk.create, "Phishing email removed", ph.incident_text(q, self.found, self.repl),
               on_done=lambda tid: self.status.setText(f"Ticket {tid} opened."),
               on_error=lambda e: self.info(str(e)))


# =================================================== testing mode / rollouts ===
class PlanDialog(QDialog):
    def __init__(self, parent, directory, kind: str):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle("Testing mode" if kind == "testing" else "Staged rollout")
        self.resize(720, 520)
        f = QFormLayout(self)
        self.name = QLineEdit(placeholderText="e.g. Spring state testing" if kind == "testing"
                              else "e.g. Block extensions for students")
        self.src = QComboBox()
        self.src.addItem("Copy the policies from a template org unit", "template")
        self.src.addItem("These policies", "list")
        self.tpl = OUField(directory, "/Testing/Template – set it up in the Admin console")
        self.pols = QPlainTextEdit()
        self.pols.setPlaceholderText("One per line: schema field=value …\n"
                                     "chrome.users.IncognitoMode incognitoModeAvailability="
                                     "UNAVAILABLE")
        self.pols.setMaximumHeight(110)
        f.addRow("Name", self.name)
        f.addRow("Settings", self.src)
        f.addRow("Template org unit", self.tpl)
        f.addRow("Policies", self.pols)
        if kind == "testing":
            self.targets = OUMultiField(directory)
            self.targets.sub.hide()
            self.start = _date_edit(days=1)
            self.end = _date_edit(days=5)
            f.addRow("Org units", self.targets)
            f.addRow("First testing day", self.start)
            f.addRow("Last testing day", self.end)
            f.addRow("", QLabel("The daily task turns testing mode on the morning of the first "
                                "day and puts everything back after the last.",
                                objectName="Muted", wordWrap=True))
        else:
            self.pilot = OUField(directory, "pilot org unit, e.g. /Students/Lincoln/Grade 5")
            self.full = OUMultiField(directory)
            self.full.sub.hide()
            self.days = QSpinBox()
            self.days.setRange(1, 30)
            self.days.setValue(5)
            self.days.setSuffix(" days")
            f.addRow("Pilot org unit", self.pilot)
            f.addRow("Then roll out to", self.full)
            f.addRow("Watch the pilot for", self.days)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def plan(self) -> dict:
        from ...tools import policy_sets as ps
        tpl = self.tpl.path() if self.src.currentData() == "template" else ""
        pols = [] if tpl else ps.parse_policies(self.pols.toPlainText())
        if self.kind == "testing":
            return ps.new_plan("testing", self.name.text().strip() or "Testing mode",
                               self.targets.paths(), tpl, pols,
                               self.start.date().toPython().isoformat(),
                               self.end.date().toPython().isoformat())
        p = ps.new_plan("rollout", self.name.text().strip() or "Rollout",
                        [self.pilot.path()] + [x for x in self.full.paths()
                                               if x != self.pilot.path()],
                        tpl, pols, watch_days=self.days.value())
        p["state"] = "draft"
        return p


class _PlansTab(ToolTab):
    KIND = "testing"
    HEAD = []

    def build(self):
        self.table = ResultsTable()
        self.table.setMinimumHeight(220)
        self.lay.addLayout(self.row(*self.buttons()))
        self.lay.addWidget(self.status)
        self.lay.addWidget(self.table)
        self.detail = QLabel("", wordWrap=True)
        self.lay.addWidget(self.detail)
        self.table.row_clicked.connect(lambda *_: self._show_detail())
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.refresh()

    def plans(self):
        from ...tools import policy_sets as ps
        return [p for p in ps.load() if p["kind"] == self.KIND]

    def _cur(self):
        sel = self.table.selected_dicts()
        if not sel:
            return None
        return next((p for p in self.plans() if p["name"] == sel[0]["Name"]), None)

    def _save_plan(self, plan):
        from ...tools import policy_sets as ps
        all_p = [p for p in ps.load() if p["id"] != plan["id"]] + [plan]
        ps.save(all_p)
        self.refresh()

    def new(self):
        d = PlanDialog(self, self.directory, self.KIND)
        if d.exec():
            p = d.plan()
            if not p["targets"] or not (p["template_ou"] or p["policies"]):
                self.info("Choose the org units and the settings (template org unit or "
                          "policies).")
                return
            self._save_plan(p)

    def delete(self):
        from ...tools import policy_sets as ps
        p = self._cur()
        if p and (not p.get("applied") or self.confirm(
                "It's still applied somewhere – delete it anyway? (Nothing is put back.)")):
            ps.save([x for x in ps.load() if x["id"] != p["id"]])
            self.refresh()

    def _apply(self, p, ous, new_state, then=None):
        """Snapshot (background), then apply through the normal runner."""
        from ...tools import policy_sets as ps
        from ...tools.chrome import direct_policies_args

        if not ps.state_ok(p):     # saved 'before' values can't be trusted – start fresh
            p["before"], p["applied"], p["schemas"] = {}, [], {}

        def work():
            run = _csv()
            tpl = None
            if p.get("template_ou"):
                c, tpl, e = run(direct_policies_args(p["template_ou"]))
                if c != 0:
                    raise RuntimeError(f"Couldn't read the template: {(e or '')[-200:]}")
            out = []
            for ou in ous:
                c, rows, e = run(direct_policies_args(ou))
                if c != 0:
                    raise RuntimeError(f"Couldn't save {ou}'s current policies – nothing "
                                       f"changed: {(e or '')[-200:]}")
                p["before"].setdefault(ou, rows)
                cmds = ps.commands_for(p, ou, tpl)
                p.setdefault("schemas", {})[ou] = ps.schemas_in(cmds)
                out += [(f"{ou}: {c_[2]}", c_) for c_ in cmds]
            return out

        def done(steps):
            if not steps:
                self.info("There are no policies to apply – check the template org unit.")
                return

            def finished(_s):
                p["applied"] = sorted(set(p.get("applied", [])) | set(ous))
                p["state"] = new_state
                ps._seal_state(p)
                p["log"].append(f"{datetime.datetime.now():%Y-%m-%d %H:%M} applied to "
                                f"{', '.join(ous)} by {team.me()}")
                self._save_plan(p)
                if then:
                    then(p)
                self.info(self.steps.summary())
            self.steps.run([Step(lab, a) for lab, a in steps], finished)
        self.status.setText("Saving the current settings first…")
        Worker(work, on_done=lambda s: (self.status.setText(""), done(s)),
               on_error=lambda e: (self.status.setText(""), self.info(str(e))))

    def _revert(self, p, new_state, ous=None):
        from ...tools import policy_sets as ps
        ous = ous or list(p.get("applied", []))
        steps = [(f"{ou}: put back {c[2]}", c) for ou in ous for c in
                 ps.revert_commands(p["before"].get(ou, []), p.get("schemas", {}).get(ou, []),
                                    ou)]
        if not steps:
            self.info("Nothing to put back.")
            return

        def finished(_s):
            p["applied"] = [x for x in p.get("applied", []) if x not in ous]
            p["state"] = new_state
            p["log"].append(f"{datetime.datetime.now():%Y-%m-%d %H:%M} put back "
                            f"{', '.join(ous)} by {team.me()}")
            ps._seal_state(p)
            self._save_plan(p)
            self.info(self.steps.summary())
        from ...gam_runner import display_command
        warn = "" if ps.state_ok(p) else (
            "⚠ The saved settings can't be verified (changed in the team folder, or saved on "
            "a computer this one doesn't trust). Check every command below.\n\n")
        if self.confirm(warn + "Put these settings back?\n\n" + "\n".join(
                f"• {display_command(s[1])}" for s in steps)):
            self.steps.run([Step(lab, a) for lab, a in steps], finished)

    def _show_detail(self):
        p = self._cur()
        self.detail.setText("<br>".join(p.get("log", [])[-8:]) if p else "")


class TestingModeTab(_PlansTab):
    KIND = "testing"
    intro = ("Switch Chromebooks to testing settings for state testing days, and back "
             "afterwards. Set up a template org unit in the Admin console with the testing "
             "settings (testing app, extensions off, no guest mode…), then schedule it here. "
             "Everything set directly on the org units is saved first and put back exactly.")

    def buttons(self):
        return [button("New testing window…", "primary", self.new),
                button("Turn on now", slot=self.on_now),
                button("Put back now", slot=self.off_now),
                button("Delete", "danger", self.delete)]

    def refresh(self):
        self.table.set_rows(["Name", "Org units", "From", "To", "State", "Settings from"],
                            [[p["name"], ", ".join(p["targets"]), p["start"], p["end"],
                              p["state"], p.get("template_ou") or
                              f"{len(p.get('policies', []))} polic(ies)"]
                             for p in self.plans()])

    def on_now(self):
        p = self._cur()
        if p and self.confirm(f"Turn on “{p['name']}” now for {', '.join(p['targets'])}?"):
            self._apply(p, p["targets"], "applied")

    def off_now(self):
        p = self._cur()
        if p:
            self._revert(p, "reverted")


class StagedRolloutsTab(_PlansTab):
    KIND = "rollout"
    intro = ("Try a Chrome policy change on a pilot org unit first. GAMbit watches that group's "
             "help-desk tickets and devices that stop checking in, then you roll it out to "
             "everyone – or roll it back – with one click.")

    def buttons(self):
        return [button("New rollout…", "primary", self.new),
                button("Start the pilot", slot=self.pilot),
                button("Check the pilot now", slot=self.check),
                button("Roll out to everyone", slot=self.promote),
                button("Roll back", "danger", self.rollback),
                button("Delete", slot=self.delete)]

    def refresh(self):
        from ...tools import policy_sets as ps
        self.table.set_rows(["Name", "Pilot", "Then", "State", "Started", "How it's going"],
                            [[p["name"], p["targets"][0] if p["targets"] else "",
                              ", ".join(p["targets"][1:]), p["state"], p.get("start", ""),
                              ps.verdict(p) if p["state"] == "pilot" else ""]
                             for p in self.plans()])

    def _numbers(self, p, then):
        from ... import fleet
        from ...tools import policy_sets as ps

        def work():
            code, rows, _e = _csv()(["print", "cros", "fields", fleet.FIELDS, "listlimit", "1"])
            devs = fleet.devices(rows) if code == 0 else None
            tickets = None
            try:
                from ...integrations import ticketing as tk
                if tk.configured() and tk.can("list"):
                    tickets = tk.list_open({})
            except Exception:  # noqa: BLE001
                pass
            return ps.watch_numbers(p, self.directory.users, devs, tickets)
        Worker(work, on_done=then, on_error=lambda e: self.info(str(e)))

    def pilot(self):
        p = self._cur()
        if not p:
            return
        if p["state"] not in ("draft", "rolled back"):
            self.info("This rollout has already started.")
            return
        if not self.confirm(f"Apply “{p['name']}” to the pilot org unit {p['targets'][0]}?"):
            return
        p["start"] = datetime.date.today().isoformat()

        def after(pl):
            self._numbers(pl, lambda n: (pl.__setitem__("baseline", n), self._save_plan(pl)))
        self._apply(p, p["targets"][:1], "pilot", after)

    def check(self):
        from ...tools import policy_sets as ps
        p = self._cur()
        if not p or p["state"] != "pilot":
            self.info("Select a rollout whose pilot is running.")
            return

        def got(n):
            p["watch"] = [w for w in p.get("watch", []) if w["date"] != n["date"]] + [n]
            self._save_plan(p)
            b = p.get("baseline", {})
            self.info(f"{ps.verdict(p)}\n\nAt the start: {b.get('tickets', '–')} tickets, "
                      f"{b.get('not_checking_in', '–')} devices not checking in.\nNow: "
                      f"{n.get('tickets', '–')} tickets, {n.get('not_checking_in', '–')} of "
                      f"{n.get('devices', '–')} devices not checking in.")
        self._numbers(p, got)

    def promote(self):
        p = self._cur()
        if not p or p["state"] != "pilot":
            self.info("Start (and watch) the pilot first.")
            return
        rest = p["targets"][1:]
        if not rest:
            self.info("This rollout has no other org units.")
            return
        if self.confirm(f"Roll “{p['name']}” out to {', '.join(rest)}?"):
            self._apply(p, rest, "rolled out")

    def rollback(self):
        p = self._cur()
        if p:
            self._revert(p, "rolled back")


class PolicyRolloutsPage(Page):
    title = "Policy rollouts"
    subtitle = ("Testing-season mode and staged rollouts for Chrome policies – everything is "
                "saved first so it can be put back exactly.")

    def build(self):
        self.tabs = QTabWidget()
        self.testing_tab = TestingModeTab(self)
        self.rollouts_tab = StagedRolloutsTab(self)
        self.tabs.addTab(self.testing_tab, "Testing mode")
        self.tabs.addTab(self.rollouts_tab, "Staged rollouts")
        from .round13_tabs import TestReadinessTab
        self.readiness_tab = TestReadinessTab(self)
        self.tabs.addTab(self.readiness_tab, "Device readiness")
        self.body.addWidget(self.tabs, 1)

    def on_show(self):
        self.testing_tab.refresh()
        self.rollouts_tab.refresh()


# ============================================================ 2-Step campaign ===
class TwoStepPage(Page):
    title = "2-Step Verification"
    subtitle = ("Roll out 2-Step Verification to staff: progress by building, reminder emails "
                "with a deadline, escalation to principals, and which buildings are ready for "
                "enforcement.")

    def build(self):
        from ...tools import campaigns as cp
        o = cp.options()
        box, form = self.group("Campaign")
        self.root = OUField(self.directory, "/Staff")
        self.root.set_path(o["root"])
        self.depth = QSpinBox()
        self.depth.setRange(1, 3)
        self.depth.setValue(int(o["depth"]))
        self.deadline = _date_edit(o.get("deadline", ""), 30)
        self.msg = QPlainTextEdit(o["message"])
        self.msg.setMaximumHeight(110)
        self.ready = QSpinBox()
        self.ready.setRange(50, 100)
        self.ready.setValue(int(o["ready_pct"]))
        self.ready.setSuffix(" %")
        self.heads = QPlainTextEdit(o.get("principals", ""))
        self.heads.setPlaceholderText("Building = principal@…  (for escalation after the "
                                      "deadline)")
        self.heads.setMaximumHeight(70)
        form.addRow("Staff are under", self.root)
        form.addRow("Building = org-unit level", self.depth)
        form.addRow("Deadline", self.deadline)
        form.addRow("Reminder ({deadline})", self.msg)
        form.addRow("Ready to enforce at", self.ready)
        form.addRow("Principals", self.heads)
        self.status = QLabel("", objectName="Muted")
        form.addRow("", self.row(button("Load progress", "primary", self.load),
                                 button("Send reminders now", slot=self.remind),
                                 button("Every Monday…", slot=self.schedule),
                                 button("Open enforcement settings", slot=lambda:
                                        QDesktopServices.openUrl(QUrl(cp.CONSOLE))),
                                 self.status))
        self.body.addWidget(box)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.who = ResultsTable()
        self.body.addWidget(self.who, 1)
        self.steps = StepList(self)
        self.steps.setMaximumHeight(130)
        self.body.addWidget(self.steps)
        self.ppl = []

    def _opts(self):
        from ...tools import campaigns as cp
        o = {**cp.options(), "root": self.root.path() or "/Staff", "depth": self.depth.value(),
             "deadline": self.deadline.date().toPython().isoformat(),
             "message": self.msg.toPlainText(), "ready_pct": self.ready.value(),
             "principals": self.heads.toPlainText()}
        cp.save_options(o)
        return o

    def load(self):
        from ...tools import campaigns as cp
        o = self._opts()

        def work():
            c, rows, e = _csv()(cp.USERS_ARGS)
            if c != 0:
                raise RuntimeError((e or "GAM failed").strip()[-200:])
            return cp.people(rows, o)

        def done(ppl):
            self.ppl = ppl
            prog = cp.progress(ppl, o["ready_pct"])
            h = ["Building", "Staff", "Set up", "Not yet", "%", "Status"]
            self.table.set_rows(h, [[str(r[k]) for k in h] for r in prog])
            self.who.set_rows(["Not set up yet", "Name", "Building"],
                              [[p["email"], p["name"], p["building"]] for p in ppl
                               if not p["enrolled"]])
            hist = o.get("history", [])[-6:]
            self.status.setText(f"{prog[-1]['%'] if prog else 0}% of staff set up" +
                                (" · trend: " + " → ".join(f"{x['pct']}%" for x in hist)
                                 if hist else ""))
        self.status.setText("Reading staff accounts…")
        Worker(work, on_done=done, on_error=lambda e: (self.status.setText(""),
                                                       self.info(str(e))))

    def remind(self):
        from ... import google_io
        from ...tools import campaigns as cp
        o = self._opts()
        if not self.ppl:
            self.info("Load progress first.")
            return
        sender = google_io.admin_email()
        if "@" not in sender:
            self.info("Set the Google account that sends email (Settings → Google Sheets and "
                      "email).")
            return
        batches = cp.remind_batches(self.ppl)
        n = sum(len(b) for b in batches)
        if n and self.confirm(f"Email the reminder to {n} staff member(s)?"):
            self.steps.run([Step(f"Reminder to {len(b)} people", cp.reminder_args(b, o, sender))
                            for b in batches], lambda _s: self.info(self.steps.summary()))

    def schedule(self):
        from ... import tasks_health
        from ...tools import campaigns as cp
        self._opts()
        settings.set("campaign2sv/scheduled", True)
        try:
            tasks_health.create(dict(cp.TASK))
            self.info("Reminders go out every Monday at 7:30 AM until the deadline; after it, "
                      "principals get the list of who's left.")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Saved, but the task couldn't be created here:\n{exc}")


# ============================================================ approved apps ===
class ApprovedAppsTab(ToolTab):
    intro = ("Compare the third-party apps people have connected to their Google accounts with "
             "your approved list (e.g. the apps you have data privacy agreements for), and "
             "remove access to the rest.")

    def build(self):
        from ...tools import app_vetting as av
        self.count = QLabel("")
        self.scope = QComboBox()
        self.scope.addItem("Everyone", "all")
        self.scope.addItem("One org unit", "ou")
        self.ou = OUField(self.directory, "/Students")
        self.lay.addLayout(self.row(button("Import approved list…", slot=self.import_list),
                                    self.count, stretch=True))
        self.lay.addLayout(self.row(QLabel("Check"), self.scope, self.ou,
                                    button("Check connected apps", "primary", self.scan),
                                    self.status, stretch=False))
        self.table = ResultsTable()
        self.table.setMinimumHeight(320)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(
            button("Mark approved", slot=lambda: self.mark("approved")),
            button("Mark not approved", slot=lambda: self.mark("denied")),
            button("Remove access for students", "danger", lambda: self.revoke(True)),
            button("Remove access for everyone", "danger", lambda: self.revoke(False))))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.apps = []
        self.count.setText(f"{len(av.load_list())} app(s) on the approved list")

    def import_list(self):
        from ...tools import app_vetting as av
        p, _ = QFileDialog.getOpenFileName(self, "Approved apps list", "",
                                           "CSV or text (*.csv *.txt)")
        if not p:
            return
        with open(p, encoding="utf-8-sig") as fh:
            new = av.parse_list(fh.read())
        merge = self.confirm(f"{len(new)} app(s) in the file. Add them to the current list? "
                             "(No replaces the list.)")
        cur = av.load_list() if merge else []
        av.save_list(cur + new)
        self.count.setText(f"{len(cur) + len(new)} app(s) on the approved list")

    def scan(self):
        from ...tools import app_vetting as av

        def got(rows):
            if rows is None:
                return
            self.apps = av.summarize(rows, av.load_list(), self.directory.users)
            h = ["App", "Status", "People", "Students", "Can see", "Client ID"]
            self.table.set_rows(h, [[str(a[k]) for k in h] for a in self.apps])
            bad = [a for a in self.apps if a["Status"] != "approved"]
            self.status.setText(f"{len(self.apps)} app(s); {len(bad)} not approved, used by "
                                f"{sum(a['Students'] for a in bad)} student(s)")
        self.read(av.tokens_args(self.scope.currentData(), self.ou.path()), got,
                  "Reading app access for every account (a few minutes)…")

    def _sel(self):
        ids = set(self.table.selected_values("Client ID"))
        return [a for a in self.apps if a["Client ID"] in ids]

    def mark(self, status):
        from ...tools import app_vetting as av
        sel = self._sel()
        if not sel:
            return
        cur = av.load_list()
        for a in sel:
            cur = [x for x in cur if x.get("client_id") != a["Client ID"]]
            cur.append({"name": a["App"], "client_id": a["Client ID"], "status": status})
            a["Status"] = status
        av.save_list(cur)
        h = ["App", "Status", "People", "Students", "Can see", "Client ID"]
        self.table.set_rows(h, [[str(a[k]) for k in h] for a in self.apps])
        self.count.setText(f"{len(cur)} app(s) on the list")

    def revoke(self, students_only):
        from ...tools import app_vetting as av
        sel = [a for a in self._sel() if a["Status"] != "approved"]
        if not sel:
            self.info("Select apps that aren't approved.")
            return
        steps = [(f"Remove {a['App']} from {len(a['students' if students_only else 'users'])} "
                  "account(s)", c) for a in sel for c in av.revoke_commands(a, students_only)]
        run_or_request(self.page, self.steps, steps, "Remove app access",
                       "Not on the approved apps list:\n" + "\n".join(
                           f"• {a['App']} ({a['Client ID']})" for a in sel))


# ======================================================= time-limited accounts ===
class TempAccountDialog(QDialog):
    def __init__(self, parent, directory, existing: bool):
        super().__init__(parent)
        from ... import temp_accounts as ta
        o = ta.options()
        self.setWindowTitle("Track an existing account" if existing else
                            "New time-limited account")
        f = QFormLayout(self)
        self.first = QLineEdit()
        self.last = QLineEdit()
        self.email = PersonField(directory, "email") if existing else QLineEdit(
            placeholderText="sub.jsmith@…")
        self.ou = OUField(directory, o["default_ou"])
        self.ou.set_path(o["default_ou"])
        self.kind = QComboBox()
        self.kind.addItems(ta.KINDS)
        self.sponsor = PersonField(directory, "who asked for it (gets the reminder)")
        self.end = _date_edit(days=30)
        if not existing:
            f.addRow("First name", self.first)
            f.addRow("Last name", self.last)
        f.addRow("Email", self.email)
        if not existing:
            f.addRow("Org unit", self.ou)
        f.addRow("Kind", self.kind)
        f.addRow("Sponsor", self.sponsor)
        f.addRow("Ends on", self.end)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.existing = existing

    def value(self) -> dict:
        em = self.email.email() if hasattr(self.email, "email") else self.email.text().strip()
        return {"first": self.first.text().strip(), "last": self.last.text().strip(),
                "email": em.lower(), "ou": self.ou.path(), "kind": self.kind.currentText(),
                "sponsor": self.sponsor.email() if hasattr(self.sponsor, "email") else "",
                "end": self.end.date().toPython().isoformat()}


class TempAccountsTab(ToolTab):
    intro = ("Substitutes, student teachers, contractors and summer-school accounts with an end "
             "date. The account and its sponsor get a reminder a week before; the daily task "
             "suspends it after the end date.")

    def build(self):
        from ... import temp_accounts as ta
        o = ta.options()
        self.show_all = QCheckBox("Show ended accounts too")
        self.show_all.toggled.connect(self.refresh)
        self.expired_ou = OUField(self.directory, "optional – move them here when they end")
        self.expired_ou.set_path(o.get("expired_ou", ""))
        self.lay.addLayout(self.row(button("New account…", "primary", self.new),
                                    button("Track an existing account…", slot=self.track),
                                    button("Extend…", slot=self.extend),
                                    button("End now", "danger", self.end_now),
                                    button("Stop tracking", slot=self.forget)))
        self.lay.addLayout(self.row(QLabel("When they end, move to"), self.expired_ou,
                                    button("Save", slot=self._save_opts), self.show_all,
                                    stretch=False))
        self.table = ResultsTable()
        self.table.setMinimumHeight(320)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.refresh()

    def _save_opts(self):
        from ... import temp_accounts as ta
        ta.save_options({**ta.options(), "expired_ou": self.expired_ou.path()})
        self.info("Saved.")

    def refresh(self, *_):
        from ... import temp_accounts as ta
        items = ta.load()
        if not self.show_all.isChecked():
            items = [i for i in items if i["status"] == "active"]
        today = datetime.date.today().isoformat()
        self.table.set_rows(["Account", "Kind", "Sponsor", "Ends", "Status", "Reminded"],
                            [[i["email"], i["kind"], i.get("sponsor", ""), i["end"],
                              ("ends today" if i["end"] == today else i["status"]),
                              i.get("warned", "")] for i in sorted(items,
                                                                   key=lambda x: x["end"])])

    def _cur(self):
        from ... import temp_accounts as ta
        sel = self.table.selected_values("Account")
        items = ta.load()
        return items, next((i for i in items if sel and i["email"] == sel[0]), None)

    def new(self):
        from ... import temp_accounts as ta
        from .users import random_password
        d = TempAccountDialog(self, self.directory, False)
        if not d.exec():
            return
        v = d.value()
        if "@" not in v["email"] or not v["ou"]:
            self.info("Fill in the email and org unit.")
            return
        pw = random_password()

        def finished(s):
            if all(x.status in ("ok", "dry") for x in s):
                items = ta.load()
                ta.add(items, v["email"], v["kind"], v["sponsor"], v["end"], team.me())
                ta.save(items)
                self.refresh()
                self.info(f"Created {v['email']} (ends {v['end']}).\n\nTemporary password: "
                          f"{pw}\n\nThey'll choose a new one when they sign in.")
            else:
                self.info(self.steps.summary())
        self.steps.run([Step(f"Create {v['email']}",
                             ta.create_args(v["email"], v["first"], v["last"], v["ou"], pw))],
                       finished)

    def track(self):
        from ... import temp_accounts as ta
        d = TempAccountDialog(self, self.directory, True)
        if d.exec():
            v = d.value()
            if "@" not in v["email"]:
                return
            items = ta.load()
            ta.add(items, v["email"], v["kind"], v["sponsor"], v["end"], team.me())
            ta.save(items)
            self.refresh()

    def extend(self):
        from ... import temp_accounts as ta
        items, rec = self._cur()
        if not rec:
            self.info("Select an account.")
            return
        new, ok = QInputDialog.getText(self, "Extend", f"New end date for {rec['email']} "
                                       "(YYYY-MM-DD)", text=rec["end"])
        if not ok:
            return
        try:
            datetime.date.fromisoformat(new.strip())
        except ValueError:
            self.info("Use the format YYYY-MM-DD.")
            return
        was = rec["status"]
        ta.extend(rec, new.strip(), team.me())
        ta.save(items)
        self.refresh()
        if was == "expired" and self.confirm(f"Unsuspend {rec['email']} now?"):
            self.run_steps(self.steps, [(f"Unsuspend {rec['email']}", a)
                                        for a in ta.reactivate_args(rec)])

    def end_now(self):
        from ... import temp_accounts as ta
        items, rec = self._cur()
        if not rec:
            return
        if self.confirm(f"Suspend {rec['email']} now?"):
            def finished(_s):
                rec["status"] = "expired"
                rec["history"].append(f"{datetime.date.today()} ended early by {team.me()}")
                ta.save(items)
                self.refresh()
            self.steps.run([Step(f"Suspend {rec['email']}", a)
                            for a in ta.expire_args(rec, ta.options())], finished)

    def forget(self):
        from ... import temp_accounts as ta
        items, rec = self._cur()
        if rec and self.confirm(f"Stop tracking {rec['email']}? (The account isn't changed.)"):
            ta.save([i for i in items if i is not rec])
            self.refresh()


# ============================================================ ownership check ===
class OwnershipPage(Page):
    title = "Ownership check"
    subtitle = ("Groups with no owner, shared drives with no manager, Classroom classes owned "
                "by someone who left, and suspended accounts still holding Drive files – each "
                "with a one-click hand-off.")

    def build(self):
        box, form = self.group("Hand things to")
        self.backup = PersonField(self.directory, "e.g. it-backup@… or the tech director")
        self.backup.setText(settings.get("ownership/backup", "") or "")
        self.use_sup = QCheckBox("Prefer the supervisor saved when the person was offboarded")
        self.use_sup.setChecked(True)
        form.addRow("Backup owner", self.backup)
        form.addRow("", self.use_sup)
        self.status = QLabel("", objectName="Muted")
        form.addRow("", self.row(button("Check now", "primary", self.scan), self.status))
        self.body.addWidget(box)
        self.summary = ResultsTable()
        self.summary.setMaximumHeight(170)
        self.body.addWidget(self.summary)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.body.addLayout(self.row(button("Hand off selected", "primary", self.fix),
                                     button("Change who gets it…", slot=self.change_to)))
        self.steps = StepList(self)
        self.steps.setMaximumHeight(140)
        self.body.addWidget(self.steps)
        self.items = []

    def scan(self):
        from ... import google_io, offboard
        from ...tools import ownership as ow
        backup = self.backup.email()
        settings.set("ownership/backup", backup)
        admin = google_io.admin_email()
        users = {u["email"].lower(): u for u in self.directory.users}
        recs = offboard.load_all() if self.use_sup.isChecked() else []
        to = ow.supervisor_lookup(self.directory.users, recs, backup)

        def work():
            run = _csv()
            out, notes = [], []
            for label, args, fn in (
                    ("groups", ow.GROUPS_ARGS, lambda r: ow.groups(r, users, backup)),
                    ("shared drives", ow.drives_args(admin) if admin else None,
                     lambda r: ow.shared_drives(r, users, admin, backup)),
                    ("classes", ow.COURSES_ARGS, lambda r: ow.courses(r, users, to)),
                    ("Drive storage", ow.STORAGE_ARGS,
                     lambda r: ow.suspended_storage(r, users, 100, to))):
                if not args:
                    notes.append(f"{label}: set the admin account first")
                    continue
                c, rows, e = run(args)
                if c == 0:
                    out += fn(rows)
                else:
                    notes.append(f"{label}: {(e or '').strip()[-120:]}")
            return out, notes

        def done(res):
            self.items, notes = res
            by = {}
            for i in self.items:
                by[i["Kind"]] = by.get(i["Kind"], 0) + 1
            self.summary.set_rows(["Kind", "Problems"], [[k, str(v)] for k, v in by.items()])
            self._show()
            self.status.setText(f"{len(self.items)} thing(s) to hand off" +
                                (" · " + "; ".join(notes) if notes else ""))
        if not self.directory.users:
            self.info("Load the user list first.")
            return
        self.status.setText("Checking groups, shared drives, classes and storage…")
        Worker(work, on_done=done, on_error=lambda e: (self.status.setText(""),
                                                       self.info(str(e))))

    def _show(self):
        h = ["Kind", "What", "Owner(s) now", "Problem", "Hand to"]
        self.table.set_rows(h, [[str(i[k]) for k in h] for i in self.items])

    def _sel(self):
        keys = {(s["Kind"], s["What"]) for s in self.table.selected_dicts()}
        return [i for i in self.items if (i["Kind"], i["What"]) in keys]

    def change_to(self):
        from ... import google_io
        from ...tools import ownership as ow
        sel = self._sel()
        if not sel:
            return
        who, ok = QInputDialog.getText(self, "Hand to", "Who should get these?")
        if not ok or "@" not in who:
            return
        who = who.strip().lower()
        users = {u["email"].lower(): u for u in self.directory.users}
        admin = google_io.admin_email()
        for i in sel:
            fresh = {"Group": lambda: ow.groups([{"email": i["id"], "owners": ""}], users, who),
                     "Shared drive": lambda: ow.shared_drives([{"id": i["id"],
                                                                 "name": i["What"]}],
                                                               users, admin, who),
                     "Classroom class": lambda: ow.courses([{"id": i["id"], "name": i["What"],
                                                             "ownerEmail": i["Owner(s) now"]}],
                                                           users, lambda _e: who),
                     "Drive files": lambda: [{**i, "Hand to": who, "args": [[
                         "create", "datatransfer", i["id"], "gdrive", who, "privacy_level",
                         "shared,private"]]}]}[i["Kind"]]()
            if fresh:
                i["Hand to"], i["args"] = who, fresh[0]["args"]
        self._show()

    def fix(self):
        sel = [i for i in self._sel() if i["args"]]
        if not sel:
            self.info("Select rows that have someone in “Hand to” (set a backup owner, or use "
                      "Change who gets it…).")
            return
        steps = [(f"{i['Kind']} {i['What']} → {i['Hand to']}", a) for i in sel for a in i["args"]]
        run_or_request(self, self.steps, steps, "Hand off ownership",
                       "Ownership check:\n" + "\n".join(f"• {i['Kind']} {i['What']}: "
                                                         f"{i['Problem']}" for i in sel[:40]))


# ======================================================= account time machine ===
class TimeMachinePage(Page):
    title = "Account time machine"
    subtitle = ("Every night GAMbit saves each account's org unit, status, aliases, licenses and "
                "groups. See what an account looked like on any day, and put it back.")

    def build(self):
        self.who = PersonField(self.directory, "Whose account?")
        self.day = QComboBox()
        self.status = QLabel("", objectName="Muted")
        self.body.addLayout(self.row(self.who, QLabel("on"), self.day,
                                     button("Compare with last night", "primary", self.compare),
                                     button("Day-by-day history", slot=self.history),
                                     stretch=False))
        self.body.addLayout(self.row(button("Save a snapshot now", slot=self.snap),
                                     button("Every night…", slot=self.schedule), self.status))
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.groups_too = QCheckBox("Also put group memberships back")
        self.groups_too.setChecked(True)
        self.body.addLayout(self.row(self.groups_too,
                                     button("Put the account back to that day", "primary",
                                            self.restore)))
        self.steps = StepList(self)
        self.steps.setMaximumHeight(140)
        self.body.addWidget(self.steps)
        self._dates()

    def on_show(self):
        self._dates()

    def _dates(self):
        from ... import timemachine as tm
        keep = self.day.currentText()
        self.day.clear()
        ds = tm.dates()
        self.day.addItems(ds)
        if keep in ds:
            self.day.setCurrentText(keep)
        elif len(ds) > 1:
            self.day.setCurrentIndex(1)
        self.status.setText(f"{len(ds)} night(s) saved" if ds else
                            "No snapshots yet – save one now or turn on Every night.")

    def _pair(self):
        from ... import timemachine as tm
        e, d = self.who.email(), self.day.currentText()
        ds = tm.dates()
        if "@" not in e or not d or not ds:
            self.info("Choose a person and a day.")
            return None
        then, now = tm.account(d, e), tm.account(ds[0], e)
        if not then or not now:
            self.info(f"{e} isn't in the {d if not then else ds[0]} snapshot.")
            return None
        return e, d, ds[0], then, now

    def compare(self):
        from ... import timemachine as tm
        p = self._pair()
        if not p:
            return
        e, d, last, then, now = p
        rows = tm.diff(then, now)
        self.table.set_rows(["What", f"On {d}", f"Now ({last})"],
                            [[r["What"], r["Then"], r["Now"]] for r in rows])
        self.status.setText(f"{len(rows)} difference(s)" if rows else "No differences.")

    def history(self):
        from ... import timemachine as tm
        e = self.who.email()
        if "@" not in e:
            return
        rows = tm.changes_over_time(e)
        self.table.set_rows(["Date", "What", "Before", "After"],
                            [[r["Date"], r["What"], r["Then"], r["Now"]] for r in rows])
        self.status.setText(f"{len(rows)} change(s) over {len(tm.dates())} night(s)")

    def restore(self):
        from ... import timemachine as tm
        p = self._pair()
        if not p:
            return
        e, d, _last, then, now = p
        steps = tm.restore_commands(e, then, now, self.groups_too.isChecked())
        if not steps:
            self.info("Nothing to put back – the account is the same as on that day.")
            return
        run_or_request(self, self.steps, steps, f"Put {e} back to {d}",
                       f"Account time machine: restore {e} to how it was on {d}.")

    def snap(self):
        from ... import timemachine as tm
        self.status.setText("Saving every account (a few minutes for big districts)…")
        Worker(tm.run, lambda _m: None, on_done=lambda n: (self.status.setText(
            f"Saved {n} account(s)."), self._dates()),
            on_error=lambda e: (self.status.setText(""), self.info(str(e))))

    def schedule(self):
        from ... import tasks_health, timemachine as tm
        settings.set("timemachine/scheduled", True)
        try:
            tasks_health.create(dict(tm.TASK))
            self.info("Accounts will be saved every night at 1:30 AM (90 days are kept).")
        except Exception as exc:  # noqa: BLE001
            self.info(f"Saved, but the task couldn't be created here:\n{exc}")


# ========================================================= scheduled questions ===
class QuestionsDialog(QDialog):
    def __init__(self, page, question: str = ""):
        super().__init__(page)
        from ... import saved_questions as sq
        self.page = page
        self.setWindowTitle("Scheduled questions")
        self.resize(820, 480)
        f = QFormLayout(self)
        self.q = QLineEdit(question)
        self.every = QComboBox()
        for k, v in sq.EVERY.items():
            self.every.addItem(v, k)
        self.every.setCurrentIndex(1)
        self.to = QLineEdit(settings.get("google/admin_email", "") or "")
        f.addRow("Question", self.q)
        f.addRow("When", self.every)
        f.addRow("Email the answer to", self.to)
        f.addRow("", page.row(button("Save question", "primary", self.add),
                              button("Delete selected", slot=self.delete),
                              button("Run selected now", slot=self.run_now),
                              button("Turn on the daily task…", slot=self.schedule)))
        self.table = ResultsTable()
        f.addRow(self.table)
        self.last = QLabel("", wordWrap=True)
        f.addRow(self.last)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.refresh()

    def refresh(self):
        from ... import saved_questions as sq
        self.qs = sq.load()
        self.table.set_rows(["Question", "When", "To", "Last run"],
                            [[q["question"], sq.EVERY.get(q["every"], ""), q["to"],
                              q["last_run"].replace("T", " ")] for q in self.qs])

    def add(self):
        from ... import saved_questions as sq
        if not self.q.text().strip():
            return
        sq.save(sq.load() + [sq.new(self.q.text(), self.every.currentData(), self.to.text(),
                                    team.me())])
        self.q.clear()
        self.refresh()

    def _sel(self):
        s = set(self.table.selected_values("Question"))
        return [q for q in self.qs if q["question"] in s]

    def delete(self):
        from ... import saved_questions as sq
        sel = {q["id"] for q in self._sel()}
        sq.save([q for q in self.qs if q["id"] not in sel])
        self.refresh()

    def run_now(self):
        from ... import saved_questions as sq
        sel = self._sel()
        if not sel:
            return
        q = sel[0]

        def done(res):
            sq.save(self.qs)
            self.refresh()
            self.last.setText(res.get("answer", ""))
        Worker(sq.run_one, q, on_done=done, on_error=lambda e: self.page.info(str(e)))

    def schedule(self):
        from ... import saved_questions as sq, tasks_health
        settings.set("questions/scheduled", True)
        try:
            tasks_health.create(dict(sq.TASK))
            self.page.info("Saved questions are checked every morning at 6:30 AM.")
        except Exception as exc:  # noqa: BLE001
            self.page.info(f"Saved, but the task couldn't be created here:\n{exc}")


# ======================================================= leadership dashboard ===
class LeaderSheetDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        from ... import leader_sheet as ls
        self.page = page
        self.setWindowTitle("Leadership dashboard (Google Sheet)")
        self.resize(640, 260)
        f = QFormLayout(self)
        f.addRow(QLabel("A Google Sheet refreshed every night with the scorecard, a 26-week "
                        "trend, per-school numbers, open help-desk tickets and unusual-activity "
                        "counts. Share it with your director and principals (view only).",
                        wordWrap=True))
        self.url = QLineEdit(ls.sheet_url())
        self.url.setPlaceholderText("Sheet link – or create a new one")
        f.addRow("Sheet", self.url)
        self.status = QLabel(f"Last updated {settings.get('leadersheet/last', '') or 'never'}",
                             objectName="Muted")
        f.addRow("", page.row(button("Create a new sheet", slot=self.create),
                              button("Update now", "primary", self.update_now),
                              button("Open", slot=self.open),
                              button("Every night…", slot=self.schedule)))
        f.addRow("", self.status)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _save(self):
        settings.set("leadersheet/url", self.url.text().strip())

    def create(self):
        from ... import leader_sheet as ls
        Worker(ls.create, on_done=lambda link: (self.url.setText(link),
                                                self.status.setText("Created.")),
               on_error=lambda e: self.page.info(str(e)))

    def update_now(self):
        from ... import leader_sheet as ls
        self._save()
        self.status.setText("Updating…")
        Worker(ls.push, lambda _m: None,
               on_done=lambda tabs: self.status.setText(f"Updated: {', '.join(tabs)}"),
               on_error=lambda e: (self.status.setText(""), self.page.info(str(e))))

    def open(self):
        if self.url.text().strip():
            QDesktopServices.openUrl(QUrl(self.url.text().strip()))

    def schedule(self):
        from ... import leader_sheet as ls, tasks_health
        self._save()
        settings.set("leadersheet/scheduled", True)
        try:
            tasks_health.create(dict(ls.TASK))
            self.page.info("The dashboard sheet will refresh every morning at 6:55 AM.")
        except Exception as exc:  # noqa: BLE001
            self.page.info(f"Saved, but the task couldn't be created here:\n{exc}")
