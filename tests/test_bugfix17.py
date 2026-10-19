"""Regression tests for the round 17 bug sweep."""

import datetime
import gzip
import json
import os
import time

import pytest

from gambit import team
from gambit.auth import access, session
from gambit.settings import settings


@pytest.fixture
def auth_env(tmp_path, monkeypatch):
    d = tmp_path / "team"
    d.mkdir()
    settings.set("team/folder", str(d))
    settings.set("access/pinned", "")
    monkeypatch.setattr(access, "_app_dir", lambda: str(tmp_path / "app"))
    session.end()
    session.set_doc(None)
    yield d
    session.end()
    session.set_doc(None)
    settings.set("team/folder", "")
    settings.set("access/pinned", "")


# ============================================================ access list ===
def test_demoted_admin_cannot_sign(auth_env):
    doc = access.new_list("boss@d.org", "d.org", "c", "s")
    doc["people"]["boss@d.org"]["role"] = "Help desk"
    with pytest.raises(access.AccessError, match="your own admin rights|trusted key"):
        access.save(doc, "boss@d.org")
    # a second admin with a trusted key can demote the first
    doc = access.load()
    doc["people"]["two@d.org"] = {"role": "Full admin"}
    access.request_admin_key("two@d.org")
    req = access.key_requests()[0]
    doc = access.save(access.approve_key(doc, req), "boss@d.org")
    doc["people"]["boss@d.org"]["role"] = "Help desk"
    doc = access.save(doc, "two@d.org")
    assert access.keyed_admins(doc) == ["two@d.org"]         # boss's key was dropped
    assert all(k["email"] != "boss@d.org" for k in doc["admin_keys"].values())
    with pytest.raises(access.AccessError):
        access.save(access.load(), "boss@d.org")


def test_damaged_list_and_set_doc_self(auth_env):
    access.new_list("boss@d.org", "d.org", "c", "s")
    good = access.load()
    open(access.path(), "w").write('{"doc": {"peop')
    with pytest.raises(access.AccessError, match="Couldn't read"):
        access.load()
    session.set_doc(good)
    session.set_doc(session.doc())                # used to wipe the list
    assert session.doc()["domain"] == "d.org"


def test_builtin_role_edits_are_kept(auth_env):
    doc = access.new_list("boss@d.org", "d.org", "c", "s")
    session.set_doc(doc)
    session.start(access.person(doc, "boss@d.org"), "google", doc)
    data = team.load_roles()
    data["roles"]["Help desk"] = {**data["roles"]["Help desk"], "pages": ["Home"]}
    team.save_roles(data)
    assert access.load()["roles"]["Help desk"]["pages"] == ["Home"]


def test_scope_refuses_uncheckable_and_unknown_changes():
    session.end()
    session._current.update(email="a@d.org", ous=["/Students/Lincoln"], last=time.time(),
                            started=time.time(), idle=600, max=3600)
    users = {"kid@d.org": {"ou": "/Students/Lincoln"}, "out@d.org": {"ou": "/Staff"}}
    sp = session.scope_problem
    assert "batch" in sp(["batch", "f.txt"], users)
    assert "csv" in sp(["csv", "f.csv", "gam", "update", "user", "~email"], users)
    assert sp(["user", "out@d.org", "turnoff2sv"], users)
    assert sp(["update", "ou", "/Staff", "name", "X"], users)
    assert sp(["delete", "ou", "/Staff"], users)
    assert sp(["create", "user", "n@d.org", "firstname", "N"], users)       # no ou given
    assert sp(["create", "alias", "a@d.org", "user", "out@d.org"], users)
    assert sp(["info", "user", "out@d.org"], users, change=False)          # reads too
    assert sp(["info", "user", "kid@d.org"], users, change=False) == ""
    assert sp(["print", "cros"], users, change=False) == ""
    session.end()


def test_more_change_verbs():
    from gambit.activity import is_change
    assert is_change(["user", "a@d.org", "turnoff2sv"])
    assert is_change(["batch", "x.txt"])
    assert not is_change(["print", "users", "fields", "primaryemail"])


# ============================================================== roster sync ===
def test_roster_sync_never_takes_over_a_namesake():
    from gambit import sis
    r = sis.Rules()
    r.kind, r.email_template = "students", "{first}{last}@x.org"
    r.ou_template, r.managed_root = "/Students/B", "/Students"
    r.use_sis_email = False
    r.email_template = "{last}@x.org"
    people = [sis.Person("111", "John", "Smith", "", "5", "B"),
              sis.Person("222", "Jane", "Smith", "", "5", "B")]
    accts = [{"email": "smith@x.org", "name": "John Smith", "ou": "/students/b",
              "suspended": False, "sis_id": "111"}]
    ch = sis.plan(people, accts, r)
    jane = [c for c in ch if c.name == "Jane Smith"][0]
    assert jane.action == "create" and jane.email != "smith@x.org"
    john = [c for c in ch if c.name == "John Smith"]
    assert not john or all("ou" not in (cmd or []) for c in john for cmd in c.commands)


# ===================================================================== misc ===
def test_storage_forecast_far_future():
    from gambit import storage_forecast as sf
    items = [{"date": "2026-10-01", "total_mb": 40 * 1024 * 1024, "by_school": {}},
             {"date": "2026-10-08", "total_mb": 40 * 1024 * 1024 + 50, "by_school": {}}]
    assert sf.forecast(items, 100)["full_date"] == "not within 10 years"


def test_task_health_parsing(tmp_path, monkeypatch):
    from gambit import tasks_health as th
    log = tmp_path / "t.log"
    log.write_text("2026-10-15 06:15:00 [sync:A] Starting\n"
                   "2026-10-15 06:15:30 [sync:A] Applied: 12 change(s). Failed: 0.\n"
                   "2026-10-16 06:15:00 [daily] Starting\n"
                   "2026-10-16 06:15:10 [daily] Watchdog failed: boom\n"
                   "2026-10-16 06:16:05 [daily] Done\n", encoding="utf-8")
    monkeypatch.setattr(th, "_log_path", lambda: str(log))
    s = th.log_summary()
    assert s["sync:A"]["failed"] is False and s["daily"]["failed"] is True


def test_time_machine_tolerates_truncated_file(tmp_path, monkeypatch):
    from gambit import timemachine as tm
    monkeypatch.setattr(tm, "folder", lambda: str(tmp_path))
    tm.save({"a@d.org": {"ou": "/x"}}, datetime.date(2026, 10, 16))
    with open(tmp_path / "2026-10-17.json.gz", "wb") as fh:
        fh.write(gzip.compress(b'{"a@d.org": {"ou": "/y"}}')[:20])
    assert [d for d, _a in tm.history("a@d.org")] == ["2026-10-16"]
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]


def test_request_dedupe(tmp_path):
    settings.set("team/folder", str(tmp_path))
    try:
        a = team.new_request([["x"]], "first", title="Mismatch fixes (1)", notify=False,
                             dedupe="mismatch-nightly")
        b = team.new_request([["y"]], "second", title="Mismatch fixes (2)", notify=False,
                             dedupe="mismatch-nightly")
        assert a["id"] == b["id"] and len(team.list_requests("pending")) == 1
        assert team.list_requests("pending")[0]["commands"] == [["y"]]
    finally:
        settings.set("team/folder", "")


def test_ou_boundaries():
    from gambit.oupath import under
    from gambit.parent_report import school_of
    assert under("/Former/2026", "/Former") and not under("/FormerVolunteers", "/Former")
    assert under("/students/lincoln", "/Students")
    assert school_of("/StudentsTest/x", "/Students") == "StudentsTest"


def test_runner_timeout(monkeypatch):
    import subprocess
    from gambit import directory
    monkeypatch.setattr(directory.settings.__class__, "gam_path", lambda self: "/bin/gam",
                        raising=False)

    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired("gam", 1)
    monkeypatch.setattr(directory, "_run", boom)
    assert directory.run_gam_text(["print", "users"], 1)[0] == 124
    assert directory.run_gam_csv(["print", "users"], 1)[0] == 124


def test_battery_args_and_models():
    from gambit.tools import battery_forecast as bf
    a = bf.args("/Chromebooks")
    assert "showorgunitpath" in a and "orgunitpath" not in a[a.index("fields") + 1]
    rows = bf.add_models([{"serialNumber": "A1"}], [{"serialNumber": "a1", "model": "Dell"}])
    assert rows[0]["model"] == "Dell"


def test_meet_report_times_have_offset():
    from gambit import meet_attendance as ma
    a = ma.report_args("t@d.org", datetime.date(2026, 10, 15))
    start = a[a.index("start") + 1]
    assert start.startswith("2026-10-15T00:00:00") and ("+" in start[10:] or "-" in start[10:]
                                                        or start.endswith("Z"))
    json.dumps(a)


def test_gam_update_replaces_locked_files(tmp_path, monkeypatch):
    """WinError 32 while updating GAM: a running gam.exe is renamed out of the way."""
    import shutil
    from gambit import updaters
    src, dst = tmp_path / "new", tmp_path / "GAM7"
    (src / "lib").mkdir(parents=True)
    dst.mkdir()
    (src / "gam.exe").write_text("new exe")
    (src / "lib" / "x.dll").write_text("new dll")
    (dst / "gam.exe").write_text("old exe")
    (dst / "gam.exe.old-1").write_text("left over")
    real = shutil.copy2
    locked = {str(dst / "gam.exe")}

    def copy2(s, d, *a, **k):
        if str(d) in locked:
            err = OSError(32, "The process cannot access the file because it is being used")
            err.winerror = 32
            raise err
        return real(s, d, *a, **k)
    monkeypatch.setattr(updaters.shutil, "copy2", copy2)

    def fake_replace(a, b):          # renaming frees the name (as on Windows)
        os.rename(a, b)
        locked.discard(a)
    monkeypatch.setattr(updaters.os, "replace", fake_replace)
    assert updaters.cleanup_old_files(str(dst)) == 1
    moved = updaters.copy_tree_replacing(str(src), str(dst), sleep=lambda s: None)
    assert moved == [str(dst / "gam.exe")]
    assert (dst / "gam.exe").read_text() == "new exe"
    assert (dst / "lib" / "x.dll").read_text() == "new dll"
    assert any(f.startswith("gam.exe.old-") for f in os.listdir(dst))
