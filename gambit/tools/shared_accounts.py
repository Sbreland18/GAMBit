"""Shared-password detection: student accounts signed in on many Chromebooks, or from
several places at nearly the same time – a sign the password is being shared (or was
stolen), which matters most for testing integrity. Also the "impossible travel" check the
nightly Unusual-activity watch uses."""

from __future__ import annotations

import datetime
import json
import re
from collections import defaultdict

from ..settings import settings

DEVICES_ARGS = ["print", "cros", "fields", "serialnumber,annotateduser,annotatedlocation,"
                "orgunitpath,recentusers,lastsync"]


def options() -> dict:
    try:
        o = json.loads(settings.get("shared/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"root": "/Students", "devices": 4, "ignore_ous": "cart, loaner, testing",
            "ips": 4, "window_min": 10, "days": 7, **o}


def save_options(o: dict):
    settings.set("shared/options", json.dumps(o))


def login_args(days: int) -> list[str]:
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    return ["report", "login", "user", "all", "start", start, "events", "login_success"]


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _t(s: str):
    try:
        return datetime.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def device_spread(rows: list[dict], opts: dict) -> dict[str, list[str]]:
    """student → serials whose recent users include them (ignoring carts etc.)."""
    skip = [w.strip().lower() for w in (opts.get("ignore_ous") or "").split(",") if w.strip()]
    out = defaultdict(set)
    for r in rows:
        low = _low(r)
        sn = low.get("serialnumber", "")
        where = (low.get("orgunitpath", "") + " " + low.get("annotatedlocation", "")).lower()
        if not sn or any(w in where for w in skip):
            continue
        for k, v in low.items():
            if re.match(r"recentusers(\.\d+)?\.email$", k) and "@" in v:
                out[v.lower()].add(sn)
    return {k: sorted(v) for k, v in out.items()}


def login_spread(rows: list[dict], window_min: int = 10) -> dict[str, dict]:
    """user → {ips per day max, near-simultaneous sign-ins from different places}"""
    by = defaultdict(list)
    for r in rows:
        low = _low(r)
        who = low.get("actor.email", "").lower()
        t = _t(low.get("id.time", ""))
        ip = low.get("ipaddress", "")
        if who and t and ip:
            by[who].append((t, ip, low.get("networkinfo.subdivisioncode", "") or
                            low.get("networkinfo.regioncode", "")))
    out = {}
    for who, evs in by.items():
        evs.sort()
        per_day = defaultdict(set)
        for t, ip, _r in evs:
            per_day[t.date()].add(ip)
        near = 0
        for (t1, ip1, _a), (t2, ip2, _b) in zip(evs, evs[1:]):
            if ip1 != ip2 and (t2 - t1).total_seconds() <= window_min * 60:
                near += 1
        out[who] = {"max_ips": max((len(v) for v in per_day.values()), default=0),
                    "near": near}
    return out


def flag(users: list[dict], devices: dict[str, list[str]], logins: dict[str, dict],
         opts: dict) -> list[dict]:
    root = opts.get("root", "/Students").rstrip("/").lower()
    ou_of = {u["email"].lower(): u.get("ou", "") for u in users}
    out = []
    for who in sorted(set(devices) | set(logins)):
        ou = ou_of.get(who, "")
        if root and not (ou.lower() == root or ou.lower().startswith(root + "/")):
            continue
        sig = []
        devs = devices.get(who, [])
        if len(devs) >= int(opts.get("devices", 4)):
            sig.append(f"signed in on {len(devs)} Chromebooks")
        lg = logins.get(who, {})
        if lg.get("max_ips", 0) >= int(opts.get("ips", 4)):
            sig.append(f"{lg['max_ips']} different networks in one day")
        if lg.get("near"):
            sig.append(f"{lg['near']} sign-in(s) from different places within "
                       f"{opts.get('window_min', 10)} min")
        if sig:
            out.append({"Student": who, "Org unit": ou, "Signs": len(sig),
                        "What we see": "; ".join(sig),
                        "Chromebooks": ", ".join(devs[:8])})
    return sorted(out, key=lambda x: (-x["Signs"], x["Student"]))


def impossible_travel(rows: list[dict], hours: float = 2.0) -> list[dict]:
    """Sign-ins to one account from two different regions within `hours`."""
    by = defaultdict(list)
    for r in rows:
        low = _low(r)
        who = low.get("actor.email", "").lower()
        t = _t(low.get("id.time", ""))
        reg = low.get("networkinfo.subdivisioncode", "") or low.get("networkinfo.regioncode",
                                                                     "")
        if who and t and reg:
            by[who].append((t, reg.upper(), low.get("ipaddress", "")))
    out = []
    for who, evs in by.items():
        evs.sort()
        for (t1, r1, ip1), (t2, r2, ip2) in zip(evs, evs[1:]):
            if r1 != r2 and (t2 - t1).total_seconds() <= hours * 3600:
                out.append({"who": who, "from": r1, "to": r2,
                            "minutes": round((t2 - t1).total_seconds() / 60),
                            "ips": f"{ip1} → {ip2}"})
                break
    return out
