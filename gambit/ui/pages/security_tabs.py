"""Workflows → Hacked account;  Google Drive → Fix sharing."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QSpinBox, QTabWidget

from ...tools import security_ops as sec
from ..pickers import OUField, PersonField
from ..tools_base import ToolTab
from ..widgets import ResultsTable, button


class HackedAccountTab(ToolTab):
    intro = ("Someone's account was hacked (or might be). First look at what changed, then "
             "lock it down in one go. Nothing changes until you click “Lock it down”.")

    def build(self):
        self.who = PersonField(self.directory, "Whose account?")
        self.days = QSpinBox()
        self.days.setRange(1, 30)
        self.days.setValue(7)
        self.days.setSuffix(" days")
        self.lay.addLayout(self.row(QLabel("Account"), self.who, QLabel("Look back"), self.days,
                                    button("1. Look for signs", "primary", self.look),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.tabs = QTabWidget()
        self.t_filters = ResultsTable()
        self.t_filters.hidden_columns = {"Filter ID"}
        self.t_logins = ResultsTable()
        self.t_sent = ResultsTable()
        self.t_other = ResultsTable()
        self.tabs.addTab(self.t_filters, "Gmail filters")
        self.tabs.addTab(self.t_logins, "Sign-ins")
        self.tabs.addTab(self.t_sent, "Mail they sent")
        self.tabs.addTab(self.t_other, "Forwarding, delegates, send-as")
        self.tabs.setMinimumHeight(300)
        self.lay.addWidget(self.tabs, 1)

        box, form = self.page.group("2. Lock it down")
        self.c_deprov = QCheckBox("Remove app passwords, backup codes and app access; turn off "
                                  "POP and IMAP")
        self.c_fwd = QCheckBox("Turn off forwarding")
        self.c_filters = QCheckBox("Delete the Gmail filters selected above (risky ones are "
                                   "selected for you)")
        self.c_deleg = QCheckBox("Remove everyone's access to the mailbox (delegates)")
        self.c_2sv = QCheckBox("Turn off 2-step verification too (if the attacker enrolled "
                               "their own phone)")
        self.c_susp = QCheckBox("Suspend the account until it's sorted out")
        for cb in (self.c_deprov, self.c_fwd, self.c_filters, self.c_deleg):
            cb.setChecked(True)
        form.addRow(QLabel("The password is always reset and every session signed out."))
        for cb in (self.c_deprov, self.c_fwd, self.c_filters, self.c_deleg, self.c_2sv,
                   self.c_susp):
            form.addRow(cb)
        self.alert = QCheckBox("Send a security alert to the tech team (Settings → alerts)")
        self.alert.setChecked(True)
        form.addRow(self.alert)
        form.addRow(self.row(button("Lock it down", "danger", self.lock)))
        self.lay.addWidget(box)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.delegates: list[str] = []
        self.forward = ""

    def look(self):
        email = self.who.email()
        if "@" not in email:
            self.info("Pick the account first.")
            return
        a = sec.look_args(email, self.days.value())
        keys = ["filters", "delegates", "forward", "sendas", "logins", "sent"]

        def done(res):
            got = dict(zip(keys, res))
            f = sec.filters(got["filters"])
            heads = ["When", "Does", "Looks risky", "Filter ID"]
            self.t_filters.set_rows(heads, [[x[h] for h in heads] for x in f])
            self.t_filters.table.clearSelection()
            for i, x in enumerate(f):
                if x["Looks risky"]:
                    self.t_filters.select_row(i, add=True)
            from ...tools.investigate import tidy
            h, rows = tidy(got["logins"])
            self.t_logins.set_rows(h, rows)
            s = got["sent"]
            sh = list(s[0].keys()) if s else ["(nothing sent)"]
            self.t_sent.set_rows(sh, [[r.get(k, "") for k in sh] for r in s])
            self.delegates = sec.delegates(got["delegates"])
            self.forward = sec.forwarding_on(got["forward"])
            sendas = [r.get("sendAsEmail", "") for r in got["sendas"]
                      if r.get("sendAsEmail", "").lower() != email.lower()]
            other = [["Forwarding", self.forward or "off"]] + \
                [["Delegate", d] for d in self.delegates] + [["Send as", x] for x in sendas]
            self.t_other.set_rows(["What", "Value"], other)
            risky = sum(1 for x in f if x["Looks risky"])
            fails = sum(1 for r in rows if any("fail" in str(c).lower() or "suspicious" in
                                                 str(c).lower() for c in r))
            signs = []
            if risky:
                signs.append(f"{risky} risky filter(s)")
            if self.forward:
                signs.append(f"forwarding to {self.forward}")
            if self.delegates:
                signs.append(f"{len(self.delegates)} delegate(s)")
            if fails:
                signs.append(f"{fails} failed/suspicious sign-in(s)")
            signs.append(f"{len(s)} message(s) sent")
            self.status.setText("Found: " + ", ".join(signs))
        self.read_many([a[k] for k in keys], done, "Looking at the account…")

    def lock(self):
        email = self.who.email()
        if "@" not in email:
            self.info("Pick the account first.")
            return
        from .users import random_password
        pw = random_password(16)
        ids = [r["Filter ID"] for r in self.t_filters.selected_dicts() if r.get("Filter ID")] \
            if self.c_filters.isChecked() else []
        steps = sec.lockdown_steps(email, pw, deprovision=self.c_deprov.isChecked(),
                                   forward_off=self.c_fwd.isChecked(), filter_ids=ids,
                                   delegate_list=self.delegates if self.c_deleg.isChecked()
                                   else [], suspend=self.c_susp.isChecked(),
                                   turnoff2sv=self.c_2sv.isChecked())
        if not self.confirm(f"Lock down {email}?\n\n" + "\n".join(f"• {s[0]}" for s in steps)):
            return

        def done(_s):
            from ...gam_runner import dry_run_on
            if dry_run_on():
                return
            self.page.info(f"New temporary password for {email}:\n\n{pw}\n\nGive it to them "
                           "in person or by phone – not by email. They'll choose their own "
                           "when they sign in.")
            if self.alert.isChecked():
                from ... import alerts
                from ..widgets import Worker
                Worker(alerts.notify, f"{email} was locked down after a suspected compromise "
                                      f"({len(steps)} steps).", "GAMbit security alert")
        self.run_steps(self.steps, steps, done)


class FixSharingTab(ToolTab):
    intro = ("Find files shared with “anyone with the link” or with people outside the "
             "district, then fix them in bulk: switch link sharing to district-only, or remove "
             "the outside access. Checking a whole org unit can take a long time.")

    def build(self):
        self.who = PersonField(self.directory, "One person…")
        self.ou = OUField(self.directory, "…or everyone under an org unit")
        self.lay.addLayout(self.row(QLabel("Files owned by"), self.who, QLabel("or"), self.ou,
                                    button("Find risky sharing", "primary", self.scan),
                                    stretch=False))
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.hidden_columns = {"File ID", "Permission ID"}
        self.table.setMinimumHeight(360)
        self.lay.addWidget(self.table, 1)
        self.mode = QComboBox()
        self.mode.addItem("“Anyone with the link” → district only; remove outside people", "domain")
        self.mode.addItem("Remove the sharing completely", "remove")
        self.lay.addLayout(self.row(QLabel("For the selected rows:"), self.mode,
                                    button("Select all", slot=lambda: self.table.table.selectAll()),
                                    button("Fix selected", "primary", self.fix)))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def _domain(self) -> str:
        if self.directory.domain:
            return self.directory.domain
        from collections import Counter
        doms = Counter(u["email"].split("@")[-1] for u in self.directory.users
                       if "@" in u.get("email", ""))
        return doms.most_common(1)[0][0] if doms else ""

    def scan(self):
        who, ou = self.who.email(), self.ou.path()
        if "@" not in who and not ou:
            self.info("Pick a person or an org unit.")
            return
        dom = self._domain()
        if not dom:
            self.info("GAMbit doesn't know your domain yet – test the connection on Home first.")
            return

        def done(rows):
            if rows is None:
                return
            sh = sec.shares(rows, dom)
            heads = ["Owner", "File", "Shared with", "Role", "Link", "Type", "File ID",
                     "Permission ID"]
            self.table.set_rows(heads, [[r[h] for h in heads] for r in sh])
            anyone = sum(1 for r in sh if r["Type"] == "anyone")
            self.status.setText(f"{len(sh):,} risky share(s): {anyone:,} public link(s), "
                                f"{len(sh) - anyone:,} outside people or groups")
        self.read(sec.scan_args(who, ou, dom), done, "Checking sharing (this can take a while)…")

    def fix(self):
        rows = self.table.selected_dicts()
        if not rows:
            self.info("Select the rows to fix (or click Select all).")
            return
        mode = self.mode.currentData()
        steps = [s for r in rows for s in sec.fix_steps(r, self._domain(), mode)]
        if steps and self.confirm(f"Fix sharing on {len(rows)} row(s)? ({len(steps)} change(s))"):
            self.run_steps(self.steps, steps, lambda _s: self.scan())
