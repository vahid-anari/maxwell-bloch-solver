"""Text and scalar parameter widget backed by a line edit."""

from __future__ import annotations

import numbers
from typing import Optional, Union

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QGridLayout

from ui.labels import SvgLabel
from ui.params.parameter_widget_base import ParameterWidgetBase
from ui.numeric_line_edit import NumericLineEdit

Num = Union[int, float]


class ParameterLineEdit(ParameterWidgetBase[Num]):
    """Parameter widget that exposes a numeric value through a line edit."""

    def __init__(
            self,
            label: str,
            init_val: Num,
            val_fmt: str = "{:0.6g}",
            value_is_int: bool = False,
            unit_label: str = "",
            min_limit: Num | None = None,
            max_limit: Num | None = None,
            min_limit_inclusive: bool = True,
            max_limit_inclusive: bool = True,
            max_length: Optional[int] = None,
            width_chars: Optional[int] = None,
            parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the parameter line edit.

        Args:
            label: Parameter name displayed to the left of the line edit.
            init_val: Initial value.
            val_fmt: Display format string.
            value_is_int: Whether the value is an integer.
            unit_label: Optional unit shown to the right, as LaTeX.
            min_limit: Optional lower hard limit.
            max_limit: Optional upper hard limit.
            min_limit_inclusive: Whether the lower hard limit is inclusive.
            max_limit_inclusive: Whether the upper hard limit is inclusive.
            max_length: Optional maximum number of characters.
            width_chars: Optional width of the line edit in characters.
            parent: Optional parent widget.
        """

        super().__init__(parent)

        self._value_is_int = value_is_int
        self._parse = int if value_is_int else float
        self._label = SvgLabel(f"{label}=", alignment=Qt.AlignRight | Qt.AlignVCenter)
        self._measured_name_width = self._label.sizeHint().width()
        self._unit_label: SvgLabel | None = None
        if unit_label:
            self._unit_label = SvgLabel(f"({unit_label})")
        self._line_edit = NumericLineEdit(
            init_val=init_val,
            value_is_int=value_is_int,
            val_fmt=val_fmt,
            min_limit=min_limit,
            max_limit=max_limit,
            min_limit_inclusive=min_limit_inclusive,
            max_limit_inclusive=max_limit_inclusive,
            place_holder_text="Enter an int" if value_is_int == "int" else "Enter a float",
            max_length=max_length,
            width_chars=width_chars,
        )
        self._line_edit.valueChanged.connect(self._on_values_changed)

        self._make_layout()

    def _make_layout(self) -> None:
        """Create the layout used by this widget."""

        gl = QGridLayout(self)
        gl.setSpacing(0)
        gl.addWidget(self._label, 0, 0)
        gl.addWidget(self._line_edit, 0, 1)
        if self._unit_label is not None:
            gl.addWidget(self._unit_label, 0, 2)
            gl.setColumnStretch(3, 1)
        else:
            gl.setColumnStretch(2, 1)
        self._gl = gl
        self._update_layout()

    def _update_layout(self) -> None:
        """Reserve the effective name width for the label column."""

        self._gl.setColumnMinimumWidth(0, self._effective_name_width())

    # ----- internal helpers -----
    def _on_values_changed(self) -> None:
        """Handle the values changed event."""

        self.valueChanged.emit(self.get_value())

    # ----- public API -----
    def get_value(self) -> Num:
        """Return the current value."""

        return self._line_edit.get_value()

    def _validate_value(self, value: Num) -> Num:
        """Validate a value before applying it.

        Args:
            value: Proposed value.

        Returns:
            Validated value.

        Raises:
            TypeError: If ``value`` is not a number, or not an integer on an
                integer line edit. ``bool`` is rejected.
        """
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise TypeError(f"value must be a number, not {type(value).__name__}")
        if self._value_is_int and not isinstance(value, numbers.Integral):
            raise TypeError(f"value must be an int, not {type(value).__name__}")
        return value

    def _apply_value(self, value: Num) -> None:
        """Apply a validated value to the widget state."""

        self._line_edit.set_value(self._parse(value))


def _demo_main() -> int:
    """Run this module as a standalone demo."""

    import sys
    from PySide6.QtWidgets import QApplication, QVBoxLayout
    from settings.app_style import AppStyleProxy

    app = QApplication(sys.argv)
    app.setStyle(AppStyleProxy())

    win = QWidget()
    win.setWindowTitle("ParameterLineEdit Demo")

    cb = ParameterLineEdit(
        label="t",
        init_val=5,
        val_fmt="{:0.1f}",
        unit_label=r"\mathrm{s}",
        min_limit=0.0,
        min_limit_inclusive=False,
        # max_limit=1.0e100,
        parent=win
    )
    cb2 = ParameterLineEdit(
        label="A_\\alpha",
        init_val=5,
        value_is_int=True,
        parent=win
    )

    cb.valueChanged.connect(print)
    layout = QVBoxLayout(win)
    layout.addWidget(cb)
    layout.addWidget(cb2)

    win.resize(300, 200)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
