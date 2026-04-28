"""Central project paths for settings, assets, and documentation."""

from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
"""Root directory of the application package."""

SETTINGS_DIR = ROOT_DIR / "settings"
"""Directory containing application settings files."""

SETTINGS_FILE_PATH = SETTINGS_DIR / "settings.json"
"""Path to the main JSON settings file."""

ASSETS_DIR = ROOT_DIR / "assets"
"""Directory containing packaged application assets."""

ICONS_DIR = ASSETS_DIR / "icons"
"""Directory containing icon and splash-image assets."""

APP_ICON_PATH = ICONS_DIR / "app_icon.png"
"""Path to the main application icon."""

APP_IMAGE_PATH = ICONS_DIR / "app_image.png"
"""Path to the splash-screen or application image asset."""

DOCS_DIR = ROOT_DIR / "docs"
"""Directory containing project documentation."""

EQUATIONS_PDF_PATH = DOCS_DIR / "equations_reference.pdf"
"""Path to the equations reference PDF."""

DOCUMENTATION_PATH = DOCS_DIR / "api" / "index.html"
"""Path to the generated API documentation index page."""

USER_GUIDE_PATH = DOCS_DIR / "user_guide.pdf"
"""Path to the user guide PDF."""

README_PATH = ROOT_DIR / "README.md"
"""Path to the project README file."""