"""Asset register reconciliation: compare the finance/fixed-asset list (serial, asset tag,
purchase date, cost, location) with the Chromebooks Google knows about, and export one
inventory with age, straight-line depreciation and end of updates for the auditors."""

from __future__ import annotations

import csv
import datetime
import json
import re

from .settings import settings

FIELDS = {
    "serial": ["serial", "serialnumber", "serial number", "serial no", "sn", "serial #"],
    "asset": ["asset", "asset tag", "assettag", "asset id", "asset number", "tag", "asset #"],
    "purchased": ["purchase date", "purchased", "date purchased", "acquired", "in service",
                  "acquisition date", "date"],
    "cost": ["cost", "price", "purchase price", "amount", "value", "unit cost"],
    "location": ["location", "school", "building", "site", "campus"],
}


def options() -> dict:
    try:
        o = json.loads(settings.get("assetreg/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"life_years": 5, "salvage": 0.0, **o}


def save_options(o: dict):
    settings.set("assetreg/options", json.dumps(o))


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9# ]", "", (h or "").lower()).strip()


def mapping(headers: list[str]) -> dict[str, str]:
    """Guess which finance column is which: {field: header}."""
    out = {}
    normed = {_norm(h): h for h in headers}
    for field, names in FIELDS.items():
        for n in names:
            if n in normed:
                out[field] = normed[n]
                break
        else:
            for nh, h in normed.items():
                if any(n in nh for n in names[:2]):
                    out[field] = h
                    break
    return out


def _date(t: str):
    t = (t or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%d-%b-%Y", "%b %d, %Y"):
        try:
            return datetime.datetime.strptime(t[:12].strip(), fmt).date()
        except ValueError:
            continue
    try:
        return datetime.date.fromisoformat(t[:10])
    except ValueError:
        return None


def _money(t) -> float:
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(t or "")) or 0)
    except ValueError:
        return 0.0


def read_finance(path: str) -> tuple[list[dict], dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    m = mapping(list(rows[0].keys()) if rows else [])
    return parse_finance(rows, m), m


def parse_finance(rows: list[dict], m: dict) -> list[dict]:
    out = []
    for r in rows:
        sn = (r.get(m.get("serial", ""), "") or "").strip().upper()
        if not sn:
            continue
        out.append({"serial": sn, "asset": (r.get(m.get("asset", ""), "") or "").strip(),
                    "purchased": _date(r.get(m.get("purchased", ""), "")),
                    "cost": _money(r.get(m.get("cost", ""), "")),
                    "location": (r.get(m.get("location", ""), "") or "").strip()})
    return out


def depreciation(cost: float, purchased, today: datetime.date, life: int,
                 salvage: float = 0.0) -> tuple[float, float]:
    """Straight-line: (age in years, book value)."""
    if not purchased:
        return 0.0, cost
    age = max((today - purchased).days / 365.25, 0)
    life = max(int(life or 1), 1)
    per_year = (cost - salvage) / life
    return round(age, 1), round(max(cost - per_year * age, salvage), 2)


def reconcile(finance: list[dict], devices: list[dict]) -> list[dict]:
    """→ [{Serial, Problem, Finance tag, Google tag, Finance location, Google OU, User}]"""
    fin = {f["serial"]: f for f in finance}
    goo = {d["serial"].upper(): d for d in devices}
    out = []
    for sn, f in fin.items():
        d = goo.get(sn)
        if not d:
            out.append({"Serial": sn, "Problem": "Bought but never enrolled in Google",
                        "Finance tag": f["asset"], "Google tag": "",
                        "Finance location": f["location"], "Google OU": "", "User": ""})
        elif f["asset"] and d.get("asset") and f["asset"].lower() != d["asset"].lower():
            out.append({"Serial": sn, "Problem": "Asset tag doesn't match",
                        "Finance tag": f["asset"], "Google tag": d["asset"],
                        "Finance location": f["location"], "Google OU": d.get("ou", ""),
                        "User": d.get("user", "")})
        elif f["asset"] and not d.get("asset"):
            out.append({"Serial": sn, "Problem": "Asset tag missing in Google",
                        "Finance tag": f["asset"], "Google tag": "",
                        "Finance location": f["location"], "Google OU": d.get("ou", ""),
                        "User": d.get("user", "")})
    for sn, d in goo.items():
        if sn not in fin:
            out.append({"Serial": sn, "Problem": "In Google but not on the finance list",
                        "Finance tag": "", "Google tag": d.get("asset", ""),
                        "Finance location": "", "Google OU": d.get("ou", ""),
                        "User": d.get("user", "")})
    order = {"Bought but never enrolled in Google": 0, "In Google but not on the finance "
             "list": 1, "Asset tag doesn't match": 2, "Asset tag missing in Google": 3}
    return sorted(out, key=lambda x: (order.get(x["Problem"], 9), x["Serial"]))


def tag_fix_args(serial_to_device_id: dict, row: dict) -> list[str] | None:
    """Copy the finance tag into Google for a mismatch/missing row."""
    did = serial_to_device_id.get(row["Serial"])
    if not did or not row.get("Finance tag"):
        return None
    return ["update", "cros", did, "assetid", row["Finance tag"]]


def inventory(finance: list[dict], devices: list[dict], opts: dict | None = None,
              today: datetime.date | None = None) -> list[dict]:
    """One row per device on either list, for the auditors."""
    opts = opts or options()
    today = today or datetime.date.today()
    fin = {f["serial"]: f for f in finance}
    goo = {d["serial"].upper(): d for d in devices}
    out = []
    for sn in sorted(set(fin) | set(goo)):
        f, d = fin.get(sn, {}), goo.get(sn, {})
        age, book = depreciation(f.get("cost", 0.0), f.get("purchased"), today,
                                 int(opts.get("life_years", 5) or 5),
                                 float(opts.get("salvage", 0) or 0))
        aue = d.get("aue")
        out.append({"Serial": sn, "Asset tag": f.get("asset") or d.get("asset", ""),
                    "Model": d.get("model", ""),
                    "Purchased": f["purchased"].isoformat() if f.get("purchased") else "",
                    "Cost": f.get("cost", ""), "Age (years)": age if f else "",
                    "Book value": book if f else "",
                    "End of updates": aue.isoformat() if aue else "",
                    "Updates ended": "yes" if aue and aue < today else "",
                    "Status": d.get("status", "") or "NOT IN GOOGLE",
                    "Location": f.get("location") or d.get("location", ""),
                    "Org unit": d.get("ou", ""), "User": d.get("user", ""),
                    "Last check-in": d["last_sync"].isoformat() if d.get("last_sync") else "",
                    "On finance list": "yes" if f else "no"})
    return out


def totals(inv: list[dict]) -> dict:
    cost = sum(float(r["Cost"] or 0) for r in inv if r["Cost"] != "")
    book = sum(float(r["Book value"] or 0) for r in inv if r["Book value"] != "")
    return {"devices": len(inv), "cost": round(cost, 2), "book": round(book, 2),
            "expired": sum(1 for r in inv if r["Updates ended"])}


CROS_ARGS = ["print", "cros", "fields", "deviceid,serialnumber,annotatedassetid,"
             "annotatedlocation,annotateduser,orgunitpath,status,lastsync,"
             "autoupdateexpiration,model"]
