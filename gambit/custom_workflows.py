"""Your own workflows: a name, a few fill-in fields and a list of GAM steps that use them.

Stored in <team>/templates/custom_workflows.json (or this PC's settings without a team
folder), so the whole team shares them.

Step format (one per line in the editor):   Label | gam command with {field} placeholders
Field format:                               key = Label shown to the person [= default]
"""

from __future__ import annotations

import json
import re

from .settings import settings

EXAMPLES = [
    {"name": "New substitute teacher",
     "description": "Creates a sub account in /Staff/Substitutes, adds it to the subs group and "
                    "emails the office.",
     "fields": [{"key": "first", "label": "First name", "default": ""},
                {"key": "last", "label": "Last name", "default": ""},
                {"key": "email", "label": "New email", "default": ""},
                {"key": "office", "label": "Office to tell", "default": ""}],
     "steps": [{"label": "Create the account",
                "command": "create user {email} firstname {first} lastname {last} "
                           "password {password} changepassword on ou /Staff/Substitutes"},
               {"label": "Add to the substitutes group",
                "command": "update group substitutes add member user {email}"},
               {"label": "Tell the office",
                "command": "sendemail to {office} subject \"New sub account: {email}\" "
                           "message \"{first} {last} can sign in as {email}. Temporary "
                           "password: {password}\""}]},
    {"name": "Student device swap",
     "description": "Moves a student's old Chromebook to Repairs and assigns them a new one.",
     "fields": [{"key": "student", "label": "Student email", "default": ""},
                {"key": "old", "label": "Old serial", "default": ""},
                {"key": "new", "label": "New serial", "default": ""}],
     "steps": [{"label": "Old device to Repairs",
                "command": "cros_sn {old} update ou /Chromebooks/Repairs user \"\" "
                           "notes \"Swapped out for {student}\""},
               {"label": "Assign the new device",
                "command": "cros_sn {new} update user {student}"}]},
]

BUILTIN_VALUES = ("password", "today")


def _load_raw() -> list[dict]:
    from . import team
    if team.folder():
        data = team.read_shared("custom_workflows.json")
        if data:
            return data.get("workflows", [])
    try:
        return json.loads(settings.get("workflows/custom", "") or "[]")
    except ValueError:
        return []


def load() -> list[dict]:
    wf = _load_raw()
    return wf if wf else [dict(e, example=True) for e in EXAMPLES]


def save(workflows: list[dict]):
    from . import team
    clean = [{k: v for k, v in w.items() if k != "example"} for w in workflows]
    if team.folder():
        team.write_shared("custom_workflows.json", {"workflows": clean})
    settings.set("workflows/custom", json.dumps(clean))


def placeholders(wf: dict) -> list[str]:
    found = []
    for st in wf.get("steps", []):
        for m in re.findall(r"\{(\w+)\}", st.get("command", "")):
            if m not in found:
                found.append(m)
    return found


def problems(wf: dict) -> list[str]:
    out = []
    if not wf.get("name", "").strip():
        out.append("It needs a name.")
    if not wf.get("steps"):
        out.append("Add at least one step.")
    keys = {f["key"] for f in wf.get("fields", [])}
    for p in placeholders(wf):
        if p not in keys and p not in BUILTIN_VALUES:
            out.append(f"{{{p}}} is used in a step but isn't a field.")
    from .gam_runner import split_command
    for st in wf.get("steps", []):
        try:
            if not split_command(st.get("command", "")):
                out.append(f"Step “{st.get('label', '')}” has no command.")
        except ValueError as exc:
            out.append(f"Step “{st.get('label', '')}”: {exc}")
    return out


def build(wf: dict, values: dict, password: str = "") -> list[tuple[str, list[str]]]:
    """Fill the fields in and return (label, gam args) per step. Values are substituted into
    already-split arguments, so spaces and quotes in what people type are safe."""
    import datetime
    from .gam_runner import split_command
    vals = {**{k: str(v) for k, v in values.items()},
            "password": password, "today": datetime.date.today().isoformat()}
    missing = [f["label"] for f in wf.get("fields", []) if not vals.get(f["key"], "").strip()
               and f["key"] in placeholders(wf)]
    if missing:
        raise ValueError("Fill in: " + ", ".join(missing))
    out = []
    for st in wf["steps"]:
        args = [re.sub(r"\{(\w+)\}", lambda m: vals.get(m.group(1), m.group(0)), a)
                for a in split_command(st["command"])]
        label = re.sub(r"\{(\w+)\}", lambda m: vals.get(m.group(1), m.group(0)), st["label"])
        out.append((label, args))
    return out


def to_text(wf: dict) -> tuple[str, str]:
    fields = "\n".join(f"{f['key']} = {f['label']}" + (f" = {f['default']}" if f.get("default")
                                                        else "") for f in wf.get("fields", []))
    steps = "\n".join(f"{s['label']} | {s['command']}" for s in wf.get("steps", []))
    return fields, steps


def from_text(name: str, description: str, fields: str, steps: str) -> dict:
    fl = []
    for ln in fields.splitlines():
        parts = [p.strip() for p in ln.split("=")]
        if parts and re.fullmatch(r"\w+", parts[0] or ""):
            fl.append({"key": parts[0], "label": parts[1] if len(parts) > 1 and parts[1]
                       else parts[0], "default": parts[2] if len(parts) > 2 else ""})
    st = []
    for ln in steps.splitlines():
        if "|" in ln:
            label, cmd = ln.split("|", 1)
            cmd = cmd.strip()
            if cmd.lower().startswith("gam "):
                cmd = cmd[4:]
            if cmd:
                st.append({"label": label.strip() or cmd[:40], "command": cmd})
        elif ln.strip():
            cmd = ln.strip()[4:] if ln.strip().lower().startswith("gam ") else ln.strip()
            st.append({"label": cmd[:50], "command": cmd})
    return {"name": name.strip(), "description": description.strip(), "fields": fl, "steps": st}
