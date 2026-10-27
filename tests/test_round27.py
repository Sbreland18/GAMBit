"""Round 27: new/copy/delete roles with GAMbit sign-in on (People live on Users & access)."""

import copy


def test_new_role_with_signin_on(qapp, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    from gambit import team
    from gambit.ui import roles_dialog
    data = {"roles": copy.deepcopy(team.BUILTIN_ROLES), "people": {"a@x": "Help desk"},
            "default_role": "No access", "signed": True}
    monkeypatch.setattr(team, "load_roles", lambda: copy.deepcopy(data))
    saved = {}
    monkeypatch.setattr(team, "save_roles", lambda d: saved.update(d))
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Chromebook Lookup", True)))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    import gc
    d = roles_dialog.RolesDialog(None, ["Home", "Users"], [])
    gc.collect()
    d._new_role()                          # used to crash: the hidden People widgets were gone
    d._copy_role()                         # "Chromebook Lookup" again → already exists
    d.roles.setCurrentRow(d.roles.count() - 1)
    d._delete_role()
    d._new_role()
    d._save()
    assert "Chromebook Lookup" in saved["roles"]
    d.close()
