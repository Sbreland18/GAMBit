"""'Explain this command': match a typed GAM command to GAM's syntax reference and
describe each part in plain English."""

from __future__ import annotations

import html
import re

from .command_catalog import Catalog, tokenize
from .gam_runner import split_command

KNOWN = {
    "user": "the next value is one person's email",
    "users": "the next value is a list of people (comma separated)",
    "group": "everyone in this group",
    "groups": "everyone in these groups",
    "ou": "everyone directly in this org unit (not sub-units)",
    "ou_and_children": "everyone in this org unit and all its sub-units",
    "all": "everyone – used as 'all users'",
    "cros_sn": "Chromebook(s) by serial number",
    "courses": "Classroom course(s)", "course": "a Classroom course",
    "print": "list the results as a table (CSV)", "show": "display the results",
    "info": "show details", "update": "change", "create": "create", "add": "add",
    "delete": "delete", "del": "delete", "remove": "remove", "sync": "make it match exactly",
    "doit": "really do it – without this GAM only previews",
    "todrive": "send the results to a Google Sheet",
    "query": "only items matching this search", "queries": "items matching any of these searches",
    "fields": "which columns to include", "csv": "run once for each row of a CSV file",
    "select": "use this section of gam.cfg (another domain/profile)",
    "redirect": "save the output to a file", "on": "turn on", "off": "turn off",
    "true": "yes", "false": "no", "changepassword": "make them choose a new password",
    "suspended": "account suspended (on) or active (off)", "password": "new password",
    "firstname": "first name", "lastname": "last name", "orgunitpath": "org unit",
    "org": "org unit", "maxresults": "how many to fetch at a time",
    "formatjson": "show the raw JSON", "countsonly": "just count, don't list",
    "allfields": "include every column", "limittoou": "only this org unit",
}


def _literals(c) -> tuple[set[str], dict[str, str], list[set[str]]]:
    toks = tokenize(c.syntax)
    lits: set[str] = set()
    next_ref: dict[str, str] = {}
    lead: list[set[str]] = []
    in_lead = True
    for i, t in enumerate(toks[1:], start=1):
        if t in ("[", "("):
            in_lead = False
        if t.startswith("<") or t in ("[", "]", "(", ")", "|", "|t", "*", "+") or \
                t.startswith('"'):
            continue
        words = [t]
        j = i
        while j + 2 < len(toks) and toks[j + 1] == "|t" and not toks[j + 2].startswith("<"):
            words.append(toks[j + 2])
            j += 2
        for w in words:
            lits.add(w.lower())
        if in_lead and toks[i - 1] != "|t":
            lead.append({w.lower() for w in words})
        k = j + 1
        if k < len(toks) and toks[k].startswith("<"):
            for w in words:
                next_ref.setdefault(w.lower(), toks[k].strip("<>"))
    return lits, next_ref, lead


def best_match(args: list[str], catalog: Catalog):
    low = [a.lower() for a in args]
    best, best_score = None, -1e9
    for c in catalog.commands:
        lits, _nr, lead = _literals(c)
        hits = sum(1 for a in low if a in lits)
        # leading keywords must appear in the same order
        lead_hits, j = 0, 0
        for opts in lead:
            pos = next((k for k in range(j, len(low)) if low[k] in opts), None)
            if pos is not None:
                lead_hits += 1
                j = pos + 1
        miss = len(lead) - lead_hits
        score = hits * 2 + lead_hits * 4 - miss * 6 - len(lits) * 0.01
        if score > best_score:
            best, best_score = c, score
    return best


def explain(text: str, catalog: Catalog) -> str:
    """HTML explanation of a GAM command line."""
    try:
        args = split_command(text)
    except ValueError as exc:
        return f"<p>Couldn't read the command: {html.escape(str(exc))}</p>"
    if not args:
        return "<p>Type a GAM command to explain.</p>"
    c = best_match(args, catalog)
    esc = html.escape
    out = []
    if c:
        out.append(f"<h3 style='margin:0'>{esc(c.description)}</h3>"
                   f"<p style='color:#57606a;margin-top:2px'>{esc(c.section)}</p>")
        lits, next_ref, _lead = _literals(c)
    else:
        lits, next_ref = set(), {}
    out.append("<table cellpadding='5' style='border-collapse:collapse'>")
    expect_value_for = None
    for a in args:
        la = a.lower()
        if expect_value_for:
            ref = expect_value_for
            body = catalog.defs.get(ref, "") if catalog else ""
            hint = f"<span style='color:#57606a'> ({esc(body[:90])})</span>" if body and \
                len(body) < 120 else ""
            meaning = f"value for <b>&lt;{esc(ref)}&gt;</b>{hint}"
            expect_value_for = None
        elif la in KNOWN:
            meaning = KNOWN[la]
            if la in next_ref:
                expect_value_for = next_ref[la]
        elif la in lits:
            meaning = "keyword"
            if la in next_ref:
                expect_value_for = next_ref[la]
                meaning = f"keyword – next comes <b>&lt;{esc(next_ref[la])}&gt;</b>"
        elif "@" in a:
            meaning = "an email address"
        elif a.startswith("/"):
            meaning = "an org unit path"
        elif re.match(r"^-?\d+[dwmyh]$", a):
            meaning = "a relative time (e.g. -7d = 7 days ago)"
        else:
            meaning = "value"
        out.append(f"<tr><td style='font-family:Consolas,monospace;background:#eef3fb'>"
                   f"{esc(a if a.lower() not in ('password',) else a)}</td>"
                   f"<td>{meaning}</td></tr>")
    out.append("</table>")
    if c:
        out.append("<p style='color:#57606a;margin-top:10px'>Closest match in GAM's reference:</p>"
                   f"<pre style='white-space:pre-wrap;font-size:9pt'>{esc(c.syntax)}</pre>")
    return "".join(out)
