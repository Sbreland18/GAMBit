"""Round 41 – GAM key protection, whole-group restore, notice before suspension."""

import datetime
import os

import pytest

from gambit.settings import settings


@pytest.fixture(autouse=True)
def clean():
    for k in ("setup/seen", "tour/seen", "whatsnew/off"):
        settings.set(k, True)
    settings.check_updates_on_start = False
    settings.set("safety/dry_run", False)
    settings.set("gamkeys/last_check", "")
    yield
    settings.set("safety/dry_run", False)


@pytest.fixture
def alerts_sent(monkeypatch):
    sent = []
    from gambit import alerts
    monkeypatch.setattr(alerts, "notify", lambda text, title="", email=True:
                        sent.append((title, text)))
    return sent


# ========================================================== 1. GAM's keys ===
ME = "S-1-5-21-1-2-3-1001"


@pytest.fixture
def gam_layout(tmp_path, monkeypatch):
    from gambit import gam_keys, gam_setup
    prog, cfg = tmp_path / "GAM7", tmp_path / "GAMConfig"
    prog.mkdir()
    cfg.mkdir()
    (prog / "gam.exe").write_text("x")
    for n in ("oauth2.txt", "oauth2service.json", "client_secrets.json"):
        (cfg / n).write_text("{}")
    monkeypatch.setattr(type(settings), "gam_dir", property(lambda self: str(prog)))
    monkeypatch.setattr(gam_setup, "effective_cfg_dir", lambda: str(cfg))
    monkeypatch.setattr(gam_setup, "project_file", lambda n: str(cfg / n))
    return gam_keys, str(prog), str(cfg)


def _acl_output(targets, open_keys=True, open_prog=True):
    lines = [f"ME|{ME}"]
    for t in targets:
        lines += [f"ACE|{t}|S-1-5-32-544|BUILTIN\\Administrators|2032127|Allow|0",
                  f"ACE|{t}|S-1-5-18|NT AUTHORITY\\SYSTEM|2032127|Allow|0",
                  f"ACE|{t}|{ME}|PC\\tech|2032127|Allow|0",
                  f"ACE|{t}|S-1-5-80-956008885-1|NT SERVICE\\TrustedInstaller|2032127|Allow|0"]
        is_key = "GAMConfig" in t
        if is_key and open_keys:
            lines.append(f"ACE|{t}|S-1-5-32-545|BUILTIN\\Users|1179817|Allow|0")   # RX
        if not is_key and open_prog:
            lines.append(f"ACE|{t}|S-1-5-11|NT AUTHORITY\\Authenticated Users|1245631|Allow|0")
        if not is_key:
            lines.append(f"ACE|{t}|S-1-5-32-545|BUILTIN\\Users|1179817|Allow|0")   # may run
    return "\n".join(lines)


def test_open_keys_and_changeable_gam_are_found(gam_layout):
    gk, prog, cfg = gam_layout
    res = gk.check(run=lambda t: _acl_output(t))
    bad = [f for f in res if f.level == "bad"]
    assert any("Users can open oauth2service.json" in f.text for f in bad)
    assert any("Authenticated Users can change gam.exe" in f.text for f in bad)
    assert not any("TrustedInstaller" in f.text or "Administrators" in f.text for f in bad)


def test_locked_down_is_ok_and_users_may_still_run_gam(gam_layout):
    gk, prog, cfg = gam_layout
    res = gk.check(run=lambda t: _acl_output(t, open_keys=False, open_prog=False))
    assert [f.level for f in res] == ["ok"]


def test_parse_handles_inherit_only_and_deny(gam_layout):
    gk, _p, _c = gam_layout
    me, acl, errs = gk.parse_acl_output(
        f"ME|{ME}\nACE|C:\\x|S-1-1-0|Everyone|1179817|Deny|0\n"
        "ACE|C:\\x|S-1-5-11|Auth|-1610612736|Allow|2\nERR|C:\\y")
    aces = acl["C:\\x"]
    assert me == ME and errs == ["C:\\y"]
    assert not aces[0].reads()                          # deny lines never count as access
    assert aces[1].reads() and aces[1].inherit_only    # GENERIC_READ|EXECUTE on new files
    assert gk._who(aces, me, "read") == ["Authenticated Users"]


def test_synced_config_folder_is_flagged(tmp_path, monkeypatch, gam_layout):
    gk, prog, cfg = gam_layout
    from gambit import gam_setup
    od = tmp_path / "OneDrive - District" / "GAMConfig"
    od.mkdir(parents=True)
    (od / "oauth2.txt").write_text("x")
    monkeypatch.setattr(gam_setup, "effective_cfg_dir", lambda: str(od))
    res = gk.check(run=lambda t: _acl_output(t, open_keys=False, open_prog=False))
    assert any(f.level == "bad" and "synced" in f.text for f in res)


def test_lock_script_uses_sids_and_quotes_paths(gam_layout):
    gk, _p, _c = gam_layout
    s = gk.lock_script(ME, r"C:\GAM7", r"C:\Ana's GAM", [r"C:\Ana's GAM\oauth2.txt"])
    assert f"*{ME}:(OI)(CI)F" in s and "*S-1-5-32-545:(OI)(CI)RX" in s
    assert "'C:\\Ana''s GAM'" in s and "/inheritance:r" in s
    same = gk.lock_script(ME, r"C:\GAM7", r"C:\GAM7", [])
    assert "S-1-5-32-545" not in same                  # keys there: nobody else, not even RX
    with pytest.raises(ValueError):
        gk.lock_script("x; Remove-Item C:\\", r"C:\GAM7", "", [])


def test_posix_check_and_lock_down(gam_layout, monkeypatch):
    gk, prog, cfg = gam_layout
    if os.name == "nt":
        pytest.skip("POSIX permissions")
    monkeypatch.setattr(gk, "IS_WINDOWS", False)
    os.chmod(os.path.join(cfg, "oauth2service.json"), 0o644)
    assert any(f.level == "bad" for f in gk.check())
    res = gk.lock_down()
    assert all(f.level == "ok" for f in res)
    assert oct(os.stat(os.path.join(cfg, "oauth2service.json")).st_mode & 0o777) == "0o600"


def test_daily_alert_once(gam_layout, monkeypatch, alerts_sent):
    gk, _p, _c = gam_layout
    real = gk.check
    monkeypatch.setattr(gk, "check", lambda: real(run=lambda t: _acl_output(t)))
    gk.run(lambda *_: None)
    gk.run(lambda *_: None)
    assert len(alerts_sent) == 1 and "aren't protected" in alerts_sent[0][1]
    assert gk.attention()


# ====================================================== 2. whole groups ===
@pytest.fixture
def tm_dir(tmp_path, monkeypatch):
    from gambit import timemachine as tm
    d = tmp_path / "tm"
    d.mkdir()
    monkeypatch.setattr(tm, "folder", lambda: str(d))
    return tm


def _members(rows):
    return [{"group": g, "email": e, "role": r, "type": t} for g, e, r, t in rows]


def test_group_snapshot_restore_includes_outside_and_nested(tm_dir):
    tm = tm_dir
    then_rows = _members([("staff@s.org", "a@s.org", "OWNER", "USER"),
                          ("staff@s.org", "b@s.org", "MEMBER", "USER"),
                          ("staff@s.org", "sub@s.org", "MEMBER", "GROUP"),
                          ("staff@s.org", "vendor@x.com", "MEMBER", "USER")])
    day = datetime.date(2026, 10, 1)
    tm.save(tm.build([{"primaryEmail": "a@s.org"}, {"primaryEmail": "b@s.org"}], then_rows),
            day)
    tm.save_groups(tm.build_groups(then_rows), day)
    then, complete = tm.group_then("2026-10-01", "STAFF@s.org")
    assert complete and set(then) == {"a@s.org", "b@s.org", "sub@s.org", "vendor@x.com"}
    now = tm.build_groups(_members([("staff@s.org", "a@s.org", "MEMBER", "USER"),
                                    ("staff@s.org", "new@s.org", "MEMBER", "USER")]))[
        "staff@s.org"]
    rows = {r["Member"]: r["Change"] for r in tm.group_diff(then, now)}
    assert rows == {"a@s.org": "role changed", "b@s.org": "removed since",
                    "sub@s.org": "removed since", "vendor@x.com": "removed since",
                    "new@s.org": "added since"}
    steps = [a for _l, a in tm.group_restore_commands("staff@s.org", then, now)]
    assert ["update", "group", "staff@s.org", "add", "member", "user", "vendor@x.com"] in steps
    assert ["update", "group", "staff@s.org", "update", "owner", "user", "a@s.org"] in steps
    assert not any("remove" in s for s in steps)            # off unless asked
    steps = [a for _l, a in tm.group_restore_commands("staff@s.org", then, now,
                                                       remove_new=True, roles=False)]
    assert ["update", "group", "staff@s.org", "remove", "user", "new@s.org"] in steps
    assert not any(s[3] == "update" for s in steps)


def test_older_nights_fall_back_to_account_snapshot(tm_dir):
    tm = tm_dir
    rows = _members([("g@s.org", "a@s.org", "MANAGER", "USER")])
    tm.save(tm.build([{"primaryEmail": "a@s.org"}], rows), datetime.date(2026, 9, 1))
    then, complete = tm.group_then("2026-09-01", "g@s.org")
    assert not complete and then == {"a@s.org": {"role": "MANAGER", "type": "USER"}}
    assert tm.dates() == ["2026-09-01"]                    # the groups folder isn't a night


def test_group_now_and_nightly_run_saves_groups(tm_dir):
    tm = tm_dir

    def run_csv(a):
        if a[:2] == ["print", "users"]:
            return 0, [{"primaryEmail": "a@s.org"}], ""
        if a[:3] == ["print", "group-members", "group"]:
            return 0, [{"email": "a@s.org", "role": "OWNER", "type": "USER"}], ""
        return 0, _members([("g@s.org", "a@s.org", "OWNER", "USER"),
                            ("g@s.org", "x@y.com", "MEMBER", "USER")]), ""
    tm.run(lambda *_: None, run_csv)
    then, complete = tm.group_then(datetime.date.today().isoformat(), "g@s.org")
    assert complete and "x@y.com" in then
    assert tm.group_now("g@s.org", run_csv) == {"a@s.org": {"role": "OWNER", "type": "USER"}}


# ============================================== 3. notice before suspension ===
TODAY = datetime.date(2026, 11, 2)


def _users(login_a="2025-01-01T00:00:00Z"):
    return [{"email": "a@s.org", "name": "Ann", "ou": "/Staff", "suspended": False,
             "last_login": login_a},
            {"email": "b@s.org", "name": "Bo", "ou": "/Staff", "suspended": False,
             "last_login": "2025-01-01T00:00:00Z"}]


RULE = {"name": "Idle staff", "kind": "inactive", "ou": "/Staff", "days": 180,
        "warn_days": 14, "warn_manager": True, "warn_also": "hr@s.org",
        "warn_contact": "helpdesk@s.org"}


def test_split_warn_then_suspend_and_drop_on_sign_in():
    from gambit import suspend_notice as sn
    from gambit.tools import automation as am
    found = am.evaluate(RULE, _users())
    warn, due, dropped, st = sn.split(RULE, found, _users(), TODAY, {})
    assert {f["email"] for f in warn} == {"a@s.org", "b@s.org"} and due == []
    later = TODAY + datetime.timedelta(days=7)
    warn, due, dropped, st2 = sn.split(RULE, found, _users(), later, st)
    assert warn == [] and due == []                          # notice still running
    ended = TODAY + datetime.timedelta(days=14)
    users = _users(login_a="2026-11-10T09:00:00Z")           # Ann signed in meanwhile
    found2 = am.evaluate(RULE, users)
    warn, due, dropped, st3 = sn.split(RULE, found2, users, ended, st2)
    assert dropped == ["a@s.org"] and [f["email"] for f in due] == ["b@s.org"]
    assert "a@s.org" not in st3["Idle staff"]


def test_emails_person_manager_and_summary():
    from gambit import suspend_notice as sn
    sent = []

    def run_text(a):
        sent.append((a[a.index("to") + 1], a[a.index("subject") + 1],
                     a[a.index("message") + 1]))
        return 0, ""

    def run_csv(a):
        return 0, [{"primaryEmail": "a@s.org", "relations.0.type": "manager",
                    "relations.0.value": "boss@s.org"}], ""
    rule = {**RULE, "warn_message": "Hi {name} {email} {date} {contact} {name.__class__}"}
    n = sn.send(rule, [{"email": "a@s.org", "why": "last sign-in 300 days ago"}], _users(),
                TODAY, lambda *_: None, run_text, run_csv)
    assert n == 1
    to = [t for t, _s, _b in sent]
    assert to == ["a@s.org", "boss@s.org", "hr@s.org"]
    body = sent[0][2]
    assert "Hi Ann a@s.org November 16, 2026 helpdesk@s.org {name.__class__}" == body
    assert "November 16, 2026" in sent[0][1]


def test_cleanup_run_holds_back_until_notice_ends(team_dir, monkeypatch):
    from gambit import suspend_notice as sn, team
    from gambit.tools import automation as am
    sent = []
    monkeypatch.setattr(sn, "send", lambda *a, **k: sent.append(len(a[1])) or len(a[1]))
    am.save_rules([RULE])
    am.run_cleanup(lambda *_: None, users=_users())
    assert sent == [2] and not team.list_requests("pending")   # warned, not suspended
    st = sn.load_state()
    for e in st["Idle staff"]:
        st["Idle staff"][e]["warned"] = (datetime.date.today() -
                                         datetime.timedelta(days=15)).isoformat()
    sn.save_state(st)
    am.run_cleanup(lambda *_: None, users=_users())
    req = [r for r in team.list_requests("pending") if r.get("kind") == "cleanup"]
    assert req and len(req[0]["commands"]) == 2


def test_dry_run_sends_nothing_and_remembers_nothing(team_dir):
    from gambit import suspend_notice as sn
    from gambit.tools import automation as am
    settings.set("safety/dry_run", True)
    am.save_rules([RULE])
    calls = []
    sn.send(RULE, [{"email": "a@s.org", "why": "x"}], _users(), TODAY, lambda *_: None,
            lambda a: calls.append(a) or (0, ""), lambda a: (0, [], ""))
    assert calls == []
    am.run_cleanup(lambda *_: None, users=_users())
    assert sn.load_state() == {}


def test_rule_dialog_notice_fields(qapp):
    from gambit.directory import Directory
    from gambit.ui.pages.automation_tabs import RuleDialog
    d = RuleDialog(None, Directory(), dict(RULE))
    r = d.rule()
    assert r["warn_days"] == 14 and r["warn_also"] == "hr@s.org" and r["warn_message"] == ""
    d.kind.setCurrentIndex(d.kind.findData("delete_old"))
    assert "warn_days" not in d.rule()
