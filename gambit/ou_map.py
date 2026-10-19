"""The district's org unit map: which org units hold students, staff, Chromebooks, loaners,
repairs and so on, which school each one belongs to, and which grade.

Set it up once in Settings & Updates → Org units & schools (“Find them for me” fills most of
it in). Every org unit inherits from the nearest mapped org unit above it, so mapping
/StudentAccounts as Students and /StudentAccounts/Hancock High School as school “Hancock
High School” covers every grade and homeroom under it.

With a team folder the map is shared, so every technician's GAMbit agrees.
"""

from __future__ import annotations

import difflib
import json
import re

from .settings import settings

TYPES = {
    "students": "Students",
    "staff": "Staff",
    "devices": "Chromebooks / devices",
    "loaners": "Loaner Chromebooks",
    "repairs": "Chromebooks in repair",
    "lost": "Lost, stolen or disabled devices",
    "former_students": "Former students (graduated, withdrawn)",
    "former_staff": "Former staff",
    "test": "Testing",
    "other": "Other (service accounts, rooms…)",
    "": "(inherit from the org unit above)",
}
DEVICE_TYPES = {"devices", "loaners", "repairs", "lost"}
SHARED_NAME = "ou_map.json"

_cache: list[dict] | None = None


# ============================================================== storage ===
def _norm_path(p: str) -> str:
    p = (p or "").strip().replace("\\", "/")
    return "/" + p.strip("/") if p.strip("/") else "/"


norm_path = _norm_path


def entries() -> list[dict]:
    """[{path, type, school, grade}] – shared copy first, then this PC's."""
    global _cache
    if _cache is not None:
        return _cache
    data = None
    try:
        from . import team
        if team.folder():
            data = team.read_shared(SHARED_NAME).get("entries")
    except Exception:  # noqa: BLE001 – a broken team folder mustn't stop the app
        data = None
    if data is None:
        try:
            data = json.loads(settings.get("oumap/entries", "[]") or "[]")
        except ValueError:
            data = []
    out = []
    for e in data if isinstance(data, list) else []:
        if isinstance(e, dict) and e.get("path"):
            out.append({"path": _norm_path(e["path"]), "type": e.get("type", "") or "",
                        "school": (e.get("school") or "").strip(),
                        "grade": (e.get("grade") or "").strip()})
    _cache = out
    return out


def save(items: list[dict]):
    global _cache
    clean = []
    seen = set()
    for e in items:
        p = _norm_path(e.get("path", ""))
        if not e.get("path") or p.lower() in seen:
            continue
        seen.add(p.lower())
        clean.append({"path": p, "type": e.get("type", "") or "",
                      "school": (e.get("school") or "").strip(),
                      "grade": (e.get("grade") or "").strip()})
    clean.sort(key=lambda e: e["path"].lower())
    settings.set("oumap/entries", json.dumps(clean))
    try:
        from . import team
        if team.folder():
            team.write_shared(SHARED_NAME, {"entries": clean})
    except Exception:  # noqa: BLE001
        pass
    _cache = clean


def reload():
    global _cache
    _cache = None


def configured() -> bool:
    return any(e["type"] for e in entries())


# ========================================================== classifying ===
def _ancestors(path: str) -> list[str]:
    p = _norm_path(path)
    parts = [x for x in p.split("/") if x]
    return ["/"] + ["/" + "/".join(parts[:i]) for i in range(1, len(parts) + 1)]


def classify(path: str, items: list[dict] | None = None) -> dict:
    """{type, school, grade, mapped_at} for any org unit (nearest mapped parent wins, per
    field)."""
    items = entries() if items is None else items
    by = {e["path"].lower(): e for e in items}
    out = {"type": "", "school": "", "grade": "", "mapped_at": ""}
    for a in _ancestors(path):
        e = by.get(a.lower())
        if not e:
            continue
        if e["type"]:
            out["type"], out["mapped_at"] = e["type"], e["path"]
        if e["school"]:
            out["school"] = e["school"]
        if e["grade"]:
            out["grade"] = e["grade"]
    return out


def is_type(path: str, kind: str, items=None) -> bool:
    return classify(path, items)["type"] == kind


def roots(kind: str, items=None) -> list[str]:
    """Top-most mapped org units of one type."""
    items = entries() if items is None else items
    paths = [e["path"] for e in items if e["type"] == kind]
    return [p for p in paths if not any(q != p and _under(p, q) for q in paths)]


def _under(path: str, root: str) -> bool:
    p, r = _norm_path(path).lower(), _norm_path(root).lower()
    return r == "/" or p == r or p.startswith(r.rstrip("/") + "/")


def schools(items=None) -> list[str]:
    items = entries() if items is None else items
    return sorted({e["school"] for e in items if e["school"]}, key=str.lower)


def school_of(path: str, items=None) -> str:
    return classify(path, items)["school"]


def device_ou_for(school: str, items=None) -> str:
    """The Chromebook org unit of a school (the top-most one typed Chromebooks)."""
    items = entries() if items is None else items
    cands = [e["path"] for e in items if e["school"].lower() == (school or "").lower()
             and classify(e["path"], items)["type"] == "devices"]
    cands.sort(key=lambda p: (p.count("/"), p.lower()))
    return cands[0] if cands else ""


def ous_of(school: str, kind: str, items=None) -> list[str]:
    items = entries() if items is None else items
    return [e["path"] for e in items if e["school"].lower() == (school or "").lower()
            and classify(e["path"], items)["type"] == kind]


def summary(items=None) -> list[dict]:
    """One row per school: its student, staff and Chromebook org units."""
    items = entries() if items is None else items
    out = []
    for s in schools(items):
        out.append({"School": s,
                    "Students": ", ".join(_top(ous_of(s, "students", items))),
                    "Staff": ", ".join(_top(ous_of(s, "staff", items))),
                    "Chromebooks": device_ou_for(s, items),
                    "Grades": ", ".join(sorted({e["grade"] for e in items if e["grade"]
                                                and classify(e["path"], items)["school"]
                                                .lower() == s.lower()}, key=_grade_key))})
    return out


def _top(paths: list[str]) -> list[str]:
    return [p for p in paths if not any(q != p and _under(p, q) for q in paths)]


# ================================================================ guess ===
GRADE_RE = re.compile(
    r"^(?:(?:grade|gr\.?)\s*(?P<a>\d{1,2})|(?P<b>\d{1,2})(?:st|nd|rd|th)?\s*(?:grade|gr)?|"
    r"(?P<k>k|kg|kinder|kindergarten)|(?P<pk>pre-?k|prek|pre ?school|pre-?kindergarten)|"
    r"(?:class\s*of\s*)?(?P<y>20\d\d)|(?P<word>first|second|third|fourth|fifth|sixth|"
    r"seventh|eighth|ninth|tenth|eleventh|twelfth|freshm[ae]n|sophomores?|juniors?|"
    r"seniors?)(?:\s*grade)?)$", re.I)
WORDS = {"first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5", "sixth": "6",
         "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10", "eleventh": "11",
         "twelfth": "12", "freshman": "9", "freshmen": "9", "sophomore": "10",
         "sophomores": "10", "junior": "11", "juniors": "11", "senior": "12", "seniors": "12"}


def grade_of_name(name: str) -> str:
    """'9th Grade' → '9', 'Kindergarten' → 'K', 'Class of 2029' → 'Class of 2029'."""
    m = GRADE_RE.match((name or "").strip())
    if not m:
        return ""
    if m.group("a") or m.group("b"):
        n = int(m.group("a") or m.group("b"))
        return str(n) if 1 <= n <= 12 else ""
    if m.group("k"):
        return "K"
    if m.group("pk"):
        return "PK"
    if m.group("y"):
        return f"Class of {m.group('y')}"
    return WORDS.get(m.group("word").lower().rstrip(), "")


def _grade_key(g: str):
    order = {"PK": -1, "K": 0}
    if g in order:
        return (0, order[g])
    return (0, int(g)) if g.isdigit() else (1, g)


def _kind_of_name(name: str, parent_kind: str = "") -> str:
    n = name.lower()
    if re.search(r"loan", n):
        return "loaners"
    if re.search(r"repair|broken|damage", n):
        return "repairs"
    if re.search(r"lost|stolen|missing", n):
        return "lost"
    if re.search(r"test|sandbox", n):
        return "test"
    if re.search(r"service|system|room|resource|shared mailbox|kiosk account|robot", n):
        return "other"
    former = re.search(r"former|graduat|alumni|withdr|inactive|left|leaver|disabled|"
                       r"suspend|archive|deprovision", n)
    if re.search(r"student|pupil|learner|kids", n) or parent_kind in ("students",
                                                                      "former_students"):
        if former:
            return "former_students"
        return "students" if re.search(r"student|pupil|learner|kids", n) else ""
    if re.search(r"staff|employee|faculty|teacher|admin|personnel", n) or parent_kind in (
            "staff", "former_staff"):
        if former:
            return "former_staff"
        return "staff" if re.search(r"staff|employee|faculty|teacher|personnel", n) else ""
    if re.search(r"chrome|device|cros|cart|laptop|kiosk", n):
        return "devices"
    if former and parent_kind in DEVICE_TYPES:
        return "lost"
    return ""


SCHOOLISH = re.compile(r"school|elementary|middle|high|academy|primary|intermediate|"
                       r"junior|senior|campus|center|centre|prep|preparatory|magnet|charter|"
                       r"\b(es|ms|hs|jhs|k-?8|k-?12)\b|district office", re.I)


def _base(name: str) -> str:
    n = re.sub(r"\b(students?|staff|chromebooks?|devices?|school|campus|the)\b", " ",
               name.lower())
    return re.sub(r"[^a-z0-9]+", "", n)


def suggest(ous: list[str]) -> list[dict]:
    """A first guess at the map from the org unit list (the person checks it)."""
    ous = sorted({_norm_path(o) for o in ous if o}, key=lambda p: (p.count("/"), p.lower()))
    out: dict[str, dict] = {}
    kind_at: dict[str, str] = {}
    for p in ous:
        if p == "/":
            continue
        parts = p.strip("/").split("/")
        parent = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"
        pk = kind_at.get(parent.lower(), "")
        k = _kind_of_name(parts[-1], pk)
        kind_at[p.lower()] = k or pk
        if k and k != pk:
            out[p.lower()] = {"path": p, "type": k, "school": "", "grade": ""}
    # schools: the level just under each top-level students / staff / devices org unit
    student_schools: list[str] = []
    for p in ous:
        parts = p.strip("/").split("/")
        if len(parts) < 2:
            continue
        parent = "/" + "/".join(parts[:-1])
        root_kind = kind_at.get(parent.lower(), "")
        parent_is_root = parent.lower() in out and out[parent.lower()]["type"] in (
            "students", "staff", "devices")
        if not parent_is_root:
            continue
        name = parts[-1]
        if out.get(p.lower(), {}).get("type") in ("loaners", "repairs", "lost", "test",
                                                   "former_students", "former_staff",
                                                   "other"):
            continue
        if _kind_of_name(name, "") in ("loaners", "repairs", "lost", "test",
                                       "former_students", "former_staff") or \
                grade_of_name(name):
            continue
        if root_kind == "students" and re.fullmatch(r"(19|20)\d\d", name.strip()):
            continue                          # a graduation-year org unit, not a school
        e = out.setdefault(p.lower(), {"path": p, "type": "", "school": "", "grade": ""})
        e["school"] = name
        if root_kind == "students":
            student_schools.append(name)
    # line device/staff school names up with the student ones ("HHS Chromebooks" → …);
    # names that match no school and don't look like one (Carts, Teachers, Admin) are
    # sub-groups, not schools
    canon = {_base(s): s for s in student_schools}
    initials = {"".join(w[0] for w in re.findall(r"[A-Za-z]+", s)
                        if w.lower() not in ("of", "the")).lower(): s for s in student_schools}
    for key, e in list(out.items()):
        if not e["school"] or e["school"] in student_schools:
            continue
        b = _base(e["school"])
        m = difflib.get_close_matches(b, list(canon), n=1, cutoff=0.75) if b else []
        if b in canon:
            e["school"] = canon[b]
        elif m:
            e["school"] = canon[m[0]]
        elif b in initials:
            e["school"] = initials[b]
        elif not SCHOOLISH.search(e["school"]):
            e["school"] = ""
            if not e["type"] and not e["grade"]:
                out.pop(key)
    # grades under student org units
    for p in ous:
        c = classify(p, list(out.values()))
        if c["type"] == "students" and (g := grade_of_name(p.rsplit("/", 1)[-1])):
            out.setdefault(p.lower(), {"path": p, "type": "", "school": "", "grade": ""})[
                "grade"] = g
    return sorted(out.values(), key=lambda e: e["path"].lower())


def merge(old: list[dict], new: list[dict]) -> list[dict]:
    """Add suggestions without overwriting what the person already set."""
    by = {e["path"].lower(): dict(e) for e in old}
    for e in new:
        cur = by.get(e["path"].lower())
        if not cur:
            by[e["path"].lower()] = dict(e)
            continue
        for k in ("type", "school", "grade"):
            if not cur.get(k) and e.get(k):
                cur[k] = e[k]
    return sorted(by.values(), key=lambda e: e["path"].lower())


# ============================================== used across GAMbit ===
def student_roots(ous: list[str] | None = None) -> list[str]:
    """Where students are: the map's Students org units, else Student lookup's setting,
    else a guess from the org unit list (a top-level org unit named like “Students”)."""
    if configured():
        r = roots("students")
        if r:
            return r
    try:
        v = json.loads(settings.get("lookup/student_ous", "") or "[]")
    except ValueError:
        v = []
    saved = [p for p in v if isinstance(p, str) and p]
    if saved:
        return saved
    guess = [norm_path(o) for o in ous or [] if norm_path(o).count("/") == 1 and
             _kind_of_name(norm_path(o)[1:]) == "students"]
    return guess or ["/Students"]


def is_student(ou: str, ous: list[str] | None = None) -> bool:
    """A current student (former-student org units under the students one don't count)."""
    if configured() and roots("students"):
        return is_type(ou, "students")
    return any(_under(ou, r) for r in student_roots(ous))


def is_staff(ou: str) -> bool:
    if configured() and roots("staff"):
        return is_type(ou, "staff")
    return _under(ou, "/Staff")
