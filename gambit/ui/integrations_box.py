"""Settings → Integrations: your SIS (live roster), your help desk and the Claude assistant."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QPlainTextEdit

from ..settings import settings
from .widgets import Worker, button


def _field(key: str, placeholder: str, secret: bool = False) -> QLineEdit:
    f = QLineEdit(settings.get(key, "") or "")
    f.setPlaceholderText(placeholder)
    if secret:
        f.setEchoMode(QLineEdit.PasswordEchoOnEdit)
    f.editingFinished.connect(lambda: settings.set(key, f.text().strip()))
    return f


def _muted(text: str) -> QLabel:
    lb = QLabel(text, objectName="Muted")
    lb.setWordWrap(True)
    return lb


def _stack(page, combo, forms: dict):
    """Show only the selected provider's fields."""
    from PySide6.QtWidgets import QStackedWidget
    st = QStackedWidget()
    idx = {}
    for key, w in forms.items():
        idx[key] = st.addWidget(w)

    from PySide6.QtWidgets import QSizePolicy

    def show(*_):
        k = combo.currentData()
        for key, i in idx.items():
            wdg = st.widget(i)
            wdg.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred if key == k
                              else QSizePolicy.Ignored)
        if k in idx:
            st.setCurrentIndex(idx[k])
            st.setVisible(True)
            st.widget(idx[k]).adjustSize()
            st.adjustSize()
        else:
            st.setVisible(False)
    combo.currentIndexChanged.connect(show)
    show()
    return st


def _sub_form():
    from PySide6.QtWidgets import QFormLayout, QWidget
    w = QWidget()
    f = QFormLayout(w)
    f.setContentsMargins(0, 0, 0, 0)
    return w, f


def _sis_section(page, form):
    from PySide6.QtWidgets import QComboBox
    from ..integrations import sis_api
    form.addRow(QLabel("<b>Student information system (live roster)</b>"))
    combo = QComboBox()
    combo.addItem("Not connected (use export files)", "")
    for k, label in sis_api.PROVIDERS.items():
        combo.addItem(label, k)
    combo.setCurrentIndex(max(0, combo.findData(sis_api.provider())))
    combo.currentIndexChanged.connect(lambda *_: settings.set("sis_api/provider",
                                                             combo.currentData() or ""))
    form.addRow("Source", combo)
    forms = {}
    # ClassLink
    w, f = _sub_form()
    f.addRow("Roster Server URL", _field("oneroster/url", "https://<district>-<app>.oneroster"
                                                          ".com/ims/oneroster/v1p1"))
    f.addRow("Client ID", _field("oneroster/client_id", "Client ID"))
    f.addRow("Client secret", _field("oneroster/secret", "Client secret", secret=True))
    f.addRow("", _muted("In ClassLink Roster Server, add GAMbit's app, share users, orgs, "
                        "classes and enrollments, and copy the endpoint, client ID and "
                        "secret."))
    forms["classlink"] = w
    # OneRoster OAuth 2
    w, f = _sub_form()
    preset = QComboBox()
    for k, (label, _u, _t, _v) in sis_api.PRESETS.items():
        preset.addItem(label, k)
    preset.setCurrentIndex(max(0, preset.findData(settings.get("sis_api/oneroster2/preset",
                                                               "infinitecampus"))))
    url = _field("sis_api/oneroster2/url", "")
    tok = _field("sis_api/oneroster2/token_url", "")
    ver = QComboBox()
    for v in ("auto", "1.1", "1.2"):
        ver.addItem(v, v)
    ver.setCurrentIndex(max(0, ver.findData(settings.get("sis_api/oneroster2/version",
                                                         "auto") or "auto")))
    ver.currentIndexChanged.connect(lambda *_: settings.set("sis_api/oneroster2/version",
                                                           ver.currentData()))

    def hints(*_):
        k = preset.currentData()
        settings.set("sis_api/oneroster2/preset", k)
        _l, u, t, v = sis_api.PRESETS[k]
        url.setPlaceholderText(u)
        tok.setPlaceholderText(t)
        if v != "auto" and not settings.get("sis_api/oneroster2/version", ""):
            ver.setCurrentIndex(ver.findData(v))
    preset.currentIndexChanged.connect(hints)
    hints()
    f.addRow("SIS", preset)
    f.addRow("OneRoster base URL", url)
    f.addRow("Token URL", tok)
    f.addRow("Client ID", _field("sis_api/oneroster2/client_id", "Client ID"))
    f.addRow("Client secret", _field("sis_api/oneroster2/secret", "Client secret",
                                     secret=True))
    f.addRow("OneRoster version", ver)
    f.addRow("", _muted("Infinite Campus: System Administration → User Security → OAuth "
                        "Management. Skyward, Aeries, Synergy and PowerSchool's OneRoster "
                        "plugin: create an OneRoster API client and copy its URLs and keys "
                        "(your SIS vendor or regional center can turn this on)."))
    forms["oneroster2"] = w
    # Clever
    w, f = _sub_form()
    f.addRow("District token", _field("sis_api/clever/token", "Clever district app token",
                                      secret=True))
    f.addRow("", _muted("Needs a Clever Secure Sync app with access to your district "
                        "(Clever dashboard → Applications → your app → district token). "
                        "Guardians come from Clever contacts."))
    forms["clever"] = w
    # PowerSchool
    w, f = _sub_form()
    f.addRow("Server", _field("sis_api/powerschool/url", "https://district.powerschool.com"))
    f.addRow("Client ID", _field("sis_api/powerschool/client_id", "from the GAMbit plugin"))
    f.addRow("Client secret", _field("sis_api/powerschool/secret", "", secret=True))
    staff = QCheckBox("Also read staff")
    staff.setChecked((settings.get("sis_api/powerschool/staff", "") or "") == "1")
    staff.toggled.connect(lambda on: settings.set("sis_api/powerschool/staff",
                                                  "1" if on else ""))
    f.addRow("", staff)
    f.addRow("", _muted("Install a PowerSchool plugin with <oauth/> and read access to "
                        "students and schools (System → System Settings → Plugin "
                        "Management), then copy its client ID and secret."))
    forms["powerschool"] = w
    form.addRow("", _stack(page, combo, forms))

    def test():
        Worker(sis_api.test, on_done=page.info,
               on_error=lambda e: page.info(f"Couldn't connect:\n{e}"))
    form.addRow("", page.row(button("Test the SIS connection", slot=test)))
    form.addRow("", _muted("Roster sync, guardian sync, Classroom yearly setup and the "
                           "mismatch report can then pull the roster live instead of using an "
                           "export file."))


def _helpdesk_section(page, form):
    from PySide6.QtWidgets import QComboBox
    from ..integrations import ticketing as tk
    form.addRow(QLabel("<b>Help desk</b>"))
    combo = QComboBox()
    combo.addItem("None", "")
    for k, label in tk.PROVIDERS.items():
        combo.addItem(label, k)
    combo.setCurrentIndex(max(0, combo.findData(tk.provider())))

    def changed(*_):
        settings.set("ticketing/provider", combo.currentData() or "")
        if hasattr(page.app, "refresh_ticket_box"):
            page.app.refresh_ticket_box()
        if hasattr(page.app, "apply_role"):
            page.app.apply_role()
    combo.currentIndexChanged.connect(changed)
    form.addRow("Help desk", combo)
    forms = {}
    for p, fields in tk.FIELDS.items():
        w, f = _sub_form()
        for k, label, ph, secret in fields:
            f.addRow(label, _field(tk.key_for(p, k), ph, secret))
        tpl = QPlainTextEdit(settings.get(tk.key_for(p, "template"), "") or "")
        tpl.setMaximumHeight(60)
        tpl.setPlaceholderText(TEMPLATE_HINTS.get(p, "{}"))
        tpl.textChanged.connect(lambda t=tpl, p=p: settings.set(tk.key_for(p, "template"),
                                                               t.toPlainText().strip()))
        f.addRow("New-ticket fields (JSON)", tpl)
        cans = tk.CAN[p]
        f.addRow("", _muted("GAMbit can " + ", ".join(
            x for x, ok in (("read tickets", "read" in cans), ("add notes", "note" in cans),
                            ("open tickets", "create" in cans),
                            ("list the queue", "list" in cans),
                            ("resolve tickets", "resolve" in cans)) if ok) + "."))
        forms[p] = w
    form.addRow("", _stack(page, combo, forms))
    auto = QCheckBox("When a ticket is linked (top bar), add a note to it listing what GAMbit did")
    auto.setChecked(bool(tk.option("auto_note", True)))
    auto.toggled.connect(lambda on: settings.set("ticketing/auto_note", on))
    form.addRow("", auto)
    alert = QCheckBox("Open a ticket when a background task fails or an alert is sent")
    alert.setChecked(bool(tk.option("alert_tickets", False)))
    alert.toggled.connect(lambda on: settings.set("ticketing/alert_tickets", on))
    form.addRow("", alert)

    def test():
        if not tk.configured():
            page.info("Fill in the connection details first.")
            return
        if not tk.can("read"):
            page.info(f"Saved. {tk.name()} only lets GAMbit create tickets, so there's "
                      "nothing to test by reading.")
            return
        tid = page.app.ticket_box.text().strip() if hasattr(page.app, "ticket_box") else ""
        if tk.can("list") and not tk.ticket_id(tid):
            Worker(tk.list_open, {}, on_done=lambda ts: page.info(
                f"Connected to {tk.name()} – {len(ts)} open ticket(s) visible."),
                on_error=lambda e: page.info(f"Couldn't reach {tk.name()}:\n{e}"))
            return
        Worker(tk.get, tk.ticket_id(tid),
               on_done=lambda t: page.info(f"Connected. Ticket {t['number']}: {t['subject']}"),
               on_error=lambda e: page.info(f"Couldn't reach {tk.name()}:\n{e}"))
    form.addRow("", page.row(button("Test the help desk", slot=test)))


TEMPLATE_HINTS = {
    "iiq": '{"ProductId": "…", "IssueCategoryId": "…", "IssueTypeId": "…", "IssueId": "…", '
           '"LocationId": "…", "ForId": "…"}',
    "zendesk": '{"priority": "normal", "tags": ["gambit"], "group_id": 123}',
    "freshservice": '{"priority": 2, "group_id": 123, "category": "Google"}',
    "freshdesk": '{"priority": 2, "group_id": 123}',
    "servicenow": '{"assignment_group": "K12 IT", "category": "software", "urgency": "3"}',
    "jira": '{"requestFieldValues": {"priority": {"name": "Medium"}}}',
    "whd": '{"problemtype": {"type": "RequestType", "id": 3}, "location": {"type": '
           '"Location", "id": 1}}',
    "teamdynamix": '{"TypeID": 1, "StatusID": 1, "PriorityID": 1, "AccountID": 1, '
                   '"RequestorUid": "…"}',
    "osticket": '{"topicId": 1, "priority": 2}',
}


def integrations_box(page):
    box, form = page.group("Integrations")
    _sis_section(page, form)
    _helpdesk_section(page, form)

    # Claude
    form.addRow(QLabel("<b>Ask GAMbit (Claude)</b>"))
    on = QCheckBox("Turn on the Ask GAMbit assistant (Tools → Ask GAMbit)")
    on.setChecked(bool(settings.get("assistant/enabled", False)))
    on.toggled.connect(lambda v: (settings.set("assistant/enabled", v), page.app.apply_role()))
    key = _field("assistant/api_key", "Anthropic API key (sk-ant-…)", secret=True)
    model = _field("assistant/model", "Model, e.g. claude-sonnet-4-5")
    share = QCheckBox("Also send people's addresses (otherwise only org units, groups and your "
                      "domain are sent, and “Explain” replaces people with person1, person2…). "
                      "Check your student-data agreement first.")
    share.setChecked(bool(settings.get("assistant/share_users", False)))
    share.toggled.connect(lambda v: settings.set("assistant/share_users", v))
    form.addRow("", on)
    form.addRow("API key", key)

    def load_models():
        from ..integrations import assistant
        settings.set("assistant/api_key", key.text().strip())
        Worker(assistant.list_models,
               on_done=lambda ms: page.info("Models you can use:\n" + "\n".join(ms[:20])),
               on_error=lambda e: page.info(f"Couldn't list models:\n{e}"))
    form.addRow("Model", page.row(model, button("List models", slot=load_models),
                                  stretch=False))
    form.addRow("", share)
    form.addRow("", _muted("The assistant only suggests commands – you review them, and they "
                           "run through dry run, roles and the big-change preview like "
                           "everything else. Whatever you type is sent to Anthropic, so don't "
                           "paste student information you wouldn't put in an email."))
    return box
