"""Round 30: the modern look – tokens & accent, icons, table pills and headers, toasts with
Undo, notification history, Ctrl+K palette, icon rail."""

import pytest

from gambit.settings import settings


@pytest.fixture(autouse=True)
def clean():
    for k in ("ui/accent", "ui/rail", "notify/history"):
        settings.set(k, "")
    yield
    for k in ("ui/accent", "ui/rail", "notify/history"):
        settings.set(k, "")


def test_tokens_and_accent():
    from gambit.ui import theme
    assert theme.accent() == "#2563EB"
    settings.set("ui/accent", "#0F766E")
    assert theme.tokens("light")["accent"] == "#0F766E"
    assert theme.tokens("dark")["accent_text"].startswith("#")
    settings.set("ui/accent", "not a colour")
    assert theme.accent() == "#2563EB"
    css = theme.build_css("light")
    assert "QListWidget#Nav::item:selected" in css and "#2563EB" in css
    assert "QFrame#Toast" in css and "QFrame#SelBar" in css
    assert theme.scaled_stylesheet(1.5).count("15.0pt") >= 1


def test_icons(qapp):
    from gambit.ui import icons
    from gambit.ui.main_window import PAGES
    assert all(icons.PAGE.get(n) in icons.P for n, _c in PAGES)      # every page has one
    assert not icons.icon("users").isNull() and not icons.page_icon("Nope").isNull()
    assert icons.split_emoji("✅ Check everything") == ("check-circle", "Check everything")
    assert icons.split_emoji("Plain") == (None, "Plain")
    from gambit.ui.widgets import button
    b = button("🖨 Print card", "primary")
    assert b.text() == "Print card" and not b.icon().isNull()
    assert b.property("_gb_icon") == "printer"


def test_pills_and_headers():
    from gambit.ui.widgets import nice_header, pill_kind, pill_text
    assert nice_header("orgUnitPath") == "ORG UNIT PATH"
    assert nice_header("name.fullName") == "NAME · FULL NAME"
    assert pill_kind("suspended", "True") == "bad" and pill_text("suspended", "True") == \
        "Suspended"
    assert pill_kind("suspended", "False") == "good"
    assert pill_kind("status", "ACTIVE") == "good" and pill_text("status", "ACTIVE") == \
        "Active"
    assert pill_kind("status", "DISABLED") == "bad"
    assert pill_kind("status", "pending") == "warn"
    assert pill_kind("isEnrolledIn2Sv", "False") == "warn"
    assert pill_kind("status", "") == ""


def test_results_table_pills_and_selection_bar(qapp):
    from gambit.ui.widgets import ResultsTable, StatusDelegate
    t = ResultsTable()
    t.set_rows(["primaryEmail", "suspended", "orgUnitPath"],
               [["a@x", "True", "/S"], ["b@x", "False", "/S"]])
    assert isinstance(t.table.itemDelegateForColumn(1), StatusDelegate)
    assert t.table.itemDelegateForColumn(0) is not t.table.itemDelegateForColumn(1)
    assert t.model.headerData(2, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Horizontal) \
        == "ORG UNIT PATH"
    assert t._headers == ["primaryEmail", "suspended", "orgUnitPath"]   # data unchanged
    t.set_rows(["x"], [["1"]])                                           # delegates reset
    assert not isinstance(t.table.itemDelegateForColumn(1), StatusDelegate)


def test_notify_center_and_toasts(qapp, fake_gam):
    settings.set("tour/seen", True)
    settings.set("setup/seen", True)
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    n0 = w.notices.unread
    w.toasts.change_done({"what": "Suspended a@x", "undo": {"commands": [["x"]]}}, 0,
                         "gam update user a@x suspended on")
    w.toasts.change_done({"what": "Suspended b@x"}, 0, "gam update user b@x suspended on")
    w.toasts._flush()
    assert w.notices.items[0]["title"] == "2 changes done" and w.notices.unread == n0 + 1
    assert any(t.findChildren(type(w.bell_btn)) for t in w.toasts.toasts)   # Undo button
    w.toasts.change_done(None, 1, "gam update user c@x suspended on")
    w.toasts._flush()
    assert w.notices.items[0]["title"].startswith("Failed:")
    w.refresh_bell()
    assert w.bell_btn.text().strip().isdigit()
    w.notices.read_all()
    assert w.bell_btn.text() == ""
    # Ctrl+K palette
    from gambit.ui.palette import CommandPalette
    w.directory.users = [{"email": "jane@x", "name": "Jane Doe", "ou": "/Staff"}]
    p = CommandPalette(w)
    p.input.setText("jane")
    texts = [p.list.item(i).text() for i in range(p.list.count())]
    assert "PEOPLE" in texts and any(t.startswith("Check everything about") for t in texts)
    p.input.setText("device history")
    assert any("Device history" in p.list.item(i).text() for i in range(p.list.count()))
    p.close()
    # icon rail
    w.toggle_rail()
    assert w.side.width() == 76 and w.rail
    named = [w.nav.item(i).data(0x0100 + 2) for i in range(w.nav.count())]
    assert "Users" in named and all(w.nav.item(i).text() == "" for i in range(w.nav.count())
                                    if w.nav.item(i).data(0x0100 + 2))
    w.go("Users")
    assert w.current_page() is w.pages["Users"]
    w.toggle_rail()
    assert not w.rail and w.side.width() > 200
    w.close()


def test_person_header(qapp):
    from gambit.ui.person_header import PersonHeader, initials
    assert initials("John Doe") == "JD" and initials("", "kim@x") == "KI"
    h = PersonHeader()
    h.set_person("John Doe", "j@x", [("Active", "good"), ("7th Grade", "info")], "Org unit /S")
    assert "John Doe" in h.text() and h.avatar.text() == "JD"
    h.setText("not found")
    assert h.text() == "not found"
