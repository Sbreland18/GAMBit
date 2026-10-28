"""Command Builder: every GAM command, searchable, with a fill-in form."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QScrollArea, QSplitter, QStackedWidget, QTabWidget,
    QVBoxLayout, QWidget,
)

from ... import builder_store
from ...command_catalog import Catalog, download
from ...gam_runner import display_command, split_command
from ..builder_form import Ctx, Missing, build
from ..widgets import Page, Worker, button


class BuilderPage(Page):
    title = "Command Builder"
    subtitle = ("Every GAM command, straight from GAM's own reference. Search, fill in the "
                "form, check the preview, then run it or save it as a template.")

    def build(self):
        self.catalog: Catalog | None = None
        self.current = None
        self.form = None
        self.ctx = None

        split = QSplitter(Qt.Horizontal)
        # ---------------------------------------------------------- left ---
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 6, 0)
        self.tabs = QTabWidget()
        lv.addWidget(self.tabs, 1)

        allw = QWidget()
        av = QVBoxLayout(allw)
        av.setContentsMargins(0, 6, 0, 0)
        self.search = QLineEdit(placeholderText="Search: vacation, calendar acl, vault hold…")
        self.search.textChanged.connect(lambda: self._timer.start(200))
        self.section = QComboBox()
        self.section.currentIndexChanged.connect(self.refresh_list)
        av.addWidget(self.search)
        av.addWidget(self.section)
        self.results = QListWidget()
        self.results.setSpacing(3)
        self.results.setWordWrap(True)
        self.results.currentItemChanged.connect(self._picked)
        av.addWidget(self.results, 1)
        self.count = QLabel("", objectName="Muted")
        av.addWidget(self.count)
        self.tabs.addTab(allw, "All commands")

        favw = QWidget()
        fv = QVBoxLayout(favw)
        fv.setContentsMargins(0, 6, 0, 0)
        self.favs = QListWidget()
        self.favs.setSpacing(3)
        self.favs.currentItemChanged.connect(self._picked)
        fv.addWidget(self.favs, 1)
        self.tabs.addTab(favw, "★ Favorites")

        tplw = QWidget()
        tv = QVBoxLayout(tplw)
        tv.setContentsMargins(0, 6, 0, 0)
        self.tpls = QListWidget()
        self.tpls.setSpacing(3)
        self.tpls.currentItemChanged.connect(self._template_picked)
        tv.addWidget(self.tpls, 1)
        tv.addLayout(self.row(button("New template", slot=self.new_template)))
        self.tabs.addTab(tplw, "Templates")
        self.tabs.currentChanged.connect(self._tab_changed)

        self.source = QLabel("", objectName="Muted")
        self.source.setWordWrap(True)
        lv.addWidget(self.source)
        lv.addLayout(self.row(button("Update command list from GAM", slot=self.update_catalog)))

        # --------------------------------------------------------- right ---
        self.right = QStackedWidget()
        self.right.addWidget(QLabel("  Pick a command on the left.", objectName="Muted"))

        cmdw = QWidget()
        cv = QVBoxLayout(cmdw)
        cv.setContentsMargins(8, 0, 0, 0)
        self.c_title = QLabel("")
        self.c_title.setTextFormat(Qt.RichText)
        self.c_title.setWordWrap(True)
        self.c_title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        cv.addWidget(self.c_title)
        self.c_syntax = QPlainTextEdit()
        self.c_syntax.setReadOnly(True)
        self.c_syntax.setMaximumHeight(70)
        self.c_syntax.setStyleSheet("font-family:Consolas,'Cascadia Mono',monospace;"
                                    "font-size:9pt;color:#57606a;background:#f6f8fb;")
        cv.addWidget(self.c_syntax)
        self.form_area = QScrollArea()
        self.form_area.setWidgetResizable(True)
        self.form_area.setFrameShape(QScrollArea.NoFrame)
        cv.addWidget(self.form_area, 1)
        cv.addWidget(QLabel("<b>Preview</b> – you can edit this before running"))
        self.preview = QPlainTextEdit()
        self.preview.setMaximumHeight(80)
        self.preview.setStyleSheet("font-family:Consolas,'Cascadia Mono',monospace;")
        self.preview.textChanged.connect(lambda: setattr(self, "_edited", True))
        cv.addWidget(self.preview)
        self.missing = QLabel("", objectName="Muted")
        cv.addWidget(self.missing)
        self.fav_btn = button("☆ Favorite", slot=self.toggle_fav)
        cv.addLayout(self.row(button("Run", "primary", self.run_preview),
                              button("Copy", slot=lambda: QApplication.clipboard().setText(
                                  self.preview.toPlainText())),
                              button("Reset form", slot=self.reset_form),
                              self.fav_btn,
                              button("Save as template…", slot=self.save_as_template)))
        self.right.addWidget(cmdw)

        tplview = QWidget()
        tpv = QVBoxLayout(tplview)
        tpv.setContentsMargins(8, 0, 0, 0)
        self.t_name = QLineEdit(placeholderText="Template name, e.g. Grade 6 rollover")
        self.t_desc = QLineEdit(placeholderText="What it does (optional)")
        tpv.addWidget(QLabel("<b>Template</b>"))
        tpv.addWidget(self.t_name)
        tpv.addWidget(self.t_desc)
        tpv.addWidget(QLabel("One GAM command per line. Lines starting with # are notes. "
                             "They run in order."))
        self.t_text = QPlainTextEdit()
        self.t_text.setStyleSheet("font-family:Consolas,'Cascadia Mono',monospace;")
        tpv.addWidget(self.t_text, 1)
        self.t_shared = QCheckBox("Share with the team (saved in the team folder)")
        tpv.addWidget(self.t_shared)
        tpv.addLayout(self.row(button("Run template", "primary", self.run_template),
                               button("Save", slot=self.save_template),
                               button("Schedule…", slot=self.schedule_template),
                               button("Delete", "danger", self.delete_template)))
        self.right.addWidget(tplview)

        split.addWidget(left)
        split.addWidget(self.right)
        split.setSizes([380, 760])
        self.body.addWidget(split, 1)

        self._timer = QTimer(self, singleShot=True, timeout=self.refresh_list)
        self._preview_timer = QTimer(self, singleShot=True, timeout=self.update_preview)
        self._edited = False

    # ---------------------------------------------------------- catalog ---
    def on_show(self):
        if self.catalog is None:
            self.load_catalog()
        self.refresh_favs()
        self.refresh_templates()

    def load_catalog(self):
        self.catalog = Catalog()
        self.section.blockSignals(True)
        self.section.clear()
        self.section.addItem("All areas", "")
        for s in self.catalog.sections:
            self.section.addItem(s, s)
        self.section.blockSignals(False)
        self.source.setText(f"{len(self.catalog.commands):,} commands · "
                            f"command list {self.catalog.source}")
        self.refresh_list()

    def update_catalog(self):
        ver = getattr(self.app, "_gam_ver", None)
        self.source.setText("Downloading the command list from GAM's GitHub page…")

        def done(ref):
            self.load_catalog()
            self.source.setText(self.source.text() + f" (GAM {ref})")
        Worker(download, ver, on_done=done,
               on_error=lambda e: self.source.setText(f"Couldn't update: {e}"))

    def show_query(self, query: str = "", section: str = ""):
        """Open the builder pre-filtered (used by other pages)."""
        if self.catalog is None:
            self.load_catalog()
        self.tabs.setCurrentIndex(0)
        idx = self.section.findData(section) if section else 0
        self.section.setCurrentIndex(max(0, idx))
        self.search.setText(query)
        self.refresh_list()

    def refresh_list(self):
        if not self.catalog:
            return
        found = self.catalog.search(self.search.text(), self.section.currentData() or "")
        self.results.clear()
        for c in found:
            self._add_item(self.results, c)
        self.count.setText(f"{len(found)} shown" + (" (top 400)" if len(found) >= 400 else ""))

    def _add_item(self, lst, c):
        it = QListWidgetItem(f"{c.title}\n{c.description}")
        it.setData(Qt.UserRole, c)
        it.setToolTip(f"{c.section}\n\n{c.syntax}")
        lst.addItem(it)

    def refresh_favs(self):
        if not self.catalog:
            return
        favs = set(builder_store.load()["favorites"])
        self.favs.clear()
        for c in self.catalog.commands:
            if c.syntax in favs:
                self._add_item(self.favs, c)
        if not favs:
            self.favs.addItem("Click ☆ Favorite on any command to pin it here.")

    def _tab_changed(self, i):
        if i == 2:
            self.right.setCurrentIndex(2 if self.tpls.currentItem() else 0)
        elif self.current:
            self.right.setCurrentIndex(1)

    # ------------------------------------------------------------- form ---
    def _picked(self, item, _prev=None):
        c = item.data(Qt.UserRole) if item else None
        if c is None:
            return
        self.open_command(c)

    def open_command(self, c):
        self.current = c
        self.right.setCurrentIndex(1)
        self.c_title.setText(
            f"<span style='font-size:13pt;font-weight:600'>{html.escape(c.description)}</span>"
            f"<br><span style='color:#57606a'>{html.escape(c.section)}</span>")
        self.c_syntax.setPlainText(c.syntax)
        favs = builder_store.load()["favorites"]
        self.fav_btn.setText("★ Favorite" if c.syntax in favs else "☆ Favorite")
        self.reset_form()

    def reset_form(self):
        if not self.current:
            return
        self.ctx = Ctx(self.catalog, self.directory, lambda *_: self._preview_timer.start(150))
        holder = QWidget(objectName="Page")
        hv = QVBoxLayout(holder)
        hv.setContentsMargins(0, 0, 8, 0)
        try:
            self.form = build(self.current.tree, self.ctx)
            hv.addWidget(self.form)
        except Exception as exc:  # noqa: BLE001
            self.form = None
            hv.addWidget(QLabel(f"This command's form couldn't be built ({exc}). "
                                "Type it in the preview box instead."))
        hv.addStretch(1)
        self.form_area.setWidget(holder)
        self._edited = False
        self.update_preview(force=True)

    def _commands(self) -> list[list[str]]:
        """All commands the form describes (one per org unit/entity if several)."""
        if self.form is None:
            return []
        args = self.form.args()
        cmds = [args]
        if self.ctx.targets:
            t = self.ctx.targets[0]
            ents = t.all_entities()
            first = t.args()
            if len(ents) > 1:
                n = len(first)
                pos = next((i for i in range(len(args) - n + 1) if args[i:i + n] == first), None)
                if pos is not None:
                    cmds = [args[:pos] + e + args[pos + n:] for e in ents]
        return cmds

    def update_preview(self, force=False):
        if self._edited and not force:
            return
        try:
            cmds = self._commands()
            text = "\n".join(display_command(c) for c in cmds)
            self.missing.setText("")
        except Missing as m:
            text = ""
            self.missing.setText(f"Still needed: {m.args[0]}")
        self.preview.blockSignals(True)
        self.preview.setPlainText(text)
        self.preview.blockSignals(False)
        self._edited = False

    def _preview_lines(self) -> list[list[str]]:
        out = []
        for ln in self.preview.toPlainText().splitlines():
            if ln.strip() and not ln.strip().startswith("#"):
                if "********" in ln:
                    raise ValueError("password")
                out.append(split_command(ln))
        return out

    def _run_lines(self, lines: list[list[str]]):
        if not lines:
            self.info("There's nothing to run yet. Fill in the form (see 'Still needed').")
            return
        first = lines[0][0] if lines[0] else ""
        risky = any(w in ("delete", "del", "purge", "wipe", "remove", "clear", "deprovision",
                          "empty", "cancel") for ln in lines for w in ln[:4])
        if risky or len(lines) > 1 or first in ("all",):
            if not self.confirm("Run these command(s)?\n\n" +
                                "\n".join(display_command(c) for c in lines[:20])):
                return
        quiet = all(c[:1] == ["print"] or "print" in c[:4] for c in lines)
        if quiet and len(lines) == 1:
            self.run(lines[0], lambda code, out, _e: self.app.show_csv(out, display_command(
                lines[0])) if code == 0 and out.strip() else None, quiet=True)
        else:
            self.run_many(lines, lambda _o: None, quiet=False)

    def run_preview(self):
        try:
            if self._edited:
                lines = self._preview_lines()
            else:
                lines = self._commands()
        except Missing as m:
            self.info(f"Please fill in: {m.args[0]}")
            return
        except ValueError:
            # preview masks passwords – rebuild from the form instead
            lines = self._commands()
        self._run_lines(lines)

    def toggle_fav(self):
        if self.current:
            on = builder_store.toggle_favorite(self.current.syntax)
            self.fav_btn.setText("★ Favorite" if on else "☆ Favorite")
            self.refresh_favs()

    # -------------------------------------------------------- templates ---
    def refresh_templates(self):
        self.tpls.clear()
        for t in builder_store.templates():
            tag = "Shared · " if t.get("shared") else ""
            it = QListWidgetItem(f"{tag}{t['name']}\n{t.get('description', '')}")
            if t.get("shared"):
                it.setToolTip("Shared with the team" + (f" – saved by {t['by']}"
                                                         if t.get("by") else ""))
            it.setData(Qt.UserRole, t)
            self.tpls.addItem(it)

    def _template_picked(self, item, _prev=None):
        t = item.data(Qt.UserRole) if item else None
        if not t:
            return
        self.t_name.setText(t["name"])
        self.t_desc.setText(t.get("description", ""))
        self.t_text.setPlainText("\n".join(t.get("commands", [])))
        self.t_shared.setChecked(bool(t.get("shared")))
        self.right.setCurrentIndex(2)

    def new_template(self):
        self.tpls.clearSelection()
        self.t_name.clear()
        self.t_desc.clear()
        self.t_text.setPlainText("# Example: move grade 6 into grade 7\n")
        self.t_shared.setChecked(False)
        self.right.setCurrentIndex(2)

    def save_as_template(self):
        try:
            if self._edited:
                text = self.preview.toPlainText()
            else:
                text = "\n".join(display_command(c) for c in self._commands())
        except Missing as m:
            self.info(f"Please fill in: {m.args[0]}")
            return
        if "********" in text:
            self.info("Templates can't store passwords. Remove the password part first.")
            return
        name, ok = QInputDialog.getText(self, "Save template", "Template name:")
        if ok and name.strip():
            builder_store.save_template(name.strip(), text.splitlines(),
                                        self.current.description if self.current else "")
            self.refresh_templates()
            self.info(f"Saved “{name.strip()}”. Find it under Templates.")

    def save_template(self):
        name = self.t_name.text().strip()
        if not name:
            self.info("Give the template a name.")
            return
        from ... import team
        shared = self.t_shared.isChecked()
        if shared and not team.folder():
            self.info("Choose a team folder in Settings & Updates → Team first.")
            return
        try:
            builder_store.save_template(name, self.t_text.toPlainText().splitlines(),
                                        self.t_desc.text().strip(), shared=shared)
        except OSError as exc:
            self.info(f"Couldn't save to the team folder:\n{exc}")
            return
        self.refresh_templates()

    def delete_template(self):
        name = self.t_name.text().strip()
        if name and self.confirm(f"Delete the template “{name}”?"):
            builder_store.delete_template(name)
            self.refresh_templates()
            self.new_template()

    def run_template(self):
        lines = []
        for ln in self.t_text.toPlainText().splitlines():
            if ln.strip() and not ln.strip().startswith("#"):
                try:
                    lines.append(split_command(ln))
                except ValueError as exc:
                    self.info(f"Couldn't read this line:\n{ln}\n\n{exc}")
                    return
        self._run_lines(lines)

    def schedule_template(self):
        self.save_template()
        if self.t_name.text().strip():
            self.app.go("Scheduled jobs")
            self.app.pages["Scheduled jobs"].prefill(self.t_name.text().strip())
