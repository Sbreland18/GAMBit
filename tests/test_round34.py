"""Round 34: what's next after actions, paste a list, row quick actions, changes today with
Undo, simple mode, jargon help, run tonight, saved table views, print / PDF."""

import json
import os
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from gambit.settings import settings


@pytest.fixture(autouse=True)
def clean():
    for k in ("setup/seen", "tour/seen", "oumap/reminded"):
        settings.set(k, True)
    settings.set("connection/auto_test", False)
    settings.check_updates_on_start = False
    settings.set("ui/simple", False)
    settings.set("favorites", "[]")
    yield
    settings.set("ui/simple", False)


USERS = [{"email": "jdoe@hancockschools.net", "name": "John Doe", "sis_id": "1001"},
         {"email": "mjones@hancockschools.net", "name": "Mary Jones", "sis_id": "1002"},
         {"email": "mjones2@hancockschools.net", "name": "Mary Jones", "sis_id": ""}]


def test_paste_tokens_and_matching():
    from gambit.ui.paste_list import match_people, tokens
    t = tokens("jdoe@hancockschools.net\n1002\nDoe, John\nNobody Here\n\n1001,1002\nMary Jones")
    assert t == ["jdoe@hancockschools.net", "1002", "Doe, John", "Nobody Here", "1001",
                 "Mary Jones"]
    ok, bad, amb = match_people(t, USERS)
    emails = [e for e, _l in ok]
    assert emails == ["jdoe@hancockschools.net", "mjones@hancockschools.net"]
    assert bad == ["Nobody Here"] and amb == [("Mary Jones", 2)]


def test_paste_serials_without_fleet(monkeypatch):
    from gambit import fleet_cache
    from gambit.ui.paste_list import match_serials
    monkeypatch.setattr(fleet_cache, "all_rows", lambda: [])
    ok, bad, _ = match_serials(["5cd0372jk1", "not a serial!"])
    assert ok[0][0] == "5CD0372JK1" and bad == ["not a serial!"]
    monkeypatch.setattr(fleet_cache, "all_rows", lambda: [
        {"serialNumber": "SN1", "annotatedAssetId": "HMS-1", "annotatedUser": "a@x"}])
    ok, bad, _ = match_serials(["hms-1", "SN9"])
    assert ok == [("SN1", "SN1  ·  a@x")] and bad == ["SN9"]


def test_people_picker_paste(qapp, monkeypatch):
    from gambit.directory import Directory
    from gambit.ui import paste_list
    from gambit.ui.pickers import PeoplePicker
    d = Directory()
    d.users = list(USERS)
    p = PeoplePicker(d, include_groups=False)
    monkeypatch.setattr(paste_list, "paste_people",
                        lambda *a, **k: ["jdoe@hancockschools.net", "mjones@hancockschools.net"])
    p._paste_list()
    assert p.emails() == ["jdoe@hancockschools.net", "mjones@hancockschools.net"]


def test_glossary(qapp):
    from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QWidget
    from gambit.ui.glossary import annotate, explain
    assert explain("orgUnitPath") and explain("Org unit:") and not explain("Email")
    w = QWidget()
    f = QFormLayout(w)
    f.addRow("Org unit", QLineEdit())
    f.addRow("Email", QLineEdit())
    assert annotate(w) == 1 and annotate(w) == 0          # only once
    lab = f.itemAt(0, QFormLayout.LabelRole).widget()
    assert "ⓘ" in lab.text() and "folder in Google Admin" in lab.toolTip()
    from gambit.ui.widgets import ResultsTable
    t = ResultsTable()
    t.set_rows(["orgUnitPath", "primaryEmail"], [["/S", "a@x"]])
    tip = t.model.headerData(0, Qt.Horizontal, Qt.ToolTipRole)
    assert tip.startswith("orgUnitPath") and "Org unit" in tip


def test_saved_views_and_print(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QVBoxLayout
    from gambit.ui.widgets import Page, ResultsTable

    class FakeApp:
        runner = None

    class P(Page):
        title = "View test"

        def build(self):
            self.t = ResultsTable()
            self.body.addWidget(self.t)
    settings.set("views/View test", "")
    p = P(FakeApp())
    t = p.t
    rows = [["b@x", "Bee", "/S"], ["a@x", "Ay", "/T"]]
    t.set_rows(["primaryEmail", "name", "orgUnitPath"], rows)
    t.filter.setText("x")
    t.table.setColumnHidden(1, True)
    t.sort_by(0)
    v = t.save_view("Just emails")
    assert v and t.views()[0]["name"] == "Just emails" and v["hidden"] == ["name"]
    t.filter.setText("")
    t.reset_columns()
    t.set_rows([], [])
    t.apply_view(v)                          # empty table → applied when rows arrive
    assert t.filter.text() == "x" and t._pending_view
    t.set_rows(["primaryEmail", "name", "orgUnitPath"], rows)
    assert t.table.isColumnHidden(1) and t.row_dict(0)["primaryEmail"] == "a@x"
    assert not t._pending_view
    t.delete_view(v)
    assert t.views() == []
    # print / PDF
    from gambit.ui import table_print
    html = table_print.build_html(t)
    assert "View test" in html and "a@x" in html and "Name" not in html.split("<thead>")[1][:200]
    out = tmp_path / "x.pdf"
    from PySide6.QtPrintSupport import QPrinter
    pr = table_print._printer(False)
    pr.setOutputFormat(QPrinter.PdfFormat)
    pr.setOutputFileName(str(out))
    table_print._document(t).print_(pr)
    assert out.exists() and out.stat().st_size > 1000


def test_window_features(qapp, fake_gam, monkeypatch):
    from gambit import activity, change_queue
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    # run tonight
    before = len(change_queue.queue())
    w.queue_tonight(["update", "ou", "/Students/2031", "add", "users", "a@x"])
    q = change_queue.queue()
    assert len(q) == before + 1 and q[-1]["when"][11:16] == "18:00"
    # changes today
    e = activity.record(["update", "user", "jdoe@hancockschools.net", "ou", "/S/2031"], 0,
                        "done", {"args": ["update", "user", "jdoe@hancockschools.net", "ou",
                                          "/S"]}, "Default")
    from gambit.ui.changes_today import ChangesToday, todays_changes
    assert any(x["id"] == e["id"] for x in todays_changes())
    dlg = ChangesToday(w)
    undone = []
    w.run_undo = lambda entry: undone.append(entry["id"])
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    from PySide6.QtWidgets import QPushButton
    btn = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Undo" and
               b.isEnabled())
    btn.click()
    assert undone and not btn.isEnabled()
    # row quick actions
    from gambit.ui.widgets import ResultsTable
    acts = ResultsTable._row_actions(w.pages["Users"].results,
                                     {"primaryEmail": "jdoe@hancockschools.net"})
    assert [a[0].split()[0] for a in acts][:2] == ["Open", "Reset"]
    # next steps after create
    from gambit.ui.next_steps import NextSteps, for_new_account, for_suspended
    acts = for_new_account(w, "jdoe@hancockschools.net")
    assert [a[0] for a in acts][:2] == ["Open the person", "Print account card"]
    assert any("Transfer" in a[0] for a in for_suspended(w, ["jdoe@hancockschools.net"]))
    hit = []
    d = NextSteps(w, "Done", "x", [("Go", lambda: hit.append(1))])
    d._pick(lambda: hit.append(2))
    d.run = lambda: None
    assert d.chosen is not None
    # simple mode
    w.set_simple(True)
    names = {w.nav.item(i).data(Qt.UserRole + 2) for i in range(w.nav.count())
             if not w.nav.item(i).isHidden()}
    assert "Users" not in names and "Student lookup" in names
    home = w.pages["Home"]
    assert home.sections["simple"].isVisibleTo(home) and w.simple_btn.isVisibleTo(w)
    w.set_simple(False)
    assert not home.sections["simple"].isVisibleTo(home) and not w.simple_btn.isVisibleTo(w)
    # saved view as a Home favorite
    w.add_view_favorite({"id": "v1", "name": "My view", "page": "Users", "table": 0})
    assert any(f["kind"] == "view" for f in w.favorites())
    w.close()
