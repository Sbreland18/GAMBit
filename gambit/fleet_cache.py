"""One Chromebook list for the whole Chromebook fleet page.

“Load Chromebooks” at the top of the page asks Google once for every field the fleet tabs
use. After that, any tab that wants the whole fleet (Assigned users, Assignment sync,
Redistribution, Asset register, Withdrawn students' devices…) gets the rows from here
instantly instead of asking Google again. Any change GAMbit makes to Chromebooks clears the
list, so nothing works from stale data.
"""

from __future__ import annotations

import threading
import time

FIELDS = ("deviceid,serialnumber,annotatedassetid,annotatedlocation,annotateduser,"
          "orgunitpath,status,lastsync,autoupdateexpiration,model,notes,osversion,"
          "recentusers,activetimeranges")
ARGS = ["print", "cros", "fields", FIELDS, "reverselists", "activetimeranges",
        "listlimit", "1"]
MAX_AGE = 60 * 60          # an hour; “Load Chromebooks” again for fresher data

_lock = threading.Lock()
_rows: list[dict] = []
_at = 0.0
_listeners: list = []


def store(rows: list[dict]):
    global _rows, _at
    with _lock:
        _rows, _at = list(rows), time.time()
    try:
        from . import device_names
        device_names.remember(rows)
    except Exception:  # noqa: BLE001
        pass


def clear():
    global _rows, _at
    with _lock:
        _rows, _at = [], 0.0


def loaded_at() -> float:
    return _at if _rows and time.time() - _at < MAX_AGE else 0.0


def all_rows() -> list[dict]:
    with _lock:
        return list(_rows) if _rows and time.time() - _at < MAX_AGE else []


def _wanted(args: list[str]) -> set[str] | None:
    """The fields a whole-fleet “print cros” asks for, or None when it asks for something
    narrower (a query, an org unit, a few serials) or something the list doesn't have."""
    a = [str(x) for x in args]
    if a[:2] != ["print", "cros"]:
        return None
    rest, fields = a[2:], set()
    i = 0
    while i < len(rest):
        tok = rest[i].lower()
        if tok == "fields" and i + 1 < len(rest):
            fields |= {f.strip().lower() for f in rest[i + 1].split(",") if f.strip()}
            i += 2
        elif tok == "listlimit" and i + 1 < len(rest) and rest[i + 1] == "1":
            i += 2
        elif tok == "reverselists" and i + 1 < len(rest) and \
                rest[i + 1].lower() == "activetimeranges":
            i += 2
        else:
            return None            # query, cros_ou, select, orderby, allfields, …
    have = {f.lower() for f in FIELDS.split(",")}
    return fields if fields and fields <= have else None


def get(args: list[str]) -> list[dict] | None:
    """Cached rows for a whole-fleet read, trimmed to the fields it asked for."""
    want = _wanted(args)
    rows = all_rows()
    if want is None or not rows:
        return None
    keep = want | {"deviceid"}

    def ok(k: str) -> bool:
        base = (k or "").split(".")[0].lower()
        return base in keep or base.replace("annotated", "") in keep
    return [{k: v for k, v in r.items() if ok(k)} for r in rows]


def changed(cmd: str):
    """Called when GAMbit runs a command: a Chromebook change means the list is stale."""
    c = " " + (cmd or "").lower() + " "
    if any(w in c for w in (" cros ", " cros_sn ", " cros_ou ", " cros_ou_and_children ",
                            " update cros ")) and any(
            w in c for w in (" update ", " action ", " issuecommand ", " delete ")):
        clear()
