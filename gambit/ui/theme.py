"""App-wide look and feel."""

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


def apply_theme(app, scale: float | None = None):
    """Call once at startup (main app and Builder). `scale` changes text size."""
    from PySide6.QtCore import Qt
    if scale is None:
        try:
            from ..settings import settings
            scale = float(settings.get("ui/text_scale", 1.0) or 1.0)
        except Exception:  # noqa: BLE001
            scale = 1.0

    try:  # Qt 6.8+: tell Qt we are a light-only app
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except Exception:
        pass
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    font = app.font()
    font.setPointSizeF(10 * scale)
    app.setFont(font)
    app.setStyleSheet(scaled_stylesheet(scale))
