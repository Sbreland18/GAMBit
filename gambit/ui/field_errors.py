"""Problems shown on the field itself: a red outline and a short line of text just under
the box (“Enter an email address like name@school.org”), instead of a pop-up. The note goes
away as soon as you change the field.

`ready_when(button, *fields, check=None)` keeps a form's main button greyed out until the
required fields are filled in (and `check()` passes)."""

from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QWidget

EMAIL_RE = re.compile(r"^[\w.+'-]+@[\w-]+(\.[\w-]+)+$")


def _target(w: QWidget) -> QWidget:
    """The box to outline (OUField → its combo, PeoplePicker → its search box)."""
    for name in ("combo", "search", "edit", "line"):
        inner = getattr(w, name, None)
        if isinstance(inner, (QLineEdit, QComboBox)):
            return inner
    return w


def _text(w) -> str:
    for name in ("text", "path", "currentText"):
        f = getattr(w, name, None)
        if callable(f):
            try:
                return str(f() or "")
            except TypeError:
                continue
    return ""


class _Note(QLabel):
    def __init__(self, field: QWidget, text: str):
        top = field.window()
        super().__init__(top, objectName="FieldError")
        self.field = field
        self.setText(text)
        self.setWordWrap(False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.adjustSize()
        self.place()
        self.show()
        self.raise_()

    def place(self):
        f = self.field
        try:
            if not f.isVisible():
                self.hide()
                return
            p = f.mapTo(self.parentWidget(), f.rect().bottomLeft())
            self.move(p.x() + 2, p.y() + 2)
            self.show()
            self.raise_()
        except RuntimeError:
            self.hide()


class _Watcher(QObject):
    """Clears the note when the field changes; keeps it under the field when things move."""

    def __init__(self, field, note):
        super().__init__(field)
        self.field, self.note = field, note
        for sig in ("textChanged", "currentTextChanged", "editTextChanged"):
            s = getattr(field, sig, None)
            if s is not None:
                try:
                    s.connect(self.clear)
                except (TypeError, RuntimeError):
                    pass
        field.installEventFilter(self)
        self.timer = QTimer(self, interval=400, timeout=note.place)
        self.timer.start()

    def eventFilter(self, _o, e):
        if e.type() in (QEvent.Move, QEvent.Resize, QEvent.Hide, QEvent.Show):
            QTimer.singleShot(0, self.note.place)
        return False

    def clear(self, *_a):
        clear(self.field)


def _form_slot(widget: QWidget):
    """(form layout, row) when the field sits in a QFormLayout row (directly or inside a
    row's own layout), else (None, -1)."""
    from PySide6.QtWidgets import QFormLayout
    w = widget
    while w is not None and w.parentWidget() is not None:
        lay = w.parentWidget().layout()
        if isinstance(lay, QFormLayout):
            row, _role = lay.getWidgetPosition(w)
            if row >= 0:
                return lay, row
            for r in range(lay.rowCount()):
                it = lay.itemAt(r, QFormLayout.FieldRole)
                if it is not None and it.layout() is not None and _in_layout(it.layout(), w):
                    return lay, r
        w = w.parentWidget()
        if w is not None and w.objectName() == "Page":
            break
    return None, -1


def _in_layout(lay, w) -> bool:
    for i in range(lay.count()):
        it = lay.itemAt(i)
        if it.widget() is w:
            return True
        if it.layout() is not None and _in_layout(it.layout(), w):
            return True
    return False


class _RowNote(QLabel):
    """The note as a real row under the field in a form (pushes the next row down)."""

    def __init__(self, form, row, text):
        super().__init__(text, objectName="FieldErrorRow")
        self.form = form
        form.insertRow(row + 1, "", self)

    def place(self):
        pass

    def remove(self):
        try:
            self.form.removeRow(self)
        except RuntimeError:
            pass


def show_error(widget: QWidget, text: str):
    f = _target(widget)
    clear(f)
    f.setProperty("invalid", True)
    f.style().unpolish(f)
    f.style().polish(f)
    form, row = _form_slot(widget)
    note = _RowNote(form, row, text) if form is not None else _Note(f, text)
    f._gb_err = (note, _Watcher(f, note))
    return note


def clear(widget: QWidget):
    f = _target(widget)
    err = getattr(f, "_gb_err", None)
    if err:
        note, watcher = err
        try:
            watcher.timer.stop()
            if isinstance(note, _RowNote):
                note.remove()                 # removeRow deletes the label too
            else:
                note.hide()
                note.deleteLater()
            watcher.deleteLater()
        except RuntimeError:
            pass
        f._gb_err = None
    if f.property("invalid"):
        f.setProperty("invalid", False)
        f.style().unpolish(f)
        f.style().polish(f)


def clear_all(root: QWidget):
    for w in root.findChildren(QWidget):
        if getattr(w, "_gb_err", None):
            clear(w)


def check_fields(fields, emails=()) -> bool:
    """fields: (label, widget) pairs that must be filled; emails: widgets that must hold an
    email address. Marks every problem; focuses the first. True when all is well."""
    first = None
    for label, w in fields:
        if not _text(w).strip():
            show_error(w, f"Enter {label}")
            first = first or w
    for w in emails:
        v = _text(w).strip()
        if v and not EMAIL_RE.match(v):
            show_error(w, "Enter an email address like name@school.org")
            first = first or w
    if first is not None:
        try:
            _target(first).setFocus()
        except RuntimeError:
            pass
        return False
    return True


def ready_when(button, *fields, check=None):
    """Grey out `button` until every field has text (and check() is true)."""
    def update(*_a):
        ok = all(_text(w).strip() for w in fields) and (check() if check else True)
        button.setEnabled(bool(ok))
        button.setToolTip("" if ok else "Fill in the required fields first")
    for w in fields:
        t = _target(w)
        for sig in ("textChanged", "currentTextChanged", "editTextChanged"):
            s = getattr(t, sig, None)
            if s is not None:
                try:
                    s.connect(update)
                except (TypeError, RuntimeError):
                    pass
    update()
    return update
