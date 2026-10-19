"""Release check: before installing a GAMbit update, run a set of read-only checks against
your domain and remember the results; the first time the new version starts it runs them
again. If something that worked before now fails, GAMbit offers – or, if you allow it,
starts – going back to the previous version."""

from __future__ import annotations

import datetime
import json
import os

from .settings import settings


def checks() -> list[tuple[str, list[str] | None]]:
    from . import google_io
    admin = google_io.admin_email()
    out = [("GAM runs", ["version"]), ("Reads the domain", ["info", "domain"]),
           ("Reads org units", ["print", "ous", "fields", "orgunitpath"])]
    if "@" in admin:
        out.append(("Reads an account", ["info", "user", admin, "quick"]))
    out += [("Settings file", None), ("Team folder", None), ("Background tasks", None)]
    return out


def _local(name: str) -> tuple[bool, str]:
    if name == "Settings file":
        try:
            settings.set("release/probe", datetime.datetime.now().isoformat())
            return bool(settings.get("release/probe", "")), ""
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
    if name == "Team folder":
        from . import team
        d = team.folder()
        if not d:
            return True, "no team folder"
        try:
            p = os.path.join(d, ".gambit-probe")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("ok")
            os.remove(p)
            return True, ""
        except OSError as exc:
            return False, str(exc)
    if name == "Background tasks":
        try:
            from . import tasks_health
            bad = [r["name"] for r in tasks_health.rows() if r["state"] == "failed"]
            return (not bad), ", ".join(bad[:5])
        except Exception as exc:  # noqa: BLE001
            return True, f"not checked ({exc})"
    return True, ""


def run(run_text=None) -> list[dict]:
    from .directory import run_gam_text
    run_text = run_text or run_gam_text
    out = []
    for name, args in checks():
        if args is None:
            ok, detail = _local(name)
        else:
            try:
                c, text = run_text(args, 120)
                ok, detail = c == 0, "" if c == 0 else (text or "").strip()[-160:]
            except Exception as exc:  # noqa: BLE001
                ok, detail = False, str(exc)
        out.append({"Check": name, "OK": ok, "Detail": detail})
    return out


def regressions(before: list[dict], after: list[dict]) -> list[dict]:
    """Checks that passed before the update and fail now."""
    was = {b["Check"]: b["OK"] for b in before}
    return [a for a in after if not a["OK"] and was.get(a["Check"], True)]


def before_update(new_version: str, run_text=None) -> list[dict]:
    res = run(run_text)
    settings.set("release/before", json.dumps(res))
    settings.set("release/pending", new_version)
    return res


def pending_for(version: str) -> bool:
    return bool(settings.get("release/pending", "")) and settings.get("release/pending", "") \
        == version


def after_update(run_text=None) -> tuple[list[dict], list[dict]]:
    try:
        before = json.loads(settings.get("release/before", "[]") or "[]")
    except ValueError:
        before = []
    after = run(run_text)
    bad = regressions(before, after)
    settings.set("release/pending", "")
    settings.set("release/last", json.dumps({"time": datetime.datetime.now().isoformat(
        timespec="minutes"), "after": after, "regressions": bad}))
    return after, bad
