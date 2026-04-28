"""Tab-based container for grouped parameter widgets.

The widget definitions are driven by the JSON settings file so the
parameter-side UI can be assembled declaratively.
"""

from __future__ import annotations

"""QTabWidget-based UI that groups parameter controls into categories."""

import copy
import sys
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCore import QRect, QSize, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStyle,
    QStyleOptionTab,
    QStylePainter,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from settings.ui_defaults import SLIDER_SHOW_RANGE
from ui.params.cosh_function import CoshFunctionWidget
from ui.params.initial_conditions import InitialConditionsWidget
from ui.params.parameter_combo_box import ParameterComboBox
from ui.params.parameter_line_edit import ParameterLineEdit
from ui.params.parameter_widget_base import ParameterWidgetBase
from ui.params.range_sliders import FloatRangeSlider
from ui.params.sample_properties import SamplePropertiesWidget
from ui.params.sliders import ArraySlider, FloatSlider, IntSlider
from utils.helper_funcs import make_layout, parse_orientation, pretty_json, set_win_center


class HorizontalWestTabBar(QTabBar):
    """Tab bar that paints west-positioned tab text horizontally."""

    def tabSizeHint(self, index: int) -> QSize:
        """Return the preferred size for one tab.

        Args:
            index: Tab index.

        Returns:
            Preferred tab size with width and height transposed for west/east
            placement.
        """

        s = super().tabSizeHint(index)
        s.transpose()
        return s

    def paintEvent(self, event):
        """Handle the Qt paint-event callback.

        Args:
            event: Qt paint event.
        """

        painter = QStylePainter(self)
        opt = QStyleOptionTab()

        for i in range(self.count()):
            self.initStyleOption(opt, i)
            painter.drawControl(QStyle.CE_TabBarTabShape, opt)

            painter.save_parameters()

            size = opt.rect.size()
            size.transpose()
            r = QRect(opt.rect)
            r.setSize(size)
            r.moveCenter(opt.rect.center())
            opt.rect = r

            c = self.tabRect(i).center()
            painter.translate(c)
            painter.rotate(90)
            painter.translate(-c)

            painter.drawControl(QStyle.CE_TabBarTabLabel, opt)
            painter.restore()


class ParameterTabsWidget(QTabWidget):
    """Tab widget that builds parameter controls from a configuration mapping."""

    valueChanged = Signal(str, object)
    configChanged = Signal(str, object)
    coshPeakChanged = Signal(str)
    showCoshPeak = Signal(bool)

    def __init__(self, tabs_cfg: Dict[str, Any]) -> None:
        """Initialize the parameter-tabs widget.

        Args:
            tabs_cfg: Mapping describing tabs, widgets, and layout properties.
        """

        super().__init__()

        self._widgets_by_tabs: Dict[str, Dict[str, ParameterWidgetBase]] = {}
        self._widgets_by_path: Dict[str, ParameterWidgetBase] = {}
        self._value = {}
        self._config = {}
        self._tabs_with_cosh: Dict[int, str] = {}
        self._fit_tab_index = None

        self.setTabsClosable(False)

        for idx, (tab_id, tab_ctx) in enumerate(tabs_cfg.items()):
            if tab_id == "fit":
                self._fit_tab_index = idx
            tab_widgets_def = tab_ctx.get("widgets", {})
            tab_props = tab_ctx.get("props", {})
            self._widgets_by_tabs[tab_id] = {}
            for w_id, w_ctx in tab_widgets_def.items():
                w = self._make_widget(w_ctx)
                self._widgets_by_tabs[tab_id][w_id] = w
                w.valueWidthChanged.connect(lambda _, t_id=tab_id: self._update_tab_layout(t_id))
                w.nameWidthChanged.connect(lambda _, t_id=tab_id: self._update_tab_layout(t_id))

                path = w_ctx.get("path", "")
                if path:
                    self._widgets_by_path[path] = w
                    emit_peak_changed = False
                    if isinstance(w, CoshFunctionWidget):
                        self._tabs_with_cosh[idx] = path
                        emit_peak_changed = True
                    w.valueChanged.connect(
                        lambda val, p=path, emit=emit_peak_changed: self._on_value_changed(
                            path=p,
                            value=val,
                            emit_peak_changed=emit,
                        )
                    )

                    w.configChanged.connect(
                        lambda cfg, p=path: self._on_config_changed(
                            path=p,
                            config=cfg,
                        )
                    )

            self._add_tab(tab_id, tab_props)

        for p, w in sorted(self._widgets_by_path.items()):
            self._value[p] = w.get_value()
            self._config[p] = w.get_config()

        self.currentChanged.connect(self._on_current_tab_changed)

    def _make_widget(self, widget_ctx: Dict[str, Any]) -> ParameterWidgetBase:
        """Create one child widget from the supplied configuration.

        Args:
            widget_ctx: Widget specification mapping.

        Returns:
            Instantiated parameter widget.

        Raises:
            ValueError: If the widget type is unknown.
        """

        w_label = widget_ctx.get("label", "None")
        w_type = widget_ctx.get("type", "None")
        if w_type == "int-slider":
            return IntSlider(
                label=w_label,
                unit=widget_ctx.get("unit", ""),
                min_val=widget_ctx.get("min_val", 0),
                max_val=widget_ctx.get("max_val", 100),
                init_val=widget_ctx.get("init_val", 0),
                val_fmt=widget_ctx.get("val_fmt", "{:.3S}"),
                min_limit=widget_ctx.get("min_limit", None),
                min_limit_inclusive=widget_ctx.get("min_limit_inclusive", True),
                max_limit=widget_ctx.get("max_limit", None),
                max_limit_inclusive=widget_ctx.get("max_limit_inclusive", True),
                orientation=parse_orientation(widget_ctx.get("orientation", "h")),
                show_range=widget_ctx.get("show_range", True) if SLIDER_SHOW_RANGE else False,
            )
        if w_type == "float-slider":
            return FloatSlider(
                label=w_label,
                unit=widget_ctx.get("unit", ""),
                min_val=widget_ctx.get("min_val", 0.0),
                max_val=widget_ctx.get("max_val", 100.0),
                init_val=widget_ctx.get("init_val", 0.0),
                val_fmt=widget_ctx.get("val_fmt", "{:.3S}"),
                min_limit=widget_ctx.get("min_limit", None),
                min_limit_inclusive=widget_ctx.get("min_limit_inclusive", True),
                max_limit=widget_ctx.get("max_limit", None),
                max_limit_inclusive=widget_ctx.get("max_limit_inclusive", True),
                orientation=parse_orientation(widget_ctx.get("orientation", "h")),
                show_range=widget_ctx.get("show_range", True) if SLIDER_SHOW_RANGE else False,
            )
        if w_type == "array-slider":
            return ArraySlider(
                label=w_label,
                unit=widget_ctx.get("unit", ""),
                arr_length=widget_ctx.get("array_length", 2),
                min_val=widget_ctx.get("min_val", 0.0),
                max_val=widget_ctx.get("max_val", 1.0),
                init_index=widget_ctx.get("init_index", -1),
                val_fmt=widget_ctx.get("val_fmt", "{:.3S}"),
                orientation=parse_orientation(widget_ctx.get("orientation", "h")),
                show_range=widget_ctx.get("show_range", True) if SLIDER_SHOW_RANGE else False,
            )
        if w_type == "range-slider":
            return FloatRangeSlider(
                label=w_label,
                min_val=widget_ctx.get("min_val", 0.0),
                max_val=widget_ctx.get("max_val", 100.0),
                init_vals=widget_ctx.get("init_vals", (1.0, 10.0)),
                val_fmt=widget_ctx.get("val_fmt", "{:.3S}"),
                use_margins=widget_ctx.get("use_margins", True),
                margins=widget_ctx.get("margins", (10, 10)),
                min_limit=widget_ctx.get("min_limit", None),
                min_limit_inclusive=widget_ctx.get("min_limit_inclusive", True),
                max_limit=widget_ctx.get("max_limit", None),
                max_limit_inclusive=widget_ctx.get("max_limit_inclusive", True),
                orientation=parse_orientation(widget_ctx.get("orientation", "h")),
                show_range=widget_ctx.get("show_range", True) if SLIDER_SHOW_RANGE else False,
            )
        if w_type == "ics":
            return InitialConditionsWidget(
                use_theta0=widget_ctx.get("use_theta0", True),
                init_w0=widget_ctx.get("init_w0", 1.0),
                init_R0=widget_ctx.get("init_R0", 1.0e-8),
                val_fmt=widget_ctx.get("val_fmt", "{:.3S}"),
            )
        if w_type == "cosh":
            return CoshFunctionWidget(params_props=widget_ctx, parent=self)
        if w_type == "combo-box":
            return ParameterComboBox(
                label=w_label,
                items=widget_ctx.get("items", []),
                parent=self,
            )
        if w_type == "line-edit":
            return ParameterLineEdit(
                label=w_label,
                init_val=widget_ctx.get("init_val", 1.0),
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
        if w_type == "sample-props":
            return SamplePropertiesWidget(params_props=widget_ctx, parent=self)

        raise ValueError(
            f"Unknown widget type {w_type!r}; expected 'int-slider', 'float-slider', "
            f"'array-slider', 'range-slider', 'theta', 'cosh', 'combo-box', "
            f"'line-edit', or 'sample-props'."
        )

    def _add_tab(self, tab_id: str, props: Dict[str, Any]) -> None:
        """Create, populate, and append one tab page.

        Args:
            tab_id: Internal tab identifier.
            props: Tab layout and label properties.
        """

        widgets = self._widgets_by_tabs[tab_id]
        tab_widget = QWidget()
        label = props.get("label", "None")
        make_layout(props, widgets, tab_widget)
        self.addTab(tab_widget, label)
        self._update_tab_layout(tab_id)

    def _update_tab_layout(self, tab_id: str) -> None:
        """Align name and value widths across widgets in one tab.

        Args:
            tab_id: Internal tab identifier.
        """

        name_w = 0
        val_w = 0
        for w in self._widgets_by_tabs[tab_id].values():
            n_w, v_w = w.get_name_width(), w.get_value_width()
            name_w, val_w = max(name_w, n_w), max(val_w, v_w)
        for w in self._widgets_by_tabs[tab_id].values():
            w.set_name_width(name_w)
            w.set_value_width(val_w)

    def _on_value_changed(self, path: str, value: Any, emit_peak_changed: bool = False) -> None:
        """Cache a new widget value and emit the related signals.

        Args:
            path: Widget path identifier.
            value: New widget value.
            emit_peak_changed: Whether to emit ``coshPeakChanged`` as well.
        """

        self._value[path] = value
        if emit_peak_changed:
            self.coshPeakChanged.emit(path)
        self.valueChanged.emit(path, value)

    def _on_config_changed(self, path: str, config: Dict[str, Any]) -> None:
        """Cache a new widget configuration and emit ``configChanged``.

        Args:
            path: Widget path identifier.
            config: Updated widget configuration mapping.
        """

        self._config[path] = config
        self.configChanged.emit(path, config)

    def _on_current_tab_changed(self, tab_idx: int) -> None:
        """Emit cosh-related signals when the active tab changes.

        Args:
            tab_idx: New active tab index.
        """

        if tab_idx in self._tabs_with_cosh.keys():
            path = self._tabs_with_cosh[tab_idx]
            self.coshPeakChanged.emit(path)
            self.showCoshPeak.emit(True)
        else:
            self.showCoshPeak.emit(False)

    def get_config(self) -> Dict[str, float]:
        """Return a deep copy of the full widget-configuration mapping.

        Returns:
            Deep copy of the cached configuration mapping.
        """

        return copy.deepcopy(self._config)

    def get_value(self) -> Dict[str, Any]:
        """Return a deep copy of the current widget-value mapping.

        Returns:
            Deep copy of the cached value mapping.
        """

        return copy.deepcopy(self._value)

    def get_widget(self, path: str) -> ParameterWidgetBase:
        """Return the widget registered under a given path.

        Args:
            path: Widget path identifier.

        Returns:
            Registered widget instance.
        """

        return self._widgets_by_path[path]

    def set_value(self, value: Dict[str, Any]) -> None:
        """Apply a value mapping to all matching widgets without emitting signals.

        Args:
            value: Mapping from widget paths to new values.
        """

        self.blockSignals(True)
        try:
            for p, w in self._widgets_by_path.items():
                if p in value.keys():
                    v = value[p]
                    self._value[p] = v
                    w.set_value(v)
        finally:
            self.blockSignals(False)

    def set_config(self, config: Dict[str, Any]) -> None:
        """Apply a configuration mapping to all matching widgets silently.

        Args:
            config: Mapping from widget paths to configuration dictionaries.
        """

        self.blockSignals(True)
        try:
            for p, w in self._widgets_by_path.items():
                if p in config.keys():
                    cfg = config[p]
                    self._config[p] = cfg
                    w.set_config(cfg)
        finally:
            self.blockSignals(False)

    def show_widget(self, path: str, show: bool) -> None:
        """Show or hide the widget registered under a path.

        Args:
            path: Widget path identifier.
            show: Whether the widget should be shown.
        """

        w = self._widgets_by_path[path]
        if show:
            w.show()
        else:
            w.hide()

    def set_fit_tab_enable(self, visible: bool) -> None:
        """Enable or disable the fit-tab page.

        Args:
            visible: Whether the fit tab should be enabled.
        """

        if self._fit_tab_index is None:
            return

        page = self.widget(self._fit_tab_index)
        if page is not None:
            page.setEnabled(visible)

    def show_scaling_formula(self) -> None:
        """Open the scaling-formula dialog via the sample-properties widget."""

        self._widgets_by_path["solve.sample"].show_formula()


def _demo_main() -> int:
    """Run the parameter-tabs widget as a standalone demo.

    Returns:
        Qt application exit code.
    """

    from PySide6.QtWidgets import QApplication, QMainWindow
    from paths import SETTINGS_FILE_PATH
    from settings.app_style import set_app_style
    from ui.menu_bar_controller import MenuBarController
    from utils.helper_funcs import read_json

    class MainWindow(QMainWindow):
        """Demo main window for the parameter-tabs widget."""

        def __init__(self):
            """Initialize the demo window and its menu/controller wiring."""

            super().__init__()
            self._solve_counter = 0
            self._plot_counter = 0

            self.value_label = QLabel("value:")
            self.config_label = QLabel("config:")

            def_cfgs = read_json(SETTINGS_FILE_PATH)
            params_tabs = def_cfgs["tabs"]
            params_tabs = ParameterTabsWidget(params_tabs)
            params_tabs.valueChanged.connect(self._on_value_changed)
            params_tabs.configChanged.connect(self._on_config_changed)
            self._params_tabs = params_tabs

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

            self._make_layout()

        def _make_layout(self):
            """Create the demo-window layout."""

            central = QWidget(self)
            self.setCentralWidget(central)
            m_l = QVBoxLayout(central)
            t_l = QHBoxLayout()
            t_l.addWidget(self.value_label)
            t_l.addWidget(self.config_label)
            m_l.addLayout(t_l, 1)
            m_l.addWidget(self._params_tabs, 0)

        def _on_menubar_clicked(self, menu_id: str, act_id: str, checked: bool) -> None:
            """Handle menu-bar actions in the demo.

            Args:
                menu_id: Identifier of the clicked menu.
                act_id: Identifier of the clicked action.
                checked: Checked state associated with the action.
            """

            if act_id == "save_parameters":
                self._on_save()
            elif act_id == "show_scaling_formula":
                self._params_tabs.show_scaling_formula()
            elif act_id == "show_fit_tab":
                self._params_tabs.set_fit_tab_enable(checked)

        def _on_value_changed(self, path: str, value: Any) -> None:
            """Update the value label after a widget value changes.

            Args:
                path: Widget path identifier.
                value: New widget value.
            """

            if isinstance(value, (int | float | bool)):
                self.value_label.setText(f"{path}: {value}")
            else:
                val_text = pretty_json(value)
                self.value_label.setText(f"{path}: {val_text}")

        def _on_config_changed(self, path: str, config: Dict[str, Any]):
            """Update the config label after a widget configuration changes.

            Args:
                path: Widget path identifier.
                config: Updated configuration mapping.
            """

            config_text = pretty_json(config)
            self.config_label.setText(f"{path}: {config_text}")

        def _on_save(self):
            """Save current parameters and configurations to a JSON file."""

            text = pretty_json({
                "params": self._params_tabs.get_value(),
                "configs": self._params_tabs.get_config(),
            })
            Path("parameters.json").write_text(text, encoding="utf-8")
            print("Parameters saved")

    app = QApplication(sys.argv)
    set_app_style(app)

    win = MainWindow()
    win.setWindowTitle("QTabWidget Sliders")
    win.resize(1000, 200)
    set_win_center(win, app)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
