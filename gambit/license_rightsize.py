"""Right-sizing premium licenses: who holds Teaching and Learning / Education Plus licenses
and whether they actually used premium features in the last N days (from the Meet audit
log: meetings over the Fundamentals participant limit and live streams, and
from Classroom's originality-report events). Holders who didn't are suggestions to
release – always through Approvals."""

from __future__ import annotations

import datetime
import json
from collections import defaultdict

from .settings import settings

PREMIUM = {"1010370001": "Teaching and Learning Upgrade", "1010310008": "Education Plus",
           "1010310009": "Education Plus (Staff)"}


def options() -> dict:
    try:
        o = json.loads(settings.get("rightsize/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"days": 90, "big_meeting": 100, "skus": list(PREMIUM), "keep": "", **o}


def save_options(o: dict):
    settings.set("rightsize/options", json.dumps(o))


def meet_args(days: int) -> list[str]:
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    return ["report", "meet", "user", "all", "start", start, "events",
            "call_ended,livestream_watched"]


def classroom_args(days: int) -> list[str]:
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    return ["report", "classroom", "user", "all", "start", start]


def premium_use(meet_rows: list[dict], class_rows: list[dict], big: int) -> dict[str, set]:
    """email → {reasons} for people who used a premium feature."""
    size = defaultdict(set)
    org_of = {}
    use = defaultdict(set)
    for r in meet_rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        org = (low.get("organizer_email") or "").lower()
        code = low.get("meeting_code") or low.get("conference_id") or ""
        ev = low.get("name", "")
        if ev in ("livestream_watched",) and org:
            use[org].add("live stream")
        if ("recording" in ev or low.get("is_recorded", "").lower() == "true") and org:
            use[org].add("recording")
        if code and org:
            size[code].add(low.get("identifier") or low.get("display_name") or
                           low.get("actor.email") or "")
            org_of[code] = org
    for code, people in size.items():
        if len(people) > big:
            use[org_of[code]].add(f"meeting with {len(people)} people")
    for r in class_rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        who = (low.get("actor.email") or "").lower()
        if who and "originality" in (low.get("name", "") + " " +
                                     " ".join(low.values())).lower():
            use[who].add("originality reports")
    return use


def suggest(holders: list[dict], use: dict[str, set], opts: dict) -> tuple[list, list]:
    """→ (per-SKU summary, per-person rows with args)"""
    from .tools.budget import sku_name
    keep = {x.strip().lower() for x in (opts.get("keep") or "").replace(";", ",").split(",")
            if x.strip()}
    skus = set(opts.get("skus") or PREMIUM)
    rows, summ = [], defaultdict(lambda: {"Held": 0, "Used premium features": 0,
                                          "Could release": 0})
    for h in holders:
        for sku in h["skus"]:
            if sku not in skus:
                continue
            s = summ[sku]
            s["Held"] += 1
            reasons = use.get(h["email"], set())
            if reasons:
                s["Used premium features"] += 1
                continue
            if h["email"] in keep:
                continue
            s["Could release"] += 1
            rows.append({"Person": h["email"], "Org unit": h["ou"], "License": sku_name(sku),
                         "Last sign-in": h["last"].isoformat() if h["last"] else "never",
                         "Premium use": "none seen", "sku": sku,
                         "args": ["user", h["email"], "delete", "license", sku]})
    summary = [{"License": sku_name(k), **v} for k, v in sorted(summ.items())]
    return summary, sorted(rows, key=lambda r: (r["License"], r["Person"]))
