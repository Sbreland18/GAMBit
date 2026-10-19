"""People tools: recently deleted accounts, "send as" addresses, Google-managed dynamic
groups, and Chat-space alerts."""

from __future__ import annotations

import datetime

# ------------------------------------------------------ deleted users ---
DELETED_ARGS = ["print", "users", "deleted_only", "fields",
                "primaryemail,id,name,ou,deletiontime"]


def deleted(rows: list[dict]) -> list[dict]:
    out = []
    today = datetime.datetime.now(datetime.timezone.utc)
    for r in rows:
        low = {(k or "").lower(): v or "" for k, v in r.items()}
        when = low.get("deletiontime", "")
        left = ""
        try:
            t = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
            days = 20 - (today - t).days
            left = f"{max(days, 0)} day(s)" if days > 0 else "too late"
        except ValueError:
            pass
        out.append({"Email": low.get("primaryemail", ""), "Name": low.get("name.fullname", "")
                    or low.get("name", ""), "Org unit": low.get("orgunitpath", ""),
                    "Deleted": when.replace("T", " ")[:16], "Time left to restore": left,
                    "ID": low.get("id", "")})
    out.sort(key=lambda x: x["Deleted"], reverse=True)
    return out


def undelete_args(uid: str, ou: str = "") -> list[str]:
    args = ["undelete", "user", f"uid:{uid}"]
    if ou:
        args += ["ou", ou]
    return args


# ------------------------------------------------------------- send as ---
def sendas_args(users: list[str], address: str, name: str, reply_to: str = "",
                make_default: bool = False) -> list[list[str]]:
    out = []
    for u in users:
        a = ["user", u, "create", "sendas", address, "name", name, "treatasalias", "true"]
        if reply_to:
            a += ["replyto", reply_to]
        if make_default:
            a.append("default")
        out.append(a)
    return out


def remove_sendas_args(users: list[str], address: str) -> list[list[str]]:
    return [["user", u, "delete", "sendas", address] for u in users]


# ------------------------------------------------------ dynamic groups ---
def ou_query(ou_ids: list[str]) -> str:
    parts = [f"user.org_units.exists(org_unit, org_unit.org_unit_id==orgUnitId('{i}'))"
             for i in ou_ids if i]
    return " || ".join(parts)


def _q(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def build_query(ou_ids: list[str], title: str = "", department: str = "",
                exclude_suspended: bool = True, custom: str = "") -> str:
    parts = []
    q = ou_query(ou_ids)
    if q:
        parts.append(f"({q})" if " || " in q else q)
    if title:
        parts.append(f"user.organizations.exists(org, org.title=='{_q(title)}')")
    if department:
        parts.append(f"user.organizations.exists(org, org.department=='{_q(department)}')")
    if custom.strip():
        parts.append(f"({custom.strip()})")
    if exclude_suspended and parts:
        parts.append("user.suspended==false")
    return " && ".join(parts)


def dynamic_group_args(email: str, name: str, query: str, description: str = "") -> list[str]:
    args = ["create", "cigroup", email, "name", name]
    if description:
        args += ["description", description]
    return args + ["dynamic", query]


def ou_ids(rows: list[dict]) -> dict[str, str]:
    """`print ous fields orgunitpath,orgunitid` → {path: id without 'id:'}"""
    out = {}
    for r in rows:
        low = {(k or "").lower(): v or "" for k, v in r.items()}
        p, i = low.get("orgunitpath", ""), low.get("orgunitid", "")
        if p and i:
            out[p] = i.replace("id:", "")
    return out


# ------------------------------------------------------- chat alerts ---
def chat_args(space: str, text: str, as_user: str) -> list[str]:
    space = space.strip()
    if space.startswith("https://"):
        # https://chat.google.com/room/AAAA… → spaces/AAAA…
        space = "spaces/" + space.rstrip("/").split("/")[-1].split("?")[0]
    if not space.startswith("spaces/"):
        space = "spaces/" + space
    return ["user", as_user, "create", "chatmessage", "space", space, "text", text[:4000]]
