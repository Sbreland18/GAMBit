"""Round 39 – page tabs down the left (like Settings & Updates)."""

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QTabWidget, QVBoxLayout, QWidget

from gambit.settings import settings


@pytest.fixture(autouse=True)
def clean():
    for k in ("setup/seen", "tour/seen", "whatsnew/off"):
        settings.set(k, True)
    settings.check_updates_on_start = False
    settings.set("connection/auto_test", False)
    settings.set("ui/side_tabs", True)
    yield
    settings.set("ui/side_tabs", True)


def _page(n=3):
    root = QWidget()
    lay = QVBoxLayout(root)
    lay.addWidget(QLabel("above"))
    tw = QTabWidget()
    inner = QTabWidget()
    inner.addTab(QLabel("a"), "Inner A")
    inner.addTab(QLabel("b"), "Inner B")
    tw.addTab(inner, "First")
    for i in range(1, n):
        tw.addTab(QLabel(str(i)), f"Tab {i}")
    lay.addWidget(tw, 1)
    return root, lay, tw, inner


def test_page_tabs_become_a_list_and_follow_the_tabs(qapp):
    from gambit.ui import tabs
    root, lay, tw, inner = _page()
    assert tabs.side_tabs(root) == 1                 # the nested one stays on top
    assert tw.property("_gb_side") and not inner.property("_gb_side")
    assert lay.stretch(1) == 1                       # same slot, same stretch
    root.show()
    QApplication.processEvents()
    lst = tw._gb_side.list
    assert not tw.tabBar().isVisible() and lst.isVisible()
    assert [lst.item(i).text() for i in range(lst.count())] == ["First", "Tab 1", "Tab 2"]
    lst.setCurrentRow(2)
    assert tw.currentIndex() == 2
    tw.setCurrentIndex(1)
    assert lst.currentRow() == 1
    tw.setTabText(1, "Renamed (3)")
    tw.setTabVisible(2, False)
    tw.addTab(QLabel("x"), "Added later")
    tw._gb_side.sync()
    assert lst.item(1).text() == "Renamed (3)" and lst.item(2).isHidden()
    assert lst.item(3).text() == "Added later"
    assert tabs.side_tabs(root) == 0                 # never twice
    tabs.set_side_tabs(False)                        # Settings → Page tabs: across the top
    QApplication.processEvents()
    assert tw.tabBar().isVisible() and not lst.isVisible()
    tabs.set_side_tabs(True)
    QApplication.processEvents()
    assert not tw.tabBar().isVisible() and lst.isVisible()
    root.close()


def test_single_tab_and_opt_out_left_alone(qapp):
    from gambit.ui import tabs
    root = QWidget()
    lay = QVBoxLayout(root)
    one = QTabWidget()
    one.addTab(QLabel("x"), "Only")
    keep = QTabWidget()
    keep.setProperty("keep_top_tabs", True)
    keep.addTab(QLabel("a"), "A")
    keep.addTab(QLabel("b"), "B")
    lay.addWidget(one)
    lay.addWidget(keep)
    assert tabs.side_tabs(root) == 0
