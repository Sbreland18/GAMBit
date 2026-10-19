"""Security baseline score: check the district's Google settings against a K-12 recommended
baseline, per org unit, with a fix list. Chrome policies can be fixed by GAMbit (through
Approvals); Admin console settings can only be read through Google's API, so those come with
a link to the right Admin console page.

The rules are data: change RULES (or the saved overrides) to match your district's policy."""

from __future__ import annotations

import json

from ..settings import settings

CONSOLE = "https://admin.google.com/ac/"
TASK = {"name": "GAMbit security baseline", "args": ["--task", "baseline"],
        "freq": "weekly", "time": "06:10",
        "what": "Scores your settings against the K-12 baseline; alerts if it drops",
        "standard": False}
# id, label, why, who (students|staff|all|devices), kind, setting, field, test, fix value,
# console path
RULES = [
    ("ext_share_students", "Students can't share Drive files outside the district",
     "Stops student work and data leaving the district by accident.", "students", "admin",
     "drive_and_docs.external_sharing", "externalSharingMode",
     {"in": ["DISALLOWED", "ALLOWLISTED_DOMAINS"]}, None, "appsettings/55656082996/sharing"),
    ("less_secure", "Less-secure apps are blocked", "Old apps that sign in with just a "
     "password are an easy way in.", "all", "admin", "security.less_secure_apps",
     "allowLessSecureApps", {"eq": False}, None, "security/lsa"),
    ("tsv_staff", "Staff must use 2-Step Verification", "Stops most stolen-password "
     "break-ins.", "staff", "admin", "security.two_step_verification_enforcement",
     "enforcedFrom", {"set": True}, None, "security/2sv"),
    ("forward_students", "Students can't auto-forward their email", "Forwarding is a common "
     "trick after an account is taken over.", "students", "admin", "gmail.auto_forwarding",
     "enableAutoForwarding", {"eq": False}, None, "apps/gmail/advancedsettings"),
    ("marketplace", "Only approved Marketplace apps can be installed", "Unvetted apps can "
     "read student data.", "all", "admin", "workspace_marketplace.apps_access_options",
     "accessLevel", {"in": ["ALLOW_LISTED_APPS", "ALLOW_NONE"]}, None,
     "apps/gsuitemarketplace/settings"),
    ("chat_external_students", "Students can't chat with people outside the district",
     "Protects students from contact by strangers.", "students", "admin",
     "chat.external_chat_restriction", "allowExternalChat", {"eq": False}, None,
     "apps/googlechat/chatsettings"),
    ("classroom_join", "Students can only join district classes", "Keeps classes inside the "
     "district.", "students", "admin", "classroom.class_membership", "whoCanJoinClasses",
     {"in": ["ANYONE_IN_DOMAIN", "ANYONE_IN_ALLOWLISTED_DOMAINS"]}, None,
     "apps/classroom/settings"),
    ("password_len", "Staff passwords are at least 8 characters", "Short passwords are "
     "guessed quickly.", "staff", "admin", "security.password", "minimumLength",
     {"min": 8}, None, "security/passwordmanagement"),
    ("safesearch", "SafeSearch is on for students", "Filters explicit search results "
     "(CIPA).", "students", "chrome", "chrome.users.SafeSearchRestrictedMode",
     "safeSearchRestrictedMode", {"eq": True}, "true", "chrome/settings/user"),
    ("youtube", "YouTube Restricted Mode is on for students", "Hides mature videos.",
     "students", "chrome", "chrome.users.SafeSearchRestrictedMode", "youtubeRestrictedMode",
     {"contains": ["STRICT", "MODERATE"]}, "MODERATE", "chrome/settings/user"),
    ("incognito", "Students can't use incognito windows", "Incognito skips browsing history "
     "and some filters.", "students", "chrome", "chrome.users.IncognitoMode",
     "incognitoModeAvailability", {"contains": ["UNAVAILABLE", "DISABLED"]}, "UNAVAILABLE",
     "chrome/settings/user"),
    ("guest", "Guest mode is off on Chromebooks", "Guest sessions aren't filtered or "
     "logged.", "devices", "chrome", "chrome.devices.GuestMode", "guestModeEnabled",
     {"eq": False}, "false", "chrome/settings/device"),
]


def options() -> dict:
    try:
        o = json.loads(settings.get("baseline/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"students": "/Students", "staff": "/Staff", "devices": "/", "off": [], **o}


def save_options(o: dict):
    settings.set("baseline/options", json.dumps(o))


def rules(o: dict | None = None) -> list[dict]:
    o = o or options()
    keys = ("id", "label", "why", "who", "kind", "setting", "field", "test", "fix", "console")
    return [dict(zip(keys, r)) for r in RULES if r[0] not in set(o.get("off", []))]


def _anc(ou: str, root: str) -> bool:
    ou, root = (ou or "/").rstrip("/") or "/", (root or "/").rstrip("/") or "/"
    return root == "/" or ou == root or ou.startswith(root + "/")


def admin_values(rows: list[dict]) -> list[dict]:
    """`print policies formatjson` → [{setting, ou, value}] (org-unit policies only)."""
    out = []
    for r in rows:
        try:
            p = json.loads(r.get("JSON") or "{}")
        except ValueError:
            continue
        st = ((p.get("setting") or {}).get("type") or "").replace("settings/", "")
        q = p.get("policyQuery") or {}
        if q.get("group") or q.get("groupEmail"):
            continue
        out.append({"setting": st, "ou": q.get("orgUnitPath") or "/",
                    "value": (p.get("setting") or {}).get("value") or {}})
    return out


def admin_effective(values: list[dict], setting: str, ou: str) -> dict | None:
    """The policy that applies to an org unit: the closest ancestor that sets it."""
    best = None
    for v in values:
        if v["setting"] == setting and _anc(ou, v["ou"]):
            if best is None or len(v["ou"].rstrip("/")) > len(best["ou"].rstrip("/")):
                best = v
    return best["value"] if best else None


def chrome_values(rows: list[dict]) -> dict:
    """`print chromepolicies ou X formatjson` (resolved) → {schema: {field: value}}"""
    out = {}
    for r in rows:
        try:
            p = json.loads(r.get("JSON") or "{}")
        except ValueError:
            continue
        out[p.get("name", "")] = {f.get("name"): f.get("value") for f in p.get("fields", [])}
    return out


def _get(value: dict, field: str):
    if not isinstance(value, dict):
        return None
    if field in value:
        return value[field]
    snake = "".join("_" + c.lower() if c.isupper() else c for c in field)
    return value.get(snake)


def passes(test: dict, v) -> bool:
    if v is None:
        return False
    if "eq" in test:
        if isinstance(test["eq"], bool):
            return str(v).lower() == str(test["eq"]).lower()
        return v == test["eq"]
    if "in" in test:
        return str(v).upper().split("_ENUM_")[-1] in test["in"] or str(v).upper() in test["in"]
    if "contains" in test:
        return any(x in str(v).upper() for x in test["contains"])
    if "min" in test:
        try:
            return int(v) >= test["min"]
        except (TypeError, ValueError):
            return False
    if "set" in test:
        return bool(v)
    return False


def check(rules_: list[dict], ous: dict, admin_rows: list[dict],
          chrome_by_ou: dict[str, list[dict]]) -> list[dict]:
    """ous = {"students": "/Students", "staff": "/Staff", "devices": "/"}"""
    admin = admin_values(admin_rows)
    chrome = {ou: chrome_values(rows) for ou, rows in chrome_by_ou.items()}
    out = []
    for r in rules_:
        targets = [ous["students"], ous["staff"]] if r["who"] == "all" else [ous[r["who"]]]
        for ou in dict.fromkeys(targets):
            if r["kind"] == "admin":
                val = _get(admin_effective(admin, r["setting"], ou) or {}, r["field"])
            else:
                val = _get(chrome.get(ou, {}).get(r["setting"], {}), r["field"])
            ok = passes(r["test"], val)
            fix = ["update", "chromepolicy", r["setting"], r["field"], r["fix"], "ou", ou] \
                if (r["kind"] == "chrome" and r["fix"] is not None and not ok) else None
            out.append({"Check": r["label"], "Org unit": ou, "Result": "✔ pass" if ok else
                        "✖ fix", "Now": "(not set)" if val is None else
                        json.dumps(val) if not isinstance(val, str) else val,
                        "Why": r["why"], "How to fix": "GAMbit can fix it" if fix else
                        (CONSOLE + r["console"] if not ok else ""), "args": fix,
                        "id": r["id"], "ok": ok})
    return out


def score(results: list[dict]) -> int:
    return round(100 * sum(r["ok"] for r in results) / len(results)) if results else 0


def args_needed(o: dict) -> list[tuple[str, list[str]]]:
    from .recovery import CI_ARGS
    ous = list(dict.fromkeys([o["students"], o["staff"], o["devices"]]))
    return [("admin", CI_ARGS)] + [(ou, ["print", "chromepolicies", "ou", ou, "formatjson"])
                                   for ou in ous]


def run(run_csv=None, o: dict | None = None) -> tuple[list[dict], int]:
    from ..directory import run_gam_csv
    run_csv = run_csv or (lambda a: run_gam_csv(a, 1800))
    o = o or options()
    admin_rows, chrome = [], {}
    for key, args in args_needed(o):
        c, rows, _e = run_csv(args)
        if key == "admin":
            admin_rows = rows if c == 0 else []
        else:
            chrome[key] = rows if c == 0 else []
    res = check(rules(o), {"students": o["students"], "staff": o["staff"],
                           "devices": o["devices"]}, admin_rows, chrome)
    sc = score(res)
    try:
        from .. import scorecard
        scorecard.record({"baseline_pct": sc})
    except Exception:  # noqa: BLE001
        pass
    return res, sc
