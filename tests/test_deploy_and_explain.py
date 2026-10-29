import json

from gambit import deploy
from gambit.settings import settings


def test_deploy_fill_only_empty(tmp_path):
    settings.set("safety/threshold", 25)
    settings.set("alerts/email", "")
    f = tmp_path / "gambit-deploy.json"
    data = {"gambit_deploy": 1, "created": "2026-01-01T00:00:00", "overwrite": False,
            "settings": {"safety/threshold": 5, "alerts/email": "t@s.org"}}
    f.write_text(json.dumps(data))
    assert deploy.apply_file(str(f)) == []          # unsigned, from a shared place
    from gambit import seal
    f.write_text(json.dumps(seal.sign("deploy", {**data, "created": "2026-01-02T00:00:00"})))
    changed = deploy.apply_file(str(f))
    assert changed == ["alerts/email"]
    assert int(settings.get("safety/threshold")) == 25
    assert deploy.apply_file(str(f)) == []            # only once per file version


def test_backup_restore(tmp_path):
    settings.set("schedule/out", "C:/Reports")
    z = deploy.backup(str(tmp_path / "b.zip"))
    settings.set("schedule/out", "")
    n, _f = deploy.restore(z)
    assert n >= 1 and settings.get("schedule/out") == "C:/Reports"


def test_explain_matches_reference():
    from gambit.command_catalog import Catalog
    from gambit.explain import best_match
    cat = Catalog()
    c = best_match(["user", "a@b.org", "vacation", "on"], cat)
    assert "vacation" in c.syntax
