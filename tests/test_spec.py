def test_spec_bundles_lazily_imported_pages():
    import os
    spec = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "GAMbit.spec"),
                encoding="utf-8").read()
    assert 'collect_submodules("gambit")' in spec and "GAMBIT_MODULES" in spec


def test_every_lazy_page_resolves():
    from gambit.ui.main_window import PAGES
    for name, ref in PAGES:
        assert ref.cls.__name__ == ref.__name__, name
