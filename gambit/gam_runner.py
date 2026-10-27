"""Runs GAM commands in the background with QProcess and streams the output."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from typing import Callable, Optional

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from .settings import IS_WINDOWS, settings

SECRET_WORDS = {"password", "newpassword"}
_PW_IN_TEXT = re.compile(r"((?:temporary )?password:\s*)\S+", re.I)
_PW_IN_JSON = re.compile(r'("(?:passphrase|password|psk|wepKey)"\s*:\s*)"[^"]*"', re.I)


def hide_text_passwords(a: str) -> str:
    """Hide “Temporary password: xyz” inside email bodies, and Wi-Fi passphrases in JSON."""
    if '"' in a and ("phrase" in a or "assword" in a or "psk" in a.lower()):
        a = _PW_IN_JSON.sub(r'\1"********"', a)
    return _PW_IN_TEXT.sub(r"\1********", a) if "assword" in a else a


def display_command(args: list[str]) -> str:
    """Human-friendly command line with passwords hidden."""
    shown, hide_next = [], False
    for a in args:
        if hide_next:
            shown.append("********")
            hide_next = False
            continue
        a = hide_text_passwords(a)
        if a == "" or re.search(r"[\s\"']", a):
            a = '"' + a.replace('"', '\\"') + '"'
        shown.append(a)
        if a.lower() in SECRET_WORDS:
            hide_next = True
    return "gam " + " ".join(shown)


def split_command(text: str) -> list[str]:
    """Split a typed command line. A leading 'gam' is optional."""
    parts = shlex.split(text.strip(), posix=True)
    if parts and parts[0].lower() in ("gam", "gam.exe"):
        parts = parts[1:]
    return parts


def gam_environment() -> dict:
    env = dict(os.environ)
    if settings.gam_cfg_dir:
        env["GAMCFGDIR"] = settings.gam_cfg_dir
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def gam_version_text(timeout: int = 20) -> Optional[str]:
    """Return the installed GAM version string (e.g. '7.48.26') or None."""
    gam = settings.gam_path()
    if not gam:
        return None
    flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
    try:
        out = subprocess.run([gam, "version", "simple"], capture_output=True,
                             text=True, timeout=timeout, env=gam_environment(),
                             creationflags=flags)
        text = (out.stdout or "").strip()
        m = re.search(r"\d+\.\d+\.\d+", text)
        if m:
            return m.group(0)
        out = subprocess.run([gam, "version"], capture_output=True, text=True,
                             timeout=timeout, env=gam_environment(),
                             creationflags=flags)
        m = re.search(r"GAM\S*\s+(\d+\.\d+\.\d+)", out.stdout or "")
        return m.group(1) if m else None
    except Exception:
        return None


# ---------------------------------------------------------------- safety ---
DESTRUCTIVE = {"delete", "del", "purge", "wipe_users", "remote_powerwash", "deprovision",
               "deprov", "empty", "clear", "cancel", "datatransfer", "transfer", "wipe",
               "undelete", "turnoff2sv"}


def dry_run_on() -> bool:
    return bool(settings.get("safety/dry_run", False))


def is_change(args: list[str]) -> bool:
    from .activity import is_change as _ic
    return _ic(args)


def helpdesk_on() -> bool:
    return bool(settings.get("helpdesk/on", False))


def blocked_reason(args: list[str]) -> str:
    """Why help-desk mode refuses this command ('' if allowed)."""
    if not helpdesk_on():
        return ""
    low = [a.lower() for a in args]
    for i, a in enumerate(low):
        if a in DESTRUCTIVE:
            return f"'{a}' commands are turned off in help-desk mode."
        if a == "suspended" and i + 1 < len(low) and low[i + 1] in ("on", "true"):
            return "Suspending accounts is turned off in help-desk mode."
        if a == "action" and i + 1 < len(low) and (low[i + 1].startswith("deprovision")
                                                   or low[i + 1] == "disable"):
            return "Disabling or deprovisioning devices is turned off in help-desk mode."
        if a in ("users", "all") and i + 1 < len(low) and low[i + 1] == "users" and a == "all":
            return "Commands for everyone in the domain are turned off in help-desk mode."
    return ""


def gam_prefix() -> list[str]:
    """`select <section>` when the current profile uses a gam.cfg section."""
    sec = (settings.get("profile/section", "") or "").strip()
    return ["select", sec] if sec else []


FRIENDLY = [
    (r"not authorized to access this resource|insufficient permission|403",
     "GAM isn't allowed to do this. Check your admin role, or run Setup wizard → "
     "Allow GAM access."),
    (r"unauthorized_client|domain-wide delegation|client is unauthorized",
     "User-data access isn't set up yet. Run Setup wizard → Allow GAM access."),
    (r"invalid_grant|token has been expired or revoked",
     "GAM's sign-in has expired or was revoked. Run Setup wizard → Sign GAM in."),
    (r"does not exist|not found|notfound|resource not found|entity not found",
     "Google couldn't find that user, group or item. Check the spelling."),
    (r"duplicate|already exists",
     "That already exists, so nothing was changed."),
    (r"invalid argument|expected <|unknown argument|invalid choice",
     "GAM didn't understand part of the command. Check the values you entered."),
    (r"quota|rate limit|429|backend error|503",
     "Google is busy or rate-limiting right now. Wait a minute and try again."),
    (r"service not enabled|has not been used in project|accessnotconfigured",
     "A Google API isn't turned on for GAM's project. Run "
     "'gam update project' from the Command Console."),
]


def friendly_error(text: str) -> str:
    low = (text or "").lower()
    for pattern, msg in FRIENDLY:
        if re.search(pattern, low):
            return msg
    return ""


# ------------------------------------------------------------------ jobs ---
class Job:
    _next_id = 1

    def __init__(self, args, callback, quiet):
        self.id = Job._next_id
        Job._next_id += 1
        self.args, self.callback, self.quiet = args, callback, quiet
        self.display = display_command(args)
        self.status = "queued"          # queued, running, done, failed, cancelled
        self.code: Optional[int] = None
        self.started_at: Optional[float] = None
        self.ended_at: Optional[float] = None
        self.progress: tuple[int, int] = (0, 0)
        self.stdout: list[str] = []
        self.stderr: list[str] = []
        self.proc: Optional[QProcess] = None

    def elapsed(self) -> float:
        import time
        if not self.started_at:
            return 0
        return (self.ended_at or time.time()) - self.started_at


_PROGRESS = re.compile(r"(\d+)\s*(?:of|/)\s*(\d+)")


class GamRunner(QObject):
    """Runs GAM commands as background jobs (several at once) and streams output."""

    started = Signal(str)            # displayed command
    output = Signal(str, bool)       # text, is_error
    finished = Signal(int, str)      # exit code, displayed command
    busy_changed = Signal(bool)
    dry_run = Signal(str)            # a change that dry run held back
    job_added = Signal(object)
    job_changed = Signal(object)

    MAX_PARALLEL = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs: list[Job] = []
        # Hooks set by the main window:
        #   preflight(args) -> bool          ask before big changes
        #   on_submit(job)                   capture "before" state (for undo)
        #   on_record(job)                   write the activity log
        #   guard(args) -> bool              role check (always, even in batches)
        self.guard = None
        self.dry_runs: list[str] = []
        self.practice_ok = None      # practice mode: changes to the test account/OU run
        self.preflight = None
        self.on_submit = None
        self.on_record = None

    @property
    def running(self) -> list[Job]:
        return [j for j in self.jobs if j.status == "running"]

    @property
    def busy(self) -> bool:
        return any(j.status in ("running", "queued") for j in self.jobs)

    def run(self, args: list[str],
            on_done: Optional[Callable[[int, str, str], None]] = None,
            quiet_stdout: bool = False) -> bool:
        """Start `gam <args>` as a job. on_done(exit_code, stdout, stderr).

        quiet_stdout=True keeps large CSV output out of the log panel
        (it is still passed to on_done).
        """
        reason = blocked_reason(args)
        if reason:
            self.output.emit(f"✖ {reason}\n", True)
            return False
        if not settings.gam_path():
            self.output.emit("GAM was not found. Open Settings & Updates to "
                             "install GAM or point GAMbit at gam.exe.\n", True)
            return False
        if dry_run_on() and is_change(args) and not (
                self.practice_ok is not None and self.practice_ok(list(args))):
            shown = display_command(args)
            self.dry_runs.append(shown)
            self.dry_run.emit(shown)
            self.output.emit(f"🧪 Dry run – not run: {shown}\n", False)
            if on_done:
                QTimer.singleShot(0, lambda: on_done(0, "", ""))
            return True
        if self.guard and not self.guard(list(args)):
            self.output.emit("Not run – your GAMbit role doesn't allow this.\n", True)
            return False
        if self.preflight and not self.preflight(list(args)):
            self.output.emit("Cancelled before running.\n", True)
            return False
        job = Job(list(args), on_done, quiet_stdout)
        job.meta = {}
        if self.on_submit:
            try:
                self.on_submit(job)
            except Exception:  # noqa: BLE001
                pass
        self.jobs.append(job)
        self.jobs = self.jobs[-200:]   # keep recent history
        self.job_added.emit(job)
        self._pump()
        return True

    def rerun(self, job: Job):
        self.run(job.args, None, False)

    def cancel(self, job: Job):
        if job.status == "queued":
            job.status = "cancelled"
            self.job_changed.emit(job)
            self._finish(job, -2)
        elif job.status == "running" and job.proc:
            job.status = "cancelled"
            job.proc.kill()

    def stop(self):
        """Stop the most recently started running job."""
        run = self.running
        if run:
            self.cancel(run[-1])

    # --- internals -------------------------------------------------------
    def _pump(self):
        while len(self.running) < self.MAX_PARALLEL:
            nxt = next((j for j in self.jobs if j.status == "queued"), None)
            if not nxt:
                break
            self._start(nxt)
        self.busy_changed.emit(self.busy)

    def _start(self, job: Job):
        import time
        gam = settings.gam_path()
        proc = QProcess(self)
        env = QProcessEnvironment()
        for k, v in gam_environment().items():
            env.insert(k, v)
        proc.setProcessEnvironment(env)
        proc.setWorkingDirectory(os.path.dirname(gam))
        proc.readyReadStandardOutput.connect(lambda j=job: self._read_out(j))
        proc.readyReadStandardError.connect(lambda j=job: self._read_err(j))
        proc.finished.connect(lambda code, _st, j=job: self._done(j, code))
        proc.errorOccurred.connect(lambda err, j=job: self._error(j, err))
        job.proc = proc
        job.status = "running"
        job.started_at = time.time()
        self.started.emit(self._label(job) + job.display)
        self.job_changed.emit(job)
        proc.start(gam, gam_prefix() + job.args)

    def _label(self, job: Job) -> str:
        return f"[#{job.id}] " if len(self.running) > 1 else ""

    @staticmethod
    def _decode(data) -> str:
        return bytes(data).decode("utf-8", errors="replace")

    def _read_out(self, job: Job):
        text = self._decode(job.proc.readAllStandardOutput())
        job.stdout.append(text)
        if not job.quiet:
            self.output.emit(text, False)

    def _read_err(self, job: Job):
        text = self._decode(job.proc.readAllStandardError())
        job.stderr.append(text)
        m = None
        for m in _PROGRESS.finditer(text):
            pass
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < b < 10_000_000 and a <= b:
                job.progress = (a, b)
                self.job_changed.emit(job)
        self.output.emit(text, False)  # GAM writes progress to stderr

    def _error(self, job: Job, err):
        if err == QProcess.FailedToStart:
            self.output.emit("Could not start GAM. Check the GAM folder in "
                             "Settings & Updates.\n", True)
            self._done(job, -1)

    def _done(self, job: Job, code):
        import time
        if job.ended_at:
            return
        job.ended_at = time.time()
        job.code = int(code)
        if job.status != "cancelled":
            job.status = "done" if job.code == 0 else "failed"
        if job.proc:
            job.proc.deleteLater()
            job.proc = None
        err = "".join(job.stderr)
        if job.status == "failed":
            hint = friendly_error(err + "".join(job.stdout))
            if hint:
                self.output.emit(f"💡 {hint}\n", True)
        self.finished.emit(job.code if job.status != "cancelled" else -2,
                           self._label(job) + job.display)
        if self.on_record:
            try:
                self.on_record(job)
            except Exception:  # noqa: BLE001
                pass
        self.job_changed.emit(job)
        self._finish(job, job.code)
        self._pump()

    def _finish(self, job: Job, code):
        if job.callback:
            cb, job.callback = job.callback, None
            cb(int(code), "".join(job.stdout), "".join(job.stderr))
