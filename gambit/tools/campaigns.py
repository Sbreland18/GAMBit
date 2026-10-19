"""2-Step Verification rollout campaign for staff: progress by building, reminder emails
with a deadline, escalation to principals after it, and the list of buildings ready to
turn enforcement on (enforcement itself is an Admin console switch per org unit –
Google's API can't change it)."""

from __future__ import annotations

import datetime
import json
from collections import defaultdict

from ..settings import settings

USERS_ARGS = ["print", "users", "fields",
              "primaryemail,name,ou,suspended,isenrolledin2sv,isenforcedin2sv"]
TASK = {"name": "GAMbit 2-Step Verification campaign", "args": ["--task", "campaign2sv"],
        "freq": "weekly", "time": "07:30",
        "what": "Weekly 2-Step Verification reminders and progress", "standard": False}
CONSOLE = "https://admin.google.com/ac/security/2sv"
DEFAULT_MSG = ("Hello,\n\nTo keep student and staff information safe, the district is turning "
               "on 2-Step Verification for Google accounts. Please set it up before {deadline} "
               "– it takes about two minutes:\n\n1. Go to https://myaccount.google.com/"
               "signinoptions/two-step-verification\n2. Follow the steps (a phone app or text "
               "message both work).\n\nAfter {deadline} you won't be able to sign in until "
               "it's set up. Questions? Reply to this email.\n\nThank you!")


def options() -> dict:
    try:
        o = json.loads(settings.get("campaign2sv/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"root": "/Staff", "depth": 1, "deadline": "", "subject":
            "Please set up 2-Step Verification", "message": DEFAULT_MSG, "ready_pct": 90,
            "escalate": True, "principals": "", "history": [], **o}


def save_options(o: dict):
    settings.set("campaign2sv/options", json.dumps(o))


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def _under(ou, root):
    ou, root = (ou or "/").rstrip("/").lower(), (root or "/").rstrip("/").lower()
    return ou == root or ou.startswith(root + "/") or root == ""


def building(ou: str, root: str, depth: int = 1) -> str:
    from .automation import school_of
    return school_of(ou, root, depth) or "(top level)"


def people(rows: list[dict], opts: dict) -> list[dict]:
    out = []
    for r in rows:
        low = _low(r)
        e = low.get("primaryemail", "").lower()
        if not e or low.get("suspended", "").lower() == "true":
            continue
        ou = low.get("orgunitpath", "")
        if not _under(ou, opts.get("root", "/Staff")):
            continue
        out.append({"email": e, "name": low.get("name.fullname", ""), "ou": ou,
                    "building": building(ou, opts.get("root", "/Staff"),
                                         int(opts.get("depth", 1) or 1)),
                    "enrolled": low.get("isenrolledin2sv", "").lower() == "true",
                    "enforced": low.get("isenforcedin2sv", "").lower() == "true"})
    return out


def progress(ppl: list[dict], ready_pct: int = 90) -> list[dict]:
    by = defaultdict(lambda: {"n": 0, "on": 0, "enforced": 0})
    for p in ppl:
        b = by[p["building"]]
        b["n"] += 1
        b["on"] += p["enrolled"]
        b["enforced"] += p["enforced"]
    rows = []
    for name, b in sorted(by.items()):
        pct = round(100 * b["on"] / b["n"]) if b["n"] else 0
        state = "enforced" if b["enforced"] and b["enforced"] >= b["n"] * 0.9 else \
            ("ready to enforce" if pct >= ready_pct else "in progress")
        rows.append({"Building": name, "Staff": b["n"], "Set up": b["on"],
                     "Not yet": b["n"] - b["on"], "%": pct, "Status": state})
    if rows:
        n, on = sum(r["Staff"] for r in rows), sum(r["Set up"] for r in rows)
        rows.append({"Building": "All staff", "Staff": n, "Set up": on, "Not yet": n - on,
                     "%": round(100 * on / n) if n else 0, "Status": ""})
    return rows


def remind_batches(ppl: list[dict], size: int = 50) -> list[list[str]]:
    todo = sorted(p["email"] for p in ppl if not p["enrolled"])
    return [todo[i:i + size] for i in range(0, len(todo), size)]


def reminder_args(batch: list[str], opts: dict, sender: str) -> list[str]:
    deadline = opts.get("deadline") or "the deadline"
    msg = (opts.get("message") or DEFAULT_MSG).replace("{deadline}", deadline)
    args = ["sendemail", "to", sender, "bcc", ",".join(batch)]
    if sender:
        args += ["from", sender]
    return args + ["subject", opts.get("subject") or "Please set up 2-Step Verification",
                   "message", msg]


def escalation_text(building_name: str, missing: list[dict], opts: dict) -> str:
    return (f"2-Step Verification – {building_name}\n\nThe deadline was "
            f"{opts.get('deadline')}. These {len(missing)} staff member(s) still haven't set "
            "it up:\n" + "\n".join(f"  • {p['name'] or p['email']} ({p['email']})"
                                   for p in missing[:100]) +
            "\n\nPlease remind them – it takes about two minutes.")


def run(log=print, run_csv=None, run_text=None, today: datetime.date | None = None) -> list:
    """Weekly task: reminders before the deadline, escalation after it, progress saved."""
    from .. import google_io
    from ..directory import run_gam_csv, run_gam_text
    from ..parent_report import parse_principals
    run_csv = run_csv or (lambda a: run_gam_csv(a, 1800))
    run_text = run_text or run_gam_text
    today = today or datetime.date.today()
    o = options()
    if not o.get("deadline"):
        log("2-Step Verification campaign: set a deadline first (Admin → 2-Step Verification).")
        return []
    code, rows, err = run_csv(USERS_ARGS)
    if code != 0:
        raise RuntimeError((err or "couldn't read users").strip()[-200:])
    ppl = people(rows, o)
    prog = progress(ppl, int(o.get("ready_pct", 90)))
    lines = []
    total = prog[-1] if prog else {"%": 0}
    o["history"] = (o.get("history", []) + [{"date": today.isoformat(), "pct": total["%"]}])[-60:]
    save_options(o)
    try:
        from .. import scorecard
        scorecard.record({"tsv_pct": total["%"]})
    except Exception:  # noqa: BLE001
        pass
    sender = google_io.admin_email()
    past = bool(o.get("deadline")) and today.isoformat() > o["deadline"]
    if not past:
        sent = 0
        for b in remind_batches(ppl):
            c, _out = run_text(reminder_args(b, o, sender), 180)
            sent += len(b) if c == 0 else 0
        lines.append(f"2SV reminders sent to {sent} staff member(s); {total['%']}% set up.")
    elif o.get("escalate"):
        heads = parse_principals(o.get("principals", ""))
        for r in prog[:-1]:
            missing = [p for p in ppl if p["building"] == r["Building"] and not p["enrolled"]]
            to = heads.get(r["Building"].lower())
            if missing and to:
                c, _out = run_text(google_io.email_args(
                    ",".join(to), f"2-Step Verification – {len(missing)} staff still to set up",
                    escalation_text(r["Building"], missing, o)), 180)
                lines.append(f"{r['Building']}: escalated {len(missing)} to "
                             f"{', '.join(to)}" + ("" if c == 0 else " (failed)"))
    ready = [r["Building"] for r in prog[:-1] if r["Status"] == "ready to enforce"]
    if ready:
        lines.append("Ready to turn on enforcement: " + ", ".join(ready) + f" ({CONSOLE})")
    for ln in lines:
        log(ln)
    return lines
