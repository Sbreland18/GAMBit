"""Practice run: before the grade move, graduation or a clean-up rule runs, show its full
effect against today's data – who moves where, who is suspended or deleted, which automatic
groups change, which licenses are freed and which Chromebooks would follow their student.
Nothing is sent to Google."""

from __future__ import annotations

import copy
from collections import Counter, defaultdict


def _under(ou: str, root: str, children: bool = True) -> bool:
    ou, root = (ou or "/").rstrip("/") or "/", (root or "/").rstrip("/") or "/"
    return ou == root or (children and (root == "/" or ou.startswith(root + "/")))


ATTR_WORDS = {"ou", "org", "suspended", "suspend", "firstname", "lastname", "email",
              "primaryemail", "password", "changepassword", "gal", "includeinglobaladdresslist",
              "externalid", "organization", "title", "department"}


def _apply_attrs(u: dict, attrs: list[str], notes: list[str]):
    low = [a.lower() for a in attrs]
    i = 0
    while i < len(low):
        k = low[i]
        v = attrs[i + 1] if i + 1 < len(attrs) else ""
        if k in ("ou", "org"):
            if (u.get("ou") or "/") != v:
                notes.append(f"move {u.get('ou') or '/'} → {v}")
            u["ou"] = v
            i += 2
        elif k in ("suspended", "suspend"):
            on = v.lower() in ("on", "true")
            if bool(u.get("suspended")) != on:
                notes.append("suspend" if on else "unsuspend")
            u["suspended"] = on
            i += 2
        elif k == "firstname":
            u["_first"] = v
            notes.append(f"first name → {v}")
            i += 2
        elif k == "lastname":
            u["_last"] = v
            notes.append(f"last name → {v}")
            i += 2
        elif k in ("email", "primaryemail"):
            notes.append(f"rename to {v}")
            u["_rename"] = v
            i += 2
        elif k == "password":
            notes.append("new password")
            i += 2
        elif k in ("changepassword", "gal", "includeinglobaladdresslist"):
            i += 2
        elif k == "externalid":
            i += 3
        else:
            i += 1


def simulate(commands: list[list[str]], users: list[dict], rules: list[dict] | None = None,
             devices: list[dict] | None = None, assign_opts: dict | None = None) -> dict:
    """Play the commands against a copy of today's accounts."""
    before = {u["email"].lower(): u for u in users}
    after = {e: copy.deepcopy(u) for e, u in before.items()}
    notes = defaultdict(list)
    deleted, created, licenses = set(), [], Counter()
    unsupported = []
    for cmd in commands:
        low = [a.lower() for a in cmd]
        if low[:2] == ["update", "ou"] and "move" in low:
            # update ou B move ou A  (rollover) – everyone directly in A goes to B
            dest = cmd[2]
            j = low.index("move")
            src = cmd[j + 2] if j + 2 < len(cmd) and low[j + 1] in ("ou", "org") else ""
            for e, u in after.items():
                if e not in deleted and (u.get("ou") or "/") == src:
                    _apply_attrs(u, ["ou", dest], notes[e])
        elif low[:1] and low[0] in ("ou", "ou_and_children", "ou_ns", "ou_and_children_ns") \
                and low[2:4] == ["update", "user"]:
            kids = low[0].startswith("ou_and_children")
            for e, u in after.items():
                if e not in deleted and _under(u.get("ou"), cmd[1], kids):
                    _apply_attrs(u, cmd[4:], notes[e])
        elif low[:2] == ["update", "user"] and len(cmd) > 2:
            e = cmd[2].lower()
            if e in after:
                _apply_attrs(after[e], cmd[3:], notes[e])
        elif low[:2] == ["delete", "user"] and len(cmd) > 2:
            e = cmd[2].lower()
            if e in after:
                deleted.add(e)
                notes[e].append("delete the account")
        elif low[:2] == ["create", "user"] and len(cmd) > 2:
            u = {"email": cmd[2].lower(), "name": "", "ou": "/", "suspended": False}
            n = []
            _apply_attrs(u, cmd[3:], n)
            after[u["email"]] = u
            created.append(u["email"])
            notes[u["email"]].append("new account" + (f" in {u['ou']}" if u["ou"] else ""))
        elif low[:1] == ["user"] and len(low) > 4 and low[2:4] == ["delete", "license"]:
            e = cmd[1].lower()
            licenses[cmd[4]] += 1
            notes[e].append(f"release license {cmd[4]}")
        elif low[:1] == ["cros_sn"]:
            notes[f"device {cmd[1].upper()}"].append(" ".join(cmd[2:])[:80])
        else:
            unsupported.append(" ".join(cmd)[:120])
    people = []
    for e in sorted(notes):
        b, a = before.get(e, {}), after.get(e, {})
        people.append({"Account": e, "Before": b.get("ou", "") + (" (suspended)" if
                                                                   b.get("suspended") else ""),
                       "After": "deleted" if e in deleted else (a.get("ou", "") +
                                                                (" (suspended)" if
                                                                 a.get("suspended") else "")),
                       "What happens": "; ".join(dict.fromkeys(notes[e]))})
    moves = Counter()
    for e, a in after.items():
        b = before.get(e)
        if b and e not in deleted and (b.get("ou") or "/") != (a.get("ou") or "/"):
            moves[(b.get("ou") or "/", a.get("ou") or "/")] += 1
    live_after = [u for e, u in after.items() if e not in deleted]
    groups = []
    for r in rules or []:
        if not r.get("enabled", True) or not r.get("group"):
            continue
        from .group_rules import members_for
        old = members_for(r, users)
        new = members_for(r, live_after)
        add, rem = sorted(new - old), sorted(old - new)
        if add or rem:
            groups.append({"Group": r["group"], "Joins": len(add), "Leaves": len(rem),
                           "Examples": ", ".join((["+" + x for x in add[:3]] +
                                                  ["−" + x for x in rem[:3]]))})
    dev_rows = []
    if devices is not None and assign_opts and assign_opts.get("move_ou", True):
        from .tools.automation import school_of
        root = assign_opts.get("student_root", "/Students")
        depth = int(assign_opts.get("school_depth", 1) or 1)
        tpl = assign_opts.get("ou_template", "/Chromebooks/{school}")
        for d in devices:
            e = (d.get("user") or "").lower()
            if not e or e not in before:
                continue
            if e in deleted or after[e].get("suspended"):
                if not before[e].get("suspended"):
                    dev_rows.append({"Serial": d["serial"], "Student": e,
                                     "What happens": "student leaves – device to collect"})
                continue
            s0 = school_of(before[e].get("ou", ""), root, depth)
            s1 = school_of(after[e].get("ou", ""), root, depth)
            if s1 and s0 != s1:
                dev_rows.append({"Serial": d["serial"], "Student": e,
                                 "What happens": f"moves to {tpl.replace('{school}', s1)}"})
    summary = [("Accounts changed", sum(1 for p in people if not p["Account"].startswith(
                "device "))),
               ("Moved to another org unit", sum(moves.values())),
               ("Suspended", sum(1 for e, a in after.items() if a.get("suspended") and
                                 e in before and not before[e].get("suspended"))),
               ("Unsuspended", sum(1 for e, a in after.items() if not a.get("suspended") and
                                   e in before and before[e].get("suspended"))),
               ("Deleted", len(deleted)), ("Created", len(created)),
               ("Licenses released", sum(licenses.values())),
               ("Automatic groups that change", len(groups)),
               ("Chromebooks affected", len(dev_rows) + sum(
                   1 for p in people if p["Account"].startswith("device "))),
               ("Commands not simulated", len(unsupported))]
    return {"people": people, "summary": summary,
            "moves": [{"From": a, "To": b, "Accounts": n} for (a, b), n in
                      sorted(moves.items(), key=lambda kv: -kv[1])],
            "groups": groups, "devices": dev_rows, "unsupported": unsupported}
