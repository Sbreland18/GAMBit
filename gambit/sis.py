"""Roster sync: read a student or staff roster, compare it with Google, plan the changes.

Works with ClassLink / OneRoster (users.csv + orgs.csv, or the .zip), Clever
(students.csv + schools.csv), PowerSchool, Infinite Campus, Skyward, a staff
Google Sheet / HR export, and any other CSV via column mapping. Pure Python so
it can be tested without Qt.
"""

from __future__ import annotations

import csv
import datetime
import io
import os
import re
import secrets
import zipfile
import dataclasses
from dataclasses import dataclass, field

# canonical field -> header names to look for (case/space-insensitive)
FORMATS: dict[str, dict] = {
    "ClassLink / OneRoster": {
        "files": ("users.csv", "orgs.csv"),
        "fields": {
            "sis_id": ["identifier", "sourcedId"],
            "first": ["givenName"], "last": ["familyName"],
            "email": ["email"], "username": ["username"],
            "grade": ["grades"], "school": ["orgSourcedIds"],
            "role": ["role"], "status": ["status"], "enabled": ["enabledUser"],
            "password": ["password"],
        },
        "orgs": {"id": ["sourcedId"], "name": ["name"]},
    },
    "Clever": {
        "files": ("students.csv", "schools.csv"),
        "fields": {
            "sis_id": ["Student_number", "Student_id", "SIS_ID"],
            "first": ["First_name"], "last": ["Last_name"],
            "email": ["Student_email"], "grade": ["Grade"], "school": ["School_id"],
            "password": ["Password"],
        },
        "orgs": {"id": ["School_id"], "name": ["School_name"]},
    },
    "PowerSchool": {
        "files": (),
        "fields": {
            "sis_id": ["Student_Number", "StudentNumber"],
            "first": ["First_Name"], "last": ["Last_Name"],
            "email": ["Student_Email", "Email", "Student_Web_ID"],
            "grade": ["Grade_Level"], "school": ["SchoolID", "School_Name"],
            "status": ["Enroll_Status"],
        },
    },
    "Infinite Campus": {
        "files": (),
        "fields": {
            "sis_id": ["studentNumber", "Student Number", "personID"],
            "first": ["firstName", "First Name"], "last": ["lastName", "Last Name"],
            "email": ["email", "Email"], "grade": ["grade", "Grade"],
            "school": ["schoolName", "School Name", "schoolID"],
        },
    },
    "Skyward": {
        "files": (),
        "fields": {
            "sis_id": ["Other ID", "Student ID", "Name ID"],
            "first": ["First Name", "First"], "last": ["Last Name", "Last"],
            "email": ["Email", "Email Address"], "grade": ["Grade", "Grd"],
            "school": ["Entity", "Building", "School"],
        },
    },
    "Staff sheet / HR export": {
        "files": (),
        "fields": {
            "sis_id": ["Employee ID", "EmployeeID", "Emp ID", "Staff ID", "Employee Number"],
            "first": ["First Name", "First", "Given Name", "Preferred First Name"],
            "last": ["Last Name", "Last", "Surname", "Family Name"],
            "email": ["Email", "Work Email", "District Email", "Email Address"],
            "school": ["Building", "Location", "School", "Campus", "Site", "Work Location"],
            "status": ["Status", "Employment Status", "Active", "Employee Status"],
            "title": ["Title", "Job Title", "Position", "Role"],
            "department": ["Department", "Dept", "Department Name"],
            "manager": ["Supervisor Email", "Supervisor", "Manager Email", "Manager",
                        "Reports To"],
        },
    },
    "Other / custom CSV": {"files": (), "fields": {
        "sis_id": ["id", "student id", "studentid", "student_id"],
        "first": ["first", "first name", "firstname"], "last": ["last", "last name", "lastname"],
        "email": ["email", "email address"], "grade": ["grade"], "school": ["school"],
        "status": ["status"], "title": ["title", "job title", "position"],
        "department": ["department", "dept"],
    }},
}
CANONICAL = ["sis_id", "first", "last", "email", "grade", "school", "status", "title",
             "department", "manager", "password", "role", "enabled", "username"]
DEFAULT_INACTIVE = ("inactive, withdrawn, left, terminated, resigned, retired, separated, "
                    "no, false, n, tobedeleted, deleted")
STUDENT_ROLES = "student"
STAFF_ROLES = "teacher, administrator, aide, proctor, staff"


def _norm(h: str) -> str:
    return re.sub(r"[\s_]+", "", (h or "").lower())


# ================================================================ loading ===
@dataclass
class Export:
    rows: list[dict]
    headers: list[str]
    schools: dict[str, str]       # school id -> name (from orgs/schools file)
    source: str


def _read_csv_bytes(data: bytes) -> list[dict]:
    text = data.decode("utf-8-sig", errors="replace")
    return [r for r in csv.DictReader(io.StringIO(text))]


def load_export(path: str, fmt: str, schools_path: str = "") -> Export:
    """Read a .csv, or a .zip with the usual files inside."""
    spec = FORMATS.get(fmt, FORMATS["Other / custom CSV"])
    rows: list[dict] = []
    org_rows: list[dict] = []
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            names = {os.path.basename(n).lower(): n for n in zf.namelist()}
            main = spec["files"][0] if spec["files"] else None
            pick = names.get(main) if main else None
            if not pick:   # first CSV that looks like people
                pick = next((n for b, n in names.items() if b.endswith(".csv") and
                             any(k in b for k in ("user", "student", "people"))), None)
            if not pick:
                raise ValueError("Couldn't find the people file (e.g. users.csv) in the zip.")
            rows = _read_csv_bytes(zf.read(pick))
            if len(spec["files"]) > 1 and spec["files"][1] in names:
                org_rows = _read_csv_bytes(zf.read(names[spec["files"][1]]))
    else:
        with open(path, "rb") as fh:
            rows = _read_csv_bytes(fh.read())
        sib = schools_path
        if not sib and len(spec["files"]) > 1:
            cand = os.path.join(os.path.dirname(path), spec["files"][1])
            sib = cand if os.path.isfile(cand) else ""
        if sib:
            with open(sib, "rb") as fh:
                org_rows = _read_csv_bytes(fh.read())
    schools = {}
    if org_rows and "orgs" in spec:
        oid = _match_header(list(org_rows[0].keys()), spec["orgs"]["id"])
        oname = _match_header(list(org_rows[0].keys()), spec["orgs"]["name"])
        if oid and oname:
            schools = {r[oid].strip(): r[oname].strip() for r in org_rows if r.get(oid)}
    headers = list(rows[0].keys()) if rows else []
    return Export(rows=rows, headers=headers, schools=schools, source=os.path.basename(path))


def _match_header(headers: list[str], candidates: list[str]) -> str:
    norm = {_norm(h): h for h in headers}
    for c in candidates:
        if _norm(c) in norm:
            return norm[_norm(c)]
    return ""


def guess_mapping(headers: list[str], fmt: str) -> dict[str, str]:
    spec = FORMATS.get(fmt, FORMATS["Other / custom CSV"])
    out = {}
    for key in CANONICAL:
        cands = spec["fields"].get(key, []) + FORMATS["Other / custom CSV"]["fields"].get(key, [])
        out[key] = _match_header(headers, cands)
    return out


def detect_format(headers: list[str]) -> str:
    best, score = "Other / custom CSV", 0
    for name, spec in FORMATS.items():
        if name.startswith("Other"):
            continue
        s = sum(1 for cands in spec["fields"].values() if _match_header(headers, cands))
        if s > score:
            best, score = name, s
    return best


# ================================================================== rules ===
@dataclass
class Rules:
    kind: str = "students"                       # students | staff
    domain: str = ""
    use_sis_email: bool = True
    email_template: str = "{first}.{last}{gradyear2}@{domain}"
    ou_template: str = "/Students/{school}/Grade {grade}"
    managed_root: str = "/Students"
    withdrawn_action: str = "suspend_move"       # suspend_move | suspend | report | offboard
    withdrawn_ou: str = "/Students/Withdrawn"
    missing_means_withdrawn: bool = True
    password_mode: str = "random"                # random | pattern | column
    password_pattern: str = "{First}{id4}{rand4}!"
    change_at_first: bool = True
    update_names: bool = True
    move_ou: bool = True
    store_sis_id: bool = True
    roles: str = "student"                       # OneRoster role filter
    school_names: dict = field(default_factory=dict)
    year_end: int = 0                            # graduation-year base; 0 = automatic
    inactive_values: str = DEFAULT_INACTIVE      # status values that mean "left"
    update_job: bool = True                      # staff: keep title/department in step

    @classmethod
    def for_staff(cls, **kw) -> "Rules":
        base = dict(kind="staff", email_template="{f}{last}@{domain}",
                    ou_template="/Staff/{school}", managed_root="/Staff",
                    withdrawn_ou="/Former Staff", missing_means_withdrawn=False,
                    roles=STAFF_ROLES, password_pattern="{First}{id4}{rand4}!", move_ou=False)
        base.update(kw)
        return cls(**base)

    def inactive_set(self) -> set[str]:
        return {v.strip().lower() for v in self.inactive_values.split(",") if v.strip()}

    @property
    def who(self) -> str:
        return "staff member" if self.kind == "staff" else "student"

    def school_year_end(self) -> int:
        if self.year_end:
            return self.year_end
        today = datetime.date.today()
        return today.year + 1 if today.month >= 7 else today.year


def grade_number(g: str):
    g = (g or "").strip().upper().split(",")[0].strip()
    if g in ("K", "KG", "KN", "00", "0", "TK"):
        return 0
    if g in ("PK", "PREK", "P", "PS", "-1"):
        return -1
    m = re.match(r"^(\d+)", g)
    return int(m.group(1)) if m else None


def grade_label(g: str) -> str:
    n = grade_number(g)
    if n is None:
        return (g or "").strip()
    return {0: "K", -1: "PK"}.get(n, str(n))


def _clean(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _fill(template: str, p: "Person", rules: Rules, rand: str = "") -> str:
    n = grade_number(p.grade)
    gy = rules.school_year_end() + (12 - n) if n is not None else ""
    school = rules.school_names.get(p.school, "") or p.school_name or p.school
    vals = {
        "first": _clean(p.first), "last": _clean(p.last),
        "First": (p.first or "").strip().title().replace(" ", ""),
        "Last": (p.last or "").strip().title().replace(" ", ""),
        "f": _clean(p.first)[:1], "l": _clean(p.last)[:1],
        "id": p.sis_id, "id4": p.sis_id[-4:], "grade": grade_label(p.grade),
        "grade2": (f"{n:02d}" if isinstance(n, int) and n > 0 else grade_label(p.grade)),
        "gradyear": str(gy), "gradyear2": str(gy)[-2:] if gy else "",
        "school": school, "schoolid": p.school, "domain": rules.domain, "rand4": rand,
        "title": p.title, "department": p.department,
    }
    return re.sub(r"\{(\w+)\}", lambda m: vals.get(m.group(1), m.group(0)), template)


# ================================================================ people ===
@dataclass
class Person:
    sis_id: str
    first: str
    last: str
    email: str
    grade: str
    school: str
    school_name: str = ""
    active: bool = True
    password: str = ""
    title: str = ""
    department: str = ""
    manager: str = ""


def people_from_export(exp: Export, mapping: dict[str, str], rules: Rules) -> list[Person]:
    def g(r, key):
        col = mapping.get(key) or ""
        return (r.get(col) or "").strip() if col else ""

    roles = {x.strip().lower() for x in rules.roles.split(",") if x.strip()}
    out = []
    for r in exp.rows:
        role = g(r, "role").lower()
        if roles and mapping.get("role") and role and role not in roles:
            continue
        active = True
        status = g(r, "status").lower()
        if status in rules.inactive_set() or \
                (rules.kind == "students" and mapping.get("status") and
                 status not in ("", "active", "0") and status.isdigit()):
            active = False
        if g(r, "enabled").lower() in ("false", "0", "no"):
            active = False
        school = g(r, "school").split(",")[0].strip()
        p = Person(sis_id=g(r, "sis_id"), first=g(r, "first"), last=g(r, "last"),
                   email=g(r, "email").lower(), grade=g(r, "grade"), school=school,
                   school_name=exp.schools.get(school, ""), active=active,
                   password=g(r, "password"), title=g(r, "title"),
                   department=g(r, "department"), manager=g(r, "manager").lower())
        if p.first or p.last or p.email:
            out.append(p)
    return out


# ================================================================== diff ===
@dataclass
class Change:
    action: str            # create, update, reactivate, withdraw, info
    email: str
    name: str
    details: str
    commands: list[list[str]]
    password: str = ""
    selected: bool = True
    supervisor: str = ""     # staff leaving with full offboarding
    person: dict = field(default_factory=dict)    # new accounts: who they are (onboarding)


def _readable_password(n=10) -> str:
    alpha = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alpha) for _ in range(n))


def _under(ou: str, root: str) -> bool:
    ou = ((ou or "/").rstrip("/") or "/").lower()
    root = ((root or "/").rstrip("/") or "/").lower()
    return root == "/" or ou == root or ou.startswith(root + "/")


def plan(people: list[Person], accounts: list[dict], rules: Rules) -> list[Change]:
    """Compare the export with Google accounts and return the changes to make.

    accounts: dicts with email, name, ou, suspended, sis_id (from the directory cache).
    """
    by_email = {a["email"].lower(): a for a in accounts}
    by_id = {str(a.get("sis_id")): a for a in accounts if a.get("sis_id")}
    taken = set(by_email)
    matched: set[str] = set()
    changes: list[Change] = []

    for p in people:
        if not p.active:
            continue
        acct = by_id.get(p.sis_id) if p.sis_id else None
        target_email = (p.email if (rules.use_sis_email and p.email) else
                        _fill(rules.email_template, p, rules)).lower()
        if acct is None:
            acct = by_email.get(target_email)
            # never take over an account that belongs to someone else (same name, other ID)
            if acct is not None and ((p.sis_id and acct.get("sis_id") and
                                      str(acct["sis_id"]) != p.sis_id) or
                                     acct["email"].lower() in matched):
                acct = None
        target_ou = _fill(rules.ou_template, p, rules).replace("//", "/")
        name = f"{p.first} {p.last}".strip()
        if acct is None:
            email = target_email
            if "@" not in email or email.startswith("@") or ".@" in email:
                changes.append(Change("info", email, name, "Can't make an email address – "
                                      "check the name, grade and email rule.", []))
                continue
            base, dom = email.split("@", 1)
            n = 2
            while email in taken:
                email = f"{base}{n}@{dom}"
                n += 1
            taken.add(email)
            if rules.password_mode == "column" and p.password:
                pw = p.password
            elif rules.password_mode == "pattern":
                pw = _fill(rules.password_pattern, p, rules, rand=str(secrets.randbelow(9000) + 1000))
            else:
                pw = _readable_password()
            cmd = ["create", "user", email, "firstname", p.first or "-", "lastname",
                   p.last or "-", "password", pw, "changepassword",
                   "on" if rules.change_at_first else "off", "ou", target_ou]
            if rules.store_sis_id and p.sis_id:
                cmd += ["externalid", "organization", p.sis_id]
            if rules.kind == "staff" and rules.update_job and (p.title or p.department):
                cmd += _org_attrs(p)
            weak = rules.password_mode == "pattern" and "{rand" not in \
                (rules.password_pattern or "").lower()
            changes.append(Change("create", email, name,
                                  ("⚠ guessable password pattern (add {rand4}) · "
                                   if weak else "") + f"New account in {target_ou}" +
                                  (" (renamed to avoid a duplicate)" if email != target_email
                                   else ""), [cmd], password=pw,
                                  supervisor=p.manager,
                                  person={"first": p.first, "last": p.last, "title": p.title,
                                          "department": p.department, "school": p.school,
                                          "school_name": rules.school_names.get(p.school, "")
                                          or p.school_name, "manager": p.manager,
                                          "ou": target_ou}))
            continue
        matched.add(acct["email"].lower())
        attrs, notes, action = [], [], "update"
        outside = not _under(acct.get("ou"), rules.managed_root)
        if acct.get("suspended"):
            attrs += ["suspended", "off"]
            notes.append("re-enrolled – unsuspend" if rules.kind == "students" else
                         "active again – unsuspend")
            action = "reactivate"
        if rules.move_ou and (acct.get("ou") or "/").rstrip("/").lower() != \
                target_ou.rstrip("/").lower():
            attrs += ["ou", target_ou]
            notes.append(f"move {acct.get('ou') or '/'} → {target_ou}")
        if rules.update_names and name and \
                _clean(acct.get("name", "")) != _clean(name):
            attrs += ["firstname", p.first, "lastname", p.last]
            notes.append(f"name “{acct.get('name', '')}” → “{name}”")
        if rules.store_sis_id and p.sis_id and str(acct.get("sis_id") or "") != p.sis_id:
            ext = merged_external_ids(acct, p.sis_id)
            if ext is None:
                notes.append("⚠ ID not saved – refresh the user list first (so their other "
                             "IDs are kept)")
            else:
                attrs += ext
                notes.append("save ID")
        if rules.kind == "staff" and rules.update_job and (p.title or p.department) and (
                (acct.get("title") or "") != p.title or
                (acct.get("department") or "") != p.department):
            orgs = merged_organizations(acct, p)
            if orgs is None:
                notes.append("⚠ job not updated – refresh the user list first (so their "
                             "other organization details are kept)")
            else:
                attrs += orgs
                notes.append(f"job “{acct.get('title') or '–'} / "
                             f"{acct.get('department') or '–'}” → "
                             f"“{p.title or '–'} / {p.department or '–'}”")
        if attrs and outside:
            # An account outside the org units this sync manages (an admin, a staff member
            # who left…) is never changed by it – an SIS email edit mustn't be enough to
            # move, rename or unsuspend it. A person checks it instead.
            changes.append(Change("info", acct["email"], name,
                                  f"⚠ outside {rules.managed_root} ({acct.get('ou') or '/'}) "
                                  "– not changed by the sync; check it's really this "
                                  f"{rules.who}: " + "; ".join(notes), []))
        elif attrs:
            changes.append(Change(action, acct["email"], name, "; ".join(notes),
                                  [["update", "user", acct["email"], *attrs]]))

    # withdrawals: listed as inactive, or (optionally) missing from the export
    inactive_ids = {p.sis_id for p in people if not p.active and p.sis_id}
    inactive_emails = {p.email for p in people if not p.active and p.email}
    for a in accounts:
        e = a["email"].lower()
        if e in matched or not _under(a.get("ou"), rules.managed_root):
            continue
        if rules.withdrawn_ou and _under(a.get("ou"), rules.withdrawn_ou) and a.get("suspended"):
            continue
        listed_inactive = (str(a.get("sis_id") or "") in inactive_ids) or e in inactive_emails
        if not listed_inactive and not rules.missing_means_withdrawn:
            continue
        if a.get("suspended") and rules.withdrawn_action != "suspend_move":
            continue
        if rules.kind == "staff":
            why = "marked inactive on the roster" if listed_inactive else "not on the roster"
        else:
            why = "marked withdrawn in the SIS" if listed_inactive else "not in the SIS export"
        if rules.withdrawn_action == "report":
            changes.append(Change("info", a["email"], a.get("name", ""),
                                  f"{why} (report only)", []))
            continue
        if rules.withdrawn_action == "offboard":
            sup = next((p.manager for p in people if not p.active and (
                p.email == e or (p.sis_id and p.sis_id == str(a.get("sis_id") or "")))), "")
            changes.append(Change("withdraw", a["email"], a.get("name", ""),
                                  f"{why} – full offboarding" +
                                  (f" (supervisor {sup})" if sup else " (no supervisor listed)"),
                                  [["offboard", a["email"]]], supervisor=sup))
            continue
        attrs = ["suspended", "on"]
        if rules.withdrawn_action == "suspend_move" and rules.withdrawn_ou:
            attrs += ["ou", rules.withdrawn_ou]
        changes.append(Change("withdraw", a["email"], a.get("name", ""),
                              f"{why} – suspend" + (f" and move to {rules.withdrawn_ou}"
                                                    if "ou" in attrs else ""),
                              [["update", "user", a["email"], *attrs]]))
    order = {"create": 0, "reactivate": 1, "update": 2, "withdraw": 3, "info": 4}
    changes.sort(key=lambda c: (order[c.action], c.email))
    return changes


_EXT_TYPES = {"account", "customer", "login_id", "network", "organization"}


def merged_external_ids(acct: dict, sis_id: str):
    """`externalid …` arguments that set the organization ID and keep every other ID the
    account has (GAM replaces the whole list). None when the saved list predates GAMbit
    keeping IDs – then nothing is changed rather than wiping IDs it can't see."""
    if "ext_ids" not in acct:
        return None
    out = []
    for e in acct.get("ext_ids") or []:
        t = (e.get("type") or "").lower()
        if t == "organization" or not e.get("value"):
            continue
        if t in _EXT_TYPES:
            out += ["externalid", t, e["value"]]
        else:
            out += ["externalid", "custom", e.get("customType") or t or "other", e["value"]]
    return out + ["externalid", "organization", sis_id]


_ORG_ARGS = (("name", "name"), ("title", "title"), ("department", "department"),
             ("location", "location"), ("costCenter", "costcenter"),
             ("description", "description"), ("domain", "domain"), ("symbol", "symbol"),
             ("fullTimeEquivalent", "fulltimeequivalent"))
_ORG_TYPES = {"domain_only", "school", "unknown", "work"}


def merged_organizations(acct: dict, p: Person):
    """`organization …` arguments that change the title/department of the primary (or
    first) organization and keep everything else – its other details and any other
    organizations. None when the saved list predates GAMbit keeping them."""
    if "orgs" not in acct:
        return None
    orgs = [dict(o) for o in acct.get("orgs") or []]
    if not orgs:
        return _org_attrs(p)
    main = next((i for i, o in enumerate(orgs) if str(o.get("primary", "")).lower() == "true"),
                0)
    if p.title:
        orgs[main]["title"] = p.title
    if p.department:
        orgs[main]["department"] = p.department
    out = []
    for i, o in enumerate(orgs):
        out.append("organization")
        t = (o.get("type") or "").lower()
        if o.get("customType"):
            out += ["customtype", o["customType"]]
        elif t in _ORG_TYPES:
            out += ["type", t]
        for key, arg in _ORG_ARGS:
            v = str(o.get(key) or "").strip()
            if v:
                out += [arg, v]
        out.append("primary" if i == main else "notprimary")
    return out


def _org_attrs(p: Person) -> list[str]:
    out = ["organization"]
    if p.title:
        out += ["title", p.title]
    if p.department:
        out += ["department", p.department]
    return out + ["primary"]


def limit_to_test_ou(changes: list[Change], accounts: list[dict], test_ou: str,
                     max_new: int = 3) -> list[Change]:
    """Test mode: only accounts already in the test OU, plus a few new ones created there."""
    ou_of = {a["email"].lower(): a.get("ou", "") for a in accounts}
    out, new = [], 0
    for c in changes:
        if c.action == "create":
            if new >= max_new:
                continue
            new += 1
            cmds, left_out = [], 0
            for i, cmd in enumerate(c.commands):
                cmd = list(cmd)
                low = [str(x).lower() for x in cmd]
                # a test account mustn't reach real people: no welcome email to their
                # supervisor and no joining real groups
                if i > 0 and (low[:1] == ["sendemail"] or low[:2] == ["update", "group"]):
                    left_out += 1
                    continue
                if "ou" in cmd:
                    cmd[cmd.index("ou") + 1] = test_ou
                cmds.append(cmd)
            out.append(dataclasses.replace(
                c, commands=cmds, details=f"TEST: new account in {test_ou}" + (
                    f" (left out in test mode: {left_out} group/email step(s))"
                    if left_out else "")))
        elif _under(ou_of.get(c.email.lower(), ""), test_ou):
            cmds = []
            for cmd in c.commands:   # keep test accounts inside the test OU
                cmd = list(cmd)
                if "ou" in cmd:
                    cmd[cmd.index("ou") + 1] = test_ou
                cmds.append(cmd)
            out.append(dataclasses.replace(c, commands=cmds, details="TEST: " + c.details))
    return out


def summarize(changes: list[Change]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in changes:
        out[c.action] = out.get(c.action, 0) + 1
    return out
