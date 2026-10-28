"""Print a table, or save it as a PDF, with a proper header: district, page, date, the filter
used and how many rows – for principals, audits and binders."""

from __future__ import annotations

import datetime
import html

from PySide6.QtCore import Qt

MAX_ROWS = 5000


def _district(win) -> str:
    d = getattr(getattr(win, "directory", None), "domain", "") or ""
    try:
        from .. import team
        name = team.setting("district/name", "") or ""
    except Exception:  # noqa: BLE001
        name = ""
    return name or d or "Google Workspace"


def build_html(table, title: str = "") -> str:
    from .widgets import nice_header
    win = table.window()
    hh = table.table.horizontalHeader()
    cols = [hh.logicalIndex(v) for v in range(hh.count())]
    cols = [c for c in cols if c < len(table._headers) and not table.table.isColumnHidden(c)]
    n = table.row_count()
    rows = []
    for r in range(min(n, MAX_ROWS)):
        cells = []
        for c in cols:
            idx = table.proxy.index(r, c)
            cells.append(html.escape(str(idx.data() or "")))
        rows.append("<tr>" + "".join(f"<td>{x}</td>" for x in cells) + "</tr>")
    head = "".join(f"<th>{html.escape(nice_header(table._headers[c]).title())}</th>"
                   for c in cols)
    when = datetime.datetime.now()
    filt = table.filter.text().strip()
    meta = [f"{n:,} row(s)", when.strftime("%B %d, %Y %I:%M %p").replace(" 0", " ")]
    if filt:
        meta.append(f"filtered by “{html.escape(filt)}”")
    more = (f"<p class='note'>Showing the first {MAX_ROWS:,} of {n:,} rows – export to CSV "
            "for all of them.</p>") if n > MAX_ROWS else ""
    return f"""<html><head><style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 9pt; color: #111827; }}
h1 {{ font-size: 15pt; margin: 0; }}
.sub {{ color: #4B5563; margin: 2px 0 10px 0; }}
table {{ border-collapse: collapse; width: 100%; }}
th {{ text-align: left; background: #EEF2F7; padding: 4px 6px; font-size: 8pt;
      border-bottom: 1px solid #CBD5E1; }}
td {{ padding: 3px 6px; border-bottom: 1px solid #E5E7EB; }}
.note {{ color: #92400E; }}
</style></head><body>
<div class='sub'>{html.escape(_district(win))}</div>
<h1>{html.escape(title or table._title())}</h1>
<div class='sub'>{' · '.join(meta)}</div>
{more}
<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>
<p class='sub'>Printed from GAMbit.</p>
</body></html>"""


def _document(table):
    from PySide6.QtGui import QTextDocument
    doc = QTextDocument()
    doc.setHtml(build_html(table))
    return doc


def _printer(landscape: bool):
    from PySide6.QtGui import QPageLayout, QPageSize
    from PySide6.QtPrintSupport import QPrinter
    p = QPrinter(QPrinter.HighResolution)
    p.setPageSize(QPageSize(QPageSize.Letter))
    p.setPageOrientation(QPageLayout.Landscape if landscape else QPageLayout.Portrait)
    return p


def print_table(table):
    """Preview with Print (and Microsoft Print to PDF on Windows), or Save as PDF."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
    hidden = sum(table.table.isColumnHidden(c) for c in range(len(table._headers)))
    landscape = len(table._headers) - hidden > 5
    box = QMessageBox(table)
    box.setWindowTitle("Print or save as PDF")
    box.setText(f"{table.row_count():,} row(s) from {table._title()}, with today's date "
                "and the filter you used.")
    pr = box.addButton("Print…", QMessageBox.AcceptRole)
    pdf = box.addButton("Save as PDF…", QMessageBox.ActionRole)
    box.addButton(QMessageBox.Cancel)
    box.exec()
    if box.clickedButton() is pdf:
        name = f"{table._title()} {datetime.date.today().isoformat()}.pdf".replace("/", "-")
        path, _ = QFileDialog.getSaveFileName(table, "Save as PDF", name, "PDF (*.pdf)")
        if not path:
            return None
        printer = _printer(landscape)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        _document(table).print_(printer)
        win = table.window()
        if hasattr(win, "toasts"):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            win.toasts.show("Saved the PDF", "ok", "Open",
                            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        return path
    if box.clickedButton() is pr:
        printer = _printer(landscape)
        dlg = QPrintPreviewDialog(printer, table)
        dlg.setWindowTitle(f"Print – {table._title()}")
        doc = _document(table)
        dlg.paintRequested.connect(lambda p: doc.print_(p))
        dlg.resize(1000, 760)
        dlg.exec()
    return None
