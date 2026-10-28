"""Windows 11 window chrome: rounded corners, and a title bar that matches GAMbit's light
or dark colours (DwmSetWindowAttribute). Does nothing on other systems or older Windows."""

from __future__ import annotations

import sys

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
DWMWCP_ROUND = 2


def _colorref(hex_color: str) -> int:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r | (g << 8) | (b << 16)


def apply(win) -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes
        from .theme import is_dark, tokens
        hwnd = wintypes.HWND(int(win.winId()))
        dwm = ctypes.windll.dwmapi

        def setattr_(attr, value):
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, wintypes.DWORD(attr), ctypes.byref(v),
                                      ctypes.sizeof(v))
        t = tokens()
        setattr_(DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if is_dark() else 0)
        setattr_(DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
        setattr_(DWMWA_CAPTION_COLOR, _colorref(t["topbar"]))
        setattr_(DWMWA_TEXT_COLOR, _colorref(t["text"]))
        return True
    except Exception:  # noqa: BLE001 – older Windows: keep the normal title bar
        return False
