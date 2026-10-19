import json

from gambit import activity, team
from gambit.tools import recovery as rc


def test_trash_and_versions():
    a = rc.trashed_files([{"doc_id": "F1", "doc_title": "Project", "id.time": "2026-10-10T09:00:00Z",
                           "actor.email": "kid@s.org"},
                          {"doc_id": "F1", "doc_title": "Project"}], True)
    assert len(a) == 1 and a[0]["By"] == "kid@s.org"
    assert rc.untrash_args("kid@s.org", ["F1", "F2"]) == ["user", "kid@s.org", "untrash",
                                                          "drivefile", "ids", "F1,F2"]
    assert activity.is_change(rc.untrash_args("k@s.org", ["F1"]))
    v = rc.revisions([{"revision.id": "3", "revision.modifiedTime": "2026-10-01T10:00:00Z",
                       "revision.lastModifyingUser.emailAddress": "t@s.org",
                       "revision.mimeType": "application/pdf"},
                      {"revision.id": "4", "revision.modifiedTime": "2026-10-02T10:00:00Z"}])
    assert v[0]["Version"] == "4" and v[1]["By"] == "t@s.org"
    s = rc.restore_revision_steps("t@s.org", "F1", "3", "/tmp/x", "F1-3")
    assert s[0][1][4:7] == ["F1", "revision", "3"] and s[1][1][-2:] == ["localfile", "/tmp/x/F1-3"]
    m = rc.untrash_mail_args("t@s.org", "in:trash newer_than:7d")
    assert m[2:4] == ["untrash", "messages"] and m[-1] == "doit"


def test_settings_snapshot_diff(qapp, team_dir):
    ci = [{"name": "policies/1", "JSON": json.dumps({
        "setting": {"type": "settings/gmail.auto_forwarding", "value": {"enableAutoForwarding": False}},
        "policyQuery": {"orgUnitPath": "/Students"}})}]
    chrome = [{"JSON": json.dumps({"name": "chrome.users.IncognitoMode", "orgUnitPath": "/",
                                   "fields": [{"name": "incognitoModeAvailability",
                                               "value": "UNAVAILABLE"}]})}]
    s1 = rc.snapshot(ci, chrome)
    assert "Admin: gmail.auto_forwarding @ /Students" in s1
    ci[0]["JSON"] = ci[0]["JSON"].replace("false", "true")
    s2 = rc.snapshot(ci, [])
    d = {x["Setting"]: x["Change"] for x in rc.diff(s1, s2)}
    assert d == {"Admin: gmail.auto_forwarding @ /Students": "changed",
                 "Chrome: chrome.users.IncognitoMode @ /": "removed"}
    rc.save_snapshot(s1, "2026-10-01_0500")
    assert "settings-snapshots" in rc.snapshots_dir() and str(team_dir) in rc.snapshots_dir()
    sent = []
    import gambit.alerts as al
    old = al.notify
    al.notify = lambda text, title="", email=True: sent.append(title)
    try:
        rows = {"policies": ci, "chromepolicies": []}
        rc.run_watch(log=lambda *_: None,
                     run_csv=lambda a: (0, rows["policies" if a[1] == "policies"
                                                 else "chromepolicies"], ""))
    finally:
        al.notify = old
    assert sent and "changed" in sent[0]
    assert len(rc.list_snapshots()) == 2


def test_roles_transfers_profiles_forms():
    p = rc.privileges([{"serviceName": "Users", "privilegeName": "USERS_RESET_PASSWORD",
                        "isOuScopable": "True"},
                       {"serviceName": "Users", "privilegeName": "USERS_RETRIEVE"}])
    assert p[0]["Per org unit"] in ("yes", "")
    avail = ["USERS_RETRIEVE", "USERS_RESET_PASSWORD", "CHROME_OS_MANAGE"]
    assert rc.template_matches(["USERS_RETRIEVE", "CHROME_OS", "NOPE"], avail) == \
        ["USERS_RETRIEVE", "CHROME_OS_MANAGE"]
    assert rc.create_role_args("Tech", "", ["A", "B"]) == ["create", "adminrole", "Tech",
                                                           "privileges", "A,B"]
    assert rc.assign_role_args("t@s.org", "Tech", "/Lincoln")[-2:] == ["org_unit", "/Lincoln"]
    assert team.categorize(rc.create_role_args("Tech", "", ["A"])) == {"other"}
    t = rc.transfers([{"oldOwnerUserEmail": "a@s.org", "newOwnerUserEmail": "b@s.org",
                       "overallTransferStatusCode": "failed", "application": "Drive"}])
    assert t[0]["Status"] == "failed"
    pr = rc.profiles([{"userEmail": "t@s.org", "osPlatformType": "WINDOWS",
                       "lastActivityTime": "2020-01-01T00:00:00Z"}])
    assert pr[0]["Note"].startswith("not used")
    f = rc.forms_post([{"User": "t@s.org", "name": "Survey",
                        "settings.emailCollectionType": "DO_NOT_COLLECT"},
                       {"User": "t@s.org", "name": "Quiz",
                        "settings.emailCollectionType": "VERIFIED"}])
    assert len(f) == 1 and f[0]["Form"] == "Survey"
    assert rc.forms_args("/Staff")[:3] == ["ou_and_children", "/Staff", "print"]


def test_classroom_and_youtube():
    rows = rc.class_activity([{"courseId": "1", "courseName": "English 9", "announcements": "3"},
                              {"courseId": "2", "courseName": "Art", "announcements": "0"}],
                             [{"courseId": "1", "courseName": "English 9", "materials": "2"}],
                             [{"courseId": "2", "courseName": "Art", "courseWorks": "0"}])
    assert [r["Class"] for r in rows] == ["Art", "English 9"]
    assert rows[0]["Note"] == "nothing posted yet" and rows[1]["Materials"] == "2"
    g = rc.studentgroup_rows([{"Class": "d:eng9", "Group": "Readers A",
                               "Student Email": "K@s.org"},
                              {"Class": "d:eng9", "Group": "Readers A", "Student Email": "j@s.org"}])
    assert g == {("d:eng9", "Readers A"): ["k@s.org", "j@s.org"]}
    assert rc.existing_groups([{"courseId": "1", "id": "g1", "title": "Readers A"}]) == \
        {("1", "readers a"): "g1"}
    assert rc.sync_group_args("1", "g1", ["k@s.org"]) == ["sync", "course-studentgroup-members",
                                                          "1", "g1", "users", "k@s.org"]
    y = rc.youtube([{"id": "UC1", "snippet.title": "Mr. T's Science"}])
    assert y[0]["Link"].endswith("UC1")


def test_transfer_check_alerts(qapp, team_dir, monkeypatch):
    from gambit import offboard
    rec = offboard.build("t@s.org", "boss@s.org", {"groups": [], "licenses": []},
                         offboard.DEFAULTS, lambda n=12: "x" * n)
    for st in rec["stages"][0]["steps"]:
        st["status"] = "done"
    offboard.save(rec)
    sent = []
    import gambit.alerts as al
    monkeypatch.setattr(al, "notify", lambda text, title="", email=True: sent.append(text))
    lines = offboard.check_transfers(
        log=lambda *_: None,
        run_csv=lambda a: (0, [{"oldOwnerUserEmail": "t@s.org",
                                "overallTransferStatusCode": "failed"}], ""))
    assert lines and "failed" in lines[0] and sent
    assert offboard.get("t@s.org")["transfer_checked"] == "failed"
