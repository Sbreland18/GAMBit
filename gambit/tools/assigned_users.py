"""Chromebook “Assigned user” clean-up: clear it, or set it to the person who last signed
in – with filters so a technician's or teacher's sign-in doesn't become the assignment, a
backup of the old values before any change, and an undo.

GAM 7:  gam cros <deviceId,…> update user ""      (blank)
        gam cros <deviceId> update user <email>
        gam print cros … fields …,annotateduser,recentusers listlimit 1
Google lists recentUsers newest first, so listlimit 1 keeps the last person who signed in.
"""

from __future__ import annotations

import csv
import datetime
import fnmatch
import io
import json
import os

from ..settings import settings

FIELDS = ("deviceid,serialnumber,annotatedassetid,annotateduser,orgunitpath,status,"
          "lastsync,model,recentusers,activetimeranges")
OPTS = ["reverselists", "activetimeranges", "listlimit", "1"]
BATCH = 200          # device IDs per "gam cros <ids> update user …" command


# ================================================================== loading ===
def load_args(scope: str, values: list[str], children: bool = True) -> list[list[str]]:
    """The print cros command(s) for: all | ou | serial | asset."""
    tail = ["fields", FIELDS, *OPTS]
    if scope == "all":
        return [["print", "cros", *tail]]
    if scope == "ou":
        how = "cros_ou_and_children" if children else "cros_ou"
        return [["print", "cros", how, ou, *tail] for ou in values]
    if scope == "serial":
        return [["print", "cros", "select", "cros_sn", ",".join(values), *tail]] if values \
            else []
    if scope == "asset":
        qs = [f'asset_id:"{a}"' if " " in a else f"asset_id:{a}" for a in values]
        if not qs:
            return []
        return [["print", "cros", *(["query", qs[0]] if len(qs) == 1 else
                                    ["queries", ",".join(qs)]), *tail]]
    raise ValueError(scope)


def _find(row: dict, *parts) -> str:
    for k, v in row.items():
        kl = (k or "").lower()
        if all(p in kl for p in parts) and v:
            return v
    return ""


def devices(rows: list[dict]) -> list[dict]:
    out, seen = [], set()
    for r in rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        did = low.get("deviceid", "")
        if not did or did in seen:
            continue
        seen.add(did)
        out.append({
            "deviceId": did, "serial": low.get("serialnumber", ""),
            "asset": low.get("annotatedassetid", ""), "ou": low.get("orgunitpath", ""),
            "status": low.get("status", ""), "model": low.get("model", ""),
            "assigned": low.get("annotateduser", "").strip(),
            "last": _find(r, "recentusers", "email").strip(),
            "last_type": _find(r, "recentusers", "type"),
            "last_day": _find(r, "activetimeranges", "date"),
            "last_sync": low.get("lastsync", "").replace("T", " ").split(".")[0].rstrip("Z"),
        })
    return out


# ================================================================= options ===
def options() -> dict:
    try:
        o = json.loads(settings.get("assigned/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"blank_only": True, "students_only": True, "ignore": "", "max_days": 0, **o}


def save_options(o: dict):
    settings.set("assigned/options", json.dumps(o))


def _ignored(email: str, patterns: str) -> bool:
    e = email.lower()
    for p in [x.strip().lower() for x in (patterns or "").replace(";", ",").split(",")]:
        if not p:
            continue
        if "*" in p or "?" in p:
            if fnmatch.fnmatch(e, p) or fnmatch.fnmatch(e.split("@")[0], p):
                return True
        elif e == p or e.split("@")[0] == p.rstrip("@") or (p.endswith("@") and
                                                              e.startswith(p)):
            return True
    return False


def _age_days(dev: dict, today: datetime.date) -> int | None:
    for key in ("last_day", "last_sync"):
        try:
            return (today - datetime.date.fromisoformat(dev[key][:10])).days
        except (ValueError, KeyError, TypeError):
            continue
    return None


def is_student_ou(ou: str, roots: list[str]) -> bool:
    o = (ou or "/").rstrip("/").lower() + "/"
    return any(r.strip() == "/" or o.startswith(r.rstrip("/").lower() + "/") for r in roots)


# =================================================================== plans ===
def _student(ou: str, student_roots: list[str] | None) -> bool:
    """The org unit map decides when it's set up; otherwise the given student roots."""
    from .. import ou_map
    if ou_map.configured() and ou_map.roots("students"):
        return ou_map.is_student(ou)
    return is_student_ou(ou, student_roots or ou_map.student_roots())


def plan_set(devs: list[dict], users: list[dict], student_roots: list[str], o: dict,
             today: datetime.date | None = None) -> list[dict]:
    """Each device with Plan = Set / Same / Skip and Why.

    users: the directory (email, ou). When it's loaded, the last user must be one of the
    district's accounts; with students_only they must also be in a student org unit."""
    today = today or datetime.date.today()
    by_email = {(u.get("email") or "").lower(): u for u in users or []}
    out = []
    for d in devs:
        last, cur = d["last"], d["assigned"]
        plan, why = "Set", ""
        age = _age_days(d, today)
        if not last or "@" not in last:
            plan, why = "Skip", "no signed-in user reported (guest or never used)"
        elif last.lower() == cur.lower():
            plan, why = "Same", "already assigned to the last user"
        elif o.get("blank_only") and cur:
            plan, why = "Skip", f"already assigned to {cur}"
        elif _ignored(last, o.get("ignore", "")):
            plan, why = "Skip", f"{last} is on the ignore list"
        elif by_email and last.lower() not in by_email:
            plan, why = "Skip", f"{last} isn't one of the district's accounts"
        elif o.get("students_only") and by_email and not _student(
                by_email[last.lower()].get("ou", ""), student_roots):
            plan, why = "Skip", (f"{last} isn't in a student org unit "
                                 f"({by_email[last.lower()].get('ou')}) – see Settings & "
                                 "Updates → Org units & schools")
        elif o.get("max_days") and age is not None and age > int(o["max_days"]):
            plan, why = "Skip", f"last used {age} days ago"
        elif cur:
            why = f"replaces {cur}"
        else:
            why = "fills in a blank"
        out.append({**d, "plan": plan, "why": why})
    return out


def set_steps(rows: list[dict]) -> list[tuple[str, list[str]]]:
    return [(f"{r['serial'] or r['deviceId']}: assigned user → {r['last']}",
             ["cros", r["deviceId"], "update", "user", r["last"]])
            for r in rows if r.get("plan") == "Set"]


def clear_steps(rows: list[dict]) -> list[tuple[str, list[str]]]:
    ids = [r["deviceId"] for r in rows if r.get("assigned")]
    out = []
    for i in range(0, len(ids), BATCH):
        part = ids[i:i + BATCH]
        out.append((f"Blank the assigned user on {len(part)} Chromebook(s)",
                    ["cros", ",".join(part), "update", "user", ""]))
    return out


# ============================================================ backup / undo ===
def backup_dir() -> str:
    from ..fleet import data_dir
    d = os.path.join(data_dir(), "assigned-user-backups")
    os.makedirs(d, exist_ok=True)
    return d


def backup(rows: list[dict], what: str) -> str:
    """Save the current assigned users of the devices about to change."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(backup_dir(), f"{stamp}-{what}.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["deviceId", "serial", "asset", "assigned", "ou"])
        for r in rows:
            w.writerow([r["deviceId"], r.get("serial", ""), r.get("asset", ""),
                        r.get("assigned", ""), r.get("ou", "")])
    return path


def latest_backup() -> str:
    try:
        files = sorted(f for f in os.listdir(backup_dir()) if f.endswith(".csv"))
    except OSError:
        return ""
    return os.path.join(backup_dir(), files[-1]) if files else ""


def undo_steps(path: str) -> list[tuple[str, list[str]]]:
    """Put every device back to the assigned user (or org unit) it had (devices that shared one value
    go in one command)."""
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    groups: dict[str, list[str]] = {}
    moved = os.path.basename(path).split(".")[0].endswith("-move")
    key = "ou" if moved else "assigned"
    for r in rows:
        if r.get("deviceId") and (not moved or r.get("ou")):
            groups.setdefault(r.get(key, ""), []).append(r["deviceId"])
    out = []
    if moved:
        for ou, ids in groups.items():
            for i in range(0, len(ids), BATCH):
                part = ids[i:i + BATCH]
                out.append((f"{len(part)} Chromebook(s): back to {ou}",
                            ["cros", ",".join(part), "update", "ou", ou]))
        return out
    for who, ids in groups.items():
        for i in range(0, len(ids), BATCH):
            part = ids[i:i + BATCH]
            out.append((f"{len(part)} Chromebook(s): assigned user back to {who or '(blank)'}",
                        ["cros", ",".join(part), "update", "user", who]))
    return out


def to_csv(rows: list[dict], cols: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


# ============================================== move to the student's school ===
def move_options() -> dict:
    from .automation import options as assign_opts
    a = assign_opts()
    try:
        o = json.loads(settings.get("assigned/move", "{}") or "{}")
    except ValueError:
        o = {}
    return {"who": "last", "student_root": a.get("student_root", "/Students"),
            "school_depth": int(a.get("school_depth", 1) or 1),
            "ou_template": a.get("ou_template", "/Chromebooks/{school}"),
            "skip_ous": "", "only_active": True, "max_days": 0, "ignore": "",
            "scope_ous": [], **o}


def move_options_saved() -> dict:
    try:
        return json.loads(settings.get("assigned/move", "{}") or "{}")
    except ValueError:
        return {}


def save_move_options(o: dict):
    settings.set("assigned/move", json.dumps(o))


def _path(p: str) -> str:
    p = (p or "").strip().replace("\\", "/")
    p = "/" + p.strip("/") if p.strip("/") else "/"
    return p


def _under(ou: str, roots: list[str]) -> bool:
    o = _path(ou).lower().rstrip("/") + "/"
    return any(o.startswith(_path(r).lower().rstrip("/") + "/") for r in roots if r.strip())


def target_for(user_ou: str, o: dict) -> str:
    """/Students/Hancock High School/9th Grade → /Chromebooks/Hancock High School."""
    from .automation import school_of
    root = _path(o.get("student_root", "/Students"))
    if not _under(user_ou, [root]) or _path(user_ou).lower() == root.lower():
        return ""
    school = school_of(_path(user_ou), root, int(o.get("school_depth", 1) or 1))
    if not school:
        return ""
    return _path(o.get("ou_template", "/Chromebooks/{school}").replace("{school}", school))


def use_map(o: dict) -> bool:
    from .. import ou_map
    return o.get("source", "map") == "map" and ou_map.configured()


def target_from_map(user_ou: str) -> tuple[str, str]:
    """(device org unit, reason when there isn't one) from the org unit map."""
    from .. import ou_map
    if not ou_map.is_student(user_ou):
        return "", "not in a student org unit"
    school = ou_map.school_of(user_ou)
    if not school:
        return "", "their org unit has no school in the org unit map"
    dev = ou_map.device_ou_for(school)
    if not dev:
        return "", f"no Chromebook org unit is mapped for {school}"
    return dev, ""


def plan_move(devs: list[dict], users: list[dict], o: dict, ous: list[str] | None = None,
              today: datetime.date | None = None) -> list[dict]:
    """Each device with Plan = Move / Same / Skip, Why and Move to."""
    today = today or datetime.date.today()
    by_email = {(u.get("email") or "").lower(): u for u in users or []}
    known = {_path(x).lower() for x in ous or []}
    skip_ous = [x.strip() for x in (o.get("skip_ous") or "").replace(";", ",").split(",")
                if x.strip()]
    from .. import ou_map
    mapped = use_map(o)
    protect = {"loaners": "a loaner", "repairs": "a repair", "lost": "a lost / disabled",
               "test": "a testing"}
    out = []
    for d in devs:
        who = d["assigned"] if o.get("who") == "assigned" else d["last"]
        kind = ou_map.classify(d["ou"])["type"] if mapped else ""
        u = by_email.get((who or "").lower())
        if u and mapped:
            target, reason = target_from_map(u.get("ou", ""))
        else:
            target, reason = (target_for(u.get("ou", ""), o) if u else ""), ""
        plan, why = "Move", ""
        age = _age_days(d, today)
        if not who or "@" not in who:
            plan, why = "Skip", ("no assigned user" if o.get("who") == "assigned" else
                                 "no signed-in user reported")
        elif skip_ous and _under(d["ou"], skip_ous):
            plan, why = "Skip", f"{d['ou']} is on the don't-move list"
        elif kind in protect:
            plan, why = "Skip", f"{d['ou']} is {protect[kind]} org unit"
        elif o.get("only_active", True) and d.get("status") and d["status"] != "ACTIVE":
            plan, why = "Skip", f"device is {d['status'].lower()}"
        elif _ignored(who, o.get("ignore", "")):
            plan, why = "Skip", f"{who} is on the ignore list"
        elif not u:
            plan, why = "Skip", f"{who} isn't in the people list"
        elif not target:
            plan, why = "Skip", (f"{who}: {reason} ({u.get('ou') or '?'})" if mapped else
                                 f"{who} isn't a student under {o.get('student_root')} "
                                 f"({u.get('ou') or '?'})")
        elif o.get("max_days") and o.get("who") != "assigned" and age is not None \
                and age > int(o["max_days"]):
            plan, why = "Skip", f"last used {age} days ago"
        elif _under(d["ou"], [target]):
            plan, why = "Same", ("already in the right org unit" if _path(d["ou"]).lower()
                                 == target.lower() else f"already inside {target}")
        elif known and target.lower() not in known:
            plan, why = "Skip", f"org unit {target} doesn't exist – create it on Org units"
        else:
            why = f"{who} is in {u.get('ou')}"
        out.append({**d, "plan": plan, "why": why, "target": target, "who": who or ""})
    return out


def move_steps(rows: list[dict]) -> list[tuple[str, list[str]]]:
    groups: dict[str, list[str]] = {}
    for r in rows:
        if r.get("plan") == "Move":
            groups.setdefault(r["target"], []).append(r["deviceId"])
    out = []
    for target, ids in sorted(groups.items()):
        for i in range(0, len(ids), BATCH):
            part = ids[i:i + BATCH]
            out.append((f"Move {len(part)} Chromebook(s) to {target}",
                        ["cros", ",".join(part), "update", "ou", target]))
    return out


MOVE_TASK = {"name": "GAMbit move Chromebooks to students' schools",
             "args": ["--task", "devicemove"], "freq": "daily", "time": "05:50",
             "what": "Moves each Chromebook to the school org unit of the student who last "
                     "signed in", "standard": False}


def run_move_task(log=print, run_csv=None, run_text=None, users=None, ous=None) -> int:
    """Background task: plan and apply the moves; stops if there are unusually many."""
    from .. import activity
    from ..directory import load_ous, load_users, run_gam_csv, run_gam_text
    run_csv = run_csv or (lambda a: run_gam_csv(a, 3600))
    run_text = run_text or run_gam_text
    o = move_options()
    scope = o.get("scope_ous") or []
    cmds = load_args("ou", scope) if scope else load_args("all", [])
    rows = []
    for a in cmds:
        c, r, e = run_csv(a)
        if c != 0:
            raise RuntimeError((e or "couldn't list Chromebooks").strip()[-200:])
        rows += r
    devs = devices(rows)
    plan = plan_move(devs, users if users is not None else load_users(), o,
                     ous if ous is not None else load_ous())
    todo = [p for p in plan if p["plan"] == "Move"]
    if not todo:
        log(f"Chromebook moves: nothing to move ({len(plan)} checked).")
        return 0
    if len(todo) > max(50, len(plan) // 4) and not o.get("allow_big"):
        log(f"{len(todo)} moves is more than usual – nothing moved. Run it by hand first "
            "(Chromebook fleet → Assigned users).")
        return 1
    backup(todo, "move")
    bad = 0
    for _label, args in move_steps(todo):
        c, _out = run_text(args, 600)
        activity.record(args, c, "done" if c == 0 else "failed", None,
                        settings.get("profile/current", "") or "Default",
                        note="Move Chromebooks to students' schools")
        bad += 1 if c else 0
    log(f"Chromebook moves: {len(todo)} device(s) moved in {len(move_steps(todo))} "
        f"command(s), {bad} failed.")
    return 1 if bad else 0
