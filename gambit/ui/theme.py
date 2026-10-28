"""App-wide look and feel."""
import re

ACCENT = "#2563EB"
DEFAULT_ACCENT = ACCENT
ACCENTS = {"Blue": "#2563EB", "Teal": "#0F766E", "Purple": "#7C3AED", "Red": "#B91C1C",
           "Green": "#15803D", "Orange": "#C2410C", "Navy": "#1E3A8A"}


def accent() -> str:
    try:
        from ..settings import settings
        a = (settings.get("ui/accent", "") or "").strip()
    except Exception:  # noqa: BLE001
        a = ""
    return a if re.fullmatch(r"#[0-9a-fA-F]{6}", a or "") else DEFAULT_ACCENT


def _shade(c: str, f: float) -> str:
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    if f < 0:
        r, g, b = (round(x * (1 + f)) for x in (r, g, b))
    else:
        r, g, b = (round(x + (255 - x) * f) for x in (r, g, b))
    return "#%02x%02x%02x" % (r, g, b)


def tokens(mode: str | None = None) -> dict:
    """The design tokens for light or dark (the Windows 11 look from the mock-up)."""
    m = mode or _MODE
    a = accent()
    if m == "dark":
        return {"window": "#0B0F15", "sidebar": "#10151D", "topbar": "#0B0F15",
                "surface": "#161C25", "surface2": "#1B2330", "border": "#222C3A",
                "input": "#2E3A4B", "text": "#E6EAF0", "muted": "#A3ADBB",
                "faint": "#8B95A3", "icon": "#C5CCD6", "hover": "#1E2733",
                "selected": "#1D2C44", "row_line": "#1F2835", "header": "#1A212B",
                "scroll": "#334155", "accent": a, "accent_hover": _shade(a, 0.12),
                "accent_text": _shade(a, 0.45), "on_accent": "#FFFFFF",
                "danger": "#FCA5A5", "danger_bg": "#3B1C1C", "danger_line": "#7F1D1D",
                "banner": "#1B2330", "banner_line": "#2A3545", "banner_text": "#E6EAF0",
                "field": "#0F141B", "line_strong": "#2A3545", "input_bg": "#0F141B",
                "tooltip": "#E6EAF0", "tooltip_text": "#111827",
                "banner_warn": "#3A2A06", "banner_warn_line": "#A16207",
                "banner_warn_text": "#FDE68A", "good_bg": "#0F2A1A", "good_line": "#166534",
                "good_text": "#86EFAC"}
    return {"window": "#EEF2F7", "sidebar": "#F5F7FA", "topbar": "#F8FAFC",
            "surface": "#FFFFFF", "surface2": "#F4F6FA", "border": "#DCE2EA",
            "input": "#D0D7E2", "text": "#111827", "muted": "#4B5563", "faint": "#6B7280",
            "icon": "#374151", "hover": "#EEF2F8", "selected": "#E8F0FE",
            "row_line": "#EEF1F5", "header": "#F8FAFC", "scroll": "#C7CED9",
            "accent": a, "accent_hover": _shade(a, -0.12), "accent_text": a,
            "on_accent": "#FFFFFF", "danger": "#B91C1C", "danger_bg": "#FEF2F2",
            "danger_line": "#FECACA", "banner": "#EFF4FF", "banner_line": "#D6E2FB",
            "banner_text": "#1E3A8A", "field": "#F8FAFC", "line_strong": "#D0D7E2", "input_bg": "#FFFFFF",
            "banner_warn": "#FFFBEB", "banner_warn_line": "#FCD34D",
            "banner_warn_text": "#78350F", "good_bg": "#ECFDF3", "good_line": "#86EFAC",
            "good_text": "#166534", "tooltip": "#111827", "tooltip_text": "#FFFFFF"}


def build_css(mode: str = "light") -> str:
    t = tokens(mode)
    try:
        from ..resources import resource_path
        check = resource_path("assets/check_dark.svg").replace("\\", "/")
    except Exception:  # noqa: BLE001
        check = ""
    return f"""
QWidget {{ font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif;
          font-size: 10.5pt; color: {t['text']}; }}
QMainWindow, QWidget#Page, QScrollArea > QWidget > QWidget#Page {{ background: {t['window']}; }}
QStackedWidget, QSplitter {{ background: {t['window']}; }}

/* ---------- sidebar ---------- */
QWidget#Side {{ background: {t['sidebar']}; border-right: 1px solid {t['border']}; }}
QListWidget#Nav {{ background: {t['sidebar']}; border: none; padding: 4px 0; outline: 0; }}
QListWidget#Nav::item {{ color: {t['text']}; padding: 8px 12px; margin: 1px 10px;
                        border-radius: 8px; border-left: 3px solid transparent; }}
QListWidget#Nav::item:hover {{ background: {t['hover']}; }}
QListWidget#Nav::item:selected {{ background: {t['surface']}; color: {t['text']};
                                 border-left: 3px solid {t['accent']}; font-weight: 600; }}
QLabel#Brand {{ background: transparent; color: {t['text']}; font-size: 13.5pt; font-weight: 700; }}
QLabel#BrandSub {{ background: transparent; color: {t['muted']}; font-size: 9pt; }}
QLabel#Logo {{ background: {t['accent']}; color: {t['on_accent']}; border-radius: 10px;
              font-weight: 700; font-size: 11pt; }}
QPushButton#RailToggle {{ background: transparent; border: none; border-radius: 8px;
                         padding: 6px; }}
QPushButton#RailToggle:hover {{ background: {t['hover']}; }}

/* ---------- top bar ---------- */
QWidget#TopBar {{ background: {t['topbar']}; border-bottom: 1px solid {t['border']}; }}
QLineEdit#GlobalSearch {{ background: {t['surface']}; border: 1px solid {t['line_strong']};
                         border-radius: 10px; padding: 8px 12px; min-height: 22px; }}
QLineEdit#GlobalSearch:focus {{ border: 1px solid {t['accent']}; }}
QPushButton#Chip, QToolButton#Chip {{ background: {t['surface']}; border: 1px solid {t['line_strong']};
                   border-radius: 10px; padding: 8px 12px; min-height: 22px; }}
QPushButton#Chip:hover, QToolButton#Chip:hover {{ background: {t['hover']}; }}
QPushButton#ChipOn {{ background: {t['banner_warn']}; color: {t['banner_warn_text']};
                     border: 1px solid {t['banner_warn_line']}; border-radius: 10px;
                     padding: 8px 12px; min-height: 22px; font-weight: 600; }}
QPushButton#ChipGood {{ background: {t['good_bg']}; color: {t['good_text']};
                       border: 1px solid {t['good_line']}; border-radius: 10px;
                       padding: 8px 12px; min-height: 22px; font-weight: 600; }}
QToolButton#UserChip {{ background: {t['surface']}; border: 1px solid {t['line_strong']};
                       border-radius: 20px; padding: 4px 12px 4px 4px; }}
QToolButton#UserChip:hover {{ background: {t['hover']}; }}
QToolButton#UserChip::menu-indicator {{ image: none; width: 0; }}
QComboBox#DomainChip {{ background: {t['surface']}; border: 1px solid {t['line_strong']};
                       border-radius: 10px; padding: 8px 12px 8px 12px; min-height: 22px; }}
QLabel#Badge {{ background: #DC2626; color: white; border-radius: 8px; font-size: 7.5pt;
               font-weight: 700; padding: 0 5px; }}

/* ---------- text ---------- */
QLabel#PageTitle {{ font-size: 18pt; font-weight: 700; color: {t['text']}; }}
QLabel#PageSub {{ color: {t['muted']}; }}
QLabel#Muted {{ color: {t['muted']}; }}
QLabel#Small {{ color: {t['muted']}; font-size: 8.5pt; }}
QLabel#Greeting {{ font-size: 21pt; font-weight: 700; }}
QLabel#SectionTitle {{ font-size: 12pt; font-weight: 600; }}
QLabel#TileLabel {{ color: {t['muted']}; font-size: 10pt; background: transparent; }}
QLabel#TileValue {{ font-size: 23pt; font-weight: 700; background: transparent; }}
QLabel#TileSub {{ font-size: 9pt; font-weight: 600; background: transparent; }}
QLabel#RowTitle {{ font-weight: 600; background: transparent; }}
QLabel#RowSub {{ color: {t['muted']}; font-size: 9pt; background: transparent; }}
QFrame#RecentRow {{ background: transparent; border: none; border-radius: 10px; }}
QFrame#RecentRow:hover, QFrame#RecentRow:focus {{ background: {t['hover']}; }}
QFrame#BigSearch {{ background: {t['field']}; border: 1px solid {t['line_strong']};
                   border-radius: 12px; }}
QFrame#BigSearch QLineEdit {{ background: transparent; border: none; font-size: 11.5pt;
                             padding: 10px 4px; }}

/* ---------- cards ---------- */
QGroupBox {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 14px;
            margin-top: 0px; padding: 48px 20px 20px 20px; font-weight: 600;
            font-size: 12pt; }}
QGroupBox::title {{ subcontrol-origin: padding; subcontrol-position: top left;
                   left: 20px; top: 18px; padding: 0; color: {t['text']}; }}
QGroupBox QLabel, QGroupBox QCheckBox, QGroupBox QRadioButton {{ font-weight: normal;
                                                               font-size: 10.5pt; }}
QFrame#Card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 14px; }}
QLabel#CardValue {{ font-size: 20pt; font-weight: 700; }}
QLabel#Banner, QFrame#Banner {{ background: {t['banner']}; border: 1px solid {t['banner_line']};
                               color: {t['banner_text']}; border-radius: 12px; padding: 12px 16px; }}
QLabel#HelpStrip {{ border-radius: 10px; }}

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit,
QTimeEdit, QDateTimeEdit {{
    background: {t['input_bg']}; color: {t['text']}; border: 1px solid {t['input']};
    border-radius: 10px; padding: 8px 12px; selection-background-color: {t['selected']};
    selection-color: {t['text']}; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus {{ border: 1px solid {t['accent']}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ background: {t['surface2']};
                                                            color: {t['faint']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {t['surface']}; color: {t['text']};
    border: 1px solid {t['border']}; outline: 0; padding: 4px;
    selection-background-color: {t['selected']}; selection-color: {t['text']}; }}
QComboBox QAbstractItemView::item {{ min-height: 26px; padding: 2px 8px; border-radius: 6px; }}
QCheckBox, QRadioButton {{ color: {t['text']}; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px;
    border: 1px solid {t['input']}; background: {t['surface']}; }}
QCheckBox::indicator {{ border-radius: 5px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']};
                               image: url("{check}"); }}
QRadioButton::indicator:checked {{ border: 1px solid {t['accent']};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 {t['accent']}, stop:0.55 {t['accent']}, stop:0.62 {t['surface']},
        stop:1 {t['surface']}); }}

/* ---------- buttons ---------- */
QPushButton {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['input']};
              border-radius: 10px; padding: 8px 16px; min-height: 22px; }}
QPushButton:hover {{ background: {t['hover']}; }}
QPushButton:pressed {{ background: {t['selected']}; }}
QPushButton:checked {{ background: {t['selected']}; border-color: {t['accent']}; }}
QPushButton:disabled {{ color: {t['faint']}; background: {t['surface2']}; }}
QPushButton[kind="primary"] {{ background: {t['accent']}; color: {t['on_accent']};
                              border: 1px solid {t['accent']}; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {t['accent_hover']};
                                    border-color: {t['accent_hover']}; }}
QPushButton[kind="danger"] {{ color: {t['danger']}; border-color: {t['danger_line']}; }}
QPushButton[kind="danger"]:hover {{ background: {t['danger_bg']}; }}
QPushButton[kind="primary"]:disabled, QPushButton[kind="danger"]:disabled {{
    background: {t['surface2']}; color: {t['faint']}; border: 1px solid {t['border']}; }}
QToolButton {{ border: none; border-radius: 8px; padding: 4px; background: transparent; }}
QToolButton:hover {{ background: {t['hover']}; }}

/* ---------- tabs ---------- */
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ padding: 7px 14px; margin: 0 4px 8px 0; border-radius: 9px;
               color: {t['muted']}; background: transparent; border: 1px solid transparent; }}
QTabBar::tab:hover {{ background: {t['hover']}; color: {t['text']}; }}
QTabBar::tab:selected {{ background: {t['surface']}; color: {t['text']}; font-weight: 600;
                        border: 1px solid {t['border']}; }}

/* ---------- tables and lists ---------- */
QTableView, QTableWidget, QTreeView, QTreeWidget, QListView, QListWidget {{
    background: {t['surface']}; color: {t['text']}; border: 1px solid {t['border']};
    border-radius: 12px; gridline-color: {t['row_line']}; outline: 0;
    alternate-background-color: {t['surface']};
    selection-background-color: {t['selected']}; selection-color: {t['text']}; }}
QTableView::item, QTableWidget::item {{ padding: 4px 8px; border-bottom: 1px solid {t['row_line']}; }}
QTableView::item:hover, QTableWidget::item:hover, QTreeView::item:hover,
QListView::item:hover {{ background: {t['hover']}; }}
QTableView::item:selected, QTableWidget::item:selected, QTreeView::item:selected,
QListView::item:selected {{ background: {t['selected']}; color: {t['text']}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {t['header']}; color: {t['muted']}; border: none;
    border-bottom: 1px solid {t['border']}; padding: 8px 10px; font-weight: 600;
    font-size: 8.5pt; }}
QTableCornerButton::section {{ background: {t['header']}; border: none; }}

/* ---------- scroll bars ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {t['scroll']}; border-radius: 4px; min-height: 28px;
                     min-width: 28px; }}
QScrollBar::handle:hover {{ background: {t['faint']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}

/* ---------- menus, tips, dialogs ---------- */
QMenu {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['border']};
        border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t['selected']}; color: {t['text']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}
QToolTip {{ background: {t['tooltip']}; color: {t['tooltip_text']}; border: none;
           border-radius: 6px; padding: 6px 9px; }}
QDialog, QMessageBox, QInputDialog, QFileDialog {{ background: {t['window']}; }}
QMessageBox QLabel, QDialog QLabel {{ color: {t['text']}; }}
QStatusBar {{ background: {t['topbar']}; color: {t['muted']}; border-top: 1px solid {t['border']}; }}
QSplitter::handle {{ background: {t['border']}; }}
QSplitter::handle:vertical {{ height: 1px; }}
QDockWidget {{ color: {t['text']}; }}
QDockWidget::title {{ background: {t['surface2']}; padding: 6px; }}
QProgressBar {{ border: none; border-radius: 4px; text-align: center; background: {t['surface2']};
               max-height: 8px; }}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 4px; }}
QPlainTextEdit#Log {{ background: #0D1117; color: #D1D9E0; border: 1px solid {t['border']};
    border-radius: 12px; font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 9.5pt; padding: 8px; }}

/* ---------- toasts, palette, selection bar ---------- */
QFrame#Toast {{ background: #111827; border-radius: 12px; }}
QFrame#Toast QLabel {{ color: #F9FAFB; }}
QFrame#Toast QPushButton {{ background: #1F2937; color: #F9FAFB; border: 1px solid #374151;
                          border-radius: 8px; padding: 5px 12px; font-weight: 600; }}
QFrame#Toast QPushButton:hover {{ background: #374151; }}
QFrame#SelBar {{ background: #111827; border-radius: 14px; }}
QFrame#SelBar QLabel {{ color: #F9FAFB; font-weight: 600; }}
QFrame#SelBar QPushButton {{ background: #1F2937; color: #F9FAFB; border: 1px solid #374151;
                           border-radius: 9px; padding: 6px 12px; }}
QFrame#SelBar QPushButton:hover {{ background: #374151; }}
QFrame#SelBar QPushButton[kind="danger"] {{ background: #DC2626; border-color: #DC2626;
                                          color: white; font-weight: 600; }}
QDialog#Palette {{ background: transparent; }}
QFrame#PaletteBox {{ background: {t['surface']}; border: 1px solid {t['border']};
                    border-radius: 14px; }}
QLineEdit#PaletteInput {{ border: none; border-bottom: 1px solid {t['row_line']};
    border-radius: 0; padding: 14px 16px; font-size: 12.5pt; background: transparent; }}
QListWidget#PaletteList {{ border: none; background: transparent; padding: 6px; }}
QListWidget#PaletteList::item {{ padding: 9px 10px; border-radius: 9px; }}
QListWidget#PaletteList::item:selected {{ background: {t['selected']}; }}
"""


STYLESHEET = ""     # built on demand (build_css) – kept for older imports


def light_palette():
    """A fixed light palette so Windows dark mode can't make text unreadable."""
    from PySide6.QtGui import QColor, QPalette

    p = QPalette()
    text, base, window = QColor("#111827"), QColor("#ffffff"), QColor("#EEF2F7")
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
        p.setColor(group, QPalette.Link, QColor(accent()))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#9aa4ae"))
    p.setColor(QPalette.Disabled, QPalette.Base, QColor("#f2f4f7"))
    p.setColor(QPalette.Disabled, QPalette.Window, window)
    p.setColor(QPalette.Disabled, QPalette.Button, QColor("#f2f4f7"))
    return p


def scaled_stylesheet(scale: float, mode: str = "light") -> str:
    """The stylesheet with every font size multiplied by `scale`."""
    css = build_css(mode)
    if abs(scale - 1.0) < 0.01:
        return css
    return re.sub(r"(\d+(?:\.\d+)?)pt",
                  lambda m: f"{float(m.group(1)) * scale:.1f}pt", css)


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
    css = _dark_stylesheet(scale) if m == "dark" else scaled_stylesheet(scale, "light")
    try:
        from ..settings import settings as _s
        if _s.get("ui/contrast", False):
            css += contrast_css(m)
    except Exception:  # noqa: BLE001
        pass
    app.setStyleSheet(css)
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
    "#ffffff": "#161c25", "white": "#161c25", "#f6f8fb": "#0f141b", "#eef2f7": "#0f141b",
    "#f4f6fa": "#1b2330", "#fef2f2": "#3b1c1c", "#fffbeb": "#3a2a06", "#e8f0fe": "#1d2c44", "#f6f8fa": "#1c2330",
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
    return scaled_stylesheet(scale, "dark")


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


def contrast_css(mode: str) -> str:
    """Settings → Appearance → High contrast: stronger text, borders and focus outlines."""
    fg, bg, line = ("#ffffff", "#000000", "#ffffff") if mode == "dark" else \
        ("#000000", "#ffffff", "#000000")
    return f"""
QWidget {{ color: {fg}; }}
QLabel#Muted, QLabel#Small, QLabel#PageSub {{ color: {fg}; }}
QPushButton, QLineEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QPlainTextEdit,
QTextEdit, QTableView, QTableWidget, QTreeWidget, QListWidget {{
    border: 2px solid {line};
}}
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QListWidget:focus,
QTableView:focus, QCheckBox:focus, QRadioButton:focus {{
    outline: 3px solid #ffbf00; border: 3px solid #ffbf00;
}}
QFrame#Card {{ border: 2px solid {line}; background: {bg}; }}
"""
