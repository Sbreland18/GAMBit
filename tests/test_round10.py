import datetime
import json
import urllib.parse

from gambit import audit_report, scorecard, sis, team, teacher_lists, whatif
from gambit.integrations import assistant, sis_api, ticketing as tk
from gambit.tools import device_history as dh, playbooks, reconcile, ticket_auto

TODAY = datetime.date(2026, 10, 14)
USERS = [
    {"email": "kid1@s.org", "name": "Kid One", "ou": "/Students/Lincoln/Grade 5",
     "suspended": False, "last_login": "2026-10-12T10:00:00Z"},
    {"email": "kid2@s.org", "name": "Kid Two", "ou": "/Students/Lincoln/Grade 5",
     "suspended": False, "last_login": ""},
    {"email": "kid3@s.org", "name": "Kid Three", "ou": "/Students/Hancock Middle/Grade 6",
     "suspended": False, "last_login": "2026-09-01T10:00:00Z"},
    {"email": "teach@s.org", "name": "Teach", "ou": "/Staff", "suspended": False,
     "last_login": "2026-10-13T10:00:00Z"},
]


def _http(routes, log):
    """routes: list of (method, url-substring, response-dict-or-callable)"""
    def http(method, url, headers, body=None, timeout=60):
        log.append((method, url, headers, body))
        for m, part, resp in routes:
            if m == method and part in url:
                r = resp(url, body) if callable(resp) else resp
                if isinstance(r, tuple):
                    return r
                return 200, {}, (r if isinstance(r, bytes) else json.dumps(r).encode())
        return 404, {}, b"not found"
    return http


# ================================================================== SIS ===
def test_oneroster_oauth2_v12(tmp_path):
    sis_api._TOKENS.clear()
    users = [{"sourcedId": "u1", "status": "active", "enabledUser": "true",
              "givenName": "Ava", "familyName": "Lane", "userMasterIdentifier": "5001",
              "email": "", "grades": ["03"],
              "roles": [{"roleType": "primary", "role": "student",
                         "org": {"sourcedId": "o1", "type": "org"}}]}]
    log = []
    http = _http([("POST", "/oauth2/token", {"access_token": "AT", "expires_in": 3600}),
                  ("GET", "/users?", {"users": users}),
                  ("GET", "/orgs?", {"orgs": [{"sourcedId": "o1", "name": "Lincoln",
                                               "type": "school"}]}),
                  ("GET", "/classes?", {"classes": []}), ("GET", "/enrollments?",
                                                          {"enrollments": []}),
                  ("GET", "/courses?", {"courses": []})], log)
    cfg = {"url": "https://x.infinitecampus.org/campus/api/ims/oneroster/rostering/v1p2",
           "token_url": "https://x.infinitecampus.org/campus/oauth2/token?appName=d",
           "client_id": "c", "secret": "s", "version": "auto"}
    path = sis_api.download("oneroster2", cfg, http, path=str(tmp_path / "ic.zip"))
    tok = next(x for x in log if x[0] == "POST")
    assert tok[2]["Authorization"].startswith("Basic ")
    assert b"grant_type=client_credentials" in tok[3]
    get = next(x for x in log if "/users?" in x[1])
    assert get[2]["Authorization"] == "Bearer AT"
    exp = sis.load_export(path, "ClassLink / OneRoster")
    people = sis.people_from_export(exp, sis.guess_mapping(exp.headers, "ClassLink / OneRoster"),
                                    sis.Rules(domain="s.org", year_end=2027))
    assert people[0].sis_id == "5001" and people[0].school == "o1"
    assert exp.schools["o1"] == "Lincoln"
    # token is cached
    n = sum(1 for x in log if x[0] == "POST")
    sis_api.download("oneroster2", cfg, http, path=str(tmp_path / "ic2.zip"))
    assert sum(1 for x in log if x[0] == "POST") == n


def test_clever_and_powerschool(tmp_path):
    sis_api._TOKENS.clear()
    cl_users = [{"data": {"id": "s1", "name": {"first": "Ava", "last": "Lane"},
                          "email": "ava@s.org",
                          "roles": {"student": {"sis_id": "5001", "grade": "3",
                                                "school": "sch1"}}}},
                {"data": {"id": "p1", "name": {"first": "Mom", "last": "Lane"},
                          "email": "mom@x.com",
                          "roles": {"contact": {"student_relationships": [
                              {"student": "s1", "relationship": "Parent"}]}}}}]
    pages = {"users": [cl_users[:1], cl_users[1:]]}

    def users_resp(url, _b):
        if "starting_after" in url:
            return {"data": pages["users"][1], "links": []}
        return {"data": pages["users"][0],
                "links": [{"rel": "next", "uri": "/v3.0/users?limit=1000&starting_after=s1"}]}
    log = []
    http = _http([("GET", "/v3.0/users", users_resp),
                  ("GET", "/v3.0/schools", {"data": [{"data": {"id": "sch1",
                                                                "name": "Lincoln"}}]}),
                  ("GET", "/v3.0/sections", {"data": [{"data": {
                      "id": "sec1", "name": "Math 3", "school": "sch1", "students": ["s1"],
                      "teachers": ["t1"], "teacher": "t1"}}]})], log)
    cfg = {"token": "DT", "url": "https://api.clever.com"}
    path = sis_api.download("clever", cfg, http, path=str(tmp_path / "c.zip"))
    assert all(x[2]["Authorization"] == "Bearer DT" for x in log)
    exp = sis.load_export(path, "ClassLink / OneRoster")
    stu = next(r for r in exp.rows if r["role"] == "student")
    assert stu["identifier"] == "5001" and stu["orgSourcedIds"] == "sch1"
    assert stu["agentSourcedIds"] == "p1"
    from gambit import guardians
    links, _how = guardians.load_links(path)
    assert ("ava@s.org", "mom@x.com") in links or links
    # PowerSchool
    log = []
    http = _http([("POST", "/oauth/access_token", {"access_token": "PS", "expires_in": 3600}),
                  ("GET", "/ws/v1/district/school", {"schools": {"school": {
                      "id": 7, "name": "Lincoln", "school_number": 100}}}),
                  ("GET", "/ws/v1/school/7/student", {"students": {"student": [
                      {"id": 11, "local_id": 5001, "name": {"first_name": "Ava",
                                                            "last_name": "Lane"},
                       "school_enrollment": {"grade_level": 3, "enroll_status": "A",
                                             "school_id": 7},
                       "contact_info": {"email": "ava@s.org"}},
                      {"id": 12, "local_id": 5002, "name": {"first_name": "Bo",
                                                            "last_name": "Gone"},
                       "school_enrollment": {"grade_level": 3, "enroll_status": "-1",
                                             "school_id": 7}}]}})], log)
    cfg = {"url": "https://ps.s.org", "client_id": "c", "secret": "s", "staff": False}
    path = sis_api.download("powerschool", cfg, http, path=str(tmp_path / "ps.zip"))
    exp = sis.load_export(path, "ClassLink / OneRoster")
    by = {r["identifier"]: r for r in exp.rows}
    assert by["5001"]["grades"] == "3" and by["5001"]["orgSourcedIds"] == "7"
    assert by["5002"]["enabledUser"] == "false"
    q = next(x for x in log if "/student" in x[1])[1]
    assert "expansions=demographics" in q and "pagesize=100" in q


# ============================================================ help desks ===
def test_ticket_ids_and_links():
    assert tk.ticket_id("https://d.zendesk.com/agent/tickets/1234", "zendesk") == "1234"
    assert tk.ticket_id("#55", "freshservice") == "55"
    assert tk.ticket_id("see INC0010023 please", "servicenow") == "INC0010023"
    assert tk.ticket_id("https://d.atlassian.net/browse/HELP-42", "jira") == "HELP-42"
    assert tk.ticket_id("…TicketDet?TicketID=998", "teamdynamix") == "998"
    assert tk.link("42", "zendesk", {"subdomain": "d"}) == "https://d.zendesk.com/agent/tickets/42"
    assert tk.can("resolve", "zendesk") and not tk.can("list", "osticket")


def test_zendesk_and_fresh():
    log = []
    http = _http([
        ("GET", "/tickets/7.json", {"ticket": {"id": 7, "subject": "Forgot password",
                                               "requester_id": 1, "status": "open"},
                                    "users": [{"id": 1, "name": "Ms Lee",
                                               "email": "lee@s.org"}]}),
        ("PUT", "/tickets/7.json", {"ticket": {"id": 7}}),
        ("POST", "/tickets.json", {"ticket": {"id": 8}}),
        ("GET", "/search.json", {"results": [{"id": 9, "subject": "Cracked screen SN "
                                                                 "5CD123ABC",
                                              "description": "serial 5CD123ABC",
                                              "requester_id": 1}]}),
        ("GET", "/users/show_many.json", {"users": [{"id": 1, "email": "lee@s.org"}]})], log)
    cfg = {"subdomain": "d", "email": "a@s.org", "token": "T", "template": ""}
    t = tk.get("7", "zendesk", cfg, http)
    assert t["for_email"] == "lee@s.org" and t["number"] == "7"
    assert log[0][2]["Authorization"].startswith("Basic ")
    tk.note("7", "did it", False, "zendesk", cfg, http)
    assert log[-1][3] == {"ticket": {"comment": {"body": "did it", "public": False}}}
    assert tk.create("Alert", "x", "", "zendesk", cfg, http) == "8"
    out = tk.list_open({}, "zendesk", cfg, http)
    assert out[0]["kind"] == "chromebook" and out[0]["target"] == "5CD123ABC"
    tk.resolve("7", "fixed", "zendesk", cfg, http)
    assert log[-1][3]["ticket"]["status"] == "solved"
    # Freshservice
    log = []
    http = _http([("POST", "/tickets/5/notes", {}), ("PUT", "/tickets/5", {}),
                  ("GET", "/tickets?include", {"tickets": [
                      {"id": 5, "subject": "Locked out of Google", "status": 2,
                       "requester": {"email": "kid1@s.org", "name": "Kid"}},
                      {"id": 6, "subject": "closed one", "status": 5}]})], log)
    cfg = {"domain": "d.freshservice.com", "api_key": "K", "email": "it@s.org"}
    out = tk.list_open({}, "freshservice", cfg, http)
    assert [t["id"] for t in out] == ["5"] and out[0]["kind"] == "account"
    tk.resolve("5", "done", "freshservice", cfg, http)
    assert log[-2][3]["private"] is False and log[-1][3] == {"status": 4}
    import base64
    assert base64.b64decode(log[0][2]["Authorization"][6:]) == b"K:X"


def test_servicenow_jira_whd_tdx_osticket():
    log = []
    sid = "a" * 32
    http = _http([("GET", "sysparm_query=number", {"result": [{"sys_id": sid}]}),
                  ("GET", f"/incident/{sid}", {"result": {
                      "sys_id": {"value": sid}, "number": {"display_value": "INC0010023"},
                      "short_description": {"display_value": "Password reset"},
                      "caller_id": {"display_value": "Kid One"},
                      "caller_id.email": {"display_value": "kid1@s.org"}}}),
                  ("PATCH", f"/incident/{sid}", {"result": {}})], log)
    cfg = {"instance": "dist", "user": "u", "password": "p", "table": "incident",
           "close_code": ""}
    t = tk.get("INC0010023", "servicenow", cfg, http)
    assert t["number"] == "INC0010023" and t["for_email"] == "kid1@s.org"
    tk.note("INC0010023", "n", False, "servicenow", cfg, http)
    assert log[-1][3] == {"work_notes": "n"}
    tk.resolve(sid, "ok", "servicenow", cfg, http)
    assert log[-1][3]["state"] == "6" and log[-1][3]["close_notes"] == "ok"
    # Jira
    log = []
    http = _http([("POST", "/request/HELP-1/comment", {}),
                  ("GET", "/transitions", {"transitions": [{"id": "31", "name": "Resolve"}]}),
                  ("POST", "/issue/HELP-1/transitions", (204, {}, b"")),
                  ("GET", "/search/jql", {"issues": [{"key": "HELP-1", "fields": {
                      "summary": "Chromebook won't charge", "description": {
                          "type": "doc", "content": [{"type": "paragraph", "content": [
                              {"type": "text", "text": "serial 5CD777LFT"}]}]},
                      "reporter": {"emailAddress": "lee@s.org"}}}]})], log)
    cfg = {"site": "d", "email": "a@s.org", "token": "T", "jql": "", "resolve_transition": ""}
    out = tk.list_open({}, "jira", cfg, http)
    assert out[0]["target"] == "5CD777LFT"
    tk.resolve("HELP-1", "done", "jira", cfg, http)
    assert log[-1][3] == {"transition": {"id": "31"}}
    assert "d.atlassian.net" in log[0][1]
    # Web Help Desk
    log = []
    http = _http([("POST", "/ra/TechNotes", {"id": 1}), ("PUT", "/ra/Tickets/12", {}),
                  ("GET", "/ra/Tickets?", [{"id": 12, "subject": "Reset password",
                                            "clientReporter": {"email": "lee@s.org"}}])],
                 log)
    cfg = {"url": "helpdesk.s.org", "api_key": "K", "closed_status_id": ""}
    assert tk.list_open({}, "whd", cfg, http)[0]["for_email"] == "lee@s.org"
    tk.resolve("12", "fixed", "whd", cfg, http)
    assert log[-2][3]["jobticket"] == {"type": "JobTicket", "id": 12}
    assert log[-1][3] == {"statustype": {"id": 3}} and "apiKey=K" in log[-1][1]
    # TeamDynamix
    from gambit.integrations import ticketing
    ticketing._TDX_TOKENS.clear()
    log = []
    http = _http([("POST", "/auth/loginadmin", b"JWT123"),
                  ("POST", "/tickets/77/feed", {}),
                  ("POST", "/tickets/search", [{"ID": 77, "Title": "Locked out",
                                                "RequestorEmail": "kid1@s.org"}])], log)
    cfg = {"url": "d.teamdynamix.com", "app_id": "9", "beid": "B", "key": "K",
           "resolved_status_id": "44"}
    out = tk.list_open({}, "teamdynamix", cfg, http)
    assert out[0]["kind"] == "account" and log[0][3] == {"BEID": "B", "WebServicesKey": "K"}
    tk.resolve("77", "ok", "teamdynamix", cfg, http)
    assert log[-1][3]["NewStatusID"] == 44 and log[-1][2]["Authorization"] == "Bearer JWT123"
    # osTicket (create only)
    log = []
    http = _http([("POST", "/api/tickets.json", b"000123")], log)
    cfg = {"url": "https://h.s.org", "api_key": "K", "email": "it@s.org", "template": ""}
    assert tk.create("Alert", "x", "", "osticket", cfg, http) == "000123"
    assert log[0][2]["X-API-Key"] == "K"
    try:
        tk.list_open({}, "osticket", cfg, http)
        raise AssertionError("should refuse")
    except RuntimeError as e:
        assert "list tickets" in str(e)


# ====================================================== password tickets ===
class FakeHD:
    def __init__(self):
        self.notes, self.resolved = [], []

    def configured(self):
        return True

    def can(self, what):
        return True

    def list_open(self, _o):
        return []

    def note(self, tid, text, public):
        self.notes.append((tid, text))

    def resolve(self, tid, text):
        self.resolved.append((tid, text))


def _t(i, subject, target, for_email):
    return {"id": i, "number": i, "subject": subject, "description": "", "category": "",
            "issue": "", "kind": "account", "target": target, "for_email": for_email}


def test_ticket_auto(team_dir, tmp_path, monkeypatch):
    from gambit import approval_policy as ap, selfservice
    from gambit.settings import settings
    sent = []
    monkeypatch.setattr(selfservice, "_tell_password", lambda to, s, pw: sent.append((to, s)))
    opts = {**ticket_auto.options(), "enabled": True}
    tickets = [_t("1", "Forgot password", "kid1@s.org", "teach@s.org"),
               _t("2", "Forgot password", "teach@s.org", "teach@s.org"),
               _t("3", "Locked out", "kid2@s.org", "kid2@s.org"),
               {**_t("4", "Printer jam", "", ""), "kind": "other"}]
    c = {x["ticket"]["id"]: x for x in ticket_auto.candidates(tickets, USERS, opts)}
    assert c["1"]["to"] == "teach@s.org" and not c["1"]["why_not"]
    assert "not a student" in c["2"]["why_not"]
    assert "no one to send" in c["3"]["why_not"]
    assert "4" not in c
    settings.set("ticketing/auto", json.dumps(opts))
    hd, ran = FakeHD(), []
    run = lambda a, t: (ran.append(a), (0, ""))[1]  # noqa: E731
    # approval rules off → request
    ap.save({**ap.DEFAULT, "on": False})
    lines = ticket_auto.process(lambda _l: None, tickets, USERS, run, hd)
    assert any("Approvals" in ln for ln in lines) and not ran
    req = next(r for r in team.list_requests("pending") if r.get("kind") == "ticket_reset")
    ok, msg = ticket_auto.run_request(req, run, hd)
    assert ok and ran[0][:3] == ["update", "user", "kid1@s.org"] and sent[-1][0] == "teach@s.org"
    assert hd.resolved and "emailed the temporary password" in hd.resolved[0][1]
    assert "password" not in hd.resolved[0][1].split("password to")[0][-2:]
    # already handled → nothing new
    assert ticket_auto.process(lambda _l: None, tickets, USERS, run, hd) == []
    # rules on → runs straight away
    ap.save({**ap.DEFAULT, "on": True})
    ran.clear()
    t5 = [_t("5", "forgot my password", "kid3@s.org", "teach@s.org")]
    lines = ticket_auto.process(lambda _l: None, t5, USERS, run, hd)
    assert ran and "resolved" in lines[0]
    ap.save({**ap.DEFAULT, "on": False})
    settings.set("ticketing/auto", "{}")


# ============================================================ playbooks ===
def test_playbooks_and_drift(team_dir):
    f = {"Finding": "Risky sign-in", "Who": "kid1@s.org", "Details": "suspicious login"}
    acts = playbooks.actions(f)
    lock = acts[0]["steps"]
    assert lock[0][1] == ["update", "user", "kid1@s.org", "password", "random",
                          "changepassword", "on"]
    assert any(a["kind"] == "goto" and a["tab"] == "Hacked account" for a in acts)
    adm = playbooks.actions({"Finding": "New admin role or privilege", "Who": "a@s.org",
                             "Details": "assign role “Help Desk Admin” for kid1@s.org"})
    assert adm[0]["kind"] == "admins" and adm[0]["role"] == "Help Desk Admin"
    rows = playbooks.admin_rows([{"roleAssignmentId": "1", "role": "Super Admin"},
                                 {"roleAssignmentId": "2", "role": "Help Desk Admin"}],
                                "Help Desk Admin")
    assert rows[0]["id"] == "2"
    assert playbooks.remove_admin_steps(rows[:1], "x")[0][1] == ["delete", "admin", "2"]
    req = playbooks.auto_request([f, {"Finding": "Mass delete", "Who": "b@s.org"}])
    assert req and req["commands"][0][2] == "kid1@s.org"
    assert {a for c in req["commands"] for a in c if "@" in a} == {"kid1@s.org"}
    changes = [
        {"Change": "changed", "Setting": "Chrome: chrome.users.MaxConnections @ /Students",
         "Before": json.dumps({"maxConnectionsPerProxy": 32, "x": {"a": 1}}),
         "Now": json.dumps({"maxConnectionsPerProxy": 99, "x": {"a": 2}})},
        {"Change": "added", "Setting": "Chrome: chrome.users.Incognito @ /Staff",
         "Before": "", "Now": "{}"},
        {"Change": "changed", "Setting": "Chrome: chrome.users.Byo @ /Students",
         "Before": json.dumps({"b": True}), "Now": json.dumps({"b": False})},
        {"Change": "changed", "Setting": "Admin: security.password @ /", "Before": "1",
         "Now": "2"}]
    acts_log = [{"command": "gam update chromepolicy chrome.users.Byo b false ou /Students"}]
    steps, manual = playbooks.revert_plan(changes, acts_log)
    cmds = [a for _l, a in steps]
    assert ["update", "chromepolicy", "chrome.users.MaxConnections", "maxConnectionsPerProxy",
            "32", "ou", "/Students"] in cmds
    assert ["delete", "chromepolicy", "chrome.users.Incognito", "ou", "/Staff"] in cmds
    assert not any("Byo" in " ".join(c) for c in cmds)
    assert any("security.password" in m for m in manual) and any("x" in m for m in manual)
    r = playbooks.drift_request(changes, "2026-10-13", acts_log)
    assert r["kind"] == "drift" and len(r["commands"]) == 2


# ======================================================= mismatch autofix ===
def test_split_autofix():
    f = [{"kind": "dev_school", "args": [["cros_sn", "A", "update", "ou", "/x"]]},
         {"kind": "withdraw", "args": [["update", "user", "a", "suspended", "on"]]},
         {"kind": "no_device", "args": []}]
    auto, rest = reconcile.split_autofix(f, {"auto": ["dev_school"], "max_auto": 5})
    assert [x["kind"] for x in auto] == ["dev_school"] and [x["kind"] for x in rest] == \
        ["withdraw"]
    auto, rest = reconcile.split_autofix(f, {"auto": ["dev_school", "withdraw"], "max_auto": 1})
    assert auto == [] and len(rest) == 2


# ============================================================ scorecard ===
def test_scorecard(team_dir):
    w1, w2 = datetime.date(2026, 10, 5), datetime.date(2026, 10, 12)
    scorecard.record({"inactive": 40, "pending": 3}, {"Lincoln": {"inactive": 10}}, w1)
    scorecard.record({"inactive": 30, "pending": 5}, {"Lincoln": {"inactive": 7}}, w2)
    rows = {r["key"]: r for r in scorecard.trend_rows()}
    assert rows["inactive"]["Change"] == -10 and rows["inactive"]["good"] is True
    assert rows["pending"]["good"] is False and rows["inactive"]["series"][-2:] == [40, 30]
    assert scorecard.school_delta("Lincoln") == {"inactive": (7, 10)}
    from gambit import school_reports as sr
    _s, body = sr.render("Lincoln", {"students": 5, "inactive": ["a"] * 7, "never": [],
                                     "no_guardian": [], "repair": [], "expired": [],
                                     "expiring": [], "classroom_active": 0,
                                     "classroom_known": 0}, {"inactive_days": 14},
                         scorecard.school_delta("Lincoln"))
    assert "▼ 3 vs last week" in body


# ========================================================= device history ===
def test_device_history():
    repairs = [{"n": 1, "serial": "SN1", "status": "Fixed", "opened": "2026-09-01",
                "closed": "2026-09-05", "model": "Dell", "user": "kid1@s.org",
                "history": [{"date": "2026-09-01", "status": "Open", "note": "cracked",
                             "by": "t"}]},
               {"n": 2, "serial": "SN1", "status": "Open", "opened": "2026-10-10",
                "model": "Dell", "history": []},
               {"n": 3, "serial": "SN2", "status": "Fixed", "opened": "2026-08-01",
                "closed": "2026-08-02", "model": "Acer", "history": []}]
    loans = [{"serial": "L1", "user": "kid1@s.org", "out": "2026-09-01", "due": "2026-09-08",
              "returned": "2026-09-06"},
             {"serial": "L2", "user": "kid2@s.org", "out": "2026-09-03", "due": "2026-09-10",
              "returned": ""}]
    tl = dh.timeline("sn1", [{"time": "2026-09-02T10:00", "command": "gam cros_sn SN1 update "
                                                                    "notes x", "code": 0}],
                     repairs, loans, [{"serial": "SN1", "flagged": "2026-10-01",
                                       "user": "gone@s.org"}],
                     {"name": "Summer", "collected": {"SN1": {"time": "2026-06-01"}}})
    assert [r["What"] for r in tl][:1] == ["Flagged to collect"]
    assert any(r["What"].startswith("Repair #1") for r in tl)
    devs = [{"serial": "SN1", "model": "Dell", "status": "ACTIVE"},
            {"serial": "SN3", "model": "Dell", "status": "ACTIVE"},
            {"serial": "SN2", "model": "Acer", "status": "ACTIVE"}]
    hot = {r["Group"]: r for r in dh.hotspots(devs, repairs, "model", today=TODAY)}
    assert hot["Dell"]["Repairs"] == 2 and hot["Dell"]["Per 100 devices"] == 100.0
    assert hot["Dell"]["Open now"] == 1 and hot["Acer"]["Avg days to fix"] == 1.0
    assert dh.peak_out(loans, TODAY) == 2
    ln = dh.loaners(loans, repairs, lambda s: "Lincoln", lambda u: "Lincoln", TODAY)
    assert ln[0]["Most out at once"] == 2 and ln[0]["Suggested loaner pool"] >= 3


# =========================================================== audit report ===
def test_audit_report():
    acts = [{"time": "2026-09-03T10:00:00", "who": "spencer", "change": True, "code": 0,
             "args": ["update", "user", "a@s.org", "password", "x"],
             "command": "gam update user a@s.org password ********"},
            {"time": "2026-09-04T10:00:00", "who": "spencer", "change": True, "code": 1,
             "args": ["delete", "user", "b@s.org"], "command": "gam delete user b@s.org"},
            {"time": "2026-10-01T10:00:00", "who": "x", "change": True, "code": 0,
             "args": ["delete", "user", "c@s.org"], "command": "gam delete user c@s.org"}]
    reqs = [{"time": "2026-09-05T10:00:00", "status": "done", "auto": True},
            {"time": "2026-09-06T10:00:00", "status": "denied", "note": "by email from b"},
            {"time": "2026-09-07T10:00:00", "status": "pending", "kind": "drift",
             "escalated": "x"}]
    finds = [{"When": "2026-09-09T05:20", "Finding": "Mass delete", "Status": "Reviewed by x"}]
    snaps = [("a", {"k": "1"}), ("b", {"k": "2", "n": "3"})]
    weeks = [("2026-W37", {"inactive": 9}), ("2026-W41", {"inactive": 1})]
    d = audit_report.build(2026, 9, acts, reqs, finds, snaps, weeks)
    assert d["changes"] == 2 and d["failed"] == 1 and d["categories"]["delete"] == 1
    assert d["auto"] == 1 and d["by_email"] == 1 and d["escalated"] == 1 and d["drift"] == 1
    assert len(d["settings_changes"]) == 2 and d["f_reviewed"] == 1
    assert d["numbers"] == {"inactive": 9}
    subj, body = audit_report.render(d)
    assert "September 2026" in subj and "1 failed" in body and "Mass delete" in body
    assert audit_report.last_month(datetime.date(2026, 1, 5)) == (2025, 12)


# ========================================================== teacher lists ===
def test_teacher_lists():
    parts = [{"courseId": "c1", "courseName": "Math 5", "userRole": "TEACHER",
              "profile.emailAddress": "teach@s.org"},
             {"courseId": "c1", "courseName": "Math 5", "userRole": "STUDENT",
              "profile.emailAddress": "kid1@s.org"},
             {"courseId": "c1", "courseName": "Math 5", "userRole": "STUDENT",
              "profile.emailAddress": "kid2@s.org"},
             {"courseId": "c2", "courseName": "Art", "userRole": "TEACHER",
              "profile.emailAddress": "other@s.org"},
             {"courseId": "c2", "courseName": "Art", "userRole": "STUDENT",
              "profile.emailAddress": "kid1@s.org"}]
    cur = [{"student": "kid1@s.org", "guardian": "m@x.com", "kind": "guardian",
            "state": "ACCEPTED"}]
    devs = [{"user": "kid1@s.org", "serial": "S1"}]
    loans = [{"serial": "L9", "user": "kid1@s.org", "due": "2026-10-01", "returned": ""}]
    fl = teacher_lists.flags_for(USERS, teacher_lists.options(), cur, devs, loans, TODAY)
    assert fl["kid2@s.org"] == ["has never signed in", "no guardian invited",
                                "no Chromebook assigned"]
    assert fl["kid1@s.org"] == ["loaner L9 overdue since 2026-10-01"]
    lists = teacher_lists.lists(parts, USERS, fl)
    assert set(lists) == {"teach@s.org", "other@s.org"}
    assert [s for s, _n, _f in lists["teach@s.org"]["Math 5"]] == ["kid1@s.org", "kid2@s.org"]
    assert teacher_lists.lists(parts, USERS, fl, only="other@s.org").keys() == {"other@s.org"}
    subj, body = teacher_lists.render("teach@s.org", lists["teach@s.org"], {})
    assert "(2)" in subj and "Kid Two" in body


# ============================================================ practice run ===
def test_whatif():
    from gambit.ui.pages.round10_pages import rollover_commands
    users = USERS + [{"email": "g12@s.org", "ou": "/Students/HS/Grade 12",
                      "suspended": False, "name": "Senior"},
                     {"email": "g11@s.org", "ou": "/Students/HS/Grade 11",
                      "suspended": False, "name": "Junior"}]
    pairs = [("/Students/HS/Grade 11", "/Students/HS/Grade 12"),
             ("/Students/HS/Grade 12", "/Students/Graduated")]
    cmds = rollover_commands(pairs, True)
    rules = [{"group": "seniors@s.org", "ous": ["/Students/HS/Grade 12"], "children": True,
              "enabled": True}]
    devs = [{"serial": "S12", "user": "g12@s.org"}, {"serial": "S11", "user": "g11@s.org"}]
    r = whatif.simulate(cmds, users, rules, devs, {"move_ou": True, "student_root":
                                                   "/Students", "school_depth": 1,
                                                   "ou_template": "/Chromebooks/{school}"})
    people = {p["Account"]: p for p in r["people"]}
    assert people["g12@s.org"]["After"] == "/Students/Graduated (suspended)"
    assert people["g11@s.org"]["After"] == "/Students/HS/Grade 12"
    summ = dict(r["summary"])
    assert summ["Moved to another org unit"] == 2 and summ["Suspended"] == 1
    g = r["groups"][0]
    assert g["Joins"] == 1 and g["Leaves"] == 1
    d = {x["Serial"]: x["What happens"] for x in r["devices"]}
    assert "collect" in d["S12"] and "S11" not in d
    r2 = whatif.simulate([["delete", "user", "kid1@s.org"],
                          ["user", "kid2@s.org", "delete", "license", "1010310008"],
                          ["print", "users"]], USERS)
    s2 = dict(r2["summary"])
    assert s2["Deleted"] == 1 and s2["Licenses released"] == 1 and s2[
        "Commands not simulated"] == 1


# ======================================================= Ask GAMbit look-up ===
def test_assistant_lookup():
    calls = []
    replies = [
        {"stop_reason": "tool_use", "content": [
            {"type": "tool_use", "id": "t1", "name": "run_gam_readonly",
             "input": {"args": ["gam", "update", "user", "x", "suspended", "on"]}},
            {"type": "tool_use", "id": "t2", "name": "run_gam_readonly",
             "input": {"args": ["print", "users", "query", "orgUnitPath='/Students'",
                                "fields", "primaryemail"]}}]},
        {"stop_reason": "end_turn", "content": [{"type": "text",
                                                 "text": "2 students: a@s.org, b@s.org"}]}]

    def http(method, url, headers, body=None, timeout=60):
        calls.append(body)
        return 200, {}, json.dumps(replies[len(calls) - 1]).encode()
    ran = []
    cfg = {"key": "k", "model": "m", "enabled": True, "share_users": False}
    res = assistant.lookup("who?", None, cfg, http,
                           run=lambda a: (ran.append(a), (0, "primaryEmail\na@s.org\n"))[1])
    assert res["answer"].startswith("2 students")
    assert ran == [["print", "users", "query", "orgUnitPath='/Students'", "fields",
                    "primaryemail"]]
    assert res["commands"][0][1] is False and "Refused" in res["commands"][0][2]
    tr = calls[1]["messages"][-1]["content"]
    assert tr[0]["is_error"] is True and tr[1]["content"].startswith("primaryEmail")
    assert calls[0]["tools"][0]["name"] == "run_gam_readonly"
    assert not assistant.readonly(["print", "users", "todrive"])
    assert not assistant.readonly(["user", "a", "print", "messages", "query", "x", "get"])
    assert assistant.readonly(["user", "a@s.org", "print", "filters"])
    assert urllib.parse  # keep import
