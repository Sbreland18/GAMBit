"""Live leadership dashboard: every night GAMbit refreshes a Google Sheet with the district
scorecard, per-school numbers, open help-desk tickets and unusual-activity counts, so the
director and principals can look any time without GAMbit."""

from __future__ import annotations

import csv
import datetime
import os
import tempfile

from .settings import settings

TASK = {"name": "GAMbit leadership dashboard", "args": ["--task", "leadersheet"],
        "freq": "daily", "time": "06:55",
        "what": "Refreshes the leadership dashboard Google Sheet", "standard": False}


def sheet_url() -> str:
    return (settings.get("leadersheet/url", "") or "").strip()


def tabs(tickets: list[dict] | None = None, findings: list[dict] | None = None,
         today: datetime.date | None = None) -> dict[str, list[list]]:
    """All tabs as rows (first row = headers). Uses GAMbit's saved data only."""
    from . import scorecard
    today = today or datetime.date.today()
    out = {}
    rows = scorecard.trend_rows()
    out["Scorecard"] = [["Measure", "This week", "Last week", "Change", "Updated"]] + [
        [r["Metric"], r["Now"], r["Last week"], r["Change"], today.isoformat()] for r in rows]
    ws = scorecard.weeks()
    keys = [k for k, _l, _g in scorecard.METRICS]
    out["Trend"] = [["Week"] + [scorecard.LABEL[k] for k in keys]] + [
        [wk] + [w.get(k, "") for k in keys] for wk, w in ws[-26:]]
    latest = next((w.get("schools") for _k, w in reversed(ws) if w.get("schools")), {}) or {}
    head = ["School", "Students", "Not signing in", "Never signed in", "No guardian",
            "Used Classroom %", "In repair", "Past end of updates"]
    out["Schools"] = [head] + [[s, n.get("students", ""), n.get("inactive", ""),
                                n.get("never", ""), n.get("no_guardian", ""),
                                n.get("classroom_pct", ""), n.get("repairs", ""),
                                n.get("expired", "")] for s, n in sorted(latest.items())]
    if tickets is not None:
        out["Open tickets"] = [["#", "Opened", "For", "Subject", "Type"]] + [
            [t["number"], t["created"], t["for"], t["subject"], t["kind"]] for t in tickets[:500]]
    if findings is not None:
        cut = (today - datetime.timedelta(days=30)).isoformat()
        recent = [f for f in findings if f.get("When", "") >= cut]
        by = {}
        for f in recent:
            by[f["Finding"]] = by.get(f["Finding"], 0) + 1
        out["Unusual activity (30 days)"] = [["Finding", "How many"]] + sorted(
            [[k, v] for k, v in by.items()], key=lambda x: -x[1])
    return out


def push(log=print, upload=None, tickets=None, findings=None) -> list[str]:
    """Write each tab to the sheet (replace_sheet_tab, or `upload` in tests)."""
    from . import google_io
    url = sheet_url()
    if not url:
        raise RuntimeError("Create or paste the dashboard sheet first.")
    if tickets is None:
        try:
            from .integrations import ticketing
            tickets = ticketing.list_open({}) if ticketing.configured() and \
                ticketing.can("list") else None
        except Exception as exc:  # noqa: BLE001
            log(f"Tickets skipped: {exc}")
            tickets = None
    if findings is None:
        from .tools import watchdog
        findings = watchdog.load_findings()
    in_place = upload is None
    upload = upload or google_io.replace_sheet_tab
    d = os.path.join(tempfile.gettempdir(), "GAMbit")
    os.makedirs(d, exist_ok=True)
    done = []
    for name, rows in tabs(tickets, findings).items():
        if in_place and google_io.write_tab_in_place(url, name, rows):
            done.append(name)   # updated in place – keeps charts and formatting
            continue
        path = os.path.join(d, f"leader_{abs(hash(name))}.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(rows)
        upload(url, name, path)
        done.append(name)
    settings.set("leadersheet/last", datetime.datetime.now().isoformat(timespec="minutes"))
    log(f"Leadership dashboard updated: {', '.join(done)}")
    return done


def create(title: str = "GAMbit leadership dashboard") -> str:
    """Make a new sheet with the scorecard tab and remember it."""
    from . import google_io
    d = os.path.join(tempfile.gettempdir(), "GAMbit")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "leader_new.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(tabs()["Scorecard"])
    link = google_io.upload_csv_as_sheet(path, title)
    settings.set("leadersheet/url", link)
    return link
