from gambit import team


def cats(cmd):
    return team.categorize(cmd.split())


def test_categories():
    assert cats("print users") == {"read"}
    assert cats("update user a@b password x changepassword on") == {"passwords"}
    assert cats("update user a@b suspended on") == {"suspend"}
    assert cats("delete user a@b") == {"delete"}
    assert "everyone" in cats("ou /Students update user changepassword on")
    assert cats("cros_sn 1 update ou /X") == {"chromebooks"}
    assert cats("update group g add member a@b") == {"groups"}
    assert cats("create user a@b firstname a lastname b password x") == {"passwords", "users"}


def test_role_check():
    office = team.BUILTIN_ROLES["Office manager"]
    ok, missing, ask = team.check("update user a@b suspended on".split(), office)
    assert not ok and missing == {"suspend"} and ask
    ok, _m, ask = team.check("cros_sn 1 update action disable".split(), office)
    assert not ok and not ask
    assert team.check("update group g add member a@b".split(), office)[0]


def test_requests_roundtrip(team_dir):
    req = team.new_request([["update", "user", "a@b", "suspended", "on"]], "left",
                           extra={"kind": "test"})
    assert team.pending_count() == 1
    team.update_request(req, "denied", note="no")
    assert team.list_requests("denied")[0]["kind"] == "test"
