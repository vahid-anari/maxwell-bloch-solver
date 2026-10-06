"""Check GitHub for a newer version of the application.

The check reads ``APP_VERSION`` from ``settings/app_metadata.py`` on the
repository's main branch and compares it with the running version. It uses
``QNetworkAccessManager`` so the request is asynchronous and runs on the main
thread without blocking the UI.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from settings.app_metadata import APP_AUTHOR_GITHUB, APP_NAME, APP_VERSION

_REPO = APP_AUTHOR_GITHUB.rstrip("/").replace("https://github.com/", "")
"""Repository identifier in ``owner/name`` form."""

METADATA_PATH = "settings/app_metadata.py"
"""Path of the metadata file inside the repository."""

VERSION_FILE_URL = f"https://raw.githubusercontent.com/{_REPO}/main/{METADATA_PATH}"
"""Raw metadata file on the main branch, read to find the latest version."""

DOWNLOAD_URL = f"https://github.com/{_REPO}/archive/refs/heads/main.zip"
"""Zip of the current main branch, offered to the user when an update exists."""

REQUEST_TIMEOUT_MS = 5000
"""Maximum time allowed for the network request, in milliseconds."""

_VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
"""Pattern extracting the version string from the metadata file."""


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
    """Query GitHub asynchronously and report whether a newer version exists."""

    updateAvailable = Signal(str, str)
    """Emitted with ``(latest_version, download_url)`` when a newer version exists."""

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

        request = QNetworkRequest(QUrl(VERSION_FILE_URL))
        request.setRawHeader(b"User-Agent", f"{APP_NAME}/{APP_VERSION}".encode())
        request.setTransferTimeout(REQUEST_TIMEOUT_MS)
        reply = self._manager.get(request)
        reply.finished.connect(lambda: self._on_finished(reply))

    def _on_finished(self, reply: QNetworkReply) -> None:
        """Parse the remote metadata file and emit the matching signal.

        Args:
            reply: Finished network reply.
        """

        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.checkFailed.emit(reply.errorString())
                return

            text = bytes(reply.readAll()).decode("utf-8")
            match = _VERSION_RE.search(text)
            if match is None:
                self.checkFailed.emit("APP_VERSION not found in remote metadata")
                return

            latest = match.group(1)
            if parse_version(latest) > parse_version(APP_VERSION):
                self.updateAvailable.emit(latest, DOWNLOAD_URL)
            else:
                self.upToDate.emit()
        except ValueError as e:
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
