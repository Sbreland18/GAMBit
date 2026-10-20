"""Round 24: saved user searches keep every org unit, and can be run, edited and deleted."""

from gambit import saved_searches as ss


def test_spec_keeps_all_org_units():
    fav = {"kind": "search", "value": "search:1", "label": "Schools",
           "spec": {"mode": "In org unit(s)", "ous": ["/A", "/B", "/C"], "children": False}}
    s = ss.spec_of(fav)
    assert s["ous"] == ["/A", "/B", "/C"] and s["children"] is False
    assert ss.describe(s) == "Users in /A, /B, /C (not sub-org units)"


def test_old_saved_search_is_a_custom_query():
    s = ss.spec_of({"kind": "search", "value": "isSuspended=true", "label": "x"})
    assert s["mode"] == "Custom query" and s["value"] == "isSuspended=true"


def test_custom_field_description():
    s = ss.spec_of({"spec": {"mode": "Custom field", "cf_field": "S.Grade", "cf_op": "is",
                             "value": "7th Grade", "ous": ["/Students"]}})
    assert ss.describe(s) == "S.Grade is “7th Grade” in /Students"


def test_keys_are_unique():
    assert ss.new_key() != ss.new_key()
