"""Round 25: field check & SIS fill, saved search sheets, sharing, history, seniors,
clean-up by school, and the new GAM pages' commands."""

import datetime

import pytest

from gambit import (custom_fields as cf, device_insights as di, field_check as fc, ou_map,
                    saved_searches as ss, school_cleanup as scu, search_sheets as sh,
                    senior_checkout as sc)
from gambit.tools import workspace_extras as x

MAP = [{"path": "/Students", "type": "students", "school": "", "grade": ""},
       {"path": "/Students/Hancock Middle School", "type": "", "school":
        "Hancock Middle School", "grade": ""},
       {"path": "/Students/Hancock Middle School/7th Grade", "type": "", "school": "",
        "grade": "7"},
       {"path": "/Students/Hancock Middle School/8th Grade", "type": "", "school": "",
        "grade": "8"},
       {"path": "/Students/Hancock High School", "type": "", "school": "Hancock High School",
        "grade": ""},
       {"path": "/Students/Hancock High School/9th Grade", "type": "", "school": "",
        "grade": "9"},
       {"path": "/Graduates", "type": "former_students", "school": "", "grade": ""},
       {"path": "/Former Staff", "type": "former_staff", "school": "", "grade": ""},
       {"path": "/Staff/HMS", "type": "staff", "school": "Hancock Middle School", "grade": ""},
       {"path": "/Chromebooks/HMS", "type": "devices", "school": "Hancock Middle School",
        "grade": ""},
       {"path": "/Chromebooks/Lost", "type": "lost", "school": "", "grade": ""}]


@pytest.fixture
def themap(monkeypatch):
    monkeypatch.setattr(ou_map, "entries", lambda: [dict(e) for e in MAP])
    cf.save({"schemas": {"Student_Information": {"display": "", "fields": [
        {"name": "Grade", "display": "", "type": "STRING", "multi": False, "indexed": True},
        {"name": "Current_School", "display": "", "type": "STRING", "multi": False,
         "indexed": True},
        {"name": "Student_ID", "display": "", "type": "STRING", "multi": False,
         "indexed": True},
        {"name": "Graduation_Year", "display": "", "type": "STRING", "multi": False,
         "indexed": True}]}},
        "columns": ["Student_Information.Grade"], "in_lists": True})
    yield MAP
    cf.save({})


# ------------------------------------------------------------ field check ---
def test_grade_normalizing_and_styles():
    for v in ("7th Grade", "07", "7", "Grade 7", "seventh", "7th"):
        assert fc.norm_grade(v) == "7", v
    assert fc.norm_grade("Kindergarten") == "K" and fc.norm_grade("0") == "K"
    assert fc.grade_style(["7", "8", "6"]) == "number"
    assert fc.grade_style(["7th Grade", "8th Grade"]) == "ordinal"
    assert fc.format_grade("8", "ordinal") == "8th Grade"
    assert fc.format_grade("11", "ordinal short") == "11th"
    assert fc.format_grade("3", "grade n") == "Grade 3"


def test_school_matching():
    assert fc.same_school("Hancock Middle School", "Hancock Middle")
    assert fc.same_school("hancock middle school", "Hancock Middle School")
    assert not fc.same_school("Hancock Middle School", "Hancock High School")


def test_check_finds_mismatches_and_fixes(themap):
    rules = [{"field": "Student_Information.Grade", "against": "grade"},
             {"field": "Student_Information.Current_School", "against": "school"}]
    users = [
        {"primaryEmail": "a@x", "orgUnitPath": "/Students/Hancock Middle School/7th Grade",
         "customSchemas.Student_Information.Grade": "8th Grade",
         "customSchemas.Student_Information.Current_School": "Hancock Middle School"},
        {"primaryEmail": "b@x", "orgUnitPath": "/Students/Hancock Middle School/7th Grade",
         "customSchemas.Student_Information.Grade": "7th Grade",
         "customSchemas.Student_Information.Current_School": "Hancock Middle School"},
        {"primaryEmail": "c@x", "orgUnitPath": "/Students/Hancock Middle School/8th Grade",
         "customSchemas.Student_Information.Grade": "9th Grade",
         "customSchemas.Student_Information.Current_School": "Hancock High School"},
        {"primaryEmail": "d@x", "orgUnitPath": "/Students/Hancock Middle School/8th Grade"},
        {"primaryEmail": "s@x", "orgUnitPath": "/Staff/HMS"}]
    rows = fc.check(users, rules)
    by = {(r["email"], r["against"]): r for r in rows}
    assert ("b@x", "grade") not in by
    assert by[("a@x", "grade")]["move_to"] == "/Students/Hancock Middle School/8th Grade"
    assert by[("c@x", "school")]["move_to"] == "/Students/Hancock High School/9th Grade"
    assert by[("d@x", "grade")]["problem"] == "Field is empty"
    assert not any(r["email"] == "s@x" for r in rows)
    moves = fc.fix_commands(rows, "move")
    assert ["update", "user", "a@x", "ou", "/Students/Hancock Middle School/8th Grade"] in \
        [a for _l, a in moves]
    assert len([a for _l, a in moves if a[2] == "c@x"]) == 1     # one move per person
    fields = dict((a[2] + a[3], a[4]) for _l, a in fc.fix_commands(rows, "field"))
    assert fields["a@xStudent_Information.Grade"] == "7th Grade"
    assert fields["c@xStudent_Information.Current_School"] == "Hancock Middle School"


def test_fill_plan_and_commands(themap):
    from gambit.sis import Person
    people = [Person("001", "John", "Doe", "a@x", "07", "9", "Hancock Middle School"),
              Person("002", "Mary", "Jones", "", "8", "9", "Hancock Middle School"),
              Person("003", "Old", "Kid", "o@x", "8", "9", active=False)]
    raws = [{"Grad": "2032"}, {"Grad": "2031"}, {"Grad": "2030"}]
    users = [{"primaryEmail": "a@x", "customSchemas.Student_Information.Grade": "7th Grade",
              "customSchemas.Student_Information.Student_ID": ""},
             {"primaryEmail": "m@x", "customSchemas.Student_Information.Student_ID": "002",
              "customSchemas.Student_Information.Grade": "7th Grade"},
             {"primaryEmail": "o@x"}]
    cfg = {"fields": {"Student_Information.Grade": {"source": "@grade",
                                                    "format": "grade ordinal"},
                      "Student_Information.Student_ID": {"source": "@sis_id",
                                                         "format": "as is"},
                      "Student_Information.Graduation_Year": {"source": "Grad",
                                                              "format": "as is"}},
           "match_field": "Student_Information.Student_ID", "clear_blank": False}
    plan = fc.fill_plan(people, raws, users, cfg)
    got = {(c["email"], c["field"].split(".")[1]): c["new"] for c in plan}
    assert ("a@x", "Grade") not in got                       # 07 → 7th Grade: unchanged
    assert got[("a@x", "Student_ID")] == "001"
    assert got[("m@x", "Grade")] == "8th Grade"              # matched by student ID
    assert got[("m@x", "Graduation_Year")] == "2031"
    assert not any(c["email"] == "o@x" for c in plan)        # inactive in the roster
    steps = fc.fill_commands(plan)
    a = next(args for _l, args in steps if args[2] == "a@x")
    assert a[:3] == ["update", "user", "a@x"] and "Student_Information.Student_ID" in a


def test_guess_rules(themap):
    g = fc.guess_rules()
    assert {"field": "Student_Information.Grade", "against": "grade"} in g
    assert {"field": "Student_Information.Current_School", "against": "school"} in g


# -------------------------------------------------------- search sheets ---
def test_saved_search_build_and_sheet_refresh(themap):
    spec = {"mode": "In org unit(s)", "ous": ["/A", "/B"], "children": False, "value": ""}
    cmds, keep = ss.build(spec)
    assert len(cmds) == 2 and cmds[0][-2:] == ["custom", "Student_Information"]
    assert keep({"orgUnitPath": "/A"}) and not keep({"orgUnitPath": "/A/x"})
    calls = []

    def run_csv(a):
        calls.append(a)
        ou = a[3].split("'")[1]
        return 0, [{"primaryEmail": f"{ou[1:].lower()}@x", "orgUnitPath": ou,
                    "customSchemas.Student_Information.Grade": "7"}], ""
    written = {}
    fav = {"kind": "search", "value": "search:1", "label": "T", "spec": spec,
           "sheet": {"url": "https://docs.google.com/spreadsheets/d/" + "x" * 30, "tab": "T"}}
    n = sh.refresh(fav, run_csv, lambda u, t, h, r: written.update(h=h, r=r, t=t))
    assert n == 2 and written["t"] == "T" and "Grade" in written["h"]
    assert len(calls) == 2


def test_run_all_records_results(monkeypatch, themap):
    from gambit.settings import settings
    import json
    url = "https://docs.google.com/spreadsheets/d/" + "y" * 30
    settings.set("favorites", json.dumps([
        {"kind": "search", "value": "search:ok", "label": "OK", "sheet": {"url": url},
         "spec": {"mode": "Everyone"}},
        {"kind": "search", "value": "search:bad", "label": "Bad", "sheet": {"url": url},
         "spec": {"mode": "Custom query", "value": "x"}},
        {"kind": "search", "value": "search:none", "label": "No sheet",
         "spec": {"mode": "Everyone"}}]))

    def run_csv(a):
        if "query" in a:
            return 2, [], "ERROR: bad query"
        return 0, [{"primaryEmail": "a@x"}], ""
    try:
        bad = sh.run_all(lambda *_: None, run_csv, lambda *a: None)
        assert bad == 1
        f = {x["value"]: x for x in json.loads(settings.get("favorites"))}
        assert f["search:ok"]["sheet"]["last_rows"] == 1 and not f["search:ok"]["sheet"][
            "error"]
        assert "bad query" in f["search:bad"]["sheet"]["error"]
        assert "sheet" not in f["search:none"]
    finally:
        settings.set("favorites", "[]")


# --------------------------------------------------------------- sharing ---
def _cros(sn, user, recent, ou="/Chromebooks/HMS", loc=""):
    r = {"deviceId": sn.lower(), "serialNumber": sn, "annotatedUser": user,
         "annotatedLocation": loc, "orgUnitPath": ou, "status": "ACTIVE"}
    for i, e in enumerate(recent):
        r[f"recentUsers.{i}.email"] = e
    return r


def test_sharing_report(themap):
    rows = [_cros("A1", "s1@x", ["s2@x", "s1@x"]),
            _cros("A2", "s2@x", ["s2@x"]),
            _cros("A3", "", ["s3@x", "s4@x", "s5@x"]),
            _cros("C1", "", ["s6@x", "s7@x", "s8@x", "s9@x"], loc="Cart 2"),
            _cros("L1", "s1@x", ["s9@x"], ou="/Chromebooks/HMS/Loaners")]
    out = di.sharing(di.devices(rows), None, 3)
    kinds = {(r["kind"], r["serial"]) for r in out}
    assert ("Used by someone else", "A1") in kinds
    assert ("Many students", "A3") in kinds
    assert not any(r["serial"] == "C1" for r in out)              # a cart
    assert not any(r["serial"] == "L1" for r in out)              # loaners
    several = next(r for r in out if r["kind"] == "Student on several Chromebooks")
    assert several["student"] == "s2@x" and "A1" in several["serial"]
    fix = di.assign_fix(out)
    assert fix == [("A1: assigned user → s2@x", ["cros_sn", "A1", "update", "user", "s2@x"])]


def test_history_builds_up(monkeypatch, tmp_path):
    monkeypatch.setattr(di, "_path", lambda: str(tmp_path / "h.json"))
    assert di.remember([_cros("A1", "s1@x", ["s1@x", "old@x"])], "2026-09-01") >= 3
    assert di.remember([_cros("A1", "s1@x", ["s1@x"])], "2026-09-02") == 0
    di.remember([_cros("A1", "s2@x", ["s2@x"], ou="/Chromebooks/HHS")], "2026-10-01")
    rows = di.history_for("a1", loans=[{"serial": "A1", "user": "s1@x", "out": "2026-09-15",
                                        "due": "2026-09-20", "returned": "2026-09-19"}],
                          repairs=[{"n": 4, "serial": "A1", "user": "s1@x", "history": [
                              {"date": "2026-09-10", "status": "Open", "note": "screen"}]}],
                          activity_entries=[])
    whats = [r["what"] for r in rows]
    assert rows[0]["date"] == "2026-10-01"
    assert "Loaner out" in whats and "Repair #4: Open" in whats
    assert "Used by (earlier)" in whats
    s1 = di.history_for("s1@x", activity_entries=[], loans=[], repairs=[])
    assert any(r["what"] == "Assigned to" for r in s1) and \
        any(r["what"] == "Assigned to" and r["detail"] == "s2@x" for r in s1)


# --------------------------------------------------------------- seniors ---
def test_senior_plan(themap):
    assert sc.guess_field() == "Student_Information.Graduation_Year"
    assert sc.graduates_ou() == "/Graduates"
    p = sc.plan([{"email": "a@x"}, {"email": "b@x"}],
                {"a@x": [{"serial": "A1", "user": "a@x", "recent_user": "", "asset": "",
                          "location": ""}]},
                {"year": "2026", "takeout": True, "collect_note": True,
                 "collect_by": "2026-05-22", "grad_ou": "/Graduates", "move_on": "2026-06-01",
                 "suspend_on": "2026-07-15", "sku": "1010310008"})
    assert sum(1 for lab, _a in p["now"] if lab.startswith("Takeout")) == 2
    assert ["cros_sn", "A1", "update", "updatenotes",
            "Collect – Class of 2026 by 2026-05-22\n#notes#"] in \
        [a for _l, a in p["now"]]
    when = {w: c for w, _t, c in p["later"]}
    assert ["update", "user", "a@x", "ou", "/Graduates"] in when["2026-06-01T06:00"]
    assert ["user", "b@x", "delete", "license", "1010310008"] in when["2026-07-15T06:00"]
    cmds, keep = sc.student_args("Student_Information.Graduation_Year", "2026")
    assert "Student_Information.Graduation_Year='2026'" in cmds[0]


def test_default_dates():
    d = sc.default_dates(datetime.date(2026, 10, 20))
    assert d["year"] == "2027" and d["suspend_on"] == "2027-07-15"


# ------------------------------------------------------- school clean-up ---
def test_school_cleanup(themap):
    today = datetime.date(2026, 10, 20)
    users = [
        {"primaryEmail": "idle@x", "orgUnitPath": "/Students/Hancock Middle School/7th Grade",
         "suspended": "False", "lastLoginTime": "2026-05-01T00:00:00Z",
         "creationTime": "2024-08-01T00:00:00Z"},
        {"primaryEmail": "never@x", "orgUnitPath": "/Staff/HMS", "suspended": "False",
         "lastLoginTime": "Never", "creationTime": "2026-08-01T00:00:00Z"},
        {"primaryEmail": "new@x", "orgUnitPath": "/Staff/HMS", "suspended": "False",
         "lastLoginTime": "Never", "creationTime": "2026-10-10T00:00:00Z"},
        {"primaryEmail": "gone@x", "orgUnitPath": "/Students/Hancock High School/9th Grade",
         "suspended": "True", "lastLoginTime": "", "creationTime": ""},
        {"primaryEmail": "ok@x", "orgUnitPath": "/Staff/HMS", "suspended": "False",
         "lastLoginTime": "2026-10-19T00:00:00Z", "creationTime": "2020-01-01"}]
    cros = [{"serialNumber": "OLD1", "orgUnitPath": "/Chromebooks/HMS", "status": "ACTIVE",
             "lastSync": "2026-07-01T00:00:00Z", "annotatedUser": "ok@x"},
            {"serialNumber": "S2", "orgUnitPath": "/Chromebooks/HMS", "status": "ACTIVE",
             "lastSync": "2026-10-19T00:00:00Z", "annotatedUser": "gone@x"},
            {"serialNumber": "L9", "orgUnitPath": "/Chromebooks/Lost", "status": "ACTIVE",
             "lastSync": "2025-01-01T00:00:00Z"}]
    rows = scu.build(users, cros, 60, 45, today)
    items = {(r["item"], r["fix"]) for r in rows}
    assert ("idle@x", "suspend") in items and ("never@x", "suspend") in items
    assert not any(r["item"] in ("new@x", "ok@x") for r in rows)
    assert ("gone@x", "move_former") in items
    assert ("OLD1", "move_lost") in items and ("S2", "clear_user") in items
    assert not any(r["item"] == "L9" for r in rows)
    cmds = dict((a[1] if a[0] == "cros_sn" else a[2], a) for _l, a in scu.commands(rows))
    assert cmds["gone@x"] == ["update", "user", "gone@x", "ou", "/Graduates"]
    assert cmds["OLD1"] == ["cros_sn", "OLD1", "update", "ou", "/Chromebooks/Lost"]
    assert cmds["S2"][-2:] == ["user", ""]
    sm = {s["school"]: s for s in scu.summary(rows)}
    assert sm["Hancock Middle School"]["total"] >= 3
    assert "idle@x" in scu.email_text("Hancock Middle School", rows)


def test_school_contacts():
    d = scu.save_contacts("Hancock High School = a@x\nbad line\nX = notanemail")
    assert d == {"Hancock High School": "a@x"} and scu.contacts() == d


# ------------------------------------------------------------ GAM pages ---
def test_sso_args():
    assert x.sso_create("/Students/HHS", "saml_sso", "inboundSamlSsoProfiles/abc") == [
        "create", "inboundssoassignment", "orgunit", "/Students/HHS", "mode", "saml_sso",
        "profile", "inboundSamlSsoProfiles/abc"]
    assert x.sso_create("", "sso_off", group="pilot@x", rank=2)[2:6] == ["group", "pilot@x",
                                                                         "rank", "2"]
    with pytest.raises(ValueError):
        x.sso_mode_args("saml_sso", "")
    assert x.assignment_name('{"name": "inboundSsoAssignments/Xy-1"}') == \
        "inboundSsoAssignments/Xy-1"
    assert x.sso_delete("/A") == ["delete", "inboundssoassignment", "orgunit:/A"]


def test_device_args():
    a = x.devices_args("windows", "company", "user:jdoe")
    assert a[:4] == ["print", "devices", "query", "type:windows user:jdoe"]
    assert "company" in a and a[-1] == "oneuserperrow"
    assert x.device_action("block", "devices/1/deviceUsers/2") == [
        "block", "deviceuser", "devices/1/deviceUsers/2", "doit"]
    assert x.device_action("wipe", "devices/1") == ["wipe", "device", "devices/1", "doit"]
    with pytest.raises(ValueError):
        x.device_action("approve", "devices/1")
    assert x.stale_devices([{"lastSyncTime": "2026-01-01T00:00"}, {"lastSyncTime":
                                                                     "2026-10-19"}], 30,
                           datetime.date(2026, 10, 20)) == [{"lastSyncTime": "2026-01-01T00:00"}]


def test_drive_chat_calendar_args():
    assert x.outside_args("hancockschools.net", "/Staff")[-6:] == [
        "typelist", "user,group", "notdomainlist", "hancockschools.net", "em",
        "oneitemperrow"]
    assert x.move_drive_args("admin@x", "0AB", "/Staff/HHS") == [
        "user", "admin@x", "update", "shareddrive", "0AB", "adminaccess", "ou", "/Staff/HHS"]
    assert x.post_args("me@x", "AAA", "hi") == ["user", "me@x", "create", "chatmessage",
                                                 "spaces/AAA", "text", "hi"]
    a = x.status_create(["ou", "/Staff/HHS"], "outofoffice", "2026-11-03", "2026-11-03",
                        message="PD day", summary="PD")
    assert a[:3] == ["ou", "/Staff/HHS", "create"] and a[-1] == "noreminders"
    assert ["range", "2026-11-03", "2026-11-03"] == a[-4:-1]
    w = x.status_create(["users", "a@x"], "workinglocation", "2026-11-03", "", where="office",
                        where_text="Central Office", start="08:00", end="12:00")
    assert w[3:6] == ["workinglocation", "office", "Central Office"]
    assert "timerange" in w and "2026-11-03T08:00:00" in w
    assert x.token_create("/Labs", 0) == ["create", "browsertoken", "ou", "/Labs"]
    assert x.profiles_args(90)[2] == "filter"


def test_headless_knows_the_new_tasks(monkeypatch):
    from gambit import headless, tasks_health
    monkeypatch.setattr("gambit.search_sheets.linked", lambda: [])
    assert headless.main(["--task", "searchsheets"]) == 0
    assert headless.main(["--task", "fieldsync"]) == 1       # not set up yet
    assert tasks_health.label_for("searchsheets") == "Saved search sheets"
    assert tasks_health.label_for("fieldsync") == "Custom fields from SIS"
