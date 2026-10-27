"""GAM commands behind the newer pages: single sign-on by org unit, Windows/Mac/phones,
shared drives by school, Chat posts, staff calendar status, and the smaller extras."""

from __future__ import annotations

import datetime
import json
import re

# ============================================================ single sign-on ===
SSO_MODES = {"saml_sso": "Sign in with a SAML provider (ClassLink, Clever…)",
             "oidc_sso": "Sign in with an OIDC provider",
             "sso_off": "Google password (SSO off)",
             "domain_wide_saml_if_enabled": "Use the domain-wide setting"}


def sso_target(ou: str = "", group: str = "", rank: int = 1) -> list[str]:
    return ["group", group, "rank", str(rank)] if group else ["orgunit", ou]


def sso_mode_args(mode: str, profile: str = "", never_redirect: bool = False) -> list[str]:
    a = ["mode", mode]
    if mode in ("saml_sso", "oidc_sso"):
        if not profile:
            raise ValueError("Pick the SSO profile.")
        a += ["profile", profile]
    if never_redirect:
        a.append("neverredirect")
    return a


def sso_create(ou: str, mode: str, profile: str = "", group: str = "", rank: int = 1,
               never_redirect: bool = False) -> list[str]:
    return ["create", "inboundssoassignment"] + sso_target(ou, group, rank) + \
        sso_mode_args(mode, profile, never_redirect)


def sso_update(name: str, mode: str, profile: str = "", never_redirect: bool = False):
    return ["update", "inboundssoassignment", name] + sso_mode_args(mode, profile,
                                                                     never_redirect)


def sso_info(ou: str = "", group: str = "") -> list[str]:
    return ["info", "inboundssoassignment",
            f"group:{group}" if group else f"orgunit:{ou}", "formatjson"]


def sso_delete(ou: str = "", group: str = "", name: str = "") -> list[str]:
    sel = name or (f"group:{group}" if group else f"orgunit:{ou}")
    return ["delete", "inboundssoassignment", sel]


def assignment_name(info_out: str) -> str:
    """The assignment's name from `info inboundssoassignment … formatjson` output."""
    m = re.search(r"inboundSsoAssignments/[A-Za-z0-9_\-]+", info_out or "")
    if m:
        return m.group(0)
    try:
        return json.loads(info_out).get("name", "")
    except (ValueError, AttributeError):
        return ""


# ======================================================== Windows, Mac, phones ===
DEVICE_FIELDS = ("name,serialnumber,devicetype,model,manufacturer,osversion,ownertype,"
                 "lastsynctime,assettag,compromisedstate,encryptionstate,managementstate")
DEVICE_TYPES = {"": "All types", "windows": "Windows", "mac_os": "Mac", "ios": "iPhone / iPad",
                "android": "Android", "linux": "Linux", "chrome_os": "ChromeOS (endpoint)"}


def devices_args(kind: str = "", owner: str = "all", query: str = "") -> list[str]:
    a = ["print", "devices"]
    q = " ".join(x for x in (f"type:{kind}" if kind else "", query.strip()) if x)
    if q:
        a += ["query", q]
    a += ["fields", DEVICE_FIELDS, "userfields", "useremail,managementstate,lastsynctime,name"]
    if owner in ("company", "personal"):
        a.append(owner)
    return a + ["oneuserperrow"]


def device_action(action: str, name: str) -> list[str]:
    """action: wipe|cancelwipe|delete on a device (devices/<id>), or approve|block|wipe|
    cancelwipe|delete on a device user (devices/<id>/deviceUsers/<id>)."""
    if not name.startswith("devices/"):
        raise ValueError("Pick a device from the list.")
    who = "deviceuser" if "/deviceUsers/" in name else "device"
    if action == "delete":
        return ["delete", who, name, "doit"]
    if who == "device" and action in ("approve", "block"):
        raise ValueError("Approve and block apply to a person on a device.")
    return [action, who, name, "doit"]


def stale_devices(rows: list[dict], days: int, today: datetime.date | None = None):
    today = today or datetime.date.today()
    cut = (today - datetime.timedelta(days=days)).isoformat()
    out = []
    for r in rows:
        t = (r.get("lastSyncTime") or r.get("lastsynctime") or "")[:10]
        if t and t < cut:
            out.append(r)
    return out


# ================================================== shared drives by school ===
def ou_drives_args(ou: str) -> list[str]:
    return ["print", "oushareddrives", "ou", ou]


def no_manager_args(ou: str = "") -> list[str]:
    a = ["print", "shareddriveorganizers", "shownorganizerdrives", "only", "showorgunits",
         "true"]
    return a + (["orgunit", ou] if ou else [])


def outside_args(domain: str, ou: str = "") -> list[str]:
    a = ["print", "shareddriveacls"]
    if ou:
        a += ["orgunit", ou]
    return a + ["pm", "typelist", "user,group", "notdomainlist", domain, "em",
                "oneitemperrow"]


def anyone_link_args(ou: str = "") -> list[str]:
    a = ["print", "shareddriveacls"]
    if ou:
        a += ["orgunit", ou]
    return a + ["pm", "type", "anyone", "em", "oneitemperrow"]


def move_drive_args(admin: str, drive_id: str, ou: str) -> list[str]:
    return ["user", admin, "update", "shareddrive", drive_id, "adminaccess", "ou", ou]


def add_manager_args(admin: str, drive_id: str, who: str) -> list[str]:
    return ["user", admin, "add", "drivefileacl", drive_id, "user", who, "role",
            "organizer", "asadmin"]


# ================================================================== Chat ===
def spaces_args(user: str) -> list[str]:
    return ["user", user, "print", "chatspaces", "types", "space"]


def post_args(user: str, space: str, text: str) -> list[str]:
    sp = space if space.startswith("spaces/") else f"spaces/{space}"
    if not text.strip():
        raise ValueError("Type the message.")
    return ["user", user, "create", "chatmessage", sp, "text", text]


def messages_args(user: str, space: str, start: str, end: str) -> list[str]:
    sp = space if space.startswith("spaces/") else f"spaces/{space}"
    return ["user", user, "print", "chatmessages", sp, "range", start, end,
            "fields", "name,createtime,sender,text,thread"]


# ====================================================== calendar status ===
STATUS = {"outofoffice": "Out of office", "focustime": "Focus time",
          "workinglocation": "Working location"}


def _when(day1: str, day2: str, start: str = "", end: str = "") -> list[str]:
    if start and end:
        return ["timerange", f"{day1}T{start}:00", f"{day1}T{end}:00"]
    return ["range", day1, day2 or day1]


def status_create(entity: list[str], kind: str, day1: str, day2: str, start: str = "",
                  end: str = "", message: str = "", summary: str = "", decline: str = "new",
                  where: str = "home", where_text: str = "") -> list[str]:
    a = list(entity) + ["create", kind]
    if kind == "workinglocation":
        a += ["home"] if where == "home" else (["office", where_text or "Office"]
                                              if where == "office" else
                                              ["custom", where_text or "Elsewhere"])
    else:
        a += ["declinemode", decline]
        if message:
            a += ["declinemessage", message]
        if summary:
            a += ["summary", summary]
        if kind == "focustime":
            a += ["chatstatus", "donotdisturb"]
    return a + _when(day1, day2, start, end) + ["noreminders"]


def status_print(entity: list[str], kind: str, day1: str, day2: str) -> list[str]:
    return list(entity) + ["print", kind, "range", day1, day2 or day1, "showdayofweek"]


def status_delete(entity: list[str], kind: str, day1: str, day2: str) -> list[str]:
    return list(entity) + ["delete", kind, "range", day1, day2 or day1]


# =========================================================== small extras ===
def domain_alias_create(alias: str, domain: str) -> list[str]:
    return ["create", "domainalias", alias.strip().lower(), domain.strip().lower()]


def contact_delegate(user: str, delegate: str, add: bool = True) -> list[str]:
    return ["user", user, "create" if add else "delete", "contactdelegate", delegate]


def tasks_args(user: str) -> list[str]:
    return ["user", user, "print", "tasks"]


def tasklists_args(user: str) -> list[str]:
    return ["user", user, "print", "tasklists"]


PROFILE_FIELDS = ("profilepermanentid,displayname,useremail,browserversion,osplatformtype,"
                  "lastactivitytime,extensioncount,policycount,name")


def profiles_args(stale_days: int = 0) -> list[str]:
    a = ["print", "chromeprofiles"]
    if stale_days:
        a += ["filter", f"lastActivityTime<{_iso_days_ago(stale_days)}"]
    return a + ["fields", PROFILE_FIELDS]


def _iso_days_ago(days: int) -> str:
    d = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def token_create(ou: str, days: int = 0) -> list[str]:
    a = ["create", "browsertoken"]
    if ou:
        a += ["ou", ou]
    if days:
        a += ["expire", (datetime.date.today() + datetime.timedelta(days=days)).isoformat()]
    return a
