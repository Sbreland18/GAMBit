"""Sign-in (SAML SSO) certificate watch.

Google's API never hands back the certificate a sign-in provider (ClassLink, Clever, ADFS,
Entra ID…) signs with – only when it was uploaded and its key size. So GAMbit reads the
certificate from the provider itself: its SAML metadata link (every provider publishes one)
or a certificate file. It then warns 30, 14 and 3 days before it expires, and when the
provider has started using a newer certificate than the one Google has – the two things
that take every student's and teacher's sign-in down at once.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import re
from dataclasses import dataclass, field

from .settings import settings

SOURCES_KEY = "sso/cert_sources"        # {profile name: {"kind": url|file, "value": …}}
LAST_KEY = "sso/last_check"             # cached result for Home and the digest
NOTIFIED_KEY = "sso/notified"           # {fingerprint: last threshold announced}
WARN_DAYS = (30, 14, 3)
OLD_UPLOAD_DAYS = 3 * 365


# ------------------------------------------------------------- certificates ---
@dataclass
class Cert:
    subject: str
    issuer: str
    not_before: datetime.datetime
    not_after: datetime.datetime
    sha256: str
    key_bits: int
    use: str = ""                                    # signing / encryption / "" (both)
    der: bytes = field(default=b"", repr=False)

    def pem(self) -> str:
        b = base64.b64encode(self.der).decode()
        return "-----BEGIN CERTIFICATE-----\n" + "\n".join(
            b[i:i + 64] for i in range(0, len(b), 64)) + "\n-----END CERTIFICATE-----\n"

    def days_left(self, now: datetime.datetime | None = None) -> int:
        now = now or datetime.datetime.now(datetime.timezone.utc)
        return (self.not_after - now).days

    def short_fp(self) -> str:
        return ":".join(self.sha256[i:i + 2] for i in range(0, 16, 2)).upper()


def _load_der(der: bytes, use: str = "") -> Cert | None:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    try:
        c = x509.load_der_x509_certificate(der)
    except ValueError:
        return None

    def name(n):
        cn = n.get_attributes_for_oid(NameOID.COMMON_NAME)
        return cn[0].value if cn else n.rfc4514_string()
    try:
        bits = int(getattr(c.public_key(), "key_size", 0) or 0)
    except Exception:  # noqa: BLE001 – unusual key types
        bits = 0
    nb = getattr(c, "not_valid_before_utc", None) or \
        c.not_valid_before.replace(tzinfo=datetime.timezone.utc)
    na = getattr(c, "not_valid_after_utc", None) or \
        c.not_valid_after.replace(tzinfo=datetime.timezone.utc)
    return Cert(str(name(c.subject)), str(name(c.issuer)), nb, na,
                hashlib.sha256(der).hexdigest(), bits, use, der)


_PEM = re.compile(rb"-----BEGIN CERTIFICATE-----(.+?)-----END CERTIFICATE-----", re.S)
_X509 = re.compile(rb"<(?:[\w-]+:)?X509Certificate\b[^>]*>(.*?)</(?:[\w-]+:)?X509Certificate\s*>",
                   re.S)
_KEYDESC = re.compile(rb"<(?:[\w-]+:)?KeyDescriptor\b([^>]*)>(.*?)</(?:[\w-]+:)?KeyDescriptor\s*>",
                      re.S)


def _b64(blob: bytes) -> bytes | None:
    try:
        return base64.b64decode(re.sub(rb"\s+", b"", blob), validate=True)
    except (ValueError, TypeError):
        return None


def parse(data: bytes) -> list[Cert]:
    """Every certificate in a PEM file, a DER file or a SAML metadata document. Metadata is
    read with patterns, not an XML parser, so nothing in it is ever fetched or expanded."""
    out: list[Cert] = []
    seen: set[str] = set()

    def add(der, use=""):
        c = _load_der(der, use) if der else None
        if c and c.sha256 not in seen:
            seen.add(c.sha256)
            out.append(c)
    data = data or b""
    if b"X509Certificate" in data:
        descs = list(_KEYDESC.finditer(data))
        if descs:
            for d in descs:
                m = re.search(rb'use\s*=\s*["\'](\w+)["\']', d.group(1))
                for x in _X509.finditer(d.group(2)):
                    add(_b64(x.group(1)), (m.group(1).decode() if m else ""))
        for x in _X509.finditer(data):                 # certificates outside KeyDescriptor
            add(_b64(x.group(1)))
        return out
    for m in _PEM.finditer(data):
        add(_b64(m.group(1)))
    if not out and data[:1] == b"\x30":                # a single DER certificate
        add(data)
    return out


def read_source(src: dict) -> list[Cert]:
    """The certificates at a saved source (raises with a plain reason)."""
    kind, value = src.get("kind", ""), (src.get("value") or "").strip()
    if not value:
        raise ValueError("No metadata link or certificate file set.")
    if kind == "url":
        from . import net
        data = net.get_bytes(value)
    else:
        import os
        if os.path.getsize(value) > 2 * 1024 * 1024:
            raise ValueError("That file is too large to be a certificate.")
        with open(value, "rb") as fh:
            data = fh.read()
    certs = parse(data)
    if not certs:
        raise ValueError("No certificate found there – use the provider's SAML metadata "
                         "link, or a .pem / .cer / .crt file.")
    return certs


# ---------------------------------------------------------------- sources ---
def sources() -> dict:
    try:
        d = json.loads(settings.get(SOURCES_KEY, "") or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def set_source(profile: str, kind: str, value: str, label: str = ""):
    if kind not in ("url", "file"):
        raise ValueError("kind must be url or file")
    value = (value or "").strip()
    if kind == "url" and not value.lower().startswith("https://"):
        raise ValueError("Use the provider's https:// metadata link.")
    d = sources()
    if value:
        d[profile] = {"kind": kind, "value": value, "label": label}
    else:
        d.pop(profile, None)
    settings.set(SOURCES_KEY, json.dumps(d))


# ----------------------------------------------------------- Google's side ---
def _pick(r: dict, *keys) -> str:
    low = {k.lower(): v for k, v in r.items()}
    for k in keys:
        v = low.get(k.lower())
        if v not in (None, ""):
            return str(v)
    return ""


def _when(s: str) -> datetime.datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def load_google(run_csv=None) -> tuple[list[dict], dict[str, list[dict]]]:
    """(profiles, {profile name: [credentials]}) from GAM."""
    from .directory import run_gam_csv
    run_csv = run_csv or run_gam_csv
    code, rows, err = run_csv(["print", "inboundssoprofiles"])
    if code != 0:
        raise RuntimeError((err or "").strip().splitlines()[-1] if (err or "").strip()
                           else "Couldn't read the single sign-on profiles.")
    profiles = []
    for r in rows:
        name = _pick(r, "name")
        if name:
            profiles.append({"name": name, "label": _pick(r, "displayName") or name,
                             "entity": _pick(r, "idpConfig.entityId"),
                             "login": _pick(r, "idpConfig.singleSignOnServiceUri")})
    creds: dict[str, list[dict]] = {p["name"]: [] for p in profiles}
    code, rows, err = run_csv(["print", "inboundssocredentials"])
    if code == 0:
        for r in rows:
            n = _pick(r, "name")
            prof = n.split("/idpCredentials/")[0] if "/idpCredentials/" in n else \
                _pick(r, "inboundSamlSsoProfile", "profile")
            creds.setdefault(prof, []).append({
                "name": n, "updated": _when(_pick(r, "updateTime")),
                "bits": int(_pick(r, "rsaKeyInfo.keySize", "dsaKeyInfo.keySize") or 0)})
    return profiles, creds


# ------------------------------------------------------------------ check ---
@dataclass
class Finding:
    level: str                       # bad / warn / info / ok
    profile: str
    text: str
    fix: str = ""
    cert: dict = field(default_factory=dict)


def _level_for(days: int) -> str:
    if days < 0 or days <= WARN_DAYS[-1]:
        return "bad"
    if days <= WARN_DAYS[0]:
        return "warn"
    return "ok"


def check(profiles: list[dict], creds: dict[str, list[dict]], srcs: dict | None = None,
          read=read_source, now: datetime.datetime | None = None) -> list[Finding]:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    srcs = sources() if srcs is None else srcs
    out: list[Finding] = []
    for p in profiles:
        label = p["label"]
        cs = creds.get(p["name"], [])
        if not cs:
            out.append(Finding("bad", label, "Google has no certificate for this provider, "
                               "so sign-in through it can't work.",
                               "Upload the provider's signing certificate (Certificates tab "
                               "→ Upload to Google)."))
        for c in cs:
            if c["bits"] and c["bits"] < 2048:
                out.append(Finding("warn", label, f"Google holds a {c['bits']}-bit key – "
                                   "weaker than today's 2048-bit minimum.",
                                   "Ask the provider for a 2048-bit certificate and upload "
                                   "it."))
        newest_upload = max((c["updated"] for c in cs if c["updated"]), default=None)
        src = srcs.get(p["name"])
        if not src:
            if newest_upload and (now - newest_upload).days > OLD_UPLOAD_DAYS:
                out.append(Finding("warn", label,
                                   f"The certificate was uploaded {(now - newest_upload).days // 365}"
                                   " years ago – it may be close to expiring.",
                                   "Add the provider's metadata link so GAMbit can see the "
                                   "expiry date."))
            else:
                out.append(Finding("info", label, "GAMbit can't see this certificate's "
                                   "expiry date yet.",
                                   "Add the provider's SAML metadata link (or the certificate "
                                   "file) on the Certificates tab."))
            continue
        try:
            certs = read(src)
        except Exception as exc:  # noqa: BLE001
            out.append(Finding("warn", label, f"Couldn't read the provider's certificate: "
                               f"{exc}", "Check the metadata link or file on the "
                               "Certificates tab."))
            continue
        signing = [c for c in certs if c.use in ("", "signing")] or certs
        live = [c for c in signing if c.not_before <= now]
        current = max(live or signing, key=lambda c: c.not_after)
        for c in signing:
            d = c.days_left(now)
            lvl = _level_for(d)
            info = {"subject": c.subject, "expires": c.not_after.date().isoformat(),
                    "days": d, "fp": c.sha256, "bits": c.key_bits}
            if d < 0:
                text = f"The signing certificate “{c.subject}” EXPIRED on " \
                       f"{c.not_after:%b %d, %Y}."
                fix = "Get a new certificate from the provider and upload it to Google now."
            elif lvl != "ok":
                text = f"The signing certificate “{c.subject}” expires in {d} day(s) " \
                       f"({c.not_after:%b %d, %Y})."
                fix = ("Ask the provider for its new certificate, upload it to Google "
                       "alongside the old one, then remove the old one after the switch.")
            else:
                text = f"Signing certificate “{c.subject}” is good until " \
                       f"{c.not_after:%b %d, %Y} ({d} days)."
                fix = ""
            if c is not current and len(signing) > 1 and lvl == "ok":
                text += " (the provider's next certificate)"
            out.append(Finding(lvl, label, text, fix, info))
            if 0 < c.key_bits < 2048:
                out.append(Finding("warn", label, f"“{c.subject}” uses a {c.key_bits}-bit "
                                   "key.", "Ask the provider for a 2048-bit certificate."))
        if newest_upload and current.not_before > newest_upload + datetime.timedelta(days=1):
            out.append(Finding("bad", label,
                               f"The provider started using a newer certificate on "
                               f"{current.not_before:%b %d, %Y}, after the last one Google "
                               f"got ({newest_upload:%b %d, %Y}).",
                               "Upload the provider's current certificate to Google – until "
                               "then sign-ins may fail.", {"fp": current.sha256}))
    return out


def upload_args(profile: str, pem_path: str) -> list[str]:
    """GAM: add a certificate to a provider (Google keeps up to two, so the new one can go
    in before the old one stops being used)."""
    return ["create", "inboundssocredential", "profile", profile, "pemfile", pem_path]


def worst(findings: list[Finding]) -> str:
    order = {"bad": 3, "warn": 2, "info": 1, "ok": 0}
    return max((f.level for f in findings), key=lambda x: order[x], default="ok")


def save_last(findings: list[Finding], error: str = ""):
    settings.set(LAST_KEY, json.dumps({
        "at": datetime.datetime.now().isoformat(timespec="minutes"), "error": error,
        "findings": [{"level": f.level, "profile": f.profile, "text": f.text, "fix": f.fix}
                     for f in findings]}))


def last() -> dict:
    try:
        d = json.loads(settings.get(LAST_KEY, "") or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def attention() -> list[tuple[str, str]]:
    """(level, text) for Home and the digest, from the last check."""
    return [(f["level"], f"{f['profile']}: {f['text']}") for f in last().get("findings", [])
            if f.get("level") in ("bad", "warn")]


def _announce(findings: list[Finding], log=print) -> int:
    """Alert once per certificate per threshold (30, 14, 3 days, expired) – never every
    night for the same thing."""
    try:
        done = json.loads(settings.get(NOTIFIED_KEY, "") or "{}")
    except ValueError:
        done = {}
    msgs = []
    for f in findings:
        if f.level not in ("bad", "warn"):
            continue
        key = f.cert.get("fp") or hashlib.sha256(f"{f.profile}|{f.text}".encode())\
            .hexdigest()[:16]
        days = f.cert.get("days")
        step = ("expired" if days is not None and days < 0 else
                next((str(t) for t in reversed(WARN_DAYS) if days is not None and days <= t),
                     f.level))
        if done.get(key) == step:
            continue
        done[key] = step
        msgs.append(f"• {f.profile}: {f.text}" + (f"\n  → {f.fix}" if f.fix else ""))
    if msgs:
        from . import alerts
        alerts.notify("Single sign-on needs attention – if this isn't fixed, people can't "
                      "sign in:\n" + "\n".join(msgs), "GAMbit sign-in certificates")
        log(f"Sent an alert about {len(msgs)} sign-in certificate problem(s).")
    settings.set(NOTIFIED_KEY, json.dumps(done))
    return len(msgs)


def run(log=print, run_csv=None, read=read_source) -> list[Finding]:
    """The daily check (background task 'daily')."""
    try:
        profiles, creds = load_google(run_csv)
    except Exception as exc:  # noqa: BLE001
        save_last([], str(exc))
        log(f"Sign-in certificates not checked: {exc}")
        return []
    if not profiles:
        save_last([])
        return []
    findings = check(profiles, creds, read=read)
    save_last(findings)
    bad = [f for f in findings if f.level in ("bad", "warn")]
    log(f"Sign-in certificates: {len(profiles)} provider(s), {len(bad)} to look at.")
    _announce(findings, log)
    return findings
