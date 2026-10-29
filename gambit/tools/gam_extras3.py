"""Round 15 GAM commands: old Chrome profile clean-up, room features, working location,
shared-drive organizers, mailbox statistics, Google Tasks for leavers, writing Sheet ranges
and Drive label permissions."""

from __future__ import annotations

import datetime
import json
import re


def _low(r: dict) -> dict:
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _int(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


# ===================================================== old Chrome profiles ===
PROFILES_ARGS = ["print", "chromeprofiles", "fields",
                 "name,useremail,displayname,osplatformtype,lastactivitytime,browserversion"]


def stale_profiles(rows: list[dict], days: int, users: list[dict] | None = None,
                   today: datetime.date | None = None) -> list[dict]:
    today = today or datetime.date.today()
    cut = (today - datetime.timedelta(days=days)).isoformat()
    gone = {u["email"].lower() for u in users or [] if u.get("suspended")}
    out = []
    for r in rows:
        low = _low(r)
        name = low.get("name", "")
        last = low.get("lastactivitytime", "")[:10]
        who = low.get("useremail", "").lower()
        why = ""
        if who and who in gone:
            why = "account suspended / left"
        elif not last or last < cut:
            why = f"not used since {last or 'ever'}"
        if name and why:
            out.append({"Person": who, "Computer": low.get("displayname", ""),
                        "OS": low.get("osplatformtype", ""), "Last used": last or "never",
                        "Why": why, "name": name})
    return sorted(out, key=lambda x: x["Last used"])


def delete_profile_args(name: str) -> list[str]:
    return ["delete", "chromeprofile", name]


# ============================================================= room features ===
FEATURES_ARGS = ["print", "features"]


def features(rows: list[dict]) -> list[str]:
    return sorted({_low(r).get("name", "") for r in rows} - {""}, key=str.lower)


def feature_create_args(name: str) -> list[str]:
    return ["create", "feature", "name", name]


def feature_delete_args(name: str) -> list[str]:
    return ["delete", "feature", name]


def feature_rename_args(old: str, new: str) -> list[str]:
    return ["update", "feature", old, "name", new]


def resource_features_args(resource_id: str, names: list[str]) -> list[str]:
    return ["update", "resource", resource_id, "addfeatures", ",".join(names)]


# ========================================================== working location ===
def working_location_args(user: str, building: str, start: str, weeks: int,
                          building_id: str = "") -> list[str]:
    """Every week on `start`'s weekday for `weeks` weeks, at this building."""
    a = ["user", user, "create", "workinglocation", "office", building]
    if building_id:
        a += ["buildingid", building_id]
    return a + ["weekly", start, str(int(weeks))]


def schedule_commands(user: str, plan: dict[str, str], start: datetime.date, weeks: int,
                      buildings: dict[str, str] | None = None) -> list[list[str]]:
    """plan = {"Mon": "Lincoln", "Tue": "Grant", …} → one command per weekday."""
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    out = []
    for i, d in enumerate(days):
        where = (plan.get(d) or "").strip()
        if not where:
            continue
        first = start + datetime.timedelta(days=(i - start.weekday()) % 7)
        out.append(working_location_args(user, where, first.isoformat(), weeks,
                                         (buildings or {}).get(where, "")))
    return out


# ====================================================== shared drive organizers ===
def organizers_args(ou: str = "") -> list[str]:
    a = ["print", "shareddriveorganizers", "oneorganizer", "false", "showorgunits", "true"]
    return a + (["orgunit", ou] if ou and ou != "/" else [])


def organizers(rows: list[dict], gone: set[str]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        orgs = [o for o in re.split(r"[\s,]+", low.get("organizers", "")) if o]
        active = [o for o in orgs if o.lower() not in gone]
        out.append({"Shared drive": low.get("name", ""), "Org unit": low.get("orgunit", ""),
                    "Managers": ", ".join(orgs), "Active managers": len(active),
                    "Created": low.get("createdtime", "")[:10], "id": low.get("id", "")})
    return sorted(out, key=lambda x: (x["Active managers"], x["Shared drive"].lower()))


# ========================================================= mailbox statistics ===
def gmailprofile_args(users: list[str]) -> list[str]:
    return ["users", ",".join(users), "print", "gmailprofile"]


def mailbox_stats(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        out.append({"Person": low.get("emailaddress", ""),
                    "Messages": _int(low.get("messagestotal")),
                    "Threads": _int(low.get("threadstotal"))})
    return sorted(out, key=lambda x: -x["Messages"])


# ================================================================ Google Tasks ===
def tasks_args(user: str) -> list[str]:
    return ["user", user, "print", "tasks", "showcompleted", "false"]


def tasks(rows: list[dict]) -> list[dict]:
    return [{"Task": _low(r).get("title", ""), "Due": _low(r).get("due", "")[:10],
             "Status": _low(r).get("status", "")} for r in rows if _low(r).get("title")]


# ================================================================ Sheet ranges ===
def sheetrange_args(user: str, file_id: str, rng: str, values: list[list]) -> list[str]:
    from ..csv_safe import cell
    js = json.dumps({"range": rng, "values": [[("" if v is None else cell(v)) for v in row]
                                              for row in values],
                     "majorDimension": "ROWS"})
    return ["user", user, "update", "sheetrange", file_id, "json", js, "userentered"]


def read_range_args(user: str, file_id: str, rng: str) -> list[str]:
    return ["user", user, "print", "sheetrange", file_id, "range", rng]


def pad(rows: list[list], min_rows: int = 0, width: int | None = None) -> list[list]:
    """Blank out leftovers from a longer previous write."""
    width = width or max((len(r) for r in rows), default=1)
    out = [list(r) + [""] * (width - len(r)) for r in rows]
    while len(out) < min_rows:
        out.append([""] * width)
    return out


# ======================================================= Drive label permissions ===
def label_name(label_id: str) -> str:
    return label_id if label_id.startswith("labels/") else f"labels/{label_id}"


def label_perms_args(label_id: str) -> list[str]:
    return ["print", "classificationlabelpermissions", label_name(label_id), "asadmin"]


def label_perm_add_args(label_id: str, who: str, role: str = "applier",
                        kind: str = "group") -> list[str]:
    return ["create", "classificationlabelpermission", label_name(label_id), kind, who,
            "role", role, "asadmin"]


def label_perm_remove_args(label_id: str, who: str, kind: str = "group") -> list[str]:
    return ["delete", "classificationlabelpermission", label_name(label_id), kind, who,
            "asadmin"]


RESOURCES_ARGS = ["print", "resources", "fields",
                  "resourceid,resourcename,buildingid,capacity,featureinstances"]


def resource_remove_features_args(resource_id: str, names: list[str]) -> list[str]:
    return ["update", "resource", resource_id, "removefeatures", ",".join(names)]


def resources(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        feats = sorted({v for k, v in low.items() if "feature" in k and k.endswith("name") and v})
        out.append({"Room": low.get("resourcename", ""), "Building": low.get("buildingid", ""),
                    "Capacity": low.get("capacity", ""), "Features": ", ".join(feats),
                    "id": low.get("resourceid", "")})
    return sorted(out, key=lambda x: (x["Building"], x["Room"]))
