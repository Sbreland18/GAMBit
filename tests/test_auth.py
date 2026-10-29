"""GAMbit sign-in: signed access list, Google ID token checks, emergency admin, scope."""

import base64
import json
import threading
import time
import urllib.request

import pytest

from gambit import team
from gambit.auth import access, crypto, google_sso as gs, local_admin, session
from gambit.settings import settings


@pytest.fixture
def auth_env(tmp_path, monkeypatch):
    d = tmp_path / "team"
    d.mkdir()
    settings.set("team/folder", str(d))
    settings.set("access/pinned", "")
    monkeypatch.setattr(access, "_app_dir", lambda: str(tmp_path / "app"))
    session.end()
    session.set_doc(None)
    yield d
    session.end()
    session.set_doc(None)
    settings.set("team/folder", "")
    settings.set("access/pinned", "")


# ================================================================== crypto ===
def test_crypto_basics():
    priv, pub = crypto.new_keypair()
    sig = crypto.sign(priv, b"hello")
    assert crypto.verify(pub, sig, b"hello") and not crypto.verify(pub, sig, b"hellO")
    assert len(crypto.fingerprint(pub)) == 19
    # RFC 6238 test vector (SHA1, secret "12345678901234567890", T=59 → 94287082)
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert crypto.totp(secret, 59, digits=8) == "94287082"
    code = crypto.totp(secret, 1000)
    assert crypto.totp_ok(secret, code, 1000) == 1000 // 30
    assert crypto.totp_ok(secret, code, 1000, last_used=1000 // 30) == -1   # no replay
    assert crypto.totp_ok(secret, "000000", 1000) == -1
    rec = crypto.hash_password("Correct-Horse-9", params={"n": 2 ** 10, "r": 8, "p": 1})
    assert crypto.check_password("Correct-Horse-9", rec)
    assert not crypto.check_password("correct-horse-9", rec)
    assert crypto.password_problems("short") and not crypto.password_problems(
        "Lincoln-Library-2026!")
    assert crypto.unprotect(crypto.protect(b"x")) == b"x"


# ============================================================ access list ===
def test_access_list_sign_verify_tamper_rollback(auth_env):
    assert not access.required()
    doc = access.new_list("boss@d.org", "d.org", "cid", "sec")
    assert access.required() and doc["serial"] == 1
    assert access.load()["people"]["boss@d.org"]["role"] == "Full admin"
    # hand edit → refused
    env = json.load(open(access.path()))
    env["doc"]["people"]["me@d.org"] = {"role": "Full admin"}
    json.dump(env, open(access.path(), "w"))
    with pytest.raises(access.AccessError, match="changed outside"):
        access.load()
    # put back a good one, then save a newer one
    env["doc"]["people"].pop("me@d.org")
    json.dump(env, open(access.path(), "w"))
    old = open(access.path()).read()
    d = access.load()
    d["people"]["tech@d.org"] = {"role": "Help desk", "ous": ["/Students/Lincoln"]}
    access.save(d, "boss@d.org")
    assert access.load()["serial"] == 2
    open(access.path(), "w").write(old)              # roll back to version 1
    with pytest.raises(access.AccessError, match="older"):
        access.load()


def test_forged_list_and_first_use(auth_env, tmp_path, monkeypatch):
    access.new_list("boss@d.org", "d.org", "cid", "sec")
    good = open(access.path()).read()
    # someone signs their own list with their own key
    monkeypatch.setattr(access, "_app_dir", lambda: str(tmp_path / "evil"))
    settings.set("access/pinned", "")
    access.new_list("evil@d.org", "d.org", "cid", "sec")
    forged = open(access.path()).read()
    # a PC that trusted the real list refuses the forgery
    monkeypatch.setattr(access, "_app_dir", lambda: str(tmp_path / "app"))
    open(access.path(), "w").write(good)
    settings.set("access/pinned", "")
    with pytest.raises(access.AccessError, match="NOT_PINNED"):
        access.load()
    info = access.first_look()
    assert info["email"] == "boss@d.org"
    access.trust_first(info["doc"])
    access.load()
    open(access.path(), "w").write(forged)
    with pytest.raises(access.AccessError, match="trusts"):
        access.load()
    # missing file while pinned = fail closed
    import os
    os.remove(access.path())
    with pytest.raises(access.AccessError, match="missing"):
        access.load()


def test_people_roles_and_keys(auth_env):
    doc = access.new_list("boss@d.org", "d.org", "cid", "sec")
    doc["people"]["off@d.org"] = {"role": "Help desk", "enabled": False}
    doc["people"]["tech@d.org"] = {"role": "Help desk", "ous": ["/Students/Lincoln"]}
    assert access.person(doc, "off@d.org") is None
    assert access.person(doc, "stranger@d.org") is None          # default: No access
    p = access.person(doc, "TECH@d.org")
    assert p["role_name"] == "Help desk" and p["ous"] == ["/Students/Lincoln"]
    # a second admin asks for their key; approval requires an admin role
    fp = access.request_admin_key("tech@d.org")
    req = access.key_requests()[0]
    assert req["fingerprint"] == fp
    d1 = access.approve_key(doc, req)          # a non-admin's key: a member key only
    assert req["key_id"] in d1["member_keys"] and req["key_id"] not in d1["admin_keys"]
    with pytest.raises(access.AccessError, match="access list"):
        access.approve_key(doc, {**req, "email": "stranger@d.org"})
    doc["people"]["tech@d.org"]["role"] = "Full admin"
    d2 = access.approve_key(doc, req)
    assert req["key_id"] in d2["admin_keys"]
    access.save(d2, "boss@d.org")
    d3 = access.load()
    d3["people"]["new@d.org"] = {"role": "Help desk"}
    access.save(d3, "tech@d.org")                                 # signed by the new admin
    assert "new@d.org" in access.load()["people"]
    with pytest.raises(access.AccessError, match="no GAMbit admin key"):
        access.save(d3, "nobody@d.org")


def test_team_uses_signed_list(auth_env):
    doc = access.new_list("boss@d.org", "d.org", "cid", "sec")
    doc["roles"]["Lincoln aide"] = {"pages": ["Student lookup", "Users"], "can": ["read",
                                                                                  "passwords"],
                                    "ask": [], "view_only": ["Users"], "admin": False}
    doc["people"]["aide@d.org"] = {"role": "Lincoln aide", "ous": ["/Students/Lincoln"]}
    doc = access.save(doc, "boss@d.org")
    session.set_doc(doc)
    session.start(access.person(doc, "aide@d.org"), "google", doc)
    assert team.me() == "aide@d.org" and team.my_role_name() == "Lincoln aide"
    assert team.page_allowed("Student lookup") and not team.page_allowed("Groups")
    assert team.page_view_only("Users") and not team.page_view_only("Student lookup")
    assert team.check(["update", "user", "a@d.org", "password", "x"])[0]
    assert not team.check(["update", "user", "a@d.org", "suspended", "on"])[0]
    assert team.load_roles()["people"]["aide@d.org"] == "Lincoln aide"
    from gambit import activity
    assert activity.who() == "aide@d.org"


# =================================================================== scope ===
def test_scope_checks():
    session.end()
    session._current.update(email="a@d.org", ous=["/Students/Lincoln"], last=time.time(),
                            started=time.time(), idle=60, max=3600)
    users = {"kid@d.org": {"ou": "/Students/Lincoln/Grade 5"},
             "other@d.org": {"ou": "/Students/Grant"}, "t@d.org": {"ou": "/Staff"}}
    sp = session.scope_problem
    assert sp(["update", "user", "kid@d.org", "password", "x"], users) == ""
    assert "other@d.org" in sp(["update", "user", "other@d.org", "password", "x"], users)
    assert sp(["update", "user", "kid@d.org", "ou", "/Students/Grant"], users)   # move out
    assert sp(["user", "kid@d.org", "signout"], users) == ""
    assert sp(["all", "users", "signout"], users) == "commands for the whole domain"
    assert sp(["ou_and_children", "/Students", "signout"], users)
    assert sp(["update", "group", "g@d.org", "add", "member", "t@d.org"], users)
    assert sp(["cros_sn", "SN1", "update", "action", "disable"], users,
              lambda k, v: "/Students/Lincoln/Carts") == ""
    assert sp(["cros_sn", "SN1", "update", "action", "disable"], users,
              lambda k, v: "/Chromebooks/Grant")
    assert sp(["create", "user", "new@d.org", "ou", "/Students/Lincoln"], users) == ""
    assert sp(["create", "user", "new@d.org", "ou", "/Staff"], users)
    assert session.in_scope("/Students/Lincoln") and not session.in_scope("/Students/Lincolnx")
    session._current["last"] = time.time() - 120
    assert "idle" in session.expired()
    session.end()


# ============================================================ Google token ===
def _jwt(priv, claims, kid="k1"):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    enc = lambda d: gs._b64url(json.dumps(d).encode())  # noqa: E731
    h, p = enc({"alg": "RS256", "kid": kid, "typ": "JWT"}), enc(claims)
    sig = priv.sign(f"{h}.{p}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{h}.{p}.{gs._b64url(sig)}"


def _rsa():
    from cryptography.hazmat.primitives.asymmetric import rsa
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = priv.public_key().public_numbers()
    jwk = {"kid": "k1", "n": gs._b64url(n.n.to_bytes(256, "big")),
           "e": gs._b64url(n.e.to_bytes(3, "big"))}
    return priv, {"k1": jwk}


def test_id_token_checks():
    priv, keys = _rsa()
    now = 1_800_000_000
    good = {"iss": "https://accounts.google.com", "aud": "cid", "exp": now + 600, "iat": now,
            "nonce": "N", "email": "Boss@D.org", "email_verified": True, "hd": "d.org",
            "name": "Boss", "sub": "1"}
    v = gs.verify_id_token(_jwt(priv, good), "cid", "N", "d.org", keys, now)
    assert v["email"] == "boss@d.org"
    for change, msg in (({"aud": "other"}, "different app"), ({"nonce": "X"}, "attempt"),
                        ({"hd": "gmail.com"}, "@d.org"), ({"exp": now - 3600}, "expired"),
                        ({"iss": "evil"}, "issued"), ({"email_verified": False}, "verified")):
        with pytest.raises(gs.SignInError, match=msg):
            gs.verify_id_token(_jwt(priv, {**good, **change}), "cid", "N", "d.org", keys, now)
    other, _k = _rsa()
    with pytest.raises(gs.SignInError, match="signature"):
        gs.verify_id_token(_jwt(other, good), "cid", "N", "d.org", keys, now)
    tok = _jwt(priv, good)
    h, p, s = tok.split(".")
    with pytest.raises(gs.SignInError, match="signature"):
        gs.verify_id_token(f"{h}.{gs._b64url(json.dumps({**good, 'email': 'x@d.org'}).encode())}"
                           f".{s}", "cid", "N", "d.org", keys, now)


def test_full_google_flow(monkeypatch):
    """Browser redirect to the loopback server, state check, PKCE code exchange."""
    priv, keys = _rsa()
    seen = {}

    def fake_post(url, data):
        seen.update(data)
        return {"id_token": _jwt(priv, {"iss": "accounts.google.com", "aud": "cid",
                                        "exp": time.time() + 600, "iat": time.time(),
                                        "nonce": seen["nonce"], "email": "t@d.org",
                                        "email_verified": True, "hd": "d.org"})}
    monkeypatch.setattr(gs, "_post", fake_post)
    monkeypatch.setattr(gs, "google_keys", lambda force=False: keys)

    def browser(url):
        from urllib.parse import parse_qs, urlparse
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert q["code_challenge_method"] == "S256" and q["hd"] == "d.org"
        seen["nonce"] = q["nonce"]
        threading.Thread(target=lambda: urllib.request.urlopen(
            f"{q['redirect_uri']}?code=abc&state={q['state']}").read(), daemon=True).start()
    who = gs.sign_in("cid", "sec", "d.org", browser, timeout=10)
    assert who["email"] == "t@d.org" and seen["code"] == "abc" and seen["code_verifier"]

    def bad_state(url):
        from urllib.parse import parse_qs, urlparse
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        threading.Thread(target=lambda: urllib.request.urlopen(
            f"{q['redirect_uri']}?code=abc&state=WRONG").read(), daemon=True).start()
    with pytest.raises(gs.SignInError, match="didn't match"):
        gs.sign_in("cid", "sec", "d.org", bad_state, timeout=10)


# ======================================================== emergency admin ===
def test_emergency_admin(auth_env, monkeypatch):
    monkeypatch.setattr(crypto, "SCRYPT", {"n": 2 ** 10, "r": 8, "p": 1})
    secret = crypto.new_totp_secret()
    with pytest.raises(ValueError, match="14"):
        local_admin.setup("short", secret, crypto.totp(secret), "boss@d.org")
    t0 = time.time()
    local_admin.setup("Lincoln-Library-2026!", secret, crypto.totp(secret, t0), "boss@d.org")
    assert local_admin.configured()
    fp = local_admin.fingerprint()
    with pytest.raises(ValueError, match="registered"):       # not in the access list
        local_admin.check("emergency-admin", "Lincoln-Library-2026!", crypto.totp(secret, t0))
    later = t0 + 31
    monkeypatch.setattr(time, "time", lambda: later)
    assert local_admin.check("emergency-admin", "Lincoln-Library-2026!",
                             crypto.totp(secret, later), fp)
    # the same code can't be used twice
    assert not local_admin.check("emergency-admin", "Lincoln-Library-2026!",
                                 crypto.totp(secret, later), fp)
    for _ in range(4):          # the replay above was failure #1
        assert not local_admin.check("emergency-admin", "wrong", "000000", fp)
    with pytest.raises(ValueError, match="locked"):
        local_admin.check("emergency-admin", "Lincoln-Library-2026!",
                          crypto.totp(secret, later + 30), fp)
