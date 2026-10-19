"""Security & compliance reports (state audits, student-privacy agreements)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


def _entity(scope: str) -> list[str]:
    s = (scope or "/").strip()
    return ["all", "users"] if s in ("", "/") else ["ou_and_children", s]


def _ou_query(scope: str) -> str:
    s = (scope or "/").strip()
    return "" if s in ("", "/") else f" orgUnitPath='{s}'"


def _has_license(row: dict) -> bool:
    return any((k or "").lower().startswith("licen") and "display" not in (k or "").lower()
               and (v or "").strip() for k, v in row.items())


@dataclass
class Report:
    key: str
    title: str
    why: str
    scope_label: str
    default_scope: str
    build: Callable[[str, str], list[str]]        # (scope, domain) -> gam args
    keep: Optional[Callable[[dict], bool]] = None
    slow: bool = False
    post: Optional[Callable[[list, str], list]] = None    # (rows, domain) -> rows
    group: str = "Security"


REPORTS = [
    Report("no2sv", "Accounts without 2-step verification",
           "Active accounts that haven't turned on 2-step verification – the most common "
           "audit question. Staff accounts matter most.",
           "Only accounts under", "/Staff",
           lambda scope, dom: ["print", "users", "query",
                               "isEnrolledIn2Sv=False isSuspended=False" + _ou_query(scope),
                               "fields", "primaryemail,name,ou,isenrolledin2sv,"
                               "isenforcedin2sv,lastlogintime"]),
    Report("external", "Files shared outside the district",
           "Files shared with “anyone with the link”, or with people/groups outside your "
           "domain. Pick an org unit – checking every file in the district can take hours. "
           "To fix them, use Google Drive → Fix sharing.",
           "Files owned by people under", "/Staff",
           lambda scope, dom: [*_entity(scope), "print", "filelist", "fields",
                               "id,name,mimetype,owners,webviewlink,permissions",
                               "pm", "type", "anyone", "em",
                               "pm", "typelist", "user,group", "notdomainlist", dom, "em",
                               "pmm", "or", "pmfilter", "oneitemperrow"],
           slow=True),
    Report("apps", "Third-party apps with access to student accounts",
           "Every app students have signed in to with their Google account, and how many "
           "students use each – needed for student-privacy agreements.",
           "Students under", "/Students",
           lambda scope, dom: [*_entity(scope), "print", "tokens", "aggregateusersby",
                               "displaytext"],
           slow=True),
    Report("admins", "Admins and their roles",
           "Everyone with admin rights in Google Workspace, which role, and where it applies.",
           "", "/",
           lambda scope, dom: ["print", "admins"]),
    Report("susplic", "Suspended accounts still holding licenses",
           "Suspended accounts that still use a paid license – release them to save money.",
           "Only accounts under", "/",
           lambda scope, dom: ["print", "users", "query", "isSuspended=True" + _ou_query(scope),
                               "fields", "primaryemail,name,ou,suspended", "licenses"],
           keep=_has_license),
]

# --------------------------------------------------------- Drive & storage ---
def _num(v) -> float:
    try:
        return float(str(v).replace(",", "") or 0)
    except ValueError:
        return 0.0


def _storage_post(rows, _dom):
    out = []
    for r in rows:
        low = {(k or "").lower(): v for k, v in r.items()}
        email = low.get("email") or low.get("user") or ""
        total = _num(low.get("accounts:used_quota_in_mb"))
        out.append({"Email": email,
                    "Total (GB)": f"{total / 1024:.1f}",
                    "Drive (GB)": f"{_num(low.get('accounts:drive_used_quota_in_mb')) / 1024:.1f}",
                    "Gmail (GB)": f"{_num(low.get('accounts:gmail_used_quota_in_mb')) / 1024:.1f}",
                    "Photos (GB)": f"{_num(low.get('accounts:gplus_photos_used_quota_in_mb')) / 1024:.1f}",
                    "Data from": low.get("date", "")})
    out.sort(key=lambda x: -float(x["Total (GB)"]))
    return out


def _drives(rows):
    drives = {}
    for r in rows:
        low = {(k or "").lower(): v for k, v in r.items()}
        did = low.get("id") or low.get("shareddriveid") or ""
        d = drives.setdefault(did, {"name": low.get("name") or low.get("shareddrivename", ""),
                                    "managers": 0, "members": 0, "outside": []})
        role = (low.get("permission.role") or low.get("role") or "").lower()
        email = (low.get("permission.emailaddress") or low.get("emailaddress") or "").lower()
        ptype = (low.get("permission.type") or low.get("type") or "").lower()
        d["members"] += 1
        if role == "organizer":
            d["managers"] += 1
        d.setdefault("emails", []).append((email, ptype, role))
    return drives


def _nomanager_post(rows, _dom):
    return [{"Shared drive": d["name"], "ID": did, "Members": str(d["members"])}
            for did, d in _drives(rows).items() if did and d["managers"] == 0]


def _outside_post(rows, dom):
    out = []
    for did, d in _drives(rows).items():
        ext = [f"{e} ({role})" for e, t, role in d.get("emails", [])
               if t in ("user", "group") and e and not e.endswith("@" + dom.lower())]
        if ext:
            out.append({"Shared drive": d["name"], "ID": did, "Outside members": ", ".join(ext)})
    return out


REPORTS += [
    Report("storage", "Who uses the most storage",
           "Drive, Gmail and Photos storage per person (Google's usage reports run about two "
           "days behind). Sorted biggest first.",
           "Only people under", "/",
           lambda scope, dom: ["report", "users"] + ([] if scope in ("", "/") else
                                                     ["orgunit", scope]) +
           ["parameters", "accounts:used_quota_in_mb,accounts:drive_used_quota_in_mb,"
                          "accounts:gmail_used_quota_in_mb,"
                          "accounts:gplus_photos_used_quota_in_mb"],
           post=_storage_post, group="Drive & storage"),
    Report("bigfiles", "Large files owned by people who have left",
           "Files over 100 MB owned by accounts in the leavers' org unit – move or delete them "
           "before the accounts are deleted.",
           "Owners under", "/Former Staff",
           lambda scope, dom: [*_entity(scope), "print", "filelist", "fields",
                               "id,name,mimetype,size,owners,modifiedtime,webviewlink",
                               "minimumfilesize", "104857600"],
           slow=True, group="Drive & storage"),
    Report("nomanager", "Shared drives with no manager",
           "Shared drives where nobody has the Manager role – nobody can add members or "
           "recover deleted files without an admin.", "", "/",
           lambda scope, dom: ["print", "shareddriveacls", "oneitemperrow"],
           post=_nomanager_post, slow=True, group="Drive & storage"),
    Report("outside", "Shared drives with members outside the district",
           "Shared drives that include people or groups from other domains.", "", "/",
           lambda scope, dom: ["print", "shareddriveacls", "oneitemperrow"],
           post=_outside_post, slow=True, group="Drive & storage"),
]

def _forms_args(scope):
    from .tools.recovery import forms_args
    return forms_args(scope)


def _forms_post(rows, dom):
    from .tools.recovery import forms_post
    return forms_post(rows, dom)


def _group_post(rows, _dom):
    from .tools.more_tools import risky_groups
    return risky_groups(rows)


REPORTS += [
    Report("opengroups", "Groups open to outsiders",
           "Groups that allow outside members, accept email from anyone on the internet, "
           "let anyone join, or show their member list publicly.", "", "/",
           lambda scope, dom: ["print", "groups", "settings", "fields",
                               "email,name,directmemberscount"],
           post=_group_post, group="Security"),
    Report("forms", "Forms that don't check who answered",
           "Google Forms that don't require sign-in (anyone with the link can answer) or let "
           "people type any email. Fine for some surveys – not for anything collecting "
           "student information.", "Forms owned by people under", "/Staff",
           lambda scope, dom: _forms_args(scope), post=_forms_post, slow=True,
           group="Security"),
    Report("sso", "Single sign-on profiles",
           "Third-party sign-in (SAML / OIDC) profiles set up for your domain – e.g. ClassLink "
           "or Clever – and their sign-in and sign-out pages. Read only.", "", "/",
           lambda scope, dom: ["print", "inboundssoprofiles"], group="Sign-in & access"),
    Report("ssoassign", "Where single sign-on applies",
           "Which org units and groups use which sign-in profile (or Google's own sign-in). "
           "Read only.", "", "/",
           lambda scope, dom: ["print", "inboundssoassignments"], group="Sign-in & access"),
    Report("caa", "Context-aware access levels",
           "Access levels (for example “district network only” or “managed Chromebooks only”) "
           "used to limit where apps can be opened. Read only.", "", "/",
           lambda scope, dom: ["print", "caalevels"], group="Sign-in & access"),
]

_ORDER: list[str] = []
for _r in REPORTS:
    if _r.group not in _ORDER:
        _ORDER.append(_r.group)
REPORTS.sort(key=lambda r: _ORDER.index(r.group))      # keep each group together
BY_KEY = {r.key: r for r in REPORTS}
