"""Guide: Admin pages."""

PAGES = {
    "Org units": dict(
        what="The org unit tree: create, rename, move, describe and delete org units, and "
             "see what's in them.",
        steps=["Click an org unit in the tree (type in the filter box to find it).",
               "*Count what's in it*, *List its users* or *List its Chromebooks*.",
               "Create a child org unit, rename, move or delete on the right.",
               "*People per org unit…* shows active, suspended and total accounts for every "
               "org unit at once."],
        tips=["An org unit must be empty before it can be deleted."],
        commands=["gam print ous", "gam create org <path>", "gam update org <path> name "
                  "…", "gam print usercountsbyorgunit"],
        keywords="org unit ou folder tree create rename move delete count"),
    "Licenses": dict(
        what="How many licenses you have, who has them, and assigning or removing them.",
        steps=["**License totals** shows each product and how many are used.",
               "**Who has this license** lists holders.",
               "Pick people, an org unit, a group or everyone and **Assign license** or "
               "**Remove license**."],
        commands=["gam print licenses", "gam user <email> add license <sku>"],
        keywords="license sku education plus assign remove"),
    "Budget planner": dict(
        what="Money you could save or need to plan: licenses on suspended, inactive or "
             "never-used accounts, Chromebook replacements by school and year, and repair "
             "and loaner trends.",
        steps=["**Licenses**: *Load licenses*, then *Release selected licenses (send for "
               "approval)*.",
               "**Chromebook replacements**: *Load Chromebooks* to see devices whose updates "
               "end each school year, with cost.",
               "**Repairs & loaners**: which models and schools break most and how many "
               "loaners each school needs."],
        keywords="budget cost license replace chromebook repair money"),
    "Policies by org unit": dict(
        what="Compare Chrome and Workspace settings across org units, change or copy "
             "policies, clean up redundant overrides and set wallpapers.",
        steps=["Choose two or more org units and what to show, then **Compare** – settings "
               "that differ come first.",
               "*Change or copy policies…* edits a Chrome policy or copies one org unit's "
               "policies to another.",
               "*Clean up overrides…* finds policies set on an org unit with the same value "
               "as its parent and removes them.",
               "*Wallpaper & picture…* uploads an image and sets it as the wallpaper, sign-in "
               "screen or account picture for an org unit."],
        commands=["gam print chromepolicies ou <ou> show all", "gam print policies",
                  "gam update chromepolicy … ou <ou>", "gam delete chromepolicy … ou <ou>",
                  "gam create chromepolicyimage …"],
        keywords="policy chrome settings compare copy wallpaper override inheritance"),
    "Policy rollouts": dict(
        what="Testing-season settings, staged rollouts of Chrome policy changes and "
             "testing-day device checks – everything saved first so it can be put back.",
        steps=["**Testing mode**: *New testing window…* – pick a template org unit and the "
               "org units to switch, with start and end dates. GAMbit applies and puts back "
               "the settings automatically.",
               "**Staged rollouts**: *New rollout…* – try policies on a pilot org unit, "
               "*Check the pilot now* (tickets and devices), then *Roll out to everyone* or "
               "*Roll back*.",
               "**Device readiness**: days before testing, *Check now* lists Chromebooks "
               "that aren't enrolled, are behind on ChromeOS, haven't checked in, are past "
               "end of updates or lack the testing app. *Restart selected* installs waiting "
               "updates; *Email the list* to test coordinators."],
        keywords="testing state test lockdown kiosk pilot rollout rollback readiness"),
    "2-Step Verification": dict(
        what="Get staff onto 2-Step Verification building by building: progress, reminder "
             "emails with a deadline, escalation to principals.",
        steps=["**Load progress** to see enrollment by building.",
               "Set the deadline and message, then **Send reminders now** or *Every "
               "Monday…*.",
               "When a building is ready, *Open enforcement settings* to enforce it in the "
               "Admin console."],
        keywords="2sv mfa two step verification campaign enforce"),
    "Ownership check": dict(
        what="Groups with no owner, shared drives with no manager, classes owned by someone "
             "who left, and suspended accounts still holding Drive files.",
        steps=["**Check now**.",
               "Choose who takes over (*Change who gets it…*) and **Hand off selected**."],
        keywords="orphaned owner manager shared drive group class hand off"),
    "Security baseline": dict(
        what="Your Google settings scored against a K-12 baseline for each org unit, with a "
             "fix list.",
        steps=["Pick the student, staff and Chromebook org units, then **Check now**.",
               "Chrome items: *Fix selected (Chrome)* (or send for approval).",
               "Admin console items: *Open the Admin console page* – Google doesn't let "
               "apps change these.",
               "*Don't check this* for rules that don't fit your district; *Every Monday…* "
               "alerts you if the score drops."],
        keywords="security baseline score cipa safesearch youtube incognito guest sharing"),
    "Records requests": dict(
        what="FERPA, legal-hold, public-records and HR requests: Vault matter, hold and "
             "exports, deadlines and delivery.",
        steps=["**New request…**: whose records, the kind (the due date is set for you), "
               "who asked, what to include, and whether to place a hold.",
               "**Start (matter, hold, exports)**.",
               "**Check exports** until they're finished (can take hours), then "
               "**Download…**.",
               "**Mark delivered**, and **Close the matter** when done."],
        tips=["The daily task alerts you about requests due within 7 days."],
        commands=["gam create vaultmatter …", "gam create vaulthold …",
                  "gam create vaultexport …", "gam download vaultexport …"],
        keywords="ferpa records request legal hold vault export subpoena public records "
                 "foia ediscovery"),
    "Access review": dict(
        what="A quarterly review of every Google admin role: 2SV, last sign-in and admin "
             "actions in 90 days, with flags for leavers and risky super admins.",
        steps=["**Load admins**.",
               "Mark each role **Keep** or **Remove** (flagged ones start as Remove).",
               "**Sign off the review…** – it's saved for audits, and removals go through "
               "Approvals.",
               "Fill in *Remind* to get a quarterly reminder; *Past reviews* shows history."],
        commands=["gam print admins", "gam report admin user all start -90d",
                  "gam delete admin <id>"],
        keywords="admin access review audit quarterly roles super admin insurance"),
}
