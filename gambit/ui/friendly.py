"""Friendly cell values for result tables: “2026-10-12T00:00:00Z” → “Oct 12, 2026 (16 days
ago)”, “False” → “No”. Only what you see changes – sorting, filtering, copying and exports
keep the exact value (shown on hover too). Settings & Updates → Appearance can turn it off.
"""

from __future__ import annotations

import datetime
import re
from functools import lru_cache

KEY = "ui/friendly"
ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?"
                 r"(Z|[+-]\d{2}:?\d{2})?)?$")
BOOL = {"true": "Yes", "false": "No"}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def enabled() -> bool:
    try:
        from ..settings import settings
        return bool(settings.get(KEY, True))
    except Exception:  # noqa: BLE001
        return True


def _ago(d: datetime.date, today: datetime.date) -> str:
    days = (today - d).days
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days == -1:
        return "tomorrow"
    if 0 < days < 60:
        return f"{days} days ago"
    if -60 < days < 0:
        return f"in {-days} days"
    if 0 < days < 730:
        return f"{round(days / 30)} months ago"
    if -730 < days < 0:
        return f"in {round(-days / 30)} months"
    return ""


def _date_text(d: datetime.date) -> str:
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


@lru_cache(maxsize=20000)
def _fmt(value: str, today: str) -> str:
    v = value.strip()
    low = v.lower()
    if low in BOOL:
        return BOOL[low]
    if len(v) < 10 or not v[:4].isdigit():
        return value
    m = ISO.match(v)
    if not m:
        return value
    y, mo, dd, hh, mi, ss, tz = m.groups()
    try:
        if hh is None:
            d = datetime.date(int(y), int(mo), int(dd))
            when = None
        else:
            dt = datetime.datetime(int(y), int(mo), int(dd), int(hh), int(mi), int(ss or 0))
            if (hh, mi, ss or "00") == ("00", "00", "00"):
                tz = None                       # a plain date stored at midnight UTC
            if tz:
                if tz == "Z":
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                else:
                    sign = 1 if tz[0] == "+" else -1
                    t = tz[1:].replace(":", "")
                    dt = dt.replace(tzinfo=datetime.timezone(
                        sign * datetime.timedelta(hours=int(t[:2]), minutes=int(t[2:] or 0))))
                dt = dt.astimezone()          # this PC's time zone
            d = dt.date()
            when = None if (hh, mi, ss or "00") == ("00", "00", "00") else dt
    except ValueError:
        return value
    if d.year < 1980:
        return "Never"
    ref = datetime.date.fromisoformat(today)
    text = _date_text(d)
    if when is not None:
        h = when.hour % 12 or 12
        text += f" {h}:{when.minute:02d} {'AM' if when.hour < 12 else 'PM'}"
    rel = _ago(d, ref)
    return f"{text} ({rel})" if rel else text


def friendly(value: str) -> str:
    if not value:
        return value
    return _fmt(value, datetime.date.today().isoformat())
