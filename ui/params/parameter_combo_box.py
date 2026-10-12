"""Discrete parameter widget backed by a combo box."""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QGridLayout, QHBoxLayout, QWidget

from settings.app_style import AppStyleProxy
from ui.labels import SvgLabel
from ui.params.parameter_widget_base import ParameterWidgetBase


class ParameterComboBox(ParameterWidgetBase[str]):
    """Parameter widget that exposes a discrete choice through a combo box."""

    def __init__(
        self,
        label: str,
        items: List[str],
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the parameter combo-box widget.

        Args:
            label: Parameter name displayed to the left of the combo box.
            items: Ordered list of selectable string values.
            parent: Optional parent widget.
        """

        super().__init__(parent)

        self._label = SvgLabel(f"{label}=", alignment=Qt.AlignRight | Qt.AlignVCenter)
        self._measured_name_width = self._label.sizeHint().width()
        combo = QComboBox(self)
        for v in items:
            combo.addItem(v)
        combo.activated.connect(self._on_activated)
        self._combo = combo
        self._last_value = combo.currentText()

        self._make_layout()

    def _make_layout(self) -> None:
        """Create and assign the grid layout used by this widget."""

        gl = QGridLayout(self)
        gl.setSpacing(0)
        gl.addWidget(self._label, 0, 0)
        gl.addWidget(self._combo, 0, 1)
        gl.setColumnStretch(0, 0)
        gl.setColumnStretch(1, 0)
        gl.setColumnStretch(2, 1)
        self._gl = gl
        self._update_layout()

    def _update_layout(self) -> None:
        """Reserve the effective name width for the label column."""

        self._gl.setColumnMinimumWidth(0, self._effective_name_width())

    def _on_activated(self, _index: int) -> None:
        """Emit the value after the user picks a different item."""
        value = self.get_value()
        if value != self._last_value:
            self._last_value = value
            self.valueChanged.emit(value)

    def get_value(self) -> str:
        """Return the currently selected combo-box text.

        Returns:
            Selected string value.
        """

        return self._combo.currentText()

    def _validate_value(self, value: str) -> str:
        """Validate a value before applying it to the combo box.

        Args:
            value: Proposed combo-box text.

        Returns:
            Validated combo-box text.

        Raises:
            TypeError: If ``value`` is not a string.
            ValueError: If no combo-box item matches ``value``.
        """

        if not isinstance(value, str):
            raise TypeError("'value' must be a string")
        if self._combo.findText(value) < 0:
            raise ValueError(f"No combo item found for text={value!r}")
        return value

    def _apply_value(self, value: str) -> None:
        """Apply a validated value by selecting the matching combo item.

        Args:
            value: Combo-box text to select.
        """
        self._combo.setCurrentIndex(self._combo.findText(value))
        self._last_value = value



def _demo_main() -> int:
    """Run this module as a standalone demo.

    Returns:
        Qt application exit code.
    """

    import sys

    app = QApplication(sys.argv)
    app.setStyle(AppStyleProxy())

    win = QWidget()
    win.setWindowTitle("ParameterComboBox Demo")

    cb = ParameterComboBox(
        label="t",
        items=["T₀", "d", "h", "m", "S", "ms", "µs", "ns"],
        parent=win,
    )

    cb.set_value("ns")
    cb.valueChanged.connect(print)
    layout = QHBoxLayout(win)
    layout.addWidget(cb)

    win.resize(300, 200)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
