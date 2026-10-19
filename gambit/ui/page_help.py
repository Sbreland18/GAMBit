"""Short in-app help for each page: (what it's for, safe=True when "Try it safely"
makes sense – i.e. the page changes things in Google)."""

HELP = {
    "Staff card": ("One staff member's security and resources on one card.", False),
    "Back to school": ("August readiness by school, with a button to fix each gap.", False),
    "Changes outside GAMbit": ("Admin-log changes that weren't made through GAMbit.", False),
    "Account recovery": ("Staff with no recovery phone or email, and a reminder email.", True),
    "Mailbox access review": ("Delegates, send-as and calendar editors – review and sign "
                              "off each quarter.", True),
    "Meet attendance": ("Who joined a teacher's Meet on an e-learning day, against the "
                        "class roster.", False),
    "AI use": ("Gemini use by school, grade and week, and use outside your AI policy.",
               False),
    "Directory quality": ("Missing directory details by school, and likely duplicate "
                          "accounts.", False),
    "Cost per student": ("Chromebook, license and repair cost per student by school.", False),
    "Guide": ("What every page does and how to use it, plus the GAM command reference. "
              "Press F1 on any page to jump here.", False),
    "Workflows": ("Step-by-step jobs that do several things at once – new staff, staff "
                  "leaving, graduation. Each step is shown before anything runs.", True),
    "Users": ("Find a person, then reset their password, change details, suspend or move "
              "them. Double-click a row to open the person.", True),
    "Student lookup": ("Type part of a name or ID to see a student's account, Chromebook, "
                       "classes and guardians on one card.", False),
    "Groups": ("Look up a group, see and change its members and settings. Automatic groups "
               "keep members in step with rules you set.", True),
    "Classroom": ("Courses, teachers and students, plus the yearly clean-up and guardian "
                  "sync.", True),
    "Roster sync": ("Compare your SIS or HR sheet with Google and create, update or move "
                    "accounts to match. Always preview first.", True),
    "Account timeline": ("Everything that happened to one account – logins, changes, "
                         "GAMbit actions – in date order.", False),
    "Chromebooks": ("Find a Chromebook by serial, user or asset tag; move, disable or "
                    "re-enable it.", True),
    "Chromebook fleet": ("Inventory, collection days, loaners, repairs and asset labels "
                         "for the whole fleet.", True),
    "Email": ("Out-of-office, signatures, delegates, forwarding and filters for one person "
              "or many.", True),
    "Google Drive": ("Search files, change sharing, transfer ownership and manage shared "
                     "drives.", True),
    "More services": ("Calendars, rooms and resources, Vault and other Google services.",
                      True),
    "Org units": ("The folder tree that controls policies. Create, rename and move org "
                  "units here.", True),
    "Licenses": ("See who holds which Google license, and assign or release them.", True),
    "Policies by org unit": ("Which Chrome and account policies apply at each org unit – "
                             "read only.", False),
    "Reports": ("Ready-made reports you can sort, filter, save as CSV or send to a Google "
                "Sheet.", False),
    "Security reports": ("Audit and privacy reports – 2-step verification, outside sharing, "
                         "apps, storage. Each can be emailed monthly.", False),
    "Activity log": ("Every change made through GAMbit, who made it, and an Undo button "
                     "where one is possible.", False),
    "Approvals": ("Requests waiting for an admin – risky changes, leavers from roster sync "
                  "and staff request forms.", False),
    "Investigations": ("Search Google's audit logs (who opened or shared a file, sign-ins, "
                       "admin changes), Meet usage, and apps with access to accounts.", True),
    "Usage": ("How much Gmail, Drive, Classroom and Meet are used – district trend, by school "
              "and per teacher.", False),
    "Staff devices": ("Laptops and phones signed in to district accounts: approve, block, or "
                      "remove the district account.", True),
    "Settings watch": ("Nightly copies of your Admin console and Chrome settings – compare "
                       "any two days and get an alert when something changes.", False),
    "Ask GAMbit": ("Describe a job in plain English; Claude suggests GAM commands, drafts a "
                   "workflow or rule – or search the logs for what happened.", True),
    "Policy rollouts": ("Testing-season mode and staged Chrome policy rollouts – everything "
                        "is saved first so it can be put back.", False),
    "2-Step Verification": ("Get staff onto 2-Step Verification building by building.", False),
    "Ownership check": ("Groups, shared drives and classes nobody owns any more – hand them "
                        "off.", False),
    "Access review": ("Quarterly review of every Google admin role, with sign-off.", False),
    "Account timing": ("How long new accounts take to sign in, leavers take to be "
                       "suspended, and approvals take.", False),
    "Storage forecast": ("When pooled storage runs out, by school, and what leavers hold.",
                         False),
    "Students going quiet": ("A weekly counselor list from sign-ins, Classroom and "
                             "Chromebooks.", False),
    "Stale content": ("Old shared drives, quiet classes and empty groups to clean up.", False),
    "Security baseline": ("Your Google settings scored against a K-12 baseline, per org "
                          "unit, with a fix list.", False),
    "Records requests": ("FERPA, legal-hold and public-records requests: Vault matter, hold "
                         "and export, with deadlines.", False),
    "Run later & freezes": ("Changes queued for tonight, change freezes during testing, and "
                            "the request form for principals.", False),
    "Account time machine": ("What an account looked like on any night, and putting it "
                             "back.", False),
    "Teacher lists": ("Each teacher gets only their own students who need a nudge, from the "
                      "Classroom rosters.", False),
    "Audit report": ("A monthly report of changes, approvals, settings and unusual activity "
                     "for your director or board.", False),
    "Mismatch report": ("Roster, Google accounts and Chromebook assignments compared – fix "
                        "what's out of step, or send it for approval.", False),
    "Budget planner": ("Licenses you could free and what they cost, and Chromebook "
                       "replacements by school and year.", False),
    "School reports": ("A weekly email to each principal with only their school's "
                       "numbers.", False),
    "Ticket queue": ("Open help-desk tickets; “Work on it” opens the right screen and notes "
                     "what you did. Password tickets can be handled end to end.", False),
    "Clean-up rules": ("Rules that find inactive or old accounts and unused licenses – "
                       "findings always go to Approvals first.", False),
    "Scheduled jobs": ("Reports and commands Windows runs for you on a schedule.", False),
    "Background tasks": ("Whether GAMbit's automatic tasks are set up and when each last "
                         "ran OK.", False),
    "Command Builder": ("Build any GAM command by picking options – no typing needed.",
                        True),
    "Bulk (CSV)": ("Run one command for every row of a spreadsheet. The first rows are "
                   "previewed before anything runs.", True),
    "Command Console": ("Type GAM commands directly, for experienced users.", True),
    "Diagnostics": ("Checks GAM, sign-in and permissions, and points at what to fix.",
                    False),
    "Live test": ("A checklist that proves GAMbit works with your domain using a test "
                  "account.", False),
    "Settings & Updates": ("GAM location, team folder, Google Sheets and email, safety "
                           "options and updates.", False),
}


def for_page(title: str):
    return HELP.get(title)
