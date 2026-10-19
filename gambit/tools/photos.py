"""Bulk profile photos: match picture files to accounts by email, username or SIS ID."""

from __future__ import annotations

import os
from dataclasses import dataclass

EXTS = (".jpg", ".jpeg", ".png")
MAX_BYTES = 5 * 1024 * 1024


@dataclass
class Match:
    path: str
    email: str
    how: str          # email | username | id | ''
    problem: str = ""


def scan(folder: str) -> list[str]:
    out = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if os.path.isfile(p) and name.lower().endswith(EXTS):
            out.append(p)
    return out


def match(files: list[str], users: list[dict], by: str = "auto") -> list[Match]:
    """by: auto | email | username | id"""
    by_email = {u["email"].lower(): u for u in users}
    by_user: dict[str, list[dict]] = {}
    for u in users:
        by_user.setdefault(u["email"].split("@")[0].lower(), []).append(u)
    by_id = {str(u.get("sis_id")).lower(): u for u in users if u.get("sis_id")}
    out = []
    for p in files:
        stem = os.path.splitext(os.path.basename(p))[0].strip().lower()
        email, how, problem = "", "", ""
        if by in ("auto", "email") and stem in by_email:
            email, how = by_email[stem]["email"], "email"
        elif by in ("auto", "id") and stem in by_id:
            email, how = by_id[stem]["email"], "SIS ID"
        elif by in ("auto", "id") and stem.lstrip("0") and stem.lstrip("0") in by_id:
            email, how = by_id[stem.lstrip("0")]["email"], "SIS ID"
        elif by in ("auto", "username") and stem in by_user:
            if len(by_user[stem]) == 1:
                email, how = by_user[stem][0]["email"], "username"
            else:
                problem = "username matches more than one account"
        if not email and not problem:
            problem = "no matching account"
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        if email and size == 0:
            problem = "empty file"
        elif email and size > MAX_BYTES:
            problem = "bigger than 5 MB – resize it first"
        out.append(Match(p, email, how, problem))
    return out


def commands(matches: list[Match]) -> list[list[str]]:
    return [["user", m.email, "update", "photo", m.path] for m in matches
            if m.email and not m.problem]
