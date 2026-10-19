"""GAMbit – a friendly GUI for GAM (https://github.com/GAM-team/GAM)."""

import sys

from PySide6.QtWidgets import QApplication

from gambit.ui.main_window import MainWindow
from gambit.ui.theme import apply_theme
from gambit.version import APP_NAME


def main():
    if "--task" in sys.argv:           # scheduled background task – no window
        from gambit.headless import main as headless_main
        sys.exit(headless_main(sys.argv[1:]))
    from gambit import support
    if sys.platform.startswith("win"):
        try:  # Show our own icon in the taskbar instead of Python's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GAMbit.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    support.install_crash_handler()
    from PySide6.QtGui import QIcon
    from gambit.resources import resource_path
    app.setWindowIcon(QIcon(resource_path("assets/gambit.ico")))   # every window + taskbar
    apply_theme(app)
    from gambit.ui.login_dialog import gate
    if not gate():                      # GAMbit sign-in (when the team has turned it on)
        sys.exit(0)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
