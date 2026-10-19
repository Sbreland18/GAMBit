import datetime
import json

from gambit import asset_register as ar, back_to_school as bts, delegation_review as dr
from gambit import next_year as ny, outside_changes as oc, recovery_coverage as rc
from gambit import scorecard, staff_card as sc, student_flags as sf
from gambit.tools import gam_extras3 as g3, group_hygiene as gh

TODAY = datetime.date(2026, 10, 15)
U = [{"email": "t1@s.org", "ou": "/Staff/Lincoln", "suspended": False},
     {"email": "t2@s.org", "ou": "/Staff/Grant", "suspended": False},
     {"email": "gone@s.org", "ou": "/Former/2026", "suspended": False},
     {"email": "sus@s.org", "ou": "/Staff/Lincoln", "suspended": True},
     {"email": "k1@s.org", "ou": "/Students/Lincoln/K", "suspended": False,
      "last_login": "2026-09-01T00:00:00Z"},
     {"email": "s5@s.org", "ou": "/Students/Lincoln/Grade 5", "suspended": False,
      "last_login": "Never"},
     {"email": "s6@s.org", "ou": "/Students/Grant/Class of 2033", "suspended": False,
      "last_login": "2026-09-01"},
     {"email": "s12@s.org", "ou": "/Students/High/12", "suspended": False,
      "last_login": "2026-09-01"}]


def test_gam_extras3():
    st = g3.stale_profiles([
        {"name": "customers/C/profiles/1", "userEmail": "t1@s.org",
         "lastActivityTime": "2026-01-01T00:00:00Z", "displayName": "PC1"},
        {"name": "customers/C/profiles/2", "userEmail": "sus@s.org",
         "lastActivityTime": "2026-10-14T00:00:00Z"},
        {"name": "customers/C/profiles/3", "userEmail": "t2@s.org",
         "lastActivityTime": "2026-10-14T00:00:00Z"}], 90, U, TODAY)
    assert [s["name"][-1] for s in st] == ["1", "2"]
    assert g3.delete_profile_args("x") == ["delete", "chromeprofile", "x"]
    assert g3.features([{"name": "Projector"}, {"name": "Doc camera"}]) == ["Doc camera",
                                                                             "Projector"]
    assert g3.resource_features_args("R1", ["A", "B"])[-1] == "A,B"
    cmds = g3.schedule_commands("t1@s.org", {"Mon": "Lincoln", "Wed": "Grant"},
                                datetime.date(2026, 10, 15), 10, {"Grant": "B2"})
    assert cmds[0][-2:] == ["2026-10-19", "10"] and "buildingid" in cmds[1]
    assert cmds[1][-2] == "2026-10-21"
    org = g3.organizers([{"name": "D1", "organizers": "gone@s.org t1@s.org"},
                         {"name": "D2", "organizers": "gone@s.org"}], {"gone@s.org"})
    assert org[0]["Shared drive"] == "D2" and org[0]["Active managers"] == 0
    assert g3.mailbox_stats([{"emailAddress": "a", "messagesTotal": "5"},
                             {"emailAddress": "b", "messagesTotal": "50"}])[0]["Person"] == "b"
    a = g3.sheetrange_args("me@s.org", "F", "'T'!A1", [["a", None]])
    assert json.loads(a[6])["values"] == [["a", ""]]
    assert g3.pad([["a"]], 3, 2) == [["a", ""], ["", ""], ["", ""]]
    assert g3.label_perm_add_args("L1", "g@s.org")[:4] == [
        "create", "classificationlabelpermission", "labels/L1", "group"]
    assert g3.tasks([{"title": "Grade", "due": "2026-10-20T00:00:00Z"}])[0]["Due"] == \
        "2026-10-20"


def test_student_flags():
    data = {"missing": [{}] * 6, "devices": [{"serialNumber": "A", "lastSync":
                                              "2026-10-10", "annotatedUser": "s5@s.org"}],
            "logins": [{"ipAddress": str(i)} for i in range(7)], "apps": [],
            "meet": [{"duration_seconds": "600"}], "ai": [], "guardians": []}
    f = sf.analyze("s5@s.org", data, {"last_login": "2026-09-01"},
                   [{"user": "s5@s.org", "opened": "x", "problem": "screen"}] * 2,
                   [{"Who": "s5@s.org", "Finding": "odd", "Status": "New"}], [], TODAY)
    lv = {x["Signal"]: x["Level"] for x in f}
    assert lv["Sign-ins"] == "high" and lv["Missing work"] == "high"
    assert lv["Sign-in places"] == "medium" and lv["Guardians"] == "medium"
    assert lv["Unusual activity"] == "high" and lv["Repairs"] == "medium"
    assert f[0]["Level"] == "high"
    assert "recent_user:s5@s.org" in sf.commands("s5@s.org")["devices"]


def test_staff_card():
    data = {"user": [{"primaryEmail": "t1@s.org", "isEnrolledIn2Sv": "False",
                      "licenses": "1010020020", "recoveryEmail": ""}],
            "admins": [{"role": "_SEED_ADMIN_ROLE"}], "asps": [{"asp.codeId": "1"}],
            "delegates": [{"delegateAddress": "t2@s.org"}],
            "forward": [{"forwardEnabled": "True", "forwardTo": "x@gmail.com"}],
            "apps": [{"clientId": "a"}, {"clientId": "b"}], "devices": [], "chromebooks": []}
    out = {r["Area"]: r for r in sc.analyze("t1@s.org", data)}
    assert out["2-Step Verification"]["Level"] == "high"
    assert out["Admin roles"]["Level"] == "medium"
    assert out["App passwords"]["Level"] == "high"
    assert "x@gmail.com" in out["Forwarding"]["Detail"]
    assert out["Connected apps"]["Detail"].startswith("2")
    assert "sharing" in sc.commands("a@s.org", True)


def test_back_to_school():
    devs = [{"user": "k1@s.org"}]
    g = [{"student": "k1@s.org", "kind": "guardian"}]
    prof = [{"emailAddress": "t1@s.org", "verifiedTeacher": "True"},
            {"emailAddress": "t2@s.org", "verifiedTeacher": "False"}]
    courses = [{"ownerEmail": "t1@s.org", "Aliases": "d:math-27"}]
    rows = bts.compute(U, devs, g, prof, courses, bts.options(), 2027)
    by = {r["School"]: r for r in rows}
    assert by["Lincoln"]["Students"] == 2 and by["Lincoln"]["Signed in"] == 50
    assert by["Lincoln"]["Chromebook assigned"] == 50 and by["Lincoln"]["Teachers verified"] \
        == 100 and by["Lincoln"]["Classes created"] == 1
    assert "Classes created" in by["Grant"]["Needs work"]
    assert bts.display(rows)[0]["Signed in"].endswith("%")


def test_trend_alerts():
    weeks = {f"2026-W{i:02d}": {"never": 10 + (i % 2), "tsv_pct": 90} for i in range(30, 38)}
    weeks["2026-W38"] = {"never": 40, "tsv_pct": 60}
    found = scorecard.trend_alerts({"weeks": weeks})
    assert {f["key"] for f in found} == {"never", "tsv_pct"}
    weeks["2026-W38"] = {"never": 9, "tsv_pct": 99}   # better, not alerts
    assert scorecard.trend_alerts({"weeks": weeks}) == []


def test_asset_register(tmp_path):
    p = tmp_path / "fin.csv"
    p.write_text("Serial Number,Asset Tag,Purchase Date,Cost,School\n"
                 "AAA,T1,2022-08-01,$300.00,Lincoln\nBBB,T2,08/01/2024,250,Grant\n"
                 "CCC,T3,2025-08-01,300,Grant\n", encoding="utf-8")
    fin, m = ar.read_finance(str(p))
    assert m["serial"] == "Serial Number" and fin[1]["purchased"] == datetime.date(2024, 8, 1)
    devs = [{"serial": "AAA", "asset": "T1", "ou": "/C", "user": "", "status": "ACTIVE",
             "aue": datetime.date(2026, 6, 1), "model": "M", "last_sync": None},
            {"serial": "BBB", "asset": "X9", "ou": "/C", "user": "", "status": "ACTIVE",
             "aue": None, "model": "M", "last_sync": None},
            {"serial": "DDD", "asset": "", "ou": "/C", "user": "", "status": "ACTIVE",
             "aue": None, "model": "M", "last_sync": None}]
    rec = ar.reconcile(fin, devs)
    assert [r["Problem"][:6] for r in rec] == ["Bought", "In Goo", "Asset "]
    assert ar.tag_fix_args({"BBB": "id9"}, rec[2]) == ["update", "cros", "id9", "assetid", "T2"]
    inv = ar.inventory(fin, devs, {"life_years": 5, "salvage": 0}, TODAY)
    a = next(r for r in inv if r["Serial"] == "AAA")
    assert a["Updates ended"] == "yes" and 0 < a["Book value"] < 300
    assert next(r for r in inv if r["Serial"] == "CCC")["Status"] == "NOT IN GOOGLE"
    assert ar.totals(inv)["devices"] == 4


def test_outside_changes():
    entries = [{"time": "2026-10-14T10:00:00", "change": True, "code": 0,
                "args": ["update", "user", "t1@s.org", "suspended", "on"], "command": "x"}]
    t_ours = datetime.datetime.fromisoformat("2026-10-14T10:02:00").astimezone(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    admin = [{"id.time": t_ours, "actor.email": "admin@s.org", "name": "SUSPEND_USER",
              "USER_EMAIL": "t1@s.org"},
             {"id.time": t_ours, "actor.email": "other@s.org", "name": "CHANGE_PASSWORD",
              "USER_EMAIL": "t2@s.org"},
             {"id.time": t_ours, "actor.email": "sync@s.org", "name": "CREATE_USER",
              "USER_EMAIL": "t9@s.org"}]
    out = oc.compare(admin, entries, {"ignore_actors": "sync@s.org", "ignore_events": ""})
    assert [o["Target"] for o in out] == ["t2@s.org"]
    assert oc.summary(out)[0]["Changes"] == 1


def test_recovery_coverage():
    rows = [{"primaryEmail": "a@s.org", "orgUnitPath": "/Staff/Lincoln", "recoveryPhone": "+1"},
            {"primaryEmail": "b@s.org", "orgUnitPath": "/Staff/Lincoln"},
            {"primaryEmail": "c@s.org", "orgUnitPath": "/Staff/Grant", "recoveryEmail": "x@y"},
            {"primaryEmail": "d@s.org", "orgUnitPath": "/Students/X"}]
    ppl = rc.people(rows, rc.options())
    cov = rc.coverage(ppl)
    assert cov[-1] == {"Building": "Everyone", "People": 3, "Covered": 2, "Missing": 1,
                       "%": 67, "Phone": 1, "Email": 1}
    assert [m["Person"] for m in rc.missing(ppl)] == ["b@s.org"]
    cmd = rc.reminder_commands(["b@s.org"], rc.options(), "it@s.org")[0]
    assert cmd[3:5] == ["bcc", "b@s.org"] and rc.LINK in cmd[-1]


def test_next_year():
    assert ny.grade_of("/Students/A/Grade 5", 2027) == 5
    assert ny.grade_of("/Students/A/Class of 2033", 2027) == 6
    assert ny.grade_of("/Students/A/K", 2027) == 0
    assert ny.grade_of("/Students/A/12th Grade", 2027) == 12
    assert ny.grade_of("/Students/A", 2027) is None
    opts = {**ny.options(), "feeds": "Lincoln = Grant", "kinder": "Lincoln = 3"}
    rows, info = ny.project(U, opts, 2027)
    by = {r["School"]: r for r in rows}
    assert info["graduating"] == 1
    assert by["Lincoln"]["Next year"] == 1 + 3          # K->1 stays, 5th moves, 3 new K
    assert by["Grant"]["Next year"] == 2 and by["Lincoln"]["Moving on"] == 1
    p = ny.plan(rows, {"Lincoln": 1, "Grant": 5}, {"ratio": 1, "spare_pct": 0}, 300)
    tot = p[-1]
    assert tot["School"] == "All schools" and tot["To buy"] == 3 and tot["Cost"] == 900
    assert ny.licenses(p, {"student_licenses": 4})["licenses_short"] == 2


def test_group_hygiene():
    rows = [{"group": "lincoln-staff@s.org", "email": "sus@s.org", "role": "MEMBER",
             "type": "USER"},
            {"group": "lincoln-staff@s.org", "email": "gone@s.org", "role": "MEMBER",
             "type": "USER"},
            {"group": "lincoln-staff@s.org", "email": "x@gmail.com", "role": "MEMBER",
             "type": "USER"},
            {"group": "lincoln-staff@s.org", "email": "t2@s.org", "role": "MEMBER",
             "type": "USER"},
            {"group": "lincoln-staff@s.org", "email": "sub@s.org", "role": "MEMBER",
             "type": "GROUP"},
            {"group": "sub@s.org", "email": "t1@s.org", "role": "MEMBER", "type": "USER"},
            {"group": "lincoln-staff@s.org", "email": "t1@s.org", "role": "MEMBER",
             "type": "USER"}]
    f = gh.check(rows, U, {**gh.options(), "school_groups": "lincoln-staff@s.org = Lincoln"})
    probs = {(x["Member"], x["Problem"].split(" (")[0]) for x in f}
    assert ("sus@s.org", "account suspended") in probs
    assert ("gone@s.org", "has left") in probs
    assert ("x@gmail.com", "outside address in a staff group") in probs
    assert ("t2@s.org", "works at Grant, not Lincoln") in probs
    assert ("t1@s.org", "also a member through a nested group") in probs
    assert f[0]["fix"][:4] == ["update", "group", "lincoln-staff@s.org", "remove"]
    assert gh.summary(f)[0]["Issues"] == 5


def test_delegation_review(team_dir):
    data = {"delegates": [{"User": "t1@s.org", "delegateAddress": "gone@s.org",
                           "delegationStatus": "accepted"},
                          {"User": "t1@s.org", "delegateAddress": "t2@s.org"}],
            "sendas": [{"User": "t1@s.org", "sendAsEmail": "t1@s.org", "isPrimary": "True"},
                       {"User": "t1@s.org", "sendAsEmail": "me@gmail.com"}],
            "calendar": [{"primaryEmail": "t2@s.org", "role": "writer", "scope.type": "user",
                          "scope.value": "t1@s.org"},
                         {"primaryEmail": "t2@s.org", "role": "reader", "scope.type": "user",
                          "scope.value": "t1@s.org"}]}
    e = dr.entries(data)
    assert len(e) == 4
    rv = dr.review(e, U)
    assert rv[0]["Who"] == "gone@s.org" and "left" in rv[0]["Flags"]
    assert any("works at Grant" in r["Flags"] for r in rv)
    assert any(r["kind"] == "sendas" and "outside" in r["Flags"] for r in rv)
    cal = next(r for r in rv if r["kind"] == "calendar")
    assert dr.remove_args(cal) == ["user", "t2@s.org", "delete", "calendaracls", "primary",
                                   "user:t1@s.org"]
    assert dr.commands({"root": "/Staff"})["calendar"][:2] == ["ou_and_children", "/Staff"]
    assert dr.due(TODAY)
    dr.sign_off(rv, {dr._key(rv[0]): "Remove"}, "me")
    assert not dr.due() and dr.history()[-1]["rows"][0]["Decision"] == "Remove"
    assert dr.new_since_last(rv) == set()
