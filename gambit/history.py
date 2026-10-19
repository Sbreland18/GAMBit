"""Ask about history: find what happened in GAMbit's activity log and background-task log
for a plain-English question ("what did we change for jsmith last week?", "why did last
night's sync fail?"). The search runs on this PC; only if you press "Explain" are the
matching lines sent to Claude."""

from __future__ import annotations

import datetime
import re

STOP = {"what", "did", "we", "change", "changed", "for", "the", "last", "this", "week",
        "night", "nights", "yesterday", "today", "why", "who", "when", "how", "many", "fail",
        "failed", "fails", "happen", "happened", "to", "a", "an", "of", "in", "on", "was",
        "were", "is", "are", "and", "or", "all", "any", "do", "does", "show", "me", "with",
        "our", "my", "has", "have", "been", "month", "days", "day", "ago", "s", "it", "get",
        "got", "make", "made", "run", "ran", "since", "about", "from", "by"}
TASK_WORDS = {"sync": "sync", "roster": "sync", "digest": "digest", "groups": "groups",
              "signature": "signatures", "signatures": "signatures", "guardian": "guardians",
              "guardians": "guardians", "cleanup": "cleanup", "clean": "cleanup",
              "device": "devicesync", "assignment": "devicesync", "requests": "requests",
              "approval": "requests", "daily": "daily", "watch": "watchdog",
              "unusual": "watchdog", "report": "schoolreports", "reports": "schoolreports"}


def time_range(q: str, now: datetime.datetime | None = None):
    """(start, end) datetimes for words like yesterday / last night / last week."""
    now = now or datetime.datetime.now()
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    t = q.lower()
    if "last night" in t or "overnight" in t:
        return day0 - datetime.timedelta(hours=6), day0 + datetime.timedelta(hours=8)
    if "yesterday" in t:
        return day0 - datetime.timedelta(days=1), day0
    if "today" in t or "this morning" in t:
        return day0, now + datetime.timedelta(minutes=1)
    if "this week" in t:
        return day0 - datetime.timedelta(days=day0.weekday()), now
    if "last week" in t:
        start = day0 - datetime.timedelta(days=day0.weekday() + 7)
        return start, start + datetime.timedelta(days=7)
    if "this month" in t:
        return day0.replace(day=1), now
    if "last month" in t:
        first = day0.replace(day=1)
        prev = (first - datetime.timedelta(days=1)).replace(day=1)
        return prev, first
    m = re.search(r"(?:last|past)\s+(\d+)\s+days?", t)
    if m:
        return now - datetime.timedelta(days=int(m.group(1))), now
    return now - datetime.timedelta(days=30), now


def terms(q: str) -> list[str]:
    emails = re.findall(r"[\w.+'-]+@[\w.-]+", q.lower())
    rest = re.sub(r"[\w.+'-]+@[\w.-]+", " ", q.lower())
    words = [re.sub(r"'s$", "", w).strip(".'-") for w in
             re.findall(r"[a-z0-9][a-z0-9._'-]*", rest)]
    return emails + [w for w in words
                     if w and w not in STOP and w not in TASK_WORDS and len(w) > 1]


def wants_failures(q: str) -> bool:
    return bool(re.search(r"\bfail|error|didn'?t work|broke|wrong", q.lower()))


def task_keys(q: str) -> set[str]:
    return {v for k, v in TASK_WORDS.items() if re.search(rf"\b{k}", q.lower())}


def find(q: str, entries: list[dict], task_log: dict | None = None,
         now: datetime.datetime | None = None) -> dict:
    """→ {"activity": [entries], "tasks": [(key, time, line)], "range": (s, e), "terms": [...]}"""
    start, end = time_range(q, now)
    s_iso, e_iso = start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")
    ts = terms(q)
    fails = wants_failures(q)
    acts = []
    for e in entries:
        t = e.get("time", "")
        if not (s_iso <= t <= e_iso):
            continue
        text = (e.get("command", "") + " " + e.get("note", "") + " " + e.get("who", "")).lower()
        if ts and not all(any(x in text for x in _variants(w)) for w in ts):
            continue
        if fails and e.get("code") in (0, None):
            continue
        acts.append(e)
    acts.sort(key=lambda e: e.get("time", ""), reverse=True)
    lines = []
    keys = task_keys(q)
    for key, info in (task_log or {}).items():
        base = key.split(":")[0]
        if keys and base not in keys:
            continue
        if not keys and not fails and not ts:
            continue
        for ln in info.get("all", info.get("lines", [])):
            when, msg = (ln if isinstance(ln, tuple) else (info.get("last", ""), ln))
            if when and not (s_iso.replace("T", " ") <= when <= e_iso.replace("T", " ")):
                continue
            low = msg.lower()
            if fails and not ("fail" in low or "error" in low or "couldn't" in low or "⚠" in msg):
                continue
            if ts and keys == set() and not any(any(x in low for x in _variants(w)) for w in ts):
                continue
            lines.append((key, when, msg))
    lines.sort(key=lambda x: x[1], reverse=True)
    return {"activity": acts[:500], "tasks": lines[:300], "range": (start, end), "terms": ts}


def _variants(w: str) -> list[str]:
    """jsmith → jsmith, jsmith@ ; 'smith' matches emails containing it."""
    return [w]


def read_task_log(path: str = "") -> dict:
    """All lines of the background-task log, grouped by task: {key: {"all": [(time, msg)]}}"""
    if not path:
        import os
        from .support import logs_dir
        path = os.path.join(logs_dir(), "tasks.log")
    pat = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \[([^\]]+)\] (.*)$")
    out: dict = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-20000:]
    except OSError:
        return out
    for ln in lines:
        m = pat.match(ln.rstrip("\n"))
        if m:
            t, key, msg = m.groups()
            out.setdefault(key, {"all": []})["all"].append((t, msg))
    return out


def as_text(res: dict, limit: int = 120) -> str:
    """Compact text of the matches (what "Explain" sends)."""
    out = []
    for e in res["activity"][:limit]:
        out.append(f"{e.get('time', '')} {e.get('who', '')} "
                   f"[{'ok' if e.get('code') == 0 else 'FAILED ' + str(e.get('code'))}] "
                   f"{e.get('command', '')}" + (f"  ({e['note']})" if e.get("note") else ""))
    for key, when, msg in res["tasks"][:limit]:
        out.append(f"{when} [task {key}] {msg}")
    return "\n".join(out)
