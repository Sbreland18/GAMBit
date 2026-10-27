"""Saved user searches (Users → Find / list users → ☆ Save this search).

A saved search keeps everything on the form – the kind of search, every org unit picked,
“include sub-org units”, the custom field and its test – so running it from Home or the
Users page gives exactly the same list. They're stored with the other favorites
(kind "search"); searches saved by older versions only had a query and still work.
"""

from __future__ import annotations

import json
import uuid

MODES = ["Everyone", "In org unit(s)", "Name or email contains", "Suspended users only",
         "Custom query", "Custom field"]


def new_key() -> str:
    return "search:" + uuid.uuid4().hex[:10]


def spec_of(fav: dict) -> dict:
    """The form settings for a favorite of kind "search" (old ones → a custom query)."""
    s = fav.get("spec")
    if isinstance(s, dict) and s.get("mode") in MODES:
        return {"mode": s["mode"], "value": s.get("value", "") or "",
                "ous": [str(o) for o in s.get("ous") or []],
                "children": bool(s.get("children", True)),
                "cf_field": s.get("cf_field", "") or "", "cf_op": s.get("cf_op", "is") or "is"}
    return {"mode": "Custom query", "value": fav.get("value", ""), "ous": [],
            "children": True, "cf_field": "", "cf_op": "is"}


def describe(spec: dict) -> str:
    m, v, ous = spec["mode"], spec.get("value", ""), spec.get("ous") or []
    where = (", ".join(ous[:4]) + (f" +{len(ous) - 4} more" if len(ous) > 4 else "")) \
        if ous else ""
    sub = "" if spec.get("children", True) else " (not sub-org units)"
    if m == "In org unit(s)":
        return f"Users in {where or '—'}{sub}"
    if m == "Name or email contains":
        return f"Name or email contains “{v}”"
    if m == "Custom query":
        return f"Query: {v}"
    if m == "Custom field":
        from .custom_fields import OPS
        test = OPS.get(spec.get("cf_op", "is"), "is")
        val = f" “{v}”" if spec.get("cf_op") in ("is", "contains", "starts") else ""
        return f"{spec.get('cf_field')} {test}{val}" + (f" in {where}{sub}" if ous else "")
    return m


def tooltip(fav: dict) -> str:
    return describe(spec_of(fav))


def dumps(spec: dict) -> str:
    return json.dumps(spec, sort_keys=True)


# ================================================================ running ===
USER_FIELDS = "primaryemail,name,suspended,ou,lastlogintime,creationtime"


def build(spec: dict, fields: str = USER_FIELDS):
    """(gam commands, keep(row) or None) for a search – used by the Users page and by the
    scheduled Google Sheet refresh, so both give the same list."""
    from . import custom_fields as cf
    m, val = spec["mode"], (spec.get("value") or "").strip()
    ous = [o for o in spec.get("ous") or []]
    direct = bool(ous) and not spec.get("children", True)
    wanted = {o.lower() for o in ous}

    def in_ous(r):
        return not direct or (r.get("orgUnitPath") or "/").lower() in wanted

    if m == "Custom field":
        col, op = spec.get("cf_field", ""), spec.get("cf_op", "is")
        sq = cf.server_query(col, op, val)
        schemas = cf.schema_names((cf.columns() if cf.active() else []) + [col])
        cmds = []
        for ou in (ous or [None]):
            q = [x for x in (f"orgUnitPath='{ou}'" if ou and ou != "/" else "", sq) if x]
            cmds.append(["print", "users"] + (["query", " ".join(q)] if q else []) +
                        ["fields", fields, "custom", ",".join(schemas)])
        return cmds, (lambda r: in_ous(r) and cf.matches(r, col, op, val))
    if m == "In org unit(s)":
        cmds = [cf.with_custom(["print", "users"] + (["query", f"orgUnitPath='{ou}'"]
                                                     if ou != "/" else []) +
                               ["fields", fields]) for ou in ous]
        return cmds, (in_ous if direct else None)
    q = {"Name or email contains": val, "Suspended users only": "isSuspended=true",
         "Custom query": val}.get(m, "")
    return [cf.with_custom(["print", "users"] + (["query", q] if q else []) +
                           ["fields", fields])], None


def merge(outs: list[str], keep=None) -> tuple[list[str], list[list[str]]]:
    """Several CSV outputs → one de-duplicated table (custom fields tidied)."""
    import csv
    import io
    return merge_rows([list(csv.DictReader(io.StringIO((t or "").strip()))) for t in outs],
                      keep)


def merge_rows(row_lists: list[list[dict]], keep=None) -> tuple[list[str], list[list[str]]]:
    from . import custom_fields as cf
    headers: list[str] = []
    rows, seen = [], set()
    for part in row_lists:
        for r in part:
            for h in r:
                if h and h not in headers:
                    headers.append(h)
            if keep and not keep(r):
                continue
            key = tuple(sorted((str(k), str(v)) for k, v in r.items()))
            if key not in seen:
                seen.add(key)
                rows.append(r)
    table = [[r.get(h, "") or "" for h in headers] for r in rows]
    return cf.tidy(headers, table) if cf.has_custom(headers) else (headers, table)


def run(spec: dict, run_csv=None) -> tuple[list[str], list[list[str]]]:
    """Run a saved search without the window: (headers, rows)."""
    if run_csv is None:
        from .directory import run_gam_csv
        run_csv = (lambda a: run_gam_csv(a, 1800))
    cmds, keep = build(spec)
    parts = []
    for c in cmds:
        code, rows, err = run_csv(c)
        if code != 0:
            last = (err or "").strip().splitlines()[-1:] or [str(code)]
            raise RuntimeError(f"GAM couldn't run the search: {last[0]}")
        parts.append(rows)
    return merge_rows(parts, keep)
