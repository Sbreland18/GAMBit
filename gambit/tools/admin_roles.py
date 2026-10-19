"""Google admin roles in plain English, for the Admin roles dropdown. Google's own list
(`gam print adminroles`) adds any custom roles and system roles not listed here."""

from __future__ import annotations

# role name → (friendly name, what it can do)
BUILTIN = {
    "_SEED_ADMIN_ROLE": ("Super Admin", "Everything in the Admin console, including billing, "
                         "security settings and making other admins. Give this to as few "
                         "people as possible, and always with 2-Step Verification."),
    "_USER_MANAGEMENT_ADMIN_ROLE": ("User Management Admin", "Create, change, rename, suspend "
                                    "and delete users (except admins), reset passwords and "
                                    "move people between org units."),
    "_HELP_DESK_ADMIN_ROLE": ("Help Desk Admin", "Look up user information and reset "
                              "non-admin passwords. Can't create, delete or move users."),
    "_GROUPS_ADMIN_ROLE": ("Groups Admin", "Create and delete groups, manage their members and "
                           "settings, and see users' names and org units."),
    "_SERVICES_ADMIN_ROLE": ("Services Admin", "Turn Google services (Gmail, Drive, Classroom…) "
                             "on or off and change their settings. Can't manage users."),
    "_MOBILE_ADMIN_ROLE": ("Mobile Admin", "Manage phones and tablets: approve, block and wipe "
                           "mobile devices and change mobile settings."),
}


def role_choices(rows: list[dict] | None = None) -> list[dict]:
    """→ [{name, label, description}] – built-in roles first, then anything else Google
    reports (custom roles show their description)."""
    out, seen = [], set()
    google = {}
    for r in rows or []:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        if low.get("rolename"):
            google[low["rolename"]] = low
    for name, (friendly, desc) in BUILTIN.items():
        if rows and name not in google:
            continue          # not offered in this domain
        out.append({"name": name, "label": f"{friendly}  ({name})", "description": desc})
        seen.add(name)
    for name, low in sorted(google.items(), key=lambda kv: kv[0].lower()):
        if name in seen:
            continue
        system = low.get("issystemrole", "").lower() == "true"
        desc = low.get("roledescription", "") or "No description."
        if low.get("issuperadminrole", "").lower() == "true":
            desc = "Super Admin level. " + desc
        friendly = name.strip("_").replace("_ROLE", "").replace("_", " ").title() \
            if name.startswith("_") else name
        out.append({"name": name, "label": f"{friendly}" + ("  (Google role)" if system
                                                            else "  (custom role)"),
                    "description": desc + "  Click “What can it do?” for its exact "
                    "privileges."})
    return out
