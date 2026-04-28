"""Velocity-selection toolbar for switching between data components.

The controller keeps navigation, save state, and per-velocity status widgets
synchronized with the active component.
"""

from __future__ import annotations

import sys
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from dialogs.dialogs import AskResult, ask_question, show_information
from settings.app_style import VELOCITY_COMBO_WIDTH
from ui.labels import SvgLabel
from utils.helper_funcs import set_widget_width, value_to_text
from utils.units import VELOCITY_UNIT_LATEX


class VelocityBarController(QWidget):
    """Controller widget for browsing, saving, and annotating velocity components."""

    valueChanged = Signal(str)
    valueSaved = Signal(str)
    valueUnsaved = Signal(str)

    def __init__(self, window: QMainWindow):
        """Initialize the velocity-bar controller.

        Args:
            window: Main window that will own the toolbar.
        """

        super().__init__(window)

        self._all_values: list[str] = []
        self._saved_values: set[str] = set()

        self._SAVE = 1
        self._DISCARD = 2
        self._CANCEL = 3
        self._dirty_value: str | None = None
        self._last_index: int = -1
        self._ignore_index_change = False

        self._velocity_label = SvgLabel("v=")
        self._combo = QComboBox()
        self._combo.setFixedWidth(VELOCITY_COMBO_WIDTH)
        self._velocity_unit_label = SvgLabel(VELOCITY_UNIT_LATEX)

        pm = QPixmap(self._combo.iconSize())
        pm.fill(Qt.transparent)
        self._empty_icon = QIcon(pm)
        self._saved_icon = self.style().standardIcon(QStyle.SP_DialogApplyButton)
        self._modified_icon = self.style().standardIcon(QStyle.SP_MessageBoxWarning)

        h = 25
        self._show_saved_cb = QCheckBox("Only saved velocities")
        self._prev_btn = self._make_btn("<", h, h, enable=False)
        self._next_btn = self._make_btn(">", h, h, enable=False)
        self._save_btn = self._make_btn("Save", 60, h)
        self._unsave_btn = self._make_btn("Unsave", 60, h)

        self._chi_square_label = SvgLabel(r"\chi^2=")
        l = QLabel("")
        l.setObjectName("chi_value")
        set_widget_width(l, 8)
        self._chi_square_value_label = l

        self._prev_btn.clicked.connect(self._on_prev_btn_clicked)
        self._next_btn.clicked.connect(self._on_next_btn_clicked)
        self._save_btn.clicked.connect(self._on_save_btn_clicked)
        self._unsave_btn.clicked.connect(self._on_unsave_btn_clicked)
        self._show_saved_cb.toggled.connect(self._on_show_saved)
        self._combo.currentIndexChanged.connect(self._on_current_index_changed)

        self._make_layout(window)
        self._refresh_combo()

    def _make_btn(self, text: str, width: int, height: int, enable: bool = True) -> QPushButton:
        """Create a fixed-size push button for the velocity toolbar.

        Args:
            text: Button text.
            width: Button width in pixels.
            height: Button height in pixels.
            enable: Initial enabled state.

        Returns:
            Configured push button.
        """

        btn = QPushButton(text)
        btn.setFixedSize(width, height)
        btn.setEnabled(enable)
        return btn

    def _make_layout(self, window: QMainWindow) -> None:
        """Build the toolbar and add all velocity-bar controls to it.

        Args:
            window: Main window that owns the toolbar.
        """

        toolbar = QToolBar("velocity", window)
        toolbar.setMovable(False)
        window.addToolBar(toolbar)

        self._add_space(toolbar, 5, add_sep=False)
        toolbar.addWidget(self._show_saved_cb)
        self._add_space(toolbar, 10)
        toolbar.addWidget(self._prev_btn)
        self._add_space(toolbar, 5, add_sep=False)
        toolbar.addWidget(self._velocity_label)
        toolbar.addWidget(self._combo)
        toolbar.addWidget(self._velocity_unit_label)
        self._add_space(toolbar, 5, add_sep=False)
        toolbar.addWidget(self._next_btn)
        self._add_space(toolbar, 10)
        toolbar.addWidget(self._save_btn)
        self._add_space(toolbar, 5, add_sep=False)
        toolbar.addWidget(self._unsave_btn)
        self._add_space(toolbar, 10)
        toolbar.addWidget(self._chi_square_label)
        toolbar.addWidget(self._chi_square_value_label)
        self._toolbar = toolbar

    def _add_space(self, tb: QToolBar, width: int, add_sep: bool = True) -> None:
        """Insert a fixed-width spacer into a toolbar.

        Args:
            tb: Target toolbar.
            width: Spacer width in pixels.
            add_sep: Whether to insert a separator in the middle of the spacing.
        """

        if add_sep:
            w1 = QWidget()
            w2 = QWidget()
            w1.setFixedWidth(width // 2)
            w2.setFixedWidth(width // 2)
            tb.addWidget(w1)
            tb.addSeparator()
            tb.addWidget(w2)
        else:
            w = QWidget()
            w.setFixedWidth(width)
            tb.addWidget(w)

    def _icon_for_value(self, v: str) -> QIcon:
        """Return the status icon for one velocity entry.

        Args:
            v: Velocity string.

        Returns:
            Icon indicating whether the velocity is modified, saved, or blank.
        """

        if v == self._dirty_value:
            return self._modified_icon
        if v in self._saved_values:
            return self._saved_icon
        return self._empty_icon

    def _refresh_combo(self) -> None:
        """Rebuild the combo-box contents and refresh dependent widget states."""

        current_value = self._current_value()
        values = self._all_values
        if self._show_saved_cb.isChecked():
            if self._saved_values:
                values = [
                    v for v in self._all_values
                    if v in self._saved_values or v == self._dirty_value
                ]
            else:
                show_information(
                    "No saved velocities",
                    "There are no saved velocities, so all values will be shown.",
                    parent=self,
                )
                self._show_saved_cb.blockSignals(True)
                self._show_saved_cb.setChecked(False)
                self._show_saved_cb.blockSignals(False)

        self._combo.blockSignals(True)
        self._combo.clear()

        for v in values:
            self._combo.addItem(self._icon_for_value(v), v, userData=v)

        if current_value is not None:
            idx = self._combo.findData(current_value)
        else:
            idx = -1

        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        elif self._combo.count() > 0:
            self._combo.setCurrentIndex(0)

        self._combo.blockSignals(False)
        self._update_widget_states()
        self._last_index = self._combo.currentIndex()

    def _current_value(self) -> str | None:
        """Return the currently selected combo-item value.

        Returns:
            Selected velocity string, or ``None`` if no item is selected.
        """

        idx = self._combo.currentIndex()
        if idx < 0:
            return None
        return self._combo.currentData()

    def _set_index(self, idx: int) -> None:
        """Select the combo item at a given index and refresh widget states.

        Args:
            idx: Target combo-box index.
        """

        total = self._combo.count()
        if total == 0:
            self._update_widget_states()
            return
        self._combo.setCurrentIndex(idx)
        self._update_widget_states()

    def _change_current_idx(self, step: int) -> None:
        """Move the combo selection by a signed number of steps.

        Args:
            step: Signed step count to apply to the current index.
        """

        total = self._combo.count()
        if total == 0:
            return

        new_idx = self._combo.currentIndex() + step

        if new_idx < 0:
            new_idx = 0
        elif new_idx >= total:
            new_idx = total - 1

        self._set_index(new_idx)

    def _on_current_index_changed(self, index: int) -> None:
        """Handle combo-box index changes.

        Args:
            index: Newly selected index.
        """

        if self._ignore_index_change:
            return

        if index < 0:
            self._update_widget_states()
            return

        old_value = None
        if 0 <= self._last_index < self._combo.count():
            old_value = self._combo.itemData(self._last_index)

        if old_value is not None and self._dirty_value == old_value:
            self._ignore_index_change = True
            self._combo.setCurrentIndex(self._last_index)
            self._ignore_index_change = False
            result = ask_question(
                "Unsaved changes",
                f"Velocity {self._current_value()} has unsaved changes.",
                "Do you want to save_parameters them before changing velocity?",
                yes_btn_label="Yes",
                no_btn_label="No",
                cancel_btn_label="Cancel",
                parent=self,
            )
            if result == AskResult.CANCEL:
                self._update_widget_states()
                return

            self._dirty_value = None

            if result == AskResult.YES:
                self.save_parameters()

            self._ignore_index_change = True
            self._combo.setCurrentIndex(index)
            self._ignore_index_change = False

            self._refresh_combo()
            value = self._current_value()
            if value is not None:
                self.valueChanged.emit(value)
            return

        self._last_index = index
        self._update_widget_states()
        value = self._current_value()
        if value is not None:
            self.valueChanged.emit(value)

    def _on_prev_btn_clicked(self) -> None:
        """Handle the previous-button click."""
        self._change_current_idx(-1)

    def _on_next_btn_clicked(self) -> None:
        """Handle the next-button click."""
        self._change_current_idx(1)

    def _on_save_btn_clicked(self) -> None:
        """Handle the save-button click."""
        self.save_parameters()

    def _on_unsave_btn_clicked(self) -> None:
        """Handle the unsave-button click."""
        v = self._current_value()
        if v is None:
            return
        self._saved_values.discard(v)
        self._dirty_value = None
        self._refresh_combo()
        self.valueUnsaved.emit(v)

    def _on_show_saved(self):
        """Refresh the selector when the saved-only filter changes."""
        self._refresh_combo()
        self.valueChanged.emit(self._current_value())

    def _update_widget_states(self) -> None:
        """Enable or disable controls based on current velocity and save state."""
        idx = self._combo.currentIndex()
        total = self._combo.count()
        v = self._current_value()
        is_saved = (v in self._saved_values) if v is not None else False
        is_dirty = (v == self._dirty_value) if v is not None else False
        has_values = len(self._all_values) > 0
        has_saved = len(self._saved_values) > 0
        if not has_values:
            self._chi_square_value_label.setText("")

        self._velocity_label.setEnabled(has_values)
        self._combo.setEnabled(has_values)
        self._velocity_unit_label.setEnabled(has_values)
        self._chi_square_label.setEnabled(has_values)
        self._chi_square_value_label.setEnabled(has_values)
        self._show_saved_cb.setEnabled(has_saved)
        self._prev_btn.setEnabled(total > 0 and idx > 0)
        self._next_btn.setEnabled(total > 0 and idx < total - 1)
        self._save_btn.setEnabled(v is not None and (is_dirty or not is_saved))
        self._unsave_btn.setEnabled(v is not None and is_saved)

    # ----- public API -----
    def save_parameters(self) -> None:
        """Mark the current velocity as saved and emit ``valueSaved``."""
        v = self._current_value()
        if v is None:
            return
        self._saved_values.add(v)
        self._dirty_value = None
        self._refresh_combo()
        self.valueSaved.emit(v)

    def get_current_velocity(self) -> str:
        """Return the currently selected velocity string.

        Returns:
            Active velocity string.

        Raises:
            ValueError: If no velocity is currently selected.
        """

        value = self._current_value()
        if value is None:
            raise ValueError("No velocity is currently selected.")
        return value

    def set_available_velocities(self, values: List[str], saved_values: List[str] | None = None) -> None:
        """Replace the velocity list and optionally mark saved entries.

        Args:
            values: All available velocity strings.
            saved_values: Optional subset of velocities that already have saved
                parameters. If ``None``, existing saved states are retained where
                possible.
        """

        self._dirty_value = None
        if not values:
            self._all_values = []
            self._saved_values = set()
            self._refresh_combo()
            return

        dp = 0
        for v in values:
            s = str(v)
            if "." in s:
                dp = max(dp, len(s.split(".")[1]))

        formatted_values = [f"{float(v):.{dp}f}" for v in sorted(values, key=float)]
        self._all_values = formatted_values

        if saved_values is None:
            self._saved_values &= set(self._all_values)
        else:
            formatted_saved = {f"{float(v):.{dp}f}" for v in saved_values}
            self._saved_values = formatted_saved & set(self._all_values)

        self._refresh_combo()
        self._set_index(0)

    def set_chi_square(self, chi_square: Optional[float]) -> None:
        """Update the χ² display label.

        Args:
            chi_square: Value to display, or ``None`` to clear the label.
        """

        text = value_to_text(chi_square, "{:.3S}") if chi_square is not None else ""
        self._chi_square_value_label.setText(text)

    def set_modified(self, modified: bool = True) -> None:
        """Mark the current velocity as modified or clean.

        Args:
            modified: ``True`` to mark the current value dirty, or ``False`` to
                clear the dirty flag.
        """

        v = self._current_value()
        if v is None:
            return
        if modified:
            self._dirty_value = v
            self._refresh_combo()
        else:
            self._dirty_value = None
            self._refresh_combo()
            self.valueChanged.emit(v)

    def add_widget(self, widget: QWidget) -> None:
        """Append an extra widget to the right end of the velocity toolbar.

        Args:
            widget: Widget to append.
        """

        self._add_space(self._toolbar, 10)
        self._toolbar.addWidget(widget)


def _demo_main() -> int:
    """Run the velocity-bar controller as a standalone demo.

    Returns:
        Qt application exit code.
    """

    from settings.app_style import set_app_style
    from ui.menu_bar_controller import MENU_SPEC_EXAMPLE, MenuBarController
    from ui.params.sliders import FloatSlider

    class MainWindow(QMainWindow):
        """Demo main window for the velocity-bar controller."""

        def __init__(self):
            """Initialize the demo window and its widgets."""

            super().__init__()

            self._label = SvgLabel(r"\alpha_\beta")
            self._mark_dirty_btn = QPushButton("Modified")
            self._vc = VelocityBarController(window=self)
            self._menu_ctrl = MenuBarController(self, menu_spec=MENU_SPEC_EXAMPLE, native_menubar=False)
            self._fs = FloatSlider(
                label=r"\chi^2",
                min_val=0.0,
                max_val=10.0,
                val_fmt="{:.3S}"
            )

            self._vc.set_available_velocities(
                values=["1", "2.5", "3.75", "82.121"],
                saved_values=["2.5", "4"]
            )
            self._vc.set_chi_square(1.2)
            self._vc.add_widget(QLabel("test"))

            self._fs.valueChanged.connect(self._vc.set_chi_square)

            self._vc.valueChanged.connect(lambda v: print(f"Value changed to {v}"))
            self._vc.valueSaved.connect(lambda v: print(f"Value Saved to {v}"))
            self._vc.valueUnsaved.connect(lambda v: print(f"Value Unsaved to {v}"))

            self._mark_dirty_btn.clicked.connect(lambda: self._vc.set_modified())

            self._make_layout()

        def _make_layout(self) -> None:
            """Create the demo-window layout."""

            central = QWidget(self)
            self.setCentralWidget(central)
            b_layout = QHBoxLayout()
            b_layout.addWidget(self._mark_dirty_btn, 0)
            b_layout.addWidget(self._fs, 1)
            main_layout = QVBoxLayout(central)
            main_layout.addWidget(self._label, 1)
            main_layout.addLayout(b_layout, 0)

    app = QApplication(sys.argv)
    set_app_style(app)
    win = MainWindow()
    win.setWindowTitle("Velocities Controller")
    win.resize(1000, 400)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
