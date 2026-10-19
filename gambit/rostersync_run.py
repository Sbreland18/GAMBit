"""Run a saved roster sync with nobody at the PC (scheduled task).

Safe changes (new accounts, updates, people coming back) are applied straight
away; people leaving become one approval request on the Approvals page (or are
just listed in the email when there's no team folder). A summary email goes to
whoever is set on the schedule.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime
import json
import os

from . import activity, google_io, sis, team
from .directory import load_users, run_gam_text
from .gam_runner import display_command
from .settings import settings

SAFE = ("create", "update", "reactivate")


def all_profiles() -> dict:
    try:
        return json.loads(settings.get("sis/profiles", "{}") or "{}")
    except ValueError:
        return {}


def rules_from_profile(p: dict) -> sis.Rules:
    r = dict(p.get("rules", {}))
    names = {}
    for ln in (p.get("schools", "") or "").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            names[k.strip()] = v.strip()
    fields = {f.name for f in dataclasses.fields(sis.Rules)}
    r = {k: v for k, v in r.items() if k in fields}
    r["school_names"] = names
    r.setdefault("roles", p.get("roles", "student"))
    return sis.Rules(**r)


def load_roster(p: dict) -> sis.Export:
    if p.get("source") == "oneroster":
        from .integrations import sis_api
        path = sis_api.download()
        return sis.load_export(path, "ClassLink / OneRoster")
    if p.get("source") == "sheet":
        path = google_io.download_sheet(p.get("sheet_url", ""), p.get("sheet_tab", ""),
                                        p.get("sheet_user", ""))
    else:
        path = p.get("path", "")
        if not path or not os.path.isfile(path):
            raise RuntimeError(f"The roster file isn't there: {path}")
    return sis.load_export(path, p.get("format", "Other / custom CSV"),
                           p.get("schools_path", ""))


def output_dir() -> str:
    from .scheduler import default_output_dir
    d = os.path.join(settings.get("schedule/out", "") or default_output_dir(), "Roster sync")
    os.makedirs(d, exist_ok=True)
    return d


def run(name: str, log=print) -> int:
    """Returns 0 when everything worked, 1 when something needs a look."""
    p = all_profiles().get(name)
    if not p:
        log(f"No saved roster sync called “{name}”.")
        return 1
    sched = p.get("schedule", {})
    apply_set = set(sched.get("apply", list(SAFE)))
    rules = rules_from_profile(p)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    log(f"Roster sync “{name}” ({rules.kind}) starting.")

    exp = load_roster(p)
    mapping = p.get("mapping") or sis.guess_mapping(exp.headers, p.get("format", ""))
    people = sis.people_from_export(exp, mapping, rules)
    if not people:
        raise RuntimeError("No people found in the roster – check the file and mapping.")
    users = load_users()
    changes = sis.plan(people, users, rules)
    if rules.kind == "staff":
        from . import onboard
        onboard.expand(changes, onboard.options(), rules.domain)
    s = sis.summarize(changes)
    log("Plan: " + ", ".join(f"{k}: {v}" for k, v in s.items()))

    managed = sum(1 for a in users if sis._under(a.get("ou"), rules.managed_root))
    problems = []
    max_new = int(sched.get("max_new", 200) or 200)
    if s.get("create", 0) > max(max_new, managed * 0.25 if managed else max_new):
        problems.append(f"{s['create']} new accounts is far more than usual, so nothing was "
                        "applied. Check the roster export, then run the sync by hand.")
        apply_set = set()
    leaving = [c for c in changes if c.action == "withdraw"]
    if managed and len(leaving) > max(25, managed * 0.1):
        problems.append(f"{len(leaving)} people leaving is a lot – the roster may be "
                        "incomplete. They were NOT sent for approval.")
        leaving_ok = False
    else:
        leaving_ok = True

    applied, failed, created = [], [], []
    for c in changes:
        if c.action not in apply_set or not c.commands:
            continue
        for i, cmd in enumerate(c.commands):
            if settings.get("safety/dry_run", False):
                if i == 0:
                    applied.append((c, "dry run – not run"))
                continue
            code, out = run_gam_text(cmd, timeout=300)
            activity.record(cmd, code, "done" if code == 0 else "failed",
                            activity.infer_undo(cmd, users), settings.get("profile/current", "")
                            or "Default", note=f"scheduled roster sync “{name}”")
            err = out.strip().splitlines()[-1] if out.strip() else str(code)
            if i > 0:                                 # onboarding steps after a create
                from . import onboard
                if code and onboard.is_retryable(cmd):
                    onboard.queue_retry(c.email, cmd, "email signature")
                    log(f"{c.email}: signature will be retried (mailbox not ready yet).")
                elif code:
                    failed.append((c, f"setup step “{display_command(cmd)[:60]}”: {err}"))
                continue
            if code == 0:
                applied.append((c, "done"))
                if c.action == "create":
                    created.append({"name": c.name, "email": c.email, "password": c.password,
                                    "group": cmd[cmd.index("ou") + 1] if "ou" in cmd else ""})
            else:
                failed.append((c, err))
                break                                 # don't run setup steps for a failed create

    request = None
    if leaving and leaving_ok and team.folder():
        offb = rules.withdrawn_action == "offboard"
        cmds = [] if offb else [cmd for c in leaving for cmd in c.commands]
        extra = {"kind": "offboard" if offb else "rostersync", "sync": name}
        if offb:
            extra["people"] = [{"email": c.email, "supervisor": c.supervisor}
                               for c in leaving]
        request = team.new_request(
            cmds, f"Scheduled roster sync “{name}” found {len(leaving)} "
                  f"{'staff' if rules.kind == 'staff' else 'student'}(s) leaving:\n" +
                  "\n".join(f"• {c.email} – {c.details}" for c in leaving[:50]),
            title=f"Roster sync “{name}”: {len(leaving)} leaving" +
                  (" (full offboarding)" if offb else ""), by="scheduled roster sync",
            extra=extra, dedupe=f"rostersync-leaving:{name}")

    # files: full preview + password cards
    out = output_dir()
    preview = os.path.join(out, f"{_slug(name)}_{stamp}_changes.csv")
    with open(preview, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Change", "Account", "Name", "Details", "Result"])
        done_ids = {id(c): r for c, r in applied}
        fail_ids = {id(c): r for c, r in failed}
        for c in changes:
            res = done_ids.get(id(c)) or (f"FAILED: {fail_ids[id(c)]}" if id(c) in fail_ids
                                         else ("sent for approval" if c.action == "withdraw"
                                               and request else "not applied"))
            w.writerow([c.action, c.email, c.name, c.details, res])
    pw_csv = ""
    if created:
        pw_csv = os.path.join(out, f"{_slug(name)}_{stamp}_new_accounts.csv")
        with open(pw_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["Name", "Email", "Temporary password", "Org unit"])
            for c in created:
                w.writerow([c["name"], c["email"], c["password"], c["group"]])
        try:
            from .ui.cards import cards_html
            with open(pw_csv.replace(".csv", "_cards.html"), "w", encoding="utf-8") as fh:
                fh.write(cards_html(created))
        except Exception:  # noqa: BLE001
            pass

    text = [f"Roster sync “{name}” ran on {datetime.datetime.now():%A %d %B %Y at %H:%M}.",
            "", f"Applied: {len(applied)} change(s). Failed: {len(failed)}.",
            f"New accounts: {len(created)}."]
    if leaving:
        if request:
            text.append(f"{len(leaving)} leaving – waiting for approval on GAMbit's "
                        "Approvals page.")
        else:
            text.append(f"{len(leaving)} leaving (not changed):")
            text += [f"  • {c.email} – {c.details}" for c in leaving[:100]]
    if failed:
        text += ["", "These didn't work:"] + [f"  • {c.email}: {e}" for c, e in failed[:50]]
    if problems:
        text += ["", "⚠ " + "\n⚠ ".join(problems)]
    text += ["", f"Full list: {preview}"]
    if created:
        text.append(f"New passwords and printable cards are saved in: {out}")
    body = "\n".join(text)
    log(body)

    to = sched.get("email_to", "")
    if to:
        attach = [preview] + ([pw_csv] if pw_csv and sched.get("email_passwords") else [])
        try:
            _send(to, f"Roster sync “{name}”: {len(applied)} applied, {len(leaving)} "
                      f"leaving{', ' + str(len(failed)) + ' failed' if failed else ''}",
                  body, attach)
        except Exception as exc:  # noqa: BLE001
            log(f"Couldn't email the summary: {exc}")
    try:
        from . import alerts
        if failed or problems:
            alerts.notify(f"GAMbit roster sync “{name}” needs a look: {len(failed)} failed"
                          + (f"; {problems[0]}" if problems else ""))
    except Exception:  # noqa: BLE001
        pass
    settings.set(f"sis/last_scheduled/{name}", datetime.datetime.now().isoformat(
        timespec="minutes"))
    return 1 if (failed or problems) else 0


def _send(to, subject, body, attach):
    args = google_io.email_args(to, subject, body)
    for a in attach:
        args += ["attach", a]
    code, out = run_gam_text(args, timeout=180)
    if code != 0:
        raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else "sendemail failed")


def _slug(s: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_")[:40] or "sync"


__all__ = ["run", "all_profiles", "rules_from_profile", "load_roster", "display_command"]
