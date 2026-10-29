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
MEMBERS_ARGS = ["print", "group-members", "fields", "email,role,type"]
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


# ================================================================ groups ===
def _groups_dir() -> str:
    d = os.path.join(folder(), "groups")
    os.makedirs(d, exist_ok=True)
    return d


def build_groups(member_rows: list[dict]) -> dict:
    """{group: {member: {"role", "type"}}} – everyone, including outside addresses and
    groups inside groups (the per-account snapshot only has the district's own accounts)."""
    out: dict = {}
    for r in member_rows:
        low = _low(r)
        g, e = low.get("group", "").lower(), low.get("email", "").lower()
        if g and e:
            out.setdefault(g, {})[e] = {"role": (low.get("role") or "MEMBER").upper(),
                                        "type": (low.get("type") or "USER").upper()}
    return out


def save_groups(groups: dict, day: datetime.date | None = None) -> str:
    day = day or datetime.date.today()
    path = os.path.join(_groups_dir(), f"{day.isoformat()}.json.gz")
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(groups, fh)
    os.replace(tmp, path)
    cut = (day - datetime.timedelta(days=keep_days())).isoformat()
    for f in os.listdir(_groups_dir()):
        if f.endswith(".json.gz") and f[:10] < cut:
            try:
                os.remove(os.path.join(_groups_dir(), f))
            except OSError:
                pass
    return path


def group_then(day: str, group: str) -> tuple[dict, bool]:
    """(members on that day, complete). Nights saved before full group snapshots only know
    the district's own accounts – complete is then False."""
    g = group.strip().lower()
    p = os.path.join(_groups_dir(), f"{day}.json.gz")
    if os.path.isfile(p):
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            return dict(json.load(fh).get(g, {})), True
    out = {}
    for e, a in load(day).items():
        role = (a.get("groups") or {}).get(g)
        if role:
            out[e] = {"role": role, "type": "USER"}
    return out, False


def group_now(group: str, run_csv) -> dict:
    code, rows, err = run_csv(["print", "group-members", "group", group, "fields",
                               "email,role,type"])
    if code != 0:
        raise RuntimeError((err or "").strip().splitlines()[-1] if (err or "").strip()
                           else f"Couldn't read the members of {group}.")
    return build_groups([{**r, "group": group} for r in rows]).get(group.lower(), {})


def group_diff(then: dict, now: dict) -> list[dict]:
    rows = []
    for m in sorted(set(then) | set(now)):
        a, b = then.get(m), now.get(m)
        if a and not b:
            rows.append({"Member": m, "Then": a["role"].lower(), "Now": "(not a member)",
                         "Change": "removed since"})
        elif b and not a:
            rows.append({"Member": m, "Then": "(not a member)", "Now": b["role"].lower(),
                         "Change": "added since"})
        elif a["role"] != b["role"]:
            rows.append({"Member": m, "Then": a["role"].lower(), "Now": b["role"].lower(),
                         "Change": "role changed"})
    return rows


def group_restore_commands(group: str, then: dict, now: dict, add_back: bool = True,
                           remove_new: bool = False, roles: bool = True
                           ) -> list[tuple[str, list[str]]]:
    role_word = {"OWNER": "owner", "MANAGER": "manager"}
    steps = []
    for m in sorted(set(then) - set(now)) if add_back else []:
        r = role_word.get(then[m]["role"], "member")
        steps.append((f"Add {m} back as {r}", ["update", "group", group, "add", r, "user",
                                                m]))
    for m in sorted(set(now) - set(then)) if remove_new else []:
        steps.append((f"Take {m} out", ["update", "group", group, "remove", "user", m]))
    for m in sorted(set(then) & set(now)) if roles else []:
        if then[m]["role"] != now[m]["role"]:
            r = role_word.get(then[m]["role"], "member")
            steps.append((f"Make {m} {r} again", ["update", "group", group, "update", r,
                                                  "user", m]))
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
    if members:
        save_groups(build_groups(members))
    log(f"Time machine: saved {len(data)} account(s) to {os.path.basename(path)}.")
    return len(data)
