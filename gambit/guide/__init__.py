"""The in-app Guide: what every page and tab does and how to use it, plus a GAM command
reference – searchable, and exportable as one web page.

Articles come from three places:
* hand-written content (basics, pages_*.py, gam_ref.py),
* the live window (every tab's title and its one-line explanation), so new tabs show up
  even before anyone writes about them,
* GAM's own command reference (command_catalog), for every command GAM has."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from . import basics, gam_ref, pages_admin, pages_devices, pages_people, pages_reports
from . import pages_more, pages_tools

PAGES: dict[str, dict] = {}
for _m in (pages_people, pages_devices, pages_admin, pages_reports, pages_tools, pages_more):
    PAGES.update(_m.PAGES)
for _p, _tabs in pages_more.TABS.items():
    PAGES.setdefault(_p, {}).setdefault("tabs", {}).update(_tabs)

SECTION_NAMES = {"": "Start here", "PEOPLE": "People", "DEVICES": "Devices",
                 "SERVICES": "Services", "ADMIN": "Admin", "REPORTS": "Reports",
                 "AUTOMATION": "Automation", "TOOLS": "Tools"}


@dataclass
class Article:
    id: str
    title: str
    path: list[str]                  # tree location, e.g. ["Features", "People", "Users"]
    body: str = ""                   # HTML
    text: str = ""                   # plain text used for searching
    keywords: str = ""
    page: str = ""                   # GAMbit page to open
    tab: str = ""                    # …and tab
    command: str = ""                # GAM command (for "Open in Command Builder")
    weight: float = 1.0              # search ranking boost
    children: list[str] = field(default_factory=list)


# ================================================================ markup ===
def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", s)
    return s


def markup(text: str) -> str:
    """Tiny markdown: paragraphs, '## ' headings, '- ' bullets, '1. ' steps."""
    out, lst, para = [], None, []

    def flush_para():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()

    def close_list():
        nonlocal lst
        if lst:
            out.append(f"</{lst}>")
            lst = None
    for raw in (text or "").strip("\n").splitlines():
        ln = raw.strip()
        if not ln:
            flush_para()
            close_list()
            continue
        m_b = re.match(r"^- (.*)", ln)
        m_n = re.match(r"^\d+\. (.*)", ln)
        if ln.startswith("## "):
            flush_para()
            close_list()
            out.append(f"<h3>{_inline(ln[3:])}</h3>")
        elif m_b or m_n:
            flush_para()
            kind = "ul" if m_b else "ol"
            if lst != kind:
                close_list()
                out.append(f"<{kind}>")
                lst = kind
            out.append("<li>" + _inline((m_b or m_n).group(1)))
        elif lst and raw.startswith(("  ", "\t")):
            out[-1] += " " + _inline(ln)       # continuation of a list item
        else:
            close_list()
            para.append(ln)
    flush_para()
    close_list()
    return "\n".join(out)


def _plain(htm: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", htm))


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ================================================================= build ===
def _page_article(name: str, section: str, cls, live_tabs: list[tuple[str, str]],
                  short: str) -> tuple[Article, list[Article]]:
    info = PAGES.get(name, {})
    sec = SECTION_NAMES.get(section, section.title())
    what = info.get("what") or getattr(cls, "subtitle", "") or short
    parts = [f"<p class='lead'>{_inline(what)}</p>"]
    if info.get("steps"):
        parts.append("<h3>How to use it</h3><ol>" +
                     "".join(f"<li>{_inline(s)}</li>" for s in info["steps"]) + "</ol>")
    tab_texts = dict(info.get("tabs", {}))
    tabs = [t for t, _i in live_tabs] or list(tab_texts)
    intros = dict(live_tabs)
    kids = []
    if tabs:
        rows = []
        for t in tabs:
            desc = tab_texts.get(t) or intros.get(t, "")
            tid = f"tab:{name}:{t}"
            rows.append(f"<li><a href='gambit:article/{html.escape(tid)}'><b>{_inline(t)}</b>"
                        f"</a>{' – ' + _inline(desc) if desc else ''}</li>")
            body = ""
            if tab_texts.get(t):
                body += f"<p>{_inline(tab_texts[t])}</p>"
            if intros.get(t) and intros[t] != tab_texts.get(t):
                body += f"<p class='muted'>{_inline(intros[t])}</p>"
            if not body:
                body = f"<p>A tab on the {html.escape(name)} page.</p>"
            body += (f"<p><a href='gambit:tab/{html.escape(name)}/{html.escape(t)}'>Open "
                     f"{html.escape(name)} → {html.escape(t)}</a> · <a href='gambit:article/"
                     f"page:{html.escape(name)}'>About the {html.escape(name)} page</a></p>")
            kids.append(Article(tid, t, ["Features", sec, name], body, _plain(body),
                                info.get("keywords", ""), name, t, weight=0.9))
        parts.append("<h3>Tabs on this page</h3><ul>" + "".join(rows) + "</ul>")
    if info.get("tips"):
        parts.append("<h3>Tips</h3><ul>" + "".join(f"<li>{_inline(s)}</li>"
                                                   for s in info["tips"]) + "</ul>")
    if info.get("commands"):
        parts.append("<h3>GAM commands behind it</h3><ul>" + "".join(
            f"<li><code>{html.escape(c)}</code></li>" for c in info["commands"]) + "</ul>")
    parts.append(f"<p><a href='gambit:page/{html.escape(name)}'>Open the {html.escape(name)} "
                 "page →</a></p>")
    body = "\n".join(parts)
    art = Article(f"page:{name}", name, ["Features", sec], body, _plain(body),
                  info.get("keywords", "") + " " + short, name, weight=1.3,
                  children=[k.id for k in kids])
    return art, kids


def build(app=None, include_catalog: bool = True) -> list[Article]:
    out: list[Article] = []
    for aid, title, kw, text in basics.ARTICLES:
        b = markup(text)
        out.append(Article(f"start:{aid}", title, ["Getting started"], b, _plain(b), kw,
                           weight=1.2))
    try:
        from ..ui.main_window import NAV
    except Exception:  # noqa: BLE001
        NAV = []
    try:
        from ..ui.page_help import HELP
    except Exception:  # noqa: BLE001
        HELP = {}
    sec = ""
    seen = set()
    for item in NAV:
        if isinstance(item, str):
            sec = item
            continue
        name, cls = item
        if name in seen or name == "Guide":
            continue
        seen.add(name)
        live = live_tabs(app, name) if app is not None else []
        art, kids = _page_article(name, sec, cls, live, (HELP.get(name) or ("",))[0])
        out.append(art)
        out += kids
    out += gam_articles(include_catalog)
    return out


def live_tabs(app, name: str) -> list[tuple[str, str]]:
    """(tab title, its intro) for the page's top-level tab widget."""
    from PySide6.QtWidgets import QTabWidget
    page = getattr(app, "pages", {}).get(name)
    if page is None:
        return []
    tw = getattr(page, "tabs", None)
    if not isinstance(tw, QTabWidget):
        tws = page.findChildren(QTabWidget)
        tw = tws[0] if tws else None
    if tw is None:
        return []
    return [(tw.tabText(i).replace("&&", "&"), getattr(tw.widget(i), "intro", "") or "")
            for i in range(tw.count())]


# ============================================================ GAM commands ===
def gam_articles(include_catalog: bool = True) -> list[Article]:
    out = []
    aid, title, kw, text = gam_ref.BASICS
    b = markup(text)
    out.append(Article(f"gam:{aid}", title, ["GAM commands"], b, _plain(b), kw, weight=1.2))
    cats: dict[str, list[tuple[str, str]]] = {}
    for cat, cmd, desc in gam_ref.COMMANDS:
        cats.setdefault(cat, []).append((cmd, desc))
    for cat, items in cats.items():
        rows = "".join(
            f"<tr><td><code>{html.escape(c)}</code><br><a href='gambit:builder/"
            f"{html.escape(_builder_query(c))}'>open in Command Builder</a></td>"
            f"<td>{_inline(d)}</td></tr>" for c, d in items)
        body = (f"<p class='lead'>The {html.escape(cat.lower())} commands districts use most. "
                "Words in &lt;angle brackets&gt; are what you fill in.</p>"
                f"<table class='cmds'><tr><th>Command</th><th>What it does</th></tr>{rows}"
                "</table>")
        out.append(Article(f"gam:cat:{_slug(cat)}", cat, ["GAM commands", "Common commands"],
                           body, _plain(body), cat, weight=1.0))
        for c, d in items:
            b = (f"<p class='lead'>{_inline(d)}</p><pre>{html.escape(c)}</pre>"
                 f"<p><a href='gambit:builder/{html.escape(_builder_query(c))}'>Open in the "
                 f"Command Builder</a> · <a href='gambit:article/gam:cat:{_slug(cat)}'>More "
                 f"{html.escape(cat)} commands</a></p>")
            out.append(Article(f"gam:cmd:{_slug(c)}", c.replace("gam ", "", 1),
                               ["GAM commands", "Common commands", cat], b, _plain(b) + " " + c,
                               cat, command=c, weight=1.1))
    if include_catalog:
        out += catalog_articles()
    return out


def _builder_query(cmd: str) -> str:
    words = [w for w in cmd.replace("gam ", "", 1).split()
             if not w.startswith(("<", '"', "\\")) and w.isascii()]
    return " ".join(w.split("|")[0] for w in words[:4])


def catalog_articles() -> list[Article]:
    """Every command in GAM's own reference, one article per section."""
    try:
        from .. import command_catalog as cc
        text, source = cc.load_text()
        cmds, _defs = cc.parse_file(text) if text else ([], {})
    except Exception:  # noqa: BLE001
        return []
    by: dict[str, list] = {}
    for c in cmds:
        sec = (c.section or "Other").strip()
        if sec.startswith("[") or len(sec) > 70:
            sec = "Other"
        c.title, c.description = cc._describe(c)
        by.setdefault(sec, []).append(c)
    out = []
    for sec, items in sorted(by.items()):
        rows = "".join(
            f"<tr><td>{_inline(c.description)}<br><code>{html.escape(c.syntax)}</code><br>"
            f"<a href='gambit:builder/{html.escape(_builder_query(c.title))}'>open in Command "
            f"Builder</a></td></tr>" for c in items)
        body = (f"<p class='lead'>Every <b>{html.escape(sec)}</b> command in GAM's reference "
                f"({len(items)}), with the full syntax. [ ] = optional, | = one of, "
                "&lt;Name&gt; = fill in.</p>"
                f"<table class='cmds'>{rows}</table>"
                f"<p class='muted'>From GamCommands.txt ({html.escape(source)}).</p>")
        out.append(Article(f"gam:all:{_slug(sec)}", sec, ["GAM commands", "Every command"],
                           body, _plain(body), "", weight=0.6))
    return out


# ================================================================ search ===
STOP = {"who", "has", "have", "how", "do", "does", "i", "the", "a", "an", "to", "what", "my",
        "is", "of", "for", "in", "on", "can", "we", "our", "and", "or", "with", "it", "me",
        "find", "show", "where", "gam", "someone", "someone's", "their", "them", "out"}


def _base(query: str) -> list[str]:
    words = [t for t in re.split(r"[\s,?]+", (query or "").lower().strip()) if t]
    keep = [t for t in words if t not in STOP]
    return keep or [t for t in words if t != "gam"]


def _terms(query: str) -> list[str]:
    q = (query or "").lower().strip()
    try:
        from ..command_catalog import SYNONYMS
    except Exception:  # noqa: BLE001
        SYNONYMS = {}
    extra = []
    for phrase, repl in SYNONYMS.items():
        if phrase in q.split() or (" " in phrase and phrase in q):
            extra.append(repl)
    terms = _base(q)
    return terms + [e for e in extra if e not in terms]


def search(articles: list[Article], query: str, limit: int = 80) -> list[Article]:
    terms = _terms(query)
    if not terms:
        return []
    base = _base(query)
    res = _score(articles, terms, base, query, need_all=True)
    if len(res) < 3 and len(base) > 1:          # nothing has every word – rank by most
        seen = {a.id for a in res}
        res += [a for a in _score(articles, terms, base, query, need_all=False)
                if a.id not in seen]
    return res[:limit]


def _score(articles, terms, base, query, need_all: bool) -> list[Article]:
    scored = []
    for a in articles:
        title, kw = a.title.lower(), (a.keywords or "").lower()
        body = a.text.lower()
        crumbs = " ".join(a.path).lower()
        hits = sum(1 for t in base if t in title or t in kw or t in body or t in crumbs)
        if (need_all and hits < len(base)) or not hits:
            continue
        s = 0.0
        for t in terms:
            if t in title:
                s += 12 + (6 if re.search(rf"\b{re.escape(t)}", title) else 0)
            if t in kw:
                s += 6
            if t in crumbs:
                s += 3
            s += min(body.count(t), 5) * 1.5
        if " ".join(base) in title:
            s += 15
        scored.append((s * a.weight * (hits / len(base)), a))
    scored.sort(key=lambda x: -x[0])
    return [a for _s, a in scored]


def highlight(htm: str, query: str) -> str:
    terms = sorted({t for t in _terms(query) if len(t) > 1}, key=len, reverse=True)
    if not terms:
        return htm
    pat = re.compile("(" + "|".join(re.escape(html.escape(t)) for t in terms) + ")", re.I)
    parts = re.split(r"(<[^>]+>)", htm)
    return "".join(p if p.startswith("<") else pat.sub(r"<span class='hl'>\1</span>", p)
                   for p in parts)


def snippet(a: Article, query: str, n: int = 160) -> str:
    t = re.sub(r"\s+", " ", a.text).strip()
    terms = _terms(query)
    i = min((t.lower().find(x) for x in terms if t.lower().find(x) >= 0), default=0)
    start = max(0, i - 50)
    return ("…" if start else "") + t[start:start + n] + ("…" if start + n < len(t) else "")


# ================================================================ export ===
CSS = """
body{font-family:Segoe UI,Arial,sans-serif;font-size:14px;line-height:1.5;color:#1d2433;
max-width:980px;margin:0 auto;padding:16px}
h1{font-size:24px;margin:8px 0}h2{font-size:19px;margin:22px 0 4px;border-bottom:1px solid
#dfe3ea;padding-bottom:4px}h3{font-size:15px;margin:14px 0 4px}
code,pre{font-family:Consolas,monospace;background:#f2f4f8;border-radius:4px;padding:1px 4px}
pre{padding:8px;white-space:pre-wrap}.lead{font-size:15px}.muted{color:#66708a}
.hl{background:#ffe58a}table.cmds{border-collapse:collapse;width:100%}
table.cmds td,table.cmds th{border-bottom:1px solid #e4e7ee;padding:6px;vertical-align:top;
text-align:left}.crumb{color:#66708a;font-size:12px}a{color:#1a5fd0}
"""


def export_html(articles: list[Article], title: str = "GAMbit guide") -> str:
    """One self-contained page with a search box, for printing or sharing."""
    secs = []
    for a in articles:
        if a.id.startswith("gam:all:"):
            continue
        body = re.sub(r"<a href='gambit:[^']*'>(.*?)</a>", r"\1", a.body)
        secs.append(f"<section data-s=\"{html.escape((a.title + ' ' + a.keywords + ' ' + a.text).lower())}\">"
                    f"<div class='crumb'>{html.escape(' › '.join(a.path))}</div>"
                    f"<h2 id='{_slug(a.id)}'>{html.escape(a.title)}</h2>{body}</section>")
    js = ("function f(q){q=q.toLowerCase().split(/\\s+/).filter(Boolean);"
          "document.querySelectorAll('section').forEach(s=>{s.style.display=q.every(t=>"
          "s.dataset.s.includes(t))?'':'none'})}")
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}"
            f"</title><style>{CSS} #q{{width:100%;padding:8px;font-size:15px}}</style>"
            f"<script>{js}</script></head><body><h1>{html.escape(title)}</h1>"
            "<input id='q' placeholder='Search…' oninput='f(this.value)'>"
            + "".join(secs) + "</body></html>")
