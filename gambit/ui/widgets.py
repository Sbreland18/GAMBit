"""Reusable widgets: background worker, CSV results table, page base class."""

from __future__ import annotations

import csv
import io
import traceback
import weakref
from typing import Callable

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QObject, QSortFilterProxyModel, Qt, QThread, QTimer,
    Signal, Slot,
)
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableView, QVBoxLayout,
    QWidget, QAbstractItemView, QHeaderView,
)


_DANGER = weakref.WeakSet()


class ElideLabel(QLabel):
    """A one-line label that never makes its window wider: long text ends in “…” and the
    whole text is in the tooltip."""

    def __init__(self, text: str = "", parent=None, **kw):
        super().__init__("", parent, **kw)
        self._full = ""
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)
        self.setText(text)

    def setText(self, text: str):
        self._full = text or ""
        self.setToolTip(self._full if len(self._full) > 60 else "")
        self._elide()

    def text(self) -> str:
        return self._full

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def _elide(self):
        w = max(10, self.width() - 4)
        super().setText(self.fontMetrics().elidedText(self._full.replace("\n", " "),
                                                      Qt.ElideRight, w))

    def minimumSizeHint(self):
        h = super().minimumSizeHint()
        h.setWidth(40)
        return h

    def sizeHint(self):
        h = super().sizeHint()
        h.setWidth(min(h.width(), 400))
        return h


def wrap_log(edit):
    """Long GAM lines (field lists, IDs) wrap inside the box instead of running off it."""
    from PySide6.QtGui import QTextOption
    edit.setLineWrapMode(edit.LineWrapMode.WidgetWidth)
    edit.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)


def button(text: str, kind: str = "", slot: Callable = None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    b.setCursor(Qt.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    if kind == "danger":
        _DANGER.add(b)
        from ..gam_runner import helpdesk_on
        if helpdesk_on():
            QTimer.singleShot(0, lambda: _hide_if_risky(b))
    return b


def _hide_if_risky(b):
    try:
        if not b.property("helpdesk_ok"):
            b.setVisible(False)
    except RuntimeError:
        pass


def apply_helpdesk(on: bool):
    """Hide (or show again) every destructive button in the app."""
    for b in list(_DANGER):
        try:
            if not b.property("helpdesk_ok"):
                b.setVisible(not on)
        except RuntimeError:
            pass


# ----------------------------------------------------------- worker -------
class _Job(QObject):
    progress = Signal(int, int)
    message = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, args, kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs

    def run(self):
        try:
            self.done.emit(self.fn(*self.args, **self.kwargs))
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.failed.emit(str(exc))


class _Relay(QObject):
    """Lives in the GUI thread so callbacks always run there (safe for widgets)."""

    def __init__(self, worker):
        super().__init__()
        self.w = worker

    @Slot(object)
    def done(self, result):
        if self.w.on_done:
            self.w.on_done(result)

    @Slot(str)
    def failed(self, err):
        if self.w.on_error:
            self.w.on_error(err)

    @Slot(int, int)
    def progress(self, d, t):
        if self.w.on_progress:
            self.w.on_progress(d, t)

    @Slot(str)
    def message(self, m):
        if self.w.on_message:
            self.w.on_message(m)


def build_failed(layout, widget, exc):
    """Show a short note where a page or tab couldn't be built (bad saved data, …)."""
    import logging
    logging.getLogger("gambit").exception("Couldn't build %s", type(widget).__name__)
    lab = QLabel(f"This part of GAMbit couldn't open: {exc}\n\nThe details are in the "
                 "GAMbit log (Diagnostics → Report a problem). Other pages still work.")
    lab.setWordWrap(True)
    lab.setStyleSheet("color:#b42318;")
    layout.addWidget(lab)


class Worker:
    """Run a plain Python function on a background thread.

    If the function accepts `progress` / `log` keyword arguments, pass
    use_progress=True / use_log=True and they will be wired to signals.
    Callbacks are always delivered on the GUI thread.
    """

    _alive: set = set()

    def __init__(self, fn, *args, on_done=None, on_error=None,
                 on_progress=None, on_message=None,
                 use_progress=False, use_log=False, **kwargs):
        self.on_done, self.on_error = on_done, on_error
        self.on_progress, self.on_message = on_progress, on_message
        self.thread = QThread()
        self.job = _Job(fn, args, kwargs)
        if use_progress:
            kwargs["progress"] = self.job.progress.emit
        if use_log:
            kwargs["log"] = lambda m: self.job.message.emit(str(m))
        self.relay = _Relay(self)
        self.job.moveToThread(self.thread)
        self.thread.started.connect(self.job.run)
        self.job.done.connect(self.relay.done)
        self.job.failed.connect(self.relay.failed)
        self.job.progress.connect(self.relay.progress)
        self.job.message.connect(self.relay.message)
        self.job.done.connect(self.thread.quit)
        self.job.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup)
        Worker._alive.add(self)
        self.thread.start()

    def _cleanup(self):
        Worker._alive.discard(self)


# ------------------------------------------------------ results table -----
class _RowsModel(QAbstractTableModel):
    """Plain list-of-lists model – fast with 100,000+ rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers: list[str] = []
        self.rows: list[list[str]] = []
        self.lower: list[str] = []          # one lowercase string per row, for filtering

    def reset(self, headers, rows):
        self.beginResetModel()
        self.headers = list(headers)
        n = len(self.headers)
        self.rows = [list(r[:n]) + [""] * (n - len(r)) for r in rows]
        self.lower = ["\x1f".join(r).lower() for r in self.rows]
        # columns where every non-empty value is a number sort numerically
        self.numeric = []
        for c in range(n):
            ok, seen = True, False
            for r in self.rows:
                v = r[c]
                if v == "":
                    continue
                seen = True
                try:
                    float(v.replace(",", ""))
                except ValueError:
                    ok = False
                    break
            self.numeric.append(ok and seen)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.DisplayRole, Qt.ToolTipRole, Qt.EditRole):
            v = self.rows[index.row()][index.column()]
            if role == Qt.ToolTipRole and len(v) < 40:
                return None
            return v
        return None

    def sort(self, column, order=Qt.AscendingOrder):
        """Sort in Python (one key per row) – much faster than per-comparison callbacks."""
        if column < 0 or column >= len(self.headers):
            return
        self.layoutAboutToBeChanged.emit()
        if self.numeric[column]:
            def key(i):
                v = self.rows[i][column]
                try:
                    return float(v.replace(",", "")) if v else float("-inf")
                except ValueError:
                    return float("-inf")
        else:
            def key(i):
                return self.rows[i][column].lower()
        order_idx = sorted(range(len(self.rows)), key=key,
                           reverse=(order == Qt.DescendingOrder))
        self.rows = [self.rows[i] for i in order_idx]
        self.lower = [self.lower[i] for i in order_idx]
        self.layoutChanged.emit()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal and section < len(self.headers):
                return self.headers[section]
            if orientation == Qt.Vertical:
                return str(section + 1)
        return None


class _RowsProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""

    def set_text(self, text: str):
        self.refilter(lambda: setattr(self, "text", text.lower().strip()))

    def refilter(self, change=None):
        """Re-run the filter (Qt 6.10+ prefers begin/endFilterChange)."""
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            if change:
                change()
            self.endFilterChange()
        else:
            if change:
                change()
            self.invalidateFilter()

    def filterAcceptsRow(self, row, _parent):
        return not self.text or self.text in self.sourceModel().lower[row]



class ResultsTable(QWidget):
    """Shows CSV output from `gam print …` with search, sort and export.

    Model/view based, so tens of thousands of rows stay quick.
    """

    row_clicked = Signal(dict)   # emitted when the user picks a row

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[list[str]] = []
        self._headers: list[str] = []

        self.filter = QLineEdit(placeholderText="Filter results…")
        self._filter_timer = QTimer(self, singleShot=True, interval=180,
                                    timeout=lambda: self._apply_filter(self.filter.text()))
        self.filter.textChanged.connect(lambda _t: self._filter_timer.start())
        self.count = QLabel("", objectName="Muted")
        export = button("Export CSV…", slot=self.export)
        self.sheet_btn = button("Google Sheet", slot=self.to_sheet)
        self.sheet_btn.setToolTip("Open these results as a new Google Sheet")
        self.sheet_btn.setProperty("helpdesk_ok", True)

        top = QHBoxLayout()
        top.addWidget(self.filter, 1)
        top.addWidget(self.count)
        top.addWidget(export)
        top.addWidget(self.sheet_btn)

        self.model = _RowsModel(self)
        self.proxy = _RowsProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # sorting is done by the model (fast); the header just shows the arrow
        hdr = self.table.horizontalHeader()
        hdr.setSectionsClickable(True)
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(-1, Qt.AscendingOrder)
        hdr.sectionClicked.connect(self._sort_clicked)
        self._sort = (-1, Qt.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        hh.setResizeContentsPrecision(200)     # size columns from the first 200 rows only
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.clicked.connect(lambda idx: self.row_clicked.emit(self.row_dict(idx.row())))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top)
        lay.addWidget(self.table)

    # ---- data ----
    def load_csv_many(self, texts: list[str], keep=None):
        """Merge several CSV outputs (e.g. one per OU) into one table."""
        headers: list[str] = []
        rows: list[dict] = []
        seen = set()
        for text in texts:
            for r in csv.DictReader(io.StringIO((text or "").strip())):
                for h in r:
                    if h and h not in headers:
                        headers.append(h)
                key = tuple(sorted(r.items(), key=lambda kv: str(kv[0])))
                if keep and not keep(r):
                    continue
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
        self.set_rows(headers, [[r.get(h, "") or "" for h in headers] for r in rows])

    def load_csv(self, text: str):
        rows = list(csv.reader(io.StringIO((text or "").strip())))
        rows = [r for r in rows if r]
        if not rows:
            self.set_rows([], [])
            return
        self.set_rows(rows[0], rows[1:])

    hidden_columns: set = set()

    def set_rows(self, headers: list[str], rows: list[list[str]]):
        self._headers = list(headers)
        self.table.setUpdatesEnabled(False)
        try:
            self.model.reset(headers, [[str(v) if v is not None else "" for v in r]
                                       for r in rows])
            self._rows = self.model.rows
            self._sort = (-1, Qt.AscendingOrder)
            self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
            self.table.resizeColumnsToContents()
            for c in range(self.model.columnCount()):
                if self.table.columnWidth(c) > 320:
                    self.table.setColumnWidth(c, 320)
                self.table.setColumnHidden(c, headers[c].lower() in {h.lower() for h in self.hidden_columns})
        finally:
            self.table.setUpdatesEnabled(True)
        self._apply_filter(self.filter.text())

    def _sort_clicked(self, col: int):
        order = Qt.DescendingOrder if self._sort == (col, Qt.AscendingOrder) \
            else Qt.AscendingOrder
        self.sort_by(col, order)

    def sort_by(self, col: int, order=Qt.AscendingOrder):
        self._sort = (col, order)
        self.table.horizontalHeader().setSortIndicator(col, order)
        self.model.sort(col, order)
        self._rows = self.model.rows
        self.proxy.refilter()

    def row_count(self) -> int:
        """Rows currently shown (after the filter)."""
        return self.proxy.rowCount()

    def _source_row(self, view_row: int) -> int:
        return self.proxy.mapToSource(self.proxy.index(view_row, 0)).row()

    def row_dict(self, row: int) -> dict:
        src = self._source_row(row)
        if src < 0 or src >= len(self.model.rows):
            return {}
        return dict(zip(self._headers, self.model.rows[src]))

    def _selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectionModel().selectedRows()} |
                      {i.row() for i in self.table.selectedIndexes()})

    def selected_dicts(self) -> list[dict]:
        return [self.row_dict(r) for r in self._selected_rows()]

    def selected_values(self, column_name: str) -> list[str]:
        if column_name not in self._headers:
            return []
        return [d.get(column_name, "") for d in self.selected_dicts() if d.get(column_name)]

    def visible_rows(self) -> list[list[str]]:
        return [self.model.rows[self._source_row(r)] for r in range(self.proxy.rowCount())]

    def select_row(self, row: int, add: bool = False):
        if not add:
            self.table.selectRow(row)
            return
        from PySide6.QtCore import QItemSelectionModel
        idx = self.proxy.index(row, 0)
        self.table.selectionModel().select(
            idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def _apply_filter(self, text: str):
        self.proxy.set_text(text)
        shown, total = self.proxy.rowCount(), self.model.rowCount()
        self.count.setText(f"{shown:,} of {total:,} rows" if text.strip() else f"{total:,} rows")

    # ---- context menu ----
    def _menu(self, pos):
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QApplication, QMenu
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        if idx.row() not in self._selected_rows():
            self.table.clearSelection()
            self.table.selectRow(idx.row())
        rows = self.selected_dicts()
        menu = QMenu(self)
        app = self.window()
        if hasattr(app, "context_actions"):
            for label, fn, _risky in app.context_actions(rows):
                if label == "-":
                    menu.addSeparator()
                    continue
                act = QAction(label, menu)
                act.triggered.connect(fn)
                menu.addAction(act)
            if not menu.isEmpty():
                menu.addSeparator()
        cell = idx.data() or ""
        menu.addAction("Copy this cell", lambda: QApplication.clipboard().setText(cell))
        menu.addAction("Copy selected rows", lambda: QApplication.clipboard().setText(
            "\n".join("\t".join(r) for r in [self._headers] +
                      [list(d.values()) for d in rows])))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ---- export ----
    def export(self):
        if not self._headers:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "results.csv",
                                              "CSV files (*.csv)")
        if path:
            self._write_csv(path)

    def _title(self) -> str:
        w = self.parentWidget()
        while w is not None:
            if isinstance(w, Page) and w.title:
                return w.title
            w = w.parentWidget()
        return "Results"

    def to_sheet(self):
        """Upload the visible rows as a new Google Sheet and open it."""
        import datetime
        import os
        import tempfile
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from .. import google_io
        if not self._headers:
            return
        folder = os.path.join(tempfile.gettempdir(), "GAMbit")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "to-sheet.csv")
        self._write_csv(path)
        title = f"GAMbit – {self._title()} – {datetime.datetime.now():%Y-%m-%d %H:%M}"
        self.sheet_btn.setEnabled(False)
        self.sheet_btn.setText("Uploading…")

        def done(link):
            self.sheet_btn.setEnabled(True)
            self.sheet_btn.setText("Google Sheet")
            if link:
                QDesktopServices.openUrl(QUrl(link))
            win = self.window()
            if hasattr(win, "log_line"):
                win.log_line(f"Created Google Sheet “{title}”: {link}", "#7ee787")

        def failed(e):
            self.sheet_btn.setEnabled(True)
            self.sheet_btn.setText("Google Sheet")
            QMessageBox.warning(self, "Google Sheet", str(e))
        Worker(google_io.upload_csv_as_sheet, path, title, on_done=done, on_error=failed)

    def _write_csv(self, path):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(self._headers)
            w.writerows(self.visible_rows())


# ------------------------------------------------------------ page base ---
class Page(QWidget):
    """Base class for each screen. `app` is the MainWindow."""

    title = ""
    subtitle = ""

    def __init__(self, app):
        super().__init__()
        self.setObjectName("Page")
        self.app = app
        self.runner = app.runner
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 12)
        outer.setSpacing(8)
        outer.addWidget(QLabel(self.title, objectName="PageTitle"))
        if self.subtitle:
            sub = QLabel(self.subtitle, objectName="PageSub")
            sub.setWordWrap(True)
            outer.addWidget(sub)
        self.help_strip = None
        from .page_help import for_page
        self._help = for_page(self.title)
        if self._help:
            self.help_strip = QLabel(objectName="HelpStrip")
            self.help_strip.setWordWrap(True)
            self.help_strip.setTextFormat(Qt.RichText)
            self.help_strip.setStyleSheet(
                "QLabel#HelpStrip{background:#eef5ff;border:1px solid #cfe0f7;"
                "border-radius:6px;padding:6px 10px;color:#1f3b5c;}")
            self.help_strip.linkActivated.connect(self._help_link)
            outer.addWidget(self.help_strip)
            self.refresh_help()
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body, 1)
        try:
            self.build()
        except Exception as exc:  # noqa: BLE001 – one broken page mustn't stop GAMbit
            build_failed(self.body, self, exc)

    def build(self):  # override
        pass

    # ------------------------------------------------------- page help ---
    def refresh_help(self):
        if not self.help_strip:
            return
        from ..settings import settings
        if not settings.get("ui/page_help", True):
            self.help_strip.hide()
            return
        text, safe = self._help
        links = []
        if safe:
            if settings.get("safety/dry_run", False):
                links.append("<b>🧪 Dry run is on</b> – nothing here will change in Google. "
                             "<a href='real'>Turn it off</a>")
            else:
                links.append("<a href='safe'>Try it safely</a> (turns on dry run)")
        if getattr(self, "title", "") != "Guide":
            links.append("<a href='guide'>How to use this page</a>")
        links.append("<a href='hide'>Hide tips</a>")
        self.help_strip.setText(f"💡 {text}&nbsp;&nbsp; " + " &nbsp;·&nbsp; ".join(links))
        self.help_strip.show()

    def _help_link(self, href: str):
        from ..settings import settings
        if href == "safe":
            self.app.set_dry_run(True)
        elif href == "real":
            self.app.set_dry_run(False)
        elif href == "guide" and hasattr(self.app, "open_guide"):
            name = next((n for n, p in self.app.pages.items() if p is self), "")
            self.app.open_guide(name)
        elif href == "hide":
            settings.set("ui/page_help", False)
            for p in self.app.pages.values():
                p.refresh_help()
            self.app.statusBar().showMessage(
                "Tips hidden – turn them back on in Settings & Updates.", 6000)

    def on_show(self):  # override: called when the page becomes visible
        pass

    # helpers
    def run(self, args, on_done=None, quiet=False):
        return self.runner.run([str(a) for a in args], on_done, quiet)

    def run_many(self, arg_lists, on_done, quiet=True, with_codes=False):
        """Run several gam commands one after another.

        on_done(list of stdout) – or on_done(codes, outs) when with_codes=True.
        """
        outs: list[str] = []
        codes: list[int] = []
        pending = [list(map(str, a)) for a in arg_lists]

        def nxt(code=0, out="", _err=""):
            if nxt.started:
                outs.append(out if code == 0 else "")
                codes.append(code)
            if not pending:
                on_done(codes, outs) if with_codes else on_done(outs)
                return
            nxt.started = True
            if not self.runner.run(pending.pop(0), nxt, quiet):
                pending.clear()
                on_done(codes + [-1], outs + [""]) if with_codes else on_done(outs)
        nxt.started = False
        nxt()

    @property
    def directory(self):
        return self.app.directory

    def confirm(self, text: str, title="Please confirm") -> bool:
        return QMessageBox.question(self, title, text,
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes

    def need(self, *fields: tuple[str, QLineEdit]) -> bool:
        for label, edit in fields:
            if not edit.text().strip():
                QMessageBox.information(self, "Missing information",
                                        f"Please enter {label}.")
                edit.setFocus()
                return False
        return True

    def info(self, text: str, title="GAMbit"):
        QMessageBox.information(self, title, text)

    @staticmethod
    def group(title: str) -> tuple[QGroupBox, QFormLayout]:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        return box, form

    @staticmethod
    def row(*widgets, stretch=True) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(8)
        for w in widgets:
            h.addWidget(w)
        if stretch:
            h.addStretch(1)
        return h


def classlink_button(field, after=None, parent=None):
    """“From <your SIS>” button: downloads the roster live (ClassLink, Clever, PowerSchool,
    Infinite Campus, Skyward, …) as a OneRoster zip and puts its path in field."""
    from ..integrations import sis_api
    label = f"From {sis_api.provider_name()}" if sis_api.provider() else "From your SIS"

    def go():
        if not sis_api.configured():
            QMessageBox.information(parent or field, "Live roster",
                                    "Set up your SIS connection in Settings → Integrations "
                                    "first.")
            return
        btn.setEnabled(False)
        btn.setText("Downloading…")

        def done(path):
            btn.setEnabled(True)
            btn.setText(label)
            field.setText(path)
            if after:
                after()

        def fail(e):
            btn.setEnabled(True)
            btn.setText(label)
            QMessageBox.warning(parent or field, "Live roster", str(e))
        Worker(sis_api.download, on_done=done, on_error=fail)
    btn = button(label, slot=go)
    btn.setToolTip("Download the roster live from your SIS (Settings → Integrations)")
    return btn
