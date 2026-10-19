"""Sign in with Google: OAuth 2.0 for desktop apps (loopback redirect + PKCE + state +
nonce). The ID token is verified here – signature against Google's published keys,
issuer, audience, expiry, nonce, verified email and the district's hosted domain. No
Google tokens are stored; GAMbit only learns who signed in."""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import socket
import threading
import time
import urllib.parse
import urllib.request

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
_JWKS: dict = {"at": 0.0, "keys": {}}


class SignInError(Exception):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def pkce() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(48))
    return verifier, _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def auth_url(client_id: str, redirect: str, state: str, nonce: str, challenge: str,
             domain: str, hint: str = "") -> str:
    q = {"client_id": client_id, "redirect_uri": redirect, "response_type": "code",
         "scope": "openid email profile", "state": state, "nonce": nonce,
         "code_challenge": challenge, "code_challenge_method": "S256",
         "prompt": "select_account", "hd": domain}
    if hint:
        q["login_hint"] = hint
    return AUTH_URL + "?" + urllib.parse.urlencode(q)


# ============================================================ loopback server ===
class _Catcher(http.server.BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self):  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" not in q and "error" not in q:
            self.send_response(404)
            self.end_headers()
            return
        self.server.result = {k: v[0] for k, v in q.items()}
        ok = "code" in q
        body = ("<html><body style='font-family:Segoe UI,sans-serif;padding:40px'><h2>"
                + ("You're signed in to GAMbit." if ok else "Sign-in was cancelled.") +
                "</h2><p>You can close this tab and go back to GAMbit.</p></body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *_a):
        pass


class _Server(http.server.HTTPServer):
    allow_reuse_address = False         # no other program may share this port


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_code(server, timeout: float, cancelled=None) -> dict:
    end = time.time() + timeout
    server.timeout = 0.5
    while time.time() < end:
        if cancelled and cancelled():
            raise SignInError("Sign-in cancelled.")
        server.handle_request()
        if getattr(server, "result", None):
            return server.result
    raise SignInError("Google sign-in timed out. Try again.")


# ============================================================== token check ===
def _post(url: str, data: dict) -> dict:
    from ..net import USER_AGENT, _context
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode("ascii"),
                                 headers={"User-Agent": USER_AGENT,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20, context=_context()) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error_description", "")
        except Exception:  # noqa: BLE001
            msg = ""
        raise SignInError(f"Google refused the sign-in ({e.code}). {msg}".strip()) from None


def google_keys(force: bool = False) -> dict:
    from ..net import get_json
    if force or time.time() - _JWKS["at"] > 3600 or not _JWKS["keys"]:
        data = get_json(CERTS_URL)
        _JWKS["keys"] = {k["kid"]: k for k in data.get("keys", [])}
        _JWKS["at"] = time.time()
    return _JWKS["keys"]


def _rsa_verify(jwk: dict, signed: bytes, sig: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    n = int.from_bytes(_unb64url(jwk["n"]), "big")
    e = int.from_bytes(_unb64url(jwk["e"]), "big")
    try:
        rsa.RSAPublicNumbers(e, n).public_key().verify(sig, signed, padding.PKCS1v15(),
                                                       hashes.SHA256())
        return True
    except InvalidSignature:
        return False


def verify_id_token(token: str, client_id: str, nonce: str, domain: str,
                    keys: dict | None = None, now: float | None = None) -> dict:
    try:
        h64, p64, s64 = token.split(".")
        header = json.loads(_unb64url(h64))
        claims = json.loads(_unb64url(p64))
        sig = _unb64url(s64)
    except (ValueError, json.JSONDecodeError):
        raise SignInError("Google sent an unreadable sign-in token.") from None
    if header.get("alg") != "RS256":
        raise SignInError("Unexpected token type.")
    keys = keys if keys is not None else google_keys()
    jwk = keys.get(header.get("kid"))
    if jwk is None and keys is _JWKS["keys"]:
        jwk = google_keys(force=True).get(header.get("kid"))
    if not jwk or not _rsa_verify(jwk, f"{h64}.{p64}".encode("ascii"), sig):
        raise SignInError("The sign-in token's signature isn't Google's.")
    now = now if now is not None else time.time()
    if claims.get("iss") not in ISSUERS:
        raise SignInError("The sign-in token wasn't issued by Google.")
    if claims.get("aud") != client_id:
        raise SignInError("The sign-in token was made for a different app.")
    if float(claims.get("exp", 0)) < now - 60 or float(claims.get("iat", 0)) > now + 300:
        raise SignInError("The sign-in token has expired – check this computer's clock.")
    if not nonce or claims.get("nonce") != nonce:
        raise SignInError("The sign-in token doesn't match this sign-in attempt.")
    email = (claims.get("email") or "").lower()
    if not claims.get("email_verified"):
        raise SignInError("Google hasn't verified this email address.")
    dom = (domain or "").lower()
    if dom and ((claims.get("hd") or "").lower() != dom or not email.endswith("@" + dom)):
        raise SignInError(f"Sign in with your @{dom} account.")
    return {"email": email, "name": claims.get("name", ""), "sub": claims.get("sub", "")}


# ================================================================== sign in ===
def sign_in(client_id: str, client_secret: str, domain: str, open_url, hint: str = "",
            timeout: float = 180, cancelled=None) -> dict:
    """Runs in a worker thread. open_url(url) shows Google's page in the browser."""
    if not client_id:
        raise SignInError("Google sign-in isn't set up yet (no OAuth client ID).")
    server = _Server(("127.0.0.1", 0), _Catcher)      # the OS picks a free port
    port = server.server_address[1]
    redirect = f"http://127.0.0.1:{port}/"
    server.result = {}
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    verifier, challenge = pkce()
    try:
        open_url(auth_url(client_id, redirect, state, nonce, challenge, domain, hint))
        got = wait_for_code(server, timeout, cancelled)
    finally:
        threading.Thread(target=server.server_close, daemon=True).start()
    if got.get("error"):
        raise SignInError("Google sign-in was cancelled." if got["error"] == "access_denied"
                          else f"Google sign-in failed: {got['error']}")
    if not secrets.compare_digest(got.get("state", ""), state):
        raise SignInError("The sign-in response didn't match this attempt.")
    tok = _post(TOKEN_URL, {"code": got["code"], "client_id": client_id,
                            "client_secret": client_secret, "redirect_uri": redirect,
                            "grant_type": "authorization_code", "code_verifier": verifier})
    if "id_token" not in tok:
        raise SignInError("Google didn't return who signed in.")
    return verify_id_token(tok["id_token"], client_id, nonce, domain)
