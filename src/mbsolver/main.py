"""Application entry point for the Maxwell-Bloch solver GUI.

This module creates the QApplication, configures the splash screen, and shows
the main application window.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from mbsolver.paths import APP_ICON_PATH, APP_IMAGE_PATH
from mbsolver.config import splash_state
from mbsolver.ui.splash_screen import SplashScreen


def _show_renamed_notice() -> None:
    """Tell the user that the app continues as Maxwell Bloch Studio."""
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(
        QMessageBox.Information,
        "Maxwell Bloch Studio",
        "Maxwell Bloch Solver is now called Maxwell Bloch Studio.\n"
        "This version gets no further updates.",
    )
    box.setInformativeText(
        "To switch, close the app and run in a terminal:\n\n"
        "    pipx uninstall maxwell-bloch-solver\n"
        "    pipx install maxwell-bloch-studio\n\n"
        "then start it with: maxwell-bloch-studio\n\n"
        "(With pip: pip uninstall maxwell-bloch-solver, then "
        "pip install maxwell-bloch-studio.)\n"
        "Your settings and parameter files carry over."
    )
    box.setTextInteractionFlags(Qt.TextSelectableByMouse)
    box.exec()


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
            "Reinstall the app with:\n\n"
            "    pipx install --force maxwell-bloch-solver\n\n"
            "or, in a source checkout, run pip install -e .",
        )
        return 1
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    app.setApplicationDisplayName("Maxwell Bloch Solver")
    _show_renamed_notice()

    base = 35
    splash_width = 16 * base
    splash_height = 9 * base

    splash = SplashScreen(app, str(APP_IMAGE_PATH), splash_width, splash_height, 0.05)
    splash.show_message("Starting...")
    splash_state.splash = splash

    from mbsolver.app.main_window import MBESolverApp

    window = MBESolverApp(app)
    window.show()
    splash.finish(window)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
