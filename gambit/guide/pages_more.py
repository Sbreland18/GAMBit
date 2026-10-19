"""Guide: pages added later (Meet attendance, AI use, directory quality, cost per student)
and extra tab notes for existing pages (merged into their entries)."""

PAGES = {
    "Meet attendance": dict(
        what="For e-learning days: who joined a teacher's Google Meet and for how long, "
             "compared with the Classroom roster, plus the meeting's recordings and "
             "transcripts.",
        steps=["Choose the teacher and the day, then **Load classes and meetings**.",
               "Pick the class and the meeting (busiest first), set how many minutes count "
               "as present, and **Take attendance**.",
               "Students are listed as Present, Partial, Absent or Not on the roster. Fill in "
               "the attendance office's address and **Email it**.",
               "*Show recordings and transcripts* lists the files Meet saved."],
        tips=["Google's Meet log can take a few hours to fill in after a meeting."],
        commands=["gam report meet user all events call_ended filter organizer_email==…",
                  "gam print course-participants course <id>",
                  "gam user <teacher> print meetconferences code <code>",
                  "gam user <teacher> print meetrecordings <conference>"],
        keywords="e-learning snow day virtual attendance meet roster recording transcript"),
    "AI use": dict(
        what="Gemini use from Google's audit log – by school, grade and week, what it's "
             "used for, and use from org units where your AI policy doesn't allow it.",
        steps=["Choose how many days and the student org unit.",
               "List the org units where AI isn't allowed (comma separated).",
               "**Build** – the tabs show By school and grade, By week, What it's used for and "
               "Outside the policy."],
        commands=["gam report gemini user all start …"],
        keywords="ai gemini artificial intelligence policy chatbot usage"),
    "Directory quality": dict(
        what="How complete your directory is, school by school, and accounts that look like "
             "duplicates.",
        steps=["Choose the staff and student org units and which staff fields are required.",
               "**Check** – Score by school, What's missing and Possible duplicates.",
               "Fix gaps from your HR sheet on Users → Directory details."],
        commands=["gam print users fields primaryemail,name,ou,organizations,phones,"
                  "relations,externalids"],
        keywords="directory missing title department manager phone id duplicate data "
                 "quality"),
    "Cost per student": dict(
        what="Chromebooks (spread over their life), licenses and repairs per student, school "
             "by school – for budget season.",
        steps=["Set the Chromebook price, life in years and average repair cost (license "
               "prices come from Budget planner → Licenses).",
               "Choose where Chromebooks and students are, then **Calculate**."],
        keywords="cost per student budget tco total cost chromebook license repair"),
}

# extra tab descriptions merged into existing pages' entries
TABS = {
    "Users": {"Photo export": "Save everyone's profile photo as <email>.jpg for an ID-card, "
                              "library or yearbook system."},
    "Classroom": {"Teacher status": "Which teachers are verified and can create classes; "
                                    "classes per teacher or student.",
                  "Guardian follow-up": "Re-send unanswered guardian invitations, cancel ones "
                                        "to mistyped addresses, acceptance by school and "
                                        "teacher; can run every Monday."},
    "Chromebook fleet": {"Battery forecast": "Predicts when each battery drops below your "
                                             "replacement level and builds an order list by "
                                             "school and model.",
                         "Repeat damage": "Students with several damage repairs over the "
                                          "years.",
                         "Device tools": "Check serial numbers before devices arrive, active "
                                         "device counts, app/extension details, download a "
                                         "device's log files, printer models."},
    "Email": {"Gmail language": "Set Gmail's menu language for a person or an org unit."},
    "Google Drive": {"Folder tools": "Hand one folder or file to someone else (transfer or "
                                     "claim), see its path, read its comments, its size, and "
                                     "find broken shortcuts."},
    "More services": {"Form responses": "Read a Google Form's responses without a linked "
                                        "Sheet.",
                      "Trusted domains": "Domains your users may share with and join classes "
                                         "from (allowlisted domains).",
                      "Chat moderation": "Every Chat space as an admin: members, outsiders, "
                                         "remove someone, delete a space."},
    "Budget planner": {"Premium licenses": "Teaching and Learning / Education Plus holders "
                                           "who haven't used a premium feature – release "
                                           "through Approvals."},
    "Investigations": {"Public apps list": "A parent-facing list of apps used with student "
                                           "accounts and their privacy-agreement status, as "
                                           "a web page or Google Sheet.",
                       "Shared passwords": "Student accounts signed in on many Chromebooks "
                                           "or from different places minutes apart."},
}


PAGES.update({
    "Staff card": dict(
        what="One staff member's security and resources on one screen: 2-Step Verification, "
             "admin roles, recovery options, storage, outside sharing, devices, licenses and "
             "premium use, app passwords, mailbox delegates, forwarding and connected apps.",
        steps=["Choose the staff member and **Show card**.",
               "Rows marked high or medium are worth fixing; tick *Include file sharing "
               "counts* for the outside-sharing row (slower)."],
        commands=["gam print admins user <email>", "gam user <email> print delegates",
                  "gam user <email> print asps", "gam user <email> print forward"],
        keywords="staff card security profile teacher employee account summary"),
    "Back to school": dict(
        what="August readiness by school: students signed in, Chromebooks assigned, "
             "guardians invited, Classroom teachers verified and this year's classes created.",
        steps=["Choose where students and staff are and the goal percentage.",
               "**Check readiness** – *Needs work* lists what is below the goal.",
               "Use the *Fix:* buttons to open the screen that fixes each one."],
        commands=["gam print courses states active,provisioned aliases",
                  "gam ou_and_children /Staff print classroomprofile"],
        keywords="back to school august readiness start of year checklist"),
    "Changes outside GAMbit": dict(
        what="Changes in Google's admin log that weren't made through GAMbit – Admin console "
             "clicks, other tools, or someone who shouldn't be making changes.",
        steps=["Choose how many days back; list accounts and events to ignore (an SIS "
               "sync account, for example).",
               "**Compare** – *Changes* lists each one, *By person* totals them."],
        tips=["Changes match when GAMbit's activity log has the same target within 15 "
              "minutes; turn on the team folder so teammates' GAMbit changes count too."],
        commands=["gam report admin user all start -7d"],
        keywords="outside console changes audit admin log unexpected who changed"),
    "Account recovery": dict(
        what="Staff with no recovery phone or email, by building, plus a reminder email "
             "pointing them to their Google Account recovery page.",
        steps=["Choose the org unit and **Check**.",
               "Edit the reminder if you like, then **Email everyone missing it** (sent in "
               "batches as BCC)."],
        commands=["gam print users fields primaryemail,ou,recoveryemail,recoveryphone"],
        keywords="recovery phone email password reset self service forgot"),
    "Mailbox access review": dict(
        what="Who can read someone else's mail, send as them or change their calendar – "
             "flagging leavers, outsiders and people at another school – with a quarterly "
             "sign-off saved for audits.",
        steps=["Choose the mailboxes' org unit and the leavers' org unit, then **Load**.",
               "Mark rows Keep or Remove (flagged ones start as Remove).",
               "**Sign off the review** – removals run or go for approval."],
        commands=["gam ou_and_children /Staff print delegates",
                  "gam ou_and_children /Staff print sendas",
                  "gam ou_and_children /Staff print calendaracls primary noselfowner"],
        keywords="delegate delegation send as calendar access review mailbox audit"),
})

_NEW_TABS = {
    "Chromebook fleet": {"Asset register": "Compare the finance asset list with Google, fix "
                                           "asset tags and export an inventory with age, "
                                           "book value and end of updates."},
    "Budget planner": {"Next year": "Next year's enrollment by school (grade roll-up and "
                                    "feeder schools) and the Chromebooks and licenses "
                                    "you'll need."},
    "Groups": {"Group clean-up": "Suspended or former staff in groups, outsiders in staff "
                                 "groups, duplicate direct+nested members and staff in "
                                 "another school's group."},
    "More services": {"Room features": "Create room features (projector, doc camera…) and "
                                       "add them to rooms.",
                      "Working locations": "Set which building itinerant staff are in each "
                                           "weekday on their Google Calendar."},
}
for _p, _t in _NEW_TABS.items():
    TABS.setdefault(_p, {}).update(_t)
