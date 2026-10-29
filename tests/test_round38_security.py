"""Round 38 – security fixes. Each test pins one fix so it can't quietly come undone."""

import io
import json
import os
import tarfile

import pytest

from gambit.settings import settings


@pytest.fixture(autouse=True)
def clean():
    for k in ("setup/seen", "tour/seen", "whatsnew/off"):
        settings.set(k, True)
    settings.check_updates_on_start = False
    settings.set("safety/dry_run", False)
    settings.set("helpdesk/on", False)
    yield
    settings.set("helpdesk/on", False)


# ------------------------------------------------------------- seals ---
def test_seal_detects_any_change_and_unknown_keys():
    from gambit import seal
    rec = seal.sign("t", {"a": 1, "cmds": [["info", "domain"]], "progress": 0}, ["a", "cmds"])
    assert seal.check("t", rec, ["a", "cmds"]) is not None
    assert seal.check("t", {**rec, "progress": 5}, ["a", "cmds"]) is not None  # mutable
    assert seal.check("t", {**rec, "a": 2}, ["a", "cmds"]) is None
    assert seal.check("other", rec, ["a", "cmds"]) is None          # kind is bound in
    bad = {**rec, "seal": {**rec["seal"], "kid": "nobody"}}
    assert seal.check("t", bad, ["a", "cmds"]) is None
    assert seal.check("t", {k: v for k, v in rec.items() if k != "seal"}) is None
    assert seal.may_run(None, [["info", "domain"]])                  # unsigned: refused


# ------------------------------------------------------ run later ---
def test_queue_refuses_passwords_and_skips_tampered_items(team_dir):
    from gambit import change_queue as cq, secret_args
    cq.save_queue([])
    for cmd in (["update", "user", "a@s.org", "password", "Hunter2!x"],
                ["update", "user", "a@s.org", "password", secret_args.NEWPW]):
        with pytest.raises(cq.QueueRefused):
            cq.add([cmd], "2000-01-01T00:00", "pw", "me")
    it = cq.add([["update", "user", "a@s.org", "suspended", "on"]], "2000-01-01T00:00",
                "A", "me", profile="")
    q = cq.queue()
    q[0]["commands"] = [["delete", "user", "boss@s.org"]]           # edited in the folder
    cq.save_queue(q)
    ran = []
    lines = cq.run_due(lambda *_: None, lambda c, t=0: (ran.append(c), (0, ""))[1])
    assert ran == [] and any("not run" in ln for ln in lines)
    assert cq.queue()[0].get("blocked")
    assert it["id"] == cq.queue()[0]["id"]


def test_queue_runs_signed_item(team_dir):
    from gambit import change_queue as cq
    cq.save_queue([])
    cq.add([["update", "user", "a@s.org", "suspended", "on"]], "2000-01-01T00:00", "A", "me",
           profile="")
    ran = []
    cq.run_due(lambda *_: None, lambda c, t=0: (ran.append(c), (0, ""))[1])
    assert ran == [["update", "user", "a@s.org", "suspended", "on"]]


# ------------------------------------------------------ offboarding ---
def test_offboarding_unsigned_plan_doesnt_run(team_dir):
    from gambit import offboard
    before = {"groups": [], "licenses": [], "ou": "/Staff", "name": "K", "gal": True,
              "complete": True}
    rec = offboard.build("k@s.org", "", before, offboard.DEFAULTS, lambda n=20: "x")
    for st in rec["stages"]:
        st["due"] = "2000-01-01"
    offboard.save(rec)                                    # not signed
    ran = []
    lines = offboard.run_due(lambda *_: None, lambda c, t=0: (ran.append(c), (0, ""))[1])
    assert ran == [] and any("wasn't run" in ln for ln in lines)


# --------------------------------------------------- policy / rules ---
def test_group_rule_and_temp_account_need_signatures():
    from gambit import group_rules as gr, temp_accounts as ta
    r = {"id": "r1", "group": "g@s.org", "ous": ["/Staff"], "enabled": True}
    for k in gr.SEAL_FIELDS:
        r.setdefault(k, r.get(k, ""))
    assert gr.verify(r) is None
    s = gr.sign_rule(dict(r))
    assert gr.verify(s) is not None
    assert gr.verify({**s, "group": "everyone@s.org"}) is None
    t = {"email": "t@s.org", "end": "2030-01-01", "status": "active"}
    assert ta.verify(t) is None
    t2 = ta.sign(dict(t))
    assert ta.verify(t2) is not None
    assert ta.verify({**t2, "end": "2000-01-01"}) is None


# ------------------------------------------------------ approvals ---
def test_email_reply_must_come_from_the_mailbox_owner():
    from gambit import email_approvals as ea
    row = {"From": "Boss <boss@s.org>", "Subject": "Re: [GAMbit approval ab12cd34 "
           "0123456789abcdef] x", "Body": "Approve – fine", "id": "m1"}
    got = ea.parse_reply(row, "boss@s.org")
    assert got["decision"] == "approve" and got["hash"] == "0123456789abcdef"
    assert ea.parse_reply(row, "other@s.org") is None
    two = {**row, "From": "boss@s.org, evil@x.org"}
    assert ea.parse_reply(two, "boss@s.org") is None
    assert ea.replies_args("boss@s.org")[:2] == ["user", "boss@s.org"]
    assert "in:sent" in " ".join(ea.replies_args("boss@s.org"))


def test_approval_bound_to_exact_commands_and_not_self(team_dir):
    from gambit import approval_policy as ap
    req = {"id": "r1", "by": "tech@s.org", "commands": [["update", "user", "a@s.org",
                                                         "suspended", "on"]]}
    a = ap.make_approval(req, "boss@s.org")
    assert ap.valid_approvers({**req, "approvals": [a]}) == ["boss@s.org"]
    changed = {**req, "commands": [["delete", "user", "a@s.org"]], "approvals": [a]}
    assert ap.valid_approvers(changed) == []
    forged = {**a, "who": "other@s.org"}                  # name changed after signing
    assert ap.valid_approvers({**req, "approvals": [forged]}) == []
    pol = {**ap.DEFAULT, "on": True, "two_person": ["delete"]}
    dreq = {**req, "commands": [["delete", "user", "a@s.org"]]}
    assert ap.needs_two(dreq, pol)
    mine = {**dreq, "approvals": [ap.make_approval(dreq, "tech@s.org")]}
    assert ap.valid_approvers(mine, pol) == []          # no approving your own request
    both = {**dreq, "approvals": [ap.make_approval(dreq, "tech@s.org"),
                                  ap.make_approval(dreq, "boss@s.org")]}
    assert ap.valid_approvers(both, pol) == ["boss@s.org"]
    assert ap.valid_approvers({**req, "approvals": ["boss@s.org"]}) == []   # old style


def test_request_hides_passwords(team_dir):
    from gambit import secret_args, team
    req = team.new_request([["update", "user", "a@s.org", "password", "Hunter2!x"]],
                           "reset", by="me@s.org")
    flat = json.dumps(req)
    assert "Hunter2!x" not in flat and secret_args.NEWPW in flat


def test_newpw_fill_collects_once():
    from gambit import secret_args
    got = []
    out = secret_args.fill(["update", "user", "a@s.org", "password", secret_args.NEWPW], got)
    assert got and got[0][0] == "a@s.org" and out[-1] == got[0][1]
    assert secret_args.NEWPW not in out
    assert secret_args.literal_passwords(["x", "password", "abc"])
    assert not secret_args.literal_passwords(["x", "password", "random"])
    assert secret_args.without_passwords(["x", "password", "abc"])[-1] == secret_args.NEWPW
    pw = secret_args.readable_password()
    assert len(pw) >= 12 and any(c.isdigit() for c in pw)


# ------------------------------------------- command classification ---
@pytest.mark.parametrize("args", [
    ["csv", "x.csv", "gam", "delete", "user", "~email"],
    ["select", "other", "delete", "user", "a@s.org"],
    ["redirect", "stdout", "o.txt", "delete", "user", "a@s.org"],
])
def test_wrappers_dont_hide_deletes(args):
    from gambit import team
    assert "delete" in team.categorize(args)


def test_helpdesk_refuses_wrapped_and_batch():
    from gambit.gam_runner import blocked_reason
    settings.set("helpdesk/on", True)
    assert blocked_reason(["batch", "x.txt"])
    assert blocked_reason(["csv", "x.csv", "gam", "delete", "user", "~e"])
    assert not blocked_reason(["info", "user", "a@s.org"])


def test_unknown_verbs_count_as_changes():
    from gambit import activity
    assert activity.is_change(["frobnicate", "user", "a@s.org"])
    assert not activity.is_change(["print", "users"])


def test_ticket_password_never_sent_to_the_locked_account():
    from gambit.tools import ticket_auto
    assert ticket_auto.recipient({"for_email": "kid@s.org"}, "kid@s.org", {}) == ""


# ----------------------------------------------------- deploy files ---
def test_deploy_never_touches_security_keys(tmp_path):
    from gambit import deploy
    for k in ("access/pinned", "auth/emergency", "seal/trusted", "helpdesk/pin",
              "update/installer_path", "deploy/anything"):
        assert not deploy.allowed_key(k)
    p = tmp_path / "gambit-deploy.json"
    settings.set("ui/density", "")
    p.write_text(json.dumps({"gambit_deploy": 1, "created": "x1", "overwrite": True,
                             "settings": {"access/pinned": "{}", "ui/density": "compact"}}))
    changed = deploy.apply_file(str(p))
    assert "access/pinned" not in changed and "ui/density" not in changed


# ----------------------------------------------------------- updates ---
def test_release_metadata_checks():
    from gambit import release_sign
    from gambit.version import GITHUB_REPO
    good = {"version": "9.9", "sha256": "a" * 64,
            "url": f"https://github.com/{GITHUB_REPO}/releases/download/v9.9/GAMbit.exe"}
    assert release_sign.problem(good) == "" or "signed" in release_sign.problem(good)
    assert release_sign.problem({**good, "url": "http://github.com/x"})
    assert release_sign.problem({**good, "url": "https://evil.example/GAMbit.exe"})
    assert release_sign.problem({**good, "url": "https://github.com/someone/else/releases/"
                                                 "download/v1/x.exe"})
    assert release_sign.problem({**good, "sha256": ""})


def test_release_signature(monkeypatch):
    from gambit import release_sign
    from gambit.auth import crypto
    from gambit.version import GITHUB_REPO
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                           serialization.NoEncryption())
    pub = k.public_key().public_bytes(serialization.Encoding.Raw,
                                      serialization.PublicFormat.Raw)
    monkeypatch.setattr(release_sign, "keys", lambda: [pub])
    meta = {"version": "9.9", "sha256": "b" * 64,
            "url": f"https://github.com/{GITHUB_REPO}/releases/download/v9.9/GAMbit.exe"}
    signed = release_sign.sign(meta, priv)
    assert release_sign.problem(signed) == ""
    assert release_sign.problem({**signed, "sha256": "c" * 64})
    assert release_sign.problem(meta)
    assert crypto  # imported for the helper


def test_tar_with_escape_or_link_refused(tmp_path):
    from gambit.updaters import _safe_extract_tar
    for name, kind in (("../evil.txt", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            ti = tarfile.TarInfo(name)
            ti.type = kind
            if kind == tarfile.SYMTYPE:
                ti.linkname = "/etc/passwd"
            tf.addfile(ti, io.BytesIO(b"") if kind == tarfile.REGTYPE else None)
        buf.seek(0)
        with tarfile.open(fileobj=buf) as tf, pytest.raises(RuntimeError):
            _safe_extract_tar(tf, str(tmp_path / "out"))
    assert not (tmp_path / "evil.txt").exists()


def test_download_hash_mismatch_deletes_file(tmp_path, monkeypatch):
    from gambit import net

    class Resp(io.BytesIO):
        headers = {"Content-Length": "5"}
        def geturl(self):
            return "https://github.com/x"
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    monkeypatch.setattr(net, "_open", lambda *a, **k: Resp(b"hello"))
    dest = tmp_path / "f.bin"
    with pytest.raises(Exception):
        net.download("https://github.com/x", str(dest), sha256="0" * 64)
    assert not dest.exists()


# ----------------------------------------------------------- secrets ---
def test_secret_keys_recognised():
    from gambit import secrets_store as ss
    for k in ("ticketing/token", "sis_api/client_secret", "alerts/webhook",
              "assistant/api_key", "helpdesk/pin"):
        assert ss.is_secret(k), k
    for k in ("ui/density", "ticketing/url", "team/folder"):
        assert not ss.is_secret(k), k


def test_secrets_not_in_plain_text_settings():
    from gambit import secrets_store as ss
    settings.set("ticketing/token", "tok-SECRET-123")
    raw = settings._s.value("ticketing/token")
    try:
        assert settings.get("ticketing/token") == "tok-SECRET-123"
        assert raw.startswith(ss.PREFIX) and "tok-SECRET-123" not in raw
    finally:
        settings.set("ticketing/token", "")


def test_problem_report_hides_secrets():
    from gambit import support
    settings.set("ticketing/token", "tok-SECRET-456")
    try:
        text = json.dumps(support._settings_dump())
        assert "ticketing/token" in text and "tok-SECRET-456" not in text
    finally:
        settings.set("ticketing/token", "")


def test_backup_with_secrets_needs_password(tmp_path):
    from gambit import deploy
    settings.set("ticketing/token", "tok-SECRET-789")
    try:
        p = str(tmp_path / "b.zip")
        with pytest.raises(Exception):
            deploy.backup(p, include_secrets=True)
        deploy.backup(p, include_secrets=True, password="correct horse battery")
        import zipfile
        with zipfile.ZipFile(p) as z:
            blob = b"".join(z.read(n) for n in z.namelist())
        assert b"tok-SECRET-789" not in blob
        assert deploy.needs_password(p)
        with pytest.raises(deploy.BackupPasswordNeeded):
            deploy.restore(p, password="wrong")
    finally:
        settings.set("ticketing/token", "")


# ---------------------------------------------------------- rich text ---
def test_html_cleaning():
    from gambit.ui import safe_html as sh
    out = sh.clean('<b>x</b><img src="\\\\evil\\s"><a href="file:///c:/x">y</a>'
                   '<script>alert(1)</script><a href="https://ok.org">z</a>')
    assert "<b>x</b>" in out and "img" not in out and "script" not in out
    assert "alert" not in out and "evil" not in out
    assert "<" not in sh.clean("<script>never closed").replace("&lt;", "")
    assert "file:" not in out and 'href="https://ok.org"' in out


def test_label_guard_cleans_rich_text(qapp):
    from PySide6.QtWidgets import QLabel
    lab = QLabel('<b>hi</b><img src="//evil/x.png">')
    assert "img" not in lab.text()
    lab.setText('<i>a</i><a href="javascript:x">b</a>')
    assert "javascript" not in lab.text()


def test_csv_formula_cells_neutralised():
    from gambit import csv_safe
    assert csv_safe.cell("=HYPERLINK(\"x\")").startswith("'")
    assert csv_safe.cell("+cmd").startswith("'") and csv_safe.cell("@sum").startswith("'")
    assert csv_safe.cell("-5") == "-5" and csv_safe.cell("12.5") == "12.5"
    assert csv_safe.cell("plain") == "plain"


# ---------------------------------------------------------- assistant ---
@pytest.mark.parametrize("args,ok", [
    (["print", "users"], True),
    (["info", "user", "a@s.org"], True),
    (["print", "users", "todrive"], False),
    (["user", "a@s.org", "print", "messages"], False),
    (["csv", "x.csv", "gam", "print", "users"], False),
    (["update", "user", "a@s.org"], False),
    (["config", "x", "print", "users"], False),
])
def test_assistant_readonly_allowlist(args, ok):
    from gambit.integrations import assistant
    assert assistant.readonly(args) is ok


def test_pseudonymize():
    from gambit.integrations import assistant
    t = assistant.pseudonymize("a@s.org did x to b@s.org; a@s.org again")
    assert "a@s.org" not in t and t.count("person1@s.org") == 2 and "person2@s.org" in t


# -------------------------------------------------------- sign-in lock ---
def test_machine_lock_forces_sign_in(tmp_path, monkeypatch):
    from gambit.auth import access
    lock = tmp_path / "lock.json"
    monkeypatch.setenv("GAMBIT_SIGNIN_LOCK", str(lock))
    assert access.machine_lock() is None
    lock.write_text(json.dumps({"keys": ["k1"]}))
    assert access.required()
    assert access.lock_allows("k1") and not access.lock_allows("k2")
    lock.write_text("not json")
    assert access.machine_lock() == {"keys": []} and access.required()


def test_unknown_role_falls_back_to_lookups_only():
    from gambit import team
    assert team.LOOKUP_ONLY
    ok, _missing, _ask = team.check(["delete", "user", "a@s.org"], team.LOOKUP_ONLY_ROLE)
    assert not ok
    ok, _m, _a = team.check(["print", "users"], team.LOOKUP_ONLY_ROLE)
    assert ok


# -------------------------------------------------------- temp folders ---
def test_private_temp_folder():
    from gambit import tempfiles
    d = tempfiles.folder()
    assert os.path.isdir(d) and os.path.basename(d).startswith("GAMbit-")
    if os.name != "nt":
        assert (os.stat(d).st_mode & 0o077) == 0


# ------------------------------------------- update dot in the sidebar ---
def test_update_dot_marks_settings_not_the_last_item(qapp, fake_gam):
    from PySide6.QtCore import Qt
    from gambit.ui.main_window import MainWindow
    from gambit import user_prefs as up
    settings.set("connection/auto_test", False)
    if "Settings & Updates" not in up.pinned():
        up.toggle_pin("Settings & Updates")      # in My pages → not at the bottom any more
    w = MainWindow()
    last = w.nav.item(w.nav.count() - 1)
    assert last.data(Qt.UserRole + 2) != "Settings & Updates"     # the reported case
    last_page, last_text = last.data(Qt.UserRole + 2), last.text()
    w.notify("GAMbit 9.9 is available")

    def rows():
        return [(w.nav.item(r).data(Qt.UserRole + 2), w.nav.item(r).text())
                for r in range(w.nav.count())]
    if last_page != "Settings & Updates":
        assert (last_page, last_text) in rows()           # untouched
    sett = [t for p, t in rows() if p == "Settings & Updates"]
    assert sett and all(t.endswith("●") for t in sett)
    assert all(not t.startswith("Settings & Updates") for p, t in rows()
               if p != "Settings & Updates")
    w.build_nav()                                         # survives a rebuild
    assert all(t.endswith("●") for p, t in rows() if p == "Settings & Updates")
    row = next(r for r in range(w.nav.count())
               if w.nav.item(r).data(Qt.UserRole + 2) == "Settings & Updates"
               and not w.nav.item(r).isHidden())
    w.nav.setCurrentRow(row)
    qapp.processEvents()
    assert w.current_page() is w.pages["Settings & Updates"]
    w.close()
    up.toggle_pin("Settings & Updates")
