"""“Leave without saving?” for forms you've started filling in, and remembering where you
were (last page, each page's tab, and a few search boxes).

Only what *you* type or pick counts as a change (not text GAMbit fills in itself), and
clicking the form's main button (Create…, Save…) marks it as done.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractSpinBox, QCheckBox, QComboBox, QLineEdit, QPlainTextEdit,
    QRadioButton, QTextEdit, QWidget,
)

from ..settings import settings


class FormTracker(QObject):
    def __init__(self, container: QWidget, label: str, save_buttons=()):
        super().__init__(container)
        self.container, self.label = container, label
        self.dirty = False
        for w in container.findChildren(QWidget):
            if isinstance(w, QLineEdit) and not w.isReadOnly() and \
                    not isinstance(w.parentWidget(), (QComboBox, QAbstractSpinBox)):
                w.textEdited.connect(self._touch)
            elif isinstance(w, QComboBox):
                w.activated.connect(self._touch)
                if w.isEditable() and w.lineEdit() is not None:
                    w.lineEdit().textEdited.connect(self._touch)
            elif isinstance(w, (QCheckBox, QRadioButton)):
                w.clicked.connect(self._touch)
            elif isinstance(w, (QPlainTextEdit, QTextEdit)):
                w.textChanged.connect(lambda w=w: w.hasFocus() and self._touch())
            elif isinstance(w, QAbstractSpinBox):
                w.editingFinished.connect(lambda w=w: w.hasFocus() and self._touch())
        for b in save_buttons:
            b.clicked.connect(self.clean)

    def _touch(self, *_a):
        self.dirty = True

    def clean(self, *_a):
        self.dirty = False

    def visible_reason(self) -> str:
        return self.label if self.dirty else ""


def track(page, container: QWidget, label: str, *save_buttons) -> FormTracker:
    t = FormTracker(container, label, save_buttons)
    page._trackers = getattr(page, "_trackers", []) + [t]
    return t


def unsaved(page) -> list[str]:
    out = []
    for t in getattr(page, "_trackers", []):
        try:
            if t.dirty:
                out.append(t.label)
        except RuntimeError:
            continue
    return out


def discard(page):
    for t in getattr(page, "_trackers", []):
        try:
            t.clean()
        except RuntimeError:
            continue


# --------------------------------------------------------------- remember ---
TABS_KEY = "remember/tabs"
LAST_PAGE_KEY = "ui/last_page"
RESTORE_KEY = "ui/restore"


def restore_on() -> bool:
    return bool(settings.get(RESTORE_KEY, True))


def _jget(key):
    import json
    try:
        d = json.loads(settings.get(key, "") or "{}")
    except ValueError:
        d = {}
    return d if isinstance(d, dict) else {}


def _jset(key, d):
    import json
    settings.set(key, json.dumps(d))


def remember_tabs(page, title: str):
    """Each tab strip on the page comes back on the tab you used last."""
    from PySide6.QtWidgets import QTabWidget
    saved = _jget(TABS_KEY)
    for n, tw in enumerate(page.findChildren(QTabWidget)):
        key = f"{title}#{n}"
        if restore_on() and key in saved and 0 <= int(saved[key]) < tw.count():
            tw.setCurrentIndex(int(saved[key]))

        def keep(i, key=key):
            d = _jget(TABS_KEY)
            d[key] = int(i)
            _jset(TABS_KEY, d)
        tw.currentChanged.connect(keep)


def remember_field(widget, key: str):
    """Keep a search box / choice between sessions (Settings → Appearance can turn it off)."""
    full = f"remember/field/{key}"
    if restore_on():
        v = settings.get(full, None)
        if v not in (None, ""):
            try:
                if isinstance(widget, QComboBox):
                    i = int(v)
                    if 0 <= i < widget.count():
                        widget.setCurrentIndex(i)
                elif hasattr(widget, "setText"):
                    widget.setText(str(v))
            except (TypeError, ValueError, RuntimeError):
                pass
    if isinstance(widget, QComboBox):
        widget.currentIndexChanged.connect(lambda i: settings.set(full, int(i)))
    elif hasattr(widget, "textChanged"):
        widget.textChanged.connect(
            lambda _t: QTimer.singleShot(0, lambda: _save_text(widget, full)))


def _save_text(widget, full):
    try:
        settings.set(full, widget.text())
    except RuntimeError:
        pass
