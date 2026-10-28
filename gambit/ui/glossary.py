"""Plain-English help for Google Admin jargon: a small ⓘ after form labels like “Org unit”
or “License” (hover or click it), and the same explanation on matching table headings."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel

TERMS = {
    "org unit": "Org unit (OU): a folder in Google Admin that groups accounts or Chromebooks. "
                "Settings, apps and policies are applied per org unit.",
    "license": "License: what Google charges per person (e.g. Education Plus). Some features "
               "only work for people who have one.",
    "sku": "SKU: Google's code for a license type (e.g. 1010070001 = Education Fundamentals).",
    "2-step": "2-Step Verification: a second check (phone prompt or code) after the "
              "password when signing in.",
    "alias": "Alias: another email address that delivers to the same account.",
    "aue": "AUE (Auto Update Expiration): the month a Chromebook stops getting ChromeOS "
           "updates and security fixes.",
    "asset id": "Asset ID: your own inventory tag saved with the Chromebook in Google Admin.",
    "annotated user": "Annotated user: the person you recorded as using this Chromebook (not "
                      "necessarily who signed in last).",
    "custom field": "Custom field: your district's own fields on user accounts (grade, "
                    "student ID…), set up in Google Admin as a custom schema.",
    "student id": "Student ID: the ID from your SIS, saved on the Google account (an "
                  "“external ID”).",
    "delegate": "Delegate: someone allowed to read and send from another person's mailbox.",
    "shared drive": "Shared drive: a Drive that belongs to the team, not to one person – files "
                    "stay when people leave.",
    "guardian": "Guardian: a parent or carer who gets Google Classroom email summaries.",
    "last sign-in": "Last sign-in: when the person last signed in to Google (can lag by a "
                    "few hours).",
    "suspended": "Suspended: the account can't sign in or get email, but nothing is deleted.",
    "dry run": "Dry run: GAMbit lists the exact GAM commands but doesn't change anything.",
    "group email": "Group email: one address that reaches every member of the group.",
    "profile": "Domain / profile: which Google Workspace (and GAM settings) GAMbit works on.",
}
ALIASES = {"ou": "org unit", "org unit path": "org unit", "organizational unit": "org unit",
           "orgunitpath": "org unit", "2-step verification": "2-step",
           "isenrolledin2sv": "2-step", "isenforcedin2sv": "2-step", "2sv": "2-step",
           "autoupdateexpiration": "aue", "auto-update expiration": "aue",
           "annotatedassetid": "asset id", "asset tag": "asset id", "asset": "asset id",
           "annotateduser": "annotated user", "lastlogintime": "last sign-in",
           "last login time": "last sign-in", "aliases": "alias", "licenses": "license",
           "skuid": "sku", "sis id": "student id", "externalids": "student id",
           "custom fields": "custom field", "domain": "profile"}


def explain(text: str) -> str:
    key = re.sub(r"[:&*]", "", (text or "")).strip().lower()
    key = key.split(".")[-1] if "." in key and " " not in key else key
    key = ALIASES.get(key, key)
    return TERMS.get(key, "")


def annotate(root) -> int:
    """Add ⓘ to matching form labels under `root`. Returns how many."""
    n = 0
    for form in root.findChildren(QFormLayout):
        for r in range(form.rowCount()):
            it = form.itemAt(r, QFormLayout.LabelRole)
            lab = it.widget() if it is not None else None
            if not isinstance(lab, QLabel) or lab.property("_gb_gloss"):
                continue
            tip = explain(lab.text())
            if not tip:
                continue
            lab.setProperty("_gb_gloss", True)
            base = lab.text()
            lab.setTextFormat(Qt.RichText)
            lab.setText(f"{base}&nbsp;<a href='gloss' style='text-decoration:none'>ⓘ</a>")
            lab.setToolTip(tip)
            lab.linkActivated.connect(lambda _h, lab=lab, tip=tip: _show(lab, tip))
            n += 1
    return n


def _show(lab, tip):
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QToolTip
    QToolTip.showText(QCursor.pos(), tip, lab)
