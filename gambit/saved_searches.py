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
