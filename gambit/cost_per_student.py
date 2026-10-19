"""Cost per student by school: Chromebooks (replacement cost spread over their supported
life), licenses, and repairs over the last 12 months, divided by each school's students –
for budget season."""

from __future__ import annotations

import datetime
import json
from collections import defaultdict

from .settings import settings


def options() -> dict:
    from .tools import budget
    b = budget.options()
    try:
        o = json.loads(settings.get("costper/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"student_root": "/Students", "device_root": b.get("device_root", "/Chromebooks"),
            "depth": int(b.get("school_depth", 1) or 1), "device_cost": b["device_cost"],
            "life_years": 5, "repair_cost": 60.0, "prices": b.get("prices", {}), **o}


def save_options(o: dict):
    settings.set("costper/options", json.dumps(o))


def _school(ou: str, root: str, depth: int) -> str:
    ou, root = (ou or "/").rstrip("/"), (root or "/").rstrip("/")
    if root and ou.lower().startswith(root.lower() + "/"):
        return "/".join(ou[len(root):].strip("/").split("/")[:depth])
    return ""


def compute(devs: list[dict], holders: list[dict], repairs: list[dict], users: list[dict],
            opts: dict, today: datetime.date | None = None) -> list[dict]:
    today = today or datetime.date.today()
    depth = int(opts.get("depth", 1) or 1)
    sroot, droot = opts["student_root"], opts["device_root"]
    by = defaultdict(lambda: {"students": 0, "devices": 0, "device_cost": 0.0,
                              "license_cost": 0.0, "repairs": 0})
    user_school = {}
    for u in users:
        s = _school(u.get("ou", ""), sroot, depth)
        if s and not u.get("suspended"):
            by[s]["students"] += 1
            user_school[u["email"].lower()] = s
    cost = float(opts.get("device_cost", 300) or 0)
    life = float(opts.get("life_years", 5) or 5)
    serial_school = {}
    for d in devs:
        if d.get("status", "ACTIVE") != "ACTIVE":
            continue
        s = _school(d.get("ou", ""), droot, depth) or user_school.get(
            (d.get("user") or "").lower(), "")
        if not s:
            continue
        serial_school[d["serial"].upper()] = s
        by[s]["devices"] += 1
        by[s]["device_cost"] += cost / life
    prices = {k: float(v or 0) for k, v in (opts.get("prices") or {}).items()}
    for h in holders:
        s = user_school.get(h["email"])
        if s:
            by[s]["license_cost"] += sum(prices.get(k, 0) for k in h["skus"])
    cut = (today - datetime.timedelta(days=365)).isoformat()
    for t in repairs:
        if t.get("opened", "") >= cut:
            s = serial_school.get((t.get("serial") or "").upper())
            if s:
                by[s]["repairs"] += 1
    rc = float(opts.get("repair_cost", 0) or 0)
    out = []
    for s, b in sorted(by.items()):
        rep = b["repairs"] * rc
        total = b["device_cost"] + b["license_cost"] + rep
        n = b["students"]
        out.append({"School": s, "Students": n, "Chromebooks": b["devices"],
                    "Devices per student": round(b["devices"] / n, 2) if n else "",
                    "Devices / year": round(b["device_cost"]),
                    "Licenses / year": round(b["license_cost"]),
                    "Repairs (12 mo)": b["repairs"], "Repairs cost": round(rep),
                    "Total / year": round(total),
                    "Per student": round(total / n, 2) if n else ""})
    if out:
        tot = {k: sum(r[k] for r in out if isinstance(r[k], (int, float))) for k in
               ("Students", "Chromebooks", "Devices / year", "Licenses / year",
                "Repairs (12 mo)", "Repairs cost", "Total / year")}
        out.append({"School": "District", **tot,
                    "Devices per student": round(tot["Chromebooks"] / tot["Students"], 2)
                    if tot["Students"] else "",
                    "Per student": round(tot["Total / year"] / tot["Students"], 2)
                    if tot["Students"] else ""})
    return out
