"""More GAM commands (Round 14): Meet conferences / recordings / transcripts, Forms
responses, Chromebook Wi-Fi networks, serial checks and device counts, app details, device
files, replacing someone in meetings, folder ownership / paths / comments / sizes / broken
shortcuts, Classroom teacher profiles and class counts, guardian invitations, trusted
(allowlisted) domains, Vault saved searches, profile photo export, Chat moderation, Gmail
display language and printer models."""

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


# ====================================================================== Meet ===
def meet_code(text: str) -> str:
    """'abc-defg-hij', a meet.google.com link or 'ABCDEFGHIJ' → 'abc-defg-hij'"""
    m = re.search(r"([a-z]{3})-?([a-z]{4})-?([a-z]{3})(?![a-z])", (text or "").lower())
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def conferences_args(owner: str, code: str = "", since: str = "") -> list[str]:
    a = ["user", owner, "print", "meetconferences"]
    if code:
        a += ["code", meet_code(code)]
    if since:
        a += ["andquery", f'start_time>="{since}T00:00:00Z"']
    return a


def conferences(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        if not low.get("name"):
            continue
        out.append({"Started": low.get("starttime", "")[:16].replace("T", " "),
                    "Ended": low.get("endtime", "")[:16].replace("T", " "),
                    "Space": low.get("space", ""), "name": low["name"]})
    return sorted(out, key=lambda x: x["Started"], reverse=True)


def meet_items_args(owner: str, kind: str, conference: str) -> list[str]:
    """kind: meetparticipants | meetrecordings | meettranscripts"""
    return ["user", owner, "print", kind, conference]


def meet_files(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        fid = next((v for k, v in low.items() if k.endswith("file") or k.endswith("document")
                    or k.endswith("fileid") or k.endswith("documentid")), "")
        link = next((v for k, v in low.items() if "exporturi" in k or "link" in k), "")
        out.append({"Kind": "recording" if "drivedestination" in " ".join(low) else
                    "transcript", "State": low.get("state", ""),
                    "Started": low.get("starttime", "")[:16].replace("T", " "),
                    "File": fid, "Link": link})
    return out


# ===================================================================== Forms ===
def form_id(text: str) -> str:
    m = re.search(r"/forms/d/(?:e/)?([A-Za-z0-9_-]{20,})", text or "")
    return m.group(1) if m else (text or "").strip()


def form_responses_args(owner: str, form: str, counts: bool = False) -> list[str]:
    a = ["user", owner, "print", "formresponses", form_id(form)]
    return a + (["countsonly"] if counts else [])


def form_responses(rows: list[dict]) -> list[dict]:
    """Flatten GAM's indexed answers into one column per question ID."""
    out = []
    for r in rows:
        low = {k: (v or "") for k, v in r.items()}
        row = {"Submitted": (low.get("lastSubmittedTime") or low.get("createTime") or
                             "")[:16].replace("T", " "),
               "Email": low.get("respondentEmail", ""), "Score": low.get("totalScore", "")}
        qids = {}
        for k, v in low.items():
            m = re.match(r"answers\.(\d+)\.questionId", k or "")
            if m:
                qids[m.group(1)] = v
        for n, q in sorted(qids.items(), key=lambda x: int(x[0])):
            vals = [v for k, v in low.items() if k.startswith(f"answers.{n}.") and
                    k.lower().endswith(".value") and v]
            row[f"Q {q}"] = "; ".join(vals)
        out.append(row)
    return out


# ===================================================== Chromebook Wi-Fi networks ===
SECURITY = {"WPA/WPA2 Personal (password)": "WPA-PSK", "Open (no password)": "None",
            "WEP": "WEP-PSK"}


def wifi_json(ssid: str, security: str, passphrase: str = "", autoconnect: bool = True,
              hidden: bool = False) -> str:
    value = {"ssid": ssid, "security": security, "autoConnect": autoconnect,
             "hiddenSsid": hidden}
    if passphrase:
        value["passphrase"] = passphrase
    return json.dumps({"settings": [{"policySchema": "chrome.networks.wifi.Details",
                                     "value": value}]})


def network_create_args(ou: str, name: str, js: str) -> list[str]:
    return ["create", "chromenetwork", ou, name, "json", js]


def network_delete_args(ou: str, network_id: str) -> list[str]:
    return ["delete", "chromenetwork", ou, network_id]


def networks_args(ou: str) -> list[str]:
    return ["print", "chromepolicies", "ou", ou, "namespace", "chrome.networks.wifi",
            "formatjson"]


def networks(rows: list[dict]) -> list[dict]:
    out = {}
    for r in rows:
        try:
            p = json.loads(r.get("JSON") or "{}")
        except ValueError:
            continue
        keys = p.get("additionalTargetKeys") or {}
        if isinstance(keys, list):
            keys = {k.get("name"): k.get("value") for k in keys if isinstance(k, dict)}
        nid = keys.get("network_id") or keys.get("networkId") or ""
        fields = {f.get("name"): f.get("value") for f in p.get("fields", [])}
        if not nid:
            continue
        o = out.setdefault(nid, {"Network ID": nid, "Name": "", "SSID": "", "Security": "",
                                 "Org unit": p.get("orgUnitPath", "")})
        o["Name"] = o["Name"] or fields.get("name", "") or fields.get("details", "")
        o["SSID"] = o["SSID"] or str(fields.get("ssid", ""))
        o["Security"] = o["Security"] or str(fields.get("security", ""))
    return list(out.values())


# ============================================================ Chromebook tools ===
def snvalidity_args(serials: list[str]) -> list[str]:
    return ["print", "chromesnvalidity", "cros_sn", ",".join(serials)]


def snvalidity(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        sn = low.get("serialnumber", "")
        exact, prefix = _int(low.get("exactmatches")), _int(low.get("prefixmatches"))
        what = ("Enrolled in your domain" if exact else
                f"Not found – {prefix} serial(s) start with this (typo?)" if prefix else
                "Not in your domain yet")
        out.append({"Serial": sn, "Result": what, "Exact": exact, "Similar": prefix})
    return out


def device_counts_args(mode: str = "active") -> list[str]:
    return ["print", "chromedevicecounts", "mode", mode]


def app_info_args(app_id: str, kind: str = "chrome") -> list[str]:
    return ["info", "chromeapp", kind, app_id]


PERMISSION_WORDS = {"<all_urls>": "every website", "webRequest": "watch/alter web traffic",
                    "proxy": "change proxy settings", "history": "browsing history",
                    "tabs": "open tabs", "cookies": "cookies", "clipboardRead": "clipboard",
                    "management": "other extensions", "desktopCapture": "capture the screen",
                    "downloads": "downloads", "identity": "your Google identity"}


def app_permissions(text: str) -> list[str]:
    found = []
    for k, label in PERMISSION_WORDS.items():
        if k.lower() in (text or "").lower():
            found.append(label)
    return found


def devicefile_args(serial: str, folder: str) -> list[str]:
    return ["cros_sn", serial, "get", "devicefile", "targetfolder", folder]


# ============================================================== calendar swap ===
def replace_attendee_args(organizers: list[str], old: str, new: str,
                          after: str = "") -> list[str]:
    """Replace `old` with `new` in every future meeting these people organize."""
    after = after or datetime.date.today().isoformat()
    return ["users", ",".join(organizers), "update", "calattendees", "primary",
            "after", after, "matchfield", "attendees", old,
            "replace", old, new, "doit"]


# ============================================================== drive folders ===
def drive_id(text: str) -> str:
    m = re.search(r"/(?:d|folders)/([A-Za-z0-9_-]{10,})|[?&]id=([A-Za-z0-9_-]{10,})",
                  text or "")
    return (m.group(1) or m.group(2)) if m else (text or "").strip()


def transfer_args(owner: str, item: str, new_owner: str, preview: bool = False) -> list:
    a = ["user", owner, "transfer", "ownership", drive_id(item), new_owner]
    return a + (["preview"] if preview else [])


def claim_args(new_owner: str, item: str, keep_old: bool = True,
               preview: bool = False) -> list[str]:
    a = ["user", new_owner, "claim", "ownership", drive_id(item)]
    a += ["retainrole", "writer"] if keep_old else ["retainrole", "none"]
    return a + (["preview"] if preview else [])


def filepath_args(owner: str, item: str) -> list[str]:
    return ["user", owner, "print", "filepath", drive_id(item), "fullpath"]


def comments_args(owner: str, item: str) -> list[str]:
    return ["user", owner, "print", "filecomments", drive_id(item), "showdeleted"]


def comments(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        for k in sorted(low):
            m = re.match(r"comments\.(\d+)\.content$", k)
            if not m:
                continue
            n = m.group(1)
            out.append({"When": low.get(f"comments.{n}.createdtime", "")[:16].replace(
                "T", " "), "Who": low.get(f"comments.{n}.author.emailaddress", "") or
                low.get(f"comments.{n}.author.displayname", ""),
                "Comment": low[k][:300],
                "Deleted": "yes" if low.get(f"comments.{n}.deleted", "").lower() == "true"
                else ""})
    return sorted(out, key=lambda x: x["When"])


def diskusage_args(owner: str, item: str) -> list[str]:
    return ["user", owner, "print", "diskusage", drive_id(item), "show", "summary"]


def shortcut_args(owner: str, item: str) -> list[str]:
    return ["user", owner, "check", "drivefileshortcut", drive_id(item), "csv"]


# ================================================================== classroom ===
def classroom_profile_args(scope: list[str]) -> list[str]:
    return [*scope, "print", "classroomprofile"]


def teacher_status(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        e = low.get("emailaddress", "") or low.get("user", "")
        if not e:
            continue
        ver = low.get("verifiedteacher", "")
        perms = " ".join(v for k, v in low.items() if k.startswith("permissions"))
        out.append({"Person": e, "Verified teacher": "yes" if ver.lower() == "true" else
                    ("no" if ver else "unknown"),
                    "Can create classes": "yes" if "CREATE_COURSE" in perms.upper() else
                    "no"})
    return sorted(out, key=lambda x: (x["Can create classes"] == "yes", x["Person"]))


def course_counts_args(kind: str = "students") -> list[str]:
    return ["print", "course-counts", kind, "states", "active"]


def course_counts(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        who = next((v for k, v in low.items() if k != "coursecount" and "@" in v), "")
        out.append({"Person": who, "Active classes": _int(low.get("coursecount"))})
    return sorted(out, key=lambda x: -x["Active classes"])


# ================================================================== guardians ===
def cancel_guardian_args(invitation_id: str, student: str) -> list[str]:
    return ["cancel", "guardianinvitation", invitation_id, student]


# ============================================================ trusted domains ===
ALLOWLIST_ARGS = ["print", "allowlisteddomains"]


def allowlist(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        dom = low.get("allowlisteddomain", "") or low.get("domain", "") or \
            next((v for k, v in low.items() if "domain" in k and "." in v), "")
        out.append({"Domain": dom, "id": low.get("name", "") or low.get("id", "") or dom})
    return [o for o in out if o["Domain"]]


def allowlist_add_args(domains: list[str]) -> list[str]:
    return ["create", "allowlisteddomains", ",".join(domains)]


def allowlist_delete_args(ids: list[str]) -> list[str]:
    return ["delete", "allowlisteddomains", ",".join(ids)]


# ====================================================================== vault ===
def vault_query_args(matter: str, name: str, corpus: str, accounts: list[str]) -> list:
    return ["create", "vaultquery", matter, "name", name, "corpus", corpus,
            "accounts", ",".join(accounts)]


def vault_queries_args(matter: str) -> list[str]:
    return ["print", "vaultqueries", "matters", matter]


# ===================================================================== photos ===
def photo_export_args(scope: list[str], folder: str) -> list[str]:
    return [*scope, "get", "profilephoto", "targetfolder", folder, "filename",
            "#email#.jpg", "nodefault"]


# ======================================================================= chat ===
def chat_spaces_admin_args(admin: str, query: str = 'spaceType = "SPACE"') -> list[str]:
    return ["user", admin, "print", "chatspaces", "asadmin", "query", query]


def chat_members_admin_args(admin: str, space: str) -> list[str]:
    return ["user", admin, "print", "chatmembers", "asadmin", space]


def chat_remove_member_args(admin: str, space: str, member: str) -> list[str]:
    return ["user", admin, "delete", "chatmember", "asadmin", space, "user", member]


def chat_delete_space_args(admin: str, space: str) -> list[str]:
    return ["user", admin, "delete", "chatspace", "asadmin", space]


def chat_spaces(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        if not low.get("name"):
            continue
        out.append({"Space": low.get("displayname", "") or low["name"],
                    "Type": low.get("spacetype", "").title(),
                    "External": "yes" if low.get("externaluserallowed", "").lower() == "true"
                    else "", "Created": low.get("createtime", "")[:10],
                    "Members": low.get("membershipcount.joineddirecthumanusercount", ""),
                    "name": low["name"]})
    return out


# ============================================================ gmail language ===
LANGUAGES = [("English (US)", "en"), ("Spanish", "es"), ("Spanish (Latin America)", "es-419"),
             ("French", "fr"), ("Portuguese (Brazil)", "pt-BR"), ("Vietnamese", "vi"),
             ("Chinese (Simplified)", "zh-CN"), ("Arabic", "ar"), ("Haitian Creole", "ht"),
             ("Korean", "ko"), ("Russian", "ru"), ("Somali", "so"), ("Tagalog", "tl")]


def language_args(scope: list[str], code: str) -> list[str]:
    return [*scope, "language", code]


def language_show_args(scope: list[str]) -> list[str]:
    return [*scope, "print", "language"]


# ============================================================ printer models ===
def printer_models_args(filt: str = "") -> list[str]:
    return ["print", "printermodels"] + (["filter", f'manufacturer:"{filt}"'] if filt else [])
