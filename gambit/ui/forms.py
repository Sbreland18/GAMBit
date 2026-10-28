"""Readable forms on wide screens: single-line fields stop at a comfortable width instead of
stretching across a 2,000-pixel window."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractSpinBox, QBoxLayout, QComboBox, QDateEdit, QDateTimeEdit, QLineEdit, QSpinBox,
    QTimeEdit, QWidget,
)

QT_MAX = 16777215
WIDE_PAGES = {"Command Console", "Command Builder", "Ask GAMbit", "Guide", ""}
FIELD_W, SMALL_W = 720, 260


def _scale() -> float:
    try:
        from ..settings import settings
        return max(1.0, float(settings.get("ui/text_scale", 1.0) or 1.0))
    except Exception:  # noqa: BLE001
        return 1.0


def _skip(w: QWidget, stop: QWidget) -> bool:
    from .widgets import ResultsTable
    if w.property("gb_wide"):
        return True
    p = w.parentWidget()
    if isinstance(p, (QComboBox, QAbstractSpinBox)):
        return True                         # the line edit inside a combo or spin box
    while p is not None and p is not stop:
        if isinstance(p, ResultsTable) or p.objectName() in ("BigSearch", "TopBar") or \
                p.property("gb_wide"):
            return True
        p = p.parentWidget()
    return False


def _layout_of(w: QWidget):
    par = w.parentWidget()
    if par is None or par.layout() is None:
        return None

    def find(lay):
        for i in range(lay.count()):
            it = lay.itemAt(i)
            if it.widget() is w:
                return lay
            if it.layout() is not None:
                got = find(it.layout())
                if got is not None:
                    return got
        return None
    return find(par.layout())


def _has_stretch(lay) -> bool:
    return any(lay.itemAt(i).spacerItem() is not None for i in range(lay.count()))


def cap_fields(page) -> int:
    """Cap single-line inputs on `page`. Fields in a row with buttons get a stretch after
    them so the buttons stay next to the field. Returns how many were capped."""
    if getattr(page, "title", "") in WIDE_PAGES:
        return 0
    s = _scale()
    n = 0
    for w in page.findChildren(QWidget):
        if not isinstance(w, (QLineEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit,
                              QDateTimeEdit)):
            continue
        if w.maximumWidth() != QT_MAX or _skip(w, page):
            continue
        small = isinstance(w, (QSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit))
        w.setMaximumWidth(int((SMALL_W if small else FIELD_W) * s))
        n += 1
        lay = _layout_of(w)
        if isinstance(lay, QBoxLayout) and lay.direction() in (QBoxLayout.LeftToRight,
                                                               QBoxLayout.RightToLeft) \
                and not _has_stretch(lay):
            if lay.stretch(lay.indexOf(w)) == 0:
                lay.setStretchFactor(w, 1)          # grows up to its cap…
            lay.addStretch(1)                       # …then the row stops there
    return n
