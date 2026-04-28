"""Composite widget for sample and scaling properties used by the solver."""

from __future__ import annotations

from typing import Any, Dict

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from settings.ui_defaults import SLIDER_SHOW_RANGE
from ui.labels import SvgLabel
from ui.params.parameter_line_edit import ParameterLineEdit
from ui.params.parameter_widget_base import ParameterWidgetBase
from ui.params.scaling_parameters import ScalingParameters
from ui.params.sliders import FloatSlider
from utils.helper_funcs import make_layout, parse_orientation, pretty_json


class SamplePropertiesWidget(ParameterWidgetBase):
    """Composite widget for sample properties and derived scaling values."""

    def __init__(
        self,
        params_props: Dict[str, Any],
        parent: QWidget | None = None,
    ):
        """Initialize the sample-properties widget.

        Args:
            params_props: Mapping that describes the editable sample-property
                widgets and layout configuration.
            parent: Optional parent widget.
        """

        super().__init__(parent)
        self._widgets: Dict[str, ParameterWidgetBase] = {}
        self._unit_to_si_factors: Dict[str, float] = {}
        self._params_id = ["nu", "gamma", "t0", "l", "n0"]
        for param_id in self._params_id:
            p_props = params_props[param_id]
            w = self._make_widget(p_props)
            self._widgets[param_id] = w
            self._unit_to_si_factors[param_id] = p_props["unit_to_si_factor"]
            w.valueChanged.connect(self._on_value_changed)
            w.configChanged.connect(lambda: self.configChanged.emit(self.get_config()))
            w.valueWidthChanged.connect(self._update_layout)
            w.nameWidthChanged.connect(self._update_layout)

        self._scaling_params = ScalingParameters(parent=self)
        self._scaling_values: Dict[str, Any] = {}

        self._update_scales_values()

        make_layout(params_props["layout"], self._widgets, self)
        self._update_layout()

    # ----- internal helpers -----
    def _make_widget(self, widget_ctx: Dict[str, Any]) -> ParameterWidgetBase:
        """Create one child widget from the supplied configuration.

        Args:
            widget_ctx: Mapping describing the widget type, label, numeric range,
                formatting, and unit-conversion settings.

        Returns:
            Created parameter widget.

        Raises:
            ValueError: If the widget type is not recognized.
        """

        w_label = widget_ctx.get("label", "None")
        w_type = widget_ctx.get("type", "None")
        unit_to_si_factor = widget_ctx.get("unit_to_si_factor", 1.0)
        if w_type == "float-slider":
            return FloatSlider(
                label=w_label,
                unit=widget_ctx.get("unit", ""),
                min_val=widget_ctx.get("min_val", 0.0) / unit_to_si_factor,
                max_val=widget_ctx.get("max_val", 100.0) / unit_to_si_factor,
                init_val=widget_ctx.get("init_val", 0.0) / unit_to_si_factor,
                val_fmt=widget_ctx.get("val_fmt", "{:.3S}"),
                min_limit=widget_ctx.get("min_limit", None),
                min_limit_inclusive=widget_ctx.get("min_limit_inclusive", True),
                max_limit=widget_ctx.get("max_limit", None),
                max_limit_inclusive=widget_ctx.get("max_limit_inclusive", True),
                orientation=parse_orientation(widget_ctx.get("orientation", "h")),
                show_range=widget_ctx.get("show_range", True) if SLIDER_SHOW_RANGE else False,
            )
        if w_type == "line-edit":
            return ParameterLineEdit(
                label=w_label,
                init_val=widget_ctx.get("init_val", 1.0) / unit_to_si_factor,
                val_fmt=widget_ctx.get("val_fmt", "{:.6g}"),
                value_is_int=widget_ctx.get("value_is_int", False),
                unit_label=widget_ctx.get("unit_label", ""),
                min_limit=widget_ctx.get("min_limit", None),
                min_limit_inclusive=widget_ctx.get("min_limit_inclusive", True),
                max_limit=widget_ctx.get("max_limit", None),
                max_limit_inclusive=widget_ctx.get("max_limit_inclusive", True),
                max_length=widget_ctx.get("max_length", None),
                width_chars=widget_ctx.get("width_chars", None),
                parent=self,
            )

        raise ValueError(
            f"Unknown widget type {w_type!r}; expected 'float-slider' or 'line-edit'."
        )

    def _update_layout(self) -> None:
        """Synchronize child-widget name and value widths."""

        name_w = 0
        val_w = 0
        for w in self._widgets.values():
            n_w, v_w = w.get_name_width(), w.get_value_width()
            name_w, val_w = max(name_w, n_w), max(val_w, v_w)
        for w in self._widgets.values():
            w.set_name_width(name_w)
            w.set_value_width(val_w)

    def _update_scales_values(self) -> None:
        """Recompute derived scaling values from the current physical parameters."""

        self._scaling_params.set_values(
            gamma=self._widgets["gamma"].get_value() * self._unit_to_si_factors["gamma"],
            nu=self._widgets["nu"].get_value() * self._unit_to_si_factors["nu"],
            l=self._widgets["l"].get_value() * self._unit_to_si_factors["l"],
            n0=self._widgets["n0"].get_value() * self._unit_to_si_factors["n0"],
            t0=self._widgets["t0"].get_value() * self._unit_to_si_factors["t0"],
        )
        self._scaling_values = self._scaling_params.get_value()

    def _on_value_changed(self) -> None:
        """Recompute scaling values and emit the combined widget value."""

        self._update_scales_values()
        self.valueChanged.emit(self.get_value())

    # ----- public API -----
    def get_value(self) -> Dict[str, float]:
        """Return all sample and derived scaling values in SI units.

        Returns:
            Mapping containing derived scaling values and raw sample properties,
            all converted to SI units.
        """

        out: Dict[str, Any] = {
            "_comment": "All values are in SI units.",
            **self._scaling_values,
        }
        for n_id, w in self._widgets.items():
            out[n_id] = w.get_value() * self._unit_to_si_factors[n_id]

        return out

    def get_config(self) -> dict[str, Any]:
        """Return the range and format configuration of all child widgets.

        Returns:
            Mapping from parameter identifiers to child-widget configuration
            dictionaries.
        """

        out: dict[str, Any] = {}
        for n_id, w in self._widgets.items():
            out[n_id] = w.get_config()
        return out

    def set_value(self, value: Dict[str, Any]):
        """Apply SI values to child widgets after converting to display units.

        Args:
            value: Mapping containing parameter values expressed in SI units.
        """

        for n_id, w in self._widgets.items():
            if n_id in value:
                w.set_value(value[n_id] / self._unit_to_si_factors[n_id])
        self._update_scales_values()

    def set_config(self, config: dict[str, Any]):
        """Apply configuration mappings to matching child widgets.

        Args:
            config: Mapping from parameter identifiers to child-widget
                configuration dictionaries.
        """

        for n_id, w in self._widgets.items():
            if n_id in config:
                w.set_config(config[n_id])

    def show_formula(self) -> None:
        """Open the scaling-formula dialog provided by ``ScalingParameters``."""

        self._scaling_params.show_formula()


def _demo_main() -> int:
    """Run this module as a standalone demo.

    Returns:
        Qt application exit code.
    """

    import sys

    from paths import SETTINGS_FILE_PATH
    from settings.app_style import set_app_style
    from ui.menu_bar_controller import MenuBarController
    from utils.helper_funcs import read_json

    app = QApplication(sys.argv)
    set_app_style(app)

    win = QMainWindow()
    win.setWindowTitle("Input Parameters Demo")

    def_cfgs = read_json(SETTINGS_FILE_PATH)
    params_props = def_cfgs["tabs"]["sample"]["widgets"]["sample_props"]

    sp = SamplePropertiesWidget(
        params_props=params_props,
        parent=win,
    )

    menu_ctrl = MenuBarController(
        window=win,
        menu_spec={
            "Help": [
                {"id": "show_scaling_formula", "text": "Show scaling formula"},
            ],
        },
        native_menubar=False,
    )

    sp.valueChanged.connect(lambda d: print(pretty_json(obj=d)))
    menu_ctrl.actionTriggered.connect(sp.show_formula)

    sp.get_value()

    w = QWidget()
    layout = QVBoxLayout(w)
    layout.addWidget(SvgLabel(r"\alpha_\beta"), 1)
    layout.addWidget(sp, 0)
    win.setCentralWidget(w)
    win.resize(800, 600)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
