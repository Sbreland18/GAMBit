"""Round 31: closer to the mock-up – Home tiles with trend lines and meters, the big look-up
box, recently-viewed rows, dashboard history, icon-only top-bar chips, Output hidden by
default, the compact selection bar."""

import json
import time

import pytest

from gambit.settings import settings


@pytest.fixture(autouse=True)
def clean():
    keys = ("ui/split2", "digest/license_seats", "recent/items")
    for k in keys:
        settings.set(k, "")
    yield
    for k in keys:
        settings.set(k, "")


def test_dashboard_history_one_point_per_day():
    from gambit import dashboard
    dashboard.save({"time": time.time() - 86400, "active": 10, "alerts": 1})
    dashboard.save({"time": time.time(), "active": 11, "alerts": 2})
    dashboard.save({"time": time.time(), "active": 12, "alerts": 3})   # same day: replaces
    assert dashboard.history("active")[-2:] == [10, 12]
    assert dashboard.history("alerts")[-1] == 3
    assert len(dashboard.load_cached()["history"]) <= dashboard.HISTORY_DAYS


def test_stat_tile_trend_meter_and_status(qapp):
    from gambit.ui.home_widgets import StatTile, ago
    t = StatTile("Licenses assigned", "Open Licenses", "id-card", "green")
    t.set(7889, "96% of the 8,200 you bought", "warn", None, 0.96)
    assert t.value.text() == "7,889" and not t.meter.isHidden() and t.spark.isHidden()
    t.set(5, "", None, [1, 2, 3])
    assert t.spark.isVisibleTo(t) and t.meter.isHidden() and t.sub.isHidden()
    t.set(5, "x", None, [3])               # one point: no line
    assert not t.spark.isVisibleTo(t)
    assert ago("") == "" and ago(time.strftime("%Y-%m-%dT%H:%M")) == "just now"


def test_home_lookup_recent_and_license_meter(qapp, fake_gam):
    from gambit import user_prefs as up
    from gambit.ui.main_window import MainWindow
    up.add_recent("user", "jdoe@hancockschools.net", "John Doe")
    up.add_recent("device", "5CD0372JK1")
    w = MainWindow()
    h = w.pages["Home"]
    h.on_show()
    from gambit.ui.home_widgets import BigSearch, RecentRow
    assert h.findChild(BigSearch) is not None and h.q_dev is h.q_person
    rows = h.findChildren(RecentRow)
    assert len([r for r in rows if not r.isHidden()]) == 2
    hit = []
    w.open_recent = lambda r: hit.append(r)
    rows[-1].clicked.emit()
    assert hit
    settings.set("digest/license_seats", "1010070001 = 8000")
    sub, status, trend, frac = h._license_line({"license_breakdown": {"1010070001": 7900}})
    assert "99%" in sub and status == "warn" and frac > 0.98
    sub, *_ = h._license_line({"license_breakdown": {"1010070001": 5}})
    assert "%" in sub
    settings.set("digest/license_seats", "")
    sub, _s, _t, frac = h._license_line({"license_breakdown": {"1010070001": 5}})
    assert "Education Fundamentals" in sub and frac is None
    w.close()


def test_topbar_chips_and_output_hidden(qapp, fake_gam):
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    assert w.dry_btn.text() == "" and w.practice_btn.text() == "" and w.helper_btn.text() == ""
    w.set_dry_run(True)
    assert w.dry_btn.objectName() == "ChipOn" and "ON" in w.dry_btn.text()
    w.set_dry_run(False)
    assert w.dry_btn.objectName() == "Chip" and w.dry_btn.text() == ""
    assert w.split.sizes()[1] == 0 and w.out_toggle.text() == "Show output"
    w.split.resize(800, 900)
    w.toggle_output(True)
    assert w.out_toggle.text() == "Hide output"
    assert w._header_text("PEOPLE", True) == "PEOPLE   ▸"
    assert w.profile_box.currentData()
    w.close()


def test_selection_bar_shortens_and_overflows(qapp):
    from gambit.ui.widgets import ResultsTable
    t = ResultsTable()
    assert t._short("Require password change at next sign-in for 3 person(s)…", 3) == \
        "Require new password"
    assert len(t._short("A very long action name that keeps going and going", 2)) <= 23
