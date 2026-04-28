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
        self._name_width = self._label.sizeHint().width()
        self._items = items
        combo = QComboBox(self)
        for v in items:
            combo.addItem(v)
        combo.currentIndexChanged.connect(self._on_values_changed)
        self._combo = combo

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

    def _update_layout(self) -> None:
        """Refresh layout sizing to reflect the current name width."""

        self._gl.setColumnMinimumWidth(0, self._name_width)

    def _on_values_changed(self) -> None:
        """Emit the current value after the combo-box selection changes."""

        self.valueChanged.emit(self.get_value())

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
            ValueError: If ``value`` is empty.
        """

        if not isinstance(value, str):
            raise TypeError("'value' must be a string")
        if not value:
            raise ValueError("item['text'] must be provided")
        return value

    def _apply_value(self, value: str) -> None:
        """Apply a validated value by selecting the matching combo item.

        Args:
            value: Combo-box text to select.

        Raises:
            ValueError: If no combo-box item matches ``value``.
        """

        idx = self._combo.findText(value)
        if idx < 0:
            raise ValueError(f"No combo item found for text={value!r}")
        self._combo.setCurrentIndex(idx)

    def set_value_width(self, width: int) -> None:
        """Keep API compatibility for callers that explicitly set value width.

        Args:
            width: Requested value width in pixels.

        Note:
            This widget does not use a separate value-width setting, so the
            argument is accepted only for interface compatibility.
        """

        _ = width

    def set_name_width(self, width: int) -> None:
        """Keep API compatibility for callers that explicitly set name width.

        Args:
            width: Requested name width in pixels.

        Note:
            This widget manages its own name width, so the argument is accepted
            only for interface compatibility.
        """

        _ = width


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
