"""Round 40 – SSO certificate watch, email domain check, tamper-evident activity log,
Spanish printouts, archive-then-delete and the deletion record."""

import base64
import datetime
import glob
import json
import os

import pytest

from gambit.settings import settings

UTC = datetime.timezone.utc


@pytest.fixture(autouse=True)
def clean():
    for k in ("setup/seen", "tour/seen", "whatsnew/off"):
        settings.set(k, True)
    settings.check_updates_on_start = False
    settings.set("safety/dry_run", False)
    for k in ("sso/cert_sources", "sso/last_check", "sso/notified", "maildns/last_check",
              "maildns/notified", "maildns/selectors", "printouts/wording", "printouts/lang"):
        settings.set(k, "")
    from gambit import retention
    for p in retention._record_paths()[:1]:          # this PC's copy (shared test AppData)
        if os.path.exists(p):
            os.remove(p)
    yield


@pytest.fixture
def alerts_sent(monkeypatch):
    sent = []
    from gambit import alerts
    monkeypatch.setattr(alerts, "notify", lambda text, title="", email=True:
                        sent.append((title, text)))
    return sent


# ================================================================ helpers ===
def _cert(days_left=200, start_days_ago=100, bits=2048, cn="ClassLink SAML"):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(UTC)
    c = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
         .public_key(key.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(now - datetime.timedelta(days=start_days_ago))
         .not_valid_after(now + datetime.timedelta(days=days_left))
         .sign(key, hashes.SHA256()))
    return c.public_bytes(serialization.Encoding.DER), key


def _metadata(*ders_with_use):
    kd = "".join(
        f'<md:KeyDescriptor{f" use={chr(34)}{u}{chr(34)}" if u else ""}><ds:KeyInfo>'
        f'<ds:X509Data><ds:X509Certificate>\n{base64.b64encode(d).decode()}\n'
        f'</ds:X509Certificate></ds:X509Data></ds:KeyInfo></md:KeyDescriptor>'
        for d, u in ders_with_use)
    return (f'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
            f'<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" '
            f'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" entityID="https://idp/x">'
            f'<md:IDPSSODescriptor>{kd}</md:IDPSSODescriptor></md:EntityDescriptor>'
            ).encode()


# ====================================================== 1. SSO certificates ===
def test_parse_metadata_pem_and_der():
    from gambit import sso_watch as sw
    a, _k = _cert(200)
    b, _k = _cert(30, cn="Encryption")
    certs = sw.parse(_metadata((a, "signing"), (b, "encryption")))
    assert [c.use for c in certs] == ["signing", "encryption"]
    assert certs[0].subject == "ClassLink SAML" and certs[0].key_bits == 2048
    pem = certs[0].pem().encode()
    assert [c.sha256 for c in sw.parse(pem)] == [certs[0].sha256]
    assert [c.sha256 for c in sw.parse(a)] == [certs[0].sha256]       # DER file
    assert sw.parse(b"<html>nothing</html>") == []


def _google(updated_days_ago=100, bits=2048, creds=True):
    p = [{"name": "inboundSamlSsoProfiles/abc", "label": "ClassLink", "entity": "x",
          "login": "y"}]
    c = {"inboundSamlSsoProfiles/abc": [{"name": "inboundSamlSsoProfiles/abc/idpCredentials/1",
                                         "updated": datetime.datetime.now(UTC) -
                                         datetime.timedelta(days=updated_days_ago),
                                         "bits": bits}] if creds else []}
    return p, c


def test_expiry_levels_and_rotation():
    from gambit import sso_watch as sw
    src = {"inboundSamlSsoProfiles/abc": {"kind": "file", "value": "x"}}
    for days, level in ((200, "ok"), (25, "warn"), (10, "warn"), (2, "bad"), (-1, "bad")):
        der, _k = _cert(days)
        f = sw.check(*_google(), src, read=lambda s, d=der: sw.parse(d))
        assert sw.worst(f) == level, (days, [x.text for x in f])
    # provider moved to a certificate made after Google's last upload
    der, _k = _cert(300, start_days_ago=5)
    f = sw.check(*_google(updated_days_ago=60), src, read=lambda s: sw.parse(der))
    assert any(x.level == "bad" and "newer certificate" in x.text for x in f)


def test_findings_without_a_source():
    from gambit import sso_watch as sw
    f = sw.check(*_google(creds=False), {})
    assert any(x.level == "bad" and "no certificate" in x.text for x in f)
    f = sw.check(*_google(updated_days_ago=4 * 365, bits=1024), {})
    assert any("1024-bit" in x.text for x in f) and any("years ago" in x.text for x in f)
    f = sw.check(*_google(), {})
    assert sw.worst(f) == "info"


def test_alerts_once_per_threshold(alerts_sent):
    from gambit import sso_watch as sw
    der, _k = _cert(10)
    src = {"inboundSamlSsoProfiles/abc": {"kind": "file", "value": "x"}}
    f = sw.check(*_google(), src, read=lambda s: sw.parse(der))
    assert sw._announce(f) == 1 and sw._announce(f) == 0        # not every night
    der2, _k = _cert(2)
    f2 = sw.check(*_google(), src, read=lambda s: sw.parse(der2))
    assert sw._announce(f2) == 1
    assert "sign-in certificates" in alerts_sent[0][0]


def test_load_google_and_run(alerts_sent):
    from gambit import sso_watch as sw

    def run_csv(a):
        if a[1] == "inboundssoprofiles":
            return 0, [{"name": "inboundSamlSsoProfiles/abc", "displayName": "ClassLink",
                        "idpConfig.entityId": "https://launchpad.classlink.com/x"}], ""
        return 0, [{"name": "inboundSamlSsoProfiles/abc/idpCredentials/9",
                    "updateTime": "2026-01-01T00:00:00Z", "rsaKeyInfo.keySize": "2048"}], ""
    p, c = sw.load_google(run_csv)
    assert p[0]["label"] == "ClassLink" and c[p[0]["name"]][0]["bits"] == 2048
    sw.run(lambda *_: None, run_csv)
    assert sw.last()["findings"] and sw.attention() == []        # only "set up" info


def test_sources_must_be_https():
    from gambit import net, sso_watch as sw
    with pytest.raises(ValueError):
        sw.set_source("p", "url", "http://idp/metadata")
    for bad in ("file:///etc/passwd", "ftp://x/y", "http://x/y"):
        with pytest.raises(ValueError):
            net.get_bytes(bad)
    sw.set_source("p", "url", "https://idp/metadata")
    assert sw.sources()["p"]["value"] == "https://idp/metadata"
    assert sw.upload_args("p", "c.pem") == ["create", "inboundssocredential", "profile", "p",
                                            "pemfile", "c.pem"]


# ======================================================== 2. email domains ===
def _rsa_pub_b64(bits):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    k = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    return base64.b64encode(k.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()


def _dns(records):
    from gambit.maildns import DNSError

    def look(name, rtype):
        v = records.get((name, rtype))
        if isinstance(v, Exception):
            raise v
        if v == "error":
            raise DNSError("boom")
        return list(v or [])
    return look


def _good(d="s.org", over=None):
    r = {(d, "MX"): ["1 smtp.google.com."],
         (d, "TXT"): ["v=spf1 include:_spf.google.com ~all", "google-site-verification=x"],
         ("_spf.google.com", "TXT"): ["v=spf1 include:_netblocks.google.com ~all"],
         ("_netblocks.google.com", "TXT"): ["v=spf1 ip4:1.2.3.0/24 ~all"],
         (f"google._domainkey.{d}", "TXT"): [f"v=DKIM1; k=rsa; p={_rsa_pub_b64(2048)}"],
         (f"_dmarc.{d}", "TXT"): [f"v=DMARC1; p=quarantine; rua=mailto:d@{d}"]}
    r.update(over or {})
    return r


def test_healthy_domain_all_ok():
    from gambit import maildns as md
    fs = md.check_domain("s.org", _dns(_good()))
    assert {f.check for f in fs} == {"MX", "SPF", "DKIM", "DMARC"}
    assert all(f.level == "ok" for f in fs), [(f.check, f.text) for f in fs]


@pytest.mark.parametrize("over,check,level,word", [
    ({("s.org", "TXT"): ["other"]}, "SPF", "bad", "No SPF"),
    ({("s.org", "TXT"): ["v=spf1 ~all", "v=spf1 -all"]}, "SPF", "bad", "2 SPF"),
    ({("s.org", "TXT"): ["v=spf1 include:_spf.google.com +all"]}, "SPF", "bad", "+all"),
    ({("s.org", "TXT"): ["v=spf1 include:_spf.google.com"]}, "SPF", "warn", "~all"),
    ({("s.org", "TXT"): ["v=spf1 ip4:1.1.1.1 ~all"]}, "SPF", "warn", "include Google"),
    ({("google._domainkey.s.org", "TXT"): []}, "DKIM", "bad", "No DKIM"),
    ({("google._domainkey.s.org", "TXT"): ["v=DKIM1; p="]}, "DKIM", "bad", "revoked"),
    ({("_dmarc.s.org", "TXT"): []}, "DMARC", "bad", "No DMARC"),
    ({("_dmarc.s.org", "TXT"): ["v=DMARC1; p=none; rua=mailto:x@s.org"]}, "DMARC", "warn",
     "p=none"),
    ({("_dmarc.s.org", "TXT"): ["v=DMARC1; p=reject"]}, "DMARC", "info", "rua"),
    ({("s.org", "MX"): []}, "MX", "bad", "bounces"),
    ({("s.org", "MX"): ["10 mx.filter.example."]}, "MX", "info", "not straight"),
    ({("s.org", "MX"): "error"}, "MX", "warn", "boom"),
])
def test_domain_problems(over, check, level, word):
    from gambit import maildns as md
    fs = [f for f in md.check_domain("s.org", _dns(_good(over=over))) if f.check == check]
    assert any(f.level == level and word.lower() in f.text.lower() for f in fs), \
        [(f.level, f.text) for f in fs]


def test_dkim_1024_and_spf_lookup_limit():
    from gambit import maildns as md
    weak = _good(over={("google._domainkey.s.org", "TXT"): [f"v=DKIM1; p={_rsa_pub_b64(1024)}"]})
    assert any(f.level == "warn" and "1024" in f.text for f in md.check_domain("s.org",
                                                                               _dns(weak)))
    many = " ".join(f"include:i{i}.example" for i in range(12))
    r = _good(over={("s.org", "TXT"): [f"v=spf1 include:_spf.google.com {many} ~all"]})
    fs = md.check_spf("s.org", _dns(r))
    assert any(f.level == "bad" and "lookups" in f.text for f in fs)


def test_doh_parsing_and_nxdomain(monkeypatch):
    from gambit import maildns as md, net
    answers = {"TXT": {"Status": 0, "Answer": [
        {"type": 5, "data": "alias."},
        {"type": 16, "data": '"v=spf1 include:_spf.google.com" " ~all"'}]}}

    def fake(method, url, headers=None, body=None, timeout=60):
        if "nx.example" in url:
            return 200, {}, json.dumps({"Status": 3}).encode()
        return 200, {}, json.dumps(answers["TXT"]).encode()
    monkeypatch.setattr(net, "request", fake)
    assert md.doh("s.org", "TXT") == ["v=spf1 include:_spf.google.com ~all"]
    assert md.doh("nx.example", "TXT") == []
    with pytest.raises(md.DNSError):
        md.doh("bad name;rm", "TXT")


def test_doh_blocked_falls_back_to_nslookup(monkeypatch):
    from gambit import maildns as md, net
    monkeypatch.setattr(net, "request", lambda *a, **k: (_ for _ in ()).throw(OSError("403")))
    monkeypatch.setattr(md, "nslookup", lambda n, t: ["v=spf1 ~all"])
    assert md.doh("s.org", "TXT") == ["v=spf1 ~all"]


def test_domain_run_alerts_only_new(alerts_sent):
    from gambit import maildns as md
    bad = _dns(_good(over={("_dmarc.s.org", "TXT"): []}))
    run_csv = (lambda a: (0, [{"domainName": "s.org", "verified": "True"}], "")
               if a[1] == "domains" else (0, [], ""))
    md.run(lambda *_: None, run_csv, look=bad)
    md.run(lambda *_: None, run_csv, look=bad)
    assert len(alerts_sent) == 1 and "DMARC" in alerts_sent[0][1]
    assert md.attention() and md.attention()[0][0] == "bad"


# ============================================== 3. tamper-evident activity ===
@pytest.fixture
def logdir(tmp_path, monkeypatch):
    from gambit import activity
    d = tmp_path / "log"
    d.mkdir()
    monkeypatch.setattr(activity, "local_dir", lambda: str(d))
    monkeypatch.setattr(activity, "shared_dir", lambda: "")
    settings.set(activity.ANCHOR_KEY, "")
    settings.set(activity.CHAIN_SINCE_KEY, "")
    settings.set(activity.INTEGRITY_KEY, "")
    return d


def _file(d):
    return glob.glob(str(d / "activity-*.jsonl"))[0]


def _rewrite(path, fn):
    lines = open(path, encoding="utf-8").read().splitlines()
    lines = fn(lines)
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def test_clean_log_verifies(logdir):
    from gambit import activity
    for i in range(4):
        activity.record(["update", "user", f"u{i}@s.org", "suspended", "on"], 0, "done",
                        None, "Default")
    rep = activity.check_file(_file(logdir))
    assert rep["bad"] == [] and rep["ok"] == 4
    assert all(e["integrity"] == "ok" for e in activity.load(0))


def _edit(lines, i, **changes):
    e = json.loads(lines[i])
    e.update(changes)
    lines[i] = json.dumps(e)
    return lines


@pytest.mark.parametrize("tamper,word", [
    (lambda L: _edit(L, 1, command="gam delete user boss@s.org"), "changed after"),
    (lambda L: L[:1] + L[2:], "removed, added or reordered"),
    (lambda L: L[:-1], "shorter"),
    (lambda L: L + [json.dumps({"id": "x", "time": "2099-01-01", "command": "gam x"})],
     "without a fingerprint"),
    (lambda L: [L[1], L[0]] + L[2:], "removed, added or reordered"),
])
def test_tampering_is_detected(logdir, tamper, word):
    from gambit import activity
    for i in range(4):
        activity.record(["update", "user", f"u{i}@s.org", "suspended", "on"], 0, "done",
                        None, "Default")
    _rewrite(_file(logdir), tamper)
    bad = activity.check_file(_file(logdir))["bad"]
    assert any(word in why for _n, why in bad), bad


def test_recomputed_hash_still_fails_the_signature(logdir):
    from gambit import activity
    for i in range(3):
        activity.record(["info", "user", f"u{i}@s.org"], 0, "done", None, "Default")

    def forge(L):
        e = json.loads(L[1])
        e["command"] = "gam evil"
        e["ch"] = activity.content_hash(e)
        e["h"] = activity.link_hash(e["prev"], e["ch"])
        L[1] = json.dumps(e)
        return L
    _rewrite(_file(logdir), forge)
    bad = activity.check_file(_file(logdir))["bad"]
    assert any("signature" in why for _n, why in bad)


def test_edited_entry_cant_be_undone_and_forged_undone_ignored(logdir):
    from gambit import activity
    e = activity.record(["update", "user", "a@s.org", "suspended", "on"], 0, "done",
                        {"label": "unsuspend", "args": ["update", "user", "a@s.org",
                                                        "suspended", "off"]}, "Default")
    _rewrite(_file(logdir), lambda L: _edit(L, 0, undo={"label": "x", "args": [
        "delete", "user", "boss@s.org"]}))
    got = next(x for x in activity.load(0) if x["id"] == e["id"])
    assert got["integrity"] == "bad"
    ok, why = activity.undo_allowed(got)
    assert not ok and "changed" in why
    # a hand-written "undone" mark mustn't hide a change
    e2 = activity.record(["update", "user", "b@s.org", "suspended", "on"], 0, "done", None,
                         "Default")
    with open(_file(logdir), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "zz", "type": "undone", "target": e2["id"],
                             "time": "2099-01-01T00:00:00"}) + "\n")
    assert not next(x for x in activity.load(0) if x["id"] == e2["id"])["undone"]


def test_deleted_month_file_and_daily_alert(logdir, alerts_sent):
    from gambit import activity
    activity.record(["info", "domain"], 0, "done", None, "Default")
    activity.run_check(lambda *_: None)
    assert alerts_sent == []
    os.remove(_file(logdir))
    activity.run_check(lambda *_: None)
    activity.run_check(lambda *_: None)
    assert len(alerts_sent) == 1 and "deleted" in alerts_sent[0][1]
    assert activity.integrity_attention()


def test_legacy_lines_before_upgrade_are_not_errors(logdir):
    from gambit import activity
    path = str(logdir / "activity-2026-01.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "old1", "time": "2026-01-02T00:00:00", "command": "x"}) +
                 "\n")
    rep = activity.check_file(path)
    assert rep["legacy"] == 1 and rep["bad"] == []


def test_sheet_copy_has_integrity_column(logdir, tmp_path):
    from gambit import activity
    activity.record(["info", "domain"], 0, "done", None, "Default")
    p = tmp_path / "x.csv"
    activity.write_csv(activity.load(0), str(p))
    head, row = open(p, encoding="utf-8").read().splitlines()[:2]
    assert "Integrity" in head and "verified" in row


# ====================================================== 4. Spanish printouts ===
def test_card_languages_and_family_note():
    from gambit.ui.print_card import card_html
    es = card_html("Ana", "ana@s.org", "Pw1", lang="es", family=True, qr=False, size="page")
    assert "Correo electrónico" in es and "Contraseña temporal" in es
    assert "Para las familias" in es and "Email" not in es
    both = card_html("Ana", "ana@s.org", "Pw1", lang="both", qr=False, size="page")
    assert "Email / <i>Correo electrónico</i>" in both
    en = card_html("Ana", "ana@s.org", "", qr=False, size="page")
    assert "Email" in en and "Correo" not in en


def test_cards_and_welcome_sheet_in_spanish():
    from gambit.ui.cards import cards_html
    from gambit.ui.pages.workflows import WelcomeSheet
    h = cards_html([{"name": "Ana", "email": "a@s.org", "password": "x", "group": "5A"}],
                   lang="es")
    assert "1 tarjeta(s)" in h and "Inicio de sesión de Google" in h
    w = WelcomeSheet.sheet_html("Ana", "a@s.org", "x", True, "es")
    assert "¡Le damos la bienvenida, Ana!" in w and "Elija una contraseña" in w
    assert "Elija" not in WelcomeSheet.sheet_html("Ana", "a@s.org", "x", False, "es")


def test_custom_wording_is_escaped_and_placeholders_safe():
    from gambit import printouts as po
    from gambit.ui.pages.workflows import WelcomeSheet
    po.save_custom({"es": {"welcome_title": "Hola {name} <script>x</script> {name.__class__}"}})
    w = WelcomeSheet.sheet_html("<b>Ana</b>", "a@s.org", "x", True, "es")
    assert "<script>" not in w and "&lt;script&gt;" in w
    assert "{name.__class__}" in w and "&lt;b&gt;Ana&lt;/b&gt;" in w
    po.set_default_lang("es")
    from gambit.ui.cards import cards_html
    assert "tarjeta" in cards_html([{"name": "A", "email": "a@s.org", "password": "p"}])
    po.save_custom({})
    assert po.phrase("welcome_title", "es", name="X") == "¡Le damos la bienvenida, X!"


# ============================================ 5. archive, then delete + record ===
def _users():
    return [{"email": "old@s.org", "suspended": True, "ou": "/Students/Gone",
             "last_login": "2020-01-01T00:00:00Z"},
            {"email": "archive@s.org", "suspended": True, "ou": "/Students/Gone",
             "last_login": "2020-01-01T00:00:00Z"}]


def _archive_request(team_dir):
    from gambit import team
    from gambit.tools import automation as am
    am.save_rules([{"name": "Old students", "kind": "delete_old", "ou": "/Students",
                    "days": 365, "enabled": True, "max": 50, "except": "",
                    "archive_to": "archive@s.org", "archive_what": ["drive"]}])
    am.run_cleanup(lambda *_: None, users=_users())
    return next(r for r in team.list_requests("pending") if r.get("kind") == "cleanup-archive")


def test_archive_rule_asks_for_transfers_not_deletes(team_dir):
    req = _archive_request(team_dir)
    assert req["commands"] == [["create", "datatransfer", "old@s.org", "drive",
                                "archive@s.org", "all"]]          # never the archive itself
    assert req["delete_after"] == ["old@s.org"]


def test_register_needs_a_signed_request(team_dir):
    from gambit import retention
    req = _archive_request(team_dir)
    assert retention.register(req) == 1
    with pytest.raises(ValueError):
        retention.register({**req, "delete_after": ["boss@s.org", "old@s.org"]})
    sneaky = dict(req)
    assert retention.register(sneaky) == 1                      # same request: not twice
    assert len(retention.pending()) == 1


def _runner(status="completed", suspended="True", gone=False):
    calls = []

    def run_csv(a):
        if a[:2] == ["print", "datatransfers"]:
            return 0, [{"oldOwnerUserEmail": "old@s.org", "newOwnerUserEmail": "archive@s.org",
                        "requestTime": datetime.datetime.now().isoformat(),
                        "overallTransferStatusCode": status}], ""
        if a[:2] == ["print", "users"]:
            return 0, ([] if gone else [{"primaryEmail": "old@s.org",
                                         "suspended": suspended}]), ""
        return 0, [], ""

    def run_text(a, t=0):
        calls.append(a)
        return 0, ""
    return run_csv, run_text, calls


def test_deletes_after_transfer_and_records_it(team_dir):
    from gambit import retention
    retention.register(_archive_request(team_dir))
    run_csv, run_text, calls = _runner("inprogress")
    retention.run_due(lambda *_: None, run_csv, run_text)
    assert calls == []                                          # still transferring
    run_csv, run_text, calls = _runner("completed")
    retention.run_due(lambda *_: None, run_csv, run_text)
    assert calls == [["delete", "user", "old@s.org"]]
    assert retention.pending()[0]["status"] == "deleted"
    rec = retention.records()
    assert len(rec) == 1 and rec[0]["archived_to"] == "archive@s.org"
    assert rec[0]["rule"] == "Old students" and rec[0]["verified"] == "yes"


@pytest.mark.parametrize("kw,status", [({"status": "failed"}, "failed"),
                                       ({"suspended": "False"}, "cancelled")])
def test_no_delete_when_transfer_fails_or_account_back(team_dir, alerts_sent, kw, status):
    from gambit import retention
    retention.register(_archive_request(team_dir))
    run_csv, run_text, calls = _runner(**kw)
    retention.run_due(lambda *_: None, run_csv, run_text)
    assert calls == [] and retention.pending()[0]["status"] == status


def test_edited_plan_and_dry_run_never_delete(team_dir):
    from gambit import retention
    retention.register(_archive_request(team_dir))
    items = retention.pending()
    retention._save_pending([{**items[0], "email": "boss@s.org"}])
    run_csv, run_text, calls = _runner()
    retention.run_due(lambda *_: None, run_csv, run_text)
    assert calls == [] and retention.pending()[0]["status"] == "blocked"
    retention._save_pending(items)
    settings.set("safety/dry_run", True)
    retention.run_due(lambda *_: None, run_csv, run_text)
    assert calls == []


def test_every_delete_lands_in_the_record(team_dir, logdir):
    from gambit import activity, retention
    activity.record(["delete", "user", "gone@s.org"], 0, "done", None, "Default")
    activity.record(["delete", "user", "failed@s.org"], 1, "failed", None, "Default")
    activity.record(["info", "user", "x@s.org"], 0, "done", None, "Default")
    rec = retention.records()
    assert [r["email"] for r in rec] == ["gone@s.org"] and rec[0]["verified"] == "yes"
    path = os.path.join(str(team_dir), retention.RECORD_FILE)
    lines = open(path, encoding="utf-8").read().splitlines()
    r = json.loads(lines[0])
    r["email"] = "someone-else@s.org"
    open(path, "w", encoding="utf-8").write(json.dumps(r) + "\n")
    local = [p for p in retention._record_paths() if not p.startswith(str(team_dir))][0]
    os.remove(local)
    assert retention.records()[0]["verified"].startswith("NO")


# ================================================================ screens ===
def test_wording_dialog_and_card_dialog(qapp):
    from gambit import printouts as po
    from gambit.ui.cards import CardsDialog
    from gambit.ui.wording_dialog import WordingDialog
    d = WordingDialog()
    row = [k for k, *_r in po.PHRASES].index("password")
    d.table.item(row, 1).setText("Clave")
    d._save()
    assert po.phrase("password", "es") == "Clave"
    c = CardsDialog(None, [{"name": "A", "email": "a@s.org", "password": "p", "group": "5A"}])
    c.lang.setCurrentIndex(c.lang.findData("es"))
    assert "Clave" in c.html
    c.family.setChecked(True)
    assert "Para las familias" in c.html
    po.save_custom({})


def test_rule_dialog_archive_fields(qapp):
    from gambit.ui.pages.automation_tabs import RuleDialog

    from gambit.directory import Directory
    d = RuleDialog(None, Directory(), {"name": "x", "kind": "delete_old", "ou": "/", "days": 365,
                                 "archive_to": "arch@s.org", "archive_what": ["drive",
                                                                              "calendar"]})
    r = d.rule()
    assert r["archive_to"] == "arch@s.org" and r["archive_what"] == ["drive", "calendar"]
    d.kind.setCurrentIndex(d.kind.findData("inactive"))
    assert d.rule()["archive_to"] == ""
