"""“Check everything” about one person (Student lookup → Check everything).

One read of the account and their Chromebooks, then a list of findings. Each finding says
what's wrong in plain words and, when GAMbit can fix it, carries the GAM commands.
"""

from __future__ import annotations

import datetime

from . import ou_map

USER_FIELDS = ("primaryemail,name,suspended,suspensionreason,ou,lastlogintime,creationtime,"
               "changepasswordatnextlogin,isenrolledin2sv,isenforcedin2sv,archived")
CROS_FIELDS = "deviceid,serialnumber,annotatedassetid,annotateduser,orgunitpath,status,lastsync,recentusers"


def user_args(email: str) -> list[str]:
    from . import custom_fields as cf, field_check as fc
    a = ["print", "users", "query", f"email:{email}", "fields", USER_FIELDS, "licenses"]
    cols = [r["field"] for r in fc.rules()]
    if cols:
        a += ["custom", ",".join(cf.schema_names(cols))]
    return a


def assigned_args(email: str) -> list[str]:
    return ["print", "cros", "query", f"user:{email}", "fields", CROS_FIELDS, "listlimit", "3"]


def recent_args(email: str) -> list[str]:
    return ["print", "cros", "query", f"recent_user:{email}", "fields", CROS_FIELDS,
            "listlimit", "3"]


def _c(r: dict, *names) -> str:
    low = {(k or "").lower(): v for k, v in (r or {}).items()}
    for n in names:
        if low.get(n.lower()):
            return str(low[n.lower()]).strip()
    return ""


def _true(v) -> bool:
    return str(v).strip().lower() == "true"


def _date(s: str):
    s = (s or "")[:10]
    if not s or s.startswith("1970"):
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def _f(level, problem, detail="", fix="", commands=None, special=""):
    return {"level": level, "problem": problem, "detail": detail, "fix": fix,
            "commands": commands or [], "special": special}


def check(email: str, user: dict | None, assigned: list[dict], recent: list[dict],
          today: datetime.date | None = None, items=None) -> list[dict]:
    """→ findings, worst first. level: bad | warn | ok."""
    today = today or datetime.date.today()
    items = ou_map.entries() if items is None else items
    out = []
    if not user:
        return [_f("bad", "No Google account found", f"{email} doesn't exist (or was "
                   "deleted). Check the spelling, or Users → Recently deleted.")]
    ou = _c(user, "orgUnitPath") or "/"
    kind = ou_map.classify(ou, items)["type"]
    student = kind == "students"
    suspended = _true(_c(user, "suspended"))
    if suspended:
        reason = _c(user, "suspensionReason")
        why = reason or "set by an admin"
        out.append(_f("bad", "The account is suspended", f"Reason: {why}. They can't sign "
                      "in anywhere.", "Unsuspend",
                      [["update", "user", email, "suspended", "off"]]))
    if _true(_c(user, "archived")):
        out.append(_f("warn", "The account is archived", "Archived accounts can't sign in."))
    if kind in ("former_students", "former_staff") and not suspended:
        out.append(_f("warn", "Active account in a former org unit", f"{ou} is for people "
                      "who have left, but this account can still sign in."))
    elif not kind and ou_map.configured():
        out.append(_f("warn", "Org unit isn't in the org unit map", f"{ou} isn't mapped "
                      "in Settings → Org units & schools, so GAMbit can't tell its school."))
    if _true(_c(user, "changePasswordAtNextLogin")):
        out.append(_f("warn", "They must choose a new password at the next sign-in",
                      "Normal after a reset. If they keep getting asked, turn it off.",
                      "Turn it off", [["update", "user", email, "changepassword", "off"]]))
    last, created = _date(_c(user, "lastLoginTime")), _date(_c(user, "creationTime"))
    if last is None and created and (today - created).days >= 2 and not suspended:
        out.append(_f("warn", "They've never signed in", f"Account made {created}. They may "
                      "not know their password.", "Reset the password", special="reset"))
    elif last and (today - last).days > 30 and not suspended:
        out.append(_f("warn", f"No sign-in for {(today - last).days} days",
                      f"Last sign-in {last}."))
    if _true(_c(user, "isEnforcedIn2Sv")) and not _true(_c(user, "isEnrolledIn2Sv")):
        out.append(_f("bad", "2-Step Verification is required but not set up",
                      "Google will block their sign-in until they set it up. Backup codes "
                      "let them in once.", "Make backup codes",
                      [["user", email, "update", "backupcodes"]]))
    lic = _c(user, "Licenses", "LicensesDisplay")
    if "licenses" in {(k or "").lower() for k in user} and not lic and not suspended:
        out.append(_f("warn", "No Google Workspace license", "Some apps (Gmail, Meet "
                      "recordings…) may not work. Add one on the Licenses page."))
    # custom fields vs the org unit
    try:
        from . import field_check as fc
        rules = fc.rules()
        if rules and student:
            for r in fc.check([user], rules, items):
                cmds = fc.fix_commands([r], "move") or fc.fix_commands([r], "field")
                how = "Move to " + r["move_to"] if r.get("move_to") else \
                    f"Set {r['field'].split('.')[-1]} to “{fc.set_value_for(r)}”"
                out.append(_f("warn", r["problem"], f"Org unit {ou}.", how,
                              [a for _l, a in cmds][:1]))
    except Exception:  # noqa: BLE001
        pass
    # Chromebooks
    mine = [d for d in assigned if _c(d, "annotatedUser").lower() == email.lower()]
    for d in mine:
        sn = _c(d, "serialNumber")
        if _c(d, "status").upper() == "DISABLED":
            out.append(_f("bad", f"Their Chromebook {sn} is disabled", "It shows the "
                          "“disabled” screen until it's turned back on.", "Re-enable it",
                          [["cros_sn", sn, "update", "action", "reenable"]]))
        sync = _date(_c(d, "lastSync"))
        if sync and (today - sync).days > 30:
            out.append(_f("warn", f"Chromebook {sn} hasn't checked in for "
                          f"{(today - sync).days} days", f"Last seen {sync}."))
    if len(mine) > 1:
        out.append(_f("warn", f"{len(mine)} Chromebooks are assigned to them",
                      ", ".join(_c(d, "serialNumber") for d in mine)))
    if student and not mine:
        using = [d for d in recent if _c(d, "recentUsers.0.email").lower() == email.lower()]
        if using:
            sn = _c(using[0], "serialNumber")
            out.append(_f("warn", "No Chromebook is assigned to them",
                          f"They were the last to sign in to {sn}.", f"Assign {sn} to them",
                          [["cros_sn", sn, "update", "user", email]]))
        else:
            out.append(_f("warn", "No Chromebook is assigned to them",
                          "And they haven't signed in to one recently."))
    if not out:
        out.append(_f("ok", "Everything looks right", f"Active, in {ou}, signed in "
                      f"{last or 'never'}" + (f", Chromebook {_c(mine[0], 'serialNumber')}"
                                              if mine else "") + "."))
    rank = {"bad": 0, "warn": 1, "ok": 2}
    out.sort(key=lambda f: rank[f["level"]])
    return out


def run(email: str, run_csv=None) -> list[dict]:
    if run_csv is None:
        from .directory import run_gam_csv
        run_csv = (lambda a: run_gam_csv(a, 300))
    c, users, err = run_csv(user_args(email))
    if c != 0:
        raise RuntimeError("Couldn't read the account: " + (err or "")[-200:])
    user = next((u for u in users if _c(u, "primaryEmail").lower() == email.lower()), None)
    _c1, assigned, _e = run_csv(assigned_args(email))
    _c2, recent, _e = run_csv(recent_args(email))
    return check(email, user, assigned if _c1 == 0 else [], recent if _c2 == 0 else [])


def summary(email: str, findings: list[dict], fixed: list[str]) -> str:
    """For the ticket note."""
    lines = [f"GAMbit check for {email}:"]
    for f in findings:
        mark = "✔" if f["problem"] in fixed else ("•" if f["level"] != "ok" else "✔")
        lines.append(f"{mark} {f['problem']}" + (" – fixed" if f["problem"] in fixed else ""))
    return "\n".join(lines)
