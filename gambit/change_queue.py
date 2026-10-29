"""Run later and change freezes.

• Run later – queue any change (or an approved request) to run tonight or on a date. The
  “staff requests” background task (every 15 minutes) runs what's due.
• Change freezes – windows (state testing, the first week of school…) when risky kinds of
  change are blocked. A Full admin can override; every override is logged with its reason.
"""

from __future__ import annotations

import datetime
import json
import uuid

from .settings import settings

RISKY_DEFAULT = ["delete", "suspend", "everyone", "chromebooks"]


def _read(name, key):
    from . import team
    if team.folder():
        d = team.read_shared(name)
        if d:
            return d.get(key, [])
    try:
        return json.loads(settings.get(f"changequeue/{key}", "[]") or "[]")
    except ValueError:
        return []


def _write(name, key, items):
    from . import team
    if team.folder():
        team.write_shared(name, {key: items})
    settings.set(f"changequeue/{key}", json.dumps(items))


def queue() -> list[dict]:
    return _read("change_queue.json", "items")


def save_queue(items: list[dict]):
    _write("change_queue.json", "items", items)


def _lock_path() -> str:
    import os
    from . import team
    p = team.shared_templates_path("change_queue.json") if team.folder() else ""
    if p:
        return os.path.join(os.path.dirname(p), "change_queue.lock")
    from .activity import local_dir
    return os.path.join(local_dir(), "change_queue.lock")


def update(fn) -> list[dict]:
    """Read the queue, let fn(items) change it, save – all while holding the queue's lock,
    so changes made meanwhile by another PC (or the background task) aren't lost."""
    from .file_lock import held
    with held(_lock_path()):
        items = queue()
        fn(items)
        save_queue(items)
        return items


def claim(ids, who: str = "") -> list[dict]:
    """Mark waiting items as running and return them. Only one GAMbit can claim an item,
    so nothing runs twice (Run now here while the background task runs it too)."""
    import socket
    want = set(ids)
    got: list[dict] = []

    def fn(items):
        for it in items:
            if it.get("id") in want and it.get("status") == "waiting":
                it["status"] = "running"
                it["claimed"] = f"{who or socket.gethostname()} " + \
                    datetime.datetime.now().isoformat(timespec="minutes")
                got.append(json.loads(json.dumps(it)))
    update(fn)
    return got


def finish(item_id: str, status: str, result: str = "", **extra):
    """Record how an item went. Passwords in its commands aren't kept once it has run."""
    from .activity import mask

    def fn(items):
        for it in items:
            if it.get("id") == item_id:
                it.update({"status": status, "result": result, **extra})
                it["commands"] = [mask(list(c)) for c in it.get("commands", [])]
    update(fn)


def cancel(ids) -> int:
    from .activity import mask
    want, n = set(ids), [0]

    def fn(items):
        for it in items:
            if it.get("id") in want and it.get("status") == "waiting":
                it["status"] = "cancelled"
                it["commands"] = [mask(list(c)) for c in it.get("commands", [])]
                n[0] += 1
    update(fn)
    return n[0]


def freezes() -> list[dict]:
    return _read("change_freezes.json", "freezes")


def save_freezes(items: list[dict]):
    _write("change_freezes.json", "freezes", items)


SEAL_KIND = "queue"
SEAL_FIELDS = ("id", "when", "commands", "title", "by", "request", "profile", "added")


class QueueRefused(ValueError):
    pass


def check_can_queue(commands: list[list[str]]):
    """Refuse what mustn't wait in a shared file: passwords (they'd sit in the team folder
    until tonight) and anything the person queuing it couldn't run themselves right now."""
    from . import secret_args, team
    for c in commands:
        if secret_args.literal_passwords(c) or any(str(a) == secret_args.NEWPW for a in c):
            raise QueueRefused("Password changes can't wait in Run later (the password would "
                               "be kept in the team folder until then). Run them now.")
        ok, missing, _ask = team.check([str(a) for a in c])
        if not ok:
            raise QueueRefused("Your GAMbit role can't run that, so it can't be queued for "
                               f"later either ({', '.join(sorted(missing))}).")


def verify(it: dict):
    from . import seal
    return seal.check(SEAL_KIND, it, SEAL_FIELDS)


def sign_item(it: dict) -> dict:
    from . import seal
    return seal.sign(SEAL_KIND, it, SEAL_FIELDS)


def resign(item_id: str) -> bool:
    """Someone allowed to run these commands checked a waiting item and signs it."""
    from . import team
    done = [False]

    def fn(items):
        for i, it in enumerate(items):
            if it.get("id") == item_id and it.get("status") == "waiting":
                for c in it.get("commands", []):
                    ok, missing, _ask = team.check([str(a) for a in c])
                    if not ok:
                        raise QueueRefused("Your GAMbit role can't run all of it "
                                           f"({', '.join(sorted(missing))}).")
                items[i] = sign_item({**it, "by": team.me()})
                items[i].pop("blocked", None)
                done[0] = True
    update(fn)
    return done[0]


def add(commands: list[list[str]], when: str, title: str, who: str, request: str = "",
        profile: str | None = None, check_role: bool = True) -> dict:
    """Queue commands. They run in the domain profile that was in use when queued, and
    only while the item's signature (who queued it) is valid."""
    commands = [[str(a) for a in c] for c in commands]
    if check_role:
        check_can_queue(commands)
    if profile is None:
        try:
            from . import profiles
            profile = profiles.current_name()
        except Exception:  # noqa: BLE001
            profile = ""
    it = {"id": uuid.uuid4().hex[:8], "when": when, "commands": commands, "title": title,
          "by": who, "request": request, "status": "waiting", "result": "",
          "profile": profile or "",
          "added": datetime.datetime.now().isoformat(timespec="minutes")}
    it = sign_item(it)
    update(lambda items: items.append(it))
    return it


def tonight(hour: int = 22) -> str:
    now = datetime.datetime.now()
    t = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if t <= now:
        t += datetime.timedelta(days=1)
    return t.isoformat(timespec="minutes")


def new_freeze(name: str, start: str, end: str, categories: list[str], who: str) -> dict:
    return {"id": uuid.uuid4().hex[:6], "name": name, "start": start, "end": end,
            "categories": categories or list(RISKY_DEFAULT), "by": who}


def active_freeze(args: list[str], when: datetime.datetime | None = None,
                  items: list[dict] | None = None) -> dict | None:
    """The freeze that blocks this command right now, if any."""
    from . import team
    from .activity import is_change
    if not is_change(args):
        return None
    t = (when or datetime.datetime.now()).isoformat(timespec="minutes")
    cats = team.categorize(args)
    for f in items if items is not None else freezes():
        a, b = span(f)
        if a <= t <= b and cats & set(f.get("categories", RISKY_DEFAULT)):
            return f
    return None


def span(f: dict) -> tuple[str, str]:
    a, b = f.get("start", "") or "0000", f.get("end", "") or "9999"
    if len(a) == 10:
        a += "T00:00"
    if len(b) == 10:
        b += "T23:59"
    return a, b


def log_override(args: list[str], freeze: dict, reason: str, who: str):
    from . import activity
    activity.record(list(args), 0, "override", None,
                    settings.get("profile/current", "") or "Default",
                    note=f"change freeze “{freeze['name']}” overridden by {who}: {reason}")


def seal_secret(cmd) -> bool:
    from . import secret_args
    return secret_args.literal_passwords(cmd) or any(str(a) == secret_args.NEWPW for a in cmd)


def due(items: list[dict], now: datetime.datetime | None = None) -> list[dict]:
    t = (now or datetime.datetime.now()).isoformat(timespec="minutes")
    return [i for i in items if i["status"] == "waiting" and i["when"] <= t]


def run_due(log=print, run_text=None, now=None) -> list[str]:
    """Background: run queued changes that are due (held back during a freeze). Each item
    is claimed first, so two PCs never both run it, and runs in the domain profile it was
    queued in."""
    from . import activity, team
    from .directory import run_gam_text
    run_text = run_text or run_gam_text
    lines = []
    if settings.get("safety/dry_run", False):
        return lines
    users = None
    for it in due(queue(), now):
        # only items whose signer may run them unattended – a hand-edited team folder
        # file (or one written by malware) never runs anything
        from . import seal
        if users is None:
            try:
                from .directory import load_users
                users = load_users() if seal.signin_required() else []
            except Exception:  # noqa: BLE001
                users = []
        why = seal.may_run(verify(it), it.get("commands", []), users)
        if not why and any(seal_secret(c) for c in it.get("commands", [])):
            why = "it contains a password change"
        if why:
            if it.get("blocked") != why:
                def mark_blocked(items, i=it["id"], w=why):
                    for x in items:
                        if x.get("id") == i:
                            x["blocked"] = w
                update(mark_blocked)
                lines.append(f"“{it.get('title', '?')}” not run – {why}. Someone allowed to "
                             "run it can check and sign it on Run later & freezes.")
            continue
        blocked = next((active_freeze(c, now) for c in it["commands"]
                        if active_freeze(c, now)), None)
        if blocked:
            if it.get("held") != blocked["id"]:
                def hold(items, i=it["id"], f=blocked["id"]):
                    for x in items:
                        if x.get("id") == i:
                            x["held"] = f
                update(hold)
                lines.append(f"“{it['title']}” is waiting – change freeze “{blocked['name']}” "
                             f"until {blocked['end']}.")
            continue
        mine = claim([it["id"]])
        if not mine:
            continue                      # someone else got it (or it was cancelled)
        it = mine[0]
        if seal.may_run(verify(it), it.get("commands", []), users):   # changed meanwhile?
            finish(it["id"], "failed", "changed after it was checked – not run")
            lines.append(f"“{it.get('title', '?')}” not run – it changed while waiting.")
            continue
        saved = dict(settings.override)
        try:
            prof = (it.get("profile") or "").strip()
            if prof:
                from . import profiles
                if prof.lower() != (profiles.current_name() or "").lower():
                    from .headless import use_profile
                    try:
                        use_profile(prof)
                    except RuntimeError as exc:
                        finish(it["id"], "failed", str(exc),
                               ran=datetime.datetime.now().isoformat(timespec="minutes"))
                        lines.append(f"“{it['title']}” not run: {exc}")
                        continue
            bad = 0
            for cmd in it["commands"]:
                try:
                    c, _out = run_text(cmd, 600)
                except Exception:  # noqa: BLE001
                    c = 1
                bad += 1 if c else 0
                activity.record(cmd, c, "done" if c == 0 else "failed", None,
                                prof or settings.get("profile/current", "") or "Default",
                                note=f"run later “{it['title']}” (queued by {it['by']})")
        finally:
            settings.override.clear()
            settings.override.update(saved)
        status = "done" if not bad else "failed"
        result = f"{len(it['commands']) - bad} ok, {bad} failed"
        finish(it["id"], status, result,
               ran=datetime.datetime.now().isoformat(timespec="minutes"))
        lines.append(f"Ran “{it['title']}”: {result}")
        if it.get("request") and team.folder():
            req = next((r for r in team.list_requests() if r["id"] == it["request"]), None)
            if req:
                team.update_request(req, status, result=result + " (run later)")
    for ln in lines:
        log(ln)
    return lines
