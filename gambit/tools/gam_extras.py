"""GAM commands GAMbit didn't use before Round 13, with small parsers so the screens stay
simple and the logic is testable:

* personal Google accounts that use a district address (`print userinvitations`)
* calendar sharing (`calendars … print acls`) and out-of-office events
* Classroom invitations nobody accepted, and topics
* Chromebook active time (`print crosactivity`), Chrome browser releases
  (`print chromehistory`), managed-profile commands and policy images
* Drive sharing counts, file activity, empty folders and shared-drive org units/themes
* app passwords, GAMbit's own service-account key, Alert Center feedback
* group trees ("why do they get this email?") and user counts per org unit"""

from __future__ import annotations

import datetime
import re


def _low(r: dict) -> dict:
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _int(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def _chunks(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


# ============================================================ personal accounts ===
INVITES_ARGS = ["print", "userinvitations"]
STATE_LABEL = {"NOT_YET_SENT": "Not invited yet", "INVITED": "Invited – waiting",
               "ACCEPTED": "Accepted", "DECLINED": "Declined"}


def invitations(rows: list[dict]) -> list[dict]:
    """`print userinvitations` → [{email, state, label, updated, sent}]"""
    out = []
    for r in rows:
        low = _low(r)
        e = low.get("email", "").lower()
        if not e:
            continue
        st = low.get("state", "").upper()
        out.append({"email": e, "state": st, "label": STATE_LABEL.get(st, st.title()),
                    "updated": low.get("updatetime", "")[:16].replace("T", " "),
                    "sent": _int(low.get("mailssentcount"))})
    order = {"NOT_YET_SENT": 0, "INVITED": 1, "DECLINED": 2, "ACCEPTED": 3}
    return sorted(out, key=lambda x: (order.get(x["state"], 9), x["email"]))


def invite_args(email: str) -> list[str]:
    return ["send", "userinvitation", email]


def cancel_invite_args(email: str) -> list[str]:
    return ["cancel", "userinvitation", email]


def isinvitable_args(emails: list[str]) -> list[str]:
    return ["users", ",".join(emails), "check", "isinvitable"]


# ================================================================== calendars ===
def cal_acl_args(calendars: list[str]) -> list[str]:
    return ["calendars", ",".join(calendars), "print", "acls"]


def cal_exposure(rows: list[dict], my_domains: set[str]) -> list[dict]:
    """ACL rows → the ones that share outside the district or publicly."""
    out = []
    for r in rows:
        low = _low(r)
        cal = low.get("calendarid", "") or low.get("calendar", "")
        role = low.get("role", "")
        st = low.get("scope.type", "").lower()
        sv = low.get("scope.value", "").lower()
        why = ""
        if st == "default" and role.lower() not in ("none", ""):
            why = "Public – anyone on the internet"
        elif st == "domain" and sv and sv not in my_domains:
            why = f"Another organization ({sv})"
        elif st in ("user", "group") and "@" in sv and sv.split("@")[-1] not in my_domains:
            why = f"Outside person ({sv})"
        if why:
            scope = "default" if st == "default" else (f"domain:{sv}" if st == "domain"
                                                      else sv)
            out.append({"Calendar": cal, "Shared with": why, "Can": _role(role),
                        "role": role, "scope": scope})
    return out


def _role(role: str) -> str:
    return {"freeBusyReader": "see free/busy", "reader": "see event details",
            "writer": "edit events", "owner": "manage sharing"}.get(role, role)


def cal_unshare_args(calendar: str, scope: str) -> list[str]:
    return ["calendars", calendar, "delete", "acls", scope]


def ooo_args(user: str, start: str, end: str, message: str = "",
             mode: str = "new") -> list[str]:
    a = ["user", user, "create", "outofoffice", "declinemode", mode]
    if message:
        a += ["declinemessage", message]
    return a + ["summary", "Out of office", "range", start, end, "noreminders"]


def ooo_print_args(user: str, start: str, end: str) -> list[str]:
    return ["user", user, "print", "outofoffice", "range", start, end]


def ooo_delete_args(user: str, start: str, end: str) -> list[str]:
    return ["user", user, "delete", "outofoffice", "range", start, end]


# ================================================================== classroom ===
CLASS_INVITES_ARGS = ["print", "classroominvitations", "states", "active"]


def class_invites(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        if not low.get("id") and not low.get("userid"):
            continue
        out.append({"Class": low.get("coursename", "") or low.get("courseid", ""),
                    "Person": low.get("useremail", "") or low.get("userid", ""),
                    "Role": low.get("role", "").title(), "course": low.get("courseid", ""),
                    "id": low.get("id", "")})
    return sorted(out, key=lambda x: (x["Class"], x["Role"], x["Person"]))


def invite_summary(invs: list[dict]) -> list[dict]:
    """Per class: how many students / teachers haven't accepted."""
    by = {}
    for i in invs:
        b = by.setdefault(i["course"], {"Class": i["Class"], "Students": 0, "Teachers": 0,
                                        "course": i["course"]})
        b["Teachers" if i["Role"] in ("Teacher", "Owner") else "Students"] += 1
    return sorted(by.values(), key=lambda b: -(b["Students"] + b["Teachers"]))


def delete_invite_args(course: str, inv_id: str) -> list[str]:
    return ["delete", "classroominvitation", "courses", course, "ids", inv_id]


def readd_args(inv: dict) -> list[str]:
    """Re-send by removing and adding again (Google sends a fresh invitation)."""
    role = "teacher" if inv["Role"] in ("Teacher", "Owner") else "student"
    return ["course", inv["course"], "add", role, inv["Person"]]


def topics_args(course: str) -> list[str]:
    return ["print", "course-topics", "course", course]


def topic_names(rows: list[dict]) -> list[str]:
    return [n for n in dict.fromkeys(_low(r).get("name", "").strip() for r in rows) if n]


def copy_topics_commands(names: list[str], targets: list[str],
                         existing: dict[str, set] | None = None) -> list[list[str]]:
    existing = existing or {}
    return [["course", t, "create", "topic", n] for t in targets for n in names
            if n.lower() not in {x.lower() for x in existing.get(t, set())}]


# ===================================================================== chrome ===
def activity_args(ou: str, days: int = 30, today: datetime.date | None = None) -> list[str]:
    start = ((today or datetime.date.today()) - datetime.timedelta(days=days)).isoformat()
    return ["print", "crosactivity", "cros_ou_and_children", ou or "/", "timeranges",
            "start", start]


def active_minutes(rows: list[dict]) -> dict[str, dict]:
    """crosactivity rows (one per active day) → serial → {minutes, days, last}"""
    out: dict[str, dict] = {}
    for r in rows:
        low = _low(r)
        sn = (low.get("serialnumber") or low.get("deviceid") or "").upper()
        if not sn:
            continue
        b = out.setdefault(sn, {"minutes": 0, "days": 0, "last": ""})
        mins = _int(low.get("activetimeranges.minutes"))
        if not mins and low.get("activetimeranges.duration"):
            mins = _int(low.get("activetimeranges.duration")) // 60000
        d = low.get("activetimeranges.date", "")
        if d or mins:
            b["minutes"] += mins
            b["days"] += 1
            b["last"] = max(b["last"], d)
    return out


PLATFORMS = {"WINDOWS": "win64", "WIN": "win64", "MAC": "mac", "MACOS": "mac", "LINUX": "linux"}


def versions_args(platform: str, channel: str = "stable") -> list[str]:
    return ["print", "chromehistory", "versions", "platform", platform, "channel", channel,
            "orderby", "version", "descending"]


def _major(v: str) -> int:
    m = re.match(r"\s*(\d+)", v or "")
    return int(m.group(1)) if m else 0


def latest_versions(rows: list[dict]) -> str:
    vs = [_low(r).get("version", "") for r in rows]
    vs = [v for v in vs if v]
    return max(vs, key=lambda v: tuple(int(x) for x in re.findall(r"\d+", v)), default="")


def behind(profiles: list[dict], latest: dict[str, str], allow: int = 1) -> list[dict]:
    """Managed Chrome profiles running a version more than `allow` major versions behind
    the newest stable release for their platform."""
    out = []
    for p in profiles:
        plat = PLATFORMS.get((p.get("os") or "").upper().split("_")[0], "")
        new = latest.get(plat, "")
        have = p.get("version", "")
        if new and have and _major(new) - _major(have) > allow:
            out.append({**p, "latest": new, "behind": _major(new) - _major(have)})
    return sorted(out, key=lambda x: -x["behind"])


def profile_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        out.append({"name": low.get("name", ""), "person": low.get("useremail", ""),
                    "computer": low.get("displayname", ""),
                    "os": low.get("osplatformtype", ""),
                    "version": low.get("browserversion", ""),
                    "last": low.get("lastactivitytime", "")[:10]})
    return [p for p in out if p["name"]]


def profile_command_args(names: list[str], cache: bool = True,
                         cookies: bool = False) -> list[str]:
    a = ["create", "chromeprofilecommand", ",".join(names)]
    if cache:
        a += ["clearcache", "true"]
    if cookies:
        a += ["clearcookies", "true"]
    return a


IMAGE_SCHEMAS = {
    "chrome.users.wallpaper": ("Student/staff wallpaper", "chrome.users.Wallpaper",
                               "wallpaperimage"),
    "chrome.users.avatar": ("Account picture", "chrome.users.Avatar", "useravatarimage"),
    "chrome.devices.signinwallpaperimage": ("Sign-in screen wallpaper",
                                            "chrome.devices.SignInWallpaperImage",
                                            "devicewallpaperimage"),
    "chrome.devices.managedguest.wallpaper": ("Managed guest wallpaper",
                                              "chrome.devices.managedguest.Wallpaper",
                                              "wallpaperimage"),
    "chrome.devices.managedguest.avatar": ("Managed guest picture",
                                           "chrome.devices.managedguest.Avatar",
                                           "useravatarimage"),
}


def image_upload_args(kind: str, path: str) -> list[str]:
    return ["create", "chromepolicyimage", kind, path]


def image_url(out: str) -> str:
    m = re.search(r"https://\S+", out or "")
    return m.group(0).rstrip(",)") if m else ""


def image_policy_args(kind: str, url: str, ou: str) -> list[str]:
    _label, schema, field = IMAGE_SCHEMAS[kind]
    return ["update", "chromepolicy", schema, field, url, "ou", ou]


# ====================================================================== drive ===
SHARE_COLS = ["anyone", "anyoneWithLink", "externalDomain", "externalDomainWithLink",
              "externalGroup", "externalUser"]


def sharecount_args(scope: list[str]) -> list[str]:
    return [*scope, "print", "filesharecounts", "excludetrashed", "internaldomains", "all"]


def sharecounts(rows: list[dict], users: list[dict] | None = None, root: str = "") -> list:
    """→ [{Owner, School, Public, With link, Outside people, Total shared, Files}]"""
    from ..parent_report import school_of
    ou = {u["email"].lower(): u.get("ou", "") for u in users or []}
    out = []
    for r in rows:
        own = (r.get("Owner") or r.get("User") or "").lower()
        if not own or own.startswith("total"):
            continue
        pub = _int(r.get("anyone"))
        link = _int(r.get("anyoneWithLink")) + _int(r.get("externalDomainWithLink"))
        outside = sum(_int(r.get(k)) for k in ("externalDomain", "externalGroup",
                                                 "externalUser"))
        out.append({"Owner": own, "School": school_of(ou.get(own, ""), root) if root else "",
                    "Public": pub, "Anyone with link": link, "Outside people": outside,
                    "Shared outside": _int(r.get("Shared External")),
                    "Files": _int(r.get("Total")), "score": pub * 5 + link * 2 + outside})
    return sorted(out, key=lambda x: -x["score"])


def share_by_school(counts: list[dict]) -> list[dict]:
    by = {}
    for c in counts:
        b = by.setdefault(c["School"] or "(other)", {"School": c["School"] or "(other)",
                                                     "People": 0, "Public": 0,
                                                     "Anyone with link": 0,
                                                     "Outside people": 0})
        b["People"] += 1
        for k in ("Public", "Anyone with link", "Outside people"):
            b[k] += c[k]
    return sorted(by.values(), key=lambda b: -(b["Public"] * 5 + b["Anyone with link"]))


def file_activity_args(owner: str, file_id: str = "", name: str = "",
                       days: int = 30) -> list[str]:
    sel = ["fileid", file_id] if file_id else ["drivefilename", name]
    return ["user", owner, "print", "driveactivity", *sel, "start", f"-{days}d"]


def file_activity(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        action = ""
        for k, v in low.items():
            if k.startswith("primaryactiondetail") and v:
                action = k.split(".", 1)[-1].split(".")[0] if "." in k else v
                break
        out.append({"When": low.get("eventtime", "")[:19].replace("T", " "),
                    "Who": low.get("user.emailaddress", "") or low.get("user.name", ""),
                    "What": action or low.get("action", ""),
                    "File": low.get("target.name", "")})
    return sorted(out, key=lambda x: x["When"], reverse=True)


def empty_folders_args(user: str) -> list[str]:
    return ["user", user, "print", "emptydrivefolders"]


def delete_empty_folders_args(user: str) -> list[str]:
    return ["user", user, "delete", "emptydrivefolders"]


SHARED_DRIVES_ARGS = ["print", "shareddrives", "fields", "id,name,createdtime,themeid"]


def shared_drives(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        if not low.get("id"):
            continue
        out.append({"Name": low.get("name", ""), "Org unit": low.get("orgunit", "") or "/",
                    "Created": low.get("createdtime", "")[:10], "Theme": low.get("themeid", ""),
                    "id": low["id"]})
    return sorted(out, key=lambda d: d["Name"].lower())


def drive_ou_args(drive_id: str, ou: str) -> list[str]:
    return ["update", "shareddrive", drive_id, "ou", ou]


def drive_theme_args(drive_id: str, theme: str) -> list[str]:
    return ["update", "shareddrive", drive_id, "theme", theme]


def drive_ou_suggestions(drives: list[dict], rules: list[tuple[str, str]]) -> list[dict]:
    """rules: [(name contains, org unit)] → drives that should move."""
    out = []
    for d in drives:
        for word, ou in rules:
            if word and word.lower() in d["Name"].lower() and d["Org unit"].rstrip("/") != \
                    ou.rstrip("/"):
                out.append({**d, "Move to": ou})
                break
    return out


# =================================================================== security ===
def asps_args(scope: list[str]) -> list[str]:
    return [*scope, "print", "asps", "oneitemperrow"]


def asps(rows: list[dict], users: list[dict] | None = None) -> list[dict]:
    ou = {u["email"].lower(): u.get("ou", "") for u in users or []}
    out = []
    for r in rows:
        low = _low(r)
        u = low.get("user", "").lower()
        name = low.get("asp.name", "")
        if not u or not (name or low.get("asp.codeid")):
            continue
        out.append({"Person": u, "Org unit": ou.get(u, ""), "App password": name,
                    "Created": low.get("asp.creationtime", "")[:16],
                    "Last used": low.get("asp.lasttimeused", "")[:16]})
    return sorted(out, key=lambda x: (x["Person"], x["Created"]))


def delete_asps_args(user: str) -> list[str]:
    return ["user", user, "delete", "asps", "all"]


SAKEYS_ARGS = ["show", "sakeys", "user"]


def sakeys(text: str, today: datetime.date | None = None) -> list[dict]:
    """`show sakeys` text → [{key, created, expires, age, current}]"""
    today = today or datetime.date.today()
    out, cur = [], None
    for ln in (text or "").splitlines():
        s = ln.strip()
        m = re.match(r"name:\s*(\S+)", s)
        if m:
            cur = {"key": m.group(1), "created": "", "expires": "", "age": None,
                   "current": False}
            out.append(cur)
            continue
        if cur is None:
            continue
        if s.startswith("validAfterTime:"):
            cur["created"] = s.split(":", 1)[1].strip()[:10]
            try:
                cur["age"] = (today - datetime.date.fromisoformat(cur["created"])).days
            except ValueError:
                pass
        elif s.startswith("validBeforeTime:"):
            cur["expires"] = s.split(":", 1)[1].strip()[:10]
        elif s.startswith("usedToAuthenticateThisRequest"):
            cur["current"] = True
    return out


ROTATE_ARGS = ["rotate", "sakeys", "retain_none"]


def alert_feedback_args(alert_id: str, how: str) -> list[str]:
    return ["create", "alertfeedback", alert_id, how]


# ===================================================================== groups ===
def grouptree_args(user: str) -> list[str]:
    return ["user", user, "print", "grouptree", "showparentsaslist", "true"]


def grouptree(rows: list[dict]) -> list[dict]:
    """→ [{Group, Name, How}] – direct groups, then the groups they are inside."""
    out = []
    for r in rows:
        low = _low(r)
        g = low.get("group", "")
        if not g:
            continue
        parents = [p for p in re.split(r"[\s,]+", low.get("parents", "")) if p]
        out.append({"Group": g, "Name": low.get("name", ""),
                    "How": "Member directly" + (f" → also gets mail for "
                                                f"{', '.join(parents)}" if parents else "")})
        for p in parents:
            out.append({"Group": p, "Name": "", "How": f"Through {g}"})
    seen, uniq = set(), []
    for o in out:
        if (o["Group"], o["How"]) not in seen:
            seen.add((o["Group"], o["How"]))
            uniq.append(o)
    return uniq


USERCOUNTS_ARGS = ["print", "usercountsbyorgunit"]


def usercounts(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for r in rows:
        low = _low(r)
        ou = low.get("orgunitpath", "")
        if not ou or ou.lower().startswith("total("):
            continue
        out[ou] = {k: _int(low.get(k)) for k in ("active", "suspended", "archived", "total")}
    return out


def rollup(counts: dict[str, dict], ou: str) -> dict:
    """Totals for an org unit and everything under it."""
    root = ou.rstrip("/") or "/"
    t = {"active": 0, "suspended": 0, "archived": 0, "total": 0}
    for o, c in counts.items():
        if root == "/" or o == root or o.startswith(root + "/"):
            for k in t:
                t[k] += c[k]
    return t
