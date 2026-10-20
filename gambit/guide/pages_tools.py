"""Guide: Automation and Tools pages."""

PAGES = {
    "Approvals": dict(
        what="Changes waiting for an admin: requests from limited roles, leavers from "
             "roster sync, staff request forms, the request catalog and clean-up rules.",
        steps=["Select a request to see its commands and reason.",
               "**Approve and run**, **Approve, run later…** (runs tonight or when you "
               "choose), or **Deny…** with a note.",
               "*Practice run* shows what the commands would change.",
               "**Approval rules…** auto-approve low-risk requests and require two admins "
               "for the riskiest; **Email approvals…** lets admins approve by replying."],
        tips=["The staff request form (teachers asking for password resets) is set up at the "
              "bottom of this page."],
        keywords="approve deny request pending two person email approval rules"),
    "Ticket queue": dict(
        what="Open help-desk tickets about accounts and Chromebooks. *Work on it* opens the "
             "right GAMbit screen already filled in, and what you do is noted on the "
             "ticket.",
        steps=["**Load open tickets**, select one and **Work on it**.",
               "*Add a note…* or *Resolve…* when done.",
               "*Handle password tickets now* resets passwords for verified requests."],
        tips=["Shown when a help desk is connected in Settings → Integrations."],
        keywords="ticket help desk incident iq zendesk queue"),
    "Scheduled jobs": dict(
        what="Run a saved Command Builder template on a schedule – for example a weekly "
             "inactive-accounts report emailed to principals.",
        steps=["Make a template in the Command Builder.",
               "Pick it here with a schedule (daily, weekly, monthly or once), a results "
               "folder and who gets the email.",
               "**Create scheduled job**; *Run selected now* to test."],
        keywords="schedule job report template recurring email results"),
    "Run later & freezes": dict(
        what="Changes queued to run tonight or on a date, change freezes that pause risky "
             "changes, and the request form for principals and secretaries.",
        steps=["**Run later**: *Queue a command…* and pick when. The 15-minute background "
               "task runs it.",
               "**Change freezes**: *New freeze…* with dates and what to pause (deletes, "
               "suspensions, whole-OU changes, Chromebooks…). Full admins can override with "
               "a logged reason.",
               "**Request catalog**: link a Google Form's response sheet; each response "
               "(substitute account, group change, new class, move a Chromebook) becomes an "
               "approval request or runs automatically, and the requester is emailed."],
        keywords="run later tonight schedule freeze testing pause request form principal "
                 "substitute"),
    "Stale content": dict(
        what="Shared drives unchanged for years, classes with no posts this school year, and "
             "empty groups – clean them up through Approvals.",
        steps=["Choose what to check and how many years, add names to keep, then **Scan**.",
               "Select items and **Clean up selected** (hide drives, archive classes, delete "
               "groups)."],
        keywords="stale old unused archive clean up shared drive class empty group"),
    "Background tasks": dict(
        what="Everything GAMbit runs with nobody at the PC, with last run and result.",
        steps=["*Set up the standard tasks* the first time.",
               "*Run here now* runs one task immediately; *Open the task log* shows its "
               "output.",
               "*Server kit…* helps move the tasks to an always-on PC."],
        keywords="background task scheduler nightly automatic server"),
    "Schedules": dict(
        what="Every scheduled job in one list: your saved jobs (for example “Blank unused "
             "Chromebooks – Middle School” and a second one for the high school) and GAMbit's "
             "own background tasks. Edit, duplicate, turn on or off, change the time and days, "
             "or run one now. GAMbit doesn't need to be open for them to run.",
        steps=["**+ New job ▾** makes a saved job: pick the job type, then its name, time and "
               "days, which Chromebooks (all, or chosen org units) and its own settings.",
               "**Edit…** (or double-click) changes a saved job. *Preview in Assigned users* "
               "loads it into the Assigned users tab so you can see what it would do, and "
               "*Save changes to the job* there updates it.",
               "**Duplicate** copies a job (turned off) – the quick way to make the same job "
               "for other org units.",
               "**Turn on / off** pauses a job without deleting it; **Change time & days…** "
               "works for GAMbit's own tasks too; **Run now** runs one here."],
        keywords="schedule scheduled jobs saved job edit enable disable turn off time days "
                 "duplicate org units task scheduler"),
    "Clean-up rules": dict(
        what="Rules that find accounts to tidy up – long-inactive accounts, old suspended "
             "accounts, licenses on suspended accounts. Findings always go to Approvals.",
        steps=["**New rule…**, *Preview selected rule*, then *Every Monday…* or *Check all "
               "rules now*."],
        keywords="cleanup inactive suspended license rule"),
    "Command Builder": dict(
        what="Every GAM command, straight from GAM's own reference, as a form. Search in "
             "plain words, fill in the form, check the preview, run or save as a template.",
        steps=["Search (e.g. *vacation*, *legal hold*, *chromebook move*).",
               "Pick a command; fill in the form – choices are dropdowns, people/org units/"
               "groups get pickers.",
               "Check the live preview (you can edit it), then **Run**.",
               "☆ Favorite it, or *Save as template…* to reuse or schedule."],
        tips=["*Update command list from GAM* refreshes the reference after a GAM update.",
              "The GAM command reference in this guide lists every command with a plain "
              "description."],
        keywords="builder command form template favorite syntax"),
    "Bulk (CSV)": dict(
        what="Run one GAM command for every row of a spreadsheet, using ~column to insert "
             "each row's values.",
        steps=["Load the CSV or Google Sheet.",
               "Write the command, e.g. `update user ~email ou ~ou` (pick a template to "
               "start).",
               "*Try the first 3 rows*, then **Run for all rows**."],
        keywords="bulk csv spreadsheet every row batch"),
    "Command Console": dict(
        what="Type any GAM command. Output appears below; *print* commands can show a "
             "table.",
        steps=["Type the command without `gam` (↑/↓ for history) and **Run** (Ctrl+Enter).",
               "**Explain** breaks it into plain English first."],
        keywords="console terminal command line type gam"),
    "Diagnostics": dict(
        what="Checks GAM can reach every part of Google Workspace GAMbit uses, with "
             "plain-English fixes.",
        steps=["**Run checks**; follow the fix shown for anything red.",
               "*GAMbit's Google key…* shows the age of GAM's service-account key and can "
               "replace it.",
               "*Report a problem…* saves a zip to send for help."],
        keywords="diagnose test connection check problem key"),
    "Live test": dict(
        what="Try every part of GAMbit for real – safely, on your test account and test "
             "org unit – and keep a record of what works.",
        steps=["Set the test account in Settings → Testing.",
               "*Run all automatic checks*, then mark the manual ones passed or failed."],
        keywords="test verify checklist works"),
    "Ask GAMbit": dict(
        what="Describe what you want in plain English. Claude suggests GAM commands (nothing "
             "runs until you click Run), drafts a workflow or clean-up rule, or looks "
             "things up for you read-only.",
        steps=["Type the question and choose the mode (suggest commands, look it up, "
               "draft…).",
               "Review the suggested commands, then *Run the selected commands*.",
               "*Ask this every week…* emails the answer on a schedule."],
        tips=["Needs a Claude (Anthropic) key in Settings → Integrations."],
        keywords="ai claude ask natural language question"),
    "Settings & Updates": dict(
        what="Where GAM lives, updates for GAM and GAMbit, domains (profiles), team folder "
             "and roles, testing, email and alerts, integrations, deployment and backups.",
        steps=["**Check for GAM updates** / **Check for GAMbit updates**.",
               "Set the team folder and *Manage roles…*.",
               "Testing: *Create the test org unit and account*.",
               "Integrations: connect your SIS, help desk and Claude.",
               "*Make a deployment file…* to roll GAMbit out to other techs."],
        tips=["Before each update GAMbit backs up its settings and runs a release check; "
              "*Go back to the previous version* if something breaks."],
        keywords="settings update upgrade profile domain team roles alerts integrations "
                 "deploy backup"),
}
