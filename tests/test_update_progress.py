"""Tests for "Update Now": the update dialog, the progress dialog and the restart."""

import gc
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from mbstudio.ui.update_dialog import UpdateDialog
from mbstudio.ui.update_progress import UpdateProgressDialog, restart_app, restart_command


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    # Delete the dialogs while Qt is still running; left to Python's exit they can crash it
    # ("shared QObject was deleted directly", segmentation fault after all tests passed).
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    gc.collect()


def run(code):
    dialog = UpdateProgressDialog([sys.executable, "-c", code], "Studio", "99.0", "Run it by hand.")
    dialog.start()
    assert dialog.wait()
    QApplication.processEvents()
    return dialog


def test_successful_update_offers_restart():
    dialog = run("print('Successfully upgraded')")
    assert dialog.succeeded
    assert "Successfully upgraded" in dialog._output.toPlainText()     # the output is shown
    assert "Updated to 99.0" in dialog._status.text()
    assert dialog._restart.isVisibleTo(dialog) and dialog._later.isVisibleTo(dialog)
    dialog._choose_restart()
    assert dialog.restart_requested


def test_failed_update_shows_the_manual_way():
    dialog = run("import sys; print('No network'); sys.exit(1)")
    assert not dialog.succeeded and not dialog.restart_requested
    assert "No network" in dialog._output.toPlainText()
    assert "did not finish" in dialog._status.text() and "Run it by hand." in dialog._status.text()
    assert dialog._close.isVisibleTo(dialog) and not dialog._restart.isVisibleTo(dialog)


def test_command_that_cannot_start():
    dialog = UpdateProgressDialog(["/no/such/pipx", "upgrade"], "Studio", "99.0", "By hand.")
    dialog.start()
    dialog.wait(2000)
    QApplication.processEvents()
    assert not dialog.succeeded and "Could not start" in dialog._status.text()


def test_no_closing_while_running():
    dialog = UpdateProgressDialog([sys.executable, "-c", "import time; time.sleep(0.5)"],
                                  "Studio", "99.0", "")
    dialog.start()
    dialog.reject()                                                     # ignored while running
    assert dialog._done is False
    dialog.wait()


def test_restart_closes_then_starts_same_python():
    started = []
    assert restart_app(lambda: True, lambda program, args: started.append([program, *args]))
    assert started == [restart_command()] and started[0][0] == sys.executable
    started.clear()
    assert not restart_app(lambda: False, lambda program, args: started.append(program))
    assert started == []                                                # user kept the window


@pytest.mark.parametrize("can_update, hint", [(True, ""), (False, "Use git pull."), (False, "")])
def test_update_dialog_button(can_update, hint):
    dialog = UpdateDialog("Studio", "99.0", "1.0", "pipx upgrade x", "x", [], "https://pypi.org",
                          "https://github.com", can_update=can_update, hint=hint)
    assert dialog.update_btn.isEnabled() is can_update
    if can_update:
        dialog.update_btn.click()
        assert dialog.result() == UpdateDialog.UPDATE_NOW
