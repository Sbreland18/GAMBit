"""Classroom guardians from the SIS: invite missing guardians, optionally remove ones the
SIS no longer lists, and report students with nobody invited / unanswered invitations.

SIS sources
  • ClassLink / OneRoster users.csv (+ the .zip): students' agentSourcedIds point at
    guardian/parent/relative rows (or the other way round)
  • any CSV: Student email + one or more Guardian/Parent email columns
"""

from __future__ import annotations

import csv
import datetime
import io
import os
import re
import zipfile

GUARDIAN_ROLES = {"guardian", "parent", "relative"}


def _norm(h):
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def _get(r, *names):
    low = {_norm(k): v for k, v in r.items()}
    for n in names:
        if low.get(_norm(n)):
            return (low[_norm(n)] or "").strip()
    return ""


def _rows(data: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig", errors="replace"))))


def load_links(path: str) -> tuple[set[tuple[str, str]], str]:
    """{(student email, guardian email)} and a description of the source."""
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            name = next((n for n in zf.namelist() if os.path.basename(n).lower() ==
                         "users.csv"), None)
            if not name:
                raise ValueError("No users.csv in that zip.")
            rows = _rows(zf.read(name))
    else:
        with open(path, "rb") as fh:
            rows = _rows(fh.read())
    if not rows:
        return set(), "empty file"
    heads = {_norm(h) for h in rows[0]}
    if "agentsourcedids" in heads and "role" in heads:
        return _oneroster(rows), "OneRoster users.csv"
    return _flat(rows), "student/guardian columns"


def _oneroster(rows) -> set:
    by_id = {_get(r, "sourcedId"): r for r in rows}
    links = set()
    for r in rows:
        role = _get(r, "role").lower()
        email = _get(r, "email").lower()
        agents = [a.strip() for a in _get(r, "agentSourcedIds").split(",") if a.strip()]
        if _get(r, "status").lower() == "tobedeleted":
            continue
        for a in agents:
            other = by_id.get(a)
            if not other:
                continue
            oemail = _get(other, "email").lower()
            orole = _get(other, "role").lower()
            if role == "student" and orole in GUARDIAN_ROLES and "@" in email and "@" in oemail:
                links.add((email, oemail))
            elif role in GUARDIAN_ROLES and orole == "student" and "@" in email and \
                    "@" in oemail:
                links.add((oemail, email))
    return links


def _flat(rows) -> set:
    links = set()
    heads = list(rows[0].keys())
    gcols = [h for h in heads if re.search(r"(guardian|parent|contact).*(email|e-mail)", h,
                                           re.I)]
    for r in rows:
        s = _get(r, "Student email", "Student Email", "Student", "Email").lower()
        if "@" not in s:
            continue
        for c in gcols:
            for g in re.split(r"[;,\s]+", (r.get(c) or "").lower()):
                if "@" in g:
                    links.add((s, g))
    return links


def parse_current(text: str) -> list[dict]:
    """`print guardians all showstudentemails` → [{student, guardian, kind, state, since, id}]"""
    out = []
    for r in csv.DictReader(io.StringIO(text or "")):
        student = _get(r, "studentEmail", "studentId").lower()
        guardian = _get(r, "invitedEmailAddress", "guardianProfile.emailAddress",
                        "guardianEmail").lower()
        if not student or not guardian:
            continue
        inv = bool(_get(r, "invitationId"))
        out.append({"student": student, "guardian": guardian,
                    "kind": "invitation" if inv else "guardian",
                    "state": (_get(r, "state") or ("COMPLETE" if not inv else "")).upper(),
                    "since": _get(r, "creationTime")[:10], "id": _get(r, "invitationId")})
    return out


def plan(links: set, current: list[dict], students: set[str], remove_extra: bool = False):
    """Returns (invites, removals) as lists of dicts with commands."""
    have = {(c["student"], c["guardian"]) for c in current
            if c["kind"] == "guardian" or c["state"] == "PENDING"}
    invites = [{"student": s, "guardian": g,
                "args": ["user", s, "create", "guardian", g]}
               for s, g in sorted(links) if (s, g) not in have and s in students]
    removals = []
    if remove_extra:
        for c in current:
            if (c["student"], c["guardian"]) in links or c["student"] not in students:
                continue
            if c["kind"] == "guardian":
                removals.append({"student": c["student"], "guardian": c["guardian"],
                                 "args": ["user", c["student"], "delete", "guardian",
                                          c["guardian"], "accepted"]})
            elif c["state"] == "PENDING":
                removals.append({"student": c["student"], "guardian": c["guardian"],
                                 "args": ["user", c["student"], "delete", "guardian",
                                          c["guardian"], "invitations"]})
    return invites, removals


def missing_report(students: list[dict], current: list[dict], days: int = 14):
    """(students with nobody, invitations unanswered for more than `days`)."""
    has = {c["student"] for c in current if c["kind"] == "guardian" or
           c["state"] == "PENDING"}
    nobody = [s for s in students if s["email"].lower() not in has]
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    stale = [c for c in current if c["kind"] == "invitation" and c["state"] == "PENDING"
             and c["since"] and c["since"] < cutoff]
    return nobody, stale
