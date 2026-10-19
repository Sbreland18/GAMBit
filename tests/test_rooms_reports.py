from gambit import parent_report, rooms, signature


def test_rooms_plan():
    rs = rooms.rooms_from_rows(rooms.read_rows(rooms.TEMPLATE))
    assert [r.rid for r in rs] == ["lincoln-elementary-library", "lincoln-elementary-room-204",
                                   "hs-cart-a"]
    b = [{"buildingId": "high-school", "buildingName": "High School", "floorNames": "2"}]
    r = [{"resourceId": "hs-cart-a", "resourceName": "Cart A", "capacity": "",
          "buildingId": "high-school", "floorName": "1"}]
    acts = rooms.plan(rs, b, r)
    kinds = [(a.action, a.target) for a in acts]
    assert kinds[0] == ("building", "Lincoln Elementary")
    assert acts[0].commands[0][:3] == ["create", "building", "Lincoln Elementary"]
    assert ("building", "High School") in kinds              # floor 1 is missing there
    upd = next(a for a in acts if a.action == "update")
    assert upd.commands[0][:3] == ["update", "resource", "hs-cart-a"] and "name" in upd.details
    new = next(a for a in acts if a.target == "lincoln-elementary-library")
    cmd = new.commands[0]
    assert cmd[cmd.index("category") + 1] == "conference_room"
    assert cmd[cmd.index("buildingid") + 1] == "lincoln-elementary"


def test_rooms_problems():
    rs = rooms.rooms_from_rows([{"Name": "A", "ID": "x"}, {"Name": "B", "ID": "X"},
                                {"Name": "C", "Floor": "2"}])
    acts = rooms.plan(rs, [], [])
    assert [a.action for a in acts] == ["create", "problem", "problem"]


STUDENTS = [{"email": "a@s.org", "name": "A", "ou": "/Students/Lincoln/Grade 3"},
            {"email": "b@s.org", "name": "B", "ou": "/Students/Lincoln/Grade 4"},
            {"email": "c@s.org", "name": "C", "ou": "/Students/High School/Grade 9"},
            {"email": "d@s.org", "name": "D", "ou": "/Students/High School"}]
CURRENT = [{"student": "a@s.org", "guardian": "mom@x.com", "kind": "guardian",
            "state": "COMPLETE", "since": ""},
           {"student": "c@s.org", "guardian": "dad@x.com", "kind": "invitation",
            "state": "PENDING", "since": "2026-09-01"}]


def test_parent_report_by_school():
    d = parent_report.details(STUDENTS, CURRENT, "/Students")
    s = {r["School"]: r for r in parent_report.summary(d)}
    assert s["Lincoln"]["Students"] == 2 and s["Lincoln"]["Connected"] == 1
    assert s["Lincoln"]["% connected"] == "50%"
    assert s["High School"]["Invited (waiting)"] == 1 and s["High School"]["Nobody invited"] == 1
    assert s["District total"]["Students"] == 4
    assert next(r for r in d if r["Email"] == "c@s.org")["Status"].startswith("Invited")
    assert parent_report.parse_principals("Lincoln = p@s.org; o@s.org\nbad line") == \
        {"lincoln": ["p@s.org", "o@s.org"]}


def test_signature_rollout(qapp):
    calls = []
    signature.save_rollout([["ou", "/Staff"]], True, "everyone in /Staff")
    bad = signature.run_rollout(log=lambda *_: None,
                                run_text=lambda a, t: (calls.append(a), (0, ""))[1])
    assert bad == 0 and calls[0][:3] == ["ou", "/Staff", "signature"]
    assert "replace" in calls[0]
    signature.save_rollout([], True, "")
    assert signature.rollout() == {}


def test_headless_tasks_accept_new_names(qapp, fake_gam):
    from gambit import headless
    assert headless.main(["--task", "signatures"]) == 0     # nothing saved → no-op
    assert headless.main(["--task", "guardians"]) == 0
