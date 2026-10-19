"""Guide: what every feature does and how to use it, plus the GAM command reference."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QLabel, QLineEdit, QSplitter, QTextBrowser, QTreeWidget,
    QTreeWidgetItem,
)

from ..widgets import Page, button

STYLE = """
h3{margin-top:14px} code{background:#eef1f6;color:#1d2433} pre{background:#eef1f6;color:#1d2433}
.lead{font-size:15px} .muted{color:#7a8499} .hl{background:#ffe58a;color:#1d2433}
.crumb{color:#7a8499} table.cmds td{padding:4px 6px;border-bottom:1px solid #d9dee8}
"""


class GuidePage(Page):
    title = "Guide"
    subtitle = ("What every part of GAMbit does and how to use it, plus a plain-English list "
                "of GAM commands. Type in the search box – e.g. reset password, lost "
                "Chromebook, legal hold, print users.")

    def build(self):
        self.articles, self.by_id = [], {}
        self.q = QLineEdit()
        self.q.setPlaceholderText("Search the guide and GAM commands…")
        self.q.setClearButtonEnabled(True)
        self._t = QTimer(self, singleShot=True, interval=180, timeout=self._search)
        self.q.textChanged.connect(lambda _t: self._t.start())
        self.count = QLabel("", objectName="Muted")
        self.open_btn = button("Open this in GAMbit", "primary", self.open_here)
        self.builder_btn = button("Open in Command Builder", slot=self.open_builder)
        self.copy_btn = button("Copy command", slot=self.copy_cmd)
        self.body.addLayout(self.row(self.q, self.count, stretch=False))
        self.body.addLayout(self.row(self.open_btn, self.builder_btn, self.copy_btn,
                                     button("Back", slot=self.back),
                                     button("Save the guide as a web page…",
                                            slot=self.export)))
        split = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(260)
        self.tree.currentItemChanged.connect(self._picked)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link)
        self.view.document().setDefaultStyleSheet(STYLE)
        split.addWidget(self.tree)
        split.addWidget(self.view)
        split.setStretchFactor(1, 3)
        split.setSizes([300, 900])
        self.body.addWidget(split, 1)
        self.current, self.history = None, []
        self._built = False

    # ------------------------------------------------------------- content ---
    def ensure_built(self):
        if self._built:
            return
        from ... import guide
        self.articles = guide.build(self.app)
        self.by_id = {a.id: a for a in self.articles}
        self._built = True
        self._fill_tree()

    def on_show(self):
        self.ensure_built()
        if self.current is None:
            self.show_article("start:welcome", remember=False)
        self.q.setFocus()

    def _fill_tree(self, results=None):
        self.tree.blockSignals(True)
        self.tree.clear()
        if results is not None:
            from PySide6.QtGui import QBrush, QColor
            self.tree.setColumnCount(2)
            for a in results:
                it = QTreeWidgetItem([a.title, " › ".join(a.path[1:] or a.path)])
                it.setToolTip(0, " › ".join(a.path + [a.title]))
                it.setForeground(1, QBrush(QColor("#7a8499")))
                it.setData(0, Qt.UserRole, a.id)
                self.tree.addTopLevelItem(it)
            self.tree.resizeColumnToContents(0)
            self.tree.blockSignals(False)
            return
        self.tree.setColumnCount(1)
        nodes: dict[tuple, QTreeWidgetItem] = {}
        kids = {k for a in self.articles for k in a.children}

        def node(path):
            path = tuple(path)
            if not path:
                return None
            if path not in nodes:
                parent = node(path[:-1])
                it = QTreeWidgetItem([path[-1]])
                (parent.addChild(it) if parent else self.tree.addTopLevelItem(it))
                nodes[path] = it
            return nodes[path]
        for a in self.articles:
            if a.id.startswith("gam:cmd:"):
                continue                       # listed on their category page
            parent = node(a.path)
            if a.id in kids:
                continue                       # tabs: added under their page below
            key = tuple(a.path) + (a.title,)
            if key in nodes:
                nodes[key].setData(0, Qt.UserRole, a.id)
                it = nodes[key]
            else:
                it = QTreeWidgetItem([a.title])
                it.setData(0, Qt.UserRole, a.id)
                (parent.addChild(it) if parent else self.tree.addTopLevelItem(it))
                nodes[key] = it
            for kid in a.children:
                k = self.by_id.get(kid)
                if k:
                    c = QTreeWidgetItem([k.title])
                    c.setData(0, Qt.UserRole, k.id)
                    it.addChild(c)
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            top.setExpanded(top.text(0) in ("Getting started", "Features"))
        self.tree.blockSignals(False)

    def _search(self):
        from ... import guide
        self.ensure_built()
        q = self.q.text().strip()
        if not q:
            self._fill_tree()
            self.count.setText("")
            return
        res = guide.search(self.articles, q)
        self._fill_tree(res)
        self.count.setText(f"{len(res)} result(s)" if res else "Nothing found – try fewer "
                                                                 "words")
        if res:
            self.show_article(res[0].id, remember=False)

    # ------------------------------------------------------------- display ---
    def _picked(self, item, _prev=None):
        if item is not None and item.data(0, Qt.UserRole):
            self.show_article(item.data(0, Qt.UserRole))

    def show_article(self, aid: str, remember: bool = True):
        from ... import guide
        self.ensure_built()
        a = self.by_id.get(aid)
        if a is None:
            return
        if remember and self.current is not None and self.current.id != aid:
            self.history.append(self.current.id)
        self.current = a
        body = guide.highlight(a.body, self.q.text()) if self.q.text().strip() else a.body
        self.view.setHtml(f"<div class='crumb'>{' › '.join(a.path)}</div><h2>{a.title}</h2>"
                          + body)
        self.open_btn.setEnabled(bool(a.page))
        self.builder_btn.setEnabled(bool(a.command) or a.id.startswith("gam:"))
        self.copy_btn.setEnabled(bool(a.command))

    def show_page(self, page_name: str):
        """F1 – open the guide at a page's article."""
        self.ensure_built()
        self.q.blockSignals(True)
        self.q.clear()
        self.q.blockSignals(False)
        self._fill_tree()
        if f"page:{page_name}" in self.by_id:
            self.show_article(f"page:{page_name}")
        else:
            self.show_article("start:welcome")

    def back(self):
        if self.history:
            self.show_article(self.history.pop(), remember=False)

    def _link(self, url: QUrl):
        s = url.toString()
        if not s.startswith("gambit:"):
            QDesktopServices.openUrl(url)
            return
        kind, _, rest = s[len("gambit:"):].partition("/")
        rest = QUrl.fromPercentEncoding(rest.encode())
        if kind == "article":
            self.show_article(rest)
        elif kind == "page":
            self._goto(rest, "")
        elif kind == "tab":
            page, _, tab = rest.partition("/")
            self._goto(page, tab)
        elif kind == "builder":
            self._builder(rest)

    def _goto(self, page: str, tab: str):
        from .insight_pages import goto
        if page in getattr(self.app, "pages", {}):
            goto(self.app, page, tab)

    def _builder(self, query: str):
        if "Command Builder" in getattr(self.app, "pages", {}):
            self.app.go("Command Builder")
            self.app.pages["Command Builder"].show_query(query)

    def open_here(self):
        if self.current and self.current.page:
            self._goto(self.current.page, self.current.tab)

    def open_builder(self):
        from ... import guide
        a = self.current
        if a is None:
            return
        self._builder(guide._builder_query(a.command or a.title))

    def copy_cmd(self):
        if self.current and self.current.command:
            QApplication.clipboard().setText(self.current.command.replace("gam ", "", 1))
            self.count.setText("Copied.")

    def export(self):
        from ... import guide
        self.ensure_built()
        path, _ = QFileDialog.getSaveFileName(self, "Save the guide", "GAMbit guide.html",
                                              "Web page (*.html)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(guide.export_html(self.articles))
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


__all__ = ["GuidePage"]
