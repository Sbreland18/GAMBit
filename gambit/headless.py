"""Background tasks run by Windows Task Scheduler – no window, nobody at the PC.

    GAMbit.exe --task sync --name "ClassLink students"
    GAMbit.exe --task daily          offboarding follow-ups, activity log → Sheet
    GAMbit.exe --task requests       read the staff request form (self-service)

Optional: --profile "<domain profile name>" to use another GAM configuration.
Everything is written to AppData/GAMbit/logs/tasks.log.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import traceback


def _log_path() -> str:
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    d = os.path.join(base, "logs")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "tasks.log")


class _Log:
    def __init__(self, task: str):
        self.path = _log_path()
        self.task = task

    def __call__(self, text: str):
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = "\n".join(f"{stamp} [{self.task}] {ln}" for ln in str(text).splitlines() or [""])
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
        if sys.stdout:
            try:
                print(line)
            except Exception:  # noqa: BLE001
                pass


def settings_get(key, default=None):
    from .settings import settings
    return settings.get(key, default)


def settings_set(key, value):
    from .settings import settings
    settings.set(key, value)


def use_profile(name: str):
    """Point GAM at another domain profile for this run only (nothing is saved)."""
    from . import profiles
    from .settings import settings
    p = next((x for x in profiles.profiles() if x["name"] == name), None)
    if not p:
        raise RuntimeError(f"No domain profile called “{name}”.")
    settings.override.update({"profile/current": name, "gam/cfgdir": p.get("cfg_dir", ""),
                              "profile/section": p.get("section", "")})


def daily(log) -> int:
    from . import activity, offboard
    code = 0
    try:
        for line in offboard.run_due(log=log):
            log(line)
    except Exception as exc:  # noqa: BLE001
        log(f"Offboarding follow-ups failed: {exc}")
        code = 1
    for line in _onboard_retries(log):
        log(line)
    try:
        for line in offboard.check_transfers(log=log):
            log(line)
    except Exception as exc:  # noqa: BLE001
        log(f"Data transfer check failed: {exc}")
    from .settings import settings
    if settings.get("fleet/loaner_reminders", False):
        try:
            from . import fleet
            fleet.send_reminders(log=log)
        except Exception as exc:  # noqa: BLE001
            log(f"Loaner reminders failed: {exc}")
    if settings.get("collect/enabled", False):
        try:
            from .tools import reconcile
            reconcile.run_collect(log=log)
        except Exception as exc:  # noqa: BLE001
            log(f"Withdrawn-device check failed: {exc}")
            code = 1
    for name, fn in (("Records requests", "records:reminders"),
                     ("Time-limited accounts", "temp_accounts:run"),
                     ("Testing mode", "tools.policy_sets:run_due"),
                     ("Rollout watch", "tools.policy_sets:run_watch"),
                     ("Access review reminder", "access_review:reminder"),
                     ("Guardian follow-up", "guardian_followup:run")) + tuple(
                         x for x, on in ((("Account timing", "lifecycle:run"),
                                          settings.get("lifecycle/on", False)),
                                         (("Storage forecast", "storage_forecast:run"),
                                          settings.get("storage/on", False))) if on):
        try:
            import importlib
            mod, func = fn.split(":")
            getattr(importlib.import_module(f".{mod}", __package__), func)(log=log)
        except Exception as exc:  # noqa: BLE001
            log(f"{name} failed: {exc}")
            code = 1
    try:
        from . import yearend
        yearend.send_reminders(log=log)
    except Exception as exc:  # noqa: BLE001
        log(f"Year-end reminders failed: {exc}")
    if activity.sheet_url():
        try:
            log(f"Activity log copied to the “{activity.push_to_sheet()}” tab.")
        except Exception as exc:  # noqa: BLE001
            log(f"Couldn't copy the activity log: {exc}")
    return code


def _onboard_retries(log) -> list[str]:
    try:
        from . import onboard
        return onboard.run_retries(log=log)
    except Exception as exc:  # noqa: BLE001
        return [f"Onboarding retries failed: {exc}"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="GAMbit", add_help=True)
    ap.add_argument("--task", required=True, choices=["sync", "daily", "requests", "groups", "digest",
                                                   "signatures", "guardians", "settingswatch",
                                                   "devicesync", "devicemove", "deviceassign", "job", "cleanup", "watchdog",
                                                   "schoolreports", "mismatch", "auditreport",
                                                   "teacherlists", "scorecard", "timemachine",
                                                   "questions", "leadersheet", "campaign2sv",
                                                   "classroomsync", "baseline", "goingquiet"])
    ap.add_argument("--name", default="")
    ap.add_argument("--profile", default="")
    args = ap.parse_args(argv)

    from PySide6.QtCore import QCoreApplication
    from .version import APP_NAME
    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    log = _Log(args.task + (f":{args.name}" if args.name else ""))
    from . import support
    support.setup_logging()
    log("Starting")
    try:
        from . import deploy
        for line in deploy.apply_on_start():
            log(line)
    except Exception:  # noqa: BLE001
        pass
    try:
        if args.profile:
            use_profile(args.profile)
        if args.task == "sync":
            from . import rostersync_run
            p = rostersync_run.all_profiles().get(args.name, {})
            prof = p.get("schedule", {}).get("domain_profile", "")
            if prof and not args.profile:
                use_profile(prof)
            return rostersync_run.run(args.name, log=log)
        if args.task == "daily":
            return daily(log)
        if args.task == "groups":
            from . import group_rules
            return 1 if group_rules.run_all(log=log) else 0
        if args.task == "devicesync":
            from .tools import automation
            return automation.run_assign_sync(log=log)
        if args.task == "job":
            from . import saved_jobs
            return saved_jobs.run(args.name, log=log)
        if args.task == "deviceassign":
            from .tools import assigned_users
            return assigned_users.run_assign_task(log=log)
        if args.task == "devicemove":
            from .tools import assigned_users
            return assigned_users.run_move_task(log=log)
        if args.task == "cleanup":
            from .tools import automation
            automation.run_cleanup(log=log)
            return 0
        if args.task == "classroomsync":
            from .tools import classroom_sync
            classroom_sync.run(log=log)
            return 0
        if args.task == "baseline":
            from .tools import baseline
            res, sc = baseline.run()
            fails = [r for r in res if not r["ok"]]
            log(f"Security baseline: {sc}% – {len(fails)} item(s) to fix.")
            prev = settings_get("baseline/last_score")
            settings_set("baseline/last_score", sc)
            if prev not in (None, "") and sc < int(prev):
                from . import alerts
                alerts.notify(f"The security baseline score dropped from {prev}% to {sc}%:\n" +
                              "\n".join(f"• {r['Check']} ({r['Org unit']})" for r in fails[:20]),
                              "GAMbit security baseline")
            return 0
        if args.task == "goingquiet":
            from . import going_quiet
            going_quiet.send(log=log)
            return 0
        if args.task == "timemachine":
            from . import timemachine
            timemachine.run(log=log)
            return 0
        if args.task == "questions":
            from . import saved_questions
            saved_questions.run(log=log)
            return 0
        if args.task == "leadersheet":
            from . import leader_sheet
            leader_sheet.push(log=log)
            return 0
        if args.task == "campaign2sv":
            from .tools import campaigns
            campaigns.run(log=log)
            return 0
        if args.task == "mismatch":
            from .tools import reconcile
            reconcile.run_autofix(log=log)
            return 0
        if args.task == "auditreport":
            from . import audit_report
            return 1 if audit_report.send(log=log) else 0
        if args.task == "teacherlists":
            from . import teacher_lists
            return 1 if teacher_lists.send(log=log) else 0
        if args.task == "scorecard":
            from . import scorecard
            scorecard.snapshot(log=log)
            return 0
        if args.task == "watchdog":
            from .tools import watchdog
            watchdog.run(log=log)
            return 0
        if args.task == "schoolreports":
            from . import school_reports
            return 1 if school_reports.send(log=log) else 0
        if args.task == "settingswatch":
            from .tools import recovery
            return recovery.run_watch(log=log)
        if args.task == "guardians":
            from . import parent_report
            return 1 if parent_report.send(log=log) else 0
        if args.task == "signatures":
            from . import signature
            return 1 if signature.run_rollout(log=log) else 0
        if args.task == "digest":
            from . import digest
            digest.send(log=log)
            return 0
        if args.task == "requests":
            from . import selfservice
            if selfservice.opts().get("sheet_url"):
                try:
                    n = selfservice.process(log=log)
                    log(f"{n} new request(s).")
                except Exception as exc:  # noqa: BLE001
                    log(f"Staff request form failed: {exc}")
            try:
                from . import email_approvals
                for line in email_approvals.process(log=log):
                    log(line)
            except Exception as exc:  # noqa: BLE001
                log(f"Email approvals failed: {exc}")
            for label, mod, fn in (("Run later", "change_queue", "run_due"),
                                   ("Request catalog", "request_catalog", "process")):
                try:
                    import importlib
                    getattr(importlib.import_module(f".{mod}", __package__), fn)(log=log)
                except Exception as exc:  # noqa: BLE001
                    log(f"{label} failed: {exc}")
            try:
                from .tools import ticket_auto
                ticket_auto.process(log=log)
            except Exception as exc:  # noqa: BLE001
                log(f"Help-desk tickets failed: {exc}")
            try:
                from . import approval_policy
                approval_policy.escalate(log=log)
            except Exception as exc:  # noqa: BLE001
                log(f"Escalation failed: {exc}")
            for line in _onboard_retries(log):
                log(line)
            return 0
    except Exception as exc:  # noqa: BLE001
        # RuntimeError = a plain-English "set this up first" message; no traceback needed
        log(f"FAILED: {exc}" + ("" if type(exc) is RuntimeError else
                                f"\n{traceback.format_exc()}"))
        try:
            from . import alerts
            alerts.notify(f"GAMbit background task “{args.task} {args.name}” failed on "
                          f"{os.environ.get('COMPUTERNAME', 'this PC')}: {exc}",
                          "GAMbit task failed")
        except Exception:  # noqa: BLE001
            pass
        return 1
    return 0
