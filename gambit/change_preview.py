"""Before → after: what each change will do, field by field, read from Google first.

Understands the common changes (people: org unit, suspended, names, password, custom
fields; Chromebooks: org unit, assigned user, notes, location, asset ID, enable/disable).
Anything else is listed in plain English without a “before”.
"""

from __future__ import annotations

USER_ATTRS = {"ou": "Org unit", "org": "Org unit", "orgunitpath": "Org unit",
              "suspended": "Suspended", "firstname": "First name", "givenname": "First name",
              "lastname": "Last name", "familyname": "Last name",
              "password": "Password", "changepassword": "Must change password",
              "email": "Email address", "primaryemail": "Email address"}
USER_COLS = {"Org unit": "orgUnitPath", "Suspended": "suspended",
             "First name": "name.givenName", "Last name": "name.familyName",
             "Must change password": "changePasswordAtNextLogin",
             "Email address": "primaryEmail"}
CROS_ATTRS = {"ou": "Org unit", "org": "Org unit", "user": "Assigned user",
              "notes": "Notes", "location": "Location", "assetid": "Asset ID",
              "asset": "Asset ID"}
CROS_COLS = {"Org unit": "orgUnitPath", "Assigned user": "annotatedUser", "Notes": "notes",
             "Location": "annotatedLocation", "Asset ID": "annotatedAssetId",
             "Status": "status"}
ACTIONS = {"disable": "DISABLED", "reenable": "ACTIVE", "deprovision_same_model_replace":
           "DEPROVISIONED", "deprovision_retiring_device": "DEPROVISIONED"}


def _norm(v) -> str:
    s = str(v if v is not None else "").strip()
    return {"on": "True", "off": "False", "true": "True", "false": "False"}.get(s.lower(), s)


def parse(args: list[str]) -> list[dict]:
    """[{kind: user|cros, target, field, col, after}] for changes this module understands."""
    a = [str(x) for x in args]
    low = [x.lower() for x in a]
    out = []
    if low[:2] == ["update", "user"] and len(a) > 3:
        targets, rest = a[2].split(","), a[3:]
        kind = "user"
    elif low[:1] == ["users"] and low[2:4] == ["update", "user"]:
        targets, rest = a[1].split(","), a[4:]
        kind = "user"
    elif low[:1] == ["cros_sn"] and len(low) > 2 and low[2] == "update":
        targets, rest = a[1].split(","), a[3:]
        kind = "cros"
    else:
        return []
    i = 0
    while i < len(rest) - 1:
        k, v = rest[i].lower(), rest[i + 1]
        if kind == "user":
            if k in USER_ATTRS:
                field = USER_ATTRS[k]
                after = "(a new password)" if field == "Password" else _norm(v)
                col = USER_COLS.get(field, "")
            elif "." in rest[i] and not rest[i].startswith("-"):
                field, col, after = rest[i], "customSchemas." + rest[i], v
            else:
                i += 1
                continue
        else:
            if k == "action":
                field, col, after = "Status", "status", ACTIONS.get(v.lower(), v.upper())
            elif k in CROS_ATTRS:
                field = CROS_ATTRS[k]
                col, after = CROS_COLS[field], v
            else:
                i += 1
                continue
        for t in targets:
            if t.strip():
                out.append({"kind": kind, "target": t.strip(), "field": field, "col": col,
                            "after": after})
        i += 2
    return out


def read_args(kind: str, targets: list[str], custom: list[str]) -> list[list[str]]:
    if kind == "user":
        out = []
        for t in targets:
            a = ["print", "users", "query", f"email:{t}", "fields",
                 "primaryemail,name,ou,suspended,changepasswordatnextlogin"]
            if custom:
                a += ["custom", ",".join(sorted({c.split(".")[0] for c in custom}))]
            out.append(a)
        return out
    return [["cros_sn", ",".join(targets), "print", "cros", "fields",
             "serialnumber,orgunitpath,annotateduser,notes,annotatedlocation,annotatedassetid,"
             "status"]]


def preview(commands: list[list[str]], run_csv=None, limit: int = 40) -> list[dict]:
    """→ [{target, field, before, after, same}] (plus plain-English rows for the rest)."""
    from .activity import describe_any
    if run_csv is None:
        from .directory import run_gam_csv
        run_csv = (lambda a: run_gam_csv(a, 120))
    changes, other = [], []
    for c in commands:
        p = parse(c)
        if p:
            changes += p
        else:
            other.append({"target": "", "field": "", "before": "",
                          "after": describe_any([str(x) for x in c]) or " ".join(map(str, c)),
                          "same": False})
    changes = changes[:limit * 4]
    users = sorted({c["target"].lower() for c in changes if c["kind"] == "user"})[:limit]
    cros = sorted({c["target"] for c in changes if c["kind"] == "cros"})[:limit]
    custom = [c["col"][len("customSchemas."):] for c in changes
              if c["col"].startswith("customSchemas.")]
    now: dict = {}
    if users:
        for a in read_args("user", users, custom):
            code, rows, _e = run_csv(a)
            for r in rows if code == 0 else []:
                now[("user", (r.get("primaryEmail") or "").lower())] = r
    if cros:
        for a in read_args("cros", cros, []):
            code, rows, _e = run_csv(a)
            for r in rows if code == 0 else []:
                now[("cros", (r.get("serialNumber") or "").upper())] = r
    out = []
    for c in changes:
        key = ("user", c["target"].lower()) if c["kind"] == "user" else \
            ("cros", c["target"].upper())
        r = now.get(key)
        if r is None:
            before = "(not found)" if (users or cros) else ""
        elif c["field"] == "Password":
            before = "(their current password)"
        else:
            before = _norm(r.get(c["col"], ""))
            if not before and c["col"].startswith("customSchemas."):
                vals = [v for k, v in r.items() if (k or "").startswith(c["col"] + ".")
                        and (k or "").endswith(".value") and v]
                before = "; ".join(vals)
        out.append({"target": c["target"], "field": c["field"], "before": before or "(blank)",
                    "after": c["after"] or "(blank)",
                    "same": _norm(before) == _norm(c["after"]) and c["field"] != "Password"})
    return out + other
