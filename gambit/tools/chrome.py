"""Chromebook and Chrome tools: remote commands, device health (telemetry), apps and
extensions, printers, and changing/copying Chrome policies between org units."""

from __future__ import annotations

import csv
import io
import json
import re

# ------------------------------------------------------------ commands ---
COMMANDS = [
    ("Restart", "reboot", "Restarts the Chromebook. Only works in kiosk mode or on the "
                          "sign-in screen; signed-in users are asked first."),
    ("Set the volume", "set_volume", "Sets the speaker volume (kiosk mode)."),
    ("Take a screenshot", "take_a_screenshot",
     "Kiosk mode only. The picture appears in the Admin console under the device."),
    ("Sign everyone out and remove their data", "wipe_users",
     "Removes all user profiles from the device. Cloud files are safe."),
    ("Powerwash (factory reset, stays enrolled)", "remote_powerwash",
     "Erases the device. It stays enrolled and in its org unit."),
]
DESTRUCTIVE = {"wipe_users", "remote_powerwash"}


def target(serials: list[str], ou: str, children: bool = True) -> list[str]:
    serials = [s.strip() for s in serials if s.strip()]
    if serials:
        return ["cros_sn", ",".join(serials)]
    return ["cros_ou_and_children" if children else "cros_ou", ou]


def command_args(entity: list[str], command: str, volume: int = 50) -> list[str]:
    args = [*entity, "issuecommand", "command", command]
    if command == "set_volume":
        args.append(str(max(0, min(100, int(volume)))))
    if command in DESTRUCTIVE:
        args.append("doit")
    return args + ["times_to_check_status", "1"]


# -------------------------------------------------------------- health ---
TELEMETRY_FIELDS = "serialnumber,batteryinfo,batterystatusreport,storageinfo,osupdatestatus"


def telemetry_args(ou: str) -> list[str]:
    return ["print", "crostelemetry", "ou_and_children", ou, "fields", TELEMETRY_FIELDS,
            "reverselists", "batterystatusreport", "listlimit", "1"]


def _col(row: dict, *suffixes) -> str:
    for k, v in row.items():
        kl = (k or "").lower()
        for s in suffixes:
            if kl.endswith(s.lower()) and v not in (None, ""):
                return v
    return ""


def _num(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def health(rows: list[dict], battery_warn: int = 70, storage_warn: int = 10) -> list[dict]:
    out = []
    for r in rows:
        serial = _col(r, "serialnumber")
        design = _num(_col(r, "designcapacity"))
        full = _num(_col(r, "fullchargecapacity"))
        pct = round(100 * full / design) if design and full else None
        cycles = _col(r, "cyclecount")
        bh = _col(r, "batteryhealth").replace("BATTERY_HEALTH_", "").replace("BATTERY_", "")
        total = _num(_col(r, "totaldiskbytes"))
        free = _num(_col(r, "availablediskbytes"))
        free_pct = round(100 * free / total) if total else None
        upd = _col(r, "updatestate").replace("UPDATE_STATE_", "").replace("_", " ").lower()
        flags = []
        if pct is not None and pct < battery_warn:
            flags.append(f"battery {pct}%")
        if bh and bh not in ("NORMAL", "UNSPECIFIED"):
            flags.append("battery: " + bh.replace("_", " ").lower())
        if free_pct is not None and free_pct < storage_warn:
            flags.append(f"storage {free_pct}% free")
        if "need" in upd and "reboot" in upd:
            flags.append("needs a restart to update")
        out.append({"Serial": serial,
                    "Battery health": f"{pct}%" if pct is not None else "",
                    "Charge cycles": cycles, "Storage free": f"{free_pct}%"
                    if free_pct is not None else "",
                    "Storage (GB)": f"{total / 1e9:.0f}" if total else "",
                    "OS update": upd, "Needs attention": "; ".join(flags)})
    out.sort(key=lambda x: (x["Needs attention"] == "", x["Serial"]))
    return out


# --------------------------------------------------------- apps / exts ---
RISKY_WORDS = ("vpn", "proxy", "unblock", "hide my", "hotspot", "answer", "cheat", "solver",
               "ai homework", "tor ", "incognito", "bypass", "game", "remote desktop")


def apps_args(ou: str) -> list[str]:
    return ["print", "chromeapps", "ou_and_children", ou, "orderby", "totalinstallcount"]


def app_devices_args(ou: str, app_id: str) -> list[str]:
    return ["print", "chromeappdevices", "ou_and_children", ou, "appid", app_id]


def apps(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = {(k or "").lower(): v or "" for k, v in r.items()}
        name = low.get("displayname", "")
        text = f"{name} {low.get('description', '')}".lower()
        hits = [w.strip() for w in RISKY_WORDS if w in text]
        installs = int(_num(low.get("browserdevicecount")) + _num(low.get("osusercount"))) \
            or int(_num(low.get("totalinstallcount")))
        out.append({"App": name or low.get("appid", ""), "Type": low.get("apptype", "").lower(),
                    "How installed": low.get("appinstalltype", "").lower(),
                    "Installs": str(installs), "Look at this": ", ".join(hits),
                    "App ID": low.get("appid", "")})
    out.sort(key=lambda x: (x["Look at this"] == "", -int(x["Installs"] or 0)))
    return out


# ------------------------------------------------------------ printers ---
PRINTER_COLS = {"name": ["name", "displayname", "printer", "printername"],
                "uri": ["uri", "address", "ip", "ipaddress", "url"],
                "ou": ["ou", "orgunit", "orgunitpath", "org unit"],
                "description": ["description", "location", "notes"],
                "model": ["model", "makeandmodel", "make and model", "driver"]}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def printers_from_csv(text: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if not rows:
        return []
    heads = {_norm(h): h for h in rows[0]}
    m = {k: next((heads[_norm(c)] for c in cands if _norm(c) in heads), None)
         for k, cands in PRINTER_COLS.items()}
    out = []
    for r in rows:
        p = {k: (r.get(c) or "").strip() if c else "" for k, c in m.items()}
        if p["name"] and p["uri"]:
            if "://" not in p["uri"]:
                p["uri"] = "ipp://" + p["uri"]
            out.append(p)
    return out


def printer_plan(wanted: list[dict], existing: list[dict]) -> list[dict]:
    have = {}
    for e in existing:
        low = {(k or "").lower(): v or "" for k, v in e.items()}
        have[_norm(low.get("displayname", ""))] = low
    plan = []
    for p in wanted:
        cur = have.get(_norm(p["name"]))
        attrs = ["displayname", p["name"], "uri", p["uri"]]
        if p["description"]:
            attrs += ["description", p["description"]]
        if p["model"]:
            attrs += ["makeandmodel", p["model"]]
        else:
            attrs += ["driverless", "true"]
        if cur is None:
            if not p["ou"]:
                plan.append({"action": "problem", "name": p["name"],
                             "details": "needs an org unit", "args": None})
                continue
            plan.append({"action": "create", "name": p["name"],
                         "details": f"{p['uri']} → {p['ou']}",
                         "args": ["create", "printer", *attrs, "ou", p["ou"]]})
        elif cur.get("uri", "") != p["uri"] or (p["description"] and
                                                cur.get("description", "") != p["description"]):
            plan.append({"action": "update", "name": p["name"],
                         "details": f"address {cur.get('uri', '')} → {p['uri']}",
                         "args": ["update", "printer", cur.get("id", ""), *attrs]})
        else:
            plan.append({"action": "same", "name": p["name"], "details": "already set up",
                         "args": None})
    return plan


PRINTER_TEMPLATE = ("Name,Address,Org unit,Description,Make and model\n"
                    "Lincoln Library Printer,10.1.20.15,/Students/Lincoln Elementary,"
                    "Library – by the circulation desk,\n"
                    "HS Room 204,ipp://10.2.4.204/ipp/print,/Staff/High School,,\n")


# ------------------------------------------------------------ policies ---
def schemas_args(text: str = "") -> list[str]:
    args = ["print", "chromeschemas"]
    if text:
        args += ["filter", text]
    return args + ["formatjson"]


def parse_schemas(rows: list[dict]) -> list[dict]:
    """→ [{schema, description, fields: [{name, description, values: [(value, text)]}]}]"""
    out = []
    for r in rows:
        try:
            j = json.loads(r.get("JSON") or "{}")
        except ValueError:
            continue
        name = j.get("schemaName") or (r.get("name") or "").split("/")[-1]
        fields = []
        for fd in j.get("fieldDescriptions", []) or []:
            vals = [(str(kv.get("value", "")).split("_ENUM_")[-1], kv.get("description", ""))
                    for kv in fd.get("knownValueDescriptions", []) or []]
            fields.append({"name": fd.get("field", ""), "description":
                           fd.get("description", ""), "values": vals})
        out.append({"schema": name, "description": j.get("policyDescription", "")
                    or r.get("policyDescription", ""), "fields": fields})
    out.sort(key=lambda s: s["schema"])
    return out


def policy_args(schema: str, values: dict[str, str], ou: str) -> list[str]:
    args = ["update", "chromepolicy", schema]
    for k, v in values.items():
        args += [k, v]
    return args + ["ou", ou]


def direct_policies_args(ou: str) -> list[str]:
    return ["print", "chromepolicies", "ou", ou, "show", "direct", "formatjson"]


def copy_plan(rows: list[dict], target_ou: str) -> tuple[list[dict], list[str]]:
    """Policies set directly on the source OU → update commands for the target OU."""
    plan, skipped = [], []
    for r in rows:
        try:
            p = json.loads(r.get("JSON") or "{}")
        except ValueError:
            continue
        if not p.get("direct", True) or p.get("appId") or p.get("printerId"):
            continue
        name = p.get("name", "")
        vals, bad = {}, []
        for f in p.get("fields", []):
            v = f.get("value", "")
            if isinstance(v, (dict, list)) or (isinstance(v, str) and v.startswith(("[{", "{"))):
                bad.append(f.get("name", ""))
                continue
            vals[f.get("name", "")] = "true" if v is True else "false" if v is False else str(v)
        if bad:
            skipped.append(f"{name}: {', '.join(bad)} (set these by hand)")
        if vals:
            plan.append({"schema": name, "values": vals,
                         "args": policy_args(name, vals, target_ou)})
    return plan, skipped
