"""Daily Classroom roster sync from the SIS: keep each class that GAMbit created (alias
d:<section>-<yy>) matched to the SIS enrollments all year – students added as schedules
change and, optionally, removed when they drop – with a practice preview and a brake on
unusually large changes."""

from __future__ import annotations

import json

from ..settings import settings

COURSES_ARGS = ["print", "courses", "states", "active,provisioned", "aliases",
                "fields", "id,name"]
PARTS_ARGS = ["print", "course-participants", "states", "active", "show", "students"]
TASK = {"name": "GAMbit Classroom roster sync", "args": ["--task", "classroomsync"],
        "freq": "daily", "time": "05:35",
        "what": "Keeps Classroom classes matched to the SIS enrollments", "standard": False}


def options() -> dict:
    try:
        o = json.loads(settings.get("classroomsync/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"source": "sis", "path": "", "remove": False, "teachers": True,
            "max_changes": 300, **o}


def save_options(o: dict):
    settings.set("classroomsync/options", json.dumps(o))


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def class_map(course_rows: list[dict]) -> dict[str, dict]:
    """alias (without d:) → {id, name}"""
    out = {}
    for r in course_rows:
        low = _low(r)
        for k, v in low.items():
            if k.startswith("alias") and v:
                for a in v.replace(",", " ").split():
                    out[a.lower().removeprefix("d:")] = {"id": low.get("id", ""),
                                                         "name": low.get("name", "")}
    return out


def members(part_rows: list[dict]) -> dict[str, dict[str, set]]:
    """course id → {"students": set, "teachers": set}"""
    out: dict[str, dict[str, set]] = {}
    for r in part_rows:
        low = _low(r)
        cid = low.get("courseid", "")
        e = (low.get("profile.emailaddress") or "").lower()
        if not cid or not e:
            continue
        role = "teachers" if low.get("userrole", "").upper() == "TEACHER" else "students"
        out.setdefault(cid, {"students": set(), "teachers": set()})[role].add(e)
    return out


def plan(sections: list[dict], classes: dict, current: dict, year_end: int,
         opts: dict) -> list[dict]:
    """→ [{class, alias, adds, removes, teacher_adds, commands}] for classes that differ."""
    from ..classroom_year import alias_for
    out = []
    for s in sections:
        alias = alias_for(s, year_end).lower()
        c = classes.get(alias)
        if not c:
            continue
        cur = current.get(c["id"], {"students": set(), "teachers": set()})
        want = {e.lower() for e in s.get("students", [])}
        adds = sorted(want - cur["students"])
        removes = sorted(cur["students"] - want) if opts.get("remove") else []
        tadds = sorted({t.lower() for t in s.get("teachers", [])[1:]} - cur["teachers"]) \
            if opts.get("teachers", True) else []
        if not (adds or removes or tadds):
            continue
        cmds = [["course", c["id"], "add", "student", e] for e in adds] + \
            [["course", c["id"], "remove", "student", e] for e in removes] + \
            [["course", c["id"], "add", "teacher", t] for t in tadds]
        out.append({"class": c["name"], "alias": alias, "adds": adds, "removes": removes,
                    "teacher_adds": tadds, "commands": cmds})
    return out


def totals(p: list[dict]) -> dict:
    return {"classes": len(p), "adds": sum(len(x["adds"]) for x in p),
            "removes": sum(len(x["removes"]) for x in p),
            "teachers": sum(len(x["teacher_adds"]) for x in p),
            "commands": sum(len(x["commands"]) for x in p)}


def too_big(p: list[dict], opts: dict) -> bool:
    return totals(p)["commands"] > int(opts.get("max_changes", 300) or 300)


def sections_from(opts: dict) -> list[dict]:
    from ..classroom_year import load_sections
    if opts.get("source") == "file" and opts.get("path"):
        path = opts["path"]
    else:
        from ..integrations import sis_api
        path = sis_api.download()
    secs, _how = load_sections(path)
    return secs


def build(opts: dict, run_csv, sections=None) -> list[dict]:
    from ..classroom_year import school_year
    sections = sections if sections is not None else sections_from(opts)
    c1, crs, e1 = run_csv(COURSES_ARGS)
    if c1 != 0:
        raise RuntimeError("Couldn't list classes: " + (e1 or "").strip()[-200:])
    show = PARTS_ARGS if not opts.get("teachers", True) else PARTS_ARGS[:-1] + ["all"]
    c2, parts, e2 = run_csv(show)
    if c2 != 0:
        raise RuntimeError("Couldn't read class rosters: " + (e2 or "").strip()[-200:])
    year_end, _label = school_year()
    return plan(sections, class_map(crs), members(parts), year_end, opts)


def run(log=print, run_csv=None, run_text=None, sections=None) -> list[str]:
    from .. import activity
    from ..directory import run_gam_csv, run_gam_text
    run_csv = run_csv or (lambda a: run_gam_csv(a, 3600))
    run_text = run_text or run_gam_text
    opts = options()
    p = build(opts, run_csv, sections)
    t = totals(p)
    lines = [f"Classroom sync: {t['classes']} class(es) differ – {t['adds']} to add, "
             f"{t['removes']} to remove, {t['teachers']} co-teacher(s)."]
    if too_big(p, opts):
        lines.append(f"That's more than your limit of {opts['max_changes']} changes – nothing "
                     "applied. Check the SIS data, then run it by hand.")
        try:
            from .. import alerts
            alerts.notify(lines[-1], "GAMbit Classroom sync")
        except Exception:  # noqa: BLE001
            pass
    elif not settings.get("safety/dry_run", False):
        bad = 0
        for x in p:
            for cmd in x["commands"]:
                c, _o = run_text(cmd, 120)
                bad += 1 if c else 0
                activity.record(cmd, c, "done" if c == 0 else "failed", None,
                                settings.get("profile/current", "") or "Default",
                                note="Classroom roster sync")
        lines.append(f"Applied {t['commands'] - bad}, {bad} failed.")
    for ln in lines:
        log(ln)
    return lines


__all__ = ["run", "build", "plan"]
