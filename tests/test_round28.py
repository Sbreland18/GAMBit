"""Round 28: the access list follows when the team folder is set after sign-in was on."""

import json
import os

import pytest

from gambit.auth import access
from gambit.settings import settings


@pytest.fixture
def env(tmp_path, monkeypatch):
    settings.set("team/folder", "")
    settings.set("access/pinned", "")
    monkeypatch.setattr(access, "_app_dir", lambda: str(tmp_path / "app"))
    yield tmp_path
    settings.set("team/folder", "")
    settings.set("access/pinned", "")


def test_list_moves_to_the_new_team_folder(env):
    access.new_list("boss@d.org", "d.org", "cid", "sec")      # no team folder yet
    old = access.path()
    assert old.startswith(str(env / "app"))
    team = env / "server" / "GAMbit Team Folder"
    team.mkdir(parents=True)
    settings.set("team/folder", str(team))
    assert not access.exists()
    doc = access.load()                                        # copied, still trusted
    assert doc["people"]["boss@d.org"]["role"] == "Full admin"
    assert access.path() == str(team / "access" / "access.json") and access.exists()
    assert os.path.isfile(old)                                 # the old copy stays


def test_forged_copy_isnt_adopted(env):
    access.new_list("boss@d.org", "d.org", "cid", "sec")
    p = access.path()
    e = json.load(open(p))
    e["doc"]["people"]["evil@d.org"] = {"role": "Full admin"}
    json.dump(e, open(p, "w"))
    settings.set("team/folder", str(env / "t"))
    with pytest.raises(access.AccessError, match="last read it from"):
        access.load()
    assert not access.exists()
