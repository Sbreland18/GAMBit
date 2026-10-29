"""Protect GAM's own keys.

GAM's config folder holds oauth2.txt (an admin's sign-in to the whole domain), and
oauth2service.json (a service account that can act as ANY user – read every mailbox and
Drive). Its program folder holds gam.exe, which GAMbit runs with those rights. On Windows,
folders made under C:\\ usually let every signed-in user of the PC read the keys and change
gam.exe. This checks who can, warns when the folders are synced or shared, and locks them
down: the keys readable only by you, Administrators and SYSTEM; the program changeable only
by you and Administrators (others may still run it).

Permissions are read as security IDs (SIDs), not names, so it works on any Windows language.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field

from .settings import settings

IS_WINDOWS = sys.platform == "win32"
LAST_KEY = "gamkeys/last_check"
KEY_FILES = ("oauth2.txt", "oauth2service.json", "client_secrets.json", "gam.cfg")

# well-known SIDs
ADMINS, SYSTEM, CREATOR_OWNER, USERS = "S-1-5-32-544", "S-1-5-18", "S-1-3-0", "S-1-5-32-545"
OK_ALWAYS = {ADMINS, SYSTEM, CREATOR_OWNER}
NAMES = {"S-1-1-0": "Everyone", "S-1-5-11": "Authenticated Users", USERS: "Users",
         "S-1-5-4": "Interactive users", "S-1-5-32-546": "Guests", "S-1-5-7": "Anonymous",
         "S-1-15-2-1": "All application packages"}

# access mask bits
GENERIC_ALL, GENERIC_WRITE, GENERIC_READ, GENERIC_EXECUTE = \
    0x10000000, 0x40000000, 0x80000000, 0x20000000
WRITE_BITS = 0x2 | 0x4 | 0x10 | 0x100 | 0x10000 | 0x40000 | 0x80000 | GENERIC_ALL | \
    GENERIC_WRITE                 # write/append data, write EA/attrs, delete, DAC, owner
READ_BITS = 0x1 | GENERIC_READ | GENERIC_ALL


@dataclass
class Ace:
    sid: str
    name: str
    mask: int
    allow: bool = True
    inherit_only: bool = False

    def reads(self) -> bool:
        return self.allow and bool(self.mask & READ_BITS)

    def writes(self) -> bool:
        return self.allow and bool(self.mask & WRITE_BITS)


@dataclass
class Finding:
    level: str                    # bad / warn / ok
    path: str
    text: str
    fix: str = ""
    who: list = field(default_factory=list)


# ------------------------------------------------------------------ paths ---
def paths() -> dict:
    """{'program': folder, 'config': folder, 'keys': [files that exist]}"""
    from . import gam_setup
    prog = settings.gam_dir or ""
    cfg = gam_setup.effective_cfg_dir()
    keys = []
    for name in KEY_FILES:
        p = os.path.join(cfg, name)
        if os.path.isfile(p):
            keys.append(p)
    for name in (gam_setup.CLIENT_SECRETS, gam_setup.SERVICE_ACCOUNT):
        try:
            p = gam_setup.project_file(name)       # gam.cfg may point somewhere else
        except Exception:  # noqa: BLE001
            p = ""
        if p and os.path.isfile(p) and os.path.abspath(p) not in map(os.path.abspath, keys):
            keys.append(p)
    return {"program": prog if prog and os.path.isdir(prog) else "",
            "config": cfg if cfg and os.path.isdir(cfg) else "", "keys": keys}


# ------------------------------------------------------- reading the ACLs ---
def _ps_quote(p: str) -> str:
    return "'" + str(p).replace("'", "''") + "'"


def _acl_script(targets: list[str]) -> str:
    lst = ",".join(_ps_quote(p) for p in targets)
    return ("$ErrorActionPreference='SilentlyContinue';"
            "'ME|' + [Security.Principal.WindowsIdentity]::GetCurrent().User.Value;"
            f"foreach ($p in @({lst})) {{"
            " $a = Get-Acl -LiteralPath $p;"
            " if (-not $a) { 'ERR|' + $p; continue };"
            " foreach ($e in $a.Access) {"
            "  try { $sid = $e.IdentityReference.Translate("
            "[Security.Principal.SecurityIdentifier]).Value } catch { $sid = "
            "$e.IdentityReference.Value };"
            "  'ACE|' + $p + '|' + $sid + '|' + $e.IdentityReference.Value + '|' + "
            "$e.FileSystemRights.value__ + '|' + $e.AccessControlType + '|' + "
            "[int]$e.PropagationFlags } }")


def parse_acl_output(text: str) -> tuple[str, dict[str, list[Ace]], list[str]]:
    """(my SID, {path: [Ace]}, paths that couldn't be read)."""
    me, acl, errs = "", {}, []
    for ln in (text or "").splitlines():
        parts = ln.strip().split("|")
        if parts[0] == "ME" and len(parts) > 1:
            me = parts[1]
        elif parts[0] == "ERR" and len(parts) > 1:
            errs.append(parts[1])
        elif parts[0] == "ACE" and len(parts) >= 7:
            path, sid, name, mask, typ, prop = parts[1], parts[2], parts[3], parts[4], \
                parts[5], parts[6]
            try:
                m = int(mask) & 0xFFFFFFFF
            except ValueError:
                m = 0
            try:
                io = bool(int(prop) & 2)               # PropagationFlags.InheritOnly
            except ValueError:
                io = False
            acl.setdefault(path, []).append(Ace(sid, name, m, typ.lower() == "allow", io))
    return me, acl, errs


def read_acls(targets: list[str], run=None) -> tuple[str, dict, list]:
    if not targets:
        return "", {}, []
    if run is None:
        import base64
        enc = base64.b64encode(_acl_script(targets).encode("utf-16-le")).decode("ascii")
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                            "-EncodedCommand", enc], capture_output=True, text=True,
                           timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return parse_acl_output(p.stdout)
    return parse_acl_output(run(targets))


def _who(aces: list[Ace], me: str, want: str, extra_ok: set = frozenset()) -> list[str]:
    ok = OK_ALWAYS | {me} | set(extra_ok)
    out = []
    for a in aces:
        if a.sid in ok or not a.allow or a.sid.startswith("S-1-5-80-"):
            continue                       # Windows services such as TrustedInstaller
        if (want == "read" and a.reads()) or (want == "write" and a.writes()):
            label = NAMES.get(a.sid) or a.name or a.sid
            if a.sid.startswith("S-1-5-21-") and a.sid.endswith("-513"):
                label = "Domain Users"
            if label not in out:
                out.append(label)
    return out


# ------------------------------------------------------------------ check ---
def check(run=None, stat=None) -> list[Finding]:
    from .private_files import synced_or_shared
    p = paths()
    out: list[Finding] = []
    if not p["config"] and not p["keys"]:
        return [Finding("ok", "", "GAM isn't set up on this computer yet – nothing to "
                        "protect.")]
    for folder, what in ((p["config"], "GAM's config folder (its keys)"),
                         (p["program"], "GAM's program folder")):
        if folder and synced_or_shared(folder):
            out.append(Finding("bad" if what.startswith("GAM's config") else "warn", folder,
                               f"{what} is in a synced or network folder – copies of it can "
                               "end up on other computers or in the cloud.",
                               "Move it to a local folder (e.g. C:\\GAMConfig) and point "
                               "GAMbit at it in Settings → GAM location."))
    if IS_WINDOWS or run is not None:
        targets = [x for x in [p["config"], p["program"]] + p["keys"] if x]
        gam = os.path.join(p["program"], "gam.exe") if p["program"] else ""
        if gam and os.path.isfile(gam):
            targets.append(gam)
        me, acl, errs = read_acls(targets, run)
        for e in errs:
            out.append(Finding("warn", e, "GAMbit couldn't read who has access to this.",
                               "Check it by hand: right-click → Properties → Security."))
        for path in p["keys"] + ([p["config"]] if p["config"] else []):
            who = _who(acl.get(path, []), me, "read")
            if who:
                out.append(Finding("bad", path, f"{', '.join(who)} can open "
                                   f"{os.path.basename(path) or path} – anyone who signs in "
                                   "to this PC could take over your Google domain with it.",
                                   "Click “Lock down GAM's keys”.", who))
        for path in [x for x in (p["program"], gam) if x]:
            who = _who(acl.get(path, []), me, "write")
            if who:
                out.append(Finding("bad", path, f"{', '.join(who)} can change "
                                   f"{os.path.basename(path) or path} – someone could swap "
                                   "in a fake gam.exe that GAMbit then runs with your admin "
                                   "rights.", "Click “Lock down GAM's keys”.", who))
    else:
        st = stat or os.stat
        for path in p["keys"]:
            try:
                mode = st(path).st_mode
            except OSError:
                continue
            if mode & 0o044:
                out.append(Finding("bad", path, f"Other users of this computer can read "
                                   f"{os.path.basename(path)}.", "chmod 600 it (Lock down "
                                   "does this).", ["group/others"]))
        if p["program"]:
            try:
                if st(p["program"]).st_mode & 0o022:
                    out.append(Finding("bad", p["program"], "Other users can change GAM's "
                                       "program folder.", "Lock down does this.",
                                       ["group/others"]))
            except OSError:
                pass
    if not any(f.level in ("bad", "warn") for f in out):
        out.append(Finding("ok", p["config"], "Only you, Administrators and SYSTEM can open "
                           "GAM's keys, and only you and Administrators can change GAM."))
    return out


def save_last(findings: list[Finding]):
    settings.set(LAST_KEY, json.dumps({
        "at": datetime.datetime.now().isoformat(timespec="minutes"),
        "findings": [{"level": f.level, "path": f.path, "text": f.text, "fix": f.fix}
                     for f in findings]}))


def last() -> dict:
    try:
        d = json.loads(settings.get(LAST_KEY, "") or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def attention() -> list[tuple[str, str]]:
    return [(f["level"], f["text"]) for f in last().get("findings", [])
            if f.get("level") in ("bad", "warn")]


# -------------------------------------------------------------- lock down ---
def lock_script(me_sid: str, program: str, config: str, keys: list[str]) -> str:
    """PowerShell: keys → only me, Administrators, SYSTEM; the program → changeable by me
    and Administrators, runnable by Users. Inheritance from C:\\ is removed."""
    import re
    if not re.fullmatch(r"S-1-5-[0-9-]+", me_sid or ""):
        raise ValueError("Couldn't tell who you are on this computer.")
    q = _ps_quote
    full = f"'*{me_sid}:(OI)(CI)F' '*{ADMINS}:(OI)(CI)F' '*{SYSTEM}:(OI)(CI)F'"
    file_full = f"'*{me_sid}:F' '*{ADMINS}:F' '*{SYSTEM}:F'"
    parts = []
    if program:
        same = config and os.path.normcase(os.path.abspath(program)) == \
            os.path.normcase(os.path.abspath(config))
        users = "" if same else f" '*{USERS}:(OI)(CI)RX'"
        parts.append(f"icacls {q(program)} /inheritance:r /grant:r {full}{users} /T /C /Q")
    if config:
        parts.append(f"icacls {q(config)} /inheritance:r /grant:r {full} /T /C /Q")
    for k in keys:
        parts.append(f"icacls {q(k)} /inheritance:r /grant:r {file_full} /C /Q")
    return "; ".join(parts) + "; exit 0"


def lock_down(elevate: bool = True) -> list[Finding]:
    """Fix the permissions (asks Windows for administrator rights only if needed)."""
    p = paths()
    if not IS_WINDOWS:
        for k in p["keys"]:
            os.chmod(k, 0o600)
        if p["config"]:
            os.chmod(p["config"], 0o700)
        if p["program"]:
            os.chmod(p["program"], os.stat(p["program"]).st_mode & ~0o022)
        res = check()
        save_last(res)
        return res
    me, _acl, _e = read_acls([x for x in (p["config"], p["program"]) if x] or ["."])
    script = lock_script(me, p["program"], p["config"], p["keys"])
    import base64
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
                   capture_output=True, timeout=300, creationflags=flags)
    res = check()
    if elevate and any(f.level == "bad" and f.who for f in res):
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Start-Process powershell -Verb RunAs -Wait -ArgumentList "
                        f"'-NoProfile','-EncodedCommand','{enc}'"],
                       timeout=600, creationflags=flags)
        res = check()
    save_last(res)
    return res


def run(log=print) -> list[Finding]:
    """Daily (and at start): check, remember, alert once when something becomes open."""
    try:
        res = check()
    except Exception as exc:  # noqa: BLE001
        log(f"GAM key check skipped: {exc}")
        return []
    before = {(f.get("path"), f.get("text")) for f in last().get("findings", [])
              if f.get("level") == "bad"}
    save_last(res)
    new = [f for f in res if f.level == "bad" and (f.path, f.text) not in before]
    if new:
        from . import alerts
        import platform
        alerts.notify(f"GAM's keys on {platform.node()} aren't protected:\n" + "\n".join(
            f"• {f.text}" for f in new) + "\nOpen GAMbit → Settings & Updates → GAM location "
            "→ Lock down GAM's keys.", "GAMbit: GAM keys")
    bad = sum(1 for f in res if f.level == "bad")
    log(f"GAM key check: {bad} problem(s).")
    return res
