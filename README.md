# GAMbit

A friendly Windows GUI for [GAM7](https://github.com/GAM-team/GAM), the Google Workspace admin command-line tool.

## What it does

- **Users**: look up, create, suspend/unsuspend, reset passwords, sign out, move OU, delete. You can also search by OU, name, or suspended status and act on the rows you select.
- **Groups**: a clickable list of all groups. Click one to see its members. From there you can:
  - select members to remove them or change their role
  - search for people by name and add them
  - edit the group's permissions in plain English (who can post, view, join, etc.), with presets
  - create groups with permissions and starting members in one step
- **Email** (needs the "Allow GAM access" setup step):
  - **Out of office**: turn auto-replies on or off with start and end dates, for people, OUs, a group, or everyone.
  - **Signatures**: an HTML editor with live preview, plus `{FirstName}`/`{Title}`/`{WorkPhone}` tags filled in per person.
  - **Forwarding**: on or off, choosing what happens to the person's own copy.
  - **Mailbox access**: give or remove delegate access, and list current delegates.
  - **Find & remove messages**: phishing cleanup. Search by subject, sender, Message-ID or any Gmail search, preview what matches, then trash or permanently delete it, with a per-mailbox limit.
  - **Send email**: to people or groups, with Cc/Bcc, HTML and attachments.
- **Users → Manage a user**:
  - **Account**: suspend, sign out, reset the password, require a password change *without* resetting it, move OU.
  - **Email addresses & aliases**: rename the primary address, add or remove aliases, export every alias in the domain.
  - **Security**: see connected third-party apps and revoke them; show or generate 2-Step Verification backup codes.
- **Groups → Aliases…**: add or remove a group's alternate addresses.
- **Email → Filters, IMAP & POP**: inspect and delete a user's Gmail filters; check, enable or disable IMAP; check or disable POP (for people, OUs, groups or everyone).
- **Google Drive**:
  - **Transfer files**: transfer ownership from a departing user, and check transfer status.
  - **A person's files & sharing**: all files, files shared with anyone who has the link, files shared outside the domain, name search, recently changed; counts and sizes.
  - **Shared drives**: list, create, see members, add people or groups with an access level, change access, remove.
  - **Storage & trash**: usage, plus emptying a user's Drive trash.
- **Classroom**:
  - Find courses by teacher, student or state, then archive, reactivate or delete them.
  - Open a course to see its roster, add or remove teachers and students, change the owner, or rename it.
  - Create courses, including aliases for syncing.
  - Sync rosters from a SIS CSV, either add-only or a full sync.
  - Invite, view or remove guardians.
- **Org units**: a tree view where you can create, rename, move, describe and delete OUs, count what's inside, and list each OU's users and Chromebooks.
- **Licenses**: totals, who has a given SKU, and assigning or removing licenses for people, OUs, a group or everyone. Education SKUs are built in.
- **Reports**:
  - Inactive accounts, with suspend or move actions.
  - Activity and audit logs: admin, sign-ins, Drive, OAuth, groups, Classroom, Chrome, account changes, mobile and Meet.
  - Recent Drive sharing changes.
  - Chromebooks reaching end of updates.
  - Storage use, sorted largest first.
- **Chromebooks**: "Last signed-in user" shows the most recent user, the last active day and the last sync. Device lists include these columns too.
- **Chromebooks**: info by serial, move OU, set asset ID/location/user, disable/re-enable, reboot, wipe users, powerwash, deprovision. Search by OU, text, or "not synced in 30 days".
- **Bulk (CSV)**: run one command for every row with `~column` placeholders (`gam csv file.csv gam …`). It comes with templates and a first-row preview.
- **Command Console**: run any GAM command. It keeps a history (↑/↓), and `print` output shows as a sortable, filterable, exportable table.
- **Settings & Updates**:
  - Checks GitHub for the newest GAM release and downloads/installs it into your GAM folder. Your `oauth2.txt` and other config are kept.
  - Checks this repo's `latest.json` for new GAMbit versions and installs them silently. GAMbit then restarts.
  - Has "Open setup terminal" for first-time `gam create project` / `gam oauth create`.

Passwords are hidden (`********`) in the output log.

## First-run Setup Wizard

If GAM isn't set up, GAMbit opens a step-by-step wizard. You can also open it any time from Home or Settings & Updates.

1. **Welcome**: enter your super admin email. You can also choose "I already use GAM" and point to your existing folders.
2. **Install GAM**: downloads the latest GAM to `C:\GAM7` and creates `C:\GAMConfig`. It can also add GAM to PATH and set `GAMCFGDIR`, so `gam` works in any Command Prompt.
3. **Create Google project**: opens a console window running `gam create project admin <you>`. The wizard explains each prompt, and the step ticks off on its own when the credential files appear.
4. **Sign GAM in**: runs `gam oauth create admin <you>`. You type `c`, sign in, and click Allow.
5. **Allow GAM access**: runs `gam user <you> update serviceaccount`, opens the Admin console approval link, and has a **Check** button that runs `check serviceaccount` and shows pass/fail.
6. **All done**: tests the connection with `gam info domain`.

Only the Google sign-in, the OAuth client creation, and the Admin console "Authorize" click need you. Google requires a person for those.

## Workflows (sidebar → Workflows)

- **New staff**: fill in one form. GAMbit then:
  1. Creates the account, with an email suggested from the name, plus OU, job title and department.
  2. Assigns a license and adds the person to groups.
  3. Applies the signature template.
  4. Opens a printable or PDF **welcome sheet** with the temporary password.
- **Staff leaving**: a checklist you can switch steps on or off:
  - Record their groups.
  - Change the password and sign them out.
  - Deprovision (app passwords, backup codes, tokens).
  - Turn on an auto-reply.
  - Forward mail, or give mailbox access, to the person taking over.
  - Transfer their Drive files to that person.
  - Remove them from all groups.
  - Hide them from the directory.
  - Move them to a "Former Staff" OU.
  - Remove their license.
  - Suspend the account (optional).
- **Year-end rollover**:
  1. **Move students up a grade.** Map each grade OU to the next one; "Fill in from grade org units…" builds the map for you. Moves run from the top grade down, and graduates can be suspended. The map is saved for next year.
  2. **Archive last year's Classroom courses.**
  3. **Require new passwords** for chosen OUs.
- **Chromebook check-in/out**: scan a barcode to check a device out to a student, check it in to a cart or room, or mark it missing (and optionally disable it). Each scan updates the assigned user, location, OU and notes, and the session log can be exported.

Every workflow shows a live checklist (○ ◐ ✔ ✖) and a summary at the end.

## Command Builder (Tools → Command Builder)

GAMbit reads GAM's own syntax reference (`GamCommands.txt`, 1,000+ commands). A copy ships in `assets/`. When you install or update GAM from Settings, GAMbit downloads the reference that matches your GAM version, and you can also refresh it with **Update command list from GAM**.

- **Search** in plain words, such as "vacation", "calendar acl", "out of office", "legal hold" or "admin role". Common terms are matched to GAM's names (for example, "chromebook" finds `cros` and "parent" finds `guardian`).
- **The form** is built from the grammar:
  - fixed choices become dropdowns;
  - `<UserTypeEntity>` becomes the people/OU/group/everyone picker;
  - emails, groups and OUs get the same pickers used elsewhere in GAMbit;
  - optional parts are checkboxes, repeatable parts get "+ Add", and alternatives get a chooser.
- **The live preview** can be edited before you click Run. `print` output opens in a results table.
- **★ Favorites** pin commands you use often.
- **Templates** are named lists of commands (for example "Grade 6 rollover") you can run in one click or schedule.

## Scheduled jobs (Tools → Scheduled jobs)

Pick a template and a schedule (daily, weekly, monthly or once). GAMbit then:

1. Writes a `.cmd` script.
2. Registers it with Windows Task Scheduler under `\GAMbit\`.
3. Saves each `print`/`report` result as a timestamped CSV, alongside a log file, in the folder you choose.
4. Optionally **emails the results** (CSV attached) with `gam sendemail`, either every time or only when the report has rows. For example, send the weekly inactive-accounts list to principals.
5. Optionally **emails you if a step fails**, with the log attached. The job exits with code 1, so Task Scheduler and the Home dashboard show the failure too.

Emails are sent from the Google account set in Settings & Updates → Google Sheets and email.

## More services

Calendar (rooms and resources, buildings, calendar sharing), Vault (matters, holds, exports, downloads), Chrome (managed browsers, enrollment tokens, policies, end-of-updates and needs-attention counts), admin roles, mobile devices (approve, block, account wipe, factory reset), Alert Center, custom user fields (schemas), the directory and shared contacts, and Chat and Meet. Each tab links to every related command in the Command Builder.

## Home dashboard

Home shows the numbers at a glance: active, suspended, inactive (90+ days) and never-signed-in accounts; licenses assigned; active Chromebooks, Chromebooks losing updates within 12 months, and Chromebooks not seen in 30 days; security alerts from the last 7 days; and scheduled jobs that failed. The numbers refresh once a day after connecting, or when you click **Refresh now**. Click any tile to open the matching list.

## Roster sync (People → Roster sync)

Keeps **student or staff** accounts in step with a roster. Pick which at the top (**Roster of: Students / Staff**). You always preview the changes before anything runs.
- **Source:** a file on this PC, or a **Google Sheet**. Paste the link, optionally name the tab, and choose the account that can open it. GAMbit downloads it with `gam user … get drivefile <id> csvsheet <tab>`.
- **Formats:** ClassLink / OneRoster (`users.csv` + `orgs.csv`, or the whole `.zip`), Clever, PowerSchool, Infinite Campus, Skyward, a staff sheet / HR export, or any other CSV. The format and column mapping are guessed from the headers, and you can change them.
- **Staff mode:**
  - It reads Employee ID, building, department, job title and status columns.
  - A status such as *Inactive*, *Left*, *Terminated*, *Resigned* or *Retired* means the person has left. The list of values is editable.
  - By default, people who leave are suspended and moved to `/Former Staff`.
  - Job title and department are kept in step on the account.
  - "Missing from the roster" is off by default, so a running new-hire sheet works. Moving existing staff between OUs is also off by default.
- **Rules:** email and OU templates (`{first}.{last}{gradyear2}@{domain}`, `/Students/{school}/Grade {grade}`), school ID → name list, managed root OU, what to do with withdrawn students (suspend + move, suspend, or report only), and new passwords (random, pattern, or from the SIS). The SIS ID is saved on the account (`externalid organization`) so matching survives name changes.
- **Preview & apply:** tick or untick each new account, update, re-enrollment or withdrawal. If an unusually large number of withdrawals shows up, they're unticked automatically. Print or save password cards for the new accounts afterwards.
- Save several sync setups (e.g. one per school) and reuse them.

## Activity log and undo (Tools → Activity log)

Every command GAMbit runs is logged: who ran it, when, which domain, and the result. Passwords are masked. With a team folder (or a separate shared folder) the whole tech team's log is combined.
- **Google Sheet copy:** paste a sheet link and GAMbit copies the log there once a day (or on **Copy now**), so anyone can answer "who suspended this account?" months later.
- **Undo:** GAMbit works out the reverse of most changes: suspend/unsuspend, OU moves, renames, group adds/removes, new users/groups/aliases/OUs, licenses, Chromebook disable, Classroom adds, vacation/IMAP/POP and delegates. For changes whose "before" isn't in the saved lists, GAMbit takes one quick look just before the change runs:
  - **group removals and role changes**, so people go back with their old role (owner, manager or member);
  - **Chromebook updates** (OU, assigned user, location, asset ID, notes), so the old values go back.
- **Run again, Explain, Copy, Export**, plus search over your whole command history.
- **Preview before big changes:** when a command targets an OU, a group or everyone, GAMbit first shows **the list of accounts it will affect**. The list is searchable and can be saved as CSV. At 100+ accounts you type the number to confirm. Set the threshold in Settings.

## Team (Settings & Updates → Team)

Pick a **team folder** every tech can reach: a mapped drive, a file share, or a Google Drive for desktop folder. Set the same folder on each PC. It holds:
- **Custom roles** (Manage roles…): choose the pages each role sees, which Workflows tabs, and what it can do (look up, passwords, users, groups, Chromebooks, email, Drive, Classroom, suspend, delete, whole-OU/everyone, other). Anything a role can *ask for* becomes an approval request. People are matched by Windows sign-in name. Built-in roles:
  - **Full admin**
  - **Help desk**
  - **Chromebook tech:** Chromebooks plus the check-in/out workflow only.
  - **Office manager:** passwords and groups.
- **Approvals** (Tools → Approvals): limited users explain why they need a suspend, delete and so on. Admins see a count in the sidebar and can **Approve and run** or **Deny** with a note. If several steps of a workflow are held back, they're bundled into one request. Everything is recorded in the activity log.
- **Shared templates:** tick *Share with the team* when saving a Command Builder template (👥 marks shared ones). Scheduled jobs can use them too.
- **Shared workflow settings:** the leaving OU, rollover steps, email signature and big-change limit.

Roles are guard rails inside GAMbit, not a security boundary: GAM on each PC still has the admin access it was set up with. For hard limits, give each person's GAM a limited admin role in Google.

## Testing safely before going live

- **🧪 Dry run** (top bar, and the switch on Workflows and Roster sync): changes aren't made. Look-ups still run, and every GAM command that *would* have changed something is listed in the **Dry run** tab at the bottom, where you can copy or save it. Workflows and roster sync show 🧪 next to each held-back step.
- **Test org unit and test account** (Settings & Updates → Testing): GAMbit can create both for you.
  - Roster sync's **Test mode** only touches accounts in the test OU, and creates at most 3 new accounts there.
  - Workflows has **Fill in the test account**.
- **Diagnostics** (Tools → Diagnostics): read-only checks of everything GAMbit uses, each with a plain-English fix. It runs `gam user <you> check serviceaccount` for Gmail settings, sending email, Drive, Sheets and Calendar, then live checks for:
  - Classroom, Chromebooks, Vault, licenses, Alert Center, reports and connected apps;
  - the team folder, Task Scheduler and the temp folder.
  
  Copy the report, or save it with a problem report.

## Scheduled roster sync (Roster sync → Schedule…)

Save a sync, then schedule it to run every night with nobody at the PC. It runs as `GAMbit.exe --task sync --name "<sync>"` under Windows Task Scheduler.
- New accounts, updates and people coming back are applied automatically. Each type can be switched off.
- Everyone **leaving** becomes **one approval request** on the Approvals page.
- A **safety brake**: if there are far more new or leaving people than usual (e.g. a broken export), nothing is applied and you get an alert.
- The summary email lists what changed and attaches the full CSV. It can also attach the new accounts' temporary passwords. Printable password cards are always saved in *GAMbit Reports → Roster sync*.
- Staff rosters can send leavers through **full offboarding**: choose it under *Staff who leave*, and map a *Supervisor email* column.

## Staff leaving – full offboarding (Workflows → Staff leaving)

One plan per person, run in stages:
- **Today:** lock the account (new password, sign-out), auto-reply (it ends by itself), forward mail and share the mailbox with the supervisor, transfer **Drive and Calendar** to the supervisor, leave every group (roles are saved), hide from the directory, move to the leavers' OU.
- **When forwarding ends** (30 days by default): stop forwarding, the auto-reply and mailbox access, **release licenses**, suspend.
- **After 90 days:** deletion becomes an approval request, or a button. It is never automatic.

The "People who have left" list shows where everyone is up to. From there you can **Run the next step now**, **Undo everything** (groups with their old roles, licenses, OU, directory, suspension; the list says what can't be undone) or **Delete the account**. Follow-ups run while GAMbit is open, and from a daily background task (`--task daily`, created automatically).

## Staff requests (Approvals → Staff request form)

Teachers ask for a student password reset or sign-out with a Google Form. GAMbit reads the response sheet and checks each request:
- the teacher must be active staff;
- the account must be a student;
- optionally, they must share an active Classroom class.

The request then goes to Approvals, or a password reset can run straight away. The teacher is emailed the new password; refused or denied requests get an explanation. You can check now, or every 15 minutes in the background (`--task requests`).

## Chromebook fleet (Services → Chromebook fleet)

- **Carts & classrooms:** devices per location (or OU): active, disabled, not seen in N days, marked missing, and short of the expected count.
- **Bulk update from a spreadsheet:** serial plus asset tag, location, user, notes and OU. GAMbit previews only what changes.
- **Summer collection:** scan serials or asset tags with a barcode scanner. It's saved to the team folder so several people can scan at once. The **Not returned** list shows who still has a device and can be emailed. Scanned devices can have "Collected <date>" written into their notes.
- **End of updates planning:** active devices by the school year their updates end, with replacement cost.

## Security reports (Admin → Security reports)

- accounts without 2-step verification;
- files shared outside the district (by OU);
- third-party apps on student accounts;
- admins and roles;
- suspended accounts still holding licenses.

Each report can be **emailed every month** as a scheduled job.

## Classroom yearly setup (Classroom → Yearly setup)

1. **Archive** last year's active classes (by creation date). You can undo this from the Activity log.
2. **Create** this year's classes from ClassLink/OneRoster (`classes.csv` + `enrollments.csv` + `users.csv`, or the .zip) or a one-row-per-student CSV.
   - Classes are named from a template, such as `{period} {subject} – {teacher} {year}`.
   - The primary teacher becomes the owner, and co-teachers and students are added.
   - Each class gets the alias `d:<section>-<yy>`, so re-running only adds anyone missing.

## Rolling out to the team (Settings & Updates → Rolling out)

- **Deployment file:** choose which settings to copy (GAM location and profiles, team folder, Google account and alerts, safety and testing, help-desk mode, updates, reports, staff request form, saved roster syncs). Save the result as `gambit-deploy.json` next to the installer, then install silently:
  `GAMbit-Setup-x.y.z.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOLAUNCH`
  - GAMbit applies the file on first start, and again whenever a newer one appears.
  - It also reads the file from `%ProgramData%\GAMbit\` and `<team folder>\deploy\`.
  - By default it only fills in empty settings. Tick "replace" to overwrite.
  - The installer is per-user, so deploy it in the user's context (Intune "user", a login script, or by hand).
- **Back up / Restore settings:** a zip with every setting (secrets are optional) plus Builder templates, scheduled-job scripts and local records.
- **Shared Google project:**
  1. On a PC that's already set up, choose *Share this PC's Google project*. This copies `client_secrets.json` and `oauth2service.json` to a folder only techs can open.
  2. On every other PC, choose *Use the shared project*.
  
  Each person then signs GAM in with their **own** admin account, so their Google admin role limits their directory changes. Gmail and Drive access still goes through the shared service account.

## Guardians (Classroom → Guardian sync)

Invites every guardian the SIS lists, from either source:
- ClassLink OneRoster `users.csv`, with guardians linked through `agentSourcedIds`;
- a CSV with a Student email column and Guardian/Parent email columns.

You can optionally remove guardians the SIS no longer lists. It also reports students with nobody invited, and invitations not answered in N days.

## Automatic groups (Groups → Automatic groups)

Each rule says who belongs in a group: org units (with or without sub-OUs), job title contains, department contains, org units to leave out, people to always include, and whether suspended accounts count.
- **Preview** shows the adds and removes. Only plain members change; owners and managers are never touched.
- **Apply** runs it now, or **Every night** rebuilds all rules at 4:40 AM (`--task groups`).
- Rules live in the team folder.

## Graduation (Workflows → Graduation)

Pick the seniors' org unit and the class year.
- **Graduation day:** move to `/Alumni/Class of {year}`, set an auto-reply with the closing date, and email each student Google Takeout instructions. Removing them from groups and hiding them from the directory are optional.
- **After N days:** turn off the auto-reply, release licenses, suspend.
- **Later:** deletion after admin approval.

Each graduate gets an offboarding record, so Run next step, Undo and Delete work from Staff leaving.

## Policies by org unit (Admin)

Compare Chrome policies (`print chromepolicies ou X show all`) and Workspace policies (`print policies`, with inherited values shown) across org units. Settings that differ come first.

## Account timeline (People)

One person's history in one place: GAMbit changes, offboarding or graduation, Admin console changes (`report admin … filter USER_EMAIL==`) and sign-ins (`report login`). Open it from right-click → Timeline or from Student lookup.

## Student lookup (People)

For the front office:
- account status, suspension reason, org unit, last sign-in, 2-step, created date;
- their Chromebook (`print cros query user:`) and active classes;
- buttons to reset the password (easy-to-read, shown on screen), sign out, require a new password, unsuspend (goes to approval for limited roles), open the timeline, or add to favorites.

## Weekly digest (Settings → Google Sheets and email)

One email covering:
- new accounts and people leaving or graduating;
- failed changes and failed scheduled jobs;
- approvals waiting and offboarding steps due this week;
- security alerts and Chromebooks not seen in 30 days.

Use **Send now**, or **Every Monday** at 7:10 AM (`--task digest`).

## Chromebook loaners, repairs and labels (Chromebook fleet)

- **Loaners:** scan to check out (assigns the device and notes the due date) and to check in. Overdue reminders can go out now, or every morning automatically.
- **Repairs:** tickets with status history (Open → Sent for repair → Fixed / Replaced). The device's notes show "IN REPAIR #n", and a repairs-by-model table shows trends.
- **Labels:** printable / PDF labels with a Code 39 barcode (serial or asset tag), asset tag and location. Barcode scanners read them in the collection and loaner boxes.

## Drive & storage (Security reports → Drive & storage)

Four reports, each of which can be emailed monthly like the security reports:
- who uses the most storage;
- files over 100 MB owned by people who have left;
- shared drives with no manager;
- shared drives with members outside the district.

## Favorites and saved searches

- ★ people, groups, org units and Chromebooks: right-click → *Add to favorites*, or ☆ on Student lookup.
- Save a Users search: Users → List → *☆ Save this search*.
- Favorites appear first in the top search box and as buttons on Home. Right-click a Home button to remove it.

## Finding your way

- **Sidebar sections**: People, Devices, Services, Admin, Reports, Automation and Tools. *Settings → Show advanced pages* hides the Command Builder, Console, Bulk, More services, Policies and Live test for people who don't need them.
- **Hide a page**: right-click it in the sidebar. Right-click → *Show all pages* brings everything back.
- **“What do you want to do?”**: type a task like *reset password*, *print labels*, *someone is leaving* or *import rooms* into the top search box. GAMbit jumps to the right page and tab.
- **Page tips**: each page starts with a one-line tip. On pages that change things, **Try it safely** turns on dry run, so GAMbit lists the commands instead of running them. *Hide tips* (or Settings) turns the tips off.

## Live test (Tools → Live test)

A checklist that proves GAMbit works with *your* domain before you rely on it.
- The automatic checks run against the test account and test org unit from Settings → Testing. They cover connecting, listing users, name, password, suspend, org unit, group, out-of-office, signature, Drive, Classroom, Chromebooks, email and Sheets.
- The manual checks are things a person confirms: dry run, a roster sync in test mode, offboarding, undo and background tasks.
- Results are saved, and *Save as a problem report* bundles them up when you need help.

## Background tasks (Automation → Background tasks)

This page lists every GAMbit task in Windows Task Scheduler, when it last ran and whether it worked.
- **Set up the standard tasks** creates four tasks: daily follow-ups, automatic groups, staff requests every 15 minutes, and the weekly digest.
- Roster syncs, the weekly signature rollout and the monthly guardian report show up here once you schedule them.
- **Run now** runs a task through Task Scheduler. **Run here now** runs it inside this window, which is handy when testing. **Open the task log** shows `tasks.log`.
- **Server kit…** writes a folder for an always-on server or VM. It contains `gambit-deploy.json` (your settings), `install-tasks.ps1` (registers every task under `\GAMbit\` with a service account you type in) and a README. Install GAMbit and GAM on the server, sign GAM in once as that account, then run the script as an administrator.

## Staff onboarding from the HR sheet (Roster sync → Rules, staff)

Turn on **New staff setup**, then click *Choose groups, license and email…*. Every account a staff roster sync creates (by hand or on a schedule) then gets these steps:
- **License**: the SKU you pick.
- **Groups by building**, with one rule per line: `Lincoln Elementary = lincoln-staff, k5-teachers`. Rules can match the building, school ID, department or job title. `*` means everyone. The *Test* box shows which groups a building gets.
- **The district signature** from Email → Signatures. If the brand-new mailbox isn't ready yet, GAMbit retries automatically for a few hours.
- **A welcome email to the supervisor** (the sheet's Supervisor/Manager column) with the email address and temporary password. A fallback address covers rows with no supervisor. The password is masked in GAMbit's logs.

## Rooms and resources (More services → Calendar → Import rooms from a spreadsheet…)

Use a CSV or Google Sheet with these columns: `Building, Floor, Name, ID, Capacity, Kind, Type, Description`. *Save a blank template…* gives you a starting file.
- ID is optional. GAMbit makes one from the building and name.
- The preview compares the sheet with Google. It creates missing buildings (and adds missing floors), creates new resources and updates ones whose details changed.

## Signature rollout (Email → Signatures)

- **Preview as** shows the signature filled in with a real person's name, title and department.
- **Re-apply every week…** sets the current template for the people, org units or group you picked, every Monday at 5:20 AM. New staff pick it up, and template changes roll out the following week.

## Guardian report for principals (Classroom → Guardian report)

For each school (the org unit right under the students' org unit), the report shows how many students have a parent or guardian connected to Classroom summaries, how many are invited but waiting, and how many have nobody invited. Click a school to see its students.
- Add `School = principal@…` lines, then click *Email them now*, or schedule it for the 1st of every month.
- Each principal gets their school's numbers plus the student list as a CSV.
- An optional address gets the all-schools summary.

## Connections (Settings → Integrations)

- **Your SIS (live roster).** Choose your source:
  - **ClassLink** – Roster Server URL, client ID and secret.
  - **OneRoster API** – for Infinite Campus, Skyward (SMS 2.0 / Qmlativ), Aeries, Synergy, PowerSchool's OneRoster plugin or any other certified SIS. Enter the base URL, token URL, client ID and secret; OneRoster 1.1 and 1.2 both work.
  - **Clever** – the district token of a Secure Sync app. Guardians come from Clever contacts.
  - **PowerSchool (native API)** – plugin client ID and secret; students (and optionally staff).

  Press *Test*. Every source is saved as a normal OneRoster .zip, so roster sync (*Live from your SIS*), guardian sync, Classroom yearly setup and the mismatch report all work the same. Guardian sync and the new-school-year tool have a *From <your SIS>* button.
- **Your help desk.** Incident IQ, Zendesk, Freshservice, Freshdesk, ServiceNow, Jira Service Management, SolarWinds Web Help Desk, TeamDynamix or osTicket. The settings show what GAMbit can do with each (read tickets, add notes, open tickets, list the queue, resolve). osTicket's API can only open tickets. A *Ticket* box appears in the top bar: paste a ticket link or number and GAMbit adds a note listing what it did. *Open a ticket when a task fails* turns alerts into tickets. Extra fields for new tickets (group, category, request type IDs) go in the JSON box.
- **Ask GAMbit (optional).** Paste a Claude API key from console.anthropic.com and turn it on. *Tools → Ask GAMbit* turns plain-English requests ("suspend the seniors who left in May") into GAM commands. Each command shows whether it changes anything and why it is needed. It never runs anything until you select the commands and press *Run*, and every run still goes through dry run, roles and the activity log. Only your request plus your org-unit and group names are sent to Anthropic. Person names are sent only if you tick *Share user names*.

## Approve by email (Approvals → Email approvals…)

Approvers get each new request by email and can reply **APPROVE** or **DENY** from their phone. The *requests* background task checks the admin mailbox every 15 minutes. Only replies from the approver addresses you list count. Approved requests then run unattended. Offboarding and staff self-service requests are marked "approved by email" but still need to be finished in GAMbit.

## My workflows (Workflows → My workflows)

You can build your own step-by-step jobs, such as "New substitute teacher" or "Student device swap". Each job has fill-in fields, and each step is a GAM command using `{field}`, `{password}` (a fresh random password) and `{today}`. Workflows are saved in the team folder so everyone shares them. Each step runs with dry run, roles and logging as usual.

## Chromebook assignment sync (Chromebook fleet → Assignment sync)

This keeps each Chromebook's assigned user, asset tag and org unit matching your assignment list. The list is a CSV or Google Sheet with Serial and Student (email or ID) columns, plus an optional Asset column. Each device moves to `/Chromebooks/{school}`, based on where its student lives. You can schedule it with *Every morning…* (5:40 AM). If a run would make an unusually large number of changes, it stops and waits for you.

## Clean-up rules (Automation → Clean-up rules)

These are rules such as "suspend students with no sign-in for 180 days", "delete accounts suspended over a year" or "release licenses from suspended accounts". Each rule has an org unit, a skip list and a safety cap. Rules never change anything themselves: every finding becomes one Approvals request. You can schedule them weekly with *Every Monday…*.

## Safer updates (Settings & Updates)

Before installing an update, GAMbit saves a full backup of your settings (in `%APPDATA%\GAMbit\backups`, keeping the newest 10). If the new version misbehaves, *Go back to version X* reinstalls the previous release. *Restore settings from a backup…* puts your settings back.

## Smaller extras

- **Chat spaces** (More services): create a Google Chat space per school or department, and keep its members in step with a group.
- **Room usage** (More services): see how often each room and resource is booked, and for how many hours.
- **Gmail labels** (Email): add or remove a label for many people at once.
- **S/MIME** (Email): upload, list and remove certificates.

## Mismatch report (People → Mismatch report)

This compares your roster (any saved roster sync, including ClassLink live), Google accounts and Chromebook assignments. It lists:

- students with no account or in the wrong school;
- accounts still active after a student left;
- students with no Chromebook, or with two;
- devices assigned to students who left or to accounts that don't exist;
- devices in another school's org unit.

Click a problem in the summary to filter the list. *Fix selected* runs the fixes, and *Send selected for approval* sends them to Approvals instead.

## Withdrawn students' devices (Chromebook fleet)

This finds Chromebooks still assigned to students who are suspended or in the withdrawn org unit. For each device it can:

- write "COLLECT" into the device notes;
- optionally disable the device;
- open an Incident IQ ticket.

Scan a device back in and GAMbit marks it collected, re-enables it, optionally moves it, and adds a note to the ticket. Tick *Check every morning* and the daily task does the finding for you.

## Year-end checklist (Workflows → Year-end checklist)

This is one dated checklist for the end of the school year. It covers collection, graduation, Classroom archive, the grade move, clean-up rules, the budget review, the new roster, new classes, guardians and device hand-out. The dates come from the last day of school.

- Each step opens the right GAMbit screen.
- Sign-off steps go to Approvals and tick themselves off when approved.
- You can give each step an owner. With reminders on, the daily task emails what's overdue or due within 3 days.

## School reports (Reports → School reports)

This is a weekly email to each principal covering only their school:

- students who haven't signed in lately, or ever;
- students with no guardian invited;
- Classroom use this week;
- Chromebooks in repair, past their end-of-updates date, or reaching it within a year.

You can preview a school's email, send all of them now, or schedule them for every Monday at 6:40 AM. An all-schools summary can go to you.

## Ask GAMbit: history and drafts (Tools → Ask GAMbit)

- **Ask about history** searches the activity log and the background-task log on this PC, for questions like "What did we change for jsmith last week?" or "Why did last night's sync fail?". This mode needs no API key. *Explain with Claude* sends only the matching lines to Anthropic for a plain-English summary.
- **Draft a workflow** and **Draft a clean-up rule** turn a description into a *My workflows* entry or a clean-up rule. The draft opens in the normal editor for you to check before saving.

## Unusual activity (Investigations → Unusual activity)

Every night (5:20 AM), GAMbit reads the last day of Google's audit logs and flags:

- mass downloads or deletes;
- Google's suspicious sign-in warnings;
- sign-ins from countries you don't expect (optional);
- new admin roles or privileges;
- external sharing spikes.

You set the thresholds and the accounts to ignore. Findings go to your alert channels and, if that's turned on, to Incident IQ. *Investigate selected* opens the audit log for that person.

## Approval rules (Approvals → Approval rules…)

- **Approve automatically:** choose categories such as password resets. They can be limited to requests where every account changed is a student. The request runs straight away and is kept in Approvals as a record.
- **Two approvers:** deletes and other categories you pick need two different people. Email replies count too, and nobody can approve their own request. Releasing a license doesn't count as a delete here.
- **Escalation:** requests waiting longer than N hours are re-sent to your alert channels and an escalation address. This is checked by the "staff requests" task.

## Budget planner (Admin → Budget planner)

- **Licenses:** shows, per license, how many are held by suspended, inactive or never-used accounts. Enter a yearly price to see the savings. *Release selected licenses* sends them for approval.
- **Chromebook replacements:** a school × school-year grid of devices whose updates end, with costs. A device's school comes from its student, or from its org unit under the devices root.

## Ticket queue (Automation → Ticket queue, shown when Incident IQ is set up)

This loads open Incident IQ tickets. You'll need the Ticketing Product ID from Incident IQ's Developer Tools, and you can optionally narrow it to one category or some keywords. GAMbit sorts each ticket as an account or Chromebook ticket. *Work on it* links the ticket in the top bar and opens Users or Chromebooks already filled in, so whatever you then do is noted on the ticket. Incident IQ's ticket search isn't officially documented, so treat this as best effort.

## Response playbooks (Investigations → Unusual activity → Respond…)

Each finding has ready-made responses:

- risky sign-ins and mass downloads can be locked down (new random password, sign out everywhere, app passwords and access removed, forwarding off), with or without suspending;
- mass deletes open *Restore files* for that person;
- sharing spikes open *Fix sharing*;
- a new admin role lists the person's roles so you can remove it.

Run it now or send it for approval. *Send a lock-down for approval straight away* makes the nightly check do this automatically.

## Settings drift guard (Settings watch)

With *Drift guard* on, the nightly settings check skips changes GAMbit made and sends the rest to Approvals as one request: Chrome policies are put back automatically (`update chromepolicy` / `delete chromepolicy`). Admin console settings can't be changed through Google's API, so they're listed to change back by hand. *Propose putting back the compared changes* does the same for any two snapshots.

## Nightly mismatch fix (Mismatch report → Every night)

The mismatch report runs at 5:50 AM. The kinds you tick (devices to their student's school, name updates, school/grade moves, unsuspending returning students) are fixed automatically; everything else with a fix goes to Approvals as one request. If there are more than your limit, a person decides.

## Password tickets end to end (Ticket queue)

"Forgot my password" tickets can be handled automatically (every 15 minutes) or with *Handle password tickets now*. GAMbit resets the password, emails it to the person the ticket is for (or a fixed address – never the locked-out account), adds a note and resolves the ticket where the help desk allows it. Your approval rules decide whether that happens straight away or waits on the Approvals page. Staff accounts are left for a person unless you untick *Only for student accounts*. *Resolve…* closes any ticket by hand.

## District scorecard (Home)

A weekly snapshot of the key numbers – mismatches, students not signing in, missing guardians, devices to collect, repairs, expired devices, unusual-activity findings, waiting approvals and licenses that could be freed – with this week, last week, the change and a 12-week trend line. The Monday task (6:20 AM), the school reports and the nightly mismatch fix all add to it, and principals' emails show "▲/▼ vs last week".

## Chromebook history, repairs and loaners

- **Chromebook fleet → Device history:** everything about one device, newest first – GAMbit changes, repairs, loaners, collections, devices-to-collect and help-desk tickets.
- **Budget planner → Repairs & loaners:** repairs per 100 devices by model or school, devices open in repair and average days to fix, plus a suggested loaner pool per school from how many were out at once and how many devices are usually in repair.

## Audit report (Reports → Audit report)

One monthly report for your director or board: changes by kind and by person, approvals (automatic, by email, escalated), settings changes and drift, unusual activity and how much was reviewed, and the scorecard numbers. *Build and open* saves it as HTML; *Every month…* emails last month's report on the 1st.

## Teacher lists (Reports → Teacher lists)

From the Classroom rosters, each teacher gets only their own students who need a nudge: no sign-in lately, never signed in, no guardian invited, no Chromebook assigned, or an overdue loaner. Preview a teacher's email, send now, or every Monday. Try it with *Only* set to a few teachers first.

## Ask GAMbit: look it up

*Look it up for me* lets Claude answer questions like "Which of Mrs. Lee's students have no Chromebook?" by running read-only GAM commands itself (print, show, info and report only – anything that changes something, writes files or emails is refused). The commands it ran are listed, and their output is sent to Anthropic to write the answer.

## Practice run

*Practice run* plays a big change against today's accounts, automatic groups and Chromebooks without touching Google: who moves where, who is suspended, deleted or created, which licenses are released, which automatic groups gain or lose members, and which Chromebooks follow their student (or need collecting). It's on Year-end rollover, Graduation (every stage), Clean-up rules, the Mismatch report and any request on the Approvals page.

## Phishing clean-up (Investigations → Phishing clean-up)

Enter the sender, subject and/or a link from the message. *Find it* counts the copies in every mailbox (or one org unit) without changing anything. *Who replied?* lists people who wrote back to the sender, so you can check their accounts. *Move every copy to the trash* runs now or goes to Approvals; people can still recover a message from the trash for 30 days. *Open a help-desk ticket* records the incident, and each clean-up is logged in the team folder.

## Testing mode and staged rollouts (Admin → Policy rollouts)

Both save the Chrome policies set directly on each org unit before changing anything, so putting things back is exact: old values return, and policies that weren't set there are removed.

- **Testing mode.** Set up a template org unit in the Admin console with your testing settings (testing app, extensions off, no guest mode…), or type the policies. Then pick the org units and the testing days. The daily task turns it on the first morning and puts everything back after the last day. *Turn on now* and *Put back now* work any time.
- **Staged rollouts.** Apply a change to a pilot org unit, then let the daily task watch that group's new help-desk tickets and devices that stop checking in. *Check the pilot now* compares with the start. *Roll out to everyone* applies it to the other org units; *Roll back* puts every org unit back.

## 2-Step Verification campaign (Admin → 2-Step Verification)

Progress by building, a deadline, and reminder emails (sent as BCC in batches of 50) to staff who haven't set it up. The Monday task keeps reminding until the deadline, then emails each principal their building's list. Buildings at your "ready" percentage are flagged so you can turn on enforcement in the Admin console (Google's API can't switch enforcement). Progress is added to the scorecard.

## Approved apps (Investigations → Approved apps)

Import your approved list: a CSV with an app name column, plus optional Client ID and Status columns, or one name per line. *Check connected apps* lists every third-party app with how many people and students use it and what it can see (Gmail, all of Drive…). Mark apps approved or not, then remove access for students or everyone, now or through Approvals.

## Time-limited accounts (Users → Time-limited accounts)

Create (or start tracking) substitute, student-teacher, contractor, summer-school and volunteer accounts with an end date and a sponsor. A week before the end, the account and the sponsor get a reminder. After the end date, the daily task suspends it and can move it to an org unit you choose. *Extend…* moves the date and offers to unsuspend.

## Ownership check (Admin → Ownership check)

Finds:

- groups with no owner, or whose owners have all left;
- shared drives with no manager, or whose managers have all left;
- Classroom classes owned by someone who left;
- suspended accounts still holding more than 100 MB in Drive.

Each is handed to the supervisor saved at offboarding, or to your backup owner, or to whoever you choose. That means adding a group owner, making them a shared drive manager (as admin), making them the class owner, or transferring the Drive files. Run it now or send it for approval.

## Account time machine (People → Account time machine)

Every night (1:30 AM; 90 days kept) GAMbit saves each account's org unit, status, name, aliases, licenses and group memberships. Pick a person and a night to see what's different now, or see a day-by-day history. *Put the account back to that day* builds the commands (org unit, suspension, aliases, licenses and, optionally, groups) to run or send for approval.

## Scheduled questions (Ask GAMbit)

In *Look it up for me* mode, *Ask this every week…* saves the question. *Scheduled questions…* manages the list: choose daily, every Monday or the 1st of the month, who gets the answer, and *Run selected now*. The 6:30 AM task answers the questions that are due, using the same read-only look-up, and emails the answer with the commands it ran.

## Leadership dashboard (Home → Leadership dashboard sheet…)

Create or paste a Google Sheet. Every night (6:55 AM) GAMbit refreshes these tabs: Scorecard, Trend (26 weeks), Schools, Open tickets and Unusual activity (30 days). Share the sheet view-only with your director and principals.

## Security baseline (Admin → Security baseline)

GAMbit checks your Google settings against a K-12 baseline for each org unit you choose (students, staff, Chromebooks). It checks external Drive sharing, less-secure apps, 2-Step Verification for staff, student email forwarding, Marketplace allow-listing, external chat, who can join classes, password length, SafeSearch, YouTube Restricted Mode, incognito and guest mode. You get a score from 0 to 100% and a fix list:

- **Chrome policies:** *Fix selected (Chrome)* fixes them, or sends the fix for approval.
- **Admin console settings:** Google only lets apps read these, so GAMbit links to the right Admin console page instead.
- **Rules that don't fit your district:** *Don't check this* turns a rule off.

*Every Monday…* adds a weekly check (6:10 AM) that alerts you if the score drops. The score also appears on the Home scorecard.

## Daily Classroom roster sync (Classroom → Daily roster sync)

This keeps the classes made by *Yearly setup* matched to the SIS all year. Each morning (5:35 AM) GAMbit reads enrollments, either live from your SIS (Settings → Integrations) or from a OneRoster .zip. It adds students whose schedules changed and adds co-teachers. It can also remove students who dropped, but only if you tick that box. *Preview* shows every change before anything runs. The daily task stops and alerts you if there are more changes than your limit (300 by default).

## Records requests (Admin → Records requests)

Track FERPA, legal-hold, public-records and HR requests. Each request records who asked, when it arrived and when it's due (FERPA: 45 days). *Start* creates the Vault matter and places a hold if you asked for one. It then exports Gmail, Drive, Groups, Chat and/or Calendar for the account.

- *Check exports* shows when the exports are ready.
- *Download…* saves the export files.
- *Mark delivered* and *Close the matter* finish the request. Every step is logged.

The daily task alerts you about requests due within 7 days or overdue. Vault exports can take hours.

## Day-one readiness (Workflows → Day-one readiness)

For staff accounts created in the last 14 days, GAMbit checks:

- the account is active
- the license
- the groups from your onboarding rules (plus an optional Classroom teachers group)
- an email signature
- optionally, a Chromebook
- whether they've signed in

*Fix the gaps for selected* runs the fixes. *Email the summary* sends the list to HR or the principal.

## Lost & stolen Chromebooks (Chromebook fleet → Lost & stolen)

Type the serial and click *Look up*. GAMbit shows the last user, last check-in and last IP address. *Mark it* disables the device, adds a note and can move it to a "lost" org unit. It also opens a help-desk ticket (if one is set up) and writes a one-page report for police or insurance.

*It's been found* re-enables the device and puts it back in its old org unit. To show your "return to" message on the screen of a disabled device, set it in the Admin console (Devices → Chrome → Settings → Device → Disabled device return instructions).

## Run later & change freezes (Automation → Run later & freezes)

- **Run later:** *Queue a command…* runs a command tonight at 10 PM or at any time you choose. On the Approvals page, *Approve, run later…* does the same for an approved request. The "staff requests" background task (every 15 minutes) runs the queue, so the PC that runs the background tasks must be on.
- **Change freezes:** a freeze is a date range during which risky kinds of change are paused, for example state testing or the first week of school. By default it pauses deletions, suspensions, whole-OU changes and Chromebook changes.
  - Paused changes are blocked everywhere in GAMbit.
  - Queued changes wait until the freeze ends.
  - A Full admin can override a freeze for 15 minutes. They must give a reason, which is logged.

## Request catalog for principals and secretaries (Run later & freezes → Request catalog)

Make one Google Form with a *What do you need?* question. The choices are: substitute account, group change, new Classroom class, move a Chromebook, or something else. Link the form's responses to a Sheet and paste the sheet's link into GAMbit. Every 15 minutes, each new response becomes a filled-in approval request. If your approval rules allow it, GAMbit runs it straight away instead. The person who asked gets an email either way.

Substitute accounts are created with a random password, which Google emails to the person who asked. They are tracked as time-limited accounts (30 days unless the form gives an end date). Only active staff under the org unit you choose can make requests.

## Release check (Settings & Updates)

Before installing a GAMbit update, GAMbit runs read-only checks:

- GAM runs
- it can read the domain, org units and an account
- the settings file can be written
- the team folder can be written
- the background tasks are healthy

It runs the same checks again the first time the new version starts. If something that passed before now fails, GAMbit offers to go back to the previous version. If you tick the box, it goes back automatically. *Run the release check now* runs the checks on demand.

## Access review (Admin → Access review)

This page lists every Google admin role assignment. For each one it shows the person's 2-Step Verification, their last sign-in and how many admin-console actions they took in the last 90 days. It flags:

- people who have left (in your leavers' org unit) or are suspended
- super admins without 2-Step Verification
- admins who haven't signed in, or haven't used their rights

Mark each role *Keep* or *Remove*, then click *Sign off the review…*. The review is saved in the team folder for audits and cyber insurance, and the removals go through Approvals. If you fill in *Remind*, the daily task emails that person each quarter when a review is due.

## Account timing (Reports → Account timing)

- **New accounts → first sign-in:** Google keeps only the *last* sign-in. Tick *Track first sign-ins every night* and GAMbit records the first day each new account signs in, so the numbers are exact from then on.
- **Leaving → suspended:** worked out from the Account time machine's nightly snapshots.
- **Approvals and offboarding:** how long decisions take, and how long offboarding's first-day steps take.

The medians appear on the weekly scorecard.

## Storage forecast (Reports → Storage forecast)

Enter your pooled storage (for example 100 TB) and click *Measure now*, or tick the weekly box. GAMbit then shows:

- when storage runs out at the current rate
- growth for each school
- the biggest users
- how much space leavers and suspended accounts hold

It alerts you when the pool will be full within 12 months.

## Students going quiet (Reports → Students going quiet)

This finds students showing up to three signs:

- no Google sign-in for N days
- N or more missing Classroom assignments across all their classes
- a Chromebook that hasn't been used for N days

Choose how many signs a student needs before they're listed, and add each school's counselors. *Every Monday…* emails each school only its own students, and marks students who are new to the list that week.

## Stale content (Automation → Stale content)

This finds:

- shared drives with no changes for 2 years or more
- Classroom classes with no posts or assignments this school year
- empty groups

*Clean up selected* hides the shared drives, archives the classes and deletes the groups, either straight away or through Approvals. Shared drives are checked as you, so drives you aren't a member of are counted and listed as "couldn't be checked".

## Other Round 13 additions

- **Users → Personal Google accounts:** consumer accounts that use a district address (`print userinvitations`). You can invite them to join, cancel invitations, or check addresses before creating new accounts (`check isinvitable`).
- **More services → Calendar sharing & out of office:** finds staff and room calendars shared publicly or outside the district, and stops sharing them in one click. It also creates, shows and removes out-of-office events that decline meetings.
- **Classroom → Invitations & topics:** shows class invitations nobody accepted, lets you send them again or remove them, and copies topics into other classes.
- **Staff devices → Out-of-date Chrome…:** lists managed Chrome profiles more than one major version behind Google's newest stable release (`print chromehistory`). You can clear the cache or cookies remotely (`create chromeprofilecommand`).
- **Policies by org unit:**
  - *Clean up overrides…* removes Chrome policies set on an org unit with the same value as its parent.
  - *Wallpaper & picture…* uploads an image (`create chromepolicyimage`) and sets it for an org unit.
- **Google Drive:**
  - *Sharing exposure* shows, per person and per school, how many files are public, shared with anyone who has the link, or shared with outsiders (`filesharecounts`).
  - *Shared drive settings* moves shared drives into org units (one at a time or by name rules) and sets themes.
  - *Empty folders* finds and deletes empty folders.
- **Investigations:**
  - *File activity* shows who did what to one file (`driveactivity`).
  - *App passwords* lists and removes app-specific passwords, which get around 2-Step Verification.
  - *Unusual activity* now also flags accounts that turned off 2-Step Verification, and risky apps (for example ones that can read Gmail) allowed by someone when the app isn't on the approved list. One click removes the app's access.
- **Reports → Activity logs:** adds the Calendar, Chat, data protection rules (DLP), Gemini, SAML, context-aware access, Keep, Vault, Looker Studio, Takeout and Assignments logs.
- **Account timeline:** adds password and 2SV changes, app access, Chrome, Classroom and group membership events.
- **Groups:**
  - *Suggested automatic groups* finds hand-kept groups that match an org unit, title or department, and makes "only add people" rules for them.
  - *Why do they get this?* shows a person's groups and the groups those groups are inside (`grouptree`).
- **Policy rollouts → Device readiness:** before testing, checks each Chromebook in the testing org units for enrollment, minimum ChromeOS version, recent check-in, end of updates and (optionally) the kiosk testing app. Restart selected devices, or email the list to test coordinators.
- **Chromebook fleet → Redistribution:** finds unused Chromebooks (no check-in for N days, or optionally little active time from `print crosactivity`) at schools with more than they need, and suggests moving them to schools that are short.
- **Org units → People per org unit…:** fast counts from `print usercountsbyorgunit`.
- **Diagnostics → GAMbit's Google key…:** shows how old GAM's service-account key is and replaces it (`rotate sakeys`).
- **More services → Alerts:** sends Alert Center feedback on whether an alert was useful.

## Guide (sidebar → Guide, or F1 anywhere)

The built-in guide explains every page and tab. For each page it covers what the page is for, how to use it step by step, its tabs, tips and the GAM commands behind it. It also has getting-started articles (setup, finding your way, trying things safely, roles and approvals, undo, background tasks, connections, getting help, shortcuts, glossary) and a **GAM command reference**:

- **Common commands:** a plain-English explanation of each of the 150 or so commands districts use most.
- **Every command:** every command in GAM's own reference, grouped by section, with the full syntax.

How to use it:

- **Search:** type words like *reset password*, *lost chromebook* or *legal hold* and results appear as you type, with your words highlighted. Synonyms work, so *chromebook* also finds *cros*.
- **F1:** opens the guide at the page you're on. The *How to use this page* link in each page's tip line does the same.
- **Open this in GAMbit:** jumps to the page and tab. **Open in Command Builder** and **Copy command** do what they say for GAM commands.
- **Save the guide as a web page…:** saves one searchable HTML file you can print or share.

Tabs added in future versions appear in the guide automatically, using their on-screen description.

## Round 14 additions

### New pages

- **Meet attendance (Reports):** for e-learning days.
  1. Pick a teacher and a day, then *Load classes and meetings*.
  2. Pick the class and meeting, then *Take attendance*. Students are listed as Present, Partial, Absent or "Not on the roster", from Google's Meet log (`report meet … call_ended`) compared with the Classroom roster.
  3. *Email it* sends the list to the attendance office.

  It can also show the meeting's recordings and transcripts (`print meetconferences`, `meetrecordings`, `meettranscripts`).
- **AI use (Reports):** Gemini activity by school, grade and week, what it's used for, and use from org units where your policy doesn't allow it (`report gemini`).
- **Directory quality (People):** a completeness score per school (title, department, manager, phone and employee ID for staff; student ID for students), what's missing for each person, and likely duplicate accounts. Duplicates are the same ID twice, two accounts with the same name, or a student who also has a staff account.
- **Cost per student (Admin):** for each school, Chromebook cost spread over the device's life, license cost (prices from the Budget planner) and the last 12 months of repairs, divided by the number of students.

### New tabs

- **Investigations:**
  - *Public apps list*: a parent-facing list of apps used with student accounts and their approval and data-privacy agreement status, saved as a web page or Google Sheet. Add *Purpose*, *DPA* and *Privacy* columns to your approved list to fill it in.
  - *Shared passwords*: student accounts signed in on many Chromebooks (carts and loaners are ignored), on several networks in one day, or from different places minutes apart. One click requires a new password.
- **Unusual activity:** a new *Impossible travel* rule – sign-ins to a staff account from two regions within 2 hours.
- **Chromebook fleet:**
  - *Battery forecast*: fits the trend in each battery's reports, predicts when it falls below your replacement level, and builds an order list by school and model.
  - *Repeat damage*: students with several damage repairs over the years, from repair tickets and assignment history.
  - *Device tools*: checks serial numbers before devices arrive (`print chromesnvalidity`), shows active device counts, shows what an app or extension can reach (`info chromeapp`), downloads a device's log files (`get devicefile`) and lists printer models.
- **Budget planner → Premium licenses:** Teaching and Learning and Education Plus holders who haven't hosted a meeting over 100 people, watched a live stream or run originality reports. Releasing those licenses goes through Approvals.
- **Classroom:**
  - *Teacher status*: shows who is a verified teacher and can create classes (`print classroomprofile`), and active classes per teacher or student (`print course-counts`).
  - *Guardian follow-up*: re-sends invitations nobody answered (up to twice), cancels invitations to mistyped addresses (`cancel guardianinvitation`), and shows acceptance by school and teacher. It can run every Monday.
- **Google Drive → Folder tools:** hand one folder or file to someone else (`transfer` or `claim ownership`), see where it lives, read its comments (including deleted ones), check its size, and find broken shortcuts.
- **More services:**
  - *Form responses*: reads a form's responses straight from Google.
  - *Trusted domains*: manages allowlisted domains.
  - *Chat moderation*: lists every space as an admin, shows its members, removes someone, or deletes a space.
  - *Calendar sharing & out of office* gains *Replace someone in meetings* (`update calattendees … replace`).
- **Policies by org unit → Wi-Fi networks…:** pushes or removes a Chromebook Wi-Fi network for an org unit (`create`/`delete chromenetwork`). The passphrase is hidden in the Output panel and the activity log.
- **Users → Photo export:** saves everyone's profile photo as `<email>.jpg`.
- **Email → Gmail language:** sets the Gmail menu language for a person or an org unit.
- **Records requests → Save searches in Vault:** saves each search in the request's Vault matter (`create vaultquery`).

## Round 19: the Helper (offline assistant)

- **Window size fix:** the "Running: gam …" status line no longer stretches the window past the screen. It now ends in "…" and shows the full command as a tooltip. Output, Jobs, Dry run and job output wrap long lines. The main window's content scrolls if it ever needs more room than the window has. Every window and dialog that opens bigger than the screen is shrunk to fit and moved into view, so the title bar and close button always show.
- **Taskbar icon fix:** `assets/gambit.ico` was rebuilt with `tools/make_ico.py`. The small sizes (16–128 px) are now classic bitmaps and only 256 px is PNG; Windows showed a broken taskbar icon for PNG-only small sizes. The icon is also set for the whole app (sign-in window and dialogs), and the installer's shortcuts carry the same AppUserModelID as the app (`GAMbit.App`).
- **Dark mode:** Settings & Updates → Appearance → *Colors*: Light, Dark or Same as Windows. It switches right away. Dark mode has its own palette and stylesheet. Colours set anywhere else are converted as they are applied: stylesheets, label HTML, HTML views, and table, list and tree text. Light backgrounds become dark, dark text becomes light (same hue), and already-dark parts such as the output log are left as they are. Tests check that no dark text or light background is left on any page.

- **Assigned users, more:**
  - *Blank it when nobody is using the Chromebook* blanks the assigned user after N days without use. "Use" is Google's last active day, or the last check-in. You can also blank devices with no usage date. Loaner, repair, lost and testing org units are left alone.
  - *Every morning (5:45 AM)* runs one task, `--task deviceassign`. It blanks unused devices first, then sets the assigned user from the student who last signed in, with the tab's settings.
  - Devices that were just blanked aren't refilled from an old sign-in.
  - Every run saves backups, so Undo works. A run stops if it would change an unusually large number of devices.
  - The last signed-in user itself is reported by Google and can't be changed.

- **Org units & schools (Settings & Updates):** a district org unit map. Each org unit is marked Students, Staff, Chromebooks/devices, Loaners, Repairs, Lost, Former students, Former staff, Testing or Other, with an optional School and Grade. Everything below a marked org unit inherits from it. *✨ Find them for me* guesses from the names:
  - top-level kinds;
  - schools under students, staff and devices, matched across names, fuzzy matches and initials (HMS → Hancock Middle School);
  - grades (9th Grade, Grade 10, K, Pre-K, Class of 2031, Seniors).

  The Schools tab checks that each school has its student, staff and Chromebook org units. The map is shared through the team folder. Student lookup, Assigned users (students only, and moves), Assignment sync and Home use it. Without a map, GAMbit guesses the student org unit from the top-level names (/StudentAccounts) instead of assuming /Students.
- **Fixes:**
  - Assigned users said real students "aren't a student". It used Student lookup's default /Students; it now uses the map or the guess.
  - The device org unit for moves now comes from the map, so a school's Chromebook org unit can have a different name. The pattern option is still there and warns when it has no `{school}`.
  - Devices already inside the right school's org unit (a cart sub-OU, say) stay put.
  - Loaner, repair, lost and testing org units are never moved.

- **Chromebook fleet → Assigned users:** blank the Assigned user field, or set it to the person who last signed in. Choose all Chromebooks, org units, serials or asset IDs. *Preview* shows a Plan and a Why for each device. Filters: only fill blanks or also replace, students only (Student lookup's student org units), an ignore list such as `tech*`, and last used within N days. People outside the district are skipped. Old values are saved to a CSV before any change (in fleet/assigned-user-backups), and *Undo last change* restores them. It runs as `gam cros <ids> update user ""` (200 devices per command) and `gam cros <id> update user <email>`, through approvals and dry run. The Helper understands "clear the assigned user on 5CD…" and "assign chromebook 5CD… to mary jones".
- **Chromebooks follow their student's school:** in the same tab, *Move it to the student's school org unit* uses the student who last signed in (or the assigned user). For example, a student in `/Students/Hancock High School/9th Grade` → the device moves to `/Chromebooks/Hancock High School`. You set the school level and the device org-unit pattern (`/Chromebooks/{school}`), and both `\` and `/` work. It skips staff, the ignore list, disabled devices, "Don't move" org units (loaners, repairs, lost) and org units that don't exist yet. *Every morning…* schedules it (the `--task devicemove` background task, 5:50 AM). That task stops if there are unusually many moves, and it saves a backup each run. Moves are batched per target org unit (`gam cros <ids> update ou <ou>`), and *Undo last change* moves the devices back.
- **Several Chromebooks at once:** on Chromebooks → Find / list devices (Asset ID or Search text) and One device → Find by asset ID, type or paste several values separated by commas, spaces or new lines, like `HS0116, HS0189`. GAMbit sends them as one GAM `queries` search.

Click **💬 Helper** in the top bar or press **F2**. A sentence typed into the top search box
goes to the Helper too.

- **Understands plain English with typos.** Typo correction against GAMbit's own vocabulary, school words ("kid", "teacher", "lock", "out of office", "won't turn on"), and names, emails, groups, org units, serials and asset tags from the directory. It asks when something is missing ("Who is it for?") and offers a choice when two people share a first name. "Her" or "them" means the last person mentioned.
- **Finds the right page** for a question, using a ranked search over the Guide, every page and tab, and the top-bar tasks.
- **Walks through a page** one step at a time: it opens the page, switches to the tab the step names, and *Show me* highlights the button.
- **Writes GAM commands** for about 35 common jobs: passwords, suspend, move, sign out, 2SV, groups, aliases, forwarding, vacation, Drive transfer, Chromebooks, inactive devices, end of updates and look-ups. Every command is checked against GAM's own syntax reference (GamCommands.txt) and marked *changes things* or *only reads*.
- **Explains** a pasted GAM command.
- **Nothing runs on its own.** *Run* goes through the normal runner, so the GAMbit role, help-desk mode, Dry run and approvals all apply. Changes ask first. *Edit in Console* and *Copy* are on every card. Pages a role can't open aren't offered.
- **Optional local AI** (⚙ in the Helper) answers open questions using the Guide as context. It runs on this PC on 127.0.0.1 only, never through a proxy. It can be GAMbit's own (llama.cpp `llama-server` plus Qwen2.5 3B or 1.5B, downloaded once into AppData\local-ai) or an existing Ollama. You can also choose files copied from another PC. Commands it writes are checked against GAM and labelled as written by the AI.
- Code: `gambit/helper/` (text, knowledge, commands, verify, brain, local_ai) and `gambit/ui/helper_panel.py`. Tests: `tests/test_helper.py`.

## Round 17: bug sweep

Three code reviews (sign-in/security, GAM command syntax, data modules), a click-every-button test of all 62 pages (about 1,000 buttons), and every background task were run. Fixed:

**Sign-in and access**
- Org-unit-limited users: batch/CSV commands, changes GAMbit can't match to a person/OU/device, new accounts without an OU, OU edits, aliases and any out-of-scope account named anywhere in a command are now refused. Looking up out-of-scope accounts is refused too.
- A demoted admin's key can no longer sign the access list. Keys of people who lose admin are dropped automatically, and saves that would leave no admin with a trusted key are refused, so admins can't lock themselves out.
- The emergency admin must be registered in the signed access list (a hand-made record on a PC isn't accepted). Unprotected secret files are refused on Windows. The emergency admin can fix sign-in settings when the PC holds a GAMbit admin key.
- Roles tied to a GAM profile can't run GAM on another profile or switch with `select`/`config`. GAM paths, profiles, project sharing, backups and GAM updates in Settings are locked for non-admins.
- A damaged or half-synced access list shows a clear message instead of crashing. Unlocking after a failed reload no longer empties the access list.
- Role definition changes reach open GAMbit windows. Edits to built-in roles are kept. People whose role was deleted fall back to No access.
- Smaller fixes: Quit during Google sign-in stops the wait. The admin-key code check ignores dashes. The sign-in listener can't share its port. Background permission checks no longer touch widgets.

**Data and background jobs**
- Roster sync no longer takes over a namesake's account (same name, different SIS ID). OU comparisons ignore case.
- GAM timeouts no longer crash loops. The run-later queue, request form and self-service save progress per item. Offboarding follow-ups are isolated per person.
- Stale-class scan won't propose archiving every class when Classroom counts fail.
- Two email approvals in one batch both count.
- Settings watch: no false "removed" alerts after a partial read, writes are atomic, and it survives a damaged snapshot.
- Storage forecast handles nearly flat growth. Task health no longer flags "Failed: 0" and detects runs properly.
- Time machine snapshots are written atomically and truncated files are skipped.
- Nightly roster-sync leavers, mismatch fixes and clean-up rules refresh their open approval request instead of filing a new one every night. Watchdog doesn't re-alert yesterday's events.
- Automatic groups don't treat a read error as "group missing". Guardian follow-up only counts resends that worked.
- The GAM zip extraction path check was fixed. Student flags read 1970 as "never signed in". OU prefix checks respect "/" boundaries (oupath.py).

**GAM commands and screens**
- Battery forecast used telemetry fields GAM rejects. It now uses `showorgunitpath` plus a model lookup.
- Meet attendance times include the PC's UTC offset.
- Reports → Chromebook end of updates and Storage crashed when sorting (old table API).
- Pages and tabs whose saved data is damaged now show a short note instead of stopping GAMbit from starting.
- Saved findings, lost/withdrawn devices and storage history skip malformed records.
- Field-name tests now also cover telemetry and named field constants.

## Round 16: sign-in, access control and fixes

**GAMbit sign-in (Settings & Updates → Users & access)**
- Google sign-in (OAuth 2.0 desktop flow with PKCE, state and nonce; the ID token is verified locally against Google's keys, issuer, audience, expiry, verified email and the district domain). No Google tokens or passwords are stored.
- Access list in `<team folder>/access/access.json`, signed with an admin's Ed25519 key (kept on the admin's PC, encrypted with Windows DPAPI). Each PC pins the trusted keys and the newest version, so edited, forged or rolled-back lists are refused; a missing list on a PC that requires sign-in fails closed. The first time, each PC asks the tech to check the admin's key code.
- People: email, role, org units, can sign in. Anyone not listed gets *No access*. New admins ask for their key to be trusted; an existing admin checks the code and approves it.
- Roles: per-page Hidden / View only / Full, allowed actions and approval requests, optional org-unit limit, and an optional GAM profile so GAM itself runs as a limited delegated admin.
- Org-unit scope: the directory, pickers and search only show people in scope, and changes to people, org units or Chromebooks outside it are refused (checked for background jobs too).
- Idle lock (default 30 minutes), session limit (default 10 hours), sign out, and access changes picked up every 3 minutes.
- Emergency admin: one per PC, a 14+ character password (scrypt) plus an authenticator code (TOTP with QR, no code reuse), lockout after 5 failures, alerts on every use.
- Sign-in log: sign-ins, refusals, locks and access changes, kept in the team folder.

**Fixes and additions**
- Account time machine (and Budget planner licenses, Staff card, day-one readiness): `licenses` was sent inside `fields`, which GAM rejects. It's now its own option. Student lookup also asked for a field GAM doesn't have (`suspensionreason`). A new test checks every `fields` list against GAM's syntax file.
- Chromebooks: *…or asset ID* lookup on One device, an *Asset ID* search mode, Asset ID next to Serial in every device list, and asset IDs typed in the top search box open the device.
- Student lookup: choose the student org units. Only students are suggested and looked up (tick *Include staff* to override).
- More services → Admin roles: the role is a dropdown of Google's roles and your custom roles, each with a plain-English description, plus *What can it do?* to list a role's privileges.

## Round 15 additions

**New pages**
- **Staff card** (People) – one staff member's 2-Step Verification, recovery options, admin roles, storage, outside sharing, devices, licenses and premium use, app passwords, mailbox delegates, forwarding and connected apps.
- **Back to school** (Start) – August readiness by school: students signed in, Chromebooks assigned, guardians invited, teachers verified, this year's classes created, with *Fix:* buttons.
- **Mailbox access review** (Admin) – delegates, send-as addresses and calendar writers; flags leavers, outsiders and other-school access; quarterly sign-off (saved to the team folder).
- **Account recovery** (Admin) – staff without a recovery phone/email by building, plus a BCC reminder campaign.
- **Changes outside GAMbit** (Reports) – admin-log changes with no matching GAMbit activity entry within 15 minutes.

**New tabs and buttons**
- Student lookup → **Flags**: sign-ins, missing work, Chromebooks, sign-in places, risky apps, Meet, AI use, guardians, repairs, unusual activity.
- Chromebook fleet → **Asset register**: finance CSV vs Google (never enrolled / not on finance list / tag mismatch), copy tags into Google, inventory CSV with age, straight-line book value and end of updates.
- Budget planner → **Next year**: grade roll-up from org units, feeder schools, kindergarten estimate, Chromebooks still supported next year, devices and licenses to buy.
- Groups → **Group clean-up**: suspended/former members, outsiders in staff groups, direct + nested duplicates, staff in another school's group.
- More services → **Room features** and **Working locations** (weekly building schedule for itinerant staff).
- Staff devices → Chrome profiles → **Clean up old profiles** (`delete chromeprofile`).
- Google Drive → Shared drive settings → **Who manages them?** (`print shareddriveorganizers`), add a manager to orphaned drives.
- Storage forecast → **Mailbox sizes** (`print gmailprofile`).
- Drive labels → **Who can apply it?** (`classificationlabelpermission`).
- Staff leaving → Other data → **Google Tasks**.
- Home scorecard shows a red alert line when a number breaks sharply from its usual range (also sent through Alerts on the weekly snapshot).
- The leadership dashboard sheet is now updated in place with `update sheetrange` (charts and formatting survive), falling back to replacing the tab.

## Automated tests

`run_tests.bat` (or `python -m pytest -q`) runs about 150 tests in under a minute. They use a pretend GAM (`tests/fakegam`), so nothing touches Google. The tests cover the roster sync plan, onboarding, offboarding, activity log masking and undo, roles, deployment files, rooms, the guardian report and signatures. They also open every page, check dry run, and check that a 30,000-row table stays fast. The Builder can run the tests before every build (*Run the tests first*).

Large districts: results tables use a model/view table, so loading, sorting and filtering 50,000 rows each take well under a second.

## More GAM power

These pages put more of GAM's features behind buttons. Anything that changes something goes through dry run, roles, the activity log and the big-change preview, like the rest of GAMbit.

### People

- **Users → Photos**: upload profile photos in bulk. Name each file after the person's email, username or SIS/employee ID (`104522.jpg` matches the account with that ID). Preview first.
- **Users → Recently deleted**: accounts deleted in the last 20 days, with how long is left to restore each one. *Restore selected* can put them in an org unit and unsuspend them.
- **Email → Send as**: let people send as a shared address such as `frontoffice@`, with an optional reply-to and default.
- **Groups → Automatic groups → New Google dynamic group…**: Google keeps the members up to date from a rule. The rule can be people in org units (and below), a job title or a department, with suspended accounts left out. Not every Google edition includes dynamic groups.

### Chromebooks and Chrome

- **Chromebooks → Send a command**: pick serial numbers or an org unit, then restart, set the volume, take a screenshot, sign everyone out (wipe users) or powerwash. Restart, volume and screenshot only work in kiosk mode or at the sign-in screen.
- **Chromebook fleet → Health**: battery health (full charge vs. design capacity), charge cycles, free storage and update status. Devices that need attention are listed first. Needs device telemetry reporting turned on in the Admin console.
- **Chromebook fleet → Apps & extensions**: everything installed, most-installed first. VPN, proxy and unblocker names are flagged, and you can see which devices have one.
- **Chromebook fleet → Printers**: create or update printers from a CSV (Name, Address, Org unit, Description, Make and model).
- **Policies by org unit → Change or copy policies…**:
  - Search Google's policy list, pick a policy, fill in its settings and set it for an org unit.
  - Or copy every policy set directly on one org unit to another. Complex values that can't be copied are listed so you can set them by hand.

### Investigations (Reports → Investigations)

- **Audit log**: ready-made questions, or choose the log yourself, with a person, an org unit and how many days to look back. The questions are:
  - who opened, downloaded or printed a file (paste its link);
  - who changed sharing;
  - files someone deleted;
  - suspicious sign-ins;
  - admin changes to an account;
  - new app sign-ins.
- **Meet usage**: meetings, participants, hours and outside participants, grouped by the organizer's org unit.
- **App access**: third-party apps people have signed in to, how many people use each and what it can reach. *Remove selected app from everyone…* signs everyone in the org unit out of it. Block it in the Admin console too, so they can't sign in again.

### Calendar (More services → Calendar → Calendars in bulk)

- **Add an event to many calendars**: puts an all-day or timed event on each person's own calendar, without sending invitations. GAMbit remembers each batch, and *Events GAMbit added* removes a batch from everyone again.
- **Add a calendar to people's lists**: subscribe people to a calendar (or remove it from their lists).
- **Cancel a leaver's future meetings**: shows, then cancels, the future meetings the person organizes. Guests can be emailed.

### Classroom → Coursework

- **Missing work**: late, not-turned-in assignments for one class or all of a teacher's active classes, either listed one by one or counted per student.
- **Copy coursework**: copies assignments, materials and topics from one class into other sections, as drafts by default.

### Google Drive

- **Orphaned files**: gathers files that aren't in any folder into one folder per person, for one person or a whole org unit. Preview first.
- **Labels**: apply or remove a Drive label (and a choice field) on a list of files, or on every file in a folder.

### Security reports and alerts

- **Security reports → Sign-in & access**: single sign-on profiles, where each one applies, and context-aware access levels. All read only.
- **Google Chat alerts** (Settings → Google Sheets and email): failure alerts can also post into a Chat space, as a person who is a member of it. GAM needs the Chat scopes for user access.

## Security and clean-up tools

- **Workflows → Hacked account**:
  - *Look for signs* shows the account's Gmail filters (ones that forward, delete or hide mail are flagged and pre-selected), recent sign-ins, the mail it sent, and its forwarding, delegates and send-as addresses.
  - *Lock it down* runs the fix in one go: reset the password and sign out every session; remove app passwords, backup codes and app access; turn off POP/IMAP and forwarding; delete the selected filters and remove delegates. Turning off 2-step verification and suspending the account are optional.
  - The new temporary password is shown once, and a security alert can go to the tech team.
- **Google Drive → Fix sharing**: finds files (for one person or an org unit) shared with "anyone with the link" or with outside people or groups. For the selected rows it either switches link sharing to district-only (keeping the role) and removes outside people, or removes the sharing completely. The "Files shared outside the district" security report points here.
- **Google Drive → Move & copy folders**:
  - Move a My Drive folder into a shared drive, keeping its folders and sharing. Files the person doesn't own get a shortcut.
  - Copy a whole folder tree into another person's My Drive (for example a curriculum folder for a new teacher).
- **Users → Directory details**: compares your HR sheet (CSV or Google Sheet) with Google and updates manager, work and mobile phone, building, floor and room, and job title and department. People are matched by email or employee ID. Building names match the buildings from the rooms import.
- **Devices → Staff devices**: Windows laptops, Macs and phones signed in to district accounts (Google endpoint management). You can approve or block the account on a device, remove the district account from it, factory-reset company-owned devices, or cancel a wipe.

## Reports

- **Reports → Usage**:
  - *District trend*: weekly 30-day active users for sign-ins, Gmail, Drive, Meet and Classroom over up to 12 months.
  - *By school and teacher*: the share of accounts at each school that used each app in the last 30 days, and Classroom posts per teacher.
- **Chromebook fleet → OS versions**: ChromeOS versions in use, newest first, with how far behind each one is.
- **Groups → Everyone who gets it…**: expands nested groups to list every person who receives a group's email.
- **Security reports → Groups open to outsiders**: groups with outside members allowed, that anyone on the internet can email, that anyone can join, or that show their member list publicly.
- **More services → Vault**:
  - *Count matching mail first* counts the messages before you export.
  - *Holds covering a person…* lists every hold that applies to someone, directly or through their org unit.

## Leavers' other data

- **Workflows → Staff leaving** has two new optional steps:
  - **Looker Studio**: gives the supervisor editor access to the person's reports and data sources. Google doesn't allow ownership transfer.
  - **Email archive**: copies their mail into an archive group before the account is suspended. Set the group in the form.
- **Google Drive → Keep notes**: list someone's Keep notes and share them with another person.
- **Email → Archive to a group**: copy a mailbox (or part of it, using a Gmail search) into a Google Group's archive. It can create the group as archive-only first.
- **More services → Shared contacts**: add district-wide contacts (vendors, offices, substitutes) from a CSV. They appear in everyone's Gmail autocomplete.

## Faster bulk jobs

Bulk (CSV) now has an *At the same time* setting (GAM's `num_threads`, default 10 in GAMbit; GAM's own default is 5) and a *Try the first 3 rows* button. With 20 at a time, a 10,000-row job finishes in minutes. If Google reports "quota exceeded", lower the number.

## Recovery and oversight

- **Google Drive → Restore files**:
  - *Trashed files* lists what a person trashed recently (from the audit log) or everything in their trash, and restores the selected files or all of them.
  - *Earlier versions* lists a file's versions, showing who saved each one and when. For uploaded files (PDF, Word, images) the selected version can be put back as the current one. Google Docs, Sheets and Slides have to be restored from File → Version history in the file itself.
- **Email → Restore deleted mail**: preview and restore trashed messages with any Gmail search (default `in:trash newer_than:7d`).
- **Reports → Settings watch**:
  - *Take a snapshot now* saves every Admin console setting (Cloud Identity policies) and the Chrome settings at the top org unit. Snapshots go in the team folder's `settings-snapshots` if you have one.
  - Compare any two snapshots to see exactly what was added, removed or changed.
  - Tick the box to check every night (background task "GAMbit settings watch", 5:05 AM) and get an alert whenever something changes.
- **More services → Admin roles → New custom role…**: pick privileges (with templates such as "Building tech"), then optionally assign the role to someone for one org unit only.
- **Workflows → Staff leaving**: the daily background task now checks each leaver's Drive/Calendar transfer and alerts if one failed. *Other data…* shows the transfer status, YouTube channels, Keep notes and Looker Studio assets for a selected leaver.
- **Staff devices → Chrome profiles on computers…**: managed Chrome profiles on Windows, Mac and Linux, with Chrome version, extensions and last use.
- **Security reports → Forms that don't check who answered**: Google Forms that don't require sign-in or don't verify emails.
- **Classroom → Class activity**: announcements, materials and assignments per class for a teacher, flagging classes with nothing posted.
- **Classroom → Student groups**: create Classroom student groups from a CSV (Class, Group, Student email) and set their members.
- **More services → Domains**: your domains and alias domains.

## Everywhere

- **Global search** (top bar): jump straight to a person, group, org unit or Chromebook serial, or search commands.
- **Right-click** any results table: open a user, reset a password, require a password change, sign out, suspend or unsuspend, open a Chromebook, disable or re-enable it, or copy.
- **Background jobs**: up to 4 GAM commands run at once, and more wait their turn. The Jobs tab shows progress, elapsed time, cancel, re-run and each job's full output.
- **Plain-English errors**: common GAM errors come with a 💡 hint explaining what to do.
- **Help-desk mode** (Settings): hides and blocks delete, wipe, suspend, deprovision and data-transfer actions, plus advanced pages. Unlocking it needs a PIN.
- **Google Sheet** button on every results table: uploads the rows as a new Google Sheet and opens it.
- **Report a problem** (Settings, Diagnostics, or after an unexpected error): saves a zip to send for help. It contains GAMbit's logs, settings with passwords, tokens and webhooks removed, two weeks of the (masked) activity log, and the Output panel.
- **Chat alerts** (Settings → Google Sheets and email): a Teams (Workflows webhook), Slack or Google Chat webhook gets an alert when a scheduled job, roster sync or background task fails. Email alerts work too.
- **Update channel** (Settings): *Beta* testers also get versions published to `latest-beta.json`.
- **Explain this command** (Console, Activity log, Ctrl+E): breaks any GAM command into plain English and shows the matching syntax from GAM's reference.
- **Keyboard shortcuts** (Shift+F1 lists them; F1 opens the guide): Ctrl+K search, Ctrl+1–9 pages, Ctrl+Enter run, Ctrl+B Builder, Ctrl+H activity log, Ctrl+J jobs, Ctrl+. stop, F5 refresh.
- **Text size** (Settings): Small, Normal, Large or Extra large.
- **Guided tour**: runs on first start; replay it from Home or Settings.
- **Domains (profiles)** (Settings, then the Domain box at the top): switch between several GAM configurations, either separate config folders or `gam.cfg` sections. Each profile keeps its own cached lists.

## Pick lists (org units, people, groups)

After a successful connection test, GAMbit loads your org units, users and groups in the background. It caches them on disk and refreshes them once a day; you can also refresh them from Settings & Updates.
- Org unit fields have suggestions and a **Browse…** tree. Searches can tick several OUs, with or without sub-OUs.
- Email fields suggest people as you type a name.

## Project layout

```
main.py                     app entry point
gambit/version.py           version + GitHub repo (Builder edits __version__)
gambit/gam_runner.py        runs gam in the background, streams output
gambit/updaters.py          GAM updater + GAMbit latest.json updater
gambit/gam_setup.py         setup helpers (config folder, PATH, console launcher)
gambit/ui/setup_wizard.py   first-run Setup Wizard
gambit/directory.py         cached OUs/users/groups + shared connection test
gambit/group_settings.py    group permission options and presets
gambit/ui/pickers.py        OU tree/field, person search, people picker, TargetPicker
gambit/command_catalog.py   GamCommands.txt parser, catalog, search, download
gambit/ui/builder_form.py   grammar → form widgets
gambit/ui/pages/builder.py  Command Builder page (favorites, templates)
gambit/builder_store.py     favorites/templates JSON
gambit/scheduler.py         Windows Task Scheduler jobs
gambit/profiles.py          domain profiles
gambit/ui/app_actions.py    global search, right-click actions, help-desk, profiles
gambit/ui/jobs_panel.py     background jobs panel
gambit/sis.py               SIS export readers, rules and sync plan
gambit/ui/pages/rostersync.py  Roster sync page; ui/cards.py password cards
gambit/activity.py          activity log, undo inference, affected-count preview
gambit/explain.py           "Explain this command"
gambit/dashboard.py         Home dashboard numbers (cached daily)
gambit/google_io.py         Google Sheets download/upload and sendemail wrappers
gambit/diagnostics.py       read-only access checks;  ui/pages/diagnostics_page.py
gambit/headless.py          background tasks (--task sync|daily|requests|groups|digest|signatures|guardians)
gambit/intents.py           "What do you want to do?" tasks; ui/page_help.py page tips
gambit/livetest.py          Live test checklist;  ui/pages/livetest_page.py
gambit/tasks_health.py      Background tasks page data; ui/server_kit.py server kit
gambit/onboard.py           New staff setup for staff roster syncs (+ signature retries)
gambit/signature.py         signature template, preview, weekly rollout
gambit/rooms.py             rooms/resources import plan;  ui/rooms_dialog.py
gambit/parent_report.py     guardian report by school;  ui/pages/guardian_report_tab.py
gambit/tools/               photos, chrome (commands/health/apps/printers/policies),
                            investigate (audit/Meet/app access), people (undelete, send as,
                            dynamic groups, Chat), calendar_class, drive_extra,
                            security_ops (hacked account, sharing fix), more_tools (shared-
                            drive moves, directory details, devices, usage, versions, groups,
                            Vault, Keep, contacts, threads), recovery (restore, settings
                            watch, admin roles, transfers, Chrome profiles, Forms, Classroom
                            activity/student groups, YouTube, domains)
gambit/tools/reconcile.py   mismatch report, withdrawn students' devices
gambit/tools/watchdog.py    unusual-activity checks (+ --task watchdog)
gambit/tools/budget.py      license savings, Chromebook replacement plan
gambit/yearend.py           year-end checklist and reminders
gambit/school_reports.py    weekly per-school principal reports (+ --task schoolreports)
gambit/history.py           searching the activity and task logs
gambit/approval_policy.py   automatic approval, two approvers, escalation
gambit/ui/pages/insight_pages.py  screens for the above
gambit/integrations/sis_api.py    ClassLink, OneRoster OAuth 2 SISs, Clever, PowerSchool → OneRoster zip
gambit/integrations/ticketing.py  help desks (iiQ, Zendesk, Freshservice, Freshdesk, ServiceNow, Jira SM, WHD, TeamDynamix, osTicket)
gambit/tools/playbooks.py   unusual-activity responses, settings drift guard
gambit/tools/ticket_auto.py password tickets end to end
gambit/tools/device_history.py  Chromebook timeline, repair hotspots, loaner needs
gambit/scorecard.py         weekly district scorecard (+ --task scorecard)
gambit/audit_report.py      monthly audit report (+ --task auditreport)
gambit/teacher_lists.py     teacher follow-up lists (+ --task teacherlists)
gambit/whatif.py            practice runs
gambit/tools/phishing.py    phishing clean-up
gambit/tools/policy_sets.py testing mode and staged rollouts (save, apply, put back, watch)
gambit/tools/campaigns.py   2-Step Verification campaign (+ --task campaign2sv)
gambit/tools/app_vetting.py approved apps check
gambit/tools/ownership.py   groups / shared drives / classes / files nobody owns
gambit/temp_accounts.py     time-limited accounts
gambit/timemachine.py       nightly account snapshots and restore (+ --task timemachine)
gambit/saved_questions.py   scheduled Ask GAMbit questions (+ --task questions)
gambit/leader_sheet.py      leadership dashboard Google Sheet (+ --task leadersheet)
gambit/integrations/        ClassLink OneRoster, Incident IQ, Ask GAMbit (Claude API)
gambit/email_approvals.py   approve/deny by email reply
gambit/custom_workflows.py  My workflows (fields + steps)
gambit/tools/automation.py  Chromebook assignment sync, clean-up rules
gambit/ui/tools_base.py     ToolTab base;  ui/pages/*_tabs.py, investigations_page.py
tests/                      pytest suite with a fake GAM (run_tests.bat)
gambit/rostersync_run.py    unattended roster sync
gambit/offboard.py          staged offboarding records, undo, follow-ups
gambit/selfservice.py       staff request form → approvals
gambit/fleet.py             Chromebook inventory / import / collection / AUE
gambit/compliance.py        security report definitions
gambit/classroom_year.py    archive + create classes from the SIS
gambit/alerts.py            Teams / Slack / Google Chat webhooks
gambit/support.py           logging, crash handler, problem-report zip
gambit/deploy.py            deployment file, backup/restore, shared Google project
gambit/guardians.py         guardian links from the SIS, plan, missing report
gambit/group_rules.py       automatic group rules (+ --task groups)
gambit/policies.py          org-unit policy matrix
gambit/timeline.py          per-account timeline
gambit/digest.py            weekly digest (+ --task digest)
gambit/ui/labels.py         Code 39 barcode labels
gambit/team.py              team folder: roles, command categories, approvals, shared settings
gambit/ui/roles_dialog.py   Manage roles; ui/pages/approvals.py Approvals page
gambit/ui/preview_dialog.py "Big change" list before acting on many accounts
builder/signing.py          code signing (pfx / cert store / Azure Trusted Signing)
gambit/ui/…                 window, theme, pages
builder/gambit_builder.py   Builder GUI (exe, installer, publish)
GAMbit.spec                 PyInstaller recipe (one-folder build)
installer/GAMbit.iss        Inno Setup script (per-user install, no admin prompt)
gambit/tools/baseline.py    security baseline rules, score and fixes (+ --task baseline)
gambit/tools/classroom_sync.py  daily Classroom roster sync (+ --task classroomsync)
gambit/records.py           FERPA / legal records requests with Vault
gambit/tools/readiness.py   day-one readiness for new staff
gambit/tools/lost_devices.py lost & stolen Chromebooks
gambit/change_queue.py      run later queue and change freezes
gambit/request_catalog.py   request form for principals and secretaries
gambit/release_check.py     checks before/after an update, rollback
gambit/ui/pages/round12_pages.py  pages and tabs for the above
gambit/tools/gam_extras.py  newer GAM commands: invitations, calendars, Classroom invites,
                            Chrome history/profiles/images, Drive sharing counts, ASPs, keys
gambit/access_review.py     quarterly admin access review
gambit/lifecycle.py         account timing (first sign-in, leavers, approvals)
gambit/storage_forecast.py  pooled-storage forecast
gambit/going_quiet.py       counselor list (+ --task goingquiet)
gambit/tools/test_readiness.py, redistribute.py, policy_cleanup.py, group_suggest.py, stale.py
gambit/ui/pages/round13_pages.py, round13_tabs.py  Round 13 screens
gambit/helper/              offline Helper: understanding, recipes, GAM syntax check, local AI
gambit/ui/helper_panel.py   the Helper dock (chat, command cards, walkthroughs, AI settings)
gambit/guide/               in-app guide: basics, pages_*.py (one entry per page), gam_ref.py
                            (plain-English GAM commands), search and HTML export
gambit/ui/pages/guide_page.py  the Guide page (F1)
gambit/tools/gam_extras2.py Meet, Forms, Wi-Fi, serial checks, device files, calattendees,
                            folder ownership/paths/comments, Classroom profiles, allowlist…
gambit/meet_attendance.py, ai_usage.py, apps_public.py, directory_quality.py,
gambit/license_rightsize.py, guardian_followup.py, cost_per_student.py
gambit/tools/shared_accounts.py, battery_forecast.py, repeat_damage.py
gambit/ui/pages/round14_pages.py, round14_tabs.py  Round 14 screens
gambit/ui/pages/round15_pages.py, round15_tabs.py  Round 15 screens
gambit/auth/                access.py (signed access list), google_sso.py, local_admin.py,
                            session.py (who is signed in, scope), crypto.py
gambit/ui/login_dialog.py, access_dialog.py, session_actions.py  sign-in screens
gambit/staff_card.py, student_flags.py, back_to_school.py, asset_register.py,
  next_year.py, outside_changes.py, recovery_coverage.py, delegation_review.py
gambit/tools/gam_extras3.py, group_hygiene.py  Round 15 GAM commands and checks
latest.json                 what installed copies check for updates
```

## First-time setup (developer PC)

1. Install **Python 3.11+** (python.org, with "Add to PATH") and **[Inno Setup 6](https://jrsoftware.org/isdl.php)**.
2. Clone the repo: `git clone https://github.com/Sbreland18/GAMbit`
3. Double-click `run_gambit.bat` to try the app. The first run creates `.venv` and installs the requirements.
4. Double-click `run_builder.bat` to open the **Builder**.

## Releasing an update (Builder)

### Get the latest code from GitHub
The Builder can pull the current files from GitHub before it builds, so the installer is always made from what's on GitHub plus your own changes. Tick **Before building, get the latest files from GitHub**, or click **Get latest now** to update the folder without building.
- **Folder is a git clone:** runs `git pull --ff-only --autostash`, which keeps your uncommitted changes.
- **No git (a downloaded or extracted folder):** downloads the branch through the GitHub API and compares three versions of each file: GitHub's, yours, and the version at the last sync (stored in `.builder_sync.json`).
  - Files changed only on GitHub are updated.
  - Files changed only here are kept.
  - Files deleted on GitHub are removed, unless you changed them here.
  - Files changed in both places: you choose **Use GitHub's** or **Keep mine**. Your copy is backed up to `_sync_backup/<time>/` either way.
- If GitHub's code already has the version you typed or a newer one, the build stops and the version box moves to the next number.

### Publish options
- **Upload my source code changes and latest.json with the GitHub API (no git needed):** your changes since the last sync go up as one commit. If someone else pushed since then, you're asked to get the latest first. The release points at that exact commit.
- **Upload only latest.json:** use this if you push the code some other way.
- **Commit & push with git:** use this if the folder is a git clone.

The token needs **Contents: Read and write** on the repository. For a private repository, getting the latest files needs the token too.


1. Pick the version. The **+ patch / + minor / + major** buttons bump it for you.
2. Type the release notes. Users see them in the update prompt.
3. Leave **Build exe** and **Build installer** checked.
4. Check **Publish this version**, then enter a GitHub token. To make one: GitHub → Settings → Developer settings → Fine-grained tokens. Give it access to `Sbreland18/GAMbit` with **Contents: Read and write**.
5. Choose how `latest.json` gets pushed:
   - **GitHub API** works without git, but it doesn't push your source changes. Commit those yourself.
   - **git** commits and pushes everything first, then pushes `latest.json` after the installer is uploaded.
6. Click **Build & Publish**.

The Builder runs these steps in order:

1. Writes `gambit/version.py`.
2. Runs PyInstaller.
3. Runs ISCC, which creates `dist/installer/GAMbit-Setup-X.Y.Z.exe`. With code signing on, GAMbit.exe, the installer and the uninstaller are all signed and verified.
4. Writes `latest.json`.
5. Creates GitHub release `vX.Y.Z` and uploads the installer.
6. Publishes `latest.json` **last**, so no copy ever sees an update before its installer exists.

### Beta releases

Choose **Release to: Beta testers only** to publish `latest-beta.json` and a GitHub *pre-release*. Only PCs set to the Beta update channel are offered it. Publish the same version again to *Everyone* when it's ready.

### Code signing

Signing removes the Windows "unknown publisher" / SmartScreen warning when staff install or update GAMbit. In the Builder's **Code signing** box, choose one of:
- **Certificate file (.pfx):** an OV certificate from a certificate authority, plus its password. The password is never saved.
- **Windows store / USB token (EV):** paste the certificate's SHA-1 thumbprint.
- **Azure Trusted Signing:** point at `Azure.CodeSigning.Dlib.dll` and a `metadata.json` (Endpoint, CodeSigningAccountName, CertificateProfileName). It's usually the cheapest option for an organization, but you have to pass Microsoft's identity validation first.

You need `signtool.exe` from the Windows SDK (*Signing Tools for Desktop Apps*). Signatures are timestamped, so they stay valid after the certificate expires.

`latest.json` format:

```json
{
  "version": "1.0.1",
  "url": "https://github.com/Sbreland18/GAMbit/releases/download/v1.0.1/GAMbit-Setup-1.0.1.exe",
  "notes": "What changed",
  "released": "2026-10-13"
}
```

GitHub's raw file cache can take about 5 minutes to show the new `latest.json`. To see what clients see, click **Check live latest.json**.

> "Remember token" stores the token in your Windows user registry (plain text). Leave it unchecked on shared PCs.

## Notes

- The default GAM folder is `C:\GAM7`. You can change it in Settings, and you can also set `GAMCFGDIR` there if your config lives somewhere else (e.g. `C:\GAMConfig`).
- The repo must be **public** so installed copies can read `latest.json` and download the installer without a token.
- Keep the `AppId` in `installer/GAMbit.iss` the same forever. That's how updates replace the old install.
