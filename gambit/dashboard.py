"""Numbers for the Home dashboard, gathered in the background and cached for a day."""

from __future__ import annotations

import datetime
import json
import os
import time

from PySide6.QtCore import QStandardPaths

from . import profiles
from .directory import run_gam_csv


def _path() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    return os.path.join(base, f"dashboard_{profiles.slug(profiles.current_name())}.json")


def load_cached() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


HISTORY_KEYS = ("active", "suspended", "inactive", "never", "licenses", "cros_active",
                "cros_expiring", "cros_stale", "alerts", "jobs")
HISTORY_DAYS = 30


def _record(data: dict) -> list[dict]:
    """One picture per day (the latest wins), newest last, for the Home trend lines."""
    hist = [h for h in (load_cached().get("history") or []) if isinstance(h, dict)]
    day = datetime.date.fromtimestamp(data.get("time") or time.time()).isoformat()
    point = {"d": day, **{k: data[k] for k in HISTORY_KEYS
                          if isinstance(data.get(k), (int, float))}}
    hist = [h for h in hist if h.get("d") != day] + [point]
    return sorted(hist, key=lambda h: h.get("d", ""))[-HISTORY_DAYS:]


def history(key: str) -> list[float]:
    return [h[key] for h in (load_cached().get("history") or [])
            if isinstance(h, dict) and isinstance(h.get(key), (int, float))]


def save(data: dict):
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    try:
        data = {**data, "history": _record(data)}
    except Exception:  # noqa: BLE001
        pass
    with open(_path(), "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _date(text: str):
    t = (text or "").strip()
    if not t or t.lower().startswith("never"):
        return None
    try:
        if t.isdigit():
            return datetime.datetime.utcfromtimestamp(int(t) / 1000).date()
        d = datetime.date.fromisoformat(t[:10])
        return None if d.year < 1980 else d
    except ValueError:
        return None


def _col(row: dict, name: str) -> str:
    low = name.lower()
    return next((v for k, v in row.items() if (k or "").lower() == low), "") or ""


def account_stats(users: list[dict], days: int = 90) -> dict:
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=days)
    active = [u for u in users if not u.get("suspended")]
    inactive = never = 0
    for u in active:
        d = _date(u.get("last_login", ""))
        if d is None:
            never += 1
        elif d < cutoff:
            inactive += 1
    return {"accounts": len(users), "active": len(active),
            "suspended": len(users) - len(active), "inactive": inactive, "never": never,
            "has_login_data": any(u.get("last_login") for u in users)}


def gather(users: list[dict]) -> dict:
    """Runs a few read-only GAM commands. Missing pieces are simply left out."""
    data = {"time": time.time(), **account_stats(users)}
    # Chromebooks
    try:
        code, rows, _ = run_gam_csv(["print", "cros", "fields",
                                     "serialnumber,status,autoupdateexpiration,lastsync"])
        if code == 0:
            today = datetime.date.today()
            soon = today + datetime.timedelta(days=365)
            month_ago = today - datetime.timedelta(days=30)
            active = [r for r in rows if _col(r, "status").upper() == "ACTIVE"]
            aue = [_date(_col(r, "autoUpdateExpiration")) for r in active]
            sync = [_date(_col(r, "lastSync")) for r in active]
            data.update({
                "cros": len(rows), "cros_active": len(active),
                "cros_disabled": sum(_col(r, "status").upper() == "DISABLED" for r in rows),
                "cros_expired": sum(1 for d in aue if d and d < today),
                "cros_expiring": sum(1 for d in aue if d and today <= d <= soon),
                "cros_stale": sum(1 for d in sync if d and d < month_ago),
            })
    except Exception:  # noqa: BLE001
        pass
    # Licenses
    try:
        code, rows, _ = run_gam_csv(["print", "licenses", "countsonly", "allskus"])
        if code == 0 and rows:
            total, by = 0, {}
            for r in rows:
                n = next((int(v) for k, v in r.items()
                          if (v or "").isdigit() and "id" not in (k or "").lower()), 0)
                name = _col(r, "skuName") or _col(r, "sku") or _col(r, "skuId") or "license"
                by[name] = by.get(name, 0) + n
                total += n
            data.update({"licenses": total, "license_breakdown": by})
    except Exception:  # noqa: BLE001
        pass
    # Alerts in the last 7 days
    try:
        since = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        code, rows, _ = run_gam_csv(["print", "alerts", "filter", f'createTime >= "{since}"'])
        if code == 0:
            data["alerts"] = len(rows)
    except Exception:  # noqa: BLE001
        pass
    # Scheduled jobs that failed last time
    try:
        from . import scheduler
        tasks = scheduler.list_tasks()
        data["jobs"] = len(tasks)
        data["jobs_failed"] = sum(1 for t in tasks
                                  if t.get("Last result", "") not in ("", "0", "267011",
                                                                      "267009"))
    except Exception:  # noqa: BLE001
        pass
    save(data)
    return data
