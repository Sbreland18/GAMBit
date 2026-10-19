"""Testing-season mode and staged policy rollouts.

Both apply a set of Chrome policies to org units and can put things back exactly:
before changing an org unit GAMbit saves the policies set directly on it, and the revert
puts those values back (or removes policies that weren't set there before).

• Testing mode – apply a testing profile (copied from a template org unit you set up in
  the Admin console, or a list of policies) between two dates; the daily task applies it on
  the first day and reverts it after the last.
• Staged rollout – apply to a pilot org unit, watch tickets and devices for a few days, then
  promote to everyone or roll back.
"""

from __future__ import annotations

import datetime
import json
import uuid

from ..settings import settings
from .chrome import copy_plan, direct_policies_args, policy_args


def _store_load() -> list[dict]:
    from .. import team
    if team.folder():
        d = team.read_shared("policy_plans.json")
        if d:
            return d.get("plans", [])
    try:
        return json.loads(settings.get("policyplans/plans", "[]") or "[]")
    except ValueError:
        return []


def load() -> list[dict]:
    return _store_load()


def save(plans: list[dict]):
    from .. import team
    if team.folder():
        team.write_shared("policy_plans.json", {"plans": plans})
    settings.set("policyplans/plans", json.dumps(plans))


def new_plan(kind: str, name: str, targets: list[str], template_ou: str = "",
             policies: list[dict] | None = None, start: str = "", end: str = "",
             watch_days: int = 5) -> dict:
    return {"id": uuid.uuid4().hex[:8], "kind": kind, "name": name, "targets": targets,
            "template_ou": template_ou, "policies": policies or [], "start": start,
            "end": end, "watch_days": watch_days, "state": "scheduled", "before": {},
            "applied": [], "log": [], "baseline": {}, "watch": []}


def parse_policies(text: str) -> list[dict]:
    """'schema field=value field=value' per line → [{schema, values}]"""
    out = []
    for ln in (text or "").splitlines():
        parts = ln.strip().split()
        if not parts or parts[0].startswith("#"):
            continue
        vals = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                vals[k] = v
        if vals:
            out.append({"schema": parts[0], "values": vals})
    return out


def policies_text(pols: list[dict]) -> str:
    return "\n".join(p["schema"] + " " + " ".join(f"{k}={v}" for k, v in p["values"].items())
                     for p in pols)


def commands_for(plan: dict, ou: str, template_rows: list[dict] | None = None) -> list:
    if plan.get("template_ou"):
        steps, _skipped = copy_plan(template_rows or [], ou)
        return [s["args"] for s in steps]
    return [policy_args(p["schema"], p["values"], ou) for p in plan.get("policies", [])]


def schemas_in(cmds: list[list[str]]) -> list[str]:
    return [c[2] for c in cmds if c[:2] == ["update", "chromepolicy"] and len(c) > 2]


def revert_commands(before_rows: list[dict], applied_schemas: list[str], ou: str) -> list:
    """Put back what was set directly on the OU before (or remove what wasn't)."""
    plan, _skipped = copy_plan(before_rows, ou)
    by = {p["schema"]: p["args"] for p in plan}
    out = []
    for s in dict.fromkeys(applied_schemas):
        out.append(by[s] if s in by else ["delete", "chromepolicy", s, "ou", ou])
    return out


def due(plan: dict, today: datetime.date | None = None) -> str:
    """'apply', 'revert' or '' for a testing-mode plan."""
    if plan.get("kind") != "testing":
        return ""
    today = (today or datetime.date.today()).isoformat()
    if plan["state"] == "scheduled" and plan.get("start", "") <= today <= plan.get("end", ""):
        return "apply"
    if plan["state"] == "applied" and today > plan.get("end", ""):
        return "revert"
    return ""


# ------------------------------------------------------------- running ---
def _record(cmd, code, note):
    from .. import activity
    activity.record(cmd, code, "done" if code == 0 else "failed", None,
                    settings.get("profile/current", "") or "Default", note=note)


def apply(plan: dict, ous: list[str], run_csv, run_text, log=print) -> int:
    """Snapshot each OU, then apply. Returns failures."""
    tpl = None
    if plan.get("template_ou"):
        c, tpl, e = run_csv(direct_policies_args(plan["template_ou"]))
        if c != 0:
            raise RuntimeError(f"Couldn't read the template org unit: {(e or '')[-200:]}")
    bad = 0
    for ou in ous:
        c, rows, e = run_csv(direct_policies_args(ou))
        if c != 0:
            raise RuntimeError(f"Couldn't save {ou}'s current policies – nothing changed: "
                               f"{(e or '')[-200:]}")
        plan["before"].setdefault(ou, rows)
        cmds = commands_for(plan, ou, tpl)
        for cmd in cmds:
            code, _out = run_text(cmd, 300)
            _record(cmd, code, f"{plan['kind']} “{plan['name']}”")
            bad += 1 if code else 0
        plan["applied"] = sorted(set(plan.get("applied", [])) | {ou})
        plan.setdefault("schemas", {})[ou] = schemas_in(cmds)
        plan["log"].append(f"{datetime.datetime.now():%Y-%m-%d %H:%M} applied to {ou}"
                           + (f" ({bad} failed)" if bad else ""))
        log(f"“{plan['name']}”: applied {len(cmds)} polic(ies) to {ou}")
    return bad


def revert(plan: dict, run_text, log=print, ous: list[str] | None = None) -> int:
    bad = 0
    for ou in ous or list(plan.get("applied", [])):
        cmds = revert_commands(plan["before"].get(ou, []),
                               plan.get("schemas", {}).get(ou, []), ou)
        for cmd in cmds:
            code, _out = run_text(cmd, 300)
            _record(cmd, code, f"{plan['kind']} “{plan['name']}” – put back")
            bad += 1 if code else 0
        plan["applied"] = [x for x in plan.get("applied", []) if x != ou]
        plan["log"].append(f"{datetime.datetime.now():%Y-%m-%d %H:%M} put back {ou}"
                           + (f" ({bad} failed)" if bad else ""))
        log(f"“{plan['name']}”: put back {ou}")
    return bad


def run_due(log=print, run_csv=None, run_text=None, today=None) -> list[str]:
    """Daily task: start and end testing windows."""
    from ..directory import run_gam_csv, run_gam_text
    run_csv = run_csv or (lambda a: run_gam_csv(a, 600))
    run_text = run_text or run_gam_text
    plans = load()
    lines = []
    if settings.get("safety/dry_run", False):
        return lines
    for p in plans:
        act = due(p, today)
        try:
            if act == "apply":
                bad = apply(p, p["targets"], run_csv, run_text, log)
                p["state"] = "applied"
                lines.append(f"Testing mode “{p['name']}” is ON for {', '.join(p['targets'])}"
                             + (f" ({bad} failed)" if bad else ""))
            elif act == "revert":
                bad = revert(p, run_text, log)
                p["state"] = "reverted"
                lines.append(f"Testing mode “{p['name']}” is OFF – settings put back"
                             + (f" ({bad} failed)" if bad else ""))
        except Exception as exc:  # noqa: BLE001
            lines.append(f"Testing mode “{p['name']}” failed: {exc}")
    save(plans)
    if lines:
        try:
            from .. import alerts
            alerts.notify("\n".join(lines), "GAMbit testing mode")
        except Exception:  # noqa: BLE001
            pass
    for ln in lines:
        log(ln)
    return lines


# ------------------------------------------------------------ rollouts ---
def _under(ou: str, root: str) -> bool:
    ou, root = (ou or "/").rstrip("/").lower(), (root or "/").rstrip("/").lower()
    return ou == root or ou.startswith(root + "/") or root == ""


def watch_numbers(plan: dict, users: list[dict], devices: list[dict] | None,
                  tickets: list[dict] | None, today: datetime.date | None = None) -> dict:
    """Pilot health: open tickets from people in the pilot org unit, and devices there that
    haven't checked in since the pilot started."""
    pilot = plan["targets"][0] if plan.get("targets") else ""
    start = plan.get("start") or (today or datetime.date.today()).isoformat()
    people = {u["email"].lower() for u in users if _under(u.get("ou"), pilot)}
    out = {"date": (today or datetime.date.today()).isoformat()}
    if tickets is not None:
        out["tickets"] = sum(1 for t in tickets if (t.get("for_email") or "").lower() in people
                             and (t.get("created") or "")[:10] >= start)
    if devices is not None:
        inside = [d for d in devices if _under(d.get("ou"), pilot) and
                  d.get("status", "ACTIVE") == "ACTIVE"]
        out["devices"] = len(inside)
        out["not_checking_in"] = sum(1 for d in inside if d.get("last_sync") and
                                     d["last_sync"].isoformat() < start)
    return out


def verdict(plan: dict) -> str:
    w = plan.get("watch") or []
    b = plan.get("baseline") or {}
    if not w:
        return "No numbers yet – check again tomorrow."
    last = w[-1]
    worse = []
    if last.get("tickets", 0) > max(2, b.get("tickets", 0) * 1.5):
        worse.append(f"{last['tickets']} new tickets from the pilot group")
    if last.get("not_checking_in", 0) > b.get("not_checking_in", 0) + max(
            2, 0.05 * (last.get("devices") or 0)):
        worse.append(f"{last['not_checking_in']} devices stopped checking in")
    days = (datetime.date.fromisoformat(last["date"]) -
            datetime.date.fromisoformat(plan.get("start") or last["date"])).days
    if worse:
        return "⚠ Looks worse: " + "; ".join(worse) + ". Consider rolling back."
    if days < int(plan.get("watch_days", 5) or 5):
        return f"So far so good ({days} of {plan.get('watch_days', 5)} days watched)."
    return "✔ No problems seen – ready to roll out to everyone."


def run_watch(log=print, run_csv=None, users=None, tickets=None) -> list[str]:
    """Daily task: record pilot numbers for rollouts in progress; alert if it looks worse."""
    from .. import fleet
    from ..directory import load_users, run_gam_csv
    plans = [p for p in load() if p.get("kind") == "rollout" and p.get("state") == "pilot"]
    if not plans:
        return []
    run_csv = run_csv or (lambda a: run_gam_csv(a, 1800))
    users = users if users is not None else load_users()
    code, rows, _e = run_csv(["print", "cros", "fields", fleet.FIELDS, "listlimit", "1"])
    devs = fleet.devices(rows) if code == 0 else None
    if tickets is None:
        try:
            from ..integrations import ticketing
            tickets = ticketing.list_open({}) if ticketing.configured() and \
                ticketing.can("list") else None
        except Exception:  # noqa: BLE001
            tickets = None
    all_plans = load()
    lines = []
    for p in all_plans:
        if p.get("kind") != "rollout" or p.get("state") != "pilot":
            continue
        nums = watch_numbers(p, users, devs, tickets)
        p["watch"] = [w for w in p.get("watch", []) if w.get("date") != nums["date"]] + [nums]
        v = verdict(p)
        lines.append(f"Rollout “{p['name']}”: {v}")
        if v.startswith("⚠"):
            try:
                from .. import alerts
                alerts.notify(f"Rollout “{p['name']}” on {p['targets'][0]}: {v}",
                              "GAMbit staged rollout")
            except Exception:  # noqa: BLE001
                pass
    save(all_plans)
    for ln in lines:
        log(ln)
    return lines
