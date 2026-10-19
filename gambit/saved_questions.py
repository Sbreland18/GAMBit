"""Scheduled questions: save an Ask GAMbit look-up (“students at Lincoln who haven't signed in
this week”) and get the answer by email every day, week or month. Each run uses the same
read-only look-up as Tools → Ask GAMbit."""

from __future__ import annotations

import datetime
import json
import uuid

from .settings import settings

TASK = {"name": "GAMbit scheduled questions", "args": ["--task", "questions"],
        "freq": "daily", "time": "06:30",
        "what": "Answers saved Ask GAMbit questions and emails them", "standard": False}
EVERY = {"daily": "Every day", "weekly": "Every Monday", "monthly": "1st of the month"}


def load() -> list[dict]:
    from . import team
    if team.folder():
        d = team.read_shared("saved_questions.json")
        if d:
            return d.get("questions", [])
    try:
        return json.loads(settings.get("questions/list", "[]") or "[]")
    except ValueError:
        return []


def save(qs: list[dict]):
    from . import team
    if team.folder():
        team.write_shared("saved_questions.json", {"questions": qs})
    settings.set("questions/list", json.dumps(qs))


def new(question: str, every: str, to: str, who: str) -> dict:
    return {"id": uuid.uuid4().hex[:8], "question": question.strip(), "every": every,
            "to": to.strip(), "by": who, "last_run": "", "last_answer": "", "on": True}


def is_due(q: dict, today: datetime.date | None = None) -> bool:
    today = today or datetime.date.today()
    if not q.get("on", True) or q.get("last_run", "")[:10] == today.isoformat():
        return False
    ev = q.get("every", "weekly")
    return ev == "daily" or (ev == "weekly" and today.weekday() == 0) or \
        (ev == "monthly" and today.day == 1)


def email_body(q: dict, res: dict) -> str:
    from .gam_runner import display_command
    cmds = "\n".join(f"  {display_command(a)}" for a, _ok, _o in res.get("commands", []))
    return (f"{res.get('answer') or '(no answer)'}\n\n—\nQuestion: {q['question']}\n"
            f"Asked {EVERY.get(q.get('every'), '')} by GAMbit for {q.get('by', '')}.\n"
            f"Read-only commands it ran:\n{cmds or '  (none)'}\n")


def run_one(q: dict, run=None, http=None, send=None) -> dict:
    from .integrations import assistant
    res = assistant.lookup(q["question"], None, http=http, run=run)
    q["last_run"] = datetime.datetime.now().isoformat(timespec="minutes")
    q["last_answer"] = (res.get("answer") or "")[:2000]
    if "@" in q.get("to", ""):
        (send or _send)(q["to"], f"GAMbit: {q['question'][:70]}", email_body(q, res))
    return res


def _send(to, subject, body):
    from . import google_io
    google_io.send_email(to, subject, body)


def run(log=print, today=None, run=None, http=None, send=None) -> list[str]:
    from .integrations import assistant
    cfg = assistant.config()
    qs = load()
    due = [q for q in qs if is_due(q, today)]
    if not due:
        return []
    if not cfg["key"]:
        log("Scheduled questions need the Claude API key (Settings → Integrations).")
        return []
    if run is None:
        from .directory import run_gam_text
        run = lambda a: run_gam_text(a, 600)  # noqa: E731
    lines = []
    for q in due:
        try:
            run_one(q, run, http, send)
            lines.append(f"Answered “{q['question'][:60]}” → {q.get('to') or 'saved'}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"“{q['question'][:60]}” failed: {exc}")
    save(qs)
    for ln in lines:
        log(ln)
    return lines
