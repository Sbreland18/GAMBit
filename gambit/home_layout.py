"""Home → Customize: which boxes Home shows, in what order, plus the quick actions, tiles,
links and notes. Each tech's own choice on this PC."""

from __future__ import annotations

import json

from .settings import settings

LAYOUT_KEY, QUICK_KEY, TILES_KEY = "home/layout", "home/quick", "home/tiles"
LINKS_KEY, NOTES_KEY = "home/links", "home/notes"

SECTIONS = {
    "status": "GAM, GAMbit and connection",
    "lookup": "Quick look-up (person or Chromebook)",
    "jobs": "Background jobs",
    "approvals": "Waiting for approval",
    "glance": "At a glance (numbers)",
    "favorites": "Favorites",
    "recent": "Recently viewed",
    "quick": "Quick actions",
    "tickets": "My open tickets",
    "notes": "My notes",
    "links": "My links",
    "whatsnew": "What's new",
    "scorecard": "District scorecard",
    "started": "Getting started",
}
ADMIN_DEFAULT = ["status", "lookup", "jobs", "approvals", "glance", "favorites", "recent",
                 "quick", "scorecard", "started"]
TECH_DEFAULT = ["lookup", "recent", "favorites", "quick", "approvals", "tickets", "notes",
                "status"]

TILES = {"accounts": "Active accounts", "suspended": "Suspended",
         "inactive": "No sign-in for 90+ days", "never": "Never signed in",
         "licenses": "Licenses assigned", "cros": "Active Chromebooks",
         "expiring": "Chromebooks losing updates", "stale": "Chromebooks not seen in 30 days",
         "alerts": "Security alerts (7 days)", "jobs": "Scheduled jobs"}

# (label, what it does) – "page:<name>", "intent:<label>", or a built-in action
QUICK = {
    "Find a user": "page:Users", "Student lookup": "page:Student lookup",
    "New staff / staff leaving": "page:Workflows", "Roster sync": "page:Roster sync",
    "Group members": "page:Groups", "Out-of-office reply": "page:Email",
    "Look up a Chromebook": "page:Chromebooks", "Chromebook fleet": "page:Chromebook fleet",
    "Approvals": "page:Approvals", "Ticket queue": "page:Ticket queue",
    "Activity log": "page:Activity log", "Schedules": "page:Schedules",
    "Clean-up by school": "page:Clean-up by school", "Senior checkout": "page:Senior checkout",
    "Chromebook sharing": "page:Chromebook sharing", "Device history": "page:Device history",
    "Custom field check": "page:Custom field check", "Reports": "page:Reports",
    "Command Builder": "page:Command Builder", "Ask the Helper": "action:helper",
    "Test connection": "action:test", "Refresh lists": "action:refresh",
}
QUICK_DEFAULT = ["Find a user", "Student lookup", "New staff / staff leaving",
                 "Group members", "Look up a Chromebook", "Approvals", "Test connection"]


def _get(key, default):
    try:
        v = json.loads(settings.get(key, "") or "null")
    except ValueError:
        v = None
    return default if v is None or not isinstance(v, type(default)) else v


def default_layout(admin: bool = True) -> list[dict]:
    on = ADMIN_DEFAULT if admin else TECH_DEFAULT
    rest = [k for k in SECTIONS if k not in on]
    return [{"id": k, "on": True} for k in on] + [{"id": k, "on": False} for k in rest]


def layout(admin: bool = True) -> list[dict]:
    saved = [x for x in _get(LAYOUT_KEY, []) if isinstance(x, dict) and x.get("id") in
             SECTIONS]
    if not saved:
        return default_layout(admin)
    have = {x["id"] for x in saved}
    return [{"id": x["id"], "on": bool(x.get("on", True))} for x in saved] + \
        [{"id": k, "on": False} for k in SECTIONS if k not in have]   # new boxes start off


def save_layout(items: list[dict]):
    settings.set(LAYOUT_KEY, json.dumps([{"id": x["id"], "on": bool(x["on"])} for x in items
                                         if x["id"] in SECTIONS]))


def reset():
    for k in (LAYOUT_KEY, QUICK_KEY, TILES_KEY):
        settings.set(k, "")


def quick() -> list[str]:
    q = [x for x in _get(QUICK_KEY, []) if x in QUICK]
    return q or list(QUICK_DEFAULT)


def save_quick(items: list[str]):
    settings.set(QUICK_KEY, json.dumps([x for x in items if x in QUICK]))


def tiles() -> list[str]:
    t = [x for x in _get(TILES_KEY, []) if x in TILES]
    return t or list(TILES)


def save_tiles(items: list[str]):
    settings.set(TILES_KEY, json.dumps([x for x in items if x in TILES]))


def links() -> list[tuple[str, str]]:
    out = []
    for ln in (settings.get(LINKS_KEY, "") or "").splitlines():
        if "=" in ln:
            name, url = ln.split("=", 1)
            url = url.strip()
            if name.strip() and url:
                out.append((name.strip(), url if "://" in url or url.startswith("\\\\")
                            else "https://" + url))
    return out


DEFAULT_LINKS = ("Google Admin console = https://admin.google.com\n"
                 "Chrome devices = https://admin.google.com/ac/chrome/devices\n"
                 "GAM wiki = https://github.com/GAM-team/GAM/wiki")
