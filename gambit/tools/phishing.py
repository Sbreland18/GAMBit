"""Pull a phishing email out of every mailbox.

1. Build a Gmail search from the sender, subject and/or a link in the message.
2. Count which mailboxes have it (read-only).
3. After approval, move every copy to the trash.
4. See who replied to the sender (their Sent mail), so those people can be checked.
"""

from __future__ import annotations

import datetime
import json
import os
import re

GMAIL_RE = re.compile(r"[\"\\]")


def _q(v: str) -> str:
    v = GMAIL_RE.sub("", (v or "").strip())
    return f'"{v}"' if " " in v else v


def query(sender: str = "", subject: str = "", link: str = "", days: int = 7,
          extra: str = "") -> str:
    parts = []
    if sender.strip():
        parts.append(f"from:{_q(sender)}")
    if subject.strip():
        parts.append(f"subject:{_q(subject)}")
    if link.strip():
        host = re.sub(r"^https?://", "", link.strip()).split("/")[0]
        parts.append(_q(host or link))
    if not parts:
        raise ValueError("Give at least the sender, the subject or a link from the message.")
    parts.append(f"newer_than:{max(1, int(days))}d")
    if extra.strip():
        parts.append(extra.strip())
    return " ".join(parts)


def entity(scope: str, ou: str = "") -> list[str]:
    if scope == "ou" and ou:
        return ["ou_and_children_ns", ou]
    return ["all", "users_ns"]


def count_args(ent: list[str], q: str) -> list[str]:
    return [*ent, "print", "messages", "query", q, "positivecountsonly"]


def trash_args(ent: list[str], q: str, per_mailbox: int = 50) -> list[str]:
    return [*ent, "trash", "messages", "query", q, "doit", "max_to_trash", str(per_mailbox)]


def replies_args(ent: list[str], sender: str, days: int = 7) -> list[str]:
    return [*ent, "print", "messages", "query",
            f"in:sent to:{_q(sender)} newer_than:{max(1, int(days))}d", "positivecountsonly"]


def counts(rows: list[dict]) -> list[dict]:
    """GAM count rows → [{mailbox, count}] (column names vary between GAM versions)."""
    out = []
    for r in rows:
        low = {(k or "").lower(): (v or "") for k, v in r.items()}
        who = low.get("user") or low.get("email") or low.get("primaryemail") or ""
        n = next((low[k] for k in ("messages", "count", "messagecount", "total")
                  if str(low.get(k, "")).isdigit()), "")
        if not n:
            n = next((v for k, v in low.items() if k not in ("user", "email") and
                      str(v).isdigit()), "0")
        if who and int(n or 0) > 0:
            out.append({"mailbox": who.lower(), "count": int(n)})
    out.sort(key=lambda x: (-x["count"], x["mailbox"]))
    return out


def incident_text(q: str, found: list[dict], replied: list[dict]) -> str:
    total = sum(x["count"] for x in found)
    lines = [f"Phishing clean-up – {datetime.datetime.now():%Y-%m-%d %H:%M}",
             f"Search: {q}", f"Found {total} message(s) in {len(found)} mailbox(es)."]
    if replied:
        lines.append(f"{len(replied)} person(s) replied to the sender – check these accounts:")
        lines += [f"  • {r['mailbox']}" for r in replied[:50]]
    return "\n".join(lines)


def log_path() -> str:
    from .. import team
    if team.folder():
        d = os.path.join(team.folder(), "incidents")
    else:
        from ..support import logs_dir
        d = os.path.join(os.path.dirname(logs_dir()), "incidents")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "phishing.jsonl")


def record(q: str, found: list[dict], replied: list[dict], action: str, who: str):
    with open(log_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"time": datetime.datetime.now().isoformat(timespec="seconds"),
                             "query": q, "mailboxes": len(found),
                             "messages": sum(x["count"] for x in found),
                             "replied": [r["mailbox"] for r in replied], "action": action,
                             "by": who}) + "\n")
