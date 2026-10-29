"""Next-year forecast: roll every student up a grade, move the top grade of each school to
the school it feeds (or graduate them), add an estimated kindergarten class, then compare
each school's projected enrollment with the Chromebooks that will still get updates next
year and the student licenses on hand."""

from __future__ import annotations

import datetime
import json
import re
from collections import defaultdict

from .settings import settings


def options() -> dict:
    try:
        o = json.loads(settings.get("nextyear/options", "{}") or "{}")
    except ValueError:
        o = {}
    return {"student_root": "/Students", "feeds": "", "kinder": "", "ratio": 1.0,
            "spare_pct": 5, "student_licenses": 0, **o}


def save_options(o: dict):
    settings.set("nextyear/options", json.dumps(o))


def parse_map(text: str) -> dict[str, str]:
    """Lines like  'Lincoln Elementary = Grant Middle'  (or '->', ':')."""
    out = {}
    for ln in (text or "").splitlines():
        m = re.match(r"\s*(.+?)\s*(?:=|->|→|:)\s*(.+?)\s*$", ln)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def school_year_end(today: datetime.date | None = None) -> int:
    today = today or datetime.date.today()
    return today.year + 1 if today.month >= 7 else today.year


def grade_of(ou: str, year_end: int):
    """Find a grade in any OU part: 'Grade 5', '05', 'K', 'Kindergarten', 'Class of 2031'."""
    from .sis import grade_number
    for part in reversed([p for p in (ou or "").split("/") if p]):
        p = part.strip()
        m = re.search(r"(?:class of|grad(?:uating)?|cohort)?\s*((?:19|20)\d\d)\b", p, re.I)
        if m:
            g = 12 - (int(m.group(1)) - year_end)
            if -1 <= g <= 12:
                return g
        low = p.lower()
        if low in ("kindergarten", "kinder"):
            return 0
        if low in ("pre-k", "prek", "pre-kindergarten", "pk"):
            return -1
        m = re.match(r"^(?:grade|gr\.?|g)?\s*(\d{1,2}|k|pk)(?:st|nd|rd|th)?(?:\s*grade)?$", low)
        if m:
            n = grade_number(m.group(1))
            if n is not None and -1 <= n <= 12:
                return n
    return None


def project(users: list[dict], opts: dict, year_end: int) -> tuple[list[dict], dict]:
    """→ (rows per school, info) using students' OUs."""
    from .parent_report import school_of
    root = opts.get("student_root", "/Students")
    rl = root.rstrip("/").lower()
    feeds = parse_map(opts.get("feeds", ""))
    kinder = {k: int(v) for k, v in parse_map(opts.get("kinder", "")).items()
              if str(v).strip().isdigit()}
    now = defaultdict(lambda: defaultdict(int))
    unknown = 0
    for u in users:
        if u.get("suspended") or not (u.get("ou") or "").lower().startswith(rl + "/"):
            continue
        g = grade_of(u["ou"], year_end)
        sch = school_of(u["ou"], root)
        if g is None:
            unknown += 1
            now[sch][None] += 1
            continue
        now[sch][g] += 1
    top = {s: max([g for g in gs if g is not None], default=None) for s, gs in now.items()}
    low = {s: min([g for g in gs if g is not None], default=None) for s, gs in now.items()}
    nxt = defaultdict(int)
    leaving, graduating = defaultdict(int), 0
    for sch, gs in now.items():
        for g, n in gs.items():
            if g is None:
                nxt[sch] += n          # can't tell – assume they stay
                continue
            if g >= 12:
                graduating += n
                continue
            if top[sch] is not None and g == top[sch] and sch in feeds:
                nxt[feeds[sch]] += n
                leaving[sch] += n
            else:   # includes a top grade with no feed set – kept here, flagged below
                nxt[sch] += n
    for sch, n in kinder.items():
        nxt[sch] += n
    for sch, gs in now.items():          # no estimate given: repeat this year's K class
        if sch not in kinder and low.get(sch) in (0, -1):
            nxt[sch] += gs.get(low[sch], 0)
    rows = []
    for sch in sorted(set(now) | set(nxt)):
        cur = sum(now[sch].values()) if sch in now else 0
        rows.append({"School": sch, "This year": cur, "Next year": nxt.get(sch, 0),
                     "Change": nxt.get(sch, 0) - cur,
                     "Grades": (f"{_g(low.get(sch))}–{_g(top.get(sch))}"
                                if top.get(sch) is not None else "?"),
                     "Moving on": leaving.get(sch, 0),
                     "Note": "" if sch in feeds or top.get(sch) in (12, None) or
                     sch not in now else "set where its top grade goes next year"})
    info = {"graduating": graduating, "unknown_grade": unknown}
    return rows, info


def _g(n):
    return {0: "K", -1: "PK"}.get(n, str(n))


def devices_next_year(devs: list[dict], user_school: dict, opts: dict,
                      year_end: int) -> dict[str, int]:
    """Active Chromebooks per school that will still get updates through next June."""
    from .tools.budget import options as bopts, school_of_device
    b = bopts()
    cut = datetime.date(year_end + 1, 6, 30)
    out = defaultdict(int)
    for d in devs:
        if d.get("status", "ACTIVE") != "ACTIVE":
            continue
        if d.get("aue") and d["aue"] < cut:
            continue
        out[school_of_device(d, b.get("device_root", ""), int(b.get("school_depth", 1) or 1),
                             user_school)] += 1
    return dict(out)


def plan(rows: list[dict], usable: dict[str, int], opts: dict, cost: float) -> list[dict]:
    ratio = float(opts.get("ratio", 1.0) or 1.0)
    spare = float(opts.get("spare_pct", 5) or 0) / 100
    out = []
    for r in rows:
        need = int(round(r["Next year"] * ratio * (1 + spare)))
        have = usable.get(r["School"], 0)
        short = max(need - have, 0)
        out.append({**r, "Chromebooks needed": need, "Still supported": have,
                    "To buy": short, "Cost": round(short * cost)})
    if out:
        tot = {k: sum(x[k] for x in out) for k in ("This year", "Next year", "Change",
                                                    "Moving on", "Chromebooks needed",
                                                    "Still supported", "To buy", "Cost")}
        out.append({"School": "All schools", "Grades": "", "Note": "", **tot})
    return out


def licenses(rows: list[dict], opts: dict) -> dict:
    total = next((r["Next year"] for r in rows if r["School"] == "All schools"),
                 sum(r["Next year"] for r in rows))
    have = int(opts.get("student_licenses", 0) or 0)
    return {"students_next_year": total, "licenses_on_hand": have,
            "licenses_short": max(total - have, 0) if have else 0}


# ================================================ year-end rollover plan ===
def rollover_grade(ou: str):
    """The grade a rollover org unit holds ('Grade 5', '05', 'K'…), or None. 'Class of 2031'
    style names don't count – their students don't move between org units each year."""
    last = [p for p in (ou or "").split("/") if p]
    if not last or re.search(r"(?:19|20)\d\d", last[-1]):
        return None
    return grade_of("/" + last[-1], school_year_end())


def pair_by_grade(kids: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Pair sibling grade org units by grade number (K→1, 1→2 … 9→10, never alphabetically,
    where '10' sorts before '9'). Returns (pairs, org units it couldn't place). The top grade
    gets an empty 'To' for the graduates' org unit."""
    by_grade: dict[int, str] = {}
    odd: list[str] = []
    for k in kids:
        g = rollover_grade(k)
        if g is None or g in by_grade:
            odd.append(k)
        else:
            by_grade[g] = k
    grades = sorted(by_grade)
    pairs = []
    for g in grades:
        if g + 1 in by_grade:
            pairs.append((by_grade[g], by_grade[g + 1]))
        elif g == grades[-1]:
            pairs.append((by_grade[g], ""))
        else:
            odd.append(by_grade[g])         # a gap (no grade g+1) – the tech decides
    return pairs, odd


def rollover_plan(pairs: list[tuple[str, str]], suspend_last: bool):
    """Turn From → To rows into ordered steps: [(label, args, required)], problem.

    Safe by construction:
      • rows between two grade org units must go up exactly one grade;
      • a destination is emptied before anyone moves into it (so nobody moves twice) –
        a loop of moves is refused;
      • every move is required: if one fails, nothing after it runs (a half-done rollover
        must never go on to suspend the wrong people);
      • “suspend graduates” only targets the one destination that isn't a grade."""
    norm = [((a or "").rstrip("/") or "/", (b or "").rstrip("/") or "/") for a, b in pairs
            if a and b]
    if len(norm) != len([p for p in pairs if p[0] or p[1]]):
        return [], "Every row needs both a From and a To org unit."
    srcs = [a for a, _b in norm]
    if len(set(x.lower() for x in srcs)) != len(srcs):
        return [], "The same From org unit is on more than one row."
    for a, b in norm:
        if a.lower() == b.lower():
            return [], f"{a} is moved into itself."
        ga, gb = rollover_grade(a), rollover_grade(b)
        if ga is not None and gb is not None and gb != ga + 1:
            return [], (f"{a} → {b} doesn't go up exactly one grade. Check the rows "
                        "(students would skip or repeat a grade).")
    # order: a move whose destination is still someone's source must wait
    todo, order = list(norm), []
    while todo:
        pending = {a.lower() for a, _b in todo}
        ready = [p for p in todo if p[1].lower() not in pending]
        if not ready:
            return [], "These rows move students in a circle – remove one of them."
        for p in ready:
            order.append(p)
            todo.remove(p)
    steps = [(f"{a}  →  {b}", ["update", "ou", b, "move", "ou", a], True) for a, b in order]
    if suspend_last:
        sinks = [b for _a, b in norm if b.lower() not in {s.lower() for s in srcs}]
        grads = [b for b in sinks if rollover_grade(b) is None]
        if len(grads) != 1:
            return [], ("“Suspend graduates” needs exactly one row that moves the top grade "
                        "into a graduates org unit (for example /Students/Graduated).")
        steps.append((f"Suspend everyone in {grads[0]}",
                      ["ou", grads[0], "update", "user", "suspended", "on"], True))
    return steps, ""
