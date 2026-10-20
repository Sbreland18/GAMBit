"""Saved scheduled jobs (Automation → Schedules)."""

import pytest

from gambit import saved_jobs as sj
from gambit import scheduler
from gambit.tools import assigned_users as au


@pytest.fixture(autouse=True)
def clean():
    sj._save_all([])
    yield
    sj._save_all([])


def test_two_jobs_of_the_same_kind_for_different_org_units():
    a = sj.new("move", "Move Chromebooks – Middle", {"source": "pattern",
               "ou_template": "/Chrome Devices/{school}"}, ["/Chrome Devices/HMS"], "05:15",
               ["MON", "WED"])
    b = sj.new("move", "Move Chromebooks – Middle", {"source": "map"},
               ["/Chrome Devices/HHS"], "06:00", [])
    assert b["name"] == "Move Chromebooks – Middle (2)"           # names stay unique
    assert sj.task_name(a) != sj.task_name(b)
    assert [j["scope_ous"] for j in sj.jobs()] == [["/Chrome Devices/HMS"],
                                                   ["/Chrome Devices/HHS"]]
    assert "pattern /Chrome Devices/{school}" in sj.describe(a)
    assert sj.when(a) == "Mon, Wed at 5:15 AM"


def test_task_names_are_safe_and_edit_keeps_the_id():
    j = sj.new("assigned", 'Blank: "HS" / unused?', {"sched_stale": True}, [], "05:00", [])
    assert sj.task_name(j) == "GAMbit job - Blank- -HS- - unused-"
    j2 = sj.update({**j, "name": "Blank HS", "enabled": False})
    assert j2["id"] == j["id"] and sj.get(j["id"])["enabled"] is False
    d = sj.duplicate(j["id"])
    assert d["enabled"] is False and d["name"] == "Blank HS copy"


def test_job_settings_never_include_the_tabs_schedule_flags():
    j = sj.new("assigned", "x", {**au.options(), "sched_time": "1", "scheduled": True,
                                 "scope_ous": ["/X"], "allow_big": True}, [], "05:00", [])
    assert not {"sched_time", "scheduled", "scope_ous", "allow_big"} & set(j["opts"])


def test_run_uses_the_jobs_own_settings_and_org_units(monkeypatch):
    seen = {}
    monkeypatch.setattr(au, "run_move_task", lambda log=print, o=None, **k:
                        (seen.update(o), 0)[1])
    j = sj.new("move", "HS", {"source": "pattern", "ou_template": "/CD/{school}"},
               ["/Chrome Devices/HHS"], "05:00", [])
    assert sj.run(j["id"], log=lambda m: None) == 0
    assert seen["scope_ous"] == ["/Chrome Devices/HHS"] and seen["ou_template"] == "/CD/{school}"
    assert sj.get(j["id"])["last_run"]
    sj.update({**sj.get(j["id"]), "enabled": False})
    seen.clear()
    assert sj.run(j["id"], log=lambda m: None) == 0 and not seen          # off: skipped
    assert sj.run(j["id"], log=lambda m: None, force=True) == 0 and seen   # Run now


def test_assigned_job_runs_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(au, "backup_dir", lambda: str(tmp_path))
    rows = [{"deviceId": "s1", "serialNumber": "S1", "annotatedUser": "",
             "orgUnitPath": "/CD/HMS", "activeTimeRanges.0.date": "2099-01-01",
             "recentUsers.0.email": "kid@x.org"}]
    calls = []
    j = sj.new("assigned", "HMS", {"sched_set": True, "students_only": True,
                                   "blank_only": True}, ["/CD/HMS"], "05:00", [])
    code = sj.run(j["id"], log=lambda m: None,
                  run_csv=lambda a: (calls.append(a), (0, rows, ""))[1],
                  run_text=lambda a, t=0: (calls.append(a), (0, ""))[1],
                  users=[{"email": "kid@x.org", "ou": "/Students/HMS"}])
    assert code == 0
    assert any("cros_ou_and_children" in a and "/CD/HMS" in a for a in calls)
    assert ["cros", "s1", "update", "user", "kid@x.org"] in calls


def test_schedule_creates_one_task_per_job(monkeypatch):
    made = []
    monkeypatch.setattr(scheduler, "IS_WINDOWS", True)
    import gambit.tasks_health as th
    monkeypatch.setattr(th, "IS_WINDOWS", True)
    monkeypatch.setattr(scheduler, "build_app_task_script", lambda n, a: f"{n}.cmd")
    monkeypatch.setattr(scheduler, "_run", lambda a: (made.append(a), (0, "ok"))[1])
    j = sj.new("move", "HS", {}, [], "05:15", ["MON", "FRI"], enabled=False)
    sj.schedule(j, old_task="GAMbit move Chromebooks to students' schools")
    flat = [" ".join(a) for a in made]
    assert any("/Delete" in f and "students' schools" in f for f in flat)
    assert any("/Create" in f and "GAMbit job - HS" in f and "MON,FRI" in f for f in flat)
    assert any("/Change" in f and "/DISABLE" in f for f in flat)


def test_legacy_morning_jobs_become_saved_jobs():
    from gambit.settings import settings
    settings.set("jobs/migrated", False)
    au.save_options({**au.options(), "sched_stale": True, "sched_time": "05:30",
                     "sched_days": ["MON"], "scope_ous": ["/CD/HMS"]})
    made = sj.migrate_legacy()
    assert len(made) == 1 and made[0]["kind"] == "assigned"
    assert made[0]["scope_ous"] == ["/CD/HMS"] and made[0]["time"] == "05:30"
    assert not au.options()["sched_stale"]
    assert sj.migrate_legacy() == []                                  # only once


def test_headless_runs_a_saved_job(monkeypatch):
    from gambit import headless
    monkeypatch.setattr(sj, "run", lambda job_id, log=print: 7 if job_id == "abc" else 0)
    assert headless.main(["--task", "job", "--name", "abc"]) == 7


def test_schedules_page_and_dialog(qapp):
    from PySide6.QtCore import QObject, Signal

    from gambit.ui.pages.schedules_page import JobDialog

    class Dir(QObject):
        ous_changed = Signal()
        ous = ["/", "/CD", "/CD/HMS"]
    j = sj.new("assigned", "HMS", {"sched_set": True, "stale_days": 45}, ["/CD/HMS"], "05:00",
               ["TUE"])
    dlg = JobDialog(None, Dir(), j)
    dlg.w["sched_stale"].setChecked(True)
    dlg.w["stale_days"].setValue(90)
    dlg.all.setChecked(True)
    r = dlg.result_job()
    assert r["opts"]["sched_stale"] and r["opts"]["stale_days"] == 90 and r["scope_ous"] == []
    assert r["days"] == ["TUE"] and r["id"] == j["id"]
