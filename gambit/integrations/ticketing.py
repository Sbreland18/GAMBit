"""Help-desk systems behind one interface: link a ticket while you work, add notes, open
tickets for alerts, read the open-ticket queue, and (where the system allows it) resolve.

Supported: Incident IQ, Zendesk, Freshservice, Freshdesk, ServiceNow, Jira Service
Management, SolarWinds Web Help Desk, TeamDynamix and osTicket (osTicket's API can only
create tickets).

Every function takes optional cfg/http so it can be tested without a network.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.parse

from ..settings import settings

PROVIDERS = {
    "iiq": "Incident IQ", "zendesk": "Zendesk", "freshservice": "Freshservice",
    "freshdesk": "Freshdesk", "servicenow": "ServiceNow",
    "jira": "Jira Service Management", "whd": "SolarWinds Web Help Desk",
    "teamdynamix": "TeamDynamix", "osticket": "osTicket",
}
# provider → [(key, label, placeholder, secret)]
FIELDS = {
    "iiq": [("site", "Site", "yourdistrict.incidentiq.com", False),
            ("site_id", "Site ID", "Administration → Developer Tools", False),
            ("token", "API token", "", True),
            ("product_id", "Ticketing product ID", "for the ticket queue (Developer Tools)",
             False)],
    "zendesk": [("subdomain", "Subdomain", "yourdistrict  (yourdistrict.zendesk.com)", False),
                ("email", "Agent email", "you@district.org", False),
                ("token", "API token", "Admin Center → Apps and integrations → APIs", True)],
    "freshservice": [("domain", "Domain", "yourdistrict.freshservice.com", False),
                     ("api_key", "API key", "Profile settings → API key", True),
                     ("email", "Requester for new tickets", "it@district.org", False)],
    "freshdesk": [("domain", "Domain", "yourdistrict.freshdesk.com", False),
                  ("api_key", "API key", "Profile settings → API key", True),
                  ("email", "Requester for new tickets", "it@district.org", False)],
    "servicenow": [("instance", "Instance", "yourdistrict  (yourdistrict.service-now.com)",
                    False),
                   ("user", "Integration user", "", False),
                   ("password", "Password", "", True),
                   ("table", "Table", "incident", False),
                   ("query", "Extra filter for the queue", "e.g. assignment_group.name=K12 IT",
                    False),
                   ("close_code", "Close code", "Solution provided", False)],
    "jira": [("site", "Site", "https://yourdistrict.atlassian.net", False),
             ("email", "Account email", "", False),
             ("token", "API token", "id.atlassian.com → Security → API tokens", True),
             ("service_desk", "Service desk ID", "for new tickets", False),
             ("request_type", "Request type ID", "for new tickets", False),
             ("jql", "Queue filter (JQL)", "project = HELP AND statusCategory != Done", False),
             ("resolve_transition", "Resolve transition name", "Resolve", False)],
    "whd": [("url", "Web Help Desk address", "https://helpdesk.district.org", False),
            ("api_key", "Tech API key", "My Profile → API key", True),
            ("closed_status_id", "Status ID for resolved", "3", False)],
    "teamdynamix": [("url", "TeamDynamix address", "https://yourdistrict.teamdynamix.com",
                     False),
                    ("app_id", "Ticketing app ID", "", False),
                    ("beid", "BEID", "Admin → Organization details", False),
                    ("key", "Web services key", "", True),
                    ("resolved_status_id", "Status ID for resolved", "", False)],
    "osticket": [("url", "osTicket address", "https://helpdesk.district.org", False),
                 ("api_key", "API key", "Admin panel → Manage → API", True),
                 ("email", "Requester email", "it@district.org", False)],
}
CAN = {
    "iiq": {"read", "note", "create", "list"},
    "zendesk": {"read", "note", "create", "list", "resolve"},
    "freshservice": {"read", "note", "create", "list", "resolve"},
    "freshdesk": {"read", "note", "create", "list", "resolve"},
    "servicenow": {"read", "note", "create", "list", "resolve"},
    "jira": {"read", "note", "create", "list", "resolve"},
    "whd": {"read", "note", "create", "list", "resolve"},
    "teamdynamix": {"read", "note", "create", "list", "resolve"},
    "osticket": {"create"},
}


# =============================================================== settings ===
def provider() -> str:
    p = settings.get("ticketing/provider", "") or ""
    if not p and (settings.get("iiq/site", "") or ""):
        p = "iiq"
    return p if p in PROVIDERS else ""


def name(p: str = "") -> str:
    return PROVIDERS.get(p or provider(), "your help desk")


def key_for(p: str, k: str) -> str:
    return f"iiq/{k}" if p == "iiq" else f"ticketing/{p}/{k}"


def config(p: str = "") -> dict:
    p = p or provider()
    c = {k: (settings.get(key_for(p, k), "") or "").strip() for k, *_ in FIELDS.get(p, [])}
    c["template"] = (settings.get(key_for(p, "template"), "") or "").strip()
    c["provider"] = p
    return c


def configured(p: str = "") -> bool:
    p = p or provider()
    if not p:
        return False
    c = config(p)
    need = [k for k, _l, _ph, _s in FIELDS[p][:3] if k not in ("email", "product_id")]
    if p == "osticket":
        need = ["url", "api_key"]
    return all(c.get(k) for k in need)


def can(what: str, p: str = "") -> bool:
    return what in CAN.get(p or provider(), set())


def option(key: str, default=False):
    """auto_note / alert_tickets, with the old Incident IQ settings as a fallback."""
    v = settings.get(f"ticketing/{key}", None)
    if v in (None, ""):
        v = settings.get(f"iiq/{key}", default)
    return v


def template(p: str = "") -> dict:
    try:
        return json.loads(config(p).get("template") or "{}")
    except ValueError:
        return {}


# ================================================================== http ===
def _req(method, url, headers, body=None, http=None, who="The help desk"):
    from .. import net
    status, _h, data = (http or net.request)(method, url, headers, body)
    if status in (401, 403):
        raise RuntimeError(f"{who} refused the request ({status}) – check the login details "
                           "in Settings → Integrations.")
    if status == 404:
        raise RuntimeError(f"{who} couldn't find that ticket (404).")
    if status >= 400:
        raise RuntimeError(f"{who} returned {status}: {data[:300].decode('utf-8', 'replace')}")
    txt = data.decode("utf-8-sig") if data else ""
    try:
        return json.loads(txt) if txt.strip() else {}
    except ValueError:
        return txt


def _basic(a: str, b: str) -> str:
    return "Basic " + base64.b64encode(f"{a}:{b}".encode()).decode()


JSON = {"Accept": "application/json", "Content-Type": "application/json"}


def _host(v: str, suffix: str = "") -> str:
    v = (v or "").strip().rstrip("/")
    if not v:
        return ""
    if "://" not in v:
        v = f"https://{v}" if ("." in v or not suffix) else f"https://{v}{suffix}"
    return v


# ============================================================== ticket ids ===
def ticket_id(text: str, p: str = "") -> str:
    p = p or provider()
    t = (text or "").strip()
    if not t:
        return ""
    if p == "iiq":
        from . import iiq
        return iiq.ticket_id(t)
    if p == "servicenow":
        m = re.search(r"\b((?:INC|RITM|REQ|SCTASK|TASK)\d{5,})\b", t, re.I) or \
            re.search(r"sys_id(?:=|%3D)([0-9a-f]{32})", t, re.I) or \
            re.fullmatch(r"([0-9a-f]{32})", t, re.I)
        return m.group(1) if m else ""
    if p == "jira":
        m = re.search(r"\b([A-Z][A-Z0-9_]+-\d+)\b", t)
        return m.group(1) if m else ""
    m = re.search(r"(?:tickets?/|TicketID=|ticket=|#)(\d+)", t, re.I) or \
        re.fullmatch(r"(\d+)", t)
    return m.group(1) if m else ""


def link(tid: str, p: str = "", cfg: dict | None = None) -> str:
    p = p or provider()
    c = cfg or config(p)
    if not tid:
        return ""
    if p == "iiq":
        from . import iiq
        return iiq.ticket_link(tid)
    if p == "zendesk":
        return f"{_host(c['subdomain'], '.zendesk.com')}/agent/tickets/{tid}"
    if p == "freshservice":
        return f"{_host(c['domain'])}/a/tickets/{tid}"
    if p == "freshdesk":
        return f"{_host(c['domain'])}/a/tickets/{tid}"
    if p == "servicenow":
        base = _host(c["instance"], ".service-now.com")
        t = c.get("table") or "incident"
        if re.fullmatch(r"[0-9a-f]{32}", tid):
            return f"{base}/nav_to.do?uri={t}.do?sys_id={tid}"
        return f"{base}/nav_to.do?uri={t}.do?sysparm_query=number={tid}"
    if p == "jira":
        return f"{_host(c['site'])}/browse/{tid}"
    if p == "whd":
        return f"{_host(c['url'])}/helpdesk/WebObjects/Helpdesk.woa/wa/TicketActions/view?" \
               f"ticket={tid}"
    if p == "teamdynamix":
        return f"{_host(c['url'])}/TDNext/Apps/{c['app_id']}/Tickets/TicketDet?TicketID={tid}"
    return ""


# ========================================================= normalization ===
def _ticket(**kw) -> dict:
    t = {"id": "", "number": "", "subject": "", "description": "", "status": "", "for": "",
         "for_email": "", "category": "", "issue": "", "serial": "", "asset": "",
         "created": "", "link": ""}
    t.update({k: ("" if v is None else str(v)) for k, v in kw.items()})
    t["created"] = t["created"][:16].replace("T", " ")
    from .iiq import classify
    t["kind"], t["target"] = classify(t)
    return t


def _adf_text(node) -> str:
    """Jira's document format → plain text."""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        return " ".join(_adf_text(c) for c in node.get("content", []) or [])
    if isinstance(node, list):
        return " ".join(_adf_text(c) for c in node)
    return ""


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


# ======================================================== provider clients ===
class _Zendesk:
    def __init__(self, c, http):
        self.base = _host(c["subdomain"], ".zendesk.com") + "/api/v2"
        self.h = {**JSON, "Authorization": _basic(f"{c['email']}/token", c["token"])}
        self.http, self.c = http, c

    def _t(self, t, users):
        req = users.get(t.get("requester_id"), {})
        return _ticket(id=t.get("id"), number=t.get("id"), subject=t.get("subject"),
                       description=t.get("description"), status=t.get("status"),
                       **{"for": req.get("name", "")}, for_email=req.get("email", ""),
                       created=t.get("created_at"), link=link(str(t.get("id")), "zendesk",
                                                              self.c))

    def get(self, tid):
        d = _req("GET", f"{self.base}/tickets/{tid}.json?include=users", self.h, None,
                 self.http, "Zendesk")
        users = {u["id"]: u for u in d.get("users", [])}
        return self._t(d.get("ticket", {}), users)

    def note(self, tid, text, public):
        _req("PUT", f"{self.base}/tickets/{tid}.json",
             self.h, {"ticket": {"comment": {"body": text, "public": bool(public)}}},
             self.http, "Zendesk")

    def create(self, subject, desc, requester, tpl):
        t = {**tpl, "subject": subject, "comment": {"body": desc}}
        if requester:
            t["requester"] = {"email": requester}
        d = _req("POST", f"{self.base}/tickets.json", self.h, {"ticket": t}, self.http,
                 "Zendesk")
        return str((d.get("ticket") or {}).get("id", ""))

    def list_open(self, opts):
        q = urllib.parse.quote("type:ticket status<solved " + (opts.get("query") or ""))
        d = _req("GET", f"{self.base}/search.json?query={q}&sort_by=created_at&sort_order=desc"
                        "&per_page=100", self.h, None, self.http, "Zendesk")
        res = d.get("results", [])
        ids = ",".join(str(t.get("requester_id")) for t in res if t.get("requester_id"))
        users = {}
        if ids:
            u = _req("GET", f"{self.base}/users/show_many.json?ids={ids}", self.h, None,
                     self.http, "Zendesk")
            users = {x["id"]: x for x in u.get("users", [])}
        return [self._t(t, users) for t in res]

    def resolve(self, tid, text):
        _req("PUT", f"{self.base}/tickets/{tid}.json", self.h,
             {"ticket": {"status": "solved", "comment": {"body": text, "public": True}}},
             self.http, "Zendesk")


class _Fresh:
    """Freshservice and Freshdesk share most of their v2 API."""

    def __init__(self, c, http, who):
        self.base = _host(c["domain"]) + "/api/v2"
        self.h = {**JSON, "Authorization": _basic(c["api_key"], "X")}
        self.http, self.c, self.who = http, c, who
        self.p = "freshservice" if who == "Freshservice" else "freshdesk"

    def _t(self, t):
        req = t.get("requester") or {}
        nm = req.get("name") or " ".join(x for x in (req.get("first_name"),
                                                     req.get("last_name")) if x)
        return _ticket(id=t.get("id"), number=t.get("id"), subject=t.get("subject"),
                       description=t.get("description_text") or _strip_html(
                           t.get("description", "")),
                       status=t.get("status"), **{"for": nm},
                       for_email=req.get("email") or req.get("primary_email", ""),
                       category=t.get("category", "") or t.get("type", ""),
                       issue=t.get("sub_category", "") or "", created=t.get("created_at"),
                       link=link(str(t.get("id")), self.p, self.c))

    def get(self, tid):
        d = _req("GET", f"{self.base}/tickets/{tid}?include=requester", self.h, None,
                 self.http, self.who)
        return self._t(d.get("ticket", d))

    def note(self, tid, text, public):
        _req("POST", f"{self.base}/tickets/{tid}/notes", self.h,
             {"body": text.replace("\n", "<br>"), "private": not public}, self.http, self.who)

    def create(self, subject, desc, requester, tpl):
        body = {"priority": 1, "status": 2, "source": 2, **tpl, "subject": subject,
                "description": desc.replace("\n", "<br>"),
                "email": requester or self.c.get("email", "")}
        d = _req("POST", f"{self.base}/tickets", self.h, body, self.http, self.who)
        return str((d.get("ticket") or d).get("id", ""))

    def list_open(self, opts):
        d = _req("GET", f"{self.base}/tickets?include=requester&per_page=100"
                        "&order_type=desc", self.h, None, self.http, self.who)
        items = d.get("tickets", d) if isinstance(d, dict) else d
        return [self._t(t) for t in items or [] if int(t.get("status", 2) or 2) in (2, 3)]

    def resolve(self, tid, text):
        self.note(tid, text, True)
        _req("PUT", f"{self.base}/tickets/{tid}", self.h, {"status": 4}, self.http, self.who)


class _ServiceNow:
    FIELDS = ("sys_id,number,short_description,description,state,caller_id,caller_id.email,"
              "opened_at,category,subcategory,cmdb_ci")

    def __init__(self, c, http):
        self.table = c.get("table") or "incident"
        self.base = _host(c["instance"], ".service-now.com") + f"/api/now/table/{self.table}"
        self.h = {**JSON, "Authorization": _basic(c["user"], c["password"])}
        self.http, self.c = http, c

    def _v(self, x):
        return x.get("display_value", x.get("value", "")) if isinstance(x, dict) else (x or "")

    def _t(self, r):
        return _ticket(id=self._v(r.get("sys_id")), number=self._v(r.get("number")),
                       subject=self._v(r.get("short_description")),
                       description=self._v(r.get("description")),
                       status=self._v(r.get("state")), **{"for": self._v(r.get("caller_id"))},
                       for_email=self._v(r.get("caller_id.email")),
                       category=self._v(r.get("category")),
                       issue=self._v(r.get("subcategory")),
                       created=self._v(r.get("opened_at")),
                       link=link(self._v(r.get("sys_id")), "servicenow", self.c))

    def _sys_id(self, tid):
        if re.fullmatch(r"[0-9a-f]{32}", tid):
            return tid
        d = _req("GET", f"{self.base}?sysparm_query=number={urllib.parse.quote(tid)}"
                        f"&sysparm_limit=1&sysparm_fields=sys_id", self.h, None, self.http,
                 "ServiceNow")
        res = d.get("result", [])
        if not res:
            raise RuntimeError(f"ServiceNow couldn't find {tid}.")
        return self._v(res[0].get("sys_id"))

    def get(self, tid):
        sid = self._sys_id(tid)
        d = _req("GET", f"{self.base}/{sid}?sysparm_display_value=all&sysparm_fields="
                        f"{self.FIELDS}", self.h, None, self.http, "ServiceNow")
        return self._t(d.get("result", {}))

    def note(self, tid, text, public):
        _req("PATCH", f"{self.base}/{self._sys_id(tid)}", self.h,
             {"comments" if public else "work_notes": text}, self.http, "ServiceNow")

    def create(self, subject, desc, requester, tpl):
        body = {**tpl, "short_description": subject, "description": desc}
        if requester:
            body.setdefault("caller_id", requester)
        d = _req("POST", self.base, self.h, body, self.http, "ServiceNow")
        r = d.get("result", {})
        return self._v(r.get("number")) or self._v(r.get("sys_id"))

    def list_open(self, opts):
        q = "active=true" + (f"^{opts['query']}" if opts.get("query") else "") + \
            "^ORDERBYDESCopened_at"
        d = _req("GET", f"{self.base}?sysparm_query={urllib.parse.quote(q)}&sysparm_limit=200"
                        f"&sysparm_display_value=all&sysparm_fields={self.FIELDS}",
                 self.h, None, self.http, "ServiceNow")
        return [self._t(r) for r in d.get("result", [])]

    def resolve(self, tid, text):
        _req("PATCH", f"{self.base}/{self._sys_id(tid)}", self.h,
             {"state": "6", "close_code": self.c.get("close_code") or "Solution provided",
              "close_notes": text}, self.http, "ServiceNow")


class _Jira:
    def __init__(self, c, http):
        self.site = _host(c["site"], ".atlassian.net")
        self.h = {**JSON, "Authorization": _basic(c["email"], c["token"])}
        self.http, self.c = http, c

    def _t(self, i):
        f = i.get("fields", {})
        rep = f.get("reporter") or {}
        return _ticket(id=i.get("key"), number=i.get("key"), subject=f.get("summary"),
                       description=_adf_text(f.get("description")),
                       status=(f.get("status") or {}).get("name", ""),
                       **{"for": rep.get("displayName", "")},
                       for_email=rep.get("emailAddress", ""),
                       category=(f.get("issuetype") or {}).get("name", ""),
                       created=f.get("created"), link=link(i.get("key", ""), "jira", self.c))

    def get(self, tid):
        d = _req("GET", f"{self.site}/rest/api/3/issue/{tid}?fields=summary,status,reporter,"
                        "description,created,issuetype", self.h, None, self.http, "Jira")
        return self._t(d)

    def note(self, tid, text, public):
        _req("POST", f"{self.site}/rest/servicedeskapi/request/{tid}/comment", self.h,
             {"body": text, "public": bool(public)}, self.http, "Jira")

    def create(self, subject, desc, requester, tpl):
        body = {"serviceDeskId": self.c.get("service_desk"),
                "requestTypeId": self.c.get("request_type"),
                "requestFieldValues": {"summary": subject, "description": desc}, **tpl}
        if requester:
            body["raiseOnBehalfOf"] = requester
        d = _req("POST", f"{self.site}/rest/servicedeskapi/request", self.h, body, self.http,
                 "Jira")
        return d.get("issueKey", "")

    def list_open(self, opts):
        jql = opts.get("query") or self.c.get("jql") or \
            "statusCategory != Done ORDER BY created DESC"
        d = _req("GET", f"{self.site}/rest/api/3/search/jql?jql={urllib.parse.quote(jql)}"
                        "&fields=summary,status,reporter,description,created,issuetype"
                        "&maxResults=100", self.h, None, self.http, "Jira")
        return [self._t(i) for i in d.get("issues", [])]

    def resolve(self, tid, text):
        self.note(tid, text, True)
        d = _req("GET", f"{self.site}/rest/api/3/issue/{tid}/transitions", self.h, None,
                 self.http, "Jira")
        want = (self.c.get("resolve_transition") or "Resolve").lower()
        trs = d.get("transitions", [])
        tr = next((t for t in trs if t.get("name", "").lower() == want), None) or \
            next((t for t in trs if t.get("name", "").lower() in ("resolve", "resolve this "
                                                                  "issue", "done", "close")),
                 None)
        if not tr:
            raise RuntimeError(f"Jira has no “{want}” transition for {tid}.")
        _req("POST", f"{self.site}/rest/api/3/issue/{tid}/transitions", self.h,
             {"transition": {"id": tr["id"]}}, self.http, "Jira")


class _WHD:
    def __init__(self, c, http):
        self.base = _host(c["url"]) + "/helpdesk/WebObjects/Helpdesk.woa/ra"
        self.q = "apiKey=" + urllib.parse.quote(c["api_key"])
        self.h = dict(JSON)
        self.http, self.c = http, c

    def _t(self, t):
        cl = t.get("clientReporter") or t.get("client") or {}
        assets = t.get("assets") or []
        a = assets[0] if assets and isinstance(assets[0], dict) else {}
        return _ticket(id=t.get("id"), number=t.get("id"), subject=t.get("subject"),
                       description=_strip_html(t.get("detail", "")),
                       status=(t.get("statustype") or {}).get("statusTypeName", ""),
                       **{"for": " ".join(x for x in (cl.get("firstName"), cl.get("lastName"))
                                          if x)},
                       for_email=cl.get("email", ""),
                       category=(t.get("problemtype") or {}).get("detailDisplayName", ""),
                       serial=a.get("serialNumber", ""), asset=a.get("assetNumber", ""),
                       created=t.get("reportDateUtc") or t.get("reportDate"),
                       link=link(str(t.get("id")), "whd", self.c))

    def get(self, tid):
        return self._t(_req("GET", f"{self.base}/Tickets/{tid}?{self.q}", self.h, None,
                            self.http, "Web Help Desk"))

    def note(self, tid, text, public):
        _req("POST", f"{self.base}/TechNotes?{self.q}", self.h,
             {"noteText": text, "jobticket": {"type": "JobTicket", "id": int(tid)},
              "isHidden": not public, "isSolution": False, "emailClient": bool(public)},
             self.http, "Web Help Desk")

    def create(self, subject, desc, requester, tpl):
        d = _req("POST", f"{self.base}/Tickets?{self.q}", self.h,
                 {**tpl, "subject": subject, "detail": desc}, self.http, "Web Help Desk")
        return str(d.get("id", "")) if isinstance(d, dict) else ""

    def list_open(self, opts):
        qual = opts.get("query") or "(statustype.statusTypeName != 'Closed' and " \
                                    "statustype.statusTypeName != 'Resolved')"
        d = _req("GET", f"{self.base}/Tickets?{self.q}&limit=100&style=details&qualifier="
                        f"{urllib.parse.quote(qual)}", self.h, None, self.http,
                 "Web Help Desk")
        return [self._t(t) for t in (d if isinstance(d, list) else [])]

    def resolve(self, tid, text):
        _req("POST", f"{self.base}/TechNotes?{self.q}", self.h,
             {"noteText": text, "jobticket": {"type": "JobTicket", "id": int(tid)},
              "isHidden": False, "isSolution": True, "emailClient": True},
             self.http, "Web Help Desk")
        _req("PUT", f"{self.base}/Tickets/{tid}?{self.q}", self.h,
             {"statustype": {"id": int(self.c.get("closed_status_id") or 3)}}, self.http,
             "Web Help Desk")


_TDX_TOKENS: dict = {}


class _TDX:
    def __init__(self, c, http):
        self.base = _host(c["url"]) + "/TDWebApi/api"
        self.app = c.get("app_id", "")
        self.http, self.c = http, c

    def _h(self):
        k = (self.base, self.c["beid"])
        tok = _TDX_TOKENS.get(k)
        if not tok or tok[1] < time.time():
            t = _req("POST", f"{self.base}/auth/loginadmin", dict(JSON),
                     {"BEID": self.c["beid"], "WebServicesKey": self.c["key"]}, self.http,
                     "TeamDynamix")
            t = t if isinstance(t, str) else t.get("token", "")
            _TDX_TOKENS[k] = tok = (t.strip().strip('"'), time.time() + 20 * 3600)
        return {**JSON, "Authorization": f"Bearer {tok[0]}"}

    def _t(self, t):
        return _ticket(id=t.get("ID"), number=t.get("ID"), subject=t.get("Title"),
                       description=_strip_html(t.get("Description", "")),
                       status=t.get("StatusName"), **{"for": t.get("RequestorName", "")},
                       for_email=t.get("RequestorEmail", ""),
                       category=t.get("TypeName", ""), issue=t.get("ServiceName", ""),
                       created=t.get("CreatedDate"),
                       link=link(str(t.get("ID")), "teamdynamix", self.c))

    def get(self, tid):
        return self._t(_req("GET", f"{self.base}/{self.app}/tickets/{tid}", self._h(), None,
                            self.http, "TeamDynamix"))

    def note(self, tid, text, public, status=0):
        _req("POST", f"{self.base}/{self.app}/tickets/{tid}/feed", self._h(),
             {"NewStatusID": status, "Comments": text, "IsPrivate": not public, "Notify": []},
             self.http, "TeamDynamix")

    def create(self, subject, desc, requester, tpl):
        body = {**tpl, "Title": subject, "Description": desc}
        if requester:
            body.setdefault("RequestorEmail", requester)
        d = _req("POST", f"{self.base}/{self.app}/tickets?NotifyRequestor=false&"
                         "NotifyResponsible=false&AllowRequestorCreation=false", self._h(),
                 body, self.http, "TeamDynamix")
        return str(d.get("ID", "")) if isinstance(d, dict) else ""

    def list_open(self, opts):
        d = _req("POST", f"{self.base}/{self.app}/tickets/search", self._h(),
                 {"MaxResults": 200, "StatusClassIDs": [1, 2, 5]}, self.http, "TeamDynamix")
        return [self._t(t) for t in (d if isinstance(d, list) else [])]

    def resolve(self, tid, text):
        st = int(self.c.get("resolved_status_id") or 0)
        if not st:
            raise RuntimeError("Set the TeamDynamix “Status ID for resolved” first.")
        self.note(tid, text, True, st)


class _OsTicket:
    def __init__(self, c, http):
        self.url = _host(c["url"]) + "/api/tickets.json"
        self.h = {**JSON, "X-API-Key": c["api_key"]}
        self.http, self.c = http, c

    def create(self, subject, desc, requester, tpl):
        d = _req("POST", self.url, self.h, {"alert": True, "autorespond": False, **tpl,
                                             "name": "GAMbit",
                                             "email": requester or self.c.get("email", ""),
                                             "subject": subject, "message": desc},
                 self.http, "osTicket")
        return str(d).strip() if not isinstance(d, dict) else str(d.get("id", ""))


class _IIQ:
    def __init__(self, c, http):
        from . import iiq
        self.m, self.http = iiq, http
        self.cfg = iiq.config()

    def get(self, tid):
        t = self.m.get_ticket(tid, self.cfg, self.http)
        return _ticket(id=tid, number=t["number"], subject=t["subject"], status=t["status"],
                       **{"for": t["for"]}, for_email=t.get("for_email", ""), link=t["link"])

    def note(self, tid, text, public):
        self.m.add_note(tid, text, public, self.cfg, self.http)

    def create(self, subject, desc, requester, tpl):
        return self.m.create_ticket(subject, desc, self.cfg, self.http)

    def list_open(self, opts):
        out = self.m.list_open(self.cfg, self.http, {**self.m.queue_options(), **opts})
        for t in out:
            t["link"] = self.m.ticket_link(t["id"], self.cfg)
        return out


def client(p: str = "", cfg: dict | None = None, http=None):
    p = p or provider()
    c = cfg or config(p)
    if not p:
        raise RuntimeError("Choose your help desk in Settings & Updates → Integrations.")
    if p != "iiq" and not (cfg or configured(p)):
        raise RuntimeError(f"Finish setting up {PROVIDERS[p]} in Settings → Integrations.")
    return {"iiq": lambda: _IIQ(c, http), "zendesk": lambda: _Zendesk(c, http),
            "freshservice": lambda: _Fresh(c, http, "Freshservice"),
            "freshdesk": lambda: _Fresh(c, http, "Freshdesk"),
            "servicenow": lambda: _ServiceNow(c, http), "jira": lambda: _Jira(c, http),
            "whd": lambda: _WHD(c, http), "teamdynamix": lambda: _TDX(c, http),
            "osticket": lambda: _OsTicket(c, http)}[p]()


WHAT = {"read": "read tickets", "note": "add notes", "list": "list tickets",
        "resolve": "resolve tickets", "create": "create tickets"}


def _need(what, p):
    if not can(what, p):
        raise RuntimeError(f"{PROVIDERS.get(p, 'This help desk')} doesn't let GAMbit "
                           f"{WHAT[what]} through its API.")


# ============================================================ public API ===
def get(tid: str, p: str = "", cfg=None, http=None) -> dict:
    p = p or provider()
    _need("read", p)
    return client(p, cfg, http).get(tid)


def note(tid: str, text: str, public: bool = False, p: str = "", cfg=None, http=None):
    p = p or provider()
    _need("note", p)
    return client(p, cfg, http).note(tid, text, public)


def create(subject: str, description: str, requester: str = "", p: str = "", cfg=None,
           http=None) -> str:
    p = p or provider()
    _need("create", p)
    tpl = template(p) if cfg is None else (json.loads(cfg.get("template") or "{}")
                                          if cfg.get("template") else {})
    return client(p, cfg, http).create(subject, description, requester, tpl)


def list_open(opts: dict | None = None, p: str = "", cfg=None, http=None) -> list[dict]:
    p = p or provider()
    _need("list", p)
    o = dict(opts or {})
    words = [w.strip().lower() for w in (o.pop("words", "") or "").split(",") if w.strip()]
    out = client(p, cfg, http).list_open(o)
    if words:
        out = [t for t in out if any(w in (t["subject"] + " " + t["category"] + " " +
                                           t["issue"] + " " + t["description"]).lower()
                                     for w in words)]
    return out


def resolve(tid: str, text: str, p: str = "", cfg=None, http=None):
    p = p or provider()
    _need("resolve", p)
    return client(p, cfg, http).resolve(tid, text)


def summary_note(steps) -> str:
    from .iiq import summary_note as s
    return s(steps)
