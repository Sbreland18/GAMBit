"""Request catalog for principals and secretaries: one Google Form for the common asks –
a substitute account, group changes, a new Classroom class, moving a Chromebook. Each new
response becomes an Approvals request already filled in (or runs straight away when your
approval rules allow it), and the person who asked gets an email either way."""

from __future__ import annotations

import csv
import datetime
import json
import os
import re

from .settings import settings

TYPES = {"sub": ("substitute", "temporary account", "sub account"),
         "group": ("group",),
         "class": ("class", "course", "classroom"),
         "move": ("chromebook", "device", "move"),
         "other": ()}
LABEL = {"sub": "Substitute / temporary account", "group": "Group change",
         "class": "New Classroom class", "move": "Move a Chromebook", "other": "Something else"}
COLS = {"time": ["timestamp"], "requester": ["email address", "email"],
        "type": ["what do you need", "request type", "type of request"],
        "first": ["first name"], "last": ["last name"], "end": ["end date", "last day"],
        "group": ["group", "group email"], "add": ["people to add", "add"],
        "remove": ["people to remove", "remove"], "class": ["class name", "course name"],
        "section": ["section", "period"], "teacher": ["teacher email", "teacher"],
        "serial": ["serial", "asset tag", "serial number"],
        "move_to": ["move to", "new location", "room", "cart"],
        "details": ["details", "anything else", "notes"]}


def options() -> dict:
    try:
        o = json.loads(settings.get("catalog/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"sheet_url": "", "tab": "", "staff_root": "/Staff", "sub_ou": "/Staff/Temporary",
            "sub_email": "sub.{first}{last}@{domain}", "sub_days": 30, **o}


def save_options(o: dict):
    settings.set("catalog/options", json.dumps(o))


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def columns(headers: list[str]) -> dict:
    out = {}
    for key, cands in COLS.items():
        for h in headers:
            nh = _norm(h)
            if any(nh == c or nh.startswith(c) for c in cands):
                out.setdefault(key, h)
    if "requester" in out and out.get("requester") == out.get("teacher"):
        out.pop("teacher")
    return out


def kind_of(text: str) -> str:
    t = (text or "").lower()
    for k, words in TYPES.items():
        if any(w in t for w in words):
            return k
    return "other"


def _emails(text: str) -> list[str]:
    return [e.lower() for e in re.findall(r"[\w.+'-]+@[\w.-]+\.\w+", text or "")]


def make_sub_email(first: str, last: str, tpl: str, domain: str) -> str:
    clean = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())  # noqa: E731
    return tpl.replace("{first}", clean(first)).replace("{last}", clean(last)) \
        .replace("{f}", clean(first)[:1]).replace("{domain}", domain).lower()


def build(row: dict, cols: dict, o: dict, domain: str) -> dict:
    """One form response → {kind, title, commands, problem, extra}"""
    g = lambda k: (row.get(cols.get(k, "")) or "").strip()  # noqa: E731
    who = g("requester").lower()
    k = kind_of(g("type"))
    out = {"kind": k, "requester": who, "commands": [], "problem": "", "extra": {},
           "title": f"{LABEL[k]} (asked by {who})", "details": g("details")}
    if k == "sub":
        first, last = g("first"), g("last")
        if not (first and last):
            out["problem"] = "the substitute's first and last name are missing"
            return out
        email = make_sub_email(first, last, o["sub_email"], domain)
        end = g("end")
        try:
            end = datetime.date.fromisoformat(end[:10]).isoformat() if end else ""
        except ValueError:
            try:
                end = datetime.datetime.strptime(end.split()[0], "%m/%d/%Y").date().isoformat()
            except (ValueError, IndexError):
                end = ""
        end = end or (datetime.date.today() + datetime.timedelta(
            days=int(o.get("sub_days", 30) or 30))).isoformat()
        out["commands"] = [["create", "user", email, "firstname", first, "lastname", last,
                            "password", "random", "changepassword", "on", "ou", o["sub_ou"],
                            "notify", who, "subject", f"New account for {first} {last}"]]
        out["title"] = f"Substitute account {email} until {end} (asked by {who})"
        out["extra"] = {"temp": {"email": email, "end": end, "sponsor": who,
                                 "kind": "Substitute"}}
    elif k == "group":
        grp = (_emails(g("group")) or [""])[0]
        adds, rems = _emails(g("add")), _emails(g("remove"))
        if not grp or not (adds or rems):
            out["problem"] = "the group email or the people to add/remove are missing"
            return out
        out["commands"] = [["update", "group", grp, "add", "member", "user", e] for e in adds] + \
            [["update", "group", grp, "remove", "user", e] for e in rems]
        out["title"] = f"Group {grp}: +{len(adds)} / −{len(rems)} (asked by {who})"
    elif k == "class":
        name, teacher = g("class"), (_emails(g("teacher")) or [who])[0]
        if not name:
            out["problem"] = "the class name is missing"
            return out
        c = ["create", "course", "name", name]
        if g("section"):
            c += ["section", g("section")]
        out["commands"] = [c + ["owner", teacher, "status", "active"]]
        out["title"] = f"New class “{name}” for {teacher} (asked by {who})"
    elif k == "move":
        sn, to = g("serial").upper(), g("move_to")
        if not sn or not to:
            out["problem"] = "the serial number or where it's going is missing"
            return out
        attr = ["ou", to] if to.startswith("/") else ["location", to]
        out["commands"] = [["cros_sn", sn, "update", *attr]]
        out["title"] = f"Move Chromebook {sn} to {to} (asked by {who})"
    return out


def _state_path() -> str:
    from . import team
    d = team.folder()
    if not d:
        from .support import logs_dir
        d = os.path.dirname(logs_dir())
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "catalog_state.json")


def _state() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"done": {}}


def _save_state(st: dict):
    from .team import _write_json
    _write_json(_state_path(), st)      # temp file + rename: never half-written


def _key(row: dict, cols: dict) -> str:
    return "|".join((row.get(cols.get(k, "")) or "").strip().lower()
                    for k in ("time", "requester", "type"))


def staff_ok(email: str, users: dict, root: str) -> bool:
    u = users.get(email.lower())
    ou, r = ((u or {}).get("ou") or "/").rstrip("/").lower(), root.rstrip("/").lower()
    return bool(u) and not u.get("suspended") and (ou == r or ou.startswith(r + "/") or not r)


def process(log=print, rows=None, cols=None, users=None, run_text=None, tell=None) -> list:
    """Background (staff requests task): new responses → approvals or straight away."""
    from . import activity, approval_policy, google_io, team
    from .directory import load_users, run_gam_text
    o = options()
    if rows is None:
        if not o.get("sheet_url"):
            return []
        path = google_io.download_sheet(o["sheet_url"], o["tab"])
        with open(path, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
    if not rows:
        return []
    cols = cols or columns(list(rows[0].keys()))
    users_l = users if users is not None else load_users()
    users_d = {u["email"].lower(): u for u in users_l}
    domain = google_io.admin_email().split("@")[-1] if "@" in google_io.admin_email() else \
        (next(iter(users_d), "x@district.org").split("@")[-1])
    run_text = run_text or run_gam_text
    tell = tell or (lambda to, s, b: google_io.send_email(to, s, b))
    st = _state()
    lines = []
    for row in rows:
        key = _key(row, cols)
        if not key.strip("|") or key in st["done"]:
            continue
        r = build(row, cols, o, domain)
        who = r["requester"]
        st["done"][key] = datetime.datetime.now().isoformat(timespec="minutes")
        _save_state(st)                 # saved before acting, so a crash can't repeat it
        if not staff_ok(who, users_d, o["staff_root"]):
            lines.append(f"Ignored a request from {who or '(no email)'} – not active staff.")
            continue
        if r["problem"]:
            _safe(tell, who, "Your technology request needs more detail",
                  f"Your request ({LABEL[r['kind']]}) couldn't be sent: {r['problem']}. "
                  "Please fill in the form again.")
            lines.append(f"{who}: {LABEL[r['kind']]} – missing details.")
            continue
        auto = r["commands"] and all(approval_policy.auto_rule(c, users_l) for c in r["commands"])
        if auto and not settings.get("safety/dry_run", False):
            bad = 0
            for c in r["commands"]:
                try:
                    code, _out = run_text(c, 300)
                except Exception:  # noqa: BLE001
                    code = 1
                bad += 1 if code else 0
                activity.record(c, code, "done" if code == 0 else "failed", None,
                                settings.get("profile/current", "") or "Default",
                                note=f"request form – {who}")
            if not bad and r["extra"].get("temp"):
                _track(r["extra"]["temp"])
            _safe(tell, who, f"Done: {LABEL[r['kind']]}",
                  f"Your request was done automatically:\n{r['title']}"
                  + ("" if not bad else f"\n\n{bad} step(s) didn't work – the technology "
                                        "department will follow up."))
            lines.append(f"{who}: {r['title']} – done automatically.")
            continue
        if not team.folder():
            lines.append(f"{who}: {r['title']} – needs approval but there's no team folder.")
            continue
        team.new_request(r["commands"], r["title"] + (f"\nDetails: {r['details']}" if
                                                       r["details"] else ""),
                         title=r["title"], by=who,
                         extra={"kind": "catalog_sub" if r["kind"] == "sub" else "catalog",
                                "catalog": r["kind"], **r["extra"]})
        _safe(tell, who, f"Request received: {LABEL[r['kind']]}",
              f"Thanks – your request is with the technology department:\n{r['title']}\n\n"
              "You'll hear back when it's done.")
        lines.append(f"{who}: {r['title']} – sent for approval.")
    _save_state(st)
    lines += finalize()
    for ln in lines:
        log(ln)
    return lines


def _safe(tell, to, subject, body):
    try:
        if "@" in (to or ""):
            tell(to, subject, body)
    except Exception:  # noqa: BLE001
        pass


def _track(t: dict):
    from . import temp_accounts as ta
    items = ta.load()
    if not any(i["email"] == t["email"] for i in items):
        ta.add(items, t["email"], t.get("kind", "Substitute"), t.get("sponsor", ""), t["end"],
               "request form")
        ta.save(items)


def finalize() -> list[str]:
    """Approved substitute accounts → time-limited accounts list."""
    from . import team
    if not team.folder():
        return []
    out = []
    for r in team.list_requests("done"):
        if r.get("kind") == "catalog_sub" and r.get("temp") and not r.get("tracked"):
            _track(r["temp"])
            r["tracked"] = True
            team.save_request(r)
            out.append(f"Tracking {r['temp']['email']} until {r['temp']['end']}.")
    return out
