"""Scheduled jobs via Windows Task Scheduler.

Each job is a small .cmd script (one GAM command per line, output saved to a
folder with a timestamp) registered with `schtasks` under the \\GAMbit\\ folder.
"""

from __future__ import annotations

import csv
import io
import os
import re
import subprocess

from PySide6.QtCore import QStandardPaths

from .gam_runner import gam_prefix, split_command
from .settings import IS_WINDOWS, settings

TASK_FOLDER = "GAMbit"


def scripts_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    d = os.path.join(base, "scheduled")
    os.makedirs(d, exist_ok=True)
    return d


def default_output_dir() -> str:
    docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or \
        os.path.expanduser("~")
    return os.path.join(docs, "GAMbit Reports")


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:60] or "job"


def cmd_quote(arg: str) -> str:
    """Quote one argument for a .cmd file (CreateProcess rules + %% for batch)."""
    a = arg.replace("%", "%%")
    if a == "" or re.search(r'[\s"&|<>^(),;=]', a):
        a = '"' + a.replace('"', '\\"') + '"'
    return a


def _sendemail(to: str, subject: str, message: str, attach: list[str], sender: str) -> str:
    """One `gam sendemail` line (arguments already quoted for the .cmd file)."""
    args = gam_prefix() + ["sendemail", "to", to]
    if sender:
        args += ["from", sender]
    args += ["subject", subject, "message", message]
    out = " ".join(cmd_quote(a) for a in args)
    # batch variables written as \x00NAME\x00 survive quoting and expand at run time
    out = re.sub(r"\x00(\w+)\x00", r"%\1%", out)
    for f in attach:       # file names contain %TS% – quote them without escaping %
        out += f' attach "{f}"'
    return out


def build_script(name: str, lines: list[str], out_dir: str, email_to: str = "",
                 email_when: str = "rows", alert_to: str = "", sender: str = "",
                 webhook: str = "") -> str:
    """Write the .cmd for a job and return its path.

    email_to:   send the CSV results to these addresses (comma separated)
    email_when: "always" | "rows" (only when a report has at least one row)
    alert_to:   email this address (with the log) when any step fails
    The script exits with 1 when a step failed, so Task Scheduler's "Last result"
    shows the failure too.
    """
    gam = settings.gam_path() or "gam"
    s = slug(name)
    body = [
        "@echo off",
        "chcp 65001 >nul",
        f"rem GAMbit scheduled job: {name}",
    ]
    if settings.gam_cfg_dir:
        body.append(f'set "GAMCFGDIR={settings.gam_cfg_dir}"')
    body += [
        "for /f %%i in ('powershell -NoProfile -Command \"Get-Date -Format yyyy-MM-dd_HHmm\"') "
        "do set TS=%%i",
        f'if not exist "{out_dir}" mkdir "{out_dir}"',
        f'set "LOG={out_dir}\\{s}_%TS%.log"',
        'echo Started %date% %time% > "%LOG%"',
        "set FAILED=0",
        "set ROWS=0",
    ]
    n = 0
    csvs: list[str] = []
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        n += 1
        args = gam_prefix() + split_command(ln)
        cmd = " ".join(cmd_quote(a) for a in args)
        is_print = any(a in ("print", "report") for a in args[:6])
        csv_path = f"{out_dir}\\{s}_%TS%_{n}.csv"
        target = f'"{csv_path}"' if is_print else '"%LOG%"'
        redirect = f'> {target} 2>> "%LOG%"' if is_print else '>> "%LOG%" 2>&1'
        body.append(f'echo Step {n} >> "%LOG%"')
        body.append(f'"{gam}" {cmd} {redirect}')
        body.append(f'if errorlevel 1 (set FAILED=1& echo Step {n} FAILED >> "%LOG%")')
        if is_print:
            csvs.append(csv_path)
            # count data rows (lines minus the header)
            body.append(f'for /f %%c in (\'type "{csv_path}" ^| find /c /v ""\') '
                        f'do if %%c GTR 1 set /a ROWS+=%%c-1')
    body.append('echo Finished %date% %time% >> "%LOG%"')
    gam_q = f'"{gam}"'
    if email_to and csvs:
        line = gam_q + " " + _sendemail(
            email_to, f"{name} – \x00date\x00",
            f"Attached: the latest results of the GAMbit scheduled job \"{name}\" "
            "(\x00ROWS\x00 rows).", csvs, sender) + ' >> "%LOG%" 2>&1'
        if email_when == "rows":
            body.append(f'if %ROWS% GTR 0 {line}')
        else:
            body.append(line)
    if alert_to:
        body.append('if "%FAILED%"=="1" copy /y "%LOG%" "%LOG%.txt" >nul')
        body.append('if "%FAILED%"=="1" ' + gam_q + " " + _sendemail(
            alert_to, f"GAMbit job failed: {name}",
            f"The scheduled job \"{name}\" had a failed step on \x00COMPUTERNAME\x00. "
            "The log is attached.", ["%LOG%.txt"], sender) + ' >> "%LOG%" 2>&1')
    if webhook:
        from .alerts import powershell_post
        body.append('if "%FAILED%"=="1" ' + powershell_post(
            webhook, f"The scheduled job {name} had a failed step on %COMPUTERNAME%. "
                     "See the log in " + out_dir.replace("%", "%%"),
            "GAMbit job failed"))
    body.append("exit /b %FAILED%")
    path = os.path.join(scripts_dir(), f"{s}.cmd")
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(body) + "\n")
    return path


def app_command(*args: str) -> str:
    """Command line that starts GAMbit itself for a background task."""
    import sys
    if getattr(sys, "frozen", False):
        # GAMbit.exe is a windowed app: `start /wait` makes the .cmd wait for it
        return 'start "" /wait "{}" {}'.format(sys.executable, " ".join(cmd_quote(a)
                                                                    for a in args))
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "main.py")
    return '"{}" "{}" {}'.format(sys.executable, main, " ".join(cmd_quote(a) for a in args))


def build_app_task_script(name: str, args: list[str]) -> str:
    """A .cmd that runs `GAMbit --task …` (roster sync, daily follow-ups, requests)."""
    path = os.path.join(scripts_dir(), f"{slug(name)}.cmd")
    body = ["@echo off", "chcp 65001 >nul", f"rem GAMbit background task: {name}",
            app_command(*args), "exit /b %errorlevel%"]
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(body) + "\n")
    return path


def _run(args: list[str]) -> tuple[int, str]:
    flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
    p = subprocess.run(args, capture_output=True, text=True, creationflags=flags,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def create_task(name: str, script: str, freq: str, time_hhmm: str,
                days: str = "", day_of_month: int = 1) -> str:
    if not IS_WINDOWS:
        raise RuntimeError("Scheduled jobs use Windows Task Scheduler, so they only work "
                           "on Windows.")
    args = ["schtasks", "/Create", "/F", "/TN", f"{TASK_FOLDER}\\{name}",
            "/TR", f'"{script}"', "/ST", time_hhmm]
    if freq == "daily":
        args += ["/SC", "DAILY"]
    elif freq == "weekly":
        args += ["/SC", "WEEKLY", "/D", days or "MON"]
    elif freq == "monthly":
        args += ["/SC", "MONTHLY", "/D", str(day_of_month)]
    elif freq.startswith("every"):          # e.g. "every15" → every 15 minutes
        args += ["/SC", "MINUTE", "/MO", freq[5:] or "15"]
    else:
        args += ["/SC", "ONCE"]
    code, out = _run(args)
    if code != 0:
        raise RuntimeError(out.strip() or "schtasks failed")
    tune_task(name)
    return out.strip()


def tune_script(name: str, wake: bool) -> str:
    """PowerShell that fixes the Task Scheduler defaults schtasks can't set:
    run as soon as possible after a missed start (PC was off or asleep), run on battery,
    don't stop when the laptop is unplugged, and optionally wake the PC for it."""
    n = name.replace("'", "''")
    folder = TASK_FOLDER.replace("'", "''")
    return (f"$t = Get-ScheduledTask -TaskPath '\\{folder}\\' -TaskName '{n}' "
            "-ErrorAction Stop; "
            "$s = $t.Settings; $s.StartWhenAvailable = $true; "
            "$s.DisallowStartIfOnBatteries = $false; $s.StopIfGoingOnBatteries = $false; "
            f"$s.WakeToRun = ${'true' if wake else 'false'}; "
            "Set-ScheduledTask -TaskPath $t.TaskPath -TaskName $t.TaskName -Settings $s "
            "| Out-Null")


def tune_task(name: str) -> bool:
    """Apply tune_script to a GAMbit task. Never fails the caller – the task still runs on
    time without it, it just won't catch up or run on battery."""
    if not IS_WINDOWS:
        return False
    from .settings import settings
    wake = bool(settings.get("tasks/wake", False))
    try:
        code, _out = _run(["powershell", "-NoProfile", "-NonInteractive",
                           "-ExecutionPolicy", "Bypass", "-Command", tune_script(name, wake)])
        return code == 0
    except Exception:  # noqa: BLE001
        return False


DAY_NAMES = {"MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday", "THU": "Thursday",
             "FRI": "Friday", "SAT": "Saturday", "SUN": "Sunday"}


def set_enabled(name: str, on: bool) -> str:
    """Turn a GAMbit task on or off without deleting it."""
    if not IS_WINDOWS:
        raise RuntimeError("Scheduled jobs use Windows Task Scheduler (Windows only).")
    code, out = _run(["schtasks", "/Change", "/TN", f"{TASK_FOLDER}\\{name}",
                      "/ENABLE" if on else "/DISABLE"])
    if code != 0:
        raise RuntimeError(out.strip() or "schtasks failed")
    return out.strip()


def schedule_script(name: str, time_hhmm: str, days: list[str]) -> str:
    n = name.replace("'", "''")
    folder = TASK_FOLDER.replace("'", "''")
    ds = [DAY_NAMES[d] for d in DAY_NAMES if d in (days or [])]
    trig = (f"New-ScheduledTaskTrigger -Daily -At '{time_hhmm}'" if len(ds) in (0, 7) else
            f"New-ScheduledTaskTrigger -Weekly -DaysOfWeek {','.join(ds)} -At '{time_hhmm}'")
    return (f"$tr = {trig}; Set-ScheduledTask -TaskPath '\\{folder}\\' -TaskName '{n}' "
            "-Trigger $tr -ErrorAction Stop | Out-Null")


def set_schedule(name: str, time_hhmm: str, days: list[str]) -> None:
    """Change any GAMbit task's time and days (keeps what it runs)."""
    if not IS_WINDOWS:
        raise RuntimeError("Scheduled jobs use Windows Task Scheduler (Windows only).")
    code, out = _run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                      "Bypass", "-Command", schedule_script(name, time_hhmm, days)])
    if code != 0:
        raise RuntimeError(out.strip() or "Couldn't change the schedule")


def tune_all() -> int:
    """Re-apply the settings to every GAMbit task (after changing “wake the PC”)."""
    return sum(1 for t in list_tasks() if tune_task(t["Name"]))


def list_tasks() -> list[dict]:
    if not IS_WINDOWS:
        return []
    code, out = _run(["schtasks", "/Query", "/FO", "CSV", "/V"])
    if code != 0:
        return []
    rows = []
    for r in csv.DictReader(io.StringIO(out)):
        tn = r.get("TaskName", "")
        if tn.startswith(f"\\{TASK_FOLDER}\\") and r.get("TaskName") != "TaskName":
            rows.append({"Name": tn.split("\\")[-1],
                         "Next run": r.get("Next Run Time", ""),
                         "Last run": r.get("Last Run Time", ""),
                         "Last result": r.get("Last Result", ""),
                         "Status": r.get("Status", ""),
                         "Schedule": r.get("Schedule Type", "")})
    # /V lists one row per trigger; keep the first
    seen, unique = set(), []
    for r in rows:
        if r["Name"] not in seen:
            seen.add(r["Name"])
            unique.append(r)
    return unique


def run_now(name: str) -> str:
    code, out = _run(["schtasks", "/Run", "/TN", f"{TASK_FOLDER}\\{name}"])
    if code != 0:
        raise RuntimeError(out.strip())
    return out.strip()


def delete_task(name: str) -> str:
    code, out = _run(["schtasks", "/Delete", "/F", "/TN", f"{TASK_FOLDER}\\{name}"])
    if code != 0:
        raise RuntimeError(out.strip())
    return out.strip()
