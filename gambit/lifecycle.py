"""Account timing: how long the district takes to get people going and to lock leavers out.

* New accounts → first sign-in. GAMbit notes, every night, the first day each new account
  shows a sign-in (Google only keeps the *last* sign-in), so the numbers are exact from the
  day this is turned on.
* Leaving → suspended, from the Account time machine's nightly snapshots: the first night
  an account was in a leavers' org unit, and the first night it was suspended.
* Approvals: request → decision.
* Offboarding: started → the "today" steps finished.

Medians go on the weekly scorecard."""

from __future__ import annotations

import datetime
import json
import os
import statistics

from .oupath import under
from .settings import settings

USERS_ARGS = ["print", "users", "fields", "primaryemail,ou,creationtime,lastlogintime,suspended"]
TRACK_DAYS = 120


def options() -> dict:
    try:
        o = json.loads(settings.get("lifecycle/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"root": "/Students", "leaver_ous": "/Former Staff, /Students/Withdrawn",
            "late_days": 7, **o}


def save_options(o: dict):
    settings.set("lifecycle/options", json.dumps(o))


def _store() -> str:
    from . import team
    if team.folder():
        d = team.folder()
    else:
        from .support import logs_dir
        d = os.path.dirname(logs_dir())
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "account_timing.json")


def load() -> dict:
    try:
        with open(_store(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"accounts": {}}


def save(data: dict):
    p = _store()
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(p + ".tmp", p)


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _d(t: str):
    t = (t or "").strip()
    if not t or t.lower().startswith("never") or t.startswith("1970"):
        return None
    try:
        return datetime.date.fromisoformat(t[:10])
    except ValueError:
        return None


def observe(data: dict, user_rows: list[dict], today: datetime.date | None = None) -> dict:
    """Update {accounts: {email: {created, ou, first_login, known}}} from tonight's users."""
    today = today or datetime.date.today()
    cut = today - datetime.timedelta(days=TRACK_DAYS)
    acc = data.setdefault("accounts", {})
    for r in user_rows:
        low = _low(r)
        e = low.get("primaryemail", "").lower()
        created = _d(low.get("creationtime"))
        if not e or not created or created < cut:
            continue
        rec = acc.get(e)
        last = _d(low.get("lastlogintime"))
        if rec is None:
            # first time we see it: if it already signed in we only know it's ≤ that day
            rec = {"created": created.isoformat(), "ou": low.get("orgunitpath", ""),
                   "first_login": last.isoformat() if last else "",
                   "known": not bool(last) or (last - created).days <= 1}
            acc[e] = rec
        elif not rec.get("first_login") and last:
            rec["first_login"] = last.isoformat()
        rec["ou"] = low.get("orgunitpath", "") or rec.get("ou", "")
    for e in [e for e, r in acc.items() if r["created"] < cut.isoformat()]:
        acc.pop(e)
    data["updated"] = today.isoformat()
    return data


def _school(ou: str, root: str) -> str:
    from .parent_report import school_of
    return school_of(ou, root)


def _median(xs):
    return round(statistics.median(xs), 1) if xs else None


def new_accounts(data: dict, opts: dict, today: datetime.date | None = None) -> list[dict]:
    today = today or datetime.date.today()
    late = int(opts.get("late_days", 7) or 7)
    by: dict[str, dict] = {}
    for e, r in data.get("accounts", {}).items():
        sch = _school(r.get("ou", ""), opts.get("root", "/Students")) \
            if under(r.get("ou", ""), opts.get("root", "/Students")) \
            else "Staff and others"
        b = by.setdefault(sch, {"School": sch, "New accounts": 0, "Signed in": 0, "days": [],
                                "Not signed in after %d days" % late: [], })
        b["New accounts"] += 1
        c = datetime.date.fromisoformat(r["created"])
        if r.get("first_login"):
            b["Signed in"] += 1
            if r.get("known", True):
                b["days"].append(max(0, (datetime.date.fromisoformat(r["first_login"]) - c)
                                     .days))
        elif (today - c).days > late:
            b["Not signed in after %d days" % late].append(e)
    out = []
    for b in sorted(by.values(), key=lambda x: x["School"]):
        lst = b.pop("Not signed in after %d days" % late)
        out.append({**{k: v for k, v in b.items() if k != "days"},
                    "Median days to first sign-in": _median(b["days"]),
                    f"Not signed in after {late} days": len(lst), "people": lst})
    return out


def leavers(snapshots: list[tuple[str, dict]], leaver_ous: list[str]) -> list[dict]:
    """snapshots = [(date, {email: {ou, suspended}})] oldest first."""
    roots = [o.rstrip("/").lower() for o in leaver_ous if o.strip()]

    def is_leaver(ou):
        ou = (ou or "").rstrip("/").lower()
        return any(ou == r or ou.startswith(r + "/") for r in roots)
    first_in, first_susp, was_out = {}, {}, set()
    for day, accounts in snapshots:
        for e, a in accounts.items():
            if not is_leaver(a.get("ou")):
                was_out.add(e)
                continue
            if e not in was_out and e not in first_in:
                continue        # was already a leaver when the history started
            first_in.setdefault(e, day)
            if a.get("suspended") and e not in first_susp:
                first_susp[e] = day
    out = []
    last_day = snapshots[-1][0] if snapshots else ""
    for e, d0 in first_in.items():
        d1 = first_susp.get(e)
        days = (datetime.date.fromisoformat(d1) - datetime.date.fromisoformat(d0)).days \
            if d1 else None
        out.append({"Account": e, "Moved to leavers": d0, "Suspended": d1 or "not yet",
                    "Days": days if days is not None else
                    f"{(datetime.date.fromisoformat(last_day) - datetime.date.fromisoformat(d0)).days}+"})
    return sorted(out, key=lambda x: x["Moved to leavers"], reverse=True)


def approvals(requests: list[dict]) -> dict:
    from . import team
    hours, by_cat = [], {}
    pending = []
    for r in requests:
        try:
            t0 = datetime.datetime.fromisoformat(r["time"])
        except (KeyError, ValueError):
            continue
        if r.get("status") == "pending":
            pending.append((t0, r))
            continue
        try:
            t1 = datetime.datetime.fromisoformat((r.get("decided") or "")[:19])
        except ValueError:
            continue
        h = max(0.0, (t1 - t0).total_seconds() / 3600)
        hours.append(h)
        cats = sorted(team.categorize(r["commands"][0])) if r.get("commands") else ["other"]
        by_cat.setdefault(", ".join(cats) or "other", []).append(h)
    oldest = min(pending, key=lambda x: x[0], default=(None, None))
    return {"median_hours": _median(hours), "count": len(hours),
            "by_category": {k: _median(v) for k, v in sorted(by_cat.items())},
            "pending": len(pending),
            "oldest_pending": oldest[1].get("title", "") if oldest[1] else "",
            "oldest_since": oldest[0].isoformat(timespec="minutes") if oldest[0] else ""}


def offboarding(records: list[dict]) -> dict:
    hours = []
    for rec in records:
        try:
            t0 = datetime.datetime.fromisoformat(rec.get("started", "")[:19])
        except ValueError:
            continue
        st = next((s for s in rec.get("stages", []) if s.get("key") == "today"), None)
        if st and st.get("done"):
            try:
                t1 = datetime.datetime.fromisoformat(st["done"][:16])
            except ValueError:
                continue
            hours.append(max(0.0, (t1 - t0).total_seconds() / 3600))
    return {"median_hours": _median(hours), "count": len(hours)}


def summary(today: datetime.date | None = None) -> dict:
    from . import offboard, team, timemachine
    o = options()
    data = load()
    snaps = []
    try:
        for day in sorted(timemachine.dates())[-120:]:
            snaps.append((day, timemachine.load(day)))
    except Exception:  # noqa: BLE001
        snaps = []
    lv = leavers(snaps, [x for x in o["leaver_ous"].split(",")])
    reqs = team.list_requests() if team.folder() else []
    return {"new": new_accounts(data, o, today), "leavers": lv,
            "approvals": approvals(reqs), "offboarding": offboarding(offboard.load_all()),
            "updated": data.get("updated", "")}


def score_values(s: dict) -> dict:
    days = [b["Median days to first sign-in"] for b in s["new"]
            if b["Median days to first sign-in"] is not None]
    lv = [x["Days"] for x in s["leavers"] if isinstance(x["Days"], int)]
    out = {}
    if days:
        out["signin_days"] = _median(days)
    if lv:
        out["leaver_days"] = _median(lv)
    if s["approvals"]["median_hours"] is not None:
        out["approval_hours"] = s["approvals"]["median_hours"]
    return out


def run(log=print, run_csv=None) -> int:
    """Daily task step: note first sign-ins for new accounts."""
    from .directory import run_gam_csv
    run_csv = run_csv or (lambda a: run_gam_csv(a, 3600))
    c, rows, e = run_csv(USERS_ARGS)
    if c != 0:
        log("Account timing: couldn't read users – " + (e or "").strip()[-160:])
        return 0
    data = observe(load(), rows)
    save(data)
    log(f"Account timing: tracking {len(data['accounts'])} new account(s).")
    return len(data["accounts"])
