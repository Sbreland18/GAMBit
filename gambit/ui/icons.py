"""GAMbit's line icons (24×24, 1.8 px strokes, drawn in the current text or accent colour).

`icon("users")` gives a QIcon; `page_icon("Chromebook fleet")` the sidebar icon for a page.
Icons are plain SVG path data kept here, so nothing extra has to be bundled.
"""

from __future__ import annotations

from functools import lru_cache

P = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20h14V9.5"/>',
    "book": '<path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H20v15H5.5A1.5 1.5 0 0 0 4 19.5z"/>'
            '<path d="M4 19.5A1.5 1.5 0 0 0 5.5 21H20"/>',
    "flow": '<rect x="3" y="3" width="7" height="6" rx="1.5"/><rect x="14" y="15" width="7" '
            'height="6" rx="1.5"/><path d="M6.5 9v3a3 3 0 0 0 3 3h4.5"/>',
    "school": '<path d="m2 9 10-5 10 5-10 5z"/><path d="M6 11v5c3 2 9 2 12 0v-5"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 '
             '1.9 6.5 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7"/><path d="M18 14.8c2 .7 3.2 '
             '2.5 3.6 5.2"/>',
    "user-x": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5 '
              '1.6 0 3 .5 4.1 1.3"/><path d="m16 15 5 5M21 15l-5 5"/>',
    "building": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 7h1M14 7h1'
                'M9 11h1M14 11h1M9 15h1M14 15h1M10 21v-3h4v3"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4.2 4-6.5 8-6.5s7 2.3 8 6.5"/>',
    "user-check": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5 '
                  '1.6 0 3 .5 4.1 1.3"/><path d="m15 18 2 2 4-4"/>',
    "id-card": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" '
               'r="2.5"/><path d="M5.5 17c.6-1.8 1.9-2.7 3.5-2.7s2.9.9 3.5 2.7"/>'
               '<path d="M15 10h3M15 14h3"/>',
    "group": '<circle cx="7" cy="9" r="3"/><circle cx="17" cy="9" r="3"/><path d="M2 19c.6-'
             '2.8 2.5-4.3 5-4.3s4.4 1.5 5 4.3"/><path d="M12 19c.6-2.8 2.5-4.3 5-4.3s4.4 1.5 '
             '5 4.3"/>',
    "sync": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "compare": '<path d="M8 3v18M16 3v18"/><path d="m4 7 4-4 4 4"/><path d="m12 17 4 4 4-4"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v4h4"/><path d="M12 8v4l3 2"/>',
    "sparkle": '<path d="M12 3 13.8 9 20 10.5 13.8 12 12 18 10.2 12 4 10.5 10.2 9z"/>',
    "fields": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h10M7 13h6"/>',
    "laptop": '<rect x="4" y="5" width="16" height="11" rx="2"/><path d="M2 19h20"/>',
    "monitor": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "share": '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle '
             'cx="18" cy="18" r="2.5"/><path d="m8.2 10.8 7.6-3.6M8.2 13.2l7.6 3.6"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 '
              '1-2-2z"/>',
    "chat": '<path d="M4 18.5 5.5 14A8 8 0 1 1 9 19z"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 '
                '3v4"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" '
            'height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect '
            'x="14" y="14" width="7" height="7" rx="1.5"/>',
    "tree": '<rect x="9" y="3" width="6" height="5" rx="1"/><rect x="3" y="16" width="6" '
            'height="5" rx="1"/><rect x="15" y="16" width="6" height="5" rx="1"/><path d="M12 '
            '8v4M6 16v-2h12v2"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9"/><path d="m17 6 3 3"/>',
    "wallet": '<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M16 12.5h2"/><path '
              'd="M3 9h15a2 2 0 0 0 2-2V5"/>',
    "policy": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4"/><path d="M10 12h5M10 16h5"/>',
    "rocket": '<path d="M5 15c-1 1-1.5 3.5-1.5 5.5 2 0 4.5-.5 5.5-1.5"/><path d="M9 15 6 12c2'
              '-6 6-9 12-9 0 6-3 10-9 12z"/><circle cx="14.5" cy="9.5" r="1.5"/>',
    "lock": '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 '
            '0v3"/>',
    "shield": '<path d="M12 3 4 6v6c0 4.5 3.4 7.9 8 9 4.6-1.1 8-4.5 8-9V6z"/><path d="m9 12 2 '
              '2 4-4"/>',
    "scale": '<path d="M12 3v18M7 21h10"/><path d="M5 7h14"/><path d="m5 7-3 6a3 3 0 0 0 6 '
             '0z"/><path d="m19 7-3 6a3 3 0 0 0 6 0z"/>',
    "inbox": '<path d="M3 13h5l1.5 3h5l1.5-3h5"/><path d="M5 5h14l2 8v6H3v-6z"/>',
    "lifebuoy": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/><path '
                'd="m5.6 5.6 4 4M14.4 14.4l4 4M18.4 5.6l-4 4M9.6 14.4l-4 4"/>',
    "login": '<path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4"/><path d="M10 16l4-4-4-4"/>'
             '<path d="M14 12H4"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 3 2.5 15 '
             '0 18M12 3c-2.5 3-2.5 15 0 18"/>',
    "chart": '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 '
             '20H2"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "trend": '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3z"/>',
    "brain": '<path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 0V4.5A2.5 '
             '2.5 0 0 0 9 4z"/><path d="M15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 '
             '0 1-6 0"/>',
    "broom": '<path d="m14 4 6 6"/><path d="m12 8 4 4-6 8H4v-6z"/><path d="M7 17l2 2"/>',
    "alert": '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4"/><path d="M12 17h.01"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" '
           'cy="12" r="3"/>',
    "activity": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "x-circle": '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    "ticket": '<path d="M3 8a2 2 0 0 0 2-2h14a2 2 0 0 0 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 0-2 '
              '2H5a2 2 0 0 0-2-2v-2a2 2 0 0 0 0-4z"/><path d="M13 6v12"/>',
    "snow": '<path d="M12 2v20M4 6.5l16 11M20 6.5l-16 11"/>',
    "file-clock": '<path d="M7 3h7l4 4v5"/><path d="M14 3v4h4"/><path d="M7 3v18h5"/><circle '
                  'cx="17" cy="17" r="4"/><path d="M17 15v2l1.5 1"/>',
    "calendar-clock": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 '
                      '3v4M16 3v4"/><path d="M12 13v3l2 1"/>',
    "wand": '<path d="m4 20 12-12"/><path d="m14 6 4 4"/><path d="M18 3v3M20 4.5h-3"/>',
    "code": '<path d="m8 8-5 4 5 4M16 8l5 4-5 4"/>',
    "table": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16"/>',
    "terminal": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 '
                '15h4"/>',
    "stethoscope": '<path d="M6 3v6a5 5 0 0 0 10 0V3"/><path d="M11 14v2a5 5 0 0 0 10 0v-2"/>'
                   '<circle cx="21" cy="12" r="1.5"/>',
    "flask": '<path d="M9 3h6"/><path d="M10 3v6L4.5 18.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 '
             '1.5-2.5L14 9V3"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 .5c0 1.5-2.5 2-2.5'
            ' 3.5"/><path d="M12 17h.01"/>',
    "settings": '<path d="M4 6h10"/><path d="M18 6h2"/><circle cx="16" cy="6" r="2"/><path '
                'd="M4 12h4"/><path d="M12 12h8"/><circle cx="10" cy="12" r="2"/><path d="M4 '
                '18h12"/><circle cx="18" cy="18" r="2"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    "printer": '<path d="M7 9V3h10v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path '
               'd="M7 14h10v7H7z"/>',
    "pin": '<path d="M9 4h6l-1 5 3 3H7l3-3z"/><path d="M12 12v8"/>',
    "chevron-left": '<path d="m15 6-6 6 6 6"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "graduation": '<path d="m2 9 10-5 10 5-10 5z"/><path d="M6 11v5c3 2 9 2 12 0v-5"/>',
    "message": '<path d="M4 5h16v11H9l-5 4z"/>',
    "dot": '<circle cx="12" cy="12" r="4"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 '
            '2-2h9"/>',
    "dot-fill": '<circle cx="12" cy="12" r="2.6" stroke-width="5.2"/>',
    "star": '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    "play": '<path d="M7 4.5v15l12-7.5z"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 '
            '4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "note": '<path d="M5 3h10l4 4v14H5z"/><path d="M9 12h6M9 16h4"/>',
}

# leading emoji in button labels → the matching line icon
EMOJI = {"✅": "check-circle", "🖨": "printer", "☆": "star", "★": "star", "🔎": "search",
         "🔍": "search", "📌": "pin", "▶": "play", "⚙": "settings", "🧪": "flask",
         "🎓": "graduation", "💬": "chat", "📝": "note", "🔗": "link", "🕘": "history",
         "✨": "sparkle", "🔒": "lock", "👤": "user", "👥": "group", "💻": "laptop",
         "🏢": "tree", "📦": "folder", "🔔": "bell", "↻": "sync", "⟳": "sync", "✉": "mail",
         "📧": "mail", "📋": "list", "🗑": "x-circle", "➕": "plus", "+": "plus"}


def split_emoji(text: str):
    """('✅ Check everything') → ('check-circle', 'Check everything'); else (None, text)."""
    t = (text or "").lstrip()
    for k, name in EMOJI.items():
        if k != "+" and t.startswith(k):
            rest = t[len(k):].lstrip("\ufe0f").lstrip()
            return name, rest
    return None, text

PAGE = {
    "Home": "home", "Guide": "book", "Workflows": "flow", "Back to school": "school",
    "Senior checkout": "graduation", "Users": "users", "Student lookup": "user-check",
    "Staff card": "id-card", "Groups": "group", "Classroom": "school",
    "Roster sync": "sync", "Mismatch report": "compare", "Account timeline": "history",
    "Account time machine": "clock", "Directory quality": "sparkle",
    "Custom field check": "fields", "Chromebooks": "laptop", "Chromebook fleet": "laptop",
    "Staff devices": "monitor", "Chromebook sharing": "share", "Device history": "history",
    "Windows, Mac & phones": "monitor", "Email": "mail", "Google Drive": "folder",
    "Shared drives by school": "folder", "Chat posts": "chat",
    "Staff calendar status": "calendar", "More services": "grid", "Org units": "tree",
    "Licenses": "key", "Budget planner": "wallet", "Policies by org unit": "policy",
    "Policy rollouts": "rocket", "2-Step Verification": "lock", "Ownership check": "eye",
    "Security baseline": "shield", "Records requests": "scale", "Access review": "shield",
    "Cost per student": "wallet", "Mailbox access review": "inbox",
    "Account recovery": "lifebuoy", "Single sign-on": "login", "Domain & extras": "globe",
    "Reports": "chart", "School reports": "chart", "Teacher lists": "list",
    "Audit report": "list", "Students going quiet": "trend", "Account timing": "clock",
    "Storage forecast": "trend", "Meet attendance": "video", "AI use": "brain",
    "Clean-up by school": "broom", "Security reports": "alert", "Investigations": "search",
    "Usage": "chart", "Settings watch": "eye", "Changes outside GAMbit": "activity",
    "Activity log": "activity", "Approvals": "check-circle", "Ticket queue": "ticket",
    "Run later & freezes": "snow", "Stale content": "file-clock",
    "Schedules": "calendar-clock", "Clean-up rules": "wand", "Command Builder": "code",
    "Bulk (CSV)": "table", "Command Console": "terminal", "Diagnostics": "stethoscope",
    "Live test": "flask", "Ask GAMbit": "help", "Settings & Updates": "settings",
}


def svg(name: str, color: str = "#374151", stroke: float = 1.8) -> str:
    body = P.get(name) or P["dot"]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
            f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke}" '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


@lru_cache(maxsize=512)
def _pixmap(name: str, color: str, size: int, ratio: float):
    from PySide6.QtCore import QByteArray, QRectF, Qt
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer
    r = QSvgRenderer(QByteArray(svg(name, color).encode()))
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r.render(p, QRectF(0, 0, size * ratio, size * ratio))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def default_color() -> str:
    try:
        from .theme import tokens
        return tokens()["icon"]
    except Exception:  # noqa: BLE001
        return "#374151"


def icon(name: str, color: str | None = None, size: int = 20):
    """A QIcon (normal colour, plus the accent for the selected state)."""
    from PySide6.QtGui import QGuiApplication, QIcon
    ratio = 2.0
    try:
        ratio = max(1.0, QGuiApplication.primaryScreen().devicePixelRatio()) * 1.0
    except Exception:  # noqa: BLE001
        pass
    ic = QIcon()
    ic.addPixmap(_pixmap(name, color or default_color(), size, ratio), QIcon.Normal, QIcon.Off)
    try:
        from .theme import tokens
        sel = tokens()["accent_text"]
    except Exception:  # noqa: BLE001
        sel = "#2563EB"
    ic.addPixmap(_pixmap(name, sel, size, ratio), QIcon.Selected, QIcon.Off)
    ic.addPixmap(_pixmap(name, sel, size, ratio), QIcon.Active, QIcon.Off)
    return ic


def page_icon(page: str, color: str | None = None):
    return icon(PAGE.get(page, "dot"), color)


def clear_cache():
    _pixmap.cache_clear()


def set_icon(widget, name: str, color: str | None = None, size: int = 20):
    """Give a button its icon and remember it, so switching light/dark redraws it."""
    widget.setProperty("_gb_icon", name)
    widget.setProperty("_gb_icon_color", color or "")
    widget.setProperty("_gb_icon_size", size)
    widget.setIcon(icon(name, color, size))


def refresh_icons():
    from PySide6.QtWidgets import QApplication
    clear_cache()
    for w in QApplication.allWidgets():
        try:
            name = w.property("_gb_icon")
            if name:
                w.setIcon(icon(name, w.property("_gb_icon_color") or None,
                               int(w.property("_gb_icon_size") or 20)))
        except Exception:  # noqa: BLE001
            continue
