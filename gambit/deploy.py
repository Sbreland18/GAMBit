"""Rolling GAMbit out to a tech team: deployment files, settings backup/restore and a
shared GAM project.

Deployment file (gambit-deploy.json)
    Put it next to GAMbit-Setup-x.y.z.exe and run
        GAMbit-Setup-x.y.z.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOLAUNCH
    The installer copies it into the program folder; GAMbit applies it on first start
    (and again whenever a newer file appears). It's also picked up from
    %ProgramData%\\GAMbit\\ and from <team folder>\\deploy\\.

Shared GAM project
    One Google Cloud project (client_secrets.json + oauth2service.json) kept in a
    folder only techs can open. Each PC keeps its own GAM config folder whose gam.cfg
    points at those two files, and each person signs GAM in with their *own* admin
    account (`gam oauth create`) – so their admin role in Google limits what they can do
    in the Directory. User-data access (Gmail, Drive…) goes through the shared service
    account, which isn't limited by admin roles.
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import shutil
import sys
import zipfile

from .settings import IS_WINDOWS, settings
from .version import APP_NAME, __version__

GROUPS = {
    "gam": ("GAM location and domain profiles",
            ["gam/dir", "gam/cfgdir", "profiles", "profile/current", "profile/section"]),
    "team": ("Team folder and shared settings",
             ["team/folder", "team/share_settings", "activity/shared_dir",
              "activity/sheet_url", "approvals/email_on", "approvals/emails"]),
    "google": ("Google account for Sheets and email, alerts",
               ["google/admin_email", "gam/admin", "alerts/email", "alerts/webhook",
                "alerts/email_on", "alerts/chat_space", "alerts/chat_user"]),
    "safety": ("Safety and testing (big-change limit, test OU, dry run)",
               ["safety/threshold", "safety/test_ou", "safety/test_user"]),
    "helpdesk": ("Help-desk mode (on, with this PC's PIN)", ["helpdesk/on", "helpdesk/pin"]),
    "updates": ("Updates (channel, check on start)",
                ["update/channel", "updates/on_start", "connection/auto_test"]),
    "reports": ("Reports folder and scheduled-job defaults",
                ["schedule/out", "schedule/email_to", "schedule/alert"]),
    "selfservice": ("Staff request form", None),       # every selfservice/* key
    "roster": ("Saved roster syncs", ["sis/profiles"]),
    "integrations": ("SIS and help-desk connections (addresses only, not the secrets)",
                     ["oneroster/url", "oneroster/client_id", "iiq/site", "iiq/site_id",
                      "iiq/auto_note", "assistant/model", "sis_api/provider",
                      "sis_api/oneroster2/preset", "sis_api/oneroster2/url",
                      "sis_api/oneroster2/token_url", "sis_api/oneroster2/client_id",
                      "sis_api/oneroster2/version", "sis_api/clever/url",
                      "sis_api/powerschool/url", "sis_api/powerschool/client_id",
                      "sis_api/powerschool/staff", "ticketing/provider", "ticketing/auto_note",
                      "ticketing/alert_tickets"] +
                     [f"ticketing/{p}/{k}" for p, ks in (
                         ("zendesk", ("subdomain", "email")),
                         ("freshservice", ("domain",)), ("freshdesk", ("domain",)),
                         ("servicenow", ("instance", "user", "table")),
                         ("jira", ("site", "email", "service_desk", "request_type", "jql")),
                         ("whd", ("url", "user")), ("teamdynamix", ("url", "app_id", "beid")),
                         ("osticket", ("url",))) for k in ks]),
    "onboard": ("New staff setup (groups, license, welcome email)", ["onboard/options"]),
    "customfields": ("Custom user fields (which schema fields to show and export)",
                     ["customfields/config"]),
}
SECRET_HINTS = ("token", "password", "webhook", "pin", "secret", "api_key", "/key")

# What a deployment file from a shared place (the team folder, %ProgramData%) may set
# when it isn't signed by a GAMbit admin this PC trusts – harmless preferences only, and
# only when this PC hasn't set them itself. Anything that decides which program runs, where
# data goes, who approves or what runs by itself needs a signed file (or the file next to
# the installer, which only an administrator can put there).
UNSIGNED_OK = {"updates/on_start", "connection/auto_test", "customfields/config",
               "team/share_settings"}
NEVER = ("access/", "auth/", "seal/", "deploy/", "update/installer_path", "helpdesk/pin")


def allowed_key(k: str) -> bool:
    """Only settings a deployment file is meant to carry – never sign-in trust, keys or
    anything outside the groups below."""
    if any(k == n.rstrip("/") or k.startswith(n) for n in NEVER):
        return False
    for g, (_label, keys) in GROUPS.items():
        if keys is None and k.startswith(f"{g}/"):
            return True
        if keys and k in keys:
            return True
    return False


def is_secret(k: str) -> bool:
    from . import secrets_store
    return secrets_store.is_secret(k) or any(h in k.lower() for h in SECRET_HINTS)


def _keys(group: str) -> list[str]:
    keys = GROUPS[group][1]
    if keys is None:
        return [k for k in settings._s.allKeys() if k.startswith(f"{group}/")]
    return keys


def build_deploy(groups: list[str], overwrite: bool = False, note: str = "",
                 include_secrets: bool = False) -> dict:
    """A deployment file, signed by whoever makes it. Secrets (PIN hash, webhook links,
    tokens) are left out unless include_secrets is True."""
    data = {}
    for g in groups:
        for k in _keys(g):
            if not allowed_key(k) or (is_secret(k) and not include_secrets):
                continue
            v = settings.get(k) if is_secret(k) else settings._s.value(k)
            if v is not None and v != "":
                data[k] = v
    from . import seal, team
    doc = {"gambit_deploy": 1, "created": datetime.datetime.now().isoformat(
        timespec="seconds"), "by": team.me(), "version": __version__,
           "overwrite": overwrite, "note": note, "settings": data}
    try:
        return seal.sign("deploy", doc)
    except Exception:  # noqa: BLE001 – an unsigned file still works next to the installer
        return doc


def write_deploy(path: str, groups: list[str], overwrite: bool = False, note: str = ""):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(build_deploy(groups, overwrite, note), fh, indent=2, default=str)


def candidate_files() -> list[str]:
    out = []
    exe_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                              else os.path.abspath(sys.argv[0] or "."))
    out.append(os.path.join(exe_dir, "gambit-deploy.json"))
    if IS_WINDOWS:
        out.append(os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), APP_NAME,
                                "gambit-deploy.json"))
    from . import team
    if team.folder():
        out += sorted(glob.glob(os.path.join(team.folder(), "deploy", "*.json")))
    return [p for p in out if os.path.isfile(p)]


def apply_file(path: str, force: bool = False) -> list[str]:
    """Apply a deployment file once (or again when it changes). Returns keys changed."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    if data.get("gambit_deploy") != 1:
        return []
    stamp_key = "deploy/applied/" + os.path.normcase(os.path.abspath(path)).replace(
        "\\", "_").replace("/", "_").replace(":", "")
    if not force and settings.get(stamp_key, "") == data.get("created"):
        return []
    trusted = _next_to_program(path) or _signed(data) or _admin_protected(path)
    changed = []
    vals = data.get("settings", {})
    if not isinstance(vals, dict):
        return []
    for k, v in vals.items():
        k = str(k)
        if not allowed_key(k):
            continue
        empty = settings._s.value(k) in (None, "")
        if not trusted and (k not in UNSIGNED_OK or not empty):
            continue                       # an unsigned shared file can't change this
        if (data.get("overwrite") and trusted) or force and trusted or empty:
            settings.set(k, v)
            changed.append(k)
    settings.set(stamp_key, data.get("created", ""))
    return changed


def _next_to_program(path: str) -> bool:
    """The file the installer copied into the program folder."""
    exe_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                              else os.path.abspath(sys.argv[0] or "."))
    return os.path.normcase(os.path.dirname(os.path.abspath(path))) == \
        os.path.normcase(os.path.abspath(exe_dir))


def _admin_protected(path: str) -> bool:
    """%ProgramData%\\GAMbit\\gambit-deploy.json that only administrators can change (the
    server kit sets that up). Ordinary users can create files there by default, so the
    file's permissions are checked – never just its location."""
    if not IS_WINDOWS:
        return False
    pd = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), APP_NAME)
    if os.path.normcase(os.path.dirname(os.path.abspath(path))) != os.path.normcase(pd):
        return False
    import subprocess
    try:
        out = subprocess.run(["icacls", path], capture_output=True, text=True, timeout=20,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except Exception:  # noqa: BLE001
        return False
    ok_sids = ("builtin\\administrators", "nt authority\\system", "administrators",
               "system", "trustedinstaller")
    for ln in out.splitlines()[:-1]:
        low = ln.lower()
        if os.path.normcase(path).lower() in low:
            low = low.split(os.path.normcase(path).lower(), 1)[1]
        low = low.strip()
        if not low or ":" not in low:
            continue
        who, rights = low.rsplit(":", 1)
        writes = any(r in rights for r in ("(f)", "(m)", "(w)", "(wd)", "(ad)", "(wdac)",
                                           "(wo)", "(gw)", "(ga)"))
        if writes and not any(who.strip().endswith(sid) for sid in ok_sids):
            return False
    return bool(out.strip())


def _signed(data: dict) -> bool:
    from . import seal
    try:
        return seal.check_file_data("deploy", data, need="admin") is not None
    except Exception:  # noqa: BLE001
        return False


def apply_on_start() -> list[str]:
    lines = []
    for p in candidate_files():
        changed = apply_file(p)
        if changed:
            lines.append(f"Applied deployment settings from {p} ({len(changed)} setting(s)).")
    return lines


# --------------------------------------------------------- backup/restore ---
def _appdata() -> str:
    from PySide6.QtCore import QStandardPaths
    return QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")


BACKED_UP = ("builder.json", "scheduled", "offboarding", "fleet", "selfservice")
# Scheduled-task scripts are run by Windows: a restored (possibly hand-made) backup must
# never replace them – GAMbit writes them again when a task is set up.
RESTORABLE = ("builder.json", "offboarding", "fleet", "selfservice")


class BackupPasswordNeeded(ValueError):
    pass


def _seal_settings(blob: bytes, password: str = "", dpapi: bool = False) -> bytes:
    """Encrypt a backup's settings: with a password (scrypt + Fernet) to take elsewhere,
    or with Windows DPAPI for this user's own automatic backups."""
    from .auth import crypto
    if dpapi:
        return json.dumps({"mode": "dpapi", "data": crypto.b64(crypto.protect(blob))}).encode()
    import base64
    import hashlib
    import secrets as _s
    from cryptography.fernet import Fernet
    salt = _s.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 15, r=8, p=1,
                         maxmem=128 * 1024 * 1024, dklen=32)
    tok = Fernet(base64.urlsafe_b64encode(key)).encrypt(blob)
    return json.dumps({"mode": "password", "salt": crypto.b64(salt), "n": 2 ** 15,
                       "data": tok.decode("ascii")}).encode()


def _open_settings(raw: bytes, password: str = "") -> bytes:
    from .auth import crypto
    env = json.loads(raw)
    if env.get("mode") == "dpapi":
        return crypto.unprotect(crypto.unb64(env["data"]))
    if not password:
        raise BackupPasswordNeeded("This backup is protected with a password.")
    import base64
    import hashlib
    from cryptography.fernet import Fernet, InvalidToken
    key = hashlib.scrypt(password.encode("utf-8"), salt=crypto.unb64(env["salt"]),
                         n=int(env.get("n", 2 ** 15)), r=8, p=1, maxmem=128 * 1024 * 1024,
                         dklen=32)
    try:
        return Fernet(base64.urlsafe_b64encode(key)).decrypt(env["data"].encode("ascii"))
    except InvalidToken:
        raise BackupPasswordNeeded("That isn't the backup's password.") from None


def backup(path: str, include_secrets: bool = False, password: str = "",
           dpapi: bool = False) -> str:
    """Settings backup. With secrets, the settings part is always encrypted – with a
    password, or (automatic backups before an update) for this Windows user only."""
    if include_secrets and not dpapi and len(password or "") < 10:
        raise ValueError("A backup with secrets needs a password of at least 10 characters.")
    vals = {}
    for k in settings._s.allKeys():
        if k.startswith(("access/", "seal/", "auth/")):
            continue                     # sign-in trust never travels in a backup
        if not include_secrets and is_secret(k):
            continue
        vals[k] = settings.get(k) if is_secret(k) else settings._s.value(k)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        blob = json.dumps(
            {"app": APP_NAME, "version": __version__,
             "created": datetime.datetime.now().isoformat(timespec="seconds"),
             "secrets_included": include_secrets, "settings": vals}, indent=2,
            default=str).encode("utf-8")
        if include_secrets:
            zf.writestr("settings.enc", _seal_settings(blob, password, dpapi))
        else:
            zf.writestr("settings.json", blob)
        base = _appdata()
        for rel in BACKED_UP:
            src = os.path.join(base, rel)
            if os.path.isfile(src):
                zf.write(src, f"appdata/{rel}")
            elif os.path.isdir(src):
                for root, _d, files in os.walk(src):
                    for f in files:
                        full = os.path.join(root, f)
                        zf.write(full, "appdata/" + os.path.relpath(full, base))
    return path


def needs_password(path: str) -> bool:
    try:
        with zipfile.ZipFile(path) as zf:
            if "settings.enc" not in zf.namelist():
                return False
            return json.loads(zf.read("settings.enc")).get("mode") == "password"
    except (OSError, ValueError, zipfile.BadZipFile):
        return False


def restore(path: str, replace: bool = False, password: str = "") -> tuple[int, int]:
    """Returns (settings restored, files restored). Sign-in trust (pinned keys) and keys
    are never restored from a file."""
    n_set = n_files = 0
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if "settings.enc" in names:
            data = json.loads(_open_settings(zf.read("settings.enc"), password))
        else:
            data = json.loads(zf.read("settings.json"))
        for k, v in data.get("settings", {}).items():
            if str(k).startswith(("access/", "seal/", "auth/")):
                continue
            if replace or settings._s.value(k) in (None, ""):
                settings.set(k, v)
                n_set += 1
        base = os.path.realpath(_appdata())
        for name in zf.namelist():
            if not name.startswith("appdata/") or name.endswith("/"):
                continue
            rel = name[len("appdata/"):].replace("\\", "/")
            if rel.split("/", 1)[0] not in RESTORABLE:
                continue                      # never keys, access lists or anything else
            dest = os.path.realpath(os.path.join(base, name[len("appdata/"):]))
            if not dest.startswith(base + os.sep):
                continue                      # never write outside AppData
            if os.path.exists(dest) and not replace:
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(name) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            n_files += 1
    return n_set, n_files


# ---------------------------------------------------------- shared project ---
BROAD = ("everyone", "builtin\\users", "authenticated users", "domain users",
         "nt authority\\interactive", "builtin\\guests")


class FolderTooOpen(RuntimeError):
    def __init__(self, who: list[str]):
        super().__init__("These can open the folder: " + ", ".join(who))
        self.who = who


def broad_readers(folder_path: str) -> list[str]:
    """Large groups that can read `folder_path` (Everyone, Users, Domain Users…)."""
    if IS_WINDOWS:
        import subprocess
        try:
            out = subprocess.run(["icacls", folder_path], capture_output=True, text=True,
                                 timeout=20, creationflags=subprocess.CREATE_NO_WINDOW).stdout
        except Exception:  # noqa: BLE001
            return ["(couldn't check the folder's permissions)"]
        found = []
        for ln in out.splitlines():
            low = ln.lower()
            for b in BROAD:
                if b in low and any(r in ln for r in ("(R)", "(RX)", "(F)", "(M)", "(GR)",
                                                      "(RD)")) and b not in found:
                    found.append(b)
        return found
    import stat
    try:
        mode = os.stat(folder_path).st_mode
    except OSError:
        return []
    return ["everyone"] if mode & stat.S_IROTH else []


def publish_project(shared_dir: str, allow_open: bool = False) -> list[str]:
    """Copy this PC's client_secrets.json + oauth2service.json to the shared folder.

    oauth2service.json can read every mailbox and Drive in the domain, whatever anyone's
    GAMbit role or Google admin role is – so it's refused when broad groups (Everyone,
    Users, Domain Users) can open the folder, unless allow_open is given."""
    from . import gam_setup
    os.makedirs(shared_dir, exist_ok=True)
    who = broad_readers(shared_dir)
    if who and not allow_open:
        raise FolderTooOpen(who)
    done = []
    for name in (gam_setup.CLIENT_SECRETS, gam_setup.SERVICE_ACCOUNT):
        src = gam_setup.project_file(name)
        if not src or not os.path.isfile(src):
            raise RuntimeError(f"This PC doesn't have {name} yet – finish the Setup wizard "
                               "first.")
        shutil.copy2(src, os.path.join(shared_dir, name))
        done.append(name)
    return done


def use_shared_project(shared_dir: str, local_cfg: str, admin_email: str = "") -> list[str]:
    """Point this PC's GAM at the shared project files; the person then signs in."""
    from . import gam_setup
    for name in (gam_setup.CLIENT_SECRETS, gam_setup.SERVICE_ACCOUNT):
        if not os.path.isfile(os.path.join(shared_dir, name)):
            raise RuntimeError(f"{name} isn't in {shared_dir}. On a PC that's already set "
                               "up, use “Share this PC's Google project” first.")
    os.makedirs(local_cfg, exist_ok=True)
    settings.gam_cfg_dir = local_cfg
    from . import profiles
    profiles.sync_current_from_settings()
    notes = gam_setup.prepare_config_dir(admin_email)
    code, out = gam_setup.run_gam(["config", "client_secrets_json",
                                   os.path.join(shared_dir, gam_setup.CLIENT_SECRETS),
                                   "oauth2service_json",
                                   os.path.join(shared_dir, gam_setup.SERVICE_ACCOUNT),
                                   "save"], timeout=60)
    notes.append("GAM now uses the shared Google project." if code == 0 else
                 f"GAM said: {out.strip()[-300:]}")
    settings.set("deploy/shared_project", shared_dir)
    return notes
