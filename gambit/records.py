"""Records requests (FERPA, legal and public-records): one place for “export everything for
this student or staff member”. GAMbit creates the Vault matter, optionally places a hold,
starts the exports, tracks the deadline, downloads the files and keeps a record – tied to the
help desk and the audit report."""

from __future__ import annotations

import datetime
import json
import re
import uuid

from .settings import settings

KINDS = {"ferpa": ("FERPA request from a parent or student", 45),
         "legal": ("Legal hold / litigation", 0),
         "public": ("Public records request", 10),
         "staff": ("Staff investigation (HR)", 30),
         "other": ("Other", 30)}
CORPORA = {"mail": "Gmail", "drive": "Drive", "groups": "Groups",
           "hangouts_chat": "Google Chat", "calendar": "Calendar"}
TASK_NOTE = "records request"


def load() -> list[dict]:
    from . import team
    if team.folder():
        d = team.read_shared("records_requests.json")
        if d:
            return d.get("requests", [])
    try:
        return json.loads(settings.get("records/list", "[]") or "[]")
    except ValueError:
        return []


def save(items: list[dict]):
    from . import team
    if team.folder():
        team.write_shared("records_requests.json", {"requests": items})
    settings.set("records/list", json.dumps(items))


def new(email: str, kind: str, requested_by: str, corpora: list[str], hold: bool,
        notes: str = "", received: str = "", who: str = "") -> dict:
    received = received or datetime.date.today().isoformat()
    days = KINDS.get(kind, KINDS["other"])[1]
    due = (datetime.date.fromisoformat(received) + datetime.timedelta(days=days)).isoformat() \
        if days else ""
    return {"id": uuid.uuid4().hex[:6], "email": email.strip().lower(), "kind": kind,
            "requested_by": requested_by.strip(), "received": received, "due": due,
            "corpora": corpora or ["mail", "drive"], "hold": bool(hold), "notes": notes,
            "matter": "", "holds": [], "exports": [], "status": "new", "ticket": "",
            "log": [f"{datetime.datetime.now():%Y-%m-%d %H:%M} opened by {who}"]}


def matter_name(r: dict) -> str:
    return f"GAMbit {KINDS.get(r['kind'], KINDS['other'])[0].split(' (')[0]} – {r['email']} " \
           f"[{r['id']}]"[:120]


def matter_args(r: dict) -> list[str]:
    return ["create", "vaultmatter", "name", matter_name(r), "description",
            (f"Requested by {r['requested_by']} on {r['received']}. {r['notes']}")[:900],
            "returnidonly"]


def hold_args(r: dict, corpus: str) -> list[str]:
    return ["create", "vaulthold", "matter", r["matter"], "name",
            f"{r['email']} {corpus} [{r['id']}]", "corpus", corpus, "accounts", r["email"],
            "returnidonly"]


def export_args(r: dict, corpus: str) -> list[str]:
    a = ["create", "vaultexport", "matter", r["matter"], "name",
         f"{r['email']} {corpus} [{r['id']}]", "corpus", corpus, "accounts", r["email"]]
    if corpus == "drive":
        a += ["includeshareddrives", "true"]
    return a + ["returnidonly"]


def status_args(r: dict) -> list[str]:
    return ["print", "vaultexports", "matters", r["matter"]]


def download_args(r: dict, export_id: str, folder: str) -> list[str]:
    return ["download", "vaultexport", export_id, "matter", r["matter"], "targetfolder",
            folder]


def close_args(r: dict) -> list[str]:
    return ["close", "vaultmatter", r["matter"]]


def _id(out: str) -> str:
    """returnidonly prints the new ID (possibly after other lines)."""
    lines = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    for ln in reversed(lines):
        m = re.fullmatch(r"[A-Za-z0-9_-]{6,}", ln)
        if m:
            return ln
    m = re.search(r"\(([A-Za-z0-9_-]{8,})\)", out or "")
    return m.group(1) if m else ""


def _log(r: dict, text: str):
    r["log"].append(f"{datetime.datetime.now():%Y-%m-%d %H:%M} {text}")


def start(r: dict, run_text, who: str = "") -> list[str]:
    """Matter, holds (if asked) and exports. Returns problems."""
    from . import activity
    prof = settings.get("profile/current", "") or "Default"
    probs = []
    if not r.get("matter"):
        a = matter_args(r)
        c, out = run_text(a, 300)
        activity.record(a, c, "done" if c == 0 else "failed", None, prof, note=TASK_NOTE)
        r["matter"] = _id(out) if c == 0 else ""
        if not r["matter"]:
            return [f"Couldn't create the Vault matter: {(out or '').strip()[-200:]}"]
        _log(r, f"Vault matter {r['matter']} created by {who}")
    if r.get("hold"):
        for corpus in r["corpora"]:
            if corpus in [h["corpus"] for h in r["holds"]]:
                continue
            a = hold_args(r, corpus)
            c, out = run_text(a, 300)
            activity.record(a, c, "done" if c == 0 else "failed", None, prof, note=TASK_NOTE)
            if c == 0:
                r["holds"].append({"corpus": corpus, "id": _id(out)})
                _log(r, f"hold on {CORPORA.get(corpus, corpus)}")
            else:
                probs.append(f"hold {corpus}: {(out or '').strip()[-160:]}")
    for corpus in r["corpora"]:
        if corpus in [e["corpus"] for e in r["exports"]]:
            continue
        a = export_args(r, corpus)
        c, out = run_text(a, 300)
        activity.record(a, c, "done" if c == 0 else "failed", None, prof, note=TASK_NOTE)
        if c == 0:
            r["exports"].append({"corpus": corpus, "id": _id(out), "status": "IN_PROGRESS"})
            _log(r, f"export of {CORPORA.get(corpus, corpus)} started")
        else:
            probs.append(f"export {corpus}: {(out or '').strip()[-160:]}")
    r["status"] = "exporting" if r["exports"] else r["status"]
    return probs


def update_status(r: dict, rows: list[dict]) -> int:
    """Apply `print vaultexports` rows; returns how many exports are finished."""
    by = {}
    for row in rows:
        low = {(k or "").lower(): (v or "") for k, v in row.items()}
        by[low.get("id", "")] = (low.get("status") or "").upper()
    done = 0
    for e in r["exports"]:
        if e["id"] in by:
            e["status"] = by[e["id"]]
        done += e["status"] == "COMPLETED"
    if r["exports"] and done == len(r["exports"]) and r["status"] == "exporting":
        r["status"] = "ready to download"
        _log(r, "all exports finished")
    return done


def due_soon(items: list[dict], days: int = 7, today: datetime.date | None = None) -> list:
    today = today or datetime.date.today()
    soon = (today + datetime.timedelta(days=days)).isoformat()
    return [r for r in items if r.get("due") and r["status"] not in ("delivered", "closed")
            and r["due"] <= soon]


def reminders(log=print, today=None) -> list[str]:
    """Daily task: alert about records requests that are due soon or overdue."""
    items = load()
    late = due_soon(items, 7, today)
    if not late:
        return []
    t = (today or datetime.date.today()).isoformat()
    lines = [f"• {r['email']} ({KINDS.get(r['kind'], KINDS['other'])[0]}) – "
             f"{'OVERDUE' if r['due'] < t else 'due'} {r['due']}, {r['status']}" for r in late]
    key = f"records/reminded/{t}"
    if not settings.get(key, False):
        from . import alerts
        alerts.notify("Records requests needing attention:\n" + "\n".join(lines),
                      "GAMbit records requests")
        settings.set(key, True)
    for ln in lines:
        log(ln)
    return lines
