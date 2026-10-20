"""Saved scheduled jobs: named copies of a GAMbit job with their own settings, org units and
time & days – for example “Blank unused Chromebooks – Middle School” every weekday at 5 AM
and a second one for the high school on Mondays.

Each job is its own Windows Task Scheduler task (``GAMbit.exe --task job --name <id>``), so
it runs with GAMbit closed. The settings live with the job, so changing the Assigned users
tab doesn't change a saved job until you save it again.
"""

from __future__ import annotations

import datetime
import json
import re
import uuid

from .settings import settings

KINDS = {
    "assigned": {"label": "Blank / set Chromebook assigned users",
                 "page": "Chromebook fleet", "tab": "Assigned users"},
    "move": {"label": "Move Chromebooks to their students' schools",
             "page": "Chromebook fleet", "tab": "Assigned users"},
}
PREFIX = "GAMbit job - "


# ============================================================== storage ===
def jobs() -> list[dict]:
    try:
        data = json.loads(settings.get("jobs/list", "[]") or "[]")
    except ValueError:
        data = []
    return [j for j in data if isinstance(j, dict) and j.get("id") and j.get("kind") in KINDS]


def _save_all(items: list[dict]):
    settings.set("jobs/list", json.dumps(items))


def get(job_id: str) -> dict | None:
    return next((j for j in jobs() if j["id"] == job_id), None)


def safe_name(name: str) -> str:
    """Task Scheduler names can't contain \\ / : * ? " < > |."""
    n = re.sub(r'[\\/:*?"<>|]+', "-", (name or "").strip())
    return re.sub(r"\s+", " ", n)[:80] or "job"


def task_name(job: dict) -> str:
    return PREFIX + safe_name(job["name"])


def unique_name(name: str, skip_id: str = "") -> str:
    taken = {safe_name(j["name"]).lower() for j in jobs() if j["id"] != skip_id}
    base, n, out = safe_name(name), 2, safe_name(name)
    while out.lower() in taken:
        out = f"{base} ({n})"
        n += 1
    return out


def new(kind: str, name: str, opts: dict, scope_ous: list[str], time_hhmm: str,
        days: list[str], enabled: bool = True) -> dict:
    if kind not in KINDS:
        raise ValueError(kind)
    job = {"id": uuid.uuid4().hex[:10], "kind": kind, "name": unique_name(name),
           "enabled": bool(enabled), "time": time_hhmm or "05:45", "days": list(days or []),
           "scope_ous": list(scope_ous or []), "opts": _clean(kind, opts),
           "created": datetime.datetime.now().isoformat(timespec="seconds")}
    items = jobs() + [job]
    _save_all(items)
    return job


def update(job: dict) -> dict:
    """Save a changed job (same id). Returns the stored job."""
    items = jobs()
    for i, j in enumerate(items):
        if j["id"] == job["id"]:
            job = {**j, **job, "name": unique_name(job.get("name") or j["name"], j["id"]),
                   "opts": _clean(j["kind"], job.get("opts", j["opts"]))}
            items[i] = job
            _save_all(items)
            return job
    raise KeyError(job["id"])


def remove(job_id: str):
    _save_all([j for j in jobs() if j["id"] != job_id])


def duplicate(job_id: str) -> dict:
    j = get(job_id)
    if not j:
        raise KeyError(job_id)
    return new(j["kind"], j["name"] + " copy", j["opts"], j["scope_ous"], j["time"],
               j["days"], enabled=False)


def _clean(kind: str, opts: dict) -> dict:
    """Only the settings the job uses (never its scheduling flags from the tab)."""
    drop = {"scope_ous", "sched_time", "sched_days", "scheduled", "allow_big"}
    o = {k: v for k, v in (opts or {}).items() if k not in drop}
    if kind == "assigned":
        o.setdefault("sched_stale", False)
        o.setdefault("sched_set", True)
    return o


# =========================================================== describing ===
def describe(job: dict) -> str:
    o = job.get("opts", {})
    where = ", ".join(job.get("scope_ous") or []) or "all Chromebooks"
    if job["kind"] == "assigned":
        parts = []
        if o.get("sched_stale"):
            parts.append(f"blank unused ({o.get('stale_days', 60)}+ days)")
        if o.get("sched_set"):
            parts.append("set from the last student" +
                         (" (blank ones only)" if o.get("blank_only", True) else ""))
        what = " and ".join(parts) or "nothing ticked"
    else:
        what = ("by the org unit map" if o.get("source", "map") == "map" else
                f"pattern {o.get('ou_template', '/Chromebooks/{school}')}")
        what = f"move to the student's school – {what}"
    return f"{what} · {where}"


def when(job: dict) -> str:
    from .ui.schedule_edit import describe as d
    return d(job.get("time", ""), job.get("days") or [])


# ========================================================== scheduling ===
def schedule(job: dict, old_task: str = "") -> str:
    """Create (or replace) the job's Windows task. Returns the task name."""
    from . import scheduler, tasks_health
    from .ui.schedule_edit import task_for
    name = task_name(job)
    if old_task and old_task != name:
        try:
            scheduler.delete_task(old_task)
        except Exception:  # noqa: BLE001 – it may not exist
            pass
    tasks_health.create(task_for({"name": name, "args": ["--task", "job", "--name", job["id"]],
                                  "freq": "daily", "time": job["time"],
                                  "what": describe(job)}, job["time"], job["days"]))
    if not job.get("enabled", True):
        scheduler.set_enabled(name, False)
    return name


def unschedule(job: dict):
    from . import scheduler
    try:
        scheduler.delete_task(task_name(job))
    except Exception:  # noqa: BLE001
        pass


# ================================================================ running ===
def run(job_id: str, log=print, **kw) -> int:
    """What the Windows task runs (also “Run now”)."""
    force = kw.pop("force", False)
    job = get(job_id)
    if not job:
        log(f"Saved job {job_id} no longer exists – remove its task on the Schedules page.")
        return 1
    if not job.get("enabled", True) and not force:
        log(f"“{job['name']}” is turned off.")
        return 0
    from .tools import assigned_users as au
    o = {**job.get("opts", {}), "scope_ous": job.get("scope_ous") or []}
    log(f"Saved job “{job['name']}”: {describe(job)}")
    if job["kind"] == "assigned":
        code = au.run_assign_task(log=log, o=o, **kw)
    else:
        code = au.run_move_task(log=log, o=o, **kw)
    items = jobs()
    for j in items:
        if j["id"] == job_id:
            j["last_run"] = datetime.datetime.now().isoformat(timespec="seconds")
            j["last_code"] = code
    _save_all(items)
    return code


# ============================================================== migration ===
def migrate_legacy() -> list[dict]:
    """The single morning jobs from before saved jobs existed become saved jobs."""
    from .tools import assigned_users as au
    made = []
    if settings.get("jobs/migrated", False):
        return made
    settings.set("jobs/migrated", True)
    ao = au.options()
    if ao.get("sched_set") or ao.get("sched_stale"):
        j = new("assigned", "Assigned users" + (" – " + ", ".join(ao.get("scope_ous") or [])
                                                if ao.get("scope_ous") else ""),
                ao, ao.get("scope_ous") or [], ao.get("sched_time") or "05:45",
                ao.get("sched_days") or [])
        made.append((j, au.ASSIGN_TASK["name"]))
        au.save_options({**ao, "sched_set": False, "sched_stale": False})
    mo = au.move_options()
    if mo.get("scheduled"):
        j = new("move", "Move Chromebooks" + (" – " + ", ".join(mo.get("scope_ous") or [])
                                              if mo.get("scope_ous") else ""),
                mo, mo.get("scope_ous") or [], mo.get("sched_time") or "05:50",
                mo.get("sched_days") or [])
        made.append((j, au.MOVE_TASK["name"]))
        au.save_move_options({**au.move_options_saved(), "scheduled": False})
    for j, old in made:
        try:
            schedule(j, old_task=old)
        except Exception:  # noqa: BLE001 – not Windows; the job is still saved
            pass
    return [j for j, _o in made]
