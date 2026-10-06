"""Application metadata used by the GUI, about dialog, and update checker.

The update checker reads ``APP_VERSION`` from this file on GitHub's main
branch, so keep the file path and the ``APP_VERSION = "..."`` line format
unchanged.
"""

from __future__ import annotations

import re

APP_NAME = "Maxwell Bloch Solver"
"""Human-readable application name."""

APP_VERSION = "8.6.0"
"""Application version string."""

APP_AUTHOR_NAME = "Vahid Anari"
"""Primary author name shown in metadata displays."""

APP_AUTHOR_EMAIL = "vahid.anari8@gmail.com"
"""Primary author email address."""

APP_AUTHOR_GITHUB = "https://github.com/vahid-anari/maxwell-bloch-solver"
"""Author GitHub profile or repository URL, if available."""

APP_AUTHOR_WEBSITE = ""
"""Author website URL, if available."""

_REPO = APP_AUTHOR_GITHUB.rstrip("/").replace("https://github.com/", "")
METADATA_PATH = "settings/metadata.py"

VERSION_FILE_URL = f"https://raw.githubusercontent.com/{_REPO}/main/{METADATA_PATH}"
"""Raw metadata file on the main branch, read to find the latest version."""

DOWNLOAD_URL = f"https://github.com/{_REPO}/archive/refs/heads/main.zip"
"""Zip of the current main branch, offered to the user when an update exists."""

_VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
