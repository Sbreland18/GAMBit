import datetime
import json

from gambit import approval_policy as ap, history, school_reports as sr, sis, team, yearend
from gambit.integrations import assistant, iiq
from gambit.tools import budget, reconcile, watchdog

TODAY = datetime.date(2026, 10, 14)
USERS = [
    {"email": "kid1@s.org", "name": "Kid One", "ou": "/Students/Lincoln/Grade 5",
     "suspended": False, "last_login": "2026-10-12T10:00:00Z", "sis_id": "1001"},
    {"email": "kid2@s.org", "name": "Kid Two", "ou": "/Students/Lincoln/Grade 5",
     "suspended": False, "last_login": "2026-08-01T10:00:00Z", "sis_id": "1002"},
    {"email": "gone@s.org", "name": "Gone Kid", "ou": "/Students/Withdrawn",
     "suspended": True, "last_login": "2026-05-01T10:00:00Z", "sis_id": "1003"},
    {"email": "hs@s.org", "name": "High Kid", "ou": "/Students/Hancock High/Grade 9",
     "suspended": False, "last_login": "", "sis_id": "1004"},
    {"email": "teacher@s.org", "name": "Teach", "ou": "/Staff", "suspended": False,
     "last_login": "2026-10-13T10:00:00Z"},
]
CROS = [
    {"serialNumber": "SN1", "annotatedUser": "kid1@s.org", "orgUnitPath": "/Chromebooks/Lincoln",
     "status": "ACTIVE", "annotatedAssetId": "A1"},
    {"serialNumber": "SN2", "annotatedUser": "gone@s.org", "orgUnitPath": "/Chromebooks/Lincoln",
     "status": "ACTIVE", "annotatedAssetId": "A2", "model": "Dell 3100"},
    {"serialNumber": "SN3", "annotatedUser": "kid1@s.org",
     "orgUnitPath": "/Chromebooks/Hancock High", "status": "ACTIVE"},
    {"serialNumber": "SN4", "annotatedUser": "nobody@s.org", "orgUnitPath": "/",
     "status": "ACTIVE"},
]


# ----------------------------------------------------------- mismatches ---
def test_mismatch_report():
    people = [sis.Person(sis_id="1001", first="Kid", last="One", email="kid1@s.org",
                         grade="5", school="Lincoln", active=True),
              sis.Person(sis_id="1002", first="Kid", last="Two", email="kid2@s.org",
                         grade="5", school="Lincoln", active=True),
              sis.Person(sis_id="1009", first="New", last="Kid", email="new@s.org",
                         grade="5", school="Lincoln", active=True)]
    rules = sis.Rules(domain="s.org", ou_template="/Students/{school}/Grade {grade}",
                      withdrawn_ou="/Students/Withdrawn", year_end=2027)
    f = reconcile.roster_findings(sis.plan(people, USERS[:4], rules))
    kinds = {x["kind"]: x for x in f}
    assert kinds["create"]["Who"] == "new@s.org" and not kinds["create"]["args"]
    assert kinds["withdraw"]["Who"] == "hs@s.org" and kinds["withdraw"]["args"]
    d = reconcile.device_findings(USERS, CROS, {"student_root": "/Students",
                                                "withdrawn_ou": "/Students/Withdrawn",
                                                "one_to_one": True,
                                                "ou_template": "/Chromebooks/{school}",
                                                "school_depth": 1})
    k = [(x["kind"], x["Who"]) for x in d]
    assert ("dev_withdrawn", "SN2") in k
    assert ("dev_unknown", "SN4") in k
    assert ("two_devices", "kid1@s.org") in k
    assert ("no_device", "kid2@s.org") in k and ("no_device", "hs@s.org") in k
    sch = next(x for x in d if x["kind"] == "dev_school")
    assert sch["Who"] == "SN3" and sch["args"] == [["cros_sn", "SN3", "update", "ou",
                                                    "/Chromebooks/Lincoln"]]
    assert reconcile.summary(d)[0][1] == "2"


def test_withdrawn_devices_flow(tmp_path, monkeypatch):
    from gambit import fleet
    monkeypatch.setattr(fleet, "data_dir", lambda: str(tmp_path))
    opts = {"student_root": "/Students", "withdrawn_ou": "/Students/Withdrawn", "note": True,
            "disable": True, "ticket": False, "return_ou": "/Chromebooks/Returned"}
    found = reconcile.find_withdrawn(USERS, CROS, opts)
    assert [x["serial"] for x in found] == ["SN2"] and found[0]["school"] == "Withdrawn"
    items = []
    new = reconcile.merge(items, found)
    assert len(new) == 1 and reconcile.merge(items, found) == []
    cmds = reconcile.flag_commands(new[0], opts)
    assert cmds[0][:4] == ["cros_sn", "SN2", "update", "notes"]
    assert cmds[1] == ["cros_sn", "SN2", "update", "action", "disable"]
    it, back, msg = reconcile.check_in(items, "a2", "tech@s.org", opts)
    assert it["status"] == "Collected" and "0 still" in msg
    assert ["cros_sn", "SN2", "update", "action", "reenable"] in back
    assert ["cros_sn", "SN2", "update", "ou", "/Chromebooks/Returned"] in back
    assert reconcile.check_in(items, "SN2", "x", opts)[0] is None
    # background run: flags, opens tickets, saves
    from gambit.settings import settings
    settings.set("collect/options", json.dumps({**opts, "ticket": True}))

    class FakeIIQ:
        made = []

        @staticmethod
        def configured():
            return True

        @staticmethod
        def can(_what):
            return True

        @staticmethod
        def create(subj, desc):
            FakeIIQ.made.append(subj)
            return "T-1"
    ran = []
    try:
        reconcile.save_items([])
        lines = reconcile.run_collect(log=lambda _l: None, run_csv=lambda a: (0, CROS, ""),
                                      run_text=lambda a, t: (ran.append(a), (0, ""))[1],
                                      users=USERS, hd=FakeIIQ)
        assert "1 new" in lines[0] and FakeIIQ.made and len(ran) == 2
        assert reconcile.load_items()[0]["ticket"] == "T-1"
    finally:
        settings.set("collect/options", "{}")


# ------------------------------------------------------------- year end ---
def test_yearend(team_dir):
    plan = yearend.load()
    plan["last_day"] = "2027-05-28"
    yearend.save(plan)
    rows = yearend.rows(plan, datetime.date(2027, 5, 26))
    assert len(rows) == len(yearend.STEPS)
    by = {r["key"]: r for r in rows}
    assert by["collect_plan"]["state"] == "Overdue"
    assert by["collect"]["state"] == "Due this week"
    yearend.mark(plan, "collect_plan", "Done", "me@s.org")
    assert yearend.progress(yearend.rows(plan))[0] == 1
    req = yearend.ask_signoff(plan, "signoff_grad", "seniors attached")
    r = {x["key"]: x for x in yearend.rows(yearend.load(), datetime.date(2027, 5, 26))}
    assert r["signoff_grad"]["state"] == "Waiting for sign-off"
    team.update_request(req, "done")
    r = {x["key"]: x for x in yearend.rows(yearend.load(), datetime.date(2027, 5, 26))}
    assert r["signoff_grad"]["status"] == "Done"
    lines = yearend.reminders(yearend.load(), datetime.date(2027, 5, 26))
    assert any("OVERDUE" in ln for ln in lines) and not any("signoff_grad" in ln for ln in lines)
    assert yearend.default_last_day(datetime.date(2026, 10, 1)).year == 2027


# ------------------------------------------------------- school reports ---
def test_school_reports():
    from gambit import fleet
    devs = fleet.devices([
        {"serialNumber": "SN1", "annotatedUser": "kid1@s.org", "status": "ACTIVE",
         "autoUpdateExpiration": "2025-06-01"},
        {"serialNumber": "SN9", "orgUnitPath": "/Chromebooks/Lincoln", "status": "ACTIVE",
         "autoUpdateExpiration": "2027-03-01"}])
    cur = [{"student": "kid1@s.org", "guardian": "mom@x.com", "kind": "guardian",
            "state": "ACCEPTED"}]
    usage = [{"email": "kid1@s.org", "classroom:last_interaction_time": "2026-10-10T00:00:00Z"},
             {"email": "kid2@s.org", "classroom:last_interaction_time": "2026-09-01T00:00:00Z"}]
    repairs = [{"n": 3, "serial": "SN1", "status": "Open", "problem": "cracked",
                "opened": "2026-10-01"}]
    st = sr.gather(USERS, {"root": "/Students", "inactive_days": 14,
                           "device_root": "/Chromebooks"}, cur, usage, devs, repairs, TODAY)
    lin = st["Lincoln"]
    assert lin["students"] == 2 and len(lin["inactive"]) == 1
    assert lin["no_guardian"] == ["kid2@s.org"]
    assert lin["classroom_active"] == 1 and lin["classroom_known"] == 2
    assert lin["expired"] == ["SN1"] and lin["expiring"] == ["SN9"]
    assert lin["repair"] and "cracked" in lin["repair"][0]
    assert st["Hancock High"]["never"] == ["hs@s.org"]
    h, rows = sr.table(st)
    assert rows[0][0] == "Hancock High" and h[5] == "Used Classroom this week"
    subj, body = sr.render("Lincoln", lin, {"inactive_days": 14})
    assert "Lincoln" in subj and "kid2@s.org" in body and "cracked" in body


# -------------------------------------------------------------- history ---
def test_history_search():
    now = datetime.datetime(2026, 10, 14, 9, 0)
    s, e = history.time_range("what did we change for jsmith last week?", now)
    assert s.date() == datetime.date(2026, 10, 5) and e.date() == datetime.date(2026, 10, 12)
    assert history.terms("what did we change for jsmith last week?") == ["jsmith"]
    assert history.terms("Why did last night's sync fail?") == []
    entries = [
        {"time": "2026-10-07T10:00:00", "who": "a", "command": "gam update user jsmith@s.org "
                                                               "suspended on", "code": 0},
        {"time": "2026-10-07T11:00:00", "who": "a", "command": "gam update user bob@s.org "
                                                               "suspended on", "code": 0},
        {"time": "2026-10-13T11:00:00", "who": "a", "command": "gam update user jsmith@s.org "
                                                               "ou /x", "code": 0}]
    r = history.find("what did we change for jsmith last week?", entries, {}, now)
    assert [x["time"] for x in r["activity"]] == ["2026-10-07T10:00:00"]
    log = {"sync:Students": {"all": [("2026-10-14 05:30:00", "Plan: create: 3"),
                                     ("2026-10-14 05:31:00", "FAILED: roster file missing")]},
           "digest": {"all": [("2026-10-14 05:00:00", "FAILED: x")]}}
    r = history.find("Why did last night's sync fail?", entries, log, now)
    assert r["tasks"] == [("sync:Students", "2026-10-14 05:31:00", "FAILED: roster file missing")]
    assert "roster file missing" in history.as_text(r)


# ----------------------------------------------------- assistant drafts ---
def _claude(reply: dict):
    sent = []

    def http(method, url, headers, body=None, timeout=60):
        sent.append(body)
        return 200, {}, json.dumps({"content": [{"type": "text",
                                                 "text": "Here:\n" + json.dumps(reply)}]}).encode()
    return http, sent


def test_assistant_drafts_and_history():
    cfg = {"key": "k", "model": "m", "enabled": True, "share_users": False}
    http, sent = _claude({"name": "New sub", "description": "d",
                          "fields": [{"key": "Email", "label": "Email"}],
                          "steps": [{"label": "Create", "command": "gam create user {email} "
                                                                    "password {password}"}]})
    wf = assistant.draft_workflow("new sub teacher", None, cfg, http)
    assert wf["fields"][0]["key"] == "email"
    assert wf["steps"][0]["command"] == "create user {email} password {password}"
    from gambit import custom_workflows as cw
    assert cw.problems(wf) == []
    http, _ = _claude({"name": "HS inactive", "kind": "inactive", "ou": "/Students/HS",
                       "days": "120", "max": 100})
    r = assistant.draft_rule("suspend hs kids", None, cfg, http)
    assert r["days"] == 120 and r["kind"] == "inactive" and r["enabled"]
    http, sent = _claude({"x": 1})
    assistant.explain_history("why?", "2026-10-14 FAILED x", cfg, http)
    assert "FAILED x" in sent[0]["messages"][0]["content"]
    assert "nothing to explain" in assistant.explain_history("q", "", cfg, http)


# ------------------------------------------------------------- watchdog ---
def test_watchdog_analyze():
    drive = [{"name": "download", "actor.email": "a@s.org"}] * 5 + \
        [{"name": "trash", "actor.email": "b@s.org"}] * 3 + \
        [{"name": "change_document_visibility", "actor.email": "c@s.org",
          "visibility": "public_on_the_web", "doc_title": "Grades"}] * 2 + \
        [{"name": "change_user_access", "actor.email": "c@s.org",
          "target_user": "friend@gmail.com"}] + \
        [{"name": "change_user_access", "actor.email": "d@s.org", "target_user": "x@s.org"}] * 9
    login = [{"name": "suspicious_login", "actor.email": "e@s.org", "ipAddress": "1.2.3.4"},
             {"name": "login_success", "actor.email": "f@s.org",
              "networkInfo.regionCode": "RU"},
             {"name": "login_success", "actor.email": "g@s.org",
              "networkInfo.regionCode": "US"}]
    admin = [{"name": "ASSIGN_ROLE", "actor.email": "admin@s.org", "ROLE_NAME": "Super Admin",
              "USER_EMAIL": "h@s.org"}]
    o = {**watchdog.options(), "downloads": 5, "deletes": 3, "shares": 3,
         "check_countries": True, "countries": "US"}
    f = watchdog.analyze({"drive": drive, "login": login, "admin": admin}, o, {"s.org"})
    got = {(x["Finding"], x["Who"]) for x in f}
    assert ("Mass download", "a@s.org") in got and ("Mass delete", "b@s.org") in got
    assert ("External sharing spike", "c@s.org") in got
    assert not any(w == "d@s.org" for _k, w in got)
    assert ("Risky sign-in", "e@s.org") in got
    assert ("Sign-in from an unexpected country", "f@s.org") in got
    assert not any(w == "g@s.org" for _k, w in got)
    adm = next(x for x in f if x["Finding"].startswith("New admin"))
    assert "Super Admin" in adm["Details"] and "h@s.org" in adm["Details"]
    q = watchdog.queries(o, "2026-10-13T00:00:00Z")
    assert q[1][1][-1].endswith(",login_success")
    o2 = {**o, "ignore": "a@s.org"}
    assert not any(x["Who"] == "a@s.org" for x in watchdog.analyze({"drive": drive}, o2,
                                                                   {"s.org"}))


# ------------------------------------------------------ approval policy ---
def test_approval_policy(team_dir):
    pol = {**ap.DEFAULT, "on": True}
    reset = ["update", "user", "kid1@s.org", "password", "x", "changepassword", "on"]
    assert ap.auto_rule(reset, USERS, pol).startswith("automatic approval")
    assert ap.auto_rule(["update", "user", "teacher@s.org", "password", "x"], USERS, pol) == ""
    assert ap.auto_rule(["ou", "/Students", "update", "user", "password", "x"], USERS, pol) == ""
    assert ap.auto_rule(["delete", "user", "kid1@s.org"], USERS, pol) == ""
    assert ap.auto_rule(reset, USERS, {**pol, "on": False}) == ""
    ap.save(pol)
    req = team.new_request([["delete", "user", "gone@s.org"]], "left", by="helper@s.org")
    assert ap.needs_two(req)
    ready, req = ap.record_approval(req, "boss1@s.org")
    assert not ready and ap.approval_note(req).startswith("1 of 2")
    ready, req = ap.record_approval(req, "boss1@s.org")
    assert not ready
    ready, req = ap.record_approval(req, "boss2@s.org")
    assert ready
    mine = team.new_request([["delete", "user", "x@s.org"]], "r", by="boss1@s.org")
    assert ap.record_approval(mine, "boss1@s.org")[0] is False
    small = team.new_request([["update", "group", "g@s.org", "add", "member", "a@s.org"]], "r")
    assert ap.record_approval(small, "boss1@s.org")[0] is True
    later = datetime.datetime.now() + datetime.timedelta(hours=30)
    assert len(ap.overdue(team.list_requests("pending"), 24, later)) >= 3
    sent = []
    import gambit.alerts as al
    orig = al.notify
    al.notify = lambda text, title="", email=True: sent.append(text) or []
    try:
        n = ap.escalate(log=lambda _l: None, now=later)
        assert n >= 3 and sent and ap.escalate(log=lambda _l: None, now=later) == 0
    finally:
        al.notify = orig
        ap.save({**ap.DEFAULT, "on": False})
    rec = ap.log_auto(reset, "automatic approval: Reset passwords")
    assert rec["status"] == "done" and rec["auto"]


# --------------------------------------------------------------- budget ---
def test_budget():
    rows = [{"primaryEmail": "a@s.org", "suspended": "True", "lastLoginTime": "2025-01-01",
             "orgUnitPath": "/Students", "Licenses": "1010310008 1010370001"},
            {"primaryEmail": "b@s.org", "suspended": "False", "lastLoginTime": "Never",
             "Licenses": "1010310008"},
            {"primaryEmail": "c@s.org", "suspended": "False", "lastLoginTime": "2026-10-01",
             "Licenses": "1010310008"},
            {"primaryEmail": "d@s.org", "suspended": "False", "lastLoginTime": "2026-01-01",
             "Licenses": ""}]
    summ, detail = budget.reclaimable(budget.license_holders(rows), 180,
                                      {"1010310008": 5}, TODAY)
    plus = next(r for r in summ if r["sku"] == "1010310008")
    assert plus["Assigned"] == 3 and plus["Could free"] == 2 and plus["Savings / year"] == 10
    assert plus["License"] == "Education Plus"
    assert {d["Account"] for d in detail} == {"a@s.org", "b@s.org"}
    assert ["user", "a@s.org", "delete", "license", "1010370001"] in [d["args"] for d in detail]
    from gambit import fleet
    devs = fleet.devices([
        {"serialNumber": "1", "annotatedUser": "kid1@s.org", "status": "ACTIVE",
         "autoUpdateExpiration": "2026-01-01"},
        {"serialNumber": "2", "orgUnitPath": "/Chromebooks/Hancock High", "status": "ACTIVE",
         "autoUpdateExpiration": "2027-08-01"},
        {"serialNumber": "3", "orgUnitPath": "/Chromebooks/Hancock High", "status": "ACTIVE",
         "autoUpdateExpiration": "2040-08-01"}])
    head, table, per_year = budget.device_plan(devs, {"device_cost": 300, "years": 3,
                                                      "device_root": "/Chromebooks"},
                                               budget.user_schools(USERS), TODAY)
    assert head[:3] == ["School", "Expired", "2026-27"] and head[4] == "2028-29"
    by = {r[0]: r for r in table}
    assert by["Lincoln"][1] == "1" and by["Hancock High"][3] == "1"
    assert by["All schools"][-1] == "$600" and per_year["Expired"] == 300


# ---------------------------------------------------------- ticket queue ---
def test_iiq_queue():
    tickets = [{"TicketId": "t1", "TicketNumber": 101, "Subject": "Can't log in to Google",
                "For": {"Name": "Kid One", "Email": "kid1@s.org"},
                "IssueCategory": {"Name": "Accounts"}},
               {"TicketId": "t2", "TicketNumber": 102, "Subject": "Cracked screen",
                "Assets": [{"SerialNumber": "sn99", "AssetTag": "A9"}],
                "For": {"Email": "kid2@s.org"}},
               {"TicketId": "t3", "TicketNumber": 103, "Subject": "Projector bulb"}]
    sent = []

    def http(method, url, headers, body=None, timeout=60):
        sent.append((method, url, body))
        return 200, {}, json.dumps({"Items": tickets}).encode()
    cfg = {"site": "https://x.incidentiq.com", "site_id": "S", "token": "T"}
    out = iiq.list_open(cfg, http, {"product_id": "P", "category_id": "C", "words": ""})
    m, url, body = sent[0]
    assert m == "POST" and "/api/v1.0/tickets?$s=100&$p=0" in url
    assert body["ProductId"] == "P" and {"Facet": "issuecategory", "Id": "C"} in body["Filters"]
    k = {t["number"]: (t["kind"], t["target"]) for t in out}
    assert k["101"] == ("account", "kid1@s.org")
    assert k["102"] == ("chromebook", "SN99")
    assert k["103"] == ("other", "")
    out = iiq.list_open(cfg, http, {"words": "screen"})
    assert [t["number"] for t in out] == ["102"]
