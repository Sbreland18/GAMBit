"""What the Helper knows: every Guide article (pages, tabs, getting started, the GAM command
reference) and the top-bar tasks, ranked with BM25 so plain-English questions find the right
page, tab or command."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from .text import Normalizer, doc_terms


@dataclass
class Doc:
    id: str
    kind: str            # page | tab | start | gam | gamcmd | task
    title: str
    text: str
    page: str = ""
    tab: str = ""
    command: str = ""
    steps: list[str] = field(default_factory=list)
    what: str = ""
    weight: float = 1.0


def _plain(md: str) -> str:
    return re.sub(r"[*`_]", "", md or "")


class Knowledge:
    def __init__(self, docs: list[Doc]):
        self.docs = docs
        self.tf: list[Counter] = []
        df: Counter = Counter()
        for d in docs:
            # the title counts three times – it's the best signal
            terms = doc_terms(d.title) * 3 + doc_terms(d.text)
            c = Counter(terms)
            self.tf.append(c)
            df.update(set(c))
        self.n = len(docs)
        self.avg = (sum(sum(c.values()) for c in self.tf) / self.n) if self.n else 1
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        vocab = set()
        for d in docs:
            vocab |= {w for w in re.findall(r"[a-z][a-z0-9-]+", (d.title + " " + d.text)
                                            .lower()) if len(w) > 3}
        self.norm = Normalizer(vocab)

    def search(self, query_terms: list[str], limit: int = 5, kinds: tuple = ()) -> list[tuple[float, Doc]]:
        if not query_terms:
            return []
        k1, b = 1.4, 0.7
        out = []
        q = Counter(query_terms)
        for d, tf in zip(self.docs, self.tf):
            if kinds and d.kind not in kinds:
                continue
            dl = sum(tf.values()) or 1
            s = 0.0
            for t, qn in q.items():
                f = tf.get(t)
                if not f:
                    continue
                s += self.idf.get(t, 0) * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self.avg))
            if s > 0:
                out.append((s * d.weight, d))
        out.sort(key=lambda x: -x[0])
        return out[:limit]

    def page(self, name: str) -> Doc | None:
        return next((d for d in self.docs if d.kind == "page" and d.page == name), None)

    def by_id(self, did: str) -> Doc | None:
        return next((d for d in self.docs if d.id == did), None)


def build(app=None) -> Knowledge:
    from .. import guide, intents
    from ..guide import gam_ref
    docs: list[Doc] = []
    for a in guide.build(app, include_catalog=False):
        if a.id.startswith("page:"):
            info = guide.PAGES.get(a.page, {})
            docs.append(Doc(a.id, "page", a.title, a.text + " " + (a.keywords or ""),
                            page=a.page, steps=list(info.get("steps", [])),
                            what=_plain(info.get("what", "")), weight=1.25))
        elif a.id.startswith("tab:"):
            docs.append(Doc(a.id, "tab", a.title, f"{a.page} {a.text} {a.keywords or ''}",
                            page=a.page, tab=a.tab, what=a.text[:400], weight=1.05))
        elif a.id.startswith("start:"):
            docs.append(Doc(a.id, "start", a.title, a.text + " " + (a.keywords or ""),
                            what=a.text[:600], weight=1.1))
        elif a.id.startswith("gam:cmd:"):
            continue          # added below with their plain-English description
        elif a.id.startswith("gam:"):
            docs.append(Doc(a.id, "gam", a.title, a.text, what=a.text[:600], weight=0.8))
    for cat, cmd, desc in gam_ref.COMMANDS:
        docs.append(Doc(f"cmd:{cmd}", "gamcmd", desc, f"{cat} {cmd} {desc}", command=cmd,
                        what=desc, weight=0.9))
    for label, words, page, tab in intents.INTENTS:
        docs.append(Doc(f"task:{label}", "task", label, f"{label} {words} {page} {tab or ''}",
                        page=page, tab=tab or "", weight=1.3))
    return Knowledge(docs)
