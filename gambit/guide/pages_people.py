"""Guide: Home, Workflows and People pages."""

PAGES = {
    "Home": dict(
        what="The district at a glance: account, license and Chromebook numbers, security "
             "alerts, failed jobs, favorites, quick actions and the weekly scorecard.",
        steps=["**Customize** (top right): drag boxes by ⠿ to move them, ✕ to remove, *Add a "
               "box* to bring one back (quick look-up, recently viewed, favorites, quick "
               "actions, waiting for approval, my open tickets, notes, links, background jobs, "
               "the numbers, the scorecard, what's new). *More options…* picks your quick "
               "actions, number tiles and links. It's just for you; *Reset to the default* "
               "(in More options) puts it back.",
               "**Quick look-up**: type a person (or a Chromebook serial / asset ID) and press "
               "Enter; *Check everything* runs the full check on that person.",
               "**Recently viewed** lists the last people, Chromebooks, groups and org units "
               "you opened (also at the top of the search box).",
               "Click any number tile to open the matching list (for example *Never signed "
               "in* opens those accounts).",
               "Use the quick-action buttons (Find a user, Look up a Chromebook, New staff / "
               "staff leaving…) for everyday jobs.",
               "**Refresh now** reloads the numbers; they also refresh once a day.",
               "The **scorecard** tracks key numbers week by week with a trend line. *Save "
               "this week's numbers now* or *Every Monday…* records them.",
               "*Leadership dashboard sheet…* keeps a Google Sheet for your director and "
               "principals up to date every night."],
        tips=["Right-click a favorite button to remove it.",
              "*Take the tour* replays the introduction."],
        commands=["gam print users fields …", "gam print cros fields …", "gam print alerts",
                  "gam print licenses"],
        keywords="dashboard scorecard numbers tiles favorites leadership sheet"),
    "Workflows": dict(
        what="Step-by-step helpers for jobs that take several GAM commands: a new staff "
             "member, someone leaving, the year-end rollover, graduation, Chromebook "
             "check-in/out, a hacked account and your own custom workflows.",
        steps=["Pick the tab for the job.",
               "Fill in the form (use *Fill in the test account* the first time).",
               "Click **Preview** (or Practice run) to see every step before anything "
               "changes.",
               "Run it. The checklist shows ○ waiting, ◐ running, ✔ done, ✖ failed, and a "
               "summary appears at the end."],
        tabs={
            "New staff": "One form creates the account (email suggested from the name), sets "
                         "the org unit, title and department, assigns a license, adds groups, "
                         "applies the signature and prints a welcome sheet with the temporary "
                         "password.",
            "Day-one readiness": "Checks staff accounts created in the last few days: active, "
                                 "licensed, in the right groups, signature, Chromebook, "
                                 "signed in. *Fix the gaps for selected* and *Email the "
                                 "summary* to HR.",
            "Staff leaving": "Full offboarding in stages. Today: lock the account, auto-reply, "
                             "forward mail and share the mailbox with the supervisor, "
                             "transfer Drive and Calendar, leave groups (roles saved), hide "
                             "from the directory, move to the leavers' org unit. Later: stop "
                             "forwarding, release licenses, suspend. Deletion is always an "
                             "approval. *People who have left* shows progress, with *Run the "
                             "next step now*, *Undo everything* and *Other data…* (YouTube, "
                             "Keep, Looker Studio).",
            "Year-end rollover": "Move students up a grade (map each grade OU to the next; "
                                 "*Fill in from grade org units…* builds the map), archive "
                                 "last year's classes and require new passwords.",
            "Year-end checklist": "Every end-of-year job in one dated checklist; each step "
                                  "opens the right screen and can be signed off.",
            "Chromebook check-in/out": "Scan a barcode to check a device out to a student, "
                                       "in to a cart or room, or mark it missing.",
            "Graduation": "Move seniors to the alumni org unit, set an auto-reply and email "
                          "Takeout instructions; later release licenses and suspend.",
            "Hacked account": "1. Look for signs (filters, forwarding, delegates, recent "
                              "sign-ins, mail they sent). 2. **Lock it down**: new password, "
                              "sign out everywhere, remove app passwords and app access, turn "
                              "off forwarding, optionally suspend.",
            "My workflows": "Build your own step-by-step jobs from GAM commands with fill-in "
                            "fields, and share them with the team.",
        },
        tips=["Turn on Dry run (or the switch on this page) to see every command first.",
              "Offboarding follow-ups run from the daily background task."],
        commands=["gam create user …", "gam update user … ou …", "gam user … deprovision",
                  "gam user … vacation on …", "gam create datatransfer …",
                  "gam update cros … ou …"],
        keywords="new hire onboarding offboarding leaving rollover graduation hacked "
                 "compromised checkout"),
    "Users": dict(
        what="Look up, create and manage Google accounts: passwords, suspension, org unit, "
             "aliases, security, photos, deleted accounts, directory details, time-limited "
             "and personal accounts.",
        steps=["**Manage a user**: type a name or email, then use the Account, Email "
               "addresses & aliases and Security sub-tabs.",
               "**Create a user**: fill in the name, email, org unit and password, then "
               "**Create user**.",
               "**Find / list users**: search by org unit, name or status, select rows and act "
               "on them (suspend, move, reset…). *☆ Save this search* keeps it – every org "
               "unit, sub-org-unit setting and custom field test.",
               "**Saved searches**: pick one in *Saved* to load it, then *▶ Run*. Change the "
               "search and click *Update with the search above* to edit it; *Rename…* and "
               "*Delete* are next to it. On Home, right-click a saved search for Run, Edit, "
               "Rename and Remove.",
               "**Google Sheet…** (next to a saved search) keeps a Google Sheet up to date "
               "with that search on a schedule – custom fields included – so counselors can "
               "bookmark a live list.",
               "**Custom fields** (your custom schemas, e.g. Student_Information → Grade, "
               "Student ID): click *Custom fields…* (or Settings & Updates → Custom user "
               "fields), *Read schemas from Google* and tick the fields. They're added as "
               "columns to user lists, so *Export CSV* includes them, and show in Lookup.",
               "**Search a custom field**: Show → *Custom field*, pick the field, *is / "
               "contains / starts with / is empty / has a value*, and optionally org units. "
               "Exact matches on searchable fields are found by Google; the rest are checked "
               "by GAMbit.",
               "Double-click a row anywhere to open that person."],
        tabs={
            "Manage a user": "Account: reset password (or just require a change at next "
                             "sign-in), sign out of all sessions, suspend, move org unit, "
                             "rename, delete. Email addresses & aliases: add/remove aliases, "
                             "export every alias. Security: connected apps (remove access), "
                             "2-Step Verification backup codes.",
            "Create a user": "Creates one account with password, org unit, title and "
                             "department.",
            "Find / list users": "Search and bulk actions on the selected rows.",
            "Photos": "Upload profile photos in bulk – name each file after the person's "
                      "email or ID and click *Match files to people*.",
            "Recently deleted": "Restore accounts deleted in the last 20 days, with their "
                                "data.",
            "Directory details": "Keep manager, phones, building and title right from an HR "
                                 "sheet: *Compare with Google*, then apply.",
            "Time-limited accounts": "Substitutes, student teachers and contractors with an "
                                     "end date: reminders a week before, then automatic "
                                     "suspension. *Extend…* or *End now*.",
            "Personal Google accounts": "Consumer accounts using a district address. "
                                        "*Invite selected to join* moves them under district "
                                        "control; *Check* tests addresses before creating "
                                        "new accounts.",
        },
        tips=["Limited roles send suspensions and deletions to Approvals automatically.",
              "Passwords are masked in the output and the activity log."],
        commands=["gam info user <email>", "gam update user <email> password … "
                  "changepassword on", "gam update user <email> suspended on|off",
                  "gam user <email> signout", "gam create alias <alias> user <email>",
                  "gam print userinvitations"],
        keywords="account password reset suspend unsuspend alias rename delete restore photo "
                 "substitute"),
    "Student lookup": dict(
        what="A one-card view for the front office: a student's account status, last sign-in, "
             "Chromebook, classes and guardians, with the common fixes on the same screen.",
        steps=["Type part of a name, email or student ID and click **Look up**.",
               "Use **Reset password** (an easy-to-read password is shown on screen), **Sign "
               "out everywhere**, **Require a new password** or **Unsuspend**.",
               "**✅ Check everything** (Ctrl+Shift+C) checks the account, password, "
               "sign-in, 2-Step, license, org unit, custom fields and their Chromebook, and "
               "lists every problem with a fix button – or *Fix everything GAMbit can*. With "
               "a ticket linked, *Add this to the ticket* posts what was found and fixed.",
               "**🖨 Print card** prints (or saves as PDF) a card with their name, email, a "
               "fresh temporary password if you tick it, their Chromebook and a QR code for "
               "Google sign-in – two per page to cut in half, or one large.",
               "**Timeline** shows everything that happened to the account; **Open in "
               "Users** for everything else."],
        tips=["Unsuspend goes to Approvals for limited roles.",
              "☆ Favorite keeps the student on Home."],
        commands=["gam info user <email>", "gam print cros query user:<email>",
                  "gam print courses student <email>"],
        keywords="front office student password chromebook classes guardian"),
    "Groups": dict(
        what="Browse every group, manage members and permissions, create groups, and keep "
             "groups filled automatically from rules.",
        steps=["Click a group in **Browse groups** to see its members.",
               "Select members to remove them or change their role; search for people to "
               "add.",
               "**Permissions…** edits who can post, view and join in plain English, with "
               "presets. **Aliases…** manages extra addresses.",
               "**Create a group** sets permissions and starting members in one go."],
        tabs={
            "Automatic groups": "Rules that say who belongs (org units, title, department, "
                                "exclusions, always include). *Preview* shows adds and "
                                "removes; *Every night…* keeps them right. Owners and "
                                "managers are never touched.",
            "Suggested automatic groups": "Finds hand-kept groups whose members match an org "
                                          "unit, title or department and turns them into "
                                          "rules (starting as 'only add people').",
            "Why do they get this?": "A person's groups and the groups those groups are "
                                     "inside – answers 'why am I getting this email?'.",
        },
        tips=["*Everyone who gets it…* expands nested groups.",
              "*New Google dynamic group…* creates a Google-managed membership query."],
        commands=["gam print groups", "gam print group-members group <g>",
                  "gam update group <g> add member user <email>",
                  "gam update group <g> settings …", "gam user <email> print grouptree"],
        keywords="group members owner manager permissions alias dynamic nested"),
    "Classroom": dict(
        what="Classes, teachers and students: find and manage courses, create them, sync "
             "rosters, set up the new year from the SIS, guardians, missing work, class "
             "activity, student groups and invitations.",
        steps=["**Courses**: find classes by teacher, student or state; open one to manage "
               "its roster, owner and name; archive, reactivate or delete.",
               "**Yearly setup**: archive last year's classes, then create this year's from "
               "ClassLink/OneRoster (named from a template, owner = primary teacher).",
               "**Daily roster sync** keeps those classes matched to the SIS all year.",
               "**Guardian sync** invites every guardian the SIS lists."],
        tabs={
            "Courses": "Find, open, archive, reactivate or delete classes.",
            "Create a course": "Create one class with an owner and alias.",
            "Roster sync (CSV)": "Sync students from a CSV – add only, or full sync.",
            "Guardians": "Invite, view or remove guardians for one student.",
            "Yearly setup": "Archive last year's classes and create this year's from the SIS.",
            "Guardian sync": "Invite all SIS guardians; optionally remove ones no longer "
                             "listed; report students with nobody invited.",
            "Guardian report": "A per-school report of guardian invitations for principals.",
            "Coursework": "Missing work for one class or teacher.",
            "Class activity": "Announcements, materials and assignments per class.",
            "Student groups": "Create Classroom student groups from a spreadsheet.",
            "Daily roster sync": "Adds (and optionally removes) students as schedules change; "
                                 "stops if there are too many changes.",
            "Invitations & topics": "Invitations nobody accepted (send again or remove) and "
                                    "copy topics into other classes.",
        },
        commands=["gam print courses …", "gam course <id> add student <email>",
                  "gam update course <id> state archived", "gam create guardianinvite …",
                  "gam print course-submissions …", "gam print classroominvitations"],
        keywords="class course teacher student roster guardian parent archive coursework"),
    "Roster sync": dict(
        what="Keep student or staff accounts matching a roster (SIS export, ClassLink or a "
             "Google Sheet): new people get accounts, moves are applied, leavers are "
             "handled – always with a preview first.",
        steps=["**1. Roster**: choose the source (file, Google Sheet or live SIS) and load "
               "it.",
               "**2. Rules**: how emails are made, which org unit each grade/school goes to, "
               "passwords, groups and licenses, and what happens to people who leave.",
               "**3. Preview & apply**: review New / Updates / Returning / Leaving, untick "
               "anything you don't want, then **Apply ticked changes**.",
               "*Save settings as…* and **Schedule…** to run it every night."],
        tips=["Test mode only touches the test org unit (max 3 new accounts).",
              "Nightly syncs send leavers to Approvals and stop if numbers look wrong.",
              "*Print password cards for new accounts…* makes handouts."],
        commands=["gam create user …", "gam update user … ou …",
                  "gam update user … suspended on"],
        keywords="sis sync import roster new students accounts classlink nightly"),
    "Mismatch report": dict(
        what="Your roster, Google accounts and Chromebook assignments side by side: students "
             "with no device, devices assigned to students who left, accounts in the wrong "
             "org unit, and more.",
        steps=["Click **Build the report**.",
               "Select rows and **Fix selected**, **Send selected for approval** or *Practice "
               "run of selected fixes*.",
               "*Add selected devices to the collection list* for devices to pick up.",
               "Turn on the nightly fix to repair safe mismatches automatically."],
        keywords="mismatch roster device assignment wrong ou withdrawn"),
    "Account timeline": dict(
        what="Everything that happened to one account, newest first: GAMbit changes, "
             "offboarding, Admin console changes, sign-ins, password and 2SV changes, app "
             "access, Chrome, Classroom and group events.",
        steps=["Choose the person and how many days to look back.",
               "Keep *Include Google's admin and sign-in logs* ticked for Google's audit-log events.",
               "Click **Show**."],
        tips=["Open it from right-click → Timeline on any table, or from Student lookup."],
        commands=["gam report admin user all filter USER_EMAIL==<email>",
                  "gam report login user <email>", "gam report useraccounts user <email>",
                  "gam report token user <email>"],
        keywords="history why can't sign in what happened audit"),
    "Account time machine": dict(
        what="Every night GAMbit saves each account's org unit, status, aliases, licenses and "
             "groups. See what an account looked like on any day and put it back.",
        steps=["Pick the person and a night.",
               "**Compare with last night** (or another day) shows the differences.",
               "**Day-by-day history** lists every change.",
               "**Put the account back to that day** builds the commands to restore it."],
        tips=["Turn on *Every night…* – history starts from the first snapshot (kept 90 "
              "days)."],
        keywords="restore snapshot history before changed put back"),
}
