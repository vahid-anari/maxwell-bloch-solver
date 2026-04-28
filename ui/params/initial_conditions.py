"""Composite widget for entering solver initial-condition values."""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.labels import SvgLabel
from ui.params.parameter_widget_base import ParameterWidgetBase
from ui.params.sliders import FloatSlider
from utils.helper_funcs import make_box


class InitialConditionsWidget(ParameterWidgetBase[dict]):
    """Composite widget for editing initial populations and coherences."""

    def __init__(
        self,
        use_theta0: bool = True,
        init_w0: float = 1.0,
        init_R0: float = 0.01,
        val_fmt: str = "{:.3S}",
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the initial-conditions widget.

        Args:
            use_theta0: Whether the widget should start in the ``theta_0``-based
                initialization mode.
            init_w0: Initial value for ``w`` at ``tau = 0``.
            init_R0: Initial value for ``R`` at ``tau = 0``.
            val_fmt: Display format string used by the sliders.
            parent: Optional parent widget.
        """

        super().__init__(parent)

        self._use_theta0 = use_theta0
        self._is_updating_checks = False

        self._w0_slider = FloatSlider(
            label=r"w\vert_{\tau=0}",
            min_val=-1.0,
            max_val=1.0,
            init_val=init_w0,
            val_fmt=val_fmt,
            min_limit=-1.0,
            max_limit=1.0,
            min_limit_inclusive=True,
            max_limit_inclusive=True,
            parent=self,
        )

        self._R0_slider = FloatSlider(
            label=r"R\vert_{\tau=0}",
            min_val=-1.0,
            max_val=1.0,
            init_val=init_R0,
            val_fmt=val_fmt,
            min_limit=-1.0,
            max_limit=1.0,
            min_limit_inclusive=True,
            max_limit_inclusive=True,
            parent=self,
        )

        self._sliders = [self._w0_slider, self._R0_slider]
        for s in self._sliders:
            s.valueWidthChanged.connect(self._update_layout)
            s.nameWidthChanged.connect(self._update_layout)
            s.valueChanged.connect(self._on_values_changed)
            s.configChanged.connect(lambda: self.configChanged.emit(self.get_config()))

        self._make_layout()

    def _make_layout(self) -> None:
        """Create and assign the layout used by this widget."""

        theta0_l = QVBoxLayout()
        theta0_l.addWidget(SvgLabel(r"w\vert_{\tau=0}=\cos (\theta_0)", fix_size=True))
        theta0_l.addWidget(SvgLabel(r"R\vert_{\tau=0}=\sin (\theta_0)", fix_size=True))
        theta0_g = make_box("Use θ₀", theta0_l, checkable=True, checked=self._use_theta0)
        theta0_g.toggled.connect(self._update_check_state)
        self._theta0_g = theta0_g

        slider_l = QVBoxLayout()
        slider_l.addWidget(self._w0_slider)
        slider_l.addWidget(self._R0_slider)
        slider_g = make_box("Manual", slider_l, checkable=True, checked=not self._use_theta0)
        slider_g.toggled.connect(self._update_check_state)
        self._slider_g = slider_g

        main_layout = QVBoxLayout(self)
        main_layout.addStretch(1)
        main_layout.addWidget(theta0_g)
        main_layout.addStretch(1)
        main_layout.addWidget(slider_g)
        main_layout.addStretch(1)
        self._update_layout()

    def _update_layout(self) -> None:
        """Synchronize slider label and value widths across the widget."""

        name_w = 0
        val_w = 0
        for s in self._sliders:
            n_w, v_w = s.get_name_width(), s.get_value_width()
            name_w, val_w = max(name_w, n_w), max(val_w, v_w)
        for s in self._sliders:
            s.set_name_width(name_w)
            s.set_value_width(val_w)

    # ----- internal helpers -----
    def _update_check_state(self) -> None:
        """Keep the mode checkboxes mutually consistent.

        The widget supports two exclusive modes: ``theta_0`` mode and manual
        slider mode. This method updates the checkable group boxes so that only
        one mode remains active at a time.
        """

        if self._is_updating_checks:
            return
        self._is_updating_checks = True
        theta_checked = self._theta0_g.isChecked()
        manual_checked = self._slider_g.isChecked()

        if self._use_theta0:
            if manual_checked:
                self._use_theta0 = False
                self._theta0_g.setChecked(False)
                self._on_values_changed()
            else:
                self._theta0_g.setChecked(True)
        else:
            if theta_checked:
                self._use_theta0 = True
                self._slider_g.setChecked(False)
                self._on_values_changed()
            else:
                self._slider_g.setChecked(True)
        self._is_updating_checks = False

    def _on_values_changed(self) -> None:
        """Emit the current widget value after an internal control changes."""

        self.valueChanged.emit(self.get_value())

    # ----- public API -----
    def get_value(self) -> Dict[str, Any]:
        """Return the current widget value.

        Returns:
            Mapping containing the active mode and current slider values.
        """

        return {
            "use_theta0": self._use_theta0,
            "w0": self._w0_slider.get_value(),
            "R0": self._R0_slider.get_value(),
        }

    def _validate_value(self, value: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a proposed widget value mapping.

        Args:
            value: Proposed value mapping.

        Returns:
            Completed mapping with missing keys filled from the current state.

        Raises:
            TypeError: If ``value`` is not a dictionary.
        """

        if not isinstance(value, dict):
            raise TypeError("Value must be a dictionary")
        return {
            "use_theta0": value.get("use_theta0", self._use_theta0),
            "w0": value.get("w0", self._w0_slider.get_value()),
            "R0": value.get("R0", self._R0_slider.get_value()),
        }

    def _apply_value(self, value: Dict[str, Any]) -> None:
        """Apply a validated value mapping to the widget state.

        Args:
            value: Validated mapping to apply.
        """

        self.blockSignals(True)
        try:
            self._theta0_g.setChecked(value["use_theta0"])
            self._w0_slider.set_value(value["w0"])
            self._R0_slider.set_value(value["R0"])
        finally:
            self.blockSignals(False)

    def get_config(self) -> Dict[str, Any]:
        """Return the current slider configuration mapping.

        Returns:
            Mapping containing the configuration of the ``w0`` and ``R0``
            sliders.
        """

        return {
            "w0": self._w0_slider.get_config(),
            "R0": self._R0_slider.get_config(),
        }

    def _apply_config(self, config: dict) -> None:
        """Apply a validated configuration mapping.

        Args:
            config: Configuration mapping to apply.
        """

        self._w0_slider.set_config(config["w0"])
        self._R0_slider.set_config(config["R0"])


def _demo_main() -> int:
    """Run this module as a standalone demo.

    Returns:
        Qt application exit code.
    """

    import sys

    from settings.app_style import set_app_style

    app = QApplication(sys.argv)
    set_app_style(app)

    win = QWidget()
    win.setWindowTitle("InitialConditionsWidget Demo")

    ics = InitialConditionsWidget(use_theta0=True)

    layout = QVBoxLayout(win)
    layout.addWidget(ics)

    win.resize(700, 400)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
