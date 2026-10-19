"""Weekly per-school report for principals: only their school's numbers – inactive
students, missing guardians, Chromebooks in repair or past their update date, and how
many students used Classroom this week."""

from __future__ import annotations

import datetime
import html
import json
import os
from collections import defaultdict

from .settings import settings

TASK = {"name": "GAMbit school reports", "args": ["--task", "schoolreports"],
        "freq": "weekly", "time": "06:40",
        "what": "Emails each principal their school's weekly report (Mondays)",
        "standard": False}


def options() -> dict:
    try:
        o = json.loads(settings.get("schoolreports/options", "{}") or "{}")
    except ValueError:
        o = {}
    from . import parent_report
    pr = parent_report.options()
    return {"root": pr.get("root", "/Students"), "principals": pr.get("principals", ""),
            "inactive_days": 14, "guardians": True, "classroom": True, "devices": True,
            "device_root": "", "district_to": "", **o}


def save_options(o: dict):
    settings.set("schoolreports/options", json.dumps(o))


def _date(text: str):
    t = (text or "").strip()
    if not t or t.lower().startswith("never") or t.startswith("1970"):
        return None
    try:
        return datetime.date.fromisoformat(t[:10])
    except ValueError:
        return None


def _blank():
    return {"students": 0, "inactive": [], "never": [], "no_guardian": [], "repair": [],
            "expired": [], "expiring": [], "classroom_active": 0, "classroom_known": 0}


def gather(users: list[dict], opts: dict, guardians_current: list[dict] | None = None,
           usage_rows: list[dict] | None = None, devices: list[dict] | None = None,
           repairs: list[dict] | None = None, today: datetime.date | None = None) -> dict:
    """→ {school: stats}. All inputs already fetched (so it's testable)."""
    from .parent_report import school_of, status_by_student
    today = today or datetime.date.today()
    root = opts.get("root", "/Students")
    cutoff = today - datetime.timedelta(days=int(opts.get("inactive_days", 14) or 14))
    week_ago = today - datetime.timedelta(days=10)      # report data lags ~3 days
    under = root.rstrip("/").lower() + "/"
    students = [u for u in users if not u.get("suspended") and
                (u.get("ou", "") + "/").lower().startswith(under)]
    school_by_email = {}
    by: dict[str, dict] = defaultdict(_blank)
    for u in students:
        s = school_of(u.get("ou", ""), root)
        school_by_email[u["email"].lower()] = s
        b = by[s]
        b["students"] += 1
        d = _date(u.get("last_login", ""))
        if d is None:
            b["never"].append(u["email"])
        elif d < cutoff:
            b["inactive"].append(f"{u['email']} (last {d.isoformat()})")
    if guardians_current is not None:
        st = status_by_student(guardians_current)
        for e, s in school_by_email.items():
            g = st.get(e)
            if not g or not (g["accepted"] or g["pending"]):
                by[s]["no_guardian"].append(e)
    if usage_rows is not None:
        for r in usage_rows:
            low = {(k or "").lower(): (v or "") for k, v in r.items()}
            e = low.get("email", "").lower()
            s = school_by_email.get(e)
            if not s:
                continue
            by[s]["classroom_known"] += 1
            d = _date(low.get("classroom:last_interaction_time", ""))
            if d and d >= week_ago:
                by[s]["classroom_active"] += 1
    if devices is not None:
        droot = opts.get("device_root", "")
        soon = today + datetime.timedelta(days=365)
        dev_school = {}
        for d in devices:
            s = school_by_email.get((d.get("user") or d.get("recent_user") or "").lower())
            if not s and droot:
                rel = school_of(d.get("ou", ""), droot)
                s = next((x for x in by if x.lower() == rel.lower()), None)
            if not s or (d.get("status") or "ACTIVE") != "ACTIVE":
                continue
            dev_school[d["serial"].upper()] = s
            label = f"{d['serial']}" + (f" ({d['asset']})" if d.get("asset") else "")
            if d.get("aue") and d["aue"] < today:
                by[s]["expired"].append(label)
            elif d.get("aue") and d["aue"] <= soon:
                by[s]["expiring"].append(label)
        for t in repairs or []:
            if t.get("status") in ("Fixed", "Replaced", "Can't be fixed"):
                continue
            s = dev_school.get((t.get("serial") or "").upper()) or \
                school_by_email.get((t.get("user") or "").lower())
            if s:
                by[s]["repair"].append(f"{t['serial']} – #{t.get('n', '')} "
                                       f"{t.get('problem', '')[:40]} (since {t.get('opened')})")
    return dict(sorted(by.items()))


def table(stats: dict) -> tuple[list[str], list[list[str]]]:
    h = ["School", "Students", "Not signed in lately", "Never signed in", "No guardian",
         "Used Classroom this week", "In repair", "Past end of updates",
         "Updates end within a year"]
    rows = []
    for s, b in stats.items():
        cls = (f"{100 * b['classroom_active'] / b['classroom_known']:.0f}%"
               if b["classroom_known"] else "–")
        rows.append([s, str(b["students"]), str(len(b["inactive"])), str(len(b["never"])),
                     str(len(b["no_guardian"])), cls, str(len(b["repair"])),
                     str(len(b["expired"])), str(len(b["expiring"]))])
    return h, rows


def _delta_text(delta: dict, key: str) -> str:
    now, before = (delta or {}).get(key, (None, None))
    if not isinstance(now, (int, float)) or not isinstance(before, (int, float)):
        return ""
    d = now - before
    if not d:
        return "same as last week"
    return f"{'▲' if d > 0 else '▼'} {abs(d)} vs last week"


def render(school: str, b: dict, opts: dict, delta: dict | None = None) -> tuple[str, str]:
    esc = html.escape
    days = opts.get("inactive_days", 14)
    subject = f"{school} – weekly technology report"
    cls = (f"{100 * b['classroom_active'] / b['classroom_known']:.0f}%"
           if b["classroom_known"] else "–")
    tiles = [("Students", b["students"], ""),
             (f"No sign-in in {days} days", len(b["inactive"]), "inactive"),
             ("Never signed in", len(b["never"]), "never"),
             ("No guardian connected", len(b["no_guardian"]), "no_guardian"),
             ("Used Classroom this week", cls, "classroom_pct"),
             ("Chromebooks in repair", len(b["repair"]), "repairs"),
             ("Past end of updates", len(b["expired"]), "expired")]
    parts = [f"<div style='font-family:Arial,sans-serif;font-size:14px;color:#1f2328'>"
             f"<h2>{esc(school)}</h2><p>Weekly report, {datetime.date.today():%B %d, %Y}.</p>"
             "<table cellpadding='8' style='border-collapse:collapse'><tr>" +
             "".join(f"<td style='border:1px solid #d0d7de;text-align:center'><div "
                     f"style='font-size:20px;font-weight:bold'>{v}</div><div "
                     f"style='color:#57606a'>{esc(t)}</div>" +
                     (f"<div style='color:#57606a;font-size:11px'>"
                      f"{esc(_delta_text(delta, k))}</div>" if k and _delta_text(delta, k)
                      else "") + "</td>" for t, v, k in tiles) +
             "</tr></table>"]

    def section(title, items):
        if not items:
            return ""
        lis = "".join(f"<li>{esc(i)}</li>" for i in items[:60])
        more = f"<p style='color:#57606a'>…and {len(items) - 60} more</p>" \
            if len(items) > 60 else ""
        return f"<h3 style='margin:18px 0 4px'>{esc(title)}</h3><ul>{lis}</ul>{more}"
    parts.append(section(f"Students with no sign-in in {days} days", b["inactive"]))
    parts.append(section("Students who have never signed in", b["never"]))
    parts.append(section("Students with no guardian invited", b["no_guardian"]))
    parts.append(section("Chromebooks in repair", b["repair"]))
    parts.append(section("Chromebooks past their end-of-updates date", b["expired"]))
    parts.append(section("Chromebooks whose updates end within a year", b["expiring"]))
    parts.append("<p style='color:#57606a'>Sent by GAMbit for the technology department. "
                 "Reply to this email with any questions.</p></div>")
    return subject, "".join(parts)


def fetch(opts: dict, run_csv=None, run_text=None, users=None) -> dict:
    """Run the read-only GAM commands and build the stats."""
    from . import fleet, guardians
    from .directory import load_users, run_gam_csv, run_gam_text
    from .tools.more_tools import users_report_args
    run_csv = run_csv or (lambda a: run_gam_csv(a, 3600))
    run_text = run_text or run_gam_text
    users = users if users is not None else load_users()
    root = opts.get("root", "/Students")
    cur = usage = devs = None
    if opts.get("guardians", True):
        code, out = run_text(["ou_and_children", root, "print", "guardians", "all",
                              "showstudentemails"], 3600)
        cur = guardians.parse_current(out) if code == 0 else None
    if opts.get("classroom", True):
        code, usage, _e = run_csv(users_report_args(root))
        usage = usage if code == 0 else None
    repairs = []
    if opts.get("devices", True):
        code, rows, _e = run_csv(["print", "cros", "fields", fleet.FIELDS, "listlimit", "1"])
        devs = fleet.devices(rows) if code == 0 else None
        repairs = fleet.load_list(fleet.data_dir(), "repairs.json")
    return gather(users, opts, cur, usage, devs, repairs)


def send(log=print, run_csv=None, run_text=None, users=None) -> int:
    from . import google_io, parent_report
    from .directory import run_gam_text
    run_text = run_text or run_gam_text
    opts = options()
    principals = parent_report.parse_principals(opts.get("principals", ""))
    if not principals and not opts.get("district_to"):
        log("No principals are set up for the school reports.")
        return 0
    stats = fetch(opts, run_csv, run_text, users)
    try:
        from . import scorecard
        scorecard.record(scorecard.totals_from_schools(stats), scorecard.school_numbers(stats))
    except Exception as exc:  # noqa: BLE001
        log(f"Couldn't save the scorecard: {exc}")
        scorecard = None
    low = {s.lower(): s for s in stats}
    tmp = os.path.join(os.path.expanduser("~"), ".gambit-tmp")
    os.makedirs(tmp, exist_ok=True)
    bad = 0
    for school, to in principals.items():
        s = low.get(school)
        if not s:
            log(f"No students found for “{school}” – check the name matches the org unit.")
            continue
        subject, body = render(s, stats[s], opts,
                               scorecard.school_delta(s) if scorecard else None)
        path = os.path.join(tmp, f"school_{abs(hash(s))}.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        args = google_io.email_args(",".join(to), subject, "")
        i = args.index("message")
        args[i:i + 2] = ["htmlfile", path]
        code, out = run_text(args, 180)
        if code:
            bad += 1
            log(f"FAILED emailing {s}: {out.strip()[-200:]}")
        else:
            log(f"Sent {s}'s report to {', '.join(to)}.")
    if opts.get("district_to"):
        h, rows = table(stats)
        text = "\n".join(" | ".join(r) for r in [h] + rows)
        try:
            google_io.send_email(opts["district_to"], "GAMbit school reports – all schools",
                                 text)
        except Exception as exc:  # noqa: BLE001
            bad += 1
            log(f"Couldn't send the district summary: {exc}")
    settings.set("schoolreports/last", datetime.datetime.now().isoformat(timespec="minutes"))
    return bad
