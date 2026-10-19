"""Guide: plain-English GAM command reference (the commands districts use most). The full
list of every GAM command comes from GAM's own reference (command_catalog)."""

BASICS = ("gam-basics", "How GAM commands are built", "syntax entity print show info todrive "
          "csv batch redirect select config", """
Every GAM command reads like a sentence: **who** it applies to, a **verb**, **what**, and
options. In GAMbit you type commands without the word `gam`.

## Who: entities
- `user jdoe@district.org` – one person; `users a@,b@,c@` – a list
- `group staff@district.org` – the members of a group
- `ou /Staff` – people directly in an org unit; `ou_and_children /Students` – including
  every org unit underneath
- `all users` – everyone (GAMbit always shows who would be affected first)
- `cros_sn 5CD123ABC` – a Chromebook by serial number

## Verbs
- `print` – a table (CSV) of results; GAMbit shows it as a sortable table
- `show` – a readable list; `info` – every detail about one thing
- `create` / `add`, `update`, `delete` / `remove` – make changes

## Handy extras
- `todrive` – send a `print` result straight to a Google Sheet
- `fields a,b,c` – only these columns (faster)
- `query "…"` – filter users or Chromebooks, e.g. `query "orgUnitPath='/Staff'"`
- `gam csv file.csv gam update user ~email ou ~ou` – one command per row (Bulk (CSV) page)
- `redirect csv ./out.csv` – save output to a file
- `select <section>` – use another domain from gam.cfg (GAMbit's Domain box)
""")

# (category, command, what it does)
COMMANDS = [
    # ------------------------------------------------------------------ setup
    ("Setup and checks", "gam version", "Shows GAM's version and where it's installed."),
    ("Setup and checks", "gam info domain", "Your domain, customer ID and counts – a quick "
     "connection test."),
    ("Setup and checks", "gam oauth create", "Signs GAM in with an admin account."),
    ("Setup and checks", "gam user <admin> check serviceaccount", "Checks GAM's service "
     "account can reach Gmail, Drive, Calendar and other per-user data."),
    ("Setup and checks", "gam rotate sakeys retain_none", "Replaces GAM's service-account "
     "key with a new one."),
    ("Setup and checks", "gam show sakeys", "Lists GAM's service-account keys and their age."),
    # ------------------------------------------------------------------ users
    ("Users", "gam info user <email>", "Everything about one account: name, org unit, "
     "suspension, aliases, groups, licenses, last sign-in."),
    ("Users", "gam print users fields primaryemail,name,ou,suspended,lastlogintime",
     "A table of accounts with the chosen columns."),
    ("Users", "gam print users query \"orgUnitPath='/Staff' isSuspended=false\"",
     "Accounts matching a search."),
    ("Users", "gam create user <email> firstname <f> lastname <l> password <pw> ou <ou>",
     "Creates an account."),
    ("Users", "gam update user <email> password <pw> changepassword on",
     "Resets the password and makes them choose a new one at next sign-in."),
    ("Users", "gam update user <email> changepassword on", "Requires a new password at next "
     "sign-in without resetting it."),
    ("Users", "gam update user <email> suspended on|off", "Suspends or unsuspends."),
    ("Users", "gam update user <email> ou <ou>", "Moves the account to another org unit."),
    ("Users", "gam update user <email> email <new email>", "Renames the primary address (the "
     "old one becomes an alias)."),
    ("Users", "gam update user <email> gal off", "Hides the person from the directory."),
    ("Users", "gam delete user <email>", "Deletes the account (restorable for 20 days)."),
    ("Users", "gam undelete user <email>", "Restores a recently deleted account."),
    ("Users", "gam print users deleted_only", "Accounts deleted in the last 20 days."),
    ("Users", "gam user <email> signout", "Signs them out of every browser and device."),
    ("Users", "gam user <email> deprovision", "Removes app passwords, backup codes and app "
     "access tokens."),
    ("Users", "gam user <email> update photo <file>", "Sets the profile photo."),
    ("Users", "gam print userinvitations", "Personal Google accounts that use a district "
     "address."),
    ("Users", "gam send userinvitation <email>", "Invites a personal account to join the "
     "district's Google account."),
    ("Users", "gam print usercountsbyorgunit", "Active, suspended and total accounts per org "
     "unit."),
    # ------------------------------------------------------------------ aliases
    ("Aliases", "gam create alias <alias> user <email>", "Adds another address for a person."),
    ("Aliases", "gam delete alias <alias>", "Removes an alias."),
    ("Aliases", "gam print aliases", "Every alias in the domain."),
    # ------------------------------------------------------------------ groups
    ("Groups", "gam print groups", "Every group, with the fields you choose."),
    ("Groups", "gam info group <group>", "A group's settings and members."),
    ("Groups", "gam print group-members group <group>", "A group's members and roles."),
    ("Groups", "gam create group <group> name \"…\"", "Creates a group."),
    ("Groups", "gam update group <group> add member|manager|owner user <email>",
     "Adds someone to a group with a role."),
    ("Groups", "gam update group <group> remove user <email>", "Removes someone."),
    ("Groups", "gam update group <group> sync member ou <ou>", "Makes the members exactly "
     "the people in an org unit."),
    ("Groups", "gam update group <group> whocanpostmessage all_members_can_post",
     "Changes a group setting (who can post, view, join…)."),
    ("Groups", "gam print groups member <email>", "The groups one person is in."),
    ("Groups", "gam user <email> print grouptree", "A person's groups and the groups those "
     "are inside."),
    ("Groups", "gam delete group <group>", "Deletes a group."),
    # ------------------------------------------------------------------ org units
    ("Org units", "gam print ous", "Every org unit."),
    ("Org units", "gam create org \"/Students/Lincoln\"", "Creates an org unit."),
    ("Org units", "gam update org <ou> name <new>", "Renames an org unit."),
    ("Org units", "gam update org <ou> add users <emails>", "Moves people into an org unit."),
    ("Org units", "gam delete org <ou>", "Deletes an empty org unit."),
    # ------------------------------------------------------------------ licenses
    ("Licenses", "gam print licenses", "Who has which license."),
    ("Licenses", "gam user <email> add license <sku>", "Assigns a license."),
    ("Licenses", "gam user <email> delete license <sku>", "Removes a license."),
    # ------------------------------------------------------------------ chromebooks
    ("Chromebooks", "gam print cros fields serialnumber,annotateduser,orgunitpath,lastsync",
     "A table of Chromebooks with the chosen columns."),
    ("Chromebooks", "gam cros_sn <serial> print cros", "One Chromebook's details by serial."),
    ("Chromebooks", "gam cros_sn <serial> update ou <ou>", "Moves a Chromebook to another "
     "org unit."),
    ("Chromebooks", "gam cros_sn <serial> update assetid <tag> location <room> user <email>",
     "Sets the asset tag, location and assigned user."),
    ("Chromebooks", "gam cros_sn <serial> update notes \"…\"", "Sets the device notes."),
    ("Chromebooks", "gam cros_sn <serial> update action disable|reenable", "Disables a lost "
     "device (shows your return message) or turns it back on."),
    ("Chromebooks", "gam cros_sn <serial> update action deprovision_retiring_device",
     "Removes a device from management."),
    ("Chromebooks", "gam cros_sn <serial> issuecommand command reboot|wipe_users|"
     "remote_powerwash doit", "Sends a remote command to the device."),
    ("Chromebooks", "gam print crosactivity", "When each Chromebook was used and by whom."),
    ("Chromebooks", "gam print crostelemetry", "Battery, storage, CPU and network health "
     "reported by each device."),
    ("Chromebooks", "gam print chromeaues", "How many devices reach end of updates each "
     "month."),
    ("Chromebooks", "gam print chromeversions", "Which ChromeOS versions devices run."),
    ("Chromebooks", "gam print chromeapps", "Apps and extensions installed on devices."),
    # ------------------------------------------------------------------ chrome policy
    ("Chrome policies and browsers", "gam print chromepolicies ou <ou> show all",
     "Chrome settings that apply to an org unit (set there or inherited)."),
    ("Chrome policies and browsers", "gam update chromepolicy <schema> <field> <value> ou "
     "<ou>", "Changes a Chrome setting for an org unit."),
    ("Chrome policies and browsers", "gam delete chromepolicy <schema> ou <ou>",
     "Removes a setting so the org unit inherits its parent's value."),
    ("Chrome policies and browsers", "gam create chromepolicyimage chrome.users.wallpaper "
     "<file>", "Uploads a wallpaper or account picture for use in a policy."),
    ("Chrome policies and browsers", "gam print browsers", "Managed Chrome browsers on "
     "Windows, Mac and Linux."),
    ("Chrome policies and browsers", "gam create browsertoken ou <ou>", "An enrollment token "
     "for managing Chrome browsers."),
    ("Chrome policies and browsers", "gam print chromeprofiles", "Managed Chrome profiles "
     "(people signed in to Chrome with a district account)."),
    ("Chrome policies and browsers", "gam print chromehistory versions platform win64 "
     "channel stable", "Google's Chrome release history – the newest stable version."),
    ("Chrome policies and browsers", "gam print printers", "Printers set up for Chromebooks."),
    # ------------------------------------------------------------------ devices
    ("Phones and computers", "gam print devices", "Computers and phones under endpoint "
     "management."),
    ("Phones and computers", "gam print mobile", "Mobile devices signed in to accounts."),
    ("Phones and computers", "gam update deviceuser <id> action approve|block|wipe",
     "Approves, blocks or removes the district account from a device."),
    # ------------------------------------------------------------------ gmail
    ("Gmail", "gam user <email> vacation on subject \"…\" message \"…\" startdate <d> "
     "enddate <d>", "Turns on an out-of-office reply."),
    ("Gmail", "gam user <email> vacation off", "Turns the reply off."),
    ("Gmail", "gam user <email> signature \"<html>\"", "Sets the email signature."),
    ("Gmail", "gam user <email> forward on keep|archive|delete <address>",
     "Forwards mail and chooses what happens to their copy."),
    ("Gmail", "gam user <email> add forwardingaddress <address>", "Adds an allowed "
     "forwarding address."),
    ("Gmail", "gam user <email> add delegate <helper>", "Gives someone access to the "
     "mailbox."),
    ("Gmail", "gam user <email> delete delegate <helper>", "Removes mailbox access."),
    ("Gmail", "gam user <email> print filters", "Gmail filters (look for forwarding to "
     "strangers after a hack)."),
    ("Gmail", "gam user <email> imap off", "Turns off IMAP."),
    ("Gmail", "gam all users print messages query \"from:x subject:y\" "
     "positivecountsonly", "Which mailboxes have matching messages."),
    ("Gmail", "gam all users trash messages query \"…\" doit", "Moves matching messages to "
     "the trash in every mailbox."),
    ("Gmail", "gam user <email> add sendas <address> name \"…\"", "Lets someone send as "
     "another address."),
    ("Gmail", "gam user <email> add label \"…\"", "Creates a Gmail label."),
    ("Gmail", "gam sendemail to <to> subject \"…\" message \"…\"", "Sends an email."),
    # ------------------------------------------------------------------ drive
    ("Drive", "gam user <email> print filelist", "A person's Drive files."),
    ("Drive", "gam user <email> print filelist query \"visibility='anyoneWithLink'\"",
     "Files anyone with the link can open."),
    ("Drive", "gam user <email> print filesharecounts", "How many files are public, shared "
     "with the link or shared outside."),
    ("Drive", "gam user <email> add drivefileacl <file id> user <other> role reader|writer",
     "Shares a file."),
    ("Drive", "gam user <email> delete drivefileacl <file id> anyone", "Stops link "
     "sharing."),
    ("Drive", "gam create datatransfer <old> gdrive <new> privacy_level shared,private",
     "Transfers all Drive files to someone else."),
    ("Drive", "gam print datatransfers", "Status of data transfers."),
    ("Drive", "gam user <email> print driveactivity fileid <id>", "Who did what to a file."),
    ("Drive", "gam user <email> untrash drivefile <id>", "Restores a trashed file."),
    ("Drive", "gam user <email> empty drivetrash", "Empties their Drive trash."),
    ("Drive", "gam user <email> print emptydrivefolders", "Empty folders in My Drive."),
    ("Drive", "gam print shareddrives", "Every shared drive."),
    ("Drive", "gam create shareddrive \"…\"", "Creates a shared drive."),
    ("Drive", "gam add drivefileacl <drive id> user <email> role organizer",
     "Adds a manager to a shared drive."),
    ("Drive", "gam update shareddrive <id> ou <ou>", "Puts a shared drive in an org unit."),
    ("Drive", "gam hide shareddrive <id>", "Hides a shared drive."),
    # ------------------------------------------------------------------ classroom
    ("Classroom", "gam print courses teacher <email> states active", "A teacher's active "
     "classes."),
    ("Classroom", "gam create course alias <alias> name \"…\" teacher <email>",
     "Creates a class."),
    ("Classroom", "gam course <id> add student|teacher <email>", "Adds someone to a class."),
    ("Classroom", "gam course <id> remove student <email>", "Removes someone."),
    ("Classroom", "gam update course <id> state archived|active", "Archives or reactivates "
     "a class."),
    ("Classroom", "gam update course <id> owner <email>", "Changes a class's owner."),
    ("Classroom", "gam print course-participants course <id>", "A class's roster."),
    ("Classroom", "gam print course-submissions course <id> submissionstates new,created "
     "late", "Missing work."),
    ("Classroom", "gam print classroominvitations", "Invitations nobody accepted."),
    ("Classroom", "gam create guardian <guardian email> <student>", "Invites a guardian."),
    ("Classroom", "gam print guardians", "Guardians and invitations."),
    # ------------------------------------------------------------------ calendar
    ("Calendar", "gam calendars <email> print acls", "Who a calendar is shared with."),
    ("Calendar", "gam calendars <email> delete acls default", "Stops public sharing."),
    ("Calendar", "gam user <email> print events", "Upcoming events."),
    ("Calendar", "gam user <email> create outofoffice range <from> <to>", "Adds "
     "out-of-office that declines meetings."),
    ("Calendar", "gam print resources", "Rooms and resources."),
    ("Calendar", "gam create resource <id> \"Room 101\"", "Creates a room."),
    # ------------------------------------------------------------------ security
    ("Security", "gam all users print tokens", "Third-party apps people signed in to and "
     "what they can reach."),
    ("Security", "gam user <email> delete token clientid <id>", "Removes an app's access."),
    ("Security", "gam user <email> print backupcodes", "2-Step Verification backup codes."),
    ("Security", "gam user <email> turnoff2sv", "Turns off 2-Step Verification (lost "
     "phone)."),
    ("Security", "gam user <email> print asps", "App passwords."),
    ("Security", "gam print alerts", "Google Alert Center alerts."),
    ("Security", "gam print admins", "Admin role assignments."),
    ("Security", "gam create admin <email> <role> customer", "Gives someone an admin role."),
    ("Security", "gam delete admin <assignment id>", "Removes an admin role assignment."),
    ("Security", "gam print policies", "Admin console settings (Cloud Identity policies)."),
    # ------------------------------------------------------------------ reports
    ("Reports and audit logs", "gam report login user <email>", "Sign-ins, including "
     "suspicious ones."),
    ("Reports and audit logs", "gam report admin start -7d", "Changes made in the Admin "
     "console."),
    ("Reports and audit logs", "gam report drive user <email> events download",
     "Drive activity (views, downloads, sharing)."),
    ("Reports and audit logs", "gam report token user all", "Apps being allowed or removed."),
    ("Reports and audit logs", "gam report useraccounts user all", "Password and 2SV "
     "changes."),
    ("Reports and audit logs", "gam report chrome", "ChromeOS events (sign-ins, enrollments, "
     "extensions)."),
    ("Reports and audit logs", "gam report classroom", "Classroom activity."),
    ("Reports and audit logs", "gam report users parameters accounts:last_login_time",
     "Per-person usage numbers (storage, sign-ins…)."),
    ("Reports and audit logs", "gam report customer", "District-wide usage numbers."),
    # ------------------------------------------------------------------ vault
    ("Vault", "gam create vaultmatter name \"…\"", "Creates a Vault matter."),
    ("Vault", "gam create vaulthold matter <m> name \"…\" corpus mail accounts <email>",
     "Places a legal hold."),
    ("Vault", "gam create vaultexport matter <m> name \"…\" corpus mail accounts <email>",
     "Starts an export."),
    ("Vault", "gam print vaultexports matters <m>", "Export status."),
    ("Vault", "gam download vaultexport <id> matter <m> targetfolder <folder>",
     "Downloads finished export files."),
    ("Vault", "gam close vaultmatter <m>", "Closes a matter (releases its holds)."),
    # ------------------------------------------------------------------ more
    ("Meet", "gam user <teacher> print meetconferences code <abc-defg-hij>",
     "A teacher's meetings with that code."),
    ("Meet", "gam user <teacher> print meetparticipants <conference>", "Who joined a meeting."),
    ("Meet", "gam user <teacher> print meetrecordings <conference>", "Where a meeting's "
     "recordings were saved."),
    ("Meet", "gam user <teacher> print meettranscripts <conference>", "A meeting's "
     "transcripts."),
    ("Meet", "gam report meet user all events call_ended", "Every Meet call: who, which "
     "meeting, how long."),
    ("Drive", "gam user <owner> transfer ownership <folder id> <new owner>", "Hands one "
     "folder (and everything in it) to someone else."),
    ("Drive", "gam user <new owner> claim ownership <folder id>", "The new owner takes over a "
     "folder others own."),
    ("Drive", "gam user <email> print filepath <file id> fullpath", "Where a file lives."),
    ("Drive", "gam user <email> print filecomments <file id> showdeleted", "Comments on a "
     "file, including deleted ones."),
    ("Drive", "gam user <email> print diskusage <folder id>", "How big a folder is."),
    ("Drive", "gam user <email> check drivefileshortcut <folder id>", "Finds broken "
     "shortcuts."),
    ("Drive", "gam user <owner> print formresponses <form id>", "A Google Form's "
     "responses."),
    ("Chromebooks", "gam print chromesnvalidity cros_sn <serials>", "Checks serial numbers "
     "against your domain (typos, not yet enrolled)."),
    ("Chromebooks", "gam print chromedevicecounts mode active", "How many devices were active "
     "in the last days."),
    ("Chromebooks", "gam cros_sn <serial> get devicefile targetfolder <folder>",
     "Downloads a device's log files."),
    ("Chrome policies and browsers", "gam create chromenetwork <ou> <name> json <settings>",
     "Pushes a Wi-Fi network to Chromebooks in an org unit."),
    ("Chrome policies and browsers", "gam delete chromenetwork <ou> <network id>",
     "Removes a pushed Wi-Fi network."),
    ("Chrome policies and browsers", "gam info chromeapp chrome <app id>", "What an "
     "extension or app is and what it can reach."),
    ("Chrome policies and browsers", "gam print printermodels", "Printer models Chromebooks "
     "support."),
    ("Calendar", "gam users <organizers> update calattendees primary after <date> matchfield "
     "attendees <old> replace <old> <new> doit", "Swaps one person for another in future "
     "meetings."),
    ("Classroom", "gam user <teacher> print classroomprofile", "Whether a teacher is verified "
     "and can create classes."),
    ("Classroom", "gam print course-counts teachers states active", "Active classes per "
     "teacher (or students)."),
    ("Classroom", "gam cancel guardianinvitation <invitation id> <student>", "Cancels a "
     "guardian invitation."),
    ("Security", "gam print allowlisteddomains", "Trusted partner domains for sharing and "
     "classes."),
    ("Security", "gam create allowlisteddomains <domains>", "Adds trusted domains."),
    ("Users", "gam ou_and_children <ou> get profilephoto targetfolder <folder>",
     "Saves profile photos to a folder."),
    ("Gmail", "gam user <email> language es", "Sets Gmail's display language."),
    ("Vault", "gam create vaultquery <matter> name \"…\" corpus mail accounts <email>",
     "Saves a search in a matter."),
    ("Chat", "gam user <admin> print chatspaces asadmin", "Every Chat space in the "
     "district."),
    ("Chat", "gam user <admin> delete chatmember asadmin <space> user <email>",
     "Removes someone from a space."),
    ("Chrome", "gam print chromeprofiles fields name,useremail,lastactivitytime",
     "Managed Chrome profiles on Windows/Mac/Linux with when they were last used."),
    ("Chrome", "gam delete chromeprofile <name>", "Removes an old managed Chrome profile."),
    ("Calendar", "gam print features", "Room features (projector, doc camera…)."),
    ("Calendar", "gam create feature name <name>", "Creates a room feature."),
    ("Calendar", "gam update resource <id> addfeatures <feature>", "Adds a feature to a room."),
    ("Calendar", "gam user <email> create workinglocation office <building> weekly "
     "<date> <weeks>", "Sets a weekly working location on someone's calendar."),
    ("Drive", "gam print shareddriveorganizers oneorganizer false showorgunits true",
     "Every shared drive with its managers."),
    ("Email", "gam user <email> print gmailprofile", "Message and thread counts for a "
     "mailbox."),
    ("Email", "gam ou_and_children /Staff print delegates", "Who can read each mailbox."),
    ("Email", "gam ou_and_children /Staff print sendas", "Extra addresses people send as."),
    ("Calendar", "gam ou_and_children /Staff print calendaracls primary noselfowner",
     "Who can see or change each person's calendar."),
    ("Users", "gam user <email> print tasks showcompleted false", "A person's open Google "
     "Tasks."),
    ("Drive", "gam user <email> update sheetrange <fileid> json '{…}' userentered",
     "Writes cells into a Google Sheet in place."),
    ("Drive", "gam print classificationlabelpermissions labels/<id> asadmin",
     "Who may apply or edit a Drive label."),
    ("Drive", "gam create classificationlabelpermission labels/<id> group <email> role "
     "applier asadmin", "Lets a group apply a Drive label."),
    ("Chrome", "gam update cros <deviceid> assetid <tag>", "Sets a Chromebook's asset tag."),
]
