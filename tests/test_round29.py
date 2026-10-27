"""Round 29: My pages & folding, tray, what's new, recent, print card, check everything,
ticket-first, before → after, digest, practice mode, contrast & shortcuts, feedback,
customizable Home."""

import datetime
import json

import pytest

from gambit import (change_preview as cp, digest, home_layout as hl, person_check as pc,
                    user_prefs as up, whats_new)
from gambit.settings import settings


@pytest.fixture(autouse=True)
def clean():
    keys = [up.PIN_KEY, up.USAGE_KEY, up.FOLD_KEY, up.RECENT_KEY, up.PRACTICE_KEY,
            hl.LAYOUT_KEY, hl.QUICK_KEY, hl.TILES_KEY, hl.LINKS_KEY, whats_new.SEEN_KEY,
            "safety/test_ou", "safety/test_user", digest.SEATS_KEY]
    for k in keys:
        settings.set(k, "")
    yield
    for k in keys:
        settings.set(k, "")


# --------------------------------------------------------------- prefs ---
def test_pins_usage_and_my_pages():
    assert up.toggle_pin("Users") and up.toggle_pin("Groups")
    assert not up.toggle_pin("Users")
    for _ in range(5):
        up.bump("Chromebooks")
    up.bump("Email")
    pins, freq = up.my_pages(["Users", "Groups", "Chromebooks", "Email"])
    assert pins == ["Groups"] and freq == ["Chromebooks"]       # Email used < 3 times
    pins, freq = up.my_pages(["Users"])                         # role hides the rest
    assert pins == [] and freq == []
    assert up.toggle_section("PEOPLE") and "PEOPLE" in up.collapsed()
    assert not up.toggle_section("PEOPLE")


def test_recent():
    up.add_recent("user", "a@x", "Ann")
    up.add_recent("device", "SN1")
    up.add_recent("user", "A@x", "Ann")                         # moves to the top, no dup
    r = up.recent()
    assert [x["value"] for x in r] == ["A@x", "SN1"]
    assert up.recent_label(r[0]) == "🕘 👤 Ann  <A@x>"
    up.add_recent("nonsense", "x")
    assert len(up.recent()) == 2


def test_practice_allows():
    users = {"t@x": {"ou": "/Test/Kids"}, "real@x": {"ou": "/Students"}}
    assert not up.practice_allows(["update", "user", "t@x", "suspended", "on"], users)
    settings.set("safety/test_ou", "/Test")
    settings.set("safety/test_user", "solo@x")
    ok = up.practice_allows
    assert ok(["update", "user", "t@x", "suspended", "on"], users)
    assert ok(["update", "user", "solo@x", "password", "x"], users)
    assert not ok(["update", "user", "real@x", "suspended", "on"], users)
    assert not ok(["update", "user", "t@x", "ou", "/Students"], users)   # moving out
    assert ok(["update", "user", "t@x", "ou", "/Test/Other"], users)
    assert not ok(["cros_sn", "SN1", "update", "notes", "x"], users)
    assert not ok(["all", "users", "update", "user", "suspended", "on"], users)


def test_whats_new():
    settings.set("setup/seen", False)
    settings.set("gam/dir", "")
    whats_new.first_run_check()                   # brand new install: nothing to show
    assert whats_new.unseen() == []
    settings.set(whats_new.SEEN_KEY, json.dumps(["tray"]))
    assert len(whats_new.unseen()) == len(whats_new.ENTRIES) - 1
    whats_new.mark_seen(["recent"])
    assert {"tray", "recent"} <= whats_new.seen()


# --------------------------------------------------------- person check ---
MAP = [{"path": "/Students", "type": "students", "school": "", "grade": ""},
       {"path": "/Graduates", "type": "former_students", "school": "", "grade": ""}]


def test_person_check_findings():
    today = datetime.date(2026, 10, 20)
    u = {"primaryEmail": "k@x", "orgUnitPath": "/Students/7", "suspended": "True",
         "suspensionReason": "ADMIN", "changePasswordAtNextLogin": "True",
         "lastLoginTime": "Never", "creationTime": "2026-09-01T00:00:00Z",
         "isEnforcedIn2Sv": "True", "isEnrolledIn2Sv": "False", "Licenses": ""}
    rec = [{"serialNumber": "SN9", "recentUsers.0.email": "k@x"}]
    f = pc.check("k@x", u, [], rec, today, MAP)
    probs = {x["problem"]: x for x in f}
    assert f[0]["level"] == "bad"
    assert probs["The account is suspended"]["commands"] == [
        ["update", "user", "k@x", "suspended", "off"]]
    assert probs["No Chromebook is assigned to them"]["commands"] == [
        ["cros_sn", "SN9", "update", "user", "k@x"]]
    assert "2-Step Verification is required but not set up" in probs
    assert "They must choose a new password at the next sign-in" in probs
    assert "No Google Workspace license" not in probs          # suspended: not relevant
    assert not any("never signed in" in p for p in probs)      # suspended: no reset nag
    dis = [{"serialNumber": "SN1", "annotatedUser": "k@x", "status": "DISABLED",
            "lastSync": "2026-10-19"}]
    good = {"primaryEmail": "k@x", "orgUnitPath": "/Students", "suspended": "False",
            "lastLoginTime": "2026-10-19T00:00:00Z", "creationTime": "2020-01-01"}
    f2 = pc.check("k@x", good, dis, [], today, MAP)
    assert f2[0]["commands"] == [["cros_sn", "SN1", "update", "action", "reenable"]]
    nolic = pc.check("k@x", {**good, "Licenses": ""}, [{**dis[0], "status": "ACTIVE"}], [],
                     today, MAP)
    assert any(x["problem"] == "No Google Workspace license" for x in nolic)
    ok = pc.check("k@x", good, [{**dis[0], "status": "ACTIVE"}], [], today, MAP)
    assert ok[0]["level"] == "ok"
    assert pc.check("k@x", None, [], [], today, MAP)[0]["problem"] == "No Google account found"
    former = pc.check("k@x", {**good, "orgUnitPath": "/Graduates"}, [], [], today, MAP)
    assert any(x["problem"] == "Active account in a former org unit" for x in former)
    assert "– fixed" in pc.summary("k@x", f, ["The account is suspended"])


# ------------------------------------------------------- before / after ---
def test_change_preview():
    p = cp.parse(["update", "user", "a@x", "ou", "/S/8", "suspended", "off",
                  "Student_Information.Grade", "8th Grade", "password", "secret"])
    assert [(c["field"], c["after"]) for c in p] == [
        ("Org unit", "/S/8"), ("Suspended", "False"),
        ("Student_Information.Grade", "8th Grade"), ("Password", "(a new password)")]
    assert cp.parse(["cros_sn", "SN1", "update", "user", "b@x", "action", "disable"])[1][
        "after"] == "DISABLED"
    calls = []

    def run_csv(a):
        calls.append(a)
        if a[0] == "print":
            assert a[-2:] == ["custom", "Student_Information"]
            return 0, [{"primaryEmail": "a@x", "orgUnitPath": "/S/7", "suspended": "False",
                        "customSchemas.Student_Information.Grade": "7th Grade"}], ""
        return 0, [{"serialNumber": "SN1", "annotatedUser": "", "status": "ACTIVE"}], ""
    rows = cp.preview([["update", "user", "a@x", "ou", "/S/8", "suspended", "off",
                        "Student_Information.Grade", "8th Grade"],
                       ["cros_sn", "SN1", "update", "user", "b@x"],
                       ["create", "group", "g@x"]], run_csv)
    by = {(r["target"], r["field"]): r for r in rows}
    assert by[("a@x", "Org unit")]["before"] == "/S/7"
    assert by[("a@x", "Suspended")]["same"]
    assert by[("a@x", "Student_Information.Grade")]["before"] == "7th Grade"
    assert by[("SN1", "Assigned user")]["before"] == "(blank)"
    assert any(r["target"] == "" and r["after"] for r in rows)   # plain English for the rest


# ----------------------------------------------------------------- digest ---
def test_digest_low_licenses_and_sections():
    settings.set(digest.SEATS_KEY, "Education Plus = 1,000\nbad line\nOther = x")
    assert digest.seats() == {"education plus": 1000}
    assert digest.low_licenses({"Education Plus": 960, "Fundamentals": 5}) == [
        ("Education Plus", 960, 1000)]
    d = {"days": 7, "created": [], "leaving": [], "failed": [], "due": [], "pending": [],
         "bad_jobs": [], "dash": {}, "today": "2026-10-20", "by_tech": {"sb": 4, "jt": 9},
         "bg_failed": [{"key": "job:x", "label": "Move Chromebooks", "ended":
                        "2026-10-19T05:51:00", "summary": "2 failed"}], "bg_ok": 3,
         "low_licenses": [("Education Plus", 960, 1000)]}
    subject, body = digest.render(d)
    assert "to check" in subject
    assert "Move Chromebooks" in body and "960 of 1,000" in body
    assert body.index("jt: 9") < body.index("sb: 4")


# ------------------------------------------------------------ home layout ---
def test_home_layout_defaults_and_save():
    admin = [x["id"] for x in hl.layout(True) if x["on"]]
    tech = [x["id"] for x in hl.layout(False) if x["on"]]
    assert admin[0] == "status" and tech[0] == "lookup" and "glance" not in tech
    hl.save_layout([{"id": "notes", "on": True}, {"id": "recent", "on": False}])
    lay = hl.layout(True)
    assert lay[0] == {"id": "notes", "on": True} and len(lay) == len(hl.SECTIONS)
    assert not next(x for x in lay if x["id"] == "status")["on"]    # new ones start off
    hl.save_quick(["Approvals", "nope"])
    assert hl.quick() == ["Approvals"]
    settings.set(hl.LINKS_KEY, "Admin = admin.google.com\nShare = \\\\srv\\it\nbad")
    assert hl.links() == [("Admin", "https://admin.google.com"), ("Share", "\\\\srv\\it")]
    hl.reset()
    assert hl.quick() == hl.QUICK_DEFAULT


# -------------------------------------------------------------- the window ---
def test_window_sidebar_home_and_tray(qapp, fake_gam):
    settings.set("tour/seen", True)
    settings.set("setup/seen", True)
    up.set_pinned(["Device history"])
    from gambit.ui.main_window import MainWindow
    w = MainWindow()
    texts = [w.nav.item(i).text() for i in range(w.nav.count())]
    assert "▾ My pages" in texts
    i = texts.index("▾ My pages")
    assert texts[i + 1] == "Device history"
    # folding PEOPLE hides its pages but not the heading
    row = texts.index("▾ People")
    w._nav_clicked(w.nav.item(row))
    users_row = next(r for r, s in w._row_section.items() if s == "PEOPLE")
    assert w.nav.item(users_row).isHidden() and not w.nav.item(row).isHidden()
    w._nav_clicked(w.nav.item(row))
    assert not w.nav.item(users_row).isHidden()
    w.toggle_pin("Device history")
    assert "▾ My pages" not in [w.nav.item(i).text() for i in range(w.nav.count())]
    # go() still works after rebuilding
    w.go("Device history")
    assert w.current_page() is w.pages["Device history"]
    # home: customize to notes + recent only
    hl.save_layout([{"id": "notes", "on": True}, {"id": "recent", "on": True}])
    home = w.pages["Home"]
    home.arrange()
    assert home.sections["notes"].isVisibleTo(home) or not home.isVisible()
    assert "notes" in home._on and "glance" not in home._on
    w.remember("device", "SN77")
    assert up.recent()[0]["value"] == "SN77"
    # no system tray when offscreen: closing really closes
    assert not w.tray.active
    w.close()


def test_print_card_html():
    from gambit.ui.print_card import card_html
    h = card_html("Kid A", "k@x", "Blue-Tiger-42", "SN1", "HMS", qr=False, size="half")
    assert h.count("k@x") == 2 and "Blue-Tiger-42" in h and "✂" in h
    assert "&lt;" in card_html("<b>", "a@x", qr=False)


def test_contrast_css():
    from gambit.ui.theme import contrast_css
    assert "#ffbf00" in contrast_css("light") and "#000000" in contrast_css("dark")
