"""Chromebook redistribution: find Chromebooks nobody is using at one school while another
school is short, and suggest moves. "Not used" = no check-in for N days, or (when Chrome
activity is available) less than a few minutes of use in the last 30 days."""

from __future__ import annotations

import datetime
import json
from collections import defaultdict

from ..settings import settings


def options() -> dict:
    try:
        o = json.loads(settings.get("redistribute/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"device_root": "/Chromebooks", "student_root": "/Students", "depth": 1,
            "idle_days": 30, "min_minutes": 30, "ratio": 1.0, "spare_pct": 5, **o}


def save_options(o: dict):
    settings.set("redistribute/options", json.dumps(o))


def _school(ou: str, root: str, depth: int = 1) -> str:
    ou, root = (ou or "/").rstrip("/"), (root or "/").rstrip("/")
    if root and ou.lower().startswith(root.lower() + "/"):
        rest = ou[len(root):].strip("/").split("/")
        return "/".join(rest[:max(1, depth)])
    return ""


def plan(devs: list[dict], users: list[dict], opts: dict,
         minutes: dict[str, dict] | None = None,
         today: datetime.date | None = None) -> tuple[list[dict], list[dict]]:
    """→ (per-school rows, suggested moves [{Serial, From, To, Why, args}])"""
    today = today or datetime.date.today()
    droot, sroot = opts.get("device_root", "/Chromebooks"), opts.get("student_root", "/Students")
    depth = int(opts.get("depth", 1) or 1)
    cut = today - datetime.timedelta(days=int(opts.get("idle_days", 30) or 30))
    minm = int(opts.get("min_minutes", 30) or 0)
    students = defaultdict(int)
    for u in users:
        if not u.get("suspended"):
            s = _school(u.get("ou", ""), sroot, depth)
            if s:
                students[s] += 1
    working, idle = defaultdict(list), defaultdict(list)
    for d in devs:
        if d.get("status", "ACTIVE") != "ACTIVE":
            continue
        s = _school(d.get("ou", ""), droot, depth)
        if not s:
            continue
        if d.get("aue") and d["aue"] < today:
            continue
        use = (minutes or {}).get((d.get("serial") or "").upper())
        is_idle = (d.get("last_sync") is None or d["last_sync"] < cut) or \
            (minutes is not None and (use is None or use["minutes"] < minm))
        (idle if is_idle else working)[s].append(d)
    ratio = float(opts.get("ratio", 1.0) or 1.0)
    spare = float(opts.get("spare_pct", 5) or 0) / 100
    rows, need, extra = [], {}, {}
    for s in sorted(set(students) | set(working) | set(idle)):
        want = int(round(students.get(s, 0) * ratio * (1 + spare)))
        have = len(working[s]) + len(idle[s])
        short = max(0, want - len(working[s]) - len(idle[s]))
        surplus = max(0, have - want)
        need[s], extra[s] = short, min(surplus, len(idle[s]))
        rows.append({"School": s, "Students": students.get(s, 0), "Used": len(working[s]),
                     "Not used": len(idle[s]), "Needed": want, "Short": short,
                     "Could give": extra[s]})
    moves = []
    givers = sorted((s for s in extra if extra[s]), key=lambda s: -extra[s])
    takers = sorted((s for s in need if need[s]), key=lambda s: -need[s])
    pool = {s: sorted(idle[s], key=lambda d: (d.get("aue") or datetime.date.max),
                      reverse=True)[:extra[s]] for s in givers}
    for t in takers:
        while need[t] > 0:
            g = next((s for s in givers if pool[s]), None)
            if not g:
                break
            d = pool[g].pop(0)
            need[t] -= 1
            target = f"{droot.rstrip('/')}/{t}"
            last = d["last_sync"].isoformat() if d.get("last_sync") else "never"
            moves.append({"Serial": d["serial"], "Asset": d.get("asset", ""),
                          "Model": d.get("model", ""), "From": g, "To": t,
                          "Why": f"not used at {g} (last check-in {last}); {t} is short",
                          "args": ["cros_sn", d["serial"], "update", "ou", target]})
    return rows, moves
