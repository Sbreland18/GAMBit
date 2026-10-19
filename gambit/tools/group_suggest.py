"""Suggest automatic groups: find hand-kept groups whose members match an org unit (or a
job title / department) almost exactly, and offer to turn them into an automatic group
rule so they stop drifting. New rules start as "only add people" so nothing is removed
until you've looked at the preview on Groups → Automatic groups."""

from __future__ import annotations

from collections import defaultdict

MEMBERS_ARGS = ["print", "group-members", "fields", "email,role,type"]


def _ancestors(ou: str) -> list[str]:
    parts = [p for p in (ou or "/").split("/") if p]
    return ["/" + "/".join(parts[:i]) for i in range(len(parts), 0, -1)]


def members_by_group(rows: list[dict]) -> dict[str, set]:
    out = defaultdict(set)
    for r in rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        g, e = low.get("group", "").lower(), low.get("email", "").lower()
        if g and e and low.get("type", "USER").upper() in ("USER", "") and \
                low.get("role", "MEMBER").upper() == "MEMBER":
            out[g].add(e)
    return out


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def suggest(members: dict[str, set], users: list[dict], rules: list[dict],
            threshold: float = 0.85, min_members: int = 5) -> list[dict]:
    active = [u for u in users if not u.get("suspended")]
    by_ou_tree = defaultdict(set)
    for u in active:
        for a in _ancestors(u.get("ou", "")):
            by_ou_tree[a].add(u["email"].lower())
    by_title, by_dept = defaultdict(set), defaultdict(set)
    for u in active:
        if u.get("title"):
            by_title[u["title"].strip().lower()].add(u["email"].lower())
        if u.get("department"):
            by_dept[u["department"].strip().lower()].add(u["email"].lower())
    ou_of = {u["email"].lower(): u.get("ou", "") for u in users}
    ruled = {(r.get("group") or "").lower() for r in rules}
    out = []
    for g, mem in sorted(members.items()):
        if g in ruled or len(mem) < min_members:
            continue
        cands = set()
        for e in mem:
            cands.update(_ancestors(ou_of.get(e, "")))
        best = (0.0, "", "")
        for ou in cands:
            if ou == "/":
                continue
            j = _jaccard(mem, by_ou_tree.get(ou, set()))
            if j > best[0]:
                best = (j, "ou", ou)
        for kind, table in (("title", by_title), ("department", by_dept)):
            for k, s in table.items():
                if len(s) >= min_members:
                    j = _jaccard(mem, s)
                    if j > best[0]:
                        best = (j, kind, k)
        if best[0] < threshold:
            continue
        target = by_ou_tree[best[2]] if best[1] == "ou" else \
            (by_title if best[1] == "title" else by_dept)[best[2]]
        out.append({"Group": g, "Members": len(mem),
                    "Matches": {"ou": "everyone in/under ", "title": "title: ",
                                "department": "department: "}[best[1]] + best[2],
                    "Match": f"{round(best[0] * 100)}%", "Would add": len(target - mem),
                    "Would remove": len(mem - target), "kind": best[1], "key": best[2]})
    return sorted(out, key=lambda x: (-float(x["Match"][:-1]), x["Group"]))


def rule_for(s: dict) -> dict:
    from ..group_rules import new_rule
    r = new_rule()
    r.update(group=s["Group"], name=s["Group"].split("@")[0], create=False, mode="addonly")
    if s["kind"] == "ou":
        r["ous"] = [s["key"]]
    elif s["kind"] == "title":
        r["title"] = s["key"]
    else:
        r["department"] = s["key"]
    return r
