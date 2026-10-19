"""Day-one readiness: for new staff (accounts created in the last few days, or starting soon
on the HR sheet), check the account, license, groups, email signature, Chromebook and
Classroom teacher access are ready. Gaps can be fixed in one go; HR and the supervisor get a
short email."""

from __future__ import annotations

import datetime
import json

from ..settings import settings

USERS_ARGS = ["print", "users", "fields",
              "primaryemail,name,ou,suspended,creationtime,lastlogintime,organizations",
              "licenses"]
TASK_NOTE = "day-one readiness"


def options() -> dict:
    try:
        o = json.loads(settings.get("readiness/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"staff_root": "/Staff", "days": 14, "classroom_group": "", "device": False,
            "hr_email": "", "notify": True, **o}


def save_options(o: dict):
    settings.set("readiness/options", json.dumps(o))


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _under(ou, root):
    ou, root = (ou or "/").rstrip("/").lower(), (root or "/").rstrip("/").lower()
    return ou == root or ou.startswith(root + "/") or root == ""


def new_staff(rows: list[dict], opts: dict, today: datetime.date | None = None) -> list:
    today = today or datetime.date.today()
    cut = (today - datetime.timedelta(days=int(opts.get("days", 14) or 14))).isoformat()
    out = []
    for r in rows:
        low = _low(r)
        e = low.get("primaryemail", "").lower()
        if not e or not _under(low.get("orgunitpath"), opts.get("staff_root", "/Staff")):
            continue
        created = low.get("creationtime", "")[:10]
        if created < cut:
            continue
        lic = []
        for k, v in low.items():
            if k.startswith("licenses") and "display" not in k and "count" not in k:
                lic += v.split()
        out.append({"email": e, "name": low.get("name.fullname", ""),
                    "ou": low.get("orgunitpath", ""), "created": created,
                    "suspended": low.get("suspended", "").lower() == "true",
                    "signed_in": bool(low.get("lastlogintime", "")) and
                    not low.get("lastlogintime", "").startswith(("Never", "1970")),
                    "licenses": lic, "title": low.get("organizations.0.title", ""),
                    "department": low.get("organizations.0.department", "")})
    return sorted(out, key=lambda p: p["created"], reverse=True)


def checks(p: dict, groups_have: set[str], has_signature: bool | None, has_device: bool | None,
           onboard_opts: dict, opts: dict, domain: str = "") -> list[dict]:
    """→ [{item, ok, fix: [(label, args)]}]"""
    from .. import onboard
    out = [{"item": "Account is active", "ok": not p["suspended"],
            "fix": [(f"Unsuspend {p['email']}", ["update", "user", p["email"], "suspended",
                                                 "off"])]}]
    lic = onboard_opts.get("license", "")
    if lic:
        ok = lic in p["licenses"]
        out.append({"item": f"License {lic}", "ok": ok,
                    "fix": [] if ok else [(f"Assign license {lic}",
                                           ["user", p["email"], "add", "license", lic])]})
    want = onboard.groups_for({"ou": p["ou"], "title": p["title"],
                               "department": p["department"]},
                              onboard.parse_groups(onboard_opts.get("groups", "")), domain)
    if opts.get("classroom_group"):
        want = want + [opts["classroom_group"]]
    for g in dict.fromkeys(want):
        ok = g.lower() in groups_have
        out.append({"item": f"In group {g}", "ok": ok,
                    "fix": [] if ok else [(f"Add to {g}", ["update", "group", g, "add",
                                                          "member", "user", p["email"]])]})
    if onboard_opts.get("signature") and has_signature is not None:
        fix = []
        if not has_signature:
            from ..signature import gam_args
            fix = [("Set email signature", gam_args(p["email"], onboard.signature_template()))]
        out.append({"item": "Email signature", "ok": has_signature, "fix": fix})
    if opts.get("device") and has_device is not None:
        out.append({"item": "Chromebook assigned", "ok": has_device, "fix": []})
    out.append({"item": "Has signed in", "ok": p["signed_in"], "fix": [], "info": True})
    return out


def summary(people: list[dict], results: dict) -> list[list[str]]:
    rows = []
    for p in people:
        cs = results.get(p["email"], [])
        need = [c for c in cs if not c["ok"] and not c.get("info")]
        rows.append([p["email"], p["name"], p["created"], p["ou"],
                     "✔ ready" if not need else f"✖ {len(need)} to fix",
                     "; ".join(c["item"] for c in need),
                     "yes" if p["signed_in"] else "not yet"])
    return rows


def email_text(p: dict, cs: list[dict]) -> str:
    lines = [f"Day-one check for {p['name'] or p['email']} ({p['email']}):", ""]
    for c in cs:
        lines.append(f"  {'✔' if c['ok'] else '✖'} {c['item']}")
    need = [c for c in cs if not c["ok"] and not c.get("info")]
    lines += ["", "Everything is ready." if not need else
              "The technology department is fixing the items marked ✖."]
    return "\n".join(lines)


def gather(people: list[dict], run_csv, opts: dict) -> tuple[dict, dict, dict]:
    """→ (groups per person, signature present per person, device per person)"""
    groups, sigs, devs = {}, {}, {}
    for p in people:
        c, rows, _e = run_csv(["print", "groups", "member", p["email"], "fields", "email"])
        groups[p["email"]] = {(_low(r).get("email") or "").lower() for r in rows} if c == 0 \
            else set()
        c, rows, _e = run_csv(["user", p["email"], "print", "signature"])
        sigs[p["email"]] = (any((_low(r).get("signature") or "").strip() for r in rows)
                            if c == 0 else None)
    if opts.get("device"):
        c, rows, _e = run_csv(["print", "cros", "fields", "serialnumber,annotateduser"])
        assigned = {(_low(r).get("annotateduser") or "").lower() for r in rows} if c == 0 \
            else None
        for p in people:
            devs[p["email"]] = (p["email"] in assigned) if assigned is not None else None
    return groups, sigs, devs
