"""Budget planner: licenses that could be freed (held by suspended, long-inactive or
never-used accounts) with their yearly cost, and Chromebook replacements by school and
school year from the end-of-updates dates."""

from __future__ import annotations

import datetime
import json
import re
from collections import defaultdict

from ..settings import settings

USERS_ARGS = ["print", "users", "fields", "primaryemail,suspended,lastlogintime,ou", "licenses"]


def options() -> dict:
    try:
        o = json.loads(settings.get("budget/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"inactive_days": 180, "prices": {}, "device_cost": float(
        settings.get("fleet/cost", 300) or 300), "device_root": "/Chromebooks",
        "school_depth": 1, "years": 5, **o}


def save_options(o: dict):
    settings.set("budget/options", json.dumps(o))


def _low(r: dict) -> dict:
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _date(text: str):
    t = (text or "").strip()
    if not t or t.lower().startswith("never") or t.startswith("1970"):
        return None
    try:
        return datetime.date.fromisoformat(t[:10])
    except ValueError:
        return None


def license_holders(rows: list[dict]) -> list[dict]:
    """GAM print users … licenses → [{email, suspended, last, ou, skus:[…]}]"""
    out = []
    for r in rows:
        low = _low(r)
        e = (low.get("primaryemail") or "").lower()
        if not e:
            continue
        skus = []
        for k, v in low.items():
            if k.startswith("licenses") and "display" not in k and "count" not in k and v:
                skus += [s for s in re.split(r"[ ,]+", v) if s]
        out.append({"email": e, "suspended": low.get("suspended", "").lower() == "true",
                    "last": _date(low.get("lastlogintime", "")), "ou": low.get("orgunitpath", ""),
                    "skus": sorted(set(skus))})
    return out


def sku_name(sku: str) -> str:
    try:
        from ..ui.pages.licenses import SKUS
        return next((n for n, s in SKUS if s == sku), sku)
    except Exception:  # noqa: BLE001
        return sku


def reclaimable(holders: list[dict], inactive_days: int, prices: dict,
                today: datetime.date | None = None) -> tuple[list[dict], list[dict]]:
    """→ (per-SKU summary rows, per-account detail rows)"""
    today = today or datetime.date.today()
    cut = today - datetime.timedelta(days=inactive_days)
    by = defaultdict(lambda: {"held": 0, "suspended": 0, "inactive": 0, "never": 0})
    detail = []
    for h in holders:
        why = ""
        if h["suspended"]:
            why = "suspended"
        elif h["last"] is None:
            why = "never signed in"
        elif h["last"] < cut:
            why = f"no sign-in since {h['last'].isoformat()}"
        for sku in h["skus"]:
            b = by[sku]
            b["held"] += 1
            if why == "suspended":
                b["suspended"] += 1
            elif why == "never signed in":
                b["never"] += 1
            elif why:
                b["inactive"] += 1
            if why:
                detail.append({"Account": h["email"], "License": sku_name(sku), "sku": sku,
                               "Why": why, "Org unit": h["ou"],
                               "args": ["user", h["email"], "delete", "license", sku]})
    rows = []
    for sku, b in sorted(by.items(), key=lambda kv: -kv[1]["held"]):
        free = b["suspended"] + b["inactive"] + b["never"]
        price = float(prices.get(sku, 0) or 0)
        rows.append({"License": sku_name(sku), "sku": sku, "Assigned": b["held"],
                     "Suspended": b["suspended"], "Inactive": b["inactive"],
                     "Never used": b["never"], "Could free": free,
                     "Price / year": price, "Savings / year": free * price})
    detail.sort(key=lambda d: (d["License"], d["Why"], d["Account"]))
    return rows, detail


def school_of_device(d: dict, root: str, depth: int, user_school: dict) -> str:
    from .automation import school_of
    s = user_school.get((d.get("user") or "").lower())
    if s:
        return s
    ou = d.get("ou", "") or "/"
    if root and (ou.lower() + "/").startswith(root.rstrip("/").lower() + "/"):
        return school_of(ou, root, depth) or "(top level)"
    return ou.strip("/").split("/")[0] or "(top level)"


def device_plan(devs: list[dict], opts: dict, user_school: dict | None = None,
                today: datetime.date | None = None) -> tuple[list[str], list[list[str]], dict]:
    """School × school-year table of devices whose updates end, with costs."""
    today = today or datetime.date.today()
    cost = float(opts.get("device_cost", 300) or 0)
    years = int(opts.get("years", 5) or 5)
    this_end = today.year + (1 if today.month > 6 else 0)
    cols = ["Expired"] + [f"{y - 1}-{str(y)[-2:]}" for y in range(this_end, this_end + years)]
    grid = defaultdict(lambda: defaultdict(int))
    for d in devs:
        if d.get("status", "ACTIVE") != "ACTIVE" or not d.get("aue"):
            continue
        y = d["aue"].year if d["aue"].month <= 6 else d["aue"].year + 1
        if d["aue"] < today:
            col = "Expired"
        elif y < this_end + years:
            col = f"{y - 1}-{str(y)[-2:]}"
        else:
            continue
        school = school_of_device(d, opts.get("device_root", ""), int(opts.get(
            "school_depth", 1) or 1), user_school or {})
        grid[school][col] += 1
    head = ["School"] + cols + ["Total devices", "Cost"]
    rows, totals = [], defaultdict(int)
    for school in sorted(grid):
        n = [grid[school][c] for c in cols]
        for c, v in zip(cols, n):
            totals[c] += v
        rows.append([school] + [str(v or "") for v in n] + [str(sum(n)),
                                                             f"${sum(n) * cost:,.0f}"])
    if rows:
        tn = [totals[c] for c in cols]
        rows.append(["All schools"] + [str(v) for v in tn] + [str(sum(tn)),
                                                              f"${sum(tn) * cost:,.0f}"])
    per_year = {c: totals[c] * cost for c in cols}
    return head, rows, per_year


def user_schools(users: list[dict], student_root: str = "/Students") -> dict:
    from .automation import school_of
    return {u["email"].lower(): school_of(u.get("ou", ""), student_root)
            for u in users if (u.get("ou", "") + "/").lower().startswith(
                student_root.rstrip("/").lower() + "/")}
