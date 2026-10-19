"""Drive extras: collect orphaned files, and apply Drive labels in bulk."""

from __future__ import annotations

import json
import re


def entity(who: str, ou: str = "") -> list[str]:
    return ["ou_and_children", ou] if ou else ["user", who]


def orphans_args(ent: list[str], folder: str = "Orphaned files", preview: bool = True,
                 shortcuts: bool = False) -> list[str]:
    a = [*ent, "collect", "orphans", "targetuserfoldername", folder]
    if shortcuts:
        a += ["useshortcuts", "true"]
    if preview:
        a.append("preview")
    return a


# --------------------------------------------------------------- labels ---
LABELS_ARGS = ["print", "classificationlabels", "formatjson"]


def parse_labels(rows: list[dict]) -> list[dict]:
    """→ [{id, title, fields: [{id, name, kind, choices: [(id, name)]}]}]"""
    out = []
    for r in rows:
        try:
            j = json.loads(r.get("JSON") or "{}")
        except ValueError:
            continue
        lid = j.get("id") or (j.get("name", "").split("/")[-1].split("@")[0])
        state = (j.get("lifecycle", {}) or {}).get("state", "")
        if state and state not in ("PUBLISHED",):
            continue
        fields = []
        for f in j.get("fields", []) or []:
            kind = next((k for k in ("selectionOptions", "textOptions", "integerOptions",
                                     "dateOptions", "userOptions") if k in f), "")
            choices = [(c.get("id", ""), (c.get("properties", {}) or {}).get("displayName", ""))
                       for c in (f.get("selectionOptions", {}) or {}).get("choices", []) or []]
            fields.append({"id": f.get("id", ""), "name": (f.get("properties", {}) or {})
                           .get("displayName", f.get("id", "")),
                           "kind": kind.replace("Options", ""), "choices": choices})
        out.append({"id": lid, "title": (j.get("properties", {}) or {}).get("title", lid),
                    "fields": fields})
    return out


def file_ids(text: str) -> list[str]:
    ids = []
    for part in re.split(r"[\s,]+", text or ""):
        m = re.search(r"/(?:d|folders)/([A-Za-z0-9_-]{10,})", part) or \
            re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", part)
        v = m.group(1) if m else (part if re.fullmatch(r"[A-Za-z0-9_-]{10,}", part) else "")
        if v and v not in ids:
            ids.append(v)
    return ids


def label_args(owner: str, ids: list[str], label: str, field: str = "", choice: str = "",
               folder: bool = False, remove: bool = False) -> list[str]:
    target = ["query", f"'{ids[0]}' in parents and trashed=false"] if folder else \
        ["ids", ",".join(ids)]
    a = ["user", owner, "process", "filedrivelabels", *target]
    if remove:
        return a + ["deletelabel", label]
    a += ["addlabel", label]
    if field and choice:
        a += ["addlabelfield", label, field, "selection", choice]
    return a
