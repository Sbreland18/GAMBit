"""Back-to-school readiness: in August, each school's progress on student accounts signed
in, Chromebooks assigned, guardians invited, Classroom teachers verified and this year's
classes created – with the screen that fixes each one."""

from __future__ import annotations

import json
from collections import defaultdict

from .settings import settings

FIXES = {"Signed in": ("Student lookup", ""), "Chromebook assigned": ("Chromebook fleet",
                                                                     "Assignment sync"),
         "Guardian invited": ("Classroom", "Guardian sync"),
         "Teachers verified": ("Classroom", "Teacher status"),
         "Classes created": ("Classroom", "Yearly setup")}


def options() -> dict:
    try:
        o = json.loads(settings.get("bts/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"student_root": "/Students", "staff_root": "/Staff", "goal": 95, **o}


def save_options(o: dict):
    settings.set("bts/options", json.dumps(o))


def courses_args() -> list[str]:
    return ["print", "courses", "states", "active,provisioned", "aliases", "fields",
            "id,name,owneremail,coursestate"]


def _pct(a, b):
    return round(100 * a / b) if b else None


def compute(users: list[dict], devices: list[dict] | None, guardians: list[dict] | None,
            profiles: list[dict] | None, courses: list[dict] | None, opts: dict,
            year_end: int) -> list[dict]:
    from .parent_report import school_of
    sroot, troot = opts["student_root"], opts["staff_root"]
    sl, tl = sroot.rstrip("/").lower(), troot.rstrip("/").lower()
    by = defaultdict(lambda: defaultdict(int))
    student_school, staff_school = {}, {}
    for u in users:
        if u.get("suspended"):
            continue
        ou = (u.get("ou") or "").lower()
        e = u["email"].lower()
        if ou.startswith(sl + "/"):
            sch = school_of(u["ou"], sroot)
            student_school[e] = sch
            b = by[sch]
            b["students"] += 1
            last = (u.get("last_login") or "").lower()
            if last and not last.startswith(("never", "1970")):
                b["signed_in"] += 1
        elif ou.startswith(tl + "/"):
            staff_school[e] = school_of(u["ou"], troot)
    if devices is not None:
        assigned = {(d.get("user") or "").lower() for d in devices if d.get("user")}
        for e, sch in student_school.items():
            by[sch]["device"] += e in assigned
            by[sch]["device_known"] += 1
    if guardians is not None:
        has = {g["student"] for g in guardians if g["kind"] == "guardian" or
               g.get("state") == "PENDING"}
        for e, sch in student_school.items():
            by[sch]["guardian"] += e in has
            by[sch]["guardian_known"] += 1
    if profiles is not None:
        for r in profiles:
            low = {(k or "").lower(): (v or "") for k, v in r.items()}
            e = (low.get("emailaddress") or "").lower()
            if e in staff_school:
                b = by[staff_school[e]]
                b["teachers"] += 1
                b["verified"] += low.get("verifiedteacher", "").lower() == "true"
    if courses is not None:
        tag = f"-{str(year_end)[-2:]}"
        for r in courses:
            low = {(k or "").lower(): (v or "") for k, v in r.items()}
            aliases = " ".join(v for k, v in low.items() if k.startswith("alias"))
            owner = (low.get("owneremail") or "").lower()
            if owner in staff_school and tag in aliases:
                by[staff_school[owner]]["classes"] += 1
    goal = int(opts.get("goal", 95) or 95)
    out = []
    for sch, b in sorted(by.items()):
        if not b["students"] and not b["teachers"]:
            continue
        row = {"School": sch, "Students": b["students"],
               "Signed in": _pct(b["signed_in"], b["students"]),
               "Chromebook assigned": _pct(b["device"], b["device_known"]),
               "Guardian invited": _pct(b["guardian"], b["guardian_known"]),
               "Teachers verified": _pct(b["verified"], b["teachers"]),
               "Classes created": b["classes"] if courses is not None else None}
        behind = [k for k in ("Signed in", "Chromebook assigned", "Guardian invited",
                              "Teachers verified") if row[k] is not None and row[k] < goal]
        if courses is not None and b["teachers"] and not b["classes"]:
            behind.append("Classes created")
        row["Needs work"] = ", ".join(behind)
        out.append(row)
    return out


def display(rows: list[dict]) -> list[dict]:
    def f(v, pct=True):
        return "–" if v is None else (f"{v}%" if pct else str(v))
    return [{**r, **{k: f(r[k]) for k in ("Signed in", "Chromebook assigned",
                                          "Guardian invited", "Teachers verified")},
             "Classes created": f(r["Classes created"], False)} for r in rows]
