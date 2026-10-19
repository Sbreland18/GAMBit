"""Plain-English handling for the offline Helper: tokens, typo correction, synonyms and
light stemming, so “how do i resset a pasword for a kid” reads like
“reset password student”."""

from __future__ import annotations

import difflib
import re

STOP = set("""a an the to for of on in at by with from and or but is are was were be been am
possible possibly example instance say wondering wonder
do does did doing i me my we our you your it its this that these those there here what which
who whom how can could would should will shall may might please pls plz just want need like
get got make let lets help some any all into about up out so if then than also too very
really thing things way something im i'm id i'd ive i've dont don't cant can't wont won't
hi hey hello thanks thank ok okay yes no""".split())

# words people use → the word GAMbit's knowledge uses
CANON = {
    # people
    "kid": "student", "kids": "student", "pupil": "student", "pupils": "student",
    "learner": "student", "scholar": "student", "child": "student", "children": "student",
    "teacher": "staff", "teachers": "staff", "employee": "staff", "employees": "staff",
    "faculty": "staff", "worker": "staff", "sub": "substitute", "subs": "substitute",
    "person": "user", "people": "user", "account": "user", "accounts": "user",
    "someone": "user", "somebody": "user", "everyone": "all", "everybody": "all",
    "parent": "guardian", "parents": "guardian", "mom": "guardian", "dad": "guardian",
    # devices
    "chromebook": "chromebook", "chromebooks": "chromebook", "cb": "chromebook",
    "cbs": "chromebook", "laptop": "chromebook", "laptops": "chromebook",
    "device": "chromebook", "devices": "chromebook", "computer": "chromebook",
    "serial": "serial", "sn": "serial", "tag": "asset", "asset": "asset",
    # actions
    "pw": "password", "pwd": "password", "pass": "password", "passwd": "password",
    "passcode": "password", "reset": "reset", "change": "change", "forgot": "reset",
    "forgotten": "reset", "unlock": "unsuspend", "reactivate": "unsuspend",
    "enable": "enable", "restore": "unsuspend", "lock": "suspend", "disable": "disable",
    "deactivate": "suspend", "block": "suspend", "suspended": "suspend",
    "delete": "delete", "remove": "remove", "erase": "delete", "kick": "remove",
    "add": "add", "put": "add", "join": "add", "insert": "add", "include": "add",
    "move": "move", "transfer": "transfer", "relocate": "move", "switch": "move",
    "list": "list", "show": "list", "display": "list", "see": "list", "view": "list",
    "find": "find", "search": "find", "lookup": "find", "look": "find", "locate": "find",
    "check": "find", "info": "info", "details": "info", "detail": "info",
    "create": "create", "new": "create", "make": "create", "setup": "create",
    "logout": "signout", "logoff": "signout", "signoff": "signout",
    "2fa": "2sv", "mfa": "2sv", "2-step": "2sv", "twostep": "2sv", "2step": "2sv",
    "authenticator": "2sv", "verification": "2sv",
    "ooo": "vacation", "autoreply": "vacation", "away": "vacation", "auto-reply": "vacation",
    "vacation": "vacation", "forwarding": "forward", "forwarded": "forward",
    "nickname": "alias", "alternate": "alias", "aliases": "alias",
    "delegate": "delegate", "delegates": "delegate", "delegation": "delegate",
    "class": "course", "classes": "course", "courses": "course", "classroom": "course",
    "ou": "ou", "ous": "ou", "orgunit": "ou", "org": "ou", "folder": "folder",
    "group": "group", "groups": "group", "list-serv": "group", "listserv": "group",
    "mailing": "group", "distribution": "group", "member": "member", "members": "member",
    "membership": "member", "memberships": "member", "owner": "owner", "owners": "owner",
    "manager": "manager", "managers": "manager",
    "drive": "drive", "file": "file", "files": "file", "doc": "file", "docs": "file",
    "license": "license", "licenses": "license", "licence": "license",
    "admin": "admin", "admins": "admin", "administrator": "admin",
    "walkthrough": "walk", "walk": "walk", "tutorial": "walk", "guide": "walk",
    "explain": "explain", "meaning": "explain", "mean": "explain",
    "synced": "sync", "syncing": "sync", "checked-in": "sync", "checkin": "sync",
}

PHRASES = [  # multi-word phrases first (applied before tokenizing)
    (r"\b(sign|log|kick)(ed|ing)? ([a-z@.'-]+(?: [a-z'-]+)?) out\b", r" signout \3 "),
    (r"\b(take|kick|pull|drop)(s|n)? ([a-z@.'-]+(?: [a-z'-]+)?) (out of|off|from)\b",
     r" remove \3 from "),
    (r"\b(old|expired|expiring|outdated|out of date) (updates?|software|chrome ?os)\b",
     " aue "),
    (r"\b(what'?s|who'?s|who is|who are|what is) (in|on)\b", " member "),
    (r"\b(not|n'?t|never) (been )?(seen|used|online|checked in|synced)\b", " inactive "),
    (r"\bstop(s|ped)? (getting )?updat(es|ing)\b", " aue "), (r"\bupdates? end\b", " aue "),
    (r"\b(give|hand) (over )?(\w+'?s? ){0,3}(drive|files|docs|ownership)\b", " transfer drive "),
    (r"\b(won'?t|doesn'?t|does not|will not|can'?t|cannot) (turn|power|boot|start|charge|"
     r"come)( on| up)?\b", " broken "),
    (r"\b(cracked|smashed|dead|damaged)\b", " broken repair "),
    (r"\bsign(ed|ing)? ?(them |him |her )?out\b", " signout "),
    (r"\blog(ged|ging)? ?(them |him |her )?out\b", " signout "),
    (r"\bout of (the )?office\b", " vacation "), (r"\bauto ?repl(y|ies)\b", " vacation "),
    (r"\b2 ?step( verification)?\b", " 2sv "), (r"\btwo[- ]?(step|factor)\b", " 2sv "),
    (r"\borg(anizational)? ?units?\b", " ou "), (r"\bgoogle classroom\b", " course "),
    (r"\bshared drives?\b", " shareddrive "), (r"\bteam drives?\b", " shareddrive "),
    (r"\bhasn'?t (signed|logged) in\b", " inactive "),
    (r"\bnot (signed|logged) in\b", " inactive "), (r"\bhaven'?t (signed|logged) in\b", " inactive "),
    (r"\bturn(ed)? off\b", " disable "), (r"\bturn(ed)? on\b", " enable "),
    (r"\bset ?up\b", " create "), (r"\blook ?up\b", " find "),
    (r"\bwalk (me )?through\b", " walk "), (r"\bshow me how\b", " walk "),
    (r"\bstep by step\b", " walk "), (r"\bhow (do|can|would|should) (i|we|you)\b", " howto "),
    (r"\bwhat does\b", " explain "), (r"\bwhat is\b", " explain "), (r"\bwhat's\b", " explain "),
    (r"\bwho is in\b", " member "), (r"\bwho('s| is) on\b", " member "),
    (r"\bwhat groups\b", " member group "), (r"\bwhich groups\b", " member group "),
    (r"\bgive (me )?(the )?(gam )?command\b", " command "),
    (r"\bend of (life|updates)\b", " aue "), (r"\bauto ?update expiration\b", " aue "),
    (r"\bcheck ?in\b", " sync "), (r"\blast seen\b", " sync "),
]

# frequent misspellings fixed before fuzzy correction
TYPOS = {"pasword": "password", "passowrd": "password", "passwrod": "password",
         "pssword": "password", "paswrd": "password", "chromebok": "chromebook",
         "chromboook": "chromebook", "cromebook": "chromebook", "chrombook": "chromebook",
         "suspened": "suspend", "suspnd": "suspend", "susspend": "suspend",
         "grup": "group", "gruop": "group", "goup": "group", "studnet": "student",
         "stuent": "student", "studen": "student", "teahcer": "teacher", "techer": "teacher",
         "resset": "reset", "rset": "reset", "recieve": "receive", "acount": "account",
         "accout": "account", "lisence": "license", "liscense": "license", "lincense": "license",
         "clasroom": "classroom", "calss": "class", "memebers": "members", "membrs": "members",
         "comand": "command", "commnad": "command", "serail": "serial", "seiral": "serial"}

TOKEN = re.compile(r"[a-z0-9][a-z0-9'@._/-]*")


def stem(w: str) -> str:
    if len(w) <= 4 or "@" in w or "/" in w:
        return w
    for suf in ("ing", "ies", "ied", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            base = w[: -len(suf)]
            if suf in ("ies", "ied"):
                base += "y"
            elif suf in ("ing", "ed") and len(base) >= 4 and base[-1] == base[-2] and \
                    base[-1] not in "aeiouls":
                base = base[:-1]          # logged → log, mapped → map (not "fill", "pass")
            return base
    return w


# informal spellings the phrase rules understand as they are
KEEP = {"whos", "whats", "hows", "cant", "dont", "wont", "havent", "hasnt", "isnt", "doesnt",
        "didnt", "arent", "wasnt", "thats", "theres", "theyre", "youre"}


class Normalizer:
    """Build once with the vocabulary GAMbit knows; then .terms(text) for any query."""

    def __init__(self, vocabulary: set[str] | None = None):
        self.vocab = {w for w in (vocabulary or set()) if len(w) > 2}
        self.vocab |= set(CANON) | set(CANON.values()) | set(TYPOS.values())
        self._vlist = sorted(self.vocab)
        self._cache: dict[str, str] = {}

    def correct(self, w: str) -> str:
        if w in TYPOS:
            return TYPOS[w]
        if w in self.vocab or len(w) < 4 or any(c.isdigit() for c in w) or "@" in w \
                or "/" in w or "." in w:
            return w
        if w not in self._cache:
            m = difflib.get_close_matches(w, self._vlist, n=1, cutoff=0.82)
            self._cache[w] = m[0] if m else w
        return self._cache[w]

    def words(self, text: str) -> list[str]:
        """Lower-cased, phrase-normalised, typo-corrected, synonym-mapped words (with stop
        words kept out)."""
        t = " " + (text or "").lower().replace("’", "'") + " "
        # fix typos first so phrases like "what groups … in" still match "what grups … in"
        t = re.sub(r"(?<![\w@./'-])[a-z]{4,}(?![\w@'-])", 
                   lambda m: m.group() if m.group() in KEEP else self.correct(m.group()), t)
        for pat, rep in PHRASES:
            t = re.sub(pat, rep, t)
        out = []
        for w in TOKEN.findall(t):
            w = w.strip("'.-/") if not w.startswith("/") else w.rstrip("/")
            if not w or w in STOP:
                continue
            w = self.correct(w)
            w = CANON.get(w, w)
            out.append(w)
        return out

    def terms(self, text: str) -> list[str]:
        return [stem(w) for w in self.words(text)]


def doc_terms(text: str) -> list[str]:
    """Terms for indexing a document (no typo correction needed)."""
    out = []
    for w in TOKEN.findall((text or "").lower()):
        w = w.strip("'.-/")
        if w and w not in STOP:
            out.append(stem(CANON.get(w, w)))
    return out
