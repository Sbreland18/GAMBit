from gambit import activity, onboard, sis, signature
from gambit.gam_runner import display_command


def _staff_changes(tmp_path):
    p = tmp_path / "staff.csv"
    p.write_text("Employee ID,First Name,Last Name,Email,Building,Title,Department,Status,"
                 "Supervisor Email\n"
                 "E1,Tom,Brady,,Central,Math Teacher,Math,Active,kwhite@school.org\n"
                 "E3,Amy,Ng,,North,Custodian,Facilities,Active,\n")
    exp = sis.load_export(str(p), "Staff sheet / HR export")
    rules = sis.Rules.for_staff(domain="school.org")
    people = sis.people_from_export(exp, sis.guess_mapping(exp.headers,
                                                           "Staff sheet / HR export"), rules)
    return {c.email: c for c in sis.plan(people, [], rules)}


def test_group_rules():
    m = onboard.parse_groups("* = allstaff\nCentral = central-staff, k5@school.org\n"
                             "# comment\ncustodian = custodians")
    g = onboard.groups_for({"school": "Central", "title": "Math Teacher"}, m, "school.org")
    assert g == ["allstaff@school.org", "central-staff@school.org", "k5@school.org"]
    assert onboard.groups_for({"title": "CUSTODIAN"}, m, "") == ["allstaff", "custodians"]


def test_expand_adds_full_setup(tmp_path):
    ch = _staff_changes(tmp_path)
    opts = {**onboard.DEFAULTS, "enabled": True, "license": "1010020020",
            "groups": "* = allstaff\nCentral = central-staff",
            "welcome_fallback": "hr@school.org"}
    onboard.expand(list(ch.values()), opts, "school.org")
    tom = ch["tbrady@school.org"]
    cmds = tom.commands
    assert cmds[0][:2] == ["create", "user"]
    assert ["user", "tbrady@school.org", "add", "license", "1010020020"] in cmds
    assert ["update", "group", "central-staff@school.org", "add", "member", "user",
            "tbrady@school.org"] in cmds
    assert any(onboard.is_retryable(c) for c in cmds)
    mail = cmds[-1]
    assert mail[:3] == ["sendemail", "to", "kwhite@school.org"]
    body = mail[mail.index("message") + 1]
    assert tom.password in body and "Tom Brady" in body
    # the password never reaches the screen or the activity log
    assert tom.password not in display_command(mail)
    assert tom.password not in " ".join(activity.mask(mail))
    # no supervisor on the sheet → fallback address
    amy = ch["ang@school.org"]
    assert amy.commands[-1][2] == "hr@school.org"
    assert "central-staff@school.org" not in str(amy.commands)


def test_off_by_default(tmp_path):
    ch = _staff_changes(tmp_path)
    onboard.expand(list(ch.values()), dict(onboard.DEFAULTS), "school.org")
    assert len(ch["tbrady@school.org"].commands) == 1


def test_signature_retry_queue(qapp):
    onboard._save_queue([])
    args = signature.gam_args("x@school.org", "<b>{FullName}</b>")
    assert "replace" in args and "FullName" in args
    onboard.queue_retry("x@school.org", args, "email signature")
    assert len(onboard.pending()) == 1
    lines = onboard.run_retries(log=lambda *_: None, run_text=lambda a, t: (1, "not ready"))
    assert lines == [] and onboard.pending()[0]["tries"] == 1
    lines = onboard.run_retries(log=lambda *_: None, run_text=lambda a, t: (0, ""))
    assert "done on retry" in lines[0] and onboard.pending() == []


def test_signature_preview():
    html = signature.render(signature.SIGNATURE_TEMPLATE,
                            {"name": "A <B>", "email": "a@s.org", "title": ""})
    assert "A &lt;B&gt;" in html and "{Title}" not in html and "{RT}" not in html


def test_scheduled_staff_sync_runs_onboarding(qapp, fake_gam, tmp_path):
    import json
    from gambit import rostersync_run
    from gambit.settings import settings
    sheet = tmp_path / "hr.csv"
    sheet.write_text("Employee ID,First Name,Last Name,Email,Building,Title,Department,Status,"
                     "Supervisor Email\n"
                     "E1,Tom,Brady,,Central,Math Teacher,Math,Active,kwhite@school.org\n")
    settings.set("sis/profiles", json.dumps({"HR": {
        "path": str(sheet), "format": "Staff sheet / HR export",
        "rules": {"kind": "staff", "domain": "school.org", "email_template": "{f}{last}@{domain}",
                  "ou_template": "/Staff/{school}", "managed_root": "/Staff",
                  "missing_means_withdrawn": False},
        "schedule": {"apply": ["create", "update", "reactivate"]}}}))
    settings.set("schedule/out", str(tmp_path / "out"))
    onboard.save_options({**onboard.DEFAULTS, "enabled": True, "license": "1010020020",
                          "groups": "Central = central-staff"})
    try:
        assert rostersync_run.run("HR", log=lambda *_: None) == 0
    finally:
        onboard.save_options(dict(onboard.DEFAULTS))
    calls = fake_gam.calls()
    i = next(n for n, c in enumerate(calls) if c.startswith("create user tbrady@school.org"))
    after = calls[i + 1:]
    assert any(c.startswith("user tbrady@school.org add license") for c in after)
    assert any("update group central-staff@school.org add member" in c for c in after)
    assert any(c.startswith("user tbrady@school.org signature") for c in after)
    assert any(c.startswith("sendemail to kwhite@school.org") for c in after)
