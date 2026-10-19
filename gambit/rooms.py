"""Import rooms and resources (bookable calendars) from a spreadsheet.

Columns (any order, names are matched loosely):
    Building, Floor, Name, ID (optional), Capacity, Kind (room / conference room / other),
    Type (e.g. "Chromebook cart"), Description

Buildings that don't exist yet are created first (with every floor the sheet uses),
then each resource is created – or updated when its details differ from Google.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

COLUMNS = {
    "building": ["building", "buildingname", "school", "site", "campus"],
    "floor": ["floor", "floorname", "level"],
    "name": ["name", "resourcename", "room", "roomname"],
    "id": ["id", "resourceid", "roomid", "code"],
    "capacity": ["capacity", "seats", "size"],
    "kind": ["kind", "category", "resourcecategory"],
    "type": ["type", "resourcetype"],
    "description": ["description", "notes", "resourcedescription"],
}
KINDS = {"conference": "CONFERENCE_ROOM", "meeting": "CONFERENCE_ROOM",
         "room": "OTHER", "other": "OTHER", "equipment": "OTHER", "cart": "OTHER",
         "category_unknown": "CATEGORY_UNKNOWN"}


def _n(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def slug(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")[:60]


def kind(value: str) -> str:
    v = (value or "").lower()
    for k, out in KINDS.items():
        if k in v:
            return out
    return "CONFERENCE_ROOM" if "conference" in v else ("OTHER" if v else "CONFERENCE_ROOM")


def gam_category(cat: str) -> str:
    return {"CONFERENCE_ROOM": "conference_room", "OTHER": "other"}.get(cat, "unknown")


@dataclass
class Room:
    building: str
    floor: str
    name: str
    rid: str
    capacity: str = ""
    category: str = "CONFERENCE_ROOM"
    rtype: str = ""
    description: str = ""


@dataclass
class Action:
    action: str                 # building, create, update, same, problem
    target: str
    details: str
    commands: list[list[str]] = field(default_factory=list)


def read_rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def mapping(headers: list[str]) -> dict[str, str]:
    by_norm = {_n(h): h for h in headers}
    out = {}
    for key, cands in COLUMNS.items():
        for c in cands:
            if c in by_norm:
                out[key] = by_norm[c]
                break
    return out


def rooms_from_rows(rows: list[dict]) -> list[Room]:
    if not rows:
        return []
    heads: list[str] = []
    for r in rows:
        heads += [k for k in r if k not in heads]
    m = mapping(heads)
    out = []
    for r in rows:
        def g(k):
            return (r.get(m[k]) or "").strip() if k in m else ""
        name = g("name")
        if not name:
            continue
        b = g("building")
        rid = g("id") or slug(f"{b}-{name}")
        cap = re.sub(r"[^0-9]", "", g("capacity"))
        out.append(Room(b, g("floor"), name, rid, cap, kind(g("kind")), g("type"),
                        g("description")))
    return out


def _low(row: dict) -> dict:
    return {(k or "").lower(): (v or "") for k, v in row.items()}


def plan(rooms: list[Room], buildings: list[dict], resources: list[dict]) -> list[Action]:
    """buildings / resources: rows from `gam print buildings` / `gam print resources`."""
    have_b, have_floors = {}, {}
    for b in map(_low, buildings):
        bid = b.get("buildingid", "")
        have_b[_n(b.get("buildingname", ""))] = bid
        have_b[_n(bid)] = bid
        fl = b.get("floornames", "") or ",".join(v for k, v in b.items()
                                                 if k.startswith("floornames.") and v)
        have_floors[bid] = [f.strip() for f in fl.split(",") if f.strip()]
    have_r = {}
    for r in map(_low, resources):
        have_r[r.get("resourceid", "").lower()] = r
    out: list[Action] = []
    # buildings first
    floors: dict[str, list[str]] = {}
    for rm in rooms:
        if rm.building:
            fl = floors.setdefault(rm.building, [])
            if rm.floor and rm.floor not in fl:
                fl.append(rm.floor)
    building_id = {}
    for b, fl in floors.items():
        if _n(b) in have_b:
            bid = building_id[b] = have_b[_n(b)]
            missing = [f for f in fl if f not in have_floors.get(bid, [])]
            if missing:
                allf = have_floors.get(bid, []) + missing
                out.append(Action("building", b, f"Add floor(s) {', '.join(missing)}",
                                  [["update", "building", bid, "floors", ",".join(allf)]]))
            continue
        bid = slug(b)
        building_id[b] = bid
        cmd = ["create", "building", b, "id", bid]
        if fl:
            cmd += ["floors", ",".join(fl)]
        out.append(Action("building", b, f"New building (id {bid})" +
                          (f", floors {', '.join(fl)}" if fl else ""), [cmd]))
    seen = set()
    for rm in rooms:
        if rm.rid.lower() in seen:
            out.append(Action("problem", rm.rid, f"ID used twice in the sheet ({rm.name})"))
            continue
        seen.add(rm.rid.lower())
        attrs = []
        if rm.building:
            attrs += ["buildingid", building_id.get(rm.building, slug(rm.building))]
            if rm.floor:
                attrs += ["floor", rm.floor]
        elif rm.floor:
            out.append(Action("problem", rm.rid, "A floor needs a building."))
            continue
        if rm.capacity:
            attrs += ["capacity", rm.capacity]
        attrs += ["category", gam_category(rm.category)]
        if rm.rtype:
            attrs += ["type", rm.rtype]
        if rm.description:
            attrs += ["description", rm.description]
        cur = have_r.get(rm.rid.lower())
        if cur is None:
            out.append(Action("create", rm.rid, f"New: {rm.name}" +
                              (f" in {rm.building}" if rm.building else "") +
                              (f", floor {rm.floor}" if rm.floor else "") +
                              (f", {rm.capacity} seats" if rm.capacity else ""),
                              [["create", "resource", rm.rid, rm.name, *attrs]]))
            continue
        diffs = []
        if cur.get("resourcename", "") != rm.name:
            diffs.append(f"name “{cur.get('resourcename', '')}” → “{rm.name}”")
        if rm.capacity and cur.get("capacity", "") != rm.capacity:
            diffs.append(f"capacity {cur.get('capacity') or '–'} → {rm.capacity}")
        if rm.building and _n(cur.get("buildingid", "")) != _n(
                building_id.get(rm.building, "")):
            diffs.append(f"building → {rm.building}")
        if rm.floor and cur.get("floorname", "") != rm.floor:
            diffs.append(f"floor {cur.get('floorname') or '–'} → {rm.floor}")
        if rm.rtype and cur.get("resourcetype", "") != rm.rtype:
            diffs.append(f"type → {rm.rtype}")
        if rm.description and cur.get("resourcedescription", "") != rm.description:
            diffs.append("description")
        if diffs:
            out.append(Action("update", rm.rid, "; ".join(diffs),
                              [["update", "resource", rm.rid, "name", rm.name, *attrs]]))
        else:
            out.append(Action("same", rm.rid, f"{rm.name} – already up to date"))
    return out


TEMPLATE = ("Building,Floor,Name,ID,Capacity,Kind,Type,Description\n"
            "Lincoln Elementary,1,Library,,30,Conference room,,Main library\n"
            "Lincoln Elementary,2,Room 204,,28,Room,Classroom,\n"
            "High School,1,Chromebook Cart A,hs-cart-a,,Other,Chromebook cart,30 devices\n")
