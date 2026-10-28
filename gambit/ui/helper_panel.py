"""💬 Helper – GAMbit's offline assistant, docked on the right of the main window.

It understands plain English (typos are fine), opens the right page, walks people through a
page step by step, and writes GAM commands. A command is only ever *suggested*: it runs when
the person clicks Run, and then goes through the same role check, dry run and approvals as
any other button in GAMbit. The optional local AI (Settings in the panel) answers open
questions; it runs on this PC only.
"""

from __future__ import annotations

import html
import re
import urllib.parse

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractButton, QCheckBox, QComboBox, QDialog, QDockWidget, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QRadioButton,
    QScrollArea, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from ..gam_runner import display_command
from ..helper import local_ai
from ..helper.brain import Answer, Brain, to_html
from ..settings import settings
from .widgets import Worker, button

CSS = """
body { font-family: 'Segoe UI', sans-serif; font-size: 10pt; color:#1f2933; }
.me { background:#e8f1fb; border-radius:8px; padding:6px 9px; margin:8px 0 2px 30px; }
.bot { padding:4px 2px; margin:2px 0 6px 0; }
.card { background:#f6f8fa; border:1px solid #d8dee4; padding:6px; margin:4px 0; }
code { font-family: Consolas, monospace; background:#eef1f4; }
pre { font-family: Consolas, monospace; font-size:9pt; background:#f6f8fa; white-space: pre-wrap; }
a { color:#0b63c5; text-decoration:none; }
.chip { color:#0b63c5; }
.muted { color:#6b7785; font-size:9pt; }
.ok { color:#1a7f37; } .warn { color:#9a6700; } .chg { color:#b42318; font-weight:600; }
"""


def _clean(t: str) -> str:
    """Button text without accelerators, emoji and punctuation, for matching a step's
    **bold label** to a button on the page."""
    t = (t or "").replace("&", "")
    t = re.sub(r"[^\w\s/'-]", " ", t)
    return re.sub(r"\s+", " ", t).strip().lower()


class HelperDock(QDockWidget):
    def __init__(self, app):
        super().__init__("Helper", app)
        self.app = app
        self.setObjectName("HelperDock")
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.brain: Brain | None = None
        self.blocks: list[str] = []
        self.cmds: list[dict] = []
        self.docs: list = []
        self.walk = None            # (doc, index)
        self._ai_busy = False

        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 6, 8, 8)
        top = QHBoxLayout()
        top.addWidget(QLabel("Ask me anything about GAMbit or GAM.", objectName="Muted"), 1)
        self.ai_lbl = QLabel("", objectName="Muted")
        top.addWidget(self.ai_lbl)
        _gear = button("", slot=self.open_ai_settings)
        from .icons import set_icon as _si
        _si(_gear, "settings")
        _gear.setToolTip("Helper settings (local AI)")
        top.addWidget(_gear)
        top.addWidget(button("Clear", slot=self.clear))
        v.addLayout(top)

        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.setOpenExternalLinks(False)
        self.view.document().setDefaultStyleSheet(CSS)
        self.view.anchorClicked.connect(self._anchor)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        v.addWidget(self.view, 1)

        # walkthrough bar
        self.walk_bar = QFrame()
        self.walk_bar.setStyleSheet("QFrame{background:#fff8e1;border:1px solid #f2d675;"
                                    "border-radius:6px;}")
        wb = QVBoxLayout(self.walk_bar)
        wb.setContentsMargins(8, 6, 8, 6)
        self.walk_title = QLabel()
        self.walk_title.setStyleSheet("font-weight:600;border:none;")
        self.walk_text = QLabel()
        self.walk_text.setWordWrap(True)
        self.walk_text.setTextFormat(Qt.RichText)
        self.walk_text.setStyleSheet("border:none;")
        wb.addWidget(self.walk_title)
        wb.addWidget(self.walk_text)
        row = QHBoxLayout()
        self.walk_back = button("◀ Back", slot=lambda: self._walk_step(-1))
        self.walk_next = button("Next ▶", "primary", slot=lambda: self._walk_step(1))
        self.walk_show = button("Show me", slot=self._highlight)
        row.addWidget(self.walk_back)
        row.addWidget(self.walk_show)
        row.addStretch(1)
        row.addWidget(button("Stop", slot=self.stop_walk))
        row.addWidget(self.walk_next)
        wb.addLayout(row)
        self.walk_bar.hide()
        v.addWidget(self.walk_bar)

        row = QHBoxLayout()
        self.input = QLineEdit(placeholderText="e.g. reset jane doe's password  ·  how do I "
                                               "add a teacher?")
        self.input.returnPressed.connect(self.send)
        row.addWidget(self.input, 1)
        row.addWidget(button("Send", "primary", self.send))
        v.addLayout(row)
        self.setWidget(w)
        self.setMinimumWidth(340)
        self._refresh_ai_label()

    # ------------------------------------------------------------ public ---
    def toggle(self):
        if self.isVisible():
            self.hide()
            return
        self.show()
        self.raise_()
        self.ensure_brain()
        self.input.setFocus()

    def ask(self, text: str):
        """Open the panel and ask a question (used by other parts of GAMbit)."""
        self.show()
        self.ensure_brain()
        self.input.setText(text)
        self.send()

    def ensure_brain(self):
        if self.brain is not None:
            return
        from ..helper import knowledge
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            k = knowledge.build(self.app)
        finally:
            QGuiApplication.restoreOverrideCursor()
        self.brain = Brain(k, getattr(self.app, "directory", None),
                           ai_available=lambda: local_ai.enabled() and local_ai.installed())
        if not self.blocks:
            self._bot(self.brain.respond(""))

    def clear(self):
        self.blocks, self.cmds, self.docs = [], [], []
        if self.brain:
            self.brain.pending, self.brain.memory, self.brain.history = None, {}, []
        self.stop_walk()
        self._render()
        if self.brain:
            self._bot(self.brain.respond(""))

    # ------------------------------------------------------------- chat ---
    def _page_name(self) -> str:
        return getattr(self.app, "_current_page_name", "") or ""

    def send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.ensure_brain()
        self._add(f"<div class='me'>{html.escape(text)}</div>")
        try:
            ans = self.brain.respond(text, page=self._page_name())
        except Exception as exc:  # noqa: BLE001 – never let the Helper crash GAMbit
            ans = Answer(f"Sorry – something went wrong understanding that ({exc}).")
        if ans.needs_ai:
            self._ask_ai(text, ans)
        else:
            self._bot(ans)
        self.brain.history += [{"role": "user", "content": text},
                               {"role": "assistant", "content": ans.text[:600]}]
        self.brain.history = self.brain.history[-8:]

    def _allowed(self, d) -> bool:
        from .. import team
        try:
            return not d.page or team.page_allowed(d.page)
        except Exception:  # noqa: BLE001
            return True

    def _bot(self, a: Answer):
        parts = []
        if a.text:
            parts.append(to_html(a.text))
        for s in a.suggestions:
            parts.append(self._card(list(s.args), s.change, s.explain or s.title,
                                    note=getattr(s, "note", "")))
        links = [d for d in a.links if self._allowed(d)]
        if links:
            ls = []
            for d in links[:4]:
                i = len(self.docs)
                self.docs.append(d)
                name = f"{d.page} → {d.tab}" if d.kind == "tab" else (d.page or d.title)
                ls.append(f"<a href='open:{i}'>Open {html.escape(name)}</a>")
            parts.append(" &nbsp; ".join(ls))
        if a.walkthrough is not None and a.walkthrough.steps and self._allowed(a.walkthrough):
            i = len(self.docs)
            self.docs.append(a.walkthrough)
            parts.append(f"<a href='walk:{i}'>Walk me through "
                         f"{html.escape(a.walkthrough.page)}</a>")
        if a.chips:
            parts.append("<span class='muted'>Try: </span>" + " · ".join(
                f"<a class='chip' href='ask:{urllib.parse.quote(c)}'>{html.escape(c)}</a>"
                for c in a.chips[:5]))
        self._add("<div class='bot'>" + "<br>".join(parts) + "</div>")
        # "walk me through X" starts the walkthrough straight away
        if a.walkthrough is not None and a.walkthrough.steps and not a.suggestions and \
                self.brain and "walk" in self.brain.k.norm.words(
                    self._last_question()) and self._allowed(a.walkthrough):
            self.start_walk(a.walkthrough)

    def _last_question(self) -> str:
        for b in reversed(self.blocks):
            if b.startswith("<div class='me'>"):
                return html.unescape(re.sub(r"<[^>]+>", "", b))
        return ""

    def _card(self, args: list[str], change: bool, explain: str, note: str = "",
              verified: bool | None = None) -> str:
        from ..helper import verify
        if verified is None:
            verified, _how = verify.check(args)
        i = len(self.cmds)
        self.cmds.append({"args": args, "change": change, "verified": verified})
        shown = html.escape(display_command(args))
        badge = ("<span class='ok'>✔ checked against GAM</span>" if verified else
                 "<span class='warn'>⚠ not a command I recognise – check it first</span>")
        kind = ("<span class='chg'>changes things</span>" if change else
                "<span class='muted'>only reads</span>")
        rows = [f"<code>{shown}</code>"]
        if explain:
            rows.append(html.escape(explain))
        if note:
            rows.append(f"<span class='muted'>{html.escape(note)}</span>")
        rows.append(f"{badge} · {kind}")
        rows.append(f"<a href='run:{i}'>▶ Run</a> &nbsp; <a href='copy:{i}'>Copy</a> &nbsp; "
                    f"<a href='console:{i}'>✎ Edit in Console</a>")
        return ("<table class='card' width='100%' cellpadding='6'><tr><td>" +
                "<br>".join(rows) + "</td></tr></table>")

    def _add(self, block: str):
        self.blocks.append(block)
        self.blocks = self.blocks[-120:]
        self._render()

    def _render(self):
        self.view.setHtml("".join(self.blocks))
        QTimer.singleShot(0, lambda: self.view.verticalScrollBar().setValue(
            self.view.verticalScrollBar().maximum()))

    # ---------------------------------------------------------- anchors ---
    def _anchor(self, url: QUrl):
        s = url.toString()
        kind, _, rest = s.partition(":")
        try:
            if kind == "ask":
                self.input.setText(urllib.parse.unquote(rest))
                self.send()
            elif kind == "open":
                self.open_doc(self.docs[int(rest)])
            elif kind == "walk":
                self.start_walk(self.docs[int(rest)])
            elif kind == "run":
                self.run_cmd(int(rest))
            elif kind == "copy":
                QGuiApplication.clipboard().setText(
                    display_command(self.cmds[int(rest)]["args"]))
                self.app.statusBar().showMessage("Command copied.", 3000)
            elif kind == "console":
                self.to_console(int(rest))
            elif kind == "ai":
                self.open_ai_settings()
        except (IndexError, ValueError):
            pass

    def open_doc(self, d):
        from .pages.insight_pages import goto
        if d.page:
            goto(self.app, d.page, d.tab)

    def to_console(self, i: int):
        c = self.cmds[i]
        if "Command Console" not in self.app.pages:
            return
        self.app.go("Command Console")
        con = self.app.pages["Command Console"]
        box = getattr(con, "cmd", None)
        if box is not None:
            box.setText(" ".join(_quote(a) for a in c["args"]))
            box.setFocus()

    def run_cmd(self, i: int):
        c = self.cmds[i]
        args = c["args"]
        if any(re.search(r"<[^>]+>", a) for a in args):
            QMessageBox.information(self, "GAMbit Helper", "This command still has a "
                                    "placeholder like <email>. Click “Edit in Console” and "
                                    "fill it in first.")
            return
        warn = "" if c["verified"] else ("\n\n⚠ GAMbit couldn't match this against GAM's "
                                         "command reference – make sure it's right.")
        if c["change"] or not c["verified"]:
            if QMessageBox.question(self, "Run this command?", display_command(args) +
                                    ("\n\nThis changes things in Google." if c["change"]
                                     else "") + warn, QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) != QMessageBox.Yes:
                return
        self._add("<div class='bot muted'>Running <code>" +
                  html.escape(display_command(args)) + "</code> …</div>")
        started = self.app.runner.run(list(args), lambda code, out, err:
                                      self._ran(args, code, out, err))
        if started is False:
            self._add("<div class='bot warn'>It didn't run here – the Output panel says "
                      "why (for example it was sent for approval, your GAMbit role doesn't "
                      "allow it, or help-desk mode is on).</div>")

    def _ran(self, args, code, out, err):
        from ..gam_runner import dry_run_on
        from ..activity import is_change
        if dry_run_on() and is_change(args):
            self._add("<div class='bot'>Dry run is on, so nothing changed – the command "
                      "is listed in the <b>Dry run</b> tab.</div>")
            return
        text = (out or "").strip()
        lines = text.splitlines()
        if code == 0:
            msg = "✔ Done."
            if lines:
                more = len(lines) - 12
                msg += "<pre>" + html.escape("\n".join(lines[:12])) + "</pre>"
                if more > 0:
                    msg += (f"<span class='muted'>… {more:,} more lines in the Output "
                            "panel.</span>")
        else:
            msg = ("✖ GAM reported a problem:<pre>" +
                   html.escape(((err or "") + "\n" + text).strip()[-1200:]) + "</pre>")
        self._add(f"<div class='bot'>{msg}</div>")

    # ------------------------------------------------------ walkthroughs ---
    def start_walk(self, d):
        if not d.steps:
            return
        self.walk = (d, 0)
        self.open_doc(d)
        self.walk_bar.show()
        self._show_step()

    def stop_walk(self):
        self.walk = None
        self.walk_bar.hide()

    def _walk_step(self, delta: int):
        if not self.walk:
            return
        d, i = self.walk
        i += delta
        if i >= len(d.steps):
            self.stop_walk()
            self._add(f"<div class='bot'>That's everything on <b>{html.escape(d.page)}</b>. "
                      "Ask me if anything wasn't clear.</div>")
            return
        self.walk = (d, max(0, i))
        self._show_step()

    def _show_step(self):
        d, i = self.walk
        self.walk_title.setText(f"{d.page} – step {i + 1} of {len(d.steps)}")
        self.walk_text.setText(to_html(d.steps[i]))
        self.walk_back.setEnabled(i > 0)
        self.walk_next.setText("Finish ✔" if i == len(d.steps) - 1 else "Next ▶")
        self.walk_show.setEnabled(bool(self._target_button() or self._target_tab()))
        QTimer.singleShot(150, self._highlight)

    def _target_button(self):
        """The button on the open page named in the step's first **bold** label."""
        if not self.walk:
            return None
        d, i = self.walk
        page = self.app.pages.get(d.page)
        if page is None:
            return None
        labels = self._labels()
        if not labels:
            return None
        btns = [b for b in page.findChildren(QAbstractButton) if b.isVisibleTo(page)]
        for lab in labels:
            for b in btns:
                t = _clean(b.text())
                if t and (t == lab or (len(lab) > 4 and (lab in t or t in lab)
                                       and abs(len(t) - len(lab)) < 12)):
                    return b
        return None

    def _labels(self) -> list[str]:
        d, i = self.walk
        return [x for x in (_clean(y) for y in re.findall(r"\*\*(.+?)\*\*", d.steps[i]))
                if len(x) > 2]

    def _target_tab(self):
        """(tab widget, index) when the step names one of the page's tabs."""
        if not self.walk:
            return None
        page = self.app.pages.get(self.walk[0].page)
        if page is None:
            return None
        for lab in self._labels():
            for tw in page.findChildren(QTabWidget):
                for k in range(tw.count()):
                    if _clean(tw.tabText(k)) == lab:
                        return tw, k
        return None

    def _highlight(self):
        t = self._target_tab()
        if t is not None:
            t[0].setCurrentIndex(t[1])
        b = self._target_button()
        if b is None:
            return
        # bring it into view (pages sit in scroll areas) and its tab to the front
        w = b.parentWidget()
        while w is not None:
            p = w.parentWidget()
            if isinstance(p, QWidget) and isinstance(p.parentWidget(), QTabWidget):
                tabs = p.parentWidget()
                idx = tabs.indexOf(w)
                if idx >= 0:
                    tabs.setCurrentIndex(idx)
            if isinstance(w, QScrollArea):
                w.ensureWidgetVisible(b)
            w = p
        old = b.styleSheet()
        b.setStyleSheet(old + "border:3px solid #f59e0b;background:#fff4ce;")
        QTimer.singleShot(2200, lambda: b.setStyleSheet(old))

    # --------------------------------------------------------------- AI ---
    def _refresh_ai_label(self):
        on = local_ai.enabled() and local_ai.installed()
        self.ai_lbl.setText("Local AI on" if on else "")

    def _ask_ai(self, question: str, ans: Answer):
        if self._ai_busy:
            self._bot(Answer("I'm still thinking about your last question – one moment."))
            return
        self._ai_busy = True
        self._add("<div class='bot muted' id='thinking'>Thinking (on this PC)… this can "
                  "take up to a minute the first time.</div>")
        links = ans.links
        hist = list(self.brain.history)

        def done(text):
            self._ai_busy = False
            self._drop_thinking()
            self._show_ai(text or "", links)

        def fail(err):
            self._ai_busy = False
            self._drop_thinking()
            self._bot(Answer(f"The local AI couldn't answer ({err}). Here's what I found "
                             "instead:", links=links,
                             chips=["What can you do?"]))
        Worker(local_ai.answer, question, ans.ai_context, hist, on_done=done, on_error=fail)

    def _drop_thinking(self):
        self.blocks = [b for b in self.blocks if "id='thinking'" not in b]

    def _show_ai(self, text: str, links):
        from ..activity import is_change
        from ..helper import verify
        cmds = verify.extract_commands(text)
        body = re.sub(r"```.*?```", "", text, flags=re.S).strip()
        a = Answer(body or "Here's what I'd try:", links=links)
        self._bot(a)
        for c in cmds:
            args = verify.split(c)
            if not args:
                continue
            ok, _how = verify.check(args)
            self._add("<div class='bot'>" + self._card(
                args, is_change(args), verify.describe(args), verified=ok,
                note="Written by the local AI – read it before you run it.") + "</div>")

    def open_ai_settings(self):
        LocalAIDialog(self).exec()
        self._refresh_ai_label()


def _quote(a: str) -> str:
    return f'"{a}"' if (" " in a or not a) and not a.startswith('"') else a


# ===================================================================== AI ===
class LocalAIDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Helper – local AI")
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        intro = QLabel(
            "The Helper works without this. Turning on the local AI lets it answer open "
            "questions in its own words. It runs <b>on this PC only</b> – nothing you type "
            "leaves the computer. It needs a one-time download (or copy the files in from "
            "another PC) and about 8 GB of memory for the standard model.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        self.on = QCheckBox("Use the local AI for questions the Helper can't answer itself")
        self.on.setChecked(local_ai.enabled())
        v.addWidget(self.on)
        self.own = QRadioButton("GAMbit's own (llama.cpp + Qwen2.5 model)")
        self.oll = QRadioButton("Ollama, already installed on this PC")
        (self.oll if local_ai.engine() == "ollama" else self.own).setChecked(True)
        v.addWidget(self.own)
        v.addWidget(self.oll)

        row = QHBoxLayout()
        self.model = QComboBox()
        for key, m in local_ai.MODELS.items():
            self.model.addItem(m["label"], key)
        row.addWidget(self.model, 1)
        self.get_btn = button("Download", "primary", self.download)
        row.addWidget(self.get_btn)
        v.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(button("Choose a model file (.gguf)…", slot=self.pick_model))
        row.addWidget(button("Choose llama-server…", slot=self.pick_server))
        row.addStretch(1)
        v.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Ollama model:"))
        self.ollama = QComboBox()
        self.ollama.setEditable(True)
        row.addWidget(self.ollama, 1)
        v.addLayout(row)
        self.bar = QProgressBar()
        self.bar.hide()
        v.addWidget(self.bar)
        self.status = QLabel()
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        row = QHBoxLayout()
        row.addWidget(button("Test it", slot=self.test))
        row.addStretch(1)
        row.addWidget(button("Close", slot=self.accept))
        v.addLayout(row)
        self.own.toggled.connect(self._save)
        self.on.toggled.connect(self._save)
        self.ollama.currentTextChanged.connect(
            lambda t: settings.set("helper/ollama_model", t.strip()))
        self._cancel = False
        self._load_ollama()
        self._refresh()

    def _load_ollama(self):
        cur = settings.get("helper/ollama_model", "") or ""
        self.ollama.blockSignals(True)
        self.ollama.clear()
        self.ollama.addItems(local_ai.ollama_models())
        if cur:
            self.ollama.setCurrentText(cur)
        self.ollama.blockSignals(False)

    def _save(self, *_a):
        local_ai.set_enabled(self.on.isChecked())
        settings.set("helper/ai_engine", "ollama" if self.oll.isChecked() else "builtin")
        if self.oll.isChecked():
            local_ai.Server.stop()
        self._refresh()

    def _refresh(self):
        own = self.own.isChecked()
        for w in (self.model, self.get_btn):
            w.setEnabled(own)
        self.ollama.setEnabled(not own)
        self.status.setText("Status: " + local_ai.status())

    def pick_model(self):
        p, _ = QFileDialog.getOpenFileName(self, "Model file", "", "GGUF models (*.gguf)")
        if p:
            if not local_ai.is_gguf(p):
                QMessageBox.warning(self, "Local AI", "That isn't a GGUF model file.")
                return
            settings.set("helper/model_path", p)
            local_ai.Server.stop()
            self._refresh()

    def pick_server(self):
        p, _ = QFileDialog.getOpenFileName(self, "llama-server", "",
                                           "llama-server (llama-server*)")
        if p:
            settings.set("helper/server_path", p)
            local_ai.Server.stop()
            self._refresh()

    def download(self):
        if self.get_btn.text() == "Cancel":
            self._cancel = True
            return
        which = self.model.currentData()
        self._cancel = False
        self.get_btn.setText("Cancel")
        self.bar.show()
        self.bar.setValue(0)

        def job(progress=None, log=None):
            if not local_ai.server_path():
                local_ai.download_server(progress, log)
            if not local_ai.model_path():
                local_ai.download_model(which, progress, log, lambda: self._cancel)
            return local_ai.status()

        def prog(done, total):
            if total:
                self.bar.setMaximum(1000)
                self.bar.setValue(int(done * 1000 / total))
                self.bar.setFormat(f"{done // 1_000_000:,} of {total // 1_000_000:,} MB")

        def finished(st):
            self.get_btn.setText("Download")
            self.bar.hide()
            self.on.setChecked(True)
            self._refresh()

        def failed(err):
            self.get_btn.setText("Download")
            self.bar.hide()
            self.status.setText(f"Download didn't finish: {err}")

        Worker(job, on_done=finished, on_error=failed, on_progress=prog,
               on_message=lambda m: self.status.setText(m), use_progress=True, use_log=True)

    def test(self):
        self.status.setText("Asking the local AI a test question…")

        Worker(local_ai.chat, [{"role": "user", "content": "Reply with the single word: ready"}],
               40, 180, on_done=lambda t: self.status.setText(f"✔ The local AI answered: "
                                                               f"{t[:80]}"),
               on_error=lambda e: self.status.setText(f"✖ {e}"))

