"""Account timeline: everything that happened to one account, from GAMbit's activity
log, offboarding records, Google's admin audit log and sign-in log."""

from __future__ import annotations

from .directory import run_gam_csv


def _col(r: dict, *names) -> str:
    low = {(k or "").lower(): v for k, v in r.items()}
    for n in names:
        if low.get(n.lower()):
            return low[n.lower()]
    return ""


def _params(r: dict) -> str:
    bits = []
    for k, v in r.items():
        kl = (k or "").lower()
        if v and ("parameters" in kl or kl.endswith(".value")) and "name" not in kl.split(".")[-1]:
            bits.append(v)
    return ", ".join(dict.fromkeys(bits))[:200]


# Extra Google logs read for one person (app, label, how to say what happened)
EXTRA_LOGS = [("useraccounts", "Account security"), ("token", "App access"),
              ("chrome", "Chrome"), ("classroom", "Classroom"), ("groups", "Groups")]
NICE = {"2sv_disable": "turned OFF 2-Step Verification", "2sv_enroll": "turned on 2-Step "
        "Verification", "password_edit": "changed their password", "recovery_email_edit":
        "changed recovery email", "recovery_phone_edit": "changed recovery phone",
        "authorize": "allowed an app", "revoke": "removed an app", "add_user": "added to group",
        "remove_user": "removed from group"}


def extra_args(app: str, email: str, days: int) -> list[str]:
    if app == "groups":
        return ["report", "groups", "user", "all", "filter", f"user_email=={email}",
                "start", f"-{days}d"]
    return ["report", app, "user", email, "start", f"-{days}d"]


def extra_events(app: str, label: str, rows: list[dict], email: str) -> list[dict]:
    out = []
    for r in rows:
        name = _col(r, "events.0.name", "name")
        what = NICE.get(name.lower(), name.replace("_", " ").lower())
        detail = _params(r)
        app_name = _col(r, "app_name")
        if app == "token" and app_name:
            detail = app_name + (f" · {_col(r, 'scope')[:120]}" if _col(r, "scope") else "")
        if app == "groups":
            g = _col(r, "group_email")
            what += f" {g}" if g else ""
        out.append({"time": _col(r, "id.time")[:19].replace("T", " "), "source": label,
                    "who": _col(r, "actor.email") or email, "what": what, "detail": detail})
    return out


def gather(email: str, days: int = 30, google: bool = True,
           extra: bool = True) -> tuple[list[dict], list[str]]:
    from . import activity, offboard
    e = email.lower()
    events, problems = [], []
    for a in activity.load(max(days, 1), team=True):
        if e in (a.get("command", "") or "").lower():
            events.append({"time": a.get("time", ""), "source": "GAMbit",
                           "who": a.get("who", ""),
                           "what": a.get("command", "").replace("gam ", "", 1),
                           "detail": ("worked" if a.get("code") == 0 else "FAILED") +
                           (f" · {a['note']}" if a.get("note") else "") +
                           (" · undone" if a.get("undone") else "")})
    rec = offboard.get(e)
    if rec:
        events.append({"time": rec.get("started", ""), "source": "Offboarding",
                       "who": rec.get("by", ""), "what": "Offboarding started" if
                       rec.get("kind") != "graduate" else "Graduation started",
                       "detail": offboard.describe(rec)})
    if google:
        code, rows, err = run_gam_csv(["report", "admin", "user", "all", "filter",
                                       f"USER_EMAIL=={e}", "start", f"-{days}d"], 300)
        if code == 0:
            for r in rows:
                events.append({"time": _col(r, "id.time")[:19].replace("T", " "),
                               "source": "Admin console", "who": _col(r, "actor.email"),
                               "what": _col(r, "events.0.name", "name").replace("_", " ")
                               .lower(), "detail": _params(r)})
        else:
            problems.append("Admin audit log: " + (err.strip().splitlines() or ["failed"])[-1])
        code, rows, err = run_gam_csv(["report", "login", "user", e, "start", f"-{days}d"], 300)
        if code == 0:
            for r in rows:
                name = _col(r, "events.0.name", "name")
                events.append({"time": _col(r, "id.time")[:19].replace("T", " "),
                               "source": "Sign-in", "who": e,
                               "what": name.replace("_", " ").lower(),
                               "detail": " ".join(x for x in (_col(r, "ipAddress"),
                                                              _params(r)) if x)})
        else:
            problems.append("Sign-in log: " + (err.strip().splitlines() or ["failed"])[-1])
        for app, label in (EXTRA_LOGS if extra else []):
            code, rows, err = run_gam_csv(extra_args(app, e, days), 300)
            if code == 0:
                events += extra_events(app, label, rows, e)
            else:
                problems.append(f"{label} log: " +
                                (err.strip().splitlines() or ["failed"])[-1])
    for ev in events:
        ev["time"] = (ev["time"] or "").replace("T", " ")[:19]
    events.sort(key=lambda x: x["time"], reverse=True)
    return events, problems
