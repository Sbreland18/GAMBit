import datetime
import json
import urllib.parse

from gambit import custom_workflows as cw, email_approvals as ea, sis, team, updaters
from gambit.integrations import assistant, iiq, oneroster
from gambit.tools import automation as am


# ------------------------------------------------------------ ClassLink ---
def test_signature_matches_classlink_reference():
    # Expected value computed with ClassLink's own sample code (oneroster/classlink.py)
    h = oneroster.sign("https://ex.oneroster.com/ims/oneroster/v1p1/users", "myclient",
                       "s3cr3t+/=", {"limit": 1000, "offset": 0}, timestamp="1700000000",
                       nonce="5555555555")
    assert h == ('OAuth oauth_consumer_key="myclient",oauth_signature_method="HMAC-SHA256",'
                 'oauth_timestamp="1700000000",oauth_nonce="5555555555",'
                 'oauth_signature="p0vw5SUMbsC8gd43Zakbfa7YoGVVjmlhq0D75EBcqBo%3D"')


def _fake_oneroster():
    users = [{"sourcedId": f"u{i}", "status": "active", "enabledUser": True, "role": "student",
              "givenName": f"Kid{i}", "familyName": "Test", "identifier": str(1000 + i),
              "email": "", "grades": ["05"], "orgs": [{"sourcedId": "org1", "type": "org"}],
              "agents": [{"sourcedId": "p1", "type": "user"}]} for i in range(3)]
    data = {"users": users, "orgs": [{"sourcedId": "org1", "name": "Lincoln Elementary",
                                      "type": "school"}],
            "classes": [], "enrollments": [], "courses": []}
    calls = []

    def http(method, url, headers, body=None, timeout=60):
        calls.append((url, headers))
        u = urllib.parse.urlparse(url)
        coll = u.path.rsplit("/", 1)[-1]
        q = dict(urllib.parse.parse_qsl(u.query))
        lim, off = int(q.get("limit", 1000)), int(q.get("offset", 0))
        assert headers["Authorization"].startswith("OAuth oauth_consumer_key=")
        return 200, {}, json.dumps({coll: data[coll][off:off + lim]}).encode()
    return http, calls


def test_oneroster_download_feeds_roster_sync(tmp_path):
    http, calls = _fake_oneroster()
    cfg = {"url": "https://ex.oneroster.com/ims/oneroster/v1p1", "client_id": "c", "secret": "s"}
    assert len(oneroster.fetch_all("users", cfg, http, page=2)) == 3     # paged: 2 + 1
    path = oneroster.download(cfg=cfg, http=http, path=str(tmp_path / "or.zip"))
    exp = sis.load_export(path, "ClassLink / OneRoster")
    assert exp.schools["org1"] == "Lincoln Elementary"
    rules = sis.Rules(domain="s.org", year_end=2027, missing_means_withdrawn=False)
    people = sis.people_from_export(exp, sis.guess_mapping(exp.headers,
                                                           "ClassLink / OneRoster"), rules)
    assert len(people) == 3 and people[0].school == "org1" and people[0].grade == "05"
    from gambit import guardians
    links, _how = guardians.load_links(path)
    assert links == set() or isinstance(links, set)


# ------------------------------------------------------------ Incident IQ ---
def test_iiq():
    tid = "4c1f8a9e-1234-4abc-9def-0123456789ab"
    assert iiq.ticket_id(f"https://x.incidentiq.com/agent/tickets/{tid.upper()}") == tid
    sent = []

    def http(method, url, headers, body=None, timeout=60):
        sent.append((method, url, headers, body))
        if method == "GET":
            return 200, {}, json.dumps({"Item": {"TicketNumber": 1234, "Subject": "Locked out",
                                                 "For": {"Name": "Jane Doe"}}}).encode()
        return 200, {}, b"{}"
    cfg = {"site": "https://x.incidentiq.com", "site_id": "S1", "token": "T"}
    t = iiq.get_ticket(tid, cfg, http)
    assert t["number"] == "1234" and t["for"] == "Jane Doe"
    iiq.add_note(tid, "did things", cfg=cfg, http=http)
    m, url, h, body = sent[-1]
    assert url.endswith(f"/api/v1.0/tickets/{tid}/activities/new")
    assert h["SiteId"] == "S1" and h["Client"] == "ApiClient" and h["Authorization"] == "Bearer T"
    assert body["ActivityItems"][0]["Comments"] == "did things"

    class S:
        def __init__(self, label, status):
            self.label, self.status = label, status
    note = iiq.summary_note([S("Reset password", "ok"), S("Sign out", "fail")])
    assert "✔ Reset password" in note and "✖ Sign out" in note


# ------------------------------------------------------------- assistant ---
def test_assistant_parse_and_call():
    r = assistant.parse_reply('Sure!\n{"explanation": "Lists them.", "commands": '
                              '[{"args": ["gam", "print", "users", "query", "orgUnitPath=/S"], '
                              '"why": "check"}, {"args": "update user a@s.org suspended on"}], '
                              '"warnings": ["big"]}')
    assert r["commands"][0]["args"][:2] == ["print", "users"]
    assert r["commands"][1]["args"] == ["update", "user", "a@s.org", "suspended", "on"]
    seen = {}

    def http(method, url, headers, body=None, timeout=60):
        seen.update(url=url, headers=headers, body=body)
        return 200, {}, json.dumps({"content": [{"type": "text", "text":
                                                 '{"explanation":"x","commands":[],'
                                                 '"warnings":[]}'}]}).encode()

    class D:
        domain, ous, groups = "s.org", ["/Students", "/Staff"], [{"email": "staff@s.org"}]
        users = [{"email": "secret.kid@s.org", "ou": "/Students"}]
    assistant.ask("move grade 5", D(), {"key": "k", "model": "m", "enabled": True,
                                        "share_users": False}, http)
    assert seen["url"].endswith("/v1/messages") and seen["headers"]["x-api-key"] == "k"
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    text = seen["body"]["messages"][0]["content"]
    assert "/Students" in text and "secret.kid" not in text      # users not shared by default


# -------------------------------------------------------- email approvals ---
def test_email_approvals(qapp, team_dir, monkeypatch):
    from gambit.settings import settings
    settings.set("approvals/email_on", True)
    settings.set("approvals/emails", "boss@s.org")
    settings.set("google/admin_email", "admin@s.org")
    sent = []
    import gambit.directory as d
    monkeypatch.setattr(d, "run_gam_text", lambda a, t=120: (sent.append(a), (0, ""))[1])
    try:
        req = team.new_request([["update", "user", "a@s.org", "suspended", "on"]], "left",
                               title="Suspend a@s.org")
        assert sent and sent[0][0] == "sendemail" and "boss@s.org" in sent[0]
        rows = [{"id": "m1", "From": "Boss <boss@s.org>",
                 "Subject": f"Re: [GAMbit approval {req['id']}] Suspend a@s.org",
                 "Body": "Approve - ok go\\n\\nOn Mon …"},
                {"id": "m2", "From": "intruder@x.com",
                 "Subject": f"Re: [GAMbit approval {req['id']}] x", "Body": "approve"}]
        ran = []
        lines = ea.process(run_text=lambda a, t: (ran.append(a), (0, ""))[1],
                           run_csv=lambda a: (0, rows, ""))
        assert ran == [["update", "user", "a@s.org", "suspended", "on"]]
        assert any("Approved by email" in ln for ln in lines)
        done = next(r for r in team.list_requests() if r["id"] == req["id"])
        assert done["status"] == "done" and "boss@s.org" in done["note"]
        assert ea.process(run_text=lambda a, t: (0, ""), run_csv=lambda a: (0, rows, "")) == []
    finally:
        settings.set("approvals/email_on", False)


# -------------------------------------------------------- custom workflows ---
def test_custom_workflow():
    wf = cw.from_text("Sub", "", "email = Email\nfirst = First name",
                      "Create | create user {email} firstname {first} password {password}\n"
                      "Tell | sendemail to office@s.org subject \"New: {first}\"")
    assert not cw.problems(wf)
    steps = cw.build(wf, {"email": "x@s.org", "first": "Mary Ann"}, "pw1")
    assert steps[0][1] == ["create", "user", "x@s.org", "firstname", "Mary Ann", "password", "pw1"]
    assert steps[1][1][-1] == "New: Mary Ann"
    bad = cw.from_text("X", "", "", "Do | create user {nope}")
    assert any("{nope}" in p for p in cw.problems(bad))
    try:
        cw.build(wf, {"email": "", "first": "A"})
        raise AssertionError("should need email")
    except ValueError:
        pass
    assert cw.load()        # examples when nothing is saved


# --------------------------------------------- assignments and clean-up ---
def test_assignment_sync_plan():
    a = am.read_assignments("Serial Number,Student ID,Asset Tag\nsn1,1001,A-1\nSN2,x@s.org,\n"
                            "SN9,1001,\n")
    users = [{"email": "kid@s.org", "sis_id": "1001", "ou": "/Students/Lincoln/Grade 5"},
             {"email": "x@s.org", "sis_id": "", "ou": "/Students/High/Grade 9"}]
    cros = [{"serialNumber": "SN1", "annotatedUser": "", "orgUnitPath": "/Chromebooks/Spare"},
            {"serialNumber": "SN2", "annotatedUser": "x@s.org", "orgUnitPath": "/Chromebooks/High"}]
    plan = {p["Serial"]: p for p in am.assign_plan(a, cros, users, am.options())}
    assert plan["SN1"]["args"] == ["cros_sn", "SN1", "update", "user", "kid@s.org", "assetid",
                                   "A-1", "ou", "/Chromebooks/Lincoln"]
    assert plan["SN2"]["args"] is None and plan["SN9"]["Change"].startswith("⚠")


def test_cleanup_rules(qapp, team_dir):
    old = (datetime.datetime.now(datetime.timezone.utc) -
           datetime.timedelta(days=400)).isoformat()
    users = [{"email": "gone@s.org", "ou": "/Students/2025", "suspended": False,
              "last_login": old},
             {"email": "keep@s.org", "ou": "/Students/2025", "suspended": False,
              "last_login": old},
             {"email": "new@s.org", "ou": "/Students/2025", "suspended": False,
              "last_login": "Never"},
             {"email": "susp@s.org", "ou": "/Former Staff", "suspended": True, "last_login": old}]
    r = {"name": "Inactive students", "kind": "inactive", "ou": "/Students", "days": 180,
         "except": "keep@s.org"}
    assert [f["email"] for f in am.evaluate(r, users)] == ["gone@s.org"]
    r2 = {"name": "Old staff", "kind": "delete_old", "ou": "/Former Staff", "days": 365}
    assert am.evaluate(r2, users)[0]["args"] == ["delete", "user", "susp@s.org"]
    rel = am.evaluate({"kind": "release", "ou": "/"}, users,
                      [{"primaryEmail": "susp@s.org", "Licenses": "1010020020 Google-Apps"}])
    assert [f["args"][-1] for f in rel] == ["1010020020", "Google-Apps"]
    am.save_rules([r, r2])
    lines = am.run_cleanup(log=lambda *_: None, users=users)
    assert all("sent for approval" in ln for ln in lines)
    reqs = [q for q in team.list_requests("pending") if q.get("kind") == "cleanup"]
    assert len(reqs) == 2 and any(["delete", "user", "susp@s.org"] in q["commands"] for q in reqs)


# --------------------------------------------------------- safer updates ---
def test_update_backup_and_rollback(qapp, monkeypatch):
    from gambit.settings import settings
    from gambit.version import __version__
    path = updaters.prepare_for_update("9.9.9")
    import os
    import zipfile
    assert os.path.isfile(path) and "settings.json" in zipfile.ZipFile(path).namelist()
    assert settings.get("update/previous_version") == __version__
    assert updaters.rollback_target() == ""            # same version → nothing to go back to
    settings.set("update/previous_version", "0.9.0")
    assert updaters.rollback_target() == "0.9.0"
    assert updaters.installer_url("0.9.0").endswith("/v0.9.0/GAMbit-Setup-0.9.0.exe")
    settings.set("update/previous_version", "")


def test_room_usage():
    from gambit.ui.pages.small_tabs import room_usage
    r = room_usage("Library", "lincoln", [
        {"start.dateTime": "2026-10-12T09:00:00-05:00", "end.dateTime": "2026-10-12T10:30:00-05:00"},
        {"start.dateTime": "2026-10-13T09:00:00-05:00", "end.dateTime": "2026-10-13T10:00:00-05:00"},
        {"start.date": "2026-10-14"}])
    assert r["Bookings"] == "2" and r["Hours"] == "2.5"
