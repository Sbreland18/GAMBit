"""Directory quality check: a score per school for missing staff titles, departments,
managers, phones and employee IDs and missing student IDs – plus likely duplicate
accounts (same name or ID twice, students who also have a staff account)."""

from __future__ import annotations

import json
import re
from collections import defaultdict

from .settings import settings

USERS_ARGS = ["print", "users", "fields", "primaryemail,name,ou,suspended,organizations,"
              "phones,relations,externalids,creationtime"]


def options() -> dict:
    try:
        o = json.loads(settings.get("dirquality/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"staff_root": "/Staff", "student_root": "/Students",
            "staff_fields": ["title", "department", "manager", "phone", "employee_id"],
            "student_fields": ["student_id"], **o}


def save_options(o: dict):
    settings.set("dirquality/options", json.dumps(o))


LABEL = {"title": "Job title", "department": "Department", "manager": "Manager",
         "phone": "Work phone", "employee_id": "Employee ID", "student_id": "Student ID"}


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _under(ou: str, root: str) -> bool:
    ou, root = (ou or "").rstrip("/").lower(), (root or "").rstrip("/").lower()
    return bool(root) and (ou == root or ou.startswith(root + "/"))


def people(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        e = low.get("primaryemail", "").lower()
        if not e or low.get("suspended", "").lower() == "true":
            continue
        ids = {}
        for k, v in low.items():
            m = re.match(r"externalids\.(\d+)\.type", k)
            if m:
                ids[v.lower()] = low.get(f"externalids.{m.group(1)}.value", "")
        phone = any(v for k, v in low.items() if k.startswith("phones.") and
                    k.endswith(".value"))
        manager = any(v for k, v in low.items() if k.startswith("relations.") and
                      k.endswith(".value"))
        out.append({"email": e, "name": low.get("name.fullname", ""),
                    "ou": low.get("orgunitpath", ""),
                    "title": low.get("organizations.0.title", ""),
                    "department": low.get("organizations.0.department", ""),
                    "manager": manager, "phone": phone,
                    "employee_id": ids.get("organization", "") or ids.get("employee", ""),
                    "student_id": ids.get("organization", "") or ids.get("student", "") or
                    ids.get("custom", ""),
                    "created": low.get("creationtime", "")[:10]})
    return out


def score(ppl: list[dict], opts: dict) -> tuple[list[dict], list[dict]]:
    """→ (per school rows, per person gaps)"""
    from .parent_report import school_of
    by = defaultdict(lambda: {"people": 0, "complete": 0, "missing": defaultdict(int)})
    gaps = []
    for p in ppl:
        if _under(p["ou"], opts["staff_root"]):
            kind, fields, root = "Staff", opts["staff_fields"], opts["staff_root"]
        elif _under(p["ou"], opts["student_root"]):
            kind, fields, root = "Students", opts["student_fields"], opts["student_root"]
        else:
            continue
        sch = f"{school_of(p['ou'], root)} ({kind.lower()})"
        miss = [LABEL[f] for f in fields if not p.get(f)]
        b = by[sch]
        b["people"] += 1
        b["complete"] += not miss
        for m in miss:
            b["missing"][m] += 1
        if miss:
            gaps.append({"Person": p["email"], "Name": p["name"], "Org unit": p["ou"],
                         "Missing": ", ".join(miss)})
    rows = []
    for sch, b in sorted(by.items()):
        rows.append({"Where": sch, "People": b["people"],
                     "Score": round(100 * b["complete"] / b["people"]) if b["people"] else 0,
                     "Most often missing": ", ".join(f"{k} ({v})" for k, v in sorted(
                         b["missing"].items(), key=lambda x: -x[1])[:3])})
    return sorted(rows, key=lambda r: r["Score"]), gaps


def _norm_name(n: str) -> str:
    return re.sub(r"[^a-z]", "", (n or "").lower())


def duplicates(ppl: list[dict], opts: dict) -> list[dict]:
    out = []
    by_name, by_id = defaultdict(list), defaultdict(list)
    for p in ppl:
        if p["name"]:
            by_name[_norm_name(p["name"])].append(p)
        sid = p.get("student_id") or p.get("employee_id")
        if sid:
            by_id[sid.strip().lower()].append(p)
    for sid, ps in by_id.items():
        if len(ps) > 1:
            out.append({"Why": f"same ID {sid}", "Accounts": ", ".join(p["email"] for p in ps),
                        "Names": ", ".join(p["name"] for p in ps)})
    for n, ps in by_name.items():
        if len(ps) < 2 or not n:
            continue
        stu = [p for p in ps if _under(p["ou"], opts["student_root"])]
        stf = [p for p in ps if _under(p["ou"], opts["staff_root"])]
        if stu and stf:
            why = "a student who also has a staff account"
        elif len(stu) > 1:
            why = "two student accounts with the same name"
        elif len(stf) > 1:
            why = "two staff accounts with the same name"
        else:
            continue
        accts = ", ".join(p["email"] for p in ps)
        if any(o["Accounts"] == accts for o in out):
            continue
        out.append({"Why": why, "Accounts": accts,
                    "Names": ", ".join(sorted({p['name'] for p in ps}))})
    return out
