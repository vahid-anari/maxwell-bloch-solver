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
    """Tell the user a newer version exists, what changed, and offer to update now.

    ``exec()`` returns ``UpdateDialog.UPDATE_NOW`` when the user clicked
    "Update Now", otherwise ``QDialog.Accepted``/``Rejected``.

    Args:
        app_name: Application name shown in the heading.
        latest: Latest version on PyPI.
        current: Running version.
        update_command: Command that updates this installation (shown to the
            user), or ``""`` when it is not known.
        dist_name: Package name, for the ``pip install -U`` alternative.
        notes: ``(version, markdown)`` pairs, newest first; may be empty.
        project_url: PyPI page of the application.
        releases_url: Page with all release notes.
        parent: Optional parent widget.
        can_update: Offer the "Update Now" button.
        hint: Shown instead of the command when the app cannot update itself
            (e.g. a copy run from a source folder).
    """

    UPDATE_NOW = 2

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
        *,
        can_update: bool = False,
        hint: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Update Available")
        self.resize(620, 520)

        heading = QLabel(
            f"<b>{escape(app_name)} {escape(latest)}</b> is available.<br>"
            f"You have version {escape(current)}."
        )

        if hint:
            how_text = escape(hint)
        elif can_update:
            how_text = ("<b>Update Now</b> runs, while the app stays open:"
                        f"<pre>    {escape(update_command)}</pre>"
                        "Restart the app afterwards to use the new version.")
        else:
            command = update_command or f"pipx upgrade {dist_name}"
            how_text = ("To update, close the app and run in a terminal:"
                        f"<pre>    {escape(command)}</pre>"
                        f"(or <code>pip install -U {escape(dist_name)}</code> in the environment "
                        "where you installed it).")
        how = QLabel(how_text)
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
        later_btn.clicked.connect(self.accept)
        self.update_btn = QPushButton("Update Now")
        self.update_btn.setEnabled(can_update)
        self.update_btn.clicked.connect(lambda: self.done(self.UPDATE_NOW))
        (self.update_btn if can_update else later_btn).setDefault(True)

        buttons = QHBoxLayout()
        buttons.addWidget(notes_btn)
        buttons.addWidget(pypi_btn)
        buttons.addStretch(1)
        buttons.addWidget(later_btn)
        buttons.addWidget(self.update_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(how)
        if notes:
            layout.addWidget(whats_new)
            layout.addWidget(browser, 1)
        else:
            whats_new.hide()
            browser.hide()
            layout.addStretch(1)
            self.resize(560, 260)
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
        can_update=True,
    ).exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(_demo_main())
