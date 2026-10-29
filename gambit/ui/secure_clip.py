"""Copying a password: kept out of Windows clipboard history and cloud clipboard sync,
and cleared again after a minute (unless something else was copied since)."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtWidgets import QApplication

CLEAR_AFTER_MS = 60_000
_W = 'application/x-qt-windows-mime;value="{}"'


def copy_secret(text: str, clear_ms: int = CLEAR_AFTER_MS):
    md = QMimeData()
    md.setText(text)
    zero = (0).to_bytes(4, "little")
    md.setData(_W.format("ExcludeClipboardContentFromMonitorProcessing"), b"\x01\x00\x00\x00")
    md.setData(_W.format("CanIncludeInClipboardHistory"), zero)
    md.setData(_W.format("CanUploadToCloudClipboard"), zero)
    cb = QApplication.clipboard()
    cb.setMimeData(md)

    def clear():
        try:
            if cb.text() == text:
                cb.clear()
        except RuntimeError:
            pass
    QTimer.singleShot(clear_ms, clear)
