"""Guide: getting-started articles. Markup: blank line = new paragraph, "- " bullets,
"1. " numbered steps, "## " sub-heading, **bold**, `code`."""

ARTICLES = [
    ("everyday", "Making GAMbit yours", "my pages pin sidebar fold tray alerts recent "
     "practice mode contrast shortcuts feedback customize home", """
## My pages and the sidebar
- Right-click any page → **📌 Pin to My pages**. Pinned pages sit at the top of the sidebar,
  with the pages you use most underneath (right-click → *Hide my most-used pages* to turn
  that off). Ctrl+Shift+P pins the page you're on.
- Click a section heading (People, Devices…) to fold it. Right-click → *Fold all sections*.
- With GAMbit sign-in or team roles, people only see the pages their role allows.

## Home
**⚙ Customize Home…** chooses the boxes, their order, your quick actions, number tiles and
links. Techs who mostly help people might keep *Quick look-up*, *Recently viewed*, *Quick
actions* and *My open tickets*.

## The tray and desktop alerts
Closing the window keeps GAMbit in the taskbar tray, so long jobs keep running. You get a
Windows alert when a long command finishes while you're elsewhere, when a background job
fails, and when a new approval request arrives. Quit from the tray icon's menu. Both can be
turned off in Settings & Updates → Appearance and safety.

## Practice mode (for new techs)
**🎓 Practice** in the top bar: changes to the test account and the test org unit
(Settings & Updates → Testing) run for real, everything else is a dry run – so a new tech
can do whole jobs safely.

## Before → after
Confirmations for changes have **Show before → after…**: each field as it is in Google now
and as it will be, before anything changes.

## Easier to read, quicker to use
Settings & Updates → Appearance: text size (up to Huge), **High contrast**. Ctrl+= and
Ctrl+- change text size; Shift+F1 or Ctrl+/ lists every shortcut.

## What's new and feedback
After an update GAMbit lists what changed (Ctrl+Shift+N any time). **Send feedback…** (in
the shortcuts window and Settings) emails your note – with the problem report attached if
you like – to whoever looks after GAMbit.
"""),
    ("welcome", "Welcome to GAMbit", "start overview what is gambit gam", """
GAMbit is a point-and-click front end for **GAM**, the command-line tool Google Workspace
admins use. Every button in GAMbit runs one or more GAM commands for you, shows you what it
ran in the **Output** panel at the bottom, and records it in the **Activity log** so it can
usually be undone.

## How GAMbit is organized
- **Home** – district numbers at a glance, shortcuts and the weekly scorecard.
- **Workflows** – step-by-step jobs: new staff, staff leaving, graduation, year-end.
- **People** – users, student lookup, groups, Classroom, roster sync and account history.
- **Devices** – Chromebooks one at a time, the whole fleet, and staff computers and phones.
- **Services** – Email, Google Drive and everything else (Calendar, Vault, Chat…).
- **Admin** – org units, licenses, policies, security baseline, records requests.
- **Reports** – ready-made reports, investigations, school and teacher emails.
- **Automation** – approvals, background tasks, scheduled jobs and clean-up rules.
- **Tools** – the Command Builder, Bulk (CSV), Console, Diagnostics, Ask GAMbit, Settings.

## Three things to know first
1. Turn on **🧪 Dry run** (top bar) whenever you want to see what would happen without
   changing anything.
2. Every results table can be filtered, sorted, saved as CSV or sent to a **Google Sheet**,
   and right-clicked for quick actions.
3. Press **F1** on any page to open this guide at that page.
"""),
    ("setup", "First-time setup", "install setup wizard oauth project service account "
     "connect", """
If GAM isn't set up yet, GAMbit opens the **Setup wizard** (you can reopen it from Home or
Settings & Updates).

1. **Welcome** – enter your super admin email, or choose *I already use GAM* and point to
   your existing GAM and config folders.
2. **Install GAM** – downloads GAM to `C:\\GAM7` and creates `C:\\GAMConfig`.
3. **Create Google project** – runs `gam create project`. Follow the prompts; the step ticks
   itself off when the files appear.
4. **Sign GAM in** – runs `gam oauth create`. Type `c`, sign in with your admin account and
   click Allow.
5. **Allow GAM access** – opens the Admin console page where you authorize GAM's service
   account, then **Check** confirms it (`gam user you check serviceaccount`).
6. **All done** – tests the connection with `gam info domain`.

Afterwards run **Tools → Diagnostics** to check every Google service GAMbit uses, and
**Settings & Updates → Testing** to create a test org unit and test account.
"""),
    ("finding", "Finding your way", "search sidebar favorites right-click navigate hide pages "
     "what do you want to do", """
- **Top search box** (Ctrl+K): type a person, group, org unit or Chromebook serial to jump
  straight to it – or type a task such as *reset password*, *someone is leaving* or *print
  labels* and GAMbit opens the right page and tab.
- **Sidebar**: right-click a page to hide it; right-click → *Show all pages* brings
  everything back. *Settings → Show advanced pages* shows or hides the expert tools.
- **Favorites**: right-click a person, group, org unit or Chromebook → *Add to favorites*.
  Favorites appear on Home and first in search.
- **Right-click any results table** to open a user, reset a password, sign out, suspend,
  open a Chromebook, copy and more.
- **Page tips**: the blue line at the top of each page explains it. *Try it safely* turns on
  dry run for that page. *Hide tips* turns the tips off.
- **This guide**: press **F1** anywhere, or open **Guide** in the sidebar.
- **Dark mode**: Settings & Updates → Appearance and safety → *Colors* (Light, Dark, or
  Same as Windows).
"""),
    ("oumap", "Org units & schools", "org unit map ou students staff chromebooks devices "
     "schools grades loaners repairs setup designate which org unit", """
**Settings & Updates → Org units & schools** tells GAMbit what your org units are.

## Set it up once
1. Click **✨ Find them for me**. GAMbit guesses from the names: Students, Staff,
   Chromebooks, Loaners, Repairs, Lost, Former students and staff, Testing, and each
   school and grade.
2. Check the tree. **Bold** means it's set on that org unit, gray means it's inherited
   from the one above.
3. Fix anything wrong: pick org units, choose *What it is*, type the *School* or *Grade*,
   then **Apply**. Give a school's Chromebook org unit the **same school name** as its
   student org unit, even if the org unit is called something else (like HMS).
4. Check the **Schools** tab, then click **Save**.

## What uses it
- Student lookup and Assigned users: who counts as a student.
- Assigned users → *Move it to the student's school org unit*, and Assignment sync: which
  Chromebook org unit goes with each school. Loaner, repair, lost and testing org units are
  never moved.

With a team folder, the map is shared with every technician.
"""),
    ("helper", "The Helper (offline assistant)", "helper assistant chat ask question plain "
     "english ai local ai walkthrough walk me through command suggest f2", """
Click **💬 Helper** in the top bar (or press **F2**). Type the way you'd say it – typos are
fine.

## What it does
- **Finds the right place**: “how do I set up a new teacher?” opens the page and lists the
  steps.
- **Walks you through a page**: “walk me through roster sync” opens the page and shows one
  step at a time. *Show me* highlights the button the step talks about.
- **Writes GAM commands**: “reset jane doe's password”, “who is in the staff group?”,
  “list Chromebooks not seen in 30 days”. It fills in the people, groups, org units and
  serials from your directory and asks if something is missing.
- **Explains a command**: paste one (“what does gam print cros … do?”).

## Nothing runs on its own
A command is only a suggestion. It runs when you click **Run**, and then goes through the
same checks as every other button: your GAMbit role, help-desk mode, **Dry run** and
approvals. Commands that change things ask first. *✔ checked against GAM* means it matches
GAM's own command reference.

## Local AI (optional)
Click **⚙** in the Helper. A free AI model can run on this PC to answer open questions in
its own words. Nothing leaves the computer. It needs a one-time download (about 2 GB, or
1 GB for the small model) and 8 GB of memory for the standard model. You can also copy the
files in from another PC, or use Ollama if it's installed. Commands the AI writes are
checked against GAM too, but read them before you run them.
"""),
    ("safe", "Trying things safely", "dry run test account practice run preview big change "
     "safe testing", """
## Dry run
Turn on **🧪 Dry run** in the top bar. Look-ups still run, but every command that would
change something is listed in the **Dry run** tab at the bottom instead of running. You can
copy or save that list.

## Test org unit and test account
Settings & Updates → Testing can create both. Workflows have *Fill in the test account*, and
Roster sync's **Test mode** only touches the test org unit.

## Practice run
Big jobs (rollover, graduation, approvals, mismatch fixes) have **Practice run**: GAMbit
simulates the commands against your current data and shows what each would change.

## Big-change preview
When a command targets an org unit, a group or everyone, GAMbit first lists every account
it will affect. Above 100 accounts you type the number to confirm.

## Undo
Most changes can be undone from the **Activity log** (Reports → Activity log → Undo
selected).
"""),
    ("team", "Team folder, roles and approvals", "team folder roles permissions approvals "
     "help desk request admin", """
Set a **team folder** (Settings & Updates → Team) that every tech can reach – a mapped drive,
file share or Google Drive for desktop folder. It holds roles, approvals, shared templates,
the combined activity log and most shared lists.

- **Roles** (Manage roles…) decide which pages each person sees and what they can do.
  Built-in roles: Full admin, Help desk, Chromebook tech and Office manager.
- Anything a role can only *ask for* becomes an **approval request**. Admins see a count in
  the sidebar and approve or deny on **Automation → Approvals**.
- **Approval rules** can auto-approve low-risk requests and require two admins for the
  riskiest ones.
- **Help-desk mode** (Settings) hides delete, wipe and suspend actions behind a PIN.

Roles are guard rails inside GAMbit. For hard limits, give each person's own GAM sign-in a
limited Google admin role.
"""),
    ("signin", "Sign-in and access (Google sign-in)", "login sign in sso google access users "
     "permissions security lock emergency admin org unit scope view only", """
With **GAMbit sign-in** turned on, everyone signs in with their district Google account
before GAMbit opens, and only the people an admin adds can use it.

## Turning it on (GAMbit admin, once)
1. In Google Cloud (the project GAM uses is fine): **OAuth consent screen → Internal**, then
   **Credentials → Create OAuth client ID → Desktop app**.
2. GAMbit → **Settings & Updates → Users & access → Sign-in**: enter your domain, the client
   ID and secret, click **Test Google sign-in**, then **Turn on GAMbit sign-in**. You become
   the first GAMbit admin.
3. **People** tab: add each person, their role, and (optionally) the org units they look
   after. Everyone else gets *No access*.
4. Set up the **emergency admin** on your computer (a long password plus an authenticator
   app) for days when Google sign-in is down.
5. The first time each tech opens GAMbit it shows a code – check it matches the code on your
   **Admin keys** tab before they trust it.

## What people can do
- **Roles** choose the pages each person sees, which pages are **view only**, what they may
  change or ask approval for, and optionally an org-unit limit and a GAM profile.
- **Org units**: a person limited to `/Students/Lincoln` only sees those accounts, and
  GAMbit refuses changes to anyone or any Chromebook outside them.
- GAMbit **locks** after the idle time you choose and asks for sign-in again after the
  session limit. Admin changes reach open GAMbit windows within a few minutes.

## How it's protected
- Google's own sign-in page is used (your 2-Step Verification applies); GAMbit checks
  Google's signed ID token and your domain, and stores no Google tokens or passwords.
- The access list is **signed** with a GAMbit admin's key that never leaves their PC. Hand
  edits, forged lists and old copies are refused. New admins' keys must be approved by an
  existing admin who checks their code.
- Every sign-in, refusal, lock and access change goes in the **Sign-in log**.

## Important
GAMbit sign-in controls what people can do **in GAMbit**. GAM on that PC still has whatever
admin rights it was set up with, so someone who can run `gam.exe` directly isn't limited by
GAMbit roles. For staff who must be limited, set their role's **GAM profile** to a gam.cfg
section signed in as a Google admin that only has the matching Google admin role (for
example Help Desk Admin limited to their school's org units).
"""),
    ("log", "Activity log and undo", "activity log undo history who did explain", """
Every command GAMbit runs is recorded: who, when, which domain, the command (passwords
masked) and whether it worked. With a team folder the whole team's log is combined.

- **Undo selected…** works out the reverse of most changes – suspensions, org unit moves,
  group changes, licenses, Chromebook changes, aliases, new accounts and more.
- **Run again**, **Copy command** and **Explain** (plain-English breakdown).
- **Google Sheet copy**: paste a sheet link and the log is copied there daily.
- **Account timeline** (People) shows one person's history from the log plus Google's own
  audit logs.
"""),
    ("tasks", "Background tasks and schedules", "background task scheduler nightly every "
     "morning schedule daily automatic", """
Many features have an **Every night…**, **Every morning…** or **Every Monday…** button. It
creates a Windows Task Scheduler task that runs GAMbit with nobody at the PC
(`GAMbit.exe --task …`).

- **Automation → Schedules** is the one place for everything GAMbit runs on a schedule:
  - *All schedules* – every saved job, report job, roster sync and GAMbit task: edit,
    duplicate, turn on/off, change the time and days, run now, see the last log. Saved jobs
    (for example *Blank unused Chromebooks* or *Move Chromebooks to their students'
    schools*) each keep their own settings and org units, so you can have one per school.
  - *Report & command jobs* – run a Command Builder template on a schedule.
  - *Setup & health* – set up the standard tasks, run one here, the task log, wake the PC.
- **GAMbit doesn't need to be open.** Each task starts its own copy of GAMbit with no
  window, does the job and exits, so it runs whether GAMbit is open, minimized or closed.
- The PC must be **on**, with you **signed in to Windows** (a locked screen is fine;
  signing out stops them). A job missed because the PC was asleep or off runs as soon as
  it's back, and jobs run on battery too. *Wake this PC from sleep…* on Schedules → Setup & health
  wakes it for them.
- For jobs that must never be missed, use a server or an always-on PC (*Server kit…*).
- Jobs with a time-and-days picker (Chromebook fleet → Assigned users) run at the time
  and on the days you tick.
- Failures are emailed or posted to Teams/Slack/Google Chat when alerts are set up
  (Settings → Google Sheets and email).
- **Run later & freezes** (Automation) queues single changes for tonight and pauses risky
  changes during testing windows.
"""),
    ("integrations", "Connections: SIS, help desk and Claude", "integrations sis classlink "
     "oneroster clever powerschool incident iq zendesk help desk ticket claude anthropic ai",
     """
**Settings & Updates → Integrations** connects GAMbit to:

- **Your SIS** – ClassLink, Clever, PowerSchool or any OneRoster system (Infinite Campus,
  Skyward, Aeries, Synergy…). Used by roster sync, the mismatch report, Classroom setup and
  daily roster sync, guardians and more.
- **Your help desk** – Incident IQ, Zendesk, Freshservice, Freshdesk, ServiceNow, Jira
  Service Management, SolarWinds Web Help Desk, TeamDynamix or osTicket. GAMbit can open
  tickets, add notes, handle password tickets and show a ticket queue.
- **Claude (Anthropic)** – powers **Ask GAMbit**: plain-English questions turned into GAM
  commands you review before running.

Each connection has a **Test** button. Keys are stored with your settings and removed from
problem reports.
"""),
    ("help", "Getting help and reporting problems", "help problem report diagnostics error "
     "support crash", """
- **Plain-English errors**: common GAM errors show a 💡 hint in the Output panel.
- **Explain** (Console, Activity log, Ctrl+E) breaks any GAM command into plain English.
- **Tools → Diagnostics** checks every service GAMbit uses and suggests fixes.
- **Tools → Live test** proves each feature works on your test account.
- **Report a problem…** (Settings, Diagnostics, or after an error) saves a zip with logs and
  settings – passwords, tokens and keys removed – to send for help.
"""),
    ("shortcuts", "Keyboard shortcuts", "keyboard shortcuts keys hotkeys", """
- **F1** – open this guide at the current page (Shift+F1 lists the shortcuts)
- **Ctrl+K** – the top search box
- **Ctrl+1 … Ctrl+9** – Home, Workflows, Users, Groups, Classroom, Email, Google Drive,
  Chromebooks, Command Builder
- **Ctrl+Enter** – run (Command Builder and Console)
- **Ctrl+B** – Command Builder · **Ctrl+H** – Activity log · **Ctrl+E** – explain a command
- **Ctrl+J** – Jobs tab · **Ctrl+L** – Output tab · **Ctrl+.** – stop the running command
- **F5** – refresh people, groups and org units
"""),
    ("glossary", "Words you'll see", "glossary terms org unit ou sku entity oauth dry run "
     "alias delegate", """
- **GAM** – the free command-line tool that talks to Google's admin APIs. GAMbit runs it.
- **Org unit (OU)** – a folder in the Admin console that decides which settings and policies
  apply to the people or devices in it, e.g. `/Students/Lincoln/Grade 5`.
- **Group** – an email list and sharing group, e.g. `staff@`.
- **Alias** – another email address that delivers to the same account.
- **Delegate / mailbox access** – someone else can read and send from a mailbox.
- **License / SKU** – a Google Workspace edition assigned to an account (SKU = product code).
- **Suspend** – the account can't sign in but keeps its data; **delete** removes it (it can
  be restored for 20 days).
- **2SV** – 2-Step Verification.
- **Serial / asset tag** – a Chromebook's serial number and your district's own tag.
- **AUE / end of updates** – the date a Chromebook stops getting ChromeOS updates.
- **Vault** – Google's eDiscovery tool: matters, holds and exports.
- **Dry run** – GAMbit lists the commands instead of running them.
- **Entity** – who a GAM command applies to: `user x`, `group g`, `ou /Staff`,
  `ou_and_children /Students`, `all users`.
"""),
]
