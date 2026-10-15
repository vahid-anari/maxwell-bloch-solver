"""Application metadata used by the GUI, the About dialog and the update checker.

The version comes from the installed package (``pyproject.toml``), so it is
set in one place only.
"""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

DIST_NAME = "maxwell-bloch-studio"
"""Name of the package on PyPI."""


def _read_version() -> str:
    """Return the installed version, or the one in ``pyproject.toml`` of a source checkout."""
    try:
        return version(DIST_NAME)
    except PackageNotFoundError:
        pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
        if pyproject.is_file():
            match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
            if match:
                return match.group(1)
        return "0+unknown"


APP_NAME = "Maxwell Bloch Studio"
"""Human-readable application name."""

APP_VERSION = _read_version()
"""Application version string."""

APP_AUTHOR_NAME = "Vahid Anari"
"""Primary author name shown in metadata displays."""

APP_AUTHOR_EMAIL = "vahid.anari8@gmail.com"
"""Primary author email address."""

APP_AUTHOR_GITHUB = "https://github.com/vahid-anari/maxwell-bloch-studio"
"""Author GitHub profile or repository URL, if available."""

APP_AUTHOR_WEBSITE = ""
"""Author website URL, if available."""

UPDATE_COMMAND = f"pipx upgrade {DIST_NAME}"
"""Command shown to the user when a newer version exists."""
