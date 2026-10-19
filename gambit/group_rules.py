"""Rule-based groups: "everyone in /Students/Hancock Middle/Grade 7", "all teachers at
Central", "titles containing Coach" … rebuilt from the user list (nightly if you like).

Only plain members are added or removed – owners and managers are never touched, and
"always include" addresses are kept.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import re
import os
import uuid

from .settings import settings


def _path() -> str:
    from . import team
    if team.folder():
        d = os.path.join(team.folder(), "groups")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "rules.json")
    return ""


def load() -> list[dict]:
    p = _path()
    try:
        if p:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        return json.loads(settings.get("groups/rules", "[]") or "[]")
    except (OSError, ValueError):
        return []


def save(rules: list[dict]):
    p = _path()
    if p:
        tmp = p + f".{uuid.uuid4().hex[:6]}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(rules, fh, indent=2)
        os.replace(tmp, p)
    else:
        settings.set("groups/rules", json.dumps(rules))


def new_rule() -> dict:
    return {"id": uuid.uuid4().hex[:8], "group": "", "name": "", "ous": [],
            "children": True, "title": "", "department": "", "exclude_ous": [],
            "suspended": False, "mode": "sync", "always": [], "create": True,
            "enabled": True, "last_run": "", "last_result": ""}


def _under(ou: str, root: str, children: bool) -> bool:
    ou = ((ou or "/").rstrip("/") or "/").lower()
    root = ((root or "/").rstrip("/") or "/").lower()
    if ou == root:
        return True
    return children and (root == "/" or ou.startswith(root + "/"))


def _contains_any(value: str, wanted: str) -> bool:
    words = [w.strip().lower() for w in (wanted or "").split(",") if w.strip()]
    return not words or any(w in (value or "").lower() for w in words)


def members_for(rule: dict, users: list[dict]) -> set[str]:
    out = set()
    for u in users:
        if u.get("suspended") and not rule.get("suspended"):
            continue
        ou = u.get("ou", "")
        if rule.get("ous") and not any(_under(ou, r, rule.get("children", True))
                                       for r in rule["ous"]):
            continue
        if any(_under(ou, r, True) for r in rule.get("exclude_ous", [])):
            continue
        if not _contains_any(u.get("title", ""), rule.get("title", "")):
            continue
        if not _contains_any(u.get("department", ""), rule.get("department", "")):
            continue
        out.add(u["email"].lower())
    out |= {a.strip().lower() for a in rule.get("always", []) if "@" in a}
    return out


def parse_members(text: str) -> tuple[set[str], set[str]]:
    """`print group-members group G` → (plain user members, owners+managers)."""
    plain, special = set(), set()
    for r in csv.DictReader(io.StringIO(text or "")):
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        e = low.get("email", "").lower()
        if not e:
            continue
        if low.get("role", "MEMBER").upper() in ("OWNER", "MANAGER"):
            special.add(e)
        elif low.get("type", "USER").upper() in ("USER", ""):
            plain.add(e)
    return plain, special


def diff(rule: dict, users: list[dict], members_text: str, exists: bool = True):
    target = members_for(rule, users)
    plain, special = parse_members(members_text) if exists else (set(), set())
    adds = sorted(target - plain - special)
    removes = sorted(plain - target) if rule.get("mode", "sync") == "sync" else []
    return adds, removes


def _chunks(items, n=400):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def commands(rule: dict, adds: list[str], removes: list[str], exists: bool) -> list[list[str]]:
    g = rule["group"]
    cmds = []
    if not exists and rule.get("create", True):
        cmds.append(["create", "group", g, "name", rule.get("name") or g.split("@")[0]])
    for part in _chunks(adds):
        cmds.append(["update", "group", g, "add", "member", "users", ",".join(part)])
    for part in _chunks(removes):
        cmds.append(["update", "group", g, "remove", "member", "users", ",".join(part)])
    return cmds


def describe(rule: dict) -> str:
    bits = []
    if rule.get("ous"):
        bits.append(("in or under " if rule.get("children", True) else "directly in ") +
                    ", ".join(rule["ous"]))
    if rule.get("title"):
        bits.append(f"title contains {rule['title']}")
    if rule.get("department"):
        bits.append(f"department contains {rule['department']}")
    if rule.get("exclude_ous"):
        bits.append("not in " + ", ".join(rule["exclude_ous"]))
    if not bits:
        bits.append("everyone")
    return "; ".join(bits) + ("" if rule.get("mode", "sync") == "sync" else " (add only)")


def run_all(log=print) -> int:
    """Unattended: rebuild every enabled rule. Returns number of failed rules."""
    from . import activity
    from .directory import load_users, run_gam_text
    users = load_users()
    rules = load()
    failed = 0
    for rule in rules:
        if not rule.get("enabled", True) or "@" not in rule.get("group", ""):
            continue
        code, out = run_gam_text(["print", "group-members", "group", rule["group"]], 300)
        exists = code == 0
        if not exists and not re.search(r"does not exist|not found|notfound|"
                                        r"doesn't exist", out or "", re.I):
            failed += 1
            rule["last_result"] = "couldn't read the group – skipped: " + \
                (out or "").strip()[-120:]
            log(f"{rule['group']}: {rule['last_result']}")
            continue
        adds, removes = diff(rule, users, out if exists else "", exists)
        if settings.get("safety/dry_run", False):
            rule["last_result"] = f"dry run: +{len(adds)} −{len(removes)}"
            log(f"{rule['group']}: {rule['last_result']}")
            continue
        bad = 0
        for cmd in commands(rule, adds, removes, exists):
            c, o = run_gam_text(cmd, 600)
            activity.record(cmd, c, "done" if c == 0 else "failed",
                            activity.infer_undo(cmd, users),
                            settings.get("profile/current", "") or "Default",
                            note="automatic group")
            bad += c != 0
        rule["last_run"] = datetime.datetime.now().isoformat(timespec="minutes")
        rule["last_result"] = f"+{len(adds)} −{len(removes)}" + (f", {bad} failed" if bad
                                                                  else "")
        failed += bad > 0
        log(f"{rule['group']}: {rule['last_result']}")
    save(rules)
    return failed
