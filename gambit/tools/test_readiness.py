"""Testing-day device readiness: days before state testing, check every Chromebook in the
testing org units – enrolled and active, on a new-enough ChromeOS version, checked in
recently, not past its end of updates, and (optionally) that the testing app is set up for
kiosk in that org unit. Each school gets a list of devices that need attention."""

from __future__ import annotations

import datetime
import json
import re

from ..settings import settings

FIELDS = ("serialnumber,annotatedassetid,annotatedlocation,annotateduser,orgunitpath,status,"
          "osversion,lastsync,autoupdateexpiration,model")


def options() -> dict:
    try:
        o = json.loads(settings.get("testready/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"ous": [], "min_version": "", "sync_days": 7, "test_date": "", "app_id": "",
            "emails": "", **o}


def save_options(o: dict):
    settings.set("testready/options", json.dumps(o))


def devices_args(ou: str) -> list[str]:
    return ["print", "cros", "cros_ou_and_children", ou, "fields", FIELDS]


def app_args(ou: str, app_id: str) -> list[str]:
    aid = app_id if ":" in app_id else f"chrome:{app_id}"
    return ["print", "chromepolicies", "ou", ou, "appid", aid, "formatjson"]


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _ver(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4])


def _date(t):
    try:
        return datetime.date.fromisoformat((t or "")[:10])
    except ValueError:
        return None


def check(rows: list[dict], opts: dict, today: datetime.date | None = None,
          app_ok: dict[str, bool] | None = None) -> list[dict]:
    today = today or datetime.date.today()
    test = _date(opts.get("test_date")) or today
    minv = _ver(opts.get("min_version", ""))
    sync_cut = today - datetime.timedelta(days=int(opts.get("sync_days", 7) or 7))
    out = []
    for r in rows:
        low = _low(r)
        sn = low.get("serialnumber", "")
        if not sn:
            continue
        probs = []
        st = low.get("status", "").upper()
        if st and st != "ACTIVE":
            probs.append(f"status {st.lower()}")
        ver = low.get("osversion", "")
        if minv and (not ver or _ver(ver) < minv):
            probs.append(f"ChromeOS {ver or '?'} (needs {opts['min_version']}+)")
        ls = _date(low.get("lastsync"))
        if ls is None or ls < sync_cut:
            probs.append("hasn't checked in since " + (ls.isoformat() if ls else "ever"))
        aue = _date(low.get("autoupdateexpiration"))
        if aue and aue < test:
            probs.append(f"past end of updates ({aue.isoformat()})")
        ou = low.get("orgunitpath", "")
        if app_ok is not None:
            hits = [k for k in app_ok if ou == k or ou.startswith(k.rstrip("/") + "/")]
            ok = app_ok[max(hits, key=len)] if hits else None     # closest org unit
            if ok is False:
                probs.append("testing app not set up for this org unit")
        out.append({"Serial": sn, "Asset": low.get("annotatedassetid", ""),
                    "Location": low.get("annotatedlocation", ""), "Org unit": ou,
                    "ChromeOS": ver, "Last check-in": ls.isoformat() if ls else "",
                    "Ready": "✔" if not probs else "✖", "Problems": "; ".join(probs),
                    "ok": not probs, "needs_update": any("ChromeOS" in p for p in probs)})
    return sorted(out, key=lambda x: (x["ok"], x["Org unit"], x["Location"], x["Serial"]))


def by_place(results: list[dict]) -> list[dict]:
    by = {}
    for r in results:
        k = (r["Org unit"], r["Location"])
        b = by.setdefault(k, {"Org unit": k[0], "Location": k[1] or "–", "Devices": 0,
                              "Ready": 0, "Not ready": 0})
        b["Devices"] += 1
        b["Ready" if r["ok"] else "Not ready"] += 1
    return sorted(by.values(), key=lambda b: (-b["Not ready"], b["Org unit"]))


def app_configured(rows: list[dict]) -> bool:
    return any((r.get("JSON") or r.get("name")) for r in rows)


def reboot_args(serial: str) -> list[str]:
    return ["cros_sn", serial, "issuecommand", "command", "reboot", "doit"]


def ous_from_plans() -> list[str]:
    try:
        from . import policy_sets as ps
        out = []
        for p in ps.load():
            if p.get("kind") == "testing":
                out += p.get("targets", [])
        return list(dict.fromkeys(out))
    except Exception:  # noqa: BLE001
        return []


def summary_text(results: list[dict], opts: dict) -> str:
    bad = [r for r in results if not r["ok"]]
    lines = [f"Testing-day device check ({len(results) - len(bad)} of {len(results)} ready)."]
    if opts.get("test_date"):
        lines.append(f"Testing starts {opts['test_date']}.")
    for b in by_place(results):
        if b["Not ready"]:
            lines.append(f"\n{b['Org unit']} – {b['Location']}: {b['Not ready']} not ready")
            for r in bad:
                if (r["Org unit"], r["Location"] or "–") == (b["Org unit"], b["Location"]):
                    lines.append(f"  • {r['Serial']} {r['Asset']} – {r['Problems']}")
    return "\n".join(lines)
