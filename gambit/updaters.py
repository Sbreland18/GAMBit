"""Update logic for GAM itself and for GAMbit (via latest.json)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from typing import Callable, Optional

from . import net
from .settings import GAM_EXE, IS_WINDOWS
from .version import GAM_LATEST_RELEASE_API, LATEST_BETA_JSON_URL, LATEST_JSON_URL, __version__

Progress = Optional[Callable[[int, int], None]]


# ---------------------------------------------------------------- GAM -----
@dataclass
class GamRelease:
    version: str
    asset_name: str
    download_url: str
    notes_url: str
    sha256: str = ""           # GitHub's published digest of the asset, when it has one


def pick_gam_asset(assets: list[dict], system: str = None,
                   machine: str = None) -> Optional[dict]:
    """Choose the right archive from a GAM release for this computer."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    arm = machine in ("arm64", "aarch64")
    arch = "arm64" if arm else "x86_64"
    names = {a["name"]: a for a in assets}

    def first(pred, newest=True):
        for n in sorted(names, reverse=newest):
            if pred(n):
                return names[n]
        return None

    if system.startswith("win"):
        return first(lambda n: f"windows-{arch}" in n and n.endswith(".zip"))
    if system == "darwin":
        # oldest macOS build runs on the most macOS versions
        return first(lambda n: "macos" in n and n.endswith(f"{arch}.tar.xz"), newest=False)
    # Linux: prefer the 'legacy' build, it runs on the widest range of distros
    return (first(lambda n: f"linux-{arch}-legacy" in n)
            or first(lambda n: f"linux-{arch}" in n and n.endswith(".tar.xz")))


def latest_gam_release() -> GamRelease:
    data = net.get_json(GAM_LATEST_RELEASE_API)
    tag = data.get("tag_name", "")
    asset = pick_gam_asset(data.get("assets", []))
    if not asset:
        raise RuntimeError("No GAM download was found for this computer.")
    url = str(asset.get("browser_download_url", ""))
    from urllib.parse import urlparse
    from .version import GAM_REPO
    u = urlparse(url)
    if u.scheme != "https" or u.hostname != "github.com" or \
            not u.path.lower().startswith(f"/{GAM_REPO.lower()}/releases/download/"):
        raise RuntimeError("The GAM download link isn't from the GAM-team GitHub releases.")
    digest = str(asset.get("digest") or "")
    return GamRelease(version=tag.lstrip("v"), asset_name=os.path.basename(asset["name"]),
                      download_url=url, notes_url=data.get("html_url", ""),
                      sha256=digest.split(":", 1)[1] if digest.startswith("sha256:") else "")


def install_gam(release: GamRelease, target_dir: str,
                progress: Progress = None, log=print) -> str:
    """Download the GAM archive and copy its contents into target_dir.

    Existing config (oauth2.txt, client_secrets.json, gam.cfg …) is untouched
    because GAM keeps that in GAMCFGDIR / ~/.gam, and we only overwrite the
    files that ship in the archive.
    """
    work = tempfile.mkdtemp(prefix="gambit_gam_")
    try:
        archive = os.path.join(work, release.asset_name)
        log(f"Downloading {release.asset_name} …")
        net.download(release.download_url, archive, progress, sha256=release.sha256)
        if release.sha256:
            log("Download checked against GitHub's published SHA-256.")

        extract_dir = os.path.join(work, "x")
        os.makedirs(extract_dir)
        log("Extracting …")
        if archive.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                _safe_extract_zip(zf, extract_dir)
        else:
            with tarfile.open(archive) as tf:
                _safe_extract_tar(tf, extract_dir)

        src = _find_gam_folder(extract_dir)
        if not src:
            raise RuntimeError("The download did not contain the GAM program.")

        os.makedirs(target_dir, exist_ok=True)
        cleanup_old_files(target_dir)
        running = gam_processes(target_dir)
        if running:
            log("GAM is running right now (" + ", ".join(running[:5]) + ") – files in use "
                "are swapped out safely; the new GAM is used from the next command.")
        log(f"Installing into {target_dir} …")
        moved = copy_tree_replacing(src, target_dir)
        if moved:
            log(f"{len(moved)} file(s) were in use and were renamed to *.old-… – they're "
                "removed the next time GAM is updated.")
        exe = os.path.join(target_dir, GAM_EXE)
        if not IS_WINDOWS and os.path.exists(exe):
            os.chmod(exe, 0o755)
        log(f"GAM {release.version} installed.")
        return exe
    finally:
        shutil.rmtree(work, ignore_errors=True)


OLD_TAG = ".old-"


def _replace_file(src: str, dst: str, tries: int = 4, wait: float = 1.5,
                  sleep=None) -> bool:
    """Copy src over dst. If dst is locked (a running gam.exe, a loaded DLL, an antivirus
    scan), wait a little and retry; then rename the locked file out of the way – Windows
    allows renaming a file that's in use – and copy the new one in. True = renamed."""
    import time
    sleep = sleep or time.sleep
    for i in range(tries):
        try:
            shutil.copy2(src, dst)
            return False
        except PermissionError:
            pass
        except OSError as exc:
            if getattr(exc, "winerror", None) not in (5, 32, 33) and exc.errno not in (13, 16,
                                                                                      26):
                raise
        if i < tries - 1:
            sleep(wait)
    old = f"{dst}{OLD_TAG}{int(__import__('time').time())}"
    try:
        os.replace(dst, old)
    except OSError as exc:
        raise RuntimeError(f"{os.path.basename(dst)} is in use by another program and can't "
                           "be replaced. Close anything running GAM (a GAMbit background "
                           "task, a Command Prompt or PowerShell window, or another GAMbit) "
                           f"and try again. ({exc})") from None
    shutil.copy2(src, dst)
    return True


def copy_tree_replacing(src: str, dst: str, sleep=None) -> list[str]:
    """Copy every file from src into dst, replacing locked files safely. → renamed files."""
    moved = []
    for dirpath, _dirs, files in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        target = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target, exist_ok=True)
        for f in files:
            d = os.path.join(target, f)
            if _replace_file(os.path.join(dirpath, f), d, sleep=sleep):
                moved.append(d)
    return moved


def cleanup_old_files(target_dir: str) -> int:
    """Remove files left by an earlier update (now that nothing uses them)."""
    n = 0
    for dirpath, _dirs, files in os.walk(target_dir):
        for f in files:
            if OLD_TAG in f:
                try:
                    os.remove(os.path.join(dirpath, f))
                    n += 1
                except OSError:
                    pass
    return n


def gam_processes(target_dir: str) -> list[str]:
    """Running gam.exe processes from this folder (Windows), e.g. ['PID 4120']."""
    if not IS_WINDOWS:
        return []
    import subprocess
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='gam.exe'\" | "
             "ForEach-Object { \"$($_.ProcessId)|$($_.ExecutablePath)\" }"],
            capture_output=True, text=True, timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except Exception:  # noqa: BLE001
        return []
    tdir = os.path.normcase(os.path.realpath(target_dir))
    found = []
    for ln in out.splitlines():
        pid, _, path = ln.partition("|")
        if path and os.path.normcase(os.path.dirname(os.path.realpath(path))).startswith(tdir):
            found.append(f"PID {pid.strip()}")
    return found


def _safe_extract_zip(zf: zipfile.ZipFile, dest: str):
    root = os.path.realpath(dest)
    for member in zf.namelist():
        path = os.path.realpath(os.path.join(dest, member))
        if os.path.commonpath([root, path]) != root:
            raise RuntimeError(f"Unsafe path in archive: {member}")
    zf.extractall(dest)


def _safe_extract_tar(tf: tarfile.TarFile, dest: str):
    """Only plain files and folders inside dest – no absolute paths, no '..', no links or
    device files (Python's 'data' filter when there is one, the same checks otherwise)."""
    root = os.path.realpath(dest)
    for m in tf.getmembers():
        path = os.path.realpath(os.path.join(dest, m.name))
        if os.path.commonpath([root, path]) != root or os.path.isabs(m.name):
            raise RuntimeError(f"Unsafe path in archive: {m.name}")
        if not (m.isfile() or m.isdir()):
            raise RuntimeError(f"Unexpected link or device in archive: {m.name}")
    try:
        tf.extractall(dest, filter="data")
    except TypeError:  # Python < 3.12: every member was checked above
        tf.extractall(dest)


def _find_gam_folder(root: str) -> Optional[str]:
    for dirpath, _dirs, files in os.walk(root):
        if GAM_EXE in files:
            return dirpath
    return None


# ------------------------------------------------------------- GAMbit -----
@dataclass
class AppUpdate:
    version: str
    url: str
    notes: str
    sha256: str = ""


class UpdateUnverified(RuntimeError):
    pass


def update_channel() -> str:
    from .settings import settings
    return "beta" if (settings.get("update/channel", "stable") or "") == "beta" else "stable"


def check_app_update(url: str = "") -> Optional[AppUpdate]:
    """Stable channel: latest.json. Beta channel: whichever of latest.json and
    latest-beta.json is newer (so testers also get stable releases)."""
    if url:
        return _check_one(url)
    best = _check_one(LATEST_JSON_URL)
    if update_channel() == "beta":
        try:
            beta = _check_one(LATEST_BETA_JSON_URL)
        except Exception:  # noqa: BLE001 – no beta file published yet
            beta = None
        if beta and (not best or net.is_newer(beta.version, best.version)):
            beta.notes = "(Beta) " + beta.notes
            best = beta
    return best


def _check_one(url: str) -> Optional[AppUpdate]:
    """Read latest.json and return an AppUpdate if it is newer than us.

    latest.json format:
        {"version": "1.2.0",
         "url": "https://github.com/.../GAMbit-Setup-1.2.0.exe",
         "notes": "What changed"}
    """
    data = net.get_json(url)
    version = str(data.get("version", "")).strip()
    dl = str(data.get("url", "")).strip()
    if not version or not dl:
        raise RuntimeError("latest.json is missing 'version' or 'url'.")
    if net.is_newer(version, __version__):
        from . import release_sign
        why = release_sign.problem(data)
        if why:
            raise UpdateUnverified(f"GAMbit {version} was announced, but it can't be "
                                   f"verified ({why}), so it isn't offered. If you expected "
                                   "this version, download it from GitHub yourself.")
        return AppUpdate(version, dl, str(data.get("notes", "")),
                         str(data.get("sha256", "")).lower())
    return None


def _safe_name(url: str, fallback: str) -> str:
    import re
    name = os.path.basename(url.split("?")[0]) or fallback
    return name if re.fullmatch(r"[\w.-]{1,120}\.exe", name) else fallback


def verify_installer(path: str) -> str:
    """'' if the installer's Windows signature is from a trusted publisher (when this copy
    knows which publishers to expect), else why not."""
    try:
        from .release_keys import TRUSTED_SIGNER_THUMBPRINTS as want
    except Exception:  # noqa: BLE001
        want = []
    want = {t.replace(" ", "").upper() for t in want if t}
    if not want or not IS_WINDOWS:
        return ""
    ps = ("$s = Get-AuthenticodeSignature -LiteralPath $env:GB_FILE; "
          "\"$($s.Status)|$($s.SignerCertificate.Thumbprint)\"")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                             capture_output=True, text=True, timeout=60,
                             env={**os.environ, "GB_FILE": path},
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"couldn't check its signature ({exc})"
    status, _, thumb = out.partition("|")
    if status != "Valid":
        return f"its Windows signature isn't valid ({status or 'unsigned'})"
    if thumb.strip().upper() not in want:
        return "it's signed by someone other than the GAMbit publisher"
    return ""


def download_app_update(update: AppUpdate, progress: Progress = None) -> str:
    """Download and check the installer: GitHub only, SHA-256 from the signed release
    information, and the Windows publisher signature (when known)."""
    from . import release_sign
    if not release_sign.url_ok(update.url) or not update.sha256:
        raise UpdateUnverified("This update can't be verified, so it isn't installed.")
    folder = tempfile.mkdtemp(prefix="gambit_update_")
    path = net.download(update.url, os.path.join(folder, _safe_name(update.url,
                                                                    "GAMbit-Setup.exe")),
                        progress, sha256=update.sha256)
    why = verify_installer(path)
    if why:
        os.remove(path)
        raise UpdateUnverified(f"The downloaded installer was deleted: {why}.")
    return path


APP_ID = "{6F1C2B7E-9A4D-4E1B-8C3F-2D5A7B9E0C41}"       # installer/GAMbit.iss AppId
UPDATE_LOG_NAME = "GAMbit-update.log"


def update_log_path() -> str:
    return os.path.join(tempfile.gettempdir(), UPDATE_LOG_NAME)


def launch_installer(path: str, silent: bool = True):
    """Start the Inno Setup installer; it relaunches GAMbit when done.

    silent=False shows the installer's own window (used to finish an update that didn't
    complete, so any message it has is visible)."""
    if not IS_WINDOWS:
        raise RuntimeError("Automatic install is only supported on Windows.")
    from .settings import settings
    settings.set("update/in_progress", time.time())   # background tasks wait it out
    settings.set("update/installer_path", path)
    settings.set("update/from_version", __version__)
    args = [path, "/SP-", "/NORESTART", f"/LOG={update_log_path()}"]
    if silent:
        args += ["/SILENT", "/NOCANCEL", "/CLOSEAPPLICATIONS", "/FORCECLOSEAPPLICATIONS"]
    scope = install_scope_flag()
    if scope:
        args.append(scope)
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP |
             getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0))
    try:
        subprocess.Popen(args, close_fds=True, creationflags=flags)
    except OSError:          # breakaway isn't allowed in some job objects
        subprocess.Popen(args, close_fds=True,
                         creationflags=subprocess.DETACHED_PROCESS |
                         subprocess.CREATE_NEW_PROCESS_GROUP)


def install_scope_flag() -> str:
    """/CURRENTUSER or /ALLUSERS from where Windows has GAMbit registered (the installer's
    own uninstall entry), so an update never switches “just me” to “everyone”. Empty when
    it can't tell – then the installer uses the previous install's mode by itself."""
    try:
        import winreg
    except ImportError:
        return ""
    key = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1"
    for hive, flag in ((winreg.HKEY_CURRENT_USER, "/CURRENTUSER"),
                       (winreg.HKEY_LOCAL_MACHINE, "/ALLUSERS")):
        for view in (0, getattr(winreg, "KEY_WOW64_64KEY", 0),
                     getattr(winreg, "KEY_WOW64_32KEY", 0)):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view):
                    return flag
            except OSError:
                continue
    return ""


def unfinished_update() -> dict | None:
    """After a restart: an update was started but this is still the old version."""
    from .settings import settings
    started = float(settings.get("update/in_progress", 0) or 0)
    if not started:
        return None
    if (settings.get("update/from_version", "") or "") != __version__:
        return None                       # we're a different version: it worked
    return {"started": started, "installer": settings.get("update/installer_path", "") or "",
            "log": update_log_path()}


def update_log_tail(lines: int = 25) -> str:
    try:
        with open(update_log_path(), encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readlines()[-lines:])
    except OSError:
        return ""


def update_in_progress(window: float = 15 * 60) -> bool:
    from .settings import settings
    try:
        t = float(settings.get("update/in_progress", 0) or 0)
    except (TypeError, ValueError):
        t = 0
    return bool(t) and time.time() - t < window


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


# ------------------------------------------------------------ safer updates ---
def installer_url(version: str) -> str:
    from .version import GITHUB_REPO
    return (f"https://github.com/{GITHUB_REPO}/releases/download/v{version}/"
            f"GAMbit-Setup-{version}.exe")


def backups_dir() -> str:
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    d = os.path.join(base, "backups")
    os.makedirs(d, exist_ok=True)
    return d


def prepare_for_update(new_version: str = "") -> str:
    """Before installing: back up settings and remember which version to go back to."""
    import datetime
    from . import deploy
    from .settings import settings
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    path = os.path.join(backups_dir(), f"before-{new_version or 'update'}-from-{__version__}-"
                                       f"{stamp}.zip")
    deploy.backup(path, include_secrets=True, dpapi=True)   # this user only
    settings.set("update/previous_version", __version__)
    settings.set("update/previous_backup", path)
    # keep the 10 newest backups
    files = sorted((os.path.join(backups_dir(), f) for f in os.listdir(backups_dir())
                    if f.startswith("before-")), key=os.path.getmtime, reverse=True)
    for old in files[10:]:
        try:
            os.remove(old)
        except OSError:
            pass
    return path


def rollback_target() -> str:
    from .settings import settings
    prev = (settings.get("update/previous_version", "") or "").strip()
    return prev if prev and prev != __version__ else ""


def release_info_url(version: str) -> str:
    from .version import GITHUB_REPO
    return f"https://github.com/{GITHUB_REPO}/releases/download/v{version}/release.json"


def download_previous(progress: Progress = None) -> str:
    """The earlier version's installer – checked against that release's signed
    release.json exactly like an update."""
    import re
    from . import release_sign
    ver = rollback_target()
    if not ver or not re.fullmatch(r"[0-9A-Za-z.\-]{1,30}", ver):
        raise RuntimeError("There's no earlier version recorded on this PC.")
    try:
        meta = net.get_json(release_info_url(ver))
    except Exception as exc:  # noqa: BLE001
        raise UpdateUnverified(f"GAMbit {ver} has no signed release information to check "
                               f"the download against ({exc}). Download it from GitHub "
                               "yourself if you need it.") from None
    why = release_sign.problem(meta) or ("" if str(meta.get("version")) == ver else
                                         "it's for a different version")
    if why:
        raise UpdateUnverified(f"GAMbit {ver} can't be verified ({why}).")
    folder = tempfile.mkdtemp(prefix="gambit_rollback_")
    path = net.download(meta["url"], os.path.join(folder, f"GAMbit-Setup-{ver}.exe"),
                        progress, sha256=str(meta["sha256"]))
    why = verify_installer(path)
    if why:
        os.remove(path)
        raise UpdateUnverified(f"The downloaded installer was deleted: {why}.")
    return path
