"""Run later and change freezes.

• Run later – queue any change (or an approved request) to run tonight or on a date. The
  “staff requests” background task (every 15 minutes) runs what's due.
• Change freezes – windows (state testing, the first week of school…) when risky kinds of
  change are blocked. A Full admin can override; every override is logged with its reason.
"""

from __future__ import annotations

import datetime
import json
import uuid

from .settings import settings

RISKY_DEFAULT = ["delete", "suspend", "everyone", "chromebooks"]


def _read(name, key):
    from . import team
    if team.folder():
        d = team.read_shared(name)
        if d:
            return d.get(key, [])
    try:
        return json.loads(settings.get(f"changequeue/{key}", "[]") or "[]")
    except ValueError:
        return []


def _write(name, key, items):
    from . import team
    if team.folder():
        team.write_shared(name, {key: items})
    settings.set(f"changequeue/{key}", json.dumps(items))


def queue() -> list[dict]:
    return _read("change_queue.json", "items")


def save_queue(items: list[dict]):
    _write("change_queue.json", "items", items)


def freezes() -> list[dict]:
    return _read("change_freezes.json", "freezes")


def save_freezes(items: list[dict]):
    _write("change_freezes.json", "freezes", items)


def add(commands: list[list[str]], when: str, title: str, who: str, request: str = "") -> dict:
    items = queue()
    it = {"id": uuid.uuid4().hex[:8], "when": when, "commands": commands, "title": title,
          "by": who, "request": request, "status": "waiting", "result": "",
          "added": datetime.datetime.now().isoformat(timespec="minutes")}
    items.append(it)
    save_queue(items)
    return it


def tonight(hour: int = 22) -> str:
    now = datetime.datetime.now()
    t = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if t <= now:
        t += datetime.timedelta(days=1)
    return t.isoformat(timespec="minutes")


def new_freeze(name: str, start: str, end: str, categories: list[str], who: str) -> dict:
    return {"id": uuid.uuid4().hex[:6], "name": name, "start": start, "end": end,
            "categories": categories or list(RISKY_DEFAULT), "by": who}


def active_freeze(args: list[str], when: datetime.datetime | None = None,
                  items: list[dict] | None = None) -> dict | None:
    """The freeze that blocks this command right now, if any."""
    from . import team
    from .activity import is_change
    if not is_change(args):
        return None
    t = (when or datetime.datetime.now()).isoformat(timespec="minutes")
    cats = team.categorize(args)
    for f in items if items is not None else freezes():
        a, b = span(f)
        if a <= t <= b and cats & set(f.get("categories", RISKY_DEFAULT)):
            return f
    return None


def span(f: dict) -> tuple[str, str]:
    a, b = f.get("start", "") or "0000", f.get("end", "") or "9999"
    if len(a) == 10:
        a += "T00:00"
    if len(b) == 10:
        b += "T23:59"
    return a, b


def log_override(args: list[str], freeze: dict, reason: str, who: str):
    from . import activity
    activity.record(list(args), 0, "override", None,
                    settings.get("profile/current", "") or "Default",
                    note=f"change freeze “{freeze['name']}” overridden by {who}: {reason}")


def due(items: list[dict], now: datetime.datetime | None = None) -> list[dict]:
    t = (now or datetime.datetime.now()).isoformat(timespec="minutes")
    return [i for i in items if i["status"] == "waiting" and i["when"] <= t]


def run_due(log=print, run_text=None, now=None) -> list[str]:
    """Background: run queued changes that are due (held back during a freeze)."""
    from . import activity, team
    from .directory import run_gam_text
    run_text = run_text or run_gam_text
    items = queue()
    lines = []
    if settings.get("safety/dry_run", False):
        return lines
    for it in due(items, now):
        blocked = next((active_freeze(c, now) for c in it["commands"]
                        if active_freeze(c, now)), None)
        if blocked:
            if it.get("held") != blocked["id"]:
                it["held"] = blocked["id"]
                lines.append(f"“{it['title']}” is waiting – change freeze “{blocked['name']}” "
                             f"until {blocked['end']}.")
            continue
        bad = 0
        it["status"] = "running"          # saved first so another PC won't run it too
        save_queue(items)
        for cmd in it["commands"]:
            try:
                c, _out = run_text(cmd, 600)
            except Exception:  # noqa: BLE001
                c = 1
            bad += 1 if c else 0
            activity.record(cmd, c, "done" if c == 0 else "failed", None,
                            settings.get("profile/current", "") or "Default",
                            note=f"run later “{it['title']}” (queued by {it['by']})")
        it["status"] = "done" if not bad else "failed"
        it["result"] = f"{len(it['commands']) - bad} ok, {bad} failed"
        it["ran"] = datetime.datetime.now().isoformat(timespec="minutes")
        lines.append(f"Ran “{it['title']}”: {it['result']}")
        if it.get("request") and team.folder():
            req = next((r for r in team.list_requests() if r["id"] == it["request"]), None)
            if req:
                team.update_request(req, it["status"], result=it["result"] + " (run later)")
        save_queue(items)
    save_queue(items)
    for ln in lines:
        log(ln)
    return lines
