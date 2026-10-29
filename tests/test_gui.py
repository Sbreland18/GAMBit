"""Offscreen smoke tests: every page builds, the runner talks to the fake GAM, and big
tables stay quick."""

import time

from PySide6.QtCore import QEventLoop, QTimer


def _wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_every_page_opens(qapp, fake_gam, monkeypatch):
    from gambit.settings import settings
    settings.set("tour/seen", True)
    settings.set("setup/seen", True)
    settings.check_updates_on_start = False
    settings.set("connection/auto_test", False)
    from gambit.ui.main_window import PAGES, MainWindow
    w = MainWindow()
    w.show()
    from PySide6.QtWidgets import QTabWidget
    from gambit.ui import tabs as _tabs
    side = 0
    for name, _cls in PAGES:
        w.go(name)
        qapp.processEvents()
        assert w.current_page() is w.pages[name]
        pg = w.pages[name]
        for t in pg.findChildren(QTabWidget):         # page tabs are down the left
            if not _tabs._nested(t, pg) and t.count() >= 2:
                assert t.property("_gb_side"), f"{name}: tabs still across the top"
                side += 1
    assert side >= 20
    # page tip: "Try it safely" turns dry run on, and every tip updates
    users = w.pages["Users"]
    assert "Try it safely" in users.help_strip.text()
    users._help_link("safe")
    assert settings.get("safety/dry_run", False)
    assert "Dry run is on" in w.pages["Groups"].help_strip.text()
    users._help_link("real")
    assert not settings.get("safety/dry_run", False)
    # intents: free text finds a task
    from gambit import intents
    assert intents.match("reset password")
    _wait(1500)             # let background look-ups finish before the window goes away
    w.close()


def test_runner_and_dry_run(qapp, fake_gam):
    from gambit.gam_runner import GamRunner
    from gambit.settings import settings
    r = GamRunner()
    got = []
    settings.set("safety/dry_run", True)
    r.run(["update", "user", "a@s.org", "suspended", "on"], lambda c, o, e: got.append(c))
    r.run(["print", "users"], lambda c, o, e: got.append(("print", c, o.count("\n"))))
    for _ in range(50):
        if len(got) == 2:
            break
        _wait(100)
    settings.set("safety/dry_run", False)
    assert got[0] == 0
    assert got[1][0] == "print" and got[1][2] >= 5
    assert not any("suspended" in c for c in fake_gam.calls())   # held back by dry run
    assert r.dry_runs and "suspended on" in r.dry_runs[0]


def test_big_table_is_fast(qapp):
    from gambit.ui.widgets import ResultsTable
    t = ResultsTable()
    rows = [[f"u{i}@s.org", f"/Grade {i % 12}", str(i)] for i in range(30000)]
    t0 = time.time()
    t.set_rows(["email", "ou", "n"], rows)
    t._apply_filter("grade 7")
    t.sort_by(2)
    assert time.time() - t0 < 5
    assert t.row_count() == 2500
    assert t.row_dict(0)["n"] == "7"
