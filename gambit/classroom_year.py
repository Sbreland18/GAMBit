"""Classroom yearly setup: archive last year's classes, create this year's from the SIS.

Sources:
  • ClassLink / OneRoster export (classes.csv + enrollments.csv + users.csv, folder or .zip)
  • any CSV with one row per student: Section ID, Course, Period, Subject, Room,
    Teacher email, Student email

Courses get a domain alias  d:<section id>-<yy>  (e.g. d:MATH7-03-27) so running the
setup again updates the same class instead of making a duplicate.
"""

from __future__ import annotations

import csv
import datetime
import io
import os
import re
import zipfile
from collections import OrderedDict


def school_year(today: datetime.date | None = None) -> tuple[int, str]:
    """(year it ends, label) – July onwards counts as the next school year."""
    d = today or datetime.date.today()
    end = d.year + 1 if d.month >= 7 else d.year
    return end, f"{end - 1}-{str(end)[-2:]}"


def _rows(data: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig", errors="replace"))))


def _norm(h):
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def _get(r: dict, *names) -> str:
    low = {_norm(k): v for k, v in r.items()}
    for n in names:
        if low.get(_norm(n)):
            return (low[_norm(n)] or "").strip()
    return ""


def _read_bundle(path: str) -> dict[str, list[dict]]:
    files = {}
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            for n in zf.namelist():
                b = os.path.basename(n).lower()
                if b.endswith(".csv"):
                    files[b] = _rows(zf.read(n))
    elif os.path.isdir(path):
        for b in os.listdir(path):
            if b.lower().endswith(".csv"):
                with open(os.path.join(path, b), "rb") as fh:
                    files[b.lower()] = _rows(fh.read())
    else:
        with open(path, "rb") as fh:
            files[os.path.basename(path).lower()] = _rows(fh.read())
        sib = os.path.dirname(path)
        for b in ("enrollments.csv", "users.csv", "courses.csv", "orgs.csv"):
            p = os.path.join(sib, b)
            if b not in files and os.path.isfile(p) and \
                    os.path.basename(path).lower() == "classes.csv":
                with open(p, "rb") as fh:
                    files[b] = _rows(fh.read())
    return files


def load_sections(path: str) -> tuple[list[dict], str]:
    """Returns (sections, description of what was read)."""
    files = _read_bundle(path)
    if "classes.csv" in files and "enrollments.csv" in files:
        return _oneroster(files), "OneRoster (classes + enrollments + users)"
    rows = next(iter(files.values()), [])
    return _flat(rows), "one row per student"


def _oneroster(files) -> list[dict]:
    users = {_get(u, "sourcedId"): u for u in files.get("users.csv", [])}
    courses = {_get(c, "sourcedId"): c for c in files.get("courses.csv", [])}
    orgs = {_get(o, "sourcedId"): _get(o, "name") for o in files.get("orgs.csv", [])}
    secs: "OrderedDict[str, dict]" = OrderedDict()
    for c in files["classes.csv"]:
        if _get(c, "status").lower() in ("tobedeleted", "inactive"):
            continue
        sid = _get(c, "sourcedId")
        course = courses.get(_get(c, "courseSourcedId"), {})
        secs[sid] = {"id": _get(c, "classCode") or sid, "course": _get(c, "title") or
                     _get(course, "title"), "subject": _get(c, "subjects") or
                     _get(course, "subjects"), "period": _get(c, "periods"),
                     "room": _get(c, "location"), "school": orgs.get(
                         _get(c, "schoolSourcedId"), ""),
                     "teachers": [], "teacher_names": [], "students": [], "_sid": sid}
    for e in files["enrollments.csv"]:
        if _get(e, "status").lower() in ("tobedeleted", "inactive"):
            continue
        s = secs.get(_get(e, "classSourcedId"))
        u = users.get(_get(e, "userSourcedId"))
        if not s or not u:
            continue
        email = (_get(u, "email") or _get(u, "username")).lower()
        if "@" not in email:
            continue
        role = (_get(e, "role") or _get(u, "role")).lower()
        if role in ("teacher", "administrator", "aide", "proctor"):
            primary = _get(e, "primary").lower() == "true"
            if primary:
                s["teachers"].insert(0, email)
                s["teacher_names"].insert(0, _get(u, "familyName"))
            else:
                s["teachers"].append(email)
                s["teacher_names"].append(_get(u, "familyName"))
        elif role == "student":
            s["students"].append(email)
    return [s for s in secs.values() if s["teachers"]]


def _flat(rows) -> list[dict]:
    secs: "OrderedDict[str, dict]" = OrderedDict()
    for r in rows:
        sid = _get(r, "Section ID", "Section", "Class ID", "SectionID", "Course Section")
        if not sid:
            continue
        s = secs.setdefault(sid, {
            "id": sid, "course": _get(r, "Course", "Course Name", "Class Name", "Title"),
            "subject": _get(r, "Subject"), "period": _get(r, "Period", "Periods", "Block"),
            "room": _get(r, "Room", "Location"), "school": _get(r, "School", "Building"),
            "teachers": [], "teacher_names": [], "students": []})
        t = _get(r, "Teacher email", "Teacher Email", "Teacher").lower()
        if "@" in t and t not in s["teachers"]:
            s["teachers"].append(t)
            s["teacher_names"].append(_get(r, "Teacher last name", "Teacher Last Name") or
                                      t.split("@")[0])
        st = _get(r, "Student email", "Student Email", "Student").lower()
        if "@" in st and st not in s["students"]:
            s["students"].append(st)
    return [s for s in secs.values() if s["teachers"]]


def alias_for(section: dict, year_end: int) -> str:
    a = re.sub(r"[^A-Za-z0-9_-]+", "-", section["id"]).strip("-")
    return f"{a}-{str(year_end)[-2:]}"


def fill(template: str, s: dict, year_label: str) -> str:
    teacher = (s["teacher_names"][0] if s["teacher_names"] else "") or ""
    vals = {"course": s["course"], "subject": s["subject"] or s["course"],
            "period": s["period"], "room": s["room"], "school": s["school"],
            "teacher": teacher.title() if teacher.islower() else teacher,
            "teacher_email": s["teachers"][0] if s["teachers"] else "",
            "section": s["id"], "year": year_label}
    out = re.sub(r"\{(\w+)\}", lambda m: str(vals.get(m.group(1), m.group(0))), template)
    out = re.sub(r"\s+([–-])\s+$", "", re.sub(r"\s{2,}", " ", out)).strip(" –-")
    return out


def plan(sections: list[dict], existing_aliases: set[str], name_tpl: str, section_tpl: str,
         year_end: int, year_label: str, add_students: bool = True) -> list[dict]:
    out = []
    for s in sections:
        alias = alias_for(s, year_end)
        cid = f"d:{alias}"
        name = fill(name_tpl, s, year_label)
        section = fill(section_tpl, s, year_label) if section_tpl else ""
        cmds = []
        exists = alias.lower() in existing_aliases
        if not exists:
            c = ["create", "course", "alias", alias, "name", name]
            if section:
                c += ["section", section]
            if s["room"]:
                c += ["room", s["room"]]
            c += ["owner", s["teachers"][0], "status", "active"]
            cmds.append(c)
        if len(s["teachers"]) > 1:
            cmds.append(["course", cid, "sync", "teachers", "addonly",
                         "users", ",".join(s["teachers"][1:])])
        if add_students and s["students"]:
            cmds.append(["course", cid, "sync", "students", "addonly",
                         "users", ",".join(s["students"])])
        out.append({"alias": alias, "name": name, "section": section,
                    "teacher": s["teachers"][0], "co_teachers": len(s["teachers"]) - 1,
                    "students": len(s["students"]),
                    "status": "already exists – add anyone missing" if exists else "new",
                    "commands": cmds})
    return out


def archive_batches(ids: list[str], size: int = 50) -> list[list[str]]:
    return [["update", "courses", ",".join(ids[i:i + size]), "state", "archived"]
            for i in range(0, len(ids), size)]
