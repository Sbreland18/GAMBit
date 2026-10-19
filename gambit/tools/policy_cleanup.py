"""Policy override clean-up: find Chrome policies set directly on a child org unit with
exactly the value it would get from its parent anyway. Removing them changes nothing today
but means a later change at the parent reaches every child."""

from __future__ import annotations

import json


def direct_args(ou: str) -> list[str]:
    return ["print", "chromepolicies", "ou", ou, "show", "direct", "formatjson"]


def resolved_args(ou: str) -> list[str]:
    return ["print", "chromepolicies", "ou", ou, "formatjson"]


def parent(ou: str) -> str:
    ou = ou.rstrip("/")
    return ou.rsplit("/", 1)[0] or "/" if ou else ""


def _policies(rows: list[dict], direct_only: bool) -> dict[str, dict]:
    out = {}
    for r in rows:
        try:
            p = json.loads(r.get("JSON") or "{}")
        except ValueError:
            continue
        if not p.get("name"):
            continue
        if p.get("additionalTargetKeys") or p.get("additionalTargetKeyNames"):
            continue                       # app / printer specific – leave alone
        if direct_only and p.get("direct") is False:
            continue
        out[p["name"]] = {f.get("name"): f.get("value") for f in p.get("fields", [])}
    return out


def redundant(ou: str, direct_rows: list[dict], parent_rows: list[dict]) -> list[dict]:
    mine = _policies(direct_rows, True)
    theirs = _policies(parent_rows, False)
    out = []
    for schema, fields in sorted(mine.items()):
        if schema in theirs and _same(fields, theirs[schema]):
            out.append({"Org unit": ou, "Policy": schema,
                        "Value": ", ".join(f"{k}={v}" for k, v in fields.items())[:200],
                        "Same as": parent(ou),
                        "args": ["delete", "chromepolicy", schema, "ou", ou]})
    return out


def _same(a: dict, b: dict) -> bool:
    keys = set(a) | set(b)
    return all(_norm(a.get(k)) == _norm(b.get(k)) for k in keys)


def _norm(v):
    if isinstance(v, str):
        return v.strip().lower()
    return json.dumps(v, sort_keys=True).lower() if v is not None else None


def scan(ous: list[str], run_csv) -> tuple[list[dict], list[str]]:
    out, probs = [], []
    cache: dict[str, list[dict]] = {}
    for ou in ous:
        if ou in ("", "/"):
            continue
        c, drows, e = run_csv(direct_args(ou))
        if c != 0:
            probs.append(f"{ou}: {(e or '').strip()[-120:]}")
            continue
        p = parent(ou)
        if p not in cache:
            c, prow, e = run_csv(resolved_args(p))
            cache[p] = prow if c == 0 else []
        out += redundant(ou, drows, cache[p])
    return out, probs
