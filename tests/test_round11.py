import datetime
import json

from gambit import leader_sheet, saved_questions as sq, scorecard, team, temp_accounts as ta
from gambit import timemachine as tm
from gambit.tools import app_vetting as av, campaigns as cp, ownership as ow
from gambit.tools import phishing as ph, policy_sets as ps

TODAY = datetime.date(2026, 10, 14)
USERS = [{"email": "kid1@s.org", "ou": "/Students/Lincoln", "suspended": False},
         {"email": "kid2@s.org", "ou": "/Students/Lincoln", "suspended": False},
         {"email": "teach@s.org", "ou": "/Staff/Lincoln", "suspended": False},
         {"email": "gone@s.org", "ou": "/Former Staff", "suspended": True},
         {"email": "boss@s.org", "ou": "/Staff/Office", "suspended": False}]


def test_phishing():
    q = ph.query("bad@paypa1.com", "Your account is locked", "https://evil.example/x?y", 3)
    assert q == 'from:bad@paypa1.com subject:"Your account is locked" evil.example newer_than:3d'
    try:
        ph.query()
        raise AssertionError
    except ValueError:
        pass
    ent = ph.entity("all")
    assert ph.count_args(ent, q)[:5] == ["all", "users_ns", "print", "messages", "query"]
    assert ph.trash_args(ph.entity("ou", "/Staff"), q)[-3:] == ["doit", "max_to_trash", "50"]
    assert ph.entity("ou", "/Staff") == ["ou_and_children_ns", "/Staff"]
    rows = [{"User": "a@s.org", "messages": "2"}, {"User": "b@s.org", "messages": "0"},
            {"User": "c@s.org", "messages": "5"}]
    found = ph.counts(rows)
    assert [f["mailbox"] for f in found] == ["c@s.org", "a@s.org"]
    assert "2 mailbox" in ph.incident_text(q, found, [{"mailbox": "a@s.org", "count": 1}])
    assert ph.replies_args(ent, "bad@x.com", 7)[5] == "in:sent to:bad@x.com newer_than:7d"


def test_policy_sets_revert_and_due(team_dir):
    before = [{"JSON": json.dumps({"name": "chrome.users.Incognito", "direct": True,
                                   "fields": [{"name": "incognitoModeAvailability",
                                               "value": "AVAILABLE"}]})}]
    tpl = [{"JSON": json.dumps({"name": "chrome.users.Incognito", "direct": True,
                                "fields": [{"name": "incognitoModeAvailability",
                                            "value": "UNAVAILABLE"}]})},
           {"JSON": json.dumps({"name": "chrome.users.Extensions", "direct": True,
                                "fields": [{"name": "blockAll", "value": True}]})}]
    p = ps.new_plan("testing", "Spring testing", ["/Students/Lincoln"], "/Testing/Template",
                    start="2026-10-14", end="2026-10-16")
    cmds = ps.commands_for(p, "/Students/Lincoln", tpl)
    assert ["update", "chromepolicy", "chrome.users.Extensions", "blockAll", "true", "ou",
            "/Students/Lincoln"] in cmds
    rev = ps.revert_commands(before, ps.schemas_in(cmds), "/Students/Lincoln")
    assert rev == [["update", "chromepolicy", "chrome.users.Incognito",
                    "incognitoModeAvailability", "AVAILABLE", "ou", "/Students/Lincoln"],
                   ["delete", "chromepolicy", "chrome.users.Extensions", "ou",
                    "/Students/Lincoln"]]
    assert ps.due(p, datetime.date(2026, 10, 13)) == ""
    assert ps.due(p, TODAY) == "apply"
    pols = ps.parse_policies("chrome.users.Foo a=1 b=two\n# note\n")
    assert pols == [{"schema": "chrome.users.Foo", "values": {"a": "1", "b": "two"}}]
    assert ps.policies_text(pols) == "chrome.users.Foo a=1 b=two"
    # the daily task applies and later reverts, saving the "before" first
    ps.save([p])
    ran = []

    def run_csv(a):
        return 0, (tpl if "/Testing/Template" in a else before), ""
    lines = ps.run_due(lambda _l: None, run_csv, lambda a, t: (ran.append(a), (0, ""))[1],
                       TODAY)
    assert "ON" in lines[0] and len(ran) == 2
    saved = ps.load()[0]
    assert saved["state"] == "applied" and saved["before"]["/Students/Lincoln"] == before
    ran.clear()
    lines = ps.run_due(lambda _l: None, run_csv, lambda a, t: (ran.append(a), (0, ""))[1],
                       datetime.date(2026, 10, 17))
    assert "OFF" in lines[0] and ran == rev and ps.load()[0]["state"] == "reverted"


def test_rollout_watch_and_verdict():
    p = ps.new_plan("rollout", "Block ext", ["/Students/Lincoln", "/Students"], "", [],
                    watch_days=3)
    p.update(state="pilot", start="2026-10-10")
    devs = [{"ou": "/Students/Lincoln", "status": "ACTIVE",
             "last_sync": datetime.date(2026, 10, 1)},
            {"ou": "/Students/Lincoln", "status": "ACTIVE",
             "last_sync": datetime.date(2026, 10, 13)}]
    tickets = [{"for_email": "kid1@s.org", "created": "2026-10-12 08:00"},
               {"for_email": "teach@s.org", "created": "2026-10-12 08:00"}]
    n = ps.watch_numbers(p, USERS, devs, tickets, TODAY)
    assert n == {"date": "2026-10-14", "tickets": 1, "devices": 2, "not_checking_in": 1}
    p["baseline"] = {"tickets": 0, "not_checking_in": 0}
    p["watch"] = [n]
    assert ps.verdict(p).startswith("✔")
    p["watch"] = [{**n, "tickets": 9}]
    assert ps.verdict(p).startswith("⚠")


def test_campaign():
    rows = [{"primaryEmail": "a@s.org", "orgUnitPath": "/Staff/Lincoln",
             "isEnrolledIn2Sv": "True", "suspended": "False"},
            {"primaryEmail": "b@s.org", "orgUnitPath": "/Staff/Lincoln",
             "isEnrolledIn2Sv": "False", "name.fullName": "Bea"},
            {"primaryEmail": "c@s.org", "orgUnitPath": "/Staff/Office", "isEnrolledIn2Sv": "True"},
            {"primaryEmail": "d@s.org", "orgUnitPath": "/Students/X", "isEnrolledIn2Sv": "False"},
            {"primaryEmail": "e@s.org", "orgUnitPath": "/Staff/Office", "suspended": "True"}]
    o = {**cp.options(), "root": "/Staff", "deadline": "2026-11-01"}
    ppl = cp.people(rows, o)
    assert {p["email"] for p in ppl} == {"a@s.org", "b@s.org", "c@s.org"}
    prog = {r["Building"]: r for r in cp.progress(ppl, 90)}
    assert prog["Lincoln"]["%"] == 50 and prog["Office"]["Status"] == "ready to enforce"
    assert prog["All staff"]["Set up"] == 2
    assert cp.remind_batches(ppl) == [["b@s.org"]]
    args = cp.reminder_args(["b@s.org"], o, "it@s.org")
    assert args[:5] == ["sendemail", "to", "it@s.org", "bcc", "b@s.org"]
    assert "2026-11-01" in args[-1]
    assert "Bea" in cp.escalation_text("Lincoln", [p for p in ppl if not p["enrolled"]], o)


def test_app_vetting():
    lst = av.parse_list("App Name,Client ID,Status\nKahoot!,,Approved\nSketchy Quiz,999,"
                        "Not approved\n")
    assert lst[0]["name"] == "Kahoot!" and lst[1]["status"] == "denied"
    assert av.parse_list("Kahoot\nQuizlet\n")[1] == {"name": "Quizlet", "client_id": "",
                                                     "status": "approved"}
    rows = [{"user": "kid1@s.org", "clientId": "111", "displayText": "Kahoot! - learning",
             "scopes": "openid email"},
            {"user": "kid1@s.org", "clientId": "999", "displayText": "Sketchy Quiz",
             "scopes": "https://mail.google.com/"},
            {"user": "kid2@s.org", "clientId": "777", "displayText": "Mystery App",
             "scopes": "https://www.googleapis.com/auth/drive"},
            {"user": "teach@s.org", "clientId": "777", "displayText": "Mystery App",
             "scopes": ""}]
    apps = {a["Client ID"]: a for a in av.summarize(rows, lst, USERS)}
    assert apps["111"]["Status"] == "approved"
    assert apps["999"]["Status"] == "denied" and "Gmail" in apps["999"]["Can see"]
    assert apps["777"]["Status"] == "not on the list" and apps["777"]["Students"] == 1
    assert "Google Drive" in apps["777"]["Can see"]
    assert av.revoke_commands(apps["777"], True) == [["users", "kid2@s.org", "delete", "tokens",
                                                      "clientid", "777"]]
    assert av.revoke_commands(apps["777"])[0][1] == "kid2@s.org,teach@s.org"


def test_temp_accounts(team_dir):
    items = []
    ta.add(items, "Sub.One@s.org", "Substitute", "boss@s.org", "2026-10-18", "me")
    ta.add(items, "sub2@s.org", "Contractor / vendor", "", "2026-10-10", "me")
    ta.add(items, "sub3@s.org", "Other", "", "2026-12-01", "me")
    warn, expire = ta.due(items, {"warn_days": 7}, TODAY)
    assert [w["email"] for w in warn] == ["sub.one@s.org"]
    assert [e["email"] for e in expire] == ["sub2@s.org"]
    assert ta.expire_args(expire[0], {"expired_ou": "/Ended"}) == [
        ["update", "user", "sub2@s.org", "suspended", "on", "ou", "/Ended"]]
    ta.save(items)
    sent, ran = [], []

    def run(a, t):
        (sent if a[0] == "sendemail" else ran).append(a)
        return 0, ""
    lines = ta.run(lambda _l: None, run, TODAY)
    assert sent and "sub.one@s.org,boss@s.org" in sent[0]
    assert ran == [["update", "user", "sub2@s.org", "suspended", "on"]]
    after = {i["email"]: i for i in ta.load()}
    assert after["sub2@s.org"]["status"] == "expired" and after["sub.one@s.org"]["warned"]
    assert len(lines) == 2
    ta.extend(after["sub2@s.org"], "2026-12-31", "me")
    assert after["sub2@s.org"]["status"] == "active" and after["sub2@s.org"]["end"] == \
        "2026-12-31"


def test_ownership():
    users = {u["email"]: u for u in USERS}
    g = ow.groups([{"email": "lincoln-staff@s.org", "Owners": ""},
                   {"email": "old@s.org", "Owners": "gone@s.org"},
                   {"email": "ok@s.org", "Owners": "teach@s.org"},
                   {"email": "ext@s.org", "Owners": "someone@gmail.com"}], users, "boss@s.org")
    assert [x["What"] for x in g] == ["lincoln-staff@s.org", "old@s.org"]
    assert g[1]["args"] == [["update", "group", "old@s.org", "add", "owner", "user",
                             "boss@s.org"]]
    d = ow.shared_drives([{"id": "D1", "name": "Athletics",
                           "permission.emailAddress": "gone@s.org",
                           "permission.role": "organizer"},
                          {"id": "D2", "name": "Math", "permission.emailAddress": "teach@s.org",
                           "permission.role": "organizer"},
                          {"id": "D3", "name": "Empty"}], users, "admin@s.org", "boss@s.org")
    assert {x["What"] for x in d} == {"Athletics", "Empty"}
    assert d[0]["args"][0][:4] == ["user", "admin@s.org", "add", "drivefileacl"]
    sup = ow.supervisor_lookup(USERS, [{"email": "gone@s.org", "supervisor": "Teach@s.org"}],
                               "boss@s.org")
    c = ow.courses([{"id": "C1", "name": "Bio", "ownerEmail": "gone@s.org"},
                    {"id": "C2", "name": "Art", "ownerEmail": "teach@s.org"}], users, sup)
    assert len(c) == 1 and c[0]["args"] == [["course", "C1", "add", "teacher", "teach@s.org"],
                                            ["update", "course", "C1", "owner", "teach@s.org"]]
    st = ow.suspended_storage([{"email": "gone@s.org", "accounts:drive_used_quota_in_mb": "2048"},
                               {"email": "teach@s.org",
                                "accounts:drive_used_quota_in_mb": "9999"}], users, 100, sup)
    assert st[0]["What"] == "2.0 GB" and st[0]["args"][0][:3] == ["create", "datatransfer",
                                                                  "gone@s.org"]


def test_timemachine(team_dir):
    u1 = [{"primaryEmail": "kid1@s.org", "name.fullName": "Kid", "orgUnitPath": "/Students/A",
           "suspended": "False", "aliases.0": "k1@s.org", "Licenses": "1010310008"}]
    m1 = [{"group": "g1@s.org", "email": "kid1@s.org", "role": "MEMBER"},
          {"group": "g2@s.org", "email": "kid1@s.org", "role": "OWNER"}]
    u2 = [{"primaryEmail": "kid1@s.org", "name.fullName": "Kid", "orgUnitPath": "/Students/B",
           "suspended": "True", "Licenses": ""}]
    m2 = [{"group": "g3@s.org", "email": "kid1@s.org", "role": "MEMBER"}]
    tm.save(tm.build(u1, m1), datetime.date(2026, 10, 12))
    tm.save(tm.build(u2, m2), datetime.date(2026, 10, 13))
    assert tm.dates()[:2] == ["2026-10-13", "2026-10-12"]
    then, now = tm.account("2026-10-12", "kid1@s.org"), tm.account("2026-10-13", "kid1@s.org")
    assert then["aliases"] == ["k1@s.org"] and then["groups"]["g2@s.org"] == "OWNER"
    what = [r["What"] for r in tm.diff(then, now)]
    assert what.count("Group") == 3 and "Org unit" in what and "License" in what
    steps = [a for _l, a in tm.restore_commands("kid1@s.org", then, now)]
    assert ["update", "user", "kid1@s.org", "ou", "/Students/A"] in steps
    assert ["update", "user", "kid1@s.org", "suspended", "off"] in steps
    assert ["create", "alias", "k1@s.org", "user", "kid1@s.org"] in steps
    assert ["user", "kid1@s.org", "add", "license", "1010310008"] in steps
    assert ["update", "group", "g2@s.org", "add", "owner", "user", "kid1@s.org"] in steps
    assert ["update", "group", "g3@s.org", "remove", "user", "kid1@s.org"] in steps
    assert len(tm.restore_commands("kid1@s.org", then, now, False)) == 4
    assert tm.changes_over_time("kid1@s.org")[0]["Date"] == "2026-10-13"
    n = tm.run(lambda _l: None, lambda a: (0, u1 if a[1] == "users" else m1, ""))
    assert n == 1


def test_saved_questions(team_dir):
    q = sq.new("Who at Lincoln hasn't signed in?", "weekly", "me@s.org", "me")
    assert sq.is_due(q, datetime.date(2026, 10, 12))          # a Monday
    assert not sq.is_due(q, TODAY)
    assert sq.is_due({**q, "every": "daily"}, TODAY)
    assert not sq.is_due({**q, "every": "daily", "last_run": "2026-10-14T06:30"}, TODAY)
    sq.save([q])
    from gambit.settings import settings
    settings.set("assistant/api_key", "k")
    replies = [{"stop_reason": "end_turn", "content": [{"type": "text", "text": "Nobody."}]}]

    def http(method, url, headers, body=None, timeout=60):
        return 200, {}, json.dumps(replies[0]).encode()
    mails = []
    try:
        lines = sq.run(lambda _l: None, datetime.date(2026, 10, 12), run=lambda a: (0, ""),
                       http=http, send=lambda to, s, b: mails.append((to, s, b)))
    finally:
        settings.set("assistant/api_key", "")
    assert "Answered" in lines[0] and mails[0][0] == "me@s.org" and "Nobody." in mails[0][2]
    assert sq.load()[0]["last_answer"] == "Nobody."


def test_leader_sheet(team_dir):
    from gambit.settings import settings
    scorecard.record({"inactive": 5, "tsv_pct": 40}, {"Lincoln": {"students": 10,
                                                                  "inactive": 2}},
                     datetime.date(2026, 10, 5))
    scorecard.record({"inactive": 3, "tsv_pct": 60}, {"Lincoln": {"students": 10,
                                                                  "inactive": 1}},
                     datetime.date(2026, 10, 12))
    t = leader_sheet.tabs([{"number": "1", "created": "x", "for": "a", "subject": "s",
                            "kind": "account"}],
                          [{"When": "2026-10-10T05:20", "Finding": "Mass delete"},
                           {"When": "2026-10-11T05:20", "Finding": "Mass delete"}], TODAY)
    assert t["Scorecard"][0][0] == "Measure"
    sc = {r[0]: r for r in t["Scorecard"][1:]}
    assert sc["Staff with 2-Step Verification (%)"][3] == 20
    assert t["Schools"][1][:3] == ["Lincoln", 10, 1]
    assert t["Unusual activity (30 days)"][1] == ["Mass delete", 2]
    up = []
    settings.set("leadersheet/url", "https://docs.google.com/spreadsheets/d/ABC/edit")
    try:
        done = leader_sheet.push(lambda _l: None, lambda url, tab, path: up.append((tab, path)),
                                 tickets=[], findings=[])
    finally:
        settings.set("leadersheet/url", "")
    assert "Scorecard" in done and "Open tickets" in done and len(up) == len(done)
    assert open(up[0][1], encoding="utf-8").readline().startswith("Measure")
    assert team  # fixture keeps the team folder
