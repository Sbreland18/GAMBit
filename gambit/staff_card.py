"""Staff card: one staff member's security and resource picture – 2-Step Verification,
admin roles, storage, outside sharing, devices, licenses (and premium use), app passwords,
mailbox access, forwarding and connected apps."""

from __future__ import annotations

import datetime


def commands(email: str, sharing: bool = False) -> dict[str, list[str]]:
    start = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    c = {
        "user": ["print", "users", "query", f"email:{email}", "fields",
                 "primaryemail,name,ou,suspended,isenrolledin2sv,isenforcedin2sv,"
                 "lastlogintime,creationtime,recoveryemail,recoveryphone", "licenses"],
        "admins": ["print", "admins", "user", email],
        "storage": ["report", "users", "user", email, "parameters",
                    "accounts:used_quota_in_mb,accounts:drive_used_quota_in_mb,"
                    "accounts:gmail_used_quota_in_mb"],
        "devices": ["print", "devices", "query", f"email:{email}", "fields",
                    "devicetype,model,serialnumber,lastsynctime"],
        "chromebooks": ["print", "cros", "query", f"user:{email}", "fields",
                        "serialnumber,model,lastsync"],
        "asps": ["user", email, "print", "asps", "oneitemperrow"],
        "delegates": ["user", email, "print", "delegates"],
        "forward": ["user", email, "print", "forward"],
        "apps": ["user", email, "print", "tokens"],
        "meet": ["report", "meet", "user", "all", "start", start, "events", "call_ended",
                 "filter", f"organizer_email=={email}"],
    }
    if sharing:
        c["sharing"] = ["user", email, "print", "filesharecounts", "excludetrashed",
                        "internaldomains", "all"]
    return c


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def analyze(email: str, data: dict, today: datetime.date | None = None) -> list[dict]:
    from .tools.budget import sku_name
    from .license_rightsize import PREMIUM
    today = today or datetime.date.today()
    out = []

    def add(area, detail, level="ok"):
        out.append({"Area": area, "Detail": detail, "Level": level})
    u = _low((data.get("user") or [{}])[0]) if data.get("user") else {}
    if u:
        tsv = u.get("isenrolledin2sv", "").lower() == "true"
        add("2-Step Verification", "on" if tsv else "OFF", "ok" if tsv else "high")
        rec = [x for x in ("recoveryemail", "recoveryphone") if u.get(x)]
        add("Account recovery", "recovery " + " and ".join(x[8:] for x in rec) if rec else
            "no recovery email or phone", "ok" if rec else "medium")
        skus = [s for k, v in u.items() if k.startswith("licenses") and "display" not in k and "count" not in k
                for s in v.split() if s]
        prem = [s for s in skus if s in PREMIUM]
        add("Licenses", ", ".join(sku_name(s) for s in skus) or "none")
        if prem and data.get("meet") is not None:
            people = {}
            for r in data["meet"]:
                low = _low(r)
                people.setdefault(low.get("meeting_code", ""), set()).add(
                    low.get("identifier", "") or low.get("display_name", ""))
            big = max((len(v) for v in people.values()), default=0)
            add("Premium use", f"largest meeting in 90 days: {big} people",
                "ok" if big > 100 else "medium")
        add("Last sign-in", u.get("lastlogintime", "")[:10] or "never")
    adm = data.get("admins")
    if adm is not None:
        roles = sorted({_low(r).get("role", "") for r in adm} - {""})
        add("Admin roles", ", ".join(roles) if roles else "none",
            "medium" if roles and u and u.get("isenrolledin2sv", "").lower() != "true"
            else "ok")
    st = data.get("storage")
    if st:
        low = _low(st[0])
        try:
            gb = float(low.get("accounts:used_quota_in_mb") or 0) / 1024
            add("Storage", f"{gb:.1f} GB (Drive {float(low.get('accounts:drive_used_quota_in_mb') or 0) / 1024:.1f}, Gmail {float(low.get('accounts:gmail_used_quota_in_mb') or 0) / 1024:.1f})")
        except ValueError:
            pass
    sh = data.get("sharing")
    if sh:
        low = sh[0]
        pub = int(float(low.get("anyone") or 0))
        link = int(float(low.get("anyoneWithLink") or 0))
        ext = sum(int(float(low.get(k) or 0)) for k in ("externalUser", "externalGroup",
                                                         "externalDomain"))
        add("Sharing", f"{pub} public, {link} anyone-with-link, {ext} shared with outsiders",
            "high" if pub else "medium" if link + ext > 20 else "ok")
    devs = (data.get("devices") or []) + (data.get("chromebooks") or [])
    if data.get("devices") is not None or data.get("chromebooks") is not None:
        names = [(_low(r).get("model") or _low(r).get("devicetype") or
                  _low(r).get("serialnumber", "")) for r in devs]
        add("Devices", ", ".join(n for n in names if n)[:200] or "none")
    a = data.get("asps")
    if a is not None:
        n = sum(1 for r in a if _low(r).get("asp.name") or _low(r).get("asp.codeid"))
        add("App passwords", str(n), "high" if n else "ok")
    d = data.get("delegates")
    if d is not None:
        who = [_low(r).get("delegateaddress", "") for r in d if _low(r).get("delegateaddress")]
        add("Mailbox access", ", ".join(who) if who else "nobody else", "medium" if who
            else "ok")
    f = data.get("forward")
    if f:
        low = _low(f[0])
        on = low.get("forwardenabled", "").lower() == "true" or low.get("enabled", "")\
            .lower() == "true"
        add("Forwarding", f"ON to {low.get('forwardto', '') or low.get('emailaddress', '')}"
            if on else "off", "medium" if on else "ok")
    ap = data.get("apps")
    if ap is not None:
        add("Connected apps", f"{len({_low(r).get('clientid') for r in ap})} app(s)")
    order = {"high": 0, "medium": 1, "ok": 2}
    return sorted(out, key=lambda x: order.get(x["Level"], 2))


def gather(email: str, run_csv, sharing: bool = False) -> list[dict]:
    data = {}
    for k, a in commands(email, sharing).items():
        try:
            c, rows, _e = run_csv(a)
        except Exception:  # noqa: BLE001
            c, rows = 1, []
        data[k] = rows if c == 0 else None
    return analyze(email, data)
