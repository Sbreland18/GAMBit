"""Monthly audit report for the director or board: what changed and who approved it,
settings changes, unusual activity and how it was handled, and the license and device
numbers. Useful for FERPA / CIPA conversations and for showing the work."""

from __future__ import annotations

import datetime
import html
import json
import os
from collections import Counter, defaultdict

from .settings import settings

TASK = {"name": "GAMbit monthly audit report", "args": ["--task", "auditreport"],
        "freq": "monthly", "time": "07:20",
        "what": "Emails last month's audit report (1st of the month)", "standard": False}


def options() -> dict:
    try:
        o = json.loads(settings.get("auditreport/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"to": "", "district": "", **o}


def save_options(o: dict):
    settings.set("auditreport/options", json.dumps(o))


def month_range(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    start = datetime.date(year, month, 1)
    end = datetime.date(year + (month == 12), month % 12 + 1, 1)
    return start, end


def last_month(today: datetime.date | None = None) -> tuple[int, int]:
    today = today or datetime.date.today()
    first = today.replace(day=1) - datetime.timedelta(days=1)
    return first.year, first.month


def _in(ts: str, start: datetime.date, end: datetime.date) -> bool:
    return start.isoformat() <= (ts or "")[:10] < end.isoformat()


def build(year: int, month: int, acts: list[dict] | None = None,
          requests: list[dict] | None = None, findings: list[dict] | None = None,
          snapshots: list[tuple[str, dict]] | None = None,
          weeks: list[tuple[str, dict]] | None = None) -> dict:
    """All inputs optional (loaded from GAMbit's own files when missing)."""
    from . import team
    start, end = month_range(year, month)
    if acts is None:
        from . import activity
        days = (datetime.date.today() - start).days + 2
        acts = activity.load(days, team=True)
    acts = [a for a in acts if _in(a.get("time", ""), start, end) and a.get("change")]
    if requests is None:
        requests = team.list_requests() if team.folder() else []
    requests = [r for r in requests if _in(r.get("time", ""), start, end)]
    if findings is None:
        from .tools import watchdog
        findings = watchdog.load_findings()
    findings = [f for f in findings if _in(f.get("When", ""), start, end)]

    cats, people, failed, undone = Counter(), Counter(), 0, 0
    examples = defaultdict(list)
    for a in acts:
        cs = team.categorize(a.get("args") or a.get("command", "").split()[1:]) - {"read"}
        for c in cs or {"other"}:
            cats[c] += 1
            if len(examples[c]) < 5:
                examples[c].append(a.get("command", ""))
        people[a.get("who", "?")] += 1
        failed += a.get("code") not in (0, None)
        undone += bool(a.get("undone"))
    req_status = Counter(r.get("status", "") for r in requests)
    auto = sum(1 for r in requests if r.get("auto"))
    by_email = sum(1 for r in requests if "by email" in (r.get("note") or ""))
    escalated = sum(1 for r in requests if r.get("escalated"))
    kinds = Counter(r.get("kind", "request") for r in requests)

    settings_changes = []
    if snapshots is None:
        snapshots = _snapshots_around(start, end)
    if len(snapshots) >= 2:
        from .tools.recovery import diff
        settings_changes = diff(snapshots[0][1], snapshots[-1][1])
    drift = sum(1 for r in requests if r.get("kind") == "drift")

    f_kinds = Counter(f.get("Finding", "") for f in findings)
    f_reviewed = sum(1 for f in findings if str(f.get("Status", "")).startswith("Reviewed"))
    if weeks is None:
        from . import scorecard
        weeks = scorecard.weeks()
    in_month = [w for k, w in weeks if _week_in(k, start, end)]
    numbers = in_month[-1] if in_month else {}
    return {"year": year, "month": month, "start": start, "end": end,
            "changes": len(acts), "categories": cats, "people": people, "failed": failed,
            "undone": undone, "examples": examples, "requests": len(requests),
            "req_status": req_status, "auto": auto, "by_email": by_email,
            "escalated": escalated, "kinds": kinds, "settings_changes": settings_changes,
            "drift": drift, "findings": len(findings), "f_kinds": f_kinds,
            "f_reviewed": f_reviewed, "numbers": numbers,
            "district": options().get("district", "")}


def _week_in(key: str, start, end) -> bool:
    try:
        y, w = key.split("-W")
        monday = datetime.date.fromisocalendar(int(y), int(w), 1)
    except ValueError:
        return False
    return start <= monday < end


def _snapshots_around(start, end) -> list[tuple[str, dict]]:
    """The last snapshot before the month and the last one in it."""
    try:
        from .tools import recovery
        names = sorted(recovery.list_snapshots())
    except Exception:  # noqa: BLE001
        return []
    before = [n for n in names if n[:10] < start.isoformat()]
    inside = [n for n in names if start.isoformat() <= n[:10] < end.isoformat()]
    pick = ([before[-1]] if before else inside[:1]) + inside[-1:]
    out = []
    for n in dict.fromkeys(pick):
        try:
            out.append((n, recovery.load_snapshot(n)))
        except (OSError, ValueError):
            pass
    return out


def render(d: dict) -> tuple[str, str]:
    from . import team
    esc = html.escape
    month = datetime.date(d["year"], d["month"], 1).strftime("%B %Y")
    subject = f"GAMbit audit report – {month}"
    title = f"{esc(d['district']) + ' – ' if d['district'] else ''}Google Workspace audit " \
            f"report, {month}"
    tiles = [("Changes made", d["changes"]), ("Approval requests", d["requests"]),
             ("Settings changed", len(d["settings_changes"])),
             ("Unusual-activity findings", d["findings"])]
    parts = [f"<div style='font-family:Arial,sans-serif;font-size:14px;color:#1f2328;"
             f"max-width:900px'><h2>{title}</h2>"
             f"<p style='color:#57606a'>{d['start']:%B %d} – "
             f"{d['end'] - datetime.timedelta(days=1):%B %d, %Y}. Prepared by GAMbit from its "
             "activity log, approvals, settings snapshots and nightly checks.</p>"
             "<table cellpadding='8' style='border-collapse:collapse'><tr>" +
             "".join(f"<td style='border:1px solid #d0d7de;text-align:center'><div "
                     f"style='font-size:22px;font-weight:bold'>{v}</div><div "
                     f"style='color:#57606a'>{esc(t)}</div></td>" for t, v in tiles) +
             "</tr></table>"]

    def table(head, rows):
        if not rows:
            return "<p style='color:#57606a'>None.</p>"
        th = "".join(f"<th style='text-align:left;border-bottom:1px solid #d0d7de;"
                     f"padding:4px 8px'>{esc(h)}</th>" for h in head)
        tr = "".join("<tr>" + "".join(f"<td style='padding:4px 8px;border-bottom:1px solid "
                                      f"#eaeef2'>{esc(str(c))}</td>" for c in r) + "</tr>"
                     for r in rows)
        return f"<table style='border-collapse:collapse'>{th}{tr}</table>"
    parts.append("<h3>1. What changed</h3>")
    extra = (f"; {d['failed']} failed" if d["failed"] else "") + \
        (f" and {d['undone']} were undone" if d["undone"] else "")
    parts.append(f"<p>{d['changes']} change(s) were made through GAMbit{extra}.</p>")
    parts.append(table(["Kind of change", "How many", "Examples"],
                       [[team.CATEGORIES.get(c, c).split(" (")[0], n,
                         " · ".join(x[:80] for x in d["examples"][c][:2])]
                        for c, n in d["categories"].most_common()]))
    parts.append(table(["Who", "Changes"], d["people"].most_common(15)))
    parts.append("<h3>2. Approvals</h3>")
    st = d["req_status"]
    parts.append(f"<p>{d['requests']} request(s): {st.get('done', 0)} done, "
                 f"{st.get('denied', 0)} denied, {st.get('pending', 0)} still waiting, "
                 f"{st.get('failed', 0)} failed. {d['auto']} approved automatically by the "
                 f"approval rules, {d['by_email']} approved by email reply, "
                 f"{d['escalated']} escalated for waiting too long.</p>")
    parts.append(table(["Came from", "Requests"], [[k.replace("_", " "), n]
                                                    for k, n in d["kinds"].most_common()]))
    parts.append("<h3>3. Admin console and Chrome settings</h3>")
    sc = d["settings_changes"]
    parts.append(f"<p>{len(sc)} setting(s) differ between the start and end of the month"
                 + (f"; {d['drift']} change(s) made outside GAMbit were sent for approval to "
                    "be put back" if d["drift"] else "") + ".</p>")
    parts.append(table(["Change", "Setting"], [[c["Change"], c["Setting"]] for c in sc[:40]]))
    parts.append("<h3>4. Unusual activity</h3>")
    parts.append(f"<p>{d['findings']} finding(s); {d['f_reviewed']} reviewed by staff.</p>")
    parts.append(table(["Finding", "How many"], d["f_kinds"].most_common()))
    n = d["numbers"]
    if n:
        from .scorecard import LABEL
        parts.append("<h3>5. The numbers at month end</h3>")
        parts.append(table(["", "Value"], [[LABEL[k], n[k]] for k in LABEL if k in n]))
    parts.append("<p style='color:#57606a'>Passwords and other secrets are never included. "
                 "The full activity log is available in GAMbit (Reports → Activity log).</p>"
                 "</div>")
    return subject, "".join(parts)


def output_dir() -> str:
    from .scheduler import default_output_dir
    d = os.path.join(settings.get("schedule/out", "") or default_output_dir(), "Audit reports")
    os.makedirs(d, exist_ok=True)
    return d


def save_html(d: dict, folder: str = "") -> str:
    _subj, body = render(d)
    path = os.path.join(folder or output_dir(),
                        f"GAMbit audit {d['year']}-{d['month']:02d}.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"<!doctype html><html><head><meta charset='utf-8'><title>GAMbit audit "
                 f"{d['year']}-{d['month']:02d}</title></head><body>{body}</body></html>")
    return path


def send(log=print, to: str = "", year: int = 0, month: int = 0, run_text=None) -> int:
    from . import google_io
    from .directory import run_gam_text
    run_text = run_text or run_gam_text
    to = to or options().get("to", "")
    if not year:
        year, month = last_month()
    d = build(year, month)
    path = save_html(d)
    log(f"Audit report saved: {path}")
    if "@" not in to:
        log("No one to email the audit report to – it was only saved.")
        return 0
    subject, _b = render(d)
    args = google_io.email_args(to, subject, "")
    i = args.index("message")
    args[i:i + 2] = ["htmlfile", path]
    code, out = run_text(args, 180)
    if code:
        log(f"FAILED emailing the audit report: {out.strip()[-200:]}")
        return 1
    log(f"Audit report for {year}-{month:02d} emailed to {to}.")
    return 0
