"""Dark mode colours, windows that stay on the screen, and the taskbar icon."""

import os
import struct

from gambit.ui import theme

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _l(c):
    return theme._hls(theme._hex(c))[1]


def test_light_mode_leaves_styles_alone():
    theme._set_mode("light")
    css = "color:#57606a; background:#fff4ce; border:1px solid #f2d675"
    assert theme.map_css(css) == css


def test_dark_mode_makes_text_light_and_backgrounds_dark():
    theme._set_mode("dark")
    try:
        out = theme.map_css("QLabel{color:#137333; background:#fff4ce; border:1px solid "
                            "#f2d675} <span style='color:#b42318'>x</span> "
                            "<font color=\"#1f2328\">y</font>")
        for c in ("#137333", "#fff4ce", "#f2d675", "#b42318", "#1f2328"):
            assert c not in out
        import re
        texts = re.findall(r"color\s*[:=]\s*[\"']?(#[0-9a-f]{6})", out)
        assert texts and all(_l(c) >= 0.6 for c in texts)
        bg = re.search(r"background:(#[0-9a-f]{6})", out).group(1)
        assert _l(bg) < 0.35
        # already-dark parts (the output log, primary buttons) don't change
        assert theme.map_css("background:#0d1117; color:#d1d9e0") == \
            "background:#0d1117; color:#d1d9e0"
        assert "white" in theme.map_css("background:#1a73e8; color:white")
        # unknown colours are converted too
        assert _l(theme.dark_color("#334455", "text")) >= 0.7
        assert _l(theme.dark_color("#fafafa", "bg")) < 0.3
    finally:
        theme._set_mode("light")


def test_switching_live_rewrites_existing_widgets(qapp):
    from PySide6.QtWidgets import QLabel
    theme.apply_theme(qapp, mode="light")
    lab = QLabel()
    lab.setText("<span style='color:#b42318'>failed</span>")
    lab.setStyleSheet("background:#fff4ce;")
    theme.apply_theme(qapp, mode="dark")
    assert "#b42318" not in QLabel.text(lab) and "#fff4ce" not in lab.styleSheet()
    theme.apply_theme(qapp, mode="light")
    assert "#b42318" in QLabel.text(lab) and "#fff4ce" in lab.styleSheet()


def test_long_status_never_widens_the_window(qapp):
    from PySide6.QtWidgets import QHBoxLayout, QWidget

    from gambit.ui.widgets import ElideLabel
    w = QWidget()
    h = QHBoxLayout(w)
    lab = ElideLabel("Running: gam print cros fields " + "serialnumber," * 300)
    h.addWidget(lab)
    assert w.minimumSizeHint().width() < 200
    assert lab.text().startswith("Running:") and lab.toolTip()


def test_window_is_kept_on_screen(qapp):
    from PySide6.QtWidgets import QDialog
    theme.apply_theme(qapp, mode="light")
    d = QDialog()
    d.resize(9000, 9000)
    d.show()
    for _ in range(5):
        qapp.processEvents()
    av = d.screen().availableGeometry()
    assert d.frameGeometry().width() <= av.width() and d.frameGeometry().height() <= av.height()
    d.close()


def test_icon_small_sizes_are_bitmaps():
    data = open(os.path.join(ROOT, "assets", "gambit.ico"), "rb").read()
    _r, _t, n = struct.unpack("<HHH", data[:6])
    sizes = {}
    for i in range(n):
        w, _h, _c, _x, _p, bpp, size, off = struct.unpack("<BBBBHHII", data[6 + 16 * i:22 + 16 * i])
        sizes[w or 256] = data[off:off + 4]
    for s in (16, 24, 32, 48):
        assert sizes[s] == b"(\x00\x00\x00", f"{s}px must be a BMP frame, not PNG"
    assert sizes[256] == b"\x89PNG"
