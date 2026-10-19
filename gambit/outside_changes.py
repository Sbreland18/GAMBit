"""Changes made outside GAMbit: compare Google's admin log with GAMbit's own activity log and
list the changes nobody made through GAMbit – console clicks, other scripts or a compromised
admin – with who made them."""

from __future__ import annotations

import datetime
import json

from .settings import settings

TARGETS = ["user_email", "group_email", "org_unit_name", "device_serial_number",
           "resource_identifier", "domain_name", "role_name", "setting_name",
           "application_name", "calendar_resource_name", "printer_name"]
WINDOW_MIN = 15


def options() -> dict:
    try:
        o = json.loads(settings.get("outside/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"days": 7, "ignore_actors": "", "ignore_events": "", **o}


def save_options(o: dict):
    settings.set("outside/options", json.dumps(o))


def admin_args(days: int) -> list[str]:
    return ["report", "admin", "user", "all", "start", f"-{int(days)}d"]


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _utc(t: str):
    t = (t or "").strip()
    if not t:
        return None
    try:
        d = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:          # GAMbit's log is local time
        d = d.astimezone()
    return d.astimezone(datetime.timezone.utc)


def _target(low: dict) -> str:
    for k in TARGETS:
        if low.get(k):
            return low[k]
    return ""


def _split(text: str) -> set[str]:
    return {x.strip().lower() for x in (text or "").replace(";", ",").split(",") if x.strip()}


def compare(admin_rows: list[dict], entries: list[dict], opts: dict | None = None) -> list[dict]:
    """→ admin-log changes with no matching GAMbit activity entry nearby in time."""
    opts = opts or options()
    skip_actor = _split(opts.get("ignore_actors", ""))
    skip_event = {e.upper() for e in _split(opts.get("ignore_events", ""))}
    ours = []
    for e in entries:
        if not e.get("change") or e.get("code") not in (0, None):
            continue
        t = _utc(e.get("time", ""))
        if t:
            ours.append((t, " ".join(str(a) for a in e.get("args") or []).lower(),
                         (e.get("command") or "").lower()))
    win = datetime.timedelta(minutes=WINDOW_MIN)
    out = []
    for r in admin_rows:
        low = _low(r)
        when = _utc(low.get("id.time", ""))
        actor = low.get("actor.email", "").lower()
        event = (low.get("name") or low.get("event") or low.get("events.0.name", "")).upper()
        if actor in skip_actor or event in skip_event or not when:
            continue
        target = _target(low)
        tl = target.lower()
        match = False
        for t, args, cmd in ours:
            if abs(t - when) <= win and (not tl or tl in args or tl in cmd):
                match = True
                break
        if match:
            continue
        out.append({"When": when.astimezone().strftime("%Y-%m-%d %H:%M"), "Who": actor,
                    "What": event.replace("_", " ").lower(), "Target": target,
                    "Details": ", ".join(f"{k}={v}" for k, v in low.items()
                                         if k in ("setting_name", "old_value", "new_value")
                                         and v)})
    return out


def summary(rows: list[dict]) -> list[dict]:
    by = {}
    for r in rows:
        b = by.setdefault(r["Who"] or "(unknown)", {"Who": r["Who"] or "(unknown)",
                                                    "Changes": 0, "Kinds": set()})
        b["Changes"] += 1
        b["Kinds"].add(r["What"])
    return [{"Who": b["Who"], "Changes": b["Changes"],
             "What": ", ".join(sorted(b["Kinds"]))[:200]}
            for b in sorted(by.values(), key=lambda x: -x["Changes"])]
