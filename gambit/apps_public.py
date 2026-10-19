"""Public apps list for families: every third-party app connected to student accounts,
with its approval and data-privacy agreement status from your approved list, as a Google
Sheet and/or a web page you can post on the district website (many state student-privacy
laws require one)."""

from __future__ import annotations

import datetime
import html
import json

from .settings import settings


def options() -> dict:
    try:
        o = json.loads(settings.get("appspublic/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"root": "/Students", "min_students": 3, "include_denied": False,
            "title": "Apps used with student accounts", "contact": "", **o}


def save_options(o: dict):
    settings.set("appspublic/options", json.dumps(o))


def build(summary: list[dict], approved: list[dict], opts: dict) -> list[dict]:
    """summary rows come from app_vetting.summarize (App, Students, Status, …)."""
    from .tools.app_vetting import _norm
    info = {(_norm(a.get("name", "")), a.get("client_id", "")): a for a in approved}

    def extra(name, cid):
        for (n, c), a in info.items():
            if (c and c == cid) or (n and n == _norm(name)):
                return a
        return {}
    out = []
    for s in summary:
        name = s.get("App") or s.get("name") or ""
        cid = s.get("client_id") or s.get("Client ID") or ""
        try:
            n = int(s.get("Students") or 0)
        except ValueError:
            n = 0
        if n < int(opts.get("min_students", 3) or 0):
            continue
        st = (s.get("Status") or "").lower()
        if "denied" in st or "not approved" in st:
            if not opts.get("include_denied"):
                continue
        a = extra(name, cid)
        out.append({"App": name, "Students using it": n,
                    "Status": "Approved" if st.startswith("approved") else
                    ("Not approved – being removed" if "denied" in st else "Under review"),
                    "What it's for": a.get("purpose", ""),
                    "Data privacy agreement": a.get("dpa", "") or ("On file" if
                                                                    st.startswith("approved")
                                                                    else ""),
                    "Privacy policy": a.get("privacy", "")})
    return sorted(out, key=lambda r: (r["Status"] != "Approved", r["App"].lower()))


COLUMNS = ["App", "Status", "What it's for", "Data privacy agreement", "Privacy policy",
           "Students using it"]


def to_csv(rows: list[dict]) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def to_html(rows: list[dict], opts: dict, district: str = "") -> str:
    def cell(v):
        v = str(v or "")
        if v.startswith("http"):
            return f"<a href='{html.escape(v)}'>link</a>"
        return html.escape(v)
    body = "".join("<tr>" + "".join(f"<td>{cell(r.get(c))}</td>" for c in COLUMNS) + "</tr>"
                   for r in rows)
    contact = f"<p>Questions? Contact {html.escape(opts['contact'])}.</p>" \
        if opts.get("contact") else ""
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>"
            f"{html.escape(opts['title'])}</title><style>body{{font-family:Arial,sans-serif;"
            "max-width:1000px;margin:auto;padding:16px}table{border-collapse:collapse;"
            "width:100%}td,th{border:1px solid #ccc;padding:6px;text-align:left}"
            "th{background:#f0f3f8}</style></head><body>"
            f"<h1>{html.escape(opts['title'])}</h1><p>{html.escape(district)} – updated "
            f"{datetime.date.today():%B %d, %Y}. These are the online apps students sign in "
            "to with their school Google account.</p>"
            "<table><tr>" + "".join(f"<th>{c}</th>" for c in COLUMNS) + "</tr>" + body +
            f"</table>{contact}</body></html>")
