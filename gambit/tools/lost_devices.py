"""Lost and stolen Chromebooks: mark a device lost and GAMbit disables it (the disabled
screen shows your “return to” message), moves it to a Lost org unit if you have one, records
its last user, last sign-in and last network, opens a ticket and builds a report for
insurance or the police. When it turns up, one click re-enables it and puts it back."""

from __future__ import annotations

import datetime
import html
import json
import os

from ..settings import settings

INFO_FIELDS = ("serialnumber,annotatedassetid,annotateduser,annotatedlocation,orgunitpath,"
               "status,model,lastsync,recentusers,lastknownnetwork,macaddress,"
               "ethernetmacaddress,autoupdateexpiration,deviceid,notes")


def options() -> dict:
    try:
        o = json.loads(settings.get("lost/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"lost_ou": "", "message": "", **o}


def save_options(o: dict):
    settings.set("lost/options", json.dumps(o))


def info_args(serial: str) -> list[str]:
    return ["cros_sn", serial, "print", "cros", "fields", INFO_FIELDS, "listlimit", "1"]


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def facts(row: dict) -> dict:
    low = _low(row)
    return {"serial": low.get("serialnumber", "").upper(),
            "asset": low.get("annotatedassetid", ""), "user": low.get("annotateduser", ""),
            "location": low.get("annotatedlocation", ""), "ou": low.get("orgunitpath", ""),
            "status": low.get("status", ""), "model": low.get("model", ""),
            "last_sync": low.get("lastsync", ""),
            "last_user": low.get("recentusers.0.email", "") or low.get("recentusers", "")
            .split(" ")[0],
            "last_ip": low.get("lastknownnetwork.0.ipaddress", "") or
            low.get("lastknownnetwork.ipaddress", ""),
            "last_wan_ip": low.get("lastknownnetwork.0.wanipaddress", ""),
            "mac": low.get("macaddress", ""), "device_id": low.get("deviceid", ""),
            "aue": low.get("autoupdateexpiration", "")}


def _store() -> str:
    from .. import fleet
    d = fleet.data_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "lost_devices.json")


def load() -> list[dict]:
    try:
        with open(_store(), encoding="utf-8") as fh:
            items = json.load(fh)
    except (OSError, ValueError):
        return []
    return [r for r in items if isinstance(r, dict) and r.get("serial")] \
        if isinstance(items, list) else []


def save(items: list[dict]):
    p = _store()
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=1)
    os.replace(p + ".tmp", p)


def mark_commands(f: dict, how: str, opts: dict) -> list[list[str]]:
    sn = f["serial"]
    note = f"{how.upper()} {datetime.date.today()} – last user {f['last_user'] or f['user'] or '?'}"
    cmds = [["cros_sn", sn, "update", "updatenotes", note[:400] + "\n#notes#"]]
    if f["status"].upper() != "DISABLED":
        cmds.append(["cros_sn", sn, "update", "action", "disable"])
    if opts.get("lost_ou"):
        cmds.append(["cros_sn", sn, "update", "ou", opts["lost_ou"]])
    return cmds


def found_commands(rec: dict) -> list[list[str]]:
    sn = rec["serial"]
    cmds = [["cros_sn", sn, "update", "action", "reenable"],
            ["cros_sn", sn, "update", "notes",
             f"Found {datetime.date.today()} (was {rec['how']} {rec['date']})"]]
    if rec.get("ou_before") and rec.get("moved", True):
        cmds.append(["cros_sn", sn, "update", "ou", rec["ou_before"]])
    return cmds


def record(f: dict, how: str, reported_by: str, details: str, who: str) -> dict:
    items = load()
    rec = {"serial": f["serial"], "how": how, "date": datetime.date.today().isoformat(),
           "reported_by": reported_by, "details": details, "by": who, "facts": f,
           "ou_before": f["ou"], "status": "missing", "ticket": "", "found": ""}
    items = [i for i in items if not (i["serial"] == f["serial"] and i["status"] == "missing")]
    items.append(rec)
    save(items)
    return rec


def report_html(rec: dict, district: str = "") -> str:
    esc = html.escape
    f = rec["facts"]
    rows = [("Serial number", f["serial"]), ("Asset tag", f["asset"]), ("Model", f["model"]),
            ("Assigned to", f["user"]), ("Last person signed in", f["last_user"]),
            ("Last check-in with Google", f["last_sync"]),
            ("Last known IP address (local / public)",
             " / ".join(x for x in (f["last_ip"], f["last_wan_ip"]) if x)),
            ("MAC address", f["mac"]), ("Google device ID", f["device_id"]),
            ("Reported", f"{rec['how']} on {rec['date']} by {rec['reported_by']}"),
            ("Details", rec["details"]),
            ("What the district did", "Device disabled remotely in Google Admin (it shows a "
                                      "return message and can't be used)" +
             ("; moved to the lost org unit" if rec.get("moved") else "")),
            ("Help-desk ticket", rec.get("ticket", ""))]
    tr = "".join(f"<tr><th style='text-align:left;padding:6px 12px;border-bottom:1px solid "
                 f"#d0d7de'>{esc(k)}</th><td style='padding:6px 12px;border-bottom:1px solid "
                 f"#d0d7de'>{esc(str(v or '–'))}</td></tr>" for k, v in rows)
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>Chromebook "
            f"{esc(f['serial'])}</title></head><body style='font-family:Arial,sans-serif'>"
            f"<h2>{esc(district + ' – ' if district else '')}Lost / stolen Chromebook report"
            f"</h2><table style='border-collapse:collapse'>{tr}</table><p style='color:#57606a'>"
            f"Prepared {datetime.date.today():%B %d, %Y} with GAMbit from Google Admin data."
            "</p></body></html>")
