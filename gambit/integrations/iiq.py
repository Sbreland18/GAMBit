"""Incident IQ: link a ticket while you work, post what GAMbit did as a ticket note, and
(optionally) open a ticket when a background task fails.

Incident IQ's public API is only partly documented. GAMbit uses:
  • GET  /api/v1.0/tickets/{TicketId}                    – read a ticket
  • POST /api/v1.0/tickets/{TicketId}/activities/new     – add a note (comment)
  • POST /api/v1.0/tickets/new                           – create a ticket from a template
with the headers Incident IQ lists in Administration → Developer Tools:
  SiteId, Authorization: Bearer <token>, Client: ApiClient.
"""

from __future__ import annotations

import json
import re

from ..settings import settings

GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


def config() -> dict:
    site = (settings.get("iiq/site", "") or "").strip()
    if site and "://" not in site:
        site = f"https://{site}" if "." in site else f"https://{site}.incidentiq.com"
    return {"site": site.rstrip("/"), "site_id": (settings.get("iiq/site_id", "") or "").strip(),
            "token": (settings.get("iiq/token", "") or "").strip()}


def configured() -> bool:
    c = config()
    return bool(c["site"] and c["site_id"] and c["token"])


def headers(cfg: dict) -> dict:
    return {"SiteId": cfg["site_id"], "Authorization": f"Bearer {cfg['token']}",
            "Client": "ApiClient", "Accept": "application/json",
            "Content-Type": "application/json"}


def ticket_id(text: str) -> str:
    """Ticket ID (GUID) from a pasted Incident IQ link or the ID itself."""
    m = re.search(GUID, text or "")
    return m.group(0).lower() if m else ""


def ticket_link(tid: str, cfg: dict | None = None) -> str:
    cfg = cfg or config()
    return f"{cfg['site']}/agent/tickets/{tid}" if cfg["site"] else ""


def _call(method: str, path: str, body=None, cfg: dict | None = None, http=None):
    from .. import net
    cfg = cfg or config()
    if not (cfg["site"] and cfg["site_id"] and cfg["token"]):
        raise RuntimeError("Set up Incident IQ in Settings → Integrations first.")
    status, _h, data = (http or net.request)(method, f"{cfg['site']}/api/v1.0/{path}",
                                             headers(cfg), body)
    if status in (401, 403):
        raise RuntimeError(f"Incident IQ refused the request ({status}) – check the API token "
                           "and Site ID.")
    if status >= 400:
        raise RuntimeError(f"Incident IQ returned {status}: "
                           f"{data[:300].decode('utf-8', 'replace')}")
    try:
        return json.loads(data.decode("utf-8-sig") or "{}")
    except ValueError:
        return {}


def get_ticket(tid: str, cfg=None, http=None) -> dict:
    """→ {number, subject, status, for, link} (best effort – field names vary)."""
    raw = _call("GET", f"tickets/{tid}", cfg=cfg, http=http)
    t = raw.get("Item", raw) if isinstance(raw, dict) else {}
    who = t.get("For") or t.get("ForUser") or {}
    return {"number": str(t.get("TicketNumber", "") or ""),
            "subject": t.get("Subject", "") or t.get("IssueDescription", "")[:80],
            "status": (t.get("WorkflowStep") or {}).get("StepName", "") or
            t.get("StatusName", "") or "",
            "for": (who.get("Name") or who.get("Email") or "") if isinstance(who, dict) else "",
            "for_email": who.get("Email", "") if isinstance(who, dict) else "",
            "link": ticket_link(tid, cfg)}


def add_note(tid: str, text: str, public: bool = False, cfg=None, http=None):
    body = {"TicketId": tid,
            "ActivityItems": [{"$type": "Spark.Shared.Models.TicketActivityComment, "
                                        "Spark.Shared",
                               "TicketActivityTypeId": 6, "Comments": text}],
            "IsPublic": bool(public), "WaitForResponse": False, "TicketWasUpdated": True}
    return _call("POST", f"tickets/{tid}/activities/new", body, cfg, http)


def template() -> dict:
    """Create-ticket template from Settings (IDs copied from Incident IQ)."""
    try:
        return json.loads(settings.get("iiq/template", "") or "{}")
    except ValueError:
        return {}


def create_ticket(subject: str, description: str, cfg=None, http=None) -> str:
    t = template()
    if not t:
        raise RuntimeError("Add a ticket template in Settings → Integrations to create "
                           "tickets.")
    body = {**t, "Subject": subject, "IssueDescription": description}
    raw = _call("POST", "tickets/new", body, cfg, http)
    item = raw.get("Item", raw) if isinstance(raw, dict) else {}
    return str(item.get("TicketId", "") or item.get("TicketNumber", ""))


def summary_note(steps) -> str:
    """Plain-text note for a finished list of GAMbit steps."""
    icons = {"ok": "✔", "dry": "(dry run)", "fail": "✖", "skip": "–", "pending": "○",
             "running": "…"}
    lines = ["GAMbit:"]
    for s in steps:
        lines.append(f"{icons.get(s.status, s.status)} {s.label}")
    return "\n".join(lines[:60])


# ------------------------------------------------------------ ticket queue ---
OPEN_STATE = "00000000-0000-0000-0000-000000000000"
ACCOUNT_WORDS = ("password", "sign in", "signin", "log in", "login", "locked", "account",
                 "email", "gmail", "google", "2-step", "2sv", "mfa", "username", "classroom")
DEVICE_WORDS = ("chromebook", "device", "screen", "keyboard", "charger", "battery", "laptop",
                "won't turn on", "broken", "cracked", "trackpad", "powerwash", "enroll")


def queue_options() -> dict:
    return {"product_id": (settings.get("iiq/product_id", "") or "").strip(),
            "category_id": (settings.get("iiq/queue_category", "") or "").strip(),
            "words": (settings.get("iiq/queue_words", "") or "").strip()}


def _items(raw) -> list[dict]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for k in ("Items", "items", "Tickets"):
            if isinstance(raw.get(k), list):
                return raw[k]
    return []


def list_open(cfg=None, http=None, opts=None, max_items: int = 300) -> list[dict]:
    """Open tickets (optionally one issue category) – best effort, the search API is
    undocumented. → [{id, number, subject, for, for_email, category, issue, serial, asset,
    created, kind, target}]"""
    o = opts or queue_options()
    body = {"OnlyShowDeleted": False, "FilterByViewPermission": True, "Schema": "All",
            "Filters": [{"Facet": "ticketstate", "Id": OPEN_STATE}]}
    if o.get("product_id"):
        body["ProductId"] = o["product_id"]
    if o.get("category_id"):
        body["Filters"].append({"Facet": "issuecategory", "Id": o["category_id"]})
    out, page = [], 0
    while len(out) < max_items:
        raw = _call("POST", f"tickets?$s=100&$p={page}&$o=TicketCreatedDate%20DESC", body,
                    cfg, http)
        items = _items(raw)
        if not items:
            break
        out += [parse_ticket(t) for t in items]
        if len(items) < 100:
            break
        page += 1
    words = [w.strip().lower() for w in (o.get("words") or "").split(",") if w.strip()]
    if words:
        out = [t for t in out if any(w in (t["subject"] + " " + t["category"] + " " +
                                           t["issue"]).lower() for w in words)]
    return out[:max_items]


def parse_ticket(t: dict) -> dict:
    who = t.get("For") or t.get("ForUser") or {}
    assets = t.get("Assets") or []
    a = assets[0] if assets and isinstance(assets[0], dict) else {}
    a = a.get("Asset", a) if isinstance(a, dict) else {}
    cat = t.get("IssueCategory") or {}
    issue = t.get("Issue") or {}
    d = {"id": str(t.get("TicketId", "") or ""),
         "number": str(t.get("TicketNumber", "") or ""),
         "subject": str(t.get("Subject", "") or t.get("IssueDescription", "") or "")[:120],
         "description": str(t.get("IssueDescription", "") or ""),
         "for": (who.get("Name") or who.get("FullName") or "") if isinstance(who, dict) else "",
         "for_email": (who.get("Email") or "").lower() if isinstance(who, dict) else "",
         "category": (cat.get("Name", "") if isinstance(cat, dict) else "") or
         str(t.get("IssueCategoryName", "") or ""),
         "issue": (issue.get("Name", "") if isinstance(issue, dict) else "") or
         str(t.get("IssueName", "") or ""),
         "serial": str(a.get("SerialNumber", "") or "").upper(),
         "asset": str(a.get("AssetTag", "") or ""),
         "created": str(t.get("TicketCreatedDate", "") or t.get("CreatedDate", "") or "")[:16]
         .replace("T", " ")}
    d["kind"], d["target"] = classify(d)
    return d


def classify(t: dict) -> tuple[str, str]:
    """("chromebook", serial) | ("account", email) | ("other", "")"""
    text = " ".join((t.get("subject", ""), t.get("category", ""), t.get("issue", ""),
                     t.get("description", "")[:300])).lower()
    serial = t.get("serial", "")
    if not serial:
        m = re.search(r"\b(?:SERIAL|SN)[#:\s]*([A-Z0-9]{8,14})\b", text.upper())
        serial = m.group(1) if m else ""
    email = t.get("for_email", "")
    m = re.search(r"[\w.+'-]+@[\w.-]+\.\w+", t.get("description", "") + " " +
                  t.get("subject", ""))
    if m:
        email = m.group(0).lower()
    if serial and (any(w in text for w in DEVICE_WORDS) or not any(w in text for w in
                                                                   ACCOUNT_WORDS)):
        return "chromebook", serial
    if any(w in text for w in ACCOUNT_WORDS) and email:
        return "account", email
    if serial:
        return "chromebook", serial
    if email:
        return "account", email
    return "other", ""
