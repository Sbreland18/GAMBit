import json

from gambit import (alerts, classroom_year, compliance, fleet, group_rules, guardians,
                    policies, scheduler, selfservice)


def test_code39_known_value():
    # '*' start/stop + 'A' : narrow=1, wide=3 units
    bars = fleet.code39_bars("A")
    assert sum(w for _b, w in bars) == 3 * (6 + 3 * 3 + 1)


def test_inventory_and_aue():
    import datetime
    t = datetime.date.today()
    devs = [{"serial": "1", "location": "Cart 1", "ou": "/D", "status": "ACTIVE",
             "last_sync": t, "aue": t.replace(year=t.year + 2), "notes": "", "model": "M",
             "user": "", "recent_user": "", "asset": ""},
            {"serial": "2", "location": "Cart 1", "ou": "/D", "status": "ACTIVE",
             "last_sync": None, "aue": t.replace(year=t.year - 1), "notes": "MISSING",
             "model": "M", "user": "", "recent_user": "", "asset": ""}]
    inv = fleet.inventory(devs, "location", 30, {"Cart 1": 30})[0]
    assert inv["devices"] == 2 and inv["not_seen"] == 1 and inv["short"] == 28
    plan = fleet.aue_plan(devs, 300)
    assert plan[0]["year"] == "Already expired" and plan[0]["cost"] == 300


def test_loaners_and_repairs():
    loans = []
    rec, cmds = fleet.loaner_out(loans, "sn1", "kid@school.org", "2000-01-01", "me")
    assert cmds[0][:5] == ["cros_sn", "sn1", "update", "user", "kid@school.org"]
    assert fleet.overdue(loans) == [rec]
    back, _ = fleet.loaner_in(loans, "SN1")
    assert back["returned"]
    tickets = []
    t, _c = fleet.repair_open(tickets, "SN1", "screen", "me")
    assert t["n"] == 1 and fleet.repair_update(t, "Fixed", "ok", "me")
    assert fleet.repair_stats(tickets)[0]["tickets"] == 1


def test_group_rules_diff():
    users = [{"email": "a@s.org", "ou": "/S/G5", "title": "", "department": ""},
             {"email": "b@s.org", "ou": "/S/G5/X", "title": "", "department": ""},
             {"email": "c@s.org", "ou": "/S/G6", "title": "", "department": ""}]
    rule = {**group_rules.new_rule(), "group": "g@s.org", "ous": ["/S/G5"]}
    members = "group,email,role,type\ng,old@s.org,MEMBER,USER\ng,boss@s.org,OWNER,USER\n"
    adds, removes = group_rules.diff(rule, users, members)
    assert adds == ["a@s.org", "b@s.org"] and removes == ["old@s.org"]
    cmds = group_rules.commands(rule, adds, removes, True)
    assert cmds[0][:5] == ["update", "group", "g@s.org", "add", "member"]


def test_guardians_plan(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("Student Email,Guardian 1 Email,Parent Email\ns@x.org,mom@g.com,dad@g.com\n")
    links, _how = guardians.load_links(str(p))
    cur = guardians.parse_current("studentEmail,invitedEmailAddress,invitationId,state,"
                                  "creationTime\ns@x.org,mom@g.com,i1,PENDING,2026-01-01\n")
    inv, rem = guardians.plan(links, cur, {"s@x.org"})
    assert [i["guardian"] for i in inv] == ["dad@g.com"] and rem == []


def test_classroom_year(tmp_path):
    p = tmp_path / "sections.csv"
    p.write_text("Section ID,Course,Period,Subject,Room,Teacher email,Student email\n"
                 "BIO-3,Biology,3,Biology,204,t@x.org,a@x.org\n"
                 "BIO-3,Biology,3,Biology,204,t@x.org,b@x.org\n")
    secs, _how = classroom_year.load_sections(str(p))
    plan = classroom_year.plan(secs, set(), "{period} {subject} – {teacher} {year}",
                               "Period {period}", 2027, "2026-27")
    create = plan[0]["commands"][0]
    assert create[:4] == ["create", "course", "alias", "BIO-3-27"]
    assert plan[0]["commands"][-1][-1] == "a@x.org,b@x.org"
    assert classroom_year.archive_batches(["1", "2"])[0] == ["update", "courses", "1,2",
                                                              "state", "archived"]


def test_compliance_posts():
    rows = [{"id": "D1", "name": "A", "permission.emailAddress": "x@gmail.com",
             "permission.role": "writer", "permission.type": "user"}]
    assert compliance._nomanager_post(rows, "s.org")[0]["Shared drive"] == "A"
    assert "x@gmail.com" in compliance._outside_post(rows, "s.org")[0]["Outside members"]


def test_policies_matrix():
    t = policies.rows_to_settings("name,orgUnitPath,fields.0.value\n"
                                  "chrome.users.IncognitoMode,/A,DISABLED\n")
    heads, rows = policies.matrix(t + [("/B", "IncognitoMode", "ALLOWED")], ["/A", "/B"])
    assert rows[0][1] == "⚠ differs"


def test_scheduler_script(tmp_path):
    path = scheduler.build_script("Weekly 100% test", ["print users"], str(tmp_path),
                                  "p@s.org", "rows", "t@s.org", "admin@s.org")
    text = open(path, encoding="utf-8").read()
    assert "exit /b %FAILED%" in text and "%ROWS%" in text and "100%% test" in text


def test_alert_payloads():
    teams = alerts.payload("https://x.webhook.office.com/a", "hi")
    assert teams["attachments"][0]["contentType"].endswith("adaptive")
    assert alerts.payload("https://hooks.slack.com/x", "hi") == {"text": "*GAMbit*\nhi"}
    assert json.loads(json.dumps(alerts.payload("https://chat.googleapis.com/x", "hi")))


def test_selfservice_rules():
    assert selfservice.classify("Reset password") == "reset"
    assert selfservice.classify("Sign out of all devices") == "signout"
    users = {"t@s.org": {"ou": "/Staff", "suspended": False},
             "kid@s.org": {"ou": "/Students/G5", "suspended": False}}
    o = {"staff_root": "/Staff", "student_root": "/Students", "require_teacher": False}
    assert selfservice.check("t@s.org", "kid@s.org", users, o) == ""
    assert "isn't a student" in selfservice.check("t@s.org", "t@s.org", users, o)
