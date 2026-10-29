"""Diagnostics: check that GAM can reach every area GAMbit uses, and say how to fix
anything that's missing. Every check is read-only."""

from __future__ import annotations

from . import tempfiles as _tf
import datetime
import os
import re
from dataclasses import dataclass, field
from typing import Callable

from .directory import run_gam_csv, run_gam_text
from .gam_runner import friendly_error, gam_version_text
from .settings import IS_WINDOWS, settings

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"

FIX_DWD = ("Run the Setup wizard → “Allow GAM access” step (it runs "
           "`gam user <you> update serviceaccount`), then tick the missing scopes and "
           "authorize them in Admin console → Security → API controls → Domain-wide "
           "delegation.")
FIX_ADMIN_SCOPE = ("Re-run the Setup wizard → “Sign GAM in” (`gam oauth create`) and tick "
                   "the {what} scopes. If Google says the API is disabled, run "
                   "`gam enable apis` (or the wizard's “Create Google project” step).")
FIX_ROLE = ("Your admin account may not have the {what} privilege. Check Admin console → "
            "Account → Admin roles.")


@dataclass
class Result:
    key: str
    area: str
    what: str
    status: str = SKIP
    detail: str = ""
    fix: str = ""
    command: str = ""
    extra: list = field(default_factory=list)


def _last(out: str) -> str:
    lines = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _err_fix(out: str, what: str, default_fix: str) -> str:
    hint = friendly_error(out)
    low = (out or "").lower()
    if "has not been used" in low or "is disabled" in low or "accessnotconfigured" in low:
        return ("The Google API for this isn't turned on in GAM's Google Cloud project. "
                "Run `gam enable apis` in the setup terminal, wait a few minutes, then "
                "check again.")
    if "insufficient" in low or "scope" in low:
        return FIX_ADMIN_SCOPE.format(what=what)
    if "not authorized" in low or "403" in low or "permission" in low:
        return FIX_ROLE.format(what=what)
    return hint or default_fix


def _live(key, area, what, args, admin_fix_what, ok_text, csv=False) -> Callable:
    def run(admin: str) -> Result:
        a = [x.replace("{admin}", admin) for x in args]
        r = Result(key, area, what, command="gam " + " ".join(a))
        if "{admin}" in " ".join(args) and "@" not in admin:
            r.status, r.detail = SKIP, "Needs the GAMbit Google account (Settings)."
            r.fix = "Set it in Settings & Updates → Google Sheets and email."
            return r
        if csv:
            code, rows, err = run_gam_csv(a, timeout=120)
            out = err
        else:
            code, out = run_gam_text(a, timeout=120)
            rows = []
        if code == 0:
            r.status, r.detail = OK, ok_text.format(n=len(rows))
        else:
            r.status = FAIL
            r.detail = _last(out) or f"GAM exited with code {code}"
            r.fix = _err_fix(out, admin_fix_what, FIX_ADMIN_SCOPE.format(what=admin_fix_what))
        return r
    return run


# ------------------------------------------------------------------ checks ---
def check_gam(_admin) -> Result:
    r = Result("gam", "GAM", "GAM is installed")
    path = settings.gam_path()
    if not path:
        r.status, r.detail = FAIL, "GAMbit can't find gam.exe."
        r.fix = "Open the Setup wizard to install GAM, or set the GAM folder in Settings."
        return r
    ver = gam_version_text()
    r.status = OK if ver else WARN
    r.detail = f"GAM {ver} at {path}" if ver else f"Found {path} but it didn't report a version."
    return r


def check_connection(_admin) -> Result:
    r = Result("connect", "Directory", "Admin connection (users, groups, org units)",
               command="gam info domain")
    code, out = run_gam_text(["info", "domain"], timeout=60)
    if code == 0:
        dom = next((ln.split(":", 1)[1].strip() for ln in out.splitlines()
                    if ln.lower().strip().startswith("primary domain")), "")
        r.status, r.detail = OK, f"Connected to {dom or 'your domain'}."
    else:
        r.status, r.detail = FAIL, _last(out)
        r.fix = friendly_error(out) or "Run the Setup wizard → “Sign GAM in”."
    return r


SCOPE_AREAS = [
    # (area, what it powers, scope URL fragments that satisfy it)
    ("Gmail", "Mailbox settings (out-of-office, forwarding, filters, delegates)",
     ["gmail.settings.basic", "mail.google.com"]),
    ("Gmail", "Sending report and alert emails (gam sendemail)",
     ["gmail.send", "mail.google.com", "gmail.modify"]),
    ("Gmail", "Searching and cleaning up messages", ["mail.google.com", "gmail.modify"]),
    ("Drive", "Google Drive (files, sharing, shared drives, transfers)", ["auth/drive"]),
    ("Sheets", "Google Sheets (roster import, Google Sheet export, activity log copy)",
     ["spreadsheets", "auth/drive"]),
    ("Calendar", "Calendars (sharing, transfers)", ["auth/calendar"]),
]


def check_service_account(admin: str) -> list[Result]:
    """`gam user <admin> check serviceaccount` – domain-wide delegation scopes."""
    if "@" not in admin:
        return [Result("dwd", "User data", "User-data access (domain-wide delegation)", SKIP,
                       "Needs the GAMbit Google account (Settings).",
                       "Set it in Settings & Updates → Google Sheets and email.")]
    code, out = run_gam_text(["user", admin, "check", "serviceaccount"], timeout=180)
    cmd = f"gam user {admin} check serviceaccount"
    scopes = {}
    for ln in out.splitlines():
        m = re.search(r"(https://\S+)\s.*?\b(PASS|FAIL)\b", ln)
        if m:
            scopes[m.group(1).rstrip("/")] = m.group(2)
    if not scopes:
        r = Result("dwd", "User data", "User-data access (domain-wide delegation)",
                   FAIL if code else WARN, _last(out) or "GAM didn't list any scopes.",
                   FIX_DWD, cmd)
        return [r]
    results = []
    auth_fail = "authentication" in out.lower() and re.search(
        r"authentication.*\bFAIL\b", out, re.I | re.S) and not any(
        v == "PASS" for v in scopes.values())
    for area, what, needles in SCOPE_AREAS:
        hits = {s: v for s, v in scopes.items() if any(n in s for n in needles)}
        r = Result(f"dwd-{area}-{what[:12]}", area, what, command=cmd)
        if auth_fail:
            r.status, r.detail, r.fix = FAIL, "The service account couldn't sign in.", FIX_DWD
        elif not hits:
            r.status = WARN
            r.detail = "None of the scopes this needs were checked."
            r.fix = FIX_DWD
        elif any(v == "PASS" for v in hits.values()):
            r.status = OK
            r.detail = "Allowed: " + ", ".join(s.split("/")[-1] for s, v in hits.items()
                                               if v == "PASS")
        else:
            r.status = FAIL
            r.detail = "Not allowed yet: " + ", ".join(s.split("/")[-1] for s in hits)
            r.fix = FIX_DWD
        results.append(r)
    failed = [s for s, v in scopes.items() if v == "FAIL"]
    if failed:
        results.append(Result("dwd-other", "User data", "Other scopes GAM checked", WARN,
                              f"{len(failed)} scope(s) not authorized: " +
                              ", ".join(s.split("/")[-1] for s in failed[:8]) +
                              ("…" if len(failed) > 8 else ""), FIX_DWD, cmd))
    return results


LIVE = [
    _live("classroom", "Classroom", "Classroom courses and rosters",
          ["print", "courses", "teacher", "{admin}", "fields", "id"], "Classroom",
          "Classroom works.", csv=True),
    _live("cros", "Chromebooks", "Chromebooks (look up, move, disable)",
          ["print", "cros", "query", "id:GAMBITDIAGNOSTIC", "fields", "deviceid"],
          "Chrome OS devices", "Chromebook access works.", csv=True),
    _live("vault", "Vault", "Vault (matters, holds, exports)",
          ["print", "vaultmatters", "matterstate", "open"],
          "Vault", "Vault works ({n} open matters).", csv=True),
    _live("licenses", "Licenses", "Licenses",
          ["print", "licenses", "countsonly", "products", "Google-Apps"], "Licensing",
          "License access works.", csv=True),
    _live("alerts", "Security", "Alert Center",
          ["print", "alerts", "filter", 'createTime >= "2099-01-01T00:00:00Z"'],
          "Alert Center", "Alert Center works.", csv=True),
    _live("reports", "Reports", "Reports (sign-ins, 2-step verification, usage)",
          ["report", "users", "user", "{admin}", "parameters", "accounts:is_2sv_enrolled"],
          "Reports", "Reports work.", csv=True),
    _live("tokens", "Security", "Connected apps (third-party app access)",
          ["user", "{admin}", "print", "tokens"], "user security", "Connected-app access works.",
          csv=True),
]


def check_google_account(admin: str) -> Result:
    r = Result("gacct", "Sheets & email", "GAMbit Google account")
    if "@" in admin:
        r.status, r.detail = OK, f"Using {admin} for Sheets and email."
    else:
        r.status, r.detail = WARN, "Not set."
        r.fix = "Settings & Updates → Google Sheets and email → Detect."
    return r


def check_team_folder(_admin) -> Result:
    from . import team
    r = Result("team", "Team", "Team folder (roles, approvals, shared templates)")
    path = team.folder()
    if not path:
        r.status, r.detail = SKIP, "No team folder – everyone is a Full admin."
        return r
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, f".gambit-write-test-{os.getpid()}")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        r.status, r.detail = OK, f"{path} is reachable and writable."
    except OSError as exc:
        r.status, r.detail = FAIL, f"Can't write to {path}: {exc}"
        r.fix = "Check the drive is mapped / Google Drive for desktop is running."
    return r


def check_scheduler(_admin) -> Result:
    r = Result("sched", "Scheduled jobs", "Windows Task Scheduler")
    if not IS_WINDOWS:
        r.status, r.detail = SKIP, "Only on Windows."
        return r
    from . import scheduler
    try:
        n = len(scheduler.list_tasks())
        r.status, r.detail = OK, f"{n} GAMbit job(s) scheduled."
    except Exception as exc:  # noqa: BLE001
        r.status, r.detail = FAIL, str(exc)
    return r


def check_temp(_admin) -> Result:
    r = Result("temp", "GAMbit", "Temporary folder (downloads, uploads)")
    try:
        d = _tf.folder()
        os.makedirs(d, exist_ok=True)
        r.status, r.detail = OK, d
    except OSError as exc:
        r.status, r.detail = FAIL, str(exc)
    return r


def all_checks():
    """Ordered list of (label, fn(admin) -> Result | list[Result])."""
    return ([("GAM", check_gam), ("Connection", check_connection),
             ("GAMbit Google account", check_google_account),
             ("User data access", check_service_account)] +
            [(f"Live check {i}", fn) for i, fn in enumerate(LIVE)] +
            [("Team folder", check_team_folder), ("Task Scheduler", check_scheduler),
             ("Temp folder", check_temp)])


def run_all(admin: str, progress=None) -> list[Result]:
    out: list[Result] = []
    checks = all_checks()
    for i, (label, fn) in enumerate(checks):
        if progress:
            progress(i, len(checks))
        try:
            res = fn(admin)
        except Exception as exc:  # noqa: BLE001
            res = Result(label, "GAMbit", label, FAIL, str(exc))
        out += res if isinstance(res, list) else [res]
        if label == "GAM" and out[-1].status == FAIL:
            break
    if progress:
        progress(len(checks), len(checks))
    settings.set("diagnostics/last", datetime.datetime.now().isoformat(timespec="minutes"))
    return out


def report_text(results: list[Result]) -> str:
    icon = {OK: "✔", WARN: "⚠", FAIL: "✖", SKIP: "–"}
    lines = [f"GAMbit diagnostics – {datetime.datetime.now():%Y-%m-%d %H:%M}", ""]
    for r in results:
        lines.append(f"{icon[r.status]} [{r.area}] {r.what}: {r.detail}")
        if r.fix and r.status in (WARN, FAIL):
            lines.append(f"    Fix: {r.fix}")
        if r.command:
            lines.append(f"    Checked with: {r.command}")
    return "\n".join(lines)
