"""Roster ↔ Google ↔ Chromebook mismatch report, and collecting devices from students
who have left.  Pure functions – the pages and background task run GAM and show results."""

from __future__ import annotations

import datetime
import json
import os
from collections import defaultdict

from ..settings import settings

COLLECT_ARGS = ["print", "cros", "fields",
                "serialnumber,annotateduser,orgunitpath,annotatedassetid,annotatedlocation,"
                "status,model,recentusers", "listlimit", "1"]


def _low(r: dict) -> dict:
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _under(ou: str, root: str) -> bool:
    ou, root = (ou or "/").rstrip("/") or "/", (root or "/").rstrip("/") or "/"
    return root == "/" or ou.lower() == root.lower() or ou.lower().startswith(root.lower() + "/")


def devices(cros: list[dict]) -> list[dict]:
    out = []
    for c in cros:
        low = _low(c)
        sn = low.get("serialnumber", "").upper()
        if not sn:
            continue
        recent = low.get("recentusers.0.email", "") or low.get("recentusers", "")
        out.append({"serial": sn, "user": low.get("annotateduser", "").lower(),
                    "ou": low.get("orgunitpath", ""), "asset": low.get("annotatedassetid", ""),
                    "location": low.get("annotatedlocation", ""),
                    "status": (low.get("status", "") or "ACTIVE").upper(),
                    "model": low.get("model", ""),
                    "recent": (recent.split()[0] if recent else "").lower()})
    return out


# ============================================================== mismatches ===
PROBLEMS = {
    "create": "On the roster, no Google account",
    "reactivate": "On the roster, but suspended in Google",
    "move": "In the wrong org unit (school or grade)",
    "name": "Name is different from the roster",
    "withdraw": "Active in Google, but left / not on the roster",
    "info": "Roster problem",
    "dev_withdrawn": "Chromebook assigned to a student who left",
    "dev_unknown": "Chromebook assigned to an account that doesn't exist",
    "no_device": "Student has no Chromebook assigned",
    "two_devices": "Student has more than one Chromebook",
    "dev_school": "Chromebook is in another school's org unit",
}


def _finding(kind, who, details, args=None, fix=""):
    return {"kind": kind, "Problem": PROBLEMS[kind], "Who": who, "Details": details,
            "Fix": fix or ("Run the fix" if args else "–"), "args": args or []}


def roster_findings(changes) -> list[dict]:
    """sis.plan() changes → findings (Google side)."""
    out = []
    for c in changes:
        if c.action == "create":
            out.append(_finding("create", c.email, c.details, None,
                                "Run roster sync (it sends the new password)"))
        elif c.action == "reactivate":
            out.append(_finding("reactivate", c.email, c.details, c.commands))
        elif c.action == "withdraw":
            cmds = [] if c.commands and c.commands[0][:1] == ["offboard"] else c.commands
            out.append(_finding("withdraw", c.email, c.details, cmds,
                                "" if cmds else "Offboard them (Workflows → Staff leaving)"))
        elif c.action == "update":
            kind = "move" if "move " in c.details else ("name" if "name “" in c.details
                                                         else None)
            if kind:
                out.append(_finding(kind, c.email, c.details, c.commands))
        elif c.action == "info":
            out.append(_finding("info", c.email or c.name, c.details))
    return out


def device_findings(users: list[dict], cros: list[dict], opts: dict) -> list[dict]:
    """Chromebook side. opts: student_root, withdrawn_ou, one_to_one, ou_template,
    school_depth."""
    from .automation import school_of
    root = opts.get("student_root", "/Students")
    wd = opts.get("withdrawn_ou", "")
    by_email = {u["email"].lower(): u for u in users}
    devs = [d for d in devices(cros) if d["status"] in ("ACTIVE", "")]
    out = []
    per_student = defaultdict(list)
    for d in devs:
        if not d["user"]:
            continue
        u = by_email.get(d["user"])
        if not u:
            out.append(_finding("dev_unknown", d["serial"], f"assigned to {d['user']}",
                                None, "Fix the assignment (Chromebooks page)"))
            continue
        per_student[u["email"].lower()].append(d)
        left = (u.get("suspended") and _under(u.get("ou"), root)) or \
            (wd and _under(u.get("ou"), wd))
        if left:
            out.append({**_finding("dev_withdrawn", d["serial"],
                                   f"{u['email']} ({u.get('ou', '')}) · asset "
                                   f"{d['asset'] or '–'}", None, "Add to the collection list"),
                        "device": d, "student": u["email"]})
            continue
        tpl = opts.get("ou_template", "")
        if tpl and _under(u.get("ou"), root):
            school = school_of(u.get("ou", ""), root, int(opts.get("school_depth", 1) or 1))
            target = tpl.replace("{school}", school) if school else ""
            if target and not _under(d["ou"], target):
                out.append(_finding("dev_school", d["serial"],
                                    f"{u['email']} is at {school}; device is in {d['ou']}",
                                    [["cros_sn", d["serial"], "update", "ou", target]]))
    for e, ds in per_student.items():
        if len(ds) > 1:
            out.append(_finding("two_devices", e, ", ".join(x["serial"] for x in ds)))
    if opts.get("one_to_one"):
        for u in users:
            if u.get("suspended") or not _under(u.get("ou"), root) or \
                    (wd and _under(u.get("ou"), wd)):
                continue
            if u["email"].lower() not in per_student:
                out.append(_finding("no_device", u["email"], u.get("ou", ""), None,
                                    "Assign one (Chromebook fleet → Assignment sync)"))
    return out


def summary(findings: list[dict]) -> list[list[str]]:
    by = defaultdict(int)
    for f in findings:
        by[f["Problem"]] += 1
    return [[k, str(v)] for k, v in sorted(by.items(), key=lambda kv: -kv[1])]


def options() -> dict:
    try:
        o = json.loads(settings.get("reconcile/options", "{}") or "{}")
    except ValueError:
        o = {}
    from .automation import options as aopts
    a = aopts()
    return {"profile": "", "student_root": a.get("student_root", "/Students"),
            "withdrawn_ou": "/Students/Withdrawn", "one_to_one": True,
            "ou_template": a.get("ou_template", "") if a.get("move_ou", True) else "",
            "school_depth": a.get("school_depth", 1), **o}


def save_options(o: dict):
    settings.set("reconcile/options", json.dumps(o))


def build(profile_name: str, users: list[dict], run_csv, opts: dict | None = None):
    """Whole report: (findings, error lines)."""
    from .. import rostersync_run, sis
    opts = opts or options()
    findings, notes = [], []
    if profile_name:
        p = rostersync_run.all_profiles().get(profile_name)
        if not p:
            notes.append(f"No saved roster sync called “{profile_name}”.")
        else:
            rules = rostersync_run.rules_from_profile(p)
            exp = rostersync_run.load_roster(p)
            mapping = p.get("mapping") or sis.guess_mapping(exp.headers, p.get("format", ""))
            people = sis.people_from_export(exp, mapping, rules)
            findings += roster_findings(sis.plan(people, users, rules))
            if rules.kind == "students":
                opts = {**opts, "student_root": rules.managed_root,
                        "withdrawn_ou": rules.withdrawn_ou or opts.get("withdrawn_ou", "")}
    code, cros, err = run_csv(COLLECT_ARGS)
    if code == 0:
        findings += device_findings(users, cros, opts)
    else:
        notes.append("Couldn't read Chromebooks: " + (err or "").strip()[-200:])
    return findings, notes


# ===================================================== withdrawn devices ===
def collect_options() -> dict:
    try:
        o = json.loads(settings.get("collect/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"student_root": "/Students", "withdrawn_ou": "/Students/Withdrawn",
            "note": True, "disable": False, "ticket": False, "return_ou": "",
            "use_recent": False, **o}


def save_collect_options(o: dict):
    settings.set("collect/options", json.dumps(o))


def _store() -> str:
    from .. import fleet
    d = fleet.data_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "withdrawn_devices.json")


def load_items() -> list[dict]:
    try:
        with open(_store(), encoding="utf-8") as fh:
            items = json.load(fh)
    except (OSError, ValueError):
        return []
    return [i for i in items if isinstance(i, dict) and i.get("serial")] \
        if isinstance(items, list) else []


def save_items(items: list[dict]):
    p = _store()
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=1)
    os.replace(p + ".tmp", p)


def find_withdrawn(users: list[dict], cros: list[dict], opts: dict) -> list[dict]:
    """Devices whose student has left (suspended under the student root, or in the
    withdrawn org unit)."""
    from .automation import school_of
    by_email = {u["email"].lower(): u for u in users}
    root, wd = opts.get("student_root", "/Students"), opts.get("withdrawn_ou", "")
    out = []
    for d in devices(cros):
        if d["status"] not in ("ACTIVE", "DISABLED", ""):
            continue
        who = d["user"] or (d["recent"] if opts.get("use_recent") else "")
        u = by_email.get(who)
        if not u:
            continue
        left = (wd and _under(u.get("ou"), wd)) or (u.get("suspended") and
                                                    _under(u.get("ou"), root))
        if left:
            out.append({"serial": d["serial"], "asset": d["asset"], "user": u["email"],
                        "name": u.get("name", ""), "school": school_of(u.get("ou", ""), root)
                        or u.get("ou", ""), "model": d["model"], "device_ou": d["ou"],
                        "disabled": d["status"] == "DISABLED"})
    return out


def merge(items: list[dict], found: list[dict]) -> list[dict]:
    """Add newly found devices to the list. Returns the new entries."""
    known = {(i["serial"], i["user"]) for i in items}
    today = datetime.date.today().isoformat()
    new = []
    for f in found:
        if (f["serial"], f["user"]) in known:
            continue
        e = {**f, "flagged": today, "status": "To collect", "ticket": "", "collected": "",
             "by": ""}
        items.append(e)
        new.append(e)
    return new


def flag_commands(item: dict, opts: dict) -> list[list[str]]:
    cmds = []
    if opts.get("note", True):
        cmds.append(["cros_sn", item["serial"], "update", "notes",
                     f"COLLECT – {item['user']} left ({item['flagged']})"[:500]])
    if opts.get("disable") and not item.get("disabled"):
        cmds.append(["cros_sn", item["serial"], "update", "action", "disable"])
    return cmds


def check_in(items: list[dict], code: str, who: str, opts: dict):
    """Mark a device collected (serial or asset tag) → (item | None, commands, message)."""
    c = (code or "").strip().upper()
    it = next((i for i in items if i["status"] == "To collect" and
               (i["serial"] == c or (i.get("asset") or "").upper() == c)), None)
    if not it:
        return None, [], f"{c} isn't on the list of devices to collect."
    it.update(status="Collected", collected=datetime.datetime.now().isoformat(
        timespec="minutes"), by=who)
    cmds = [["cros_sn", it["serial"], "update", "notes",
             f"Collected {it['collected'][:10]} by {who} (from {it['user']})"[:500]]]
    if it.get("disabled") or opts.get("disable"):
        cmds.append(["cros_sn", it["serial"], "update", "action", "reenable"])
    if opts.get("return_ou"):
        cmds.append(["cros_sn", it["serial"], "update", "ou", opts["return_ou"]])
    left = sum(1 for i in items if i["status"] == "To collect")
    return it, cmds, f"✔ {it['serial']} from {it['user']} – {left} still to collect"


def ticket_text(item: dict) -> tuple[str, str]:
    return (f"Collect Chromebook {item['serial']} – {item['user']} left",
            f"{item.get('name') or item['user']} ({item['school']}) is no longer enrolled.\n"
            f"Chromebook serial {item['serial']}, asset tag {item.get('asset') or '–'}, "
            f"model {item.get('model') or '–'}.\nFlagged by GAMbit on {item['flagged']}.")


def run_collect(log=print, run_csv=None, run_text=None, users=None, hd=None) -> list[str]:
    """Background: find devices of students who left, flag them, open tickets."""
    from .. import activity
    from ..directory import load_users, run_gam_csv, run_gam_text
    run_csv = run_csv or (lambda a: run_gam_csv(a, 1800))
    run_text = run_text or run_gam_text
    opts = collect_options()
    users = users if users is not None else load_users()
    code, cros, err = run_csv(COLLECT_ARGS)
    if code != 0:
        raise RuntimeError("Couldn't list Chromebooks: " + (err or "").strip()[-200:])
    items = load_items()
    new = merge(items, find_withdrawn(users, cros, opts))
    lines = []
    if opts.get("ticket"):
        if hd is None:
            from ..integrations import ticketing as hd
    for it in new:
        if not settings.get("safety/dry_run", False):
            for cmd in flag_commands(it, opts):
                c, _o = run_text(cmd, 120)
                activity.record(cmd, c, "done" if c == 0 else "failed", None,
                                settings.get("profile/current", "") or "Default",
                                note="withdrawn student's device")
        if opts.get("ticket") and hd.configured() and hd.can("create"):
            try:
                it["ticket"] = hd.create(*ticket_text(it))
            except Exception as exc:  # noqa: BLE001
                lines.append(f"Couldn't open a ticket for {it['serial']}: {exc}")
    save_items(items)
    todo = sum(1 for i in items if i["status"] == "To collect")
    lines.insert(0, f"Devices to collect: {len(new)} new, {todo} in total.")
    if new:
        try:
            from .. import alerts
            alerts.notify("Chromebooks to collect from students who left:\n" + "\n".join(
                f"• {i['serial']} ({i.get('asset') or 'no tag'}) – {i['user']}, {i['school']}"
                for i in new[:40]), "GAMbit: devices to collect")
        except Exception:  # noqa: BLE001
            pass
    for ln in lines:
        log(ln)
    return lines


# ===================================================== nightly auto-fix ===
AUTO_CHOICES = {
    "dev_school": "Move Chromebooks to their student's school",
    "name": "Update names to match the roster",
    "move": "Move accounts to the right school / grade org unit",
    "reactivate": "Unsuspend students who are back on the roster",
}
AUTOFIX_TASK = {"name": "GAMbit nightly mismatch fix", "args": ["--task", "mismatch"],
                "freq": "daily", "time": "05:50",
                "what": "Builds the mismatch report, fixes the safe ones, sends the rest for "
                        "approval", "standard": False}


def autofix_options() -> dict:
    try:
        o = json.loads(settings.get("reconcile/autofix", "{}") or "{}")
    except ValueError:
        o = {}
    return {"enabled": False, "auto": ["dev_school", "name"], "max_auto": 50,
            "send_rest": True, **o}


def save_autofix_options(o: dict):
    settings.set("reconcile/autofix", json.dumps(o))


def split_autofix(findings: list[dict], opts: dict) -> tuple[list[dict], list[dict]]:
    """→ (fix automatically, send for approval) – only findings that have commands."""
    auto_kinds = set(opts.get("auto", []))
    fixable = [f for f in findings if f["args"]]
    auto = [f for f in fixable if f["kind"] in auto_kinds]
    rest = [f for f in fixable if f["kind"] not in auto_kinds]
    if len(auto) > int(opts.get("max_auto", 50) or 50):
        rest, auto = auto + rest, []                 # unusually many: a person decides
    return auto, rest


def run_autofix(log=print, run_csv=None, run_text=None, users=None) -> list[str]:
    from .. import activity, team
    from ..directory import load_users, run_gam_csv, run_gam_text
    run_csv = run_csv or (lambda a: run_gam_csv(a, 1800))
    run_text = run_text or run_gam_text
    o, af = options(), autofix_options()
    users = users if users is not None else load_users()
    findings, notes = build(o.get("profile", ""), users, run_csv, o)
    auto, rest = split_autofix(findings, af)
    lines = [f"Mismatch report: {len(findings)} finding(s)."] + notes
    bad = 0
    dry = settings.get("safety/dry_run", False)
    for f in auto:
        for cmd in f["args"]:
            if dry:
                continue
            c, _out = run_text(cmd, 300)
            bad += 1 if c else 0
            activity.record(cmd, c, "done" if c == 0 else "failed", None,
                            settings.get("profile/current", "") or "Default",
                            note="nightly mismatch fix")
    if auto:
        lines.append(f"Fixed automatically: {len(auto)}" + (f" ({bad} failed)" if bad else "") +
                     (" – dry run, nothing changed" if dry else ""))
    if rest and af.get("send_rest", True) and team.folder():
        team.new_request([a for f in rest for a in f["args"]],
                         "Nightly mismatch report:\n" + "\n".join(
                             f"• {f['Who']} – {f['Problem']}: {f['Details']}"
                             for f in rest[:60]),
                         title=f"Mismatch fixes ({len(rest)})", by="nightly mismatch fix",
                         extra={"kind": "mismatch"}, dedupe="mismatch-nightly")
        lines.append(f"Sent {len(rest)} fix(es) for approval.")
    try:
        from .. import scorecard
        scorecard.record({"mismatches": len(findings)})
    except Exception:  # noqa: BLE001
        pass
    for ln in lines:
        log(ln)
    return lines
