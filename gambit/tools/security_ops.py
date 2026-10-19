"""Security operations: lock down a compromised account, and fix risky Drive sharing."""

from __future__ import annotations

import datetime


def _low(r: dict) -> dict:
    return {(k or "").lower(): (v or "") for k, v in r.items()}


# ===================================================== hacked account ===
def look_args(email: str, days: int = 7) -> dict[str, list[str]]:
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    return {
        "filters": ["user", email, "print", "filters"],
        "delegates": ["user", email, "print", "delegates"],
        "forward": ["user", email, "print", "forward"],
        "sendas": ["user", email, "print", "sendas"],
        "logins": ["report", "login", "user", email, "start", start],
        "sent": ["user", email, "print", "messages", "query", f"in:sent newer_than:{days}d",
                 "headers", "date,to,subject", "max_to_print", "200"],
    }


CRITERIA = ("from", "to", "subject", "query", "negatedquery", "hasattachment", "size",
            "excludechats")
ACTIONS = ("forward", "trash", "archive", "markread", "neverspam", "label", "star",
           "important", "notimportant")


def risky_filter(r: dict) -> str:
    """Why a Gmail filter looks like an attacker's (or '')."""
    low = _low(r)
    why = []
    if low.get("forward"):
        why.append("forwards mail")
    if low.get("trash"):
        why.append("deletes mail")
    if low.get("archive") and (low.get("markread") or low.get("trash")):
        why.append("hides mail")
    elif low.get("archive"):
        why.append("skips the inbox")
    return ", ".join(why)


def filters(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        crit = "; ".join(low[k] for k in CRITERIA if low.get(k))
        act = "; ".join(low[k] for k in ACTIONS if low.get(k))
        out.append({"Filter ID": low.get("id", ""), "When": crit, "Does": act,
                    "Looks risky": risky_filter(r)})
    out.sort(key=lambda x: x["Looks risky"] == "")
    return out


def delegates(rows: list[dict]) -> list[str]:
    out = []
    for r in rows:
        low = _low(r)
        e = low.get("delegateaddress") or low.get("delegate") or ""
        if "@" in e:
            out.append(e)
    return out


def forwarding_on(rows: list[dict]) -> str:
    for r in rows:
        low = _low(r)
        if (low.get("forwardenabled") or "").lower() == "true":
            return low.get("forwardto", "") or low.get("emailaddress", "") or "on"
    return ""


def lockdown_steps(email: str, password: str, *, deprovision: bool = True,
                   forward_off: bool = True, filter_ids: list[str] = (),
                   delegate_list: list[str] = (), suspend: bool = False,
                   turnoff2sv: bool = False) -> list[tuple[str, list[str]]]:
    steps = [("Reset the password (they must choose a new one)",
              ["update", "user", email, "password", password, "changepassword", "on"]),
             ("Sign out of every device", ["user", email, "signout"])]
    if deprovision:
        a = ["user", email, "deprovision", "popimap"]
        if turnoff2sv:
            a.append("turnoff2sv")
        steps.append(("Remove app passwords, backup codes and app access; turn off POP/IMAP",
                      a))
    if forward_off:
        steps.append(("Turn off forwarding", ["user", email, "forward", "off"]))
    if filter_ids:
        steps.append((f"Delete {len(filter_ids)} Gmail filter(s)",
                      ["user", email, "delete", "filters", ",".join(filter_ids)]))
    for d in delegate_list:
        steps.append((f"Remove mailbox access for {d}",
                      ["user", email, "delete", "delegate", d]))
    if suspend:
        steps.append(("Suspend the account", ["update", "user", email, "suspended", "on"]))
    return steps


# ===================================================== sharing clean-up ===
def scan_args(who: str, ou: str, domain: str) -> list[str]:
    ent = ["user", who] if "@" in who else (["ou_and_children", ou] if ou and ou != "/"
                                            else ["all", "users"])
    return [*ent, "print", "filelist", "fields",
            "id,name,mimetype,owners.emailaddress,webviewlink,permissions",
            "pm", "type", "anyone", "em",
            "pm", "typelist", "user,group", "notdomainlist", domain, "em",
            "pmm", "or", "pmfilter", "oneitemperrow"]


def shares(rows: list[dict], domain: str) -> list[dict]:
    """One row per risky permission: owner, file, who, role, permission id."""
    out = []
    for r in rows:
        low = _low(r)
        owner = low.get("owner") or low.get("owners.0.emailaddress") or ""
        ptype = low.get("permission.type", "")
        pid = low.get("permission.id", "")
        if not pid or not ptype:
            continue
        who = low.get("permission.emailaddress") or low.get("permission.domain") or ""
        if ptype == "anyone":
            disc = low.get("permission.allowfilediscovery", "").lower() == "true"
            who = "Anyone on the internet (can search for it)" if disc else \
                "Anyone with the link"
        elif ptype in ("user", "group") and who.lower().endswith("@" + domain.lower()):
            continue
        out.append({"Owner": owner, "File": low.get("name", ""),
                    "Shared with": who, "Type": ptype, "Role": low.get("permission.role", ""),
                    "Link": low.get("webviewlink", ""), "File ID": low.get("id", ""),
                    "Permission ID": pid})
    out.sort(key=lambda x: (x["Type"] != "anyone", x["Owner"], x["File"]))
    return out


def fix_steps(row: dict, domain: str, mode: str) -> list[tuple[str, list[str]]]:
    """mode: 'domain' (anyone → district only) | 'remove'."""
    owner, fid, pid = row["Owner"], row["File ID"], row["Permission ID"]
    if not owner or not fid:
        return []
    out = []
    if mode == "domain" and row["Type"] == "anyone":
        role = row["Role"] if row["Role"] in ("reader", "commenter", "writer") else "reader"
        out.append((f"{row['File']}: share with {domain} only",
                    ["user", owner, "add", "drivefileacl", fid, "domain", domain, "role",
                     role, "withlink"]))
    out.append((f"{row['File']}: remove {row['Shared with']}",
                ["user", owner, "delete", "drivefileacl", fid, f"id:{pid}"]))
    return out
