"""Application splash-screen helpers and widget implementation."""

from time import sleep

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

import settings.splash_state as splash_state



def show_splash_message(text: str) -> None:
    """Show a message on the global splash screen, if one exists.

    Args:
        text: Message text to display on the shared splash-screen instance.

    Returns:
        None.
    """
    s = splash_state.splash
    if s is not None:
        s.show_message(text)
        QApplication.processEvents()


class SplashScreen(QSplashScreen):
    """Application splash screen with a simple message-display API.

    This widget wraps :class:`QSplashScreen` and provides a convenience method
    for displaying status text during application startup.
    """

    def __init__(
        self,
        app: QApplication,
        image_path: str,
        width: int,
        height: int,
        delay_sec: float = 0.0,
    ) -> None:
        """Initialize the splash screen.

        Args:
            app: Application instance associated with the splash screen.
            image_path: Path to the background image used for the splash screen.
            width: Target splash-screen width in pixels.
            height: Target splash-screen height in pixels.
            delay_sec: Delay in seconds applied after updating the splash
                message.

        Returns:
            None.
        """
        bg = QPixmap(image_path)
        pixmap = bg.scaled(
            width,
            height,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        super().__init__(pixmap)
        self.app = app
        self.delay_sec = delay_sec
        self.setFont(QFont("Times New Roman", 18))
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.show()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, event) -> None:
        """Handle the Qt ``mousePressEvent`` callback.

        Args:
            event: Mouse press event delivered by Qt.

        Returns:
            None.
        """
        event.accept()

    def show_message(self, message: str) -> None:
        """Show a message on the splash screen.

        The message rendering is scheduled through ``QTimer.singleShot`` and an
        optional blocking delay is applied afterward.

        Args:
            message: Message text to display.

        Returns:
            None.
        """
        QTimer.singleShot(0, lambda: self.show_0(message))
        sleep(self.delay_sec)

    def show_0(self, message: str) -> None:
        """Render a message in the splash screen's message area.

        Args:
            message: Message text to render.

        Returns:
            None.
        """
        self.showMessage(
            message,
            alignment=Qt.AlignBottom | Qt.AlignHCenter,
            color=Qt.white,
        )



def _demo_main() -> int:
    """Run this module as a standalone demo.

    Returns:
        Application exit code returned by Qt.
    """
    import sys

    from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

    from paths import ICONS_DIR

    class MainWindow(QMainWindow):
        """Simple main window used by the splash-screen demo."""

        def __init__(self) -> None:
            """Initialize the demo main window.

            Returns:
                None.
            """
            super().__init__()
            self.setWindowTitle("Main App")
            self.setCentralWidget(QLabel("Hello from the main window"))

    app = QApplication(sys.argv)

    # --- SplashAndIcon setup ---
    a = 35
    w = 16 * a
    h = 9 * a
    splash = SplashScreen(app, f"{ICONS_DIR}/app_image.png", w, h, 0.5)
    splash.show_message("Starting...")
    splash_state.splash = splash

    # Messages to show during startup
    steps = [
        "Loading configuration...",
        "Initializing models...",
        "Connecting to database...",
        "Preparing UI...",
        "Done.",
    ]

    win = MainWindow()

    def run_step(i: int = 0) -> None:
        """Run one startup step for the demo sequence.

        Args:
            i: Index of the startup step to display.

        Returns:
            None.
        """
        show_splash_message(steps[i])

        if i + 1 < len(steps):
            QTimer.singleShot(0, lambda: run_step(i + 1))
        else:
            win.show()
            splash.finish(win)

    QTimer.singleShot(0, run_step)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
