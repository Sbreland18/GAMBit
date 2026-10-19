"""Helpers for first-time GAM setup (used by the Setup Wizard).

GAM's own setup has three parts that need a person and a web browser:
  1. gam create project   – makes a Google Cloud project + service account
  2. gam oauth create     – signs GAM in as your admin account
  3. domain-wide delegation – one "Authorize" click in the Admin console
GAMbit does everything else, launches those commands pre-filled in a console
window, and watches the config folder so each step ticks itself off.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

from .gam_runner import gam_environment, gam_prefix
from .settings import IS_WINDOWS, settings

CLIENT_SECRETS = "client_secrets.json"
SERVICE_ACCOUNT = "oauth2service.json"
OAUTH_TOKEN = "oauth2.txt"


def default_cfg_dir() -> str:
    return r"C:\GAMConfig" if IS_WINDOWS else os.path.join(os.path.expanduser("~"), ".gam")


def effective_cfg_dir() -> str:
    """The folder GAM will actually use for its config/credentials."""
    return (settings.gam_cfg_dir or os.environ.get("GAMCFGDIR")
            or os.path.join(os.path.expanduser("~"), ".gam"))


def cfg_file(name: str) -> str:
    return os.path.join(effective_cfg_dir(), name)


def _cfg_value(name: str) -> str:
    """A value from gam.cfg (e.g. a shared client_secrets_json path), or ''."""
    try:
        with open(cfg_file("gam.cfg"), encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                k, sep, v = ln.partition("=")
                if sep and k.strip().lower() == name:
                    return v.strip()
    except OSError:
        pass
    return ""


def project_file(name: str) -> str:
    """Where GAM finds client_secrets.json / oauth2service.json (shared or local)."""
    key = {CLIENT_SECRETS: "client_secrets_json", SERVICE_ACCOUNT: "oauth2service_json"}[name]
    custom = _cfg_value(key)
    if custom and os.path.basename(custom) != custom:
        return os.path.expandvars(os.path.expanduser(custom))
    return cfg_file(custom or name)


def has_project() -> bool:
    return os.path.isfile(project_file(CLIENT_SECRETS)) and \
        os.path.isfile(project_file(SERVICE_ACCOUNT))


def has_oauth() -> bool:
    return os.path.isfile(cfg_file(OAUTH_TOKEN))


def is_fully_set_up() -> bool:
    return bool(settings.gam_path()) and has_project() and has_oauth()


def run_gam(args: list[str], timeout: int = 120) -> tuple[int, str]:
    """Run gam and return (exit_code, combined output). For non-interactive commands."""
    gam = settings.gam_path()
    if not gam:
        return -1, "GAM is not installed."
    flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
    try:
        p = subprocess.run([gam, *gam_prefix(), *args], capture_output=True, text=True, timeout=timeout,
                           env=gam_environment(), creationflags=flags,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "GAM took too long to answer."
    except Exception as exc:  # noqa: BLE001
        return -1, str(exc)


def prepare_config_dir(admin_email: str = "") -> list[str]:
    """Create the config folder and write basic gam.cfg settings."""
    notes = []
    cfg = effective_cfg_dir()
    os.makedirs(cfg, exist_ok=True)
    notes.append(f"Config folder ready: {cfg}")
    code, out = run_gam(["version"], timeout=60)  # first run creates gam.cfg
    notes.append("GAM started successfully." if code == 0 else f"GAM said: {out.strip()[:300]}")
    if "@" in admin_email:
        domain = admin_email.split("@", 1)[1]
        code, out = run_gam(["config", "domain", domain, "save"], timeout=60)
        notes.append(f"Default domain set to {domain}." if code == 0
                     else f"Could not save domain: {out.strip()[:300]}")
    return notes


def set_windows_user_env(gam_dir: str, cfg_dir: str) -> str:
    """Add GAM to the user PATH and set GAMCFGDIR so 'gam' works in any Command Prompt."""
    if not IS_WINDOWS:
        return "Only needed on Windows."
    import ctypes
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            path, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            path, kind = "", winreg.REG_EXPAND_SZ
        parts = [p for p in path.split(";") if p]
        if not any(os.path.normcase(p.rstrip("\\")) == os.path.normcase(gam_dir.rstrip("\\"))
                   for p in parts):
            parts.append(gam_dir)
            winreg.SetValueEx(key, "Path", 0, kind, ";".join(parts))
        if cfg_dir:
            winreg.SetValueEx(key, "GAMCFGDIR", 0, winreg.REG_SZ, cfg_dir)
    # Tell Windows the environment changed (new Command Prompts pick it up)
    HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x1A, 0x2
    ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0,
                                             "Environment", SMTO_ABORTIFHUNG, 3000, None)
    return "GAM added to your PATH and GAMCFGDIR saved (new Command Prompt windows)."


def launch_console(args: list[str], title: str, intro: list[str]) -> str | None:
    """Open a real console window running `gam <args>` with friendly instructions.

    Returns None on success, or a message telling the user what to run by hand.
    """
    gam = settings.gam_path()
    if not gam:
        return "GAM is not installed yet."
    if not IS_WINDOWS:
        return ("Open a terminal and run:\n\n"
                f"GAMCFGDIR=\"{effective_cfg_dir()}\" \"{gam}\" " + " ".join(args))

    def esc(line: str) -> str:  # make text safe for `echo` in a batch file
        return re.sub(r"([&|<>^()])", r"^\1", line.replace("%", "%%")) if line else "."

    def q(a: str) -> str:
        return f'"{a}"' if re.search(r'[\s&|<>^()]', a) else a

    lines = ["@echo off", f"title GAMbit setup - {esc(title)}", "color F0",
             f'cd /d "{os.path.dirname(gam)}"', "echo ============================================================",
             f"echo   {esc(title)}", "echo ============================================================"]
    lines += [f"echo {esc(t)}" if t else "echo." for t in intro]
    lines += ["echo.", "echo ------------------------------------------------------------", "echo.",
              f'"{gam}" ' + " ".join(q(a) for a in args),
              "set GAMEXIT=%ERRORLEVEL%",
              "echo.", "echo ------------------------------------------------------------",
              'if "%GAMEXIT%"=="0" (echo  This step is finished. Close this window and go back to GAMbit.) '
              'else (echo  Something went wrong ^(code %GAMEXIT%^). Read the message above, '
              'then close this window and click Start again in GAMbit.)',
              "pause"]
    fd, bat = tempfile.mkstemp(prefix="gambit_setup_", suffix=".cmd")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(["@chcp 65001 >nul"] + lines) + "\n")
    subprocess.Popen(["cmd.exe", "/C", bat], env=gam_environment(),
                     creationflags=subprocess.CREATE_NEW_CONSOLE)
    return None


def parse_service_account_check(output: str) -> dict:
    """Summarise `gam user X check serviceaccount` output."""
    passes = len(re.findall(r"\bPASS\b", output))
    fails = len(re.findall(r"\bFAIL\b", output))
    url = re.search(r"https://admin\.google\.com/\S+", output)
    return {"pass": passes, "fail": fails,
            "url": url.group(0).rstrip(".,)") if url else
            "https://admin.google.com/ac/owl/domainwidedelegation"}


def open_url(url: str):
    if IS_WINDOWS:
        os.startfile(url)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", url])
    else:
        subprocess.Popen(["xdg-open", url])
