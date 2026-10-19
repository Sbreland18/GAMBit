"""Gmail tools: out-of-office, signatures, forwarding, delegates, message cleanup, send."""

from __future__ import annotations

import os

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDateEdit, QFileDialog, QGroupBox,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QRadioButton,
    QScrollArea, QSpinBox, QSplitter, QTabWidget, QTextBrowser, QTextEdit,
    QVBoxLayout, QWidget,
)

from ... import team
from ...settings import settings
from ..pickers import PeoplePicker, PersonField, TargetPicker
from ..widgets import Page, ResultsTable, button

from ...signature import SIGNATURE_TEMPLATE, TAGS, tag_replacements  # noqa: F401

PREVIEW_HEADERS = "date,from,to,subject,message-id"


def _scroll(widget: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QScrollArea.NoFrame)
    widget.setObjectName("Page")
    s.setWidget(widget)
    return s


def _date_row(label: str):
    cb = QCheckBox(label)
    de = QDateEdit(QDate.currentDate())
    de.setCalendarPopup(True)
    de.setDisplayFormat("ddd, MMM d, yyyy")
    de.setEnabled(False)
    cb.toggled.connect(de.setEnabled)
    return cb, de


class EmailPage(Page):
    title = "Email"
    subtitle = ("Out-of-office replies, signatures, forwarding, mailbox delegation, "
                "finding and removing messages, and sending email.")

    def build(self):
        self.warn = QLabel("These tools work inside users' mailboxes, so GAM needs "
                           "user-data access (Setup wizard → <b>Allow GAM access</b>).",
                           objectName="Banner")
        self.warn.setWordWrap(True)
        self.body.addWidget(self.warn)
        self.tabs = QTabWidget()
        self.tabs.addTab(_scroll(self._vacation_tab()), "Out of office")
        self.tabs.addTab(_scroll(self._signature_tab()), "Signatures")
        self.tabs.addTab(_scroll(self._forward_tab()), "Forwarding")
        self.tabs.addTab(_scroll(self._delegate_tab()), "Mailbox access")
        self.tabs.addTab(self._cleanup_tab(), "Find && remove messages")
        self.tabs.addTab(self._settings_tab(), "Filters, IMAP && POP")
        self.tabs.addTab(_scroll(self._send_tab()), "Send email")
        from .people_tabs import SendAsTab
        self.sendas_tab = SendAsTab(self)
        self.tabs.addTab(self.sendas_tab, "Send as")
        from .more_tabs import ArchiveTab
        self.archive_tab = ArchiveTab(self)
        self.tabs.addTab(self.archive_tab, "Archive to a group")
        from .recovery_tabs import RestoreMailTab
        self.restore_tab = RestoreMailTab(self)
        self.tabs.addTab(self.restore_tab, "Restore deleted mail")
        from .small_tabs import LabelsTab, SmimeTab
        self.labels_tab, self.smime_tab = LabelsTab(self), SmimeTab(self)
        self.tabs.addTab(self.labels_tab, "Labels")
        self.tabs.addTab(self.smime_tab, "S/MIME")
        from .round14_tabs import GmailLanguageTab
        self.lang_tab = GmailLanguageTab(self)
        self.tabs.addTab(self.lang_tab, "Gmail language")
        self.body.addWidget(self.tabs, 1)

    def on_show(self):
        self.warn.setVisible(not settings.get("gam/delegation_ok", False))

    def _need_targets(self, picker: TargetPicker):
        ents = picker.entities()
        if not ents:
            self.info("Choose who this applies to first.")
        return ents

    # ================================================== out of office ===
    def _vacation_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box = QGroupBox("Who")
        QVBoxLayout(box).addWidget(t := TargetPicker(self.directory))
        self.v_who = t
        lay.addWidget(box)

        box, form = self.group("Auto-reply")
        self.v_subject = QLineEdit(placeholderText="Out of office")
        self.v_msg = QTextEdit()
        self.v_msg.setPlaceholderText(
            "Thanks for your email. I'm out of the office until Monday and will reply "
            "when I return.\n\nTags you can use: {FirstName} {FullName} {Email} {Title}")
        self.v_msg.setFixedHeight(120)
        self.v_html = QCheckBox("Message is HTML")
        self.v_start_on, self.v_start = _date_row("Start on")
        self.v_end_on, self.v_end = _date_row("End on")
        self.v_end.setDate(QDate.currentDate().addDays(7))
        self.v_domain = QCheckBox("Only reply to people in our organization")
        self.v_contacts = QCheckBox("Only reply to people in their contacts")
        form.addRow("Subject", self.v_subject)
        form.addRow("Message", self.v_msg)
        form.addRow("", self.v_html)
        form.addRow("", self.row(self.v_start_on, self.v_start, self.v_end_on, self.v_end))
        form.addRow("", self.v_domain)
        form.addRow("", self.v_contacts)
        form.addRow("", self.row(button("Turn on auto-reply", "primary", self.vacation_on),
                                 button("Turn off", slot=self.vacation_off),
                                 button("Show current settings", slot=self.vacation_show)))
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def vacation_on(self):
        ents = self._need_targets(self.v_who)
        msg = self.v_msg.toPlainText().strip()
        if not ents:
            return
        if not msg:
            self.info("Type the auto-reply message.")
            return
        if self.v_start_on.isChecked() and self.v_end_on.isChecked() and \
                self.v_end.date() < self.v_start.date():
            self.info("The end date is before the start date.")
            return
        opts = ["vacation", "on", "subject", self.v_subject.text().strip() or "Out of office",
                "message", msg, *tag_replacements(msg),
                "html", "true" if self.v_html.isChecked() else "false",
                "domainonly", "true" if self.v_domain.isChecked() else "false",
                "contactsonly", "true" if self.v_contacts.isChecked() else "false",
                "start", self.v_start.date().toString("yyyy-MM-dd")
                if self.v_start_on.isChecked() else "Started",
                "end", self.v_end.date().toString("yyyy-MM-dd")
                if self.v_end_on.isChecked() else "NotSpecified"]
        if self.v_who.is_everyone() and not self.confirm(
                "Turn on this auto-reply for EVERYONE in the domain?"):
            return
        self.run_many([e + opts for e in ents], lambda _o: None, quiet=False)

    def vacation_off(self):
        if ents := self._need_targets(self.v_who):
            if self.confirm(f"Turn off auto-reply for {self.v_who.describe()}?"):
                self.run_many([e + ["vacation", "off"] for e in ents], lambda _o: None,
                              quiet=False)

    def vacation_show(self):
        if ents := self._need_targets(self.v_who):
            self.run_many([e + ["show", "vacation"] for e in ents], lambda _o: None,
                          quiet=False)

    # ===================================================== signatures ===
    def _signature_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box = QGroupBox("Who")
        QVBoxLayout(box).addWidget(t := TargetPicker(self.directory))
        self.s_who = t
        lay.addWidget(box)

        box = QGroupBox("Signature")
        bl = QVBoxLayout(box)
        tags = QLabel("Tags are filled in for each person: " +
                      "  ".join("{" + t + "}" for t in TAGS) +
                      "<br>Wrap optional parts in {RT}…{/RT} – they're left out when "
                      "the person has no value (e.g. no phone).", objectName="Muted")
        tags.setWordWrap(True)
        tags.setTextFormat(Qt.RichText)
        bl.addWidget(tags)
        split = QSplitter(Qt.Horizontal)
        self.s_html = QTextEdit()
        self.s_html.setAcceptRichText(False)
        self.s_html.setPlainText(team.setting("email/signature", "") or SIGNATURE_TEMPLATE)
        self.s_html.setStyleSheet("font-family: Consolas, 'Cascadia Mono', monospace;")
        self.s_preview = QTextBrowser()
        self.s_html.textChanged.connect(self._sig_preview)
        split.addWidget(self.s_html)
        split.addWidget(self.s_preview)
        split.setFixedHeight(200)
        bl.addWidget(split)
        self.s_is_html = QCheckBox("Signature is HTML (uncheck for plain text)")
        self.s_is_html.setChecked(True)
        self.s_is_html.toggled.connect(self._sig_preview)
        bl.addWidget(self.s_is_html)
        bl.addLayout(self.row(
            button("Set signature", "primary", self.signature_set),
            button("Show current signature", slot=self.signature_show),
            button("Open template…", slot=self._sig_open),
            button("Save template…", slot=self._sig_save),
            button("Reset to example", slot=lambda: self.s_html.setPlainText(SIGNATURE_TEMPLATE))))
        self.s_as = PersonField(self.directory, "Preview as… (pick a real person)")
        self.s_as.textChanged.connect(self._sig_preview)
        self.s_weekly = QLabel("", objectName="Muted")
        bl.addLayout(self.row(QLabel("Preview as"), self.s_as,
                              button("Re-apply every week…", slot=self.signature_weekly),
                              self.s_weekly))
        lay.addWidget(box)
        lay.addStretch(1)
        self._sig_preview()
        self._weekly_label()
        return w

    def _sig_preview(self, *_):
        from ...signature import render
        text = self.s_html.toPlainText()
        who = "sample person"
        person = {"name": "Jane Doe", "first": "Jane", "last": "Doe",
                  "email": "jdoe@yourschool.org", "title": "4th Grade Teacher",
                  "department": "Elementary", "phone": "(555) 555-0100"}
        email = self.s_as.email() if hasattr(self, "s_as") else ""
        u = next((x for x in self.directory.users if x.get("email", "").lower() ==
                  (email or "").lower()), None) if email else None
        if u:
            who = u.get("name") or email
            parts = (u.get("name") or "").split(" ", 1)
            person = {"name": u.get("name", ""), "first": parts[0],
                      "last": parts[1] if len(parts) > 1 else "", "email": u["email"],
                      "title": u.get("title", ""), "department": u.get("department", ""),
                      "phone": u.get("phone", "")}
        text = render(text, person).replace("{RTL}", "").replace("{/RTL}", "")
        if self.s_is_html.isChecked() if hasattr(self, "s_is_html") else True:
            self.s_preview.setHtml(f"<p style='color:#57606a'>Preview ({who})</p>" + text)
        else:
            self.s_preview.setPlainText(text)
        team.set_setting("email/signature", self.s_html.toPlainText())

    def _sig_open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open signature template", "",
                                              "HTML or text (*.html *.htm *.txt)")
        if path:
            with open(path, encoding="utf-8") as fh:
                self.s_html.setPlainText(fh.read())

    def _sig_save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save signature template",
                                              "signature.html", "HTML (*.html)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.s_html.toPlainText())

    def signature_set(self):
        ents = self._need_targets(self.s_who)
        sig = self.s_html.toPlainText().strip()
        if not ents or not sig:
            return
        if not self.confirm(f"Set this signature for {self.s_who.describe()}?\n\n"
                            "It replaces their current signature."):
            return
        opts = ["signature", sig, *tag_replacements(sig),
                "html", "true" if self.s_is_html.isChecked() else "false"]
        self.run_many([e + opts for e in ents], lambda _o: None, quiet=False)

    def signature_weekly(self):
        from ... import signature, tasks_health
        ents = self._need_targets(self.s_who)
        if not ents:
            return
        if not self.confirm(f"Every Monday at 5:20 AM, set the current template for "
                            f"{self.s_who.describe()}?\n\nNew staff pick it up automatically, "
                            "and changes to the template roll out the next week. (Uses Windows "
                            "Task Scheduler on this PC.)"):
            return
        signature.save_rollout(ents, self.s_is_html.isChecked(), self.s_who.describe())
        try:
            tasks_health.create(dict(signature.ROLLOUT_TASK))
        except Exception as exc:  # noqa: BLE001
            self.info(f"Saved, but the weekly task couldn't be created here:\n{exc}\n\n"
                      "Set it up from Automation → Background tasks on a Windows PC.")
        self._weekly_label()

    def _weekly_label(self):
        from ... import signature
        r = signature.rollout()
        self.s_weekly.setText(f"Weekly: {r.get('who', '')}" if r.get("targets") else "")

    def signature_show(self):
        if ents := self._need_targets(self.s_who):
            self.run_many([e + ["show", "signature"] for e in ents], lambda _o: None,
                          quiet=False)

    # ===================================================== forwarding ===
    def _forward_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box, form = self.group("Forward a mailbox")
        self.f_user = PersonField(self.directory, "Whose email should be forwarded?")
        self.f_to = PersonField(self.directory, "Forward to (name or email)…")
        self.f_action = QComboBox()
        for label, val in (("Keep a copy in their inbox", "keep"),
                           ("Keep a copy, marked as read", "markread"),
                           ("Archive their copy", "archive"),
                           ("Move their copy to trash", "trash")):
            self.f_action.addItem(label, val)
        form.addRow("Mailbox", self.f_user)
        form.addRow("Forward to", self.f_to)
        form.addRow("Their copy", self.f_action)
        form.addRow("", self.row(button("Turn on forwarding", "primary", self.forward_on),
                                 button("Turn off forwarding", slot=self.forward_off),
                                 button("Show current", slot=self.forward_show)))
        note = QLabel("Forwarding to an address outside your organization: Google sends that "
                      "address a confirmation email, and forwarding starts once they "
                      "accept it.", objectName="Muted")
        note.setWordWrap(True)
        form.addRow("", note)
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def _fwd_user(self):
        u = self.f_user.email()
        if "@" not in u:
            self.info("Choose whose mailbox to forward.")
            return None
        return u

    def forward_on(self):
        u, to = self._fwd_user(), self.f_to.email()
        if not u:
            return
        if "@" not in to:
            self.info("Choose where to forward the email.")
            return
        act = self.f_action.currentData()
        if act == "trash" and not self.confirm(
                f"{u}'s copies will go to trash after forwarding. Continue?"):
            return
        self.run_many([["user", u, "add", "forwardingaddress", to],
                       ["user", u, "forward", "on", act, to]], lambda _o: None, quiet=False)

    def forward_off(self):
        if u := self._fwd_user():
            self.run(["user", u, "forward", "off"])

    def forward_show(self):
        if u := self._fwd_user():
            self.run_many([["user", u, "show", "forward"],
                           ["user", u, "show", "forwardingaddresses"]], lambda _o: None,
                          quiet=False)

    # ====================================================== delegates ===
    def _delegate_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box, form = self.group("Let someone read and send from a mailbox")
        self.d_user = PersonField(self.directory, "Whose mailbox? (e.g. a shared office account)")
        form.addRow("Mailbox", self.row(self.d_user, button("Show who has access", slot=self.delegates_show),
                                        stretch=False))
        self.d_people = PeoplePicker(self.directory, include_groups=False)
        form.addRow("People", self.d_people)
        form.addRow("", self.row(button("Give access", "primary", self.delegate_add),
                                 button("Remove access", "danger", self.delegate_remove)))
        note = QLabel("Delegates can read, send and delete messages in that mailbox. "
                      "It can take up to an hour to show up for them.", objectName="Muted")
        note.setWordWrap(True)
        form.addRow("", note)
        lay.addWidget(box)
        self.d_table = ResultsTable()
        self.d_table.setMinimumHeight(180)
        lay.addWidget(self.d_table)
        return w

    def _d_user(self):
        u = self.d_user.email()
        if "@" not in u:
            self.info("Choose the mailbox first.")
            return None
        return u

    def delegates_show(self):
        if u := self._d_user():
            self.run(["user", u, "print", "delegates", "shownames"],
                     lambda c, out, _e: self.d_table.load_csv(out) if c == 0 else None,
                     quiet=True)

    def delegate_add(self):
        u, people = self._d_user(), self.d_people.emails()
        if u and people:
            self.run(["user", u, "add", "delegate", ",".join(people)],
                     lambda c, *_: (self.d_people.clear() if c == 0 else None,
                                    self.delegates_show()))
        elif u:
            self.info("Add the people who should get access.")

    def delegate_remove(self):
        u = self._d_user()
        if not u:
            return
        people = self.d_people.emails() or self.d_table.selected_values("delegateAddress")
        if not people:
            self.info("Pick people in the list above, or select them in the table.")
            return
        if self.confirm(f"Remove {len(people)} delegate(s) from {u}?"):
            self.run(["user", u, "delete", "delegate", ",".join(people)],
                     lambda *_: self.delegates_show())

    # ===================================================== cleanup ======
    def _cleanup_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        top = QHBoxLayout()

        box = QGroupBox("1. Whose mailboxes")
        QVBoxLayout(box).addWidget(t := TargetPicker(self.directory))
        self.c_who = t
        top.addWidget(box, 1)

        box, form = self.group("2. Which messages")
        self.c_subject = QLineEdit(placeholderText="Words in the subject")
        self.c_from = QLineEdit(placeholderText="sender@example.com")
        self.c_msgid = QLineEdit(placeholderText="<abc123@mail.example.com> – most precise")
        self.c_query = QLineEdit(placeholderText="Any Gmail search, e.g. has:attachment filename:zip")
        self.c_days = QSpinBox()
        self.c_days.setRange(0, 3650)
        self.c_days.setValue(7)
        self.c_days.setSpecialValueText("Any time")
        self.c_days.setSuffix(" days")
        form.addRow("Subject", self.c_subject)
        form.addRow("From", self.c_from)
        form.addRow("Message-ID", self.c_msgid)
        form.addRow("Gmail search", self.c_query)
        form.addRow("Received within", self.c_days)
        top.addWidget(box, 1)
        lay.addLayout(top)

        row = QHBoxLayout()
        row.addWidget(QLabel("<b>3.</b>"))
        row.addWidget(button("Preview matches", "primary", self.cleanup_preview))
        row.addWidget(button("Count only", slot=self.cleanup_count))
        row.addWidget(button("Use selected message's ID", slot=self._use_msgid))
        row.addStretch(1)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.c_trash = QRadioButton("Move to trash (recoverable 30 days)")
        self.c_delete = QRadioButton("Delete permanently")
        self.c_trash.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.c_trash)
        grp.addButton(self.c_delete)
        row.addWidget(self.c_trash)
        row.addWidget(self.c_delete)
        row.addWidget(QLabel("Max per mailbox"))
        self.c_max = QSpinBox()
        self.c_max.setRange(0, 100000)
        self.c_max.setValue(10)
        self.c_max.setSpecialValueText("No limit")
        row.addWidget(self.c_max)
        row.addWidget(button("Remove matching messages…", "danger", self.cleanup_remove))
        row.addStretch(1)
        lay.addLayout(row)
        self.c_results = ResultsTable()
        self.c_results.hidden_columns = {"threadid", "id"}
        lay.addWidget(self.c_results, 1)
        return w

    def _query(self) -> str:
        parts = []
        if s := self.c_subject.text().strip():
            parts.append(f'subject:"{s}"' if " " in s else f"subject:{s}")
        if f := self.c_from.text().strip():
            parts.append(f"from:{f}")
        if m := self.c_msgid.text().strip():
            parts.append(f"rfc822msgid:{m.strip('<>')}")
        if q := self.c_query.text().strip():
            parts.append(q)
        if parts and self.c_days.value():
            parts.append(f"newer_than:{self.c_days.value()}d")
        return " ".join(parts)

    def _cleanup_ready(self):
        ents = self._need_targets(self.c_who)
        q = self._query()
        if ents and not q:
            self.info("Fill in at least one of Subject, From, Message-ID or Gmail search.")
            return None, None
        return ents, q

    def cleanup_preview(self):
        ents, q = self._cleanup_ready()
        if ents:
            self.run_many([e + ["print", "messages", "query", q, "headers", PREVIEW_HEADERS,
                                "max_to_print", "50"] for e in ents],
                          self.c_results.load_csv_many)

    def cleanup_count(self):
        ents, q = self._cleanup_ready()
        if ents:
            self.run_many([e + ["print", "messages", "query", q, "countsonly"] for e in ents],
                          self.c_results.load_csv_many)

    def _use_msgid(self):
        col = next((h for h in self.c_results._headers if h.lower() == "message-id"), None)
        ids = self.c_results.selected_values(col) if col else []
        if not ids:
            self.info("Preview matches, then click a message in the results.")
            return
        self.c_msgid.setText(ids[0])
        self.c_subject.clear()
        self.c_from.clear()
        self.c_query.clear()

    def cleanup_remove(self):
        ents, q = self._cleanup_ready()
        if not ents:
            return
        permanent = self.c_delete.isChecked()
        verb = "PERMANENTLY DELETE" if permanent else "move to trash"
        limit = self.c_max.value()
        msg = (f"This will {verb} messages matching:\n\n    {q}\n\nin the mailboxes of "
               f"{self.c_who.describe()}"
               + (f", up to {limit} per mailbox." if limit else ", with no limit per mailbox.")
               + "\n\nTip: click Preview first to check what matches.")
        if permanent or self.c_who.is_everyone():
            text, ok = QInputDialog.getText(self, "Please confirm",
                                            msg + "\n\nType REMOVE to continue:")
            if not ok or text.strip().upper() != "REMOVE":
                return
        elif not self.confirm(msg):
            return
        action, cap = (("delete", "max_to_delete") if permanent else ("trash", "max_to_trash"))
        self.run_many([e + [action, "messages", "query", q, "doit", cap, str(limit)]
                       for e in ents], lambda _o: None, quiet=False)

    # ================================================= mail settings ===
    def _settings_tab(self):
        w = QWidget(objectName="Page")
        lay = QVBoxLayout(w)
        top = QHBoxLayout()

        box = QGroupBox("IMAP and POP access")
        bl = QVBoxLayout(box)
        self.p_who = TargetPicker(self.directory)
        bl.addWidget(self.p_who)
        bl.addLayout(self.row(button("Check IMAP", slot=lambda: self._mail_setting("imap", None)),
                              button("Turn IMAP on", slot=lambda: self._mail_setting("imap", True)),
                              button("Turn IMAP off", slot=lambda: self._mail_setting("imap", False))))
        bl.addLayout(self.row(button("Check POP", slot=lambda: self._mail_setting("pop", None)),
                              button("Disable POP", "danger",
                                     lambda: self._mail_setting("pop", False))))
        top.addWidget(box, 3)

        box, form = self.group("Gmail filters")
        self.fl_user = PersonField(self.directory, "Whose filters?")
        form.addRow("Mailbox", self.fl_user)
        form.addRow("", self.row(button("Show filters", "primary", self.filters_show),
                                 button("Delete selected filter", "danger",
                                        self.filter_delete)))
        hint = QLabel("Look for filters that forward, delete or skip the inbox – a common "
                      "sign of a compromised account.", objectName="Muted")
        hint.setWordWrap(True)
        form.addRow("", hint)
        top.addWidget(box, 2)
        lay.addLayout(top)
        self.ms_results = ResultsTable()
        lay.addWidget(self.ms_results, 1)
        return w

    def _mail_setting(self, kind: str, on):
        ents = self._need_targets(self.p_who)
        if not ents:
            return
        if on is None:
            self.run_many([e + ["print", kind] for e in ents], self.ms_results.load_csv_many)
            return
        label = f"{'Turn on' if on else 'Turn off'} {kind.upper()}"
        if self.confirm(f"{label} for {self.p_who.describe()}?"):
            self.run_many([e + [kind, "on" if on else "off"] for e in ents],
                          lambda _o: self._mail_setting(kind, None), quiet=False)

    def filters_show(self):
        u = self.fl_user.email()
        if "@" not in u:
            self.info("Choose whose filters to show.")
            return
        self.run(["user", u, "print", "filters"],
                 lambda c, out, _e: self.ms_results.load_csv(out) if c == 0 else None,
                 quiet=True)

    def filter_delete(self):
        u = self.fl_user.email()
        ids = self.ms_results.selected_values("id")
        if "@" not in u or not ids:
            self.info("Show a user's filters, then select the filter(s) to delete.")
            return
        if self.confirm(f"Delete {len(ids)} filter(s) from {u}?"):
            self.run(["user", u, "delete", "filters", ",".join(ids)],
                     lambda *_: self.filters_show())

    # ========================================================== send ====
    def _send_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box, form = self.group("New message")
        self.m_to = PeoplePicker(self.directory, include_groups=True)
        self.m_cc = QLineEdit(placeholderText="Optional, comma separated")
        self.m_bcc = QLineEdit(placeholderText="Optional, comma separated")
        self.m_from = PersonField(self.directory, "Optional – defaults to your admin account",
                                  include_groups=True)
        self.m_subject = QLineEdit()
        self.m_body = QTextEdit()
        self.m_body.setAcceptRichText(False)
        self.m_body.setFixedHeight(160)
        self.m_html = QCheckBox("Message is HTML")
        self.m_attach = QListWidget()
        self.m_attach.setFixedHeight(64)
        form.addRow("To", self.m_to)
        form.addRow("Cc", self.m_cc)
        form.addRow("Bcc", self.m_bcc)
        form.addRow("From", self.m_from)
        form.addRow("Subject", self.m_subject)
        form.addRow("Message", self.m_body)
        form.addRow("", self.m_html)
        form.addRow("Attachments", self.m_attach)
        form.addRow("", self.row(button("Add file…", slot=self._attach),
                                 button("Remove file", slot=lambda: [
                                     self.m_attach.takeItem(self.m_attach.row(i))
                                     for i in self.m_attach.selectedItems()])))
        note = QLabel("Without Cc/Bcc, each recipient gets their own copy. With Cc or Bcc, "
                      "one message goes to everyone.", objectName="Muted")
        note.setWordWrap(True)
        form.addRow("", note)
        form.addRow("", self.row(button("Send", "primary", self.send)))
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def _attach(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach files")
        for p in paths:
            self.m_attach.addItem(os.path.normpath(p))

    def send(self):
        to = self.m_to.emails()
        if not to:
            self.info("Add at least one recipient.")
            return
        if not self.m_subject.text().strip():
            self.info("Add a subject.")
            return
        body = self.m_body.toPlainText()
        args = ["sendemail", "to", ",".join(to)]
        if self.m_cc.text().strip():
            args += ["cc", self.m_cc.text().replace(" ", "")]
        if self.m_bcc.text().strip():
            args += ["bcc", self.m_bcc.text().replace(" ", "")]
        if "@" in self.m_from.email():
            args += ["from", self.m_from.email()]
        args += ["subject", self.m_subject.text().strip(),
                 "htmlmessage" if self.m_html.isChecked() else "message", body]
        for i in range(self.m_attach.count()):
            args += ["attach", self.m_attach.item(i).text()]
        if self.confirm(f"Send “{self.m_subject.text().strip()}” to {len(to)} recipient(s)?"):
            self.run(args)
