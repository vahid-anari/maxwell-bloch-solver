"""Boolean parameter widget backed by a checkbox with an optional state label."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QWidget, QCheckBox, QStackedWidget

from ui.labels import SvgLabel
from ui.params.parameter_widget_base import ParameterWidgetBase


class ParameterToggle(ParameterWidgetBase[bool]):
    """Parameter widget with a checkbox and an optional state-dependent label."""

    def __init__(
            self,
            text: str,
            label_on: str | None = None,
            label_off: str | None = None,
            checked: bool = True,
            parent: QWidget | None = None,
    ) -> None:
        """Initialize the toggle widget.

        Args:
            text: Checkbox text.
            label_on: Label shown when the checkbox is checked. ``None`` shows
                nothing in that state.
            label_off: Label shown when the checkbox is unchecked. ``None``
                shows nothing in that state.
            checked: Initial checked state.
            parent: Optional parent widget.
        """

        super().__init__(parent)

        self._check = QCheckBox(text, self)
        self._check.setChecked(checked)
        self._stack: QStackedWidget | None = None
        if label_on is not None or label_off is not None:
            self._stack = QStackedWidget(self)
            align = Qt.AlignRight | Qt.AlignVCenter
            for lbl in (label_off, label_on):  # index 0 = off, 1 = on
                self._stack.addWidget(
                    SvgLabel(lbl, alignment=align, fix_size=True) if lbl is not None else QWidget()
                )
            self._stack.setCurrentIndex(int(checked))

        self._check.toggled.connect(self._on_toggled)

        self._make_layout()

    def _make_layout(self) -> None:
        """Create the grid: [name spacer | checkbox | stretch | label | value spacer]."""

        gl = QGridLayout(self)
        gl.setSpacing(0)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.addWidget(self._check, 0, 1)
        if self._stack is not None:
            gl.addWidget(self._stack, 0, 3, Qt.AlignRight | Qt.AlignVCenter)
        gl.setColumnStretch(2, 1)
        self._gl = gl
        self._update_layout()

    def _update_layout(self) -> None:
        """Indent the checkbox by half the shared name width of sibling widgets."""
        self._gl.setColumnMinimumWidth(0, self._name_width // 2)

    def _on_toggled(self, state: bool) -> None:
        """Switch the label and emit the new value.

        Args:
            state: New checked state.
        """

        if self._stack is not None:
            self._stack.setCurrentIndex(int(state))
        self.valueChanged.emit(state)

    def get_value(self) -> bool:
        """Return whether the checkbox is checked.

        Returns:
            Current checked state.
        """

        return self._check.isChecked()

    def _validate_value(self, value: bool) -> bool:
        """Validate a value before applying it.

        Args:
            value: Proposed checked state.

        Returns:
            Validated checked state.

        Raises:
            TypeError: If ``value`` is not a bool.
        """

        if not isinstance(value, bool):
            raise TypeError("'value' must be a bool")
        return value

    def _apply_value(self, value: bool) -> None:
        """Apply a validated value to the checkbox.

        The label follows automatically through the ``toggled`` signal.

        Args:
            value: Checked state to apply.
        """

        self._check.setChecked(value)


def _demo_main() -> int:
    """Run this module as a standalone demo.

    Returns:
        Qt application exit code.
    """

    import sys
    from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout

    from settings.app_style import AppStyleProxy

    app = QApplication(sys.argv)
    app.setStyle(AppStyleProxy())

    win = QWidget()
    win.setWindowTitle("ParameterToggle Demo")

    tg = ParameterToggle(
        text="Normalize to max",
        label_on=r"F = I_\mathrm{res} / \max(I_\mathrm{res}) \times I_\mathrm{scale}",
        label_off=r"F = I_\mathrm{res} \times I_\mathrm{scale}",
        checked=True,
        parent=win,
    )
    tg.valueChanged.connect(print)

    plain = ParameterToggle(text="Plain checkbox (no labels)", parent=win)
    plain.set_value(False)
    plain.valueChanged.connect(print)

    layout = QVBoxLayout(win)
    layout.addWidget(tg)
    layout.addWidget(plain)
    layout.addStretch(1)

    win.resize(500, 150)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
