"""Shared-drive moves and folder copies, directory details from the HR sheet, staff
laptops and phones (Cloud Identity devices), usage reports, ChromeOS versions, group
audits, Vault counts/holds, Keep notes, and domain shared contacts."""

from __future__ import annotations

import csv
import datetime
import io
import re


def _low(r: dict) -> dict:
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ============================================================== drive moves ===
def move_to_shared_drive_args(user: str, folder_id: str, drive_id: str,
                              subfolder: str = "") -> list[str]:
    a = ["user", user, "move", "drivefile", folder_id, "teamdriveparentid", drive_id]
    if subfolder:
        a += ["teamdriveparentname", subfolder]
    return a + ["mergewithparent", "false", "createshortcutsfornonmovablefiles", "true",
                "duplicatefiles", "uniquename", "duplicatefolders", "merge",
                "copysubfolderpermissions", "true"]


def copy_folder_steps(owner: str, folder_id: str, to_user: str, new_name: str = "",
                      share_first: bool = True) -> list[tuple[str, list[str]]]:
    steps = []
    if share_first and owner and owner.lower() != to_user.lower():
        steps.append((f"Let {to_user} view the folder",
                      ["user", owner, "add", "drivefileacl", folder_id, "user", to_user,
                       "role", "reader"]))
    a = ["user", to_user, "copy", "drivefile", folder_id, "recursive", "parentid", "root",
         "duplicatefiles", "uniquename", "copyfilepermissions", "false"]
    if new_name:
        a[5:5] = ["newfilename", new_name]
    steps.append((f"Copy into {to_user}'s My Drive", a))
    return steps


def shared_drives(rows: list[dict]) -> list[tuple[str, str]]:
    out = []
    for r in rows:
        low = _low(r)
        if low.get("id"):
            out.append((low.get("name", low["id"]), low["id"]))
    return sorted(out)


# ======================================================= directory details ===
DIR_COLS = {
    "email": ["email", "emailaddress", "workemail", "googleemail", "account"],
    "id": ["employeeid", "staffid", "id", "personid"],
    "manager": ["supervisoremail", "manageremail", "supervisor", "manager", "reportsto"],
    "phone": ["workphone", "phone", "phonenumber", "extension", "officephone"],
    "mobile": ["mobile", "cell", "cellphone", "mobilephone"],
    "building": ["building", "buildingid", "school", "site", "campus", "location"],
    "floor": ["floor", "floorname"],
    "desk": ["room", "desk", "office", "deskcode", "roomnumber"],
    "title": ["title", "jobtitle", "position"],
    "department": ["department", "dept"],
}
DIR_FIELDS = ["primaryemail", "relations", "phones", "locations", "organizations",
              "externalids"]


def dir_mapping(headers: list[str]) -> dict[str, str]:
    by = {_norm(h): h for h in headers}
    return {k: next((by[c] for c in cands if c in by), "") for k, cands in DIR_COLS.items()}


def current_details(rows: list[dict]) -> dict[str, dict]:
    """`print users fields …` → {email: {manager, phone, mobile, building, floor, desk,
    title, department, id}}"""
    out = {}
    for r in rows:
        low = _low(r)
        e = (low.get("primaryemail") or "").lower()
        if not e:
            continue
        d = {k: "" for k in DIR_COLS if k != "email"}
        for k, v in low.items():
            m = re.match(r"(relations|phones|locations|organizations|externalids)\.(\d+)\.(\w+)",
                         k)
            if not m:
                continue
            kind, n, f = m.groups()
            t = low.get(f"{kind}.{n}.type", "")
            if kind == "relations" and f == "value" and t == "manager":
                d["manager"] = v.lower()
            elif kind == "phones" and f == "value":
                d["mobile" if t == "mobile" else "phone"] = v
            elif kind == "locations":
                key = {"buildingid": "building", "floorname": "floor",
                       "deskcode": "desk"}.get(f)
                if key:
                    d[key] = v
            elif kind == "organizations" and f in ("title", "department") and not d[f]:
                d[f] = v
            elif kind == "externalids" and f == "value" and t == "organization":
                d["id"] = v
        out[e] = d
    return out


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def dir_plan(sheet: list[dict], mapping: dict, current: dict[str, dict], domain: str = "",
             building_ids: dict[str, str] | None = None) -> list[dict]:
    """→ [{email, changes: text, args}]  (building names map to building IDs)"""
    building_ids = {_norm(k): v for k, v in (building_ids or {}).items()}
    by_id = {d["id"]: e for e, d in current.items() if d.get("id")}
    out = []
    for r in sheet:
        def g(k):
            c = mapping.get(k)
            return (r.get(c) or "").strip() if c else ""
        email = g("email").lower()
        if not email and g("id"):
            email = by_id.get(g("id"), "")
        if email and "@" not in email and domain:
            email = f"{email}@{domain}"
        cur = current.get(email)
        if not cur:
            if email or g("id"):
                out.append({"email": email or g("id"), "changes": "⚠ no Google account found",
                            "args": None})
            continue
        attrs, notes = [], []
        mgr = g("manager").lower()
        if mgr and "@" not in mgr and domain:
            mgr = f"{mgr}@{domain}"
        if mgr and "@" in mgr and mgr != cur["manager"] and mgr != email:
            attrs += ["relation", "manager", mgr]
            notes.append(f"manager → {mgr}")
        phone, mobile = g("phone"), g("mobile")
        if (phone and _digits(phone) != _digits(cur["phone"])) or \
                (mobile and _digits(mobile) != _digits(cur["mobile"])):
            p = phone or cur["phone"]
            mo = mobile or cur["mobile"]
            if p:
                attrs += ["phone", "type", "work", "value", p, "primary"]
            if mo:
                attrs += ["phone", "type", "mobile", "value", mo, "notprimary"]
            notes.append("phone → " + " / ".join(x for x in (p, mo) if x))
        b = g("building")
        bid = building_ids.get(_norm(b), b) if b else ""
        fl, desk = g("floor"), g("desk")
        if (bid and bid != cur["building"]) or (fl and fl != cur["floor"]) or \
                (desk and desk != cur["desk"]):
            loc = ["location", "type", "desk", "area", "desk"]
            if bid:
                loc += ["buildingid", bid]
            if fl:
                loc += ["floor", fl]
            if desk:
                loc += ["deskcode", desk]
            attrs += loc + ["endlocation"]
            notes.append("desk → " + ", ".join(x for x in (b, fl and f"floor {fl}",
                                                           desk and f"room {desk}") if x))
        t, dep = g("title"), g("department")
        if (t and t != cur["title"]) or (dep and dep != cur["department"]):
            attrs += ["organization", "title", t or cur["title"], "department",
                      dep or cur["department"], "primary"]
            notes.append(f"job → {t or cur['title']} / {dep or cur['department']}")
        if attrs:
            out.append({"email": email, "changes": "; ".join(notes),
                        "args": ["update", "user", email, *attrs]})
    return out


# ============================================================ staff devices ===
DEVICE_ARGS = ["print", "devices", "oneuserperrow", "fields",
               "name,devicetype,model,serialnumber,osversion,lastsynctime,ownertype,"
               "encryptionstate,compromisedstate", "userfields",
               "name,useremail,managementstate,lastsynctime"]


def devices(rows: list[dict], include_chromeos: bool = False) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        dtype = low.get("devicetype", "")
        if dtype == "CHROME_OS" and not include_chromeos:
            continue
        user_name = low.get("user.name", "")
        email = low.get("user.useremail", "")
        state = low.get("user.managementstate", "") or low.get("managementstate", "")
        out.append({"Person": email, "Type": dtype.replace("_", " ").title(),
                    "Model": low.get("model", ""), "Serial": low.get("serialnumber", ""),
                    "OS": low.get("osversion", ""), "Owner": low.get("ownertype", "").title(),
                    "Last sync": low.get("lastsynctime", "").replace("T", " ")[:16],
                    "Status": state.replace("_", " ").lower(),
                    "Encrypted": low.get("encryptionstate", "").replace("_", " ").lower(),
                    "Device": low.get("name", ""), "Device user": user_name})
    out.sort(key=lambda x: (x["Status"] != "approval pending", x["Person"]))
    return out


def device_action_args(action: str, row: dict) -> list[str]:
    if action in ("approve", "block", "wipeuser", "cancelwipeuser"):
        verb = {"approve": "approve", "block": "block", "wipeuser": "wipe",
                "cancelwipeuser": "cancelwipe"}[action]
        return [verb, "deviceuser", row["Device user"], "doit"]
    verb = {"wipe": "wipe", "cancelwipe": "cancelwipe", "delete": "delete"}[action]
    return [verb, "device", row["Device"], "doit"]


# ===================================================================== usage ===
USAGE_APPS = [("Gmail", "gmail"), ("Drive", "drive"), ("Classroom", "classroom"),
              ("Meet", "meet"), ("Calendar", "calendar"), ("Chat", "chat")]


def usage_params(rows: list[dict]) -> list[str]:
    """Pick 30-day (or 7-day) active-user counts from `report usageparameters customer`."""
    names = [(_low(r).get("parameter") or list(r.values())[0] or "") for r in rows]
    out = []
    for _label, app in USAGE_APPS:
        cands = [n for n in names if n.startswith(app + ":")]
        pick = next((n for n in cands if "num_30day_active_users" in n), None) or \
            next((n for n in cands if "30day" in n and "active" in n), None) or \
            next((n for n in cands if "7day_active" in n), None)
        if pick:
            out.append(pick)
    acc = next((n for n in names if n == "accounts:num_30day_logins"), None)
    return ([acc] if acc else []) + out


def usage_args(params: list[str], months: int = 6) -> list[str]:
    start = (datetime.date.today() - datetime.timedelta(days=30 * months)).isoformat()
    end = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    return ["report", "usage", "customer", "start", start, "end", end,
            "skipdaysofweek", "mon,tue,wed,thu,fri,sat", "fields", ",".join(params)]


def usage_table(rows: list[dict]) -> tuple[list[str], list[list[str]]]:
    """Long rows (date,name,value) or wide rows → Date × app table."""
    by: dict[str, dict] = {}
    for r in rows:
        low = _low(r)
        date = low.get("date", "")
        if "name" in low and "value" in low:
            by.setdefault(date, {})[low["name"]] = low["value"]
        else:
            for k, v in low.items():
                if ":" in k:
                    by.setdefault(date, {})[k] = v
    cols = sorted({k for d in by.values() for k in d})
    label = {k: k.split(":")[0].title() + (" logins" if "login" in k else " active users")
             for k in cols}
    return (["Week of"] + [label[c] for c in cols],
            [[d] + [by[d].get(c, "") for c in cols] for d in sorted(by)])


def users_report_args(ou: str) -> list[str]:
    date = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    ent = ["user", "all"] if ou in ("", "/") else ["orgunit", ou]
    return ["report", "users", *ent, "date", date, "fields",
            "accounts:last_login_time,gmail:last_interaction_time,"
            "drive:last_active_usage_time,classroom:last_interaction_time,"
            "classroom:num_posts_created,classroom:role"]


def school_usage(rows: list[dict], users: list[dict], depth: int = 2,
                 days: int = 30) -> list[dict]:
    from .investigate import school_of
    ou_of = {u["email"].lower(): u.get("ou", "") for u in users}
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    by: dict[str, dict] = {}
    for r in rows:
        low = _low(r)
        e = (low.get("email") or "").lower()
        b = by.setdefault(school_of(ou_of.get(e, ""), depth),
                          {"people": 0, "login": 0, "gmail": 0, "drive": 0, "classroom": 0})
        b["people"] += 1
        for key, col in (("login", "accounts:last_login_time"),
                         ("gmail", "gmail:last_interaction_time"),
                         ("drive", "drive:last_active_usage_time"),
                         ("classroom", "classroom:last_interaction_time")):
            if (low.get(col) or "")[:10] >= cutoff:
                b[key] += 1
    out = []
    for k, b in sorted(by.items()):
        n = b["people"] or 1
        out.append({"Org unit": k, "Accounts": str(b["people"]),
                    "Signed in": f"{100 * b['login'] // n}%",
                    "Gmail": f"{100 * b['gmail'] // n}%", "Drive": f"{100 * b['drive'] // n}%",
                    "Classroom": f"{100 * b['classroom'] // n}%"})
    return out


def teacher_classroom(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        role = (low.get("classroom:role") or "").lower()
        if "teacher" not in role:
            continue
        out.append({"Teacher": low.get("email", ""),
                    "Posts (last 30 days)": low.get("classroom:num_posts_created", "0") or "0",
                    "Last used Classroom": (low.get("classroom:last_interaction_time") or "")
                    .replace("T", " ")[:10]})
    out.sort(key=lambda x: -int(x["Posts (last 30 days)"] or 0))
    return out


# ========================================================= ChromeOS versions ===
def versions_args(ou: str) -> list[str]:
    return ["print", "chromeversions"] + ([] if ou in ("", "/") else ["ou_and_children", ou])


def versions(rows: list[dict]) -> list[dict]:
    out = []
    total = 0
    for r in rows:
        low = _low(r)
        n = int(re.sub(r"\D", "", low.get("count", "0")) or 0)
        total += n
        out.append({"Version": low.get("version", ""), "Channel": low.get("channel", "").lower(),
                    "Devices": n})

    def key(v):
        return [int(x) if x.isdigit() else 0 for x in re.split(r"\D+", v["Version"]) if x]
    out.sort(key=key, reverse=True)
    newest = key(out[0])[:1] if out else []
    for v in out:
        v["Share"] = f"{100 * v['Devices'] / total:.0f}%" if total else ""
        v["Behind"] = "" if key(v)[:1] == newest else \
            f"{newest[0] - key(v)[0]} major version(s) behind" if newest and key(v) else ""
        v["Devices"] = str(v["Devices"])
    return out


# ================================================================== groups ===
def members_recursive_args(group: str) -> list[str]:
    return ["print", "group-members", "group", group, "recursive", "noduplicates",
            "fields", "email,role,type,status"]


GROUP_RISK_ARGS = ["print", "groups", "settings", "fields",
                   "email,name,directmemberscount"]


def risky_groups(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        why = []
        if low.get("allowexternalmembers", "").lower() == "true":
            why.append("outside members allowed")
        if low.get("whocanpostmessage", "") == "ANYONE_CAN_POST":
            why.append("anyone on the internet can email it")
        if low.get("whocanjoin", "") == "ANYONE_CAN_JOIN":
            why.append("anyone can join")
        if low.get("whocanviewmembership", "") == "ANYONE_CAN_VIEW":
            why.append("member list is public")
        if why:
            out.append({"Group": low.get("email", ""), "Name": low.get("name", ""),
                        "Members": low.get("directmemberscount", ""),
                        "Open to outsiders": ", ".join(why)})
    return out


# =================================================================== vault ===
def vault_count_args(matter: str, accounts: list[str], ou: str, terms: str, start: str,
                     end: str) -> list[str]:
    a = ["print", "vaultcounts", "matter", matter, "corpus", "mail"]
    a += ["accounts", ",".join(accounts)] if accounts else (["ou", ou] if ou else ["everyone"])
    if terms:
        a += ["terms", terms]
    if start:
        a += ["start", start]
    if end:
        a += ["end", end]
    return a + ["wait", "60"]


def holds_args(email: str) -> list[str]:
    return ["user", email, "print", "vaultholds"]


def holds_for(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        out.append({"Matter": low.get("mattername") or low.get("matterid", ""),
                    "Hold": low.get("name", ""),
                    "Covers them through": f"org unit {low['orgunitpath']}"
                    if low.get("orgunitpath") else "their account"})
    return out


# =================================================================== keep ===
def notes_args(user: str) -> list[str]:
    return ["user", user, "print", "notes", "role", "owner", "fields", "name,title,updatetime"]


def notes(rows: list[dict]) -> list[dict]:
    return [{"Note": _low(r).get("title", "") or "(untitled)",
             "Updated": _low(r).get("updatetime", "").replace("T", " ")[:16],
             "ID": _low(r).get("name", "")} for r in rows]


def share_notes_args(user: str, names: list[str], to: str) -> list[str]:
    return ["user", user, "create", "noteacl", ",".join(names), "user", to]


# =============================================================== contacts ===
CONTACT_COLS = {"name": ["name", "fullname", "contact", "displayname"],
                "email": ["email", "emailaddress"],
                "phone": ["phone", "phonenumber", "workphone"],
                "org": ["organization", "company", "organisation", "vendor"],
                "title": ["title", "jobtitle", "role"],
                "note": ["notes", "note", "description"]}
CONTACTS_ARGS = ["print", "contacts", "fields", "name,email,phone,organization"]


def contacts_from_csv(text: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if not rows:
        return []
    by = {_norm(h): h for h in rows[0]}
    m = {k: next((by[c] for c in cands if c in by), "") for k, cands in CONTACT_COLS.items()}
    out = []
    for r in rows:
        c = {k: (r.get(col) or "").strip() if col else "" for k, col in m.items()}
        if c["name"] and (c["email"] or c["phone"]):
            out.append(c)
    return out


def contact_plan(wanted: list[dict], existing: list[dict]) -> list[dict]:
    have = set()
    for r in existing:
        for k, v in _low(r).items():
            if "email" in k and "@" in v:
                have.add(v.lower())
    plan = []
    for c in wanted:
        if c["email"] and c["email"].lower() in have:
            plan.append({"action": "same", "name": c["name"], "args": None})
            continue
        a = ["create", "contact", "name", c["name"]]
        if c["email"]:
            a += ["email", "work", c["email"], "primary"]
        if c["phone"]:
            a += ["phone", "work", c["phone"], "primary"]
        if c["org"] or c["title"]:
            a += ["organization", "work", c["org"] or "-"]
            if c["title"]:
                a += ["title", c["title"]]
            a.append("primary")
        if c["note"]:
            a += ["note", c["note"]]
        plan.append({"action": "create", "name": c["name"], "args": a})
    return plan


CONTACT_TEMPLATE = ("Name,Email,Phone,Organization,Title,Notes\n"
                    "District Office – Payroll,payroll@district.org,555-0100,District Office,"
                    "Payroll,\nABC Bus Company,dispatch@abcbus.com,555-0199,ABC Bus Company,"
                    "Dispatch,Transportation vendor\n")


# ============================================================ fast bulk ===
def threaded(args: list[str], threads: int) -> list[str]:
    """Put `config num_threads N` in front of a `gam csv …` command."""
    if threads and threads != 5 and args[:1] == ["csv"]:
        return ["config", "num_threads", str(max(1, min(threads, 50)))] + args
    return args
