"""“What's new” – shown once after an update, listing what changed with links to the pages.

Each entry has a stable id; a PC remembers which ids it has shown. A brand-new install
doesn't get the whole history – it starts with everything marked as seen.
"""

from __future__ import annotations

import json

from .settings import settings

SEEN_KEY = "whatsnew/seen"

ENTRIES = [
    # ----- round 41
    {"id": "gam-keys", "title": "GAM's keys locked down",
     "text": "GAMbit checks who on this PC can open GAM's keys (they control your whole "
             "Google domain) or change gam.exe, and Settings & Updates → GAM location → Lock "
             "down GAM's keys fixes it in one click.", "page": "Settings & Updates"},
    {"id": "group-restore", "title": "Put a whole group back",
     "text": "The Account time machine now saves every group's members each night – outside "
             "addresses and groups inside groups too – and can put a group back to how it was "
             "on any day.", "page": "Account time machine"},
    {"id": "suspend-notice", "title": "Notice before suspending",
     "text": "A clean-up rule that suspends inactive accounts can email people (and their "
             "manager) first. Anyone who signs in during the notice drops off the list.",
     "page": "Clean-up rules"},
    # ----- round 40
    {"id": "sso-certs", "title": "Sign-in certificate warnings",
     "text": "Single sign-on → Certificates reads your sign-in provider's certificate "
             "(ClassLink, Clever, ADFS…) and warns 30, 14 and 3 days before it expires – "
             "and when the provider starts using one Google doesn't have yet. Add the "
             "provider's metadata link once.", "page": "Single sign-on"},
    {"id": "mail-dns", "title": "Email security check",
     "text": "Domain & extras → Email security checks SPF, DKIM, DMARC and MX for every "
             "domain and says exactly what to change, so nobody can easily send mail that "
             "looks like it's from the district.", "page": "Domain & extras"},
    {"id": "log-seal", "title": "Tamper-evident activity log",
     "text": "Every line in the activity log is fingerprinted, signed and chained to the one "
             "before. Activity log → Check the log for edits shows anything changed outside "
             "GAMbit, and Undo won't run from an edited line.", "page": "Activity log"},
    {"id": "spanish", "title": "Account cards in Spanish",
     "text": "Account cards, class card sets and Welcome sheets print in English, Spanish or "
             "both, with an optional note for families. Change any wording in Settings → "
             "Appearance and safety → Printouts.", "page": ""},
    {"id": "archive-delete", "title": "Archive before deleting",
     "text": "A clean-up rule that deletes old accounts can first hand their Drive files to an "
             "archive account; each account is deleted only after Google finishes the "
             "transfer. Every deletion is kept in a signed deletion record (Clean-up rules → "
             "Deletion record).", "page": "Clean-up rules"},
    # ----- round 39
    {"id": "side-tabs", "title": "Page tabs down the left",
     "text": "Every page's tabs are now a list down the left, like Settings & Updates. "
             "Prefer them across the top? Settings & Updates → Appearance and safety → "
             "Page tabs.", "page": "Users"},
    {"id": "update-dot", "title": "Settings & Updates link fixed",
     "text": "When an update is ready, the dot now goes on Settings & Updates itself – "
             "it no longer renamed the last page in the sidebar (which opened Ask GAMbit).",
     "page": ""},
    # ----- round 38 (security review)
    {"id": "sec-signed", "title": "Shared items are now signed",
     "text": "Run later items, offboarding plans, time-limited accounts, policy plans, "
             "automatic groups and approvals are signed by whoever made them, and background "
             "tasks skip anything unsigned or changed in the team folder. Open Settings → "
             "Team → Signatures & trust to check and sign items made before this version.",
     "page": "Settings & Updates"},
    {"id": "sec-approvals", "title": "Safer approvals",
     "text": "An approval covers the exact commands. If a request changes, it needs approving "
             "again, and nobody can approve their own two-person request. Email approvals "
             "are read from the approver's Sent mail. Approvals made before this version "
             "need approving again.", "page": "Approvals"},
    {"id": "sec-secrets", "title": "Secrets and passwords locked down",
     "text": "Tokens and the help-desk PIN (now 6+ characters) are stored encrypted, backups "
             "with secrets need a password, copied passwords clear from the clipboard after "
             "a minute, and passwords can't wait in Run later.", "page": ""},
    {"id": "sec-updates", "title": "Verified updates and deploy files",
     "text": "Updates to GAMbit, GAM and the local AI are checked before they install. Shared "
             "deploy files must be signed by a GAMbit admin or protected so only "
             "administrators can change them.", "page": ""},
    # ----- round 37 (QA review fixes)
    {"id": "qa-safety", "title": "Safety fixes from a full review",
     "text": "Practice mode is stricter (group changes and anyone outside the test org unit "
             "stay dry runs), saved Chromebook jobs and background tasks respect Dry run, "
             "Undo only puts back what really changed, and the year-end rollover pairs "
             "grades by number and stops if a move fails.", "page": ""},
    {"id": "qa-passwords", "title": "Fewer passwords kept on disk",
     "text": "The offboarding lock password is never saved, and passwords are removed from "
             "Run later items and approval requests once they've run.", "page": ""},
    # ----- round 36
    {"id": "first-day", "title": "First-day checklist",
     "text": "Home shows a short checklist for a new PC or a new tech – connect GAM, map "
             "schools, set a test account, try a dry run, pin pages, background tasks. Each "
             "item ticks itself off. The tour is updated for the new look too.",
     "page": "Home"},
    {"id": "jobs-fix", "title": "Running jobs pop-up fixed",
     "text": "Clicking “1 running” no longer freezes GAMbit – the job list is now a light "
             "pop-up that updates while it's open.", "page": ""},
    {"id": "next-steps", "title": "What's next?",
     "text": "After creating an account GAMbit offers the usual follow-ups – print the card, "
             "open the person, add them to a class. After suspending: move, transfer their "
             "files, sign out.", "page": "Users"},
    {"id": "paste-list", "title": "Paste a list",
     "text": "Paste a column of emails, names or student IDs (or Chromebook serials) into "
             "Paste a list… – GAMbit matches each one and shows what it couldn't.",
     "page": ""},
    {"id": "row-actions", "title": "Buttons on table rows",
     "text": "Hover a row for Open, Reset password and more at its right end.", "page": ""},
    {"id": "changes-today", "title": "Undo anything from today",
     "text": "The bell → Changes today (Ctrl+Shift+Z) lists today's changes, each with Undo "
             "when GAMbit knows how to put it back.", "page": ""},
    {"id": "simple-mode", "title": "Simple mode",
     "text": "Six big buttons for everyday jobs and a short sidebar – for staff who don't "
             "need everything. Settings & Updates → Appearance.", "page": "Settings & Updates"},
    {"id": "views-print", "title": "Saved views, printouts and tonight",
     "text": "Save a table's filter, columns and sort as a view (and pin it to Home), print "
             "or save any table as a PDF, and queue big changes to run tonight at 6 PM.",
     "page": ""},
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
