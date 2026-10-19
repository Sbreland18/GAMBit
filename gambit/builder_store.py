"""Favorites and saved templates for the Command Builder (stored as JSON).

Favorites are personal (AppData/builder.json). Templates can be personal or,
when a team folder is set, shared with the team (<team>/templates/builder.json).
"""

from __future__ import annotations

import json
import os

from PySide6.QtCore import QStandardPaths


def _path() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    return os.path.join(base, "builder.json")


def load() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        data = {}
    data.setdefault("favorites", [])
    data.setdefault("templates", [])
    return data


def save(data: dict):
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, _path())


def toggle_favorite(syntax: str) -> bool:
    data = load()
    if syntax in data["favorites"]:
        data["favorites"].remove(syntax)
        on = False
    else:
        data["favorites"].append(syntax)
        on = True
    save(data)
    return on


def _shared() -> dict:
    from . import team
    data = team.read_shared("builder.json") if team.folder() else {}
    data.setdefault("templates", [])
    return data


def templates() -> list[dict]:
    """Shared team templates first, then this PC's own."""
    shared = [{**t, "shared": True} for t in _shared()["templates"]]
    names = {t["name"] for t in shared}
    mine = [t for t in load()["templates"] if t["name"] not in names]
    return sorted(shared, key=lambda t: t["name"].lower()) + mine


def save_template(name: str, commands: list[str], description: str = "",
                  shared: bool = False):
    from . import team
    entry = {"name": name, "description": description, "commands": commands}
    if shared:
        data = _shared()
        entry["by"] = team.me()
        data["templates"] = [t for t in data["templates"] if t["name"] != name] + [entry]
        data["templates"].sort(key=lambda t: t["name"].lower())
        team.write_shared("builder.json", data)
        mine = load()      # don't keep a personal copy with the same name
        mine["templates"] = [t for t in mine["templates"] if t["name"] != name]
        save(mine)
        return
    data = load()
    data["templates"] = [t for t in data["templates"] if t["name"] != name]
    data["templates"].append(entry)
    data["templates"].sort(key=lambda t: t["name"].lower())
    save(data)


def delete_template(name: str):
    from . import team
    data = load()
    data["templates"] = [t for t in data["templates"] if t["name"] != name]
    save(data)
    if team.folder():
        sh = _shared()
        if any(t["name"] == name for t in sh["templates"]):
            sh["templates"] = [t for t in sh["templates"] if t["name"] != name]
            team.write_shared("builder.json", sh)


def template_lines(t: dict) -> list[str]:
    """Commands in a template, without blank lines or # comments."""
    return [ln.strip() for ln in t.get("commands", [])
            if ln.strip() and not ln.strip().startswith("#")]
