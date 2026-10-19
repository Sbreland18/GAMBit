"""Round 13 tabs and dialogs that live on existing pages: personal Google accounts, calendar
sharing and out-of-office, Classroom invitations and topics, out-of-date Chrome browsers,
policy images, Drive sharing exposure / shared-drive settings / empty folders, file
activity, app passwords, GAMbit's Google key, group trees and suggestions, testing-day
device readiness, Chromebook redistribution, policy override clean-up and user counts."""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFileDialog, QLabel, QLineEdit,
    QPlainTextEdit, QSpinBox, QVBoxLayout,
)

from ...settings import settings
from ...tools import gam_extras as gx
from ..pickers import OUField, OUMultiField, PersonField
from ..tools_base import ToolTab
from ..widgets import ResultsTable, Worker, button
from .round11_pages import run_or_request


def _csv():
    from ...directory import run_gam_csv
    return lambda a: run_gam_csv(a, 3600)


def _text():
    from ...directory import run_gam_text
    return lambda a, t=600: run_gam_text(a, t)


def fill(table: ResultsTable, rows: list[dict], cols: list[str]):
    table.set_rows(cols, [[("" if r.get(c) is None else str(r.get(c))) for c in cols]
                          for r in rows])


def _domains() -> set[str]:
    from ...tools.watchdog import domains
    return domains()


def _date_edit(days: int = 0) -> QDateEdit:
    d = QDateEdit(QDate.currentDate().addDays(days))
    d.setCalendarPopup(True)
    return d


# ======================================================= personal accounts ===
class PersonalAccountsTab(ToolTab):
    intro = ("Personal (consumer) Google accounts that use a district email address – usually "
             "made before the district had Google, or by someone signing up for a service. "
             "They're outside your control until the person accepts an invitation to join. "
             "Google lists them here; invite them, or check addresses before creating new "
             "accounts so there's no clash.")

    def build(self):
        self.state = QComboBox()
        for label, v in (("Not invited yet", "notyetsent"), ("Invited – waiting", "invited"),
                         ("Declined", "declined"), ("Accepted", "accepted"), ("All", "")):
            self.state.addItem(label, v)
        self.lay.addLayout(self.row(QLabel("Show"), self.state,
                                    button("Load", "primary", self.load), self.status))
        self.table = ResultsTable()
        self.table.setMinimumHeight(260)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(button("Invite selected to join", "primary", self.invite),
                                    button("Cancel invitation", slot=self.cancel)))
        box, form = self.page.group("Check addresses before creating accounts")
        self.check_box = QPlainTextEdit()
        self.check_box.setPlaceholderText("one email address per line")
        self.check_box.setMaximumHeight(80)
        form.addRow(self.check_box)
        form.addRow("", self.row(button("Check", slot=self.check)))
        self.lay.addWidget(box)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def load(self):
        args = list(gx.INVITES_ARGS) + (["state", self.state.currentData()]
                                        if self.state.currentData() else [])

        def got(rows):
            if rows is None:
                return
            items = [{"email": i["email"], "Status": i["label"], "Updated": i["updated"],
                      "Emails sent": i["sent"]} for i in gx.invitations(rows)]
            fill(self.table, items, ["email", "Status", "Updated", "Emails sent"])
            self.status.setText(f"{len(items):,} personal account(s)")
        self.read(args, got)

    def invite(self):
        sel = self.table.selected_values("email")
        if not sel:
            self.info("Select the accounts to invite.")
            return
        if self.confirm(f"Email {len(sel)} person/people an invitation to move their personal "
                        "account into the district's Google account?"):
            self.run_steps(self.steps, [(f"Invite {e}", gx.invite_args(e)) for e in sel],
                           lambda _s: self.load())

    def cancel(self):
        sel = self.table.selected_values("email")
        if sel and self.confirm(f"Cancel {len(sel)} invitation(s)?"):
            self.run_steps(self.steps, [(f"Cancel {e}", gx.cancel_invite_args(e)) for e in sel],
                           lambda _s: self.load())

    def check(self):
        emails = [e.strip() for e in self.check_box.toPlainText().split() if "@" in e]
        if not emails:
            return

        def got(rows):
            if rows is None:
                return
            bad = [r for r in rows if any("true" in (v or "").lower() for k, v in r.items()
                                          if "invitable" in (k or "").lower())]
            self.info(("These addresses already have a personal Google account – invite "
                       "them instead of creating a new account:\n" +
                       "\n".join(f"• {next(iter(r.values()))}" for r in bad)) if bad else
                      "None of these addresses has a personal Google account. ✔")
        self.read(gx.isinvitable_args(emails), got)


# ================================================================ calendars ===
class CalendarsTab(ToolTab):
    intro = ("Find staff and room calendars shared publicly or with people outside the "
             "district, and put out-of-office on someone's calendar (it declines new "
             "meetings while they're away).")

    def build(self):
        box, form = self.page.group("Calendar sharing check")
        self.ou = OUField(self.directory, "/Staff")
        self.ou.set_path("/Staff")
        self.rooms = QCheckBox("Include room and resource calendars")
        form.addRow("Whose calendars", self.ou)
        form.addRow("", self.rooms)
        form.addRow("", self.row(button("Scan", "primary", self.scan), self.status))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(220)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(button("Stop sharing selected", "danger", self.unshare)))
        box, form = self.page.group("Out of office")
        self.who = PersonField(self.directory, "Who is away?")
        self.start, self.end = _date_edit(), _date_edit(7)
        self.msg = QLineEdit(placeholderText="Decline message, e.g. I'm out until Monday – "
                                             "please contact the front office.")
        self.mode = QComboBox()
        self.mode.addItem("Decline new invitations only", "new")
        self.mode.addItem("Decline new and existing meetings", "all")
        self.mode.addItem("Don't decline anything", "none")
        form.addRow("Person", self.who)
        form.addRow("From / until", self.row(self.start, self.end, stretch=False))
        form.addRow("Message", self.msg)
        form.addRow("Meetings", self.mode)
        form.addRow("", self.row(button("Add out of office", "primary", self.add_ooo),
                                 button("Show", slot=self.show_ooo),
                                 button("Remove", slot=self.del_ooo)))
        self.lay.addWidget(box)
        from .round14_tabs import replace_box
        replace_box(self, self.lay)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.found = []

    def scan(self):
        root = (self.ou.path() or "/").rstrip("/").lower()
        cals = [u["email"] for u in self.directory.users if not u.get("suspended") and
                (root in ("", "/") or (u.get("ou") or "").lower() == root or
                 (u.get("ou") or "").lower().startswith(root + "/"))]
        if not cals and not self.rooms.isChecked():
            self.info("No accounts found there (load people first from the Users page).")
            return
        rooms = self.rooms.isChecked()

        def work():
            run = _csv()
            out = []
            more = cals[:]
            if rooms:
                c, rows, _e = run(["print", "resources", "fields", "email"])
                more += [r.get("resourceEmail") or r.get("email") or "" for r in rows
                         if c == 0]
            for part in gx._chunks([m for m in more if m], 50):
                c, rows, _e = run(gx.cal_acl_args(part))
                if c == 0:
                    out += gx.cal_exposure(rows, _domains())
            return out

        def done(found):
            self.found = found
            fill(self.table, found, ["Calendar", "Shared with", "Can"])
            self.status.setText(f"{len(found):,} calendar share(s) outside the district")
        self.status.setText(f"Checking {len(cals):,} calendar(s)…")
        Worker(work, on_done=done, on_error=lambda e: (self.status.setText(""),
                                                       self.info(str(e))))

    def unshare(self):
        rows = self.table.selected_dicts()
        steps = [(f"{f['Calendar']}: stop sharing with {f['scope']}",
                  gx.cal_unshare_args(f["Calendar"], f["scope"]))
                 for r in rows for f in self.found
                 if f["Calendar"] == r["Calendar"] and f["Shared with"] == r["Shared with"]]
        run_or_request(self.page, self.steps, steps, "Stop sharing calendars",
                       "Calendar shared outside the district")

    def _range(self):
        return (self.start.date().toPython().isoformat(),
                self.end.date().toPython().isoformat())

    def add_ooo(self):
        who = self.who.email()
        if "@" not in who:
            self.info("Choose the person.")
            return
        a, b = self._range()
        self.run_steps(self.steps, [(f"Out of office for {who} {a} – {b}",
                                     gx.ooo_args(who, a, b, self.msg.text().strip(),
                                                 self.mode.currentData()))])

    def show_ooo(self):
        who = self.who.email()
        if "@" in who:
            a, b = self._range()
            self.read(gx.ooo_print_args(who, a, b), lambda rows: rows is not None and
                      fill(self.table, rows, list(rows[0].keys()) if rows else ["(none)"]))

    def del_ooo(self):
        who = self.who.email()
        if "@" in who and self.confirm("Remove the out-of-office events in these dates?"):
            a, b = self._range()
            self.run_steps(self.steps, [(f"Remove out of office for {who}",
                                         gx.ooo_delete_args(who, a, b))])


# ===================================================== classroom invitations ===
class ClassInvitesTab(ToolTab):
    intro = ("Students and teachers who were invited to a class and never accepted – and "
             "copying a class's topics into other classes.")

    def build(self):
        self.lay.addLayout(self.row(button("Load invitations", "primary", self.load),
                                    self.status))
        self.summary = ResultsTable()
        self.summary.setMinimumHeight(160)
        self.lay.addWidget(self.summary)
        self.table = ResultsTable()
        self.table.setMinimumHeight(200)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(button("Send again (remove + invite)", slot=self.resend),
                                    button("Remove invitation", "danger", self.remove)))
        box, form = self.page.group("Copy topics")
        self.src = QLineEdit(placeholderText="class ID to copy from")
        self.dst = QLineEdit(placeholderText="class IDs to copy into, separated by commas")
        form.addRow("From", self.src)
        form.addRow("Into", self.dst)
        form.addRow("", self.row(button("Copy topics", slot=self.copy_topics)))
        self.lay.addWidget(box)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.invs = []

    def load(self):
        def got(rows):
            if rows is None:
                return
            self.invs = gx.class_invites(rows)
            fill(self.summary, gx.invite_summary(self.invs), ["Class", "Students", "Teachers"])
            fill(self.table, self.invs, ["Class", "Person", "Role", "id"])
            self.status.setText(f"{len(self.invs):,} invitation(s) not accepted")
        self.read(gx.CLASS_INVITES_ARGS, got)

    def _sel(self):
        ids = set(self.table.selected_values("id"))
        return [i for i in self.invs if i["id"] in ids]

    def resend(self):
        sel = self._sel()
        steps = []
        for i in sel:
            steps += [(f"{i['Person']}: remove old invitation",
                       gx.delete_invite_args(i["course"], i["id"])),
                      (f"{i['Person']}: invite to {i['Class']}", gx.readd_args(i))]
        if steps and self.confirm(f"Send {len(sel)} invitation(s) again?"):
            self.run_steps(self.steps, steps, lambda _s: self.load())

    def remove(self):
        sel = self._sel()
        if sel and self.confirm(f"Remove {len(sel)} invitation(s)?"):
            self.run_steps(self.steps, [(f"{i['Person']} – {i['Class']}",
                                         gx.delete_invite_args(i["course"], i["id"]))
                                        for i in sel], lambda _s: self.load())

    def copy_topics(self):
        src = self.src.text().strip()
        dst = [x.strip() for x in self.dst.text().split(",") if x.strip()]
        if not src or not dst:
            self.info("Fill in the class to copy from and the classes to copy into.")
            return

        def got(results):
            names = gx.topic_names(results[0])
            existing = {t: {n.lower() for n in gx.topic_names(r)}
                        for t, r in zip(dst, results[1:])}
            cmds = gx.copy_topics_commands(names, dst, existing)
            if not cmds:
                self.info("Those classes already have all the topics.")
                return
            if self.confirm(f"Add {len(cmds)} topic(s)?"):
                self.run_steps(self.steps, [(f"{c[1]}: {c[4]}", c) for c in cmds])
        self.read_many([gx.topics_args(src)] + [gx.topics_args(t) for t in dst], got)


# ===================================================== chrome browsers / images ===
class BrowserVersionsDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Out-of-date Chrome browsers")
        self.resize(1000, 600)
        v = QVBoxLayout(self)
        tip = QLabel("Managed Chrome profiles on staff Windows, Mac and Linux computers running "
                     "a Chrome version more than one major release behind Google's newest "
                     "stable release. Clearing the cache also nudges an update check.",
                     wordWrap=True)
        v.addWidget(tip)
        self.status = QLabel("Loading…", objectName="Muted")
        v.addWidget(self.status)
        self.table = ResultsTable()
        v.addWidget(self.table, 1)
        self.cookies = QCheckBox("Also clear cookies (signs them out of websites)")
        v.addLayout(page.row(button("Clear cache for selected", "primary", self.clear),
                             self.cookies))
        from ..steps import StepList
        self.steps = StepList(page)
        self.steps.setMaximumHeight(140)
        v.addWidget(self.steps)
        self.items = []
        Worker(self._work, on_done=self._done, on_error=lambda e: self.status.setText(str(e)))

    def _work(self):
        from ...tools.recovery import PROFILES_ARGS
        run = _csv()
        latest = {}
        for plat in ("win64", "mac", "linux"):
            c, rows, _e = run(gx.versions_args(plat))
            if c == 0:
                latest[plat] = gx.latest_versions(rows)
        c, rows, e = run(PROFILES_ARGS)
        if c != 0:
            raise RuntimeError("Couldn't list Chrome profiles: " + (e or "").strip()[-200:])
        return gx.behind(gx.profile_rows(rows), latest), latest

    def _done(self, res):
        self.items, latest = res
        fill(self.table, [{"Person": p["person"], "Computer": p["computer"], "OS": p["os"],
                           "Chrome": p["version"], "Newest": p["latest"],
                           "Versions behind": p["behind"], "Last used": p["last"],
                           "name": p["name"]} for p in self.items],
             ["Person", "Computer", "OS", "Chrome", "Newest", "Versions behind", "Last used",
              "name"])
        self.status.setText(f"{len(self.items):,} profile(s) behind · newest stable: " +
                            ", ".join(f"{k} {v}" for k, v in latest.items() if v))

    def clear(self):
        names = self.table.selected_values("name")
        if not names:
            return
        cmds = [gx.profile_command_args(part, True, self.cookies.isChecked())
                for part in gx._chunks(names, 50)]
        from ..steps import Step
        self.steps.run([Step(f"Clear cache on {len(p)} profile(s)", c)
                        for p, c in zip(gx._chunks(names, 50), cmds)],
                       lambda _s: self.page.info(self.steps.summary()))


class PolicyImageDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Wallpaper and account picture")
        v = QVBoxLayout(self)
        box, form = page.group("Upload an image and set it for an org unit")
        self.kind = QComboBox()
        for k, (label, _s, _f) in gx.IMAGE_SCHEMAS.items():
            self.kind.addItem(label, k)
        self.path = QLineEdit(placeholderText="a .jpg or .png file")
        self.ou = OUField(page.directory, "/Students")
        form.addRow("What", self.kind)
        form.addRow("Image", page.row(self.path, button("Browse…", slot=self._browse),
                                      stretch=False))
        form.addRow("For", self.ou)
        self.status = QLabel("", objectName="Muted", wordWrap=True)
        form.addRow("", page.row(button("Upload and apply", "primary", self.go), self.status))
        v.addWidget(box)

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Image", "", "Images (*.jpg *.jpeg *.png)")
        if p:
            self.path.setText(p)

    def go(self):
        kind, path, ou = self.kind.currentData(), self.path.text().strip(), self.ou.path()
        if not path or not ou:
            self.status.setText("Choose the image and the org unit.")
            return
        if not self.page.confirm(f"Upload {path} and set it as the "
                                 f"{self.kind.currentText().lower()} for {ou}?"):
            return

        def work():
            run = _text()
            c, out = run(gx.image_upload_args(kind, path))
            url = gx.image_url(out) if c == 0 else ""
            if not url:
                raise RuntimeError("Google didn't accept the image: " + (out or "")[-200:])
            args = gx.image_policy_args(kind, url, ou)
            c, out = run(args)
            from ... import activity
            activity.record(args, c, "done" if c == 0 else "failed", None,
                            settings.get("profile/current", "") or "Default",
                            note="policy image")
            if c != 0:
                raise RuntimeError((out or "")[-200:])
            return url
        self.status.setText("Uploading…")
        Worker(work, on_done=lambda u: self.status.setText(f"Done ✔ ({u[:60]}…)"),
               on_error=lambda e: self.status.setText(str(e)))


# ===================================================================== drive ===
class SharingExposureTab(ToolTab):
    intro = ("How many files each person shares publicly, with anyone who has the link, or "
             "with people outside the district – by person and by school. Use Fix sharing to "
             "clean up the worst.")

    def build(self):
        self.ou = OUField(self.directory, "/Students")
        self.ou.set_path("/Staff")
        self.by = QComboBox()
        self.by.addItems(["By person", "By school"])
        self.by.currentIndexChanged.connect(self._show)
        self.lay.addLayout(self.row(QLabel("People in"), self.ou,
                                    button("Count", "primary", self.load), self.by,
                                    self.status))
        self.table = ResultsTable()
        self.table.setMinimumHeight(320)
        self.lay.addWidget(self.table, 1)
        self.lay.addWidget(QLabel("Counting reads every file's sharing – allow a few minutes "
                                  "per hundred people.", objectName="Muted"))
        self.counts = []

    def load(self):
        ou = self.ou.path() or "/"
        scope = ["all", "users"] if ou == "/" else ["ou_and_children", ou]

        def got(rows):
            if rows is None:
                return
            from ...school_reports import options
            self.counts = gx.sharecounts(rows, self.directory.users,
                                         options().get("root", "/Students"))
            self._show()
        self.read(gx.sharecount_args(scope), got, "Counting shared files…")

    def _show(self, *_):
        if self.by.currentIndex() == 0:
            fill(self.table, self.counts, ["Owner", "School", "Public", "Anyone with link",
                                           "Outside people", "Shared outside", "Files"])
        else:
            fill(self.table, gx.share_by_school(self.counts),
                 ["School", "People", "Public", "Anyone with link", "Outside people"])
        self.status.setText(f"{len(self.counts):,} people")


class SharedDriveSettingsTab(ToolTab):
    intro = ("Put shared drives in org units so the right sharing rules apply (for example "
             "student-club drives under /Students), and set their themes.")

    def build(self):
        from .round15_tabs import OrganizersDialog
        self.lay.addLayout(self.row(button("Load shared drives", "primary", self.load),
                                    button("Who manages them?…",
                                           slot=lambda: OrganizersDialog(self.page).exec()),
                                    self.status))
        self.table = ResultsTable()
        self.table.setMinimumHeight(260)
        self.lay.addWidget(self.table, 1)
        self.ou = OUField(self.directory, "/Students/Clubs")
        self.theme = QLineEdit(placeholderText="theme ID, e.g. abacus")
        self.lay.addLayout(self.row(QLabel("Selected:"), self.ou,
                                    button("Move to org unit", slot=self.move),
                                    self.theme, button("Set theme", slot=self.set_theme)))
        box, form = self.page.group("Suggest moves by name")
        self.rules = QPlainTextEdit(settings.get("shareddrives/ou_rules", "") or "")
        self.rules.setPlaceholderText("one per line:  club = /Students/Clubs")
        self.rules.setMaximumHeight(80)
        form.addRow(self.rules)
        form.addRow("", self.row(button("Suggest", slot=self.suggest)))
        self.lay.addWidget(box)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.drives = []

    def load(self):
        def got(rows):
            if rows is None:
                return
            self.drives = gx.shared_drives(rows)
            fill(self.table, self.drives, ["Name", "Org unit", "Created", "Theme", "id"])
            self.status.setText(f"{len(self.drives):,} shared drive(s)")
        self.read(gx.SHARED_DRIVES_ARGS, got)

    def move(self):
        ids, ou = self.table.selected_values("id"), self.ou.path()
        if ids and ou:
            run_or_request(self.page, self.steps, [(f"Move {i} to {ou}", gx.drive_ou_args(i, ou))
                                                   for i in ids],
                           "Move shared drives", "Shared drive org units")

    def set_theme(self):
        ids, th = self.table.selected_values("id"), self.theme.text().strip()
        if ids and th:
            self.run_steps(self.steps, [(f"Theme {i}", gx.drive_theme_args(i, th))
                                        for i in ids], lambda _s: self.load())

    def suggest(self):
        text = self.rules.toPlainText()
        settings.set("shareddrives/ou_rules", text)
        rules = [tuple(x.strip() for x in ln.split("=", 1)) for ln in text.splitlines()
                 if "=" in ln]
        sug = gx.drive_ou_suggestions(self.drives, rules)
        fill(self.table, sug, ["Name", "Org unit", "Move to", "id"])
        self.status.setText(f"{len(sug)} suggested move(s) – select and run below")
        self._sug = sug
        if sug and self.confirm(f"Move all {len(sug)} now?"):
            run_or_request(self.page, self.steps, [(f"{d['Name']} → {d['Move to']}",
                                                    gx.drive_ou_args(d["id"], d["Move to"]))
                                                   for d in sug],
                           "Move shared drives", "Shared drive org units by name")


class EmptyFoldersTab(ToolTab):
    intro = "Find and remove empty folders in someone's My Drive."

    def build(self):
        self.who = PersonField(self.directory, "Whose Drive?")
        self.lay.addLayout(self.row(self.who, button("Find empty folders", "primary",
                                                     self.load),
                                    button("Delete them all", "danger", self.delete),
                                    self.status))
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def load(self):
        who = self.who.email()
        if "@" in who:
            self.read(gx.empty_folders_args(who), lambda rows: rows is not None and (
                fill(self.table, rows, ["id", "name"]),
                self.status.setText(f"{len(rows):,} empty folder(s)")))

    def delete(self):
        who = self.who.email()
        if "@" in who and self.confirm(f"Delete every empty folder in {who}'s My Drive?"):
            self.run_steps(self.steps, [(f"Delete empty folders for {who}",
                                         gx.delete_empty_folders_args(who))],
                           lambda _s: self.load())


class FileActivityTab(ToolTab):
    intro = ("Who did what to one file or folder – edits, moves, renames, deletes, "
             "permission changes – from Drive's own activity history.")

    def build(self):
        box, form = self.page.group("File")
        self.owner = PersonField(self.directory, "Owner (or anyone who can see it)")
        self.fid = QLineEdit(placeholderText="file ID or link")
        self.name = QLineEdit(placeholderText="…or the exact file name")
        self.days = QSpinBox()
        self.days.setRange(1, 3650)
        self.days.setValue(30)
        self.days.setSuffix(" days")
        form.addRow("Person", self.owner)
        form.addRow("File", self.fid)
        form.addRow("", self.name)
        form.addRow("Look back", self.days)
        form.addRow("", self.row(button("Show activity", "primary", self.load), self.status))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)

    def load(self):
        import re
        who = self.owner.email()
        fid = self.fid.text().strip()
        m = re.search(r"/d/([A-Za-z0-9_-]{10,})|id=([A-Za-z0-9_-]{10,})", fid)
        if m:
            fid = m.group(1) or m.group(2)
        if "@" not in who or not (fid or self.name.text().strip()):
            self.info("Choose the person and the file.")
            return
        self.read(gx.file_activity_args(who, fid, self.name.text().strip(), self.days.value()),
                  lambda rows: rows is not None and (
                      fill(self.table, gx.file_activity(rows), ["When", "Who", "What", "File"]),
                      self.status.setText(f"{len(rows):,} event(s)")))


# ================================================================== security ===
class AppPasswordsTab(ToolTab):
    intro = ("App passwords let old mail apps sign in without 2-Step Verification – a common "
             "way into an account. See who has them and remove them.")

    def build(self):
        self.ou = OUField(self.directory, "Everyone (or pick an org unit)")
        self.lay.addLayout(self.row(QLabel("People in"), self.ou,
                                    button("Find app passwords", "primary", self.load),
                                    self.status))
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(button("Remove for selected people", "danger",
                                           self.remove)))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def load(self):
        ou = self.ou.path()
        scope = ["ou_and_children", ou] if ou and ou != "/" else ["all", "users"]
        self.read(gx.asps_args(scope), lambda rows: rows is not None and (
            fill(self.table, gx.asps(rows, self.directory.users),
                 ["Person", "Org unit", "App password", "Created", "Last used"]),
            self.status.setText(f"{len(gx.asps(rows)):,} app password(s)")))

    def remove(self):
        who = list(dict.fromkeys(self.table.selected_values("Person")))
        run_or_request(self.page, self.steps, [(f"Remove app passwords for {e}",
                                                gx.delete_asps_args(e)) for e in who],
                       "Remove app passwords", "App passwords get around 2-Step Verification")


class GoogleKeyDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("GAMbit's Google key")
        self.resize(720, 360)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("GAM signs in to Google with a service-account key "
                           "(oauth2service.json). Keys should be replaced every year or so. "
                           "Replacing makes a new key, saves it for GAM and deletes the old "
                           "one.", wordWrap=True))
        self.table = ResultsTable()
        v.addWidget(self.table, 1)
        self.status = QLabel("Checking…", objectName="Muted")
        v.addLayout(page.row(button("Replace the key now", "danger", self.rotate),
                             self.status))
        self.refresh()

    def refresh(self):
        def done(res):
            keys = gx.sakeys(res[1]) if res[0] == 0 else []
            fill(self.table, [{"Key": k["key"], "Created": k["created"], "Expires": k["expires"],
                               "Age (days)": k["age"], "In use": "yes" if k["current"] else ""}
                              for k in keys], ["Key", "Created", "Expires", "Age (days)",
                                               "In use"])
            old = [k for k in keys if (k["age"] or 0) > 365]
            self.status.setText("The key in use is over a year old – replace it." if any(
                k["current"] for k in old) else f"{len(keys)} key(s)")
        Worker(lambda: _text()(gx.SAKEYS_ARGS, 120), on_done=done,
               on_error=lambda e: self.status.setText(str(e)))

    def rotate(self):
        if not self.page.confirm("Replace GAMbit's Google key? GAM saves the new key "
                                 "itself. Other computers using a copy of the old "
                                 "oauth2service.json will need the new file (Settings → "
                                 "Deployment file)."):
            return
        self.status.setText("Replacing…")
        Worker(lambda: _text()(gx.ROTATE_ARGS, 300), on_done=lambda r: (
            self.status.setText("Done ✔" if r[0] == 0 else (r[1] or "")[-160:]),
            self.refresh()), on_error=lambda e: self.status.setText(str(e)))


# ==================================================================== groups ===
class GroupTreeTab(ToolTab):
    intro = ("Why does someone get a group's email? Their groups, and the groups those "
             "groups are inside.")

    def build(self):
        self.who = PersonField(self.directory, "Person")
        self.lay.addLayout(self.row(self.who, button("Show", "primary", self.load),
                                    self.status))
        self.table = ResultsTable()
        self.table.setMinimumHeight(320)
        self.lay.addWidget(self.table, 1)

    def load(self):
        who = self.who.email()
        if "@" in who:
            self.read(gx.grouptree_args(who), lambda rows: rows is not None and (
                fill(self.table, gx.grouptree(rows), ["Group", "Name", "How"]),
                self.status.setText(f"{len(rows)} direct group(s)")))


class GroupSuggestTab(ToolTab):
    intro = ("Groups kept by hand whose members match an org unit, job title or department "
             "almost exactly. Turn them into automatic groups so they stay right. New rules "
             "only add people until you change them on Automatic groups.")

    def build(self):
        self.th = QSpinBox()
        self.th.setRange(50, 100)
        self.th.setValue(85)
        self.th.setSuffix(" % match")
        self.lay.addLayout(self.row(QLabel("At least"), self.th,
                                    button("Find groups", "primary", self.scan), self.status))
        self.table = ResultsTable()
        self.table.setMinimumHeight(300)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(button("Make automatic rules for selected", "primary",
                                           self.make)))
        self.found = []

    def scan(self):
        from ... import group_rules
        from ...tools import group_suggest as gs
        users = self.directory.users

        def got(rows):
            if rows is None:
                return
            self.found = gs.suggest(gs.members_by_group(rows), users, group_rules.load(),
                                    self.th.value() / 100)
            fill(self.table, self.found, ["Group", "Members", "Matches", "Match", "Would add",
                                          "Would remove"])
            self.status.setText(f"{len(self.found)} group(s) could be automatic")
        self.read(gs.MEMBERS_ARGS, got, "Reading every group's members…")

    def make(self):
        from ... import group_rules
        from ...tools import group_suggest as gs
        sel = set(self.table.selected_values("Group"))
        new = [gs.rule_for(s) for s in self.found if s["Group"] in sel]
        if new and self.confirm(f"Add {len(new)} automatic group rule(s) (only adding "
                                "people)?"):
            group_rules.save(group_rules.load() + new)
            self.info("Added – see Groups → Automatic groups to preview and run them.")


# ================================================================= devices ===
class TestReadinessTab(ToolTab):
    intro = ("Days before state testing: is every Chromebook in the testing org units "
             "enrolled, up to date, checking in and (optionally) set up with the testing app?")

    def build(self):
        from ...tools import test_readiness as tr
        o = tr.options()
        box, form = self.page.group("Check")
        self.ous = OUMultiField(self.directory)
        self.ous.set_paths(o["ous"] or tr.ous_from_plans())
        self.minv = QLineEdit(o["min_version"])
        self.minv.setPlaceholderText("e.g. 120 (leave empty to skip)")
        self.sync = QSpinBox()
        self.sync.setRange(1, 90)
        self.sync.setValue(int(o["sync_days"]))
        self.sync.setSuffix(" days")
        self.date = _date_edit(7)
        if o.get("test_date"):
            self.date.setDate(QDate.fromString(o["test_date"], "yyyy-MM-dd"))
        self.app = QLineEdit(o["app_id"])
        self.app.setPlaceholderText("optional – the testing app's ID (kiosk)")
        self.emails = QLineEdit(o["emails"])
        self.emails.setPlaceholderText("optional – who gets the list (test coordinators)")
        form.addRow("Testing org units", self.ous)
        form.addRow("ChromeOS at least", self.minv)
        form.addRow("Checked in within", self.sync)
        form.addRow("Testing starts", self.date)
        form.addRow("Testing app", self.app)
        form.addRow("Email to", self.emails)
        form.addRow("", self.row(button("Check now", "primary", self.check),
                                 button("Email the list", slot=self.email), self.status))
        self.lay.addWidget(box)
        self.places = ResultsTable()
        self.places.setMinimumHeight(140)
        self.lay.addWidget(self.places)
        self.table = ResultsTable()
        self.table.setMinimumHeight(240)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(button("Restart selected (installs a waiting update)",
                                           slot=self.reboot)))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.results = []

    def _opts(self):
        from ...tools import test_readiness as tr
        o = {**tr.options(), "ous": self.ous.paths(), "min_version": self.minv.text().strip(),
             "sync_days": self.sync.value(),
             "test_date": self.date.date().toPython().isoformat(),
             "app_id": self.app.text().strip(), "emails": self.emails.text().strip()}
        tr.save_options(o)
        return o

    def check(self):
        from ...tools import test_readiness as tr
        o = self._opts()
        if not o["ous"]:
            self.info("Choose the testing org units.")
            return

        def work():
            run = _csv()
            rows, app_ok = [], {} if o["app_id"] else None
            for ou in o["ous"]:
                c, r, e = run(tr.devices_args(ou))
                if c != 0:
                    raise RuntimeError(f"{ou}: " + (e or "").strip()[-160:])
                rows += r
                if app_ok is not None:
                    c, r2, _e = run(tr.app_args(ou, o["app_id"]))
                    app_ok[ou] = c == 0 and tr.app_configured(r2)
            return tr.check(rows, o, app_ok=app_ok)

        def done(res):
            self.results = res
            fill(self.places, tr.by_place(res), ["Org unit", "Location", "Devices", "Ready",
                                                 "Not ready"])
            fill(self.table, [r for r in res if not r["ok"]] or res,
                 ["Serial", "Asset", "Location", "Org unit", "ChromeOS", "Last check-in",
                  "Ready", "Problems"])
            bad = sum(1 for r in res if not r["ok"])
            self.status.setText(f"{len(res) - bad} of {len(res)} ready")
        self.status.setText("Checking devices…")
        Worker(work, on_done=done, on_error=lambda e: (self.status.setText(""),
                                                       self.info(str(e))))

    def reboot(self):
        from ...tools import test_readiness as tr
        sns = self.table.selected_values("Serial")
        if sns and self.confirm(f"Restart {len(sns)} Chromebook(s)? Anyone using them will "
                                "lose unsaved work."):
            self.run_steps(self.steps, [(f"Restart {s}", tr.reboot_args(s)) for s in sns])

    def email(self):
        from ... import google_io
        from ...tools import test_readiness as tr
        o = self._opts()
        if not self.results or "@" not in o["emails"]:
            self.info("Check first, and fill in who gets the list.")
            return
        Worker(google_io.send_email, o["emails"], "Testing-day Chromebook check",
               tr.summary_text(self.results, o),
               on_done=lambda _r: self.status.setText("Sent."),
               on_error=lambda e: self.info(str(e)))


class RedistributeTab(ToolTab):
    intro = ("Chromebooks nobody is using at one school while another school is short – "
             "with suggested moves.")

    def build(self):
        from ...tools import redistribute as rd
        o = rd.options()
        box, form = self.page.group("Settings")
        self.droot = OUField(self.directory, "/Chromebooks")
        self.droot.set_path(o["device_root"])
        self.sroot = OUField(self.directory, "/Students")
        self.sroot.set_path(o["student_root"])
        self.idle = QSpinBox()
        self.idle.setRange(7, 365)
        self.idle.setValue(int(o["idle_days"]))
        self.idle.setSuffix(" days without a check-in")
        self.ratio = QDoubleSpinBox()
        self.ratio.setRange(0.1, 3)
        self.ratio.setSingleStep(0.1)
        self.ratio.setValue(float(o["ratio"]))
        self.ratio.setSuffix(" device(s) per student")
        self.use = QCheckBox("Also use Chrome activity (minutes used in the last 30 days)")
        form.addRow("School Chromebooks are under", self.droot)
        form.addRow("Students are under", self.sroot)
        form.addRow("Not used =", self.idle)
        form.addRow("Each school needs", self.ratio)
        form.addRow("", self.use)
        form.addRow("", self.row(button("Find", "primary", self.run), self.status))
        self.lay.addWidget(box)
        self.schools = ResultsTable()
        self.schools.setMinimumHeight(160)
        self.lay.addWidget(self.schools)
        self.table = ResultsTable()
        self.table.setMinimumHeight(220)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self.row(button("Move selected to the new school's org unit",
                                           slot=self.move)))
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)
        self.moves = []

    def run(self):
        from ... import fleet
        from ...tools import redistribute as rd
        o = {**rd.options(), "device_root": self.droot.path() or "/Chromebooks",
             "student_root": self.sroot.path() or "/Students", "idle_days": self.idle.value(),
             "ratio": self.ratio.value()}
        rd.save_options(o)
        users, use = self.directory.users, self.use.isChecked()

        def work():
            run = _csv()
            c, rows, e = run(["print", "cros", "fields", fleet.FIELDS])
            if c != 0:
                raise RuntimeError((e or "").strip()[-200:])
            mins = None
            if use:
                c, r2, _e = run(gx.activity_args(o["device_root"]))
                mins = gx.active_minutes(r2) if c == 0 else None
            return rd.plan(fleet.devices(rows), users, o, mins)

        def done(res):
            rows, self.moves = res
            fill(self.schools, rows, ["School", "Students", "Used", "Not used", "Needed",
                                      "Short", "Could give"])
            fill(self.table, self.moves, ["Serial", "Asset", "Model", "From", "To", "Why"])
            self.status.setText(f"{len(self.moves)} suggested move(s)")
        self.status.setText("Reading Chromebooks…")
        Worker(work, on_done=done, on_error=lambda e: (self.status.setText(""),
                                                       self.info(str(e))))

    def move(self):
        sel = set(self.table.selected_values("Serial"))
        steps = [(f"{m['Serial']}: {m['From']} → {m['To']}", m["args"]) for m in self.moves
                 if m["Serial"] in sel]
        run_or_request(self.page, self.steps, steps, "Move Chromebooks between schools",
                       "Redistribution")


# ================================================================== policies ===
class PolicyCleanupDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Policy override clean-up")
        self.resize(1000, 600)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Chrome policies set on an org unit with exactly the value it gets "
                           "from its parent anyway. Removing them changes nothing today, but "
                           "later changes at the parent will reach these org units.",
                           wordWrap=True))
        self.ous = OUMultiField(page.directory)
        self.status = QLabel("", objectName="Muted")
        v.addLayout(page.row(QLabel("Org units"), self.ous,
                             button("Scan", "primary", self.scan), self.status))
        self.table = ResultsTable()
        v.addWidget(self.table, 1)
        v.addLayout(page.row(button("Remove selected overrides", "danger", self.remove)))
        from ..steps import StepList
        self.steps = StepList(page)
        self.steps.setMaximumHeight(140)
        v.addWidget(self.steps)
        self.found = []

    def scan(self):
        from ...tools import policy_cleanup as pc
        ous = self.ous.paths()
        if self.ous.sub.isChecked():
            ous = [o for o in self.page.directory.ous if any(
                o == p or o.startswith(p.rstrip("/") + "/") for p in ous)] or ous
        self.status.setText(f"Reading {len(ous)} org unit(s)…")

        def done(res):
            self.found, probs = res
            fill(self.table, self.found, ["Org unit", "Policy", "Value", "Same as"])
            self.status.setText(f"{len(self.found)} redundant override(s)" +
                                (f" · {len(probs)} problem(s)" if probs else ""))
        Worker(pc.scan, ous, _csv(), on_done=done, on_error=lambda e: self.status.setText(
            str(e)))

    def remove(self):
        rows = self.table.selected_dicts()
        keys = {(r["Org unit"], r["Policy"]) for r in rows}
        steps = [(f"{f['Org unit']}: {f['Policy']}", f["args"]) for f in self.found
                 if (f["Org unit"], f["Policy"]) in keys]
        run_or_request(self.page, self.steps, steps, "Remove redundant policy overrides",
                       "Same value as the parent org unit")


def user_counts_dialog(page):
    d = QDialog(page)
    d.setWindowTitle("People per org unit")
    d.resize(700, 600)
    v = QVBoxLayout(d)
    t = ResultsTable()
    st = QLabel("Counting…", objectName="Muted")
    v.addWidget(st)
    v.addWidget(t, 1)

    def done(res):
        c, rows, e = res
        if c != 0:
            st.setText((e or "").strip()[-200:])
            return
        counts = gx.usercounts(rows)
        fill(t, [{"Org unit": k, **v2} for k, v2 in sorted(counts.items())],
             ["Org unit", "active", "suspended", "archived", "total"])
        st.setText(f"{sum(x['total'] for x in counts.values()):,} accounts in "
                   f"{len(counts)} org unit(s)")
    Worker(lambda: _csv()(gx.USERCOUNTS_ARGS), on_done=done,
           on_error=lambda e: st.setText(str(e)))
    d.exec()


def alert_feedback(page, table, how: str):
    ids = page._selected(table, "alertId", "alert")
    if ids:
        page.run_many([gx.alert_feedback_args(i, how) for i in ids],
                      lambda _o: page.info(f"Feedback sent for {len(ids)} alert(s)."),
                      quiet=False)


__all__ = ["PersonalAccountsTab", "CalendarsTab", "ClassInvitesTab", "BrowserVersionsDialog",
           "PolicyImageDialog", "SharingExposureTab", "SharedDriveSettingsTab",
           "EmptyFoldersTab", "FileActivityTab", "AppPasswordsTab", "GoogleKeyDialog",
           "GroupTreeTab", "GroupSuggestTab", "TestReadinessTab", "RedistributeTab",
           "PolicyCleanupDialog", "user_counts_dialog", "alert_feedback"]
