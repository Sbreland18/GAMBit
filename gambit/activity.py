"""Activity log: a permanent record of every GAM command GAMbit runs, with undo.

Each entry is one JSON line in AppData/activity/activity-YYYY-MM.jsonl, and –
if a shared folder is set – also in that folder (one file per person, so a
whole tech team can share a log without write conflicts).
"""

from __future__ import annotations

from . import tempfiles as _tf
from . import csv_safe
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
                "forwardingaddress", "suspend", "unsuspend", "claim", "deletephoto",
                # GAM7 verbs that change things and weren't caught before (QA round 36)
                "accept", "append", "approve", "block", "cancelwipe", "dedup", "disable",
                "enable", "hide", "unhide", "import", "importemail", "insert", "insertemail",
                "language", "modify", "obliterate", "profile", "replace", "replacedomain",
                "revoke", "rotate", "send", "sendreply", "spam", "draft", "draftemail",
                "addevent", "deleteevent", "moveevent", "updateevent", "yubikey", "upload"}
# words that name *what* a command acts on (gam <entity> <value> <verb> …)
_ENTITY_FIRST = {"user", "users", "user_ns", "users_ns", "group", "groups", "group_ns",
                 "groups_ns", "group_users", "group_users_ns", "ou", "ou_ns",
                 "ou_and_children", "ou_and_children_ns", "ous", "ous_ns", "ous_and_children",
                 "ous_and_children_ns", "cros", "cros_sn", "cros_ou", "cros_ou_and_children",
                 "cros_ous", "cros_ous_and_children", "courses", "course", "query",
                 "queries", "domains", "teachers", "students", "file", "csvfile",
                 "datafile", "croscsvfile", "crosfile", "license", "licenses"}
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


def verb_index(low: list[str]) -> int:
    """Where the action word is: 0 for `gam update user …`, 2 for `gam users a,b update …`
    (after `select <section>`, which strip_config leaves in place)."""
    i = 0
    if low[:1] == ["select"]:
        i = 2
    if len(low) > i + 1 and (low[i] in _ENTITY_FIRST or low[i] == "all"):
        return i + 2
    return i


_TF = {"true", "false", "on", "off", "yes", "no", "enabled", "disabled", "1", "0"}
_REDIRECT_CSV_FLAGS = {"multiprocess": 0, "append": 0, "noheader": 0, "delayopen": 0,
                       "charset": 1, "columndelimiter": 1, "quotechar": 1, "sortheaders": 1,
                       "timestampcolumn": 1}
_FILE_LOOPS = {"csv", "loop", "csvtest"}
_BATCHES = {"batch", "tbatch"}
READ_EXTRA = {"whatis", "showsections", "list"}


def unwrap(args) -> tuple[list[str], bool, bool]:
    """The command GAM will really run, behind its wrappers.

    → (inner command, understood, changes GAM's own config). `select <section> [save]`,
    `config … [save]`, `selectfilter …`, `multiprocessexit …` and `redirect csv|stdout|
    stderr <file> …` are stepped over; `csv|loop <file> … gam <command>` gives the command
    after `gam`. A batch file (`batch`, `tbatch`) – or anything GAMbit can't follow, like
    `todrive` options – is reported as not understood, so callers treat it as the most
    powerful kind of change."""
    a = [str(x) for x in args or []]
    cfg = False
    while a:
        w = a[0].lower()
        if w == "select" and len(a) >= 2:
            a = a[2:]
            while a and a[0].lower() in ("save", "verify"):
                cfg = cfg or a[0].lower() == "save"
                a = a[1:]
        elif w in ("selectfilter", "selectoutputfilter", "selectinputfilter") and len(a) >= 2:
            a = a[2:]
        elif w == "multiprocessexit" and len(a) >= 2:
            a = a[2:]
        elif w == "config":
            b = strip_config(a)
            cfg = cfg or any(x.lower() == "save" for x in a[:len(a) - len(b)])
            if len(b) == len(a):
                return a, False, cfg
            a = b
        elif w == "redirect":
            if len(a) < 3 or a[1].lower() not in ("csv", "stdout", "stderr"):
                return a, False, cfg
            kind = a[1].lower()
            a = a[3:]
            if kind == "csv":
                while a:
                    f = a[0].lower()
                    if f in _REDIRECT_CSV_FLAGS:
                        a = a[1 + _REDIRECT_CSV_FLAGS[f]:]
                    elif f in ("noescapechar", "transpose"):
                        a = a[2:] if len(a) > 1 and a[1].lower() in _TF else a[1:]
                    elif f == "todrive":
                        return a, False, cfg      # its options can't be followed safely
                    else:
                        break
            else:
                while a and a[0].lower() in ("multiprocess", "append"):
                    a = a[1:]
        else:
            break
    if not a:
        return a, True, cfg
    w = a[0].lower()
    if w in _BATCHES:
        return a, False, cfg
    if w in _FILE_LOOPS:
        low = [x.lower() for x in a]
        if "gam" in low[2:]:
            inner, ok, c2 = unwrap(a[low.index("gam", 2) + 1:])
            return inner, ok, cfg or c2
        return a, False, cfg
    return a, True, cfg


def is_change(args: list[str]) -> bool:
    """True if `gam <args>` changes something. Only the action word of the real command
    (behind `redirect`, `csv … gam`, `select` …) decides – a group, org unit or file whose
    *name* is a word like “info” or “print” can't make a change look like a read. Anything
    GAMbit can't follow (batch files, unknown action words) counts as a change."""
    inner, ok, cfg = unwrap(args)
    if not ok or cfg:
        return True
    full = [a.lower() for a in inner]
    if not full:
        return False
    if "collect" in full[:8] and "preview" in full:
        return False
    vi = verb_index(full)
    rest = full[vi:vi + 8]
    if not rest:
        return False
    if rest[0] in MODIFY_VERBS:
        return True
    if rest[0] in READ_VERBS or rest[0] in READ_EXTRA:
        return False
    return True                    # an action GAMbit doesn't know: assume it changes things


CHAIN = ("prev", "h", "ch", "sig")          # fingerprint fields – never part of the content
ANCHOR_KEY = "activity/anchors"              # {file name: {"n": lines, "h": last h}}
CHAIN_SINCE_KEY = "activity/chain_since"     # when this PC started fingerprinting lines


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)\
        .encode("utf-8")


def content_hash(entry: dict) -> str:
    import hashlib
    return hashlib.sha256(_canon({k: v for k, v in entry.items() if k not in CHAIN}))\
        .hexdigest()


def link_hash(prev: str, ch: str) -> str:
    import hashlib
    return hashlib.sha256(f"{prev}|{ch}".encode()).hexdigest()


def _last_h(path: str) -> tuple[str, int]:
    """(fingerprint of the last line, number of lines) of a log file."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return "", 0
    lines = [ln for ln in data.splitlines() if ln.strip()]
    for ln in reversed(lines):
        try:
            return str(json.loads(ln).get("h") or ""), len(lines)
        except ValueError:
            return "", len(lines)
    return "", 0


def _anchors() -> dict:
    try:
        d = json.loads(settings.fresh(ANCHOR_KEY, "") or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def _set_anchor(path: str, n: int, h: str):
    d = _anchors()
    d[os.path.basename(path)] = {"n": n, "h": h}
    settings.set(ANCHOR_KEY, json.dumps(d))


def _sign_ch(ch: str) -> dict:
    try:
        from . import seal
        return seal.seal_for("activity", ch)
    except Exception:  # noqa: BLE001 – never lose a log line over a signature
        return {}


def _write(entry: dict):
    """Append one line to each log file. Every line carries a fingerprint of its content
    (signed with this computer's / person's key) chained to the line before it, so an
    edited, inserted or deleted line shows up when the log is checked."""
    from . import file_lock
    month = entry["time"][:7]
    paths = [(os.path.join(local_dir(), f"activity-{month}.jsonl"), True)]
    if shared_dir():
        paths.append((os.path.join(shared_dir(), f"activity-{who()}-{month}.jsonl"), False))
    if not settings.get(CHAIN_SINCE_KEY, ""):
        settings.set(CHAIN_SINCE_KEY, entry["time"])
    body = {k: v for k, v in entry.items() if k not in CHAIN}
    ch = content_hash(body)
    sig = _sign_ch(ch)
    for p, local in paths:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            try:
                lock = file_lock.held(p + ".lock", wait=5)
                lock.__enter__()
            except Exception:  # noqa: BLE001 – busy: still write (a gap shows as a break)
                lock = None
            try:
                prev, n = _last_h(p)
                line = dict(body, prev=prev, ch=ch, h=link_hash(prev, ch), sig=sig)
                with open(p, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(line, ensure_ascii=False) + "\n")
                if local:
                    _set_anchor(p, n + 1, line["h"])
            finally:
                if lock is not None:
                    lock.__exit__(None, None, None)
        except OSError:
            pass


# ------------------------------------------------------------ checking ---
def verify_lines(lines: list[str], trusted: dict | None = None,
                 chain_since: str = "") -> list[tuple[str, str]]:
    """For each line: (state, why). state is ok / legacy (written before fingerprints) /
    unverified (signed on a computer this one doesn't know) / bad."""
    from .auth import crypto
    if trusted is None:
        from . import seal
        try:
            trusted = seal._trusted()
        except Exception:  # noqa: BLE001
            trusted = {}
    out: list[tuple[str, str]] = []
    expect, chained = "", False
    for ln in lines:
        try:
            e = json.loads(ln)
            if not isinstance(e, dict):
                raise ValueError
        except ValueError:
            out.append(("bad", "unreadable line"))
            continue
        if "h" not in e:
            late = chain_since and str(e.get("time", "")) >= chain_since
            if chained or late:
                out.append(("bad", "a line without a fingerprint, added after fingerprints "
                                   "started (written or edited by hand)"))
            else:
                out.append(("legacy", "written before GAMbit fingerprinted the log"))
            continue
        ch = content_hash(e)
        if ch != e.get("ch") or link_hash(str(e.get("prev", "")), ch) != e.get("h"):
            out.append(("bad", "changed after GAMbit wrote it"))
            expect, chained = str(e.get("h", "")), True
            continue
        if str(e.get("prev", "")) != expect:
            out.append(("bad", "lines before this one were removed, added or reordered"))
            expect, chained = e["h"], True
            continue
        expect, chained = e["h"], True
        s = e.get("sig") or {}
        if not s:
            out.append(("ok", "fingerprinted (not signed)"))
            continue
        t = trusted.get(str(s.get("kid", "")))
        if not t:
            out.append(("unverified", "signed on a computer this one doesn't know"))
            continue
        level, _who, pub = t
        from .seal import _bytes
        try:
            good = crypto.verify(pub, crypto.unb64(str(s.get("sig", ""))),
                                 _bytes("activity", ch))
        except (ValueError, TypeError):
            good = False
        out.append(("ok", "signed") if good else ("bad", "the signature doesn't match"))
    return out


def check_file(path: str, trusted: dict | None = None) -> dict:
    """{file, lines, ok, legacy, unverified, bad: [(line no, why)], last}"""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    except OSError as exc:
        return {"file": path, "lines": 0, "ok": 0, "legacy": 0, "unverified": 0,
                "bad": [(0, f"can't be read: {exc}")], "last": ""}
    states = verify_lines(lines, trusted, settings.get(CHAIN_SINCE_KEY, "") or "")
    rep = {"file": path, "lines": len(lines), "ok": 0, "legacy": 0, "unverified": 0,
           "bad": [], "last": ""}
    hs = []
    for i, (st, why) in enumerate(states, 1):
        if st == "bad":
            rep["bad"].append((i, why))
        else:
            rep[st] += 1
        try:
            hs.append(str(json.loads(lines[i - 1]).get("h") or ""))
        except ValueError:
            hs.append("")
    rep["last"] = next((h for h in reversed(hs) if h), "")
    a = _anchors().get(os.path.basename(path))
    if a and os.path.dirname(os.path.abspath(path)) == os.path.abspath(local_dir()):
        n, h = int(a.get("n", 0) or 0), str(a.get("h", ""))
        if n > len(lines):
            rep["bad"].append((len(lines), f"the file is {n - len(lines)} line(s) shorter "
                                           "than when GAMbit last wrote to it"))
        elif n and hs[n - 1] != h:
            rep["bad"].append((n, "the lines GAMbit last wrote were changed or replaced"))
    return rep


def check_all(team: bool = True) -> list[dict]:
    """Check this computer's log files (and the team's, if shared) – plus files the log
    should have that are gone."""
    from . import seal
    try:
        trusted = seal._trusted()
    except Exception:  # noqa: BLE001
        trusted = {}
    files = sorted(glob.glob(os.path.join(local_dir(), "activity-*.jsonl")))
    reps = [check_file(f, trusted) for f in files]
    have = {os.path.basename(f) for f in files}
    for name in sorted(_anchors()):
        if name not in have:
            reps.append({"file": os.path.join(local_dir(), name), "lines": 0, "ok": 0,
                         "legacy": 0, "unverified": 0,
                         "bad": [(0, "this month's log file was deleted")], "last": ""})
    if team and shared_dir() and os.path.isdir(shared_dir()):
        for f in sorted(glob.glob(os.path.join(shared_dir(), "activity-*.jsonl"))):
            reps.append(check_file(f, trusted))
    return reps


INTEGRITY_KEY = "activity/integrity_last"


def integrity_summary(reps: list[dict]) -> dict:
    bad = [(os.path.basename(r["file"]), n, why) for r in reps for n, why in r["bad"]]
    return {"at": datetime.datetime.now().isoformat(timespec="minutes"),
            "files": len(reps), "lines": sum(r["lines"] for r in reps),
            "bad": bad[:200], "bad_count": len(bad)}


def run_check(log=print) -> dict:
    """Daily: check the log and alert when something new looks tampered with."""
    summ = integrity_summary(check_all())
    try:
        before = json.loads(settings.get(INTEGRITY_KEY, "") or "{}")
    except ValueError:
        before = {}
    settings.set(INTEGRITY_KEY, json.dumps(summ))
    old = {tuple(x) for x in before.get("bad", [])}
    new = [x for x in summ["bad"] if tuple(x) not in old]
    log(f"Activity log check: {summ['lines']} line(s) in {summ['files']} file(s), "
        f"{summ['bad_count']} problem(s).")
    if new:
        from . import alerts
        alerts.notify("GAMbit's activity log looks edited – lines were changed, added or "
                      "removed outside GAMbit:\n" + "\n".join(
                          f"• {f}, line {n}: {why}" for f, n, why in new[:20]),
                      "GAMbit activity log")
    return summ


def integrity_attention() -> list[tuple[str, str]]:
    try:
        d = json.loads(settings.get(INTEGRITY_KEY, "") or "{}")
    except ValueError:
        return []
    n = int(d.get("bad_count", 0) or 0)
    return [("bad", f"The activity log has {n} line(s) that were changed outside "
                    "GAMbit")] if n else []


def undo_allowed(entry: dict) -> tuple[bool, str]:
    """Undo and re-run read commands from the log – never from a line that was edited."""
    st = entry.get("integrity")
    if st == "bad":
        return False, ("This log entry was changed after GAMbit wrote it, so GAMbit won't "
                       "run commands from it.")
    return True, ""


# ============================================ plain-English Chromebook changes ===
_CROS_ENT = {"cros": "id", "cros_sn": "serial"}
_ACTIONS = {"disable": "disabled", "reenable": "re-enabled", "deprovision": "deprovisioned",
            "deprovision_same_model_replace": "deprovisioned (replaced)",
            "deprovision_different_model_replace": "deprovisioned (replaced)",
            "deprovision_retiring_device": "deprovisioned (retired)",
            "disable_wiped": "disabled", "remote_powerwash": "powerwashed",
            "wipe_users": "wiped the users", "reboot": "rebooted"}


def _cros_target(args: list[str]):
    """(kind, [ids or serials], rest) for Chromebook commands, else None."""
    a = list(args)
    if a[:1] == ["select"] and len(a) > 2:
        a = a[2:]
    if len(a) >= 3 and a[0] == "update" and a[1] == "cros":
        return "id", [x for x in a[2].split(",") if x], a[3:]
    if len(a) >= 3 and a[0].lower() in _CROS_ENT:
        kind = _CROS_ENT[a[0].lower()]
        return kind, [x for x in a[1].split(",") if x], a[2:]
    if len(a) >= 3 and a[0].lower() in ("cros_ou", "cros_ou_and_children"):
        return "ou", [a[1]], a[2:]
    return None


def device_labels(kind: str, items: list[str]) -> list[str]:
    from . import device_names
    if kind == "id":
        return [device_names.label(x) for x in items]
    return list(items)


def describe(args: list[str]) -> str:
    """'Moved Chromebook 5CD0372JK1 (asset HS2074) to /Chrome Devices/Hancock High School'
    – or '' for commands that aren't Chromebook changes (their command already says it)."""
    try:
        t = _cros_target(strip_config(list(args or [])))
    except Exception:  # noqa: BLE001
        return ""
    if not t:
        return ""
    kind, items, rest = t
    low = [x.lower() for x in rest]
    if not low:
        return ""
    if low[0] == "update":
        rest, low = rest[1:], low[1:]
    did = []
    i = 0
    while i < len(low):
        k = low[i]
        v = rest[i + 1] if i + 1 < len(rest) else ""
        if k in ("ou", "org"):
            did.append(f"moved to {v}")
        elif k == "user":
            did.append(f"assigned user set to {v}" if v else "assigned user blanked")
        elif k in ("assetid", "asset", "tag"):
            did.append(f"asset ID set to {v}" if v else "asset ID blanked")
        elif k == "location":
            did.append(f"location set to {v}" if v else "location blanked")
        elif k in ("notes", "updatenotes"):
            did.append("notes updated")
        elif k == "action":
            did.append(_ACTIONS.get(v.lower(), f"action {v}"))
        elif k == "issuecommand" and i + 2 < len(rest):
            v = rest[i + 2]
            did.append(_ACTIONS.get(v.lower(), f"sent {v}"))
            i += 1
        elif k in ("print", "show", "info", "get"):
            return ""
        else:
            i += 1
            continue
        i += 2
    if not did:
        return ""
    if kind == "ou":
        who = f"every Chromebook in {items[0]}"
    else:
        names = device_labels(kind, items)
        shown = ", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5
                                        else "")
        who = (f"Chromebook {shown}" if len(names) == 1 else
               f"{len(names)} Chromebooks ({shown})")
    return f"{who}: " + "; ".join(did)


def describe_any(args: list[str]) -> str:
    """Plain English for any logged command: Chromebook changes in detail, the common
    account and group changes, else GAM's own one-line description."""
    d = describe(args)
    if d:
        return d
    a = strip_config(list(args or []))
    if a[:1] == ["select"] and len(a) > 2:
        a = a[2:]
    low = [x.lower() for x in a]
    try:
        if low[:2] == ["update", "user"] and len(a) > 3:
            u, rest = a[2], low[3:]
            if rest[:2] == ["suspended", "on"]:
                return f"Suspended {u}"
            if rest[:2] == ["suspended", "off"]:
                return f"Unsuspended {u}"
            if rest[:1] == ["password"]:
                return f"Reset {u}'s password"
            if rest[:1] in (["ou"], ["org"]) and len(a) > 4:
                return f"Moved {u} to {a[4]}"
            return f"Updated {u} ({', '.join(rest[::2][:4])})"
        if low[:1] == ["user"] and len(a) > 2:
            u, verb = a[1], low[2]
            return {"signout": f"Signed {u} out everywhere",
                    "turnoff2sv": f"Turned off 2-Step Verification for {u}",
                    "deprovision": f"Removed {u}'s app passwords and tokens"}.get(
                verb, "")
        if low[:2] == ["update", "group"] and len(a) > 4:
            g = a[2]
            if low[3] in ("add", "remove", "delete", "sync"):
                who = a[-1]
                n = who.count(",") + 1
                who = who if n <= 3 else f"{n} members"
                return (f"Added {who} to {g}" if low[3] == "add" else
                        f"Synced the members of {g}" if low[3] == "sync" else
                        f"Removed {who} from {g}")
        if low[:2] == ["create", "user"] and len(a) > 2:
            return f"Created the account {a[2]}"
        if low[:2] == ["delete", "user"] and len(a) > 2:
            return f"Deleted the account {a[2]}"
        if low[:2] == ["undelete", "user"] and len(a) > 2:
            return f"Restored the deleted account {a[2]}"
        if low[:2] == ["create", "datatransfer"] and len(a) > 4:
            return f"Started moving {a[2]}'s {a[3]} files to {a[4]}"
        if low[:2] == ["create", "alias"] and len(a) > 4:
            return f"Added the alias {a[2]} to {a[4]}"
        if low[:2] == ["create", "group"] and len(a) > 2:
            return f"Created the group {a[2]}"
        if low[:2] == ["delete", "group"] and len(a) > 2:
            return f"Deleted the group {a[2]}"
    except IndexError:
        pass
    try:
        from .helper import verify
        return verify.describe(a) or ""
    except Exception:  # noqa: BLE001
        return ""


def named_command(args: list[str]) -> str:
    """The command with Chromebook device IDs shown as their serial numbers."""
    t = _cros_target(strip_config(list(args or [])))
    shown = display_command(args)
    if not t or t[0] != "id":
        return shown
    from . import device_names
    ids = t[1]
    names = [device_names.serial_or_id(x) for x in ids]
    if names == ids:
        return shown
    joined = ",".join(names[:5]) + (f",…+{len(names) - 5} more" if len(names) > 5 else "")
    return shown.replace(",".join(ids), f"[{joined}]", 1)


def record(args: list[str], code: int, status: str, undo: Optional[dict],
           profile: str, undo_of: str = "", note: str = "") -> dict:
    what = describe_any(args) if is_change(args) else ""
    t = _cros_target(strip_config(list(args or []))) if what else None
    entry = {
        "id": uuid.uuid4().hex[:12],
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "who": who(), "computer": platform.node(), "profile": profile,
        "command": display_command(args), "args": mask(args),
        "change": is_change(args), "code": code, "status": status,
        "undo": undo if (undo and code == 0) else None,
        "undo_of": undo_of, "note": note,
    }
    if what:
        entry["what"] = what
        entry["command_named"] = named_command(args)
        if t and t[0] != "ou":
            entry["devices"] = device_labels(t[0], t[1])[:500]
    _write(entry)
    if code == 0 and entry["change"]:
        try:
            from . import retention
            retention.on_activity(entry)          # account deletions → deletion record
        except Exception:  # noqa: BLE001 – recording must never fail a command
            pass
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
    entries, undone, by_id = [], set(), {}
    try:
        from . import seal
        trusted = seal._trusted()
    except Exception:  # noqa: BLE001
        trusted = {}
    since_chain = settings.get(CHAIN_SINCE_KEY, "") or ""
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        except OSError:
            continue
        for ln, (state, why) in zip(lines, verify_lines(lines, trusted, since_chain)):
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(e, dict) or not e.get("id"):
                continue
            if e.get("type") == "undone":
                if state != "bad":            # a forged "undone" mark mustn't hide a change
                    undone.add(e.get("target"))
                continue
            if since and e.get("time", "") < since:
                continue
            e["integrity"], e["integrity_why"] = state, why
            prev = by_id.get(e["id"])
            if prev is not None:              # the same line in the local + team copy
                if state == "bad":
                    prev["integrity"], prev["integrity_why"] = state, why
                continue
            by_id[e["id"]] = e
            entries.append(e)
    for e in entries:
        e["undone"] = e["id"] in undone
    entries.sort(key=lambda e: e.get("time", ""), reverse=True)
    return entries


def write_csv(entries: list[dict], path: str):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv_safe.writer(fh)
        w.writerow(["Time", "Who", "Computer", "Domain", "Command", "Result", "Undone",
                    "Note", "Integrity", "Fingerprint"])
        label = {"ok": "verified", "legacy": "older (not fingerprinted)",
                 "unverified": "signed on another computer", "bad": "EDITED OUTSIDE GAMBIT"}
        for e in entries:
            res = "OK" if e.get("code") == 0 else (e.get("status") or f"exit {e.get('code')}")
            w.writerow([e.get("time", "").replace("T", " "), e.get("who"), e.get("computer"),
                        e.get("profile"), e.get("command"), res,
                        "yes" if e.get("undone") else "", e.get("note", ""),
                        label.get(e.get("integrity", ""), ""), (e.get("h") or "")[:16]])


def sheet_url() -> str:
    return (settings.get("activity/sheet_url", "") or "").strip()


def push_to_sheet() -> str:
    """Copy the last 365 days of the log to the Google Sheet. Returns the tab name."""
    from . import google_io
    team = bool(shared_dir())
    entries = load(365, team=team)
    path = os.path.join(_tf.folder(), "activity-upload.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_csv(entries, path)
    tab = "Team activity" if team else f"Activity - {who()}"
    google_io.replace_sheet_tab(sheet_url(), tab, path)
    # the chain's fingerprints, kept off this PC: the Sheet's version history keeps every
    # night's copy, so a later edit of the log here can be compared with what was sent
    fp = os.path.join(_tf.folder(), "activity-fingerprints.csv")
    with open(fp, "w", newline="", encoding="utf-8") as fh:
        w = csv_safe.writer(fh)
        w.writerow(["Checked", "Computer", "File", "Lines", "Last fingerprint", "Problems"])
        now = datetime.datetime.now().isoformat(timespec="minutes").replace("T", " ")
        for r in check_all(team=team):
            w.writerow([now, platform.node(), os.path.basename(r["file"]), r["lines"],
                        r["last"], "; ".join(f"line {n}: {why}" for n, why in r["bad"][:5])])
    try:
        google_io.replace_sheet_tab(sheet_url(), "Log fingerprints"
                                    + ("" if team else f" - {who()}"), fp)
    except Exception:  # noqa: BLE001 – the activity copy itself already went through
        pass
    settings.set("activity/sheet_pushed", datetime.datetime.now().isoformat(timespec="minutes"))
    return tab


# ================================================================== undo ===
FLIP = {"on": "off", "off": "on", "true": "false", "false": "true"}
FLIP_ATTRS = {"suspended", "suspend", "changepassword", "gal", "includeinglobaladdresslist",
              "archived"}
# the column `print users fields …` returns for each on/off attribute
FLIP_COLUMN = {"suspended": "suspended", "suspend": "suspended",
               "changepassword": "changePasswordAtNextLogin",
               "gal": "includeInGlobalAddressList",
               "includeinglobaladdresslist": "includeInGlobalAddressList",
               "archived": "archived"}
_FLIP_FIELDS = "primaryemail,orgunitpath,suspended,changepassword,gal,archived"
UNDO_CHUNK = 200


def _truthy(v) -> Optional[bool]:
    v = str(v if v is not None else "").strip().lower()
    if v in ("true", "on", "1", "yes"):
        return True
    if v in ("false", "off", "0", "no"):
        return False
    return None


def _flip_pairs(attrs: list[str]) -> tuple[dict, list[str]]:
    """{attr: wanted bool} for the on/off attributes in `attrs`, plus the other keys."""
    wanted, other = {}, []
    i = 0
    while i < len(attrs):
        k = attrs[i].lower()
        v = attrs[i + 1] if i + 1 < len(attrs) else ""
        if k in FLIP_ATTRS and _truthy(v) is not None:
            wanted[k] = bool(_truthy(v))
        else:
            other.append(k)
        i += 3 if k == "externalid" else 2
    return wanted, other


def _flip_steps(before: dict[str, dict], wanted: dict) -> list[list[str]]:
    """Undo steps that put back only what really changed: users whose value was already
    the new value are left alone. `before` = {email: {attr: bool|None}}; users whose old
    value isn't known are left out (never guessed)."""
    groups: dict[tuple, list[str]] = {}
    for email, vals in before.items():
        back = []
        for k, new in wanted.items():
            old = vals.get(FLIP_COLUMN[k])
            if old is None or old == new:
                continue
            back += [k, "on" if old else "off"]
        if back:
            groups.setdefault(tuple(back), []).append(email)
    steps = []
    for back, emails in sorted(groups.items()):
        emails = sorted(emails)
        for i in range(0, len(emails), UNDO_CHUNK):
            steps.append(["users", ",".join(emails[i:i + UNDO_CHUNK]), "update", "user",
                          *back])
    return steps


def _user_update_split(a: list[str]) -> Optional[tuple[list[str], list[str]]]:
    """(entity args, attrs) for `update user(s) E …` and `<entity> … update user …`."""
    low = [x.lower() for x in a]
    if low[:2] in (["update", "user"], ["update", "users"]) and len(a) > 3:
        return ["users", a[2]], a[3:]
    if "update" in low and low[0] in ENTITY_KW and low[0] != "update":
        idx = low.index("update")
        if low[idx + 1:idx + 2] == ["user"]:
            return a[:idx], a[idx + 2:]
    return None


def infer_undo(args: list[str], users: list[dict]) -> Optional[dict]:
    """Work out the command that reverses `args`, using the cached 'before' state.

    Returns {"args": [...], "label": "..."} or None when it can't be undone safely.
    On/off attributes are only put back where the cached list shows the value really
    changed (suspending someone who was already suspended has nothing to undo); values
    GAMbit doesn't keep a copy of aren't guessed – capture_undo looks those up instead.
    """
    a = list(args)
    low = [x.lower() for x in a]
    if not low:
        return None
    by_email = {u["email"].lower(): u for u in users if u.get("email")}
    ou_of = {e: u.get("ou", "") for e, u in by_email.items()}

    def cached_before(emails: list[str]) -> Optional[dict]:
        out = {}
        for e in emails:
            u = by_email.get(e.strip().lower())
            if u is None:
                return None                   # someone we know nothing about – no guess
            out[e.strip().lower()] = {"suspended": bool(u.get("suspended"))}
        return out

    def inv_user_attrs(attrs: list[str], email: Optional[str]):
        out, skipped = [], []
        i = 0
        while i < len(attrs):
            k = attrs[i].lower()
            v = attrs[i + 1] if i + 1 < len(attrs) else ""
            if k in FLIP_ATTRS and _truthy(v) is not None:
                u = by_email.get((email or "").lower())
                if FLIP_COLUMN[k] == "suspended" and u is not None:
                    old = bool(u.get("suspended"))
                    if old != bool(_truthy(v)):
                        out += [attrs[i], "on" if old else "off"]
                    # unchanged → nothing to put back
                else:
                    skipped.append(k)          # old value unknown – don't guess
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
    split = _user_update_split(a)
    if split and low[0] != "update":
        entity, attrs = split
        wanted, other = _flip_pairs(attrs)
        if not wanted or other:
            return None            # OU moves etc. for many people: no safe single undo
        ent = [x.lower() for x in entity]
        if ent[:1] in (["user"], ["users"]) and len(entity) == 2:
            before = cached_before([e for e in entity[1].split(",") if e.strip()])
            if before is None:
                return None
            steps = _flip_steps(before, wanted)
            if not steps:
                return None
            n = sum(len(s[1].split(",")) for s in steps)
            return {"steps": steps, "args": steps[0],
                    "label": f"Put back {', '.join(wanted)} for {n} account(s)"}
        return None               # OUs, groups…: only capture_undo can know who changed
    # groups
    if low[:2] == ["update", "group"] and len(a) > 5:
        g, op = a[2], low[3]
        if op in ("add", "create"):
            rest = a[5:] if low[4] in ("member", "manager", "owner") else a[4:]
            return {"args": ["update", "group", g, "remove", *rest],
                    "label": f"Remove them from {g} again"}
        if op in ("remove", "delete"):
            rest = a[5:] if low[4] in ("member", "manager", "owner") else a[4:]
            if not rest:
                return None
            return {"args": ["update", "group", g, "add", "member", *rest],
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
        # on/off user attributes (suspended, changepassword, gal, archived), for one
        # person or many: read the real values first so Undo only reverses what changed
        split = _user_update_split(list(args))
        if split:
            entity, attrs = split
            wanted, other = _flip_pairs(attrs)
            if wanted:
                code, rows, _ = run_csv([*entity, "print", "users", "fields", _FLIP_FIELDS])
                if code != 0:
                    return None
                before, ou_before = {}, {}
                named = None
                if [x.lower() for x in entity[:1]] in (["user"], ["users"]) and \
                        len(entity) == 2:
                    named = {e.strip().lower() for e in entity[1].split(",") if e.strip()}
                for r in rows:
                    e = _col(r, "primaryEmail").lower()
                    if not e or (named is not None and e not in named):
                        continue
                    before[e] = {c: _truthy(_col(r, c)) for c in set(FLIP_COLUMN.values())}
                    ou_before[e] = _col(r, "orgUnitPath")
                moves_ou = [k for k in other if k in ("ou", "org")]
                rest = [k for k in other if k not in ("ou", "org")]
                steps = _flip_steps(before, wanted)
                if moves_ou:
                    by_ou: dict[str, list[str]] = {}
                    for e, o in ou_before.items():
                        if o:
                            by_ou.setdefault(o, []).append(e)
                    for o, es in sorted(by_ou.items()):
                        es = sorted(es)
                        for i in range(0, len(es), UNDO_CHUNK):
                            steps.append(["users", ",".join(es[i:i + UNDO_CHUNK]), "update",
                                          "user", "ou", o])
                if not steps:
                    return {"none": True,
                            "label": "Nothing to undo – the values were already set"}
                n = len(before)
                what = ", ".join([*wanted, *(["ou"] if moves_ou else [])])
                return {"steps": steps, "args": steps[0],
                        "label": f"Put back {what} ({n} account(s) checked)" +
                                 (f" (can't undo: {', '.join(rest)})" if rest else "")}
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
        # cros_sn SN[,SN…] update <attrs>   (not actions – those are handled elsewhere)
        if low[0] == "cros_sn" and len(args) > 3 and low[2] == "update" and \
                "action" not in low:
            serials = [x.strip() for x in args[1].split(",") if x.strip()]
            if not serials:
                return None
            code, rows, _ = run_csv(["cros_sn", args[1], "print", "cros", "fields",
                                     "serialnumber,orgunitpath,annotateduser,"
                                     "annotatedlocation,annotatedassetid,notes"])
            if code != 0 or not rows:
                return None
            by_sn = {_col(r, "serialNumber").upper(): r for r in rows if _col(r, "serialNumber")}
            if len(serials) == 1 and not by_sn:
                by_sn = {serials[0].upper(): rows[0]}     # older output without the serial
            keymap = {"ou": "orgUnitPath", "org": "orgUnitPath", "user": "annotatedUser",
                      "location": "annotatedLocation", "asset": "annotatedAssetId",
                      "assetid": "annotatedAssetId", "tag": "annotatedAssetId",
                      "notes": "notes", "updatenotes": "notes"}
            keys = []
            i = 3
            while i + 1 < len(args):
                if low[i] in keymap:
                    keys.append(low[i])
                    i += 2
                else:
                    i += 1
            if not keys:
                return None
            steps, missing = [], []
            for sn in serials:
                before = by_sn.get(sn.upper())
                if before is None:
                    missing.append(sn)          # never guess another device's values
                    continue
                back = []
                for k in keys:
                    out_key = "notes" if k == "updatenotes" else k
                    back += [out_key, _col(before, keymap[k]) or ("/" if out_key in
                                                                  ("ou", "org") else "")]
                steps.append(["cros_sn", sn, "update", *back])
            if not steps:
                return None
            what = ", ".join(dict.fromkeys("notes" if k == "updatenotes" else k
                                           for k in keys))
            label = (f"Put back the Chromebook's {what}" if len(steps) == 1 else
                     f"Put back {what} on {len(steps)} Chromebooks")
            if missing:
                label += f" (not found: {', '.join(missing[:5])})"
            return {"steps": steps, "args": steps[0], "label": label}
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
