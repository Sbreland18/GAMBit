"""Reusable widgets: background worker, CSV results table, page base class."""

from __future__ import annotations

from .. import tempfiles as _tf
import re

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
    QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QStyledItemDelegate, QTableView, QVBoxLayout,
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
    ic = None
    try:
        from .icons import split_emoji
        ic, text = split_emoji(text)
    except Exception:  # noqa: BLE001
        pass
    b = QPushButton(text)
    if ic:
        from .icons import set_icon
        set_icon(b, ic, "#FFFFFF" if kind == "primary" else None)
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
        try:
            if self.w.on_done:
                self.w.on_done(result)
        finally:
            self.w._end_busy()

    @Slot(str)
    def failed(self, err):
        try:
            if self.w.on_error:
                self.w.on_error(err)
        finally:
            self.w._end_busy()

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
        try:
            from .table_states import hub
            self._busy = hub().begin()
        except Exception:  # noqa: BLE001
            self._busy = False
        self.thread.start()

    def _end_busy(self):
        if getattr(self, "_busy", False):
            self._busy = False
            from .table_states import hub
            hub().end()

    def _cleanup(self):
        Worker._alive.discard(self)


from .friendly import friendly  # noqa: E402


# ------------------------------------------------------ results table -----
class _RowsModel(QAbstractTableModel):
    """Plain list-of-lists model – fast with 100,000+ rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers: list[str] = []
        self.rows: list[list[str]] = []
        self.lower: list[str] = []          # one lowercase string per row, for filtering
        from .friendly import enabled
        self.friendly = enabled()

    def reset(self, headers, rows):
        self.beginResetModel()
        self.headers = list(headers)
        n = len(self.headers)
        self.rows = [list(r[:n]) + [""] * (n - len(r)) for r in rows]
        from .friendly import enabled, friendly as _f
        self.friendly = enabled()
        if self.friendly:   # the filter matches what you see too ("Oct", "Yes", "days ago")
            self.lower = ["\x1f".join(r + [_f(v) for v in r if v and (
                v[:1].isdigit() or v.lower() in ("true", "false"))]).lower()
                for r in self.rows]
        else:
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
        if role in (Qt.DisplayRole, Qt.ToolTipRole, Qt.EditRole, Qt.UserRole):
            v = self.rows[index.row()][index.column()]
            if role in (Qt.EditRole, Qt.UserRole):
                return v                                  # the exact value
            shown = friendly(v) if self.friendly else v
            if role == Qt.ToolTipRole:
                return v if (shown != v or len(v) >= 40) else None
            return shown
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
        # selections and the current row follow their rows to the new positions
        new_pos = {old: new for new, old in enumerate(order_idx)}
        olds = self.persistentIndexList()
        if olds:
            self.changePersistentIndexList(
                olds, [self.index(new_pos.get(i.row(), i.row()), i.column()) for i in olds])
        self.layoutChanged.emit()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.ToolTipRole and orientation == Qt.Horizontal and \
                section < len(self.headers):
            from .glossary import explain
            h = self.headers[section]
            tip = explain(h)
            return f"{h}\n\n{tip}" if tip else h
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal and section < len(self.headers):
                return nice_header(self.headers[section])
            if orientation == Qt.Vertical:
                return str(section + 1)
        return None


def nice_header(h: str) -> str:
    """orgUnitPath → ORG UNIT PATH, name.fullName → NAME · FULL NAME (display only)."""
    import re as _re
    t = _re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", h or "")
    return t.replace(".", " · ").replace("_", " ").upper()


# ---------------------------------------------------- status pills in tables ---
STATUS_COLS = {"suspended", "status", "state", "archived", "issuspended", "isenrolledin2sv",
               "isenforcedin2sv", "enabled", "result", "outcome", "ok", "is admin",
               "isadmin", "compromisedstate", "managementstate", "encryptionstate"}
_GOOD = {"active", "done", "ok", "success", "succeeded", "approved", "provisioned",
         "compliant", "encrypted", "managed", "enabled", "on", "yes", "passed", "fixed"}
_BAD = {"failed", "fail", "error", "disabled", "rejected", "compromised", "blocked",
        "deprovisioned", "wiped", "lost", "stolen"}
_WARN = {"pending", "waiting", "queued", "warning", "never", "never signed in",
         "not_compliant", "noncompliant", "unencrypted", "unmanaged", "approval needed"}


def pill_kind(column: str, value: str) -> str:
    """'good' | 'bad' | 'warn' | 'info' | '' for a status-like cell."""
    c, v = (column or "").replace(".", "").lower(), (value or "").strip().lower()
    if not v:
        return ""
    if c in ("suspended", "issuspended", "archived"):
        return "bad" if v == "true" else "good" if v == "false" else ""
    if c in ("isenrolledin2sv", "isenforcedin2sv", "enabled", "ok"):
        return "good" if v == "true" else "warn" if v == "false" else ""
    if c in ("isadmin", "is admin"):
        return "info" if v == "true" else ""
    if v in _GOOD:
        return "good"
    if v in _BAD or v.startswith("fail"):
        return "bad"
    if v in _WARN:
        return "warn"
    return "info"


def pill_text(column: str, value: str) -> str:
    c, v = (column or "").replace(".", "").lower(), (value or "").strip()
    if c in ("suspended", "issuspended"):
        return {"true": "Suspended", "false": "Active"}.get(v.lower(), v)
    if c == "archived":
        return {"true": "Archived", "false": "No"}.get(v.lower(), v)
    if c in ("isenrolledin2sv", "isenforcedin2sv", "enabled", "ok", "isadmin"):
        return {"true": "Yes", "false": "No"}.get(v.lower(), v)
    return v[:1].upper() + v[1:].lower() if v.isupper() and len(v) > 2 else v


class StatusDelegate(QStyledItemDelegate):
    """Draws status-like cells (Suspended, ACTIVE, Failed…) as soft coloured pills."""

    COLORS = {"light": {"good": ("#DCFCE7", "#166534"), "bad": ("#FEE2E2", "#991B1B"),
                        "warn": ("#FEF3C7", "#92400E"), "info": ("#EEF2F7", "#334155")},
              "dark": {"good": ("#14351F", "#86EFAC"), "bad": ("#3B1C1C", "#FCA5A5"),
                       "warn": ("#3A2A06", "#FDE68A"), "info": ("#1F2937", "#CBD5E1")}}

    def __init__(self, column_name: str, parent=None):
        super().__init__(parent)
        self.column = column_name

    def paint(self, painter, option, index):
        value = index.data(Qt.UserRole) or ""
        kind = pill_kind(self.column, value)
        if not kind:
            return super().paint(painter, option, index)
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QFontMetrics
        from PySide6.QtWidgets import QStyle
        from .theme import is_dark
        style = option.widget.style() if option.widget else None
        if style is not None:      # selection / hover background, no text
            opt = type(option)(option)
            opt.text = ""
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, option.widget)
        bg, fg = self.COLORS["dark" if is_dark() else "light"][kind]
        text = pill_text(self.column, value)
        f = option.font
        f.setPointSizeF(max(7.5, f.pointSizeF() * 0.88))
        f.setBold(True)
        fm = QFontMetrics(f)
        w = min(option.rect.width() - 12, fm.horizontalAdvance(text) + 20)
        h = min(option.rect.height() - 8, fm.height() + 6)
        r = QRectF(option.rect.x() + 8, option.rect.center().y() - h / 2 + 0.5, w, h)
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(r, h / 2, h / 2)
        painter.setPen(QColor(fg))
        painter.setFont(f)
        painter.drawText(r, Qt.AlignCenter, fm.elidedText(text, Qt.ElideRight, int(w - 10)))
        painter.restore()


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

        from PySide6.QtWidgets import QMenu, QToolButton
        self.view_btn = QToolButton(objectName="ViewBtn")
        self.view_btn.setToolTip("Table view: compact or comfortable rows, choose columns")
        self.view_btn.setPopupMode(QToolButton.InstantPopup)
        from .icons import set_icon
        set_icon(self.view_btn, "list")
        self.view_menu = QMenu(self.view_btn)
        self.view_menu.aboutToShow.connect(self._fill_view_menu)
        self.view_btn.setMenu(self.view_menu)
        top = QHBoxLayout()
        top.addWidget(self.filter, 1)
        top.addWidget(self.count)
        top.addWidget(export)
        top.addWidget(self.sheet_btn)
        top.addWidget(self.view_btn)

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
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setMouseTracking(True)
        self.table.setWordWrap(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        hh.setResizeContentsPrecision(200)     # size columns from the first 200 rows only
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.clicked.connect(lambda idx: self.row_clicked.emit(self.row_dict(idx.row())))
        self.table.clicked.connect(self._maybe_drawer)
        self.no_drawer = False
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top)
        lay.addWidget(self.table)
        self._delegates: list = []
        self.selbar = None
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self._copy_btn = None
        # Buttons that float over a row act on that row's data: whenever the rows under them
        # change (set_rows, filter, sort – the only ways they change) they're hidden, or a
        # click would act on someone no longer shown there. Called directly rather than
        # from model signals, which also fire while a table is being destroyed.
        self.table.viewport().installEventFilter(self)
        self.table.installEventFilter(self)
        self.empty_text = None
        self.start_text = ("Nothing here yet", "Results show up here after you search.")
        from .table_states import TableStates, hub
        self.states = TableStates(self)
        hub().tables.add(self)
        QTimer.singleShot(0, self.states.refresh)
        self._apply_density()

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
        try:   # customSchemas.S.F(.0.value) columns → one tidy column per custom field
            from .. import custom_fields
            if custom_fields.has_custom(headers):
                headers, rows = custom_fields.tidy(list(headers), [list(r) for r in rows])
        except Exception:  # noqa: BLE001 – never lose results over a label
            pass
        self._headers = list(headers)
        for c in range(len(self._delegates)):     # status pills per column
            self.table.setItemDelegateForColumn(c, None)
        self._delegates = []
        for c, h in enumerate(headers):
            key = (h or "").split(".")[-1].lower()
            if key in STATUS_COLS or (h or "").lower() in STATUS_COLS:
                d = StatusDelegate(key, self.table)
                self._delegates.append(d)
                self.table.setItemDelegateForColumn(c, d)
            else:
                self._delegates.append(None)
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
        self._apply_columns()
        if headers and getattr(self, "_pending_view", None):
            self._use_view(self._pending_view)
        if headers or rows:
            self.states.loaded_once = True
        self.states.loading(False)
        self._apply_filter(self.filter.text())
        self._hide_hover()
        self._selection_changed()

    # ---- density and columns ----
    DENSITY_KEY = "ui/density"
    ROW_H = {"comfortable": 34, "compact": 26}

    @classmethod
    def density(cls) -> str:
        from ..settings import settings
        d = settings.get(cls.DENSITY_KEY, "comfortable") or "comfortable"
        return d if d in cls.ROW_H else "comfortable"

    def _apply_density(self):
        self.table.verticalHeader().setDefaultSectionSize(self.ROW_H[self.density()])

    @classmethod
    def set_density(cls, d: str):
        from ..settings import settings
        from .table_states import hub
        settings.set(cls.DENSITY_KEY, d)
        for t in list(hub().tables):
            try:
                t._apply_density()
            except RuntimeError:
                continue

    def _cols_key(self) -> str:
        import hashlib
        sig = "|".join(sorted(h.lower() for h in self._headers))
        return f"cols/{self._title()}/{hashlib.md5(sig.encode()).hexdigest()[:10]}"

    def _cols_pref(self) -> dict:
        import json
        from ..settings import settings
        try:
            d = json.loads(settings.get(self._cols_key(), "") or "{}")
        except ValueError:
            d = {}
        return d if isinstance(d, dict) else {}

    def _save_cols(self, order: list[str], hidden: list[str]):
        import json
        from ..settings import settings
        settings.set(self._cols_key(), json.dumps({"order": order, "hidden": hidden}))

    def _apply_columns(self):
        if not self._headers:
            return
        pref = self._cols_pref()
        hh = self.table.horizontalHeader()
        hh.setSectionsMovable(True)
        # start from the natural order: a column order dragged for the last results must
        # not carry over to different columns
        hh.blockSignals(True)
        for logical in range(hh.count()):
            if hh.visualIndex(logical) != logical:
                hh.moveSection(hh.visualIndex(logical), logical)
        hh.blockSignals(False)
        hidden = {h.lower() for h in pref.get("hidden", [])}
        for c, h in enumerate(self._headers):
            if h.lower() in hidden:
                self.table.setColumnHidden(c, True)
        order = [o.lower() for o in pref.get("order", [])]
        if order:
            low = [h.lower() for h in self._headers]
            hh.blockSignals(True)
            for target, name in enumerate(o for o in order if o in low):
                logical = low.index(name)
                hh.moveSection(hh.visualIndex(logical), target)
            hh.blockSignals(False)
        if not getattr(self, "_moved_hooked", False):
            self._moved_hooked = True
            hh.sectionMoved.connect(lambda *_: self._remember_order())

    def _remember_order(self):
        hh = self.table.horizontalHeader()
        order = [self._headers[hh.logicalIndex(v)] for v in range(hh.count())
                 if hh.logicalIndex(v) < len(self._headers)]
        hidden = [h for c, h in enumerate(self._headers) if self.table.isColumnHidden(c)]
        self._save_cols(order, hidden)

    def _fill_view_menu(self):
        m = self.view_menu
        m.clear()
        d = self.density()
        for key, label in (("comfortable", "Comfortable rows"), ("compact", "Compact rows")):
            a = m.addAction(label)
            a.setCheckable(True)
            a.setChecked(d == key)
            a.triggered.connect(lambda _=False, k=key: self.set_density(k))
        m.addSeparator()
        views = self.views()
        vm = m.addMenu("Saved views")
        vm.setEnabled(bool(views))
        for v in views:
            vm.addAction(v["name"], lambda v=v: self.apply_view(v))
        m.addAction("Save this view…", self.save_view).setEnabled(bool(self._headers))
        if views:
            dm = m.addMenu("Delete a view")
            for v in views:
                dm.addAction(v["name"], lambda v=v: self.delete_view(v))
        m.addAction("Print or save as PDF…", self.print_table).setEnabled(
            self.row_count() > 0)
        m.addSeparator()
        a = m.addAction("Columns…", self.choose_columns)
        a.setEnabled(bool(self._headers))
        a = m.addAction("Reset columns", self.reset_columns)
        a.setEnabled(bool(self._cols_pref()))

    # ---- saved views (filter + columns + sort, per page) ----
    def _views_key(self) -> str:
        return f"views/{self._title()}"

    def _table_index(self) -> int:
        page = self.parentWidget()
        while page is not None and not isinstance(page, Page):
            page = page.parentWidget()
        if page is None:
            return 0
        tables = page.findChildren(ResultsTable)
        return tables.index(self) if self in tables else 0

    def views(self) -> list[dict]:
        import json
        from ..settings import settings
        try:
            v = json.loads(settings.get(self._views_key(), "[]") or "[]")
        except ValueError:
            v = []
        return [x for x in v if isinstance(x, dict) and x.get("table", 0) ==
                self._table_index()]

    def _all_views(self) -> list[dict]:
        import json
        from ..settings import settings
        try:
            v = json.loads(settings.get(self._views_key(), "[]") or "[]")
        except ValueError:
            v = []
        return [x for x in v if isinstance(x, dict)]

    def save_view(self, name: str | None = None):
        import json
        import uuid
        from PySide6.QtWidgets import QInputDialog
        from ..settings import settings
        if name is None:
            name, ok = QInputDialog.getText(self, "Save this view",
                                            "Name (e.g. “7th grade, not signed in”):")
            if not ok or not name.strip():
                return None
        hh = self.table.horizontalHeader()
        order = [self._headers[hh.logicalIndex(i)] for i in range(hh.count())
                 if hh.logicalIndex(i) < len(self._headers)]
        hidden = [h for c, h in enumerate(self._headers) if self.table.isColumnHidden(c)]
        col, ordr = self._sort
        v = {"id": uuid.uuid4().hex[:8], "name": name.strip(), "table": self._table_index(),
             # page = the sidebar page to open; scope = the (possibly nested) page that
             # owns the table – they differ for tables inside a tab of another page
             "page": self._outer_title(), "scope": self._title(),
             "filter": self.filter.text(), "order": order,
             "hidden": hidden,
             "sort": [self._headers[col] if 0 <= col < len(self._headers) else "",
                      "desc" if ordr == Qt.DescendingOrder else "asc"]}
        views = [x for x in self._all_views() if not (x.get("name") == v["name"] and
                                                       x.get("table") == v["table"])]
        settings.set(self._views_key(), json.dumps(views + [v]))
        win = self.window()
        if hasattr(win, "toasts"):
            win.toasts.show(f"Saved view “{v['name']}”", "ok", "Add to Home",
                            lambda: win.add_view_favorite(v), ms=7000, remember=False)
        return v

    def delete_view(self, v: dict):
        import json
        from ..settings import settings
        settings.set(self._views_key(), json.dumps(
            [x for x in self._all_views() if x.get("id") != v.get("id")]))

    def apply_view(self, v: dict):
        """Filter, columns and sort from a saved view (now, or when rows arrive)."""
        self._pending_view = v
        self.filter.setText(v.get("filter", ""))
        if self._headers:
            self._use_view(v)

    def _use_view(self, v: dict):
        self._pending_view = None
        low = [h.lower() for h in self._headers]
        order = [h for h in v.get("order", []) if h.lower() in low]
        hidden = [h for h in v.get("hidden", []) if h.lower() in low]
        if order or hidden:
            self._save_cols(order or list(self._headers), hidden)
            off = {h.lower() for h in hidden} | {h.lower() for h in self.hidden_columns}
            for c, h in enumerate(self._headers):
                self.table.setColumnHidden(c, h.lower() in off)   # never shows internal ones
            self._apply_columns()
        name, how = (v.get("sort") or ["", "asc"])[:2]
        if name and name.lower() in low:
            self.sort_by(low.index(name.lower()),
                         Qt.DescendingOrder if how == "desc" else Qt.AscendingOrder)
        self._apply_filter(self.filter.text())

    # ---- print / PDF ----
    def print_table(self):
        from .table_print import print_table
        print_table(self)

    def reset_columns(self):
        from ..settings import settings
        settings.set(self._cols_key(), "")
        hh = self.table.horizontalHeader()
        hh.blockSignals(True)
        for logical in range(hh.count()):
            hh.moveSection(hh.visualIndex(logical), logical)
        hh.blockSignals(False)
        low_hidden = {h.lower() for h in self.hidden_columns}
        for c, h in enumerate(self._headers):
            self.table.setColumnHidden(c, h.lower() in low_hidden)

    def choose_columns(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QListWidget, QListWidgetItem
        dlg = QDialog(self)
        dlg.setWindowTitle("Columns")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("Tick the columns to show. Drag to change the order.",
                           objectName="Muted"))
        lst = QListWidget()
        lst.setDragDropMode(QListWidget.InternalMove)
        hh = self.table.horizontalHeader()
        for vis in range(hh.count()):
            c = hh.logicalIndex(vis)
            if c >= len(self._headers):
                continue
            it = QListWidgetItem(nice_header(self._headers[c]))
            it.setData(Qt.UserRole, self._headers[c])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            it.setCheckState(Qt.Unchecked if self.table.isColumnHidden(c) else Qt.Checked)
            lst.addItem(it)
        v.addWidget(lst, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.resize(380, 480)
        if not dlg.exec():
            return
        order = [lst.item(i).data(Qt.UserRole) for i in range(lst.count())]
        hidden = [lst.item(i).data(Qt.UserRole) for i in range(lst.count())
                  if lst.item(i).checkState() != Qt.Checked]
        if len(hidden) == len(order):
            hidden = hidden[1:]                  # always keep one column
        self._save_cols(order, hidden)
        for c, h in enumerate(self._headers):
            self.table.setColumnHidden(c, h in hidden)
        self._apply_columns()

    # ---- copy on hover, Enter opens details ----
    COPY_COLS = ("email", "primaryemail", "serialnumber", "serial", "annotatedassetid",
                 "assetid", "asset", "deviceid", "id", "macaddress", "ethernetmacaddress",
                 "owner", "user", "annotateduser", "member", "group", "orgunitpath")

    def _copyable(self, idx) -> str:
        if not idx.isValid():
            return ""
        v = (idx.data(Qt.UserRole) or "").strip()
        if not v or len(v) > 120:
            return ""
        src = self.proxy.mapToSource(idx).column()
        col = (self._headers[src] if src < len(self._headers) else "").split(".")[-1].lower()
        if "@" in v or col in self.COPY_COLS:
            return v
        return ""

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        t = e.type()
        if obj is self.table.viewport():
            if t == QEvent.MouseMove:
                pos = e.position().toPoint()
                self._hover_row(pos)
                self._hover_copy(pos)
            elif t == QEvent.Leave:
                if self._copy_btn is not None and not self._copy_btn.underMouse():
                    self._copy_btn.hide()
                bar = getattr(self, "_row_bar", None)
                if bar is not None and not bar.underMouse():
                    bar.hide()
                    self._bar_row = -1
        elif obj is self.table and t == QEvent.KeyPress and \
                e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() == Qt.NoModifier:
            idx = self.table.currentIndex()
            if idx.isValid():
                win = self.window()
                row = self.row_dict(idx.row())
                mo = self.metaObject()
                handled = self.isSignalConnected(mo.method(mo.indexOfSignal(
                    "row_clicked(QVariantMap)")))
                self.row_clicked.emit(row)
                if not handled and hasattr(win, "show_details") and not self.no_drawer:
                    win.show_details(row)
                return True
        return False

    ROW_PICK = (("Open", "eye"), ("Reset password", "key"), ("Sign out of all", "login"),
                ("Re-enable", "check-circle"), ("Disable", "x-circle"))

    def _row_actions(self, row: dict):
        win = self.window()
        if not hasattr(win, "context_actions"):
            return []
        try:
            acts = [a for a in win.context_actions([row]) if a[0] != "-" and a[1]]
        except Exception:  # noqa: BLE001
            return []
        out = []
        for key, ic in self.ROW_PICK:
            a = next((a for a in acts if a[0].startswith(key)), None)
            if a is not None:
                out.append((a[0], ic, a[1]))
            if len(out) == 3:
                break
        return out

    def _hide_hover(self):
        bar = getattr(self, "_row_bar", None)
        if bar is not None:
            bar.hide()
        self._bar_row = -1
        if self._copy_btn is not None:
            self._copy_btn.hide()
            self._copy_btn.setProperty("value", "")

    def _rows_moved(self, *_):
        self._hide_hover()
        self._selection_changed()

    def _hover_row(self, pos):
        """Small buttons at the end of the row under the mouse (Open, Reset password…)."""
        if getattr(self, "no_row_actions", False):
            return
        idx = self.table.indexAt(pos)
        bar = getattr(self, "_row_bar", None)
        if not idx.isValid():
            if bar is not None:
                bar.hide()
                self._bar_row = -1
            return
        if idx.row() == getattr(self, "_bar_row", -1) and bar is not None and bar.isVisible():
            return
        self._bar_row = idx.row()
        acts = self._row_actions(self.row_dict(idx.row()))
        if not acts:
            if bar is not None:
                bar.hide()
            return
        from PySide6.QtWidgets import QToolButton
        from .icons import set_icon
        if bar is None:
            bar = QFrame(self.table.viewport(), objectName="RowActions")
            bar.setAttribute(Qt.WA_StyledBackground, True)
            QHBoxLayout(bar).setContentsMargins(4, 2, 4, 2)
            self._row_bar = bar
        lay = bar.layout()
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for label, ic, fn in acts:
            b = QToolButton(objectName="RowActionBtn")
            set_icon(b, ic, None, 16)
            short = label.rstrip("…").split(" for ")[0]
            b.setToolTip(short)
            b.setAccessibleName(short)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            lay.addWidget(b)
        vp = self.table.viewport()
        r = self.table.visualRect(idx)
        bar.adjustSize()
        h = min(r.height() - 4, 30)
        bar.setFixedHeight(h)
        bar.move(vp.width() - bar.sizeHint().width() - 8, r.top() + (r.height() - h) // 2)
        bar.show()
        bar.raise_()

    def _hover_copy(self, pos):
        idx = self.table.indexAt(pos)
        val = self._copyable(idx)
        if not val:
            if self._copy_btn is not None:
                self._copy_btn.hide()
            return
        if self._copy_btn is None:
            from PySide6.QtWidgets import QToolButton
            from .icons import set_icon
            self._copy_btn = QToolButton(self.table.viewport(), objectName="CellCopy")
            set_icon(self._copy_btn, "copy", None, 16)
            self._copy_btn.setCursor(Qt.PointingHandCursor)
            self._copy_btn.setAccessibleName("Copy")
            self._copy_btn.clicked.connect(self._do_copy)
        r = self.table.visualRect(idx)
        b = self._copy_btn
        b.setProperty("value", val)
        b.setToolTip(f"Copy {val}")
        size = min(26, r.height() - 4)
        b.setFixedSize(size, size)
        b.move(r.right() - size - 4, r.top() + (r.height() - size) // 2)
        bar = getattr(self, "_row_bar", None)
        if bar is not None and bar.isVisible() and bar.geometry().intersects(b.geometry()):
            b.move(bar.x() - size - 4, b.y())         # sit just left of the row buttons
        b.show()
        b.raise_()

    def _do_copy(self):
        from PySide6.QtWidgets import QApplication
        val = self._copy_btn.property("value") or ""
        QApplication.clipboard().setText(val)
        win = self.window()
        if hasattr(win, "toasts"):
            win.toasts.show(f"Copied {val}", "ok", ms=2500, remember=False)

    def _maybe_drawer(self, idx):
        """A plain click on a person, group or Chromebook row opens the details panel –
        unless this table's page already does something with row clicks."""
        from PySide6.QtWidgets import QApplication
        if self.no_drawer or QApplication.keyboardModifiers() != Qt.NoModifier:
            return
        mo = self.metaObject()
        sig = mo.method(mo.indexOfSignal("row_clicked(QVariantMap)"))
        if self.isSignalConnected(sig) or len(self._selected_rows()) > 1:
            return
        win = self.window()
        if hasattr(win, "show_details"):
            win.show_details(self.row_dict(idx.row()))

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
        self._rows_moved()

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
        self._hide_hover()
        self.proxy.set_text(text)
        self._selection_changed()
        shown, total = self.proxy.rowCount(), self.model.rowCount()
        self.count.setText(f"{shown:,} of {total:,} rows" if text.strip() else f"{total:,} rows")
        if hasattr(self, "states"):
            self.states.refresh()

    def set_empty_text(self, title: str, hint: str = "", before: tuple | None = None):
        """What an empty table says after a search (and, optionally, before one)."""
        self.empty_text = (title, hint)
        if before:
            self.start_text = before
        self.states.refresh()

    def set_loading(self, on: bool = True):
        self.states.loading(on)

    # ---- context menu ----
    # ---- floating selection bar ----
    SEL_PICK = ("Reset password", "Require password", "Sign out", "Unsuspend", "Suspend",
                "Re-enable", "Disable", "Add to favorites")

    def _selection_changed(self, *_):
        rows = self._selected_rows()
        app = self.window()
        if len(rows) < 2 or not hasattr(app, "context_actions"):
            if self.selbar is not None:
                self.selbar.hide()
            return
        try:
            acts = [a for a in app.context_actions(self.selected_dicts())
                    if a[0] != "-" and a[1] is not None]
        except Exception:  # noqa: BLE001
            acts = []
        acts = [a for a in acts if any(a[0].startswith(p) or p in a[0] for p in self.SEL_PICK)]
        if not acts:
            if self.selbar is not None:
                self.selbar.hide()
            return
        if self.selbar is None:
            self.selbar = QFrame(self, objectName="SelBar")
            self.selbar.setAttribute(Qt.WA_StyledBackground, True)
            QHBoxLayout(self.selbar).setContentsMargins(16, 8, 8, 8)
        lay = self.selbar.layout()
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        lay.addWidget(QLabel(f"{len(rows)} selected"))
        room = max(2, (self.width() - 220) // 170)       # how many buttons fit
        shown, more = acts[:room], acts[room:]
        for label, fn, risky in shown:
            b = QPushButton(self._short(label, len(rows)))
            b.setToolTip(label)
            if risky:
                b.setProperty("kind", "danger")
            b.clicked.connect(fn)
            lay.addWidget(b)
        if more:
            from PySide6.QtWidgets import QMenu
            mb = QPushButton("More ▾")
            m = QMenu(mb)
            for label, fn, _r in more:
                m.addAction(label, fn)
            mb.setMenu(m)
            lay.addWidget(mb)
        x = QPushButton("✕")
        x.setToolTip("Clear the selection")
        x.clicked.connect(self.table.clearSelection)
        lay.addWidget(x)
        self.selbar.adjustSize()
        self._place_selbar()
        self.selbar.show()
        self.selbar.raise_()

    SHORT = {"Require password change at next sign-in": "Require new password",
             "Sign out of all sessions": "Sign out everywhere"}

    @classmethod
    def _short(cls, label: str, n: int) -> str:
        t = label.rstrip("…").replace(f" for {n} person(s)", "").strip()
        for long_, short in cls.SHORT.items():
            if t.startswith(long_):
                return short
        return t if len(t) <= 24 else t[:22].rstrip() + "…"

    def _place_selbar(self):
        if self.selbar is None:
            return
        w = min(self.selbar.sizeHint().width(), self.width() - 24)
        self.selbar.resize(w, self.selbar.sizeHint().height())
        vis = self.visibleRegion().boundingRect()       # stay on screen in a scrolled page
        bottom = min(self.height(), vis.bottom() + 1) if not vis.isEmpty() else self.height()
        self.selbar.move(max(8, (self.width() - w) // 2),
                         max(0, bottom - self.selbar.height() - 14))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.selbar is not None and self.selbar.isVisible():
            self._place_selbar()

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
        cell = idx.data(Qt.UserRole) or ""
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

    def _outer_title(self) -> str:
        """The title of the outermost page this table is on (the one in the sidebar)."""
        found, w = "", self.parentWidget()
        while w is not None:
            if isinstance(w, Page) and w.title:
                found = w.title
            w = w.parentWidget()
        return found or "Results"

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
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from .. import google_io
        if not self._headers:
            return
        folder = _tf.folder()
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
        from .. import csv_safe
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv_safe.writer(fh)             # no formulas from Google data
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
        self.tips_link = None
        if self.title:
            trow = QHBoxLayout()
            trow.setSpacing(10)
            trow.addWidget(QLabel(self.title, objectName="PageTitle"))
            trow.addStretch(1)
            self.title_row = trow
            outer.addLayout(trow)
        if self.subtitle:
            sub = QLabel(self.subtitle, objectName="PageSub")
            sub.setWordWrap(True)
            outer.addWidget(sub)
        self.help_strip = None
        from .page_help import for_page
        self._help = for_page(self.title)
        if self._help:
            self.help_bar = QFrame(objectName="HelpBar")
            self.help_bar.setAttribute(Qt.WA_StyledBackground, True)
            hb = QHBoxLayout(self.help_bar)
            hb.setContentsMargins(12, 8, 12, 8)
            hb.setSpacing(10)
            self.help_icon = QLabel()
            self.help_icon.setStyleSheet("background:transparent;")
            hb.addWidget(self.help_icon, 0, Qt.AlignTop)
            self.help_strip = QLabel(objectName="HelpStrip")
            self.help_strip.setWordWrap(True)
            self.help_strip.setTextFormat(Qt.RichText)
            self.help_strip.linkActivated.connect(self._help_link)
            hb.addWidget(self.help_strip, 1)
            outer.addWidget(self.help_bar)
            if self.title:
                from .icons import set_icon
                self.tips_link = QPushButton(" Tips", objectName="TipsLink")
                self.tips_link.setCursor(Qt.PointingHandCursor)
                self.tips_link.setToolTip("Show the tips for this page")
                set_icon(self.tips_link, "help")
                self.tips_link.clicked.connect(self._show_tips_once)
                self.title_row.addWidget(self.tips_link, 0, Qt.AlignVCenter)
            self.refresh_help()
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body, 1)
        try:
            self.build()
        except Exception as exc:  # noqa: BLE001 – one broken page mustn't stop GAMbit
            build_failed(self.body, self, exc)
        try:
            from . import a11y, forms, glossary, tabs, unsaved
            tabs.enhance(self)
            forms.cap_fields(self)
            forms.polish_tables(self)
            a11y.name_buttons(self)
            glossary.annotate(self)
            if self.title:
                unsaved.remember_tabs(self, self.title)
        except Exception:  # noqa: BLE001 – looks only
            pass
        try:
            from . import tabs as _tabs
            _tabs.side_tabs(self)          # page tabs down the left, like Settings
        except Exception:  # noqa: BLE001 – looks only
            pass

    def build(self):  # override
        pass

    # ------------------------------------------------------- page help ---
    def refresh_help(self):
        if not self.help_strip:
            return
        from ..settings import settings
        from .icons import icon
        from .theme import tokens
        self.help_icon.setPixmap(icon("sparkle", tokens()["accent_text"], 18).pixmap(18, 18))
        shown = settings.get("ui/page_help", True) or getattr(self, "_tips_once", False)
        if self.tips_link is not None:
            self.tips_link.setVisible(not shown)
        if not shown:
            self.help_strip.hide()
            self.help_bar.hide()
            return
        self.help_bar.show()
        text, safe = self._help
        links = []
        if safe:
            if settings.get("safety/dry_run", False):
                links.append("<b>Dry run is on</b> – nothing here will change in Google. "
                             "<a href='real'>Turn it off</a>")
            else:
                links.append("<a href='safe'>Try it safely</a> (turns on dry run)")
        if getattr(self, "title", "") != "Guide":
            links.append("<a href='guide'>How to use this page</a>")
        links.append("<a href='hide'>Hide tips</a>" if not getattr(self, "_tips_once", False)
                     else "<a href='close'>Close</a>")
        self.help_strip.setText(f"{text}&nbsp;&nbsp; " + " &nbsp;·&nbsp; ".join(links))
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
        elif href == "close":
            self._tips_once = False
            self.refresh_help()
        elif href == "hide":
            settings.set("ui/page_help", False)
            for p in self.app.pages.values():
                p.refresh_help()
            self.app.statusBar().showMessage(
                "Tips hidden – turn them back on in Settings & Updates.", 6000)

    def _show_tips_once(self):
        self._tips_once = True
        self.refresh_help()

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

    def need(self, *fields: tuple[str, QLineEdit], emails=()) -> bool:
        """Required fields: each missing one gets a red outline and a note under it."""
        from .field_errors import check_fields
        return check_fields(fields, emails)

    NUDGE_RE = re.compile(r"^(choose|pick|type|enter|fill in|select|paste|please (choose|"
                          r"type|enter|pick|select))\b", re.I)

    def info(self, text: str, title="GAMbit"):
        """Messages. A short “Choose the person first.” kind of message goes on the field it's
        about (red outline + note) – or, when that isn't clear, a small pop-up – instead of
        a window you have to click away."""
        t = (text or "").strip()
        if title == "GAMbit" and len(t) < 160 and "\n" not in t and self.NUDGE_RE.match(t):
            try:
                if self._nudge(t):
                    return
            except Exception:  # noqa: BLE001 – fall back to the normal message
                pass
        QMessageBox.information(self, title, text)

    def _nudge(self, text: str) -> bool:
        from .field_errors import show_error
        target = None if text.lower().startswith(("select", "please select")) else \
            guess_field(self, text)
        if target is not None:
            show_error(target, text)
            return True
        win = self.window()
        if hasattr(win, "toasts"):
            win.toasts.show(text, "warn", ms=6000, remember=False)
            return True
        return False

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
        from PySide6.QtWidgets import QAbstractButton
        h = QHBoxLayout()
        h.setSpacing(8)
        for w in widgets:
            h.addWidget(w)
        if stretch or (widgets and all(isinstance(w, QAbstractButton) for w in widgets)):
            h.addStretch(1)            # a row of only buttons never stretches them
        return h


_SYN = {"person": ("email", "person", "name", "user", "student", "staff", "owner",
                    "teacher", "account", "who", "mailbox", "member"),
        "org": ("org", "unit", "ou", "/"), "file": ("file", "csv", "spreadsheet", "path"),
        "serial": ("serial", "asset", "chromebook", "device"),
        "group": ("group",), "domain": ("domain",), "name": ("name",)}


def _field_words(w) -> str:
    from .field_errors import _form_slot
    bits = []
    for name in ("placeholderText", "toolTip", "accessibleName"):
        f = getattr(w, name, None)
        if callable(f):
            bits.append(f() or "")
    inner = getattr(w, "combo", None)
    if inner is not None and inner.lineEdit() is not None:
        bits.append(inner.lineEdit().placeholderText())
    form, row = _form_slot(w)
    if form is not None and row >= 0:
        it = form.itemAt(row, QFormLayout.LabelRole)
        if it is not None and isinstance(it.widget(), QLabel):
            bits.append(re.sub(r"<[^>]+>", " ", it.widget().text()))
    if w.__class__.__name__ == "OUField":
        bits.append("org unit ou")
    if w.__class__.__name__ in ("PersonField", "PeoplePicker"):
        bits.append("person email name student staff")
    return " ".join(bits).lower()


GENERIC_WORDS = {"the", "first", "choose", "pick", "type", "enter", "fill", "and", "for",
                 "please", "select", "paste", "new", "one", "two", "email", "address",
                 "full", "this", "that", "who", "applies", "different"}


def guess_field(page, text: str):
    """The input on the visible part of `page` that a message like “Choose the owner
    first.” is about – or None when it isn't clear (then a small pop-up is used instead).
    It only picks a box whose label or hint shares a real word with the message, or the
    single empty box on screen."""
    from PySide6.QtWidgets import QAbstractSpinBox, QComboBox
    all_words = set(re.findall(r"[a-z]+", text.lower()))
    words = {x for x in all_words if len(x) > 2} - GENERIC_WORDS
    cands = []
    for w in page.findChildren(QWidget):
        if not w.isVisible() or not w.isEnabled():
            continue
        cls = w.__class__.__name__
        if cls == "OUField":
            cands.append((w, not w.path()))
            continue
        if not isinstance(w, QLineEdit) or w.isReadOnly():
            continue
        p = w.parentWidget()
        if isinstance(p, (QComboBox, QAbstractSpinBox)):
            continue
        skip = False
        while p is not None and p is not page:
            if isinstance(p, ResultsTable) or p.__class__.__name__ in ("OUField",
                                                                       "BigSearch"):
                skip = True
                break
            p = p.parentWidget()
        if not skip:
            cands.append((w, not w.text().strip()))
    if not cands:
        return None

    def strong(w):
        hay = _field_words(w)
        return sum(1 for x in words if re.search(rf"\b{re.escape(x)}", hay))

    def soft(w):
        hay = _field_words(w)
        return sum(1 for syn in _SYN.values()
                   if any(x in all_words for x in syn) and any(x in hay for x in syn))
    ranked = sorted(cands, key=lambda c: (strong(c[0]), c[1], soft(c[0])), reverse=True)
    top, empty = ranked[0]
    if strong(top) > 0 and (len(ranked) == 1 or
                            (strong(top), empty) > (strong(ranked[1][0]), ranked[1][1])):
        return top
    empties = [w for w, e in cands if e]
    if len(empties) == 1 and soft(empties[0]) > 0:
        return empties[0]
    return None


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
