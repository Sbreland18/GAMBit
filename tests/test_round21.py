"""One Schedules page, serials in the activity log, and one Chromebook load for the fleet."""


import pytest

from gambit import activity, device_names, fleet_cache, scheduler, team

ROWS = [{"deviceId": "3716965a-d82a", "serialNumber": "5CD0372JK1", "annotatedAssetId": "HS2074",
         "orgUnitPath": "/Chrome Devices/HMS", "annotatedUser": "", "status": "ACTIVE",
         "recentUsers.0.email": "kid@x.org", "recentUsers.0.type": "USER_TYPE_MANAGED",
         "activeTimeRanges.0.date": "2026-10-19", "lastSync": "2026-10-19T08:00:00Z",
         "model": "Dell 3100", "osVersion": "128", "notes": "", "annotatedLocation": "Cart 3",
         "autoUpdateExpiration": "2027-06-01"},
        {"deviceId": "bbb", "serialNumber": "5CD999", "orgUnitPath": "/Chrome Devices/HHS",
         "status": "ACTIVE"}]


@pytest.fixture(autouse=True)
def fresh():
    fleet_cache.clear()
    yield
    fleet_cache.clear()


# ------------------------------------------------------------- fleet cache ---
def test_whole_fleet_reads_use_the_loaded_list():
    fleet_cache.store(ROWS)
    from gambit.asset_register import CROS_ARGS as AR
    from gambit.tools.automation import CROS_ARGS as AS
    from gambit.tools.assigned_users import load_args
    from gambit.tools.reconcile import COLLECT_ARGS
    for args in (AR, AS, COLLECT_ARGS, load_args("all", [])[0]):
        rows = fleet_cache.get(args)
        assert rows is not None and len(rows) == 2, args
    trimmed = fleet_cache.get(AS)[0]
    assert "model" not in {k.lower() for k in trimmed} and "deviceId" in trimmed
    # narrower reads still go to Google
    assert fleet_cache.get(["print", "cros", "query", "asset_id:HS1", "fields", "deviceid"]) is None
    assert fleet_cache.get(["print", "cros", "cros_ou", "/X", "fields", "deviceid"]) is None
    assert fleet_cache.get(["print", "cros", "fields", "cpustatusreports"]) is None


def test_changes_clear_the_list(monkeypatch):
    fleet_cache.store(ROWS)
    fleet_cache.changed("gam print cros fields deviceid")
    assert fleet_cache.all_rows()
    fleet_cache.changed('gam cros 3716965a-d82a update ou "/Chrome Devices/HHS"')
    assert not fleet_cache.all_rows()


def test_run_gam_csv_answers_from_the_list():
    from gambit.directory import run_gam_csv
    fleet_cache.store(ROWS)
    code, rows, _err = run_gam_csv(["print", "cros", "fields", "serialnumber,orgunitpath"])
    assert code == 0 and [r["serialNumber"] for r in rows] == ["5CD0372JK1", "5CD999"]


# ------------------------------------------------------------- activity log ---
def test_activity_log_says_what_was_done_with_serials():
    device_names.remember(ROWS)
    e = activity.record(["cros", "3716965a-d82a", "update", "ou",
                         "/Chrome Devices/Hancock North Central Elementary School"], 0, "done",
                        None, "Default")
    assert e["what"] == ("Chromebook 5CD0372JK1 (asset HS2074): moved to /Chrome Devices/"
                         "Hancock North Central Elementary School")
    assert "[5CD0372JK1]" in e["command_named"] and "3716965a-d82a" in e["command"]
    assert e["devices"] == ["5CD0372JK1 (asset HS2074)"]
    assert e["args"][1] == "3716965a-d82a"                      # undo/run again unchanged
    many = activity.describe(["cros", "3716965a-d82a,bbb,unknown-id", "update", "user", ""])
    assert many.startswith("3 Chromebooks (5CD0372JK1 (asset HS2074), 5CD999, unknown-id)")
    assert many.endswith("assigned user blanked")


@pytest.mark.parametrize("args,want", [
    (["update", "user", "jdoe@x.org", "suspended", "on"], "Suspended jdoe@x.org"),
    (["update", "user", "jdoe@x.org", "password", "x", "changepassword", "on"],
     "Reset jdoe@x.org's password"),
    (["update", "group", "staff@x.org", "add", "member", "users", "a@x.org"],
     "Added a@x.org to staff@x.org"),
    (["user", "jdoe@x.org", "signout"], "Signed jdoe@x.org out everywhere"),
    (["cros_sn", "5CD1", "update", "action", "disable"], "Chromebook 5CD1: disabled"),
    (["select", "hs", "cros", "bbb", "update", "assetid", "HS9"],
     "Chromebook 5CD999: asset ID set to HS9"),
])
def test_plain_english(args, want):
    device_names.remember(ROWS)
    assert activity.describe_any(args) == want


def test_activity_page_shows_what_was_done(qapp):
    device_names.remember(ROWS)
    from gambit.ui.pages.activity_page import _what
    what, named, devs = _what({"id": "x", "args": ["cros", "3716965a-d82a", "update", "ou",
                                                    "/CD/HHS"], "command": "gam cros …"})
    assert what.startswith("Chromebook 5CD0372JK1") and "[5CD0372JK1]" in named
    assert devs == ["5CD0372JK1 (asset HS2074)"]


# ---------------------------------------------------------------- schedules ---
def test_task_args_read_from_the_cmd_script(tmp_path):
    cmd = tmp_path / "x.cmd"
    cmd.write_text('@echo off\nstart "" /wait "C:\\GAMbit\\GAMbit.exe" --task job --name '
                   'a1b2c3\nexit /b %errorlevel%\n', encoding="utf-8")
    assert scheduler.task_args(str(cmd)) == ["--task", "job", "--name", "a1b2c3"]
    assert scheduler.task_args("C:\\gam.exe", "print users") == []
    assert scheduler.task_args("x.exe", '--task sync --name "HS Students"') == \
        ["--task", "sync", "--name", "HS Students"]


def test_old_roles_still_see_the_combined_page():
    role = {"pages": ["Background tasks", "Users"]}
    assert team.page_allowed("Schedules", role)
    assert not team.page_allowed("Schedules", {"pages": ["Users"]})


def test_one_schedules_page_with_three_tabs(qapp, fake_gam):
    from gambit.settings import settings
    settings.set("tour/seen", True)
    from gambit.ui.main_window import NAV, MainWindow
    names = {i[0] for i in NAV if not isinstance(i, str)}
    assert "Schedules" in names and "Background tasks" not in names and \
        "Scheduled jobs" not in names
    w = MainWindow()
    s = w.pages["Schedules"]
    assert [s.tabs.tabText(i).replace("&&", "&") for i in range(s.tabs.count())] == \
        ["All schedules", "Report & command jobs", "Setup & health"]
    w.go("Background tasks")                              # old links still work
    assert w._current_page_name == "Schedules" and s.tabs.currentIndex() == 2
    w.go("Scheduled jobs")
    assert s.tabs.currentIndex() == 1
    assert w.pages["Scheduled jobs"] is s.jobs_page        # e.g. Command Builder → prefill
    w.close()


def test_orphaned_saved_job_task_is_listed(monkeypatch, tmp_path):
    from gambit import saved_jobs, tasks_health
    saved_jobs._save_all([])
    monkeypatch.setattr(scheduler, "list_tasks", lambda: [
        {"Name": "GAMbit job - Assigned users", "Status": "Ready", "Next run": "",
         "Last run": "", "Last result": "0", "Schedule": "Weekly", "time": "05:45",
         "days": ["MON"], "task_args": ["--task", "job", "--name", "zz9"]}])
    rows = {r["name"]: r for r in tasks_health.rows()}
    r = rows["GAMbit job - Assigned users"]
    assert r["scheduled"] and r["orphan_job"] == "zz9"
    j = saved_jobs.adopt({"id": "zz9", "kind": "assigned", "name": "Assigned users",
                          "enabled": True, "time": "05:45", "days": ["MON"],
                          "scope_ous": [], "opts": {}})
    assert saved_jobs.get("zz9")["name"] == "Assigned users" and j["opts"]["sched_set"]
    saved_jobs._save_all([])


def test_fleet_tab_fills_assigned_users(qapp):
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QWidget

    from gambit.ui.pages.round19_tabs import AssignedUsersTab

    class Dir(QObject):
        ous_changed = Signal()
        users, ous = [{"email": "kid@x.org", "ou": "/Students/HMS"}], ["/"]

        def refresh_users(self):
            pass

    class P(QWidget):
        directory = Dir()

        def row(self, *w, stretch=True):
            from PySide6.QtWidgets import QHBoxLayout
            h = QHBoxLayout()
            for x in w:
                h.addWidget(x)
            return h

        def info(self, t):
            pass
    t = AssignedUsersTab(P())
    fleet_cache.store(ROWS)
    t.on_fleet_loaded()
    assert len(t.devs) == 2 and t.table.row_count() == 2
    assert "loaded at the top" in t.status.text()
    t.scope.setCurrentIndex(t.scope.findData("ou"))
    t.ous.set_paths(["/Chrome Devices/HHS"])
    t.load()
    assert [d["serial"] for d in t.devs] == ["5CD999"]       # filtered without Google
