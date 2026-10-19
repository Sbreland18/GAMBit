import json

from gambit import activity, team
from gambit.tools import calendar_class as cc
from gambit.tools import chrome, drive_extra as dx, investigate as inv, people, photos


def test_photos_match(tmp_path):
    users = [{"email": "jdoe@s.org", "sis_id": "104522"}, {"email": "ann@s.org", "sis_id": ""},
             {"email": "ann@t.org", "sis_id": ""}]
    for n in ("jdoe@s.org.jpg", "0104522.png", "ann.jpg", "nobody.jpg", "empty.jpg"):
        (tmp_path / n).write_bytes(b"" if n == "empty.jpg" else b"x" * 10)
    (tmp_path / "notes.txt").write_text("x")
    m = {x.path.split("/")[-1]: x for x in photos.match(photos.scan(str(tmp_path)), users)}
    assert "notes.txt" not in m
    assert m["jdoe@s.org.jpg"].email == "jdoe@s.org"
    assert m["0104522.png"].how == "SIS ID"
    assert "more than one" in m["ann.jpg"].problem
    assert m["nobody.jpg"].problem
    cmds = photos.commands(list(m.values()))
    assert len(cmds) == 2 and cmds[0][:4] == ["user", "jdoe@s.org", "update", "photo"]


def test_chrome_commands_and_health():
    ent = chrome.target(["A1", "B2"], "/X")
    assert ent == ["cros_sn", "A1,B2"]
    assert chrome.target([], "/Carts", False) == ["cros_ou", "/Carts"]
    a = chrome.command_args(ent, "remote_powerwash")
    assert a[2:5] == ["issuecommand", "command", "remote_powerwash"] and "doit" in a
    assert chrome.command_args(ent, "set_volume", 140)[5] == "100"
    rows = [{"serialNumber": "S1", "batteryInfo.0.designCapacity": "5000",
             "batteryStatusReport.0.fullChargeCapacity": "3000",
             "batteryStatusReport.0.cycleCount": "410",
             "storageInfo.totalDiskBytes": "32000000000",
             "storageInfo.availableDiskBytes": "1000000000"},
            {"serialNumber": "S2", "batteryInfo.0.designCapacity": "5000",
             "batteryStatusReport.0.fullChargeCapacity": "4900"}]
    h = chrome.health(rows)
    assert h[0]["Serial"] == "S1" and "battery 60%" in h[0]["Needs attention"]
    assert "storage 3% free" in h[0]["Needs attention"] and h[1]["Needs attention"] == ""


def test_apps_flag_and_printers():
    a = chrome.apps([{"appId": "x", "displayName": "Super VPN Free", "totalInstallCount": "3"},
                     {"appId": "y", "displayName": "Kami", "totalInstallCount": "900"}])
    assert a[0]["App"] == "Super VPN Free" and "vpn" in a[0]["Look at this"]
    want = chrome.printers_from_csv(chrome.PRINTER_TEMPLATE)
    assert want[0]["uri"] == "ipp://10.1.20.15"
    plan = chrome.printer_plan(want, [{"id": "p1", "displayName": "HS Room 204",
                                       "uri": "ipp://old"}])
    assert plan[0]["args"][:2] == ["create", "printer"] and "driverless" in plan[0]["args"]
    assert plan[1]["action"] == "update" and plan[1]["args"][2] == "p1"


def test_policy_schema_and_copy():
    schema = {"schemaName": "chrome.users.IncognitoMode", "policyDescription": "Incognito",
              "fieldDescriptions": [{"field": "incognitoModeAvailability", "description": "d",
                                     "knownValueDescriptions": [
                                         {"value": "INCOGNITO_MODE_AVAILABILITY_ENUM_DISABLED",
                                          "description": "Off"}]}]}
    s = chrome.parse_schemas([{"name": "customers/C/policySchemas/x",
                               "JSON": json.dumps(schema)}])
    assert s[0]["fields"][0]["values"][0][0] == "DISABLED"
    pol = {"name": "chrome.users.UrlBlocking", "direct": True,
           "fields": [{"name": "urlBlocklist", "value": "a.com,b.com"},
                      {"name": "complex", "value": "[{\"a\": 1}]"}]}
    plan, skipped = chrome.copy_plan([{"JSON": json.dumps(pol)},
                                      {"JSON": json.dumps({**pol, "direct": False})}], "/New")
    assert len(plan) == 1 and plan[0]["args"] == ["update", "chromepolicy",
                                                  "chrome.users.UrlBlocking", "urlBlocklist",
                                                  "a.com,b.com", "ou", "/New"]
    assert "complex" in skipped[0]


def test_investigations():
    assert inv.doc_id("https://docs.google.com/document/d/1AbCdEfGhIjKlMn/edit") == \
        "1AbCdEfGhIjKlMn"
    a = inv.report_args("drive", days=7, events="view,download", doc="1AbCdEfGhIjKlMn")
    assert a[:4] == ["report", "drive", "user", "all"] and "doc_id==1AbCdEfGhIjKlMn" in a
    a = inv.report_args("admin", admin_target="kid@s.org")
    assert a[2:4] == ["user", "all"] and "USER_EMAIL==kid@s.org" in a
    heads, rows = inv.tidy([{"id.time": "2026-10-01T10:00:00Z", "actor.email": "a@s.org",
                             "name": "view", "doc_title": "Test", "ipAddress": ""}])
    assert heads == ["When", "Who", "What", "File"] and rows[0][0] == "2026-10-01 10:00:00"
    users = [{"email": "t@s.org", "ou": "/Staff/Lincoln/Teachers"}]
    u = inv.meet_usage([{"organizer_email": "t@s.org", "conference_id": "c1",
                         "duration_seconds": "3600"},
                        {"organizer_email": "t@s.org", "conference_id": "c1",
                         "duration_seconds": "1800"}], users)
    assert u[0]["Organizer's org unit"] == "/Staff/Lincoln" and u[0]["Meetings"] == "1"
    assert u[0]["Hours"] == "1.5"
    t = inv.token_rows([{"clientId": "c", "displayText": "Quizlet", "users": "40",
                         "scopes": "https://www.googleapis.com/auth/drive"}])
    assert t[0]["Can reach"] == "drive"
    assert inv.revoke_args("/Students", "c") == ["ou_and_children", "/Students", "delete",
                                                 "tokens", "clientid", "c"]


def test_people_tools():
    d = people.deleted([{"primaryEmail": "a@s.org", "id": "123", "orgUnitPath": "/",
                         "deletionTime": "2000-01-01T00:00:00Z"}])
    assert d[0]["Time left to restore"] == "too late"
    assert people.undelete_args("123", "/Staff") == ["undelete", "user", "uid:123", "ou",
                                                     "/Staff"]
    q = people.build_query(["03abc", "03def"], title="Teacher")
    assert q.startswith("(user.org_units.exists") and " || " in q
    assert "org.title=='Teacher'" in q and q.endswith("user.suspended==false")
    assert people.ou_ids([{"orgUnitPath": "/A", "orgUnitId": "id:03abc"}]) == {"/A": "03abc"}
    assert people.chat_args("https://chat.google.com/room/AAAA123?cls=7", "hi", "me@s.org")[5] \
        == "spaces/AAAA123"
    s = people.sendas_args(["a@s.org"], "office@s.org", "Office")
    assert s[0][:5] == ["user", "a@s.org", "create", "sendas", "office@s.org"]


def test_calendar_and_classroom(qapp):
    import datetime
    a = cc.event_args(["ou", "/Staff"], "No school", allday=datetime.date(2026, 11, 3),
                      batch="b1")
    assert a[:5] == ["ou", "/Staff", "create", "event", "primary"]
    assert "allday" in a and a[-2:] == ["gambitbatch", "b1"]
    assert cc.remove_batch_args(["ou", "/Staff"], "b1")[-2:] == ["gambitbatch=b1", "doit"]
    cc.save_batch("b1", "No school", ["ou", "/Staff"], "2026-11-03")
    assert cc.batches()[0]["id"] == "b1"
    cc.forget_batch("b1")
    assert all(b["id"] != "b1" for b in cc.batches())
    assert "singleevents" in cc.cancel_future_args("x@s.org")
    works = [{"courseId": "1", "id": "w1", "title": "Essay", "dueDate.year": "2026",
              "dueDate.month": "10", "dueDate.day": "2"}]
    subs = [{"courseId": "1", "courseWorkId": "w1", "profile.emailAddress": "kid@s.org",
             "profile.name.fullName": "Kid A"}]
    rows = cc.missing(subs, works, [{"id": "1", "name": "English 9", "section": "P2"}])
    assert rows[0] == {"Class": "English 9 – P2", "Student": "kid@s.org", "Name": "Kid A",
                       "Assignment": "Essay", "Due": "2026-10-02"}
    assert cc.by_student(rows)[0]["Missing"] == "1"
    c = cc.copy_args("111", "222")
    assert c[:5] == ["update", "course", "222", "copyfrom", "111"] and "markpublishedasdraft" in c


def test_drive_extras():
    assert dx.file_ids("https://drive.google.com/drive/folders/1AbCdEfGhIjK\n"
                       "https://docs.google.com/x/d/2ZyXwVuTsRqP/edit 2ZyXwVuTsRqP") == \
        ["1AbCdEfGhIjK", "2ZyXwVuTsRqP"]
    a = dx.label_args("o@s.org", ["F1234567890"], "L1", "f1", "c1", folder=True)
    assert a[4:6] == ["query", "'F1234567890' in parents and trashed=false"]
    assert a[-5:] == ["addlabelfield", "L1", "f1", "selection", "c1"]
    labels = dx.parse_labels([{"JSON": json.dumps({
        "id": "L1", "properties": {"title": "Confidential"}, "lifecycle": {"state": "PUBLISHED"},
        "fields": [{"id": "f1", "properties": {"displayName": "Level"},
                    "selectionOptions": {"choices": [{"id": "c1", "properties":
                                                      {"displayName": "High"}}]}}]})}])
    assert labels[0]["fields"][0]["choices"] == [("c1", "High")]
    o = dx.orphans_args(["user", "a@s.org"])
    assert o[-1] == "preview" and not activity.is_change(o)
    assert activity.is_change(dx.orphans_args(["user", "a@s.org"], preview=False))


def test_roles_know_the_new_commands():
    assert "delete" in team.categorize(chrome.command_args(["cros_sn", "A"], "wipe_users"))
    assert "chromebooks" in team.categorize(chrome.command_args(["cros_sn", "A"], "reboot"))
    assert "groups" in team.categorize(people.dynamic_group_args("g@s.org", "G", "q"))
    assert "everyone" in team.categorize(inv.revoke_args("/Students", "c"))
