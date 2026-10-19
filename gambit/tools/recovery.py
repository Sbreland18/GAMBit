"""Recovery and oversight: restore trashed Drive files and earlier versions, untrash mail,
nightly snapshots of Admin console / Chrome settings with change alerts, custom admin
roles, data-transfer checks, Chrome profiles, Forms privacy, Classroom activity and
student groups, YouTube channels, and domains."""

from __future__ import annotations

from ..settings import settings

import datetime
import json
import os
import re


def _low(r: dict) -> dict:
    return {(k or "").lower(): (v or "") for k, v in r.items()}


GOOGLE_NATIVE = "application/vnd.google-apps."


# ================================================================ drive ===
def trashed_by_audit_args(user: str, days: int) -> list[str]:
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    return ["report", "drive", "user", user, "start", start, "events", "trash"]


def trash_list_args(user: str) -> list[str]:
    return ["user", user, "print", "filelist", "query", "trashed = true and 'me' in owners",
            "fields", "id,name,mimetype,modifiedtime,webviewlink"]


def trashed_files(rows: list[dict], from_audit: bool) -> list[dict]:
    out, seen = [], set()
    for r in rows:
        low = _low(r)
        fid = low.get("doc_id") if from_audit else low.get("id")
        if not fid or fid in seen:
            continue
        seen.add(fid)
        out.append({"File": low.get("doc_title") if from_audit else low.get("name", ""),
                    "When": (low.get("id.time") if from_audit else low.get("modifiedtime", ""))
                    .replace("T", " ")[:16],
                    "By": low.get("actor.email", "") if from_audit else "",
                    "ID": fid})
    out.sort(key=lambda x: x["When"], reverse=True)
    return out


def untrash_args(user: str, ids: list[str]) -> list[str]:
    return ["user", user, "untrash", "drivefile", "ids", ",".join(ids)]


def revisions_args(owner: str, file_id: str) -> list[str]:
    return ["user", owner, "print", "filerevisions", file_id, "oneitemperrow", "fields",
            "id,modifiedtime,lastmodifyinguser,originalfilename,mimetype,size"]


def revisions(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = {k.removeprefix("revision."): v for k, v in _low(r).items()}
        who = low.get("lastmodifyinguser.emailaddress") or \
            low.get("lastmodifyinguser.displayname") or ""
        out.append({"Version": low.get("id", ""),
                    "Saved": low.get("modifiedtime", "").replace("T", " ")[:16],
                    "By": who, "Type": low.get("mimetype", ""), "Size": low.get("size", "")})
    out.sort(key=lambda x: x["Saved"], reverse=True)
    return out


def restore_revision_steps(owner: str, file_id: str, rev: str, folder: str,
                           name: str) -> list[tuple[str, list[str]]]:
    """Non-Google files: download that version, upload it as the newest one."""
    path = os.path.join(folder, name)
    return [(f"Download version {rev}", ["user", owner, "get", "drivefile", file_id,
                                         "revision", rev, "targetfolder", folder,
                                         "targetname", name, "overwrite"]),
            ("Save it as the current version", ["user", owner, "update", "drivefile", file_id,
                                                "localfile", path])]


# ================================================================= mail ===
def trashed_mail_args(user: str, query: str) -> list[str]:
    return ["user", user, "print", "messages", "query", query, "includespamtrash",
            "headers", "date,from,subject", "max_to_print", "500"]


def untrash_mail_args(user: str, query: str) -> list[str]:
    return ["user", user, "untrash", "messages", "query", query, "doit"]


# ===================================================== settings watch ===
CI_ARGS = ["print", "policies", "nowarnings", "formatjson"]


def chrome_root_args(ou: str = "/") -> list[str]:
    return ["print", "chromepolicies", "ou", ou, "show", "direct", "formatjson"]


def snapshot(ci_rows: list[dict], chrome_rows: list[dict]) -> dict:
    """→ {key: value-json}; key = 'Admin: <setting> @ <ou/group>' or 'Chrome: …'."""
    snap = {}
    for r in ci_rows:
        try:
            p = json.loads(r.get("JSON") or "{}")
        except ValueError:
            continue
        setting = (p.get("setting") or {}).get("type", "") or r.get("name", "")
        q = p.get("policyQuery") or {}
        where = q.get("orgUnitPath") or q.get("groupEmail") or q.get("orgUnit") or "/"
        key = f"Admin: {setting.replace('settings/', '')} @ {where}"
        snap[key] = json.dumps((p.get("setting") or {}).get("value", {}), sort_keys=True)
    for r in chrome_rows:
        try:
            p = json.loads(r.get("JSON") or "{}")
        except ValueError:
            continue
        key = f"Chrome: {p.get('name', '')} @ {p.get('orgUnitPath', '/')}"
        snap[key] = json.dumps({f.get("name"): f.get("value") for f in p.get("fields", [])},
                               sort_keys=True)
    return snap


def diff(old: dict, new: dict) -> list[dict]:
    out = []
    for k in sorted(set(old) | set(new)):
        if k not in old:
            out.append({"Change": "added", "Setting": k, "Before": "", "Now": new[k][:300]})
        elif k not in new:
            out.append({"Change": "removed", "Setting": k, "Before": old[k][:300], "Now": ""})
        elif old[k] != new[k]:
            out.append({"Change": "changed", "Setting": k, "Before": old[k][:300],
                        "Now": new[k][:300]})
    return out


def snapshots_dir() -> str:
    from PySide6.QtCore import QStandardPaths
    from .. import team
    if team.folder():
        d = os.path.join(team.folder(), "settings-snapshots")
    else:
        base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
            os.path.expanduser("~")
        d = os.path.join(base, "settings-snapshots")
    os.makedirs(d, exist_ok=True)
    return d


def save_snapshot(snap: dict, when: str = "") -> str:
    when = when or datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = os.path.join(snapshots_dir(), f"{when}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return path


def list_snapshots() -> list[str]:
    d = snapshots_dir()
    return sorted((f for f in os.listdir(d) if f.endswith(".json")), reverse=True)


def load_snapshot(name: str) -> dict:
    with open(os.path.join(snapshots_dir(), name), encoding="utf-8") as fh:
        return json.load(fh)


TASK = {"name": "GAMbit settings watch", "args": ["--task", "settingswatch"],
        "freq": "daily", "time": "05:05",
        "what": "Saves a copy of the Admin console and Chrome settings and alerts on changes",
        "standard": False}


def run_watch(log=print, run_csv=None) -> int:
    """Background task: snapshot, compare with the previous one, alert on changes."""
    from ..directory import run_gam_csv
    run_csv = run_csv or (lambda a: run_gam_csv(a, 1800))
    c1, ci, e1 = run_csv(CI_ARGS)
    c2, cr, e2 = run_csv(chrome_root_args("/"))
    if c1 != 0 or c2 != 0:     # a partial read would look like settings were removed
        raise RuntimeError("Couldn't read all settings – nothing compared or saved: " +
                           ((e1 if c1 else e2) or "").strip()[-300:])
    snap = snapshot(ci, cr)
    prev, older = [], None
    for name in list_snapshots():     # newest readable snapshot
        try:
            older = load_snapshot(name)
            prev = [name]
            break
        except (OSError, ValueError):
            continue
    changes = diff(older, snap) if prev else []
    save_snapshot(snap)
    log(f"Saved {len(snap)} settings" + (f"; {len(changes)} changed since {prev[0][:-5]}"
                                        if prev else " (first snapshot)"))
    if changes:
        from .. import alerts
        text = "\n".join(f"• {c['Change']}: {c['Setting']}" for c in changes[:30])
        alerts.notify(f"{len(changes)} Google admin setting(s) changed since "
                      f"{prev[0][:-5]}:\n{text}\n\nSee who changed them: GAMbit → "
                      "Investigations → Admin changes.", "GAMbit: admin settings changed")
        for c in changes[:200]:
            log(f"{c['Change']}: {c['Setting']}")
        if settings.get("watch/drift_guard", False):
            try:
                from .. import activity
                from .playbooks import drift_request
                req = drift_request(changes, prev[0][:-5], activity.load(30, team=True))
                if req:
                    log(f"Drift guard: sent “{req['title']}” for approval.")
            except Exception as exc:  # noqa: BLE001
                log(f"Drift guard failed: {exc}")
    return 0


# ========================================================== admin roles ===
PRIVILEGES_ARGS = ["print", "privileges"]

ROLE_TEMPLATES = {
    "Building tech (reset passwords, view users)": ["USERS_RETRIEVE", "USERS_RESET_PASSWORD",
                                                    "USERS_UPDATE_SECURITY"],
    "Chromebook manager": ["CHROME_OS", "MANAGE_DEVICES", "MANAGE_DEVICE_SETTINGS"],
    "Office manager (users and groups)": ["USERS_RETRIEVE", "USERS_UPDATE", "GROUPS_RETRIEVE",
                                          "GROUPS_UPDATE"],
}


def privileges(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        name = low.get("privilegename", "")
        if name:
            out.append({"Privilege": name, "Service": low.get("servicename", ""),
                        "Per org unit": "yes" if low.get("isouscopable", "").lower() == "true"
                        else "", "Service ID": low.get("serviceid", "")})
    out.sort(key=lambda x: (x["Service"], x["Privilege"]))
    return out


def template_matches(template: list[str], available: list[str]) -> list[str]:
    """Privileges from a template that exist in this domain (prefix match, e.g. CHROME_OS)."""
    out = []
    for t in template:
        out += [p for p in available if p == t or p.startswith(t + "_")]
    return list(dict.fromkeys(out))


def create_role_args(name: str, description: str, privs: list[str]) -> list[str]:
    a = ["create", "adminrole", name]
    if description:
        a += ["description", description]
    return a + ["privileges", ",".join(privs)]


def assign_role_args(email: str, role: str, ou: str = "") -> list[str]:
    return ["create", "admin", email, role] + (["org_unit", ou] if ou else ["customer"])


# ======================================================== data transfers ===
def transfers_args(old_user: str = "") -> list[str]:
    return ["print", "datatransfers"] + (["olduser", old_user] if old_user else [])


def transfers(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        out.append({"From": low.get("oldowneruseremail", ""),
                    "To": low.get("newowneruseremail", ""),
                    "Requested": low.get("requesttime", "").replace("T", " ")[:16],
                    "Status": low.get("overalltransferstatuscode", "").lower(),
                    "App": low.get("application", ""),
                    "App status": low.get("status", "").lower()})
    out.sort(key=lambda x: x["Requested"], reverse=True)
    return out


# ======================================================== chrome profiles ===
PROFILES_ARGS = ["print", "chromeprofiles", "fields",
                 "useremail,displayname,osplatformtype,osversion,browserversion,"
                 "browserchannel,lastactivitytime,extensioncount,policycount,affiliationstate"]


def profiles(rows: list[dict], stale_days: int = 60) -> list[dict]:
    cutoff = (datetime.date.today() - datetime.timedelta(days=stale_days)).isoformat()
    out = []
    for r in rows:
        low = _low(r)
        last = low.get("lastactivitytime", "")[:10]
        out.append({"Person": low.get("useremail", ""), "Profile": low.get("displayname", ""),
                    "Computer": f"{low.get('osplatformtype', '').title()} "
                                f"{low.get('osversion', '')}".strip(),
                    "Chrome": low.get("browserversion", ""),
                    "Extensions": low.get("extensioncount", ""), "Last used": last,
                    "Note": "not used in 60+ days" if last and last < cutoff else ""})
    out.sort(key=lambda x: (x["Person"], x["Last used"]))
    return out


# ================================================================= forms ===
FORM_QUERY = "mimeType = 'application/vnd.google-apps.form' and 'me' in owners and trashed = false"


def forms_args(scope: str) -> list[str]:
    ent = ["all", "users"] if scope in ("", "/") else (["user", scope] if "@" in scope
                                                       else ["ou_and_children", scope])
    return [*ent, "print", "forms", "query", FORM_QUERY]


def forms_post(rows: list[dict], _dom: str = "") -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        collect = low.get("settings.emailcollectiontype", "")
        quiz = low.get("settings.quizsettings.isquiz", "").lower() == "true"
        why = []
        if collect in ("", "DO_NOT_COLLECT", "EMAIL_COLLECTION_TYPE_UNSPECIFIED"):
            why.append("doesn't collect who answered – anyone with the link can respond")
        elif collect == "RESPONDER_INPUT":
            why.append("people type their own email (not verified)")
        if why:
            out.append({"Owner": low.get("user", ""), "Form": low.get("name", "") or
                        low.get("title", ""), "Quiz": "yes" if quiz else "",
                        "Concern": "; ".join(why), "Link": low.get("responderuri", ""),
                        "Form ID": low.get("formid", "")})
    return out


# ============================================================= classroom ===
def activity_args(kind: str, scope: list[str]) -> list[str]:
    return ["print", kind, *scope, "countsonly"]


def class_activity(ann: list[dict], mat: list[dict], work: list[dict]) -> list[dict]:
    """Rows from `print course-announcements|course-materials|course-works … countsonly`
    (courseId, courseName, <count column>)."""
    names: dict[str, str] = {}

    def counts(rows):
        out = {}
        for r in rows:
            low = _low(r)
            cid = low.get("courseid", "")
            names[cid] = low.get("coursename", "") or names.get(cid, cid)
            out[cid] = next((v for k, v in low.items() if k not in ("courseid", "coursename")),
                            "0") or "0"
        return out
    a, m, w = counts(ann), counts(mat), counts(work)
    out = []
    for cid in sorted(names, key=lambda c: names[c].lower()):
        row = {"Class": names[cid], "Announcements": a.get(cid, "0"),
               "Materials": m.get(cid, "0"), "Assignments": w.get(cid, "0")}
        row["Note"] = "nothing posted yet" if all(row[k] in ("0", "") for k in
                                                  ("Announcements", "Materials",
                                                   "Assignments")) else ""
        out.append(row)
    return out


def studentgroup_rows(text_rows: list[dict]) -> dict[tuple[str, str], list[str]]:
    """CSV with Class (ID or d:alias), Group, Student email → {(class, group): [emails]}"""
    def col(r, *names):
        low = {re.sub(r"[^a-z]", "", (k or "").lower()): v for k, v in r.items()}
        return next(((low.get(n) or "").strip() for n in names if low.get(n)), "")
    out: dict = {}
    for r in text_rows:
        c, g, s = col(r, "class", "course", "courseid", "classid"), \
            col(r, "group", "studentgroup", "groupname"), \
            col(r, "student", "studentemail", "email")
        if c and g and "@" in s:
            out.setdefault((c, g), []).append(s.lower())
    return out


def existing_groups(rows: list[dict]) -> dict[tuple[str, str], str]:
    out = {}
    for r in rows:
        low = _low(r)
        cid, title, gid = low.get("courseid", ""), low.get("title", ""), low.get("id", "")
        if cid and title and gid:
            out[(cid, title.lower())] = gid
    return out


def create_group_args(course: str, title: str) -> list[str]:
    return ["create", "course-studentgroups", "course", course, "title", title]


def sync_group_args(course: str, gid: str, emails: list[str]) -> list[str]:
    return ["sync", "course-studentgroup-members", course, gid, "users", ",".join(emails)]


# =============================================================== youtube ===
def youtube_args(user: str) -> list[str]:
    return ["user", user, "print", "youtubechannels", "mine"]


def youtube(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        out.append({"Channel": low.get("snippet.title", "") or low.get("title", ""),
                    "Subscribers": low.get("statistics.subscribercount", ""),
                    "Videos": low.get("statistics.videocount", ""),
                    "Link": f"https://www.youtube.com/channel/{low.get('id', '')}"
                    if low.get("id") else ""})
    return out


# =============================================================== domains ===
DOMAIN_ARGS = ["print", "domains"]
ALIAS_ARGS = ["print", "domainaliases"]
