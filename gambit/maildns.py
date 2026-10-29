"""Email domain health: the public DNS records that stop people sending mail that looks like
it's from the district (SPF, DKIM, DMARC) and make sure mail reaches Gmail (MX).

Looked up with DNS-over-HTTPS (Google Public DNS, then Cloudflare), so it works the same on
every PC without extra tools. Only domain names are sent – nothing about people.
"""

from __future__ import annotations

import base64
import datetime
import json
import re
import urllib.parse
from dataclasses import dataclass

from .settings import settings

LAST_KEY = "maildns/last_check"
SELECTORS_KEY = "maildns/selectors"          # {domain: "google"}
NOTIFIED_KEY = "maildns/notified"
RESOLVERS = ("https://dns.google/resolve", "https://cloudflare-dns.com/dns-query")
TYPES = {"TXT": 16, "MX": 15}
GOOGLE_MX = ("aspmx.l.google.com", "smtp.google.com", "googlemail.com", "google.com")
SPF_LOOKUP_TERMS = ("include", "a", "mx", "ptr", "exists", "redirect")


class DNSError(RuntimeError):
    pass


def _txt(data: str) -> str:
    """'"v=spf1 …" "more"' → 'v=spf1 …more' (TXT records come in quoted pieces)."""
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', data or "")
    return "".join(p.replace('\\"', '"') for p in parts) if parts else (data or "").strip()


def doh(name: str, rtype: str) -> list[str]:
    """Records of one type for a name (empty if there are none). Raises DNSError when no
    resolver could answer."""
    from . import net
    name = name.strip().rstrip(".").lower()
    if not re.fullmatch(r"[a-z0-9_.-]{1,253}", name):
        raise DNSError(f"Not a domain name: {name}")
    last = ""
    for base in RESOLVERS:
        url = f"{base}?name={urllib.parse.quote(name)}&type={rtype}"
        try:
            code, _h, body = net.request("GET", url, {"Accept": "application/dns-json"},
                                         timeout=15)
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            continue
        if code != 200:
            last = f"HTTP {code}"
            continue
        try:
            d = json.loads(body.decode("utf-8"))
        except ValueError:
            last = "unreadable answer"
            continue
        status = d.get("Status")
        if status == 3:                                   # NXDOMAIN
            return []
        if status != 0:
            last = f"DNS status {status}"
            continue
        want = TYPES[rtype]
        out = []
        for a in d.get("Answer") or []:
            if a.get("type") != want:
                continue                                  # CNAME steps etc.
            out.append(_txt(a.get("data", "")) if rtype == "TXT" else
                       str(a.get("data", "")).strip())
        return out
    try:                                   # web DNS blocked (school filters often do):
        return nslookup(name, rtype)       # use this computer's own resolver
    except DNSError as exc:
        raise DNSError(f"Couldn't look up {name} ({last or 'no answer'}; {exc}).") from None


def parse_nslookup(out: str, rtype: str) -> list[str]:
    """Records from nslookup's output (Windows and Linux wording)."""
    low = out.lower()
    if rtype == "MX":
        out_mx = []
        for m in re.finditer(r"mail exchanger\s*=\s*(?:(\d+)\s+)?(\S+)", out, re.I):
            out_mx.append(f"{m.group(1) or 0} {m.group(2).rstrip('.')}")
        if not out_mx and "mx preference" in low:         # Windows' layout
            prefs = re.findall(r"mx preference\s*=\s*(\d+),\s*mail exchanger\s*=\s*(\S+)",
                               out, re.I)
            out_mx = [f"{p} {h.rstrip('.')}" for p, h in prefs]
        return out_mx
    recs, cur = [], None
    for ln in out.splitlines():
        if re.search(r"\btext\s*=", ln, re.I):
            if cur is not None:
                recs.append(cur)
            cur = _txt(ln.split("=", 1)[1])
        elif cur is not None and ln.strip().startswith('"'):
            cur += _txt(ln)                  # Windows puts long records on several lines
        elif cur is not None and ln.strip():
            recs.append(cur)
            cur = None
    if cur is not None:
        recs.append(cur)
    return recs


def nslookup(name: str, rtype: str) -> list[str]:
    import subprocess
    import sys
    kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    try:
        p = subprocess.run(["nslookup", f"-type={rtype}", name], capture_output=True,
                           text=True, timeout=15, **kw)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DNSError(f"nslookup didn't work: {exc}") from None
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    low = out.lower()
    if "non-existent domain" in low or "nxdomain" in low or "can't find" in low or \
            "no answer" in low or "can\u2019t find" in low:
        return []
    if "timed out" in low or "no response from server" in low:
        raise DNSError("DNS server didn't answer")
    return parse_nslookup(out, rtype)


# ------------------------------------------------------------------ checks ---
@dataclass
class Finding:
    level: str              # bad / warn / info / ok
    domain: str
    check: str              # MX / SPF / DKIM / DMARC
    text: str
    fix: str = ""


def selector(domain: str) -> str:
    try:
        d = json.loads(settings.get(SELECTORS_KEY, "") or "{}")
    except ValueError:
        d = {}
    return (d.get(domain.lower()) or "google").strip() or "google"


def set_selector(domain: str, sel: str):
    try:
        d = json.loads(settings.get(SELECTORS_KEY, "") or "{}")
    except ValueError:
        d = {}
    sel = (sel or "").strip().lower()
    if sel and not re.fullmatch(r"[a-z0-9_-]{1,63}", sel):
        raise ValueError("A DKIM selector is letters, numbers, - and _ only.")
    if sel and sel != "google":
        d[domain.lower()] = sel
    else:
        d.pop(domain.lower(), None)
    settings.set(SELECTORS_KEY, json.dumps(d))


def check_mx(domain: str, look) -> list[Finding]:
    mx = look(domain, "MX")
    hosts = [m.split()[-1].rstrip(".").lower() for m in mx if m.split()]
    if not hosts:
        return [Finding("bad", domain, "MX", "No mail servers (MX records) – mail sent to "
                        f"@{domain} bounces.",
                        "If people get mail at this domain, add Google's MX record "
                        "(smtp.google.com, priority 1) at your DNS host.")]
    if any(h == g or h.endswith("." + g) for h in hosts for g in GOOGLE_MX):
        return [Finding("ok", domain, "MX", "Mail is delivered to Google.")]
    return [Finding("info", domain, "MX", f"Mail goes to {', '.join(hosts[:3])} first, not "
                    "straight to Google (a mail filter or another system).",
                    "Fine if that's your spam filter – make sure it passes mail on to "
                    "Google.")]


def _spf_lookups(record: str, look, depth: int = 0, seen: set | None = None) -> int:
    """How many DNS lookups an SPF record makes (the limit is 10)."""
    seen = seen if seen is not None else set()
    n = 0
    for term in record.split()[1:]:
        t = term.lstrip("+-~?").lower()
        name = t.split(":", 1)[0].split("=", 1)[0].split("/", 1)[0]
        if name not in SPF_LOOKUP_TERMS:
            continue
        n += 1
        if name in ("include", "redirect") and depth < 6:
            target = t.split(":", 1)[1] if ":" in t else t.split("=", 1)[-1]
            if target in seen:
                continue
            seen.add(target)
            try:
                inner = [r for r in look(target, "TXT") if r.lower().startswith("v=spf1")]
            except DNSError:
                continue
            if inner:
                n += _spf_lookups(inner[0], look, depth + 1, seen)
    return n


def check_spf(domain: str, look) -> list[Finding]:
    recs = [r for r in look(domain, "TXT") if r.lower().startswith("v=spf1")]
    if not recs:
        return [Finding("bad", domain, "SPF", "No SPF record – anyone can send mail that "
                        f"claims to be from @{domain}, and Gmail and Yahoo may reject your "
                        "own bulk mail.",
                        "Add a TXT record at your DNS host: v=spf1 include:_spf.google.com "
                        "~all (plus any other service that sends as you).")]
    if len(recs) > 1:
        return [Finding("bad", domain, "SPF", f"{len(recs)} SPF records – receiving servers "
                        "treat that as no SPF at all.",
                        "Merge them into one v=spf1 record.")]
    r = recs[0]
    low = r.lower().split()
    out = []
    if "include:_spf.google.com" not in low and "redirect=_spf.google.com" not in low:
        out.append(Finding("warn", domain, "SPF", "The SPF record doesn't include Google, so "
                           "mail you send from Gmail may fail SPF.",
                           "Add include:_spf.google.com to the record."))
    ending = next((t for t in low if t.endswith("all") and t.lstrip("+-~?") == "all"), "")
    if ending in ("+all", "all"):
        out.append(Finding("bad", domain, "SPF", f"The record ends with {ending}, which lets "
                           "every server on the internet send as you.",
                           "End it with ~all (or -all once you're sure the list is "
                           "complete)."))
    elif ending == "?all" or not ending:
        out.append(Finding("warn", domain, "SPF", "The record doesn't say what to do with "
                           "other senders (no ~all or -all).", "End it with ~all."))
    n = _spf_lookups(r, look)
    if n > 10:
        out.append(Finding("bad", domain, "SPF", f"The record needs {n} DNS lookups – over "
                           "the limit of 10, so it fails for everyone.",
                           "Remove services you no longer use, or ask your DNS host about "
                           "SPF flattening."))
    if not out:
        out.append(Finding("ok", domain, "SPF", f"SPF is set up ({r[:80]})."))
    return out


def _key_bits(p: str) -> int:
    try:
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        k = load_der_public_key(base64.b64decode(re.sub(r"\s+", "", p)))
        return int(getattr(k, "key_size", 0) or 0)
    except Exception:  # noqa: BLE001
        return 0


def check_dkim(domain: str, look) -> list[Finding]:
    sel = selector(domain)
    name = f"{sel}._domainkey.{domain}"
    recs = [r for r in look(name, "TXT") if "p=" in r.replace(" ", "")]
    how = ("Admin console → Apps → Google Workspace → Gmail → Authenticate email: "
           "generate a 2048-bit key, add the TXT record it shows at your DNS host, then "
           "click Start authentication.")
    if not recs:
        return [Finding("bad", domain, "DKIM", f"No DKIM key at {name} – your mail isn't "
                        "signed with your own domain, so it's easier to fake and more "
                        "likely to land in spam.", how)]
    tags = dict(t.strip().split("=", 1) for t in recs[0].split(";") if "=" in t)
    p = (tags.get("p") or "").strip()
    if not p:
        return [Finding("bad", domain, "DKIM", "The DKIM key has been revoked (empty p=).",
                        how)]
    bits = _key_bits(p)
    if bits and bits < 2048:
        return [Finding("warn", domain, "DKIM", f"The DKIM key is {bits}-bit; 2048-bit is "
                        "today's standard.", how)]
    return [Finding("ok", domain, "DKIM", f"DKIM is published (selector “{sel}”"
                    + (f", {bits}-bit" if bits else "") + ").")]


def check_dmarc(domain: str, look) -> list[Finding]:
    recs = [r for r in look(f"_dmarc.{domain}", "TXT") if r.lower().startswith("v=dmarc1")]
    example = (f"Add a TXT record named _dmarc.{domain}: v=DMARC1; p=quarantine; "
               f"rua=mailto:dmarc-reports@{domain}")
    if not recs:
        return [Finding("bad", domain, "DMARC", "No DMARC policy – receiving servers aren't "
                        "told to reject mail that pretends to be from you, and Gmail and "
                        "Yahoo require DMARC for bulk senders.", example)]
    if len(recs) > 1:
        return [Finding("bad", domain, "DMARC", f"{len(recs)} DMARC records – receivers "
                        "ignore all of them.", "Keep exactly one.")]
    tags = {k.strip().lower(): v.strip() for k, _s, v in
            (t.partition("=") for t in recs[0].split(";")) if k.strip()}
    pol = tags.get("p", "").lower()
    out = []
    if pol not in ("none", "quarantine", "reject"):
        out.append(Finding("bad", domain, "DMARC", "The DMARC record has no valid p= policy.",
                           example))
    elif pol == "none":
        out.append(Finding("warn", domain, "DMARC", "DMARC is only watching (p=none) – fake "
                           "mail claiming to be from you is still delivered.",
                           "Once the reports show your real mail passes, change it to "
                           "p=quarantine, then p=reject."))
    try:
        pct = int(tags.get("pct", "100"))
    except ValueError:
        pct = 100
    if pol in ("quarantine", "reject") and pct < 100:
        out.append(Finding("info", domain, "DMARC", f"The policy only applies to {pct}% of "
                           "failing mail.", "Raise pct to 100 when you're ready."))
    if not tags.get("rua"):
        out.append(Finding("info", domain, "DMARC", "No rua= address, so nobody gets DMARC "
                           "reports about who sends as you.",
                           f"Add rua=mailto:dmarc-reports@{domain} (any mailbox you read)."))
    if not out or all(f.level == "info" for f in out):
        out.insert(0, Finding("ok", domain, "DMARC", f"DMARC policy is p={pol}."))
    return out


def check_domain(domain: str, look=doh, mail_domain: bool = True) -> list[Finding]:
    out: list[Finding] = []
    for fn in (check_mx, check_spf, check_dkim, check_dmarc):
        try:
            res = fn(domain, look)
        except DNSError as exc:
            res = [Finding("warn", domain, fn.__name__[6:].upper(), str(exc),
                           "Try again later – DNS couldn't be reached.")]
        if not mail_domain:                     # an alias nobody sends from: softer
            res = [Finding("info" if f.level in ("bad", "warn") and
                           f.check in ("DKIM",) else f.level, f.domain, f.check, f.text,
                           f.fix) for f in res]
        out += res
    return out


# ----------------------------------------------------------------- domains ---
def domains(run_csv=None) -> list[tuple[str, bool]]:
    """[(domain, sends mail)] – the primary and secondary domains, then domain aliases."""
    from .directory import run_gam_csv
    run_csv = run_csv or run_gam_csv
    out: list[tuple[str, bool]] = []
    code, rows, err = run_csv(["print", "domains"])
    if code != 0:
        raise RuntimeError((err or "").strip().splitlines()[-1] if (err or "").strip()
                           else "Couldn't list the domains.")
    for r in rows:
        low = {k.lower(): v for k, v in r.items()}
        d = (low.get("domainname") or "").strip().lower()
        if d and str(low.get("verified", "True")).lower() != "false":
            out.append((d, True))
    code, rows, _e = run_csv(["print", "domainaliases"])
    if code == 0:
        for r in rows:
            low = {k.lower(): v for k, v in r.items()}
            d = (low.get("domainaliasname") or "").strip().lower()
            if d and d not in {x for x, _m in out} and \
                    str(low.get("verified", "True")).lower() != "false":
                out.append((d, False))
    return out


def run_all(look=doh, run_csv=None, doms=None) -> list[Finding]:
    doms = doms if doms is not None else domains(run_csv)
    out: list[Finding] = []
    for d, mail in doms:
        out += check_domain(d, look, mail)
    return out


def save_last(findings: list[Finding], error: str = ""):
    settings.set(LAST_KEY, json.dumps({
        "at": datetime.datetime.now().isoformat(timespec="minutes"), "error": error,
        "findings": [f.__dict__ for f in findings]}))


def last() -> dict:
    try:
        d = json.loads(settings.get(LAST_KEY, "") or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def attention() -> list[tuple[str, str]]:
    return [(f["level"], f"{f['domain']} {f['check']}: {f['text']}")
            for f in last().get("findings", []) if f.get("level") == "bad"]


def run(log=print, run_csv=None, look=doh) -> list[Finding]:
    """Daily: check every domain; alert about problems that are new since last time."""
    try:
        findings = run_all(look, run_csv)
    except Exception as exc:  # noqa: BLE001
        save_last([], str(exc))
        log(f"Email domain check skipped: {exc}")
        return []
    save_last(findings)
    bad = [f for f in findings if f.level == "bad"]
    log(f"Email domain check: {len(bad)} problem(s).")
    try:
        before = set(json.loads(settings.get(NOTIFIED_KEY, "") or "[]"))
    except ValueError:
        before = set()
    now = {f"{f.domain}|{f.check}|{f.text}" for f in bad}
    new = [f for f in bad if f"{f.domain}|{f.check}|{f.text}" not in before]
    if new:
        from . import alerts
        alerts.notify("Email security problems (people could send mail that looks like it's "
                      "from the district):\n" + "\n".join(
                          f"• {f.domain} {f.check}: {f.text}\n  → {f.fix}" for f in new),
                      "GAMbit email domain check")
    settings.set(NOTIFIED_KEY, json.dumps(sorted(now)))
    return findings
