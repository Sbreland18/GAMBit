from gambit import offboard


def pw(n=20):
    return "x" * n


BEFORE = {"groups": [["staff@school.org", "member"], ["science@school.org", "owner"]],
          "licenses": ["1010310008"], "ou": "/Staff", "name": "Kim White", "gal": True}


def test_build_stages_and_undo(team_dir):
    rec = offboard.build("kwhite@school.org", "jdoe@school.org", BEFORE,
                         offboard.DEFAULTS, pw)
    keys = [s["key"] for s in rec["stages"]]
    assert keys == ["today", "later", "delete"]
    today = [s["args"] for s in rec["stages"][0]["steps"]]
    assert ["create", "datatransfer", "kwhite@school.org", "drive,calendar",
            "jdoe@school.org", "all", "release_resources"] in today
    assert ["update", "group", "science@school.org", "remove", "kwhite@school.org"] in today
    later = [s["args"] for s in rec["stages"][1]["steps"]]
    assert ["user", "kwhite@school.org", "delete", "license", "1010310008"] in later
    assert rec["stages"][2]["auto"] is False
    offboard.save(rec)
    offboard.mark(rec, "today", {s["id"]: 0 for s in rec["stages"][0]["steps"]})
    undo = [s["args"] for s in offboard.undo_steps(offboard.get("kwhite@school.org"))]
    assert ["update", "group", "science@school.org", "add", "owner", "kwhite@school.org"] in undo
    assert ["update", "user", "kwhite@school.org", "ou", "/Staff"] in undo
    assert "Change password" in offboard.cannot_undo(rec)


def test_no_supervisor_skips_mail_steps():
    rec = offboard.build("a@school.org", "", BEFORE, offboard.DEFAULTS, pw)
    flat = [a for st in rec["stages"] for s in st["steps"] for a in s["args"]]
    assert "datatransfer" not in flat and "delegate" not in flat
    assert rec["notes"]


def test_graduate():
    rec = offboard.build_graduate("s@school.org", {"ou": "/Students/G12", "groups": [],
                                                   "licenses": []},
                                  offboard.GRAD_DEFAULTS, 2027)
    first = rec["stages"][0]["steps"][0]["args"]
    assert first == ["update", "user", "s@school.org", "ou", "/Alumni/Class of 2027"]
    assert rec["kind"] == "graduate"
