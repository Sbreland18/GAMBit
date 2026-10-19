import datetime
import json

from gambit import ai_usage, apps_public, cost_per_student as cps, directory_quality as dq
from gambit import guardian_followup as gf, license_rightsize as lr, meet_attendance as ma
from gambit.tools import battery_forecast as bf, gam_extras2 as g2, repeat_damage as rd
from gambit.tools import shared_accounts as sa, watchdog as wd

TODAY = datetime.date(2026, 10, 15)


def test_gam_extras2_basics():
    assert g2.meet_code("https://meet.google.com/abc-defg-hij?x") == "abc-defg-hij"
    assert g2.meet_code("ABCDEFGHIJ") == "abc-defg-hij"
    assert g2.form_id("https://docs.google.com/forms/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit") == \
        "1AbCdEfGhIjKlMnOpQrStUvWxYz"
    resp = g2.form_responses([{"respondentEmail": "a@s.org", "createTime":
                               "2026-10-01T10:00:00Z", "answers.0.questionId": "q1",
                               "answers.0.textAnswers.answers.0.value": "Yes"}])
    assert resp[0]["Q q1"] == "Yes" and resp[0]["Email"] == "a@s.org"
    js = json.loads(g2.wifi_json("Test", "WPA-PSK", "pw", True, False))
    assert js["settings"][0]["value"]["ssid"] == "Test"
    assert g2.network_create_args("/C", "T", "{}") == ["create", "chromenetwork", "/C", "T",
                                                       "json", "{}"]
    net = g2.networks([{"JSON": json.dumps({"name": "chrome.networks.wifi.Details",
                                            "orgUnitPath": "/C",
                                            "additionalTargetKeys": {"network_id": "n1"},
                                            "fields": [{"name": "ssid", "value": "Test"}]})}])
    assert net == [{"Network ID": "n1", "Name": "", "SSID": "Test", "Security": "",
                    "Org unit": "/C"}]
    sv = g2.snvalidity([{"serialNumber": "A", "exactMatches": "1"},
                        {"serialNumber": "B", "exactMatches": "0", "prefixMatches": "2"},
                        {"serialNumber": "C"}])
    assert [s["Result"][:6] for s in sv] == ["Enroll", "Not fo", "Not in"]
    assert "every website" in g2.app_permissions('"permissions": ["<all_urls>", "tabs"]')
    r = g2.replace_attendee_args(["p@s.org"], "old@s.org", "new@s.org", "2026-10-15")
    assert r[:5] == ["users", "p@s.org", "update", "calattendees", "primary"]
    assert r[-4:] == ["replace", "old@s.org", "new@s.org", "doit"]
    assert g2.drive_id("https://drive.google.com/drive/folders/1AbCdEfGhIjK") == "1AbCdEfGhIjK"
    assert g2.claim_args("n@s.org", "1AbCdEfGhIjK", True)[-2:] == ["retainrole", "writer"]
    com = g2.comments([{"comments.0.content": "mean thing", "comments.0.deleted": "True",
                        "comments.0.author.emailAddress": "x@s.org"}])
    assert com[0]["Deleted"] == "yes" and com[0]["Who"] == "x@s.org"
    ts = g2.teacher_status([{"emailAddress": "t@s.org", "verifiedTeacher": "True",
                             "permissions.0.permission": "CREATE_COURSE"}])
    assert ts[0]["Can create classes"] == "yes"
    assert g2.cancel_guardian_args("i1", "k@s.org") == ["cancel", "guardianinvitation", "i1",
                                                        "k@s.org"]
    assert g2.photo_export_args(["ou", "/S"], "C:/p")[2:4] == ["get", "profilephoto"]
    assert g2.chat_spaces([{"name": "spaces/1", "displayName": "Club",
                            "externalUserAllowed": "True"}])[0]["External"] == "yes"


def test_meet_attendance():
    ev = [{"identifier": "a@s.org", "meeting_code": "ABCDEFGHIJ", "duration_seconds": "1500",
           "id.time": "2026-10-15T13:00:00Z"},
          {"identifier": "a@s.org", "meeting_code": "ABCDEFGHIJ", "duration_seconds": "300",
           "id.time": "2026-10-15T13:40:00Z"},
          {"identifier": "b@s.org", "meeting_code": "ABCDEFGHIJ", "duration_seconds": "120",
           "id.time": "2026-10-15T13:05:00Z"},
          {"identifier": "x@gmail.com", "meeting_code": "ABCDEFGHIJ",
           "duration_seconds": "600", "id.time": "2026-10-15T13:05:00Z"},
          {"identifier": "z@s.org", "meeting_code": "OTHERCODEX", "duration_seconds": "900"}]
    s = ma.sessions(ev, "abc-defg-hij")
    assert round(s["a@s.org"]["minutes"]) == 30 and s["a@s.org"]["joins"] == 2
    assert "z@s.org" not in s
    rows = ma.attendance({"a@s.org": "A", "b@s.org": "B", "c@s.org": "C"}, s, 10)
    st = {r["Student"]: r["Status"] for r in rows}
    assert st == {"a@s.org": "Present", "b@s.org": "Partial", "c@s.org": "Absent",
                  "x@gmail.com": "Not on the roster"}
    assert ma.codes(ev)[0] == ("ABCDEFGHIJ", 3)
    assert "Absent:" in ma.email_text("Math", TODAY, rows)
    assert ma.report_args("t@s.org", TODAY)[-1] == "organizer_email==t@s.org"


def test_public_apps_and_ai():
    summary = [{"App": "Quizlet", "Client ID": "1", "Status": "approved", "Students": 40},
               {"App": "Shady", "Client ID": "2", "Status": "denied", "Students": 9},
               {"App": "Rare", "Client ID": "3", "Status": "not on the list", "Students": 1}]
    approved = [{"name": "Quizlet", "client_id": "", "status": "approved",
                 "purpose": "Flashcards", "dpa": "https://sdpc.example/1"}]
    rows = apps_public.build(summary, approved, apps_public.options())
    assert [r["App"] for r in rows] == ["Quizlet"]
    assert rows[0]["What it's for"] == "Flashcards"
    page = apps_public.to_html(rows, apps_public.options(), "Hancock")
    assert "Quizlet" in page and "<a href='https://sdpc.example/1'>" in page
    users = [{"email": "k@s.org", "ou": "/Students/Elementary/Grade 3"},
             {"email": "h@s.org", "ou": "/Students/High/Grade 10"},
             {"email": "t@s.org", "ou": "/Staff"}]
    ev = [{"actor.email": "k@s.org", "name": "feature_utilization", "id.time": "2026-10-13"},
          {"actor.email": "h@s.org", "name": "feature_utilization", "id.time": "2026-10-14"},
          {"actor.email": "t@s.org", "name": "summarize", "id.time": "2026-10-14"}]
    res = ai_usage.analyze(ev, users, {"root": "/Students",
                                       "not_allowed": "/Students/Elementary"})
    assert res["people"] == 3 and res["flagged"][0]["Person"] == "k@s.org"
    assert {p["School"] for p in res["places"]} == {"Elementary", "High", "Staff and others"}
    assert res["weeks"][0]["Students"] == 2


def test_shared_accounts_and_travel():
    devs = [{"serialNumber": f"S{i}", "orgUnitPath": "/Chromebooks/HS",
             "recentUsers.0.email": "k@s.org"} for i in range(5)]
    devs.append({"serialNumber": "C1", "orgUnitPath": "/Chromebooks/Cart 3",
                 "recentUsers.0.email": "j@s.org"})
    spread = sa.device_spread(devs, sa.options())
    assert len(spread["k@s.org"]) == 5 and "j@s.org" not in spread
    logins = [{"actor.email": "k@s.org", "id.time": "2026-10-14T13:00:00Z",
               "ipAddress": "1.1.1.1"},
              {"actor.email": "k@s.org", "id.time": "2026-10-14T13:03:00Z",
               "ipAddress": "2.2.2.2"}]
    ls = sa.login_spread(logins, 10)
    assert ls["k@s.org"]["near"] == 1
    users = [{"email": "k@s.org", "ou": "/Students/HS"}]
    f = sa.flag(users, spread, ls, sa.options())
    assert f[0]["Signs"] == 2
    trav = sa.impossible_travel([
        {"actor.email": "t@s.org", "id.time": "2026-10-14T13:00:00Z",
         "networkInfo.subdivisionCode": "US-TX", "ipAddress": "1.1.1.1"},
        {"actor.email": "t@s.org", "id.time": "2026-10-14T13:40:00Z",
         "networkInfo.subdivisionCode": "RO-B", "ipAddress": "9.9.9.9"}])
    assert trav[0]["from"] == "US-TX" and trav[0]["minutes"] == 40
    found = wd.analyze({"travel": [
        {"actor.email": "t@s.org", "id.time": "2026-10-14T13:00:00Z",
         "networkInfo.regionCode": "US"},
        {"actor.email": "t@s.org", "id.time": "2026-10-14T13:20:00Z",
         "networkInfo.regionCode": "NG"}]}, wd.options(), {"s.org"})
    assert any(x["Finding"] == "Impossible travel" for x in found)
    qs = dict(wd.queries(wd.options(), "2026-10-14T00:00:00Z"))
    assert qs["travel"][:4] == ["report", "login", "orgunit", "/Staff"]


def test_directory_quality():
    rows = [{"primaryEmail": "t@s.org", "name.fullName": "Pat Lee", "orgUnitPath": "/Staff/HS",
             "organizations.0.title": "Teacher", "phones.0.value": "555",
             "relations.0.value": "boss@s.org", "externalIds.0.type": "organization",
             "externalIds.0.value": "E1"},
            {"primaryEmail": "u@s.org", "name.fullName": "Sam Roe", "orgUnitPath": "/Staff/HS"},
            {"primaryEmail": "pat.lee@s.org", "name.fullName": "Pat Lee",
             "orgUnitPath": "/Students/HS", "externalIds.0.type": "organization",
             "externalIds.0.value": "S9"},
            {"primaryEmail": "k1@s.org", "name.fullName": "Kid", "orgUnitPath": "/Students/HS",
             "externalIds.0.type": "organization", "externalIds.0.value": "S9"}]
    ppl = dq.people(rows)
    o = dq.options()
    score, gaps = dq.score(ppl, o)
    staff = next(s for s in score if s["Where"] == "HS (staff)")
    assert staff["Score"] == 0 and "Department" in staff["Most often missing"]
    assert any(g["Person"] == "u@s.org" for g in gaps)
    d = dq.duplicates(ppl, o)
    whys = {x["Why"] for x in d}
    assert "same ID s9" in whys and "a student who also has a staff account" in whys


def test_battery_forecast():
    row = {"serialNumber": "A", "model": "Dell 3100", "orgUnitPath": "/Chromebooks/HS",
           "batteryInfo.0.designCapacity": "4000"}
    caps = [("2026-04-01", 3200), ("2026-06-01", 3000), ("2026-08-01", 2800),
            ("2026-10-01", 2600)]
    for i, (d, c) in enumerate(caps):
        row[f"batteryStatusReport.{i}.reportTime"] = d + "T00:00:00Z"
        row[f"batteryStatusReport.{i}.fullChargeCapacity"] = str(c)
    design, pts = bf.points(row)
    assert design == 4000 and pts[-1][1] == 65.0
    p = bf.predict(pts, 60, TODAY)
    assert p["per_month"] < 0 and "2026-10" < p["when"] < "2027-01"
    fc = bf.forecast([row], {"replace_at": 60, "by": "2027-06-30"}, TODAY)
    assert fc[0]["due"]
    order = bf.order_list(fc, {"device_root": "/Chromebooks", "depth": 1, "battery_cost": 40})
    assert order == [{"School": "HS", "Model": "Dell 3100", "Batteries": 1,
                      "Estimated cost": 40.0}]
    assert bf.predict([(TODAY, 55)], 60, TODAY)["when"] == "now"


def test_repeat_damage():
    tickets = [{"serial": "A", "opened": "2025-01-10", "problem": "cracked screen",
                "user": "k@s.org"},
               {"serial": "B", "opened": "2026-02-01", "problem": "Liquid spill"},
               {"serial": "C", "opened": "2026-03-01", "problem": "won't boot",
                "user": "k@s.org"}]
    hist = rd.assignment_history([{"command": "gam cros_sn B update user k@s.org",
                                   "time": "2025-09-01T10:00", "code": 0}])
    assert hist == {"B": [{"date": "2025-09-01", "user": "k@s.org"}]}
    rows = rd.report(tickets, [{"email": "k@s.org", "name": "Kid", "ou": "/Students/HS"}], 2,
                     True, 4, hist, TODAY)
    assert rows[0]["Repairs"] == 2 and rows[0]["Devices"] == 2
    assert rd.by_school(rows) == [{"School": "HS", "Students": 1, "Repairs": 2}]
    assert rd.report(tickets, [], 2, False, 4, hist, TODAY)[0]["Repairs"] == 3


def test_license_rightsize():
    holders = [{"email": "a@s.org", "skus": ["1010370001"], "ou": "/Staff", "last": TODAY,
                "suspended": False},
               {"email": "b@s.org", "skus": ["1010370001", "1010070001"], "ou": "/Staff",
                "last": None, "suspended": False},
               {"email": "c@s.org", "skus": ["1010370001"], "ou": "/Staff", "last": TODAY,
                "suspended": False}]
    meet = [{"organizer_email": "a@s.org", "meeting_code": "X", "identifier": f"p{i}@s.org"}
            for i in range(120)]
    cls = [{"actor.email": "c@s.org", "name": "originality_report_run"}]
    use = lr.premium_use(meet, cls, 100)
    assert "meeting with 120 people" in use["a@s.org"] and use["c@s.org"]
    summ, rows = lr.suggest(holders, use, {**lr.options(), "keep": ""})
    assert [r["Person"] for r in rows] == ["b@s.org"]
    assert rows[0]["args"] == ["user", "b@s.org", "delete", "license", "1010370001"]
    assert summ[0]["Held"] == 3 and summ[0]["Could release"] == 1


def test_guardian_followup(monkeypatch):
    from gambit.settings import settings
    settings.set("guardianfu/resent", "{}")
    cur = [{"student": "k@s.org", "guardian": "mom@gmial.com", "kind": "invitation",
            "state": "PENDING", "since": "2026-10-10", "id": "i1"},
           {"student": "k@s.org", "guardian": "dad@gmail.com", "kind": "invitation",
            "state": "PENDING", "since": "2026-09-01", "id": "i2"},
           {"student": "j@s.org", "guardian": "g@gmail.com", "kind": "guardian",
            "state": "COMPLETE", "since": "", "id": ""},
           {"student": "m@s.org", "guardian": "new@gmail.com", "kind": "invitation",
            "state": "PENDING", "since": "2026-10-14", "id": "i3"}]
    resend, cancel = gf.plan(cur, 14, TODAY)
    assert [c["Guardian"] for c in cancel] == ["mom@gmial.com"]
    assert [r["Guardian"] for r in resend] == ["dad@gmail.com"]
    assert resend[0]["args"][1] == ["user", "k@s.org", "create", "guardian", "dad@gmail.com"]
    gf.note_resent(resend)
    gf.note_resent(resend)
    assert gf.plan(cur, 14, TODAY, max_resends=2)[0] == []
    users = [{"email": e, "ou": "/Students/HS"} for e in ("k@s.org", "j@s.org", "m@s.org",
                                                          "n@s.org")]
    bys, byt = gf.acceptance(cur, users, "/Students", {"t@s.org": {"c1"}},
                             {"c1": ["k@s.org", "j@s.org"]})
    assert bys[0] == {"School": "HS", "Students": 4, "Accepted": 1, "Waiting": 2,
                      "None invited": 1, "Accepted %": 25}
    assert byt[0]["Accepted %"] == 50
    assert gf.looks_wrong("x@yahoo") and not gf.looks_wrong("x@yahoo.com")


def test_cost_per_student():
    users = [{"email": f"s{i}@s.org", "ou": "/Students/HS"} for i in range(10)]
    devs = [{"serial": f"D{i}", "ou": "/Chromebooks/HS", "status": "ACTIVE"} for i in range(10)]
    holders = [{"email": "s0@s.org", "skus": ["1010370001"]}]
    repairs = [{"serial": "D1", "opened": "2026-05-01"}, {"serial": "D2",
                                                           "opened": "2024-01-01"}]
    o = {"student_root": "/Students", "device_root": "/Chromebooks", "depth": 1,
         "device_cost": 300, "life_years": 5, "repair_cost": 50,
         "prices": {"1010370001": 48}}
    rows = cps.compute(devs, holders, repairs, users, o, TODAY)
    hs = rows[0]
    assert hs["Devices / year"] == 600 and hs["Licenses / year"] == 48
    assert hs["Repairs (12 mo)"] == 1 and hs["Total / year"] == 698
    assert hs["Per student"] == 69.8 and rows[-1]["School"] == "District"


def test_wifi_passphrase_is_masked():
    from gambit.activity import mask
    from gambit.gam_runner import display_command
    a = g2.network_create_args("/C", "N", g2.wifi_json("S", "WPA-PSK", "topsecret"))
    assert "topsecret" not in display_command(a)
    assert "topsecret" not in " ".join(mask(a))
