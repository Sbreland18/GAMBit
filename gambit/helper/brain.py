"""The Helper's conversation logic: understand the request, then answer with a GAM command
(ready to run), a page to open, a step-by-step walkthrough, or – for open questions when the
local AI is on – a written answer grounded in GAMbit's Guide."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from . import commands as hc
from .knowledge import Doc, Knowledge

ACTION_WORDS = {"reset", "suspend", "unsuspend", "enable", "disable", "move", "transfer",
                "signout", "add", "remove", "delete", "create", "list", "find", "info",
                "command", "member", "forward", "delegate", "vacation", "2sv", "alias",
                "transfer", "aue", "inactive", "clear", "blank", "assign"}
CONTROL = {"howto", "walk", "explain", "command", "tell", "know", "use", "using", "work",
           "works", "doe"}
HELLO = {"hi", "hello", "hey", "howdy", "morning", "afternoon", "yo"}
CAPS = ("I can help three ways:\n"
        "• **Find the right place** – ask “how do I set up a new teacher?” and I'll open "
        "the page.\n"
        "• **Walk you through it** – say “walk me through roster sync” and I'll go step by "
        "step, opening each page for you.\n"
        "• **Write GAM commands** – say “reset jane doe's password” or “list chromebooks not "
        "seen in 30 days”. You check it, then click Run.\n"
        "Typos are fine – just type the way you'd say it.")
STARTERS = ["What can you do?", "How do I use this page?", "Reset a student's password",
            "Walk me through roster sync", "List Chromebooks not seen in 30 days"]


@dataclass
class Answer:
    text: str = ""                                   # light markdown: **bold**, • bullets
    suggestions: list = field(default_factory=list)  # commands.Suggestion
    links: list[Doc] = field(default_factory=list)   # pages/tabs to open
    walkthrough: Doc | None = None
    chips: list[str] = field(default_factory=list)
    needs_ai: bool = False
    ai_context: str = ""
    confident: bool = True


def to_html(text: str) -> str:
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![*\w])\*([^*\n]+?)\*(?![*\w])", r"<i>\1</i>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t.replace("\n", "<br>")


class Brain:
    def __init__(self, knowledge: Knowledge, directory=None, ai_available=lambda: False):
        self.k = knowledge
        self.directory = directory
        self.ai_available = ai_available
        self.memory: dict = {}
        self.pending: tuple | None = None        # (recipe, slots, raw text)
        self.history: list[dict] = []

    # ------------------------------------------------------------- helpers ---
    def _dir(self):
        d = self.directory
        if d is None:
            return [], [], []
        return (getattr(d, "users", []) or [], getattr(d, "groups", []) or [],
                getattr(d, "ous", []) or [])

    def _remember(self, s: hc.Slots):
        for k in ("users", "groups", "serials", "ous"):
            v = getattr(s, k)
            if v:
                self.memory[k] = list(v)

    def _merge(self, a: hc.Slots, b: hc.Slots) -> hc.Slots:
        for k in ("users", "groups", "ous", "serials", "assets", "quoted", "other_emails"):
            setattr(a, k, list(dict.fromkeys(getattr(a, k) + getattr(b, k))))
        a.days = b.days or a.days
        return a

    # ------------------------------------------------------------ respond ---
    def respond(self, text: str, page: str = "") -> Answer:
        text = (text or "").strip()
        if not text:
            return Answer(CAPS, chips=STARTERS)
        words = set(self.k.norm.words(text))
        terms = self.k.norm.terms(text)
        users, groups, ous = self._dir()
        slots = hc.extract(text, users, groups, ous, self.memory)

        # 1. answering a question the Helper asked ("Who is it for?")
        pending, self.pending = self.pending, None
        if pending:
            self.pending = pending
            recipe, old, raw = self.pending
            new_request = (bool(words & ACTION_WORDS) and len(words) > 2) or "?" in text \
                or "howto" in words or "walk" in words or "explain" in words
            self.pending = None
            if not new_request:
                merged = self._merge(old, slots)
                miss = hc.missing(recipe, merged)
                if not miss:
                    self.pending = None
                    return self._suggest(recipe, merged, raw)
                if self._filled_any(old, slots):
                    self.pending = (recipe, merged, raw)
                    return Answer(hc.ASK[miss[0]], confident=True)
                if text.lower().strip(" .!") in ("no", "cancel", "stop", "nevermind",
                                                 "never mind", "forget it", "nope"):
                    return Answer("OK, cancelled.")

        # 2. small talk
        if re.fullmatch(r"\s*(thanks|thank you|thx|ty|cheers|great|perfect|ok thanks)[.! ]*",
                        text.lower()):
            return Answer("You're welcome! Anything else?")
        if words <= HELLO | {"help", "assistant", "helper"} or "can you do" in text.lower() \
                or text.lower().strip("?! .") in ("help", "what can you do", "commands"):
            return Answer(("Hi! " if words & HELLO else "") + CAPS, chips=STARTERS)
        if words & {"thanks", "thank", "thx", "ty"} and len(words) <= 3:
            return Answer("You're welcome! Anything else?")

        # 3. explain a GAM command someone pasted
        if self._looks_like_command(text):
            return self._explain_command(text)

        # 4. "this page"
        if re.search(r"\b(this|current) (page|screen|tab)\b", text.lower()) and page:
            d = self.k.page(page)
            if d:
                return self._page_answer(d, walk="walk" in words or "howto" in words)

        # 5. a GAM command recipe
        ranked = hc.rank(words, slots)
        raw_words = set(re.findall(r"[a-z]+", text.lower()))   # "all"/"every" are stop words
        kept = [x for x in ranked if not (x[1].avoid & raw_words)]
        bulk = bool(raw_words & {"all", "every", "each", "everything", "everyone"})
        if len(kept) < len(ranked) or bulk:  # ruled out, or a whole-fleet job – don't settle
            kept = [x for x in kept if x[0] > 0]
        ranked = kept
        if ranked and ranked[0][1].id.startswith("cros") and hc.missing(ranked[0][1], slots):
            # the recipe is missing details – if the Guide clearly points somewhere else
            # (a whole-fleet tool, say), that's the better answer
            gterms = [t for t in terms if t not in CONTROL] or terms
            r0 = ranked[0][1]
            for gs, gd in self.k.search(gterms, limit=2):
                cov = self._coverage(gterms, gd)
                if gd.kind in ("task", "tab") and gd.page != r0.page and \
                        ((gs >= 12 and cov >= 0.7) or (gs >= 25 and cov >= 0.45)):
                    ranked = []
                    break
        how = "howto" in words or "walk" in words
        want_cmd = bool(words & ACTION_WORDS) or "command" in words or (
            bool(ranked) and not hc.missing(ranked[0][1], slots) and not how)
        if ranked and want_cmd and not ("walk" in words and not slots.users):
            recipe = ranked[0][1]
            miss = hc.missing(recipe, slots)
            if miss:
                self.pending = (recipe, slots, text)
                if miss[0] in ("user", "users") and slots.maybe_users:
                    names = {u["email"].lower(): u.get("name", "") for u in users}
                    return Answer("Which person do you mean?", chips=[
                        f"{names.get(e, '')} {e}".strip() for e in slots.maybe_users])
                if how and recipe.page:
                    pd = self._links_for(recipe)
                    a = self._page_answer(pd[0], also=pd[1:]) if pd else Answer()
                    a.text += ("\n\nOr I can write the command for you: " +
                               hc.ASK[miss[0]][0].lower() + hc.ASK[miss[0]][1:])
                    return a
                return Answer(f"Sure – {recipe_label(recipe)}. " + hc.ASK[miss[0]],
                              links=self._links_for(recipe))
            return self._suggest(recipe, slots, text, how)

        # 6. the Guide
        terms = [t for t in terms if t not in CONTROL] or terms
        hits = self.k.search(terms, limit=6)
        if not hits:
            return self._unsure(text, [])
        top_score, top = hits[0]
        cover = self._coverage(terms, top)
        strong = cover >= 0.6 and top_score >= 5.0 and (len(hits) == 1 or
                                                        top_score >= hits[1][0] * 1.1)
        if cover < 0.4:
            hits = [h for h in hits if self._coverage(terms, h[1]) >= 0.4]
            if not hits:
                return self._unsure(text, [])
            top_score, top = hits[0]
        if "explain" in words:      # "what is …" – a Getting started article fits best
            st = next((x for _s, x in hits[:4] if x.kind == "start" and
                       self._coverage(terms, x) >= 0.6), None)
            if st is not None:
                return Answer(f"**{st.title}**\n{_first_sentences(st.what, 4)}",
                              links=[x for _s, x in hits[:4] if x.kind in ("page", "tab")][:3])
        if top.kind in ("page", "tab", "task") and (strong or how):
            d = self.k.page(top.page) if top.kind == "task" else top
            if top.kind == "task" and top.tab:
                d = next((x for _s, x in hits if x.kind == "tab" and x.page == top.page
                          and x.tab == top.tab), None) or self.k.by_id(
                    f"tab:{top.page}:{top.tab}") or d
            if d is not None:
                return self._page_answer(d, walk="walk" in words, also=[x for _s, x in
                                                                        hits[1:4]])
        if top.kind == "gamcmd" and strong:
            return Answer(f"**{top.title}**\n`gam {top.command[4:] if top.command.startswith('gam ') else top.command}`\n"
                          "Words in <angle brackets> are what you fill in. Tell me the person "
                          "or device and I'll fill it in for you.",
                          links=[x for _s, x in hits[1:4] if x.kind in ("page", "tab")])
        if not strong and cover >= 0.75 and top.kind in ("page", "tab", "task"):
            d = self.k.page(top.page) if top.kind == "task" and not top.tab else top
            if top.kind == "task" and top.tab:
                d = self.k.by_id(f"tab:{top.page}:{top.tab}") or self.k.page(top.page)
            if d is not None and d.kind in ("page", "tab"):
                return self._page_answer(d, walk="walk" in words)
        if top.kind == "start" and (strong or cover >= 0.75):
            return Answer(f"**{top.title}**\n{_first_sentences(top.what, 4)}",
                          links=[x for _s, x in hits[1:4] if x.kind in ("page", "tab")])
        return self._unsure(text, hits)

    def _coverage(self, terms: list[str], d: Doc) -> float:
        """Share of the question's meaning (idf-weighted) that the document contains."""
        i = self.k.docs.index(d)
        tf = self.k.tf[i]
        top = max(self.k.idf.values()) if self.k.idf else 1
        tot = sum(self.k.idf.get(t, top) for t in set(terms)) or 1
        got = sum(self.k.idf.get(t, top) for t in set(terms) if tf.get(t))
        # words the Guide never uses (a school's name, say) count for less
        hit = sum(1 for t in set(terms) if tf.get(t))
        unknown = sum(top * 0.75 for t in set(terms) if t not in self.k.idf) if hit >= 2 else 0
        return got / max(tot - unknown, 1e-9) if got else 0.0

    # ----------------------------------------------------------- builders ---
    def _filled_any(self, old: hc.Slots, new: hc.Slots) -> bool:
        return any(getattr(new, k) for k in ("users", "groups", "ous", "serials", "assets",
                                              "other_emails")) or bool(new.days)

    def _suggest(self, recipe, slots, raw, how=False) -> Answer:
        sug = hc.make(recipe, slots, raw, self._dir()[0])
        self._remember(slots)
        links = self._links_for(recipe)
        terms = [t for t in self.k.norm.terms(raw) if t not in CONTROL]
        for _s, d in self.k.search(terms, 3, ("tab", "page")):
            if self._coverage(terms, d) >= 0.5 and all(d.id != x.id for x in links):
                links.append(d)
                break
        if set(self.k.norm.words(raw)) & {"broken", "repair"} and recipe.id.startswith("cros"):
            rep = self.k.by_id("tab:Chromebook fleet:Repairs")
            if rep and all(rep.id != x.id for x in links):
                links.insert(0, rep)
        lead = "Here's the command" + (" – check it, then click **Run**." if sug.change
                                       else ". It only reads, so it's safe to run.")
        if how:
            lead = (f"In GAMbit this is on the **{sug.page}** page" +
                    (f" → **{sug.tab}**" if sug.tab else "") + ". " + lead)
        return Answer(lead, suggestions=[sug], links=links, chips=self._next_chips(recipe))

    def _links_for(self, recipe) -> list[Doc]:
        out = []
        if recipe.page:
            d = (self.k.by_id(f"tab:{recipe.page}:{recipe.tab}") if recipe.tab else None) \
                or self.k.page(recipe.page)
            if d:
                out.append(d)
        return out

    def _next_chips(self, recipe) -> list[str]:
        return {"reset_password": ["Sign them out everywhere", "Which Chromebook do they use?"],
                "suspend_user": ["Which groups are they in?", "Give their Drive files to "
                                 "their supervisor"],
                "user_info": ["Which groups are they in?", "Reset their password"],
                "cros_stale": ["Walk me through the Chromebook fleet page"],
                }.get(recipe.id, [])

    def _page_answer(self, d: Doc, walk: bool = False, also=None) -> Answer:
        if d.kind == "tab":
            text = f"**{d.page} → {d.tab}**\n{_first_sentences(d.what, 3)}"
            page_doc = self.k.page(d.page)
            return Answer(text, links=[d] + ([page_doc] if page_doc else []),
                          walkthrough=page_doc if page_doc and page_doc.steps else None,
                          chips=[f"Walk me through {d.page}"] if page_doc and
                          page_doc.steps else [])
        text = f"**{d.page}**\n{_first_sentences(d.what, 3)}"
        if d.steps and not walk:
            text += "\n\nHow to use it:\n" + "\n".join(
                f"{i}. {s}" for i, s in enumerate(d.steps[:6], 1))
        links = [d] + [x for x in (also or []) if x.kind in ("page", "tab") and x.id != d.id][:2]
        return Answer(text, links=links, walkthrough=d if d.steps else None,
                      chips=([] if walk else ([f"Walk me through {d.page}"] if d.steps
                                              else [])))

    def _looks_like_command(self, text: str) -> bool:
        t = text.strip().lower()
        if re.search(r"(^|\s|`)gam\s+\S+\s+\S+", t):
            return True
        return bool(re.match(r"^(explain\s+)?(print|show|info|update|create|delete|"
                             r"user|users|ou|ou_and_children|cros_sn|group)\s+\S+\s+\S+",
                             t)) and ("@" in t or "/" in t or " print " in f" {t} ") \
            and not words_are_english(t)

    def _explain_command(self, text: str) -> Answer:
        from . import verify
        cmd = text.strip().strip("`")
        m = re.search(r"\bgam\s+(.+)", cmd, re.I)
        if m:
            cmd = m.group(1)
        cmd = re.sub(r"^\s*(explain|what does|what is)\s+", "", cmd, flags=re.I)
        cmd = re.sub(r"[`?]+$|\s+(do|does|mean|means)\s*\??\s*$", "", cmd.strip(), flags=re.I)
        args = verify.split(cmd)
        ok, how = verify.check(args)
        lines = [f"`gam {' '.join(args)}`"]
        desc = verify.describe(args)
        if desc:
            lines.append(f"In plain English: **{desc}**.")
        lines.append("✔ GAM knows this command (" + how + ")." if ok else
                     "⚠ This doesn't match any GAM command I know – check the spelling.")
        from ..activity import is_change
        lines.append("It **changes** things in Google." if is_change(args) else
                     "It only **reads** – nothing changes.")
        sug = hc.Suggestion("pasted", "Your command", args, "", is_change(args))
        return Answer("\n".join(lines), suggestions=[sug] if ok else [])

    def _unsure(self, text: str, hits) -> Answer:
        ctx = self.context_for(text, hits)
        tops = [d for _s, d in hits[:3]]
        if self.ai_available():
            return Answer("", needs_ai=True, ai_context=ctx, links=[d for d in tops if
                                                                     d.kind in ("page",
                                                                                "tab")])
        if tops:
            names = [d.title if d.kind != "tab" else f"{d.page} → {d.tab}" for d in tops]
            return Answer("I'm not completely sure, but one of these is probably what you "
                          "need:", links=[d for d in tops if d.kind in ("page", "tab", "task")]
                          or [], chips=[f"Tell me about {n}" for n in names[:3]],
                          confident=False)
        return Answer("Sorry – I didn't catch that. Try saying what you want to do, like "
                      "“move a student to another school” or “who is in the staff group?”",
                      chips=STARTERS[:3], confident=False)

    def context_for(self, text: str, hits=None) -> str:
        hits = hits if hits is not None else self.k.search(self.k.norm.terms(text), 6)
        parts = []
        for _s, d in hits[:6]:
            where = f"{d.page}" + (f" → {d.tab}" if d.tab else "") if d.page else ""
            body = d.what or d.text[:500]
            if d.steps:
                body += " Steps: " + " ".join(f"{i}. {s}" for i, s in enumerate(d.steps, 1))
            if d.command:
                body += f" Command: {d.command}"
            parts.append(f"[{d.title}]{' (page: ' + where + ')' if where else ''}: {body}")
        cmds = self.k.search(self.k.norm.terms(text), 6, ("gamcmd",))
        if cmds:
            parts.append("GAM commands that may help:\n" + "\n".join(
                f"- {d.command} – {d.what}" for _s, d in cmds))
        return "\n".join(parts)


def recipe_label(r) -> str:
    return {"reset_password": "I'll reset the password", "suspend_user": "I'll suspend the "
            "account", "unsuspend_user": "I'll unsuspend the account", "move_user": "I'll move "
            "the account", "add_to_group": "I'll add them to the group", "remove_from_group":
            "I'll take them out of the group", "cros_move": "I'll move the Chromebook",
            "cros_disable": "I'll disable the Chromebook", "transfer_drive": "I'll hand over "
            "the Drive files"}.get(r.id, "I can do that")


def words_are_english(t: str) -> bool:
    return bool(re.search(r"\b(how|what|why|can|please|want|need|my|the)\b", t))


def _first_sentences(t: str, n: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (t or "").strip())
    return " ".join(parts[:n])
