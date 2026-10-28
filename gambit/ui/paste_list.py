"""Paste a list: a column of emails, names, student IDs or Chromebook serials copied from a
spreadsheet. GAMbit matches each one and shows what it couldn't match before you use them."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

EMAIL_RE = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")


def tokens(text: str) -> list[str]:
    """One entry per line (or per cell when tabs/commas separate single-word values)."""
    out = []
    for line in (text or "").replace("\r", "").split("\n"):
        line = line.strip().strip('"').strip()
        if not line:
            continue
        found = EMAIL_RE.findall(line)
        if found:
            out += found
            continue
        cells = [c.strip().strip('"') for c in re.split(r"[\t;]", line) if c.strip()]
        if len(cells) == 1 and "," in line and " " not in line:
            cells = [c.strip() for c in line.split(",") if c.strip()]   # 123,456,789
        out += cells
    seen, uniq = set(), []
    for t in out:
        if t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)
    return uniq


def match_people(items: list[str], users: list[dict], groups: list[dict] = (),
                 include_groups: bool = False):
    """→ (matched [(email, label)], unmatched [text], ambiguous [(text, n)])."""
    by_email = {u["email"].lower(): u for u in users}
    by_local = {}
    for u in users:
        by_local.setdefault(u["email"].split("@")[0].lower(), []).append(u)
    by_id = {}
    for u in users:
        if u.get("sis_id"):
            by_id.setdefault(str(u["sis_id"]).lower(), []).append(u)
    by_name = {}
    for u in users:
        if u.get("name"):
            by_name.setdefault(u["name"].lower(), []).append(u)
    g_by_email = {g["email"].lower(): g for g in groups} if include_groups else {}
    matched, unmatched, ambiguous, seen = [], [], [], set()

    def take(u_or_g, kind="user"):
        e = u_or_g["email"]
        if e.lower() in seen:
            return
        seen.add(e.lower())
        name = u_or_g.get("name") or ""
        matched.append((e, f"{name}  <{e}>" if name else e))

    for t in items:
        low = t.lower().strip()
        if "@" in low:
            if low in by_email:
                take(by_email[low])
            elif low in g_by_email:
                take(g_by_email[low], "group")
            else:
                unmatched.append(t)
            continue
        hits = by_id.get(low) or by_local.get(low) or by_name.get(low)
        if not hits and "," in t:                                  # "Doe, John"
            last, _c, first = t.partition(",")
            hits = by_name.get(f"{first.strip()} {last.strip()}".lower())
        if not hits and len(low) >= 4:
            hits = [u for u in users if low in (u.get("name") or "").lower()]
        if not hits:
            unmatched.append(t)
        elif len(hits) == 1:
            take(hits[0])
        else:
            ambiguous.append((t, len(hits)))
    return matched, unmatched, ambiguous


SERIAL_RE = re.compile(r"^[A-Za-z0-9-]{5,24}$")


def match_serials(items: list[str]):
    """→ (matched [(serial, label)], unmatched [text], note). Uses the saved fleet list."""
    rows = []
    try:
        from .. import fleet_cache
        rows = fleet_cache.all_rows() or []
    except Exception:  # noqa: BLE001
        rows = []

    def col(r, name):
        return next((v for k, v in r.items() if (k or "").lower() == name), "") or ""
    known = {col(r, "serialnumber").upper(): r for r in rows if col(r, "serialnumber")}
    assets = {col(r, "annotatedassetid").upper(): r for r in rows
              if col(r, "annotatedassetid")}
    matched, unmatched = [], []
    for t in items:
        up = t.strip().upper()
        r = known.get(up) or assets.get(up)
        if r is not None:
            sn = col(r, "serialnumber")
            user = col(r, "annotateduser")
            matched.append((sn, sn + (f"  ·  {user}" if user else "")))
        elif not known and SERIAL_RE.match(up):
            matched.append((up, up + "  ·  not checked (load the fleet list to check)"))
        else:
            unmatched.append(t)
    return matched, unmatched, ""


class PasteListDialog(QDialog):
    def __init__(self, parent, directory=None, kind: str = "people",
                 include_groups: bool = False):
        super().__init__(parent)
        self.d, self.kind, self.include_groups = directory, kind, include_groups
        self.result_items: list[str] = []
        self.setWindowTitle("Paste a list")
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        what = ("emails, names or student IDs" if kind == "people"
                else "Chromebook serial numbers or asset tags")
        lay.addWidget(QLabel(f"Paste {what} – one per line, straight from a spreadsheet "
                             "column is fine.", wordWrap=True))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("jdoe@hancockschools.net\nJane Smith\n001x48x9x" if
                                     kind == "people" else "5CD0372JK1\nHMS-01234")
        self.text.textChanged.connect(self.check)
        lay.addWidget(self.text, 2)
        self.summary = QLabel("", objectName="SectionTitle")
        lay.addWidget(self.summary)
        lists = QHBoxLayout()
        left, right = QVBoxLayout(), QVBoxLayout()
        left.addWidget(QLabel("Found", objectName="Muted"))
        self.ok_list = QListWidget()
        left.addWidget(self.ok_list)
        right.addWidget(QLabel("Couldn't match", objectName="Muted"))
        self.bad_list = QListWidget()
        right.addWidget(self.bad_list)
        lists.addLayout(left, 3)
        lists.addLayout(right, 2)
        lay.addLayout(lists, 3)
        foot = QHBoxLayout()
        foot.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.add_btn = QPushButton("Add")
        self.add_btn.setProperty("kind", "primary")
        self.add_btn.clicked.connect(self.accept)
        foot.addWidget(cancel)
        foot.addWidget(self.add_btn)
        lay.addLayout(foot)
        self.check()

    def check(self):
        items = tokens(self.text.toPlainText())
        if self.kind == "people":
            users = getattr(self.d, "users", []) or []
            groups = getattr(self.d, "groups", []) or []
            ok, bad, amb = match_people(items, users, groups, self.include_groups)
            bad = bad + [f"{t}  (matches {n} people)" for t, n in amb]
        else:
            ok, bad, _n = match_serials(items)
        self.ok_list.clear()
        self.bad_list.clear()
        for value, label in ok:
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, value)
            self.ok_list.addItem(it)
        self.bad_list.addItems(bad)
        self.result_items = [v for v, _l in ok]
        self.summary.setText(f"{len(ok)} found" + (f" · {len(bad)} couldn't match" if bad
                                                   else "") if items else "")
        self.add_btn.setText(f"Add {len(ok)}" if ok else "Add")
        self.add_btn.setEnabled(bool(ok))


def paste_people(parent, directory, include_groups=False) -> list[str]:
    dlg = PasteListDialog(parent, directory, "people", include_groups)
    return dlg.result_items if dlg.exec() else []


def paste_serials(parent) -> list[str]:
    dlg = PasteListDialog(parent, None, "serials")
    return dlg.result_items if dlg.exec() else []
