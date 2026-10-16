"""Run the update command inside the app, show its output, then offer a restart."""

from __future__ import annotations

import sys
from typing import Callable, Optional, Sequence

from PySide6.QtCore import QProcess
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class UpdateProgressDialog(QDialog):
    """Run ``command`` (e.g. ``pipx upgrade maxwell-bloch-studio``) and show its output.

    After a successful run the dialog offers "Restart Now" and "Later";
    ``restart_requested`` tells which was chosen. After a failure it shows the
    error and the command to run by hand.

    Args:
        command: Program and arguments.
        app_name: Application name for the messages.
        latest: Version being installed.
        manual_hint: What to do by hand if the update fails.
        parent: Optional parent widget.
    """

    def __init__(self, command: Sequence[str], app_name: str, latest: str, manual_hint: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Updating")
        self.resize(640, 380)
        self._command = list(command)
        self._app_name = app_name
        self._latest = latest
        self._manual_hint = manual_hint
        self.succeeded = False
        self.restart_requested = False

        self._status = QLabel(f"Updating {app_name} to {latest}…")
        self._status.setWordWrap(True)
        self._output = QPlainTextEdit(readOnly=True)
        self._output.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._output.appendPlainText("$ " + " ".join(self._command))

        self._later = QPushButton("Later")
        self._later.clicked.connect(self.reject)
        self._restart = QPushButton("Restart Now")
        self._restart.clicked.connect(self._choose_restart)
        self._close = QPushButton("Close")
        self._close.clicked.connect(self.reject)
        for button in (self._later, self._restart, self._close):
            button.hide()

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._close)
        buttons.addWidget(self._later)
        buttons.addWidget(self._restart)

        layout = QVBoxLayout(self)
        layout.addWidget(self._status)
        layout.addWidget(self._output, 1)
        layout.addLayout(buttons)

        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._read_output)
        self._proc.finished.connect(self._finished)
        self._proc.errorOccurred.connect(self._error)
        self._done = False

    def start(self) -> None:
        """Start the update (``exec`` calls it)."""
        self._proc.start(self._command[0], self._command[1:])

    def exec(self) -> int:  # noqa: D102
        self.start()
        return super().exec()

    def wait(self, msecs: int = 30000) -> bool:
        """Block until the command has finished (for tests and scripts)."""
        return self._proc.waitForFinished(msecs)

    def reject(self) -> None:
        if not self._done:  # no closing while pip is replacing files
            return
        super().reject()

    def _read_output(self) -> None:
        text = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        if text:
            self._output.appendPlainText(text.rstrip("\n"))

    def _finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._read_output()
        if exit_status == QProcess.NormalExit and exit_code == 0:
            self._succeed()
        else:
            self._fail(f"The update stopped with exit code {exit_code}.")

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.FailedToStart:
            self._fail(f"Could not start {self._command[0]}.")

    def _succeed(self) -> None:
        self._done = True
        self.succeeded = True
        self._status.setText(f"<b>Updated to {self._latest}.</b> Restart now to use the new "
                             f"version? Unsaved parameters are asked about as usual.")
        self._later.show()
        self._restart.show()
        self._restart.setDefault(True)

    def _fail(self, reason: str) -> None:
        if self._done:
            return
        self._done = True
        self._status.setText(f"<b>The update did not finish.</b> {reason}<br>{self._manual_hint}")
        self._close.show()
        self._close.setDefault(True)

    def _choose_restart(self) -> None:
        self.restart_requested = True
        self.accept()


def restart_command() -> list:
    """How to start the app again in the same Python (picks up the new version)."""
    return [sys.executable, "-m", "mbstudio"]


def restart_app(close_window: Callable[[], bool],
                start_detached: Callable[[str, list], object] = QProcess.startDetached) -> bool:
    """Close the main window (which may ask about unsaved work) and start the app again.

    Returns:
        ``True`` if the window closed and the new instance was started;
        ``False`` if the user cancelled closing.
    """
    if not close_window():
        return False
    command = restart_command()
    start_detached(command[0], command[1:])
    return True
