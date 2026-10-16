"""Application entry point for the Maxwell-Bloch solver GUI.

This module creates the QApplication, configures the splash screen, and shows
the main application window.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from mbstudio.paths import APP_ICON_PATH, APP_IMAGE_PATH
from mbstudio.config.app_metadata import APP_VERSION


def main(argv: Sequence[str] | None = None) -> int:
    """Launch the Maxwell-Bloch solver application.

    Args:
        argv: Optional command-line argument sequence. If ``None``, the process
            arguments from ``sys.argv`` are used.

    Returns:
        Qt application exit code.
    """
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    try:
        import mbsolver  # noqa: F401
        import sciwidgets  # noqa: F401
    except ImportError as exc:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(
            None,
            "Missing package",
            f"This version needs the '{exc.name}' package.\n\n"
            "Reinstall the app with:\n\n"
            "    pipx install --force maxwell-bloch-studio\n\n"
            "or, in a source checkout, run pip install -e .",
        )
        return 1
    from sciwidgets.splash import SplashScreen  # after the missing-package check

    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    app.setApplicationDisplayName("Maxwell Bloch Studio")

    base = 35
    splash = SplashScreen(
        APP_IMAGE_PATH,
        size=(16 * base, 9 * base),
        title="Maxwell\nBloch\nStudio",
        subtitle=f"Version {APP_VERSION}",
        font_family="Times New Roman",
        delay=0.05,
    )
    splash.show_message("Starting...")

    from mbstudio.app.main_window import MBESolverApp

    window = MBESolverApp(app)
    window.show()
    splash.finish(window)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
