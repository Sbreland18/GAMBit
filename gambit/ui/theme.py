"""App-wide look and feel."""
import re

ACCENT = "#1a73e8"

STYLESHEET = f"""
QWidget {{ font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; color: #1f2328; }}
QMainWindow, QWidget#Page {{ background: #f6f8fb; }}

QListWidget#Nav {{
    background: #0f2741; border: none; padding-top: 8px; outline: 0;
}}
QListWidget#Nav::item {{
    color: #c9d6e6; padding: 5px 16px; margin: 0px 8px; border-radius: 7px;
}}
QListWidget#Nav::item:disabled {{ color: #6f87a3; padding: 9px 16px 1px 16px; background: transparent; }}
QListWidget#Nav::item:hover {{ background: #183a5e; color: white; }}
QListWidget#Nav::item:selected {{ background: {ACCENT}; color: white; }}
QListWidget#Nav::item:disabled:hover {{ background: transparent; color: #6f87a3; }}
QLabel#Brand {{ background: #0f2741; color: white; font-size: 16pt; font-weight: 600;
               padding: 18px 16px 6px 16px; }}
QLabel#BrandSub {{ background: #0f2741; color: #8fa6bf; padding: 0 16px 12px 16px; font-size: 9pt; }}

QLabel#PageTitle {{ font-size: 17pt; font-weight: 600; }}
QLabel#PageSub {{ color: #57606a; }}
QLabel#Muted {{ color: #57606a; }}
QLabel#Small {{ color: #57606a; font-size: 9pt; }}

QGroupBox {{
    background: white; border: 1px solid #dfe3e8; border-radius: 10px;
    margin-top: 14px; padding: 14px 12px 12px 12px; font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
QGroupBox QLabel, QGroupBox QCheckBox {{ font-weight: normal; }}

QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox {{
    background: white; border: 1px solid #c9d1d9; border-radius: 6px; padding: 5px 7px;
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}

QPushButton {{
    background: white; border: 1px solid #c9d1d9; border-radius: 6px; padding: 6px 14px;
}}
QPushButton:hover {{ background: #eef3fb; border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #9aa4ae; background: #f2f4f7; }}
QPushButton[kind="primary"] {{ background: {ACCENT}; color: white; border: 1px solid {ACCENT}; }}
QPushButton[kind="primary"]:hover {{ background: #1765cc; }}
QPushButton[kind="danger"] {{ color: #b42318; border-color: #f0b4ae; }}
QPushButton[kind="danger"]:hover {{ background: #fdecea; }}
QPushButton[kind="primary"]:disabled, QPushButton[kind="danger"]:disabled {{
    background: #eef1f4; color: #9aa4ae; border: 1px solid #d5dbe1; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ padding: 7px 16px; border: none; color: #57606a; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}

QTableWidget {{ background: white; border: 1px solid #dfe3e8; border-radius: 8px;
               gridline-color: #eef0f3; }}
QHeaderView::section {{ background: #f1f4f8; border: none; padding: 6px; font-weight: 600; }}

QPlainTextEdit#Log {{ background: #0d1117; color: #d1d9e0; border-radius: 8px;
                     font-family: "Cascadia Mono", "Consolas", monospace; font-size: 9.5pt; }}
QFrame#Card {{ background: white; border: 1px solid #dfe3e8; border-radius: 12px; }}
QLabel#CardValue {{ font-size: 15pt; font-weight: 600; }}
QLabel#Banner {{ background: #fff4ce; border: 1px solid #f2d675; border-radius: 8px; padding: 8px 12px; }}

/* Popups, menus and dialogs: always light with dark text, even when Windows is in dark mode */
QComboBox QAbstractItemView {{
    background: white; color: #1f2328; border: 1px solid #c9d1d9; outline: 0;
    selection-background-color: #dbe9fd; selection-color: #0b3d91; padding: 2px;
}}
QComboBox QAbstractItemView::item {{ min-height: 24px; padding: 2px 8px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QMenu {{ background: white; color: #1f2328; border: 1px solid #c9d1d9; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: #dbe9fd; color: #0b3d91; }}
QToolTip {{ background: #1f2328; color: white; border: none; padding: 5px 8px; }}
QDialog, QMessageBox, QInputDialog, QFileDialog {{ background: #f6f8fb; }}
QMessageBox QLabel, QDialog QLabel {{ color: #1f2328; }}
QCheckBox, QRadioButton {{ color: #1f2328; spacing: 6px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{ color: #1f2328; selection-background-color: #b6d4fb; selection-color: #1f2328; }}
QLineEdit:disabled, QComboBox:disabled {{ background: #f2f4f7; color: #8b949e; }}
QTableWidget {{ color: #1f2328; alternate-background-color: #f8fafc;
               selection-background-color: #dbe9fd; selection-color: #0b3d91; }}
QScrollArea {{ background: transparent; }}

QProgressBar {{ border: 1px solid #c9d1d9; border-radius: 6px; text-align: center; background: white; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
"""


def light_palette():
    """A fixed light palette so Windows dark mode can't make text unreadable."""
    from PySide6.QtGui import QColor, QPalette

    p = QPalette()
    text, base, window = QColor("#1f2328"), QColor("#ffffff"), QColor("#f6f8fb")
    for group in (QPalette.Active, QPalette.Inactive):
        p.setColor(group, QPalette.Window, window)
        p.setColor(group, QPalette.WindowText, text)
        p.setColor(group, QPalette.Base, base)
        p.setColor(group, QPalette.AlternateBase, QColor("#f8fafc"))
        p.setColor(group, QPalette.Text, text)
        p.setColor(group, QPalette.Button, base)
        p.setColor(group, QPalette.ButtonText, text)
        p.setColor(group, QPalette.ToolTipBase, QColor("#1f2328"))
        p.setColor(group, QPalette.ToolTipText, base)
        p.setColor(group, QPalette.PlaceholderText, QColor("#8b949e"))
        p.setColor(group, QPalette.Highlight, QColor("#dbe9fd"))
        p.setColor(group, QPalette.HighlightedText, QColor("#0b3d91"))
        p.setColor(group, QPalette.Link, QColor(ACCENT))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#9aa4ae"))
    p.setColor(QPalette.Disabled, QPalette.Base, QColor("#f2f4f7"))
    p.setColor(QPalette.Disabled, QPalette.Window, window)
    p.setColor(QPalette.Disabled, QPalette.Button, QColor("#f2f4f7"))
    return p


def scaled_stylesheet(scale: float) -> str:
    """The stylesheet with every font size multiplied by `scale`."""
    import re
    if abs(scale - 1.0) < 0.01:
        return STYLESHEET
    return re.sub(r"(\d+(?:\.\d+)?)pt",
                  lambda m: f"{float(m.group(1)) * scale:.1f}pt", STYLESHEET)


def apply_theme(app, scale: float | None = None, mode: str | None = None):
    """Call at startup (main app and Builder), and again to switch light ↔ dark live.
    `scale` changes text size; `mode` is light | dark (default: the saved choice)."""
    from PySide6.QtCore import Qt
    if scale is None:
        try:
            from ..settings import settings
            scale = float(settings.get("ui/text_scale", 1.0) or 1.0)
        except Exception:  # noqa: BLE001
            scale = 1.0
    m = mode or wanted_mode(app)
    first = not _ORIG
    _install_hooks()
    _set_mode(m)
    try:  # Qt 6.8+: tell Qt which scheme we draw, so native bits match
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark if m == "dark"
                                        else Qt.ColorScheme.Light)
    except Exception:
        pass
    app.setStyle("Fusion")
    app.setPalette(dark_palette() if m == "dark" else light_palette())
    font = app.font()
    font.setPointSizeF(10 * scale)
    app.setFont(font)
    app.setStyleSheet(_dark_stylesheet(scale) if m == "dark" else scaled_stylesheet(scale))
    _ScreenClamp.install(app)
    if not first:
        refresh_all(app)


class _ScreenClamp:
    """Keeps windows and dialogs on the screen and catches colours given in constructors –
    checked when a window opens (not on every event, which would slow GAMbit down)."""

    _done = False

    @classmethod
    def install(cls, app):
        if cls._done:
            return
        cls._done = True
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QDialog, QWidget
        orig_show, orig_exec, orig_open = QWidget.show, QDialog.exec, QDialog.open

        def before(w):
            if w.isWindow():
                polish_tree(w)
                QTimer.singleShot(0, lambda o=w: fit_to_screen(o))
                QTimer.singleShot(400, lambda o=w: fit_to_screen(o, move=False))

        def show(self):
            before(self)
            return orig_show(self)

        def exec_(self, *a):
            before(self)
            return orig_exec(self, *a)

        def open_(self):
            before(self)
            return orig_open(self)
        QWidget.show = show
        QDialog.exec = exec_
        QDialog.open = open_


def polish_tree(root):
    """polish() a window and everything in it (only does work in dark mode or once)."""
    from PySide6.QtWidgets import QWidget
    if not is_dark():          # light mode draws the colours as written – nothing to do
        return
    try:
        polish(root)
        for w in root.findChildren(QWidget):
            polish(w)
    except Exception:  # noqa: BLE001
        pass


def fit_to_screen(w, move: bool = True):
    """Shrink (and on opening, move) a top-level window so all of it – the title bar and
    its close button too – is on the screen."""
    try:
        from PySide6.QtCore import Qt
        from shiboken6 import isValid
        if not isValid(w) or not w.isVisible() or w.inherits("QMenu") or \
                w.windowType() in (Qt.Popup, Qt.ToolTip, Qt.SplashScreen) or \
                w.isMaximized() or w.isFullScreen():
            return
        scr = w.screen()
        if scr is None:
            return
        av = scr.availableGeometry()
        fr = w.frameGeometry()
        extra_w, extra_h = fr.width() - w.width(), fr.height() - w.height()
        nw = min(w.width(), av.width() - extra_w)
        nh = min(w.height(), av.height() - extra_h)
        if (nw, nh) != (w.width(), w.height()):
            w.resize(max(nw, 200), max(nh, 150))
            move = True
        if move:
            fr = w.frameGeometry()
            x = max(av.x(), min(fr.x(), av.x() + av.width() - fr.width()))
            y = max(av.y(), min(fr.y(), av.y() + av.height() - fr.height()))
            if (x, y) != (fr.x(), fr.y()):
                w.move(x, y)
    except Exception:  # noqa: BLE001 – never let layout help break a window
        pass


# ================================================================ dark mode ===
# Hand-picked dark equivalents for the colours GAMbit uses most; anything else is
# converted by lightness (light backgrounds → dark, dark text → light, same hue).
DARK_BG = {
    "#ffffff": "#1c2330", "white": "#1c2330", "#f6f8fb": "#0f141b", "#f6f8fa": "#1c2330",
    "#f8fafc": "#1a212b", "#f1f4f8": "#232b38", "#f2f4f7": "#1f2630", "#eef1f4": "#232a35",
    "#eef1f6": "#232a35", "#eef3fb": "#263247", "#eef5ff": "#1d2c44", "#e8f1fb": "#1d2c44",
    "#dbe9fd": "#1f3a63", "#cfe0f7": "#233c62", "#eef0f3": "#2a3240", "#b6d4fb": "#2b4a7a",
    "#fff4ce": "#3b3214", "#fff8e1": "#352d12", "#ffe58a": "#4a3d10", "#fdecea": "#3d1d1a",
    "#e6f4ea": "#173524",
}
DARK_BORDER = {"#dfe3e8": "#353e4c", "#c9d1d9": "#455063", "#d5dbe1": "#3a4352",
               "#d8dee4": "#3a4352", "#d9dee8": "#3a4352", "#f2d675": "#7a6420",
               "#f0b4ae": "#7a3a33"}
DARK_TEXT = {"#1f2328": "#e6edf3", "black": "#e6edf3", "#000000": "#e6edf3",
             "#57606a": "#a4adb8", "#6b7785": "#a4adb8", "#7b8794": "#9aa4b0",
             "#9aa4ae": "#76818d", "#8b949e": "#7d8590", "#0b3d91": "#cfe1ff",
             "#137333": "#6fdd8b", "#1a7f37": "#6fdd8b", "#b42318": "#ff9b8e",
             "#cf222e": "#ff8f8f", "#9a6700": "#e3b341", "#0b63c5": "#79b8ff",
             "#1a73e8": "#79b8ff", "#1d2433": "#e6edf3", "#7a8499": "#a4adb8"}
NAMED = {"white": "#ffffff", "black": "#000000", "red": "#ff0000", "green": "#008000",
         "gray": "#808080", "grey": "#808080", "orange": "#ffa500", "blue": "#0000ff"}

_MODE = "light"


def mode() -> str:
    return _MODE


def is_dark() -> bool:
    return _MODE == "dark"


def _hex(c: str) -> str | None:
    c = c.strip().lower()
    if c in NAMED:
        return NAMED[c]
    if re.fullmatch(r"#[0-9a-f]{3}", c):
        return "#" + "".join(ch * 2 for ch in c[1:])
    return c if re.fullmatch(r"#[0-9a-f]{6}", c) else None


def _hls(c: str):
    import colorsys
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)


def _from_hls(h, l, s) -> str:
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h, max(0, min(1, l)), max(0, min(1, s)))
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def dark_color(c: str, role: str) -> str:
    """role: bg | border | text.  Already-dark backgrounds and light text stay as they are."""
    raw = c.strip().lower()
    table = {"bg": DARK_BG, "border": DARK_BORDER, "text": DARK_TEXT}[role]
    if raw in table:
        return table[raw]
    hx = _hex(raw)
    if not hx:
        return c
    if hx in table:
        return table[hx]
    h, l, s = _hls(hx)
    if role == "bg":
        return _from_hls(h, 0.10 + (1 - l) * 0.6, s * 0.55) if l > 0.6 else c
    if role == "border":
        return _from_hls(h, 0.30, s * 0.4) if l > 0.6 else c
    # text: anything that wouldn't read on a dark background gets lightened
    return _from_hls(h, max(0.72, 1.05 - l), min(s, 0.9)) if l < 0.6 else c


_PROP = re.compile(
    r"(?P<prop>(?<![\w-])(?:background-color|background|color|bgcolor|"
    r"border(?:-top|-bottom|-left|-right)?(?:-color)?|selection-background-color|"
    r"selection-color|alternate-background-color|gridline-color))"
    r"(?P<sep>\s*[:=]\s*[\"']?)(?P<val>[^;\"'}<>]+)", re.I)
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|\b(?:white|black|red|green|gray|"
                    r"grey|orange|blue)\b", re.I)


def map_css(text: str) -> str:
    """Rewrite the colours in a stylesheet, style="" attribute or HTML for dark mode."""
    if not text or not is_dark():
        return text

    def prop(m):
        p = m.group("prop").lower()
        role = ("text" if p in ("color", "selection-color") else
                "border" if p.startswith("border") or p == "gridline-color" else "bg")
        val = _COLOR.sub(lambda c: dark_color(c.group(0), role), m.group("val"))
        return m.group("prop") + m.group("sep") + val
    return _PROP.sub(prop, text)


def _dark_stylesheet(scale: float) -> str:
    _set_mode("dark")
    css = map_css(scaled_stylesheet(scale))
    css += """
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox, QDateEdit, QTimeEdit {
    background: #1c2330; color: #e6edf3; }
QTextBrowser { background: #161b22; color: #e6edf3; }
QCheckBox::indicator, QRadioButton::indicator { background: #1c2330;
    border: 1px solid #6e7b8c; width: 14px; height: 14px; }
QCheckBox::indicator { border-radius: 3px; }
QRadioButton::indicator { border-radius: 8px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { background: #1a73e8;
    border-color: #79b8ff; }
QCheckBox::indicator:checked { image: url("@CHECK@"); }
QTreeWidget, QTreeView, QListWidget, QListView, QTableView {
    background: #161b22; color: #e6edf3; alternate-background-color: #1a212b;
    selection-background-color: #1f3a63; selection-color: #ffffff; }
QListWidget#Nav { background: #0b1d31; }
QLabel#Brand, QLabel#BrandSub { background: #0b1d31; }
QHeaderView::section { color: #e6edf3; }
QScrollBar:vertical, QScrollBar:horizontal { background: #161b22; }
QScrollBar::handle { background: #3a4352; border-radius: 4px; }
QMenuBar, QStatusBar { background: #0f141b; color: #c9d1d9; }
QDockWidget { color: #e6edf3; }
QDockWidget::title { background: #161b22; padding: 4px; }
QSplitter::handle { background: #232b38; }
a { color: #79b8ff; }
"""
    try:
        from ..resources import resource_path
        check = resource_path("assets/check_dark.svg").replace("\\", "/")
    except Exception:  # noqa: BLE001
        check = ""
    return css.replace("@CHECK@", check)


def _set_mode(m: str):
    global _MODE
    _MODE = m


def dark_palette():
    from PySide6.QtGui import QColor, QPalette
    p = QPalette()
    text, base, window = QColor("#e6edf3"), QColor("#1c2330"), QColor("#0f141b")
    for group in (QPalette.Active, QPalette.Inactive):
        p.setColor(group, QPalette.Window, window)
        p.setColor(group, QPalette.WindowText, text)
        p.setColor(group, QPalette.Base, base)
        p.setColor(group, QPalette.AlternateBase, QColor("#1a212b"))
        p.setColor(group, QPalette.Text, text)
        p.setColor(group, QPalette.Button, QColor("#232b38"))
        p.setColor(group, QPalette.ButtonText, text)
        p.setColor(group, QPalette.ToolTipBase, QColor("#30363d"))
        p.setColor(group, QPalette.ToolTipText, text)
        p.setColor(group, QPalette.PlaceholderText, QColor("#7d8590"))
        p.setColor(group, QPalette.Highlight, QColor("#1f3a63"))
        p.setColor(group, QPalette.HighlightedText, QColor("#ffffff"))
        p.setColor(group, QPalette.Link, QColor("#79b8ff"))
        p.setColor(group, QPalette.LinkVisited, QColor("#c39bff"))
        p.setColor(group, QPalette.BrightText, QColor("#ffffff"))
        p.setColor(group, QPalette.Light, QColor("#3a4352"))
        p.setColor(group, QPalette.Mid, QColor("#2a3240"))
        p.setColor(group, QPalette.Dark, QColor("#0b0f14"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#6e7781"))
    p.setColor(QPalette.Disabled, QPalette.Base, QColor("#161b22"))
    p.setColor(QPalette.Disabled, QPalette.Window, window)
    p.setColor(QPalette.Disabled, QPalette.Button, QColor("#1f2630"))
    return p


# --------------------------------------------- applying colours everywhere ---
_ORIG: dict = {}


def _colored(t) -> bool:
    return isinstance(t, str) and ("color" in t or "background" in t) and \
        ("<" in t or ":" in t)


def _map_brush(b):
    from PySide6.QtGui import QBrush, QColor
    if not is_dark():
        return b
    try:
        br = QBrush(b) if not isinstance(b, QBrush) else b
        if br.style() == 0:          # Qt.NoBrush – “use the default colour”
            return b
        return QBrush(QColor(dark_color(br.color().name(), "text")))
    except Exception:  # noqa: BLE001
        return b


def _install_hooks():
    if _ORIG:
        return
    from PySide6.QtGui import QTextDocument
    from PySide6.QtWidgets import (
        QLabel, QListWidgetItem, QTableWidgetItem, QTextEdit, QTreeWidgetItem, QWidget,
    )
    _ORIG.update(ss=QWidget.setStyleSheet, txt=QLabel.setText, html=QTextEdit.setHtml,
                 dss=QTextDocument.setDefaultStyleSheet,
                 tfg=QTableWidgetItem.setForeground, lfg=QListWidgetItem.setForeground,
                 rfg=QTreeWidgetItem.setForeground)

    def set_ss(self, css):
        self.setProperty("_gb_css", css or "")
        _ORIG["ss"](self, map_css(css) if css else css)

    def set_txt(self, text):
        if _colored(text):
            self.setProperty("_gb_txt", text)
            _ORIG["txt"](self, map_css(text))
        else:
            if self.property("_gb_txt") is not None:
                self.setProperty("_gb_txt", None)
            _ORIG["txt"](self, text)

    def set_html(self, html):
        self.setProperty("_gb_html", html)
        _ORIG["html"](self, map_css(html))

    def set_dss(self, css):
        _ORIG["dss"](self, map_css(css))

    QWidget.setStyleSheet = set_ss
    QLabel.setText = set_txt
    QTextEdit.setHtml = set_html
    QTextDocument.setDefaultStyleSheet = set_dss
    QTableWidgetItem.setForeground = lambda self, b: _ORIG["tfg"](self, _map_brush(b))
    QListWidgetItem.setForeground = lambda self, b: _ORIG["lfg"](self, _map_brush(b))
    QTreeWidgetItem.setForeground = lambda self, c, b: _ORIG["rfg"](self, c, _map_brush(b))


def polish(w):
    """First look at a widget: catch colours given in its constructor."""
    from PySide6.QtWidgets import QLabel
    try:
        if w.property("_gb_seen"):
            return
        w.setProperty("_gb_seen", True)
        css = w.styleSheet()
        if css and w.property("_gb_css") is None:
            w.setProperty("_gb_css", css)
            if is_dark():
                _ORIG["ss"](w, map_css(css))
        if isinstance(w, QLabel):
            t = QLabel.text(w)
            if _colored(t) and w.property("_gb_txt") is None:
                w.setProperty("_gb_txt", t)
                if is_dark():
                    _ORIG["txt"](w, map_css(t))
    except Exception:  # noqa: BLE001
        pass


def refresh_all(app):
    """Re-apply every widget's own colours after switching light ↔ dark."""
    from PySide6.QtWidgets import QLabel, QTextEdit
    for w in app.allWidgets():
        try:
            polish(w)                    # first time we see it: remember its own colours
            css = w.property("_gb_css")
            if css:
                _ORIG["ss"](w, map_css(css))
            if isinstance(w, QLabel) and w.property("_gb_txt"):
                _ORIG["txt"](w, map_css(w.property("_gb_txt")))
            if isinstance(w, QTextEdit) and w.property("_gb_html"):
                _ORIG["html"](w, map_css(w.property("_gb_html")))
        except Exception:  # noqa: BLE001
            continue


def wanted_mode(app=None) -> str:
    try:
        from ..settings import settings
        m = (settings.get("ui/theme", "light") or "light").lower()
    except Exception:  # noqa: BLE001
        m = "light"
    if m == "system":
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QGuiApplication
            hints = (app or QGuiApplication.instance()).styleHints()
            return "dark" if hints.colorScheme() == Qt.ColorScheme.Dark else "light"
        except Exception:  # noqa: BLE001
            return "light"
    return "dark" if m == "dark" else "light"
