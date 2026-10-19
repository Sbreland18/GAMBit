"""Student flags: every signal GAMbit has about one student on one card – going quiet
(sign-ins, missing work, Chromebook use), shared-password signs, repeat damage, guardian
status, connected apps, recent Meet time, AI use and open unusual-activity findings."""

from __future__ import annotations

import datetime
from collections import Counter


def commands(email: str, days: int = 14) -> dict[str, list[str]]:
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    return {
        "missing": ["print", "course-submissions", "student", email, "states", "active",
                    "submissionstates", "new,created", "late"],
        "devices": ["print", "cros", "query", f"recent_user:{email}", "fields",
                    "serialnumber,lastsync,annotateduser,orgunitpath"],
        "logins": ["report", "login", "user", email, "start", start, "events",
                   "login_success"],
        "apps": ["user", email, "print", "tokens"],
        "meet": ["report", "meet", "user", email, "start", start, "events", "call_ended"],
        "ai": ["report", "gemini", "user", email, "start", start],
        "guardians": ["user", email, "print", "guardians", "all"],
    }


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def analyze(email: str, data: dict, user: dict | None = None, repairs=None, findings=None,
            approved=None, today: datetime.date | None = None) -> list[dict]:
    """data: {key: rows or None} from commands(); → [{Signal, Detail, Level}]"""
    from .tools.app_vetting import RISKY, _status
    import re
    today = today or datetime.date.today()
    e = email.lower()
    out = []

    def add(sig, detail, level="info"):
        out.append({"Signal": sig, "Detail": detail, "Level": level})
    last = (user or {}).get("last_login", "")
    if user is not None:
        if not last or last.lower().startswith(("never", "1970")):
            add("Sign-ins", "has never signed in", "high")
        else:
            try:
                d = datetime.date.fromisoformat(last[:10])
                gap = (today - d).days
                add("Sign-ins", f"last sign-in {d:%b %d} ({gap} days ago)",
                    "high" if gap > 14 else "medium" if gap > 7 else "ok")
            except ValueError:
                pass
    miss = data.get("missing")
    if miss is not None:
        n = len(miss)
        add("Missing work", f"{n} late/missing assignment(s)",
            "high" if n >= 5 else "medium" if n else "ok")
    devs = data.get("devices")
    if devs is not None:
        sns = [_low(r).get("serialnumber", "") for r in devs]
        syncs = sorted((_low(r).get("lastsync", "")[:10] for r in devs), reverse=True)
        mine = [_low(r) for r in devs if _low(r).get("annotateduser", "").lower() == e]
        detail = f"used {len(sns)} Chromebook(s) recently"
        if mine:
            detail += f"; assigned {mine[0].get('serialnumber', '')}"
        if syncs and syncs[0]:
            detail += f"; last check-in {syncs[0]}"
        add("Chromebooks", detail, "medium" if len(sns) >= 4 else "ok")
    logs = data.get("logins")
    if logs is not None:
        ips = {_low(r).get("ipaddress", "") for r in logs} - {""}
        add("Sign-in places", f"{len(ips)} different network(s) in 2 weeks",
            "medium" if len(ips) >= 6 else "ok")
    apps = data.get("apps")
    if apps is not None:
        names, risky = set(), []
        for r in apps:
            low = _low(r)
            nm = low.get("displaytext", "") or low.get("clientid", "")
            names.add(nm)
            sc = low.get("scopes", "") + " "
            if any(re.search(p, sc) for p, _l in RISKY) and \
                    _status(nm, low.get("clientid", ""), approved or []) != "approved":
                risky.append(nm)
        add("Connected apps", f"{len(names)} app(s)" + (f"; not approved with risky access: "
                                                         f"{', '.join(sorted(set(risky)))}"
                                                         if risky else ""),
            "high" if risky else "ok")
    meet = data.get("meet")
    if meet is not None:
        mins = 0.0
        for r in meet:
            try:
                mins += float(_low(r).get("duration_seconds") or 0) / 60
            except ValueError:
                pass
        add("Meet", f"{round(mins)} minutes in Meet over 2 weeks")
    ai = data.get("ai")
    if ai is not None:
        add("AI use", f"{len(ai)} Gemini event(s) in 2 weeks")
    g = data.get("guardians")
    if g is not None:
        st = Counter((_low(r).get("state") or "COMPLETE").upper() for r in g)
        if not g:
            add("Guardians", "no guardian invited", "medium")
        else:
            add("Guardians", ", ".join(f"{v} {k.lower()}" for k, v in st.items()))
    if repairs is not None:
        mine = [t for t in repairs if (t.get("user") or "").lower() == e]
        if mine:
            add("Repairs", f"{len(mine)} repair(s); last {mine[-1].get('opened', '')}: "
                f"{(mine[-1].get('problem') or '')[:40]}", "medium" if len(mine) >= 2 else
                "info")
    if findings is not None:
        mine = [f for f in findings if (f.get("Who") or "").lower() == e and
                f.get("Status", "New") == "New"]
        if mine:
            add("Unusual activity", "; ".join(sorted({f["Finding"] for f in mine}))[:200],
                "high")
    order = {"high": 0, "medium": 1, "info": 2, "ok": 3}
    return sorted(out, key=lambda x: order.get(x["Level"], 2))


def gather(email: str, run_csv, user=None) -> list[dict]:
    from . import fleet
    from .tools import app_vetting, watchdog
    data = {}
    for k, a in commands(email).items():
        try:
            c, rows, _e = run_csv(a)
        except Exception:  # noqa: BLE001
            c, rows = 1, []
        data[k] = rows if c == 0 else None
    return analyze(email, data, user, fleet.load_list(fleet.data_dir(), "repairs.json"),
                   watchdog.load_findings(), app_vetting.load_list())
