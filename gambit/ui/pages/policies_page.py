"""Policies by org unit – compare Chrome and Workspace settings across org units."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLabel

from ... import policies
from ...directory import run_gam_csv
from ..pickers import OUMultiField
from ..widgets import Page, ResultsTable, Worker, button


def _gather(kind: str, ous: list[str]):
    triples = []
    errors = []
    if kind in ("chrome", "both"):
        for ou in ous:
            code, rows, err = run_gam_csv(["print", "chromepolicies", "ou", ou, "show", "all"],
                                          300)
            if code != 0:
                errors.append(f"Chrome {ou}: " + (err.strip().splitlines() or ["failed"])[-1])
                continue
            text = _to_csv(rows)
            triples += policies.rows_to_settings(text, ou)
    if kind in ("workspace", "both"):
        code, rows, err = run_gam_csv(["print", "policies", "nowarnings"], 600)
        if code != 0:
            errors.append("Workspace: " + (err.strip().splitlines() or ["failed"])[-1])
        else:
            all_t = policies.rows_to_settings(_to_csv(rows))
            # Workspace policies are inherited: an OU without its own value uses its parent's
            for ou in ous:
                chain = _ancestors(ou)
                seen = {}
                for anc in chain:
                    for o, sname, val in all_t:
                        if o.rstrip("/") == anc.rstrip("/") or (anc == "/" and o in ("", "/")):
                            seen[sname] = val + ("" if anc == ou else f"  (from {anc})")
                triples += [(ou, sname, val) for sname, val in seen.items()]
    return triples, errors


def _ancestors(ou: str) -> list[str]:
    parts = [p for p in ou.split("/") if p]
    return ["/"] + ["/" + "/".join(parts[:i]) for i in range(1, len(parts) + 1)]


def _to_csv(rows: list[dict]) -> str:
    import csv
    import io
    if not rows:
        return ""
    buf = io.StringIO()
    heads = []
    for r in rows:
        for k in r:
            if k not in heads:
                heads.append(k)
    w = csv.DictWriter(buf, fieldnames=heads)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


class PoliciesPage(Page):
    title = "Policies by org unit"
    subtitle = ("Compare settings across org units – for example, check every grade level "
                "has the same Chrome restrictions, or which org units can email outside the "
                "district. Settings that differ are listed first.")

    def build(self):
        self.ous = OUMultiField(self.directory)
        self.ous.sub.hide()
        self.kind = QComboBox()
        self.kind.addItem("Chrome (users, browsers and devices)", "chrome")
        self.kind.addItem("Workspace (Gmail, Drive, Meet …)", "workspace")
        self.kind.addItem("Both", "both")
        self.body.addLayout(self.row(QLabel("Org units"), self.ous, QLabel("Show"), self.kind,
                                     stretch=False))
        self.go = button("Compare", "primary", self.compare)
        self.status = QLabel("Pick two or more org units (e.g. every grade at one school).",
                             objectName="Muted")
        self.status.setWordWrap(True)
        self.body.addLayout(self.row(self.go, button("Change or copy policies…",
                                                     slot=self.edit_policies),
                                     button("Clean up overrides…", slot=self.cleanup),
                                     button("Wallpaper && picture…", slot=self.images),
                                     button("Wi-Fi networks…", slot=self.wifi)))
        self.body.addWidget(self.status)
        self.table = ResultsTable()
        self.body.addWidget(self.table, 1)

    def cleanup(self):
        from .round13_tabs import PolicyCleanupDialog
        PolicyCleanupDialog(self).exec()

    def wifi(self):
        from .round14_tabs import WifiDialog
        WifiDialog(self).exec()

    def images(self):
        from .round13_tabs import PolicyImageDialog
        PolicyImageDialog(self).exec()

    def edit_policies(self):
        from .chrome_tabs import PolicyDialog
        PolicyDialog(self).exec()

    def compare(self):
        ous = self.ous.paths()
        if not ous:
            self.info("Choose the org units to compare.")
            return
        self.go.setEnabled(False)
        self.status.setText("Reading policies from Google (one request per org unit)…")

        def done(res):
            triples, errors = res
            self.go.setEnabled(True)
            heads, rows = policies.matrix(triples, ous)
            self.table.set_rows(heads, rows)
            n = sum(1 for r in rows if r[1])
            self.status.setText(f"{len(rows):,} settings · {n:,} differ between these org "
                                "units" + ((" · problems: " + "; ".join(errors)) if errors
                                          else ""))

        def failed(e):
            self.go.setEnabled(True)
            self.status.setText(f"Couldn't read policies: {e}")
        Worker(_gather, self.kind.currentData(), ous, on_done=done, on_error=failed)
