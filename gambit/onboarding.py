"""The first-day checklist on Home: the handful of things that make GAMbit work well on a
new PC or for a new tech. Each item ticks itself off when GAMbit sees it's done."""

from __future__ import annotations

from .settings import settings

HIDE_KEY = "onboard/hidden"
DRY_KEY = "onboard/dry_tried"
TASKS_KEY = "onboard/tasks_ok"
SOLO_KEY = "onboard/solo"


def hidden() -> bool:
    return bool(settings.get(HIDE_KEY, False))


def set_hidden(on: bool):
    settings.set(HIDE_KEY, bool(on))


def tasks_installed() -> bool:
    """True once GAMbit's standard background tasks exist in Task Scheduler (checked in the
    background and remembered; only on Windows)."""
    if settings.get(TASKS_KEY, False):
        return True
    try:
        from . import scheduler
        names = {t.get("Name", "") for t in scheduler.list_tasks()}
    except Exception:  # noqa: BLE001
        return False
    ok = any("staff requests" in n for n in names) and any("daily follow-ups" in n
                                                          for n in names)
    if ok:
        settings.set(TASKS_KEY, True)
    return ok


def items(directory=None, tasks_ok: bool | None = None) -> list[dict]:
    """[{key, title, why, done, optional}] in the order to do them."""
    from . import gam_setup, ou_map, team, user_prefs
    try:
        connected = gam_setup.is_fully_set_up() and (
            directory is None or directory.connected is not False)
    except Exception:  # noqa: BLE001
        connected = False
    out = [
        {"key": "gam", "title": "Connect GAM to Google Workspace",
         "why": "The setup wizard installs GAM and signs it in – about 15 minutes, once.",
         "done": connected},
        {"key": "lists", "title": "Load your people, groups and org units",
         "why": "So searches, pickers and the numbers on Home work.",
         "done": bool(getattr(directory, "users", None))},
        {"key": "schools", "title": "Tell GAMbit which org units are your schools",
         "why": "Students vs staff, schools and grades – used by reports, Back to school "
                "and Chromebooks. “Find them for me” does most of it.",
         "done": ou_map.configured()},
        {"key": "test", "title": "Set a test account and a test org unit",
         "why": "Practice mode and Live test make real changes only there.",
         "done": bool((settings.get("safety/test_user", "") or "").strip() and
                      (settings.get("safety/test_ou", "") or "").strip())},
        {"key": "dry", "title": "Try a dry run",
         "why": "Turn on Dry run in the top bar and do something – GAMbit lists the exact "
                "GAM commands and changes nothing.",
         "done": bool(settings.get(DRY_KEY, False))},
        {"key": "pin", "title": "Pin the pages you use most",
         "why": "Right-click a page in the sidebar → Pin to My pages.",
         "done": bool(user_prefs.pinned())},
        {"key": "tasks", "title": "Set up the background tasks",
         "why": "Nightly jobs, staff requests, Run later and the weekly digest run from "
                "Windows Task Scheduler.",
         "done": bool(tasks_ok) if tasks_ok is not None else bool(settings.get(TASKS_KEY,
                                                                             False))},
        {"key": "team", "title": "Share with your team (optional)",
         "why": "A team folder gives everyone the same roles, approvals and activity log. "
                "Skip it if you're the only tech.",
         "done": bool(team.folder()) or bool(settings.get(SOLO_KEY, False)),
         "optional": True},
    ]
    return out


def progress(its: list[dict]) -> tuple[int, int]:
    return sum(1 for i in its if i["done"]), len(its)


def complete(its: list[dict]) -> bool:
    return all(i["done"] or i.get("optional") for i in its)
