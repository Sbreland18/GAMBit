from gambit import guide
from gambit.guide import gam_ref


def test_markup():
    h = guide.markup("Intro **bold** and `code`.\n\n## Head\n- one\n- two\n  more\n\n1. a\n2. b")
    assert "<p>Intro <b>bold</b> and <code>code</code>.</p>" in h
    assert "<h3>Head</h3>" in h and "<ul>" in h and "<li>two more" in h and "<ol>" in h
    assert "&lt;x&gt;" in guide.markup("<x>")


def test_curated_pages_and_tabs_match_the_app(qapp, fake_gam):
    from gambit.settings import settings
    settings.set("tour/seen", True)
    settings.set("setup/seen", True)
    from gambit.ui.main_window import NAV, MainWindow
    names = {i[0] for i in NAV if not isinstance(i, str)}
    unknown = set(guide.PAGES) - names
    assert not unknown, f"guide pages that don't exist: {unknown}"
    missing = names - set(guide.PAGES) - {"Guide"}
    assert not missing, f"pages with no guide entry: {missing}"
    w = MainWindow()
    for name, info in guide.PAGES.items():
        live = {t for t, _i in guide.live_tabs(w, name)}
        bad = set(info.get("tabs", {})) - live
        assert not bad, f"{name}: guide tabs not on the page: {bad}"
    arts = guide.build(w, include_catalog=False)
    ids = {a.id for a in arts}
    assert "page:Users" in ids and "tab:Chromebook fleet:Lost & stolen" in ids
    # every page article links to real children
    for a in arts:
        assert all(k in ids for k in a.children)
    # F1 opens the guide at the current page
    w.go("Users")
    w.open_guide()
    g = w.pages["Guide"]
    assert g.current.id == "page:Users"
    g.q.setText("lost chromebook")
    g._search()
    assert g.current.id in ("tab:Chromebook fleet:Lost & stolen", "page:Chromebook fleet")
    w.close()


def test_search_and_commands():
    arts = guide.build(None)
    top = [a.id for a in guide.search(arts, "reset password")[:5]]
    assert any(i.startswith(("page:", "tab:", "gam:cmd:")) for i in top)
    legal = guide.search(arts, "legal hold")
    assert legal and any("Vault" in " ".join(a.path) or "Records" in a.title for a in
                         legal[:5])
    cmd = guide.search(arts, "print users")[0]
    assert "print users" in cmd.title or "print users" in cmd.text.lower()
    assert any(a.id.startswith("gam:all:") for a in arts)       # GAM's full reference
    assert guide.search(arts, "zzzzqqq") == []
    assert "<span class='hl'>hold</span>" in guide.highlight("<p>a hold</p>", "hold")
    assert guide._builder_query("gam user <email> vacation on|off") == "user vacation on"
    cats = {c for c, _cmd, _d in gam_ref.COMMANDS}
    assert {"Users", "Groups", "Chromebooks", "Gmail", "Drive", "Classroom", "Vault"} <= cats
    page = guide.export_html(arts[:20])
    assert page.startswith("<!doctype html>") and "gambit:" not in page and "<input" in page
