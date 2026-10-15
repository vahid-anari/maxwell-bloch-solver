"""Check PyPI for a newer version of the application.

The check reads the latest released version from PyPI's JSON API and compares
it with the running version. When a newer version exists, it also reads the
release notes of the newer versions from the GitHub Releases of the repository
(written from ``CHANGELOG.md`` at each release). The notes are optional: if
GitHub cannot be reached, the update is reported without them.

Both requests use ``QNetworkAccessManager``, so they are asynchronous and run on
the main thread without blocking the UI.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from mbstudio.config.app_metadata import APP_NAME, APP_VERSION, DIST_NAME, GITHUB_REPO

VERSION_URL = f"https://pypi.org/pypi/{DIST_NAME}/json"
"""PyPI JSON API of the package; ``info.version`` is the latest release."""

PROJECT_URL = f"https://pypi.org/project/{DIST_NAME}/"
"""PyPI page offered to the user when an update exists."""

RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=30"
"""GitHub API listing the releases (newest first) with their notes."""

RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
"""GitHub page with all release notes, offered to the user."""

REQUEST_TIMEOUT_MS = 5000
"""Maximum time allowed for each network request, in milliseconds."""

MAX_NOTES = 10
"""At most this many versions' notes are shown in the update notice."""


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


def newer_release_notes(
    releases: list, current: str, latest: str, limit: int = MAX_NOTES
) -> list[tuple[str, str]]:
    """Pick the notes of the versions newer than ``current``, up to ``latest``.

    Args:
        releases: Release list from the GitHub API (``tag_name``, ``body``,
            ``draft``, ``prerelease`` per entry).
        current: Running version.
        latest: Latest version on PyPI; GitHub releases above it are ignored.
        limit: Maximum number of versions returned.

    Returns:
        ``(version, notes_markdown)`` pairs, newest first. Versions without
        notes are left out.
    """

    cur, top = parse_version(current), parse_version(latest)
    picked: list[tuple[tuple[int, ...], str, str]] = []
    for rel in releases:
        if not isinstance(rel, dict) or rel.get("draft") or rel.get("prerelease"):
            continue
        tag = str(rel.get("tag_name") or "")
        ver = parse_version(tag)
        body = str(rel.get("body") or "").strip()
        if ver and cur < ver <= top and body:
            picked.append((ver, tag.lstrip("vV"), body))
    picked.sort(reverse=True)
    return [(v, b) for _, v, b in picked[:limit]]


class UpdateChecker(QObject):
    """Query PyPI asynchronously and report whether a newer version exists."""

    updateAvailable = Signal(str, str, object)
    """Emitted with ``(latest_version, project_url, notes)`` when a newer version exists.

    ``notes`` is a list of ``(version, markdown)`` pairs, newest first; it is
    empty when the release notes could not be read.
    """

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
        reply = self._manager.get(self._request(VERSION_URL))
        reply.finished.connect(lambda: self._on_finished(reply))

    @staticmethod
    def _request(url: str) -> QNetworkRequest:
        """Build a GET request with the app's User-Agent and the timeout."""

        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", f"{APP_NAME}/{APP_VERSION}".encode())
        request.setTransferTimeout(REQUEST_TIMEOUT_MS)
        return request

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
                self._fetch_notes(latest)
            else:
                self.upToDate.emit()
        except (ValueError, KeyError, TypeError) as e:
            self.checkFailed.emit(str(e))
        finally:
            reply.deleteLater()

    def _fetch_notes(self, latest: str) -> None:
        """Read the release notes from GitHub, then report the update.

        Args:
            latest: Latest version string found on PyPI.
        """

        request = self._request(RELEASES_API_URL)
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        reply = self._manager.get(request)
        reply.finished.connect(lambda: self._on_notes_finished(reply, latest))

    def _on_notes_finished(self, reply: QNetworkReply, latest: str) -> None:
        """Emit ``updateAvailable`` with whatever notes could be read.

        Args:
            reply: Finished network reply from the GitHub API.
            latest: Latest version string found on PyPI.
        """

        notes: list[tuple[str, str]] = []
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = json.loads(bytes(reply.readAll()).decode("utf-8"))
                if isinstance(data, list):
                    notes = newer_release_notes(data, APP_VERSION, latest)
        except (ValueError, TypeError):
            notes = []
        finally:
            reply.deleteLater()
        self.updateAvailable.emit(latest, PROJECT_URL, notes)


def _demo_main() -> int:
    """Run a single update check from the command line.

    Returns:
        Qt application exit code.
    """

    import sys

    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication(sys.argv)
    checker = UpdateChecker()

    def on_update(v: str, url: str, notes: list) -> None:
        print(f"Update available: {v} -> {url}")
        for ver, body in notes:
            print(f"\n## {ver}\n{body}")
        app.quit()

    checker.updateAvailable.connect(on_update)
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
