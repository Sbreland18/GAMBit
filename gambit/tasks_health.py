"""Background task health: every GAMbit task in Windows Task Scheduler, what it does,
when it last ran and whether it worked (from Task Scheduler and GAMbit's task log)."""

from __future__ import annotations

import datetime
import os
import re

from .settings import IS_WINDOWS, settings

STANDARD = [
    # (task name, args, schedule kind, default time, what it does)
    ("GAMbit daily follow-ups", ["--task", "daily"], "daily", "06:15",
     "Offboarding/graduation steps that are due, loaner reminders, activity log → Sheet"),
    ("GAMbit automatic groups", ["--task", "groups"], "daily", "04:40",
     "Rebuilds automatic groups"),
    ("GAMbit staff requests", ["--task", "requests"], "every15", "07:00",
     "Staff request form, email approvals, password tickets and escalation (every 15 min)"),
    ("GAMbit weekly digest", ["--task", "digest"], "weekly", "07:10",
     "Emails the weekly digest on Mondays"),
]
OK_RESULTS = ("0", "0x0", "267011", "267009", "")   # 267011 = never run, 267009 = running


def _log_path() -> str:
    from .support import logs_dir
    return os.path.join(logs_dir(), "tasks.log")


_FAIL = re.compile(r"\bfailed\b(?!\s*[:=]?\s*0\b)", re.I)


def _new_run(last: str, t: str, msg: str) -> bool:
    """A run starts with GAMbit's 'Starting' line, or after a gap of over 5 minutes."""
    if msg.startswith("Starting"):
        return True
    if not last:
        return True
    try:
        gap = (datetime.datetime.fromisoformat(t) - datetime.datetime.fromisoformat(last))
    except ValueError:
        return t[:16] != last[:16]
    return gap.total_seconds() > 300


def log_summary() -> dict:
    """task key ('daily', 'sync:Name', …) -> {last, failed, lines}"""
    out: dict = {}
    try:
        with open(_log_path(), encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-5000:]
    except OSError:
        return out
    pat = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \[([^\]]+)\] (.*)$")
    for ln in lines:
        m = pat.match(ln.rstrip("\n"))
        if not m:
            continue
        t, key, msg = m.groups()
        e = out.setdefault(key, {"last": "", "failed": False, "lines": []})
        if _new_run(e["last"], t, msg):
            e["failed"] = False
            e["lines"] = []
        e["last"] = t
        e["lines"].append(msg)
        if msg.startswith("FAILED") or _FAIL.search(msg):
            e["failed"] = True
    return out


def _key_for(args: list[str]) -> str:
    if "--task" not in args:
        return ""
    t = args[args.index("--task") + 1]
    if "--name" in args:
        t += ":" + args[args.index("--name") + 1]
    return t


def reconcile_autofix_on() -> bool:
    try:
        from .tools.reconcile import autofix_options
        return bool(autofix_options().get("enabled"))
    except Exception:  # noqa: BLE001
        return False


def rows() -> list[dict]:
    from . import rostersync_run, scheduler
    try:
        sched = {t["Name"]: t for t in scheduler.list_tasks()}
    except Exception:  # noqa: BLE001
        sched = {}
    logs = log_summary()
    defs = [{"name": n, "args": a, "freq": f, "time": tm, "what": w, "standard": True}
            for n, a, f, tm, w in STANDARD]
    for name, p in rostersync_run.all_profiles().items():
        if p.get("schedule"):
            defs.append({"name": f"Roster sync - {scheduler.slug(name)}",
                         "args": ["--task", "sync", "--name", name], "freq": "daily",
                         "time": p["schedule"].get("time", "05:30"),
                         "what": f"Roster sync “{name}”", "standard": False})
    from .signature import ROLLOUT_TASK, rollout
    if rollout().get("targets"):
        defs.append(dict(ROLLOUT_TASK))
    from .tools import automation as _auto
    if settings.get("assign/scheduled", False):
        defs.append(dict(_auto.ASSIGN_TASK))
    if settings.get("cleanup/scheduled", False):
        defs.append(dict(_auto.CLEANUP_TASK))
    if reconcile_autofix_on():
        from .tools.reconcile import AUTOFIX_TASK
        defs.append(dict(AUTOFIX_TASK))
    for key, mod, attr in (("classroomsync/scheduled", "tools.classroom_sync", "TASK"),
                           ("baseline/scheduled", "tools.baseline", "TASK"),
                           ("goingquiet/scheduled", "going_quiet", "TASK"),
                           ("timemachine/scheduled", "timemachine", "TASK"),
                           ("questions/scheduled", "saved_questions", "TASK"),
                           ("leadersheet/scheduled", "leader_sheet", "TASK"),
                           ("campaign2sv/scheduled", "tools.campaigns", "TASK"),
                           ("auditreport/scheduled", "audit_report", "TASK"),
                           ("teacherlists/scheduled", "teacher_lists", "TASK"),
                           ("scorecard/scheduled", "scorecard", "TASK")):
        if settings.get(key, False):
            import importlib
            defs.append(dict(getattr(importlib.import_module(f".{mod}", __package__), attr)))
    if settings.get("watchdog/scheduled", False):
        from .tools.watchdog import TASK as WD
        defs.append(dict(WD))
    if settings.get("schoolreports/scheduled", False):
        from .school_reports import TASK as SR
        defs.append(dict(SR))
    if settings.get("watch/enabled", False):
        from .tools.recovery import TASK as WATCH
        defs.append(dict(WATCH))
    from . import parent_report
    pr = parent_report.options()
    if pr.get("principals") or pr.get("district_to"):
        defs.append(dict(parent_report.TASK))
    known = {d["name"] for d in defs}
    for n in sched:
        if n not in known:
            defs.append({"name": n, "args": [], "freq": "", "time": "",
                         "what": "Scheduled job (template / report)", "standard": False})
    out = []
    for d in defs:
        t = sched.get(d["name"])
        lg = logs.get(_key_for(d["args"]), {}) if d["args"] else {}
        res = (t or {}).get("Last result", "")
        if not t:
            state = "not scheduled"
        elif res not in OK_RESULTS or lg.get("failed"):
            state = "failed"
        elif res == "267011" and not lg:
            state = "never run"
        else:
            state = "ok"
        out.append({**d, "scheduled": bool(t), "state": state,
                    "next": (t or {}).get("Next run", ""),
                    "last": lg.get("last") or (t or {}).get("Last run", ""),
                    "result": res, "log": lg.get("lines", [])})
    return out


def create(d: dict):
    from . import scheduler
    if not IS_WINDOWS:
        raise RuntimeError("Background tasks use Windows Task Scheduler.")
    script = scheduler.build_app_task_script(d["name"], d["args"])
    days = (d.get("days") or "MON") if d["freq"] == "weekly" else ""   # monthly: the 1st
    scheduler.create_task(d["name"], script, d["freq"] or "daily", d["time"] or "06:00", days)
    if d["args"] == ["--task", "daily"]:
        settings.set("tasks/daily_created", True)


def run_here(args: list[str]) -> int:
    """Run a background task inside this GAMbit (useful when testing)."""
    from .headless import main
    return main(args)
