"""Round 16 fixes: GAM field names, asset IDs, student org units, admin role list."""

import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNTAX = os.path.join(ROOT, "tests", "data", "GamCommands.txt")


def _names(text, tag):
    i = text.index(f"<{tag}> ::=")
    blk = text[i:text.index("\n\n", i)]
    return set(re.findall(r"[a-z0-9._]+", blk.split("::=")[1]))


def test_every_fields_list_uses_real_gam_field_names():
    """`print users … fields licenses` broke the time machine – GAM rejects any field it
    doesn't know, so check every fields list GAMbit sends against GAM's syntax file."""
    text = open(SYNTAX, encoding="utf-8").read()
    sets = {"users": _names(text, "UserFieldName"), "cros": _names(text, "CrOSFieldName"),
            "devices": _names(text, "DeviceFieldName"),
            "groups": _names(text, "GroupFieldName"),
            "courses": _names(text, "CourseFieldName"),
            "crostelemetry": _names(text, "CrOSTelemetryFieldName")}
    bad = []
    for f in glob.glob(os.path.join(ROOT, "gambit", "**", "*.py"), recursive=True):
        s = re.sub(r'"\s*\n\s*"', "", open(f, encoding="utf-8").read())
        for m in re.finditer(r'"print", "(cros|devices|users|groups|courses|crostelemetry)"'
                             r'([^\]]*?)"fields",\s*f?"([^"]+)"', s):
            for tok in m.group(3).split(","):
                if tok and "{" not in tok and tok not in sets[m.group(1)]:
                    bad.append((os.path.relpath(f, ROOT), m.group(1), tok))
    assert bad == []


def test_time_machine_and_budget_args():
    from gambit import timemachine
    from gambit.tools import budget
    assert timemachine.USERS_ARGS[-1] == "licenses" and "licenses" not in \
        timemachine.USERS_ARGS[3]
    assert budget.USERS_ARGS[-1] == "licenses"
    data = timemachine.build([{"primaryEmail": "a@d.org", "Licenses": "1010020020 1010310008",
                               "LicensesCount": "2", "LicensesDisplay": "x"}], [])
    assert data["a@d.org"]["licenses"] == ["1010020020", "1010310008"]


def test_asset_id_helpers():
    from gambit.ui.pages.devices import asset_query, shape_rows
    assert asset_query("HMS-0123") == "asset_id:HMS-0123"
    assert asset_query("Cart 2 #4") == 'asset_id:"Cart 2 #4"'
    heads, rows = shape_rows([{"serialNumber": "SN1", "annotatedAssetId": "HMS-0123",
                               "annotatedUser": "kid@d.org", "lastSync":
                               "2026-10-14T10:00:00.000Z", "deviceId": "d1",
                               "recentUsers.0.email": "kid@d.org"}])
    assert heads[:2] == ["Serial", "Asset ID"] and rows[0][:3] == ["SN1", "HMS-0123",
                                                                   "kid@d.org"]
    assert rows[0][heads.index("Last sync")] == "2026-10-14 10:00:00"
    assert rows[0][heads.index("deviceId")] == "d1"


def test_student_ous():
    from gambit.settings import settings
    from gambit.ui.pages.lookup_page import is_student_ou, student_ous
    settings.set("lookup/student_ous", "")
    assert student_ous() == ["/Students"]
    settings.set("lookup/student_ous", '["/K12/Students", "/Alt School"]')
    assert is_student_ou("/K12/Students/Grade 5", student_ous())
    assert not is_student_ou("/Staff/Teachers", student_ous())
    assert not is_student_ou("/K12/StudentsX", student_ous())
    settings.set("lookup/student_ous", "")


def test_admin_role_choices():
    from gambit.tools.admin_roles import role_choices
    base = role_choices([])
    assert base[0]["name"] == "_SEED_ADMIN_ROLE" and "Super Admin" in base[0]["label"]
    live = role_choices([{"roleName": "_HELP_DESK_ADMIN_ROLE", "isSystemRole": "True"},
                         {"roleName": "Lincoln Tech", "roleDescription": "Lincoln devices",
                          "isSystemRole": "False"}])
    names = [r["name"] for r in live]
    assert names == ["_HELP_DESK_ADMIN_ROLE", "Lincoln Tech"]
    assert "Lincoln devices" in live[1]["description"] and "custom" in live[1]["label"]


def test_named_field_constants():
    """FIELDS constants passed to `fields` (not caught by the literal check above)."""
    text = open(SYNTAX, encoding="utf-8").read()
    from gambit.tools import battery_forecast, lost_devices, test_readiness
    from gambit import fleet
    tele = _names(text, "CrOSTelemetryFieldName")
    cros = _names(text, "CrOSFieldName")
    assert set(battery_forecast.FIELDS.split(",")) <= tele
    for mod in (fleet, test_readiness):
        f = getattr(mod, "FIELDS", "")
        if f:
            assert set(f.split(",")) <= cros, mod.__name__
    f = getattr(lost_devices, "INFO_FIELDS", "")
    if f:
        assert set(f.split(",")) <= cros
