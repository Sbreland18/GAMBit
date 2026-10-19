"""Less common areas: Calendar, Vault, Chrome, admin roles, mobile, alerts,
custom fields, contacts/directory, Chat & Meet.

Each tab has the everyday actions plus a link to every related command in the
Command Builder. Syntax comes from GamCommands.txt.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from ..pickers import OUField, PeoplePicker, PersonField
from ..widgets import Page, ResultsTable, button

CAL_ROLES = [("See all event details", "reader"), ("See only free/busy", "freebusyreader"),
             ("Make changes to events", "writer"), ("Make changes and manage sharing", "owner")]
CORPUS = [("Gmail", "mail"), ("Drive", "drive"), ("Groups", "groups"),
          ("Chat", "hangouts_chat"), ("Calendar", "calendar"), ("Voice", "voice")]


class ServicesPage(Page):
    title = "More services"
    subtitle = ("Calendar, Vault, Chrome, admin roles, mobile devices, alerts, custom fields, "
                "the directory, and Chat & Meet.")

    def build(self):
        self.tabs = QTabWidget()
        for label, fn in [("Calendar", self._calendar), ("Vault", self._vault),
                          ("Chrome", self._chrome), ("Admin roles", self._roles),
                          ("Mobile devices", self._mobile), ("Alerts", self._alerts),
                          ("Custom fields", self._schemas),
                          ("Contacts && directory", self._contacts),
                          ("Chat && Meet", self._chatmeet)]:
            self.tabs.addTab(fn(), label)
        self._roles_loaded = False

        def _tab_changed(i):
            if self.tabs.tabText(i) == "Admin roles" and not self._roles_loaded:
                self._roles_loaded = True
                self.load_roles()
        self.tabs.currentChanged.connect(_tab_changed)
        from .more_tabs import ContactsTab
        self.contacts_tab = ContactsTab(self)
        self.tabs.addTab(self.contacts_tab, "Shared contacts")
        from .recovery_tabs import DomainsTab
        self.domains_tab = DomainsTab(self)
        self.tabs.addTab(self.domains_tab, "Domains")
        from .small_tabs import ChatSpacesTab, RoomUsageTab
        self.chat_tab, self.rooms_tab = ChatSpacesTab(self), RoomUsageTab(self)
        self.tabs.addTab(self.chat_tab, "Chat spaces")
        self.tabs.addTab(self.rooms_tab, "Room usage")
        from .round13_tabs import CalendarsTab
        self.calcheck_tab = CalendarsTab(self)
        self.tabs.addTab(self.calcheck_tab, "Calendar sharing && out of office")
        from .round14_tabs import ChatModerationTab, FormResponsesTab, TrustedDomainsTab
        self.forms_tab, self.trusted_tab, self.chatmod_tab = (
            FormResponsesTab(self), TrustedDomainsTab(self), ChatModerationTab(self))
        self.tabs.addTab(self.forms_tab, "Form responses")
        self.tabs.addTab(self.trusted_tab, "Trusted domains")
        self.tabs.addTab(self.chatmod_tab, "Chat moderation")
        from .round15_tabs import RoomFeaturesTab, WorkingLocationTab
        self.features_tab, self.workloc_tab = RoomFeaturesTab(self), WorkingLocationTab(self)
        self.tabs.addTab(self.features_tab, "Room features")
        self.tabs.addTab(self.workloc_tab, "Working locations")
        self.body.addWidget(self.tabs, 1)

    # -------------------------------------------------------------- helpers ---
    def _tab(self, builder_query: str, section: str = ""):
        outer = QWidget(objectName="Page")
        ov = QVBoxLayout(outer)
        ov.setContentsMargins(0, 6, 0, 0)
        top = QHBoxLayout()
        ov.addLayout(top)
        table = ResultsTable()
        ov.addWidget(table, 1)
        more = button("All related commands in the Command Builder →",
                      slot=lambda: self.app.open_builder(builder_query, section))
        ov.addLayout(self.row(more))
        return outer, top, table

    def _load(self, table: ResultsTable, args):
        self.run(args, lambda c, out, _e: table.load_csv(out) if c == 0 else None, quiet=True)

    @staticmethod
    def _combo(pairs, current=0):
        cb = QComboBox()
        for label, val in pairs:
            cb.addItem(label, val)
        cb.setCurrentIndex(current)
        return cb

    def _selected(self, table, column, what="item"):
        vals = table.selected_values(column)
        if not vals:
            # tolerate header case differences
            col = next((h for h in table._headers if h.lower() == column.lower()), None)
            vals = table.selected_values(col) if col else []
        if not vals:
            self.info(f"Load the list, then select the {what}(s) first.")
        return vals

    # ============================================================ calendar ===
    def _calendar(self):
        w, top, self.cal_t = self._tab("calendar acl", "")
        box, form = self.group("Rooms and resources")
        form.addRow(self.row(button("List rooms && resources", "primary",
                                    lambda: self._load(self.cal_t, ["print", "resources"])),
                             button("List buildings",
                                    slot=lambda: self._load(self.cal_t, ["print", "buildings"]))))
        self.r_id = QLineEdit(placeholderText="Short ID, e.g. lib-room-1")
        self.r_name = QLineEdit(placeholderText="Library Conference Room")
        self.r_cap = QSpinBox()
        self.r_cap.setRange(0, 5000)
        self.r_cat = self._combo([("Conference room", "conference_room"), ("Room", "room"),
                                  ("Other (equipment, cart…)", "other")])
        form.addRow("New resource ID", self.r_id)
        form.addRow("Name", self.r_name)
        form.addRow("Capacity", self.r_cap)
        form.addRow("Kind", self.r_cat)
        form.addRow("", self.row(button("Create resource", slot=self.create_resource),
                                 button("Import rooms from a spreadsheet…",
                                        slot=self.import_rooms)))
        top.addWidget(box, 1)

        box, form = self.group("Share a calendar")
        self.c_cal = PersonField(self.directory, "Calendar (person's email or calendar ID)")
        self.c_who = PersonField(self.directory, "Share with (email, group) – or type domain",
                                 include_groups=True)
        self.c_role = self._combo(CAL_ROLES)
        form.addRow("Calendar", self.c_cal)
        form.addRow("Share with", self.c_who)
        form.addRow("They can", self.c_role)
        form.addRow("", self.row(button("Share", "primary", self.share_calendar),
                                 button("Show who has access", slot=self.show_cal_acl)))
        hint = QLabel("Tip: rooms have calendar IDs too – list resources and copy the "
                      "resourceEmail.", objectName="Muted")
        hint.setWordWrap(True)
        form.addRow("", hint)
        top.addWidget(box, 1)

        box, form = self.group("Calendars in bulk")
        for label, slot in (("Add an event to many calendars…", self.cal_event),
                            ("Events GAMbit added (remove them)…", self.cal_batches),
                            ("Add a calendar to people's lists…", self.cal_subscribe),
                            ("Cancel a leaver's future meetings…", self.cal_leaver)):
            form.addRow(button(label, slot=slot))
        top.addWidget(box, 1)
        return w

    def _cal_dialog(self, cls, done=None):
        from . import misc_tabs as mt
        run_dialog = mt.run_dialog_steps
        dlg = cls(self)
        run_dialog(self, dlg, done=lambda: done(dlg) if done else None)

    def cal_event(self):
        from .misc_tabs import EventDialog
        self._cal_dialog(EventDialog)

    def cal_batches(self):
        from .misc_tabs import BatchesDialog
        from ...tools import calendar_class as cc
        from ...gam_runner import dry_run_on
        self._cal_dialog(BatchesDialog, lambda d: getattr(d, "_forget", None) and
                         not dry_run_on() and cc.forget_batch(d._forget))

    def cal_subscribe(self):
        from .misc_tabs import SubscribeDialog
        self._cal_dialog(SubscribeDialog)

    def cal_leaver(self):
        from .misc_tabs import LeaverMeetingsDialog
        self._cal_dialog(LeaverMeetingsDialog)

    def new_role(self):
        from .misc_tabs import run_dialog_steps
        from .recovery_tabs import AdminRoleDialog
        run_dialog_steps(self, AdminRoleDialog(self))

    def import_rooms(self):
        from ..rooms_dialog import RoomsImportDialog
        RoomsImportDialog(self).exec()
        self._load(self.cal_t, ["print", "resources"])

    def create_resource(self):
        rid, name = self.r_id.text().strip(), self.r_name.text().strip()
        if not rid or not name:
            self.info("A resource needs an ID and a name.")
            return
        args = ["create", "resource", rid, name, "category", self.r_cat.currentData()]
        if self.r_cap.value():
            args += ["capacity", str(self.r_cap.value())]
        self.run(args, lambda c, *_: c == 0 and self._load(self.cal_t, ["print", "resources"]))

    def share_calendar(self):
        cal, who = self.c_cal.email(), self.c_who.email()
        if not cal or not who:
            self.info("Choose the calendar and who to share it with.")
            return
        scope = "domain" if who.lower() == "domain" else who
        self.run(["calendars", cal, "add", "acls", self.c_role.currentData(), scope],
                 lambda *_: self.show_cal_acl())

    def show_cal_acl(self):
        cal = self.c_cal.email()
        if cal:
            self._load(self.cal_t, ["calendars", cal, "print", "acls"])

    # =============================================================== vault ===
    def _vault(self):
        w, top, self.v_t = self._tab("vault", "Vault/Takeout")
        box, form = self.group("Matters")
        self.vm_name = QLineEdit(placeholderText="e.g. 2026-Records request – J. Smith")
        self.vm_desc = QLineEdit(placeholderText="Description (optional)")
        form.addRow("New matter", self.vm_name)
        form.addRow("Description", self.vm_desc)
        form.addRow("", self.row(button("Create matter", "primary", self.create_matter),
                                 button("List matters", slot=lambda: self._load(
                                     self.v_t, ["print", "vaultmatters"])),
                                 button("Close selected matter", slot=self.close_matter)))
        top.addWidget(box, 1)

        box, form = self.group("Holds and exports")
        self.vh_matter = QLineEdit(placeholderText="Matter name or ID (select one in the list)")
        self.vh_corpus = self._combo(CORPUS)
        self.vh_people = PeoplePicker(self.directory, include_groups=False)
        self.vh_ou = OUField(self.directory, "…or an org unit")
        self.vh_terms = QLineEdit(placeholderText="Search terms for exports (optional)")
        form.addRow("Matter", self.row(self.vh_matter, button("Use selected",
                                                              slot=self._use_matter),
                                       stretch=False))
        form.addRow("Data", self.vh_corpus)
        form.addRow("Accounts", self.vh_people)
        form.addRow("", self.vh_ou)
        form.addRow("Search terms", self.vh_terms)
        form.addRow("", self.row(button("Place hold", "primary", self.create_hold),
                                 button("List holds", slot=self.list_holds),
                                 button("Start export", slot=self.create_export),
                                 button("List exports", slot=self.list_exports),
                                 button("Download selected export…", slot=self.download_export)))
        form.addRow("", self.row(button("Count matching mail first", slot=self.vault_count),
                                 button("Holds covering a person…", slot=self.vault_person)))
        top.addWidget(box, 2)
        return w

    def _use_matter(self):
        vals = self._selected(self.v_t, "matterId", "matter")
        if vals:
            self.vh_matter.setText(vals[0])

    def create_matter(self):
        n = self.vm_name.text().strip()
        if not n:
            self.info("Give the matter a name.")
            return
        args = ["create", "vaultmatter", "name", n]
        if self.vm_desc.text().strip():
            args += ["description", self.vm_desc.text().strip()]
        self.run(args, lambda *_: self._load(self.v_t, ["print", "vaultmatters"]))

    def close_matter(self):
        ids = self._selected(self.v_t, "matterId", "matter")
        if ids and self.confirm(f"Close {len(ids)} matter(s)? Holds in them are released."):
            self.run_many([["close", "vaultmatter", i] for i in ids],
                          lambda _o: self._load(self.v_t, ["print", "vaultmatters"]), quiet=False)

    def _scope(self) -> list[str] | None:
        people = self.vh_people.emails()
        if people:
            return ["accounts", ",".join(people)]
        if self.vh_ou.path():
            return ["orgunit", self.vh_ou.path()]
        return None

    def _matter(self):
        m = self.vh_matter.text().strip()
        if not m:
            self.info("Choose the matter first.")
        return m

    def create_hold(self):
        m, scope = self._matter(), self._scope()
        if not m:
            return
        if not scope:
            self.info("Add the accounts, or choose an org unit, to hold.")
            return
        self.run(["create", "vaulthold", "matter", m, "corpus", self.vh_corpus.currentData(),
                  *scope], lambda *_: self.list_holds())

    def vault_count(self):
        from ...tools import more_tools as mt
        m = self._matter()
        if not m:
            return
        args = mt.vault_count_args(m, self.vh_people.emails(), self.vh_ou.path(),
                                   self.vh_terms.text().strip(), "", "")
        self._load(self.v_t, args)

    def vault_person(self):
        from PySide6.QtWidgets import QInputDialog
        from ...tools import more_tools as mt
        email, ok = QInputDialog.getText(self, "Holds covering a person", "Email address:")
        if not ok or "@" not in email:
            return

        def done(code, out, _e):
            if code != 0:
                return
            import csv as _csv
            import io as _io
            rows = mt.holds_for(list(_csv.DictReader(_io.StringIO(out or ""))))
            self.v_t.set_rows(["Matter", "Hold", "Covers them through"],
                              [[r["Matter"], r["Hold"], r["Covers them through"]] for r in rows])
            if not rows:
                self.info(f"No Vault holds cover {email.strip()}.")
        self.runner.run(mt.holds_args(email.strip()), done, quiet_stdout=True)

    def list_holds(self):
        args = ["print", "vaultholds"]
        if self.vh_matter.text().strip():
            args += ["matters", self.vh_matter.text().strip()]
        self._load(self.v_t, args)

    def create_export(self):
        m = self._matter()
        if not m:
            return
        scope = self._scope() or ["everyone"]
        if scope == ["everyone"] and not self.confirm("Export data for EVERYONE?"):
            return
        args = ["create", "vaultexport", "matter", m, "corpus", self.vh_corpus.currentData(),
                *scope]
        if self.vh_terms.text().strip():
            args += ["terms", self.vh_terms.text().strip()]
        self.run(args, lambda *_: self.list_exports())

    def list_exports(self):
        args = ["print", "vaultexports"]
        if self.vh_matter.text().strip():
            args += ["matters", self.vh_matter.text().strip()]
        self._load(self.v_t, args)

    def download_export(self):
        rows = sorted({i.row() for i in self.v_t.table.selectedIndexes()})
        if not rows:
            self.info("List exports, then select a finished export.")
            return
        r = self.v_t.row_dict(rows[0])
        eid = next((v for k, v in r.items() if k.lower() == "id"), "")
        mid = next((v for k, v in r.items() if k.lower() == "matterid"), "")
        folder = QFileDialog.getExistingDirectory(self, "Save export to")
        if eid and mid and folder:
            self.run(["download", "vaultexport", eid, "matter", mid, "targetfolder", folder])

    # ============================================================== chrome ===
    def _chrome(self):
        w, top, self.ch_t = self._tab("chrome", "")
        box, form = self.group("Chrome browsers (managed Chrome on PCs and Macs)")
        self.ch_ou = OUField(self.directory, "Org unit (blank = all)")
        form.addRow("Org unit", self.ch_ou)
        form.addRow("", self.row(button("List browsers", "primary", self.list_browsers),
                                 button("Create enrollment token", slot=self.browser_token)))
        self.ch_move = OUField(self.directory, "Move selected browsers to…")
        form.addRow("Move to", self.row(self.ch_move, button("Move", slot=self.move_browsers),
                                        stretch=False))
        top.addWidget(box, 1)
        box, form = self.group("Policies and fleet health")
        self.cp_ou = OUField(self.directory, "Org unit")
        form.addRow("Org unit", self.cp_ou)
        form.addRow("", self.row(button("Show Chrome policies", slot=self.show_policies)))
        form.addRow("", self.row(
            button("End-of-updates counts", slot=lambda: self._load(self.ch_t,
                                                                    ["print", "chromeaues"])),
            button("Devices needing attention",
                   slot=lambda: self._load(self.ch_t, ["print", "chromeneedsattn"]))))
        top.addWidget(box, 1)
        return w

    def list_browsers(self):
        args = ["print", "browsers"]
        if self.ch_ou.path():
            args += ["ou", self.ch_ou.path()]
        self._load(self.ch_t, args)

    def browser_token(self):
        args = ["create", "browsertoken"]
        if self.ch_ou.path():
            args += ["ou", self.ch_ou.path()]
        self.run(args)

    def move_browsers(self):
        ids = self._selected(self.ch_t, "deviceId", "browser")
        ou = self.ch_move.path()
        if ids and ou:
            self.run(["move", "browsers", "ou", ou, "ids", ",".join(ids)],
                     lambda *_: self.list_browsers())
        elif ids:
            self.info("Choose where to move them.")

    def show_policies(self):
        ou = self.cp_ou.path()
        if not ou:
            self.info("Choose an org unit.")
            return
        self._load(self.ch_t, ["print", "chromepolicies", "ou", ou])

    # =============================================================== roles ===
    def _roles(self):
        w, top, self.ro_t = self._tab("admin", "Administrators")
        box, form = self.group("Who has admin rights")
        form.addRow(self.row(button("List admins", "primary", lambda: self._load(
                                 self.ro_t, ["print", "admins"])),
                             button("List roles", slot=lambda: self._load(
                                 self.ro_t, ["print", "adminroles"])),
                             button("Remove selected admin assignment", "danger",
                                    self.remove_admin)))
        top.addWidget(box, 1)
        box, form = self.group("Make someone an admin")
        self.ad_user = PersonField(self.directory, "Person or group")
        self.ad_role = QComboBox()
        self.ad_role.setMinimumWidth(320)
        self.ad_role.currentIndexChanged.connect(self._role_changed)
        self.ad_role_desc = QLabel("", wordWrap=True)
        self.ad_role_desc.setMinimumHeight(40)
        self._fill_roles([])
        self.ad_ou = OUField(self.directory, "Limit to an org unit (blank = whole domain)")
        form.addRow("Person", self.ad_user)
        form.addRow("Role", self.row(self.ad_role,
                                     button("Refresh roles", slot=self.load_roles),
                                     button("What can it do?", slot=self.role_privileges),
                                     stretch=False))
        form.addRow("", self.ad_role_desc)
        form.addRow("Where", self.ad_ou)
        form.addRow("", self.row(button("Assign role", "primary", self.assign_admin),
                                 button("New custom role…", slot=self.new_role)))
        top.addWidget(box, 1)
        return w

    def _fill_roles(self, rows: list[dict]):
        from ...tools.admin_roles import role_choices
        cur = self.ad_role.currentData()
        self.ad_role.blockSignals(True)
        self.ad_role.clear()
        for r in role_choices(rows):
            self.ad_role.addItem(r["label"], r["name"])
            self.ad_role.setItemData(self.ad_role.count() - 1, r["description"],
                                     Qt.ToolTipRole)
        self.ad_role.blockSignals(False)
        i = self.ad_role.findData(cur) if cur else -1
        self.ad_role.setCurrentIndex(i if i >= 0 else 0)
        self._role_changed()

    def _role_changed(self, *_):
        i = self.ad_role.currentIndex()
        d = self.ad_role.itemData(i, Qt.ToolTipRole) if i >= 0 else ""
        self.ad_role_desc.setText(d or "")

    def load_roles(self):
        import csv
        import io

        def done(code, out, _e):
            if code == 0:
                self._fill_roles(list(csv.DictReader(io.StringIO(out or ""))))
        self.run(["print", "adminroles"], done, quiet=True)

    def role_privileges(self):
        role = self.ad_role.currentData()
        if role:
            self._load(self.ro_t, ["print", "adminroles", "role", role, "privileges",
                                   "oneitemperrow"])

    def assign_admin(self):
        u, role = self.ad_user.email(), (self.ad_role.currentData() or "").strip()
        if "@" not in u or not role:
            self.info("Choose the person and the role.")
            return
        where = ["org_unit", self.ad_ou.path()] if self.ad_ou.path() else ["customer"]
        if "SEED" in role.upper() and not self.confirm(f"Make {u} a SUPER ADMIN?"):
            return
        self.run(["create", "admin", u, role, *where],
                 lambda *_: self._load(self.ro_t, ["print", "admins"]))

    def remove_admin(self):
        ids = self._selected(self.ro_t, "roleAssignmentId", "admin assignment")
        if ids and self.confirm(f"Remove {len(ids)} admin assignment(s)?"):
            self.run_many([["delete", "admin", i] for i in ids],
                          lambda _o: self._load(self.ro_t, ["print", "admins"]), quiet=False)

    # ============================================================== mobile ===
    def _mobile(self):
        w, top, self.mo_t = self._tab("mobile", "Mobile Devices")
        box, form = self.group("Phones and tablets that sync school accounts")
        self.mo_q = QLineEdit(placeholderText="Search (optional), e.g. email:jdoe or model:pixel")
        form.addRow("Search", self.mo_q)
        form.addRow("", self.row(button("List devices", "primary", self.list_mobile)))
        form.addRow("Selected devices", self.row(
            button("Approve", slot=lambda: self.mobile_action("approve")),
            button("Block", slot=lambda: self.mobile_action("block")),
            button("Remove school account", "danger",
                   lambda: self.mobile_action("admin_account_wipe")),
            button("Factory reset…", "danger", lambda: self.mobile_action("admin_remote_wipe")),
            button("Delete from list", "danger", self.delete_mobile)))
        top.addWidget(box, 1)
        return w

    def list_mobile(self):
        args = ["print", "mobile"]
        if self.mo_q.text().strip():
            args += ["query", self.mo_q.text().strip()]
        self._load(self.mo_t, args)

    def mobile_action(self, action):
        ids = self._selected(self.mo_t, "resourceId", "device")
        if not ids:
            return
        words = {"admin_remote_wipe": "FACTORY RESET (erases the whole device)",
                 "admin_account_wipe": "remove the school account from"}
        if action in words and not self.confirm(f"This will {words[action]} "
                                                f"{len(ids)} device(s). Continue?"):
            return
        args = ["update", "mobile", ",".join(ids), "action", action]
        if action in words:
            args.append("doit")
        self.run(args, lambda *_: self.list_mobile())

    def delete_mobile(self):
        ids = self._selected(self.mo_t, "resourceId", "device")
        if ids and self.confirm(f"Remove {len(ids)} device(s) from the list?"):
            self.run(["delete", "mobile", ",".join(ids), "doit"], lambda *_: self.list_mobile())

    # ============================================================== alerts ===
    def _alerts(self):
        w, top, self.al_t = self._tab("alert", "Alert Center")
        box, form = self.group("Google security alerts")
        self.al_filter = QComboBox()
        self.al_filter.setEditable(True)
        self.al_filter.addItems(["", 'type="Suspicious login"', 'type="User reported phishing"',
                                 'type="Leaked password"', 'type="Device compromised"'])
        form.addRow("Filter (optional)", self.al_filter)
        form.addRow("", self.row(button("List alerts", "primary", self.list_alerts),
                                 button("Details for selected", slot=self.alert_info),
                                 button("Delete selected", "danger", self.delete_alerts)))
        from .round13_tabs import alert_feedback
        form.addRow("Was it useful?", self.row(
            button("Very useful", slot=lambda: alert_feedback(self, self.al_t, "very_useful")),
            button("Somewhat", slot=lambda: alert_feedback(self, self.al_t, "somewhat_useful")),
            button("Not useful", slot=lambda: alert_feedback(self, self.al_t, "not_useful"))))
        top.addWidget(box, 1)
        return w

    def list_alerts(self):
        args = ["print", "alerts", "orderby", "createtime", "descending"]
        if self.al_filter.currentText().strip():
            args[2:2] = ["filter", self.al_filter.currentText().strip()]
        self._load(self.al_t, args)

    def alert_info(self):
        for i in self._selected(self.al_t, "alertId", "alert")[:5]:
            self.run(["info", "alert", i])

    def delete_alerts(self):
        ids = self._selected(self.al_t, "alertId", "alert")
        if ids and self.confirm(f"Delete {len(ids)} alert(s)?"):
            self.run_many([["delete", "alert", i] for i in ids],
                          lambda _o: self.list_alerts(), quiet=False)

    # ======================================================= custom fields ===
    def _schemas(self):
        w, top, self.sc_t = self._tab("schema", "Schemas")
        box, form = self.group("Custom user fields (e.g. Student ID, Badge number)")
        form.addRow(self.row(button("List custom fields", "primary",
                                    lambda: self._load(self.sc_t, ["print", "schemas"]))))
        self.sc_name = QLineEdit(placeholderText="Schema name, e.g. SchoolInfo")
        self.sc_field = QLineEdit(placeholderText="Field name, e.g. StudentID")
        self.sc_type = self._combo([("Text", "string"), ("Whole number", "int64"),
                                    ("Date", "date"), ("Yes/No", "bool"), ("Email", "email"),
                                    ("Phone", "phone")])
        form.addRow("Schema", self.sc_name)
        form.addRow("Field", self.sc_field)
        form.addRow("Type", self.sc_type)
        form.addRow("", self.row(button("Create schema with this field", slot=self.create_schema),
                                 button("Add field to existing schema", slot=self.add_field)))
        top.addWidget(box, 1)
        box, form = self.group("Set a value for a person")
        self.sv_user = PersonField(self.directory, "Person")
        self.sv_value = QLineEdit(placeholderText="Value")
        form.addRow("Person", self.sv_user)
        form.addRow("Value", self.sv_value)
        form.addRow("", self.row(button("Save value", "primary", self.set_value),
                                 button("Show values for everyone", slot=self.show_values)))
        note = QLabel("Uses the schema and field typed on the left.", objectName="Muted")
        form.addRow("", note)
        top.addWidget(box, 1)
        return w

    def _sf(self):
        s, f = self.sc_name.text().strip(), self.sc_field.text().strip()
        if not s or not f:
            self.info("Type the schema name and field name.")
            return None, None
        return s, f

    def create_schema(self):
        s, f = self._sf()
        if s:
            self.run(["create", "schema", s, "field", f, "type", self.sc_type.currentData(),
                      "endfield"], lambda *_: self._load(self.sc_t, ["print", "schemas"]))

    def add_field(self):
        s, f = self._sf()
        if s:
            self.run(["update", "schema", s, "field", f, "type", self.sc_type.currentData(),
                      "endfield"], lambda *_: self._load(self.sc_t, ["print", "schemas"]))

    def set_value(self):
        s, f = self._sf()
        u = self.sv_user.email()
        if s and "@" in u:
            self.run(["update", "user", u, f"{s}.{f}", self.sv_value.text()])
        elif s:
            self.info("Choose the person.")

    def show_values(self):
        s, _f = self._sf()
        if s:
            self._load(self.sc_t, ["print", "users", "fields", "primaryemail,name",
                                   "custom", s])

    # ===================================================== contacts / GAL ===
    def _contacts(self):
        w, top, self.co_t = self._tab("contacts gal", "")
        box, form = self.group("Staff directory (Global Address List)")
        self.gal_user = PersonField(self.directory, "Person")
        form.addRow("Person", self.gal_user)
        form.addRow("", self.row(button("Hide from directory", slot=lambda: self.gal(False)),
                                 button("Show in directory", slot=lambda: self.gal(True))))
        form.addRow("", self.row(button("List people hidden from the directory",
                                        slot=lambda: self._load(
                                            self.co_t, ["print", "users", "query",
                                                        "includeInGlobalAddressList=false",
                                                        "fields", "primaryemail,name,ou"]))))
        top.addWidget(box, 1)
        box, form = self.group("Shared contacts")
        form.addRow(self.row(button("List domain shared contacts", "primary",
                                    lambda: self._load(self.co_t, ["print", "domaincontacts"]))))
        note = QLabel("Shared contacts appear for everyone in Gmail and Contacts, e.g. a "
                      "district office number. Create and edit them in the Command Builder.",
                      objectName="Muted")
        note.setWordWrap(True)
        form.addRow(note)
        top.addWidget(box, 1)
        return w

    def gal(self, on: bool):
        u = self.gal_user.email()
        if "@" not in u:
            self.info("Choose the person.")
            return
        self.run(["update", "user", u, "gal", "on" if on else "off"])

    # ========================================================= chat / meet ===
    def _chatmeet(self):
        w, top, self.cm_t = self._tab("chat meet", "")
        box, form = self.group("Google Chat")
        self.ch_user = PersonField(self.directory, "Person")
        form.addRow("Person", self.ch_user)
        form.addRow("", self.row(button("List their Chat spaces", "primary", lambda: self._for_user(
            self.ch_user, ["print", "chatspaces"]))))
        top.addWidget(box, 1)
        box, form = self.group("Google Meet")
        self.mt_user = PersonField(self.directory, "Person")
        self.mt_access = self._combo([("Only people in our organization (trusted)", "trusted"),
                                      ("Anyone with the link can ask (open)", "open"),
                                      ("Only invited people (restricted)", "restricted")])
        form.addRow("Person", self.mt_user)
        form.addRow("Who can join", self.mt_access)
        form.addRow("", self.row(
            button("Create a meeting link", "primary", lambda: self._for_user(
                self.mt_user, ["create", "meetspace", "accesstype",
                               self.mt_access.currentData()], table=False)),
            button("Their recent meetings", slot=lambda: self._for_user(
                self.mt_user, ["print", "meetconferences"]))))
        top.addWidget(box, 1)
        return w

    def _for_user(self, field, rest, table=True):
        u = field.email()
        if "@" not in u:
            self.info("Choose the person.")
            return
        args = ["user", u, *rest]
        if table:
            self._load(self.cm_t, args)
        else:
            self.run(args)

