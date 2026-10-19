"""Guide: Devices and Services pages."""

PAGES = {
    "Chromebooks": dict(
        what="Find one Chromebook (or many) by serial, user or asset tag and act on it: "
             "move, disable, re-enable, reboot, wipe users, powerwash, deprovision.",
        steps=["**One device**: type the serial and **Show info**. Change the org unit, "
               "asset ID, location, user or notes and **Save details**.",
               "**Last signed-in user** shows who used it last and when it last synced.",
               "**Find / list devices**: search by org unit, text or 'not synced in 30 "
               "days', then *Use selected serials ↑*.",
               "**Send a command**: reboot, wipe users or powerwash one device, a list of "
               "serials or a whole org unit (a cart, a classroom)."],
        tips=["**Disable** shows your 'return to' message; **Re-enable** undoes it.",
              "Deprovision removes the device from management – only for devices leaving the "
              "district."],
        commands=["gam cros_sn <serial> print cros", "gam cros_sn <serial> update ou <ou>",
                  "gam cros_sn <serial> update action disable|reenable",
                  "gam cros_sn <serial> issuecommand command reboot|wipe_users|"
                  "remote_powerwash"],
        keywords="chromebook serial disable reenable reboot powerwash wipe move asset"),
    "Chromebook fleet": dict(
        what="Everything for the whole fleet: carts and classrooms, bulk updates, summer "
             "collection, end-of-updates planning, loaners, repairs, labels, health, apps, "
             "printers, OS versions, assignment sync, assigned users, withdrawn students' devices, device "
             "history, lost & stolen, and redistribution.",
        steps=["Click **Load Chromebooks** once; most tabs use that list.",
               "Pick the tab for the job – each tab starts with a short explanation."],
        tabs={
            "Carts & classrooms": "Devices per location or org unit: active, disabled, not "
                                  "seen in N days, missing, and short of the expected count "
                                  "(*How many should each cart have?…*).",
            "Bulk update from a spreadsheet": "Serial plus asset tag, location, user, notes "
                                              "and org unit; *Preview* shows only what "
                                              "changes.",
            "Summer collection": "Scan serials or asset tags as devices come back; several "
                                 "people can scan at once. *Not returned* lists who still "
                                 "has one, and can email them.",
            "End of updates planning": "Active devices by the school year their updates end, "
                                       "with replacement cost.",
            "Loaners": "Scan to check out (sets the due date) and check in. Overdue "
                       "reminders now or every morning.",
            "Repairs": "Repair tickets with status history; the device's notes show IN "
                       "REPAIR. Can open help-desk tickets.",
            "Labels": "Print asset labels with Code 39 barcodes.",
            "Assigned users": "Blank the Assigned user field (all Chromebooks, org units, "
                              "serials or asset IDs), or set it to the person who last "
                              "signed in. *Preview* shows the plan; filters keep teachers "
                              "and technicians out (students only, ignore list, last used "
                              "within N days, only fill blanks). Old values are saved "
                              "first and *Undo last change* restores them. *Move it to the "
                              "student's school org unit*: a student in /Students/Hancock "
                              "High School/9th Grade signs in → the Chromebook moves to "
                              "/Chromebooks/Hancock High School (school level and device "
                              "org unit pattern are settings). *Don't move* protects loaner, "
                              "repair and lost org units; *Every morning…* runs it daily. "
                              "*Blank it when nobody is using the Chromebook*: blanks the "
                              "assigned user after N days without use. *Every morning "
                              "(5:45 AM)* can blank unused ones and set the rest from the "
                              "student who last signed in, every day.",
            "Lost & stolen": "Look up the serial, then *Mark it*: disables the device, notes "
                             "it, can move it to a lost org unit, opens a ticket and writes a "
                             "one-page report for police or insurance. *It's been found* "
                             "undoes it.",
            "Redistribution": "Finds unused Chromebooks at schools with more than they need "
                              "and suggests moves to schools that are short.",
        },
        commands=["gam print cros fields …", "gam cros_sn <serial> update location|"
                  "assetid|notes|user …", "gam print crosactivity …",
                  "gam print crostelemetry …"],
        keywords="fleet inventory cart loaner repair label collection aue health printers "
                 "extensions lost stolen redistribute"),
    "Staff devices": dict(
        what="Windows laptops, Macs, iPhones and Android phones signed in to district "
             "accounts (Google endpoint management), plus managed Chrome browsers.",
        steps=["**Load devices** (tick *Include Chromebooks* if you want them too).",
               "Select devices, pick an action (approve, block, remove the district account, "
               "factory reset company-owned devices…) and **Do it**.",
               "*Chrome profiles on computers…* lists managed Chrome profiles.",
               "*Out-of-date Chrome…* lists profiles behind Google's newest stable release "
               "and can clear their cache or cookies remotely."],
        commands=["gam print devices", "gam update deviceuser … action approve|block|"
                  "wipe", "gam print chromeprofiles", "gam print chromehistory versions …",
                  "gam create chromeprofilecommand …"],
        keywords="phone laptop mac windows mobile approve block wipe endpoint chrome browser"),
    "Email": dict(
        what="Gmail settings for one person or many: out-of-office, signatures, forwarding, "
             "mailbox access, finding and removing messages, filters, IMAP/POP, sending "
             "email, send-as, archiving to a group, restoring deleted mail, labels and "
             "S/MIME.",
        steps=["Pick who it applies to – a person, several people, an org unit, a group or "
               "everyone.",
               "Choose the tab, fill in the settings and click the action button.",
               "Use *Show current…* buttons to check before changing."],
        tabs={
            "Out of office": "Auto-replies on or off with start and end dates.",
            "Signatures": "An HTML editor with live preview; tags like {FirstName}, {Title}, "
                          "{WorkPhone} are filled in per person. *Re-apply every week…* "
                          "keeps them consistent.",
            "Forwarding": "Turn forwarding on or off and choose what happens to the copy.",
            "Mailbox access": "Give or remove delegate access; list current delegates.",
            "Find & remove messages": "Search by subject, sender, Message-ID or any Gmail "
                                      "search; *Preview matches* first; then trash or "
                                      "permanently delete, with a per-mailbox limit.",
            "Filters, IMAP & POP": "Show and delete filters; check, enable or disable IMAP "
                                   "and POP.",
            "Send email": "Send to people or groups with Cc/Bcc, HTML and attachments.",
        },
        tips=["Removing messages can be undone for 25 days from *Restore deleted mail*."],
        commands=["gam user <email> vacation on|off …", "gam user <email> signature …",
                  "gam user <email> forward on|off …", "gam user <email> add delegate …",
                  "gam user <email> delete messages query … doit", "gam sendemail …"],
        keywords="gmail out of office vacation signature forwarding delegate phishing "
                 "filters imap pop send as labels smime"),
    "Google Drive": dict(
        what="Hand off a departing person's files, audit and fix sharing, manage shared "
             "drives, check storage, restore files and more.",
        steps=["**Transfer files**: pick the old and new owner, **Start transfer…**, then "
               "*Check transfer status*.",
               "**A person's files & sharing**: search one person's files – all, shared with "
               "anyone with the link, shared outside, by name, recently changed.",
               "**Shared drives**: list, create, see members, add people or groups, change "
               "access.",
               "**Fix sharing**: *Find risky sharing* across people or org units, then fix "
               "in bulk."],
        tabs={
            "Storage & trash": "Storage used per person; empty someone's Drive trash.",
            "Orphaned files": "Files not in any folder – collect them into one folder before "
                              "a transfer.",
            "Labels": "Apply a Drive label to files in bulk.",
            "Move & copy folders": "Move a My Drive folder into a shared drive, or copy a "
                                   "folder tree.",
            "Keep notes": "List a person's Keep notes and share them.",
            "Restore files": "Bring back trashed files or an earlier version.",
            "Sharing exposure": "Per person and per school: files public, shared with anyone "
                                "with the link, or shared outside.",
            "Shared drive settings": "Move shared drives into org units (one by one or by "
                                     "name rules) and set themes.",
            "Empty folders": "Find and delete someone's empty folders.",
        },
        commands=["gam create datatransfer <old> gdrive <new>", "gam user <email> print "
                  "filelist …", "gam create shareddrive …", "gam user <email> add "
                  "drivefileacl …", "gam user <email> print filesharecounts"],
        keywords="drive files transfer sharing shared drive storage trash restore orphaned "
                 "labels"),
    "More services": dict(
        what="Everything else Google offers: Calendar and rooms, Vault, Chrome browser "
             "management, admin roles, mobile devices, Alert Center, custom fields, the "
             "directory, shared contacts, domains, Chat and Meet.",
        steps=["Pick the tab. Each tab has its common actions plus *All related commands in "
               "the Command Builder →* for anything else."],
        tabs={
            "Calendar": "Rooms and resources, buildings, calendar sharing; add an event or "
                        "calendar to many people; cancel a leaver's future meetings.",
            "Vault": "Matters, holds, exports and downloads (Records requests does this "
                     "end to end).",
            "Chrome": "Managed browsers, enrollment tokens, end-of-updates and "
                      "needs-attention counts.",
            "Admin roles": "Who has which admin role; assign or remove roles.",
            "Mobile devices": "Approve, block, account-wipe or factory-reset phones.",
            "Alerts": "Google Alert Center – list, details, delete, and tell Google whether "
                      "an alert was useful.",
            "Custom fields": "Create schemas (e.g. Student ID) and set values.",
            "Calendar sharing & out of office": "Find calendars shared publicly or outside "
                                                "the district and stop sharing; add out-of-"
                                                "office that declines meetings.",
        },
        commands=["gam print resources", "gam calendars <cal> print acls",
                  "gam create vaultmatter …", "gam print admins", "gam print alerts",
                  "gam print mobile"],
        keywords="calendar rooms resources vault admin roles alerts mobile schema chat meet "
                 "contacts domains"),
}
