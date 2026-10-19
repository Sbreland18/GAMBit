"""Activity log: a permanent record of every GAM command GAMbit runs, with undo.

Each entry is one JSON line in AppData/activity/activity-YYYY-MM.jsonl, and –
if a shared folder is set – also in that folder (one file per person, so a
whole tech team can share a log without write conflicts).
"""

from __future__ import annotations

import datetime
import getpass
import glob
import json
import os
import platform
import uuid
from typing import Optional

from PySide6.QtCore import QStandardPaths

from .gam_runner import SECRET_WORDS, display_command, hide_text_passwords
from .settings import settings

READ_VERBS = {"print", "show", "info", "report", "check", "version", "help", "config",
              "checkconnection", "download", "get"}
MODIFY_VERBS = {"create", "add", "update", "delete", "del", "remove", "sync", "move",
                "transfer", "wipe", "purge", "trash", "untrash", "undelete", "clear",
                "cancel", "empty", "deprovision", "signout", "vacation", "signature",
                "forward", "imap", "pop", "issuecommand", "close", "reopen", "sendemail",
                "csv", "datatransfer", "collect", "process", "copy", "photo", "turnoff2sv",
                "delegate", "batch", "tbatch", "archive", "label", "filter", "sendas",
                "forwardingaddress", "suspend", "unsuspend", "claim", "deletephoto"}
ENTITY_KW = {"cros_ou", "cros_ou_and_children", "user", "users", "group", "groups", "ou", "ou_and_children", "ous",
             "ous_and_children", "all", "cros_sn", "courses", "course", "query"}


def local_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    d = os.path.join(base, "activity")
    os.makedirs(d, exist_ok=True)
    return d


def shared_dir() -> str:
    d = (settings.get("activity/shared_dir", "") or "").strip()
    if not d:
        team = (settings.get("team/folder", "") or "").strip()
        d = os.path.join(team, "activity") if team else ""
    return d


def who() -> str:
    from .auth import session
    if session.active():
        return session.email()
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return "unknown"


def mask(args: list[str]) -> list[str]:
    out, hide = [], False
    for a in args:
        out.append("********" if hide else hide_text_passwords(a))
        hide = (a.lower() in SECRET_WORDS) and not hide
    return out


def strip_config(args: list[str]) -> list[str]:
    """Drop a leading `config <name> <value> …` (e.g. num_threads) to see the real command."""
    a = list(args)
    if a[:1] and a[0].lower() == "config":
        a = a[1:]
        while a:
            w = a[0].lower()
            if w in ("save", "verify"):
                a = a[1:]
            elif "_" in w and len(a) >= 2:          # every GAM config variable has a _
                a = a[2:]
            else:
                break
    return a


def is_change(args: list[str]) -> bool:
    args = strip_config(args)
    low = [a.lower() for a in args[:8]]
    if "collect" in low and "preview" in (a.lower() for a in args):
        return False
    if any(a in READ_VERBS for a in low[:4]) and not any(a in MODIFY_VERBS for a in low[:2]):
        return False
    return any(a in MODIFY_VERBS for a in low)


def _write(entry: dict):
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    month = entry["time"][:7]
    paths = [os.path.join(local_dir(), f"activity-{month}.jsonl")]
    if shared_dir():
        paths.append(os.path.join(shared_dir(), f"activity-{who()}-{month}.jsonl"))
    for p in paths:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass


def record(args: list[str], code: int, status: str, undo: Optional[dict],
           profile: str, undo_of: str = "", note: str = "") -> dict:
    entry = {
        "id": uuid.uuid4().hex[:12],
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "who": who(), "computer": platform.node(), "profile": profile,
        "command": display_command(args), "args": mask(args),
        "change": is_change(args), "code": code, "status": status,
        "undo": undo if (undo and code == 0) else None,
        "undo_of": undo_of, "note": note,
    }
    _write(entry)
    return entry


def mark_undone(entry_id: str, by: str):
    _write({"id": uuid.uuid4().hex[:12], "type": "undone", "target": entry_id, "by": by,
            "time": datetime.datetime.now().isoformat(timespec="seconds"), "who": who()})


def load(days: int = 30, team: bool = False) -> list[dict]:
    since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat() \
        if days else ""
    files = glob.glob(os.path.join(local_dir(), "activity-*.jsonl"))
    if team and shared_dir() and os.path.isdir(shared_dir()):
        files = [f for f in files] + glob.glob(os.path.join(shared_dir(), "activity-*.jsonl"))
    entries, undone, seen = [], set(), set()
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                for ln in fh:
                    try:
                        e = json.loads(ln)
                    except ValueError:
                        continue
                    if e.get("type") == "undone":
                        undone.add(e.get("target"))
                        continue
                    if e.get("id") in seen or (since and e.get("time", "") < since):
                        continue
                    seen.add(e.get("id"))
                    entries.append(e)
        except OSError:
            continue
    for e in entries:
        e["undone"] = e["id"] in undone
    entries.sort(key=lambda e: e.get("time", ""), reverse=True)
    return entries


def write_csv(entries: list[dict], path: str):
    import csv
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Time", "Who", "Computer", "Domain", "Command", "Result", "Undone",
                    "Note"])
        for e in entries:
            res = "OK" if e.get("code") == 0 else (e.get("status") or f"exit {e.get('code')}")
            w.writerow([e.get("time", "").replace("T", " "), e.get("who"), e.get("computer"),
                        e.get("profile"), e.get("command"), res,
                        "yes" if e.get("undone") else "", e.get("note", "")])


def sheet_url() -> str:
    return (settings.get("activity/sheet_url", "") or "").strip()


def push_to_sheet() -> str:
    """Copy the last 365 days of the log to the Google Sheet. Returns the tab name."""
    import tempfile
    from . import google_io
    team = bool(shared_dir())
    entries = load(365, team=team)
    path = os.path.join(tempfile.gettempdir(), "GAMbit", "activity-upload.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_csv(entries, path)
    tab = "Team activity" if team else f"Activity - {who()}"
    google_io.replace_sheet_tab(sheet_url(), tab, path)
    settings.set("activity/sheet_pushed", datetime.datetime.now().isoformat(timespec="minutes"))
    return tab


# ================================================================== undo ===
FLIP = {"on": "off", "off": "on", "true": "false", "false": "true"}
FLIP_ATTRS = {"suspended", "suspend", "changepassword", "gal", "includeinglobaladdresslist",
              "archived"}


def infer_undo(args: list[str], users: list[dict]) -> Optional[dict]:
    """Work out the command that reverses `args`, using the cached 'before' state.

    Returns {"args": [...], "label": "..."} or None when it can't be undone safely.
    """
    a = list(args)
    low = [x.lower() for x in a]
    ou_of = {u["email"].lower(): u.get("ou", "") for u in users}

    def inv_user_attrs(attrs: list[str], email: Optional[str]):
        out, skipped = [], []
        i = 0
        while i < len(attrs):
            k = attrs[i].lower()
            v = attrs[i + 1] if i + 1 < len(attrs) else ""
            if k in FLIP_ATTRS and v.lower() in FLIP:
                out += [attrs[i], FLIP[v.lower()]]
                i += 2
            elif k in ("ou", "org") and email and ou_of.get(email.lower()):
                out += ["ou", ou_of[email.lower()]]
                i += 2
            elif k in ("password", "firstname", "lastname", "externalid"):
                skipped.append(k)
                i += 3 if k == "externalid" else 2
            else:
                skipped.append(k)
                i += 2
        return out, skipped

    # update user E attrs…
    if low[:2] == ["update", "user"] and len(a) > 3:
        email = a[2]
        if low[3] in ("email", "primaryemail", "username") and len(a) > 4:
            return {"args": ["update", "user", a[4], "email", email],
                    "label": f"Rename {a[4]} back to {email}"}
        inv, skipped = inv_user_attrs(a[3:], email)
        if inv:
            return {"args": ["update", "user", email, *inv],
                    "label": "Put back " + ", ".join(inv[::2]) +
                             (f" (can't undo: {', '.join(skipped)})" if skipped else "")}
        return None
    # <entity> … update user attrs  (users a,b / ou X / group G …)
    if "update" in low and low[low.index("update") + 1:low.index("update") + 2] == ["user"] \
            and low[0] in ENTITY_KW and low[0] != "update":
        idx = low.index("update")
        inv, skipped = inv_user_attrs(a[idx + 2:], None)
        if inv:
            return {"args": [*a[:idx], "update", "user", *inv],
                    "label": "Put back " + ", ".join(inv[::2])}
        return None
    # groups
    if low[:2] == ["update", "group"] and len(a) > 5:
        g, op = a[2], low[3]
        if op in ("add", "create"):
            rest = a[5:] if low[4] in ("member", "manager", "owner") else a[4:]
            return {"args": ["update", "group", g, "remove", *rest],
                    "label": f"Remove them from {g} again"}
        if op in ("remove", "delete"):
            return {"args": ["update", "group", g, "add", "member", *a[4:]],
                    "label": f"Add them back to {g} (as members)"}
        return None
    if low[:2] == ["create", "group"] and len(a) > 2:
        return {"args": ["delete", "group", a[2]], "label": f"Delete the new group {a[2]}"}
    if low[:2] == ["create", "user"] and len(a) > 2:
        return {"args": ["delete", "user", a[2]], "label": f"Delete the new account {a[2]}"}
    # aliases
    if low[:2] == ["create", "alias"] and len(a) > 2:
        return {"args": ["delete", "alias", a[2]], "label": f"Remove alias {a[2]}"}
    # org units
    if low[:2] == ["create", "ou"] and len(a) > 2:
        return {"args": ["delete", "ou", a[2]], "label": f"Delete the new org unit {a[2]}"}
    if low[:2] == ["update", "ou"] and len(a) > 4 and low[3] == "name":
        old = a[2]
        new = old.rsplit("/", 1)[0] + "/" + a[4]
        return {"args": ["update", "ou", new, "name", old.rsplit("/", 1)[-1]],
                "label": f"Rename {new} back to {old}"}
    # chromebooks
    if low[0] == "cros_sn" and "action" in low:
        act = low[low.index("action") + 1] if low.index("action") + 1 < len(low) else ""
        back = {"disable": "reenable", "reenable": "disable"}.get(act)
        if back:
            return {"args": [*a[:low.index("action")], "action", back],
                    "label": f"{back.title()} the device again"}
    # classroom
    if low[0] == "courses" and len(a) > 4 and low[2] in ("add", "remove", "delete"):
        op = "remove" if low[2] == "add" else "add"
        return {"args": [a[0], a[1], op, *a[3:]],
                "label": f"{op.title()} them {'from' if op == 'remove' else 'to'} the course again"}
    if low[:2] in (["update", "course"], ["update", "courses"]) and len(a) > 4 and \
            low[3] in ("status", "state") and low[4] == "archived":
        return {"args": [a[0], a[1], a[2], "state", "active"],
                "label": "Make the course(s) active again"}
    # licenses
    for verb, back in (("add", "delete"), ("delete", "add")):
        if verb in low and low[low.index(verb) + 1:low.index(verb) + 2] == ["license"]:
            i = low.index(verb)
            return {"args": [*a[:i], back, *a[i + 1:]],
                    "label": f"{'Remove' if back == 'delete' else 'Give back'} the license"}
    # mailbox settings: vacation / forward / imap / pop  on|off
    for kw in ("vacation", "forward", "imap", "pop"):
        if kw in low:
            i = low.index(kw)
            if i + 1 < len(low) and low[i + 1] in FLIP:
                if kw == "forward" and low[i + 1] in ("off", "false"):
                    return None   # we don't know where it forwarded before
                return {"args": [*a[:i], kw, FLIP[low[i + 1]]],
                        "label": f"Turn {kw} {FLIP[low[i + 1]]} again"}
    # delegates
    for verb, back in (("add", "delete"), ("delete", "add")):
        if verb in low and low[low.index(verb) + 1:low.index(verb) + 2] == ["delegate"]:
            i = low.index(verb)
            return {"args": [*a[:i], back, *a[i + 1:]],
                    "label": f"{'Remove' if back == 'delete' else 'Give back'} mailbox access"}
    return None


# ============================================================ preflight ===
def affected(args: list[str], users: list[dict], groups: list[dict]) -> Optional[tuple]:
    """For a change aimed at an OU/group/everyone, return (count, sample emails)."""
    if not is_change(args) or not args:
        return None
    low = [a.lower() for a in args]
    k = low[0]
    if k in ("ou", "ou_and_children") and len(args) > 1:
        path = args[1].rstrip("/") or "/"

        def inside(ou):
            ou = (ou or "/").rstrip("/") or "/"
            if k == "ou":
                return ou == path
            return path == "/" or ou == path or ou.startswith(path + "/")
        hits = [u["email"] for u in users if inside(u.get("ou")) and not u.get("suspended")]
        return len(hits), hits[:15]
    if k == "all" and len(low) > 1 and low[1] == "users":
        hits = [u["email"] for u in users if not u.get("suspended")]
        return len(hits), hits[:15]
    if k == "group" and len(args) > 1:
        g = next((x for x in groups if x["email"].lower() == args[1].lower()), None)
        n = int(g.get("members") or 0) if g and str(g.get("members", "")).isdigit() else 0
        return (n, []) if n else None
    if k == "users" and len(args) > 1:
        emails = [e for e in args[1].split(",") if e]
        return len(emails), emails[:15]
    if low[:2] == ["update", "ou"] and len(args) > 4 and low[3] in ("move", "add") \
            and low[4] in ("ou", "ou_and_children"):
        sub = affected(args[4:6] + ["update"], users, groups)
        return sub
    return None


# ============================================== undo that needs a quick look ===
ROLES = ("member", "manager", "owner")


def _col(row: dict, *names) -> str:
    low = {(k or "").lower(): v for k, v in row.items()}
    for n in names:
        if low.get(n.lower()):
            return low[n.lower()]
    return ""


def capture_undo(args: list[str], run_csv) -> Optional[dict]:
    """Undo for changes whose 'before' state isn't in GAMbit's saved lists.

    Looks it up with one quick read-only GAM call just before the change runs:
    group member roles (removals and role changes) and Chromebook OU/user/
    location/asset ID/notes. `run_csv(args) -> (code, rows, err)`.
    Returns {"steps": [[...], ...], "label": ...} or None.
    """
    low = [a.lower() for a in args]
    try:
        # update group G remove|delete|update [role] a,b,c
        if low[:2] == ["update", "group"] and len(args) > 4 and \
                low[3] in ("remove", "delete", "update"):
            g, op = args[2], low[3]
            rest = args[4:]
            if rest and rest[0].lower() in ROLES:
                rest = rest[1:]
            emails = {e.strip().lower() for x in rest for e in x.split(",") if "@" in e}
            if not emails:
                return None
            code, rows, _ = run_csv(["print", "group-members", "group", g])
            if code != 0:
                return None
            by_role: dict[str, list[str]] = {}
            for r in rows:
                e = _col(r, "email").lower()
                if e in emails:
                    by_role.setdefault(_col(r, "role").lower() or "member", []).append(e)
            if not by_role:
                return None
            verb = "add" if op in ("remove", "delete") else "update"
            steps = [["update", "group", g, verb, role, ",".join(sorted(es))]
                     for role, es in sorted(by_role.items())]
            n = sum(len(v) for v in by_role.values())
            return {"steps": steps, "args": steps[0],
                    "label": (f"Add {n} back to {g} with their old roles" if verb == "add"
                              else f"Put back {n} old role(s) in {g}")}
        # cros_sn SN update <attrs>   (not actions – those are handled elsewhere)
        if low[0] == "cros_sn" and len(args) > 3 and low[2] == "update" and \
                "action" not in low:
            sn = args[1]
            code, rows, _ = run_csv(["cros_sn", sn, "print", "cros", "fields",
                                     "orgunitpath,annotateduser,annotatedlocation,"
                                     "annotatedassetid,notes"])
            if code != 0 or not rows:
                return None
            before = rows[0]
            keymap = {"ou": "orgUnitPath", "org": "orgUnitPath", "user": "annotatedUser",
                      "location": "annotatedLocation", "asset": "annotatedAssetId",
                      "assetid": "annotatedAssetId", "tag": "annotatedAssetId",
                      "notes": "notes", "updatenotes": "notes"}
            back = []
            i = 3
            while i + 1 < len(args):
                k = low[i]
                if k in keymap:
                    out_key = "notes" if k == "updatenotes" else k
                    back += [out_key, _col(before, keymap[k]) or ("/" if out_key in
                                                                  ("ou", "org") else "")]
                    i += 2
                else:
                    i += 1
            if not back:
                return None
            steps = [["cros_sn", sn, "update", *back]]
            return {"steps": steps, "args": steps[0],
                    "label": "Put back the Chromebook's " + ", ".join(back[::2])}
    except Exception:  # noqa: BLE001 – never block a command because undo lookup failed
        return None
    return None


def affected_list(args: list[str], users: list[dict], groups: list[dict],
                  run_csv=None) -> Optional[tuple]:
    """Like affected(), but returns the full list (fetching group members if needed)."""
    res = affected(args, users, groups)
    if res is None:
        return None
    n, _sample = res
    low = [a.lower() for a in args]
    if low[0] == "group" and run_csv:
        code, rows, _ = run_csv(["print", "group-members", "group", args[1]])
        if code == 0:
            emails = [_col(r, "email") for r in rows if _col(r, "email")]
            return len(emails), emails
    if low[0] in ("ou", "ou_and_children") or low[:2] == ["all", "users"] or \
            low[:2] == ["update", "ou"]:
        k = low[0] if low[0] != "update" else low[4]
        path = args[1] if low[0] != "update" else args[5]
        if k == "all":
            return n, [u["email"] for u in users if not u.get("suspended")]
        p = path.rstrip("/") or "/"

        def inside(ou):
            ou = (ou or "/").rstrip("/") or "/"
            if k == "ou":
                return ou == p
            return p == "/" or ou == p or ou.startswith(p + "/")
        return n, [u["email"] for u in users if inside(u.get("ou")) and not u.get("suspended")]
    if low[0] == "users":
        return n, [e for e in args[1].split(",") if e]
    return res
