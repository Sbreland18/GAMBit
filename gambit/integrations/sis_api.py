"""Live roster from your SIS or rostering hub. Every source is saved as a normal OneRoster
CSV .zip (users / orgs / classes / enrollments / courses), so roster sync, guardian sync,
Classroom yearly setup and the mismatch report work the same whichever one you use.

Sources
  • ClassLink Roster Server  – OneRoster 1.1, OAuth 1.0 signed requests
  • OneRoster (OAuth 2.0)    – Infinite Campus, Skyward, Aeries, Synergy, PowerSchool's
                               OneRoster plugin, Rapid Identity and other certified SISs
                               (OneRoster 1.1 or 1.2; client-credentials token)
  • Clever (Secure Sync)     – API v3.0 with the district token
  • PowerSchool (native API) – plugin client ID/secret, /ws/v1 student and school data
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import time
import urllib.parse

from ..settings import settings

PROVIDERS = {
    "classlink": "ClassLink (Roster Server)",
    "oneroster2": "OneRoster API (Infinite Campus, Skyward, Aeries, Synergy, …)",
    "clever": "Clever (Secure Sync)",
    "powerschool": "PowerSchool (native API)",
}
# OneRoster OAuth 2 presets: (label, base URL hint, token URL hint, version)
PRESETS = {
    "infinitecampus": ("Infinite Campus",
                       "https://<district>.infinitecampus.org/campus/api/ims/oneroster/"
                       "rostering/v1p2",
                       "https://<district>.infinitecampus.org/campus/oauth2/token?appName="
                       "<appName>", "1.2"),
    "skyward": ("Skyward (SMS 2.0 / Qmlativ)",
                "https://<host>/<path>/ims/oneroster/v1p1  (from Skyward's API settings)",
                "https://<host>/<path>/oauth/token  (from Skyward's API settings)", "1.1"),
    "aeries": ("Aeries", "https://<district>.aeries.net/admin/api/ims/oneroster/v1p1",
               "token URL from Aeries' OneRoster settings", "1.1"),
    "synergy": ("Synergy (Edupoint)", "https://<district>.edupoint.com/ims/oneroster/v1p1",
                "token URL from Synergy's OneRoster settings", "1.1"),
    "powerschool_or": ("PowerSchool OneRoster plugin",
                       "https://<server>/ims/oneroster/v1p1", "https://<server>/oauth/"
                       "access_token", "1.1"),
    "other": ("Other OneRoster SIS", "…/ims/oneroster/v1p1 or …/rostering/v1p2",
              "token URL", "auto"),
}


def provider() -> str:
    p = settings.get("sis_api/provider", "") or ""
    if not p and (settings.get("oneroster/url", "") or ""):
        p = "classlink"                      # settings from before more SISs were added
    return p if p in PROVIDERS else ""


def provider_name(p: str = "") -> str:
    p = p or provider()
    if p == "oneroster2":
        pre = settings.get("sis_api/oneroster2/preset", "other") or "other"
        return PRESETS.get(pre, PRESETS["other"])[0]
    return {"classlink": "ClassLink", "clever": "Clever",
            "powerschool": "PowerSchool"}.get(p, "your SIS")


def config(p: str = "") -> dict:
    p = p or provider()
    if p == "classlink":
        from . import oneroster
        return oneroster.config()
    g = lambda k: (settings.get(f"sis_api/{p}/{k}", "") or "").strip()  # noqa: E731
    if p == "oneroster2":
        return {"url": g("url").rstrip("/"), "token_url": g("token_url"),
                "client_id": g("client_id"), "secret": g("secret"),
                "version": g("version") or "auto"}
    if p == "clever":
        return {"token": g("token"), "url": (g("url") or "https://api.clever.com").rstrip("/")}
    if p == "powerschool":
        return {"url": g("url").rstrip("/"), "client_id": g("client_id"),
                "secret": g("secret"), "staff": g("staff") == "1"}
    return {}


def configured(p: str = "") -> bool:
    p = p or provider()
    c = config(p)
    if p == "classlink":
        return bool(c.get("url") and c.get("client_id") and c.get("secret"))
    if p == "oneroster2":
        return bool(c["url"] and c["token_url"] and c["client_id"] and c["secret"])
    if p == "clever":
        return bool(c["token"])
    if p == "powerschool":
        return bool(c["url"] and c["client_id"] and c["secret"])
    return False


def _json(status, body, who: str):
    if status in (401, 403):
        raise RuntimeError(f"{who} refused the request ({status}) – check the client ID, "
                           "secret or token, and what the app is allowed to read.")
    if status >= 400:
        raise RuntimeError(f"{who} returned {status}: {body[:300].decode('utf-8', 'replace')}")
    return json.loads(body.decode("utf-8-sig") or "{}")


# ======================================================== OAuth 2 tokens ===
_TOKENS: dict = {}


def client_credentials(token_url: str, client_id: str, secret: str, http=None,
                       who: str = "The SIS") -> str:
    """OAuth 2 client-credentials token (cached until it expires)."""
    from .. import net
    key = (token_url, client_id)
    tok = _TOKENS.get(key)
    if tok and tok[1] > time.time() + 60:
        return tok[0]
    basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": client_id,
                                   "client_secret": secret}).encode()
    status, _h, data = (http or net.request)(
        "POST", token_url, {"Authorization": f"Basic {basic}",
                            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                            "Accept": "application/json"}, body)
    d = _json(status, data, who)
    t = d.get("access_token")
    if not t:
        raise RuntimeError(f"{who} didn't return an access token.")
    _TOKENS[key] = (t, time.time() + int(d.get("expires_in", 3600) or 3600))
    return t


# ============================================== OneRoster 1.1 / 1.2 (OAuth 2) ===
def _or2_get(cfg, path, params, http):
    from .. import net
    tok = client_credentials(cfg["token_url"], cfg["client_id"], cfg["secret"], http,
                             provider_name("oneroster2"))
    url = f"{cfg['url']}/{path}?" + urllib.parse.urlencode(params)
    status, _h, body = (http or net.request)("GET", url, {"Authorization": f"Bearer {tok}",
                                                          "Accept": "application/json"})
    return _json(status, body, provider_name("oneroster2"))


def normalize_12(collection: str, item: dict) -> dict:
    """OneRoster 1.2 records → the 1.1 shape the CSV writer uses."""
    it = dict(item)
    if collection == "users":
        roles = it.get("roles") or []
        if roles and not it.get("role"):
            prim = next((r for r in roles if r.get("roleType") == "primary"), roles[0])
            it["role"] = prim.get("role", "")
            it["orgs"] = [r.get("org") for r in roles if isinstance(r.get("org"), dict)]
        if not it.get("identifier"):
            it["identifier"] = it.get("userMasterIdentifier", "") or it.get("identifier", "")
        if isinstance(it.get("enabledUser"), str):
            it["enabledUser"] = it["enabledUser"].lower() == "true"
    return it


def fetch_or2(collection: str, cfg: dict, http=None, page: int = 1000) -> list[dict]:
    v12 = cfg.get("version") == "1.2" or "v1p2" in cfg["url"]
    out, offset = [], 0
    while True:
        data = _or2_get(cfg, collection, {"limit": page, "offset": offset}, http)
        items = data.get(collection) or next((v for v in data.values()
                                              if isinstance(v, list)), [])
        out += [normalize_12(collection, i) if v12 else i for i in items]
        if len(items) < page:
            return out
        offset += page


# ================================================================ Clever ===
def _clever_get(cfg, uri, http):
    from .. import net
    url = uri if uri.startswith("http") else cfg["url"] + uri
    status, _h, body = (http or net.request)("GET", url, {
        "Authorization": f"Bearer {cfg['token']}", "Accept": "application/json"})
    return _json(status, body, "Clever")


def clever_all(cfg, path, http=None) -> list[dict]:
    out, uri = [], f"/v3.0/{path}" + ("&" if "?" in path else "?") + "limit=1000"
    while uri:
        d = _clever_get(cfg, uri, http)
        out += [x.get("data", x) for x in d.get("data", [])]
        uri = next((ln.get("uri") for ln in d.get("links", []) if ln.get("rel") == "next"), "")
        if uri and not d.get("data"):
            break
    return out


def clever_to_oneroster(users, schools, sections) -> dict[str, list[dict]]:
    orgs = [{"sourcedId": s["id"], "status": "active", "name": s.get("name", ""),
             "type": "school", "identifier": s.get("sis_id", "") or s.get("school_number", "")}
            for s in schools]
    out_users, guardians = [], {}
    for u in users:
        roles = u.get("roles") or {}
        name = u.get("name") or {}
        base = {"sourcedId": u["id"], "status": "active", "enabledUser": True,
                "givenName": name.get("first", ""), "familyName": name.get("last", ""),
                "middleName": name.get("middle", ""), "email": u.get("email", "") or ""}
        if "student" in roles:
            st = roles["student"]
            base.update(role="student", identifier=st.get("sis_id", "") or
                        st.get("student_number", ""), grades=[st.get("grade", "")]
                        if st.get("grade") else [],
                        orgs=[{"sourcedId": x} for x in st.get("schools", [])
                              or [st.get("school")] if x],
                        username=(st.get("credentials") or {}).get("district_username", ""))
            out_users.append(base)
        elif "teacher" in roles or "staff" in roles:
            r = roles.get("teacher") or roles.get("staff")
            base.update(role="teacher" if "teacher" in roles else "administrator",
                        identifier=r.get("sis_id", "") or r.get("teacher_number", "") or
                        r.get("staff_id", ""), orgs=[{"sourcedId": x} for x in
                                                     r.get("schools", []) or [r.get("school")]
                                                     if x])
            out_users.append(base)
        elif "contact" in roles:
            c = roles["contact"]
            base.update(role="guardian", identifier=c.get("sis_id", ""))
            out_users.append(base)
            for rel in c.get("student_relationships", []) or []:
                sid = rel.get("student") if isinstance(rel, dict) else rel
                if sid:
                    guardians.setdefault(sid, []).append(u["id"])
    for u in out_users:
        if u["role"] == "student" and guardians.get(u["sourcedId"]):
            u["agents"] = [{"sourcedId": g} for g in guardians[u["sourcedId"]]]
    classes, enrolls = [], []
    for s in sections:
        classes.append({"sourcedId": s["id"], "status": "active", "title": s.get("name", ""),
                        "classCode": s.get("section_number", "") or s.get("sis_id", ""),
                        "classType": "scheduled", "school": {"sourcedId": s.get("school", "")},
                        "grades": [s["grade"]] if s.get("grade") else [],
                        "subjects": [s["subject"]] if s.get("subject") else [],
                        "periods": [s["period"]] if s.get("period") else []})
        for role, key in (("student", "students"), ("teacher", "teachers")):
            for uid in s.get(key, []) or []:
                enrolls.append({"sourcedId": f"{s['id']}-{uid}", "status": "active",
                                "class": {"sourcedId": s["id"]},
                                "school": {"sourcedId": s.get("school", "")},
                                "user": {"sourcedId": uid}, "role": role,
                                "primary": key == "teachers" and uid == s.get("teacher")})
    return {"users": out_users, "orgs": orgs, "classes": classes, "enrollments": enrolls,
            "courses": []}


# =========================================================== PowerSchool ===
def _ps_get(cfg, path, params, http):
    from .. import net
    tok = client_credentials(cfg["url"] + "/oauth/access_token", cfg["client_id"],
                             cfg["secret"], http, "PowerSchool")
    url = f"{cfg['url']}{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    status, _h, body = (http or net.request)("GET", url, {"Authorization": f"Bearer {tok}",
                                                          "Accept": "application/json"})
    return _json(status, body, "PowerSchool")


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def ps_schools(cfg, http=None) -> list[dict]:
    d = _ps_get(cfg, "/ws/v1/district/school", {}, http)
    return _as_list((d.get("schools") or {}).get("school"))


def ps_people(cfg, school_id, kind: str, http=None) -> list[dict]:
    """kind: student | staff"""
    exp = "demographics,school_enrollment,contact_info" if kind == "student" else \
        "emails,school_affiliations"
    out, page = [], 1
    while True:
        d = _ps_get(cfg, f"/ws/v1/school/{school_id}/{kind}",
                    {"expansions": exp, "page": page, "pagesize": 100}, http)
        items = _as_list(((d.get(f"{kind}s") or d.get(kind) or {}) or {}).get(kind))
        out += items
        if len(items) < 100:
            return out
        page += 1


def powerschool_to_oneroster(schools, students, staff=()) -> dict[str, list[dict]]:
    orgs = [{"sourcedId": str(s.get("id", "")), "status": "active", "name": s.get("name", ""),
             "type": "school", "identifier": str(s.get("school_number", "") or "")}
            for s in schools]
    users = []
    for st in students:
        name = st.get("name") or {}
        enr = st.get("school_enrollment") or {}
        contact = st.get("contact_info") or {}
        active = str(enr.get("enroll_status", "A")).upper() in ("A", "0", "ACTIVE")
        users.append({"sourcedId": str(st.get("id", "")),
                      "status": "active" if active else "tobedeleted",
                      "enabledUser": active, "role": "student",
                      "givenName": name.get("first_name", ""),
                      "familyName": name.get("last_name", ""),
                      "middleName": name.get("middle_name", ""),
                      "identifier": str(st.get("local_id", "") or ""),
                      "username": st.get("student_username", "") or "",
                      "email": contact.get("email", "") or "",
                      "grades": [str(enr.get("grade_level", ""))]
                      if enr.get("grade_level") not in (None, "") else [],
                      "orgs": [{"sourcedId": str(enr.get("school_id", "") or "")}]})
    for s in staff:
        name = s.get("name") or {}
        emails = s.get("emails") or {}
        users.append({"sourcedId": f"staff-{s.get('id', '')}", "status": "active",
                      "enabledUser": True, "role": "teacher",
                      "givenName": name.get("first_name", ""),
                      "familyName": name.get("last_name", ""),
                      "identifier": str(s.get("local_id", "") or ""),
                      "email": emails.get("work_email", "") if isinstance(emails, dict) else "",
                      "orgs": [{"sourcedId": str(s.get("school_id", "") or "")}]})
    return {"users": users, "orgs": orgs, "classes": [], "enrollments": [], "courses": []}


# =================================================================== all ===
def cache_path(p: str = "") -> str:
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    d = os.path.join(base, "oneroster")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{p or provider() or 'sis'}-oneroster.zip")


def download(p: str = "", cfg: dict | None = None, http=None, path: str = "",
             progress=None) -> str:
    """Pull the roster and save it as a OneRoster .zip. Returns the path."""
    from . import oneroster
    p = p or provider()
    if not p:
        raise RuntimeError("Choose your SIS in Settings & Updates → Integrations first.")
    cfg = cfg or config(p)
    if p == "classlink":
        return oneroster.download(cfg=cfg, http=http, path=path or cache_path(p),
                                  progress=progress)
    if p == "oneroster2":
        data = {}
        for c in ("users", "orgs", "classes", "enrollments", "courses"):
            try:
                data[c] = fetch_or2(c, cfg, http)
            except RuntimeError:
                if c in ("users", "orgs"):
                    raise
                data[c] = []
            if progress:
                progress(c, len(data[c]))
    elif p == "clever":
        data = clever_to_oneroster(clever_all(cfg, "users", http),
                                   clever_all(cfg, "schools", http),
                                   _optional(lambda: clever_all(cfg, "sections", http)))
    elif p == "powerschool":
        schools = ps_schools(cfg, http)
        students, staff = [], []
        for s in schools:
            students += ps_people(cfg, s.get("id"), "student", http)
            if cfg.get("staff"):
                staff += [{**x, "school_id": s.get("id")} for x in
                          _optional(lambda: ps_people(cfg, s.get("id"), "staff", http))]
        data = powerschool_to_oneroster(schools, students, staff)
    else:
        raise RuntimeError(f"Unknown SIS source “{p}”.")
    path = path or cache_path(p)
    oneroster.build_zip(data, path, source=provider_name(p))
    settings.set("sis_api/last_download", datetime.datetime.now().isoformat(timespec="minutes"))
    return path


def _optional(fn):
    try:
        return fn()
    except RuntimeError:
        return []


def test(p: str = "", cfg: dict | None = None, http=None) -> str:
    from . import oneroster
    p = p or provider()
    cfg = cfg or config(p)
    if p == "classlink":
        return oneroster.test(cfg, http)
    if p == "oneroster2":
        d = _or2_get(cfg, "orgs", {"limit": 5, "offset": 0}, http)
        orgs = d.get("orgs", [])
    elif p == "clever":
        orgs = [x.get("data", x) for x in _clever_get(cfg, "/v3.0/schools?limit=5",
                                                      http).get("data", [])]
    elif p == "powerschool":
        orgs = ps_schools(cfg, http)[:5]
    else:
        raise RuntimeError("Choose your SIS first.")
    return (f"Connected to {provider_name(p)} – first schools: " +
            ", ".join(o.get("name", "") for o in orgs[:5]))
