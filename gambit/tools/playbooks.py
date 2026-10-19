"""Response playbooks for unusual-activity findings, and the settings drift guard.

Playbooks turn a finding into ready-made responses: lock the account down, open the right
screen already filled in, or remove a new admin role. Changes go through Approvals (or run
straight away for a Full admin who chooses to).

The drift guard looks at what changed between two settings snapshots, skips changes GAMbit
itself made, and proposes putting Chrome policies back as one approval request. Admin
console (Cloud Identity) settings can't be changed through the API, so those are listed
for a person to change back by hand."""

from __future__ import annotations

import datetime
import json
import re

ACCOUNT_RISK = ("Mass download", "Risky sign-in", "Sign-in from an unexpected country",
                "Impossible travel")


def lockdown(who: str, suspend: bool = False) -> list[tuple[str, list[str]]]:
    from .security_ops import lockdown_steps
    steps = lockdown_steps(who, "random", deprovision=True, forward_off=True, suspend=suspend)
    return steps


def actions(f: dict) -> list[dict]:
    """→ [{label, kind: steps|goto|admins, steps, page, tab, prefill, why}]"""
    who, kind = f.get("Who", ""), f.get("Finding", "")
    email = who if "@" in who else ""
    out = []
    if kind in ACCOUNT_RISK and email:
        out.append({"label": "Lock the account down", "kind": "steps",
                    "steps": lockdown(email),
                    "why": "New random password, sign out everywhere, remove app passwords "
                           "and app access, turn off forwarding."})
        out.append({"label": "Lock down and suspend", "kind": "steps",
                    "steps": lockdown(email, True), "why": "Everything above, plus suspend."})
        out.append({"label": "Open the hacked-account check", "kind": "goto",
                    "page": "Workflows", "tab": "Hacked account", "prefill": {"who": email},
                    "call": "look", "why": "Filters, forwarding, delegates and recent "
                                            "sign-ins side by side."})
    if kind == "Risky app allowed" and email and f.get("client_id"):
        out.append({"label": "Remove the app's access", "kind": "steps",
                    "steps": [(f"Remove app access for {email}",
                               ["user", email, "delete", "token", "clientid",
                                f["client_id"]])],
                    "why": "Takes back the access the app was given. Add it to the approved "
                           "list instead if it's fine."})
    if kind == "2-Step Verification turned off" and email:
        out.append({"label": "Open the 2-Step Verification campaign", "kind": "goto",
                    "page": "2-Step Verification", "tab": None, "prefill": {},
                    "why": "Remind them, or check whether 2SV is enforced for their org "
                           "unit."})
    if kind == "Mass delete" and email:
        out.append({"label": "Restore their deleted files", "kind": "goto",
                    "page": "Google Drive", "tab": "Restore files", "prefill": {"who": email},
                    "call": "find", "why": "Lists what they trashed so you can put it back."})
    if kind == "External sharing spike" and email:
        out.append({"label": "Fix their sharing", "kind": "goto", "page": "Google Drive",
                    "tab": "Fix sharing", "prefill": {"who": email}, "call": "scan",
                    "why": "Finds files shared outside the district and removes the links."})
    if kind.startswith("New admin role"):
        m = re.search(r"for ([\w.+'-]+@[\w.-]+)", f.get("Details", ""))
        target = m.group(1) if m else ""
        if target:
            out.append({"label": f"Review {target}'s admin roles", "kind": "admins",
                        "target": target, "role": _role_from(f.get("Details", "")),
                        "why": "Lists their admin roles so you can remove the new one."})
    if email:
        out.append({"label": "Open the audit log for this person", "kind": "goto",
                    "page": "Investigations", "tab": "Audit log", "prefill": {"who": email},
                    "why": "Everything they did in the last few days."})
    return out


def _role_from(details: str) -> str:
    m = re.search(r"“([^”]+)”", details or "")
    return m.group(1) if m else ""


def admin_rows(rows: list[dict], role: str = "") -> list[dict]:
    """`print admins user X` rows → [{id, role, scope}] (the matching role first)."""
    out = []
    for r in rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        rid = low.get("roleassignmentid", "")
        if rid:
            out.append({"id": rid, "role": low.get("role", "") or low.get("roleid", ""),
                        "scope": low.get("orgunit", "") or low.get("scopetype", "")})
    out.sort(key=lambda x: (x["role"].lower() != role.lower(), x["role"]))
    return out


def remove_admin_steps(items: list[dict], who: str) -> list[tuple[str, list[str]]]:
    return [(f"Remove {i['role']} from {who}", ["delete", "admin", i["id"]]) for i in items]


def auto_request(findings: list[dict]) -> dict | None:
    """Watchdog background option: one approval request locking down risky accounts."""
    from .. import team
    risky = [f for f in findings if f.get("Finding") in ACCOUNT_RISK and "@" in f.get("Who", "")]
    if not risky or not team.folder():
        return None
    who = sorted({f["Who"] for f in risky})
    cmds = [a for w in who for _l, a in lockdown(w)]
    return team.new_request(cmds, "Unusual activity:\n" + "\n".join(
        f"• {f['Finding']}: {f['Who']} – {f['Details']}" for f in risky[:20]),
        title=f"Lock down {len(who)} account(s) after unusual activity",
        by="unusual-activity check", extra={"kind": "playbook"})


# ===================================================== settings drift guard ===
def _scalar(v) -> str | None:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float, str)):
        return str(v)
    if isinstance(v, list) and all(isinstance(x, (str, int, float)) for x in v):
        return ",".join(str(x) for x in v)
    return None


def _split_key(key: str) -> tuple[str, str, str]:
    """'Chrome: schema @ /ou' → ('Chrome', 'schema', '/ou')"""
    kind, rest = key.split(": ", 1) if ": " in key else ("", key)
    name, _, where = rest.rpartition(" @ ")
    return kind, name, where


def made_by_gambit(change: dict, activity: list[dict]) -> bool:
    kind, name, where = _split_key(change["Setting"])
    for e in activity:
        cmd = e.get("command", "")
        if "chromepolicy" in cmd and name and name in cmd and (where in cmd or where == "/"):
            return True
    return False


def revert_plan(changes: list[dict], activity: list[dict]) -> tuple[list, list]:
    """→ (steps [(label, args)], manual [lines]) for changes GAMbit didn't make."""
    steps, manual = [], []
    for c in changes:
        if made_by_gambit(c, activity):
            continue
        kind, name, where = _split_key(c["Setting"])
        if kind != "Chrome":
            manual.append(f"{c['Setting']}: was {c['Before'] or '(not set)'} – now "
                          f"{c['Now'] or '(not set)'}")
            continue
        try:
            before = json.loads(c["Before"]) if c["Before"] else {}
            now = json.loads(c["Now"]) if c["Now"] else {}
        except ValueError:
            manual.append(f"{c['Setting']}: couldn't read the old value")
            continue
        if c["Change"] == "added":
            steps.append((f"Remove {name} set directly on {where}",
                          ["delete", "chromepolicy", name, "ou", where]))
            continue
        pairs, skipped = [], []
        for field, val in before.items():
            if now.get(field) == val:
                continue
            sv = _scalar(val)
            if sv is None:
                skipped.append(field)
            else:
                pairs += [field, sv]
        if pairs:
            steps.append((f"Put back {name} on {where}",
                          ["update", "chromepolicy", name, *pairs, "ou", where]))
        if skipped:
            manual.append(f"{c['Setting']}: fields {', '.join(skipped)} need changing by hand")
    return steps, manual


def drift_request(changes: list[dict], since: str, activity: list[dict]) -> dict | None:
    from .. import team
    steps, manual = revert_plan(changes, activity)
    if not (steps or manual) or not team.folder():
        return None
    reason = (f"Settings changed outside GAMbit since {since}.\n" +
              ("\nTo put back automatically:\n" + "\n".join(f"• {lab}" for lab, _a in steps)
               if steps else "") +
              ("\n\nChange back by hand in the Admin console:\n" +
               "\n".join(f"• {m}" for m in manual[:40]) if manual else ""))
    return team.new_request([a for _l, a in steps], reason,
                            title=f"Settings drift: {len(steps)} to put back" +
                                  (f", {len(manual)} by hand" if manual else ""),
                            by="settings watch", extra={"kind": "drift",
                                                        "when": datetime.date.today()
                                                        .isoformat()})
