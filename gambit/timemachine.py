"""Account time machine: every night GAMbit saves each account's org unit, status, aliases,
licenses and group memberships. Pick a date to see what an account looked like then, and
put it back to that state (through Approvals)."""

from __future__ import annotations

import datetime
import gzip
import json
import os
import re

from .settings import settings

USERS_ARGS = ["print", "users", "fields", "primaryemail,name,ou,suspended,aliases", "licenses"]
MEMBERS_ARGS = ["print", "group-members", "fields", "email,role"]
TASK = {"name": "GAMbit account time machine", "args": ["--task", "timemachine"],
        "freq": "daily", "time": "01:30",
        "what": "Saves every account's org unit, groups, aliases and licenses each night",
        "standard": False}


def keep_days() -> int:
    return int(settings.get("timemachine/keep_days", 90) or 90)


def folder() -> str:
    from . import team
    if team.folder():
        d = os.path.join(team.folder(), "timemachine")
    else:
        from .support import logs_dir
        d = os.path.join(os.path.dirname(logs_dir()), "timemachine")
    os.makedirs(d, exist_ok=True)
    return d


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _split(v: str) -> list[str]:
    return [x for x in re.split(r"[\s,]+", v or "") if x]


def build(user_rows: list[dict], member_rows: list[dict]) -> dict:
    data = {}
    for r in user_rows:
        low = _low(r)
        e = low.get("primaryemail", "").lower()
        if not e:
            continue
        aliases, lic = [], []
        for k, v in low.items():
            if k.startswith("aliases") and "count" not in k:
                aliases += _split(v)
            elif k.startswith("licenses") and "display" not in k and "count" not in k:
                lic += _split(v)
        data[e] = {"name": low.get("name.fullname", ""), "ou": low.get("orgunitpath", ""),
                   "suspended": low.get("suspended", "").lower() == "true",
                   "aliases": sorted({a.lower() for a in aliases if "@" in a}),
                   "licenses": sorted(set(lic)), "groups": {}}
    for r in member_rows:
        low = _low(r)
        e, g = low.get("email", "").lower(), low.get("group", "").lower()
        if e in data and g:
            data[e]["groups"][g] = (low.get("role") or "MEMBER").upper()
    return data


def save(data: dict, day: datetime.date | None = None) -> str:
    day = day or datetime.date.today()
    path = os.path.join(folder(), f"{day.isoformat()}.json.gz")
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)
    cut = (day - datetime.timedelta(days=keep_days())).isoformat()
    for f in os.listdir(folder()):
        if f.endswith(".json.gz") and f[:10] < cut:
            try:
                os.remove(os.path.join(folder(), f))
            except OSError:
                pass
    return path


def dates() -> list[str]:
    return sorted((f[:10] for f in os.listdir(folder()) if f.endswith(".json.gz")),
                  reverse=True)


def load(day: str) -> dict:
    with gzip.open(os.path.join(folder(), f"{day}.json.gz"), "rt", encoding="utf-8") as fh:
        return json.load(fh)


def account(day: str, email: str) -> dict | None:
    return load(day).get(email.lower())


def history(email: str, limit: int = 120) -> list[tuple[str, dict]]:
    out = []
    for d in dates()[:limit]:
        try:
            a = load(d).get(email.lower())
        except (OSError, ValueError, EOFError):
            continue
        if a:
            out.append((d, a))
    return out


def changes_over_time(email: str) -> list[dict]:
    """Day-by-day what changed for one account (newest first)."""
    hist = sorted(history(email))
    out = []
    for (d0, a), (d1, b) in zip(hist, hist[1:]):
        for row in diff(a, b):
            out.append({"Date": d1, **row})
    return list(reversed(out))


def diff(then: dict, now: dict) -> list[dict]:
    rows = []
    if (then.get("ou") or "/") != (now.get("ou") or "/"):
        rows.append({"What": "Org unit", "Then": then.get("ou"), "Now": now.get("ou")})
    if bool(then.get("suspended")) != bool(now.get("suspended")):
        rows.append({"What": "Status", "Then": "suspended" if then["suspended"] else "active",
                     "Now": "suspended" if now["suspended"] else "active"})
    if then.get("name") and then.get("name") != now.get("name"):
        rows.append({"What": "Name", "Then": then["name"], "Now": now.get("name", "")})
    for key, label in (("aliases", "Alias"), ("licenses", "License")):
        a, b = set(then.get(key, [])), set(now.get(key, []))
        for x in sorted(a - b):
            rows.append({"What": label, "Then": x, "Now": "(gone)"})
        for x in sorted(b - a):
            rows.append({"What": label, "Then": "(none)", "Now": x})
    g0, g1 = then.get("groups", {}), now.get("groups", {})
    for g in sorted(set(g0) | set(g1)):
        if g0.get(g) != g1.get(g):
            rows.append({"What": "Group", "Then": f"{g} ({g0[g].lower()})" if g in g0 else
                         "(not a member)", "Now": f"{g} ({g1[g].lower()})" if g in g1 else
                         "(not a member)"})
    return rows


def restore_commands(email: str, then: dict, now: dict,
                     groups_too: bool = True) -> list[tuple[str, list[str]]]:
    steps = []
    if (then.get("ou") or "/") != (now.get("ou") or "/") and then.get("ou"):
        steps.append((f"Move back to {then['ou']}", ["update", "user", email, "ou", then["ou"]]))
    if bool(then.get("suspended")) != bool(now.get("suspended")):
        on = "on" if then.get("suspended") else "off"
        steps.append(("Suspend again" if on == "on" else "Unsuspend",
                      ["update", "user", email, "suspended", on]))
    for a in sorted(set(then.get("aliases", [])) - set(now.get("aliases", []))):
        steps.append((f"Add back alias {a}", ["create", "alias", a, "user", email]))
    for sku in sorted(set(then.get("licenses", [])) - set(now.get("licenses", []))):
        steps.append((f"Add back license {sku}", ["user", email, "add", "license", sku]))
    for sku in sorted(set(now.get("licenses", [])) - set(then.get("licenses", []))):
        steps.append((f"Remove license {sku}", ["user", email, "delete", "license", sku]))
    if groups_too:
        g0, g1 = then.get("groups", {}), now.get("groups", {})
        for g in sorted(set(g0) - set(g1)):
            role = {"OWNER": "owner", "MANAGER": "manager"}.get(g0[g], "member")
            steps.append((f"Add back to {g}", ["update", "group", g, "add", role, "user", email]))
        for g in sorted(set(g1) - set(g0)):
            steps.append((f"Take out of {g}", ["update", "group", g, "remove", "user", email]))
    return steps


def run(log=print, run_csv=None) -> int:
    from .directory import run_gam_csv
    run_csv = run_csv or (lambda a: run_gam_csv(a, 3600))
    c1, users, e1 = run_csv(USERS_ARGS)
    if c1 != 0:
        raise RuntimeError("Couldn't read users: " + (e1 or "").strip()[-200:])
    c2, members, e2 = run_csv(MEMBERS_ARGS)
    if c2 != 0:
        log("Couldn't read group members – saving accounts only: " + (e2 or "").strip()[-160:])
        members = []
    data = build(users, members)
    path = save(data)
    log(f"Time machine: saved {len(data)} account(s) to {os.path.basename(path)}.")
    return len(data)
