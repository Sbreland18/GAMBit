"""Guide: Reports pages."""

PAGES = {
    "Reports": dict(
        what="Ready-made reports: inactive accounts, every Google audit log, Chromebooks "
             "reaching end of updates, and storage use.",
        steps=["**Inactive accounts**: choose days without sign-in and org units, *Find "
               "inactive accounts*, then *Suspend* or *Move to OU* the selected ones.",
               "**Activity logs**: pick a log (admin, sign-ins, Drive, app access, groups, "
               "Classroom, Chrome, account changes, Calendar, Chat, DLP, Gemini, Vault…), a "
               "person or everyone, and a date range, then *Show activity*.",
               "**Chromebook end of updates** and **Storage** are one-click lists."],
        tips=["Google keeps about six months of audit logs; usage numbers lag 2–3 days."],
        commands=["gam print users fields lastlogintime …", "gam report <log> user …",
                  "gam report users parameters accounts:used_quota_in_mb"],
        keywords="inactive audit log report storage end of updates activity"),
    "School reports": dict(
        what="A weekly email to each principal with only their school: students not "
             "signing in, missing guardians, Chromebooks in repair or past updates, Classroom "
             "use.",
        steps=["Set the student root and which principal gets which school.",
               "**Build the report**, then *Preview the email for the selected school*.",
               "**Send now** or *Every Monday…*."],
        keywords="principal school weekly email report"),
    "Teacher lists": dict(
        what="Each teacher gets only their own students who need a nudge: not signing in, no "
             "guardian, no Chromebook or an overdue loaner – from Classroom rosters.",
        steps=["**Build the lists**, preview a teacher's email, then **Send now** or *Every "
               "Monday…*."],
        keywords="teacher list students nudge email"),
    "Audit report": dict(
        what="One monthly report for your director or board: what changed and who approved "
             "it, settings changes, unusual activity and how it was handled.",
        steps=["**Build and open** to read it; **Email it now** or *Every month…*."],
        keywords="board director monthly audit report compliance"),
    "Students going quiet": dict(
        what="Students whose activity has dropped off across sign-ins, missing Classroom "
             "work and Chromebook use – a weekly list for each school's counselors.",
        steps=["Set the three signs (days without a sign-in, missing assignments, days since "
               "the Chromebook was used) and how many signs a student needs.",
               "Add each school's counselors (one school per line: *School = email, "
               "email*).",
               "**Find now**, then **Email counselors now** or *Every Monday…*."],
        tips=["Students new to the list each week are marked NEW."],
        keywords="counselor disengaged attendance missing work going quiet"),
    "Account timing": dict(
        what="How long the district takes: new account → first sign-in, leaving → "
             "suspended, and approvals.",
        steps=["Tick *Track first sign-ins every night* (Google only keeps the last sign-in, "
               "so tracking starts from then).",
               "Set the leavers' org units.",
               "**Refresh** – the tabs show New accounts, Leavers and Approvals & offboarding. "
               "The medians go on the scorecard."],
        keywords="timing sla first sign in leaver suspended approval turnaround"),
    "Storage forecast": dict(
        what="When the district's pooled storage runs out, which schools grow fastest and "
             "how much leavers hold.",
        steps=["Enter your pooled storage (e.g. 100 TB).",
               "**Measure now**, and tick *Add a data point every week*.",
               "After a few weeks the forecast date appears; History, By school and Biggest "
               "users tabs show the detail."],
        keywords="storage quota pooled full forecast growth"),
    "Security reports": dict(
        what="One-click reports for audits and privacy agreements: accounts without 2SV, "
             "files shared outside, apps on student accounts, admins, suspended accounts "
             "with licenses, storage.",
        steps=["Pick a report and **Run report**.",
               "*Email this every month…* sends it automatically."],
        keywords="security privacy audit 2sv sharing apps report monthly"),
    "Investigations": dict(
        what="Who opened, downloaded or shared a file; suspicious sign-ins; admin changes; "
             "Meet usage; connected apps; unusual activity overnight; phishing clean-up; "
             "approved apps; file activity; app passwords.",
        steps=["**Audit log**: pick a ready-made question (or choose the log), the person "
               "and dates, then **Search**.",
               "**Unusual activity**: set what counts as unusual and *Every night…*. Select "
               "a finding and **Respond…** for one-click responses (lock down, restore "
               "files, remove an app's access…)."],
        tabs={
            "Phishing clean-up": "Find which mailboxes got a phishing email, check *Who "
                                 "replied?*, then *Move every copy to the trash*.",
            "Approved apps": "Compare connected apps with your approved list; remove access "
                             "for students or everyone.",
            "File activity": "Paste a file link and the owner to see who edited, moved, "
                             "renamed, deleted or reshared it.",
            "App passwords": "Who has app passwords (they get around 2SV) – remove them.",
        },
        commands=["gam report drive …", "gam report login …", "gam all users print tokens",
                  "gam user <email> print driveactivity …", "gam print asps"],
        keywords="investigate audit phishing suspicious login download share apps oauth "
                 "unusual"),
    "Usage": dict(
        what="How much Google Workspace is used – district trend and by school and teacher.",
        steps=["Pick the tab and **Build**."],
        keywords="usage adoption active users gmail drive classroom"),
    "Settings watch": dict(
        what="A nightly copy of your Admin console and Chrome settings, so you can see "
             "exactly what changed and when, and get an alert.",
        steps=["*Take a snapshot now* (and turn on the nightly task).",
               "Pick two dates and **Compare**.",
               "*Propose putting back the compared changes* sends a fix for approval."],
        keywords="settings changed drift snapshot compare admin console"),
    "Activity log": dict(
        what="Every command GAMbit has run – who, when, result – with undo, run again, "
             "explain and search.",
        steps=["Search or filter, select a row.",
               "**Undo selected…**, **Run again**, **Explain** or **Copy command**.",
               "Paste a Google Sheet link and **Copy now** (or daily) to keep a shared copy."],
        keywords="history log undo who did what"),
}
