"""Approved-apps check: compare the third-party apps students and staff have connected to
their Google accounts with the district's approved list (for example the apps you have data
privacy agreements for), and remove access to the rest in bulk – through Approvals."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict

from ..settings import settings

RISKY = ((r"mail\.google\.com", "read and send all Gmail"), (r"/auth/gmail", "Gmail"),
         (r"/auth/drive ", "all Google Drive files"),
         ("/auth/admin", "admin settings"), ("/auth/classroom", "Classroom"),
         ("/auth/contacts", "contacts"), ("/auth/calendar", "calendar"))


def tokens_args(scope: str = "all", ou: str = "") -> list[str]:
    ent = ["ou_and_children", ou] if scope == "ou" and ou else ["all", "users"]
    return [*ent, "print", "tokens"]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def parse_list(text: str) -> list[dict]:
    """CSV with an app name column and optionally client ID and status columns.
    A plain list of names (one per line) also works."""
    text = (text or "").lstrip("﻿")
    rows = list(csv.DictReader(io.StringIO(text)))
    out = []
    heads = {"app", "appname", "name", "product", "resource", "softwarename", "title",
             "clientid", "oauthclientid"}
    if rows and any(k and _norm(k) in heads for k in rows[0]):
        for r in rows:
            low = {_norm(k): (v or "").strip() for k, v in r.items() if k}
            name = next((low[k] for k in ("app", "appname", "name", "product", "resource",
                                          "softwarename", "title") if low.get(k)), "")
            cid = next((low[k] for k in ("clientid", "oauthclientid", "id") if low.get(k)), "")
            status = (low.get("status") or low.get("approval") or "approved").lower()
            if name or cid:
                item = {"name": name, "client_id": cid,
                        "status": "denied" if any(w in status for w in
                                                  ("den", "not", "reject", "block"))
                        else "approved"}
                # optional columns used by the public apps list
                for key, cands in (("purpose", ("purpose", "use", "description",
                                                "whatitsfor")),
                                   ("dpa", ("dpa", "dataprivacyagreement", "agreement",
                                            "ndpa", "contract")),
                                   ("privacy", ("privacy", "privacypolicy", "privacyurl"))):
                    v = next((low[k] for k in cands if low.get(k)), "")
                    if v:
                        item[key] = v
                out.append(item)
        return out
    for ln in text.splitlines():
        if ln.strip():
            out.append({"name": ln.strip(), "client_id": "", "status": "approved"})
    return out


def load_list() -> list[dict]:
    from .. import team
    d = team.read_shared("approved_apps.json") if team.folder() else {}
    if not d:
        try:
            d = json.loads(settings.get("apps/approved", "{}") or "{}")
        except ValueError:
            d = {}
    return d.get("apps", [])


def save_list(apps: list[dict]):
    from .. import team
    if team.folder():
        team.write_shared("approved_apps.json", {"apps": apps})
    settings.set("apps/approved", json.dumps({"apps": apps}))


def _status(name: str, cid: str, approved: list[dict]) -> str:
    n = _norm(name)
    for a in approved:
        if (a.get("client_id") and a["client_id"] == cid) or \
                (a.get("name") and _norm(a["name"]) and (_norm(a["name"]) == n or
                                                         (len(_norm(a["name"])) > 5 and
                                                          _norm(a["name"]) in n))):
            return a["status"]
    return "not on the list"


def summarize(rows: list[dict], approved: list[dict], users: list[dict],
              student_root: str = "/Students") -> list[dict]:
    ou_of = {u["email"].lower(): u.get("ou", "") for u in users}
    root = student_root.rstrip("/").lower() + "/"
    apps = defaultdict(lambda: {"name": "", "users": set(), "students": set(), "scopes": set()})
    for r in rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        cid = low.get("clientid", "")
        user = (low.get("user") or low.get("primaryemail") or "").lower()
        if not cid or not user:
            continue
        a = apps[cid]
        a["name"] = a["name"] or low.get("displaytext") or low.get("appname") or cid
        a["users"].add(user)
        if (ou_of.get(user, "") + "/").lower().startswith(root):
            a["students"].add(user)
        a["scopes"] |= set((low.get("scopes") or "").split())
    out = []
    for cid, a in apps.items():
        sc = " ".join(sorted(a["scopes"]))
        risky = sorted({label for pat, label in RISKY if re.search(pat, sc + " ")})
        out.append({"App": a["name"], "Client ID": cid, "Status": _status(a["name"], cid,
                                                                           approved),
                    "People": len(a["users"]), "Students": len(a["students"]),
                    "Can see": ", ".join(risky), "users": sorted(a["users"]),
                    "students": sorted(a["students"])})
    order = {"denied": 0, "not on the list": 1, "approved": 2}
    out.sort(key=lambda x: (order.get(x["Status"], 1), -x["Students"], -x["People"]))
    return out


def revoke_commands(app: dict, students_only: bool = False, size: int = 50) -> list:
    who = app["students"] if students_only else app["users"]
    return [["users", ",".join(who[i:i + size]), "delete", "tokens", "clientid",
             app["Client ID"]] for i in range(0, len(who), size)]
