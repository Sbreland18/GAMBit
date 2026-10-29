"""Chromebook ↔ student assignment sync, and scheduled clean-up rules (sent for approval)."""

from __future__ import annotations

import csv
import datetime
import io
import json
import re

from ..settings import settings


def _low(r: dict) -> dict:
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ======================================================= device assignments ===
ASSIGN_COLS = {"serial": ["serial", "serialnumber", "serialno", "assetserial", "sn"],
               "student": ["student", "studentemail", "email", "user", "assignedto",
                           "studentid", "id"],
               "asset": ["asset", "assettag", "assetid", "tag"]}
CROS_ARGS = ["print", "cros", "fields",
             "serialnumber,annotateduser,orgunitpath,annotatedassetid,annotatedlocation"]


def options() -> dict:
    try:
        o = json.loads(settings.get("assign/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"source": "", "student_root": "/Students", "school_depth": 1,
            "ou_template": "/Chromebooks/{school}", "move_ou": True, "set_asset": True, **o}


def save_options(o: dict):
    settings.set("assign/options", json.dumps(o))


def read_assignments(text: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if not rows:
        return []
    by = {_norm(h): h for h in rows[0]}
    m = {k: next((by[c] for c in cands if c in by), "") for k, cands in ASSIGN_COLS.items()}
    out = []
    for r in rows:
        a = {k: (r.get(c) or "").strip() if c else "" for k, c in m.items()}
        if a["serial"] and a["student"]:
            out.append(a)
    return out


def school_of(ou: str, root: str, depth: int = 1) -> str:
    ou, root = (ou or "/").rstrip("/"), (root or "/").rstrip("/")
    rest = ou[len(root):].strip("/") if ou.lower().startswith(root.lower()) else ou.strip("/")
    parts = rest.split("/") if rest else []
    return "/".join(parts[:depth])


def assign_plan(assignments: list[dict], cros: list[dict], users: list[dict],
                opts: dict) -> list[dict]:
    by_email = {u["email"].lower(): u for u in users}
    by_id = {str(u.get("sis_id")).lower(): u for u in users if u.get("sis_id")}
    devs = {}
    for c in cros:
        low = _low(c)
        devs[low.get("serialnumber", "").upper()] = low
    plan = []
    for a in assignments:
        sn = a["serial"].upper()
        dev = devs.get(sn)
        stu = a["student"].lower()
        u = by_email.get(stu) or by_id.get(stu) or by_id.get(stu.lstrip("0"))
        if not dev:
            plan.append({"Serial": sn, "Student": a["student"], "Change": "⚠ device not found",
                         "args": None})
            continue
        if not u:
            plan.append({"Serial": sn, "Student": a["student"], "Change": "⚠ student not found",
                         "args": None})
            continue
        attrs, notes = [], []
        if dev.get("annotateduser", "").lower() != u["email"].lower():
            attrs += ["user", u["email"]]
            notes.append(f"user {dev.get('annotateduser') or '–'} → {u['email']}")
        if opts.get("set_asset", True) and a.get("asset") and \
                dev.get("annotatedassetid", "") != a["asset"]:
            attrs += ["assetid", a["asset"]]
            notes.append(f"asset tag → {a['asset']}")
        if opts.get("move_ou", True):
            from .. import ou_map
            if ou_map.configured():          # the district's org unit map decides
                from .assigned_users import target_from_map
                target = target_from_map(u.get("ou", ""))[0]
                school = target
            else:
                from ..ou_map import school_from_path   # “8th Grade” is never a school
                school = school_from_path(u.get("ou", ""),
                                          opts.get("student_root", "/Students"),
                                          int(opts.get("school_depth", 1) or 1))
                target = opts.get("ou_template", "/Chromebooks/{school}").replace(
                    "{school}", school)
            if school:
                cur = (dev.get("orgunitpath") or "/").rstrip("/").lower()
                if cur != target.rstrip("/").lower() and \
                        not cur.startswith(target.rstrip("/").lower() + "/"):
                    attrs += ["ou", target]
                    notes.append(f"{dev.get('orgunitpath') or '/'} → {target}")
        plan.append({"Serial": sn, "Student": u["email"],
                     "Change": "; ".join(notes) or "already right",
                     "args": ["cros_sn", sn, "update", *attrs] if attrs else None})
    plan.sort(key=lambda p: (p["args"] is None, p["Serial"]))
    return plan


def run_assign_sync(log=print, run_csv=None, run_text=None, load_text=None) -> int:
    """Background task: apply the saved assignment sync (safe changes, no approval needed)."""
    from .. import activity, google_io
    from ..directory import load_users, run_gam_csv, run_gam_text
    run_csv = run_csv or (lambda a: run_gam_csv(a, 1800))
    run_text = run_text or run_gam_text
    o = options()
    src = o.get("source", "")
    if not src:
        log("No assignment source saved – set it up on Chromebook fleet → Assignment sync.")
        return 0
    if load_text:
        text = load_text(src)
    else:
        path = google_io.download_sheet(src) if src.startswith("http") else src
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
    code, cros, err = run_csv(CROS_ARGS)
    if code != 0:
        raise RuntimeError((err or "couldn't list Chromebooks").strip()[-200:])
    plan = assign_plan(read_assignments(text), cros, load_users(), o)
    todo = [p for p in plan if p["args"]]
    if len(todo) > max(50, len(plan) // 4) and not o.get("allow_big"):
        log(f"{len(todo)} changes is more than usual – nothing applied. Run it by hand first.")
        return 1
    bad = 0
    for p in todo:
        c, _out = run_text(p["args"], 300)
        activity.record(p["args"], c, "done" if c == 0 else "failed", None,
                        settings.get("profile/current", "") or "Default",
                        note="Chromebook assignment sync")
        bad += 1 if c else 0
    log(f"Assignment sync: {len(todo) - bad} updated, {bad} failed, "
        f"{len(plan) - len(todo)} unchanged or skipped.")
    return 1 if bad else 0


ASSIGN_TASK = {"name": "GAMbit Chromebook assignment sync", "args": ["--task", "devicesync"],
               "freq": "daily", "time": "05:40",
               "what": "Matches Chromebooks to students from the assignment sheet",
               "standard": False}


# ============================================================== clean-up ===
RULE_KINDS = {
    "inactive": "Suspend accounts nobody has signed in to for a while",
    "delete_old": "Delete suspended accounts that haven't signed in for a long time",
    "release": "Release licenses from suspended accounts",
}


def rules() -> list[dict]:
    from .. import team
    if team.folder():
        d = team.read_shared("cleanup_rules.json")
        if d:
            return d.get("rules", [])
    try:
        return json.loads(settings.get("cleanup/rules", "[]") or "[]")
    except ValueError:
        return []


def save_rules(rs: list[dict]):
    from .. import team
    if team.folder():
        team.write_shared("cleanup_rules.json", {"rules": rs})
    settings.set("cleanup/rules", json.dumps(rs))


def _under(ou: str, root: str) -> bool:
    ou, root = (ou or "/").rstrip("/") or "/", (root or "/").rstrip("/") or "/"
    return root == "/" or ou == root or ou.startswith(root + "/")


def _days_since(stamp: str) -> int | None:
    if not stamp or stamp.lower().startswith("never") or stamp.startswith("1970"):
        return None
    try:
        t = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return (datetime.datetime.now(datetime.timezone.utc) - t).days
    except ValueError:
        return None


def evaluate(rule: dict, users: list[dict], licenses: list[dict] | None = None) -> list[dict]:
    """→ [{email, why, args}] for one rule."""
    kind, ou, days = rule.get("kind"), rule.get("ou", "/"), int(rule.get("days", 180) or 0)
    skip = {e.strip().lower() for e in (rule.get("except", "") or "").split(",") if e.strip()}
    out = []
    if kind == "release":
        for r in licenses or []:
            low = _low(r)
            e = (low.get("primaryemail") or low.get("email") or "").lower()
            if not e or e in skip:
                continue
            u = next((x for x in users if x["email"].lower() == e), None)
            if u and not _under(u.get("ou"), ou):
                continue
            for k, v in low.items():
                if k.startswith("licenses") and "display" not in k and "count" not in k and v:
                    for sku in [s for s in re.split(r"[ ,]+", v) if s]:
                        out.append({"email": e, "why": f"suspended, holds {sku}",
                                    "args": ["user", e, "delete", "license", sku]})
        return out
    for u in users:
        e = u["email"].lower()
        if e in skip or not _under(u.get("ou"), ou):
            continue
        since = _days_since(u.get("last_login", ""))
        never = since is None
        if kind == "inactive" and not u.get("suspended"):
            if (never and rule.get("include_never", False)) or (since is not None and
                                                                since >= days):
                out.append({"email": e, "why": "never signed in" if never else
                            f"last sign-in {since} days ago",
                            "args": ["update", "user", e, "suspended", "on"]})
        elif kind == "delete_old" and u.get("suspended"):
            if (since is not None and since >= days) or (never and rule.get("include_never")):
                out.append({"email": e, "why": "suspended; " + ("never signed in" if never else
                                                               f"last sign-in {since} days ago"),
                            "args": ["delete", "user", e]})
    return out


LICENSE_ARGS = ["print", "users", "query", "isSuspended=True", "fields", "primaryemail",
                "licenses"]


def run_cleanup(log=print, run_csv=None, users=None) -> list[str]:
    """Evaluate every rule; each one that finds something becomes ONE approval request."""
    from .. import team
    from ..directory import load_users, run_gam_csv
    run_csv = run_csv or (lambda a: run_gam_csv(a, 1800))
    rs = [r for r in rules() if r.get("enabled", True)]
    if not rs:
        return ["No clean-up rules are set up."]
    users = users if users is not None else load_users()
    lic = None
    lines = []
    for r in rs:
        if r.get("kind") == "release" and lic is None:
            code, lic, _e = run_csv(LICENSE_ARGS)
            lic = lic if code == 0 else []
        found = evaluate(r, users, lic)
        cap = int(r.get("max", 200) or 200)
        if not found:
            lines.append(f"“{r.get('name')}”: nothing to do.")
            continue
        if len(found) > cap:
            lines.append(f"“{r.get('name')}”: {len(found)} accounts is over the limit of {cap} – "
                         "not sent. Check the rule.")
            continue
        if not team.folder():
            lines.append(f"“{r.get('name')}”: {len(found)} account(s) – set up a team folder so "
                         "clean-up rules can ask for approval.")
            continue
        archive = (r.get("archive_to") or "").strip().lower()
        if r.get("kind") == "delete_old" and archive:
            from .. import retention
            what = [w for w in (r.get("archive_what") or ["drive"]) if w in retention.WHAT]
            found = [f for f in found if f["email"] != archive]   # never the archive itself
            team.new_request(
                [retention.transfer_args(f["email"], archive, what) for f in found],
                f"Clean-up rule “{r.get('name')}” found {len(found)} account(s). Approving "
                f"hands their {' and '.join(retention.WHAT[w] for w in what)} to {archive}; "
                "GAMbit deletes each account only after Google says that transfer finished "
                "(and it's still suspended):\n" +
                "\n".join(f"• {f['email']} – {f['why']}" for f in found[:60]),
                title=f"Clean-up: archive then delete – {r.get('name')} ({len(found)})",
                by="clean-up rules",
                extra={"kind": "cleanup-archive", "rule": r.get("name"),
                       "archive_to": archive, "what": what,
                       "delete_after": [f["email"] for f in found],
                       "why": {f["email"]: f["why"] for f in found}},
                dedupe=f"cleanup:{r.get('name')}")
            lines.append(f"“{r.get('name')}”: {len(found)} account(s) sent for approval "
                         f"(archive to {archive}, then delete).")
            continue
        team.new_request([f["args"] for f in found],
                         f"Clean-up rule “{r.get('name')}” found {len(found)} account(s):\n" +
                         "\n".join(f"• {f['email']} – {f['why']}" for f in found[:60]),
                         title=f"Clean-up: {r.get('name')} ({len(found)})",
                         by="clean-up rules", extra={"kind": "cleanup", "rule": r.get("name")},
                         dedupe=f"cleanup:{r.get('name')}")
        lines.append(f"“{r.get('name')}”: {len(found)} account(s) sent for approval.")
    for ln in lines:
        log(ln)
    return lines


CLEANUP_TASK = {"name": "GAMbit clean-up rules", "args": ["--task", "cleanup"],
                "freq": "weekly", "time": "06:30",
                "what": "Checks the clean-up rules every Monday and sends findings for approval",
                "standard": False}
