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
SECRET_HINTS = ("token", "password", "webhook", "pin", "secret", "api_key")


def _keys(group: str) -> list[str]:
    keys = GROUPS[group][1]
    if keys is None:
        return [k for k in settings._s.allKeys() if k.startswith(f"{group}/")]
    return keys


def build_deploy(groups: list[str], overwrite: bool = False, note: str = "") -> dict:
    data = {}
    for g in groups:
        for k in _keys(g):
            v = settings._s.value(k)
            if v is not None and v != "":
                data[k] = v
    from . import team
    return {"gambit_deploy": 1, "created": datetime.datetime.now().isoformat(
        timespec="seconds"), "by": team.me(), "version": __version__,
            "overwrite": overwrite, "note": note, "settings": data}


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
    changed = []
    for k, v in data.get("settings", {}).items():
        if data.get("overwrite") or force or settings._s.value(k) in (None, ""):
            settings.set(k, v)
            changed.append(k)
    settings.set(stamp_key, data.get("created", ""))
    return changed


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


def backup(path: str, include_secrets: bool = False) -> str:
    vals = {}
    for k in settings._s.allKeys():
        if not include_secrets and any(h in k.lower() for h in SECRET_HINTS):
            continue
        vals[k] = settings._s.value(k)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("settings.json", json.dumps(
            {"app": APP_NAME, "version": __version__,
             "created": datetime.datetime.now().isoformat(timespec="seconds"),
             "secrets_included": include_secrets, "settings": vals}, indent=2, default=str))
        base = _appdata()
        for rel in ("builder.json", "scheduled", "offboarding", "fleet", "selfservice"):
            src = os.path.join(base, rel)
            if os.path.isfile(src):
                zf.write(src, f"appdata/{rel}")
            elif os.path.isdir(src):
                for root, _d, files in os.walk(src):
                    for f in files:
                        full = os.path.join(root, f)
                        zf.write(full, "appdata/" + os.path.relpath(full, base))
    return path


def restore(path: str, replace: bool = False) -> tuple[int, int]:
    """Returns (settings restored, files restored)."""
    n_set = n_files = 0
    with zipfile.ZipFile(path) as zf:
        data = json.loads(zf.read("settings.json"))
        for k, v in data.get("settings", {}).items():
            if replace or settings._s.value(k) in (None, ""):
                settings.set(k, v)
                n_set += 1
        base = os.path.realpath(_appdata())
        for name in zf.namelist():
            if not name.startswith("appdata/") or name.endswith("/"):
                continue
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
def publish_project(shared_dir: str) -> list[str]:
    """Copy this PC's client_secrets.json + oauth2service.json to the shared folder."""
    from . import gam_setup
    os.makedirs(shared_dir, exist_ok=True)
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
