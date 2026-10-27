"""Guide entries for the round 25 pages."""

PAGES = {
    "Custom field check": dict(
        what="Keep custom fields (grade, school, student ID, graduation year…) right: compare "
             "them with the org unit map, and fill them from your roster (SIS).",
        steps=["**Field vs org unit**: pick the custom field that holds the grade and the one "
               "that holds the school, then **Check**. Each mismatch shows what the field "
               "says, what the org unit says, and the org unit the field points at.",
               "Select rows and **Move selected students to the field's org unit**, or "
               "**Correct the field to match the org unit** (grades are written the way you "
               "pick: 7th Grade, 7, Grade 7…).",
               "**Fill from the SIS**: pick a saved roster sync, **Read its columns**, choose "
               "which roster column goes into which custom field, then **Preview changes** "
               "and **Apply selected**.",
               "**Schedule the background task** keeps the fields in step each night. It "
               "stops (and alerts you) if far more people would change than the limit."],
        tabs={"Field vs org unit": "Custom fields compared with the org unit map, with "
                                   "move-or-correct fixes.",
              "Fill from the SIS": "Copy roster columns into custom fields, now or nightly."},
        commands=["gam print users query \"orgUnitPath='/Students'\" fields … custom <schema>",
                  "gam update user <email> ou <org unit>",
                  "gam update user <email> Student_Information.Grade \"7th Grade\""]),
    "Senior checkout": dict(
        what="End of year for a graduating class: Takeout reminder, Chromebook collection, "
             "move to the graduates org unit, then suspend and free licenses on later dates.",
        steps=["Pick the graduation-year custom field and the year (or the seniors' org "
               "unit), then **Find the class** – it also finds each senior's Chromebook.",
               "Tick the checklist items and dates. Select some rows to do only those "
               "students; otherwise the whole class.",
               "**Review & run the checklist**: emails and Chromebook notes run now (or go "
               "for approval); the move, suspension and license removal are queued on "
               "Automation → Run later & freezes, where they can be reviewed or cancelled.",
               "The Chromebook collection appears on Chromebook fleet → Collections for "
               "scanning returns."],
        commands=["gam sendemail <senior> subject … message …",
                  "gam cros_sn <serial> update notes \"Collect – Class of 2026\"",
                  "gam update user <email> ou /Graduates", "gam update user <email> "
                  "suspended on", "gam user <email> delete license <SKU>"]),
    "Chromebook sharing": dict(
        what="Finds swaps and sharing from the last few people who signed in to each "
             "Chromebook: students on several Chromebooks, Chromebooks used by many students, "
             "and Chromebooks assigned to one student but used by another.",
        steps=["Optionally pick an org unit, how many recent users to look at and what "
               "counts as “many”, then **Find sharing**. Carts, loaners, labs and libraries "
               "are left out.",
               "For “Used by someone else” rows, **Make the last user the assigned user** "
               "fixes the assignment.",
               "**Open device history for the selected student** shows the full story."],
        commands=["gam print cros fields deviceid,serialnumber,annotateduser,recentusers,… "
                  "listlimit 5", "gam cros_sn <serial> update user <email>"]),
    "Device history": dict(
        what="Every Chromebook a student has had – or every student a Chromebook has had – "
             "with loaners, repairs and GAMbit's changes, for damage fees and parent calls.",
        steps=["Type a student's email, a serial number or an asset ID and **Show history**.",
               "History builds up each time GAMbit reads the fleet (Chromebook fleet → Load "
               "Chromebooks, Chromebook sharing, or **Read the fleet now**). It records who "
               "each Chromebook was assigned to, who used it and its org unit.",
               "Loaners and repairs come from Chromebook fleet; changes from the Activity "
               "log. Export CSV or Google Sheet to share."],
        commands=["gam print cros fields …,recentusers listlimit 5"]),
    "Windows, Mac & phones": dict(
        what="Devices in Google endpoint management – staff Windows laptops, Macs, iPads and "
             "phones – with their users.",
        steps=["Pick the type and ownership (company or personal), optionally search "
               "(serial:…, user:…) or only devices not seen for N days, then **List "
               "devices**.",
               "Select rows to approve or block a person on a device, wipe the school account "
               "from it, wipe the whole device (company devices), cancel a wipe or delete "
               "it. Everything asks first and follows approvals."],
        commands=["gam print devices query type:windows fields … oneuserperrow",
                  "gam approve|block|wipe deviceuser devices/<id>/deviceUsers/<id> doit",
                  "gam wipe device devices/<id> doit"]),
    "Shared drives by school": dict(
        what="Shared drives by org unit, and the checks that matter: drives with no manager, "
             "members outside the district, and anyone-with-the-link sharing.",
        steps=["Pick a school's org unit and **Drives in this org unit**, or run a check "
               "(blank org unit = every drive).",
               "Select drives, then **Move selected** to another org unit or **Add manager "
               "to selected**. These use GAMbit's admin account (Settings → Google Sheets and "
               "email)."],
        commands=["gam print oushareddrives ou <org unit>",
                  "gam print shareddriveorganizers shownorganizerdrives only",
                  "gam print shareddriveacls pm notdomainlist <domain> em",
                  "gam user <admin> update shareddrive <id> adminaccess ou <org unit>"]),
    "Chat posts": dict(
        what="Post an announcement into Google Chat spaces, or read a space's messages for "
             "an investigation.",
        steps=["Choose who to post or read as (the posts come from them), then **Load their "
               "spaces**.",
               "Select spaces, type the message and **Post to selected spaces**.",
               "To read, select one space, pick the dates and **Read selected space**."],
        commands=["gam user <email> print chatspaces types space",
                  "gam user <email> create chatmessage spaces/<id> text \"…\"",
                  "gam user <email> print chatmessages spaces/<id> range <start> <end>"]),
    "Staff calendar status": dict(
        what="Out-of-office, focus time or working location for many staff at once.",
        steps=["Choose who: people, org units (a building) or a group.",
               "Pick the status, the days (or part of one day), a title, and how to answer "
               "invitations, then **Set it**.",
               "**Show what's set** lists it for the first org unit / group; **Remove for "
               "these days** takes it off."],
        commands=["gam ou <org unit> create outofoffice range <d1> <d2> declinemode new …",
                  "gam group <email> create workinglocation office \"Central Office\" range …",
                  "gam ou <org unit> delete outofoffice range <d1> <d2>"]),
    "Single sign-on": dict(
        what="Which org units and groups sign in through ClassLink, Clever or another SAML "
             "or OIDC provider, and which use Google passwords.",
        steps=["**Load assignments and profiles** shows the current setup.",
               "Pick an org unit (or type a group and its rank), choose how they sign in – a "
               "provider profile, Google passwords (SSO off) or the domain-wide setting – "
               "and **Set it**. GAMbit updates an existing assignment or creates one.",
               "**Remove this assignment** makes the org unit follow the one above it again."],
        commands=["gam print inboundssoassignments", "gam print inboundssoprofiles",
                  "gam create inboundssoassignment orgunit <ou> mode saml_sso profile <id>",
                  "gam update inboundssoassignment <name> mode sso_off"]),
    "Domain & extras": dict(
        what="Smaller things GAM can do: domain aliases, contact delegates, Google Tasks, "
             "Chrome browser profiles and browser enrollment tokens.",
        steps=["Each tab lists first, then acts on what you select.",
               "Changes ask first and follow approvals."],
        tabs={"Domain aliases": "List, add and remove domain aliases.",
              "Contact delegates": "Who can manage a person's contacts; add or remove.",
              "Google Tasks": "A person's task lists and tasks, for records or offboarding.",
              "Chrome browser profiles": "Managed Chrome profiles on Windows/Mac; remove "
                                         "inactive ones.",
              "Browser enrollment tokens": "Create, list and revoke tokens that enroll Chrome "
                                           "browsers into an org unit."},
        commands=["gam print domainaliases", "gam user <email> print contactdelegates",
                  "gam user <email> print tasks", "gam print chromeprofiles",
                  "gam create browsertoken ou <org unit>"]),
    "Clean-up by school": dict(
        what="One to-do list per building, each row with a fix: idle and never-used "
             "accounts, suspended accounts still in school org units, Chromebooks not seen "
             "for weeks, and Chromebooks assigned to suspended or deleted accounts.",
        steps=["Set how many days count as idle, then **Build the lists**. Schools come from "
               "Settings → Org units & schools.",
               "Pick a school to see only its list; **By school** has the counts.",
               "Select rows and **Fix selected** (suspend, move to the former org unit, note "
               "or move unseen Chromebooks, clear assigned users).",
               "Type each school's tech below and **Email each school its list**."],
        commands=["gam print users fields …,lastlogintime,creationtime",
                  "gam print cros fields …,lastsync", "gam update user <email> suspended on"]),
}
