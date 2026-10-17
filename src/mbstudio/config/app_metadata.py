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

GITHUB_REPO = "vahid-anari/maxwell-bloch-studio"
"""GitHub repository (``owner/name``); its Releases hold the release notes."""

APP_AUTHOR_GITHUB = f"https://github.com/{GITHUB_REPO}"
"""Author GitHub profile or repository URL, if available."""

APP_AUTHOR_WEBSITE = ""
"""Author website URL, if available."""

def _app_info():
    from sciwidgets.app import AppInfo

    from mbstudio.paths import APP_ICON_PATH

    return AppInfo(
        name=APP_NAME,
        version=APP_VERSION,
        dist_name=DIST_NAME,
        module="mbstudio",
        command="mbstudio",
        github_repo=GITHUB_REPO,
        icon=APP_ICON_PATH,
        bundle_id="io.github.vahid-anari.mbstudio",
        linux_id="maxwell-bloch-studio",
        marker="MBStudio",  # keys recorded in installed launchers (MBStudioPython, X-MBStudio-*): keep
        comment="Simulate and fit Maxwell-Bloch models of maser light curves",
        categories="Science;Physics;Education;",
    )


APP = _app_info()
"""The app for ``sciwidgets.app`` (launcher, update check)."""
