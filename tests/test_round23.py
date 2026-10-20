"""Round 23: custom user fields (custom schemas) in lists, exports, Lookup and search."""

import pytest

from gambit import custom_fields as cf

SCHEMAS = ("schemaId,schemaName,displayName,fields.0.displayName,fields.0.fieldName,"
           "fields.0.fieldType,fields.0.indexed,fields.0.multiValued,fields.1.displayName,"
           "fields.1.fieldName,fields.1.fieldType,fields.1.indexed,fields.1.multiValued,"
           "fields.2.fieldName,fields.2.fieldType,fields.2.indexed,fields.2.multiValued\n"
           "S1,Student_Information,Student Information,Grade,Grade,STRING,True,False,"
           "Student ID,Student_ID,STRING,True,False,Chrono_Grade,INT64,False,False\n"
           "S2,Bus,,,Route,STRING,True,True,,,,,,,,,\n")


@pytest.fixture(autouse=True)
def fresh():
    cf.save({"schemas": cf.parse_schemas(SCHEMAS),
             "columns": ["Student_Information.Student_ID", "Student_Information.Grade"],
             "headers": "friendly", "in_lists": True})
    yield
    cf.save({})


def test_parse_schemas():
    s = cf.parse_schemas(SCHEMAS)
    assert list(s) == ["Student_Information", "Bus"]
    f = s["Student_Information"]["fields"]
    assert [x["name"] for x in f] == ["Grade", "Student_ID", "Chrono_Grade"]
    assert f[2]["type"] == "INT64" and not f[2]["indexed"]
    assert s["Bus"]["fields"][0]["multi"]


def test_args_and_with_custom():
    assert cf.args() == ["custom", "Student_Information"]
    cmd = cf.with_custom(["print", "users", "fields", "primaryemail"])
    assert cmd[-2:] == ["custom", "Student_Information"]
    assert cf.with_custom(cmd) == cmd                       # not twice
    cf.save({**cf.config(), "in_lists": False})
    assert cf.args() == [] and cf.args(force=True)


def test_tidy_keeps_chosen_fields_in_order_and_joins_multi():
    h = ["primaryEmail", "customSchemas.Student_Information.Grade",
         "customSchemas.Student_Information.Chrono_Grade",
         "customSchemas.Student_Information.Student_ID",
         "customSchemas.Bus.Route.0.value", "customSchemas.Bus.Route.0.type",
         "customSchemas.Bus.Route.1.value"]
    rows = [["a@x", "7th Grade", "5", "001x48x9x", "12", "work", "14"]]
    nh, nr = cf.tidy(h, rows)
    assert nh == ["primaryEmail", "Student ID", "Grade", "Route"]
    assert nr == [["a@x", "001x48x9x", "7th Grade", "12; 14"]]
    cf.save({**cf.config(), "headers": "gam"})
    nh, _ = cf.tidy(h, rows)
    assert nh[1:3] == ["Student_Information.Student_ID", "Student_Information.Grade"]


def test_missing_chosen_field_still_gets_a_column():
    nh, nr = cf.tidy(["primaryEmail", "customSchemas.Student_Information.Grade"],
                     [["a@x", "7th Grade"]])
    assert nh == ["primaryEmail", "Student ID", "Grade"] and nr == [["a@x", "", "7th Grade"]]


def test_clashing_label_gets_schema_prefix():
    cf.save({**cf.config(), "columns": ["Student_Information.Grade"]})
    nh, _ = cf.tidy(["primaryEmail", "Grade", "customSchemas.Student_Information.Grade"],
                    [["a", "b", "c"]])
    assert nh[-1] == "Student Information: Grade"


def test_server_query_only_for_exact_indexed():
    assert cf.server_query("Student_Information.Grade", "is", "7th Grade") == \
        "Student_Information.Grade='7th Grade'"
    assert cf.server_query("Student_Information.Grade", "contains", "7") == ""
    assert cf.server_query("Student_Information.Chrono_Grade", "is", "5") == ""  # not indexed


def test_matches_raw_and_tidy_rows():
    raw = {"primaryEmail": "a", "customSchemas.Student_Information.Grade": "7th Grade"}
    assert cf.matches(raw, "Student_Information.Grade", "is", "7th grade")
    assert cf.matches(raw, "Student_Information.Grade", "contains", "7th")
    assert not cf.matches(raw, "Student_Information.Student_ID", "notempty", "")
    assert cf.matches({"Grade": "8th Grade"}, "Student_Information.Grade", "starts", "8")
    multi = {"customSchemas.Bus.Route.0.value": "12", "customSchemas.Bus.Route.1.value": "14"}
    assert cf.matches(multi, "Bus.Route", "is", "14")


def test_learn_from_user_columns():
    s = cf.schemas_from_users("primaryEmail,customSchemas.X.A,customSchemas.X.B.0.value\n")
    assert [f["name"] for f in s["X"]["fields"]] == ["A", "B"] and s["X"]["fields"][1]["multi"]


def test_lookup_card_values():
    vals = cf.tidy_dict({"primaryEmail": "a", "customSchemas.Student_Information.Grade": "7th",
                         "customSchemas.Student_Information.Student_ID": "9"})
    assert vals == [("Student ID", "9"), ("Grade", "7th")]


def test_deploy_group():
    from gambit import deploy
    assert "customfields/config" in deploy.GROUPS["customfields"][1]
