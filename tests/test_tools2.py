import datetime

from gambit import activity, offboard, team
from gambit.tools import more_tools as mt
from gambit.tools import security_ops as sec


def test_hacked_account():
    f = sec.filters([{"id": "f1", "from": "from boss@x.com", "forward": "forward evil@x.com"},
                     {"id": "f2", "query": "query invoice", "trash": "trash"},
                     {"id": "f3", "from": "from news@x.com", "label": "label News"}])
    assert f[0]["Looks risky"] == "forwards mail" and f[1]["Looks risky"] == "deletes mail"
    assert f[2]["Looks risky"] == "" and f[2]["When"] == "from news@x.com"
    assert sec.delegates([{"User": "a", "delegateAddress": "b@s.org"}]) == ["b@s.org"]
    assert sec.forwarding_on([{"forwardEnabled": "True", "forwardTo": "evil@x.com"}]) == \
        "evil@x.com"
    steps = sec.lockdown_steps("a@s.org", "pw", filter_ids=["f1", "f2"], delegate_list=["b@s.org"],
                               suspend=True)
    cmds = [s[1] for s in steps]
    assert cmds[0][:3] == ["update", "user", "a@s.org"] and "changepassword" in cmds[0]
    assert ["user", "a@s.org", "signout"] in cmds
    assert ["user", "a@s.org", "deprovision", "popimap"] in cmds
    assert ["user", "a@s.org", "delete", "filters", "f1,f2"] in cmds
    assert cmds[-1] == ["update", "user", "a@s.org", "suspended", "on"]
    look = sec.look_args("a@s.org")
    assert look["logins"][:3] == ["report", "login", "user"]


def test_sharing_fix():
    rows = [{"Owner": "t@s.org", "id": "F1", "name": "Test", "webViewLink": "L",
             "permission.id": "anyoneWithLink", "permission.type": "anyone",
             "permission.role": "reader"},
            {"Owner": "t@s.org", "id": "F2", "name": "Grades",
             "permission.id": "123", "permission.type": "user", "permission.role": "writer",
             "permission.emailAddress": "mom@gmail.com"},
            {"Owner": "t@s.org", "id": "F3", "name": "Internal",
             "permission.id": "9", "permission.type": "user", "permission.role": "writer",
             "permission.emailAddress": "x@s.org"}]
    sh = sec.shares(rows, "s.org")
    assert [r["File"] for r in sh] == ["Test", "Grades"]
    assert sh[0]["Shared with"] == "Anyone with the link"
    fix = sec.fix_steps(sh[0], "s.org", "domain")
    assert fix[0][1] == ["user", "t@s.org", "add", "drivefileacl", "F1", "domain", "s.org",
                         "role", "reader", "withlink"]
    assert fix[1][1][-1] == "id:anyoneWithLink"
    assert len(sec.fix_steps(sh[1], "s.org", "domain")) == 1
    assert "notdomainlist" in sec.scan_args("t@s.org", "", "s.org")


def test_drive_moves():
    a = mt.move_to_shared_drive_args("t@s.org", "FOLD", "SD1", "Math")
    assert a[:7] == ["user", "t@s.org", "move", "drivefile", "FOLD", "teamdriveparentid", "SD1"]
    assert a[7:9] == ["teamdriveparentname", "Math"]
    s = mt.copy_folder_steps("old@s.org", "FOLD", "new@s.org", "3rd Grade")
    assert s[0][1][2:4] == ["add", "drivefileacl"]
    assert s[1][1][:7] == ["user", "new@s.org", "copy", "drivefile", "FOLD", "newfilename",
                           "3rd Grade"] and "recursive" in s[1][1]


def test_directory_plan():
    current = mt.current_details([{
        "primaryEmail": "t@s.org", "relations.0.type": "manager",
        "relations.0.value": "old@s.org", "phones.0.type": "work", "phones.0.value": "555-0100",
        "organizations.0.title": "Teacher", "organizations.0.department": "Math",
        "externalIds.0.type": "organization", "externalIds.0.value": "E1"}])
    assert current["t@s.org"]["manager"] == "old@s.org"
    sheet = [{"Employee ID": "E1", "Supervisor Email": "new@s.org", "Phone": "(555) 0100",
              "Building": "Lincoln Elementary", "Room": "204", "Title": "Teacher"},
             {"Employee ID": "E9", "Supervisor Email": "x@s.org"}]
    m = mt.dir_mapping(list(sheet[0].keys()))
    assert m["id"] == "Employee ID" and m["manager"] == "Supervisor Email" and m["desk"] == "Room"
    plan = mt.dir_plan(sheet, m, current, "s.org", {"Lincoln Elementary": "lincoln-elementary"})
    p = plan[0]
    assert p["email"] == "t@s.org" and "phone" not in p["changes"]      # same digits
    assert p["args"][:6] == ["update", "user", "t@s.org", "relation", "manager", "new@s.org"]
    assert "buildingid" in p["args"] and "lincoln-elementary" in p["args"]
    assert "deskcode" in p["args"] and p["args"][-1] == "endlocation"
    assert plan[1]["args"] is None


def test_devices_usage_versions_groups():
    d = mt.devices([{"name": "devices/D1", "deviceType": "WINDOWS", "model": "Latitude",
                     "ownerType": "COMPANY", "user.name": "devices/D1/deviceUsers/U1",
                     "user.userEmail": "t@s.org", "user.managementState": "APPROVAL_PENDING"},
                    {"name": "devices/D2", "deviceType": "CHROME_OS"}])
    assert len(d) == 1 and d[0]["Status"] == "approval pending"
    assert mt.device_action_args("approve", d[0]) == ["approve", "deviceuser",
                                                      "devices/D1/deviceUsers/U1", "doit"]
    assert mt.device_action_args("wipe", d[0]) == ["wipe", "device", "devices/D1", "doit"]
    p = mt.usage_params([{"parameter": "gmail:num_30day_active_users"},
                         {"parameter": "drive:num_7day_active_users"},
                         {"parameter": "accounts:num_30day_logins"},
                         {"parameter": "gmail:num_emails_sent"}])
    assert p == ["accounts:num_30day_logins", "gmail:num_30day_active_users",
                 "drive:num_7day_active_users"]
    h, rows = mt.usage_table([{"date": "2026-09-06", "gmail:num_30day_active_users": "900"}])
    assert h == ["Week of", "Gmail active users"] and rows == [["2026-09-06", "900"]]
    today = datetime.date.today().isoformat()
    s = mt.school_usage([{"email": "t@s.org", "accounts:last_login_time": today + "T08:00:00Z",
                          "classroom:role": "TEACHER", "classroom:num_posts_created": "4"},
                         {"email": "k@s.org"}],
                        [{"email": "t@s.org", "ou": "/Staff/Lincoln"},
                         {"email": "k@s.org", "ou": "/Staff/Lincoln/Aides"}])
    assert s[0]["Accounts"] == "2" and s[0]["Signed in"] == "50%"
    assert mt.teacher_classroom([{"email": "t@s.org", "classroom:role": "TEACHER",
                                  "classroom:num_posts_created": "4"}])[0]["Posts (last 30 days)"] \
        == "4"
    v = mt.versions([{"version": "128.0.6613.1", "count": "10"},
                     {"version": "126.0.1.1", "count": "30"}])
    assert v[0]["Version"].startswith("128") and v[1]["Behind"] == "2 major version(s) behind"
    assert v[1]["Share"] == "75%"
    g = mt.risky_groups([{"email": "a@s.org", "allowExternalMembers": "True",
                          "whoCanPostMessage": "ANYONE_CAN_POST"},
                         {"email": "b@s.org", "allowExternalMembers": "False"}])
    assert len(g) == 1 and "anyone on the internet" in g[0]["Open to outsiders"]
    assert "recursive" in mt.members_recursive_args("g@s.org")


def test_vault_keep_contacts_bulk():
    a = mt.vault_count_args("M1", ["a@s.org"], "", "subject:report", "", "")
    assert a[:6] == ["print", "vaultcounts", "matter", "M1", "corpus", "mail"]
    assert a[6:8] == ["accounts", "a@s.org"]
    assert mt.holds_for([{"matterName": "Case", "name": "Hold 1", "orgUnitPath": "/Staff"}])[0][
        "Covers them through"] == "org unit /Staff"
    assert mt.share_notes_args("a@s.org", ["notes/1", "notes/2"], "b@s.org") == \
        ["user", "a@s.org", "create", "noteacl", "notes/1,notes/2", "user", "b@s.org"]
    plan = mt.contact_plan(mt.contacts_from_csv(mt.CONTACT_TEMPLATE),
                           [{"emails.0.value": "payroll@district.org"}])
    assert plan[0]["action"] == "same" and plan[1]["args"][:4] == ["create", "contact", "name",
                                                                  "ABC Bus Company"]
    assert mt.threaded(["csv", "f.csv", "gam", "x"], 20)[:3] == ["config", "num_threads", "20"]
    assert mt.threaded(["print", "users"], 20) == ["print", "users"]
    assert activity.is_change(mt.threaded(["csv", "f.csv", "gam", "x"], 20))


def test_offboarding_new_steps():
    opts = {**offboard.DEFAULTS, "steps": offboard.DEFAULTS["steps"] + ["looker", "archive"],
            "archive_group": "arch@s.org"}
    rec = offboard.build("t@s.org", "boss@s.org", {"groups": [], "licenses": []}, opts,
                         lambda n=12: "x" * n)
    allargs = [st["args"] for stg in rec["stages"] for st in stg["steps"]]
    assert any(a[2:4] == ["add", "datastudiopermissions"] for a in allargs)
    later = [st["args"] for st in rec["stages"][1]["steps"]]
    arch = next(a for a in later if "archive" in a)
    assert arch[:5] == ["user", "t@s.org", "archive", "messages", "arch@s.org"]
    assert later.index(arch) < next(i for i, a in enumerate(later) if "suspended" in a)


def test_roles_for_new_commands():
    assert "delete" in team.categorize(["wipe", "device", "devices/D1", "doit"])
    assert "passwords" in team.categorize(sec.lockdown_steps("a@s.org", "p")[0][1])
