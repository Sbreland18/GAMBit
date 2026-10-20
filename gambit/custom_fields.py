"""Custom user fields (Google "custom schemas", e.g. Student_Information.Grade).

Every district's schemas are different, so GAMbit reads them from Google
(`gam print schemas`) and you tick the fields you want in Settings & Updates →
Custom user fields. The ticked fields then:

- appear as columns in user lists (Users → Find users, Org units → Users in this org unit,
  Reports → Inactive accounts) and so in every CSV export and Google Sheet;
- show on the user card in Lookup;
- can be searched: Users → Find users → “Custom field”.

Columns come out of GAM as ``customSchemas.Student_Information.Grade`` (multi-value fields
as ``customSchemas.S.F.0.value``…); :func:`tidy` turns them into one tidy column each.

With a team folder the choice is shared, so every technician exports the same columns.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import re

from .settings import settings

SHARED_NAME = "custom_fields.json"
KEY = "customfields/config"
_COL = re.compile(r"^customSchemas\.([^.]+)\.([^.]+)(?:\.(\d+)\.(\w+))?$", re.I)
_FIELD = re.compile(r"^fields\.(\d+)\.(\w+)$", re.I)

_cache: dict | None = None


# ============================================================== storage ===
def _default() -> dict:
    return {"schemas": {}, "columns": [], "headers": "friendly", "in_lists": True,
            "loaded_at": ""}


def config() -> dict:
    """{schemas: {name: {display, fields: [{name, display, type, multi, indexed}]}},
    columns: ["Schema.Field", …], headers: friendly|gam, in_lists: bool}"""
    global _cache
    if _cache is not None:
        return _cache
    data = None
    try:
        from . import team
        if team.folder():
            data = team.read_shared(SHARED_NAME) or None
    except Exception:  # noqa: BLE001 – a broken team folder mustn't stop the app
        data = None
    if not data:
        try:
            data = json.loads(settings.get(KEY, "") or "{}")
        except ValueError:
            data = {}
    cfg = {**_default(), **(data if isinstance(data, dict) else {})}
    cfg["columns"] = [c for c in cfg.get("columns") or [] if isinstance(c, str) and "." in c]
    _cache = cfg
    return cfg


def save(cfg: dict):
    global _cache
    cfg = {**_default(), **cfg}
    settings.set(KEY, json.dumps(cfg))
    try:
        from . import team
        if team.folder():
            team.write_shared(SHARED_NAME, cfg)
    except Exception:  # noqa: BLE001
        pass
    _cache = cfg


def reload():
    global _cache
    _cache = None


def columns() -> list[str]:
    return list(config()["columns"])


def active() -> bool:
    """Custom fields go into user lists."""
    c = config()
    return bool(c["columns"]) and bool(c.get("in_lists", True))


def schema_names(cols: list[str] | None = None) -> list[str]:
    out = []
    for c in columns() if cols is None else cols:
        s = c.split(".", 1)[0]
        if s.lower() not in {x.lower() for x in out}:
            out.append(s)
    return out


def field_info(col: str) -> dict:
    s, _, f = col.partition(".")
    sch = next((v for k, v in config()["schemas"].items() if k.lower() == s.lower()), {})
    return next((x for x in sch.get("fields", []) if x["name"].lower() == f.lower()),
                {"name": f, "display": "", "type": "STRING", "multi": False, "indexed": False})


# ============================================================ discovery ===
def _true(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def parse_schemas(text: str) -> dict:
    """`gam print schemas` CSV → {name: {display, fields: […]}}."""
    out: dict = {}
    for r in csv.DictReader(io.StringIO((text or "").strip())):
        low = {(k or "").lower(): v for k, v in r.items()}
        name = (low.get("schemaname") or "").strip()
        if not name:
            continue
        fields: dict[int, dict] = {}
        for k, v in r.items():
            m = _FIELD.match(k or "")
            if m:
                fields.setdefault(int(m.group(1)), {})[m.group(2).lower()] = v or ""
        out[name] = {"display": (low.get("displayname") or "").strip(),
                     "fields": [{"name": f.get("fieldname", "").strip(),
                                 "display": f.get("displayname", "").strip(),
                                 "type": (f.get("fieldtype") or "STRING").upper(),
                                 "multi": _true(f.get("multivalued", "")),
                                 "indexed": _true(f.get("indexed", "true") or "true")}
                                for _i, f in sorted(fields.items()) if f.get("fieldname")]}
    return out


def schemas_from_users(text: str) -> dict:
    """Learn schema and field names from `print users … custom all` output (when reading
    the schema definitions isn't allowed). Types and indexing aren't known this way."""
    out: dict = {}
    for h in next(csv.reader(io.StringIO((text or "").strip())), []):
        m = _COL.match(h or "")
        if not m:
            continue
        s, f = m.group(1), m.group(2)
        sch = out.setdefault(s, {"display": "", "fields": []})
        if not any(x["name"] == f for x in sch["fields"]):
            sch["fields"].append({"name": f, "display": "", "type": "STRING",
                                  "multi": bool(m.group(3)), "indexed": False})
    return out


def remember_schemas(found: dict, replace: bool = True) -> dict:
    cfg = dict(config())
    sch = dict(found) if replace else {**found, **cfg.get("schemas", {})}
    cfg["schemas"] = sch
    known = {f"{s}.{x['name']}".lower() for s, v in sch.items() for x in v["fields"]}
    cfg["columns"] = [c for c in cfg["columns"] if c.lower() in known]
    cfg["loaded_at"] = datetime.datetime.now().isoformat(timespec="minutes")
    save(cfg)
    return cfg


# ============================================================ GAM args ===
def args(force: bool = False) -> list[str]:
    """Extra `print users` arguments for the chosen custom fields."""
    if not (active() or (force and columns())):
        return []
    return ["custom", ",".join(schema_names())]


def with_custom(cmd: list[str], force: bool = False) -> list[str]:
    extra = args(force)
    return list(cmd) + extra if extra and "custom" not in [str(a).lower() for a in cmd] \
        else list(cmd)


# ============================================================ tidying ===
def label(col: str, style: str | None = None, clash: bool = False) -> str:
    style = style or config().get("headers", "friendly")
    if style == "gam":
        return col
    info = field_info(col)
    name = info.get("display") or info["name"].replace("_", " ")
    return f"{col.split('.', 1)[0].replace('_', ' ')}: {name}" if clash else name


def has_custom(headers: list[str]) -> bool:
    return any(_COL.match(h or "") for h in headers)


def tidy(headers: list[str], rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """One column per custom field: chosen fields in the chosen order (others from schemas
    you didn't set up are kept too), multi-values joined with “; ”."""
    if not has_custom(headers):
        return headers, rows
    chosen = columns()
    chosen_schemas = {c.split(".", 1)[0].lower() for c in chosen}
    keep_idx, groups, order = [], {}, []
    for i, h in enumerate(headers):
        m = _COL.match(h or "")
        if not m:
            keep_idx.append(i)
            continue
        s, f, n, sub = m.group(1), m.group(2), m.group(3), (m.group(4) or "").lower()
        col = f"{s}.{f}"
        if s.lower() in chosen_schemas and col.lower() not in {c.lower() for c in chosen}:
            continue                       # a field you didn't tick
        if n is not None and sub not in ("value", ""):
            continue                       # .0.type / .0.customType
        key = col.lower()
        if key not in groups:
            groups[key] = (col, [])
            order.append(key)
        groups[key][1].append(i)
    rank = {c.lower(): i for i, c in enumerate(chosen)}
    present = set(order)
    # chosen fields nobody has a value for still get a column (when GAM sent that schema)
    sent = {k.split(".", 1)[0] for k in order}
    for c in chosen:
        if c.lower() not in present and c.split(".", 1)[0].lower() in sent:
            groups[c.lower()] = (c, [])
            order.append(c.lower())
    first = {k: i for i, k in enumerate(order)}
    order.sort(key=lambda k: (rank.get(k, 10_000), first[k]))
    names = [groups[k][0] for k in order]
    short = [label(c, clash=False) for c in names]
    dup = {s.lower() for s in short if [x.lower() for x in short].count(s.lower()) > 1}
    others = {(headers[i] or "").lower() for i in keep_idx}
    new_h = [headers[i] for i in keep_idx] + [
        label(c, clash=(s.lower() in dup or s.lower() in others)) for c, s in zip(names, short)]
    out = []
    for r in rows:
        base = [r[i] if i < len(r) else "" for i in keep_idx]
        for k in order:
            vals = [r[i] for i in groups[k][1] if i < len(r) and (r[i] or "").strip()]
            base.append("; ".join(vals))
        out.append(base)
    return new_h, out


def tidy_dict(row: dict) -> list[tuple[str, str]]:
    """(label, value) for the chosen custom fields in one `print users` row (Lookup card)."""
    headers = list(row.keys())
    h, rows = tidy(headers, [[row.get(k, "") or "" for k in headers]])
    std = set(headers)
    return [(k, v) for k, v in zip(h, rows[0] if rows else []) if k not in std]


# ============================================================ searching ===
OPS = {"is": "is", "contains": "contains", "starts": "starts with", "empty": "is empty",
       "notempty": "has a value"}


def server_query(col: str, op: str, value: str) -> str:
    """A Google directory query for an exact match on an indexed field, else ''."""
    info = field_info(col)
    if op != "is" or not info.get("indexed") or not value.strip():
        return ""
    t = info.get("type", "STRING")
    if t in ("INT64", "DOUBLE"):
        try:
            float(value)
        except ValueError:
            return ""
        return f"{col}={value.strip()}"
    if t == "BOOL":
        return f"{col}={'true' if _true(value) else 'false'}"
    v = value.strip().replace("'", "\\'")
    return f"{col}='{v}'"


def matches(row: dict, col: str, op: str, value: str) -> bool:
    """Check a tidied (or raw) row locally."""
    labs = {label(col).lower(), label(col, clash=True).lower()}
    cand = [v for k, v in row.items() if k and (k.lower() in labs or k.lower() == col.lower() or
                                               k.lower() == f"customschemas.{col}".lower() or
                                               k.lower().startswith(f"customschemas.{col}.".lower())
                                               and k.lower().endswith(".value"))]
    have = "; ".join(str(v) for v in cand if str(v or "").strip())
    vals = [x.strip().lower() for x in have.split(";") if x.strip()] or [""]
    want = (value or "").strip().lower()
    if op == "empty":
        return not have.strip()
    if op == "notempty":
        return bool(have.strip())
    if op == "is":
        return want in vals
    if op == "starts":
        return any(x.startswith(want) for x in vals)
    return want in have.lower()
