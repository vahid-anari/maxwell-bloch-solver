"""Application entry point for the Maxwell-Bloch solver GUI.

This module creates the QApplication, configures the splash screen, and shows
the main application window.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from paths import APP_ICON_PATH, APP_IMAGE_PATH
from settings import splash_state
from ui.splash_screen import SplashScreen


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
        import maxbloch  # noqa: F401
        import sciwidgets  # noqa: F401
    except ImportError as exc:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(
            None,
            "Missing package",
            f"This version needs the '{exc.name}' package.\n\n"
            "In the app's folder, run:\n\n"
            "    pip install -r requirements.txt\n\n"
            "then start the app again.",
        )
        return 1
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    app.setApplicationDisplayName("Maxwell Bloch Solver")

    base = 35
    splash_width = 16 * base
    splash_height = 9 * base

    splash = SplashScreen(app, str(APP_IMAGE_PATH), splash_width, splash_height, 0.05)
    splash.show_message("Starting...")
    splash_state.splash = splash

    from app.main_window import MBESolverApp

    window = MBESolverApp(app)
    window.show()
    splash.finish(window)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
