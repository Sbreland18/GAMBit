"""Check a suggested GAM command against GAM's own syntax reference (GamCommands.txt), so the
Helper can say “checked” – or warn when a command (for example one the local AI wrote)
doesn't match anything GAM knows."""

from __future__ import annotations

import re
import shlex

USER_ENTITIES = {"user", "users", "group", "groups", "group_ns", "group_susp", "ou", "ous",
                 "ou_ns", "ou_and_children", "ou_and_children_ns", "ous_and_children",
                 "course", "courses", "teachers", "students", "file", "csvfile", "query",
                 "queries", "license", "licenses", "domains", "cros", "crosfile"}
CROS_ENTITIES = {"cros_sn", "cros_ou", "cros_ou_and_children", "cros_ous",
                 "cros_ous_and_children", "cros_query", "cros"}

_PREFIXES: list[list[str]] | None = None


def split(command: str) -> list[str]:
    c = (command or "").strip()
    if c.lower().startswith("gam "):
        c = c[4:]
    try:
        return shlex.split(c, posix=True)
    except ValueError:
        return c.split()


_DESC: dict[str, str] = {}


def _prefixes() -> list[list[str]]:
    global _PREFIXES
    if _PREFIXES is None:
        from ..command_catalog import Catalog
        out = []
        for c in Catalog().commands:
            toks = []
            for t in c.syntax.split()[1:]:
                if t.startswith(("[", "(", "*")) or t in ("|",):
                    break
                toks.append(t)
            if any(not t.startswith("<") for t in toks):
                out.append(toks)      # needs at least one real keyword
                _DESC.setdefault("gam " + " ".join(toks), c.description or c.title)
        _PREFIXES = out
    return _PREFIXES


def _norm_entity(args: list[str]) -> list[str]:
    a = list(args)
    if not a:
        return a
    first = a[0].lower()
    if first == "all" and len(a) > 1 and a[1].lower() in ("users", "users_ns", "cros"):
        return [("<CrOSTypeEntity>" if a[1].lower() == "cros" else "<UserTypeEntity>")] + a[2:]
    if first in CROS_ENTITIES and len(a) > 2 and a[2].lower() in ("update", "print", "show",
                                                                   "info", "issuecommand",
                                                                   "get"):
        return ["<CrOSTypeEntity>"] + a[2:]
    if first in USER_ENTITIES and len(a) > 2 and a[1] and a[2].lower() not in ("name",):
        if first in ("course", "courses") and a[2].lower() in ("add", "create", "remove",
                                                               "delete", "sync", "update"):
            return a                    # gam course <id> add … is its own command
        return ["<UserTypeEntity>"] + a[2:]
    return a


def _tok_ok(pattern: str, value: str) -> bool:
    if pattern.startswith("<"):
        return True
    alts = [p.strip('"').lower() for p in pattern.split("|")]
    return value.lower() in alts


def check(command) -> tuple[bool, str]:
    """→ (matches GAM's syntax, the syntax prefix it matched or a reason)."""
    args = split(command) if isinstance(command, str) else list(command)
    if not args:
        return False, "empty"
    try:
        prefixes = _prefixes()
    except Exception as exc:  # noqa: BLE001
        return False, f"GAM's reference isn't available ({exc})"
    if not prefixes:
        return False, "GAM's reference isn't available"
    norm = _norm_entity(args)
    best = ""
    for p in prefixes:
        cand = norm if p[0].startswith("<UserTypeEntity") or p[0].startswith(
            "<CrOSTypeEntity") else args
        if len(cand) < len(p):
            continue
        if all(_tok_ok(pt, cand[i]) for i, pt in enumerate(p)):
            if len(" ".join(p)) > len(best):
                best = " ".join(p)
    return (True, "gam " + best) if best else (False, "no GAM command starts like this")


def extract_commands(text: str) -> list[str]:
    """Commands from an AI answer: ```gam blocks, then lines that start with 'gam '."""
    out = []
    for block in re.findall(r"```(?:gam|bash|shell|sh|cmd|powershell)?\s*\n(.*?)```", text or "",
                            re.S | re.I):
        out += [ln.strip() for ln in block.splitlines() if ln.strip() and
                not ln.strip().startswith("#")]
    if not out:
        out = [m.strip() for m in re.findall(r"(?m)^\s*`?(gam\s+[^`\n]+)`?\s*$", text or "")]
    return [re.sub(r"^gam\s+", "", c, flags=re.I) for c in out][:6]


def describe(command) -> str:
    """GAM's own one-line description of the command, when it's known."""
    ok, how = check(command)
    return _DESC.get(how, "") if ok else ""
