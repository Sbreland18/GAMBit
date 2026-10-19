"""Turns GAM's own syntax reference (GamCommands.txt) into a searchable catalog
of commands, each with a parsed grammar the Command Builder can render as a form.

GamCommands.txt is downloaded from the GAM project to match the installed GAM
version (falling back to the copy bundled with GAMbit), so the catalog grows
automatically as GAM adds commands.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QStandardPaths

from .resources import resource_path

RAW_URL = "https://raw.githubusercontent.com/GAM-team/GAM/{ref}/src/GamCommands.txt"


# ================================================================= grammar ===
@dataclass
class Node:
    kind: str                      # lit, choice, ref, seq, alt, opt, group
    value: str = ""                # literal text / ref name
    options: list = field(default_factory=list)   # choice options
    children: list = field(default_factory=list)
    repeat: str = ""               # "", "*", "+"

    def text(self, limit: int = 80) -> str:
        s = render(self)
        return s if len(s) <= limit else s[:limit - 1] + "…"


def render(n: Node) -> str:
    rep = n.repeat
    if n.kind == "lit":
        s = n.value
    elif n.kind == "choice":
        s = "|".join(n.options)
    elif n.kind == "ref":
        s = (n.options[0] if n.options else "") + f"<{n.value}>"
    elif n.kind == "seq":
        s = " ".join(render(c) for c in n.children)
    elif n.kind == "alt":
        s = "|".join(render(c) for c in n.children)
    elif n.kind == "opt":
        s = "[" + " ".join(render(c) for c in n.children) + "]"
    else:  # group
        s = "(" + " ".join(render(c) for c in n.children) + ")"
    return s + rep


def tokenize(text: str) -> list[str]:
    """Split GAM BNF into tokens.

    '|' with no spaces around it binds tightly ("create|add", "(a)|(b)") and is
    returned as "|t"; '|' with spaces around it is a loose alternative ("|").
    '*' / '+' directly after an item are repeat markers.
    """
    toks: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        prev_space = i == 0 or text[i - 1].isspace()
        if ch == "|":
            next_space = i + 1 >= n or text[i + 1].isspace()
            toks.append("|" if (prev_space or next_space) else "|t")
            i += 1
        elif ch in "()[]":
            toks.append(ch)
            i += 1
        elif ch in "*+" and not prev_space:
            toks.append(ch)
            i += 1
        elif ch == "<":
            j = text.find(">", i)
            j = n - 1 if j < 0 else j
            toks.append(text[i:j + 1])
            i = j + 1
        elif ch == '"':
            j = text.find('"', i + 1)
            j = n - 1 if j < 0 else j
            toks.append(text[i:j + 1])
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()[]|<"':
                if text[j] in "*+" and j + 1 < n and (text[j + 1].isspace() or
                                                       text[j + 1] in ")]|"):
                    break
                j += 1
            if j == i:
                j = i + 1
            if j < n and text[j] == "<" and text[j - 1] in ":=.":
                # "user:<EmailAddress>" – a fixed prefix glued to a value
                k = text.find(">", j)
                if k > 0:
                    toks.append(text[i:k + 1])
                    i = k + 1
                    continue
            toks.append(text[i:j])
            i = j
    return toks


class _Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def alt(self) -> Node:
        branches = [self.seq()]
        while self.peek() == "|":
            self.take()
            branches.append(self.seq())
        return branches[0] if len(branches) == 1 else Node("alt", children=branches)

    def seq(self) -> Node:
        items = []
        while True:
            tok = self.peek()
            if tok is None or tok == "|" or tok in (")", "]"):
                break
            if tok == "|t":           # stray tight bar
                self.take()
                continue
            item = self.tight()
            if item:
                items.append(item)
        return items[0] if len(items) == 1 else Node("seq", children=items)

    def tight(self) -> Optional[Node]:
        first = self.item()
        if first is None or self.peek() != "|t":
            return first
        branches = [first]
        while self.peek() == "|t":
            self.take()
            nxt = self.item()
            if nxt is not None:
                branches.append(nxt)
        if all(b.kind == "lit" and not b.repeat for b in branches):
            return Node("choice", options=[b.value for b in branches])
        return Node("alt", children=branches)

    def item(self) -> Optional[Node]:
        tok = self.take()
        if tok is None:
            return None
        if tok == "(":
            inner = self.alt()
            if self.peek() == ")":
                self.take()
            n = Node("group", children=[inner])
        elif tok == "[":
            inner = self.alt()
            if self.peek() == "]":
                self.take()
            n = Node("opt", children=[inner])
        elif tok in ("*", "+", ")", "]"):
            return None
        elif tok.startswith("<") and tok.endswith(">"):
            n = Node("ref", value=tok[1:-1].strip())
        elif "<" in tok and tok.endswith(">") and not tok.startswith('"'):
            prefix, name = tok.split("<", 1)
            n = Node("ref", value=name[:-1].strip(), options=[prefix])
        else:
            n = Node("lit", value=tok)
        if self.peek() in ("*", "+"):
            n.repeat = self.take()
        return n


def parse(text: str) -> Node:
    p = _Parser(tokenize(text))
    node = p.alt()
    while p.peek() is not None:          # unbalanced brackets – keep going
        p.take()
        more = p.alt()
        node = Node("seq", children=[node, more])
    return node


# ================================================================ catalog ===
@dataclass
class Command:
    syntax: str            # full syntax, one line
    section: str
    note: str              # free-text description from the file, if any
    title: str = ""
    description: str = ""
    _tree: Optional[Node] = None

    @property
    def tree(self) -> Node:
        if self._tree is None:
            self._tree = parse(self.syntax[len("gam"):].strip())
        return self._tree

    @property
    def key(self) -> str:
        return self.syntax


VERBS = {
    "create": "Create", "add": "Add", "update": "Change", "delete": "Delete", "del": "Delete",
    "remove": "Remove", "print": "List (table)", "show": "Show", "info": "Show details of",
    "sync": "Sync", "clear": "Clear", "undelete": "Restore", "move": "Move",
    "transfer": "Transfer", "copy": "Copy", "get": "Download", "check": "Check",
    "wipe": "Wipe", "cancel": "Cancel", "empty": "Empty", "purge": "Permanently delete",
    "trash": "Move to trash", "untrash": "Restore from trash", "archive": "Archive",
    "watch": "Watch", "suspend": "Suspend", "unsuspend": "Unsuspend", "signout": "Sign out",
    "turnoff2sv": "Turn off 2-Step Verification for", "deprovision": "Deprovision",
    "import": "Import", "insert": "Insert", "replace": "Replace", "upload": "Upload",
    "collect": "Collect", "claim": "Claim", "accept": "Accept", "issuecommand": "Send a command to",
}
SYNONYMS = {
    "out of office": "vacation", "ooo": "vacation", "auto reply": "vacation",
    "autoreply": "vacation", "away": "vacation",
    "chromebook": "cros", "chromebooks": "cros", "chrome device": "cros",
    "share": "acl", "sharing": "acl", "permission": "acl", "permissions": "acl",
    "room": "resource", "rooms": "resource", "building": "building",
    "phone": "mobile", "phones": "mobile", "parent": "guardian", "parents": "guardian",
    "class": "course", "classes": "course", "teacher": "teacher", "student": "student",
    "2sv": "backupcodes", "2fa": "backupcodes", "backup codes": "backupcodes",
    "legal hold": "vault hold", "hold": "vault", "ediscovery": "vault",
    "role": "admin role", "roles": "role", "admin": "admin",
    "custom field": "schema", "custom fields": "schema", "custom attribute": "schema",
    "alert": "alert", "alerts": "alert", "directory": "gal", "contacts": "contact",
    "nickname": "alias", "alternate address": "alias", "mailbox access": "delegate",
    "folder": "drivefile", "file": "drivefile", "files": "drivefile",
    "shared drive": "shareddrive", "team drive": "shareddrive",
    "password": "password", "signature": "signature", "forwarding": "forward",
    "label": "label", "filter": "filter", "meet": "meet", "chat": "chat", "space": "chat",
    "policy": "policy", "policies": "policy", "printer": "printer", "license": "license",
}

# Ref names (lower case) that should never be expanded into sub-forms
LEAF_REFS = {"string", "number", "integer", "emailaddress", "useritem", "groupitem",
             "orgunitpath", "orgunititem", "date", "time", "filename", "boolean",
             "usertypeentity", "userentity", "groupentity", "emailaddressentity",
             "emailaddresslist", "userlist", "grouplist", "orgunitentity", "courseid",
             "uniqueid", "domainname", "todriveattribute", "queryuser", "querygmail",
             "regularexpression", "rematchpattern", "fieldname"}


def _describe(c: Command) -> tuple[str, str]:
    """A short title and a plain-English description generated from the syntax."""
    words = []
    toks = tokenize(c.syntax)[1:]
    k = 0
    while k < len(toks):
        tok = toks[k]
        if tok in ("[", "(", "*", "+", "|", "]", ")"):
            break
        if tok == "|t":
            words[-1] += "|" + (toks[k + 1] if k + 1 < len(toks) else "")
            k += 2
            continue
        words.append(tok)
        k += 1
    title = "gam " + " ".join(words)
    lits = [w.replace("|", " / ") for w in words if not w.startswith("<")]
    heads = [w.split("|")[0] for w in words if not w.startswith("<")]
    target = ""
    if words and words[0].startswith("<UserTypeEntity"):
        target = " for users"
    elif words and words[0].startswith("[<UserTypeEntity"):
        target = ""
    verb = next((w for w in heads if w in VERBS), None)
    if verb:
        idx = heads.index(verb)
        obj = " ".join(lits[idx + 1:]) or " ".join(lits[:idx])
        scope = f" on {' '.join(lits[:idx])}" if idx and lits[idx + 1:] else ""
        desc = f"{VERBS[verb]} {obj}{scope}{target}".strip()
    else:
        desc = (("Set " if target else "Run ") + " ".join(lits) + target).strip()
    if c.note:
        desc = f"{desc} — {c.note}"
    return title, desc


def parse_file(text: str) -> tuple[list[Command], dict[str, str]]:
    """Returns (commands, definitions {name: syntax text})."""
    lines = text.splitlines()
    commands: list[Command] = []
    defs: dict[str, str] = {}
    section, note, note_used = "General", "", False
    i = 0
    def_re = re.compile(r"^<([^>]+)>\s*::=\s*(.*)$")
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if line.startswith("# ") or line.startswith("## "):
            section = line.lstrip("#").strip()
            note, note_used = "", False
            i += 1
            continue
        m = def_re.match(line)
        if m:
            name, body = m.group(1).strip(), [m.group(2)]
            i += 1
            while i < len(lines) and lines[i][:1] in (" ", "\t") and lines[i].strip():
                cont = lines[i].strip()
                if not cont.lower().startswith(("see:", "see ", "http")):
                    body.append(cont)
                i += 1
            defs[name] = " ".join(b for b in body if b)
            continue
        if line.startswith("gam ") or line == "gam":
            body = [stripped]
            i += 1
            while i < len(lines) and lines[i][:1] in (" ", "\t") and lines[i].strip():
                if not lines[i].strip().startswith("#"):
                    body.append(lines[i].strip())
                i += 1
            syntax = " ".join(body)
            if "..." not in syntax[:30]:
                commands.append(Command(syntax=syntax, section=section, note=note))
                note_used = bool(note)
            continue
        if not stripped and note_used:
            # a note describes the block right under it, not the whole section
            nxt = next((ln for ln in lines[i + 1:i + 4] if ln.strip()), "")
            if nxt.startswith("gam "):
                note, note_used = "", False
        if stripped and not stripped.startswith("#") and stripped[0].isalpha() \
                and "::=" not in stripped and len(stripped) < 200:
            note, note_used = stripped.rstrip(".:"), False
        i += 1
    for c in commands:
        c.title, c.description = _describe(c)
    return commands, defs


# ============================================================== loading ===
def cache_path() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    return os.path.join(base, "GamCommands.txt")


def bundled_path() -> str:
    return resource_path("assets/GamCommands.txt")


def load_text() -> tuple[str, str]:
    """(text, where it came from) – downloaded copy if present, else bundled."""
    for path, label in ((cache_path(), "downloaded"), (bundled_path(), "bundled with GAMbit")):
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                return fh.read(), label
    return "", "missing"


def download(gam_version: Optional[str] = None) -> str:
    """Fetch GamCommands.txt for the installed GAM version (or the latest)."""
    from . import net
    refs = ([f"v{gam_version}"] if gam_version else []) + ["main", "master"]
    last_err = None
    for ref in refs:
        url = RAW_URL.format(ref=ref)
        tmp = cache_path() + ".part"
        try:
            os.makedirs(os.path.dirname(tmp), exist_ok=True)
            net.download(url, tmp)
            with open(tmp, encoding="utf-8") as fh:
                head = fh.read(200)
            if "GAM command line syntax" not in head:
                raise RuntimeError("unexpected file contents")
            os.replace(tmp, cache_path())
            return ref
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise RuntimeError(f"Couldn't download GamCommands.txt: {last_err}")


class Catalog:
    def __init__(self):
        text, self.source = load_text()
        self.commands, self.defs = parse_file(text) if text else ([], {})
        self._def_trees: dict[str, Optional[Node]] = {}
        self.sections = sorted({c.section for c in self.commands})

    def definition(self, name: str) -> Optional[Node]:
        if name not in self._def_trees:
            body = self.defs.get(name)
            self._def_trees[name] = parse(body) if body else None
        return self._def_trees[name]

    def enum_options(self, name: str) -> Optional[list[str]]:
        """If <name> is just a list of fixed words, return them."""
        tree = self.definition(name)
        if tree is None:
            return None
        if tree.kind == "choice" and not tree.repeat:
            return tree.options
        if tree.kind == "alt" and all(c.kind in ("lit", "choice") and not c.repeat
                                      for c in tree.children):
            out = []
            for c in tree.children:
                out += c.options if c.kind == "choice" else [c.value]
            return out
        if tree.kind == "ref" and tree.value in ("TrueValues", "FalseValues"):
            return None
        return None

    def search(self, query: str, section: str = "", limit: int = 400) -> list[Command]:
        q = query.lower().strip()
        for phrase, repl in SYNONYMS.items():
            if phrase in q.split() or (" " in phrase and phrase in q):
                q = q.replace(phrase, f"{phrase} {repl}")
        terms = [t for t in re.split(r"\s+", q) if t]
        scored = []
        for c in self.commands:
            if section and c.section != section:
                continue
            hay = f"{c.syntax} {c.section} {c.description}".lower()
            title = c.title.lower()
            if not terms:
                scored.append((0, c))
                continue
            hits = sum(1 for t in terms if t in hay)
            if hits == 0:
                continue
            score = hits * 10 + sum(5 for t in terms if t in title) + \
                sum(3 for t in terms if t in c.section.lower())
            score -= len(c.syntax) / 400
            scored.append((score, c))
        scored.sort(key=lambda x: -x[0])
        return [c for _s, c in scored[:limit]]
