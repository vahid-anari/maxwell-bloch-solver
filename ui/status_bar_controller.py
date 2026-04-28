"""Status bar controller for path, timing, and memory feedback."""

from __future__ import annotations

import os
from enum import Enum
from time import perf_counter_ns
from typing import Optional

import psutil
from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from utils.helper_funcs import set_widget_width


class StatusState(str, Enum):
    """Represent the high-level operating mode shown in the status bar.

    Attributes:
        READY: Idle state shown when no long-running task is active.
        IMPORTING: State shown while importing data or configuration.
        SAVING: State shown while saving data or configuration.
        SOLVING: State shown while a solve operation is running.
        EXPORTING: State shown while exporting results.
        ERROR: State shown after an error condition occurs.
    """

    READY = "Ready"
    IMPORTING = "Importing…"
    SAVING = "Saving…"
    SOLVING = "Solving…"
    EXPORTING = "Exporting…"
    ERROR = "Error"


def format_compact_number(value: float) -> str:
    """Format a numeric value for compact display.

    The returned string uses up to two decimal places for small values and fewer
    decimals for larger values to keep the status-bar text compact.

    Args:
        value: Numeric value to format.

    Returns:
        Formatted numeric string suitable for compact display.
    """

    if value < 10:
        return f"{value:.2f}"
    if value < 100:
        return f"{value:.1f}"
    return f"{value:.0f}"


class StatusBarController(QObject):
    """Control the status-bar widgets for path, timing, and memory feedback."""

    def __init__(
        self,
        window: QMainWindow,
        timer_interval: int = 700,
    ) -> None:
        """Initialize the status-bar controller.

        Args:
            window: Main window whose status bar is managed by this controller.
            timer_interval: Update interval, in milliseconds, for refreshing the
                elapsed-time and memory displays while timing is active.
        """

        super().__init__(window)
        self._window = window
        self._sb = window.statusBar()
        self._process = psutil.Process(os.getpid())
        self._time_ns: int = 0
        self._last_state = StatusState.READY

        self._current_path: str = ""
        self._path_modified: bool = False

        self._timer = QTimer(self)
        self._timer.setInterval(timer_interval)
        self._timer.timeout.connect(self._update_time)

        self._status_lbl = self._make_label("Ready")
        self._folder_path_lbl = self._make_label("Path:")
        self._memory_lbl = self._make_label("0.00 MB", 6, Qt.AlignRight)
        self._time_lbl = self._make_label("0.00 s", 6, Qt.AlignRight)

        self._status_lbl.setFixedWidth(70)
        self._make_layout()

    def _make_label(
        self,
        text: str,
        char_width: Optional[int] = None,
        align: Qt.Alignment = Qt.AlignLeft,
    ) -> QLabel:
        """Create a QLabel configured for the status bar.

        Args:
            text: Initial label text.
            char_width: Optional approximate width in characters used to size the
                widget.
            align: Horizontal alignment for the label text.

        Returns:
            Configured status-bar label widget.
        """

        l = QLabel(text, alignment=align | Qt.AlignVCenter)
        if char_width is not None:
            set_widget_width(l, char_width)
        return l

    def _make_progress(self) -> QProgressBar:
        """Create the indeterminate progress bar for long operations.

        Returns:
            Hidden indeterminate progress bar configured for the status bar.
        """

        progress = QProgressBar(self._sb)
        progress.setTextVisible(True)
        progress.setFixedWidth(200)
        progress.setRange(0, 0)
        progress.hide()
        progress.setFixedHeight(18)
        return progress

    def _make_layout(self) -> None:
        """Build and attach the left and right status-bar sections."""

        left_w = QWidget()
        left_l = QHBoxLayout(left_w)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(0)
        left_l.addSpacing(10)
        left_l.addWidget(self._status_lbl)
        left_l.addSpacing(10)
        self._add_v_line(left_l)
        left_l.addWidget(self._folder_path_lbl)
        left_l.addStretch(1)
        self._sb.addWidget(left_w)

        right_w = QWidget()
        right_l = QHBoxLayout(right_w)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(0)
        right_l.addStretch(1)
        self._add_v_line(right_l)
        right_l.addWidget(QLabel("Memory:"))
        right_l.addWidget(self._memory_lbl)
        self._add_v_line(right_l)
        right_l.addWidget(QLabel("Time:"))
        right_l.addWidget(self._time_lbl)
        right_l.addSpacing(8)
        self._sb.addPermanentWidget(right_w)

    def _add_v_line(self, layout: QLayout) -> None:
        """Insert a padded vertical separator into a layout.

        Args:
            layout: Layout that will receive the separator widget.
        """

        layout.addSpacing(10)
        layout.addWidget(self._vline())
        layout.addSpacing(10)

    def _vline(self) -> QFrame:
        """Create a sunken vertical separator line.

        Returns:
            Vertical line widget for separating status-bar sections.
        """

        line = QFrame(self._sb)
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def _update_time(self) -> None:
        """Refresh the elapsed-time label using an auto-selected time unit."""

        cur_t = perf_counter_ns()
        time_ = (cur_t - self._time_ns) / 1.0e6
        unit = "ms"
        if time_ >= 1000:
            time_ = time_ / 1000.0
            unit = "s"
            if time_ >= 60:
                time_ = time_ / 60.0
                if time_ < 60:
                    unit = "m"
                else:
                    time_ = time_ / 60.0
                    unit = "h"
        self._time_lbl.setText(f"{format_compact_number(time_)} {unit}")
        self._update_memory()

    def _update_memory(self) -> None:
        """Refresh the memory label with the current process RSS usage."""

        value_byte = self._process.memory_info().rss
        unit = "B"
        if value_byte >= 1000:
            value_byte = value_byte / 1024
            if value_byte < 1000:
                unit = "KB"
            else:
                value_byte = value_byte / 1024
                if value_byte < 1000:
                    unit = "MB"
                else:
                    value_byte = value_byte / 1024
                    unit = "GB"
        self._memory_lbl.setText(f"{format_compact_number(value_byte)} {unit}")

    def _update_path_label(self) -> None:
        """Refresh the displayed path text and its tooltip."""

        path_text = self._current_path if self._current_path else "Untitled"
        mark = " *" if self._path_modified else ""
        text = f"Path{mark}: {path_text}"
        self._folder_path_lbl.setText(text)
        self._folder_path_lbl.setToolTip(text)

    def set_state(self, state: StatusState) -> None:
        """Set the current status-bar state.

        This method updates the state label, starts or stops the elapsed-time
        timer as needed, refreshes the memory display, and processes pending UI
        events.

        Args:
            state: New status value to display.
        """

        self._timer.stop()
        if self._last_state == StatusState.SOLVING:
            self._update_time()
        self._last_state = state
        if state == StatusState.SOLVING:
            self._time_ns = perf_counter_ns()
            self._timer.start()

        self._update_memory()
        self._status_lbl.setText(state)
        QApplication.processEvents()

    def set_path(self, path: str) -> None:
        """Update the displayed path and clear the modified marker.

        Args:
            path: File-system path to show in the status bar. An empty string is
                displayed as ``Untitled``.
        """

        self._current_path = path
        if path:
            self._path_modified = False
        self._update_path_label()

    def set_path_modified(self) -> None:
        """Mark the current path as modified and refresh the label."""

        self._path_modified = True
        self._update_path_label()

    def is_modified(self) -> bool:
        """Return whether the current path is marked as modified.

        Returns:
            ``True`` if unsaved changes are currently indicated, otherwise
            ``False``.
        """

        return self._path_modified


def _demo_main() -> int:
    """Run this module as a standalone demo application.

    Returns:
        Qt application exit code.
    """

    import sys
    from settings.app_style import set_app_style

    class MainWindow(QMainWindow):
        """Demonstration main window for the status-bar controller."""

        def __init__(self) -> None:
            """Initialize the demo window and its controls."""

            super().__init__()
            self.setWindowTitle("StatusBarController demo")
            self.status_ctrl = StatusBarController(self)
            self.edit_folder_path = QLineEdit(self)
            self.status_ctrl.set_path("C:/Vahid/Download/abcdefghijklmnopqrstuvwxyz")
            self.combo = QComboBox(self)
            for state in StatusState:
                self.combo.addItem(state.value, state)
            self.combo.setFixedWidth(self.combo.sizeHint().width())
            cb = QCheckBox("Set Modified")
            cb.checkStateChanged.connect(self.on_modified_changed)
            self.cb = cb

            self.edit_folder_path.editingFinished.connect(self.on_folder_path_change)
            self.combo.currentIndexChanged.connect(self.on_combo_changed)

            self._make_layout()

        def _make_layout(self) -> None:
            """Create the central layout used by the demo window."""

            central = QWidget(self)
            layout = QVBoxLayout(central)
            self.setCentralWidget(central)
            form = QFormLayout()
            form.addRow("Folder", self.edit_folder_path)
            layout.addLayout(form)
            layout.addWidget(self.combo)
            layout.addWidget(self.cb)
            layout.addStretch(1)

        def on_folder_path_change(self) -> None:
            """Handle updates to the folder-path editor."""

            self.status_ctrl.set_path(self.edit_folder_path.text())

        def on_combo_changed(self) -> None:
            """Handle changes to the selected status value."""

            self.status_ctrl.set_state(self.combo.currentData())

        def on_modified_changed(self) -> None:
            """Handle toggling of the modified-state checkbox."""

            self.status_ctrl.set_path_modified()

    app = QApplication(sys.argv)
    set_app_style(app)

    w = MainWindow()
    w.resize(900, 300)
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
