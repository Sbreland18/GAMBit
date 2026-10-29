"""Saved user searches that keep a Google Sheet up to date.

Users → Find / list users → pick a saved search → *Keep a Google Sheet up to date…*.
Every night (or the days you pick) the background task runs the saved search – custom
fields included – and rewrites one tab of the sheet, keeping the sheet's link, sharing and
formatting. Counselors can bookmark the sheet; nobody exports anything by hand.
"""

from __future__ import annotations

from . import tempfiles as _tf
from . import csv_safe
import datetime
import os
import tempfile

from .settings import settings

TASK = {"name": "GAMbit saved search sheets", "args": ["--task", "searchsheets"],
        "freq": "daily", "time": "05:30",
        "what": "Refreshes the Google Sheets linked to saved user searches", "standard": False}
TIME_KEY, DAYS_KEY = "searchsheets/time", "searchsheets/days"


def _favorites() -> list[dict]:
    import json
    try:
        return json.loads(settings.fresh("favorites", "[]") or "[]")
    except ValueError:
        return []


def _save(favs: list[dict]):
    import json
    settings.set("favorites", json.dumps(favs))


def linked() -> list[dict]:
    return [f for f in _favorites() if f.get("kind") == "search" and
            (f.get("sheet") or {}).get("url")]


def set_sheet(key: str, sheet: dict | None):
    favs = _favorites()
    for f in favs:
        if f.get("kind") == "search" and f["value"] == key:
            if sheet:
                f["sheet"] = {**f.get("sheet", {}), **sheet}
            else:
                f.pop("sheet", None)
    _save(favs)


def _write(url: str, tab: str, headers: list[str], rows: list[list[str]]):
    from . import google_io
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    body = [list(headers)] + [list(r) for r in rows]
    if google_io.write_tab_in_place(url, tab, body):
        return
    path = os.path.join(_tf.folder(), f"gambit-sheet-{stamp[:10]}.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv_safe.writer(fh).writerows(body)
    google_io.replace_sheet_tab(url, tab, path)


def refresh(fav: dict, run_csv=None, write=None) -> int:
    """Run one saved search into its sheet. Returns the number of people written."""
    from . import saved_searches as ss
    sheet = fav.get("sheet") or {}
    headers, rows = ss.run(ss.spec_of(fav), run_csv)
    (write or _write)(sheet["url"], sheet.get("tab") or "GAMbit", headers, rows)
    return len(rows)


def create_sheet(fav: dict, title: str = "") -> str:
    """First time: make a new sheet with the search's results; returns its link."""
    from . import google_io, saved_searches as ss
    headers, rows = ss.run(ss.spec_of(fav))
    folder = tempfile.mkdtemp(prefix="gambit_sheet_")
    path = os.path.join(folder, "GAMbit.csv")   # Google names the first tab after the file
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv_safe.writer(fh)
        w.writerow(headers)
        w.writerows(rows)
    return google_io.upload_csv_as_sheet(path, title or f"GAMbit – {fav['label']}")


def run_all(log=print, run_csv=None, write=None) -> int:
    """The background task. Returns how many sheets failed."""
    bad = 0
    items = linked()
    if not items:
        log("No saved searches are linked to a Google Sheet.")
    for f in items:
        if not f["sheet"].get("on", True):
            continue
        now = datetime.datetime.now().isoformat(timespec="minutes")
        try:
            n = refresh(f, run_csv, write)
            set_sheet(f["value"], {"last": now, "last_rows": n, "error": ""})
            log(f"“{f['label']}”: {n} people written to the sheet.")
        except Exception as exc:  # noqa: BLE001 – keep going with the other sheets
            bad += 1
            set_sheet(f["value"], {"last": now, "error": str(exc)[:300]})
            log(f"“{f['label']}” failed: {exc}")
    if bad:
        try:
            from . import alerts
            alerts.notify(f"{bad} saved search sheet(s) couldn't be refreshed – see "
                          "Users → Find / list users.", "GAMbit saved search sheets")
        except Exception:  # noqa: BLE001
            pass
    return bad


def schedule(time_hhmm: str, days: list[str]):
    from . import tasks_health
    from .ui.schedule_edit import task_for
    settings.set(TIME_KEY, time_hhmm)
    settings.set(DAYS_KEY, ",".join(days))
    tasks_health.create(task_for(TASK, time_hhmm, days))
