"""“Ask GAMbit”: turn a plain-English request into GAM commands with Claude (Anthropic API).

Nothing is run by the assistant. It only proposes commands, which GAMbit shows for review
and then runs through the normal path (roles, dry run, big-change preview, activity log).
By default only your org-unit paths, group addresses and domain go to the API – never user
lists – plus whatever you type yourself.
"""

from __future__ import annotations

import json
import os
import re

from ..settings import settings

API = "https://api.anthropic.com/v1"
DEFAULT_MODEL = "claude-sonnet-4-5"

SYSTEM = """You are the command assistant inside GAMbit, a Windows app that runs GAM7 (the
Google Workspace admin command-line tool) for a K-12 school district.

Turn the admin's request into GAM7 commands. Rules:
- Use only syntax that appears in the reference below, or that you are certain GAM7 accepts.
- Never invent org units, groups or users; use the ones given, or a clearly marked
  placeholder like <student email>.
- Prefer the smallest safe change. For anything that changes many accounts, first give a
  read-only "print" command so they can check who is affected.
- Never delete accounts or wipe devices unless explicitly asked.
- Commands are argument lists WITHOUT the leading "gam".

Reply with JSON only, no prose around it:
{"explanation": "<two or three plain sentences>",
 "commands": [{"args": ["print", "users", "..."], "why": "<short reason>"}],
 "warnings": ["<anything risky or uncertain>"]}"""


def config() -> dict:
    return {"key": (settings.get("assistant/api_key", "") or
                    os.environ.get("ANTHROPIC_API_KEY", "")).strip(),
            "model": (settings.get("assistant/model", "") or DEFAULT_MODEL).strip(),
            "enabled": bool(settings.get("assistant/enabled", False)),
            "share_users": bool(settings.get("assistant/share_users", False))}


def _headers(key: str) -> dict:
    return {"x-api-key": key, "anthropic-version": "2023-06-01",
            "content-type": "application/json"}


def list_models(cfg=None, http=None) -> list[str]:
    from .. import net
    cfg = cfg or config()
    status, _h, body = (http or net.request)("GET", f"{API}/models?limit=100",
                                             _headers(cfg["key"]))
    if status >= 400:
        raise RuntimeError(f"Anthropic returned {status}: {body[:200].decode('utf-8', 'replace')}")
    return [m.get("id", "") for m in json.loads(body).get("data", []) if m.get("id")]


_CAT = None


def reference(request: str, limit: int = 25) -> str:
    """Relevant lines from GAM's own syntax reference."""
    try:
        global _CAT
        from ..command_catalog import Catalog
        cat = _CAT = _CAT or Catalog()
        words = " ".join(w for w in re.findall(r"[a-z0-9]+", request.lower()) if len(w) > 2)
        hits = cat.search(words, limit=limit)
        return "\n".join(c.syntax[:400] for c in hits[:limit])
    except Exception:  # noqa: BLE001
        return ""


def context(directory, share_users: bool = False) -> str:
    parts = [f"Domain: {getattr(directory, 'domain', '') or 'unknown'}"]
    ous = [o if isinstance(o, str) else o.get("path", "") for o in
           (getattr(directory, "ous", []) or [])][:300]
    if ous:
        parts.append("Org units:\n" + "\n".join(ous))
    groups = [g.get("email", "") for g in (getattr(directory, "groups", []) or [])][:300]
    if groups:
        parts.append("Groups:\n" + "\n".join(groups))
    if share_users:
        users = [f"{u.get('email', '')} ({u.get('ou', '')})" for u in
                 (getattr(directory, "users", []) or [])][:500]
        parts.append("Some users:\n" + "\n".join(users))
    return "\n\n".join(parts)


def build_messages(request: str, ctx: str, ref: str) -> list[dict]:
    return [{"role": "user", "content":
             f"GAM syntax reference (excerpt):\n{ref}\n\nThis district:\n{ctx}\n\n"
             f"Request: {request}"}]


def parse_reply(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise RuntimeError("The assistant didn't return commands. Try rewording the request.")
    data = json.loads(m.group(0))
    cmds = []
    for c in data.get("commands", []) or []:
        args = c.get("args") if isinstance(c, dict) else c
        if isinstance(args, str):
            from ..gam_runner import split_command
            args = split_command(args)
        if not isinstance(args, list) or not args:
            continue
        args = [str(a) for a in args]
        if args[0].lower() in ("gam", "gam.exe"):
            args = args[1:]
        cmds.append({"args": args, "why": (c.get("why", "") if isinstance(c, dict) else "")})
    return {"explanation": data.get("explanation", ""), "commands": cmds,
            "warnings": [str(w) for w in data.get("warnings", []) or []]}


def _complete(system: str, content: str, cfg=None, http=None, max_tokens: int = 1500) -> str:
    from .. import net
    cfg = cfg or config()
    if not cfg["key"]:
        raise RuntimeError("Add an Anthropic API key in Settings → Integrations first.")
    body = {"model": cfg["model"], "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": content}]}
    status, _h, data = (http or net.request)("POST", f"{API}/messages", _headers(cfg["key"]),
                                             body, timeout=120)
    if status >= 400:
        try:
            msg = json.loads(data).get("error", {}).get("message", "")
        except ValueError:
            msg = data[:200].decode("utf-8", "replace")
        raise RuntimeError(f"Anthropic returned {status}: {msg}")
    reply = json.loads(data)
    return "".join(b.get("text", "") for b in reply.get("content", []) if b.get("type") == "text")


def ask(request: str, directory=None, cfg=None, http=None) -> dict:
    cfg = cfg or config()
    msgs = build_messages(request, context(directory, cfg["share_users"]), reference(request))
    return parse_reply(_complete(SYSTEM, msgs[0]["content"], cfg, http))


# ------------------------------------------------------------ history ---
HISTORY_SYSTEM = """You help a school district IT admin understand what happened in GAMbit,
a Windows app that runs GAM7 (Google Workspace admin tool). You get their question and the
matching lines from GAMbit's activity log and background-task log. Answer in plain English
in a few short sentences or bullets: what happened, when, who did it, and – for failures –
the likely cause and what to try next. Only use what is in the lines; if they don't answer
the question, say so."""


def pseudonymize(text: str) -> str:
    """People's addresses replaced by stable placeholders (person1@…, person2@…) so log
    lines can be explained without sending who they are; passwords are always hidden."""
    from ..gam_runner import hide_text_passwords
    seen: dict[str, str] = {}

    def sub(m):
        e = m.group(0).lower()
        if e not in seen:
            seen[e] = f"person{len(seen) + 1}@{e.split('@', 1)[1]}"
        return seen[e]
    text = "\n".join(hide_text_passwords(ln) for ln in (text or "").splitlines())
    return re.sub(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+", sub, text)


def explain_history(question: str, lines: str, cfg=None, http=None) -> str:
    if not lines.strip():
        return "Nothing in the logs matched, so there's nothing to explain."
    cfg = cfg or config()
    if not cfg.get("share_users"):
        question, _sep, lines = pseudonymize(f"{question}\n\x00\n{lines}").partition(
            "\n\x00\n")
    return _complete(HISTORY_SYSTEM, f"Question: {question}\n\nLog lines:\n{lines[:60000]}",
                     cfg, http, 900).strip()


# ------------------------------------------------------------ drafting ---
WORKFLOW_SYSTEM = """You draft "My workflows" for GAMbit, a Windows app that runs GAM7 for a
K-12 school district. A workflow has fill-in fields and ordered steps; each step is one GAM7
command (without the leading "gam") that may use {field_key} placeholders, plus the built-ins
{password} (a fresh random password) and {today} (YYYY-MM-DD).
Use only GAM7 syntax you are certain of (see the reference). Use the org units and groups
given; never invent them – make them fields instead. Keep it to the fewest steps.
Reply with JSON only:
{"name": "...", "description": "...",
 "fields": [{"key": "email", "label": "New email", "default": ""}],
 "steps": [{"label": "Create the account", "command": "create user {email} ..."}]}"""

RULE_SYSTEM = """You turn a plain-English clean-up policy into a GAMbit clean-up rule.
Kinds: "inactive" = suspend accounts with no sign-in for N days; "delete_old" = delete
suspended accounts with no sign-in for N days; "release" = release licenses from suspended
accounts. Use an org unit from the list given ("/" for everyone).
Reply with JSON only:
{"name": "...", "kind": "inactive|delete_old|release", "ou": "/Students", "days": 180,
 "include_never": false, "max": 200, "except": ""}"""


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise RuntimeError("The assistant didn't return a draft. Try rewording it.")
    return json.loads(m.group(0))


def draft_workflow(text: str, directory=None, cfg=None, http=None) -> dict:
    cfg = cfg or config()
    content = (f"GAM syntax reference (excerpt):\n{reference(text)}\n\nThis district:\n"
               f"{context(directory, False)}\n\nWorkflow to draft: {text}")
    d = _json(_complete(WORKFLOW_SYSTEM, content, cfg, http, 1800))
    fields = [{"key": re.sub(r"[^a-z0-9_]", "_", str(f.get("key", "")).lower()).strip("_"),
               "label": str(f.get("label", "") or f.get("key", "")),
               "default": str(f.get("default", "") or "")}
              for f in d.get("fields", []) if isinstance(f, dict) and f.get("key")]
    steps = []
    for s in d.get("steps", []):
        if not isinstance(s, dict):
            continue
        cmd = s.get("command") or s.get("args") or ""
        if isinstance(cmd, list):
            from ..gam_runner import display_command
            cmd = display_command([str(a) for a in cmd])[4:]
        cmd = re.sub(r"^\s*gam(\.exe)?\s+", "", str(cmd))
        if cmd.strip():
            steps.append({"label": str(s.get("label", "") or cmd[:40]), "command": cmd.strip()})
    return {"name": str(d.get("name", "") or "New workflow"),
            "description": str(d.get("description", "") or ""), "fields": fields,
            "steps": steps}


def draft_rule(text: str, directory=None, cfg=None, http=None) -> dict:
    cfg = cfg or config()
    content = f"This district:\n{context(directory, False)}\n\nPolicy: {text}"
    d = _json(_complete(RULE_SYSTEM, content, cfg, http, 600))
    kind = d.get("kind") if d.get("kind") in ("inactive", "delete_old", "release") \
        else "inactive"
    try:
        days = max(1, int(d.get("days", 180) or 180))
        cap = max(1, int(d.get("max", 200) or 200))
    except (TypeError, ValueError):
        days, cap = 180, 200
    return {"name": str(d.get("name", "") or text[:40]), "kind": kind,
            "ou": str(d.get("ou", "/") or "/"), "days": days,
            "include_never": bool(d.get("include_never", False)), "max": cap,
            "except": str(d.get("except", "") or ""), "enabled": True}


# ------------------------------------------------------------ look-ups ---
LOOKUP_SYSTEM = """You answer a K-12 district IT admin's question about their Google Workspace
by running READ-ONLY GAM7 commands with the run_gam_readonly tool, then answering in plain
English (short sentences or a short list; include the key emails/serials). Rules:
- Only print / show / info / report commands. Anything that changes something is refused.
- Prefer narrow commands (a query, a single user, one org unit, specific fields) so results
  are small. Use the syntax reference and the district's org units and groups given.
- Use at most 6 commands. If you can't find the answer, say what you tried.
- Never ask the admin to run anything; just answer."""
READ_VERBS = {"print", "show", "info", "report"}
BLOCKED = {"todrive", "sendemail", "redirect", "config", "csv", "batch", "tbatch", "loop",
           "oauth", "update", "create", "delete", "add", "remove", "sync", "wipe", "undelete",
           "signout", "deprovision", "transfer", "move", "suspend", "get", "download", "copy",
           "archive", "untrash", "trash", "issuecommand", "collect", "process", "empty",
           "purge", "cancel", "clear", "csvfile", "file", "gdoc", "gcsdoc", "gsheet",
           "write", "upload", "import", "export", "takeout"}
TOOLS = [{"name": "run_gam_readonly",
          "description": "Run one read-only GAM7 command (print/show/info/report) and get its "
                         "output (CSV or text, truncated if long). Do not include 'gam'.",
          "input_schema": {"type": "object",
                           "properties": {"args": {"type": "array", "items": {"type": "string"},
                                                   "description": "GAM arguments, e.g. "
                                                                  "[\"print\",\"users\",...]"},
                                          "why": {"type": "string"}},
                           "required": ["args"]}}]


# Never run for the AI, even as a look-up: anything that reads mail or file *contents*,
# saves files on this PC, or switches GAM's configuration.
CONTENT = {"messages", "message", "thread", "threads", "showbody", "saveattachments",
           "attachments", "attachment", "targetfolder", "targetname", "save", "select",
           "selectfilter", "showsections", "drivefile", "drivefiles", "filecontent",
           "fileshare", "verify", "multiprocessexit", "showparticipants", "chatmessages",
           "chatmessage", "notes", "vault", "vaultholds", "exports", "export"}
ALLOWED_VERBS = {"print", "show", "info", "report"}


def readonly(args: list[str]) -> bool:
    """Allowlist: a plain print/show/info/report (no wrappers, no GAM settings, no mail or
    file contents) – the only thing the AI may run without a person."""
    from ..activity import is_change, verb_index
    low = [str(a).lower() for a in args]
    if low[:1] in (["gam"], ["gam.exe"]):
        low = low[1:]
        args = list(args)[1:]
    if not low or set(low) & (BLOCKED | CONTENT):
        return False
    if any(x.startswith(("-", "\\\\", "//")) or ":\\" in x or "/" in x[:1] and
           x.count("/") > 6 for x in low):
        return False                  # options or paths a look-up doesn't need
    vi = verb_index(low)
    if vi >= len(low) or low[vi] not in ALLOWED_VERBS:
        return False
    return not is_change(list(args))


def lookup(question: str, directory=None, cfg=None, http=None, run=None, on_step=None,
           max_steps: int = 6) -> dict:
    """→ {"answer": str, "commands": [(args, ok, rows/lines)]}"""
    from .. import net
    cfg = cfg or config()
    if not cfg["key"]:
        raise RuntimeError("Add an Anthropic API key in Settings → Integrations first.")
    if run is None:
        from ..directory import run_gam_text
        run = lambda a: run_gam_text(a, 600)  # noqa: E731
    msgs = [{"role": "user", "content":
             f"GAM syntax reference (excerpt):\n{reference(question)}\n\nThis district:\n"
             f"{context(directory, cfg['share_users'])}\n\nQuestion: {question}"}]
    done_cmds = []
    for _step in range(max_steps + 1):
        body = {"model": cfg["model"], "max_tokens": 1500, "system": LOOKUP_SYSTEM,
                "messages": msgs, "tools": TOOLS}
        if len(done_cmds) >= max_steps:
            body["tool_choice"] = {"type": "none"}
        status, _h, data = (http or net.request)("POST", f"{API}/messages", _headers(cfg["key"]),
                                                 body, timeout=120)
        if status >= 400:
            try:
                msg = json.loads(data).get("error", {}).get("message", "")
            except ValueError:
                msg = data[:200].decode("utf-8", "replace")
            raise RuntimeError(f"Anthropic returned {status}: {msg}")
        reply = json.loads(data)
        content = reply.get("content", [])
        uses = [b for b in content if b.get("type") == "tool_use"]
        if not uses or reply.get("stop_reason") != "tool_use":
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            return {"answer": text.strip(), "commands": done_cmds}
        msgs.append({"role": "assistant", "content": content})
        results = []
        for u in uses:
            args = [str(a) for a in (u.get("input") or {}).get("args", [])]
            if args[:1] and args[0].lower() in ("gam", "gam.exe"):
                args = args[1:]
            if not readonly(args):
                out, ok = "Refused: only read-only print/show/info/report commands are " \
                          "allowed.", False
            else:
                code, out = run(args)
                ok = code == 0
                out = (out or "")[:15000] + ("\n…(truncated)" if len(out or "") > 15000 else "")
            done_cmds.append((args, ok, out))
            if on_step:
                on_step(args, ok)
            results.append({"type": "tool_result", "tool_use_id": u.get("id"),
                            "content": out or "(no output)", "is_error": not ok})
        msgs.append({"role": "user", "content": results})
    return {"answer": "Stopped after too many look-ups.", "commands": done_cmds}
