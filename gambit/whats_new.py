"""“What's new” – shown once after an update, listing what changed with links to the pages.

Each entry has a stable id; a PC remembers which ids it has shown. A brand-new install
doesn't get the whole history – it starts with everything marked as seen.
"""

from __future__ import annotations

import json

from .settings import settings

SEEN_KEY = "whatsnew/seen"

ENTRIES = [
    # ----- this round
    {"id": "jobs-chip", "title": "See what's running",
     "text": "While GAM commands work, the top bar shows “2 running” (or a percentage). Click "
             "it for each job's progress, how long it's taken and a Stop button.", "page": ""},
    {"id": "friendly-values", "title": "Dates you can read",
     "text": "Tables show “Oct 12, 2026 (16 days ago)” and Yes/No instead of raw timestamps "
             "and True/False. Hover for the exact value; exports keep it. Hover an email or "
             "serial for a copy button.", "page": "Users"},
    {"id": "steps", "title": "Create a user, step by step",
     "text": "Users → Create a user and Workflows → New staff are now Details → extras → "
             "Review, and Review lists exactly what will happen before anything runs. "
             "Missing or wrong fields are marked right on the form.", "page": "Users"},
    {"id": "find-setting", "title": "Find any setting",
     "text": "Settings & Updates has a list of sections and a search box – type “tray”, "
             "“accent” or “backup”.", "page": "Settings & Updates"},
    {"id": "details-panel", "title": "Details without leaving your list",
     "text": "Click a person, group or Chromebook in any table and their details and actions "
             "slide in from the right. Double-click still opens the full page; Esc closes "
             "the panel.", "page": ""},
    {"id": "home-edit", "title": "Arrange Home by dragging",
     "text": "Home → Customize: drag boxes by their handle, use ↑ ↓ ✕, or Add a box. "
             "Done saves it.", "page": "Home"},
    {"id": "tables-2", "title": "Tables you can shape",
     "text": "The list button next to Google Sheet: compact or comfortable rows, and "
             "Columns… to hide or reorder columns (remembered per page). Tables also show "
             "loading rows and say why they're empty.", "page": "Users"},
    {"id": "nav-2", "title": "Back button and a shorter sidebar",
     "text": "← Back in the top bar (or Alt+Left) returns to the page you came from. Pages "
             "in My pages aren't listed twice, and other sections fold as you move around "
             "(right-click the sidebar to change either).", "page": ""},
    {"id": "modern-look-2", "title": "Home, redesigned",
     "text": "Number tiles with icons and 30-day trend lines, one big look-up box for people "
             "and Chromebooks, recently viewed people with their school, and a cleaner top "
             "bar. The Output panel now starts hidden – Show output in the bottom-right "
             "corner (or Ctrl+L) brings it back.", "page": "Home"},
    {"id": "modern-look", "title": "A fresh, modern look",
     "text": "New colours, icons and an icon-only sidebar option, an accent colour of your "
             "choice (Settings & Updates → Appearance), and a Needs your attention box on "
             "Home.", "page": "Settings & Updates"},
    {"id": "palette", "title": "Ctrl+K finds anything",
     "text": "Press Ctrl+K and type a person, Chromebook, group, page or task. The actions "
             "for the person you found are right there.", "page": ""},
    {"id": "toasts", "title": "Undo from the pop-up",
     "text": "After a change a small pop-up says what was done, with Undo. The bell in the "
             "top bar keeps every pop-up and alert.", "page": ""},
    # ----- earlier
    {"id": "home-custom", "title": "Make Home yours",
     "text": "Choose what Home shows and in what order – recent items, quick look-up, your "
             "approvals, notes, links and more. Home → Customize.", "page": "Home"},
    {"id": "my-pages", "title": "My pages and folding sections",
     "text": "Pin the pages you use to the top of the sidebar (right-click a page). Your most "
             "used pages appear there too, and sections fold with a click.", "page": ""},
    {"id": "tray", "title": "GAMbit stays in the tray",
     "text": "Closing the window keeps GAMbit running in the taskbar tray, with alerts when a "
             "long job finishes, a background job fails or an approval is waiting.",
     "page": "Settings & Updates"},
    {"id": "recent", "title": "Recently viewed",
     "text": "The people, Chromebooks, groups and org units you opened lately are on Home "
             "and at the top of the search box.", "page": "Home"},
    {"id": "fix-person", "title": "Check everything about a person",
     "text": "Student lookup → Check everything: suspended, password, sign-in, org unit, "
             "custom fields, Chromebook and license – each problem with a fix button.",
     "page": "Student lookup"},
    {"id": "print-card", "title": "Printable account cards",
     "text": "Student lookup → Print card: name, email, a fresh temporary password, their "
             "Chromebook and a QR code, ready to hand out.", "page": "Student lookup"},
    {"id": "ticket-first", "title": "Work from a ticket",
     "text": "Ticket queue → Work on it opens the person, checks everything, and adds what "
             "you fixed to the ticket.", "page": "Ticket queue"},
    {"id": "preview", "title": "Before → after previews",
     "text": "Before a change runs, “Show before → after” lists each field as it is now and "
             "as it will be.", "page": ""},
    {"id": "digest2", "title": "A fuller weekly digest",
     "text": "Changes by each tech, failed background jobs, licenses running low and "
             "Chromebooks that dropped off.", "page": "Settings & Updates"},
    {"id": "practice", "title": "Practice mode for new techs",
     "text": "Changes to the test account and test org unit run for real; everything else "
             "is a dry run. Turn it on in the top bar or Settings.", "page": "Settings & Updates"},
    {"id": "feedback", "title": "Send feedback",
     "text": "Help → Send feedback saves the problem report and emails it, details attached.",
     "page": ""},
    # ----- earlier rounds
    {"id": "fast-start", "title": "Faster start-up",
     "text": "A start-up screen shows what GAMbit is doing, and pages are built when you "
             "open them.", "page": ""},
    {"id": "field-check", "title": "Custom field check",
     "text": "Compare grade and school fields with the org unit map, and fill custom fields "
             "from the SIS.", "page": "Custom field check"},
    {"id": "search-sheets", "title": "Saved searches that keep a Google Sheet up to date",
     "text": "Users → Find / list users → Saved → Google Sheet…", "page": "Users"},
    {"id": "sharing-history", "title": "Chromebook sharing and device history",
     "text": "Spot swaps, and see every Chromebook a student has had.",
     "page": "Chromebook sharing"},
    {"id": "seniors", "title": "Senior checkout",
     "text": "Takeout reminders, Chromebook collection, then move and suspend on dates you "
             "pick.", "page": "Senior checkout"},
    {"id": "cleanup-school", "title": "Clean-up by school",
     "text": "A to-do list per building, emailed to each school's tech.",
     "page": "Clean-up by school"},
    {"id": "more-gam", "title": "More of GAM",
     "text": "Single sign-on, Windows/Mac/phones, shared drives by school, Chat posts, staff "
             "calendar status, domain aliases and more.", "page": "Single sign-on"},
]


def seen() -> set[str]:
    try:
        v = json.loads(settings.get(SEEN_KEY, "") or "null")
    except ValueError:
        v = None
    return set(v) if isinstance(v, list) else set()


def first_run_check():
    """A PC that never saw 'What's new' and is brand new (setup not finished) starts with
    everything marked as seen; an existing install gets the list once."""
    if settings.get(SEEN_KEY, None) in (None, ""):
        if not settings.get("setup/seen", False) and not settings.get("gam/dir", ""):
            mark_seen([e["id"] for e in ENTRIES])


def unseen() -> list[dict]:
    s = seen()
    return [e for e in ENTRIES if e["id"] not in s]


def mark_seen(ids):
    settings.set(SEEN_KEY, json.dumps(sorted(seen() | set(ids))))
