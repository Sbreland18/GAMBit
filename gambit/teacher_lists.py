"""Teacher follow-up lists: from the Classroom rosters, each teacher gets only their own
students who haven't signed in lately, have no guardian invited, have no Chromebook
assigned, or have an overdue loaner. The principal report, one level down."""

from __future__ import annotations

import datetime
import html
import json
import os
from collections import defaultdict

from .settings import settings

TASK = {"name": "GAMbit teacher lists", "args": ["--task", "teacherlists"],
        "freq": "weekly", "time": "06:45",
        "what": "Emails each teacher a short follow-up list for their classes (Mondays)",
        "standard": False}
PARTICIPANTS_ARGS = ["print", "course-participants", "states", "active", "show", "all"]


def options() -> dict:
    try:
        o = json.loads(settings.get("teacherlists/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"inactive_days": 14, "guardians": True, "devices": True, "loaners": True,
            "only": "", "max_teachers": 400, **o}


def save_options(o: dict):
    settings.set("teacherlists/options", json.dumps(o))


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _date(t):
    t = (t or "").strip()
    if not t or t.lower().startswith("never") or t.startswith("1970"):
        return None
    try:
        return datetime.date.fromisoformat(t[:10])
    except ValueError:
        return None


def rosters(participants: list[dict]) -> tuple[dict, dict, dict]:
    """→ (teacher → {course ids}, course id → [student emails], course id → name)"""
    teachers, students, names = defaultdict(set), defaultdict(set), {}
    for r in participants:
        low = _low(r)
        cid = low.get("courseid", "")
        names[cid] = low.get("coursename", "") or cid
        e = (low.get("profile.emailaddress") or "").lower()
        if not e:
            continue
        role = low.get("userrole", "").upper()
        if role == "TEACHER":
            teachers[e].add(cid)
        elif role == "STUDENT":
            students[cid].add(e)
    return dict(teachers), {c: sorted(s) for c, s in students.items()}, names


def flags_for(users: list[dict], opts: dict, guardians_current=None, devices=None,
              loans=None, today: datetime.date | None = None) -> dict:
    """student email → [reasons]"""
    from .parent_report import status_by_student
    today = today or datetime.date.today()
    cut = today - datetime.timedelta(days=int(opts.get("inactive_days", 14) or 14))
    st = status_by_student(guardians_current) if guardians_current is not None else None
    has_dev = {(d.get("user") or "").lower() for d in devices or [] if d.get("user")}
    overdue = defaultdict(list)
    for ln in loans or []:
        if not ln.get("returned") and ln.get("due") and ln["due"] < today.isoformat():
            overdue[(ln.get("user") or "").lower()].append(ln)
    out = {}
    for u in users:
        if u.get("suspended"):
            continue
        e = u["email"].lower()
        f = []
        d = _date(u.get("last_login", ""))
        if d is None:
            f.append("has never signed in")
        elif d < cut:
            f.append(f"no sign-in since {d:%b %d}")
        if st is not None and opts.get("guardians", True):
            g = st.get(e)
            if not g or not (g["accepted"] or g["pending"]):
                f.append("no guardian invited")
        if devices is not None and opts.get("devices", True) and e not in has_dev:
            f.append("no Chromebook assigned")
        if opts.get("loaners", True):
            for ln in overdue.get(e, []):
                f.append(f"loaner {ln['serial']} overdue since {ln['due']}")
        if f:
            out[e] = f
    return out


def lists(participants: list[dict], users: list[dict], flags: dict,
          only: str = "") -> dict:
    """teacher → {course name → [(student, name, reasons)]} (only flagged students)."""
    teachers, students, names = rosters(participants)
    nm = {u["email"].lower(): u.get("name", "") for u in users}
    keep = {x.strip().lower() for x in (only or "").split(",") if x.strip()}
    out = {}
    for t, cids in teachers.items():
        if keep and t not in keep:
            continue
        per = {}
        for cid in sorted(cids, key=lambda c: names.get(c, c)):
            rows = [(s, nm.get(s, ""), flags[s]) for s in students.get(cid, []) if s in flags]
            if rows:
                per[names.get(cid, cid)] = rows
        if per:
            out[t] = per
    return out


def render(teacher: str, per: dict, opts: dict) -> tuple[str, str]:
    esc = html.escape
    n = len({s for rows in per.values() for s, _n, _f in rows})
    subject = f"Students to follow up on this week ({n})"
    parts = ["<div style='font-family:Arial,sans-serif;font-size:14px;color:#1f2328'>",
             f"<p>Hello,</p><p>These {n} student(s) in your Google Classroom classes may need "
             "a nudge. It's a short list – nothing is wrong with the others.</p>"]
    for course, rows in per.items():
        parts.append(f"<h3 style='margin:16px 0 4px'>{esc(course)}</h3><ul>")
        parts += [f"<li><b>{esc(name or s)}</b> ({esc(s)}) – {esc('; '.join(f))}</li>"
                  for s, name, f in rows]
        parts.append("</ul>")
    parts.append("<p style='color:#57606a'>Sent by the technology department with GAMbit. "
                 "Reply if something looks wrong.</p></div>")
    return subject, "".join(parts)


def fetch(opts: dict, run_csv=None, run_text=None, users=None) -> tuple[dict, list]:
    from . import fleet, guardians
    from .directory import load_users, run_gam_csv, run_gam_text
    run_csv = run_csv or (lambda a: run_gam_csv(a, 3600))
    run_text = run_text or run_gam_text
    users = users if users is not None else load_users()
    code, parts, err = run_csv(PARTICIPANTS_ARGS)
    if code != 0:
        raise RuntimeError("Couldn't read the Classroom rosters: " + (err or "").strip()[-200:])
    cur = devs = None
    if opts.get("guardians", True):
        from .parent_report import options as pr_options
        root = pr_options().get("root", "/Students") or "/Students"
        c, out = run_text(["ou_and_children", root, "print", "guardians", "all",
                           "showstudentemails"], 3600)
        cur = guardians.parse_current(out) if c == 0 else None
    if opts.get("devices", True):
        c, rows, _e = run_csv(["print", "cros", "fields", fleet.FIELDS, "listlimit", "1"])
        devs = fleet.devices(rows) if c == 0 else None
    loans = fleet.load_list(fleet.data_dir(), "loaners.json") if opts.get("loaners") else []
    fl = flags_for(users, opts, cur, devs, loans)
    return lists(parts, users, fl, opts.get("only", "")), users


def send(log=print, run_csv=None, run_text=None, users=None) -> int:
    from . import google_io
    from .directory import run_gam_text
    run_text = run_text or run_gam_text
    opts = options()
    per_teacher, _u = fetch(opts, run_csv, run_text, users)
    tmp = os.path.join(os.path.expanduser("~"), ".gambit-tmp")
    os.makedirs(tmp, exist_ok=True)
    bad = sent = 0
    for t, per in list(per_teacher.items())[:int(opts.get("max_teachers", 400) or 400)]:
        subject, body = render(t, per, opts)
        path = os.path.join(tmp, f"teacher_{abs(hash(t))}.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        args = google_io.email_args(t, subject, "")
        i = args.index("message")
        args[i:i + 2] = ["htmlfile", path]
        code, out = run_text(args, 180)
        if code:
            bad += 1
            log(f"FAILED emailing {t}: {out.strip()[-160:]}")
        else:
            sent += 1
    log(f"Teacher lists: {sent} sent, {bad} failed.")
    settings.set("teacherlists/last", datetime.datetime.now().isoformat(timespec="minutes"))
    return bad
