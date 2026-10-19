"""Org-unit path helpers. Google OU paths aren't case-sensitive, and '/Former' must not
match '/FormerVolunteers'."""

from __future__ import annotations


def norm(ou: str) -> str:
    return ((ou or "/").strip().rstrip("/") or "/").lower()


def under(ou: str, root: str) -> bool:
    """True when ou is root or anywhere below it."""
    o, r = norm(ou), norm(root)
    return r == "/" or o == r or o.startswith(r + "/")
