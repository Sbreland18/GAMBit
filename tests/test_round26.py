"""Round 26: "0 failed" isn't a failure; pages are built on demand; start-up screen."""

import datetime
import json

from gambit import tasks_health


def test_zero_failed_is_not_a_failure():
    f = tasks_health._looks_failed
    assert not f("Chromebook moves: 4 device(s) moved in 3 command(s), 0 failed.")
    assert not f("failed: 0") and not f("No failed steps")
    assert f("2 failed") and f("Failed: GAM said no") and f("FAILED: x")


def test_old_runs_with_zero_failed_read_as_ok(monkeypatch, tmp_path):
    p = tmp_path / "runs.jsonl"
    now = datetime.datetime.now().isoformat(timespec="seconds")
    p.write_text(json.dumps({"key": "job:x", "started": now, "ended": now, "code": 0,
                             "ok": False, "summary": "moved 4, 0 failed."}) + "\n" +
                 json.dumps({"key": "job:y", "started": now, "ended": now, "code": 1,
                             "ok": False, "summary": "moved 4, 0 failed."}) + "\n")
    monkeypatch.setattr(tasks_health, "_runs_path", lambda: str(p))
    runs = {r["key"]: r for r in tasks_health.runs_since(datetime.datetime.now() -
                                                          datetime.timedelta(hours=1))}
    assert runs["job:x"]["ok"] and not runs["job:y"]["ok"]


def test_pages_build_on_demand(qapp, fake_gam):
    from gambit.settings import settings
    settings.set("tour/seen", True)
    settings.set("setup/seen", True)
    from gambit.ui.main_window import PAGES, MainWindow
    w = MainWindow()
    assert w.pages.built("Home") and not w.pages.built("Device history")
    assert "Device history" in w.pages and len(w.pages) == len(PAGES)
    w.go("Device history")
    assert w.pages.built("Device history")
    assert w.current_page() is w.pages["Device history"]
    assert w.pages.get("Nope") is None
    w.close()


def test_splash_draws(qapp):
    from gambit.ui.splash import Splash
    s = Splash("9.9.9")
    s.step("Loading GAMbit…", 50)
    assert not s.pixmap().isNull() and s.msg == "Loading GAMbit…"
    s.close()
