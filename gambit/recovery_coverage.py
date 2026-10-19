"""Account recovery coverage: which staff have no recovery email or phone (so a forgotten
password means a help-desk call), the percentage by building, and a reminder campaign
pointing people at their Google Account recovery page."""

from __future__ import annotations

import json
from collections import defaultdict

from .settings import settings

USERS_ARGS = ["print", "users", "fields",
              "primaryemail,name,ou,suspended,recoveryemail,recoveryphone"]
LINK = "https://myaccount.google.com/recovery"
DEFAULT_MSG = ("Hello,\n\nIf you ever forget your district Google password, a recovery phone "
               "number or personal email lets you reset it yourself in a minute instead of "
               "waiting on the help desk.\n\nPlease add one now (about one minute):\n"
               f"{LINK}\n\nThank you!")


def options() -> dict:
    try:
        o = json.loads(settings.get("recoverycov/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"root": "/Staff", "depth": 1, "subject": "Add a recovery phone or email to your "
            "Google account", "message": DEFAULT_MSG, **o}


def save_options(o: dict):
    settings.set("recoverycov/options", json.dumps(o))


def people(rows: list[dict], opts: dict) -> list[dict]:
    from .tools.campaigns import _low, _under, building
    root = opts.get("root", "/Staff")
    out = []
    for r in rows:
        low = _low(r)
        e = low.get("primaryemail", "").lower()
        if not e or low.get("suspended", "").lower() == "true":
            continue
        ou = low.get("orgunitpath", "")
        if not _under(ou, root):
            continue
        em, ph = bool(low.get("recoveryemail")), bool(low.get("recoveryphone"))
        out.append({"email": e, "name": low.get("name.fullname", ""), "ou": ou,
                    "building": building(ou, root, int(opts.get("depth", 1) or 1)),
                    "email_set": em, "phone_set": ph, "covered": em or ph})
    return out


def coverage(ppl: list[dict]) -> list[dict]:
    by = defaultdict(lambda: {"n": 0, "cov": 0, "ph": 0, "em": 0})
    for p in ppl:
        b = by[p["building"]]
        b["n"] += 1
        b["cov"] += p["covered"]
        b["ph"] += p["phone_set"]
        b["em"] += p["email_set"]
    rows = [{"Building": k, "People": b["n"], "Covered": b["cov"], "Missing": b["n"] - b["cov"],
             "%": round(100 * b["cov"] / b["n"]) if b["n"] else 0, "Phone": b["ph"],
             "Email": b["em"]} for k, b in sorted(by.items())]
    if rows:
        n, c = sum(r["People"] for r in rows), sum(r["Covered"] for r in rows)
        rows.append({"Building": "Everyone", "People": n, "Covered": c, "Missing": n - c,
                     "%": round(100 * c / n) if n else 0,
                     "Phone": sum(r["Phone"] for r in rows),
                     "Email": sum(r["Email"] for r in rows)})
    return rows


def missing(ppl: list[dict]) -> list[dict]:
    return [{"Person": p["email"], "Name": p["name"], "Building": p["building"]}
            for p in sorted(ppl, key=lambda x: (x["building"], x["email"]))
            if not p["covered"]]


def reminder_commands(emails: list[str], opts: dict, sender: str,
                      size: int = 50) -> list[list[str]]:
    todo = sorted(set(emails))
    out = []
    for i in range(0, len(todo), size):
        a = ["sendemail", "to", sender or todo[i], "bcc", ",".join(todo[i:i + size])]
        if sender:
            a += ["from", sender]
        out.append(a + ["subject", opts.get("subject") or "Add a recovery phone or email",
                        "message", opts.get("message") or DEFAULT_MSG])
    return out
