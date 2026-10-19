"""Tools → Ask GAMbit: describe a job in plain English, get GAM commands to review."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLabel, QPlainTextEdit

from ...gam_runner import display_command
from ...integrations import assistant
from ..steps import Step, StepList
from ..widgets import Page, ResultsTable, Worker, button

EXAMPLES = ("List every 5th grader at Lincoln who hasn't signed in this month · "
            "Move the Chromebooks in cart 3 to /Devices/Lincoln/Library · "
            "Add everyone in /Staff/High School to hs-staff@ · "
            "Which groups is jdoe@ a member of?")


class AskPage(Page):
    title = "Ask GAMbit"
    subtitle = ("Describe what you want in plain English: Claude suggests GAM commands "
                "(nothing runs until you click Run), drafts a workflow or clean-up rule, or "
                "you can search what happened in GAMbit's logs.")
    MODES = [("Suggest commands", "commands"),
             ("Look it up for me (Claude runs read-only commands)", "lookup"),
             ("Ask about history (searches this PC)", "history"),
             ("Draft a workflow", "workflow"), ("Draft a clean-up rule", "rule")]
    HINTS = {"commands": "e.g. " + EXAMPLES,
             "lookup": "e.g. Which of Mrs. Lee's students have no Chromebook? · How many "
                       "students at Lincoln haven't signed in this week? · Who owns the "
                       "shared drive called Athletics?",
             "history": "e.g. What did we change for jsmith last week? · Why did last night's "
                        "sync fail? · Who reset passwords yesterday?",
             "workflow": "e.g. When a sub starts: create the account in /Staff/Subs, add them "
                         "to subs@, and share the Sub Folder with them",
             "rule": "e.g. Suspend students at the high school who haven't signed in for 120 "
                     "days, but never more than 100 at once"}

    def build(self):
        self.banner = QLabel("", objectName="Banner")
        self.banner.setWordWrap(True)
        self.body.addWidget(self.banner)
        self.mode = QComboBox()
        for label, key in self.MODES:
            self.mode.addItem(label, key)
        self.mode.currentIndexChanged.connect(self._mode)
        self.body.addLayout(self.row(QLabel("I want to"), self.mode, stretch=True))
        self.ask_box = QPlainTextEdit()
        self.ask_box.setPlaceholderText("e.g. " + EXAMPLES)
        self.ask_box.setMaximumHeight(110)
        self.body.addWidget(self.ask_box)
        self.status = QLabel("", objectName="Muted")
        self.go = button("Suggest commands", "primary", self.ask)
        self.explain_btn = button("Explain with Claude", slot=self.explain_history)
        self.explain_btn.hide()
        self.save_q = button("Ask this every week…", slot=self.schedule_question)
        self.save_q.hide()
        self.body.addLayout(self.row(self.go, self.explain_btn, self.save_q,
                                     button("Scheduled questions…",
                                            slot=self.schedule_question_list),
                                     self.status))
        self.explain = QLabel("")
        self.explain.setWordWrap(True)
        self.body.addWidget(self.explain)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)
        self.run_row = self.row(
            button("Run the selected commands (or all)", "primary", self.run_selected),
            button("Open the first one in the Console", slot=self.to_console))
        self.body.addLayout(self.run_row)
        self.steps = StepList(self)
        self.steps.setMaximumHeight(150)
        self.body.addWidget(self.steps)
        self.result = None

    def _key(self):
        return self.mode.currentData()

    def _mode(self, *_):
        k = self._key()
        self.ask_box.setPlaceholderText(self.HINTS[k])
        self.go.setText({"commands": "Suggest commands", "lookup": "Look it up",
                         "history": "Search the logs",
                         "workflow": "Draft it", "rule": "Draft it"}[k])
        self.explain_btn.setVisible(k == "history")
        self.save_q.setVisible(k == "lookup")
        for i in range(self.run_row.count()):
            w = self.run_row.itemAt(i).widget()
            if w is not None:
                w.setVisible(k == "commands")
        self.table.set_rows([], [])
        self.explain.setText("")
        self.status.setText("")
        self.on_show()

    def on_show(self):
        cfg = assistant.config()
        if self._key() == "history":
            self.banner.hide()
            return
        if not cfg["enabled"] or not cfg["key"]:
            self.banner.setText("Turn on Ask GAMbit and add an Anthropic API key in Settings & "
                                "Updates → Integrations.")
            self.banner.show()
        else:
            self.banner.hide()

    def ask(self):
        text = self.ask_box.toPlainText().strip()
        k = self._key()
        if k == "history":
            return self.search_history(text)
        cfg = assistant.config()
        if not cfg["enabled"] or not cfg["key"]:
            self.on_show()
            return
        if not text:
            return
        self.go.setEnabled(False)
        self.status.setText("Asking Claude…")
        if k in ("workflow", "rule"):
            return self._draft(k, text)
        if k == "lookup":
            return self._lookup(text)

        def done(res):
            self.go.setEnabled(True)
            self.result = res
            from ...activity import is_change
            self.table.set_rows(["Command", "Changes things?", "Why"],
                                [[display_command(c["args"]),
                                  "yes" if is_change(c["args"]) else "no (look-up)", c["why"]]
                                 for c in res["commands"]])
            warn = "".join(f"<br>⚠ {w}" for w in res["warnings"])
            self.explain.setText(res["explanation"] + warn)
            self.status.setText(f"{len(res['commands'])} command(s) suggested")

        def fail(e):
            self.go.setEnabled(True)
            self.status.setText("")
            self.info(str(e))
        Worker(assistant.ask, text, self.directory, on_done=done, on_error=fail)

    def _chosen(self) -> list[list[str]]:
        if not self.result:
            return []
        sel = {r["Command"] for r in self.table.selected_dicts()}
        return [c["args"] for c in self.result["commands"]
                if not sel or display_command(c["args"]) in sel]

    def run_selected(self):
        cmds = self._chosen()
        if not cmds:
            self.info("Ask for something first.")
            return
        if any("<" in a and ">" in a for c in cmds for a in c):
            self.info("Some commands still have placeholders like <student email>. Open them "
                      "in the Console and fill those in first.")
            return
        if not self.confirm("Run these commands?\n\n" +
                            "\n".join(display_command(c) for c in cmds)):
            return
        self.steps.run([Step(display_command(c)[:90], c) for c in cmds],
                       lambda _s: self.info(self.steps.summary()))

    def to_console(self):
        cmds = self._chosen()
        if not cmds:
            return
        self.app.go("Command Console")
        con = self.app.pages["Command Console"]
        box = getattr(con, "input", None) or getattr(con, "cmd", None)
        if box is not None and hasattr(box, "setText"):
            box.setText(display_command(cmds[0])[4:])

    def schedule_question(self):
        from .round11_pages import QuestionsDialog
        QuestionsDialog(self, self.ask_box.toPlainText().strip()).exec()

    def schedule_question_list(self):
        from .round11_pages import QuestionsDialog
        QuestionsDialog(self).exec()

    # ------------------------------------------------------------ look-ups ---
    def _lookup(self, text: str):
        from ...gam_runner import display_command as dc
        self.status.setText("Claude is looking it up (read-only)…")

        def done(res):
            self.go.setEnabled(True)
            self.status.setText(f"{len(res['commands'])} read-only command(s) run")
            self.table.set_rows(["Command run", "Worked?", "Lines of output"],
                                [[dc(a), "yes" if ok else "no", str(len((out or "")
                                                                       .splitlines()))]
                                 for a, ok, out in res["commands"]])
            self.explain.setText((res["answer"] or "(no answer)").replace("\n", "<br>") +
                                 "<br><span style='color:#57606a'>The output of these "
                                 "look-ups was sent to Anthropic to write the answer.</span>")

        def fail(e):
            self.go.setEnabled(True)
            self.status.setText("")
            self.info(str(e))
        Worker(assistant.lookup, text, self.directory, on_done=done, on_error=fail)

    # ------------------------------------------------------------ history ---
    def search_history(self, text: str):
        from ... import activity, history
        if not text:
            return
        res = history.find(text, activity.load(400, team=True), history.read_task_log())
        self.hist = (text, res)
        rows = [[e.get("time", "").replace("T", " "), e.get("who", ""),
                 "ok" if e.get("code") == 0 else f"FAILED ({e.get('code')})",
                 e.get("command", ""), e.get("note", "")] for e in res["activity"]]
        rows += [[w, f"task {k}", "", m, ""] for k, w, m in res["tasks"]]
        rows.sort(key=lambda r: r[0], reverse=True)
        self.table.set_rows(["When", "Who / task", "Result", "What", "Note"], rows)
        s, e = res["range"]
        n = len(rows)
        self.explain.setText(
            f"Searched {s:%b %d} – {e:%b %d %H:%M}" +
            (f" for “{' '.join(res['terms'])}”" if res["terms"] else "") +
            f": {n} match(es), found on this PC. <i>Explain with Claude</i> sends these "
            f"{min(n, 240)} line(s) to Anthropic.")
        self.status.setText("")

    def explain_history(self):
        from ... import history
        cfg = assistant.config()
        if not cfg["enabled"] or not cfg["key"]:
            self.info("Turn on Ask GAMbit and add an Anthropic API key in Settings & Updates → "
                      "Integrations to get an explanation.")
            return
        if not getattr(self, "hist", None):
            self.info("Search the logs first.")
            return
        q, res = self.hist
        self.status.setText("Asking Claude…")
        Worker(assistant.explain_history, q, history.as_text(res),
               on_done=lambda t: (self.status.setText(""),
                                  self.explain.setText(t.replace("\n", "<br>"))),
               on_error=lambda e: (self.status.setText(""), self.info(str(e))))

    # ------------------------------------------------------------ drafts ---
    def _draft(self, kind: str, text: str):
        fn = assistant.draft_workflow if kind == "workflow" else assistant.draft_rule

        def done(d):
            self.go.setEnabled(True)
            self.status.setText("Draft ready – check it, then save.")
            if kind == "workflow":
                self._open_workflow(d)
            else:
                self._open_rule(d)

        def fail(e):
            self.go.setEnabled(True)
            self.status.setText("")
            self.info(str(e))
        Worker(fn, text, self.directory, on_done=done, on_error=fail)

    def _open_workflow(self, wf: dict):
        from ... import custom_workflows as cw
        from .custom_wf_tab import EditDialog
        dlg = EditDialog(self, wf)
        dlg.setWindowTitle("Drafted workflow – review before saving")
        if dlg.exec() and dlg.result_wf:
            mine = [w for w in cw.load() if not w.get("example")]
            cw.save(mine + [dlg.result_wf])
            tab = getattr(self.app.pages.get("Workflows"), "custom_tab", None)
            if tab is not None:
                tab.reload()
            self.info(f"Saved “{dlg.result_wf['name']}” to Workflows → My workflows.")

    def _open_rule(self, rule: dict):
        from ...tools import automation as am
        from .automation_tabs import RuleDialog
        dlg = RuleDialog(self, self.directory, rule)
        dlg.setWindowTitle("Drafted clean-up rule – review before saving")
        if dlg.exec():
            am.save_rules(am.rules() + [dlg.rule()])
            page = self.app.pages.get("Clean-up rules")
            if page is not None and hasattr(page, "refresh"):
                page.refresh()
            self.info(f"Saved “{dlg.rule()['name']}” to Automation → Clean-up rules.")
