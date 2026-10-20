"""Remember which serial number and asset ID go with each Chromebook device ID, so the
activity log can say “5CD0372JK1 (asset HS2074)” instead of a 36-character ID.

Filled whenever GAMbit lists Chromebooks (the window and background tasks), kept in
GAMbit's app-data folder.
"""

from __future__ import annotations

import json
import os
import threading

_lock = threading.Lock()
_cache: dict | None = None
LIMIT = 60000


def _path() -> str:
    from .activity import local_dir
    return os.path.join(local_dir(), "device-names.json")


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            with open(_path(), encoding="utf-8") as fh:
                _cache = json.load(fh)
            if not isinstance(_cache, dict):
                _cache = {}
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _col(row: dict, *names) -> str:
    low = {(k or "").lower(): v for k, v in row.items()}
    for n in names:
        if low.get(n):
            return str(low[n]).strip()
    return ""


def remember(rows: list[dict]):
    """Rows from any `print cros` (needs deviceId plus a serial or asset ID)."""
    added = 0
    with _lock:
        c = _load()
        for r in rows or []:
            did = _col(r, "deviceid")
            if not did:
                continue
            ent = {"serial": _col(r, "serialnumber", "serial"),
                   "asset": _col(r, "annotatedassetid", "asset")}
            ent = {k: v for k, v in ent.items() if v}
            if ent and c.get(did) != {**c.get(did, {}), **ent}:
                c[did] = {**c.get(did, {}), **ent}
                added += 1
        if added:
            if len(c) > LIMIT:
                for k in list(c)[: len(c) - LIMIT]:
                    c.pop(k, None)
            try:
                os.makedirs(os.path.dirname(_path()), exist_ok=True)
                tmp = _path() + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(c, fh)
                os.replace(tmp, _path())
            except OSError:
                pass


def reload():
    global _cache
    with _lock:
        _cache = None


def lookup(device_id: str) -> dict:
    return dict(_load().get(device_id, {}))


def label(device_id: str) -> str:
    """'5CD0372JK1 (asset HS2074)', or the ID itself when it isn't known yet."""
    e = lookup(device_id)
    if e.get("serial") and e.get("asset"):
        return f"{e['serial']} (asset {e['asset']})"
    return e.get("serial") or (f"asset {e['asset']}" if e.get("asset") else device_id)


def serial_or_id(device_id: str) -> str:
    return lookup(device_id).get("serial") or device_id
