"""Per-person conveniences kept on this PC: My pages (pinned and most used), folded sidebar
sections, recently viewed people/devices/groups/org units, and practice mode.

None of this is shared through the team folder – it's each tech's own GAMbit.
"""

from __future__ import annotations

import datetime
import json

from .settings import settings

PIN_KEY, USAGE_KEY, FOLD_KEY = "nav/pinned", "nav/usage", "nav/collapsed"
FREQUENT_KEY = "nav/show_frequent"
RECENT_KEY = "recent/items"
RECENT_MAX = 25
PRACTICE_KEY = "practice/on"


def _j(key: str, default):
    try:
        v = json.loads(settings.get(key, "") or "null")
    except ValueError:
        v = None
    return default if v is None or not isinstance(v, type(default)) else v


# ============================================================== My pages ===
def pinned() -> list[str]:
    return [p for p in _j(PIN_KEY, []) if isinstance(p, str)]


def set_pinned(names: list[str]):
    out = []
    for n in names:
        if n not in out:
            out.append(n)
    settings.set(PIN_KEY, json.dumps(out))


def toggle_pin(name: str) -> bool:
    p = pinned()
    if name in p:
        p.remove(name)
        set_pinned(p)
        return False
    set_pinned(p + [name])
    return True


def usage() -> dict[str, int]:
    return {k: int(v) for k, v in _j(USAGE_KEY, {}).items() if isinstance(v, (int, float))}


def bump(name: str):
    if not name or name in ("Home",):
        return
    u = usage()
    u[name] = u.get(name, 0) + 1
    settings.set(USAGE_KEY, json.dumps(u))


def show_frequent() -> bool:
    return bool(settings.get(FREQUENT_KEY, True))


def my_pages(available: list[str], frequent: int = 5) -> tuple[list[str], list[str]]:
    """(pinned, most used) – only pages in `available` (what the role allows)."""
    have = set(available)
    pins = [p for p in pinned() if p in have]
    if not show_frequent():
        return pins, []
    used = sorted(((n, c) for n, c in usage().items() if n in have and n not in pins
                   and c >= 3), key=lambda x: -x[1])
    return pins, [n for n, _c in used[:frequent]]


def collapsed() -> set[str]:
    return {x for x in _j(FOLD_KEY, []) if isinstance(x, str)}


def set_collapsed(sections: set[str]):
    settings.set(FOLD_KEY, json.dumps(sorted(sections)))


def toggle_section(section: str) -> bool:
    c = collapsed()
    if section in c:
        c.discard(section)
    else:
        c.add(section)
    set_collapsed(c)
    return section in c


# ======================================================= recently viewed ===
ICONS = {"user": "👤", "device": "💻", "group": "👥", "ou": "🏢"}


def recent(limit: int = RECENT_MAX) -> list[dict]:
    return [r for r in _j(RECENT_KEY, []) if isinstance(r, dict) and r.get("value")][:limit]


def add_recent(kind: str, value: str, label: str = ""):
    value = (value or "").strip()
    if kind not in ICONS or not value:
        return
    items = [r for r in recent() if not (r["kind"] == kind and r["value"].lower() ==
                                         value.lower())]
    items.insert(0, {"kind": kind, "value": value, "label": label or value,
                     "when": datetime.datetime.now().isoformat(timespec="minutes")})
    settings.set(RECENT_KEY, json.dumps(items[:RECENT_MAX]))


def clear_recent():
    settings.set(RECENT_KEY, "[]")


def recent_label(r: dict) -> str:
    lab = r.get("label") or r["value"]
    extra = f"  <{r['value']}>" if r["kind"] in ("user", "group") and lab != r["value"] else ""
    return f"🕘 {ICONS[r['kind']]} {lab}{extra}"


# ========================================================== practice mode ===
def practice_on() -> bool:
    return bool(settings.get(PRACTICE_KEY, False))


def practice_target() -> tuple[str, str]:
    return ((settings.get("safety/test_ou", "") or "").strip(),
            (settings.get("safety/test_user", "") or "").strip().lower())


def practice_allows(args: list[str], users_by_email: dict | None = None) -> bool:
    """In practice mode, a change runs for real only when everything it touches is the test
    account or inside the test org unit. Anything else stays a dry run."""
    from .auth import session
    ou, user = practice_target()
    if not ou and not user:
        return False
    found = session.targets(args)
    if not found:
        return False
    users_by_email = users_by_email or {}
    for kind, v in found:
        if kind in ("ou", "dest"):
            if not ou or not session.in_scope(v, [ou]):
                return False
        elif kind == "user":
            if user and v.lower() == user:
                continue
            u = users_by_email.get(v.lower())
            if not ou or u is None or not session.in_scope(u.get("ou", ""), [ou]):
                return False
        else:                       # Chromebooks, the whole domain…
            return False
    return True
