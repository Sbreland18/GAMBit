"""Round 35: the jobs pop-up no longer freezes (plain pop-up, not a menu), consistency pass
(messages on the field, table polish, button rows), updated tour and Guide, first-day
checklist."""

import time

import pytest
from PySide6.QtWidgets import QApplication

from gambit.settings import settings


@pytest.fixture(autouse=True)
def clean():
    for k in ("setup/seen", "tour/seen", "oumap/reminded", "whatsnew/off"):
        settings.set(k, True)
    settings.set("connection/auto_test", False)
    settings.check_updates_on_start = False
    settings.set("onboard/hidden", False)
    yield


def pump(sec=0.2):
    end = time.time() + sec
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def test_jobs_popup_is_not_a_blocking_menu(qapp, fake_gam):
    from PySide6.QtWidgets import QMenu
    from gambit.gam_runner import Job
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    chip = w.jobs_chip
    assert not isinstance(chip.menu, QMenu) and chip.btn.menu() is None
    j = Job(["print", "users"], None, True)
    j.status, j.started_at = "running", time.time()
    w.runner.jobs.append(j)
    chip.refresh()
    chip.toggle()                         # returns at once – nothing blocks
    assert chip.menu.isVisible() and j.id in chip._rows
    for _ in range(3):
        chip.refresh()                    # updates in place while open
    assert chip.menu.isVisible()
    chip.toggle()
    assert not chip.menu.isVisible()
    w.runner.jobs.remove(j)
    w.close()


def test_nudge_goes_on_the_field_or_a_toast(qapp, fake_gam):
    from PySide6.QtWidgets import QFormLayout, QLineEdit
    from gambit.ui.widgets import Page

    class App:
        runner = None
    shown = []

    class P(Page):
        title = "Nudge test"

        def build(self):
            box, form = self.group("Thing")
            self.owner = QLineEdit(placeholderText="Owner")
            self.drive = QLineEdit(placeholderText="New shared drive name")
            form.addRow("Owner", self.owner)
            form.addRow("Name", self.drive)
            self.body.addWidget(box)
    p = P(App())
    p.resize(800, 600)
    p.show()
    pump()
    p.info("Type a name for the new shared drive.")
    assert p.drive.property("invalid") and not p.owner.property("invalid")
    p.drive.setText("x")
    assert not p.drive.property("invalid")
    import gambit.ui.widgets as W
    called = []
    orig = W.QMessageBox.information
    W.QMessageBox.information = staticmethod(lambda *a, **k: called.append(a[2]))
    try:
        p.info("Something went fine.\nSecond line")      # not a nudge → normal message
        assert called
        p.info("Select a request.")                       # no window with toasts → message
        assert len(called) == 2
    finally:
        W.QMessageBox.information = orig


def test_button_rows_and_table_polish(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton, QTableWidget, QWidget, QVBoxLayout
    from gambit.ui import forms
    from gambit.ui.widgets import Page
    h = Page.row(QPushButton("A"), QPushButton("B"), stretch=False)
    assert h.itemAt(h.count() - 1).spacerItem() is not None
    w = QWidget()
    t = QTableWidget(2, 2, w)
    QVBoxLayout(w).addWidget(t)
    assert forms.polish_tables(w) == 1 and forms.polish_tables(w) == 0
    assert not t.showGrid() and t.verticalHeader().defaultSectionSize() >= 34
    assert t.horizontalHeader().defaultAlignment() & Qt.AlignLeft


def test_onboarding_items(qapp):
    from gambit import onboarding

    class D:
        users, connected = [], None
    its = onboarding.items(D())
    keys = [i["key"] for i in its]
    assert keys[:3] == ["gam", "lists", "schools"] and "tasks" in keys
    settings.set(onboarding.DRY_KEY, True)
    assert next(i for i in onboarding.items(D()) if i["key"] == "dry")["done"]
    done, total = onboarding.progress(its)
    assert total == len(its) and 0 <= done <= total
    assert not onboarding.complete([{"done": False}]) and onboarding.complete(
        [{"done": True}, {"done": False, "optional": True}])


def test_checklist_on_home(qapp, fake_gam):
    from gambit import onboarding
    from gambit.ui.main_window import MainWindow
    settings.set(onboarding.DRY_KEY, False)
    w = MainWindow()
    h = w.pages["Home"]
    h.arrange()
    boxes = [h.lay.itemAt(i).widget() for i in range(h.lay.count())
             if h.lay.itemAt(i).widget() in h.sections.values()]
    assert boxes[0] is h.sections["started"] and h.chk_lay.count() == 8
    h._checklist_do("dry")
    assert settings.get(onboarding.DRY_KEY) and settings.get("safety/dry_run")
    w.set_dry_run(False)
    h._hide_checklist()
    assert onboarding.hidden() and not h.sections["started"].isVisibleTo(h)
    w.close()


def test_tour_steps_point_at_real_widgets(qapp, fake_gam):
    from gambit.ui.app_actions import Tour
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    t = Tour(w)
    keys = [k for _p, k, _t, _x in t.STEPS]
    assert "bottom" not in keys and {"lookup", "customize", "table", "bell"} <= set(keys)
    for page, key, _title, _text in t.STEPS:
        if page:
            w.go(page)
        assert t._target(key) is not None, key
    w.close()


def test_guide_has_no_old_emoji_wording():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "gambit" / "guide"
    text = "".join(p.read_text(encoding="utf-8") for p in root.glob("*.py"))
    for old in ("🧪 Dry run", "📌 Pin", "⚙ Customize", "🎓 Practice", "💬 Helper",
                "Domain box"):
        assert old not in text, old
