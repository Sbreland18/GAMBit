"""Round 33: running-jobs chip, friendly values, org unit drop-down, errors on the field,
unsaved-changes guard, Settings sections + search, keyboard focus, copy on hover,
remembering where you were, step-by-step Create a user / New staff."""

import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

from gambit.settings import settings


@pytest.fixture(autouse=True)
def clean():
    for k in ("setup/seen", "tour/seen", "oumap/reminded"):
        settings.set(k, True)
    settings.set("connection/auto_test", False)
    settings.check_updates_on_start = False
    for k, v in {"ui/friendly": True, "ui/restore": True, "ui/drawer": True,
                 "remember/tabs": "", "ui/last_page": ""}.items():
        settings.set(k, v)
    yield


def pump(sec=0.2):
    end = time.time() + sec
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def test_friendly_values():
    from gambit.ui.friendly import friendly
    assert friendly("False") == "No" and friendly("TRUE") == "Yes"
    assert friendly("1970-01-01T00:00:00.000Z") == "Never"
    assert friendly("2024-08-01").startswith("Aug 1, 2024")
    assert friendly("2024-08-01T00:00:00.000Z").startswith("Aug 1, 2024")   # no day slip
    assert "PM" in friendly("2024-08-01T15:04:00") or "AM" in friendly("2024-08-01T15:04:00")
    assert friendly("12345") == "12345" and friendly("") == ""
    import datetime
    today = datetime.date.today().isoformat()
    assert "today" in friendly(today)


def test_table_shows_friendly_but_keeps_exact(qapp):
    from gambit.ui.widgets import ResultsTable
    t = ResultsTable()
    t.set_rows(["primaryEmail", "suspended", "lastLoginTime"],
               [["a@x.org", "False", "2024-08-01T00:00:00.000Z"]])
    idx = t.proxy.index(0, 2)
    assert idx.data().startswith("Aug 1, 2024") and idx.data(Qt.UserRole).startswith("2024")
    assert idx.data(Qt.ToolTipRole) == "2024-08-01T00:00:00.000Z"
    assert t.row_dict(0)["lastLoginTime"] == "2024-08-01T00:00:00.000Z"     # exports/actions
    t._apply_filter("aug")
    assert t.row_count() == 1                                              # filter sees it
    settings.set("ui/friendly", False)
    t.set_rows(["x"], [["False"]])
    assert t.proxy.index(0, 0).data() == "False"
    settings.set("ui/friendly", True)


def test_copy_on_hover(qapp):
    from gambit.ui.widgets import ResultsTable
    t = ResultsTable()
    t.resize(700, 300)
    t.show()
    t.set_rows(["primaryEmail", "name"], [["a@x.org", "A"]])
    pump()
    r = t.table.visualRect(t.proxy.index(0, 0))
    t._hover_copy(r.center())
    assert t._copy_btn.isVisible() and t._copy_btn.property("value") == "a@x.org"
    t._do_copy()
    assert QApplication.clipboard().text() == "a@x.org"
    r = t.table.visualRect(t.proxy.index(0, 1))
    t._hover_copy(r.center())
    assert not t._copy_btn.isVisible()


def test_field_errors_inline(qapp):
    from PySide6.QtWidgets import QFormLayout, QPushButton, QWidget
    from gambit.ui import field_errors as fe
    w = QWidget()
    f = QFormLayout(w)
    name, email = QLineEdit(), QLineEdit("not-an-email")
    f.addRow("Name", name)
    f.addRow("Email", email)
    assert not fe.check_fields([("a name", name)], emails=[email])
    assert name.property("invalid") and email.property("invalid")
    assert f.rowCount() == 4                       # a note row under each field
    name.setText("Pat")                            # editing clears it
    assert not name.property("invalid") and f.rowCount() == 3
    email.setText("pat@school.org")
    assert fe.check_fields([("a name", name)], emails=[email]) and f.rowCount() == 2
    b = QPushButton("Go")
    fe.ready_when(b, name)
    name.clear()
    assert not b.isEnabled()
    name.setText("x")
    assert b.isEnabled()


def test_ou_popup_labels_counts_recent(qapp, fake_gam):
    from gambit.ui.main_window import MainWindow
    from gambit.ui.pickers import OUPopup, ou_counts, ou_label
    w = MainWindow()
    d = w.directory
    d.ous = ["/Students", "/Students/Middle School", "/Staff"]
    d.users = [{"email": "a@x", "ou": "/Staff"}, {"email": "b@x", "ou": "/Staff"}]
    assert ou_counts(d) == {"/staff": 2}
    assert "2 people" in ou_label("/Staff", ou_counts(d))
    pop = OUPopup(d, "/Staff")
    got = []
    pop.picked.connect(got.append)
    it = pop.tree.currentItem()
    assert it.data(0, Qt.UserRole) == "/Staff"
    pop._choose(it)
    assert got == ["/Staff"]
    pop2 = OUPopup(d)
    assert pop2.tree.topLevelItem(0).text(0) == "Recently used"
    pop2.search.setText("middle")
    root = pop2.tree.topLevelItem(1)
    assert not root.isHidden()
    w.close()


def test_jobs_chip(qapp, fake_gam):
    from gambit.gam_runner import Job
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    chip = w.jobs_chip
    j = Job(["print", "users"], None, True)
    j.status, j.started_at, j.progress = "running", time.time() - 3, (5, 20)
    w.runner.jobs.append(j)
    chip.refresh()
    assert chip.btn.isVisibleTo(w) and "25%" in chip.btn.text()
    chip.fill()
    assert j.id in chip._rows
    cancelled = []
    w.runner.cancel = lambda job: cancelled.append(job)
    chip.stop_all()
    assert cancelled == [j]
    w.runner.jobs.remove(j)
    chip.refresh()
    assert not chip.btn.isVisibleTo(w)
    w.close()


def test_create_user_stepper_and_unsaved_guard(qapp, fake_gam, monkeypatch):
    from gambit.ui import unsaved
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    w.go("Users")
    u = w.pages["Users"]
    st = u.c_stepper
    u.c_first.setText("Pat")
    st.next()                                     # last name + email missing
    assert st.i == 0 and u.c_last.property("invalid")
    u.c_last.setText("Smith")
    u.c_email.setText("pat.smith@hancockschools.net")
    st.next()
    st.next()
    assert st.i == 2 and "Create pat.smith@hancockschools.net" in st.review_lbl.text()
    assert "gam create user" in st.cmds.text()
    # typed by the user → leaving asks
    u.c_first.textEdited.emit("Pat")
    assert unsaved.unsaved(u) == ["a new user account"]
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: asked.append(a[1]) or QMessageBox.No))
    w.go("Groups")
    assert asked == ["Leave without saving?"] and w.current_page() is u
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    w.go("Groups")
    assert w.current_page() is w.pages["Groups"] and not unsaved.unsaved(u)
    w.close()


def test_new_staff_stepper_plan(qapp, fake_gam):
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    wf = w.pages["Workflows"]
    s = wf.ns_stepper
    s.next()
    assert s.i == 0                               # names and email required
    wf.ns_first.setText("Pat")
    wf.ns_last.setText("Lee")
    wf.ns_email.setText("pat.lee@hancockschools.net")
    s.next()
    s.next()
    assert s.i == 2
    plan = wf._ns_review()
    assert plan[0][0].startswith("Create pat.lee@") and "create user" in plan[0][1]
    w.close()


def test_settings_sections_and_search(qapp, fake_gam):
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    sp = w.pages["Settings & Updates"]
    nav = sp.section_nav
    titles = [nav.list.item(i).text() for i in range(nav.list.count())]
    assert "Appearance and safety" in titles and len(titles) >= 8
    nav.search.setText("tray")
    shown = [nav.list.item(i).text() for i in range(nav.list.count())
             if not nav.list.item(i).isHidden()]
    assert shown == ["Appearance and safety"]
    nav.search.setText("zzzz-nothing")
    assert nav.none.isVisibleTo(nav)
    nav.search.clear()
    w.close()


def test_remember_tabs_last_page_and_fields(qapp, fake_gam):
    from PySide6.QtWidgets import QTabWidget
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    w.go("Groups")
    tw = w.pages["Groups"].findChild(QTabWidget)
    tw.setCurrentIndex(1)
    w.pages["Users"].l_value.setText("/Students/2031")
    assert settings.get("ui/last_page") == "Groups"
    w.close()
    w2 = MainWindow()
    w2.restore_last_page()
    assert w2.current_page() is w2.pages["Groups"]
    assert w2.pages["Groups"].findChild(QTabWidget).currentIndex() == 1
    pump(0.1)
    assert w2.pages["Users"].l_value.text() == "/Students/2031"
    assert not w2.back_btn.isVisibleTo(w2)
    settings.set("ui/restore", False)
    w3 = MainWindow()
    w3.restore_last_page()
    assert w3.current_page() is w3.pages["Home"]
    for x in (w2, w3):
        x.close()


def test_focus_ring_and_button_names(qapp):
    from PySide6.QtWidgets import QPushButton, QWidget, QHBoxLayout
    from gambit.ui import a11y
    host = QWidget()
    lay = QHBoxLayout(host)
    a, b = QPushButton("A"), QPushButton("")
    b.setToolTip("Notifications – alerts and pop-ups")
    lay.addWidget(a)
    lay.addWidget(b)
    host.show()
    assert a11y.name_buttons(host) == 1 and b.accessibleName() == "Notifications"
    watch = a11y.input_watch()
    watch._kbd = time.time()                 # as if Tab was just pressed
    watch._focus(None, a)
    assert a.property("kbdfocus") is True
    watch._kbd = 0
    watch._focus(a, b)                       # mouse focus: no outline
    assert not a.property("kbdfocus") and not b.property("kbdfocus")
