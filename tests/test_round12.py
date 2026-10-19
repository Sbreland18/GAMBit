import datetime
import json

from gambit import change_queue as cq, records, release_check as rc, request_catalog as cat
from gambit import team
from gambit.settings import settings
from gambit.tools import baseline as bl, classroom_sync as cs, lost_devices as ld
from gambit.tools import readiness as rd

TODAY = datetime.date(2026, 10, 14)


def _pol(setting, ou, value):
    return {"JSON": json.dumps({"setting": {"type": f"settings/{setting}", "value": value},
                                "policyQuery": {"orgUnitPath": ou}})}


def _cp(name, **fields):
    return {"JSON": json.dumps({"name": name, "fields": [{"name": k, "value": v}
                                                         for k, v in fields.items()]})}


def test_baseline_passes_and_effective():
    assert bl.passes({"eq": False}, False) and bl.passes({"eq": False}, "false")
    assert not bl.passes({"eq": False}, None)
    assert bl.passes({"in": ["DISALLOWED"]}, "DISALLOWED")
    assert bl.passes({"contains": ["STRICT", "MODERATE"]}, "YOUTUBE_RESTRICTED_MODE_MODERATE")
    assert bl.passes({"min": 8}, "10") and not bl.passes({"min": 8}, "6")
    assert bl.passes({"set": True}, "2026-01-01") and not bl.passes({"set": True}, "")
    vals = bl.admin_values([_pol("gmail.auto_forwarding", "/", {"enableAutoForwarding": True}),
                            _pol("gmail.auto_forwarding", "/Students",
                                 {"enableAutoForwarding": False})])
    assert bl.admin_effective(vals, "gmail.auto_forwarding", "/Students/HS") == \
        {"enableAutoForwarding": False}
    assert bl.admin_effective(vals, "gmail.auto_forwarding", "/Staff") == \
        {"enableAutoForwarding": True}
    assert bl._get({"allow_less_secure_apps": False}, "allowLessSecureApps") is False


def test_baseline_check_and_score():
    ous = {"students": "/Students", "staff": "/Staff", "devices": "/"}
    rules = [r for r in bl.rules({"off": []}) if r["id"] in ("forward_students", "safesearch",
                                                             "guest")]
    admin = [_pol("gmail.auto_forwarding", "/Students", {"enableAutoForwarding": False})]
    chrome = {"/Students": [_cp("chrome.users.SafeSearchRestrictedMode",
                                safeSearchRestrictedMode=False)],
              "/": [_cp("chrome.devices.GuestMode", guestModeEnabled=False)]}
    res = bl.check(rules, ous, admin, chrome)
    by = {r["id"]: r for r in res}
    assert by["forward_students"]["ok"] and by["guest"]["ok"]
    assert not by["safesearch"]["ok"]
    assert by["safesearch"]["args"] == ["update", "chromepolicy",
                                        "chrome.users.SafeSearchRestrictedMode",
                                        "safeSearchRestrictedMode", "true", "ou", "/Students"]
    assert bl.score(res) == 67
    # admin settings can't be fixed by GAMbit → console link
    rules2 = [r for r in bl.rules() if r["id"] == "less_secure"]
    res2 = bl.check(rules2, ous, [], {})
    assert len(res2) == 2 and all(not r["ok"] and r["args"] is None and
                                  r["How to fix"].startswith(bl.CONSOLE) for r in res2)
    assert "less_secure" not in {r["id"] for r in bl.rules({"off": ["less_secure"]})}


def test_classroom_sync_plan():
    sec = {"id": "MATH 101.3", "students": ["a@s.org", "b@s.org"],
           "teachers": ["t1@s.org", "t2@s.org"]}
    alias = "math-101-3-27"
    classes = cs.class_map([{"id": "111", "name": "Math", "aliases": f"d:{alias}"}])
    assert classes == {alias: {"id": "111", "name": "Math"}}
    cur = cs.members([{"courseId": "111", "profile.emailAddress": "b@s.org",
                       "userRole": "STUDENT"},
                      {"courseId": "111", "profile.emailAddress": "old@s.org",
                       "userRole": "STUDENT"},
                      {"courseId": "111", "profile.emailAddress": "t1@s.org",
                       "userRole": "TEACHER"}])
    p = cs.plan([sec], classes, cur, 2027, {"remove": False, "teachers": True})
    assert p[0]["adds"] == ["a@s.org"] and p[0]["removes"] == []
    assert p[0]["commands"] == [["course", "111", "add", "student", "a@s.org"],
                                ["course", "111", "add", "teacher", "t2@s.org"]]
    p2 = cs.plan([sec], classes, cur, 2027, {"remove": True, "teachers": False})
    assert p2[0]["removes"] == ["old@s.org"] and len(p2[0]["commands"]) == 2
    assert cs.totals(p2)["commands"] == 2
    assert cs.too_big(p2, {"max_changes": 1}) and not cs.too_big(p2, {"max_changes": 300})
    # unknown classes are skipped; matching rosters produce nothing
    assert cs.plan([{**sec, "id": "X"}], classes, cur, 2027, {}) == []


def test_records_flow(monkeypatch):
    monkeypatch.setattr("gambit.activity.record", lambda *a, **k: None)
    r = records.new("Kid@S.org", "ferpa", "Parent", ["mail", "drive"], True,
                    received="2026-10-01")
    assert r["email"] == "kid@s.org" and r["due"] == "2026-11-15"
    assert records.new("a@s.org", "legal", "Lawyer", [], True)["due"] == ""
    assert records._id("Matter created\nabc123XYZ\n") == "abc123XYZ"
    calls = []

    def run_text(args, _t):
        calls.append(args)
        return 0, {"vaultmatter": "MATTER01", "vaulthold": "HOLD0001",
                   "vaultexport": "EXP00001"}[args[1]] + "\n"
    assert records.start(r, run_text, "me") == []
    assert r["matter"] == "MATTER01" and len(r["holds"]) == 2 and len(r["exports"]) == 2
    assert r["status"] == "exporting"
    assert calls[1][:5] == ["create", "vaulthold", "matter", "MATTER01", "name"]
    n = len(calls)
    records.start(r, run_text, "me")       # idempotent
    assert len(calls) == n
    assert records.update_status(r, [{"id": "EXP00001", "status": "COMPLETED"}]) == 2
    assert r["status"] == "ready to download"
    assert records.close_args(r) == ["close", "vaultmatter", "MATTER01"]
    late = records.due_soon([r], 7, datetime.date(2026, 11, 10))
    assert late == [r]
    assert records.due_soon([r], 7, datetime.date(2026, 10, 2)) == []
    bad = records.new("b@s.org", "other", "x", ["mail"], False)
    assert records.start(bad, lambda a, t: (1, "denied"), "me")[0].startswith("Couldn't")


def test_readiness():
    rows = [{"primaryEmail": "new@s.org", "name.fullName": "New Hire", "orgUnitPath":
             "/Staff/Lincoln", "suspended": "False", "creationTime": "2026-10-10T12:00:00Z",
             "lastLoginTime": "Never", "licenses": "1010020020",
             "organizations.0.title": "Teacher"},
            {"primaryEmail": "old@s.org", "orgUnitPath": "/Staff", "creationTime":
             "2025-01-01T00:00:00Z"},
            {"primaryEmail": "kid@s.org", "orgUnitPath": "/Students", "creationTime":
             "2026-10-12T00:00:00Z"}]
    people = rd.new_staff(rows, {"staff_root": "/Staff", "days": 14}, TODAY)
    assert [p["email"] for p in people] == ["new@s.org"]
    p = people[0]
    assert not p["signed_in"] and p["licenses"] == ["1010020020"]
    cs_ = rd.checks(p, {"lincoln-staff@s.org"}, False, None,
                    {"license": "1010020020", "groups": "* = all-staff@s.org\n"
                     "/staff/lincoln = lincoln-staff@s.org", "signature": "on"},
                    {"classroom_group": "teachers@s.org"}, "s.org")
    items = {c["item"]: c for c in cs_}
    assert items["Account is active"]["ok"] and items["License 1010020020"]["ok"]
    assert not items["In group all-staff@s.org"]["ok"]
    assert items["In group all-staff@s.org"]["fix"][0][1][:3] == ["update", "group",
                                                                   "all-staff@s.org"]
    assert items["In group lincoln-staff@s.org"]["ok"]
    assert not items["In group teachers@s.org"]["ok"]
    assert not items["Email signature"]["ok"] and items["Email signature"]["fix"]
    assert "Has signed in" in items and items["Has signed in"].get("info")
    assert "new@s.org" in rd.email_text(p, cs_)


def test_lost_devices(tmp_path, monkeypatch):
    monkeypatch.setattr("gambit.fleet.data_dir", lambda: str(tmp_path))
    f = ld.facts({"serialNumber": "abc123", "orgUnitPath": "/Students/HS", "status": "ACTIVE",
                  "recentUsers.0.email": "kid@s.org", "lastKnownNetwork.0.ipAddress":
                  "10.0.0.5", "annotatedAssetId": "A-77"})
    assert f["serial"] == "ABC123" and f["last_user"] == "kid@s.org"
    cmds = ld.mark_commands(f, "stolen", {"lost_ou": "/Lost"})
    assert ["cros_sn", "ABC123", "update", "action", "disable"] in cmds
    assert cmds[-1] == ["cros_sn", "ABC123", "update", "ou", "/Lost"]
    assert "STOLEN" in cmds[0][4]
    assert len(ld.mark_commands({**f, "status": "DISABLED"}, "lost", {})) == 1
    rec = ld.record(f, "stolen", "Principal", "taken from bus", "me")
    ld.record(f, "stolen", "Principal", "again", "me")
    assert len(ld.load()) == 1
    back = ld.found_commands(rec)
    assert back[0] == ["cros_sn", "ABC123", "update", "action", "reenable"]
    assert back[-1] == ["cros_sn", "ABC123", "update", "ou", "/Students/HS"]
    html = ld.report_html(rec, "Hancock")
    assert "ABC123" in html and "10.0.0.5" in html and "<script" not in html


def test_change_queue_freeze_and_run(team_dir, monkeypatch):
    monkeypatch.setattr("gambit.activity.record", lambda *a, **k: None)
    settings.set("safety/dry_run", False)
    fz = cq.new_freeze("State testing", "2026-10-14", "2026-10-16", [], "me")
    assert cq.span(fz) == ("2026-10-14T00:00", "2026-10-16T23:59")
    cq.save_freezes([fz])
    during = datetime.datetime(2026, 10, 15, 10, 0)
    after = datetime.datetime(2026, 10, 17, 9, 0)
    susp = ["update", "user", "a@s.org", "suspended", "on"]
    assert cq.active_freeze(susp, during)["name"] == "State testing"
    assert cq.active_freeze(susp, after) is None
    assert cq.active_freeze(["print", "users"], during) is None
    assert cq.active_freeze(["update", "user", "a@s.org", "firstname", "A"], during) is None
    req = team.new_request([susp], "leaving", title="Suspend a", by="me", notify=False)
    cq.add([susp], "2026-10-15T09:00", "Suspend a", "me", req["id"])
    ran = []
    run_text = lambda a, t: (ran.append(a), (0, ""))[1]  # noqa: E731
    lines = cq.run_due(lambda *_: None, run_text, during)
    assert not ran and "waiting" in lines[0]
    assert cq.run_due(lambda *_: None, run_text, during) == []   # only told once
    cq.run_due(lambda *_: None, run_text, after)
    assert ran == [susp] and cq.queue()[0]["status"] == "done"
    assert next(r for r in team.list_requests() if r["id"] == req["id"])["status"] == "done"
    assert cq.tonight() > datetime.datetime.now().isoformat(timespec="minutes")


def test_request_catalog_build():
    o = cat.options()
    hdr = ["Timestamp", "Email Address", "What do you need?", "First name", "Last name",
           "End date", "Group email", "People to add", "People to remove", "Class name",
           "Section", "Teacher email", "Serial number", "Move to", "Details"]
    cols = cat.columns(hdr)
    assert cols["requester"] == "Email Address" and cols["teacher"] == "Teacher email"
    row = {h: "" for h in hdr}
    row.update({"Timestamp": "10/14/2026 8:00", "Email Address": "Sec@s.org",
                "What do you need?": "Substitute account", "First name": "Jo",
                "Last name": "O'Neil", "End date": "10/30/2026"})
    r = cat.build(row, cols, o, "s.org")
    assert r["kind"] == "sub" and r["extra"]["temp"]["end"] == "2026-10-30"
    assert r["commands"][0][:3] == ["create", "user", "sub.jooneil@s.org"]
    assert r["commands"][0][r["commands"][0].index("notify") + 1] == "sec@s.org"
    g = cat.build({**row, "What do you need?": "Group change", "Group email": "staff@s.org",
                   "People to add": "a@s.org, b@s.org", "People to remove": "c@s.org"},
                  cols, o, "s.org")
    assert len(g["commands"]) == 3 and g["commands"][2][3] == "remove"
    c = cat.build({**row, "What do you need?": "New Classroom class", "Class name": "Art",
                   "Teacher email": "t@s.org"}, cols, o, "s.org")
    assert c["commands"][0][-4:] == ["owner", "t@s.org", "status", "active"]
    m = cat.build({**row, "What do you need?": "Move a Chromebook", "Serial number": "x9",
                   "Move to": "Cart 4"}, cols, o, "s.org")
    assert m["commands"] == [["cros_sn", "X9", "update", "location", "Cart 4"]]
    bad = cat.build({**row, "What do you need?": "Move a Chromebook"}, cols, o, "s.org")
    assert bad["problem"]


def test_request_catalog_process(team_dir, monkeypatch):
    monkeypatch.setattr("gambit.activity.record", lambda *a, **k: None)
    monkeypatch.setattr("gambit.google_io.admin_email", lambda: "admin@s.org")
    monkeypatch.setattr("gambit.approval_policy.auto_rule",
                        lambda c, users: c[0] == "cros_sn")
    users = [{"email": "sec@s.org", "ou": "/Staff/Lincoln", "suspended": False},
             {"email": "kid@s.org", "ou": "/Students", "suspended": False}]
    hdr = ["Timestamp", "Email Address", "What do you need?", "First name", "Last name",
           "Serial number", "Move to"]
    rows = [dict(zip(hdr, ["1", "sec@s.org", "Substitute", "Jo", "Smith", "", ""])),
            dict(zip(hdr, ["2", "sec@s.org", "Move a Chromebook", "", "", "SN1", "/Carts"])),
            dict(zip(hdr, ["3", "kid@s.org", "Substitute", "Jo", "Smith", "", ""]))]
    mails, ran = [], []
    run_text = lambda a, t: (ran.append(a), (0, ""))[1]  # noqa: E731
    lines = cat.process(lambda *_: None, rows, None, users, run_text,
                        lambda to, s, b: mails.append((to, s)))
    assert ran == [["cros_sn", "SN1", "update", "ou", "/Carts"]]
    assert any("sent for approval" in ln for ln in lines)
    assert any("not active staff" in ln for ln in lines)
    pend = [r for r in team.list_requests() if r.get("kind") == "catalog_sub"]
    assert len(pend) == 1 and pend[0]["temp"]["email"] == "sub.josmith@s.org"
    assert {m[0] for m in mails} == {"sec@s.org"}
    assert cat.process(lambda *_: None, rows, None, users, run_text, lambda *a: None) == []
    # approved and done → tracked as a time-limited account
    tracked = []
    monkeypatch.setattr(cat, "_track", lambda t: tracked.append(t["email"]))
    team.update_request(pend[0], "done")
    assert cat.finalize() and tracked == ["sub.josmith@s.org"]
    assert cat.finalize() == []


def test_release_check(monkeypatch):
    monkeypatch.setattr(rc, "checks", lambda: [("GAM runs", ["version"]),
                                               ("Reads the domain", ["info", "domain"]),
                                               ("Settings file", None)])
    ok = lambda a, t: (0, "fine")  # noqa: E731
    before = rc.before_update("9.9.9", ok)
    assert all(b["OK"] for b in before) and rc.pending_for("9.9.9")
    assert not rc.pending_for("9.9.8")
    broken = lambda a, t: (1, "boom") if a == ["info", "domain"] else (0, "")  # noqa: E731
    after, bad = rc.after_update(broken)
    assert [b["Check"] for b in bad] == ["Reads the domain"] and bad[0]["Detail"] == "boom"
    assert not rc.pending_for("9.9.9")
    # something that already failed before isn't a regression
    assert rc.regressions([{"Check": "X", "OK": False}], [{"Check": "X", "OK": False}]) == []
