"""Widgets and helpers for editing multi-component hyperbolic-cosine profiles."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from numba import njit
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from settings.app_style import USE_LATEX
from settings.ui_defaults import SLIDER_SHOW_RANGE
from ui.labels import SvgLabel
from ui.params.multi_variable_slider import MultiVariableSlider
from ui.params.parameter_widget_base import ParameterWidgetBase
from ui.params.sliders import FloatSlider
from utils.helper_funcs import make_box


@njit
def cosh_func(
    symmetric: bool,
    x: np.ndarray,
    a: np.ndarray,
    x0: np.ndarray,
    w: np.ndarray,
    wl: np.ndarray,
    wr: np.ndarray,
) -> np.ndarray:
    """Evaluate a sum of hyperbolic-cosine components on the supplied coordinates.

    Args:
        symmetric: Whether each component uses a single shared width.
        x: Coordinates where the profile is evaluated.
        a: Component amplitudes.
        x0: Component center positions.
        w: Symmetric component widths.
        wl: Left-side widths for asymmetric components.
        wr: Right-side widths for asymmetric components.

    Returns:
        Array containing the summed profile values at each coordinate in ``x``.
    """

    n = a.shape[0]
    m = x.shape[0]
    y = np.zeros(m, dtype=np.float64)

    for i in range(n):
        ai = a[i]
        x0i = x0[i]
        wi = w[i]
        wli = wl[i]
        wri = wr[i]

        for j in range(m):
            width = wi if symmetric else wli if x[j] < x0i else wri

            if width == 0.0:
                continue
            elif np.isinf(width):
                y[j] += ai
            else:
                z = (x[j] - x0i) / width
                t = np.tanh(z)
                y[j] += ai * (1.0 - t * t)

    return y


class CoshFunctionWidget(ParameterWidgetBase):
    """Composite widget for editing a sum of hyperbolic-cosine components."""

    def __init__(
        self,
        params_props: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ):
        """Initialize the hyperbolic-cosine function editor widget.

        Args:
            params_props: Mapping that defines slider, checkbox, and formula
                properties used to build the widget.
            parent: Optional parent widget.
        """

        super().__init__(parent)

        self._symmetric = params_props.get("symmetric", True)
        self._arr_length = params_props.get("arr_length", 1)
        self._current_idx = params_props.get("idx", 0)
        self._use_xp = params_props.get("use_period", False)

        self._all_sliders = []
        self._a_slider = self._make_slider(params_props.get("a", {}))
        self._x0_slider = self._make_slider(params_props.get("x0", {}))
        self._w_slider = self._make_slider(params_props.get("w", {}))
        self._wl_slider = self._make_slider(params_props.get("wl", {}))
        self._wr_slider = self._make_slider(params_props.get("wr", {}))
        self._xp_slider = self._make_slider(params_props.get("xp", {}), "FloatSlider")

        self._show_values_pb = QPushButton("Show values")

        self._arr_length_sb = QSpinBox(minimum=1, maximum=100, value=self._arr_length)

        self._current_idx_combo = QComboBox()

        self._all_check_boxes: List[QCheckBox] = []
        self._symmetric_cb = self._make_checkbox({"label": "Symmetric", "checked": self._symmetric})
        self._same_a_cb = self._make_checkbox(params_props.get("same_a", {}))
        self._same_w_cb = self._make_checkbox(params_props.get("same_w", {}))
        self._same_wl_cb = self._make_checkbox(params_props.get("same_wl", {}))
        self._same_wr_cb = self._make_checkbox(params_props.get("same_wr", {}))
        self._use_xp_cb = self._make_checkbox(params_props.get("use_xp", {}))

        self._use_xp_label = SvgLabel(self._make_use_xp_text())

        a = self._a_slider._label_text
        x0 = self._x0_slider._label_text
        f = params_props.get("f", "f")
        x = params_props.get("x", "x")
        if USE_LATEX:
            self._f1 = SvgLabel(
                fr"{f}({x})=\displaystyle\sum_{{i=0}}^{{N-1}}"
                fr"{a}^i\;\mathrm{{sech}}^2\!\left(\frac{{{x}-{x0}^i}}{{w^i}}\right)"
            )
            self._f2 = SvgLabel(
                fr"w^i=\left\lbrace "
                fr"\begin{{array}}{{ll}}"
                fr"w_l^i \quad & {x}<{x0}^i"
                fr"\\ \rule{{0pt}}{{2.8ex}}"
                fr"w_r^i \quad & {x}>{x0}^i"
                fr"\end{{array}}"
                fr"\right."
            )
        else:
            self._f1 = SvgLabel(
                fr"{f}({x})=\sum_{{i=0}}^{{N-1}}"
                fr"{a}^i\;\mathrm{{sech}}^2\!\left(\frac{{{x}-{x0}^i}}{{w^i}}\right)"
            )
            self._f2 = SvgLabel(
                fr"w^i = w_l^i \;\; ({x} < {x0}^i), \quad w_r^i \;\; ({x} > {x0}^i)"
            )
        self._empty = QWidget()

        self._make_connections()

        self._on_arr_length_changed(self._arr_length)
        self._on_use_xp_changed()
        self._set_symmetric(True)
        self._make_layout()

    # ----- internal helpers -----
    def _make_layout(self) -> None:
        """Create and assign the main layout used by this widget."""

        sliders_layout = QVBoxLayout()
        sliders_layout.addStretch(1)
        for slider in self._all_sliders:
            sliders_layout.addWidget(slider, 0)
            sliders_layout.addStretch(1)

        func_layout = QVBoxLayout()
        func_layout.addStretch(1)
        func_layout.addWidget(self._f1, 0)
        func_layout.addWidget(self._empty, 1)
        func_layout.addWidget(self._f2, 0)
        func_layout.addStretch(1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_layout.addWidget(self._show_values_pb)
        btn_layout.addStretch(1)

        gl = QGridLayout()
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setHorizontalSpacing(0)
        gl.addWidget(SvgLabel("N=", alignment=Qt.AlignRight | Qt.AlignVCenter), 0, 0)
        gl.addWidget(self._arr_length_sb, 0, 1)
        gl.addWidget(SvgLabel("i=", alignment=Qt.AlignRight | Qt.AlignVCenter), 1, 0)
        gl.addWidget(self._current_idx_combo, 1, 1)
        gl.setColumnStretch(2, 1)

        option_layout = QVBoxLayout()
        option_layout.addStretch(1)
        option_layout.addWidget(self._symmetric_cb)
        option_layout.addStretch(1)
        option_layout.addLayout(gl)
        option_layout.addStretch(1)
        option_layout.addLayout(btn_layout)
        option_layout.addStretch(1)

        cb_layout = QVBoxLayout()
        cb_layout.addStretch(1)
        cb_layout.addWidget(self._same_a_cb, 0)
        cb_layout.addWidget(self._same_w_cb, 0)
        cb_layout.addWidget(self._same_wl_cb, 0)
        cb_layout.addWidget(self._same_wr_cb, 0)
        cb_layout.addWidget(self._use_xp_cb, 0)
        cb_layout.addWidget(self._use_xp_label, 0)
        cb_layout.addStretch(1)

        sliders_box = make_box(label="", layout=sliders_layout)
        func_box = make_box(label="", layout=func_layout)
        cb_box = make_box(label="", layout=cb_layout)
        option_box = make_box(label="", layout=option_layout)

        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.addWidget(option_box, 0)
        h_layout.addWidget(func_box, 0)
        h_layout.addWidget(sliders_box, 1)
        h_layout.addWidget(cb_box, 0)

        self.setContentsMargins(0, 0, 0, 0)
        self.setLayout(h_layout)
        self._update_sliders_name_width()
        self._update_sliders_value_width()

    def _make_slider(
        self,
        props: Dict[str, Any],
        slider_type: str = "MultiVariableSlider",
    ) -> MultiVariableSlider | FloatSlider:
        """Create one slider used by the widget.

        Args:
            props: Slider property mapping.
            slider_type: Slider class selector.

        Returns:
            Created slider instance.
        """

        if slider_type == "MultiVariableSlider":
            slider = MultiVariableSlider(
                label=props.get("label", "None"),
                unit=props.get("unit", ""),
                html_label=props.get("html_label", "None"),
                min_val=props.get("min_val", 0.01),
                max_val=props.get("max_val", 1.0),
                init_vals=props.get("init_vals", np.array([1.0])),
                val_fmt=props.get("val_fmt", "{:.3S}"),
                min_limit=props.get("min_limit", None),
                min_limit_inclusive=props.get("min_limit_inclusive", True),
                max_limit=props.get("max_limit", None),
                max_limit_inclusive=props.get("max_limit_inclusive", True),
                show_range=props.get("show_range", True) if SLIDER_SHOW_RANGE else False,
            )
        else:
            slider = FloatSlider(
                label=props.get("label", "None"),
                unit=props.get("unit", ""),
                min_val=props.get("min_val", 0.01),
                max_val=props.get("max_val", 1.0),
                init_val=props.get("init_value", 1.0),
                val_fmt=props.get("val_fmt", "{:.3S}"),
                min_limit=props.get("min_limit", None),
                min_limit_inclusive=props.get("min_limit_inclusive", True),
                max_limit=props.get("max_limit", None),
                max_limit_inclusive=props.get("max_limit_inclusive", True),
                show_range=props.get("show_range", True) if SLIDER_SHOW_RANGE else False,
            )
        self._all_sliders.append(slider)
        return slider

    def _make_checkbox(self, props: Dict[str, Any]) -> QCheckBox:
        """Create one checkbox used by the widget.

        Args:
            props: Checkbox property mapping.

        Returns:
            Created checkbox instance.
        """

        cb = QCheckBox(props.get("label", "None"), parent=self)
        cb.setChecked(props.get("checked", False))
        return cb

    def _make_use_xp_text(self) -> str:
        """Build the explanatory text for the periodic offset mode.

        Returns:
            Formatted label text for the ``use_xp`` option.
        """

        x0 = self._x0_slider._label_text
        xp = self._xp_slider._label_text
        return rf"{x0}^i = {x0}^0 + i 	imes {xp}"

    def _make_connections(self):
        """Connect internal signals and slots for sliders and controls."""

        for slider in self._all_sliders:
            slider.nameWidthChanged.connect(self._update_sliders_name_width)
            slider.valueWidthChanged.connect(self._update_sliders_value_width)
            slider.configChanged.connect(lambda: self.configChanged.emit(self.get_config()))
        self._a_slider.arrayChanged.connect(self._on_A_slider_changed)
        self._w_slider.arrayChanged.connect(self._on_w_slider_changed)
        self._wl_slider.arrayChanged.connect(self._on_wl_slider_changed)
        self._wr_slider.arrayChanged.connect(self._on_wr_slider_changed)
        self._x0_slider.arrayChanged.connect(self._on_x0_slider_changed)
        self._xp_slider.valueChanged.connect(self._on_xp_slider_changed)

        self._show_values_pb.clicked.connect(self._on_show_values_clicked)
        self._arr_length_sb.valueChanged.connect(self._on_arr_length_changed)
        self._current_idx_combo.currentIndexChanged.connect(self._on_current_idx_changed)
        self._symmetric_cb.checkStateChanged.connect(self._on_symmetric_changed)
        self._same_a_cb.checkStateChanged.connect(self._on_same_A_changed)
        self._same_w_cb.checkStateChanged.connect(self._on_same_w_changed)
        self._same_wl_cb.checkStateChanged.connect(self._on_same_wl_changed)
        self._same_wr_cb.checkStateChanged.connect(self._on_same_wr_changed)
        self._use_xp_cb.stateChanged.connect(self._on_use_xp_changed)

    def _set_symmetric(self, symmetric: bool):
        """Switch between symmetric and asymmetric width-editing modes.

        Args:
            symmetric: Whether symmetric mode should be enabled.
        """

        self._symmetric = symmetric
        if symmetric:
            wl = self._wl_slider.get_arr_values()
            wr = self._wr_slider.get_arr_values()
            self._w_slider.set_arr_values((wl + wr) / 2.0, idx=self._current_idx)
            s_wl = self._same_wl_cb.isChecked()
            s_wr = self._same_wr_cb.isChecked()
            self._same_w_cb.setChecked(s_wl and s_wr)
            self._same_w_cb.show()
            self._w_slider.show()
            self._f2.hide()
            self._empty.hide()
            self._same_wl_cb.hide()
            self._same_wr_cb.hide()
            self._wl_slider.hide()
            self._wr_slider.hide()
        else:
            w = self._w_slider.get_arr_values()
            self._wl_slider.set_arr_values(w, idx=self._current_idx)
            self._wr_slider.set_arr_values(w, idx=self._current_idx)
            s_w = self._same_w_cb.isChecked()
            self._same_wl_cb.setChecked(s_w)
            self._same_wr_cb.setChecked(s_w)
            self._same_w_cb.hide()
            self._w_slider.hide()
            self._f2.show()
            self._empty.show()
            self._same_wl_cb.show()
            self._same_wr_cb.show()
            self._wl_slider.show()
            self._wr_slider.show()

    def _set_current_idx(self, idx: int) -> None:
        """Set the current component index.

        Args:
            idx: Index to select. Wrapped modulo the current array length.
        """

        self._current_idx = idx % self._arr_length
        self._current_idx_combo.setCurrentIndex(self._current_idx)

    def _set_current_idx_items(self, arr_length: int):
        """Rebuild the current-index combo-box items.

        Args:
            arr_length: Number of available component indices.
        """

        current_idx_combo = self._current_idx_combo
        old_idx = self._current_idx

        current_idx_combo.blockSignals(True)
        try:
            current_idx_combo.clear()
            current_idx_combo.addItems([str(i) for i in range(arr_length)])
        finally:
            current_idx_combo.blockSignals(False)

        if old_idx < arr_length:
            self._set_current_idx(old_idx)
        else:
            self._set_current_idx(0)

    def _set_sliders_arr_length(self, arr_length: int) -> None:
        """Apply a new array length to all array-aware sliders.

        Args:
            arr_length: New shared array length.
        """

        length_changed = False
        for slider in self._all_sliders:
            if hasattr(slider, "get_arr_length"):
                old_arr_length = slider.get_arr_length()
                if old_arr_length != arr_length:
                    length_changed = True
                    self.blockSignals(True)
                    try:
                        slider.set_arr_length(arr_length)
                    finally:
                        self.blockSignals(False)

        if length_changed:
            self.valueChanged.emit(self.get_value())

    def _update_x0_slider_state(self) -> None:
        """Enable or disable the ``x0`` slider based on the current mode."""
        if self._current_idx == 0:
            self._x0_slider.setDisabled(False)
        else:
            self._x0_slider.setDisabled(self._use_xp)

    def _values_as_html(self) -> str:
        """Build an HTML table containing all currently stored values.

        Returns:
            HTML table showing amplitude, center, and width parameters for each
            component, with the active component highlighted.
        """

        text = f"""
                <tr>
                    <th style="padding:2px 12px 6px 0; text-align:left; border-bottom:1px solid #999;">i</th>
                    <th style="padding:2px 12px 6px 0; text-align:left; border-bottom:1px solid #999;">{self._a_slider.html_label}</th>
                    <th style="padding:2px 12px 6px 0; text-align:left; border-bottom:1px solid #999;">{self._x0_slider.html_label}</th>
                """

        if self._symmetric:
            text += f"""
                        <th style="padding:2px 0 6px 0; text-align:left; border-bottom:1px solid #999;">{self._w_slider.html_label}</th>
                    </tr>
                    """
        else:
            text += f"""
                        <th style="padding:2px 12px 6px 0; text-align:left; border-bottom:1px solid #999;">{self._wl_slider.html_label}</th>
                        <th style="padding:2px 0 6px 0; text-align:left; border-bottom:1px solid #999;">{self._wr_slider.html_label}</th>
                    </tr>
                    """
        rows = [text]

        for i in range(self._arr_length):
            A = self._a_slider.get_value_text(i)
            x0 = self._x0_slider.get_value_text(i)
            w = self._w_slider.get_value_text(i)
            wl = self._wl_slider.get_value_text(i)
            wr = self._wr_slider.get_value_text(i)

            row_style = ' style="background-color:#eaf3ff;"' if i == self._current_idx else ""
            current_text = ' <span style="color:#888;">&larr; current</span>' if i == self._current_idx else ""

            text = f"""
                <tr{row_style}>
                    <td style="padding:2px 12px 2px 0; white-space:nowrap;" align="left">{i}:</td>
                    <td style="padding:2px 12px 2px 0; white-space:nowrap;"><b>{A}</b></td>
                    <td style="padding:2px 12px 2px 0; white-space:nowrap;"><b>{x0}</b></td>
                    """
            if self._symmetric:
                text += f"""

                            <td style="padding:2px 0 2px 0; white-space:nowrap;"><b>{w}</b>{current_text}</td>
                        </tr>
                        """
            else:
                text += f"""
                            <td style="padding:2px 12px 2px 0; white-space:nowrap;"><b>{wl}</b></td>
                            <td style="padding:2px 0 2px 0; white-space:nowrap;"><b>{wr}</b>{current_text}</td>
                        </tr>
                        """

            rows.append(text)

        return f"""
        <table cellspacing="0" cellpadding="0">
            {''.join(rows)}
        </table>
        """

    # ----- update slider width -----
    def _update_sliders_name_width(self) -> None:
        """Synchronize all slider name widths to the widest slider label."""
        name_w = 0
        for slider in self._all_sliders:
            name_w = max(name_w, slider.get_name_width())
        for slider in self._all_sliders:
            slider.set_name_width(name_w)

    def _update_sliders_value_width(self) -> None:
        """Synchronize all slider value widths to the widest value display."""
        val_w = 0
        for slider in self._all_sliders:
            val_w = max(val_w, slider.get_value_width())
        for slider in self._all_sliders:
            slider.set_value_width(val_w)

    # ----- sliders signal -----
    def _on_A_slider_changed(self) -> None:
        """Handle changes to the amplitude slider array."""
        self.valueChanged.emit(self.get_value())

    def _on_x0_slider_changed(self) -> None:
        """Handle changes to the center-position slider array."""
        if self._use_xp:
            self._on_xp_slider_changed(self._xp_slider.get_value())
        self.valueChanged.emit(self.get_value())

    def _on_w_slider_changed(self) -> None:
        """Handle changes to the symmetric-width slider array."""
        self.valueChanged.emit(self.get_value())

    def _on_wl_slider_changed(self) -> None:
        """Handle changes to the left-width slider array."""
        self.valueChanged.emit(self.get_value())

    def _on_wr_slider_changed(self) -> None:
        """Handle changes to the right-width slider array."""
        self.valueChanged.emit(self.get_value())

    def _on_xp_slider_changed(self, value: float) -> None:
        """Update center positions using the periodic spacing slider.

        Args:
            value: Spacing between successive component centers.
        """

        x00 = self._x0_slider.get_arr_values()[0]
        new_x0 = np.asarray([x00 + i * value for i in range(self._arr_length)])
        self._x0_slider.set_arr_values(new_x0, idx=self._current_idx, default_preserve_mode="first")
        self.valueChanged.emit(self.get_value())

    # ----- options signal -----
    def _on_symmetric_changed(self):
        """Handle toggling between symmetric and asymmetric width modes."""
        self._set_symmetric(self._symmetric_cb.isChecked())
        self.valueChanged.emit(self.get_value())

    def _on_show_values_clicked(self) -> None:
        """Open a read-only dialog showing all current component values."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Values")

        text_box = QTextEdit(dlg)
        text_box.setReadOnly(True)
        text_box.setAcceptRichText(True)

        html = self._values_as_html()
        text_box.setHtml(html)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok, parent=dlg)
        btn_box.accepted.connect(dlg.accept)

        layout = QVBoxLayout(dlg)
        layout.addWidget(text_box)
        layout.addWidget(btn_box)

        doc = text_box.document()
        doc.adjustSize()

        doc_w = int(doc.idealWidth())
        frame_w = 2 * text_box.frameWidth()
        margins = text_box.contentsMargins().left() + text_box.contentsMargins().right()
        scrollbar_w = text_box.style().pixelMetric(QStyle.PM_ScrollBarExtent)

        dlg_w = doc_w + frame_w + margins + scrollbar_w + 30
        dlg_h = min(700, 140 + 22 * self._arr_length)

        dlg.resize(dlg_w, dlg_h)
        dlg.exec()

    def _on_arr_length_changed(self, arr_length: int) -> None:
        """Handle changes to the number of components.

        Args:
            arr_length: New number of components.
        """

        self._arr_length = arr_length
        self._set_current_idx_items(arr_length)
        self._set_sliders_arr_length(arr_length)

    def _on_current_idx_changed(self, idx: int) -> None:
        """Handle changes to the currently selected component index.

        Args:
            idx: New selected index.
        """

        self._current_idx = idx
        self._update_x0_slider_state()
        for slider in self._all_sliders:
            if hasattr(slider, "set_index"):
                slider.set_index(idx)
        self.valueChanged.emit(self.get_value())

    def _on_same_A_changed(self) -> None:
        """Handle toggling same-value mode for amplitudes."""
        checked = self._same_a_cb.isChecked()
        self._a_slider.set_use_same_values(checked)
        self.valueChanged.emit(self.get_value())

    def _on_same_w_changed(self) -> None:
        """Handle toggling same-value mode for symmetric widths."""
        checked = self._same_w_cb.isChecked()
        self._w_slider.set_use_same_values(checked)
        self.valueChanged.emit(self.get_value())

    def _on_same_wl_changed(self) -> None:
        """Handle toggling same-value mode for left widths."""
        checked = self._same_wl_cb.isChecked()
        self._wl_slider.set_use_same_values(checked)
        self.valueChanged.emit(self.get_value())

    def _on_same_wr_changed(self) -> None:
        """Handle toggling same-value mode for right widths."""
        checked = self._same_wr_cb.isChecked()
        self._wr_slider.set_use_same_values(checked)
        self.valueChanged.emit(self.get_value())

    def _on_use_xp_changed(self) -> None:
        """Handle enabling or disabling the periodic-spacing mode."""
        checked = self._use_xp_cb.isChecked()
        self._use_xp = checked
        self._update_x0_slider_state()
        self._xp_slider.setDisabled(not checked)
        self._use_xp_label.setDisabled(not checked)
        if checked:
            self._on_xp_slider_changed(self._xp_slider.get_value())
            self._xp_slider.show()
        else:
            self.valueChanged.emit(self.get_value())
        self.valueChanged.emit(self.get_value())

    # ----- public API -----
    def get_peak_position(self) -> Tuple[float, float, float]:
        """Return the active peak position and half-width information.

        Returns:
            Tuple of ``(x0, wl, wr)`` for the currently selected component.
        """

        cur_idx = self._current_idx
        x0 = self._x0_slider.get_arr_values()[cur_idx]
        a = self._a_slider.get_arr_values()[cur_idx]
        if a == 0:
            wl = wr = 0
        else:
            if self._symmetric:
                w = self._w_slider.get_arr_values()[cur_idx]
                wl = wr = w / 2.0
            else:
                wl = self._wl_slider.get_arr_values()[cur_idx]
                wr = self._wr_slider.get_arr_values()[cur_idx]

        return x0, wl, wr

    def get_value(self) -> Dict[str, Any]:
        """Return the current parameter values and option states.

        Returns:
            Mapping containing the current arrays, scalar spacing value, array
            length, selected index, and checkbox states.
        """

        return {
            "a": self._a_slider.get_arr_values(),
            "x0": self._x0_slider.get_arr_values(),
            "w": self._w_slider.get_arr_values(),
            "wl": self._wl_slider.get_arr_values(),
            "wr": self._wr_slider.get_arr_values(),
            "xp": self._xp_slider.get_value(),
            "arr_length": self._arr_length,
            "current_idx": self._current_idx,
            "symmetric": self._symmetric_cb.isChecked(),
            "same_a": self._same_a_cb.isChecked(),
            "same_w": self._same_w_cb.isChecked(),
            "same_wl": self._same_wl_cb.isChecked(),
            "same_wr": self._same_wr_cb.isChecked(),
            "use_xp": self._use_xp,
        }

    def _validate_value(self, values: dict[str, Any]) -> dict[str, Any]:
        """Validate a value mapping before applying it.

        Args:
            values: Proposed widget value mapping.

        Returns:
            Completed value mapping with missing keys filled from the current state.

        Raises:
            TypeError: If ``values`` is not a dictionary.
        """

        if not isinstance(values, dict):
            raise TypeError(f"value must be dict, got {type(values).__name__}")
        old_values = self.get_value()
        new_values = {}
        for k, v in old_values.items():
            if k not in values:
                new_values[k] = v
            else:
                new_values[k] = values[k]
        return new_values

    def _apply_value(self, values: Dict[str, Any]) -> None:
        """Apply a validated value mapping to the widget state.

        Args:
            values: Validated value mapping.
        """

        self.blockSignals(True)
        try:
            self._a_slider.set_arr_values(values["a"])
            self._x0_slider.set_arr_values(values["x0"])
            self._w_slider.set_arr_values(values["w"])
            self._wl_slider.set_arr_values(values["wl"])
            self._wr_slider.set_arr_values(values["wr"])
            self._xp_slider.set_value(values["xp"])
            self._arr_length_sb.setValue(values["arr_length"])
            self._set_current_idx(values["current_idx"])
            self._symmetric_cb.setChecked(values["symmetric"])
            self._same_a_cb.setChecked(values["same_a"])
            self._same_w_cb.setChecked(values["same_w"])
            self._same_wl_cb.setChecked(values["same_wl"])
            self._same_wr_cb.setChecked(values["same_wr"])
            self._use_xp_cb.setChecked(values["use_xp"])
        finally:
            self.blockSignals(False)

    def get_config(self) -> dict:
        """Return the current configuration mapping.

        Returns:
            Mapping containing slider configuration dictionaries for the editable
            parameter controls.
        """

        return {
            "a": self._a_slider.get_config(),
            "x0": self._x0_slider.get_config(),
            "wl": self._wl_slider.get_config(),
            "wr": self._wr_slider.get_config(),
            "xp": self._xp_slider.get_config(),
        }

    def _apply_config(self, config: dict) -> None:
        """Apply a validated configuration mapping.

        Args:
            config: Configuration mapping to apply.
        """

        self._a_slider.set_config(config["a"])
        self._x0_slider.set_config(config["x0"])
        self._wl_slider.set_config(config["wl"])
        self._wr_slider.set_config(config["wr"])
        self._xp_slider.set_config(config["xp"])


def _demo_main() -> int:
    """Run this module as a standalone demo.

    Returns:
        Qt application exit code.
    """

    import sys

    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from PySide6.QtWidgets import QApplication
    from settings.app_style import set_app_style

    app = QApplication(sys.argv)
    set_app_style(app)

    win = QWidget()
    win.setWindowTitle("Peak Functions Demo")

    N = 5
    params_props = {
        "f": r"\Lambda_n",
        "x": r"\tau",
        "a": {
            "label": r"\Lambda",
            "html_label": "Λ",
            "min_val": -10.0,
            "max_val": 10.0,
            "init_values": np.ones(N),
        },
        "x0": {
            "label": r"\tau_0",
            "html_label": "τ<sub>0</sub>",
            "min_val": 0.0,
            "max_val": 10.0,
            "init_values": np.linspace(1.0, 9.0, N),
        },
        "w": {
            "label": "w",
            "html_label": "w",
            "min_val": 0.0,
            "max_val": 10.0,
            "init_values": np.ones(N),
        },
        "wl": {
            "label": "w_l",
            "html_label": "w<sub>l</sub>",
            "min_val": 0.0,
            "max_val": 10.0,
            "init_values": np.ones(N),
        },
        "wr": {
            "label": "w_r",
            "html_label": "w<sub>r</sub>",
            "min_val": 0.0,
            "max_val": 10.0,
            "init_values": np.ones(N),
        },
        "xp": {
            "label": r"\tau_p",
            "html_label": "τ<sub>p</sub>",
            "min_val": 0.01,
            "max_val": 10.0,
            "init_values": 1.0,
            "min_limit": 0.0,
            "min_limit_inclusive": False,
        },
        "symmetric": True,
        "arr_length": 5,
        "current_idx": 0,
        "same_a": {
            "label": "Use Same Λ",
            "checked": False,
        },
        "same_w": {
            "label": "Use Same w",
            "checked": False,
        },
        "same_wl": {
            "label": "Use Same wₗ",
            "checked": False,
        },
        "same_wr": {
            "label": "Use Same wᵣ",
            "checked": False,
        },
        "use_xp": {
            "label": "Use τₚ",
            "checked": False,
        },
    }

    pf = CoshFunctionWidget(params_props=params_props, parent=win)

    x = np.linspace(-2.0, 120.0, 15000)
    y = x * 0.0

    fig = Figure(figsize=(7, 4))
    fig.subplots_adjust(left=0.1, right=0.9, top=0.95, bottom=0.12)
    canvas = FigureCanvas(fig)
    ax = fig.add_subplot(111)
    line, = ax.plot(x, y)
    vspan = ax.axvspan(0.0, 0.0, alpha=0.2)

    ax.set_xlabel(r"$\tau$", usetex=True, fontsize=16)
    ax.set_ylabel(r"$f(\tau)$", usetex=True, fontsize=16)
    ax.grid(True, alpha=0.3)

    def redraw_line(params_values) -> None:
        """Redraw the model line using the current widget parameters.

        Args:
            params_values: Current parameter mapping returned by the widget.
        """
        new_y = cosh_func(
            symmetric=params_values["symmetric"],
            x=x,
            a=np.asarray(params_values["a"], dtype=float),
            x0=np.asarray(params_values["x0"], dtype=float),
            wl=np.asarray(params_values["wl"], dtype=float),
            w=np.asarray(params_values["w"], dtype=float),
            wr=np.asarray(params_values["wr"], dtype=float),
        )
        line.set_ydata(new_y)
        dy = new_y.max() - new_y.min()
        if dy == 0.0:
            dy = 1.0
        ax.set_ylim(new_y.min() - 0.1 * dy, new_y.max() + 0.1 * dy)
        canvas.draw_idle()

    def redraw_vspan(x0, wl, wr) -> None:
        """Redraw the highlighted span around the active peak.

        Args:
            x0: Peak center.
            wl: Left half-width.
            wr: Right half-width.
        """
        if math.isinf(wl):
            wl = 0.1
        if math.isinf(wr):
            wr = 0.1
        wl = max(wl, 0.1)
        wr = max(wr, 0.1)
        vspan.set_x(x0 - wl)
        vspan.set_width(wl + wr)

    def on_value_changed(values: dict) -> None:
        """Handle changes to the widget value mapping.

        Args:
            values: Current parameter mapping.
        """
        redraw_vspan(*pf.get_peak_position())
        redraw_line(pf.get_value())

    pf.valueChanged.connect(on_value_changed)

    layout = QVBoxLayout(win)
    layout.addWidget(canvas, 1)
    layout.addWidget(pf, 0)

    redraw_line(pf.get_value())
    redraw_vspan(*pf.get_peak_position())

    win.resize(1200, 900)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
