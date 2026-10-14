"""MB Solver's parameter tabs, built with the sciwidgets parameter panel.

The tabs come from the ``"panel"`` section of ``resources/settings.json`` (see
``sciwidgets.panel``). This module adds what is specific to MB Solver: its own
widget types (pulse, step, initial conditions, sample properties), the
current-span signals for the pulse and step tabs, the Fit tab switch and the
scaling-formula dialog.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from sciwidgets.panel import ParameterTabs, register_type, widget_types
from mbsolver.config.ui_defaults import SLIDER_SHOW_RANGE
from mbsolver.ui.widgets.initial_conditions import InitialConditionsWidget
from mbsolver.ui.widgets.pulse_function import PulseFunctionWidget
from mbsolver.ui.widgets.sample_properties import SamplePropertiesWidget
from mbsolver.ui.widgets.step_function import StepFunctionWidget
from mbsolver.utils.helper_funcs import pretty_json, set_win_center

APP_WIDGET_TYPES = {
    "pulse": PulseFunctionWidget,
    "step": StepFunctionWidget,
    "ics": InitialConditionsWidget,
    "sample-props": SamplePropertiesWidget,
}
"""MB Solver's own widget types, usable in the panel description."""


def _register_app_types() -> None:
    """Register MB Solver's widget types with the panel (once)."""
    known = set(widget_types())
    for name, cls in APP_WIDGET_TYPES.items():
        if name not in known:
            register_type(name, cls)


class ParameterTabsWidget(ParameterTabs):
    """Parameter tabs with MB Solver's widget types and current-span signals.

    Signals:
        valueChanged (str, object): The user changed a value (path, value).
        configChanged (str, object): The user changed a configuration
            (path, config).
        spanChanged (str): The parameters of the pulse or step widget at this
            path changed, or its tab was brought to the front.
        showSpan (bool): Whether the tab in front has a pulse or step widget,
            i.e. whether the plot should show its current span.
    """

    spanChanged = Signal(str)
    showSpan = Signal(bool)

    def __init__(self, description: Mapping[str, Any]) -> None:
        """Build the tabs.

        Args:
            description: The ``"panel"`` section of the settings file.
        """
        _register_app_types()
        description = copy.deepcopy(dict(description))
        if not SLIDER_SHOW_RANGE:
            description["defaults"] = {"show_range": False, **description.get("defaults", {})}
        super().__init__(description)

        # Tabs whose pulse/step widget drives the current span on the plot
        self._span_path_by_tab: Dict[str, str] = {}
        for path, widget in self.items():
            if isinstance(widget, (PulseFunctionWidget, StepFunctionWidget)):
                tab_id = next(t for t in self.tab_ids() if path in self.page(t).paths())
                self._span_path_by_tab[tab_id] = path
                widget.valueChanged.connect(lambda _, p=path: self.spanChanged.emit(p))

        self.currentChanged.connect(self._on_current_tab_changed)

    def _on_current_tab_changed(self, _index: int) -> None:
        """Report the current span of the tab in front, if it has one."""
        path = self._span_path_by_tab.get(self.current_tab())
        if path is not None:
            self.spanChanged.emit(path)
            self.showSpan.emit(True)
        else:
            self.showSpan.emit(False)

    # ----- values, sorted by path so saved files keep a stable order -----
    def get_value(self) -> Dict[str, Any]:
        """Return all values as ``{path: value}``, sorted by path."""
        return dict(sorted(super().get_value().items()))

    def get_config(self) -> Dict[str, Dict[str, Any]]:
        """Return all configurations as ``{path: config}``, sorted by path."""
        return dict(sorted(super().get_config().items()))

    # ----- MB-specific -----
    def set_fit_tab_enable(self, enabled: bool) -> None:
        """Enable or disable the contents of the Fit tab (the tab stays selectable).

        Args:
            enabled: Whether the Fit tab's widgets are enabled.
        """
        if "fit" in self.tab_ids():
            self.page("fit").setEnabled(enabled)

    def show_scaling_formula(self) -> None:
        """Open the scaling-formula dialog of the sample-properties widget."""
        self.get_widget("solve.sample").show_formula()


def _demo_main() -> int:
    """Run the parameter tabs on their own: ``python -m mbsolver.app.parameter_tabs``.

    Returns:
        Qt application exit code.
    """

    from PySide6.QtWidgets import QApplication, QMainWindow
    from mbsolver.paths import SETTINGS_FILE_PATH
    from mbsolver.config.app_style import set_app_style
    from sciwidgets.window import MenuBarController
    from mbsolver.utils.helper_funcs import read_json

    class MainWindow(QMainWindow):
        """Demo main window for the parameter tabs."""

        def __init__(self):
            """Initialize the demo window and its menu."""

            super().__init__()
            self.value_label = QLabel("value:")
            self.config_label = QLabel("config:")

            self._params_tabs = ParameterTabsWidget(read_json(SETTINGS_FILE_PATH)["panel"])
            self._params_tabs.valueChanged.connect(self._on_value_changed)
            self._params_tabs.configChanged.connect(self._on_config_changed)

            self._menu_ctrl = MenuBarController(
                window=self,
                menu_spec={
                    "File": [
                        {"id": "save_parameters", "text": "Save"},
                    ],
                    "Help": [
                        {"id": "show_scaling_formula", "text": "Show scaling formula"},
                        {"id": "show_fit_tab", "text": "Show fit tab", "checkable": True, "checked": True},
                    ],
                },
                native_menubar=False,
            )
            self._menu_ctrl.actionTriggered.connect(self._on_menubar_clicked)

            central = QWidget(self)
            self.setCentralWidget(central)
            m_l = QVBoxLayout(central)
            t_l = QHBoxLayout()
            t_l.addWidget(self.value_label)
            t_l.addWidget(self.config_label)
            m_l.addLayout(t_l, 1)
            m_l.addWidget(self._params_tabs, 0)

        def _on_menubar_clicked(self, menu_id: str, act_id: str, checked: bool) -> None:
            """Handle menu-bar actions in the demo."""
            if act_id == "save_parameters":
                text = pretty_json({
                    "params": self._params_tabs.get_value(),
                    "configs": self._params_tabs.get_config(),
                })
                Path("parameters.json").write_text(text, encoding="utf-8")
                print("Parameters saved")
            elif act_id == "show_scaling_formula":
                self._params_tabs.show_scaling_formula()
            elif act_id == "show_fit_tab":
                self._params_tabs.set_fit_tab_enable(checked)

        def _on_value_changed(self, path: str, value: Any) -> None:
            """Show the last changed value."""
            text = value if isinstance(value, (int, float, bool)) else pretty_json(value)
            self.value_label.setText(f"{path}: {text}")

        def _on_config_changed(self, path: str, config: Dict[str, Any]) -> None:
            """Show the last changed configuration."""
            self.config_label.setText(f"{path}: {pretty_json(config)}")

    app = QApplication(sys.argv)
    set_app_style(app)

    win = MainWindow()
    win.setWindowTitle("Parameter tabs")
    win.resize(1000, 600)
    set_win_center(win, app)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
