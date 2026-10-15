"""Update notice that also lists what is new in the newer versions."""

from __future__ import annotations

from html import escape
from typing import Optional, Sequence, Tuple

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


def notes_markdown(notes: Sequence[Tuple[str, str]]) -> str:
    """Join the notes of several versions into one Markdown text, newest first.

    Args:
        notes: ``(version, markdown)`` pairs, newest first.

    Returns:
        Markdown with one ``###`` heading per version.
    """

    return "\n\n".join(f"### {version}\n\n{body.strip()}" for version, body in notes)


class UpdateDialog(QDialog):
    """Tell the user a newer version exists, how to install it, and what changed.

    Args:
        app_name: Application name shown in the heading.
        latest: Latest version on PyPI.
        current: Running version.
        update_command: Command that updates a pipx installation.
        dist_name: Package name, for the ``pip install -U`` alternative.
        notes: ``(version, markdown)`` pairs, newest first.
        project_url: PyPI page of the application.
        releases_url: Page with all release notes.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        app_name: str,
        latest: str,
        current: str,
        update_command: str,
        dist_name: str,
        notes: Sequence[Tuple[str, str]],
        project_url: str,
        releases_url: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Update Available")
        self.resize(620, 520)

        heading = QLabel(
            f"<b>{escape(app_name)} {escape(latest)}</b> is available.<br>"
            f"You have version {escape(current)}."
        )

        how = QLabel(
            "To update, close the app and run in a terminal:"
            f"<pre>    {escape(update_command)}</pre>"
            f"(or <code>pip install -U {escape(dist_name)}</code> in the environment "
            "where you installed it)."
        )
        how.setWordWrap(True)
        how.setTextInteractionFlags(Qt.TextSelectableByMouse)

        whats_new = QLabel("<b>What's new</b>")

        browser = QTextBrowser(self)
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(notes_markdown(notes))

        notes_btn = QPushButton("Open Release Notes")
        notes_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(releases_url)))
        pypi_btn = QPushButton("Open PyPI Page")
        pypi_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(project_url)))
        later_btn = QPushButton("Later")
        later_btn.setDefault(True)
        later_btn.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(notes_btn)
        buttons.addWidget(pypi_btn)
        buttons.addWidget(later_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(how)
        layout.addWidget(whats_new)
        layout.addWidget(browser, 1)
        layout.addLayout(buttons)


def _demo_main() -> int:
    """Show the dialog with sample notes: ``python -m mbstudio.ui.update_dialog``."""

    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    UpdateDialog(
        "Maxwell Bloch Studio", "10.0.4", "10.0.2", "pipx upgrade maxwell-bloch-studio",
        "maxwell-bloch-studio",
        [("10.0.4", "- Fixed: something.\n- New: something else."),
         ("10.0.3", "- Release notes in the update notice.")],
        "https://pypi.org/project/maxwell-bloch-studio/",
        "https://github.com/vahid-anari/maxwell-bloch-studio/releases",
    ).exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(_demo_main())
