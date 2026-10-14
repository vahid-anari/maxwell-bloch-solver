"""Locations of the files shipped with the application.

Everything that is not Python code lives in ``resources/`` next to this file,
both in a source checkout and in an installed package.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
"""Directory of the ``mbsolver`` package."""

RESOURCES_DIR = PACKAGE_DIR / "resources"
"""Directory with settings, icons and documentation PDFs."""

SETTINGS_FILE_PATH = RESOURCES_DIR / "settings.json"
"""Default panel, plot and widget settings (read-only; user changes go to QSettings)."""

ICONS_DIR = RESOURCES_DIR / "icons"
"""Directory containing icon and splash-image assets."""

APP_ICON_PATH = ICONS_DIR / "app_icon.png"
"""Path to the main application icon."""

APP_IMAGE_PATH = ICONS_DIR / "app_image.png"
"""Path to the splash-screen image."""

EQUATIONS_PDF_PATH = RESOURCES_DIR / "equations_reference.pdf"
"""Path to the equations reference PDF."""

USER_GUIDE_PATH = RESOURCES_DIR / "user_guide.pdf"
"""Path to the user guide PDF."""
