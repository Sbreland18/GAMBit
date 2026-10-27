"""Custom fields vs the org unit map, and filling custom fields from the SIS.

**Check** (People → Custom field check): for every student, compare a custom field (Grade,
Current_School…) with what the org unit map says about the org unit they're in. Each
mismatch gets two possible fixes – move the student to the org unit the field points at,
or correct the field to match the org unit.

**Fill from the SIS**: map roster columns (from a saved roster sync) to custom fields, e.g.
Student ID → Student_Information.Student_ID, Grade → Student_Information.Grade. A preview
lists every field that would change; a background task can keep them in step each night.
"""

from __future__ import annotations

import difflib
import json
import re

from . import custom_fields as cf
from . import ou_map
from .settings import settings

CHECK_KEY = "fieldcheck/rules"
FILL_KEY = "fieldfill/config"
FILL_TASK = {"name": "GAMbit custom fields from SIS", "args": ["--task", "fieldsync"],
             "freq": "daily", "time": "04:45",
             "what": "Copies roster (SIS) values into users' custom fields", "standard": False}
AGAINST = {"grade": "Grade of the org unit", "school": "School of the org unit"}
FORMATS = {"as is": "As in the roster", "grade ordinal": "Grade as “7th Grade”",
           "grade number": "Grade as a number (K = 0)", "upper": "UPPER CASE",
           "lower": "lower case"}
PERSON_FIELDS = {"@sis_id": "Student ID (roster mapping)", "@first": "First name",
                 "@last": "Last name", "@grade": "Grade (roster mapping)",
                 "@school": "School ID (roster mapping)", "@school_name": "School name",
                 "@email": "Email"}


# ============================================================ storage ===
def _get(key: str, default):
    try:
        v = json.loads(settings.get(key, "") or "null")
    except ValueError:
        v = None
    return default if v is None else v


def rules() -> list[dict]:
    """[{field: "Schema.Field", against: grade|school}]"""
    return [r for r in _get(CHECK_KEY, []) if r.get("field") and r.get("against") in AGAINST]


def save_rules(items: list[dict]):
    settings.set(CHECK_KEY, json.dumps(items))


def guess_rules() -> list[dict]:
    """Grade / school fields from the schemas GAMbit knows about."""
    out = []
    for s, sch in cf.config().get("schemas", {}).items():
        for f in sch.get("fields", []):
            n = f["name"].lower()
            col = f"{s}.{f['name']}"
            if re.fullmatch(r"(current_?)?grade(_?level)?", n):
                out.append({"field": col, "against": "grade"})
            elif re.fullmatch(r"(current_?)?school(_?name)?", n):
                out.append({"field": col, "against": "school"})
    return out


def fill_config() -> dict:
    c = _get(FILL_KEY, {})
    return {"profile": c.get("profile", ""), "fields": dict(c.get("fields") or {}),
            "clear_blank": bool(c.get("clear_blank", False)),
            "max_changes": int(c.get("max_changes", 300) or 300),
            "match_field": c.get("match_field", "")}


def save_fill_config(c: dict):
    settings.set(FILL_KEY, json.dumps(c))


# ======================================================== normalizing ===
def norm_grade(v: str) -> str:
    """'7th Grade', '07', 'Grade 7', 'seventh' → '7'; 'K', 'Kindergarten' → 'K'."""
    v = (v or "").strip()
    if not v:
        return ""
    g = ou_map.grade_of_name(v)
    if g:
        return g
    if re.fullmatch(r"\d{1,2}", v):
        n = int(v)
        return "K" if n == 0 else str(n) if n <= 12 else v
    if v.upper() in ("KG", "KN", "TK", "00"):
        return "K"
    return v


def _school_key(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    s = re.sub(r"\b(school|schools|academy|campus|the|of)\b", " ", s)
    s = re.sub(r"\belem\b", "elementary", s)
    return re.sub(r"\s+", " ", s).strip()


def same_school(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a.strip().lower() == b.strip().lower():
        return True
    ka, kb = _school_key(a), _school_key(b)
    if not ka or not kb:
        return False
    # "Hancock Middle School" vs "Hancock Middle" vs "HMS" – words, then closeness
    if _kind(a) and _kind(b) and _kind(a) != _kind(b):
        return False                  # Hancock Middle vs Hancock High
    return ka == kb or difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.9 or \
        ka in kb or kb in ka


def _kind(s: str) -> str:
    s = (s or "").lower()
    return "e" if "elem" in s else "m" if "middle" in s or "jr" in s else \
        "h" if "high" in s or "sr" in s else ""


def grade_style(values: list[str]) -> str:
    """How the district writes grades in this field: '7th Grade', '7', 'Grade 7'…"""
    vals = [v for v in values if v]
    if not vals:
        return "ordinal"
    if sum(bool(re.fullmatch(r"\d{1,2}", v)) for v in vals) > len(vals) / 2:
        return "number"
    if sum(v.lower().startswith("grade") for v in vals) > len(vals) / 2:
        return "grade n"
    if sum(bool(re.fullmatch(r"\d{1,2}(st|nd|rd|th)", v.strip(), re.I)) for v in vals) > \
            len(vals) / 2:
        return "ordinal short"
    return "ordinal"


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def format_grade(g: str, style: str) -> str:
    g = norm_grade(g)
    if g in ("K", "PK"):
        return {"number": "0" if g == "K" else "-1"}.get(style, "Kindergarten" if g == "K"
                                                          else "Pre-K")
    if not g.isdigit():
        return g
    n = int(g)
    return {"number": str(n), "grade n": f"Grade {n}", "ordinal short": _ordinal(n)}.get(
        style, f"{_ordinal(n)} Grade")


# ============================================================== check ===
def _student_ous(items=None) -> list[dict]:
    """Student org units with their school and grade (from the org unit map)."""
    items = ou_map.entries() if items is None else items
    out = []
    for e in items:
        c = ou_map.classify(e["path"], items)
        if c["type"] == "students":
            out.append({"path": e["path"], "school": c["school"], "grade": c["grade"]})
    return out


def target_ou(school: str, grade: str, items=None) -> str:
    """The student org unit for this school and grade (most specific one)."""
    cands = []
    for o in _student_ous(items):
        if school and not same_school(o["school"], school):
            continue
        if grade and norm_grade(o["grade"]) != norm_grade(grade):
            continue
        if not school and not grade:
            continue
        cands.append(o["path"])
    cands.sort(key=lambda p: -p.count("/"))
    # only a clear answer: the deepest match, unless two equally deep ones disagree
    if len(cands) > 1 and cands[0].count("/") == cands[1].count("/"):
        return ""
    return cands[0] if cands else ""


def _val(row: dict, col: str) -> str:
    low = {(k or "").lower(): v for k, v in row.items()}
    for k in (f"customschemas.{col}".lower(), col.lower(), cf.label(col).lower(),
              cf.label(col, clash=True).lower()):
        if low.get(k):
            return str(low[k]).strip()
    vals = [str(v) for k, v in row.items() if (k or "").lower().startswith(
        f"customschemas.{col}.".lower()) and (k or "").lower().endswith(".value") and v]
    return "; ".join(vals)


def check(users: list[dict], rule_list: list[dict] | None = None, items=None,
          only_students: bool = True) -> list[dict]:
    """users: `print users … custom <schemas>` rows. One row per problem."""
    items = ou_map.entries() if items is None else items
    rule_list = rules() if rule_list is None else rule_list
    out = []
    for r in users:
        email = r.get("primaryEmail") or r.get("primaryemail") or ""
        ou = r.get("orgUnitPath") or r.get("orgunitpath") or "/"
        c = ou_map.classify(ou, items)
        if only_students and c["type"] != "students":
            continue
        if (r.get("suspended") or "").lower() == "true":
            continue
        vals = {x["field"]: _val(r, x["field"]) for x in rule_list}
        field_school = next((vals[x["field"]] for x in rule_list if x["against"] == "school"),
                            "")
        field_grade = next((vals[x["field"]] for x in rule_list if x["against"] == "grade"), "")
        for x in rule_list:
            col, v = x["field"], vals[x["field"]]
            ou_v = c["school"] if x["against"] == "school" else c["grade"]
            if not ou_v:
                continue                       # the map doesn't say – nothing to compare
            if x["against"] == "school":
                ok = same_school(v, ou_v)
            else:
                ok = norm_grade(v) == norm_grade(ou_v)
            if ok:
                continue
            move = target_ou(field_school or c["school"], field_grade or c["grade"], items) \
                if v else ""
            if move and move.lower() == ou.lower():
                move = ""
            out.append({"email": email, "name": r.get("name.fullName", "") or "",
                        "ou": ou, "field": col, "field_value": v,
                        "ou_value": ou_v, "against": x["against"],
                        "problem": "Field is empty" if not v else
                        f"{cf.label(col)} says “{v}”, the org unit says “{ou_v}”",
                        "move_to": move})
    return out


def set_value_for(row: dict, style: str = "ordinal") -> str:
    """The field value that matches the org unit."""
    if row["against"] == "grade":
        return format_grade(row["ou_value"], style)
    return row["ou_value"]


def fix_commands(rows: list[dict], how: str, style: str = "ordinal") -> list[tuple[str, list]]:
    """how: 'move' (move to the field's org unit) or 'field' (set the field to the org unit's
    value). Rows without a clear answer are skipped."""
    steps = []
    for r in rows:
        if how == "move":
            if r.get("move_to"):
                steps.append((f"Move {r['email']} to {r['move_to']}",
                              ["update", "user", r["email"], "ou", r["move_to"]]))
        else:
            v = set_value_for(r, style)
            if v:
                steps.append((f"{r['email']}: {r['field']} = {v}",
                              ["update", "user", r["email"], r["field"], v]))
    # one move per person
    seen, out = set(), []
    for lab, a in steps:
        k = (a[2], a[3])
        if k not in seen:
            seen.add(k)
            out.append((lab, a))
    return out


# ============================================================== fill ===
def _fmt(v: str, how: str) -> str:
    v = (v or "").strip()
    if how == "grade ordinal":
        return format_grade(v, "ordinal") if v else ""
    if how == "grade number":
        g = norm_grade(v)
        return {"K": "0", "PK": "-1"}.get(g, g)
    if how == "upper":
        return v.upper()
    if how == "lower":
        return v.lower()
    return v


def source_value(person, raw: dict, source: str) -> str:
    if source.startswith("@"):
        return str(getattr(person, source[1:], "") or "")
    low = {(k or "").lower(): v for k, v in (raw or {}).items()}
    return str(low.get(source.lower(), "") or "")


def fill_plan(people: list, raws: list[dict], users: list[dict], cfg: dict) -> list[dict]:
    """people: sis.Person list (same order as raws, the roster rows they came from).
    users: `print users … custom <schemas>` rows. → [{email, field, old, new}]"""
    fields = cfg.get("fields") or {}
    if not fields:
        return []
    by_email = {(u.get("primaryEmail") or "").lower(): u for u in users}
    by_id: dict[str, dict] = {}
    mf = cfg.get("match_field", "")
    if mf:
        for u in users:
            v = _val(u, mf)
            if v:
                by_id[v.lower()] = u
    out = []
    for p, raw in zip(people, raws):
        if not getattr(p, "active", True):
            continue
        u = by_email.get((p.email or "").lower()) or \
            (by_id.get((p.sis_id or "").lower()) if p.sis_id else None)
        if not u:
            continue
        email = u.get("primaryEmail")
        for col, how in fields.items():
            src, fmt = how.get("source", ""), how.get("format", "as is")
            new = _fmt(source_value(p, raw, src), fmt)
            old = _val(u, col)
            if not new and not cfg.get("clear_blank"):
                continue
            if new == old or (fmt.startswith("grade") and new and
                              norm_grade(new) == norm_grade(old) and
                              _fmt(old, fmt) == new):
                continue
            out.append({"email": email, "field": col, "old": old, "new": new})
    return out


def fill_commands(plan: list[dict]) -> list[tuple[str, list]]:
    """One `update user` per person with all their fields."""
    per: dict[str, list] = {}
    for c in plan:
        per.setdefault(c["email"], []).append(c)
    steps = []
    for email, cs in per.items():
        args = ["update", "user", email]
        for c in cs:
            args += [c["field"], c["new"]]
        steps.append((f"{email}: " + ", ".join(f"{cf.label(c['field'])} → {c['new'] or '(blank)'}"
                                               for c in cs), args))
    return steps


def users_args(cols: list[str], root: str = "") -> list[str]:
    a = ["print", "users"]
    if root and root != "/":
        a += ["query", f"orgUnitPath='{root}'"]
    return a + ["fields", "primaryemail,name,ou,suspended",
                "custom", ",".join(cf.schema_names(cols))]


def roster(profile_name: str):
    """(people, raw rows, managed root) from a saved roster sync."""
    from . import rostersync_run, sis
    p = rostersync_run.all_profiles().get(profile_name)
    if not p:
        raise RuntimeError(f"No saved roster sync called “{profile_name}”.")
    rules_ = rostersync_run.rules_from_profile(p)
    exp = rostersync_run.load_roster(p)
    mapping = p.get("mapping") or sis.guess_mapping(exp.headers, p.get("format", ""))
    people, raws = [], []
    for r in exp.rows:     # keep each person with its own roster row
        got = sis.people_from_export(sis.Export(rows=[r], headers=exp.headers,
                                                schools=exp.schools, source=exp.source),
                                     mapping, rules_)
        if got:
            people.append(got[0])
            raws.append(r)
    return people, raws, rules_.managed_root, exp.headers


def run_fill(log=print, run_csv=None, run_text=None) -> int:
    """Background task: fill custom fields from the SIS. 0 = fine, 1 = needs a look."""
    from . import activity
    cfg = fill_config()
    if not cfg["profile"] or not cfg["fields"]:
        log("Custom fields from the SIS isn't set up (People → Custom field check).")
        return 1
    if run_csv is None:
        from .directory import run_gam_csv
        run_csv = (lambda a: run_gam_csv(a, 3600))
    if run_text is None:
        from .directory import run_gam_text
        run_text = (lambda a: run_gam_text(a, 300))
    people, raws, root, _h = roster(cfg["profile"])
    code, users, err = run_csv(users_args(list(cfg["fields"]) + ([cfg["match_field"]]
                                                               if cfg["match_field"] else []),
                                          root))
    if code != 0:
        log(f"Couldn't read users: {err}")
        return 1
    plan = fill_plan(people, raws, users, cfg)
    steps = fill_commands(plan)
    log(f"{len(plan)} field change(s) for {len(steps)} people.")
    if len(steps) > cfg["max_changes"]:
        msg = (f"{len(steps)} people would change – more than the limit of "
               f"{cfg['max_changes']}, so nothing was changed. Check the roster, then run it "
               "from People → Custom field check.")
        log(msg)
        try:
            from . import alerts
            alerts.notify(msg, "GAMbit custom fields from SIS")
        except Exception:  # noqa: BLE001
            pass
        return 1
    bad = 0
    for lab, args in steps:
        if settings.get("safety/dry_run", False):
            log(f"(dry run) {lab}")
            continue
        c, out = run_text(args)
        activity.record(args, c, "done" if c == 0 else "failed", None,
                        settings.get("profile/current", "") or "Default",
                        note="custom fields from SIS")
        if c != 0:
            bad += 1
            log(f"Failed: {lab}: {(out or '').strip().splitlines()[-1:]}")
    return 1 if bad else 0
