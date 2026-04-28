"""Text and scalar parameter widget backed by a line edit."""

from __future__ import annotations

from typing import Optional, Union

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QGridLayout

from ui.labels import SvgLabel
from ui.params.parameter_widget_base import ParameterWidgetBase
from ui.numeric_line_edit import NumericLineEdit

Num = Union[int, float]


class ParameterLineEdit(ParameterWidgetBase[Num]):
    """Parameter widget that exposes a scalar or text value through a line edit."""

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
        """Initialize ParameterLineEdit."""

        super().__init__(parent)

        self._parse = int if value_is_int else float
        self._label = SvgLabel(f"{label}=", alignment=Qt.AlignRight | Qt.AlignVCenter)
        self._name_width = self._label.sizeHint().width()
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
        if hasattr(self, "_unit_label"):
            gl.addWidget(self._unit_label, 0, 2)
            gl.setColumnStretch(3, 1)
        else:
            gl.setColumnStretch(2, 1)
        self._gl = gl

    def _update_layout(self) -> None:
        """Update the widget layout to reflect the current state."""

        self._gl.setColumnMinimumWidth(0, self._name_width)

    # ----- internal helpers -----
    def _on_values_changed(self) -> None:
        """Handle the values changed event."""

        self.valueChanged.emit(self.get_value())

    # ----- public API -----
    def get_value(self) -> Num:
        """Return the current value."""

        return self._line_edit.get_value()

    def _validate_value(self, value: Num) -> Num:
        """Validate the provided value."""

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Value must be an int or float")
        return value

    def _apply_value(self, value: Num) -> None:
        """Apply a validated value to the widget state."""

        self._line_edit.set_value(self._parse(value))

    def set_value_width(self, width: int) -> None:
        """Keep API compatibility for layouts that set a value width explicitly."""

        pass

    def set_name_width(self, width: int) -> None:
        """Keep API compatibility for layouts that set a name width explicitly."""

        pass


def _demo_main() -> int:
    """Run this module as a standalone demo."""

    import sys
    from PySide6.QtWidgets import QApplication, QVBoxLayout
    from settings.app_style import AppStyleProxy

    app = QApplication(sys.argv)
    app.setStyle(AppStyleProxy())

    win = QWidget()
    win.setWindowTitle("ParameterComboBox Demo")

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
