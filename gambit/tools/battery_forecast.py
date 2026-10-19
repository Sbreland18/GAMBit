"""Battery replacement forecast: each Chromebook reports its battery's full-charge capacity
over time. GAMbit fits the trend and predicts when each battery falls below your
replacement level, then builds an order list by school and model for the year."""

from __future__ import annotations

import datetime
import json
import re
from collections import defaultdict

from ..settings import settings

# telemetry has no model or OU path fields: the OU comes from `showorgunitpath` and the model
# from a separate `print cros` read (models_args) merged in with add_models()
FIELDS = "serialnumber,batteryinfo,batterystatusreport"


def options() -> dict:
    try:
        o = json.loads(settings.get("battery/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"ou": "/", "replace_at": 60, "by": "", "reports": 30, "depth": 1,
            "device_root": "/Chromebooks", "battery_cost": 45.0, **o}


def save_options(o: dict):
    settings.set("battery/options", json.dumps(o))


def args(ou: str, reports: int = 30) -> list[str]:
    return ["print", "crostelemetry", "ou_and_children", ou or "/", "fields", FIELDS,
            "showorgunitpath", "listlimit", str(reports)]


def models_args(ou: str) -> list[str]:
    return ["print", "cros", "cros_ou_and_children", ou or "/", "fields",
            "serialnumber,model"]


def add_models(rows: list[dict], cros_rows: list[dict]) -> list[dict]:
    model = {}
    for r in cros_rows or []:
        low = {(k or "").lower(): v for k, v in r.items()}
        if low.get("serialnumber"):
            model[low["serialnumber"].upper()] = low.get("model", "")
    out = []
    for r in rows:
        low = {(k or "").lower(): v for k, v in r.items()}
        sn = (low.get("serialnumber") or "").upper()
        out.append({**r, "model": r.get("model") or model.get(sn, "")})
    return out


def _num(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _date(v: str):
    try:
        return datetime.date.fromisoformat((v or "")[:10])
    except ValueError:
        return None


def points(row: dict) -> tuple[float, list[tuple[datetime.date, float]]]:
    """(design capacity, [(date, health %)]) from one telemetry row."""
    low = {(k or "").lower(): v for k, v in row.items()}
    design = next((_num(v) for k, v in low.items() if k.endswith("designcapacity") and v), 0)
    reports = defaultdict(dict)
    for k, v in low.items():
        m = re.match(r"batterystatusreport\.(\d+)\.(fullchargecapacity|reporttime)$", k)
        if m and v:
            reports[m.group(1)][m.group(2)] = v
    pts = []
    for rep in reports.values():
        d, full = _date(rep.get("reporttime", "")), _num(rep.get("fullchargecapacity"))
        if d and full and design:
            pts.append((d, round(100 * full / design, 1)))
    return design, sorted(pts)


def predict(pts: list[tuple[datetime.date, float]], replace_at: float,
            today: datetime.date | None = None) -> dict:
    today = today or datetime.date.today()
    if not pts:
        return {"now": None, "per_month": None, "when": ""}
    now = pts[-1][1]
    if now <= replace_at:
        return {"now": now, "per_month": None, "when": "now"}
    if len(pts) < 2 or (pts[-1][0] - pts[0][0]).days < 14:
        return {"now": now, "per_month": None, "when": ""}
    xs = [p[0].toordinal() for p in pts]
    ys = [p[1] for p in pts]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0
    if slope >= 0:
        return {"now": now, "per_month": round(slope * 30.4, 2), "when": "not soon"}
    day = xs[-1] + (replace_at - now) / slope
    when = datetime.date.fromordinal(int(day))
    return {"now": now, "per_month": round(slope * 30.4, 2),
            "when": when.isoformat() if when > today else "now"}


def forecast(rows: list[dict], opts: dict, today: datetime.date | None = None) -> list:
    today = today or datetime.date.today()
    by = (opts.get("by") or "").strip() or f"{today.year + (1 if today.month > 6 else 0)}-06-30"
    out = []
    for r in rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        sn = low.get("serialnumber", "")
        if not sn:
            continue
        _d, pts = points(r)
        p = predict(pts, float(opts.get("replace_at", 60)), today)
        if p["now"] is None:
            continue
        due = p["when"] == "now" or (p["when"] not in ("", "not soon") and p["when"] <= by)
        out.append({"Serial": sn, "Model": low.get("model", ""),
                    "Org unit": low.get("orgunitpath", ""), "Battery now": f"{p['now']}%",
                    "Change per month": "" if p["per_month"] is None else
                    f"{p['per_month']}%", "Below the line": p["when"] or "not enough data",
                    "Replace by": "yes" if due else "", "due": due})
    return sorted(out, key=lambda x: (not x["due"], x["Below the line"]))


def order_list(fc: list[dict], opts: dict) -> list[dict]:
    root = (opts.get("device_root") or "/").rstrip("/")
    depth = int(opts.get("depth", 1) or 1)
    by = defaultdict(int)
    for f in fc:
        if not f["due"]:
            continue
        ou = f["Org unit"]
        rest = ou[len(root):].strip("/").split("/") if ou.lower().startswith(root.lower()) \
            else ou.strip("/").split("/")
        school = "/".join(rest[:depth]) or "(top)"
        by[(school, f["Model"] or "Unknown model")] += 1
    cost = float(opts.get("battery_cost", 0) or 0)
    return [{"School": s, "Model": m, "Batteries": n, "Estimated cost": round(n * cost, 2)}
            for (s, m), n in sorted(by.items())]
