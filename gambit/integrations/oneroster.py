"""ClassLink Roster Server (OneRoster 1.1 REST) – pull the roster live instead of exporting
files. Requests are signed with OAuth 1.0 HMAC-SHA256 the way ClassLink's own sample code
does. The data is written out as a normal OneRoster CSV .zip, so roster sync, guardian sync
and Classroom yearly setup all work unchanged."""

from __future__ import annotations

import base64
import csv
import datetime
import hashlib
import hmac
import io
import json
import os
import secrets
import time
import urllib.parse
import zipfile

from ..settings import settings

COLUMNS = {
    "users": ["sourcedId", "status", "dateLastModified", "enabledUser", "orgSourcedIds",
              "role", "username", "userIds", "givenName", "familyName", "middleName",
              "identifier", "email", "sms", "phone", "agentSourcedIds", "grades", "password"],
    "orgs": ["sourcedId", "status", "dateLastModified", "name", "type", "identifier",
             "parentSourcedId"],
    "classes": ["sourcedId", "status", "dateLastModified", "title", "grades",
                "courseSourcedId", "classCode", "classType", "location", "schoolSourcedId",
                "termSourcedIds", "subjects", "subjectCodes", "periods"],
    "enrollments": ["sourcedId", "status", "dateLastModified", "classSourcedId",
                    "schoolSourcedId", "userSourcedId", "role", "primary", "beginDate",
                    "endDate"],
    "courses": ["sourcedId", "status", "dateLastModified", "schoolYearSourcedId", "title",
                "courseCode", "grades", "orgSourcedId", "subjects"],
}
# JSON reference fields → CSV column
REFS = {"orgs": "orgSourcedIds", "agents": "agentSourcedIds", "terms": "termSourcedIds",
        "parent": "parentSourcedId", "course": "courseSourcedId", "school": "schoolSourcedId",
        "class": "classSourcedId", "user": "userSourcedId", "schoolYear": "schoolYearSourcedId",
        "org": "orgSourcedId"}


def config() -> dict:
    return {"url": (settings.get("oneroster/url", "") or "").strip().rstrip("/"),
            "client_id": (settings.get("oneroster/client_id", "") or "").strip(),
            "secret": (settings.get("oneroster/secret", "") or "").strip()}


def configured() -> bool:
    c = config()
    return bool(c["url"] and c["client_id"] and c["secret"])


# --------------------------------------------------------------- signing ---
def _nonce(n: int) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    return "".join(secrets.choice(chars) for _ in range(n))


def sign(url: str, client_id: str, secret: str, params: dict, method: str = "GET",
         timestamp: str = "", nonce: str = "") -> str:
    """The Authorization header for one request (OAuth 1.0, HMAC-SHA256)."""
    timestamp = timestamp or str(int(time.time()))
    nonce = nonce or _nonce(len(timestamp))
    oauth = {"oauth_consumer_key": client_id, "oauth_signature_method": "HMAC-SHA256",
             "oauth_timestamp": timestamp, "oauth_nonce": nonce}
    allp = {**oauth, **{k: str(v) for k, v in params.items()}}
    base = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in sorted(allp.items()))
    base_string = f"{method}&{urllib.parse.quote_plus(url)}&{urllib.parse.quote_plus(base)}"
    key = urllib.parse.quote_plus(secret) + "&"
    sig = base64.b64encode(hmac.new(key.encode(), base_string.encode(),
                                    hashlib.sha256).digest()).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ",".join(f'{k}="{urllib.parse.quote_plus(v)}"' for k, v in oauth.items())


def get(endpoint: str, params: dict | None = None, cfg: dict | None = None,
        http=None) -> dict:
    from .. import net
    cfg = cfg or config()
    url = f"{cfg['url']}/{endpoint.lstrip('/')}"
    params = params or {}
    hdr = {"Authorization": sign(url, cfg["client_id"], cfg["secret"], params),
           "Accept": "application/json"}
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    status, _h, body = (http or net.request)("GET", full, hdr)
    if status == 401:
        raise RuntimeError("ClassLink said the client ID or secret is wrong (401).")
    if status >= 400:
        raise RuntimeError(f"ClassLink returned {status}: {body[:300].decode('utf-8', 'replace')}")
    return json.loads(body.decode("utf-8-sig") or "{}")


def fetch_all(collection: str, cfg: dict | None = None, http=None, page: int = 1000,
              progress=None) -> list[dict]:
    out, offset = [], 0
    while True:
        data = get(collection, {"limit": page, "offset": offset}, cfg, http)
        items = data.get(collection) or next((v for v in data.values() if isinstance(v, list)),
                                             [])
        out += items
        if progress:
            progress(collection, len(out))
        if len(items) < page:
            return out
        offset += page


# ------------------------------------------------------------- to CSV ---
def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ",".join(_cell(x.get("sourcedId") if isinstance(x, dict) else x) for x in v)
    if isinstance(v, dict):
        return str(v.get("sourcedId", "")) or json.dumps(v)
    return str(v)


def to_row(item: dict, cols: list[str]) -> dict:
    row = {c: "" for c in cols}
    for k, v in item.items():
        col = REFS.get(k, k)
        if col in row:
            row[col] = _cell(v)
    if "userIds" in row and isinstance(item.get("userIds"), list):
        row["userIds"] = ",".join(f"{{{u.get('type', '')}:{u.get('identifier', '')}}}"
                                  for u in item["userIds"] if isinstance(u, dict))
    return row


def build_zip(data: dict[str, list[dict]], path: str, source: str = "ClassLink API") -> str:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, items in data.items():
            cols = COLUMNS[name]
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=cols)
            w.writeheader()
            for it in items:
                w.writerow(to_row(it, cols))
            zf.writestr(f"{name}.csv", buf.getvalue())
        zf.writestr("manifest.csv", "propertyName,value\nmanifest.version,1.0\n"
                                    f"oneroster.version,1.1\nsource.systemName,{source}\n")
    return path


def cache_path() -> str:
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    d = os.path.join(base, "oneroster")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "classlink-oneroster.zip")


def download(collections=("users", "orgs", "classes", "enrollments", "courses"),
             cfg: dict | None = None, http=None, progress=None, path: str = "") -> str:
    """Pull everything and save it as a OneRoster .zip. Returns the path."""
    data = {}
    for c in collections:
        try:
            data[c] = fetch_all(c, cfg, http, progress=progress)
        except RuntimeError:
            if c in ("users", "orgs"):
                raise
            data[c] = []                       # optional collections may not be shared
    path = path or cache_path()
    build_zip(data, path)
    settings.set("oneroster/last_download", datetime.datetime.now().isoformat(
        timespec="minutes"))
    return path


def test(cfg: dict | None = None, http=None) -> str:
    data = get("orgs", {"limit": 5, "offset": 0}, cfg, http)
    orgs = data.get("orgs", [])
    names = ", ".join(o.get("name", "") for o in orgs[:5])
    return f"Connected – {len(orgs)} org(s) in the first page: {names}"
