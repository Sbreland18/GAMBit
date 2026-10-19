"""More services → Chat spaces, Room usage;  Email → Labels, S/MIME."""

from __future__ import annotations

import datetime

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QDateEdit, QFileDialog, QGroupBox, QLabel, QLineEdit, QVBoxLayout,
)

from ... import google_io
from ..pickers import GroupField, PersonField, TargetPicker
from ..tools_base import ToolTab
from ..widgets import ResultsTable, button


def _space(text: str) -> str:
    t = text.strip()
    if t.startswith("https://"):
        t = "spaces/" + t.rstrip("/").split("/")[-1].split("?")[0]
    return t if t.startswith("spaces/") else f"spaces/{t}"


# ================================================================ chat spaces ===
class ChatSpacesTab(ToolTab):
    intro = ("Create Google Chat spaces (for example one per school or department) and keep "
             "their members in step with a group. Spaces are created as the person below, "
             "who becomes the space manager.")

    def build(self):
        self.as_user = PersonField(self.directory, "Create and manage as (a person)")
        self.as_user.setText(google_io.admin_email())
        self.lay.addLayout(self.row(QLabel("Acting as"), self.as_user,
                                    button("List my spaces", slot=self.list_spaces),
                                    stretch=False))
        box, form = self.page.group("New space")
        self.name = QLineEdit(placeholderText="e.g. Lincoln Elementary Staff")
        self.desc = QLineEdit(placeholderText="optional")
        self.group = GroupField(self.directory, "Add the members of this group")
        self.announce = QCheckBox("Announcement space (only managers can post)")
        form.addRow("Name", self.name)
        form.addRow("Description", self.desc)
        form.addRow("Members", self.group)
        form.addRow("", self.announce)
        form.addRow("", self.row(button("Create space", "primary", self.create)))
        self.lay.addWidget(box)
        box, form = self.page.group("Keep a space's members in step with a group")
        self.s_space = QLineEdit(placeholderText="Space link or spaces/AAAA…")
        self.s_group = GroupField(self.directory, "Group")
        self.addonly = QCheckBox("Only add people (never remove)")
        self.addonly.setChecked(True)
        form.addRow("Space", self.s_space)
        form.addRow("Group", self.s_group)
        form.addRow("", self.addonly)
        form.addRow("", self.row(button("Sync members", slot=self.sync)))
        self.lay.addWidget(box)
        self.lay.addWidget(self.status)
        self.table = ResultsTable()
        self.table.setMinimumHeight(220)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def _user(self):
        u = self.as_user.email()
        if "@" not in u:
            self.info("Choose who to act as.")
            return ""
        return u

    def list_spaces(self):
        u = self._user()
        if u:
            self.read(["user", u, "print", "chatspaces"], lambda rows: rows is not None and
                      self.table.set_rows(list(rows[0].keys()) if rows else ["(no spaces)"],
                                          [list(r.values()) for r in rows]))

    def create(self):
        u = self._user()
        if not u or not self.name.text().strip():
            self.info("Give the space a name.")
            return
        a = ["user", u, "create", "chatspace", "type", "space",
             "announcement" if self.announce.isChecked() else "collaboration",
             "displayname", self.name.text().strip()]
        if self.desc.text().strip():
            a += ["description", self.desc.text().strip()]
        if "@" in self.group.email():
            a += ["members", "group", self.group.email()]
        self.run_steps(self.steps, [(f"Create space “{self.name.text().strip()}”", a)],
                       lambda _s: self.list_spaces())

    def sync(self):
        u, sp, g = self._user(), self.s_space.text().strip(), self.s_group.email()
        if not u or not sp or "@" not in g:
            self.info("Fill in the space and the group.")
            return
        a = ["user", u, "sync", "chatmembers", _space(sp)]
        if self.addonly.isChecked():
            a.append("addonly")
        a += ["users", "group", g]
        self.run_steps(self.steps, [(f"Sync {sp} with {g}", a)])


# ================================================================= room usage ===
class RoomUsageTab(ToolTab):
    intro = "How often each room and resource is booked, and for how many hours."

    def build(self):
        self.start = QDateEdit(QDate.currentDate().addDays(-30))
        self.end = QDateEdit(QDate.currentDate())
        for d in (self.start, self.end):
            d.setCalendarPopup(True)
        self.lay.addLayout(self.row(QLabel("From"), self.start, QLabel("to"), self.end,
                                    button("Build the report", "primary", self.load),
                                    self.status, stretch=False))
        self.table = ResultsTable()
        self.table.setMinimumHeight(380)
        self.lay.addWidget(self.table, 1)

    def load(self):
        a, b = self.start.date().toPython(), self.end.date().toPython()
        if b < a:
            self.info("The end date is before the start.")
            return

        def got(rows):
            if rows is None:
                return
            res = []
            for r in rows:
                low = {(k or "").lower(): v for k, v in r.items()}
                if low.get("resourceemail"):
                    res.append((low.get("resourcename", low["resourceemail"]),
                                low["resourceemail"], low.get("buildingid", "")))
            if not res:
                self.status.setText("No rooms or resources found.")
                return
            self.read_many([room_events_args(e, a, b) for _n, e, _b in res],
                           lambda results: self._show(res, results),
                           f"Reading {len(res)} calendar(s)…")
        self.read(["print", "resources", "fields",
                   "resourceemail,resourcename,buildingid"], got)

    def _show(self, res, results):
        rows = [room_usage(name, bld, events) for (name, _e, bld), events in zip(res, results)]
        rows.sort(key=lambda x: -float(x["Hours"]))
        h = ["Room / resource", "Building", "Bookings", "Hours", "Busiest day"]
        self.table.set_rows(h, [[r[k] for k in h] for r in rows])
        self.status.setText(f"{len(rows)} room(s)")


def room_events_args(email: str, a: datetime.date, b: datetime.date) -> list[str]:
    return ["calendar", email, "print", "events", "after", f"{a.isoformat()}T00:00:00Z",
            "before", f"{(b + datetime.timedelta(days=1)).isoformat()}T00:00:00Z",
            "singleevents", "fields", "start,end,summary"]


def room_usage(name: str, building: str, events: list[dict]) -> dict:
    hours, days = 0.0, {}
    n = 0
    for e in events:
        low = {(k or "").lower(): v or "" for k, v in e.items()}
        s = low.get("start.datetime", "")
        t = low.get("end.datetime", "")
        if not s or not t:
            continue
        try:
            ds = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
            de = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
        except ValueError:
            continue
        n += 1
        hours += max(0.0, (de - ds).total_seconds() / 3600)
        day = ds.strftime("%A")
        days[day] = days.get(day, 0) + 1
    busiest = max(days, key=days.get) if days else ""
    return {"Room / resource": name, "Building": building, "Bookings": str(n),
            "Hours": f"{hours:.1f}", "Busiest day": busiest}


# ===================================================================== labels ===
class LabelsTab(ToolTab):
    intro = ("Add or remove a Gmail label for many people at once – for example “Parent "
             "contacts” or “IEP/2026” (use / for nested labels).")

    def build(self):
        box = QGroupBox("Who")
        v = QVBoxLayout(box)
        self.who = TargetPicker(self.directory)
        v.addWidget(self.who)
        self.lay.addWidget(box)
        self.name = QLineEdit(placeholderText="Label name, e.g. Parent contacts or IEP/2026")
        self.lay.addLayout(self.row(QLabel("Label"), self.name,
                                    button("Add label", "primary", self.add),
                                    button("Remove label", "danger", self.remove),
                                    stretch=False))
        self.person = PersonField(self.directory, "See one person's labels")
        self.lay.addLayout(self.row(self.person, button("Show labels", slot=self.show),
                                    stretch=False))
        self.table = ResultsTable()
        self.table.setMinimumHeight(220)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def _go(self, verb):
        ents, n = self.who.entities(), self.name.text().strip()
        if not ents or not n:
            self.info("Choose who and type the label name.")
            return
        if verb == "delete" and not self.confirm(f"Remove the label “{n}” for "
                                                 f"{self.who.describe()}? Messages keep their "
                                                 "other labels."):
            return
        steps = [(f"{'Add' if verb == 'create' else 'Remove'} “{n}” for {' '.join(e)}",
                  [*e, "create", "label", n, "buildpath", "true"] if verb == "create"
                  else [*e, "delete", "label", n]) for e in ents]
        self.run_steps(self.steps, steps)

    def add(self):
        self._go("create")

    def remove(self):
        self._go("delete")

    def show(self):
        p = self.person.email()
        if "@" in p:
            self.read(["user", p, "print", "labels"], lambda rows: rows is not None and
                      self.table.set_rows(list(rows[0].keys()) if rows else ["(no labels)"],
                                          [list(r.values()) for r in rows]))


# ===================================================================== S/MIME ===
class SmimeTab(ToolTab):
    intro = ("S/MIME lets someone sign and encrypt email with a certificate. Upload their "
             "certificate (.p12 or .pfx with its password) here. Only needed if your district "
             "uses encrypted email.")

    def build(self):
        box, form = self.page.group("Certificate")
        self.who = PersonField(self.directory, "Whose certificate?")
        self.file = QLineEdit(placeholderText="certificate.p12")
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("Certificate password (if it has one)")
        self.default = QCheckBox("Use it by default")
        self.default.setChecked(True)
        form.addRow("Person", self.who)
        form.addRow("File", self.row(self.file, button("Browse…", slot=self._browse),
                                     stretch=False))
        form.addRow("Password", self.pw)
        form.addRow("", self.default)
        form.addRow("", self.row(button("Upload certificate", "primary", self.upload),
                                 button("Show certificates", slot=self.show),
                                 button("Remove default certificate", "danger", self.delete)))
        self.lay.addWidget(box)
        self.table = ResultsTable()
        self.table.setMinimumHeight(200)
        self.lay.addWidget(self.table, 1)
        self.steps = self.steps_list()
        self.lay.addWidget(self.steps)

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Certificate", "", "Certificates (*.p12 *.pfx)")
        if p:
            self.file.setText(p)

    def upload(self):
        u, f = self.who.email(), self.file.text().strip()
        if "@" not in u or not f:
            self.info("Choose the person and the certificate file.")
            return
        a = ["user", u, "add", "smime", "file", f]
        if self.pw.text():
            a += ["password", self.pw.text()]
        if self.default.isChecked():
            a.append("default")
        self.run_steps(self.steps, [(f"Upload S/MIME certificate for {u}", a)],
                       lambda _s: (self.pw.clear(), self.show()))

    def show(self):
        u = self.who.email()
        if "@" in u:
            self.read(["user", u, "print", "smimes"], lambda rows: rows is not None and
                      self.table.set_rows(list(rows[0].keys()) if rows else ["(none)"],
                                          [list(r.values()) for r in rows]))

    def delete(self):
        u = self.who.email()
        if "@" in u and self.confirm(f"Remove {u}'s default S/MIME certificate?"):
            self.run_steps(self.steps, [(f"Remove S/MIME certificate for {u}",
                                         ["user", u, "delete", "smime"])])
