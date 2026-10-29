"""Archive, then delete – and keep a record of every account deletion.

Clean-up rules can delete long-suspended accounts. With an archive account set on the rule,
the approval request first hands the person's Drive files (and, if chosen, Calendar) to the
archive account; GAMbit then deletes each account only after Google says that transfer
finished, the account is still suspended, and the signed plan still checks out.

Every account deletion GAMbit runs – by a rule, an approval, Run later or by hand – is
written to a deletion record (who, when, why, which rule, archived where), each line signed,
for records retention and student data-privacy agreements.
"""

from __future__ import annotations

import datetime
import json
import os
import platform
import uuid

from .settings import settings

PENDING_FILE = "cleanup_deletions.json"
RECORD_FILE = "deletion_records.jsonl"
SEAL_KIND, SEAL_FIELDS = "deletion", ("id", "email", "rule", "archive_to", "what", "request",
                                      "approved_by", "created")
RECORD_KIND = "deletionrecord"
ARCHIVE_NOTE = "archive-then-delete"
GIVE_UP_DAYS = 21
WHAT = {"drive": "Drive files", "calendar": "Calendar"}


# --------------------------------------------------------------- commands ---
def transfer_args(email: str, archive: str, what=("drive",)) -> list[str]:
    what = [w for w in what if w in WHAT] or ["drive"]
    a = ["create", "datatransfer", email, ",".join(what), archive, "all"]
    if "calendar" in what:
        a.append("release_resources")
    return a


def delete_args(email: str) -> list[str]:
    return ["delete", "user", email]


# ---------------------------------------------------------- where it lives ---
def _dir() -> str:
    from . import team
    if team.folder():
        return team.folder()
    from PySide6.QtCore import QStandardPaths
    d = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    os.makedirs(d, exist_ok=True)
    return d


def _pending_path() -> str:
    return os.path.join(_dir(), PENDING_FILE)


def _load_pending() -> list[dict]:
    try:
        with open(_pending_path(), encoding="utf-8") as fh:
            d = json.load(fh)
        return [x for x in d.get("items", []) if isinstance(x, dict)]
    except (OSError, ValueError, AttributeError):
        return []


def _save_pending(items: list[dict]):
    p = _pending_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"items": items}, fh, indent=1)
    os.replace(tmp, p)


def _update(fn):
    from . import file_lock
    with file_lock.held(_pending_path() + ".lock"):
        items = _load_pending()
        fn(items)
        _save_pending(items)
        return items


def pending() -> list[dict]:
    return _load_pending()


def verify(item: dict):
    from . import seal
    return seal.check(SEAL_KIND, item, SEAL_FIELDS)


# --------------------------------------------- after the approval has run ---
def register(req: dict) -> int:
    """The approved request started the archive transfers: remember each account to delete
    once its transfer finishes. Signed by the approver."""
    from . import seal, team
    if team.verify_request(req) is None:
        raise ValueError("This request isn't signed by anyone GAMbit trusts (or it was "
                         "changed in the team folder), so no deletions were planned.")
    archive = (req.get("archive_to") or "").lower()
    started = {str(c[2]).lower() for c in req.get("commands", [])
               if len(c) > 4 and [str(x).lower() for x in c[:2]] == ["create", "datatransfer"]
               and str(c[4]).lower() == archive}
    emails = [e.lower() for e in req.get("delete_after", []) if "@" in str(e)
              and str(e).lower() in started and str(e).lower() != archive]
    if not emails:
        return 0
    now = datetime.datetime.now().isoformat(timespec="seconds")
    made = []
    for e in emails:
        it = {"id": uuid.uuid4().hex[:10], "email": e, "rule": req.get("rule", ""),
              "archive_to": (req.get("archive_to") or "").lower(),
              "what": list(req.get("what") or ["drive"]), "request": req.get("id", ""),
              "approved_by": team.me(), "created": now, "status": "transferring",
              "reason": req.get("why", {}).get(e, "") if isinstance(req.get("why"), dict)
              else ""}
        made.append(seal.sign(SEAL_KIND, it, SEAL_FIELDS))

    def add(items):
        have = {(x.get("email"), x.get("request")) for x in items}
        items.extend(m for m in made if (m["email"], m["request"]) not in have)
    _update(add)
    return len(made)


# ------------------------------------------------------------- background ---
def _transfer_state(rows: list[dict], item: dict) -> str:
    from .tools.recovery import transfers
    start = (datetime.datetime.fromisoformat(item["created"]) -
             datetime.timedelta(days=1)).isoformat(sep=" ")[:16]
    mine = [t for t in transfers(rows) if t["To"].lower() == item["archive_to"]
            and t["From"].lower() == item["email"] and t["Requested"] >= start]
    if not mine:
        return ""
    states = {t["Status"] for t in mine}
    if "failed" in states:
        return "failed"
    if states <= {"completed"}:
        return "completed"
    return "inprogress"


def _still_suspended(email: str, run_csv) -> str:
    """'yes', 'no' or 'gone'."""
    code, rows, _e = run_csv(["print", "users", "query", f"email:{email}", "fields",
                              "primaryemail,suspended"])
    if code != 0:
        raise RuntimeError(f"couldn't look up {email}")
    row = next((r for r in rows if str(r.get("primaryEmail", "")).lower() == email), None)
    if row is None:
        return "gone"
    return "yes" if str(row.get("suspended", "")).lower() == "true" else "no"


def run_due(log=print, run_csv=None, run_text=None, today=None) -> list[str]:
    """Daily: delete the accounts whose archive transfer has finished."""
    from . import activity, alerts, seal
    from .directory import run_gam_csv, run_gam_text
    from .tools.recovery import transfers_args
    run_csv = run_csv or (lambda a: run_gam_csv(a, 600))
    run_text = run_text or run_gam_text
    now = today or datetime.datetime.now()
    lines, problems = [], []
    for it in [x for x in _load_pending() if x.get("status") in ("transferring", "ready")]:
        e = it.get("email", "")
        why = seal.may_run(verify(it), [delete_args(e)])
        if why:
            _set(it["id"], status="blocked", note=why)
            lines.append(f"{e}: not deleted – {why}.")
            problems.append(f"{e}: {why}")
            continue
        code, rows, _err = run_csv(transfers_args(e))
        state = _transfer_state(rows if code == 0 else [], it) if code == 0 else "unknown"
        age = (now - datetime.datetime.fromisoformat(it["created"])).days
        if state == "failed":
            _set(it["id"], status="failed", note="the archive transfer failed – not deleted")
            problems.append(f"{e}: the transfer to {it['archive_to']} failed, so the account "
                            "was NOT deleted")
            continue
        if state != "completed":
            if age > GIVE_UP_DAYS:
                _set(it["id"], status="failed",
                     note=f"the transfer didn't finish in {GIVE_UP_DAYS} days – not deleted")
                problems.append(f"{e}: the archive transfer didn't finish in {GIVE_UP_DAYS} "
                                "days – not deleted")
            elif not state and age >= 2:
                _set(it["id"], status="failed", note="no archive transfer found – not deleted")
                problems.append(f"{e}: Google has no transfer of their files to "
                                f"{it['archive_to']} – not deleted")
            continue
        if settings.get("safety/dry_run", False):
            lines.append(f"{e}: archived – would be deleted now (dry run is on).")
            continue
        try:
            sus = _still_suspended(e, run_csv)
        except RuntimeError as exc:
            lines.append(f"{e}: will try again – {exc}.")
            continue
        if sus == "no":
            _set(it["id"], status="cancelled",
                 note="the account was turned back on, so it wasn't deleted")
            lines.append(f"{e}: turned back on since – not deleted.")
            continue
        if sus == "gone":
            _set(it["id"], status="deleted", note="already deleted elsewhere")
            record_deleted(e, how="already deleted elsewhere", rule=it.get("rule", ""),
                           approved_by=it.get("approved_by", ""), request=it.get("request", ""),
                           archive_to=it["archive_to"], what=it.get("what"))
            continue
        args = delete_args(e)
        c, out = run_text(args, 300)
        activity.record(args, c, "done" if c == 0 else "failed", None,
                        settings.get("profile/current", "") or "Default",
                        note=f"{ARCHIVE_NOTE} (rule “{it.get('rule', '')}”, approved by "
                             f"{it.get('approved_by', '')})")
        if c != 0:
            lines.append(f"{e}: delete failed – {(out or '').strip()[-160:]}")
            problems.append(f"{e}: the delete failed")
            continue
        _set(it["id"], status="deleted", note=f"deleted {now:%Y-%m-%d}")
        record_deleted(e, how="clean-up rule after archiving", rule=it.get("rule", ""),
                       approved_by=it.get("approved_by", ""), request=it.get("request", ""),
                       archive_to=it["archive_to"], what=it.get("what"),
                       reason=it.get("reason", ""))
        lines.append(f"{e}: files archived to {it['archive_to']}, account deleted.")
    if problems:
        alerts.notify("Archive-then-delete needs a look:\n" +
                      "\n".join(f"• {p}" for p in problems[:30]),
                      "GAMbit clean-up deletions")
    for ln in lines:
        log(ln)
    return lines


def _set(item_id: str, **changes):
    def fn(items):
        for x in items:
            if x.get("id") == item_id:
                x.update(changes, updated=datetime.datetime.now().isoformat(timespec="seconds"))
    _update(fn)


def cancel(item_id: str) -> bool:
    done = [False]

    def fn(items):
        for x in items:
            if x.get("id") == item_id and x.get("status") in ("transferring", "ready",
                                                               "blocked"):
                x.update(status="cancelled", note="cancelled by " + _me())
                done[0] = True
    _update(fn)
    return done[0]


def _me() -> str:
    from . import team
    return team.me()


# ------------------------------------------------------ the deletion record ---
def _record_paths() -> list[str]:
    from . import team
    from PySide6.QtCore import QStandardPaths
    local = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    out = [os.path.join(local, RECORD_FILE)]
    if team.folder():
        out.append(os.path.join(team.folder(), RECORD_FILE))
    return out


def record_deleted(email: str, how: str = "", rule: str = "", approved_by: str = "",
                   request: str = "", archive_to: str = "", what=None, reason: str = "",
                   who: str = "", note: str = "") -> dict:
    """Add a signed line to the deletion record (on this PC and in the team folder)."""
    from . import seal
    from .activity import who as _who
    rec = {"id": uuid.uuid4().hex[:12], "email": (email or "").lower(),
           "deleted": datetime.datetime.now().isoformat(timespec="seconds"),
           "by": who or _who(), "computer": platform.node(), "how": how, "rule": rule,
           "reason": reason, "approved_by": approved_by, "request": request,
           "archived_to": archive_to,
           "archived": ", ".join(WHAT.get(w, w) for w in (what or [])) if archive_to else "",
           "note": note}
    try:
        rec = seal.sign(RECORD_KIND, rec)
    except Exception:  # noqa: BLE001 – the record matters more than its signature
        pass
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    for p in _record_paths():
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            continue
    return rec


def on_activity(entry: dict):
    """Called for every logged command: a successful single-account delete goes into the
    deletion record (the archive-then-delete task writes its own, fuller line)."""
    if entry.get("code") != 0 or entry.get("status") in ("cancelled", "dry run"):
        return
    note = str(entry.get("note", ""))
    if note.startswith(ARCHIVE_NOTE):
        return
    from .activity import unwrap
    inner, understood, _cfg = unwrap([str(a) for a in entry.get("args", [])])
    low = [a.lower() for a in inner]
    if not understood or len(low) < 3 or low[0] != "delete" or low[1] != "user":
        return
    email = inner[2]
    if "@" not in email:
        return
    rule, req_id, approved_by, reason = "", "", "", ""
    if note.startswith("approved request "):
        req_id = note.split()[2] if len(note.split()) > 2 else ""
        try:
            from . import team
            r = next((x for x in team.list_requests() if x.get("id") == req_id), None)
        except Exception:  # noqa: BLE001
            r = None
        if r:
            rule = r.get("rule", "") if r.get("kind") in ("cleanup", "cleanup-archive") else ""
            approved_by = r.get("decided_by", "") or entry.get("who", "")
            reason = (r.get("reason") or "")[:300]
    how = "clean-up rule (approved)" if rule else \
        "approved request" if req_id else (note or "run in GAMbit")
    record_deleted(email, how=how, rule=rule, approved_by=approved_by, request=req_id,
                   reason=reason, who=entry.get("who", ""), note=note[:200])


def records() -> list[dict]:
    """The deletion record, newest first, each with 'verified' (signature checks out)."""
    from . import seal
    seen, out = set(), []
    for p in _record_paths():
        try:
            with open(p, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for ln in lines:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(r, dict) or r.get("id") in seen:
                continue
            seen.add(r.get("id"))
            try:
                v = seal.check(RECORD_KIND, r)
            except Exception:  # noqa: BLE001
                v = None
            r["verified"] = "yes" if v else ("not signed" if not r.get("seal") else
                                              "NO – changed or unknown signer")
            out.append(r)
    out.sort(key=lambda r: r.get("deleted", ""), reverse=True)
    return out


RECORD_COLUMNS = [("deleted", "Deleted"), ("email", "Account"), ("how", "How"),
                  ("rule", "Rule"), ("reason", "Why"), ("approved_by", "Approved by"),
                  ("by", "Run by"), ("archived_to", "Files archived to"),
                  ("archived", "What was archived"), ("computer", "Computer"),
                  ("verified", "Signature OK")]


def export_csv(path: str, rows: list[dict] | None = None):
    from . import csv_safe
    rows = records() if rows is None else rows
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv_safe.writer(fh)
        w.writerow([h for _k, h in RECORD_COLUMNS])
        for r in rows:
            w.writerow([str(r.get(k, "")).replace("T", " ") if k == "deleted" else
                        r.get(k, "") for k, _h in RECORD_COLUMNS])
