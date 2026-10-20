"""Safe self-updates, the full Schedules list, and Home → Background jobs."""

import datetime
import json
import os

from gambit import saved_jobs as sj
from gambit import scheduler, tasks_health, updaters

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------------ updates ---
def test_installer_never_deletes_the_app_before_copying():
    iss = open(os.path.join(ROOT, "installer", "GAMbit.iss"), encoding="utf-8").read()
    head = iss.split("[Code]")[0]
    assert "Type: filesandordirs; Name: \"{app}\\_internal\"" not in head
    assert "taskkill.exe" in iss and "/IM GAMbit.exe" in iss          # background tasks too
    assert "RenameFile(App + '\\_internal', App + '\\_internal.old')" in iss
    assert "procedure DeinitializeSetup" in iss and "not InstallOk" in iss   # roll back


def test_update_keeps_the_install_type(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    exe = tmp_path / "Local" / "Programs" / "GAMbit" / "GAMbit.exe"
    assert updaters.install_scope_flag(str(exe)) == "/CURRENTUSER"
    assert updaters.install_scope_flag("/opt/Program Files/GAMbit/GAMbit.exe") == "/ALLUSERS"


def test_background_tasks_wait_while_updating():
    from gambit import headless
    from gambit.settings import settings
    import time
    settings.set("update/in_progress", time.time())
    try:
        assert headless.main(["--task", "job", "--name", "nope"]) == 0
        runs = [r for r in tasks_health.runs_since(datetime.datetime.now() -
                                                   datetime.timedelta(minutes=1))
                if r["key"] == "job:nope"]
        assert runs and runs[0]["skipped"]
    finally:
        settings.set("update/in_progress", 0)


# ---------------------------------------------------------------- schedules ---
def test_task_list_reads_powershell_json(monkeypatch):
    monkeypatch.setattr(scheduler, "IS_WINDOWS", True)
    data = [{"Name": "GAMbit job - Move – HS", "State": "Ready", "Last": "", "Next":
             "2026-10-21 05:15", "Result": "267011", "Start": "2026-10-01T05:15:00",
             "Days": 62, "Kind": "MSFT_TaskWeeklyTrigger"},
            {"Name": "GAMbit daily follow-ups", "State": "Disabled", "Last": "2026-10-20 06:15",
             "Next": "", "Result": "0", "Start": "2026-01-01T06:15:00", "Days": 0,
             "Kind": "MSFT_TaskDailyTrigger"}]
    seen = []
    monkeypatch.setattr(scheduler, "_run", lambda a: (seen.append(a),
                                                      (0, "﻿" + json.dumps(data)))[1])
    t = scheduler.list_tasks()
    assert seen[0][0] == "powershell" and "-TaskPath '\\GAMbit\\'" in seen[0][-1]
    assert t[0]["Name"] == "GAMbit job - Move – HS"            # the dash survives
    assert t[0]["days"] == ["MON", "TUE", "WED", "THU", "FRI"] and t[0]["time"] == "05:15"
    assert t[1]["Status"] == "Disabled" and t[1]["Schedule"] == "Daily"


def test_task_list_fallback_only_asks_for_gambits_folder(monkeypatch):
    monkeypatch.setattr(scheduler, "IS_WINDOWS", True)
    calls = []
    csv_out = ('"HostName","TaskName","Next Run Time","Status","Last Run Time","Last Result",'
               '"Schedule Type"\n"PC","\\GAMbit\\GAMbit job - A","x","Ready","y","0","Daily"\n'
               'ERROR: Access is denied.\n')

    def run(a):
        calls.append(a)
        return (1, "boom") if a[0] == "powershell" else (1, csv_out)
    monkeypatch.setattr(scheduler, "_run", run)
    t = scheduler.list_tasks()
    assert calls[1][:4] == ["schtasks", "/Query", "/TN", "\\GAMbit\\"]
    assert [x["Name"] for x in t] == ["GAMbit job - A"]        # partial output still used


# ------------------------------------------------------- Home → background jobs ---
def test_runs_are_recorded_and_labelled(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks_health, "_runs_path", lambda: str(tmp_path / "runs.jsonl"))
    monkeypatch.setattr(tasks_health, "log_summary", lambda: {
        "daily": {"failed": False, "lines": ["Starting", "3 follow-ups done"]},
        "job:abc": {"failed": True, "lines": ["Starting", "FAILED: no GAM"]}})
    sj._save_all([{"id": "abc", "kind": "move", "name": "Move HS", "enabled": True,
                   "time": "05:00", "days": [], "scope_ous": [], "opts": {}}])
    try:
        tasks_health.record_run("daily", "2026-10-20T06:15:00", 0)
        tasks_health.record_run("job:abc", "2026-10-20T05:00:00", 1)
        runs = tasks_health.runs_since(datetime.datetime.now() - datetime.timedelta(hours=1))
        by = {r["key"]: r for r in runs}
        assert by["daily"]["ok"] and by["daily"]["summary"] == "3 follow-ups done"
        assert not by["job:abc"]["ok"] and by["job:abc"]["summary"] == "FAILED: no GAM"
        assert tasks_health.label_for("job:abc") == "Move HS"
        assert tasks_health.label_for("sync:Students") == "Roster sync – Students"
        assert tasks_health.label_for("daily") == "Daily follow-ups"
    finally:
        sj._save_all([])


def test_missed_saved_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks_health, "_runs_path", lambda: str(tmp_path / "runs.jsonl"))
    now = datetime.datetime(2026, 10, 20, 9, 0)
    sj._save_all([{"id": "m1", "kind": "move", "name": "Move HS", "enabled": True,
                   "time": "05:00", "days": ["TUE"], "scope_ous": [], "opts": {},
                   "created": "2026-10-01T00:00:00"},
                  {"id": "m2", "kind": "move", "name": "Weekend", "enabled": True,
                   "time": "05:00", "days": ["SAT"], "scope_ous": [], "opts": {}},
                  {"id": "m3", "kind": "move", "name": "Off", "enabled": False,
                   "time": "05:00", "days": [], "scope_ous": [], "opts": {}}])
    try:
        missed = tasks_health.missed_jobs(datetime.datetime(2026, 10, 19, 15, 0), now)
        assert [m["name"] for m in missed] == ["Move HS"]      # Tue 20 Oct 05:00
    finally:
        sj._save_all([])


def test_home_jobs_box(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(tasks_health, "_runs_path", lambda: str(tmp_path / "runs.jsonl"))
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with open(tmp_path / "runs.jsonl", "w", encoding="utf-8") as fh:
        for key, ok in (("daily", True), ("groups", False)):
            fh.write(json.dumps({"key": key, "started": now, "ended": now, "code": 0 if ok
                                 else 1, "ok": ok, "skipped": False,
                                 "summary": "fine" if ok else "FAILED: x"}) + "\n")
    from gambit.ui.jobs_box import JobsBox

    class P:
        app = None
    box = JobsBox(P())
    assert box.table.rowCount() == 2
    assert box.table.item(0, 0).text() == "✖"                 # failures first
    assert "1 succeeded" in box.summary.text() and "1 failed" in box.summary.text()
