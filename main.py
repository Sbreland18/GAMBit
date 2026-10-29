"""GAMbit – a friendly GUI for GAM (https://github.com/GAM-team/GAM)."""

import sys


def main():
    if "--task" in sys.argv:           # scheduled background task – no window
        from gambit.headless import main as headless_main
        sys.exit(headless_main(sys.argv[1:]))
    if sys.platform.startswith("win"):
        try:  # Show our own icon in the taskbar instead of Python's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GAMbit.App")
        except Exception:
            pass
    # Only Qt and the start-up screen first, so something shows straight away
    from PySide6.QtWidgets import QApplication
    from gambit.version import APP_NAME, __version__
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    splash = None
    try:
        from gambit.ui.splash import Splash
        splash = Splash(__version__)
        splash.show()
        app.processEvents()
    except Exception:  # the start-up screen is a nicety – never stop GAMbit over it
        splash = None

    def step(msg, pct):
        if splash is not None:
            splash.step(msg, pct)

    step("Getting ready…", 10)
    from gambit import support
    support.install_crash_handler()
    try:                                # secrets saved by older versions → encrypted
        from gambit import secrets_store
        from gambit.settings import settings as _settings
        secrets_store.migrate(_settings)
    except Exception:  # noqa: BLE001
        pass
    from PySide6.QtGui import QIcon
    from gambit.resources import resource_path
    app.setWindowIcon(QIcon(resource_path("assets/gambit.ico")))   # every window + taskbar
    step("Applying your theme…", 20)
    from gambit.ui.theme import apply_theme
    apply_theme(app)
    from gambit.ui import dialogs
    dialogs.install()                   # modern message windows everywhere
    step("Loading GAMbit…", 35)
    from gambit.ui.main_window import MainWindow
    from gambit.ui.login_dialog import gate
    if splash is not None:
        splash.hide()
    if not gate():                      # GAMbit sign-in (when the team has turned it on)
        sys.exit(0)
    if splash is not None:
        splash.show()
    step("Building the window…", 60)
    win = MainWindow()
    step("Opening…", 95)
    win.show()
    win.restore_last_page()
    if splash is not None:
        splash.finish(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
