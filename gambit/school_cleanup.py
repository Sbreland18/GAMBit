"""Clean-up by school (Reports → Clean-up by school).

One to-do list per building, built from what GAMbit already reads, each row with a fix:

- accounts nobody has signed in to for N days      → suspend
- accounts that never signed in (older than 30 days) → suspend
- suspended accounts still sitting in a school org unit → move to former students / staff
- Chromebooks not seen for N days                   → note “Not seen since …” (or move to lost)
- Chromebooks assigned to a suspended or deleted account → clear the assigned user

Schools come from Settings → Org units & schools. Each building's list can be emailed to
its tech (“Hancock High School = jsmith@…”).
"""

from __future__ import annotations

import datetime
import json

from . import ou_map
from .settings import settings

USERS_ARGS = ["print", "users", "fields", "primaryemail,name,ou,suspended,lastlogintime,"
              "creationtime"]
CROS_ARGS = ["print", "cros", "fields", "deviceid,serialnumber,annotatedassetid,annotateduser,"
             "orgunitpath,status,lastsync", "listlimit", "1"]
CONTACTS_KEY = "cleanup/school_contacts"
FIXES = {"suspend": "Suspend", "move_former": "Move to former org unit",
         "note_unseen": "Note “not seen”", "move_lost": "Move to lost org unit",
         "clear_user": "Clear assigned user"}


def _date(s: str):
    s = (s or "")[:10]
    if not s or s.startswith("1970"):
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def contacts() -> dict[str, str]:
    try:
        return json.loads(settings.get(CONTACTS_KEY, "{}") or "{}")
    except ValueError:
        return {}


def save_contacts(text: str) -> dict[str, str]:
    d = {}
    for ln in (text or "").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            if k.strip() and "@" in v:
                d[k.strip()] = v.strip()
    settings.set(CONTACTS_KEY, json.dumps(d))
    return d


def build(users: list[dict], cros: list[dict], days: int = 60, cros_days: int = 45,
          today: datetime.date | None = None, items=None) -> list[dict]:
    today = today or datetime.date.today()
    items = ou_map.entries() if items is None else items
    cut, cros_cut = today - datetime.timedelta(days=days), \
        today - datetime.timedelta(days=cros_days)
    new_cut = today - datetime.timedelta(days=30)
    former = {"students": (ou_map.roots("former_students", items) or [""])[0],
              "staff": (ou_map.roots("former_staff", items) or [""])[0]}
    lost = (ou_map.roots("lost", items) or [""])[0]
    out = []
    state = {}
    for u in users:
        email = (u.get("primaryEmail") or "").lower()
        ou = u.get("orgUnitPath") or "/"
        c = ou_map.classify(ou, items)
        susp = (u.get("suspended") or "").lower() == "true"
        state[email] = "suspended" if susp else "active"
        if c["type"] not in ("students", "staff"):
            continue
        school = c["school"] or "(no school)"
        who = "student" if c["type"] == "students" else "staff"
        if susp:
            if former[c["type"]]:
                out.append({"school": school, "problem": f"Suspended {who} still in a school "
                            "org unit", "item": email, "detail": ou, "fix": "move_former",
                            "target": former[c["type"]]})
            continue
        last, created = _date(u.get("lastLoginTime")), _date(u.get("creationTime"))
        if last is None:
            if created and created < new_cut:
                out.append({"school": school, "problem": f"{who.title()} never signed in",
                            "item": email, "detail": f"created {created}", "fix": "suspend",
                            "target": ""})
        elif last < cut:
            out.append({"school": school, "problem": f"{who.title()} not signed in for "
                        f"{days}+ days", "item": email, "detail": f"last sign-in {last}",
                        "fix": "suspend", "target": ""})
    for d in cros:
        status = (d.get("status") or "").upper()
        if status not in ("ACTIVE", ""):
            continue
        ou = d.get("orgUnitPath") or "/"
        c = ou_map.classify(ou, items)
        if c["type"] in ("lost", "repairs"):
            continue
        school = c["school"] or "(no school)"
        sn = d.get("serialNumber") or ""
        sync = _date(d.get("lastSync"))
        if sync and sync < cros_cut:
            out.append({"school": school, "problem": f"Chromebook not seen for {cros_days}+ "
                        "days", "item": sn, "detail": f"last seen {sync} · "
                        f"{d.get('annotatedUser') or 'unassigned'}",
                        "fix": "move_lost" if lost else "note_unseen", "target": lost,
                        "seen": str(sync)})
        user = (d.get("annotatedUser") or "").lower()
        if user and "@" in user and state.get(user) in ("suspended", None) and state:
            out.append({"school": school, "problem": "Chromebook assigned to a " +
                        ("suspended" if state.get(user) else "deleted or unknown") +
                        " account", "item": sn, "detail": user, "fix": "clear_user",
                        "target": ""})
    out.sort(key=lambda r: (r["school"].lower(), r["problem"], r["item"]))
    return out


def commands(rows: list[dict]) -> list[tuple[str, list]]:
    steps = []
    for r in rows:
        f, it = r["fix"], r["item"]
        if f == "suspend":
            steps.append((f"Suspend {it}", ["update", "user", it, "suspended", "on"]))
        elif f == "move_former" and r.get("target"):
            steps.append((f"Move {it} to {r['target']}",
                          ["update", "user", it, "ou", r["target"]]))
        elif f == "move_lost" and r.get("target"):
            steps.append((f"Move {it} to {r['target']}",
                          ["cros_sn", it, "update", "ou", r["target"]]))
        elif f == "note_unseen":
            steps.append((f"Note on {it}", ["cros_sn", it, "update", "notes",
                                            f"Not seen since {r.get('seen', '')} "
                                            f"(GAMbit clean-up {datetime.date.today()})"]))
        elif f == "clear_user":
            steps.append((f"Clear the assigned user of {it}",
                          ["cros_sn", it, "update", "user", ""]))
    return steps


def summary(rows: list[dict]) -> list[dict]:
    per: dict[str, dict] = {}
    for r in rows:
        s = per.setdefault(r["school"], {"school": r["school"], "total": 0})
        s["total"] += 1
        s[r["problem"]] = s.get(r["problem"], 0) + 1
    return sorted(per.values(), key=lambda x: -x["total"])


def email_text(school: str, rows: list[dict]) -> str:
    lines = [f"Clean-up list for {school} ({len(rows)} item(s)) from GAMbit:", ""]
    cur = ""
    for r in rows:
        if r["problem"] != cur:
            cur = r["problem"]
            lines += ["", cur + ":"]
        lines.append(f"  • {r['item']} – {r['detail']}")
    return "\n".join(lines) + "\n\nFix them in GAMbit → Reports → Clean-up by school.\n"
