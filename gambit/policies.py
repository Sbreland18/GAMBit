"""Org-unit policy view: which Chrome and Workspace (Gmail, Drive …) settings each org
unit has, side by side, so a grade level missing a setting stands out."""

from __future__ import annotations

import csv
import io
from collections import OrderedDict

META = {"name", "customer", "type", "orgunitpath", "parentorgunitpath", "orgunitid",
        "direct", "policyquery.orgunit", "policyquery.query", "policyquery.group",
        "policyquery.sortorder", "setting.type", "schemaname", "policy", "group"}


def _low(r):
    return {(k or "").strip(): (v or "").strip() for k, v in r.items()}


def rows_to_settings(text: str, ou_hint: str = "") -> list[tuple[str, str, str]]:
    """GAM CSV (print chromepolicies / print policies) → [(ou, setting, value)]."""
    out = []
    for r in csv.DictReader(io.StringIO(text or "")):
        r = _low(r)
        lk = {k.lower(): k for k in r}
        ou = next((r[lk[k]] for k in lk if "orgunit" in k and "parent" not in k and
                   "id" not in k and r[lk[k]]), "") or ou_hint
        setting = next((r[lk[k]] for k in ("setting.type", "name", "schemaname", "policy")
                        if k in lk and r[lk[k]]), "")
        if not setting:
            continue
        setting = setting.replace("settings/", "").replace("chrome.users.", "") \
            .replace("chrome.devices.", "devices.")
        vals = [f"{k.split('.')[-1]}={v}" for k, v in r.items()
                if v and k.lower() not in META and not k.lower().startswith("policyquery")]
        out.append((ou or "/", setting, "; ".join(vals) or "set"))
    return out


def matrix(triples: list[tuple[str, str, str]], ous: list[str]):
    """→ (headers, rows) with one row per setting and one column per OU.
    Settings that differ between the chosen OUs come first."""
    by_setting: "OrderedDict[str, dict]" = OrderedDict()
    for ou, setting, value in triples:
        by_setting.setdefault(setting, {})[ou] = value
    rows = []
    for setting, per in by_setting.items():
        vals = [per.get(o, "") for o in ous]
        differs = len(set(vals)) > 1
        rows.append((not differs, setting, ["⚠ differs" if differs else ""] + vals))
    rows.sort(key=lambda x: (x[0], x[1].lower()))
    return ["Setting", "", *ous], [[s, *v] for _same, s, v in rows]
