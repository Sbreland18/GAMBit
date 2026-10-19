"""Unusual-activity alerts: every night, read Google's audit logs for the last day and flag
mass downloads or deletes, risky sign-ins (Google's own suspicious-login events, or a sign-in
from a country you don't expect), new admin roles, and spikes in external sharing.
Each finding is alerted (and opens an Incident IQ ticket if that's turned on) and listed on
Investigations → Unusual activity, where one click opens the audit log for that person."""

from __future__ import annotations

import datetime
import json
import os
from collections import defaultdict

from ..settings import settings

TASK = {"name": "GAMbit unusual activity", "args": ["--task", "watchdog"],
        "freq": "daily", "time": "05:20",
        "what": "Checks the audit logs for unusual activity overnight",
        "standard": False}

SUSPICIOUS = ("suspicious_login,suspicious_login_less_secure_app,suspicious_programmatic_login,"
              "gov_attack_warning,account_disabled_hijacked,account_disabled_password_leak,"
              "account_disabled_spamming,leaked_password")
ADMIN_EVENTS = "ASSIGN_ROLE,CREATE_ROLE,ADD_PRIVILEGE,GRANT_ADMIN_PRIVILEGE"


def options() -> dict:
    try:
        o = json.loads(settings.get("watchdog/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"downloads": 200, "deletes": 200, "shares": 50, "countries": "US",
            "check_countries": False, "admin": True, "suspicious": True,
            "tsv_off": True, "risky_apps": True, "student_root": "/Students",
            "travel": True, "travel_hours": 2, "travel_ou": "/Staff",
            "ignore": "", **o}


def save_options(o: dict):
    settings.set("watchdog/options", json.dumps(o))


def _low(r: dict) -> dict:
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _since(hours: int = 26, now: datetime.datetime | None = None) -> str:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return (now - datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def queries(opts: dict, start: str) -> list[tuple[str, list[str]]]:
    q = [("drive", ["report", "drive", "user", "all", "start", start, "events",
                    "download,delete,trash,change_user_access,change_document_visibility"])]
    if opts.get("suspicious", True) or opts.get("check_countries"):
        ev = ["events", SUSPICIOUS + (",login_success" if opts.get("check_countries") else "")]
        q.append(("login", ["report", "login", "user", "all", "start", start, *ev]))
    if opts.get("travel", True):
        ou = (opts.get("travel_ou") or "/").strip()
        who = ["user", "all"] if ou in ("", "/") else ["orgunit", ou]
        q.append(("travel", ["report", "login", *who, "start", start, "events",
                             "login_success"]))
    if opts.get("tsv_off", True):
        q.append(("useraccounts", ["report", "useraccounts", "user", "all", "start", start,
                                   "events", "2sv_disable"]))
    if opts.get("risky_apps", True):
        q.append(("token", ["report", "token", "user", "all", "start", start, "events",
                            "authorize"]))
    if opts.get("admin", True):
        q.append(("admin", ["report", "admin", "user", "all", "start", start, "events",
                            ADMIN_EVENTS]))
    return q


def _domain(e: str) -> str:
    return e.rsplit("@", 1)[-1].lower() if "@" in e else ""


def analyze(results: dict[str, list[dict]], opts: dict, my_domains: set[str],
            ou_of: dict[str, str] | None = None, approved: list[dict] | None = None) -> list:
    """results: {"drive": rows, "login": rows, "admin": rows, "useraccounts": rows,
    "token": rows} → findings."""
    ignore = {x.strip().lower() for x in (opts.get("ignore") or "").split(",") if x.strip()}
    allowed = {c.strip().upper() for c in (opts.get("countries") or "").split(",") if c.strip()}
    out = []
    dl, rm, ext = defaultdict(int), defaultdict(int), defaultdict(int)
    examples = defaultdict(list)
    for r in results.get("drive", []):
        low = _low(r)
        who = low.get("actor.email", "").lower()
        if not who or who in ignore:
            continue
        ev = low.get("name", "")
        if ev == "download":
            dl[who] += 1
        elif ev in ("delete", "trash"):
            rm[who] += 1
        elif ev == "change_document_visibility" and low.get("visibility") in (
                "people_with_link", "public_on_the_web", "shared_externally"):
            ext[who] += 1
            examples[who].append(low.get("doc_title", ""))
        elif ev == "change_user_access":
            tgt = low.get("target_user", "") or low.get("target_domain", "")
            dom = _domain(tgt) if "@" in tgt else tgt.lower()
            if dom and dom not in my_domains and dom not in ("all", "anyone"):
                ext[who] += 1
                examples[who].append(low.get("doc_title", ""))
    for who, n in dl.items():
        if n >= int(opts.get("downloads", 200)):
            out.append(_f("Mass download", who, f"{n} files downloaded", "high",
                          "drive", "download"))
    for who, n in rm.items():
        if n >= int(opts.get("deletes", 200)):
            out.append(_f("Mass delete", who, f"{n} files deleted or trashed", "high",
                          "drive", "trash,delete"))
    for who, n in ext.items():
        if n >= int(opts.get("shares", 50)):
            ex = ", ".join(x for x in examples[who][:3] if x)
            out.append(_f("External sharing spike", who,
                          f"{n} files shared outside the district" + (f" (e.g. {ex})" if ex
                                                                      else ""),
                          "medium", "drive", "change_user_access,change_document_visibility"))
    seen_country = set()
    for r in results.get("login", []):
        low = _low(r)
        who = low.get("actor.email", "").lower()
        if not who or who in ignore:
            continue
        ev = low.get("name", "")
        ip = low.get("ipaddress", "")
        if ev == "login_success":
            cc = (low.get("networkinfo.regioncode", "") or "").upper()
            if opts.get("check_countries") and cc and allowed and cc not in allowed and \
                    (who, cc) not in seen_country:
                seen_country.add((who, cc))
                out.append(_f("Sign-in from an unexpected country", who,
                              f"signed in from {cc}" + (f" ({ip})" if ip else ""), "high",
                              "login", "login_success"))
        elif ev:
            out.append(_f("Risky sign-in", who, ev.replace("_", " ") +
                          (f" from {ip}" if ip else ""), "high", "login", ev))
    for r in results.get("admin", []):
        low = _low(r)
        who = low.get("actor.email", "").lower()
        if who in ignore:
            continue
        ev = low.get("name", "")
        what = low.get("role_name", "") or low.get("privilege_name", "")
        tgt = low.get("user_email", "")
        out.append(_f("New admin role or privilege", who or "(Google)",
                      f"{ev.replace('_', ' ').lower()}" + (f" “{what}”" if what else "") +
                      (f" for {tgt}" if tgt else ""), "high", "admin", ""))
    out += _account_findings(results, opts, ignore, ou_of or {}, approved or [])
    if opts.get("travel", True):
        from .shared_accounts import impossible_travel
        for t in impossible_travel(results.get("travel", []), float(opts.get("travel_hours",
                                                                             2))):
            if t["who"] not in ignore:
                out.append(_f("Impossible travel", t["who"],
                              f"signed in from {t['from']} then {t['to']} {t['minutes']} min "
                              f"later ({t['ips']})", "high", "login", "login_success"))
    # de-duplicate identical findings
    uniq, keys = [], set()
    for f in out:
        k = (f["Finding"], f["Who"], f["Details"])
        if k not in keys:
            keys.add(k)
            uniq.append(f)
    return uniq


def _is_student(who: str, ou_of: dict, root: str) -> bool:
    r = (root or "/Students").rstrip("/").lower()
    ou = (ou_of.get(who, "") or "").rstrip("/").lower()
    return ou == r or ou.startswith(r + "/")


def _account_findings(results, opts, ignore, ou_of, approved) -> list[dict]:
    import re
    from .app_vetting import RISKY, _status
    out = []
    root = opts.get("student_root", "/Students")
    for r in results.get("useraccounts", []):
        low = _low(r)
        who = low.get("actor.email", "").lower()
        if who and who not in ignore and low.get("name", "") == "2sv_disable":
            stu = _is_student(who, ou_of, root)
            out.append(_f("2-Step Verification turned off", who,
                          ("student" if stu else "staff") + " account turned off 2-Step "
                          "Verification", "medium" if stu else "high", "useraccounts",
                          "2sv_disable"))
    for r in results.get("token", []):
        low = _low(r)
        who = low.get("actor.email", "").lower()
        if not who or who in ignore or low.get("name", "") != "authorize":
            continue
        app, cid = low.get("app_name", ""), low.get("client_id", "")
        scope = " ".join(v for k, v in low.items() if k.startswith("scope")) + " "
        risky = [label for pat, label in RISKY if re.search(pat, scope)]
        if not risky or _status(app, cid, approved) == "approved":
            continue
        stu = _is_student(who, ou_of, root)
        f = _f("Risky app allowed", who,
               f"{'student' if stu else 'staff'} allowed “{app or cid}” to "
               f"{', '.join(dict.fromkeys(risky))} (not on the approved list)",
               "high" if stu else "medium", "token", "authorize")
        f["client_id"] = cid
        out.append(f)
    return out


def _f(kind, who, details, level, app, events):
    return {"Finding": kind, "Who": who, "Details": details, "Level": level, "app": app,
            "events": events}


def _store() -> str:
    from .. import team
    if team.folder():
        d = os.path.join(team.folder(), "watchdog")
    else:
        from ..support import logs_dir
        d = os.path.join(os.path.dirname(logs_dir()), "watchdog")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "findings.json")


def load_findings() -> list[dict]:
    try:
        with open(_store(), encoding="utf-8") as fh:
            items = json.load(fh)
    except (OSError, ValueError):
        return []
    return [{"When": "", "Who": "", "Details": "", "Status": "New", **f}
            for f in items if isinstance(f, dict) and f.get("Finding")] \
        if isinstance(items, list) else []


def save_findings(items: list[dict]):
    p = _store()
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(items[-2000:], fh, indent=1)
    os.replace(p + ".tmp", p)


def domains() -> set[str]:
    from .. import google_io
    ds = {d.strip().lower() for d in (settings.get("watchdog/domains", "") or "").split(",")
          if d.strip()}
    a = google_io.admin_email()
    if "@" in a:
        ds.add(_domain(a))
    return ds


def run(log=print, run_csv=None, now=None) -> list[dict]:
    from ..directory import run_gam_csv
    run_csv = run_csv or (lambda a: run_gam_csv(a, 3600))
    opts = options()
    start = _since(26, now)
    results, errors = {}, []
    for key, args in queries(opts, start):
        code, rows, err = run_csv(args)
        if code == 0:
            results[key] = rows
        else:
            errors.append(f"{key}: {(err or '').strip()[-160:]}")
    ou_of, approved = {}, []
    if "useraccounts" in results or "token" in results:
        try:
            from ..directory import load_users
            ou_of = {u["email"].lower(): u.get("ou", "") for u in load_users()}
        except Exception:  # noqa: BLE001
            ou_of = {}
        try:
            from .app_vetting import load_list
            approved = load_list()
        except Exception:  # noqa: BLE001
            approved = []
    found = analyze(results, opts, domains(), ou_of, approved)
    stamp = datetime.datetime.now().isoformat(timespec="minutes")
    items = load_findings()
    # the look-back overlaps yesterday's run by a couple of hours – don't report twice
    cut = (datetime.datetime.now() - datetime.timedelta(hours=48)).isoformat(
        timespec="minutes")
    seen = {(i.get("Finding"), i.get("Who"), i.get("Details")) for i in items
            if i.get("When", "") >= cut}
    found = [f for f in found if (f.get("Finding"), f.get("Who"), f.get("Details")) not in seen]
    for f in found:
        f["When"] = stamp
        f["Status"] = "New"
    items += found
    save_findings(items)
    for e in errors:
        log(f"Couldn't read the {e}")
    log(f"Unusual activity: {len(found)} finding(s).")
    if found and opts.get("auto_respond"):
        try:
            from .playbooks import auto_request
            req = auto_request(found)
            if req:
                log(f"Sent “{req['title']}” for approval.")
        except Exception as exc:  # noqa: BLE001
            log(f"Couldn't send the lock-down request: {exc}")
    if found:
        from .. import alerts
        alerts.notify("Unusual activity in Google Workspace (last 24 hours):\n" + "\n".join(
            f"• {f['Finding']}: {f['Who']} – {f['Details']}" for f in found[:30]) +
            "\n\nOpen GAMbit → Investigations → Unusual activity to look into it.",
            "GAMbit: unusual activity")
    return found
