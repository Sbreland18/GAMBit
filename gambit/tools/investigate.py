"""Investigations: Google's audit logs (who opened, downloaded or shared a file; sign-ins;
admin changes), Meet usage by school, and third-party app access with one-click removal."""

from __future__ import annotations

import datetime
import re
from collections import defaultdict

APPS = [("Drive (files)", "drive"), ("Sign-ins", "login"), ("Admin changes", "admin"),
        ("Google Meet", "meet"), ("Chrome", "chrome"), ("Groups", "groups"),
        ("Classroom", "classroom"), ("Calendar", "calendar"), ("Gmail", "gmail"),
        ("App access (OAuth)", "token")]

PRESETS = [
    # label, app, events, explanation
    ("Who opened, downloaded or printed a file", "drive", "view,download,print,copy",
     "Paste the file's link. Shows every person who looked at it."),
    ("Who changed a file's sharing", "drive",
     "change_user_access,change_document_visibility,change_document_access_scope",
     "Paste a link, or pick a person to see everything they shared."),
    ("Files a person deleted", "drive", "trash,delete", "Pick a person."),
    ("Suspicious or failed sign-ins", "login",
     "login_failure,suspicious_login,suspicious_login_less_secure_app,"
     "suspicious_programmatic_login", "Leave the person empty for everyone."),
    ("Admin changes to an account", "admin", "", "Pick the account that was changed – the "
                                                  "list shows which admin did what."),
    ("Third-party apps people signed in to", "token", "authorize",
     "New app sign-ins, with the app name."),
]

# columns worth showing (matched case-insensitively against GAM's report columns)
SHOW = [("When", ["id.time"]), ("Who", ["actor.email"]), ("What", ["name", "event"]),
        ("File", ["doc_title"]), ("File ID", ["doc_id"]),
        ("To / target", ["target_user", "target_domain", "user_email"]),
        ("Visibility", ["visibility", "new_value"]), ("App", ["app_name", "client_id"]),
        ("Setting", ["setting_name"]), ("IP address", ["ipaddress"]),
        ("Login type", ["login_type"]), ("Meeting", ["meeting_code"])]


def doc_id(text: str) -> str:
    t = (text or "").strip()
    m = re.search(r"/d/([A-Za-z0-9_-]{10,})", t) or re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", t)
    if m:
        return m.group(1)
    return t if re.fullmatch(r"[A-Za-z0-9_-]{10,}", t) else ""


def report_args(app: str, who: str = "", ou: str = "", days: int = 7, events: str = "",
                doc: str = "", admin_target: str = "") -> list[str]:
    args = ["report", app]
    if app == "admin" and admin_target:
        args += ["user", "all"]
    elif who:
        args += ["user", who]
    elif ou and ou != "/":
        args += ["orgunit", ou]
    else:
        args += ["user", "all"]
    start = (datetime.date.today() - datetime.timedelta(days=max(1, days))).isoformat()
    args += ["start", start]
    if events:
        args += ["events", events]
    filters = []
    if doc:
        filters.append(f"doc_id=={doc}")
    if admin_target:
        filters.append(f"USER_EMAIL=={admin_target}")
    if filters:
        args += ["filter", ",".join(filters)]
    return args


def tidy(rows: list[dict]) -> tuple[list[str], list[list[str]]]:
    if not rows:
        return [], []
    keys = {(k or "").lower(): k for k in rows[0]}
    cols = []
    for label, cands in SHOW:
        k = next((keys[c] for c in cands if c in keys), None)
        if k and any((r.get(k) or "").strip() for r in rows):
            cols.append((label, k))
    if not cols:
        heads = list(rows[0].keys())
        return heads, [[r.get(h, "") or "" for h in heads] for r in rows]
    out = []
    for r in rows:
        line = []
        for label, k in cols:
            v = r.get(k, "") or ""
            if label == "When":
                v = v.replace("T", " ")[:19]
            line.append(v)
        out.append(line)
    out.sort(key=lambda x: x[0], reverse=True)
    return [c[0] for c in cols], out


# ---------------------------------------------------------- Meet usage ---
def meet_args(days: int = 30) -> list[str]:
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    return ["report", "meet", "user", "all", "start", start, "events", "call_ended"]


def school_of(ou: str, depth: int = 2) -> str:
    parts = [p for p in (ou or "/").split("/") if p]
    return "/" + "/".join(parts[:depth]) if parts else "/"


def meet_usage(rows: list[dict], users: list[dict], depth: int = 2) -> list[dict]:
    ou_of = {u["email"].lower(): u.get("ou", "") for u in users}
    by = defaultdict(lambda: {"meetings": set(), "people": 0, "minutes": 0.0,
                              "outside": 0})
    for r in rows:
        low = {(k or "").lower(): v or "" for k, v in r.items()}
        org = (low.get("organizer_email") or low.get("actor.email") or "").lower()
        conf = low.get("conference_id") or low.get("meeting_code") or ""
        try:
            secs = float(low.get("duration_seconds") or 0)
        except ValueError:
            secs = 0
        place = school_of(ou_of.get(org, ""), depth) if org in ou_of else "(outside / unknown)"
        b = by[place]
        if conf:
            b["meetings"].add(conf)
        b["people"] += 1
        b["minutes"] += secs / 60
        if (low.get("is_external") or "").lower() == "true":
            b["outside"] += 1
    out = [{"Organizer's org unit": k, "Meetings": str(len(v["meetings"])),
            "Participants": str(v["people"]), "Hours": f"{v['minutes'] / 60:.1f}",
            "Outside participants": str(v["outside"])}
           for k, v in sorted(by.items())]
    if out:
        out.append({"Organizer's org unit": "Total",
                    "Meetings": str(sum(int(x["Meetings"]) for x in out)),
                    "Participants": str(sum(int(x["Participants"]) for x in out)),
                    "Hours": f"{sum(float(x['Hours']) for x in out):.1f}",
                    "Outside participants": str(sum(int(x["Outside participants"])
                                                    for x in out))})
    return out


# ---------------------------------------------------------- app access ---
def tokens_args(ou: str) -> list[str]:
    ent = ["all", "users"] if ou in ("", "/") else ["ou_and_children", ou]
    return [*ent, "print", "tokens", "aggregateusersby", "clientid"]


def token_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = {(k or "").lower(): v or "" for k, v in r.items()}
        scopes = low.get("scopes", "")
        risky = [s for s in ("gmail", "drive", "classroom", "admin", "contacts")
                 if s in scopes.lower()]
        out.append({"App": low.get("displaytext", "") or low.get("clientid", ""),
                    "People": low.get("users", ""),
                    "Can reach": ", ".join(risky) or "basic profile",
                    "Client ID": low.get("clientid", "")})
    out.sort(key=lambda x: -int(x["People"] or 0))
    return out


def revoke_args(ou: str, client_id: str) -> list[str]:
    ent = ["all", "users"] if ou in ("", "/") else ["ou_and_children", ou]
    return [*ent, "delete", "tokens", "clientid", client_id]
