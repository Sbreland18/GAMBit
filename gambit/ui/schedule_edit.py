"""Pick when a background task runs: a time and the days of the week."""

from __future__ import annotations

from PySide6.QtCore import QTime
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QTimeEdit, QWidget

from .widgets import button

DAYS = [("MON", "Mon"), ("TUE", "Tue"), ("WED", "Wed"), ("THU", "Thu"), ("FRI", "Fri"),
        ("SAT", "Sat"), ("SUN", "Sun")]
WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI"]


def describe(time_hhmm: str, days: list[str]) -> str:
    """'05:45', ['MON'..'FRI'] → 'weekdays at 5:45 AM'."""
    t = QTime.fromString(time_hhmm or "05:45", "HH:mm")
    when = t.toString("h:mm AP") if t.isValid() else time_hhmm
    ds = [d for d, _l in DAYS if d in (days or [])]
    if len(ds) == 7 or not ds:
        return f"every day at {when}"
    if ds == WEEKDAYS:
        return f"weekdays at {when}"
    if ds == ["SAT", "SUN"]:
        return f"weekends at {when}"
    names = dict(DAYS)
    return f"{', '.join(names[d] for d in ds)} at {when}"


def task_for(task: dict, time_hhmm: str, days: list[str]) -> dict:
    """A tasks_health task dict with this schedule."""
    ds = [d for d, _l in DAYS if d in (days or [])]
    every = len(ds) in (0, 7)
    return {**task, "time": time_hhmm or task.get("time", "05:45"),
            "freq": "daily" if every else "weekly", "days": "" if every else ",".join(ds)}


class ScheduleEdit(QWidget):
    """[time] Mon Tue Wed Thu Fri Sat Sun  (Weekdays) (Every day)"""

    def __init__(self, time_hhmm: str = "05:45", days: list[str] | None = None, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QVBoxLayout
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(QLabel("Run at"))
        self.time = QTimeEdit()
        self.time.setDisplayFormat("h:mm AP")
        top.addWidget(self.time)
        top.addStretch(1)
        v.addLayout(top)
        h = QHBoxLayout()
        v.addLayout(h)
        h.addWidget(QLabel("On"))
        self.boxes: dict[str, QCheckBox] = {}
        for key, label in DAYS:
            cb = QCheckBox(label)
            self.boxes[key] = cb
            h.addWidget(cb)
        h.addWidget(button("Weekdays", slot=lambda: self.set_days(WEEKDAYS)))
        h.addWidget(button("Every day", slot=lambda: self.set_days([d for d, _l in DAYS])))
        h.addStretch(1)
        self.set(time_hhmm, days if days is not None else WEEKDAYS)

    def set_days(self, days: list[str]):
        for k, cb in self.boxes.items():
            cb.setChecked(k in days)

    def set(self, time_hhmm: str, days: list[str]):
        t = QTime.fromString(time_hhmm or "05:45", "HH:mm")
        self.time.setTime(t if t.isValid() else QTime(5, 45))
        self.set_days(days)

    def time_hhmm(self) -> str:
        return self.time.time().toString("HH:mm")

    def days(self) -> list[str]:
        return [k for k, cb in self.boxes.items() if cb.isChecked()]

    def text(self) -> str:
        return describe(self.time_hhmm(), self.days())
