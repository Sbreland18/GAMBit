"""Chromebook fleet → Assigned users: blank the field, or set it to the last signed-in user."""

import datetime

from gambit.helper import verify
from gambit.tools import assigned_users as au

ROWS = [  # print cros CSV, as GAM writes it with recentusers listlimit 1
    {"deviceId": "d1", "serialNumber": "S1", "annotatedUser": "", "orgUnitPath": "/Chromebooks",
     "recentUsers.0.email": "kid1@hancockschools.net", "recentUsers.0.type": "USER_TYPE_MANAGED",
     "lastSync": "2026-10-10T08:00:00.000Z"},
    {"deviceId": "d2", "serialNumber": "S2", "annotatedUser": "old@hancockschools.net",
     "recentUsers.0.email": "kid2@hancockschools.net", "lastSync": "2026-10-11T08:00:00Z"},
    {"deviceId": "d3", "serialNumber": "S3", "annotatedUser": "teacher@hancockschools.net",
     "recentUsers.0.email": "teacher@hancockschools.net", "lastSync": "2026-10-11T08:00:00Z"},
    {"deviceId": "d4", "serialNumber": "S4", "annotatedUser": "", "lastSync": "2026-10-11"},
    {"deviceId": "d5", "serialNumber": "S5", "annotatedUser": "",
     "recentUsers.0.email": "tech1@hancockschools.net", "lastSync": "2026-10-11"},
    {"deviceId": "d6", "serialNumber": "S6", "annotatedUser": "",
     "recentUsers.0.email": "staffer@hancockschools.net", "lastSync": "2026-10-11"},
    {"deviceId": "d7", "serialNumber": "S7", "annotatedUser": "",
     "recentUsers.0.email": "kid3@hancockschools.net", "lastSync": "2025-01-01"},
    {"deviceId": "d8", "serialNumber": "S8", "annotatedUser": "",
     "recentUsers.0.email": "visitor@gmail.com", "lastSync": "2026-10-11"},
]
USERS = [{"email": f"kid{i}@hancockschools.net", "ou": "/Students/HS"} for i in (1, 2, 3)] + \
    [{"email": e, "ou": "/Staff"} for e in ("teacher@hancockschools.net", "tech1@hancockschools.net",
                                            "staffer@hancockschools.net")]
TODAY = datetime.date(2026, 10, 19)


def plan(**o):
    opts = {**au.options(), "blank_only": False, "students_only": True, "ignore": "tech*",
            "max_days": 0, **o}
    return {r["deviceId"]: r for r in au.plan_set(au.devices(ROWS), USERS, ["/Students"], opts,
                                                   TODAY)}


def test_devices_reads_last_user():
    d = au.devices(ROWS + ROWS[:1])
    assert len(d) == 8 and d[0]["last"] == "kid1@hancockschools.net"
    assert d[0]["last_sync"] == "2026-10-10 08:00:00"


def test_plan_filters():
    p = plan()
    assert p["d1"]["plan"] == "Set" and "blank" in p["d1"]["why"]
    assert p["d2"]["plan"] == "Set" and "replaces" in p["d2"]["why"]
    assert p["d3"]["plan"] == "Same"
    assert p["d4"]["plan"] == "Skip"                       # nobody signed in
    assert p["d5"]["plan"] == "Skip" and "ignore" in p["d5"]["why"]
    assert p["d6"]["plan"] == "Skip" and "student" in p["d6"]["why"]
    assert p["d8"]["plan"] == "Skip" and "district" in p["d8"]["why"]
    assert plan(blank_only=True)["d2"]["plan"] == "Skip"
    assert plan(max_days=30)["d7"]["plan"] == "Skip"
    assert plan(students_only=False)["d6"]["plan"] == "Set"


def test_commands_are_valid_gam():
    rows = list(plan().values())
    sets = au.set_steps(rows)
    assert [a for _l, a in sets] == [["cros", "d1", "update", "user", "kid1@hancockschools.net"],
                                     ["cros", "d2", "update", "user", "kid2@hancockschools.net"],
                                     ["cros", "d7", "update", "user", "kid3@hancockschools.net"]]
    clears = au.clear_steps(rows)
    assert clears[0][1] == ["cros", "d2,d3", "update", "user", ""]
    for _l, a in sets + clears:
        assert verify.check(a)[0], a
    for scope, vals in (("all", []), ("ou", ["/Chromebooks"]), ("serial", ["S1", "S2"]),
                        ("asset", ["HS0116", "HS0189"])):
        for a in au.load_args(scope, vals):
            assert verify.check(a)[0], a
            assert "recentusers" in " ".join(a)


def test_clear_batches_large_fleets():
    rows = [{"deviceId": f"d{i}", "assigned": "x@y"} for i in range(450)]
    steps = au.clear_steps(rows)
    assert len(steps) == 3 and steps[0][1][1].count(",") == au.BATCH - 1


def test_backup_and_undo(tmp_path, monkeypatch):
    monkeypatch.setattr(au, "backup_dir", lambda: str(tmp_path))
    devs = au.devices(ROWS)
    au.backup(devs, "clear")
    steps = au.undo_steps(au.latest_backup())
    back = {a[4]: a[1].split(",") for _l, a in steps}
    assert back[""] == ["d1", "d4", "d5", "d6", "d7", "d8"]
    assert back["old@hancockschools.net"] == ["d2"]
    for _l, a in steps:
        assert verify.check(a)[0]


def test_tab_builds_and_previews(qapp):
    from PySide6.QtWidgets import QWidget

    from gambit.ui.pages.round19_tabs import AssignedUsersTab

    from PySide6.QtCore import QObject, Signal

    class Dir(QObject):
        ous_changed = Signal()
        users, ous = USERS, ["/", "/Students", "/Chromebooks"]

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
            self.last = t

    t = AssignedUsersTab(P())
    t.devs = au.devices(ROWS)
    t.students.setChecked(True)
    t.preview()
    assert t.table.row_count() == 8
    assert "would be set" in t.status.text()
    t.devs = au.devices(MOVE_ROWS)
    t.directory.users = MOVE_USERS
    t.preview_move()
    assert t.table.row_count() == 7 and "would move" in t.status.text()
    assert "/Chromebooks/Hancock High School" in t.m_example.text()


# ------------------------------------------------- move to the student's school ---
MOVE_ROWS = [
    {"deviceId": "m1", "serialNumber": "M1", "orgUnitPath": "/Chromebooks", "status": "ACTIVE",
     "recentUsers.0.email": "ninth@hancockschools.net", "lastSync": "2026-10-18"},
    {"deviceId": "m2", "serialNumber": "M2", "orgUnitPath": "/Chromebooks/Hancock High School",
     "status": "ACTIVE", "recentUsers.0.email": "ninth@hancockschools.net",
     "lastSync": "2026-10-18"},
    {"deviceId": "m3", "serialNumber": "M3", "orgUnitPath": "/Chromebooks/Loaners",
     "status": "ACTIVE", "recentUsers.0.email": "ninth@hancockschools.net",
     "lastSync": "2026-10-18"},
    {"deviceId": "m4", "serialNumber": "M4", "orgUnitPath": "/Chromebooks", "status": "DISABLED",
     "recentUsers.0.email": "ninth@hancockschools.net", "lastSync": "2026-10-18"},
    {"deviceId": "m5", "serialNumber": "M5", "orgUnitPath": "/Chromebooks", "status": "ACTIVE",
     "recentUsers.0.email": "teach@hancockschools.net", "lastSync": "2026-10-18"},
    {"deviceId": "m6", "serialNumber": "M6", "orgUnitPath": "/Chromebooks", "status": "ACTIVE",
     "recentUsers.0.email": "mid@hancockschools.net", "lastSync": "2026-10-18"},
    {"deviceId": "m7", "serialNumber": "M7", "orgUnitPath": "/", "status": "ACTIVE",
     "recentUsers.0.email": "ninth@hancockschools.net", "lastSync": "2026-10-18"},
]
MOVE_USERS = [{"email": "ninth@hancockschools.net", "ou": "/Students/Hancock High School/9th Grade"},
              {"email": "mid@hancockschools.net", "ou": "/Students/Hancock Middle/6th Grade"},
              {"email": "teach@hancockschools.net", "ou": "/Staff/Hancock High School"}]
OUS = ["/", "/Chromebooks", "/Chromebooks/Hancock High School", "/Chromebooks/Loaners"]
MOPTS = {"who": "last", "student_root": "/Students", "school_depth": 1,
         "ou_template": "/Chromebooks/{school}", "skip_ous": "/Chromebooks/Loaners",
         "only_active": True, "max_days": 0, "ignore": ""}


def test_target_for_the_example_in_the_question():
    o = {**MOPTS, "student_root": "Students", "ou_template": "Chromebooks\\{school}"}
    assert au.target_for("Students\\Hancock High School\\9th Grade", o) == \
        "/Chromebooks/Hancock High School"
    assert au.target_for("/Staff/Hancock High School", MOPTS) == ""
    assert au.target_for("/Students/Hancock High School/9th Grade",
                         {**MOPTS, "school_depth": 2}) == \
        "/Chromebooks/Hancock High School/9th Grade"


def test_plan_move():
    p = {r["deviceId"]: r for r in au.plan_move(au.devices(MOVE_ROWS), MOVE_USERS, MOPTS, OUS,
                                                TODAY)}
    assert p["m1"]["plan"] == "Move" and p["m1"]["target"] == "/Chromebooks/Hancock High School"
    assert p["m2"]["plan"] == "Same"
    assert p["m3"]["plan"] == "Skip" and "don't-move" in p["m3"]["why"]
    assert p["m4"]["plan"] == "Skip" and "disabled" in p["m4"]["why"]
    assert p["m5"]["plan"] == "Skip" and "isn't a student" in p["m5"]["why"]
    assert p["m6"]["plan"] == "Skip" and "doesn't exist" in p["m6"]["why"]
    assert p["m7"]["plan"] == "Move"
    steps = au.move_steps(list(p.values()))
    assert steps == [("Move 2 Chromebook(s) to /Chromebooks/Hancock High School",
                      ["cros", "m1,m7", "update", "ou", "/Chromebooks/Hancock High School"])]
    assert verify.check(steps[0][1])[0]


def test_move_undo_restores_org_units(tmp_path, monkeypatch):
    monkeypatch.setattr(au, "backup_dir", lambda: str(tmp_path))
    devs = au.devices(MOVE_ROWS)
    path = au.backup([d for d in devs if d["deviceId"] in ("m1", "m7")], "move")
    steps = au.undo_steps(path)
    assert sorted(a[4] for _l, a in steps) == ["/", "/Chromebooks"]
    assert all(a[3] == "ou" and verify.check(a)[0] for _l, a in steps)


def test_move_task(tmp_path, monkeypatch):
    monkeypatch.setattr(au, "backup_dir", lambda: str(tmp_path))
    au.save_move_options(MOPTS)
    ran = []
    code = au.run_move_task(log=lambda m: ran.append(m),
                            run_csv=lambda a: (0, MOVE_ROWS, ""),
                            run_text=lambda a, t=0: (ran.append(a), (0, ""))[1],
                            users=MOVE_USERS, ous=OUS)
    assert code == 0
    assert ["cros", "m1,m7", "update", "ou", "/Chromebooks/Hancock High School"] in ran
    assert au.latest_backup().endswith("-move.csv")


# ------------------------------------------- blank unused + the morning run ---
STALE_ROWS = [
    {"deviceId": "s1", "serialNumber": "S1", "annotatedUser": "kid1@hancockschools.net",
     "orgUnitPath": "/Chromebooks", "activeTimeRanges.0.date": "2026-07-01",
     "recentUsers.0.email": "kid1@hancockschools.net", "lastSync": "2026-10-18"},
    {"deviceId": "s2", "serialNumber": "S2", "annotatedUser": "kid2@hancockschools.net",
     "orgUnitPath": "/Chromebooks", "activeTimeRanges.0.date": "2026-10-15",
     "recentUsers.0.email": "kid2@hancockschools.net", "lastSync": "2026-10-18"},
    {"deviceId": "s3", "serialNumber": "S3", "annotatedUser": "kid3@hancockschools.net",
     "orgUnitPath": "/Chromebooks"},
    {"deviceId": "s4", "serialNumber": "S4", "annotatedUser": "", "orgUnitPath": "/Chromebooks",
     "activeTimeRanges.0.date": "2026-01-01"},
    {"deviceId": "s5", "serialNumber": "S5", "annotatedUser": "tech1@hancockschools.net",
     "orgUnitPath": "/Chromebooks", "activeTimeRanges.0.date": "2026-01-01"},
]


def test_plan_stale():
    p = {r["deviceId"]: r for r in au.plan_stale(au.devices(STALE_ROWS), 60,
                                                 {"ignore": "tech*"}, TODAY)}
    assert p["s1"]["plan"] == "Blank" and "110 days" in p["s1"]["why"]
    assert p["s2"]["plan"] == "Same"
    assert p["s3"]["plan"] == "Skip"                     # no usage date
    assert p["s4"]["plan"] == "Same"                     # already blank
    assert p["s5"]["plan"] == "Skip"                     # ignore list
    assert au.plan_stale(au.devices(STALE_ROWS), 60, {"stale_never": True},
                         TODAY)[2]["plan"] == "Blank"
    steps = au.stale_steps(list(p.values()))
    assert steps[0][1] == ["cros", "s1", "update", "user", ""]


def test_set_skips_what_would_be_blanked():
    users = [{"email": "kid1@hancockschools.net", "ou": "/Students/HS"}]
    devs = [{**d, "assigned": ""} for d in au.devices(STALE_ROWS[:1])]
    o = {**au.options(), "stale_on": True, "stale_days": 60}
    assert au.plan_set(devs, users, ["/Students"], o, TODAY)[0]["plan"] == "Skip"
    o["stale_on"] = False
    assert au.plan_set(devs, users, ["/Students"], o, TODAY)[0]["plan"] == "Set"


def test_morning_task(tmp_path, monkeypatch):
    monkeypatch.setattr(au, "backup_dir", lambda: str(tmp_path))
    rows = [dict(r) for r in STALE_ROWS] + [
        {"deviceId": "s6", "serialNumber": "S6", "annotatedUser": "", "orgUnitPath": "/Chromebooks",
         "activeTimeRanges.0.date": datetime.date.today().isoformat(),
         "recentUsers.0.email": "kid6@hancockschools.net"}]
    users = [{"email": f"kid{i}@hancockschools.net", "ou": "/Students/HS"} for i in range(1, 7)]
    au.save_options({**au.options(), "sched_stale": True, "sched_set": True, "stale_days": 60,
                     "blank_only": True, "students_only": True, "ignore": "tech*"})
    ran = []
    code = au.run_assign_task(log=ran.append, run_csv=lambda a: (0, rows, ""),
                              run_text=lambda a, t=0: (ran.append(a), (0, ""))[1], users=users)
    assert code == 0
    assert ["cros", "s1", "update", "user", ""] in ran                      # blanked
    assert ["cros", "s6", "update", "user", "kid6@hancockschools.net"] in ran  # set
    assert not any(a[:2] == ["cros", "s1"] and a[-1] for a in ran if isinstance(a, list))
    assert len([f for f in tmp_path.iterdir()]) == 2                       # two backups
    au.save_options({**au.options(), "sched_stale": False, "sched_set": False})
    assert au.run_assign_task(log=ran.append, run_csv=lambda a: (0, rows, "")) == 0
