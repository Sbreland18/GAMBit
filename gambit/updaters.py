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
    return GamRelease(version=tag.lstrip("v"), asset_name=asset["name"],
                      download_url=asset["browser_download_url"],
                      notes_url=data.get("html_url", ""))


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
        net.download(release.download_url, archive, progress)

        extract_dir = os.path.join(work, "x")
        os.makedirs(extract_dir)
        log("Extracting …")
        if archive.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                _safe_extract_zip(zf, extract_dir)
        else:
            with tarfile.open(archive) as tf:
                try:
                    tf.extractall(extract_dir, filter="data")
                except TypeError:  # Python < 3.12
                    tf.extractall(extract_dir)

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
        return AppUpdate(version, dl, str(data.get("notes", "")))
    return None


def download_app_update(update: AppUpdate, progress: Progress = None) -> str:
    folder = tempfile.mkdtemp(prefix="gambit_update_")
    name = os.path.basename(update.url.split("?")[0]) or "GAMbit-Setup.exe"
    return net.download(update.url, os.path.join(folder, name), progress)


def launch_installer(path: str):
    """Start the Inno Setup installer silently; it relaunches GAMbit when done."""
    if not IS_WINDOWS:
        raise RuntimeError("Automatic install is only supported on Windows.")
    import tempfile
    from .settings import settings
    log = os.path.join(tempfile.gettempdir(), "GAMbit-update.log")
    settings.set("update/in_progress", time.time())   # background tasks wait it out
    subprocess.Popen([path, "/SILENT", "/SP-", "/NOCANCEL", "/CLOSEAPPLICATIONS",
                      "/FORCECLOSEAPPLICATIONS", "/NORESTART", f"/LOG={log}",
                      install_scope_flag()],
                     close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS)


def install_scope_flag(exe: str | None = None) -> str:
    """/CURRENTUSER when GAMbit is installed just for this user (under the user's own
    folders), /ALLUSERS when it's in Program Files – so an update never switches the
    install to the other place."""
    exe = os.path.normcase(os.path.abspath(exe or sys.executable))
    user_roots = [os.environ.get(k, "") for k in ("LOCALAPPDATA", "APPDATA", "USERPROFILE")]
    if any(r and exe.startswith(os.path.normcase(os.path.abspath(r)) + os.sep)
           for r in user_roots):
        return "/CURRENTUSER"
    return "/ALLUSERS"


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
    deploy.backup(path, include_secrets=True)
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


def download_previous(progress: Progress = None) -> str:
    ver = rollback_target()
    if not ver:
        raise RuntimeError("There's no earlier version recorded on this PC.")
    folder = tempfile.mkdtemp(prefix="gambit_rollback_")
    return net.download(installer_url(ver), os.path.join(folder, f"GAMbit-Setup-{ver}.exe"),
                        progress)
