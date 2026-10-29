"""Round 36: fixes from the QA review. Each test reproduces a reported problem and checks
the fix (they fail on the code before the fix)."""

import json
import os
import time

import pytest
from PySide6.QtWidgets import QApplication

from gambit.settings import settings


@pytest.fixture(autouse=True)
def clean():
    for k in ("setup/seen", "tour/seen", "oumap/reminded", "whatsnew/off"):
        settings.set(k, True)
    settings.set("connection/auto_test", False)
    settings.check_updates_on_start = False
    settings.set("safety/dry_run", False)
    yield
    settings.set("safety/dry_run", False)
    from gambit import user_prefs
    settings.set(user_prefs.PRACTICE_KEY, False)


_KEEP = []          # runners live as long as the app does (like the real one)


def _runner():
    from gambit.gam_runner import GamRunner
    r = GamRunner()
    _KEEP.append(r)
    return r


def pump(sec=0.2):
    end = time.time() + sec
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.01)


# ------------------------------------------------------------ 1. practice ---
PRACTICE_USERS = {"test@x.org": {"email": "test@x.org", "ou": "/Test"},
                  "kid@x.org": {"email": "kid@x.org", "ou": "/Test/A"},
                  "boss@x.org": {"email": "boss@x.org", "ou": "/Staff"}}


@pytest.mark.parametrize("args", [
    ["update", "group", "allstaff@x.org", "sync", "member", "test@x.org"],
    ["update", "group", "allstaff@x.org", "add", "member", "test@x.org"],
    ["update", "ou", "/Test", "add", "users", "boss@x.org"],
    ["update", "ou", "/Test", "move", "ou", "/Staff"],
    ["user", "test@x.org", "transfer", "drive", "boss@x.org"],
    ["user", "test@x.org", "add", "delegate", "boss"],
    ["update", "user", "boss@x.org", "ou", "/Test"],
    ["user", "test@x.org", "forward", "on", "keep", "someone@outside.com"],
])
def test_practice_mode_never_reaches_beyond_the_test_account(args):
    from gambit import user_prefs as up
    settings.set("safety/test_ou", "/Test")
    settings.set("safety/test_user", "test@x.org")
    assert up.practice_allows(args, PRACTICE_USERS) is False


@pytest.mark.parametrize("args", [
    ["update", "user", "test@x.org", "suspended", "on"],
    ["update", "user", "test@x.org", "ou", "/Test/A"],
    ["update", "user", "kid@x.org", "changepassword", "on"],
    ["user", "test@x.org", "transfer", "drive", "kid@x.org"],
])
def test_practice_mode_still_runs_test_changes(args):
    from gambit import user_prefs as up
    settings.set("safety/test_ou", "/Test")
    settings.set("safety/test_user", "test@x.org")
    assert up.practice_allows(args, PRACTICE_USERS) is True


# ------------------------------------------- 2. background task's profile ---
def test_run_here_puts_the_profile_back(monkeypatch):
    from gambit import headless, tasks_health

    def fake_main(args):
        settings.override.update({"profile/current": "Other", "gam/cfgdir": "C:/other"})
        return 0
    monkeypatch.setattr(headless, "main", fake_main)
    settings.override.clear()
    assert tasks_health.run_here(["--task", "daily"]) == 0
    assert "profile/current" not in settings.override
    assert "gam/cfgdir" not in settings.override

    def boom(args):
        settings.override["profile/current"] = "Other"
        raise RuntimeError("x")
    monkeypatch.setattr(headless, "main", boom)
    with pytest.raises(RuntimeError):
        tasks_health.run_here(["--task", "daily"])
    assert "profile/current" not in settings.override


# ------------------------------------ 3. saved Chromebook jobs and dry run ---
def test_saved_job_dry_run_changes_nothing(tmp_path, monkeypatch):
    from gambit import activity
    from gambit.tools import assigned_users as au
    from tests.test_assigned_users import MOPTS, MOVE_ROWS, MOVE_USERS, OUS
    monkeypatch.setattr(au, "backup_dir", lambda: str(tmp_path))
    au.save_move_options(MOPTS)
    recorded, ran, logs = [], [], []
    monkeypatch.setattr(activity, "record", lambda *a, **k: recorded.append(a))
    code = au.run_move_task(log=logs.append, run_csv=lambda a: (0, MOVE_ROWS, ""),
                            run_text=lambda a, t=0: (ran.append(a), (0, ""))[1],
                            users=MOVE_USERS, ous=OUS, dry=True)
    assert code == 0 and ran == [] and recorded == []
    assert not os.listdir(tmp_path)                     # no backup either
    assert any("would run: gam cros m1,m7 update ou" in m for m in logs)


def test_saved_job_run_now_passes_dry(monkeypatch):
    from gambit import saved_jobs
    from gambit.tools import assigned_users as au
    got = {}
    monkeypatch.setattr(saved_jobs, "get", lambda i: {"id": i, "name": "J", "kind": "move",
                                                      "opts": {}, "enabled": True})
    monkeypatch.setattr(saved_jobs, "describe", lambda j: "")
    monkeypatch.setattr(au, "run_move_task", lambda **k: got.update(k) or 0)
    saved = []
    monkeypatch.setattr(saved_jobs, "_save_all", lambda items: saved.append(items))
    assert saved_jobs.run("j1", log=lambda m: None, force=True, dry=True) == 0
    assert got["dry"] is True and saved == []          # a rehearsal isn't a "last run"


# ---------------------------------------------------------------- 4. undo ---
USERS = [{"email": "a@s.org", "ou": "/Staff", "suspended": False},
         {"email": "b@s.org", "ou": "/Staff", "suspended": True}]


def test_undo_does_not_flip_values_that_did_not_change():
    from gambit import activity
    # b was already suspended: nothing to undo
    assert activity.infer_undo(["update", "user", "b@s.org", "suspended", "on"], USERS) is None
    # unknown old value: no guess
    assert activity.infer_undo(["update", "user", "a@s.org", "changepassword", "on"],
                               USERS) is None
    u = activity.infer_undo(["users", "a@s.org,b@s.org", "update", "user", "suspended", "on"],
                            USERS)
    assert u["steps"] == [["users", "a@s.org", "update", "user", "suspended", "off"]]
    # an OU or group: GAMbit can't know who changed without looking
    assert activity.infer_undo(["ou", "/Staff", "update", "user", "suspended", "on"],
                               USERS) is None


def test_capture_undo_reads_real_values_for_ous():
    from gambit import activity
    asked = []

    def run_csv(args):
        asked.append(args)
        return 0, [{"primaryEmail": "a@s.org", "suspended": "False",
                    "changePasswordAtNextLogin": "True", "orgUnitPath": "/Staff"},
                   {"primaryEmail": "b@s.org", "suspended": "True",
                    "changePasswordAtNextLogin": "False", "orgUnitPath": "/Staff"}], ""
    u = activity.capture_undo(["ou", "/Staff", "update", "user", "suspended", "on"], run_csv)
    assert asked[0][:4] == ["ou", "/Staff", "print", "users"]
    assert u["steps"] == [["users", "a@s.org", "update", "user", "suspended", "off"]]
    u = activity.capture_undo(["update", "user", "a@s.org", "changepassword", "on"], run_csv)
    assert u.get("none")                              # a already had to change it
    u = activity.capture_undo(["update", "user", "b@s.org", "changepassword", "on"], run_csv)
    assert u["steps"] == [["users", "b@s.org", "update", "user", "changepassword", "off"]]
    from gambit.helper import verify
    assert verify.check(u["steps"][0])[0]


def test_submit_uses_none_marker(qapp, fake_gam, monkeypatch):
    from gambit import activity
    from gambit.gam_runner import Job
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    monkeypatch.setattr(activity, "capture_undo", lambda a, r: {"none": True, "label": ""})
    j = Job(["update", "user", "b@s.org", "suspended", "on"], None, True)
    j.meta = {}
    w._on_submit(j)
    assert j.meta["undo"] is None
    w.close()


# ------------------------------------------------------------ 5/6. rollover ---
def test_rollover_pairs_by_grade_number_not_alphabet():
    from gambit.next_year import pair_by_grade
    pairs, odd = pair_by_grade(["/S/Grade 10", "/S/Grade 11", "/S/Grade 12", "/S/Grade 9"])
    assert pairs == [("/S/Grade 9", "/S/Grade 10"), ("/S/Grade 10", "/S/Grade 11"),
                     ("/S/Grade 11", "/S/Grade 12"), ("/S/Grade 12", "")] and not odd
    pairs, odd = pair_by_grade(["/E/K", "/E/01", "/E/03", "/E/Office"])
    assert pairs == [("/E/K", "/E/01"), ("/E/03", "")]
    assert set(odd) == {"/E/01", "/E/Office"}          # a gap after 1, and no grade


def test_rollover_plan_is_safe():
    from gambit.next_year import rollover_plan
    rows = [("/S/Grade 9", "/S/Grade 10"), ("/S/Grade 12", "/S/Graduated"),
            ("/S/Grade 10", "/S/Grade 11"), ("/S/Grade 11", "/S/Grade 12")]
    steps, problem = rollover_plan(rows, True)
    assert not problem and all(req for _l, _a, req in steps)
    order = [a[5] for _l, a, _r in steps if a[0] == "update"]
    assert order == ["/S/Grade 12", "/S/Grade 11", "/S/Grade 10", "/S/Grade 9"]
    assert steps[-1][1] == ["ou", "/S/Graduated", "update", "user", "suspended", "on"]
    assert rollover_plan([("/S/Grade 9", "/S/Grade 11")], False)[1]      # skips a grade
    assert rollover_plan([("/S/A", "/S/B"), ("/S/B", "/S/A")], False)[1]  # a loop
    # no graduates row → never suspend the 12th graders
    assert rollover_plan([("/S/Grade 11", "/S/Grade 12")], True)[1]


def test_rollover_steps_are_required(qapp, fake_gam, monkeypatch):
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    wf = w.pages["Workflows"]
    if hasattr(wf, "ro_table"):
        wf.ro_table.setRowCount(0)
        wf.ro_add("/S/Grade 11", "/S/Grade 12")
        wf.ro_add("/S/Grade 12", "/S/Graduated")
        got = []
        monkeypatch.setattr(wf, "confirm", lambda *a, **k: True)
        monkeypatch.setattr(wf.ro_steps, "run", lambda steps, done=None: got.extend(steps))
        wf.ro_run()
        assert got and all(s.required for s in got)
        assert got[0].args[2] == "/S/Graduated"
    w.close()


# ----------------------------------------------- 7. offboarding lock password ---
def test_offboard_lock_password_is_never_saved(team_dir):
    from gambit import offboard
    from gambit.secret_args import TOKEN, fill
    rec = offboard.build("k@s.org", "", {"groups": [], "ou": "/Staff", "name": "K"},
                         offboard.DEFAULTS, lambda n=20: "Sup3rSecret!pw")
    offboard.save(rec)
    text = open(offboard._file("k@s.org"), encoding="utf-8").read()
    assert "Sup3rSecret" not in text and TOKEN in text
    args = next(s["args"] for s in rec["stages"][0]["steps"] if s["key"] == "lock"
                and "password" in s["args"])
    a1, a2 = fill(args)[-1], fill(args)[-1]
    assert TOKEN not in (a1, a2) and a1 != a2 and len(a1) >= 20
    # an old plan with a password in it is cleaned the first time it's read
    old = json.loads(text)
    for st in old["stages"]:
        for s in st["steps"]:
            if "password" in s["args"]:
                s["args"][-1] = "OldPlainPassw0rd"
    with open(offboard._file("k@s.org"), "w", encoding="utf-8") as fh:
        json.dump(old, fh)
    offboard.get("k@s.org")
    assert "OldPlainPassw0rd" not in open(offboard._file("k@s.org"), encoding="utf-8").read()


def test_runner_fills_the_secret_only_for_gam(qapp, fake_gam):
    from gambit.secret_args import TOKEN
    r = _runner()
    r.run(["update", "user", "k@s.org", "password", TOKEN])
    job = r.jobs[-1]
    for _ in range(200):
        pump(0.05)
        if job.status not in ("running", "queued"):
            break
    assert job.status == "done" and job.args[-1] == TOKEN    # what's recorded and shown
    calls = [c for c in fake_gam.calls() if "k@s.org" in c]
    assert calls and TOKEN not in calls[-1] and "password" in calls[-1]


# --------------------------------------------- 8. floating buttons on tables ---
def test_row_buttons_hide_when_rows_change(qapp):
    from gambit.ui.widgets import ResultsTable
    t = ResultsTable()
    t.resize(800, 400)
    t.show()
    t.set_rows(["primaryEmail"], [["a@x"], ["b@x"]])
    from PySide6.QtWidgets import QFrame, QToolButton
    t._row_bar = QFrame(t.table.viewport())
    t._row_bar.show()
    t._bar_row = 0
    t._copy_btn = QToolButton(t.table.viewport())
    t._copy_btn.setProperty("value", "a@x")
    t._copy_btn.show()
    t.set_rows(["primaryEmail"], [["z@x"]])
    assert not t._row_bar.isVisible() and t._bar_row == -1
    assert not t._copy_btn.isVisible() and not t._copy_btn.property("value")
    t._row_bar.show()
    t._apply_filter("zz")
    assert not t._row_bar.isVisible()
    t._row_bar.show()
    t.sort_by(0)
    assert not t._row_bar.isVisible()


def test_selection_follows_rows_when_sorted(qapp):
    from gambit.ui.widgets import ResultsTable
    t = ResultsTable()
    t.set_rows(["primaryEmail"], [["c@x"], ["a@x"], ["b@x"]])
    t.table.selectRow(0)                                 # c@x
    t.sort_by(0)
    assert [d["primaryEmail"] for d in t.selected_dicts()] == ["c@x"]


def test_selection_bar_refreshes_on_new_rows(qapp):
    from gambit.ui.widgets import ResultsTable
    t = ResultsTable()
    t.set_rows(["primaryEmail"], [["a@x"], ["b@x"]])
    calls = []
    t._selection_changed = lambda *a: calls.append(1)
    t.set_rows(["primaryEmail"], [["c@x"]])
    assert calls


# ---------------------------------------------- 9. view-only page bypass ---
def test_page_name_not_set_when_leaving_is_refused(qapp, fake_gam, monkeypatch):
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    w.go("Users")
    assert w._current_page_name == "Users"
    monkeypatch.setattr(w, "_ok_to_leave", lambda name: False)
    w.go("Groups")
    assert w._current_page_name == "Users"
    w.close()


# ----------------------------------------------- 11. undo marker doesn't leak ---
def test_undo_marker_cleared_in_dry_run(qapp, fake_gam):
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    w.set_dry_run(True)
    w.run_undo({"id": "e1", "undo": {"args": ["update", "user", "a@s.org", "suspended",
                                              "off"]}})
    assert w._pending_undo_of == ""
    w.set_dry_run(False)
    w.close()


# ---------------------------------------- 16. running jobs are never trimmed ---
def test_history_trim_keeps_live_jobs(qapp):
    from gambit.gam_runner import Job
    r = _runner()
    live = Job(["print", "users"], None, True)
    live.status = "running"
    r.jobs = [live] + [Job(["info", "domain"], None, True) for _ in range(250)]
    for j in r.jobs[1:]:
        j.status = "done"
    r._trim_history()
    assert live in r.jobs and len(r.jobs) == 201


# ------------------------------------------ 15. .cmd quoting can't break out ---
def _cmd_unquoted(line: str) -> str:
    """The characters cmd.exe sees outside quotes (it only counts quote characters)."""
    out, q = [], False
    for ch in line:
        if ch == '"':
            q = not q
        elif not q:
            out.append(ch)
    return "".join(out)


def _crt_split(line: str) -> list[str]:
    """How the C runtime (2008+) splits a command line into argv."""
    args, cur, i, q, have = [], [], 0, False, False
    while i < len(line):
        ch = line[i]
        if ch == "\\":
            n = 0
            while i < len(line) and line[i] == "\\":
                n += 1
                i += 1
            if i < len(line) and line[i] == '"':
                cur.append("\\" * (n // 2))
                if n % 2:
                    cur.append('"')
                    i += 1
                have = True
                continue
            cur.append("\\" * n)
            have = True
            continue
        if ch == '"':
            if q and i + 1 < len(line) and line[i + 1] == '"':
                cur.append('"')
                i += 2
                continue
            q = not q
            have = True
            i += 1
            continue
        if ch in " \t" and not q:
            if have or cur:
                args.append("".join(cur))
            cur, have = [], False
            i += 1
            continue
        cur.append(ch)
        have = True
        i += 1
    if have or cur:
        args.append("".join(cur))
    return args


@pytest.mark.parametrize("arg", [
    'Weekly "A & B" report', 'a & calc', 'x" & calc & "', 'C:\\path with space\\',
    'end\\"quote', 'name:\'x\' | more', 'line1\nline2', '', 'plain', 'tab\there',
    '100%', 'a^b<c>d', 'back\\\\"slash & x',
])
def test_cmd_quote_is_safe_for_cmd_and_gam(arg):
    from gambit.scheduler import cmd_quote
    q = cmd_quote(arg)
    line = "gam " + q + " next"
    outside = _cmd_unquoted(line)
    assert not set("&|<>^") & set(outside)          # no operator outside quotes
    assert "\n" not in q
    want = arg.replace("\r", " ").replace("\n", " ").replace("%", "%%")
    assert _crt_split(line) == ["gam", want, "next"]


def test_webhook_line_cannot_run_commands():
    from gambit.alerts import powershell_post
    line = powershell_post("https://hooks.example.com/x", "Job A & calc | x had a failed step")
    assert "&" not in _cmd_unquoted(line).replace(">nul 2>&1", "") and \
        "|" not in _cmd_unquoted(line)


# ------------------------------------------------- 10. what counts as a change ---
@pytest.mark.parametrize("args,change", [
    (["group", "help", "update", "user", "suspended", "on"], True),       # group named “help”
    (["users", "info", "update", "user", "suspended", "on"], True),
    (["user", "a@s.org", "approve", "deviceuser", "x"], True),
    (["cros_sn", "S1", "cancelwipe", "users"], True),
    (["user", "a@s.org", "rotate", "sakeys"], True),
    (["user", "a@s.org", "hide", "shareddrive", "x"], True),
    (["user", "a@s.org", "revoke", "browsertoken"], True),
    (["send", "userinvitation", "a@s.org"], True),
    (["users", "a@s.org", "language", "en"], True),
    (["select", "s1", "update", "user", "a@s.org", "ou", "/y"], True),
    (["print", "users"], False), (["user", "a@s.org", "print", "groups"], False),
    (["ou", "/x", "print", "users"], False), (["select", "s1", "info", "domain"], False),
    (["report", "users"], False), (["collect", "orphans", "preview"], False),
])
def test_is_change_reads_the_action_word(args, change):
    from gambit import activity
    assert activity.is_change(args) is change


# --------------------------------------------- 12. undo in the right domain ---
def test_undo_refused_in_another_domain(qapp, fake_gam, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from gambit import profiles
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    monkeypatch.setattr(profiles, "profiles", lambda: [{"name": "Default"}, {"name": "Other"}])
    monkeypatch.setattr(profiles, "current_name", lambda: "Default")
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    ran = []
    monkeypatch.setattr(w.runner, "run", lambda *a, **k: ran.append(a) or True)
    e = {"id": "x", "profile": "Other", "undo": {"args": ["update", "user", "a@s.org",
                                                         "suspended", "off"]}}
    assert w.run_undo(e) is False and not ran
    e["profile"] = "Default"
    assert w.run_undo(e) is True and ran
    w.close()


# -------------------------------------------- 13. undo for several Chromebooks ---
def test_cros_undo_per_serial():
    from gambit import activity

    def run_csv(args):
        return 0, [{"serialNumber": "SN2", "orgUnitPath": "/B", "notes": "two"},
                   {"serialNumber": "SN1", "orgUnitPath": "/A", "notes": "one"}], ""
    u = activity.capture_undo(["cros_sn", "SN1,SN2,SN3", "update", "ou", "/Lost"], run_csv)
    assert ["cros_sn", "SN1", "update", "ou", "/A"] in u["steps"]
    assert ["cros_sn", "SN2", "update", "ou", "/B"] in u["steps"]
    assert len(u["steps"]) == 2 and "SN3" in u["label"]        # never guessed


# ----------------------------------------------------- 14. Run later queue ---
def test_queue_claim_runs_once_and_keeps_other_edits(team_dir, monkeypatch):
    from gambit import change_queue as cq
    cq.save_queue([])
    with pytest.raises(cq.QueueRefused):                  # passwords never wait in a file
        cq.add([["update", "user", "a@s.org", "password", "Secret123!"]], "2000-01-01T00:00",
               "A", "me", profile="Default")
    a = cq.add([["update", "user", "a@s.org", "suspended", "on"]], "2000-01-01T00:00",
               "A", "me", profile="Default")
    assert a["profile"] == "Default"
    assert [x["id"] for x in cq.claim([a["id"]])] == [a["id"]]
    assert cq.claim([a["id"]]) == []                          # nobody runs it twice
    b = cq.add([["info", "domain"]], "2000-01-01T00:00", "B", "me")   # added meanwhile
    cq.finish(a["id"], "done", "1 ok")
    items = {x["id"]: x for x in cq.queue()}
    assert b["id"] in items and items[a["id"]]["status"] == "done"
    assert cq.verify(items[b["id"]]) is not None              # signed when queued


def test_queue_runs_in_its_own_profile(team_dir, monkeypatch):
    from gambit import change_queue as cq, headless, profiles
    cq.save_queue([])
    cq.add([["update", "user", "a@s.org", "ou", "/x"]], "2000-01-01T00:00", "A", "me",
           profile="Other")
    monkeypatch.setattr(profiles, "current_name", lambda: "Default")
    seen = []

    def use(name):
        settings.override["profile/current"] = name
    monkeypatch.setattr(headless, "use_profile", use)

    def run_text(cmd, t):
        seen.append(settings.get("profile/current"))
        return 0, ""
    settings.override.clear()
    cq.run_due(lambda *_: None, run_text)
    assert seen == ["Other"] and "profile/current" not in settings.override


# ------------------------------------------------------ 17. steps that depend ---
def test_setup_steps_skip_after_failed_create(qapp, fake_gam):
    from gambit.ui.steps import Step, StepList

    class P:
        class runner:
            @staticmethod
            def run(args, cb):
                cb(1 if args[0] == "fail" else 0, "", "")
                return True
    sl = StepList(P())
    a = Step("create", ["fail"])
    b = Step("setup", ["ok"], after=a)
    c = Step("other", ["ok"])
    done = []
    sl.run([a, b, c], lambda s: done.append([x.status for x in s]))
    assert done == [["fail", "skip", "ok"]]


# ------------------------------------------------ 18/22. offboarding snapshot ---
def test_restart_keeps_original_before(team_dir):
    from gambit import offboard
    before = {"groups": [["g@s.org", "owner"]], "licenses": [], "ou": "/Staff", "name": "K",
              "gal": True, "complete": True}
    rec = offboard.build("k@s.org", "", before, offboard.DEFAULTS, lambda n=20: "x")
    offboard.save(rec)
    assert offboard.earlier_before("k@s.org") is None    # unsigned: not trusted
    offboard.save(rec, sign_it=True)
    assert offboard.earlier_before("k@s.org")["ou"] == "/Staff"
    rec2 = offboard.build("k@s.org", "", {"groups": [], "ou": "", "name": "K"},
                          offboard.DEFAULTS, lambda n=20: "x")
    ou_step = next(s for s in rec2["stages"][0]["steps"] if s["key"] == "ou")
    assert ou_step["undo"] is None                  # never "move them back to /"
    with pytest.raises(ValueError):
        offboard.build_graduate("s@s.org", before, {**offboard.GRAD_DEFAULTS, "alumni_ou": ""},
                                2026)


def test_capture_reports_incomplete():
    from gambit import offboard
    b = offboard.capture("k@s.org", lambda a: (1, [], "boom"))
    assert b["complete"] is False


# --------------------------------------------------- 19/21/27. manage user ---
def test_manage_user_needs_a_real_person(qapp, fake_gam, monkeypatch):
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    p = w.pages["Users"]
    p.directory.users = [{"email": "jdoe@school.org", "name": "Jane Doe"},
                         {"email": "jdoe@other.org", "name": "J Doe"}]
    p.m_email.setText("smith")
    assert p._email() is None
    p.m_email.setText("Jane Doe")
    assert p._email() == "jdoe@school.org"
    p.m_email.setText("jdoe")                      # two people have that username
    assert p._email() is None
    p.m_pw.setText("Typed1234!")
    p.m_email.setText("someone@school.org")
    assert p.m_pw.text() == ""                     # a password belongs to one person
    w.set_dry_run(True)
    shown = []
    monkeypatch.setattr(p, "info", lambda t, *a: shown.append(t))
    p.reset_pw()
    for _ in range(50):
        pump(0.02)
        if shown:
            break
    assert shown and "NOT changed" in shown[0] and p.m_pw.text() == ""
    w.set_dry_run(False)
    w.close()


def test_quick_reset_dedupes(qapp, fake_gam, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    ran, shown = [], []
    monkeypatch.setattr(w.runner, "run", lambda args, cb=None, *a: (ran.append(args),
                                                                     cb(0, "", ""), True)[2])
    monkeypatch.setattr(w, "_show_pw", lambda r, dry=False: shown.append(r))
    w.quick_reset(["a@s.org", "A@s.org", "b@s.org"])
    assert len(ran) == 2 and len(shown) == 1 and len(shown[0]) == 2
    w.close()


# ------------------------------------------------- 20. keep other IDs and jobs ---
def test_sis_keeps_other_ids_and_organizations():
    from gambit import sis
    acct = {"ext_ids": [{"type": "login_id", "value": "L1"},
                        {"type": "custom", "customType": "Badge", "value": "B9"},
                        {"type": "organization", "value": "OLD"}],
            "orgs": [{"name": "HCS", "title": "Teacher", "department": "Math",
                      "costCenter": "77", "primary": "True"},
                     {"name": "Coach", "title": "Coach", "primary": "False"}]}
    ext = sis.merged_external_ids(acct, "NEW")
    assert ext == ["externalid", "login_id", "L1", "externalid", "custom", "Badge", "B9",
                   "externalid", "organization", "NEW"]
    p = sis.Person(sis_id="1", first="A", last="B", email="", grade="", school="",
                   title="Principal", department="")
    org = sis.merged_organizations(acct, p)
    assert org[:2] == ["organization", "name"] and "Principal" in org and "costcenter" in org
    assert org.count("organization") == 2 and org[-1] == "notprimary"
    from gambit.helper import verify
    assert verify.check(["update", "user", "a@s.org", *ext, *org])[0]
    assert sis.merged_external_ids({}, "NEW") is None          # old saved list: no wipe


# ---------------------------------------------------- 23. loading per job ---
def test_finished_label_matches_started(qapp, fake_gam):
    r = _runner()
    started, finished = [], []
    r.started.connect(started.append)
    r.finished.connect(lambda c, s: finished.append(s))
    for _ in range(3):
        r.run(["info", "domain"])
    for _ in range(200):
        pump(0.05)
        if len(finished) == 3:
            break
    assert sorted(started) == sorted(finished)


# ------------------------------------------- 24. unsaved forms after failure ---
def test_failed_create_keeps_unsaved_warning(qapp, fake_gam, monkeypatch):
    from gambit.ui import unsaved
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    g = w.pages["Groups"]
    g._n_tracker.dirty = True
    monkeypatch.setattr(g, "run", lambda args, cb=None, **k: cb and cb(1, "", ""))
    g.n_email.setText("new@s.org")
    g.create_group()
    assert "a new group" in unsaved.unsaved(g)
    monkeypatch.setattr(g, "run", lambda args, cb=None, **k: cb and cb(0, "", ""))
    monkeypatch.setattr(g, "open_group", lambda e: None)
    g.create_group()
    assert "a new group" not in unsaved.unsaved(g)
    w.close()


# --------------------------------------------- 26. column order per result ---
def test_column_order_does_not_carry_over(qapp):
    from gambit.ui.widgets import ResultsTable
    t = ResultsTable()
    t.set_rows(["a", "b", "c"], [["1", "2", "3"]])
    hh = t.table.horizontalHeader()
    hh.moveSection(0, 2)
    settings.set(t._cols_key(), "")
    t.set_rows(["x", "y", "z"], [["1", "2", "3"]])
    assert [hh.logicalIndex(i) for i in range(3)] == [0, 1, 2]


# ------------------------------------------------- 28. restore a hidden page ---
def test_restore_skips_pages_hidden_by_simple_mode(qapp, fake_gam):
    from gambit.ui import unsaved
    from gambit.ui.main_window import MainWindow
    settings.set(unsaved.RESTORE_KEY, True)
    settings.set(unsaved.LAST_PAGE_KEY, "Users")
    settings.set("ui/simple", True)
    try:
        w = MainWindow()
        w.restore_last_page()
        assert w._current_page_name in ("", "Home")
        w.close()
    finally:
        settings.set("ui/simple", False)


# ----------------------------------------------------------- suspected items ---
def test_beta_is_not_newer_than_release():
    from gambit.net import is_newer
    assert not is_newer("1.5.0-beta1", "1.5.0") and is_newer("1.5.0", "1.5.0-beta1")
    assert is_newer("1.5.0-rc2", "1.5.0-rc1") and is_newer("7.49.0", "7.48.20")
    assert is_newer("GAM 7.49.0 - https://github.com/a/b", "7.48.0")


def test_finished_requests_drop_passwords(team_dir):
    from gambit import team
    r = team.new_request([["update", "user", "a@s.org", "password", "Secret123!"]],
                         "why", notify=False)
    r = team.update_request(r, "done")
    assert "Secret123!" not in json.dumps(r)
    saved = open(os.path.join(str(team_dir), *[]) and team._path("requests",
                                                                  f"{r['id']}.json"),
                 encoding="utf-8").read()
    assert "Secret123!" not in saved


def test_masked_password_never_runs(qapp, fake_gam):
    from gambit.directory import run_gam_text
    assert _runner().run(["update", "user", "a@s.org", "password", "********"]) is False
    code, out = run_gam_text(["update", "user", "a@s.org", "password", "********"])
    assert code == 77 and not any("a@s.org" in c for c in fake_gam.calls())


def test_group_removal_fallback_undo():
    from gambit import activity
    u = activity.infer_undo(["update", "group", "g@s.org", "remove", "member", "a@s.org,b@s.org"],
                            [])
    assert u["args"] == ["update", "group", "g@s.org", "add", "member", "a@s.org,b@s.org"]


def test_welcome_password_hidden_whatever_the_wording():
    from gambit import onboard
    from gambit.gam_runner import display_command
    a = onboard.welcome_email("n@s.org", "Xy7pq9Lm!", {"first": "N", "manager": "b@s.org"},
                              {"welcome": True, "body": "Your code is {password} – enjoy"})
    assert "Xy7pq9Lm!" not in display_command(a)


def test_ou_queries_escape_quotes():
    from gambit import queries
    assert queries.ou("/O'Brien School") == "orgUnitPath='/O\\'Brien School'"


def test_device_notes_are_kept():
    from gambit.tools import lost_devices
    cmds = lost_devices.mark_commands({"serial": "S1", "last_user": "a", "user": "",
                                       "status": "ACTIVE"}, "lost", {})
    assert cmds[0][3] == "updatenotes" and cmds[0][4].endswith("#notes#")


def test_test_mode_sync_doesnt_reach_real_people():
    from gambit import sis
    c = sis.Change("create", "n@s.org", "N", "", [
        ["create", "user", "n@s.org", "ou", "/Staff"],
        ["update", "group", "allstaff@s.org", "add", "member", "user", "n@s.org"],
        ["sendemail", "to", "boss@s.org", "subject", "x", "message", "y"],
        ["user", "n@s.org", "add", "license", "1010020020"]])
    out = sis.limit_to_test_ou([c], [], "/Test")
    flat = [x[0] for x in out[0].commands]
    assert flat == ["create", "user"] and out[0].commands[0][-1] == "/Test"


def test_toast_undo_runs_once(qapp):
    from PySide6.QtWidgets import QPushButton, QWidget
    from gambit.ui.toast import ToastHost, NotifyCenter
    win = QWidget()
    win.resize(800, 600)
    host = ToastHost(win, NotifyCenter(win))
    hits = []
    t = host.show("Done", "ok", "Undo", lambda: hits.append(1), ms=5000)
    btn = next(b for b in (t or win).findChildren(QPushButton) if b.text() == "Undo")
    btn.click()
    btn.click()
    assert hits == [1]


def test_drawer_values_are_plain_text(qapp, fake_gam):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    w.resize(1400, 900)
    w.show_details({"primaryEmail": "x@s.org", "description": "<b>bold</b>"})
    d = w.drawer
    labs = [lab for lab in d.findChildren(QLabel) if "<b>bold</b>" in lab.text()]
    assert labs and all(lab.textFormat() == Qt.PlainText for lab in labs)
    from gambit.ui import friendly
    settings.set(friendly.KEY, False)
    try:
        w.show_details({"primaryEmail": "x@s.org", "lastLoginTime": "2026-10-01T10:00:00.000Z"})
        assert any(lab.text() == "2026-10-01T10:00:00.000Z" for lab in d.findChildren(QLabel))
    finally:
        settings.set(friendly.KEY, True)
    w.close()
