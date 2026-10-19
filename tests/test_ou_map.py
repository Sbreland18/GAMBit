"""The district org unit map (Settings & Updates → Org units & schools)."""

import pytest

from gambit import ou_map
from gambit.tools import assigned_users as au

OUS = ["/", "/StudentAccounts", "/StudentAccounts/Hancock High School",
       "/StudentAccounts/Hancock High School/9th Grade",
       "/StudentAccounts/Hancock High School/10th Grade",
       "/StudentAccounts/Hancock Middle School", "/StudentAccounts/Hancock Middle School/8th Grade",
       "/StudentAccounts/Hancock Elementary", "/StudentAccounts/Hancock Elementary/Kindergarten",
       "/StudentAccounts/Graduated", "/Chrome Devices", "/Chrome Devices/Hancock High School",
       "/Chrome Devices/Hancock High School/Carts", "/Chrome Devices/HMS",
       "/Chrome Devices/Hancock Elementary Chromebooks", "/Chrome Devices/Loaners",
       "/Staff", "/Staff/Hancock High School", "/Former Staff", "/Service Accounts", "/Testing"]


@pytest.fixture
def mapped():
    ou_map.save(ou_map.suggest(OUS))
    yield
    ou_map.save([])


def test_suggest_finds_kinds_schools_and_grades():
    s = ou_map.suggest(OUS)
    c = lambda p: ou_map.classify(p, s)  # noqa: E731
    assert c("/StudentAccounts/Hancock High School/9th Grade/Room 3") == {
        "type": "students", "school": "Hancock High School", "grade": "9",
        "mapped_at": "/StudentAccounts"}
    assert c("/StudentAccounts/Graduated")["type"] == "former_students"
    assert c("/Chrome Devices/HMS")["school"] == "Hancock Middle School"      # initials
    assert c("/Chrome Devices/Hancock Elementary Chromebooks")["school"] == "Hancock Elementary"
    assert c("/Chrome Devices/Loaners")["type"] == "loaners"
    assert c("/Former Staff")["type"] == "former_staff"
    assert c("/Service Accounts")["type"] == "other"
    assert c("/Testing")["type"] == "test"
    assert c("/StudentAccounts/Hancock Elementary/Kindergarten")["grade"] == "K"
    assert ou_map.device_ou_for("Hancock High School", s) == "/Chrome Devices/Hancock High School"


@pytest.mark.parametrize("name,grade", [("9th Grade", "9"), ("Grade 10", "10"), ("K", "K"),
                                        ("Kindergarten", "K"), ("Pre-K", "PK"),
                                        ("Class of 2029", "Class of 2029"), ("Seniors", "12"),
                                        ("Freshmen", "9"), ("Library", "")])
def test_grade_names(name, grade):
    assert ou_map.grade_of_name(name) == grade


def test_merge_keeps_what_the_person_set():
    old = [{"path": "/Chrome Devices/HMS", "type": "devices", "school": "Middle", "grade": ""}]
    m = ou_map.merge(old, ou_map.suggest(OUS))
    hms = next(e for e in m if e["path"] == "/Chrome Devices/HMS")
    assert hms["school"] == "Middle"


def test_students_follow_the_map(mapped):
    assert ou_map.student_roots() == ["/StudentAccounts"]
    assert ou_map.is_student("/StudentAccounts/Hancock High School/9th Grade")
    assert not ou_map.is_student("/StudentAccounts/Graduated")
    assert not ou_map.is_student("/Staff/Hancock High School")
    assert ou_map.is_staff("/Staff/Hancock High School")


def test_student_root_guess_without_a_map():
    ou_map.save([])
    assert ou_map.student_roots(OUS) == ["/StudentAccounts"]
    assert ou_map.is_student("/StudentAccounts/Hancock High School/9th Grade", OUS)


def test_set_and_move_use_the_map(mapped):
    rows = [{"deviceId": "a", "serialNumber": "A", "orgUnitPath": "/Chrome Devices",
             "status": "ACTIVE", "recentUsers.0.email": "leia@hancockstudents.com",
             "lastSync": "2026-10-18"},
            {"deviceId": "b", "serialNumber": "B", "status": "ACTIVE",
             "orgUnitPath": "/Chrome Devices/Hancock High School/Carts",
             "recentUsers.0.email": "leia@hancockstudents.com", "lastSync": "2026-10-18"},
            {"deviceId": "c", "serialNumber": "C", "orgUnitPath": "/Chrome Devices/Loaners",
             "status": "ACTIVE", "recentUsers.0.email": "leia@hancockstudents.com",
             "lastSync": "2026-10-18"},
            {"deviceId": "d", "serialNumber": "D", "orgUnitPath": "/Chrome Devices",
             "status": "ACTIVE", "recentUsers.0.email": "kid@hancockstudents.com",
             "lastSync": "2026-10-18"}]
    users = [{"email": "leia@hancockstudents.com",
              "ou": "/StudentAccounts/Hancock High School/9th Grade"},
             {"email": "kid@hancockstudents.com", "ou": "/StudentAccounts/Somewhere Else"}]
    devs = au.devices(rows)
    s = {r["deviceId"]: r for r in au.plan_set(devs, users, None,
                                               {**au.options(), "blank_only": False})}
    assert s["a"]["plan"] == "Set"                    # the map knows she's a student
    p = {r["deviceId"]: r for r in au.plan_move(devs, users, {**au.move_options(),
                                                             "source": "map"}, OUS)}
    assert p["a"]["plan"] == "Move" and p["a"]["target"] == "/Chrome Devices/Hancock High School"
    assert p["b"]["plan"] == "Same"                   # a cart inside the school stays put
    assert p["c"]["plan"] == "Skip" and "loaner" in p["c"]["why"]
    assert p["d"]["plan"] == "Skip" and "no school" in p["d"]["why"]


def test_dialog_guess_and_save(qapp, mapped):
    from PySide6.QtCore import QObject, Signal

    from gambit.ui.ou_map_dialog import OUMapDialog

    class Dir(QObject):
        ous_changed = Signal()
        ous = OUS

    ou_map.save([])
    dlg = OUMapDialog(None, Dir())
    assert len(dlg.nodes) == len(OUS) - 1
    dlg.guess()
    assert "Hancock High School" in [dlg.sum_table.item(r, 0).text()
                                     for r in range(dlg.sum_table.rowCount())] \
        if hasattr(dlg.sum_table, "item") else True
    it = dlg.nodes["/staff/hancock high school"]
    dlg.tree.setCurrentItem(it)
    dlg.kind.setCurrentIndex(dlg.kind.findData("staff"))
    dlg.apply()
    dlg.save()
    assert ou_map.configured() and ou_map.is_staff("/Staff/Hancock High School")
    assert ou_map.device_ou_for("Hancock Middle School") == "/Chrome Devices/HMS"


def test_subgroups_are_not_schools():
    s = ou_map.suggest(["/Students", "/Students/2031", "/Students/Middle School",
                        "/Staff", "/Staff/Teachers", "/Staff/Admin", "/Chromebooks",
                        "/Chromebooks/Carts", "/Chromebooks/MS"])
    assert ou_map.schools(s) == ["Middle School"]
    assert ou_map.classify("/Students/2031", s)["grade"] == "Class of 2031"
    assert ou_map.device_ou_for("Middle School", s) == "/Chromebooks/MS"
