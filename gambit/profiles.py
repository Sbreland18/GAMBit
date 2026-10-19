"""Domain profiles: switch GAMbit between several GAM configurations.

A profile is a GAM config folder (GAMCFGDIR, each with its own sign-in) and,
optionally, a section name from gam.cfg (run as `gam select <section> …`).
"""

from __future__ import annotations

import json
import re

from .settings import settings


def _all() -> list[dict]:
    try:
        data = json.loads(settings.get("profiles", "[]") or "[]")
    except ValueError:
        data = []
    if not data:
        data = [{"name": "Default", "cfg_dir": settings.gam_cfg_dir,
                 "section": settings.get("profile/section", "") or ""}]
        settings.set("profiles", json.dumps(data))
    return data


def profiles() -> list[dict]:
    return _all()


def current_name() -> str:
    names = [p["name"] for p in _all()]
    cur = settings.get("profile/current", "") or ""
    return cur if cur in names else names[0]


def current() -> dict:
    return next(p for p in _all() if p["name"] == current_name())


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower() or "default"


def save_profile(name: str, cfg_dir: str, section: str = ""):
    data = [p for p in _all() if p["name"] != name]
    data.append({"name": name, "cfg_dir": cfg_dir, "section": section})
    data.sort(key=lambda p: p["name"].lower())
    settings.set("profiles", json.dumps(data))


def remove_profile(name: str):
    data = [p for p in _all() if p["name"] != name]
    settings.set("profiles", json.dumps(data))
    if current_name() == name and data:
        switch(data[0]["name"])


def switch(name: str):
    p = next((x for x in _all() if x["name"] == name), None)
    if not p:
        return
    settings.set("profile/current", name)
    settings.gam_cfg_dir = p.get("cfg_dir", "")
    settings.set("profile/section", p.get("section", ""))


def sync_current_from_settings():
    """Keep the active profile in step when the GAM config folder is edited elsewhere."""
    p = current()
    if p.get("cfg_dir", "") != settings.gam_cfg_dir:
        save_profile(p["name"], settings.gam_cfg_dir, p.get("section", ""))
