"""Group hygiene: suspended or former staff still in groups, outside addresses in staff
groups, people who are both direct and nested members, and members whose school doesn't
match a school group – with the remove commands to clean them up."""

from __future__ import annotations

import json
import re
from collections import defaultdict

from ..settings import settings

MEMBERS_ARGS = ["print", "group-members", "fields", "email,role,type,status"]


def options() -> dict:
    try:
        o = json.loads(settings.get("grouphygiene/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"former_root": "/Former", "staff_pattern": "staff", "staff_root": "/Staff",
            "school_groups": "", "domains": "", **o}


def save_options(o: dict):
    settings.set("grouphygiene/options", json.dumps(o))


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def members(rows: list[dict]) -> dict[str, list[dict]]:
    by = defaultdict(list)
    for r in rows:
        low = _low(r)
        g = low.get("group", "").lower()
        e = low.get("email", "").lower()
        if g and e:
            by[g].append({"email": e, "role": low.get("role", "MEMBER").upper(),
                          "type": low.get("type", "USER").upper(),
                          "status": low.get("status", "").upper()})
    return by


def _nested_users(g: str, by: dict, seen=None) -> set[str]:
    seen = seen if seen is not None else set()
    if g in seen:
        return set()
    seen.add(g)
    out = set()
    for m in by.get(g, []):
        if m["type"] == "GROUP":
            out |= {x["email"] for x in by.get(m["email"], []) if x["type"] != "GROUP"}
            out |= _nested_users(m["email"], by, seen)
    return out


from ..oupath import under  # noqa: E402


def check(member_rows: list[dict], users: list[dict], opts: dict | None = None) -> list[dict]:
    """→ [{Group, Member, Problem, Role, fix}]"""
    from ..parent_report import school_of
    from ..next_year import parse_map
    opts = opts or options()
    by = members(member_rows)
    udir = {u["email"].lower(): u for u in users}
    domains = {d.strip().lower().lstrip("@") for d in re.split(r"[,\s]+",
                                                               opts.get("domains", "")) if d}
    if not domains:
        domains = {e.split("@")[-1] for e in udir if "@" in e}
    former = (opts.get("former_root") or "").rstrip("/").lower()
    pat = (opts.get("staff_pattern") or "").lower()
    sroot = opts.get("staff_root", "/Staff")
    school_map = {k.lower(): v for k, v in parse_map(opts.get("school_groups", "")).items()}
    out = []

    def add(g, m, why, level):
        out.append({"Group": g, "Member": m["email"], "Problem": why, "Role": m["role"],
                    "Level": level, "fix": ["update", "group", g, "remove", m["email"]]})
    for g, ms in sorted(by.items()):
        nested = _nested_users(g, by)
        is_staff = bool(pat) and pat in g
        for m in ms:
            if m["type"] == "GROUP":
                continue
            e = m["email"]
            u = udir.get(e)
            dom = e.split("@")[-1]
            if u is not None and u.get("suspended"):
                add(g, m, "account suspended", "high")
            elif u is not None and former and under(u.get("ou") or "", former):
                add(g, m, f"has left ({u.get('ou')})", "high")
            elif dom and dom not in domains and m["type"] in ("USER", "CUSTOMER", "") \
                    and e != "*":
                if is_staff:
                    add(g, m, "outside address in a staff group", "high")
                elif m["role"] in ("OWNER", "MANAGER"):
                    add(g, m, f"outside address is a group {m['role'].lower()}", "medium")
            if e in nested and m["role"] == "MEMBER":
                add(g, m, "also a member through a nested group (direct membership "
                    "not needed)", "low")
            sch = school_map.get(g)
            if sch and u is not None and not u.get("suspended") and \
                    (u.get("ou") or "").lower().startswith(sroot.rstrip("/").lower() + "/"):
                mine = school_of(u["ou"], sroot)
                if mine.lower() != sch.lower():
                    add(g, m, f"works at {mine}, not {sch}", "medium")
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda x: (order[x["Level"]], x["Group"], x["Member"]))


def summary(findings: list[dict]) -> list[dict]:
    c = defaultdict(lambda: defaultdict(int))
    for f in findings:
        c[f["Group"]][f["Problem"].split(" (")[0]] += 1
    return [{"Group": g, "Issues": sum(v.values()),
             "What": ", ".join(f"{n} {k}" for k, n in sorted(v.items(), key=lambda kv: -kv[1]))}
            for g, v in sorted(c.items(), key=lambda kv: -sum(kv[1].values()))]
