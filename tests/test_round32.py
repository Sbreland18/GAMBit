"""Round 32: details side panel, tab overflow menu, modern message windows, loading and
empty states, shorter sidebar, line icons instead of emoji, narrower form fields, ticket
chip, editing Home in place, back button, table density and columns."""

import json
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from gambit.settings import settings

DEFAULTS = {"ui/drawer": True, "ui/density": "comfortable", "nav/dedupe": True,
            "nav/autofold": True, "ui/page_help": True, "home/layout": "", "nav/pinned": "[]"}


@pytest.fixture(autouse=True)
def clean():
    for k, v in DEFAULTS.items():
        settings.set(k, v)
    for k in ("setup/seen", "tour/seen", "oumap/reminded"):   # no first-run windows
        settings.set(k, True)
    settings.set("connection/auto_test", False)
    settings.check_updates_on_start = False
    yield
    for k, v in DEFAULTS.items():
        settings.set(k, v)


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def test_modern_message_buttons_and_risk(qapp):
    from gambit.ui.dialogs import ModernMessage, SB
    m = ModernMessage(None, "question", "Please confirm", "Suspend 3 accounts?",
                      SB.Yes | SB.No)
    from PySide6.QtWidgets import QPushButton
    btns = {b.text(): b for b in m.findChildren(QPushButton)}
    assert set(btns) == {"Yes", "No"} and btns["Yes"].property("kind") == "danger"
    btns["Yes"].click()
    assert m.result_button == SB.Yes
    m2 = ModernMessage(None, "question", "Save", "Save the layout?", SB.Yes | SB.No)
    assert {b.text(): b for b in m2.findChildren(QPushButton)}["Yes"].property("kind") == \
        "primary"
    m2.reject()
    assert m2.result_button == SB.No            # Esc = No
    m3 = ModernMessage(None, "info", "GAMbit", "Couldn't read users.")
    assert m3.findChild(QPushButton).text() == "OK"


def test_dialogs_install_routes_static_calls(qapp, monkeypatch):
    from gambit.ui import dialogs
    orig = (QMessageBox.question, QMessageBox.information, QMessageBox.warning,
            QMessageBox.critical)
    monkeypatch.setattr(dialogs, "_installed", False)
    seen = []
    monkeypatch.setattr(dialogs.ModernMessage, "run",
                        lambda self: seen.append(self.windowTitle()) or dialogs.SB.Yes)
    try:
        dialogs.install()
        assert QMessageBox.question(None, "Delete", "Delete it?") == QMessageBox.Yes
        QMessageBox.information(None, "Hello", "x")
        assert seen == ["Delete", "Hello"]
    finally:
        (QMessageBox.question, QMessageBox.information, QMessageBox.warning,
         QMessageBox.critical) = orig


def test_table_states_empty_filter_and_loading(qapp, monkeypatch):
    from gambit.ui import table_states
    from gambit.ui.widgets import ResultsTable
    monkeypatch.setattr(table_states._Hub, "user_started", lambda self: False)
    table_states.hub().active = 0
    t = ResultsTable()
    t.resize(600, 400)
    t.show()
    pump()
    assert t.states.mode == "empty" and "Nothing here yet" in t.states.title.text()
    t.set_rows(["primaryEmail"], [["a@x"], ["b@x"]])
    pump()
    assert not t.states.isVisible()
    t.filter.setText("zzz")
    t._apply_filter("zzz")
    assert "Nothing matches" in t.states.title.text() and t.states.clear_btn.isVisibleTo(t.states)
    t.states.clear_btn.click()
    t._apply_filter("")
    assert not t.states.isVisible()
    t.set_rows(["primaryEmail"], [])
    pump()
    assert t.states.title.text() == "No results"
    t.set_empty_text("No suspended accounts", "Good news.")
    assert t.states.title.text() == "No suspended accounts"
    t.set_loading(True)
    assert t.states.delay.isActive()
    t.states.delay.stop()
    t.states._show_loading()                 # what the short delay does
    assert t.states.mode == "loading"
    t.set_rows(["primaryEmail"], [["a@x"]])
    assert t.states.mode != "loading"


def test_density_and_columns(qapp):
    from gambit.ui.widgets import ResultsTable
    t = ResultsTable()
    t.set_rows(["primaryEmail", "name", "orgUnitPath"], [["a@x", "A", "/S"]])
    ResultsTable.set_density("compact")
    assert t.table.verticalHeader().defaultSectionSize() == 26
    ResultsTable.set_density("comfortable")
    assert t.table.verticalHeader().defaultSectionSize() == 34
    t._save_cols(["orgUnitPath", "primaryEmail", "name"], ["name"])
    t.set_rows(["primaryEmail", "name", "orgUnitPath"], [["a@x", "A", "/S"]])
    hh = t.table.horizontalHeader()
    assert hh.logicalIndex(0) == 2 and t.table.isColumnHidden(1)
    t.reset_columns()
    assert hh.logicalIndex(0) == 0 and not t.table.isColumnHidden(1)
    t._fill_view_menu()
    assert any("Compact" in a.text() for a in t.view_menu.actions())


def test_forms_cap_and_tabs_more(qapp):
    from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QTabWidget, QWidget
    from gambit.ui import forms, tabs
    page = QWidget()
    page.title = "Users"
    lay = QHBoxLayout(page)
    e = QLineEdit()
    lay.addWidget(e)
    lay.addWidget(QPushButton("Go"))
    assert forms.cap_fields(page) == 1 and e.maximumWidth() == 720
    wide = QLineEdit()
    wide.setProperty("gb_wide", True)
    lay.addWidget(wide)
    assert forms.cap_fields(page) == 0
    tw = QTabWidget()
    for i in range(14):
        tw.addTab(QWidget(), f"A rather long tab name {i}")
    holder = _wrap(tw)
    tabs.enhance(holder)
    pump(0.3)
    more = tw._gb_more
    more.check()
    assert more.btn.isVisible()
    more._fill()
    assert len([a for a in more.menu.actions() if a.text()]) == 14


def _wrap(w):
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    if w.parentWidget() is None:
        holder = QWidget()
        QVBoxLayout(holder).addWidget(w)
        holder.resize(500, 300)
        holder.show()
    return w.parentWidget()


def test_window_drawer_back_ticket_sidebar(qapp, fake_gam):
    from gambit import user_prefs as up
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    pump()
    # details panel
    assert w.show_details({"primaryEmail": "jdoe@hancockschools.net", "name": "John Doe"})
    assert w.drawer.isVisible() and w.drawer.key == ("user", "jdoe@hancockschools.net")
    assert not w.show_details({"something": "else"})
    w.show_details({"serialNumber": "5CD0", "model": "Dell"})
    assert w.drawer.key == ("device", "5CD0")
    settings.set("ui/drawer", False)
    w.close_details()
    assert not w.show_details({"primaryEmail": "a@b.c"})
    # back button
    w.go("Users")
    w.go("Groups")
    assert w.back_btn.isVisibleTo(w) and w.back_btn.text().strip() == "Users"
    w.go_back()
    assert w.current_page() is w.pages["Users"]
    # ticket chip
    w.ticket_box.setText("https://help.example.org/tickets/1234")
    w._ticket_chip()
    assert w.ticket_btn.text().strip() == "#1234"
    # sidebar: pinned pages aren't repeated below; autofold keeps one section open
    up.toggle_pin("Groups")
    w.build_nav()
    rows = [w.nav.item(i).data(Qt.UserRole + 2) for i in range(w.nav.count())]
    assert rows.count("Groups") == 1
    settings.set("nav/dedupe", False)
    w.build_nav()
    rows = [w.nav.item(i).data(Qt.UserRole + 2) for i in range(w.nav.count())]
    assert rows.count("Groups") == 2
    w.go("Chromebooks")
    pump(0.2)
    folded = up.collapsed()
    assert w.section_of("Chromebooks") not in folded and "PEOPLE" in folded
    # tips: no emoji, line icon instead
    users = w.pages["Users"]
    assert "💡" not in users.help_strip.text() and users.help_icon.pixmap() is not None
    w.close()


def test_home_edit_in_place(qapp, fake_gam):
    from gambit import home_layout as hl
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    h = w.pages["Home"]
    h.set_editing(True)
    pump(0.2)
    keys = h.editor.visible_keys()
    assert h.editor.bars and h.done_btn.isVisibleTo(h) and not h.cust_btn.isVisibleTo(h)
    first = keys[0]
    h.editor.move(first, 1)
    assert h.editor.visible_keys()[1] == first
    h.editor.move_to(first, 0)
    assert h.editor.visible_keys()[0] == first
    h.editor.remove(first)
    assert first not in h.editor.visible_keys()
    h.editor.add(first)
    assert h.editor.visible_keys()[-1] == first
    saved = json.loads(settings.get(hl.LAYOUT_KEY))
    assert saved[len(h.editor.visible_keys()) - 1]["id"] == first
    h.set_editing(False)
    assert not h.editor.bars and h.cust_btn.isVisibleTo(h)
    w.close()
