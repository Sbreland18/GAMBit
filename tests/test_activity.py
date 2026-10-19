from gambit import activity

USERS = [{"email": "a@school.org", "ou": "/Staff", "suspended": False},
         {"email": "b@school.org", "ou": "/Students/G5", "suspended": False},
         {"email": "c@school.org", "ou": "/Students/G5/X", "suspended": True}]


def test_is_change():
    assert not activity.is_change(["print", "users"])
    assert activity.is_change(["update", "user", "a@school.org", "suspended", "on"])
    assert not activity.is_change(["user", "a@school.org", "print", "groups"])


def test_mask():
    assert activity.mask(["update", "user", "x", "password", "secret"])[-1] == "********"


def test_infer_undo_suspend_and_ou():
    u = activity.infer_undo(["update", "user", "a@school.org", "suspended", "on",
                             "ou", "/Former"], USERS)
    assert u["args"] == ["update", "user", "a@school.org", "suspended", "off", "ou", "/Staff"]


def test_infer_undo_misc():
    assert activity.infer_undo(["create", "user", "n@school.org"], USERS)["args"] == \
        ["delete", "user", "n@school.org"]
    assert activity.infer_undo(["update", "courses", "1,2", "state", "archived"],
                               USERS)["args"][-1] == "active"
    assert activity.infer_undo(["user", "a@school.org", "vacation", "on"],
                               USERS)["args"][-1] == "off"
    assert activity.infer_undo(["user", "a@school.org", "forward", "off"], USERS) is None


def test_capture_undo_group_roles():
    def run_csv(args):
        return 0, [{"email": "a@school.org", "role": "OWNER"},
                   {"email": "b@school.org", "role": "MEMBER"}], ""
    u = activity.capture_undo(["update", "group", "g@school.org", "remove", "member",
                               "a@school.org,b@school.org"], run_csv)
    assert ["update", "group", "g@school.org", "add", "owner", "a@school.org"] in u["steps"]
    assert ["update", "group", "g@school.org", "add", "member", "b@school.org"] in u["steps"]


def test_capture_undo_cros():
    def run_csv(args):
        return 0, [{"orgUnitPath": "/Carts", "annotatedUser": "kid@school.org"}], ""
    u = activity.capture_undo(["cros_sn", "SN1", "update", "ou", "/Lost", "user", ""], run_csv)
    assert u["steps"][0] == ["cros_sn", "SN1", "update", "ou", "/Carts", "user",
                             "kid@school.org"]


def test_affected_counts():
    n, sample = activity.affected(["ou_and_children", "/Students", "update", "user",
                                   "changepassword", "on"], USERS, [])
    assert n == 1 and sample == ["b@school.org"]          # suspended c is skipped
    assert activity.affected(["print", "users"], USERS, []) is None
