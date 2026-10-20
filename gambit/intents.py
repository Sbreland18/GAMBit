"""“What do you want to do?” – plain-English tasks for the top search box."""

from __future__ import annotations

# (label shown, extra words people type, page, tab text or None)
INTENTS = [
    ("Reset a password", "password reset forgot locked change pw", "Student lookup", None),
    ("Look up a student", "find student who kid lookup", "Student lookup", None),
    ("Add a new staff member", "new hire onboard create staff teacher account",
     "Workflows", "New staff"),
    ("Someone is leaving", "offboard leave left quit retire terminate staff leaving",
     "Workflows", "Staff leaving"),
    ("Set up new hires from the HR sheet", "hr sheet onboarding new hires staff sync",
     "Roster sync", None),
    ("Import rooms and resources", "rooms resources calendar building conference book",
     "More services", "Calendar"),
    ("Roll out the email signature", "signature everyone district template rollout",
     "Email", "Signatures"),
    ("Guardian report for principals", "parent guardian invitations report principal",
     "Classroom", "Guardian report"),
    ("Upload profile photos", "photo picture day pictures headshot", "Users", "Photos"),
    ("Restore a deleted account", "undelete restore deleted recover account", "Users",
     "Recently deleted"),
    ("Restart or wipe Chromebooks remotely", "reboot restart remote command powerwash wipe "
     "volume screenshot", "Chromebooks", "Send a command"),
    ("Check Chromebook batteries", "battery health telemetry storage", "Chromebook fleet",
     "Health"),
    ("Find extensions on Chromebooks", "extension extensions apps vpn proxy installed",
     "Chromebook fleet", "Apps & extensions"),
    ("Set up Chromebook printers", "printer printers print", "Chromebook fleet", "Printers"),
    ("Change a Chrome policy", "chrome policy setting wallpaper blocklist copy policies",
     "Policies by org unit", None),
    ("Who opened or downloaded a file", "audit who viewed downloaded shared file leak drive log",
     "Investigations", "Audit log"),
    ("Suspicious sign-ins", "login suspicious failed sign in hacked compromised",
     "Investigations", "Audit log"),
    ("Meet usage report", "meet meetings usage hours", "Investigations", "Meet usage"),
    ("Remove a risky app from everyone", "oauth token app revoke third party block",
     "Investigations", "App access"),
    ("Make a dynamic group", "dynamic group rule automatic cloud identity", "Groups",
     "Automatic groups"),
    ("Put an event on everyone's calendar", "calendar event school calendar holiday "
     "subscribe", "More services", "Calendar"),
    ("Missing assignments", "missing work coursework late assignments copy assignments",
     "Classroom", "Coursework"),
    ("Let someone send as a shared address", "send as sendas from address front office",
     "Email", "Send as"),
    ("Collect orphaned files", "orphan orphaned files lost", "Google Drive", "Orphaned files"),
    ("Apply Drive labels", "label labels confidential classification", "Google Drive",
     "Labels"),
    ("Single sign-on settings", "sso saml classlink clever sign-on access level",
     "Security reports", None),
    ("Someone's account was hacked", "hacked compromised phishing phished breach lock down "
     "spam sent", "Workflows", "Hacked account"),
    ("Fix files shared with anyone", "public link anyone with the link unshare sharing fix "
     "external", "Google Drive", "Fix sharing"),
    ("Move a folder to a shared drive", "shared drive migrate move folder copy curriculum",
     "Google Drive", "Move & copy folders"),
    ("Update phone, manager and room", "directory phone manager supervisor desk room org chart",
     "Users", "Directory details"),
    ("Staff laptops and phones", "laptop windows mac iphone android endpoint device approve",
     "Staff devices", None),
    ("Usage report for the board", "usage adoption active users dashboard board grant",
     "Usage", None),
    ("ChromeOS versions", "chromeos version update behind os", "Chromebook fleet",
     "OS versions"),
    ("Who gets a group's email", "nested group members recursive everyone", "Groups", None),
    ("Groups open to outsiders", "group external outside public join", "Security reports", None),
    ("Count mail before a Vault export", "vault count hold export legal", "More services",
     "Vault"),
    ("Share a leaver's Keep notes", "keep notes", "Google Drive", "Keep notes"),
    ("Archive a mailbox to a group", "archive mailbox group keep email history",
     "Email", "Archive to a group"),
    ("Add shared contacts", "contacts vendor directory autocomplete", "More services",
     "Shared contacts"),
    ("Restore deleted Drive files", "restore deleted trash undelete file recover lost project "
     "version history", "Google Drive", "Restore files"),
    ("Restore deleted email", "restore deleted email untrash mail recover", "Email",
     "Restore deleted mail"),
    ("What changed in the admin settings", "settings changed snapshot drift watch admin console",
     "Settings watch", None),
    ("Make a custom admin role", "custom admin role privileges building tech delegate",
     "More services", "Admin roles"),
    ("Check a leaver's data transfer", "transfer status youtube keep looker other data",
     "Workflows", "Staff leaving"),
    ("Chrome profiles on staff computers", "chrome profile browser windows mac managed",
     "Staff devices", None),
    ("Forms that don't require sign-in", "forms survey anonymous sign-in privacy",
     "Security reports", None),
    ("Class activity", "classroom activity announcements materials unused classes",
     "Classroom", "Class activity"),
    ("Classroom student groups", "student groups reading groups classroom groups", "Classroom",
     "Student groups"),
    ("Our domains", "domain alias domains secondary", "More services", "Domains"),
    ("Ask GAMbit", "ask assistant ai claude plain english help me", "Ask GAMbit", None),
    ("Link an Incident IQ ticket", "ticket incident iq iiq help desk", "Settings & Updates",
     None),
    ("Pull the roster live from your SIS", "classlink clever powerschool infinite campus skyward aeries synergy oneroster api roster live", "Roster sync",
     None),
    ("Approve requests by email", "approve phone email approval", "Approvals", None),
    ("Build my own workflow", "custom workflow my workflows template steps chain",
     "Workflows", "My workflows"),
    ("Clear Chromebook assigned users", "blank clear remove empty erase all every assigned user "
     "annotated user chromebook", "Chromebook fleet", "Assigned users"),
    ("Blank the assigned user on Chromebooks nobody uses", "unused not used stale idle "
     "inactive chromebook blank clear assigned user days hasnt signed", "Chromebook fleet",
     "Assigned users"),
    ("Make the last signed-in user the assigned user", "last user recent user logged in "
     "signed in assign assigned user chromebook", "Chromebook fleet", "Assigned users"),
    ("Move Chromebooks to the school of the student using them", "move chromebook org unit "
     "ou school student logs logged login signs signed in last user follow grade grader", "Chromebook fleet",
     "Assigned users"),
    ("Sync Chromebook assignments", "assign assignment chromebook student device sync",
     "Chromebook fleet", "Assignment sync"),
    ("Clean up inactive accounts", "cleanup clean up inactive stale suspend delete old "
     "release licenses", "Clean-up rules", None),
    ("Go back to the previous GAMbit version", "rollback downgrade previous version update",
     "Settings & Updates", None),
    ("Create a Chat space", "chat space spaces google chat members", "More services",
     "Chat spaces"),
    ("Room booking report", "room usage booking resource calendar report", "More services",
     "Room usage"),
    ("Add a Gmail label for many people", "gmail label labels bulk", "Email", "Labels"),
    ("Upload an S/MIME certificate", "smime s/mime certificate encryption", "Email", "S/MIME"),
    ("Graduate seniors", "graduation alumni seniors class of", "Workflows", "Graduation"),
    ("Year-end rollover", "rollover promote grade move year end", "Workflows",
     "Year-end rollover"),
    ("Check a Chromebook in or out", "checkout check in chromebook loan", "Workflows",
     "Chromebook check-in/out"),
    ("Lend a loaner Chromebook", "loaner loan borrow", "Chromebook fleet", "Loaners"),
    ("Log a Chromebook repair", "repair broken cracked screen ticket", "Chromebook fleet",
     "Repairs"),
    ("Print Chromebook labels", "label barcode asset tag print", "Chromebook fleet", "Labels"),
    ("Collect Chromebooks for the summer", "summer collection collect return",
     "Chromebook fleet", "Summer collection"),
    ("Find a Chromebook", "device serial chromebook lookup lost", "Chromebooks", None),
    ("Set an out-of-office reply", "vacation away auto reply ooo", "Email", None),
    ("Set email signatures", "signature footer", "Email", "Signatures"),
    ("Give someone access to a mailbox", "delegate delegation shared mailbox", "Email", None),
    ("Add people to a group", "group members add mailing list", "Groups", None),
    ("Keep a group up to date automatically", "automatic dynamic rule group nightly",
     "Groups", "Automatic groups"),
    ("Sync students from the SIS", "roster classlink powerschool sis sync import students",
     "Roster sync", None),
    ("Invite parents to Classroom", "guardian parent invite classroom", "Classroom",
     "Guardian sync"),
    ("Set up this year's classes", "classroom courses create archive year", "Classroom",
     "Yearly setup"),
    ("Who changed this account?", "history audit timeline who did", "Account timeline", None),
    ("Undo a change", "undo revert mistake", "Activity log", None),
    ("Approve a request", "approval approve request pending", "Approvals", None),
    ("See inactive accounts", "inactive not signed in stale unused", "Reports", None),
    ("Run a security report", "2-step 2sv audit external sharing apps admins",
     "Security reports", None),
    ("Who uses the most storage", "storage quota space drive full", "Security reports", None),
    ("Check background tasks are running", "scheduled nightly tasks health", "Background tasks",
     None),
    ("Check GAM is set up correctly", "diagnostics access scopes broken not working",
     "Diagnostics", None),
    ("Test GAMbit safely", "live test checklist try dry run", "Live test", None),
    ("Find roster, account and device mismatches", "mismatch missing wrong school no device "
     "classlink compare reconcile", "Mismatch report", None),
    ("Collect Chromebooks from students who left", "withdrawn left student device collect "
     "return", "Chromebook fleet", "Withdrawn students' devices"),
    ("Plan the end of the school year", "year end rollover checklist summer plan",
     "Workflows", "Year-end checklist"),
    ("Email principals their school's report", "principal school report weekly",
     "School reports", None),
    ("What happened last week? (search the logs)", "history what did we change why fail "
     "log", "Ask GAMbit", None),
    ("Get alerts about unusual activity", "unusual suspicious mass download delete admin "
     "sharing alert", "Investigations", "Unusual activity"),
    ("Approve password resets automatically", "approval rules auto two person escalate",
     "Approvals", None),
    ("Plan license and Chromebook budgets", "budget license cost save money replace aue",
     "Budget planner", None),
    ("Work through Incident IQ tickets", "ticket queue incident iq helpdesk", "Ticket queue",
     None),
    ("Respond to unusual activity", "respond lock down hacked playbook", "Investigations",
     "Unusual activity"),
    ("Put back settings changed outside GAMbit", "drift revert settings changed",
     "Settings watch", None),
    ("Fix mismatches every night", "nightly mismatch auto fix", "Mismatch report", None),
    ("Handle password tickets automatically", "ticket password reset help desk automatic",
     "Ticket queue", None),
    ("See this week's district numbers", "scorecard trend weekly numbers", "Home", None),
    ("See a Chromebook's history", "device history serial timeline repairs", "Chromebook fleet",
     "Device history"),
    ("Which Chromebooks break most / loaners needed", "repair hotspots loaners model school",
     "Budget planner", None),
    ("Monthly audit report for the board", "audit ferpa cipa board monthly report",
     "Audit report", None),
    ("Email teachers their follow-up lists", "teacher list follow up classroom students",
     "Teacher lists", None),
    ("Practice run before a big change", "practice what if simulate preview rollover "
     "graduation", "Workflows", "Year-end rollover"),
    ("Ask a question about our Google data", "look up question who which how many",
     "Ask GAMbit", None),
    ("Remove a phishing email from every mailbox", "phishing spam scam email remove delete "
     "everyone", "Investigations", "Phishing clean-up"),
    ("Testing mode for state testing", "testing lockdown kiosk state test chromebooks",
     "Policy rollouts", "Testing mode"),
    ("Try a policy on a pilot group first", "staged rollout pilot policy chrome",
     "Policy rollouts", "Staged rollouts"),
    ("Get staff onto 2-Step Verification", "2sv two step verification mfa campaign",
     "2-Step Verification", None),
    ("Check apps against our approved list", "approved apps oauth third party dpa privacy",
     "Investigations", "Approved apps"),
    ("Account for a substitute or contractor", "substitute sub temporary contractor student "
     "teacher end date expire", "Users", "Time-limited accounts"),
    ("Find groups, drives and classes nobody owns", "ownership owner orphaned shared drive "
     "group class left", "Ownership check", None),
    ("See an account on an earlier date / put it back", "time machine restore history "
     "snapshot account", "Account time machine", None),
    ("Get a question answered by email every week", "scheduled question weekly email ask",
     "Ask GAMbit", None),
    ("Share a live dashboard with leadership", "leadership dashboard google sheet director "
     "principals", "Home", None),
    ("Score our security settings", "security baseline score settings cipa safesearch "
     "audit hardening", "Security baseline", None),
    ("Keep Classroom rosters matched to the SIS", "classroom roster daily sync sis "
     "schedule change drop add", "Classroom", "Daily roster sync"),
    ("Handle a FERPA or legal records request", "ferpa records request legal hold vault "
     "export subpoena public records foia", "Records requests", None),
    ("Is a new hire ready for day one?", "new hire day one ready readiness onboarding check",
     "Workflows", "Day-one readiness"),
    ("Report a lost or stolen Chromebook", "lost stolen chromebook disable missing police",
     "Chromebook fleet", "Lost & stolen"),
    ("Run a change tonight / freeze changes", "run later tonight schedule change freeze "
     "testing window", "Run later & freezes", None),
    ("Request form for principals and secretaries", "request catalog form principal "
     "secretary substitute", "Run later & freezes", "Request catalog"),
    ("Check GAMbit after an update", "release check update rollback version", 
     "Settings & Updates", None),
    ("Review who has admin rights", "admin access review audit quarterly roles super admin "
     "cyber insurance", "Access review", None),
    ("How fast do new accounts get used / leavers locked out?", "account timing sla first "
     "sign in leavers suspended approvals turnaround", "Account timing", None),
    ("When will we run out of storage?", "storage forecast pooled full quota growth",
     "Storage forecast", None),
    ("Students who have gone quiet", "counselor disengaged going quiet attendance missing "
     "work not signing in", "Students going quiet", None),
    ("Clean up old shared drives, classes and groups", "stale old archive unused shared "
     "drives classes empty groups", "Stale content", None),
    ("Personal Google accounts using our domain", "personal consumer unmanaged conflict "
     "account invitation", "Users", "Personal Google accounts"),
    ("Calendars shared outside / set out of office", "calendar public sharing out of office "
     "leave away", "More services", "Calendar sharing & out of office"),
    ("Classroom invitations nobody accepted", "classroom invitation pending accept topics",
     "Classroom", "Invitations & topics"),
    ("Who shares the most files outside?", "sharing exposure public anyone with link "
     "external files", "Google Drive", "Sharing exposure"),
    ("Who changed or deleted this file?", "file activity history who edited deleted moved",
     "Investigations", "File activity"),
    ("Find app passwords", "app passwords asp 2sv bypass less secure", "Investigations",
     "App passwords"),
    ("Why does someone get this group's email?", "group tree nested why email member",
     "Groups", "Why do they get this?"),
    ("Turn hand-made groups into automatic ones", "suggest automatic group rule dynamic",
     "Groups", "Suggested automatic groups"),
    ("Are the Chromebooks ready for testing?", "testing day device readiness state test "
     "chromeos version", "Policy rollouts", "Device readiness"),
    ("Move unused Chromebooks to schools that need them", "redistribute idle unused "
     "chromebooks shortage", "Chromebook fleet", "Redistribution"),
    ("How do I…? / help", "help guide how do i manual instructions documentation explain "
     "what does", "Guide", None),
    ("What does a GAM command do?", "gam command reference syntax what does", "Guide", None),
    ("Meet attendance for an e-learning day", "meet attendance e-learning snow day virtual "
     "who joined", "Meet attendance", None),
    ("Who uses AI / Gemini?", "ai gemini usage policy", "AI use", None),
    ("Missing directory info / duplicate accounts", "directory quality missing duplicate",
     "Directory quality", None),
    ("Cost per student", "cost per student budget tco", "Cost per student", None),
    ("Shared student passwords", "shared password sharing account testing integrity",
     "Investigations", "Shared passwords"),
    ("Public list of apps for parents", "public apps list parents privacy dpa website",
     "Investigations", "Public apps list"),
    ("Which batteries need replacing?", "battery forecast replace order", "Chromebook fleet",
     "Battery forecast"),
    ("Push a Wi-Fi network to Chromebooks", "wifi wi-fi network ssid chromebook",
     "Policies by org unit", None),
    ("Hand one folder to someone else", "transfer ownership folder claim", "Google Drive",
     "Folder tools"),
    ("Set up org units and schools", "org unit map designate which org units students staff "
     "chromebooks schools grades setup ou map", "Settings & Updates", None),
    ("See and edit all my scheduled jobs", "schedules scheduled jobs list edit enable "
     "disable turn off pause change time days saved job duplicate", "Schedules", None),
    ("Make a second scheduled job for other org units", "second another job copy duplicate "
     "org units schedule chromebook move blank", "Schedules", None),
    ("Do scheduled jobs run when GAMbit is closed?", "scheduled jobs background closed "
     "minimize tray open running task scheduler asleep off", "Background tasks", None),
    ("Dark mode", "dark mode theme colors night black background light mode",
     "Settings & Updates", None),
    ("Ask the Helper", "assistant chat ai question help me ask helper", "Guide", None),
    ("Report a problem", "bug crash problem help support", "Diagnostics", None),
    ("Give someone admin rights", "admin role assign rights privileges make admin delegated",
     "More services", "Admin roles"),
    ("Students who haven't signed in lately", "inactive not signed logged in quiet absent "
     "students login", "Students going quiet", None),
    ("Everything about one staff member", "staff card teacher security summary",
     "Staff card", None),
    ("Are we ready for back to school?", "back to school august readiness start year",
     "Back to school", None),
    ("Who changed things outside GAMbit?", "outside console changes admin log who changed",
     "Changes outside GAMbit", None),
    ("Who has no recovery phone or email?", "recovery phone email forgot password",
     "Account recovery", None),
    ("Who can read someone's mail?", "delegate send as mailbox calendar access review",
     "Mailbox access review", None),
    ("Compare the finance asset list with Google", "asset register finance inventory "
     "depreciation audit", "Chromebook fleet", "Asset register"),
    ("How many Chromebooks next year?", "next year forecast enrollment cohort devices "
     "licenses", "Budget planner", "Next year"),
    ("Clean up group members", "group hygiene cleanup suspended former outsider nested",
     "Groups", "Group clean-up"),
    ("Room features (projector…)", "room feature projector resource", "More services",
     "Room features"),
    ("Itinerant staff working location", "working location itinerant building calendar",
     "More services", "Working locations"),
]


def labels() -> list[str]:
    return [f"➜ {t[0]}" for t in INTENTS]


def match(text: str):
    """Best intent for free text, or None."""
    t = text.lower().strip().lstrip("➜").strip()
    if not t:
        return None
    for it in INTENTS:
        if t == it[0].lower():
            return it
    words = [w for w in t.replace("?", "").split() if len(w) > 2]
    best, score = None, 0
    for it in INTENTS:
        hay = (it[0] + " " + it[1]).lower()
        s = sum(1 for w in words if w in hay)
        if s > score:
            best, score = it, s
    return best if score >= max(1, len(words) // 2) else None
