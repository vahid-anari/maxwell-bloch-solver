"""Check PyPI for a newer version of the application.

The check reads the latest released version from PyPI's JSON API and compares
it with the running version. It uses ``QNetworkAccessManager`` so the request
is asynchronous and runs on the main thread without blocking the UI.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from mbsolver.config.app_metadata import APP_NAME, APP_VERSION, DIST_NAME

VERSION_URL = f"https://pypi.org/pypi/{DIST_NAME}/json"
"""PyPI JSON API of the package; ``info.version`` is the latest release."""

PROJECT_URL = f"https://pypi.org/project/{DIST_NAME}/"
"""PyPI page offered to the user when an update exists."""

REQUEST_TIMEOUT_MS = 5000
"""Maximum time allowed for the network request, in milliseconds."""


def parse_version(text: str) -> tuple[int, ...]:
    """Convert a version string such as '8.6' or 'v8.6.1' to a comparable tuple.

    Args:
        text: Version string, optionally prefixed with 'v'.

    Returns:
        Tuple of integers; parsing stops at the first non-numeric part.
    """

    parts: list[int] = []
    for p in text.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


class UpdateChecker(QObject):
    """Query PyPI asynchronously and report whether a newer version exists."""

    updateAvailable = Signal(str, str)
    """Emitted with ``(latest_version, project_url)`` when a newer version exists."""

    upToDate = Signal()
    """Emitted when the running version is the latest."""

    checkFailed = Signal(str)
    """Emitted with an error message when the check could not complete."""

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the checker.

        Args:
            parent: Optional parent object.
        """

        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)

    def check(self) -> None:
        """Start an asynchronous check; results arrive through the signals."""

        if not parse_version(APP_VERSION) or APP_VERSION.startswith("0+"):
            self.checkFailed.emit("The running version is unknown (not installed as a package).")
            return
        request = QNetworkRequest(QUrl(VERSION_URL))
        request.setRawHeader(b"User-Agent", f"{APP_NAME}/{APP_VERSION}".encode())
        request.setTransferTimeout(REQUEST_TIMEOUT_MS)
        reply = self._manager.get(request)
        reply.finished.connect(lambda: self._on_finished(reply))

    def _on_finished(self, reply: QNetworkReply) -> None:
        """Parse PyPI's answer and emit the matching signal.

        Args:
            reply: Finished network reply.
        """

        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.checkFailed.emit(reply.errorString())
                return

            data = json.loads(bytes(reply.readAll()).decode("utf-8"))
            latest = str(data["info"]["version"])
            if parse_version(latest) > parse_version(APP_VERSION):
                self.updateAvailable.emit(latest, PROJECT_URL)
            else:
                self.upToDate.emit()
        except (ValueError, KeyError, TypeError) as e:
            self.checkFailed.emit(str(e))
        finally:
            reply.deleteLater()


def _demo_main() -> int:
    """Run a single update check from the command line.

    Returns:
        Qt application exit code.
    """

    import sys

    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication(sys.argv)
    checker = UpdateChecker()

    checker.updateAvailable.connect(
        lambda v, url: (print(f"Update available: {v} -> {url}"), app.quit())
    )
    checker.upToDate.connect(
        lambda: (print(f"Up to date ({APP_VERSION})"), app.quit())
    )
    checker.checkFailed.connect(
        lambda msg: (print(f"Check failed: {msg}"), app.quit())
    )

    checker.check()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
