"""Showing text that may contain values from Google, tickets, the SIS or the team folder.

Qt treats a label's text as HTML when it *looks* like HTML, so a group name, ticket subject
or workflow title containing markup could restyle a message, hide the lines after it
(“<!--”), add links, or load an image from a network path (on Windows, a file:// image on a
share makes the PC try to sign in to that server). Everything shown goes through here:
plain text stays plain; GAMbit's own simple formatting is kept; everything else is removed.
"""

from __future__ import annotations

import html
import re

ALLOWED = {"b", "i", "u", "em", "strong", "br", "p", "ul", "ol", "li", "small", "big",
           "code", "tt", "pre", "h3", "h4", "hr", "span", "div", "table", "tr", "td", "th",
           "a", "sup", "sub"}
_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b([^<>]*)>")
_COMMENT = re.compile(r"<!--.*?(-->|$)", re.S)
_LOOKS = re.compile(r"<(/?)(%s)\b[^<>]*>" % "|".join(sorted(ALLOWED)), re.I)
# https:// pages, GAMbit's own gambit: links, and plain words a label handles itself
SAFE_HREF = re.compile(r"^(https://[^\s\"'<>]+|gambit:[^\s\"'<>]*|[A-Za-z0-9_#-]+)$")
_STYLE_OK = re.compile(r"^(\s*(color|font-weight|font-size|font-style|margin[a-z-]*|"
                       r"padding[a-z-]*|text-align)\s*:\s*[#\w .%-]+;?)*\s*$", re.I)


def esc(value) -> str:
    """A value placed into GAMbit's own HTML."""
    return html.escape(str(value if value is not None else ""), quote=True)


def might_be_rich(text: str) -> bool:
    """Exactly Qt's own test for 'show this as HTML'."""
    from PySide6 import QtGui
    try:
        return bool(QtGui.Qt.mightBeRichText(text or ""))
    except Exception:  # noqa: BLE001
        return looks_rich(text)


def safe_auto(text):
    """For a label left on automatic format: if Qt would show it as HTML, clean it first."""
    if isinstance(text, str) and "<" in text and might_be_rich(text):
        return clean(text)
    return text


def install_label_guard():
    """Every QLabel GAMbit makes cleans HTML before Qt renders it (replaces the class in
    PySide6.QtWidgets before the UI modules import it). Labels set to plain text are left
    alone; links that aren't https:// or GAMbit's own are removed."""
    from PySide6 import QtWidgets
    from PySide6.QtCore import Qt
    lab = QtWidgets.QLabel
    if getattr(lab, "_gb_safe", False):
        return
    lab._gb_safe = True
    o_init, o_set = lab.__init__, lab.setText

    def __init__(self, *a, **k):
        if a and isinstance(a[0], str):
            a = (safe_auto(a[0]),) + a[1:]
        if isinstance(k.get("text"), str):
            k["text"] = safe_auto(k["text"])
        o_init(self, *a, **k)

    def setText(self, text):
        if isinstance(text, str):
            fmt = self.textFormat()
            if fmt == Qt.RichText:
                text = clean(text)
            elif fmt == Qt.AutoText:
                text = safe_auto(text)
        o_set(self, text)
    lab.__init__ = __init__
    lab.setText = setText

    # Rich text views never fetch images from the network or a file share (a UNC path
    # makes Windows try to sign in to that server – leaking the tech's login hash).
    tb = QtWidgets.QTextBrowser
    orig = tb.loadResource

    def guarded(self, typ, url):
        scheme = (url.scheme() or "").lower()
        if scheme in ("http", "https", "ftp", "smb") or (scheme == "file" and url.host()):
            return None
        if url.toString().startswith(("\\\\", "//")):
            return None
        return orig(self, typ, url)
    tb.loadResource = guarded


def looks_rich(text: str) -> bool:
    """Like Qt's own guess (it looks at the first line), so messages render as before –
    but what renders as HTML is cleaned first."""
    first = (text or "").split("\n", 1)[0]
    return bool(_LOOKS.search(first) or "<!--" in first)


def clean(text: str) -> str:
    """Keep simple formatting tags; drop comments, scripts, images, unknown tags and every
    attribute except a harmless style and https:// links."""
    t = _COMMENT.sub("", text or "")
    t = re.sub(r"<(script|style|iframe|object|embed|noscript|template)\b.*?"
               r"(</\1\s*>|$)", "", t, flags=re.I | re.S)   # the tag and what's inside
    t = re.sub(r"<(img|link|meta|base|input|form)\b[^>]*>?", "", t, flags=re.I | re.S)

    def tag(m):
        close, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if name not in ALLOWED:
            return esc(m.group(0))
        if close:
            return f"</{name}>"
        keep = []
        for an, av in re.findall(r'([a-zA-Z-]+)\s*=\s*"([^"]*)"', attrs) + \
                re.findall(r"([a-zA-Z-]+)\s*=\s*'([^']*)'", attrs):
            an = an.lower()
            if an == "href" and name == "a" and SAFE_HREF.match(av):
                keep.append(f'href="{esc(av)}"')
            elif an == "style" and _STYLE_OK.match(av) and "url" not in av.lower():
                keep.append(f'style="{esc(av)}"')
        return f"<{name}{' ' + ' '.join(keep) if keep else ''}>"
    return _TAG.sub(tag, t)


def set_label(label, text: str):
    """Put text on a QLabel safely (plain unless it's GAMbit-style simple HTML)."""
    from PySide6.QtCore import Qt
    text = text or ""
    if looks_rich(text):
        label.setTextFormat(Qt.RichText)
        label.setText(clean(text))
    else:
        label.setTextFormat(Qt.PlainText)
        label.setText(text)


def open_link(url: str):
    """Links in messages open only when they're https:// web pages."""
    if re.match(r"^https://[^\s\"'<>]+$", url or ""):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(url))
