import datetime
import json
from collections import Counter

from gambit import access_review as ar, going_quiet as gq, lifecycle as lc
from gambit import storage_forecast as sf, timeline
from gambit.tools import gam_extras as gx, group_suggest as gs, policy_cleanup as pc
from gambit.tools import redistribute as rd, stale, test_readiness as tr, watchdog as wd

TODAY = datetime.date(2026, 10, 15)


def test_invitations_calendar_ooo():
    inv = gx.invitations([{"email": "B@s.org", "state": "ACCEPTED"},
                          {"email": "a@s.org", "state": "NOT_YET_SENT", "mailsSentCount": "0"}])
    assert [i["email"] for i in inv] == ["a@s.org", "b@s.org"]
    assert inv[0]["label"] == "Not invited yet"
    assert gx.invite_args("a@s.org") == ["send", "userinvitation", "a@s.org"]
    rows = [{"calendarId": "t@s.org", "role": "reader", "scope.type": "default"},
            {"calendarId": "t@s.org", "role": "writer", "scope.type": "user",
             "scope.value": "friend@gmail.com"},
            {"calendarId": "t@s.org", "role": "owner", "scope.type": "user",
             "scope.value": "t@s.org"},
            {"calendarId": "t@s.org", "role": "reader", "scope.type": "domain",
             "scope.value": "s.org"}]
    ex = gx.cal_exposure(rows, {"s.org"})
    assert [e["scope"] for e in ex] == ["default", "friend@gmail.com"]
    assert gx.cal_unshare_args("t@s.org", "default") == ["calendars", "t@s.org", "delete",
                                                        "acls", "default"]
    a = gx.ooo_args("t@s.org", "2026-10-20", "2026-10-24", "Away")
    assert a[:4] == ["user", "t@s.org", "create", "outofoffice"]
    assert a[-4:] == ["range", "2026-10-20", "2026-10-24", "noreminders"]


def test_classroom_invites_topics():
    rows = [{"courseId": "1", "courseName": "Math", "id": "i1", "role": "STUDENT",
             "userEmail": "k@s.org"},
            {"courseId": "1", "courseName": "Math", "id": "i2", "role": "TEACHER",
             "userEmail": "t@s.org"}]
    inv = gx.class_invites(rows)
    assert gx.invite_summary(inv) == [{"Class": "Math", "Students": 1, "Teachers": 1,
                                       "course": "1"}]
    assert gx.readd_args(inv[0]) == ["course", "1", "add", "student", "k@s.org"]
    assert gx.delete_invite_args("1", "i1")[:3] == ["delete", "classroominvitation", "courses"]
    cmds = gx.copy_topics_commands(["Unit 1", "Unit 2"], ["9", "8"], {"9": {"unit 1"}})
    assert cmds == [["course", "9", "create", "topic", "Unit 2"],
                    ["course", "8", "create", "topic", "Unit 1"],
                    ["course", "8", "create", "topic", "Unit 2"]]


def test_chrome_extras():
    m = gx.active_minutes([{"serialNumber": "a1", "activeTimeRanges.date": "2026-10-01",
                            "activeTimeRanges.minutes": "30"},
                           {"serialNumber": "A1", "activeTimeRanges.date": "2026-10-02",
                            "activeTimeRanges.duration": "600000"}])
    assert m == {"A1": {"minutes": 40, "days": 2, "last": "2026-10-02"}}
    assert gx.latest_versions([{"version": "129.0.1"}, {"version": "131.0.6778.86"},
                               {"version": "130.2"}]) == "131.0.6778.86"
    prof = gx.profile_rows([{"name": "customers/x/profiles/1", "userEmail": "t@s.org",
                             "osPlatformType": "WINDOWS", "browserVersion": "120.0.1"},
                            {"name": "p2", "osPlatformType": "MAC",
                             "browserVersion": "131.0"}])
    b = gx.behind(prof, {"win64": "131.0.1", "mac": "131.0"})
    assert [x["name"] for x in b] == ["customers/x/profiles/1"] and b[0]["behind"] == 11
    assert gx.profile_command_args(["p1"], True, True) == [
        "create", "chromeprofilecommand", "p1", "clearcache", "true", "clearcookies", "true"]
    out = "Chrome Policy Image: chrome.users.Wallpaper wallpaperImage https://x/y.jpg, Added"
    assert gx.image_url(out) == "https://x/y.jpg"
    assert gx.image_policy_args("chrome.users.wallpaper", "https://x/y.jpg", "/S") == [
        "update", "chromepolicy", "chrome.users.Wallpaper", "wallpaperimage",
        "https://x/y.jpg", "ou", "/S"]


def test_drive_security_groups_counts():
    users = [{"email": "a@s.org", "ou": "/Students/Lincoln"},
             {"email": "b@s.org", "ou": "/Students/Grant"}]
    sc = gx.sharecounts([{"Owner": "a@s.org", "Total": "50", "anyone": "2",
                          "anyoneWithLink": "3", "externalUser": "4"},
                         {"Owner": "b@s.org", "Total": "9"}], users, "/Students")
    assert sc[0]["Owner"] == "a@s.org" and sc[0]["School"] == "Lincoln" and \
        sc[0]["Public"] == 2 and sc[0]["Anyone with link"] == 3
    assert gx.share_by_school(sc)[0]["School"] == "Lincoln"
    act = gx.file_activity([{"eventTime": "2026-10-01T10:00:00Z", "user.emailAddress":
                             "x@s.org", "primaryActionDetail.delete.type": "TRASH",
                             "target.name": "Plan"}])
    assert act[0]["What"] == "delete" and act[0]["Who"] == "x@s.org"
    d = gx.shared_drives([{"id": "0A", "name": "Chess club", "orgUnit": "/"}])
    assert gx.drive_ou_suggestions(d, [("club", "/Students/Clubs")])[0]["Move to"] == \
        "/Students/Clubs"
    ap = gx.asps([{"User": "a@s.org", "asp.codeId": "1", "asp.name": "Outlook",
                   "asp.creationTime": "2025-01-01 10:00"}], users)
    assert ap[0]["App password"] == "Outlook" and ap[0]["Org unit"] == "/Students/Lincoln"
    keys = gx.sakeys("Service Account: x\n  name: abc123\n    validAfterTime: 2025-01-01T00:00"
                     "\n    usedToAuthenticateThisRequest: True\n  name: def\n"
                     "    validAfterTime: 2026-10-01T00:00\n", TODAY)
    assert keys[0]["age"] == 652 and keys[0]["current"] and not keys[1]["current"]
    gt = gx.grouptree([{"User": "a@s.org", "Group": "g1@s.org", "Name": "G1",
                        "Parents": "all@s.org"}])
    assert gt[1] == {"Group": "all@s.org", "Name": "", "How": "Through g1@s.org"}
    cnt = gx.usercounts([{"orgUnitPath": "/S", "active": "3", "suspended": "1",
                          "archived": "0", "total": "4"},
                         {"orgUnitPath": "/S/A", "active": "2", "total": "2"},
                         {"orgUnitPath": "Total(C1)", "total": "6"}])
    assert gx.rollup(cnt, "/S")["total"] == 6 and "Total(C1)" not in cnt


def test_access_review():
    admins = [{"roleAssignmentId": "1", "role": "Super Admin", "assignedToUser": "old@s.org"},
              {"roleAssignmentId": "2", "role": "Help Desk", "assignedToUser": "t@s.org",
               "orgUnit": "/Staff"}]
    users = [{"primaryEmail": "old@s.org", "orgUnitPath": "/Former Staff",
              "isEnrolledIn2Sv": "False", "lastLoginTime": "2026-01-01T00:00:00Z",
              "suspended": "True"},
             {"primaryEmail": "t@s.org", "orgUnitPath": "/Staff", "isEnrolledIn2Sv": "True",
              "lastLoginTime": "2026-10-14T00:00:00Z", "suspended": "False"}]
    acts = [{"actor.email": "t@s.org"}]
    r = ar.review(admins, users, acts, {"former_root": "/Former Staff"}, TODAY)
    assert r[0]["Admin"] == "old@s.org" and "SUPER ADMIN" in r[0]["Flags"] and \
        "has left" in r[0]["Flags"]
    assert r[1]["Flags"] == "" and r[1]["Admin actions"] == 1
    assert ar.remove_args("1") == ["delete", "admin", "1"]


def test_account_timing(monkeypatch):
    data = lc.observe({}, [{"primaryEmail": "n@s.org", "orgUnitPath": "/Students/Lincoln",
                            "creationTime": "2026-10-01T00:00:00Z", "lastLoginTime": "Never"},
                           {"primaryEmail": "z@s.org", "orgUnitPath": "/Students/Lincoln",
                            "creationTime": "2026-09-20T00:00:00Z", "lastLoginTime": ""}],
                      datetime.date(2026, 10, 2))
    data = lc.observe(data, [{"primaryEmail": "n@s.org", "orgUnitPath": "/Students/Lincoln",
                              "creationTime": "2026-10-01T00:00:00Z",
                              "lastLoginTime": "2026-10-04T08:00:00Z"}], TODAY)
    assert data["accounts"]["n@s.org"]["first_login"] == "2026-10-04"
    rows = lc.new_accounts(data, {"root": "/Students", "late_days": 7}, TODAY)
    assert rows[0]["Median days to first sign-in"] == 3 and \
        rows[0]["Not signed in after 7 days"] == 1
    snaps = [("2026-10-01", {"x@s.org": {"ou": "/Staff", "suspended": False},
                             "y@s.org": {"ou": "/Former Staff", "suspended": True}}),
             ("2026-10-02", {"x@s.org": {"ou": "/Former Staff", "suspended": False}}),
             ("2026-10-05", {"x@s.org": {"ou": "/Former Staff", "suspended": True}})]
    lv = lc.leavers(snaps, ["/Former Staff"])
    assert lv == [{"Account": "x@s.org", "Moved to leavers": "2026-10-02",
                   "Suspended": "2026-10-05", "Days": 3}]
    ap = lc.approvals([{"time": "2026-10-01T08:00:00", "decided": "2026-10-01T12:00:00",
                        "status": "done", "commands": [["update", "user", "a", "suspended",
                                                        "on"]]},
                       {"time": "2026-10-02T08:00:00", "status": "pending", "title": "X"}])
    assert ap["median_hours"] == 4.0 and ap["pending"] == 1 and ap["oldest_pending"] == "X"
    s = {"new": rows, "leavers": lv, "approvals": ap}
    assert lc.score_values(s) == {"signin_days": 3, "leaver_days": 3, "approval_hours": 4.0}


def test_storage_forecast():
    users = [{"email": "a@s.org", "ou": "/Students/Lincoln"},
             {"email": "g@s.org", "ou": "/Graduates", "suspended": True}]
    u = sf.usage([{"email": "a@s.org", "accounts:used_quota_in_mb": "1024"},
                  {"email": "g@s.org", "accounts:used_quota_in_mb": "2048"}], users,
                 sf.options())
    assert u["by_school"] == {"Lincoln": 1024.0, "Staff and others": 2048.0}
    assert u["leavers_mb"] == 2048 and u["top"][0]["Person"] == "g@s.org"
    items = []
    tb = 1024 * 1024
    for i, d in enumerate(("2026-01-01", "2026-04-01", "2026-07-01")):
        items.append({"date": d, "total_mb": (50 + 10 * i) * tb, "by_school": {"A": i * tb}})
    f = sf.forecast(items, 100)
    assert f["now_tb"] == 70 and 3.2 < f["per_month_tb"] < 3.5
    assert f["full_date"] > "2027-01-01" and f["months_left"] > 8
    assert sf.school_trend(items)[0]["School"] == "A"
    assert sf.add_week(items, {"total_mb": 1, "by_school": {}},
                       datetime.date(2026, 7, 1))[-1]["total_mb"] == 1


def test_test_readiness():
    rows = [{"serialNumber": "A", "status": "ACTIVE", "osVersion": "128.0.1",
             "lastSync": "2026-10-14T00:00:00Z", "orgUnitPath": "/Testing",
             "autoUpdateExpiration": "2030-01-01"},
            {"serialNumber": "B", "status": "ACTIVE", "osVersion": "118.0",
             "lastSync": "2026-09-01T00:00:00Z", "orgUnitPath": "/Testing",
             "autoUpdateExpiration": "2026-10-01", "annotatedLocation": "Cart 1"},
            {"serialNumber": "C", "status": "DISABLED", "osVersion": "128",
             "lastSync": "2026-10-14", "orgUnitPath": "/Testing/X"}]
    res = tr.check(rows, {"min_version": "120", "sync_days": 7, "test_date": "2026-10-20"},
                   TODAY, app_ok={"/Testing": True, "/Testing/X": False})
    by = {r["Serial"]: r for r in res}
    assert by["A"]["ok"]
    assert "needs 120" in by["B"]["Problems"] and "end of updates" in by["B"]["Problems"]
    assert "disabled" in by["C"]["Problems"] and "testing app" in by["C"]["Problems"]
    assert tr.by_place(res)[0]["Not ready"] >= 1
    assert "Cart 1" in tr.summary_text(res, {"test_date": "2026-10-20"})
    assert tr.reboot_args("B")[-3:] == ["command", "reboot", "doit"]


def test_redistribute():
    users = [{"email": f"s{i}@s.org", "ou": "/Students/Lincoln"} for i in range(4)] + \
            [{"email": "t@s.org", "ou": "/Students/Grant"}]
    recent, old = TODAY - datetime.timedelta(days=1), TODAY - datetime.timedelta(days=90)
    devs = [{"serial": "L1", "ou": "/Chromebooks/Lincoln", "status": "ACTIVE",
             "last_sync": recent},
            {"serial": "G1", "ou": "/Chromebooks/Grant", "status": "ACTIVE", "last_sync": recent},
            {"serial": "G2", "ou": "/Chromebooks/Grant", "status": "ACTIVE", "last_sync": old},
            {"serial": "G3", "ou": "/Chromebooks/Grant", "status": "ACTIVE", "last_sync": old}]
    rows, moves = rd.plan(devs, users, {**rd.options(), "spare_pct": 0}, None, TODAY)
    lin = next(r for r in rows if r["School"] == "Lincoln")
    assert lin["Short"] == 3
    assert {m["Serial"] for m in moves} == {"G2", "G3"}
    assert moves[0]["args"][-2:] == ["ou", "/Chromebooks/Lincoln"]


def _pol(name, direct=True, **fields):
    return {"JSON": json.dumps({"name": name, "direct": direct,
                                "fields": [{"name": k, "value": v} for k, v in fields.items()]})}


def test_policy_cleanup():
    assert pc.parent("/Students/HS") == "/Students" and pc.parent("/Students") == "/"
    child = [_pol("chrome.users.IncognitoMode", incognitoModeAvailability="UNAVAILABLE"),
             _pol("chrome.users.SafeSearch", safeSearch=True)]
    par = [_pol("chrome.users.IncognitoMode", False, incognitoModeAvailability="unavailable"),
           _pol("chrome.users.SafeSearch", False, safeSearch=False)]
    red = pc.redundant("/Students/HS", child, par)
    assert [r["Policy"] for r in red] == ["chrome.users.IncognitoMode"]
    assert red[0]["args"] == ["delete", "chromepolicy", "chrome.users.IncognitoMode", "ou",
                              "/Students/HS"]
    calls = []

    def run_csv(a):
        calls.append(a)
        return (0, child if "direct" in a else par, "")
    found, probs = pc.scan(["/Students/HS", "/Students/MS"], run_csv)
    assert len(found) == 2 and not probs
    assert sum(1 for c in calls if c[3] == "/Students") == 1   # parent read once


def test_going_quiet():
    users = [{"email": "a@s.org", "ou": "/Students/Lincoln", "last_login": "2026-09-01"},
             {"email": "b@s.org", "ou": "/Students/Lincoln", "last_login": "2026-10-14"},
             {"email": "t@s.org", "ou": "/Staff", "last_login": "2020-01-01"}]
    devs = [{"user": "a@s.org", "last_sync": datetime.date(2026, 9, 1)},
            {"user": "a@s.org", "last_sync": None}]
    rows = gq.flag(users, gq.options(), Counter({"a@s.org": 6, "b@s.org": 1}), devs, TODAY)
    assert len(rows) == 1 and rows[0]["Signals"] == 3 and rows[0]["School"] == "Lincoln"
    assert gq.missing_counts([{"profile.emailAddress": "A@s.org"}] * 2) == {"a@s.org": 2}
    assert gq.counselors("Lincoln = c1@s.org, c2@s.org\nbad line") == {
        "lincoln": ["c1@s.org", "c2@s.org"]}
    gq.mark_new(rows, set())
    subj, body = gq.render("Lincoln", rows)
    assert "1 (1 new)" in subj and "NEW" in body


def test_group_suggest():
    users = [{"email": f"u{i}@s.org", "ou": "/Staff/Lincoln", "title": "Teacher"}
             for i in range(10)] + [{"email": "x@s.org", "ou": "/Staff/Grant"}]
    rows = [{"group": "lincoln@s.org", "email": f"u{i}@s.org", "role": "MEMBER",
             "type": "USER"} for i in range(9)]
    rows += [{"group": "misc@s.org", "email": e, "role": "MEMBER", "type": "USER"}
             for e in ("u1@s.org", "x@s.org", "u2@s.org", "u3@s.org", "u9@s.org")]
    sug = gs.suggest(gs.members_by_group(rows), users, [], 0.85)
    assert [s["Group"] for s in sug] == ["lincoln@s.org"]
    assert sug[0]["Would add"] == 1 and sug[0]["Match"] == "90%"
    r = gs.rule_for(sug[0])
    assert r["mode"] == "addonly" and (r["ous"] == ["/Staff/Lincoln"] or r["title"])
    assert gs.suggest(gs.members_by_group(rows), users, [{"group": "lincoln@s.org"}]) == []


def test_stale():
    drives = [{"id": "1", "Name": "Old club", "Created": "2018-01-01"},
              {"id": "2", "Name": "Active", "Created": "2018-01-01"},
              {"id": "3", "Name": "Board archive", "Created": "2015-01-01"},
              {"id": "4", "Name": "Unknown", "Created": "2015-01-01"}]
    s = stale.stale_drives(drives, {"1": "2022-05-01", "2": "2026-10-01", "3": "2020-01-01",
                                    "4": "?"}, 2, "board", TODAY)
    assert [x["Name"] for x in s] == ["Old club"] and s[0]["args"] == ["hide",
                                                                       "shareddrive", "1"]
    courses = [{"id": "c1", "name": "Art", "creationTime": "2025-08-01"},
               {"id": "c2", "name": "Math", "creationTime": "2025-08-01"},
               {"id": "c3", "name": "New", "creationTime": "2026-09-01"}]
    cl = stale.stale_classes(courses, [{"courseId": "c2", "courseWorks": "4"}],
                             [{"courseId": "c1", "courseAnnouncements": "0"}], TODAY)
    assert [c["id"] for c in cl] == ["c1"] and cl[0]["args"][-2:] == ["state", "archived"]
    g = stale.empty_groups([{"email": "e@s.org", "members": "0"},
                            {"email": "f@s.org", "members": "3"}])
    assert [x["Name"] for x in g] == ["e@s.org"]
    assert stale.year_start(TODAY) == datetime.date(2026, 7, 1)


def test_watchdog_new_rules_and_timeline():
    ou_of = {"kid@s.org": "/Students/Lincoln", "t@s.org": "/Staff"}
    res = {"useraccounts": [{"actor.email": "t@s.org", "name": "2sv_disable"}],
           "token": [{"actor.email": "kid@s.org", "name": "authorize", "app_name": "Free AI",
                      "client_id": "9.apps", "scope": "https://mail.google.com/"},
                     {"actor.email": "kid@s.org", "name": "authorize", "app_name": "Quizlet",
                      "client_id": "1.apps", "scope": "https://mail.google.com/"}]}
    f = wd.analyze(res, wd.options(), {"s.org"}, ou_of,
                   [{"name": "Quizlet", "client_id": "", "status": "approved"}])
    kinds = {(x["Finding"], x["Who"], x["Level"]) for x in f}
    assert ("2-Step Verification turned off", "t@s.org", "high") in kinds
    risky = [x for x in f if x["Finding"] == "Risky app allowed"]
    assert len(risky) == 1 and risky[0]["client_id"] == "9.apps" and risky[0]["Level"] == "high"
    from gambit.tools import playbooks
    acts = playbooks.actions(risky[0])
    assert acts[0]["steps"][0][1] == ["user", "kid@s.org", "delete", "token", "clientid",
                                      "9.apps"]
    ev = timeline.extra_events("useraccounts", "Account security",
                               [{"id.time": "2026-10-01T10:00:00Z", "name": "2sv_disable"}],
                               "t@s.org")
    assert ev[0]["what"] == "turned OFF 2-Step Verification"
    assert timeline.extra_args("groups", "t@s.org", 7)[:3] == ["report", "groups", "user"]
