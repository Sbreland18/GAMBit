"""Scheduled jobs: run with GAMbit closed, catch up after sleep, run on battery."""

from gambit import scheduler


def test_created_tasks_are_tuned(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "IS_WINDOWS", True)
    monkeypatch.setattr(scheduler, "_run", lambda a: (calls.append(a), (0, "ok"))[1])
    scheduler.create_task("GAMbit Chromebook assigned users", "C:\\x.cmd", "weekly", "05:15",
                          "MON,WED")
    assert calls[0][:2] == ["schtasks", "/Create"] and "MON,WED" in calls[0]
    ps = calls[1]
    assert ps[0] == "powershell" and "StartWhenAvailable = $true" in ps[-1]
    assert "DisallowStartIfOnBatteries = $false" in ps[-1]
    assert "WakeToRun = $false" in ps[-1]


def test_tuning_failure_does_not_fail_scheduling(monkeypatch):
    monkeypatch.setattr(scheduler, "IS_WINDOWS", True)
    seq = iter([(0, "SUCCESS"), (1, "access denied")])
    monkeypatch.setattr(scheduler, "_run", lambda a: next(seq))
    assert scheduler.create_task("x", "y.cmd", "daily", "06:00") == "SUCCESS"


def test_tune_script_quotes_names_and_wake():
    s = scheduler.tune_script("GAMbit move Chromebooks to students' schools", True)
    assert "students'' schools" in s and "WakeToRun = $true" in s
    assert "-TaskPath '\\GAMbit\\'" in s


def test_schedule_picker_explains_gambit_can_be_closed(qapp):
    from PySide6.QtWidgets import QLabel

    from gambit.ui.schedule_edit import NOTE, ScheduleEdit
    w = ScheduleEdit()
    texts = [QLabel.text(x) for x in w.findChildren(QLabel)]
    assert NOTE in texts and "doesn't need to be open" in NOTE


def test_assigned_user_jobs_listed_with_their_days(monkeypatch):
    from gambit import tasks_health
    from gambit.tools import assigned_users as au
    au.save_options({**au.options(), "sched_set": True, "sched_time": "05:15",
                     "sched_days": ["MON", "WED"]})
    au.save_move_options({**au.move_options_saved(), "scheduled": True, "sched_time": "06:30",
                          "sched_days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]})
    try:
        rows = {r["name"]: r for r in tasks_health.rows()}
        a, m = rows[au.ASSIGN_TASK["name"]], rows[au.MOVE_TASK["name"]]
        assert (a["freq"], a["days"], a["time"]) == ("weekly", "MON,WED", "05:15")
        assert (m["freq"], m["time"]) == ("daily", "06:30")
        assert a["args"] == ["--task", "deviceassign"]
    finally:
        au.save_options({**au.options(), "sched_set": False})
        au.save_move_options({**au.move_options_saved(), "scheduled": False})
