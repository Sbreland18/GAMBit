import zipfile

from gambit import sis

USERS = """sourcedId,status,enabledUser,role,username,givenName,familyName,email,identifier,grades,orgSourcedIds
s1,active,true,student,,Ann-Marie,O'Hara,,10004,KG,org1
s2,active,true,student,,Bob,Smith,bsmith@school.org,10002,06,org2
s3,tobedeleted,true,student,,Gone,Kid,gone@school.org,10009,07,org2
t1,active,true,teacher,,Jane,Doe,jdoe@school.org,T1,,org2
"""
ORGS = "sourcedId,name\norg1,Hancock Elementary\norg2,Hancock Middle\n"
ACCOUNTS = [
    {"email": "bsmith@school.org", "name": "Robert Smith", "ou": "/Students/Hancock Middle/Grade 5",
     "suspended": False, "sis_id": ""},
    {"email": "gone@school.org", "name": "Gone Kid", "ou": "/Students/Hancock Middle/Grade 7",
     "suspended": False, "sis_id": "10009"},
    {"email": "other@school.org", "name": "Other", "ou": "/Students/Hancock Middle/Grade 7",
     "suspended": False, "sis_id": ""},
]


def _zip(tmp_path):
    p = tmp_path / "oneroster.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("users.csv", USERS)
        zf.writestr("orgs.csv", ORGS)
    return str(p)


def test_oneroster_plan(tmp_path):
    exp = sis.load_export(_zip(tmp_path), "ClassLink / OneRoster")
    assert exp.schools["org2"] == "Hancock Middle"
    mapping = sis.guess_mapping(exp.headers, "ClassLink / OneRoster")
    rules = sis.Rules(domain="school.org", year_end=2027, missing_means_withdrawn=False)
    people = sis.people_from_export(exp, mapping, rules)
    assert [p.first for p in people] == ["Ann-Marie", "Bob", "Gone"]   # teacher filtered out
    changes = {c.email: c for c in sis.plan(people, ACCOUNTS, rules)}
    new = next(c for c in changes.values() if c.action == "create")
    assert new.email == "annmarie.ohara39@school.org"
    assert "/Students/Hancock Elementary/Grade K" in new.commands[0]
    assert "changepassword" in new.commands[0] and \
        new.commands[0][new.commands[0].index("changepassword") + 1] == "on"
    upd = changes["bsmith@school.org"]
    assert upd.action == "update" and "/Students/Hancock Middle/Grade 6" in upd.commands[0]
    assert changes["gone@school.org"].action == "withdraw"
    assert "other@school.org" not in changes          # missing ≠ withdrawn when switched off


def test_missing_means_withdrawn(tmp_path):
    exp = sis.load_export(_zip(tmp_path), "ClassLink / OneRoster")
    rules = sis.Rules(domain="school.org", missing_means_withdrawn=True)
    people = sis.people_from_export(exp, sis.guess_mapping(exp.headers, "ClassLink / OneRoster"),
                                    rules)
    changes = {c.email: c for c in sis.plan(people, ACCOUNTS, rules)}
    assert changes["other@school.org"].action == "withdraw"
    cmd = changes["other@school.org"].commands[0]
    assert cmd[-2:] == ["ou", "/Students/Withdrawn"] and "suspended" in cmd


def test_staff_sheet_and_offboard(tmp_path):
    p = tmp_path / "staff.csv"
    p.write_text("Employee ID,First Name,Last Name,Email,Building,Title,Department,Status,"
                 "Supervisor Email\n"
                 "E1,Tom,Brady,,Central,Math Teacher,Math,Active,kwhite@school.org\n"
                 "E2,Jane,Doe,jdoe@school.org,Central,Teacher,Science,Terminated,"
                 "kwhite@school.org\n")
    exp = sis.load_export(str(p), "Staff sheet / HR export")
    assert sis.detect_format(exp.headers) == "Staff sheet / HR export"
    rules = sis.Rules.for_staff(domain="school.org", withdrawn_action="offboard")
    people = sis.people_from_export(exp, sis.guess_mapping(exp.headers,
                                                           "Staff sheet / HR export"), rules)
    accts = [{"email": "jdoe@school.org", "name": "Jane Doe", "ou": "/Staff/Teachers",
              "suspended": False}]
    ch = {c.email: c for c in sis.plan(people, accts, rules)}
    assert ch["tbrady@school.org"].action == "create"
    assert "organization" in ch["tbrady@school.org"].commands[0]
    leave = ch["jdoe@school.org"]
    assert leave.action == "withdraw" and leave.supervisor == "kwhite@school.org"
    assert leave.commands == [["offboard", "jdoe@school.org"]]


def test_test_mode_limits_changes():
    ch = [sis.Change("create", f"n{i}@school.org", "N", "", [["create", "user", f"n{i}@school.org",
                                                               "ou", "/Students/X"]])
          for i in range(5)]
    ch.append(sis.Change("update", "t@school.org", "T", "", [["update", "user", "t@school.org",
                                                               "ou", "/Students/Y"]]))
    ch.append(sis.Change("update", "real@school.org", "R", "", [["update", "user",
                                                                  "real@school.org"]]))
    accts = [{"email": "t@school.org", "ou": "/Test"}, {"email": "real@school.org",
                                                        "ou": "/Students"}]
    out = sis.limit_to_test_ou(ch, accts, "/Test")
    assert sum(c.action == "create" for c in out) == 3
    assert all("/Test" in c.commands[0] for c in out)
    assert "real@school.org" not in {c.email for c in out}
