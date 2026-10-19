"""Mailbox and calendar access review: who can read someone else's mail (delegates), send as
them (send-as addresses) or change their calendar (writer/owner sharing). Flags access held
by people who have left, outsiders and people at a different school, and keeps a quarterly
sign-off like the admin access review."""

from __future__ import annotations

import datetime
import json

from .settings import settings


def options() -> dict:
    try:
        o = json.loads(settings.get("delegreview/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"root": "/Staff", "former_root": "/Former", "every_days": 90, **o}


def save_options(o: dict):
    settings.set("delegreview/options", json.dumps(o))


def _who(root: str) -> list[str]:
    return ["ou_and_children", root] if root and root != "/" else ["all", "users"]


def commands(opts: dict | None = None) -> dict[str, list[str]]:
    opts = opts or options()
    w = _who(opts.get("root", "/Staff"))
    return {"delegates": w + ["print", "delegates"],
            "sendas": w + ["print", "sendas"],
            "calendar": w + ["print", "calendaracls", "primary", "noselfowner"]}


def _low(r):
    return {(k or "").lower(): (v or "") for k, v in r.items()}


def entries(data: dict) -> list[dict]:
    """→ [{Owner, Who, Access, kind, id}] from the three reports."""
    out = []
    for r in data.get("delegates") or []:
        low = _low(r)
        o, w = low.get("user", "").lower(), low.get("delegateaddress", "").lower()
        if o and w:
            st = low.get("delegationstatus", "")
            out.append({"Owner": o, "Who": w, "Access": "Reads and sends their mail" +
                        (f" ({st.lower()})" if st and st.lower() != "accepted" else ""),
                        "kind": "delegate", "id": w})
    for r in data.get("sendas") or []:
        low = _low(r)
        o, w = low.get("user", "").lower(), low.get("sendasemail", "").lower()
        if o and w and w != o and low.get("isprimary", "").lower() != "true":
            out.append({"Owner": o, "Who": w, "Access": "Can send mail as this address",
                        "kind": "sendas", "id": w})
    for r in data.get("calendar") or []:
        low = _low(r)
        o = (low.get("primaryemail") or low.get("calendarid", "")).lower()
        role = low.get("role", "").lower()
        st, w = low.get("scope.type", "").lower(), low.get("scope.value", "").lower()
        if role in ("writer", "owner") and st in ("user", "group") and w and w != o:
            out.append({"Owner": o, "Who": w, "Access": f"Calendar {role}" +
                        (" (group)" if st == "group" else ""), "kind": "calendar",
                        "id": f"{st}:{w}"})
    return out


from .oupath import under  # noqa: E402


def review(rows: list[dict], users: list[dict], opts: dict | None = None) -> list[dict]:
    from .parent_report import school_of
    opts = opts or options()
    udir = {u["email"].lower(): u for u in users}
    domains = {e.split("@")[-1] for e in udir}
    former = (opts.get("former_root") or "").rstrip("/").lower()
    root = opts.get("root", "/Staff")
    out = []
    for e in rows:
        o, w = udir.get(e["Owner"]), udir.get(e["Who"])
        flags = []
        if e["kind"] == "sendas":
            if e["Who"].split("@")[-1] not in domains:
                flags.append("outside address")
        elif w is None:
            if e["Who"].split("@")[-1] not in domains:
                flags.append("outsider")
        else:
            if w.get("suspended"):
                flags.append("holder suspended")
            if former and under(w.get("ou") or "", former):
                flags.append("holder has left")
            if o and not flags and (o.get("ou") or "").lower().startswith(
                    root.rstrip("/").lower() + "/") and (w.get("ou") or "").lower().startswith(
                    root.rstrip("/").lower() + "/"):
                so, sw = school_of(o["ou"], root), school_of(w["ou"], root)
                if so != sw:
                    flags.append(f"holder works at {sw}, owner at {so}")
        if o and o.get("suspended"):
            flags.append("mailbox owner suspended")
        out.append({**e, "Flags": "; ".join(flags), "risk": 2 * len(flags) +
                    (1 if e["kind"] == "delegate" else 0)})
    return sorted(out, key=lambda x: (-x["risk"], x["Owner"], x["Who"]))


def remove_args(e: dict) -> list[str]:
    if e["kind"] == "delegate":
        return ["user", e["Owner"], "delete", "delegate", e["Who"]]
    if e["kind"] == "sendas":
        return ["user", e["Owner"], "delete", "sendas", e["Who"]]
    return ["user", e["Owner"], "delete", "calendaracls", "primary", e["id"]]


def _key(e: dict) -> str:
    return f"{e['kind']}|{e['Owner']}|{e['Who']}"


def _load() -> list[dict]:
    from . import team
    if team.folder():
        return team.read_shared("mailbox_reviews.json").get("reviews", [])
    try:
        return json.loads(settings.get("delegreview/history", "[]") or "[]")
    except ValueError:
        return []


def history() -> list[dict]:
    return _load()


def sign_off(rows: list[dict], decisions: dict[str, str], who: str, note: str = "") -> dict:
    from . import team
    rec = {"date": datetime.date.today().isoformat(), "by": who, "note": note,
           "rows": [{"Owner": r["Owner"], "Who": r["Who"], "Access": r["Access"],
                     "Flags": r["Flags"], "Decision": decisions.get(_key(r), "Keep")}
                    for r in rows]}
    items = _load() + [rec]
    if team.folder():
        team.write_shared("mailbox_reviews.json", {"reviews": items[-40:]})
    settings.set("delegreview/history", json.dumps(items[-8:]))
    return rec


def due(today: datetime.date | None = None) -> bool:
    today = today or datetime.date.today()
    h = _load()
    if not h:
        return True
    try:
        last = datetime.date.fromisoformat(h[-1]["date"])
    except (KeyError, ValueError):
        return True
    return (today - last).days >= int(options().get("every_days", 90) or 90)


def new_since_last(rows: list[dict]) -> set[str]:
    h = _load()
    if not h:
        return set()
    seen = {f"{r.get('Owner')}|{r.get('Who')}|{r.get('Access')}" for r in h[-1]["rows"]}
    return {_key(r) for r in rows if f"{r['Owner']}|{r['Who']}|{r['Access']}" not in seen}
