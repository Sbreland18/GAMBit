"""End-of-year checkout for graduating students (Workflows → Senior checkout).

Pick the class by its graduation-year custom field (or an org unit), and GAMbit builds the
whole checklist:

1. **Takeout reminder** – email each senior how to take their files with them (now).
2. **Chromebook collection** – note each senior's Chromebook ("Collect – Class of 2026")
   and start a collection on Chromebook fleet → Collections so returns are scanned in.
3. **Move to the graduates org unit** – on the date you pick (Run later).
4. **Suspend** – on a later date, after they've had time to use Takeout.
5. **Free the license** – with the suspension.

Dated steps go to Automation → Run later & freezes, so they can be reviewed or cancelled,
and everything follows approvals.
"""

from __future__ import annotations

import datetime

from . import custom_fields as cf
from . import ou_map

TAKEOUT_SUBJECT = "Before you graduate: save your school Google files"
TAKEOUT_BODY = (
    "Congratulations, Class of {year}!\n\n"
    "Your school Google account will be turned off on {suspend}. Before then you can copy "
    "your Gmail, Drive files, Photos and more to a personal account:\n\n"
    "1. Go to https://takeout.google.com while signed in to your school account.\n"
    "2. Choose what to export and click Next step.\n"
    "3. Pick “Add to Drive” of another account or download the .zip files.\n\n"
    "Or share files you want to keep with your personal Gmail and make a copy there.\n\n"
    "Please also return your school Chromebook and charger by {collect}.\n\n"
    "Thank you, and good luck!")


def guess_field() -> str:
    for s, sch in cf.config().get("schemas", {}).items():
        for f in sch.get("fields", []):
            n = f["name"].lower()
            if "graduat" in n or ("grad" in n and "grade" not in n and
                                  ("year" in n or "class" in n)) or n in ("classof", "class_of"):
                return f"{s}.{f['name']}"
    return ""


def graduates_ou() -> str:
    r = ou_map.roots("former_students")
    return r[0] if r else ""


def student_args(field: str, year: str, ou: str = "") -> tuple[list[list[str]], object]:
    """Commands that list the class, and a filter for the rows."""
    from . import saved_searches as ss
    if field:
        spec = {"mode": "Custom field", "cf_field": field, "cf_op": "is", "value": year,
                "ous": [ou] if ou else [], "children": True}
    else:
        spec = {"mode": "In org unit(s)", "ous": [ou], "children": True, "value": ""}
    return ss.build(spec)


def plan(students: list[dict], devices_by_user: dict[str, list[dict]], o: dict) -> dict:
    """o: year, grad_ou, move_on, suspend_on, sku, takeout, collect_note, collect_by.
    Returns {"now": [(label, args)], "later": [(when, title, [args…])], "devices": [...]}"""
    year = o.get("year", "")
    now, later, devs = [], [], []
    emails = [s["email"] for s in students if s.get("email")]
    if o.get("takeout"):
        from . import google_io
        body = TAKEOUT_BODY.format(year=year, suspend=o.get("suspend_on", "") or "soon",
                                   collect=o.get("collect_by", "") or "the last day")
        for e in emails:
            now.append((f"Takeout reminder to {e}",
                        google_io.email_args(e, TAKEOUT_SUBJECT, body)))
    if o.get("collect_note"):
        note = f"Collect – Class of {year}" + (f" by {o['collect_by']}" if o.get("collect_by")
                                               else "")
        for e in emails:
            for d in devices_by_user.get(e.lower(), []):
                devs.append(d)
                now.append((f"Note on {d['serial']} ({e}): {note}",
                            ["cros_sn", d["serial"], "update", "notes", note]))
    if o.get("grad_ou") and o.get("move_on") and emails:
        later.append((o["move_on"] + "T06:00", f"Class of {year}: move {len(emails)} to "
                      f"{o['grad_ou']}", [["update", "user", e, "ou", o["grad_ou"]]
                                          for e in emails]))
    if o.get("suspend_on") and emails:
        cmds = [["update", "user", e, "suspended", "on"] for e in emails]
        if o.get("sku"):
            cmds += [["user", e, "delete", "license", o["sku"]] for e in emails]
        later.append((o["suspend_on"] + "T06:00",
                      f"Class of {year}: suspend {len(emails)}" +
                      (" and free their licenses" if o.get("sku") else ""), cmds))
    return {"now": now, "later": later, "devices": devs}


def devices_by_user(rows: list[dict]) -> dict[str, list[dict]]:
    from . import fleet
    out: dict[str, list[dict]] = {}
    for d in fleet.devices(rows):
        u = (d.get("user") or "").lower()
        if u:
            out.setdefault(u, []).append(d)
    return out


def start_collection(year: str, devs: list[dict]) -> str:
    from . import fleet
    path = fleet.collection_path(fleet.data_dir())
    coll = fleet.new_collection(f"Class of {year} Chromebooks", devs, f"Class of {year}")
    fleet.save_collection(path, coll)
    return path


def default_dates(today: datetime.date | None = None) -> dict:
    today = today or datetime.date.today()
    y = today.year if today.month <= 7 else today.year + 1
    return {"year": str(y), "move_on": f"{y}-06-01", "suspend_on": f"{y}-07-15",
            "collect_by": f"{y}-05-22"}
