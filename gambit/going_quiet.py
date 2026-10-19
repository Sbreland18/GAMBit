"""Students going quiet: a weekly list for counselors of students whose activity has dropped
off across everything GAMbit can see – no Google sign-in for a while, a pile of missing
Classroom work across all their classes, and a Chromebook that hasn't checked in. Each
school's counselors get only their own students; "new this week" marks students who
weren't on last week's list."""

from __future__ import annotations

import datetime
import json
from collections import Counter

from .settings import settings

TASK = {"name": "GAMbit students going quiet", "args": ["--task", "goingquiet"],
        "freq": "weekly", "time": "07:05",
        "what": "Emails counselors the students whose activity has dropped off",
        "standard": False}
MISSING_ARGS = ["print", "course-submissions", "states", "active", "submissionstates",
                "new,created", "late", "showuserprofile"]


def options() -> dict:
    try:
        o = json.loads(settings.get("goingquiet/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"root": "/Students", "signin_days": 10, "missing": 5, "device_days": 14,
            "classroom": True, "devices": True, "min_signals": 2, "counselors": "", **o}


def save_options(o: dict):
    settings.set("goingquiet/options", json.dumps(o))


def _d(t):
    t = (t or "").strip()
    if not t or t.lower().startswith("never") or t.startswith("1970"):
        return None
    try:
        return datetime.date.fromisoformat(t[:10])
    except ValueError:
        return None


def missing_counts(sub_rows: list[dict]) -> Counter:
    c = Counter()
    for r in sub_rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        e = (low.get("profile.emailaddress") or "").lower()
        if e:
            c[e] += 1
    return c


def flag(users: list[dict], opts: dict, missing: Counter | None = None,
         devices: list[dict] | None = None, today: datetime.date | None = None) -> list[dict]:
    from .parent_report import school_of
    today = today or datetime.date.today()
    root = opts.get("root", "/Students")
    s_cut = today - datetime.timedelta(days=int(opts.get("signin_days", 10) or 10))
    d_cut = today - datetime.timedelta(days=int(opts.get("device_days", 14) or 14))
    need = int(opts.get("missing", 5) or 5)
    dev_sync = {}
    for d in devices or []:
        u = (d.get("user") or "").lower()
        if not u:
            continue
        ls = d.get("last_sync")
        if u not in dev_sync or (ls and (dev_sync[u] is None or ls > dev_sync[u])):
            dev_sync[u] = ls        # the most recent check-in of any of their devices
    out = []
    rl = root.rstrip("/").lower()
    for u in users:
        if u.get("suspended"):
            continue
        ou = (u.get("ou") or "").lower()
        if not (ou == rl or ou.startswith(rl + "/")):
            continue
        e = u["email"].lower()
        sig = []
        last = _d(u.get("last_login", ""))
        if last is None:
            sig.append("never signed in")
        elif last < s_cut:
            sig.append(f"no sign-in since {last:%b %d}")
        if missing is not None and missing.get(e, 0) >= need:
            sig.append(f"{missing[e]} missing assignments")
        if devices is not None and e in dev_sync:
            ls = dev_sync[e]
            if ls is None or ls < d_cut:
                sig.append("Chromebook not used since " + (f"{ls:%b %d}" if ls else "ever"))
        if sig:
            out.append({"Student": e, "Name": u.get("name", ""),
                        "School": school_of(u.get("ou", ""), root), "Signals": len(sig),
                        "What we see": "; ".join(sig), "Last sign-in":
                        last.isoformat() if last else "never"})
    return sorted(out, key=lambda x: (-x["Signals"], x["School"], x["Student"]))


def counselors(text: str) -> dict[str, list[str]]:
    out = {}
    for ln in (text or "").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            out[k.strip().lower()] = [x.strip() for x in v.replace(";", ",").split(",")
                                      if "@" in x]
    return out


def mark_new(rows: list[dict], last: set[str]) -> list[dict]:
    for r in rows:
        r["New this week"] = "yes" if r["Student"] not in last else ""
    return rows


def render(school: str, rows: list[dict]) -> tuple[str, str]:
    new = sum(1 for r in rows if r.get("New this week"))
    subj = f"Students going quiet – {school}: {len(rows)}" + (f" ({new} new)" if new else "")
    lines = [f"Students at {school} whose activity has dropped off (from Google sign-ins, "
             "Classroom and Chromebooks):", ""]
    for r in rows:
        lines.append(f"• {r['Name'] or r['Student']} ({r['Student']})"
                     + (" – NEW" if r.get("New this week") else "") + f": {r['What we see']}")
    lines += ["", "Sent by GAMbit. Reply to the technology department if a student's account "
              "or Chromebook needs help."]
    return subj, "\n".join(lines)


def fetch(opts: dict, run_csv=None, users=None) -> list[dict]:
    from . import fleet
    from .directory import load_users, run_gam_csv
    run_csv = run_csv or (lambda a: run_gam_csv(a, 7200))
    users = users if users is not None else load_users()
    miss = devs = None
    if opts.get("classroom", True):
        c, rows, _e = run_csv(MISSING_ARGS)
        miss = missing_counts(rows) if c == 0 else None
    if opts.get("devices", True):
        c, rows, _e = run_csv(["print", "cros", "fields", fleet.FIELDS])
        devs = fleet.devices(rows) if c == 0 else None
    rows = flag(users, opts, miss, devs)
    keep = int(opts.get("min_signals", 2) or 1)
    return [r for r in rows if r["Signals"] >= keep]


def send(log=print, run_csv=None, users=None, tell=None) -> int:
    from . import google_io
    o = options()
    tell = tell or google_io.send_email
    rows = fetch(o, run_csv, users)
    try:
        last = set(json.loads(settings.get("goingquiet/last", "[]") or "[]"))
    except ValueError:
        last = set()
    mark_new(rows, last)
    settings.set("goingquiet/last", json.dumps([r["Student"] for r in rows]))
    who = counselors(o.get("counselors", ""))
    sent = 0
    for school in sorted({r["School"] for r in rows}):
        to = who.get(school.lower())
        if not to:
            continue
        subj, body = render(school, [r for r in rows if r["School"] == school])
        try:
            tell(",".join(to), subj, body)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            log(f"Couldn't email {school}: {exc}")
    log(f"Students going quiet: {len(rows)} student(s); {sent} school email(s) sent.")
    return sent
