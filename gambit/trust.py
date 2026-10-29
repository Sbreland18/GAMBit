"""Trust centre: what in the shared team folder is signed, by whom – and signing what a
person has checked.

After updating to a GAMbit that signs shared records, older items have no signature yet
(and anything edited by hand has a broken one). Background tasks skip those, so someone who
is allowed to run them looks at each item's exact commands here and signs it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import seal, team


@dataclass
class Item:
    kind: str
    label: str
    signed: str                       # describe() text
    ok: bool
    detail: str
    commands: list = field(default_factory=list)
    sign: Optional[Callable[[], None]] = None
    admin_only: bool = False


def _cmds_text(cmds) -> str:
    from .gam_runner import display_command
    return "\n".join(display_command([str(a) for a in c]) for c in cmds) or "(no commands)"


def _check_role(cmds):
    for c in cmds:
        ok, missing, _ask = team.check([str(a) for a in c])
        if not ok:
            raise PermissionError("Your GAMbit role can't run all of it ("
                                  + ", ".join(sorted(missing)) + ") – so you can't sign it.")


def items() -> list[Item]:
    out: list[Item] = []
    out += _queue()
    out += _offboarding()
    out += _temp_accounts()
    out += _policy_plans()
    out += _group_rules()
    out += _shared_files()
    return out


# ------------------------------------------------------------------ kinds ---
def _queue() -> list[Item]:
    from . import change_queue as cq
    res = []
    try:
        q = cq.queue()
    except Exception:  # noqa: BLE001
        return res
    for it in q:
        if it.get("status") != "waiting":
            continue
        v = cq.verify(it)
        cmds = it.get("commands", [])

        def sign(i=it["id"], c=cmds):
            _check_role(c)
            cq.resign(i)
        res.append(Item("Run later", f"{it.get('title', '?')} – {it.get('when', '')}",
                        seal.describe(v), v is not None, _cmds_text(cmds), cmds, sign))
    return res


def _offboarding() -> list[Item]:
    from . import offboard
    res = []
    try:
        recs = offboard.load_all()
    except Exception:  # noqa: BLE001
        return res
    for rec in recs:
        if not isinstance(rec, dict) or rec.get("status") != "active":
            continue
        v = offboard.verify(rec)
        cmds = [s.get("args", []) for st in rec.get("stages", [])
                for s in st.get("steps", []) if s.get("status") == "pending"]

        def sign(r=rec, c=cmds):
            auto = [s.get("args", []) for st in r.get("stages", []) if st.get("auto")
                    for s in st.get("steps", []) if s.get("status") == "pending"]
            _check_role(auto)
            fresh = offboard.get(r.get("email", ""))       # sign what's on disk now
            if fresh is None or offboard._stable(fresh) != offboard._stable(r):
                raise RuntimeError("The plan changed while you were looking – open it again.")
            offboard.save(fresh, sign_it=True)
        res.append(Item("Offboarding", rec.get("email", "?"), seal.describe(v), v is not None,
                        "Still to run:\n" + _cmds_text(cmds), cmds, sign))
    return res


def _temp_accounts() -> list[Item]:
    from . import temp_accounts as ta
    res = []
    try:
        all_items = ta.load()
    except Exception:  # noqa: BLE001
        return res
    for rec in all_items:
        if rec.get("status") != "active":
            continue
        v = ta.verify(rec)
        cmds = ta.expire_args(rec, ta.options())

        def sign(email=rec.get("email"), c=cmds):
            _check_role(c)
            items_now = ta.load()
            for r in items_now:
                if r.get("email") == email:
                    ta.sign(r)
            ta.save(items_now)
        res.append(Item("Time-limited account", f"{rec.get('email')} – ends {rec.get('end')}",
                        seal.describe(v), v is not None,
                        f"Ends {rec.get('end')} (sponsor {rec.get('sponsor') or '–'}); then:\n"
                        + _cmds_text(cmds), cmds, sign))
    return res


def _policy_plans() -> list[Item]:
    from .tools import policy_sets as ps
    res = []
    try:
        plans = ps.load()
    except Exception:  # noqa: BLE001
        return res
    for p in plans:
        if p.get("state") in ("reverted", "rolled back"):
            continue
        v = ps.verify(p)
        detail = json.dumps({k: p.get(k) for k in ps.SEAL_FIELDS}, indent=1)
        cmds = [["update", "chromepolicy", "ou", t] for t in p.get("targets", [])]

        def sign(pid=p["id"], c=cmds):
            _check_role(c)
            now = ps.load()
            for i, x in enumerate(now):
                if x.get("id") == pid:
                    signed = seal.sign("policyplan", x, ps.SEAL_FIELDS)
                    x["seal"] = signed["seal"]
            ps.save(now)
        res.append(Item("Chrome policy plan", p.get("name", "?"), seal.describe(v),
                        v is not None, detail, cmds, sign))
    return res


def _group_rules() -> list[Item]:
    from . import group_rules as gr
    res = []
    try:
        rules = gr.load()
    except Exception:  # noqa: BLE001
        return res
    for r in rules:
        if not r.get("enabled", True):
            continue
        v = gr.verify(r)
        detail = json.dumps({k: r.get(k) for k in gr.SEAL_FIELDS}, indent=1)
        cmds = [["update", "group", r.get("group", ""), "sync", "member", "ou", o]
                for o in (r.get("ous") or ["/"])]

        def sign(rid=r["id"], c=cmds):
            _check_role(c)
            now = gr.load()
            for x in now:
                if x.get("id") == rid:
                    gr.sign_rule(x)
            gr.save(now)
        res.append(Item("Automatic group", r.get("group", "?"), seal.describe(v),
                        v is not None, detail, cmds, sign))
    return res


SHARED = (("approval_policy.json", "approvalpolicy", "Approval rules"),
          ("workflows.json", "workflows", "Shared workflow settings"))


def _shared_files() -> list[Item]:
    res = []
    if not team.folder():
        return res
    for name, kind, label in SHARED:
        raw = team.read_shared(name)
        if not raw:
            continue
        data, v = team.read_shared_verified(name, kind)

        def sign(n=name, k=kind, before=json.dumps(data, sort_keys=True)):
            if not team.can_write_shared():
                raise PermissionError("Only a GAMbit admin can sign shared settings.")
            now = {x: y for x, y in team.read_shared(n).items() if x != "seal"}
            if json.dumps(now, sort_keys=True) != before:
                raise RuntimeError("The file changed while you were looking – open it again.")
            team.write_shared_signed(n, k, now)
        res.append(Item("Shared settings", label, seal.describe(v), v is not None,
                        json.dumps(data, indent=1, ensure_ascii=False), [], sign,
                        admin_only=True))
    return res


# --------------------------------------------------------- your key ---
def my_key_status() -> str:
    from .auth import access, session
    if session.active() and session.doc():
        how = access.key_trusted(session.doc(), session.email())
        try:
            k = access.my_key(session.email())
        except Exception:  # noqa: BLE001
            k = None
        code = __import__("gambit.auth.crypto", fromlist=["x"]).fingerprint(k[1]) if k \
            else "(none yet)"
        if how == "admin":
            return f"Your key {code} is a trusted GAMbit admin key."
        if how == "member":
            return f"Your key {code} is trusted – what you queue or ask for is signed by you."
        return (f"Your key {code} is waiting for a GAMbit admin to approve it (Users & "
                "access → Keys). Until then what you queue only runs from this computer.")
    return (f"This computer's key: {seal.local_fingerprint()} (GAMbit sign-in is off, so "
            "other computers trust it only after you pair them below).")
