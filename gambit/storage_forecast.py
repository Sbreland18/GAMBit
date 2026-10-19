"""Storage forecast: once a week GAMbit adds up everyone's storage use (by school), keeps
the history, and projects when the district's pooled storage runs out. It also shows the
biggest users and how much space leavers and graduates would free."""

from __future__ import annotations

import datetime
import json
import os

from .settings import settings

REPORT_ARGS = ["report", "users", "parameters",
               "accounts:used_quota_in_mb,accounts:drive_used_quota_in_mb,"
               "accounts:gmail_used_quota_in_mb"]


def options() -> dict:
    try:
        o = json.loads(settings.get("storage/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"limit_tb": 100.0, "root": "/Students",
            "leaver_ous": "/Former Staff, /Students/Withdrawn, /Graduates", "warn_months": 12,
            **o}


def save_options(o: dict):
    settings.set("storage/options", json.dumps(o))


def _store() -> str:
    from . import team
    if team.folder():
        d = team.folder()
    else:
        from .support import logs_dir
        d = os.path.dirname(logs_dir())
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "storage_history.json")


def history() -> list[dict]:
    try:
        with open(_store(), encoding="utf-8") as fh:
            items = json.load(fh).get("weeks", [])
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for i in items if isinstance(items, list) else []:
        if isinstance(i, dict) and i.get("date") and isinstance(i.get("total_mb"),
                                                                (int, float)):
            out.append({"by_school": {}, **i})
    return out


def save_history(items: list[dict]):
    p = _store()
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump({"weeks": items[-260:]}, fh)
    os.replace(p + ".tmp", p)


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def usage(report_rows: list[dict], users: list[dict], opts: dict) -> dict:
    """→ {total_mb, by_school {name: mb}, top [..], leavers_mb, leavers}"""
    from .parent_report import school_of
    ou = {u["email"].lower(): u for u in users}
    root = opts.get("root", "/Students")
    roots = [x.strip().rstrip("/").lower() for x in opts.get("leaver_ous", "").split(",")
             if x.strip()]
    total, by, rows, leave_mb, leavers = 0.0, {}, [], 0.0, 0
    for r in report_rows:
        low = {(k or "").lower(): v for k, v in r.items()}
        e = (low.get("email") or "").lower()
        if not e:
            continue
        mb = _num(low.get("accounts:used_quota_in_mb"))
        u = ou.get(e, {})
        o = (u.get("ou") or "").rstrip("/").lower()
        if o.startswith(root.rstrip("/").lower()):
            sch = school_of(u.get("ou", ""), root)
        else:
            sch = "Staff and others"
        total += mb
        by[sch] = by.get(sch, 0.0) + mb
        is_leaver = u.get("suspended") or any(o == x or o.startswith(x + "/") for x in roots)
        if is_leaver:
            leave_mb += mb
            leavers += 1
        rows.append({"Person": e, "School": sch, "GB": round(mb / 1024, 1),
                     "Drive GB": round(_num(low.get("accounts:drive_used_quota_in_mb")) / 1024,
                                       1),
                     "Gmail GB": round(_num(low.get("accounts:gmail_used_quota_in_mb")) / 1024,
                                       1),
                     "Leaver": "yes" if is_leaver else ""})
    rows.sort(key=lambda x: -x["GB"])
    return {"total_mb": total, "by_school": by, "top": rows[:200], "leavers_mb": leave_mb,
            "leavers": leavers}


def add_week(items: list[dict], u: dict, day: datetime.date | None = None) -> list[dict]:
    day = (day or datetime.date.today()).isoformat()
    items = [i for i in items if i["date"] != day]
    items.append({"date": day, "total_mb": round(u["total_mb"]),
                  "by_school": {k: round(v) for k, v in u["by_school"].items()}})
    return sorted(items, key=lambda i: i["date"])


def _fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    """least squares → (slope, intercept)"""
    n = len(points)
    if n < 2:
        return 0.0, points[0][1] if points else 0.0
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points)
    if not sxx:
        return 0.0, my
    slope = sum((p[0] - mx) * (p[1] - my) for p in points) / sxx
    return slope, my - slope * mx


def forecast(items: list[dict], limit_tb: float, key: str = "total") -> dict:
    """→ {now_tb, per_month_tb, full_date, months_left, pct}"""
    pts = []
    for i in items[-52:]:
        d = datetime.date.fromisoformat(i["date"]).toordinal()
        v = i["total_mb"] if key == "total" else i["by_school"].get(key, 0)
        pts.append((d, v / 1024 / 1024))
    if not pts:
        return {"now_tb": 0, "per_month_tb": 0, "full_date": "", "months_left": None, "pct": 0}
    slope, icpt = _fit(pts)
    now_d, now_v = pts[-1]
    out = {"now_tb": round(now_v, 2), "per_month_tb": round(slope * 30.4, 3),
           "pct": round(100 * now_v / limit_tb, 1) if limit_tb else 0, "full_date": "",
           "months_left": None}
    if slope > 0 and limit_tb and key == "total":
        day = (limit_tb - icpt) / slope
        if day - now_d > 3650:
            out["full_date"] = "not within 10 years"
        elif day > now_d:
            out["full_date"] = datetime.date.fromordinal(int(day)).isoformat()
            out["months_left"] = round((day - now_d) / 30.4, 1)
        else:
            out["full_date"] = "already over"
            out["months_left"] = 0
    return out


def school_trend(items: list[dict]) -> list[dict]:
    if not items:
        return []
    schools = sorted(items[-1]["by_school"])
    out = []
    for s in schools:
        f = forecast(items, 0, s)
        out.append({"School": s, "Now (TB)": f["now_tb"],
                    "Growth per month (GB)": round(f["per_month_tb"] * 1024, 1)})
    return sorted(out, key=lambda x: -x["Now (TB)"])


def run(log=print, run_csv=None, users=None, force: bool = False) -> dict | None:
    """Weekly step (from the daily task): snapshot and warn if the pool fills soon."""
    from .directory import load_users, run_gam_csv
    items = history()
    if items and not force:
        last = datetime.date.fromisoformat(items[-1]["date"])
        if (datetime.date.today() - last).days < 6:
            return None
    run_csv = run_csv or (lambda a: run_gam_csv(a, 3600))
    c, rows, e = run_csv(REPORT_ARGS)
    if c != 0:
        log("Storage forecast: couldn't read the usage report – " + (e or "").strip()[-160:])
        return None
    o = options()
    u = usage(rows, users if users is not None else load_users(), o)
    items = add_week(items, u)
    save_history(items)
    f = forecast(items, float(o.get("limit_tb") or 0))
    log(f"Storage: {f['now_tb']} TB used ({f['pct']}%)" +
        (f", full around {f['full_date']}" if f["full_date"] else ""))
    if f["months_left"] is not None and f["months_left"] <= float(o.get("warn_months", 12)):
        key = f"storage/warned/{items[-1]['date'][:7]}"
        if not settings.get(key, False):
            from . import alerts
            alerts.notify(f"District storage is {f['pct']}% full ({f['now_tb']} TB of "
                          f"{o['limit_tb']} TB). At the current rate it fills around "
                          f"{f['full_date']}. Leavers hold "
                          f"{round(u['leavers_mb'] / 1024 / 1024, 2)} TB.",
                          "GAMbit storage forecast")
            settings.set(key, True)
    return f
