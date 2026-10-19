"""District scorecard: one snapshot of the key numbers each week, kept so trends show on
Home and principals see “vs. last week” in their reports."""

from __future__ import annotations

import datetime
import json
import os


TASK = {"name": "GAMbit weekly scorecard", "args": ["--task", "scorecard"],
        "freq": "weekly", "time": "06:20",
        "what": "Saves this week's district numbers for the trend lines on Home",
        "standard": False}

# key, label, True when going up is good
METRICS = [
    ("mismatches", "Roster / account / device mismatches", False),
    ("inactive", "Students not signing in lately", False),
    ("never", "Students who never signed in", False),
    ("no_guardian", "Students with no guardian invited", False),
    ("to_collect", "Chromebooks to collect", False),
    ("repairs", "Chromebooks in repair", False),
    ("expired", "Chromebooks past end of updates", False),
    ("findings", "Unusual-activity findings (7 days)", False),
    ("pending", "Approvals waiting", False),
    ("licenses_free", "Licenses that could be freed", False),
    ("tsv_pct", "Staff with 2-Step Verification (%)", True),
    ("baseline_pct", "Security baseline score (%)", True),
    ("signin_days", "Days from new account to first sign-in (median)", False),
    ("leaver_days", "Days from leaving to suspended (median)", False),
    ("approval_hours", "Hours to decide an approval (median)", False),
]
LABEL = {k: lab for k, lab, _g in METRICS}


def week_key(d: datetime.date | None = None) -> str:
    y, w, _ = (d or datetime.date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def _path() -> str:
    from . import team
    if team.folder():
        d = os.path.join(team.folder(), "scorecard")
    else:
        from .support import logs_dir
        d = os.path.join(os.path.dirname(logs_dir()), "scorecard")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "scorecard.json")


def load() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"weeks": {}}


def save(data: dict):
    p = _path()
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    os.replace(p + ".tmp", p)


def record(values: dict, schools: dict | None = None, when: datetime.date | None = None):
    """Merge numbers into this week's snapshot (later values win)."""
    data = load()
    wk = data.setdefault("weeks", {}).setdefault(week_key(when), {})
    wk.update({k: v for k, v in values.items() if v is not None})
    if schools:
        wk.setdefault("schools", {}).update(schools)
    wk["updated"] = datetime.datetime.now().isoformat(timespec="minutes")
    save(data)
    return wk


def school_numbers(stats: dict) -> dict:
    """school_reports stats → small per-school numbers to keep."""
    out = {}
    for s, b in stats.items():
        out[s] = {"students": b["students"], "inactive": len(b["inactive"]),
                  "never": len(b["never"]), "no_guardian": len(b["no_guardian"]),
                  "repairs": len(b["repair"]), "expired": len(b["expired"]),
                  "classroom_pct": round(100 * b["classroom_active"] / b["classroom_known"])
                  if b["classroom_known"] else None}
    return out


def totals_from_schools(stats: dict) -> dict:
    return {"inactive": sum(len(b["inactive"]) for b in stats.values()),
            "never": sum(len(b["never"]) for b in stats.values()),
            "no_guardian": sum(len(b["no_guardian"]) for b in stats.values()),
            "expired": sum(len(b["expired"]) for b in stats.values())}


def weeks(data: dict | None = None) -> list[tuple[str, dict]]:
    data = data or load()
    return sorted(data.get("weeks", {}).items())


def trend_rows(data: dict | None = None, n: int = 12) -> list[dict]:
    ws = weeks(data)[-n:]
    rows = []
    for k, label, up_good in METRICS:
        series = [w.get(k) for _wk, w in ws]
        vals = [v for v in series if isinstance(v, (int, float))]
        if not vals:
            continue
        now = series[-1] if isinstance(series[-1], (int, float)) else None
        prev = next((v for v in reversed(series[:-1]) if isinstance(v, (int, float))), None)
        change = (now - prev) if now is not None and prev is not None else None
        good = None if not change else (change > 0) == up_good
        rows.append({"key": k, "Metric": label, "Now": now, "Last week": prev,
                     "Change": change, "good": good, "series": series})
    return rows


def school_delta(school: str, data: dict | None = None) -> dict:
    """{metric: (now, last week)} for one school from the two latest snapshots."""
    ws = [w for _k, w in weeks(data) if school in (w.get("schools") or {})]
    if len(ws) < 2:
        return {}
    a, b = ws[-2]["schools"][school], ws[-1]["schools"][school]
    return {k: (b.get(k), a.get(k)) for k in b if k in a}


def _count_findings(days: int = 7) -> int:
    from .tools import watchdog
    cut = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
    return sum(1 for f in watchdog.load_findings() if f.get("When", "") >= cut[:16])


def snapshot(log=print, run_csv=None, run_text=None, users=None, heavy: bool = True) -> dict:
    """Gather this week's numbers. heavy=False skips the slow Google reads."""
    from . import fleet, team
    from .tools import reconcile
    vals = {"pending": len(team.list_requests("pending")) if team.folder() else None,
            "to_collect": sum(1 for i in reconcile.load_items() if i["status"] == "To collect"),
            "repairs": sum(1 for t in fleet.load_list(fleet.data_dir(), "repairs.json")
                           if t.get("status") not in ("Fixed", "Replaced", "Can't be fixed")),
            "findings": _count_findings()}
    try:
        from . import lifecycle
        vals.update(lifecycle.score_values(lifecycle.summary()))
    except Exception as exc:  # noqa: BLE001
        log(f"Account timing skipped: {exc}")
    schools = None
    if heavy:
        try:
            from . import school_reports as sr
            stats = sr.fetch(sr.options(), run_csv, run_text, users)
            vals.update(totals_from_schools(stats))
            schools = school_numbers(stats)
        except Exception as exc:  # noqa: BLE001
            log(f"School numbers skipped: {exc}")
        try:
            from .directory import run_gam_csv
            from .tools import budget
            rc = run_csv or (lambda a: run_gam_csv(a, 1800))
            code, rows, _e = rc(budget.USERS_ARGS)
            if code == 0:
                summ, _d = budget.reclaimable(budget.license_holders(rows),
                                              int(budget.options()["inactive_days"]), {})
                vals["licenses_free"] = sum(r["Could free"] for r in summ)
        except Exception as exc:  # noqa: BLE001
            log(f"License numbers skipped: {exc}")
    wk = record(vals, schools)
    try:
        alert_on_trends(log)
    except Exception as exc:  # noqa: BLE001
        log(f"Trend alerts skipped: {exc}")
    log("Scorecard saved: " + ", ".join(f"{LABEL.get(k, k)} {v}" for k, v in wk.items()
                                         if k in LABEL))
    return wk


# ------------------------------------------------------------- trend alerts ---
def trend_alerts(data: dict | None = None, n: int = 8, sigma: float = 2.0,
                 min_change: float = 0.2) -> list[dict]:
    """Numbers that broke away from their recent range in the bad direction.
    A metric is flagged when the latest week is more than `sigma` standard deviations
    (and at least `min_change` = 20 %) away from the previous `n` weeks' average."""
    import statistics
    ws = weeks(data)
    if len(ws) < 4:
        return []
    *hist, (wk, latest) = ws[-(n + 1):]
    out = []
    for key, label, higher_good in METRICS:
        vals = [w.get(key) for _k, w in hist if isinstance(w.get(key), (int, float))]
        now = latest.get(key)
        if len(vals) < 3 or not isinstance(now, (int, float)):
            continue
        mean = statistics.mean(vals)
        sd = statistics.pstdev(vals) or max(abs(mean) * 0.05, 1)
        worse = (now < mean) if higher_good else (now > mean)
        if worse and abs(now - mean) > sigma * sd and \
                abs(now - mean) >= max(abs(mean) * min_change, 1):
            out.append({"Measure": label, "This week": now, "Usual": round(mean, 1),
                        "Week": wk, "key": key})
    return out


def alert_on_trends(log=print, data: dict | None = None) -> list[dict]:
    found = trend_alerts(data)
    if found:
        from . import alerts
        alerts.notify("These scorecard numbers moved sharply this week:\n" + "\n".join(
            f"• {f['Measure']}: {f['This week']} (usually about {f['Usual']})"
            for f in found), "GAMbit scorecard alert")
        for f in found:
            log(f"Scorecard alert: {f['Measure']} {f['This week']} vs ~{f['Usual']}")
    return found
