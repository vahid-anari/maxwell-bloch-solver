"""Array-aware slider widget for editing one value from a vector at a time."""

from __future__ import annotations

import math
from typing import Literal, Optional, Sequence

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dialogs.dialogs import AskResult, multi_slider_ask_clamp_value
from ui.params.sliders import EditConfigDialog, FloatSlider, SpecialValue, normalize_special_value


class MultiVariableSlider(FloatSlider):
    """Float slider that exposes one element of an internal value array at a time.

    The widget stores per-index current values, default values, and optional
    special values such as ``+inf`` and ``-inf``. The selected index is shown on
    the base ``FloatSlider`` interface, and updates to the active slider value
    are written back to the corresponding array element.

    Attributes:
        arrayChanged: Emitted when the stored current-value array changes. The
            emitted object is a copy of the internal NumPy array.
    """

    arrayChanged = Signal(object)

    def __init__(
        self,
        label: str,
        html_label: str,
        min_val: float,
        max_val: float,
        init_vals: Sequence[float | str],
        init_idx: int = 0,
        unit: str = "",
        use_same_values: bool = False,
        steps: int = 10000,
        val_fmt: str = "{:.3f}",
        min_limit: float | None = None,
        max_limit: float | None = None,
        min_limit_inclusive: bool = True,
        max_limit_inclusive: bool = True,
        show_range: bool = True,
        orientation: Qt.Orientation = Qt.Horizontal,
        editable: bool = True,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the multi-variable slider.

        Args:
            label: LaTeX-style label shown beside the slider.
            html_label: HTML label used in the values dialog table header.
            min_val: Minimum editable numeric range.
            max_val: Maximum editable numeric range.
            init_vals: Initial per-index values. Entries may be finite numbers or
                special infinity markers.
            init_idx: Initial active index in the stored array.
            unit: Optional unit label shown beside the value.
            use_same_values: If ``True``, changing one entry propagates the same
                value to all entries.
            steps: Integer resolution of the underlying float slider.
            val_fmt: Display format string for finite values.
            min_limit: Optional lower hard limit.
            max_limit: Optional upper hard limit.
            min_limit_inclusive: Whether the lower hard limit is inclusive.
            max_limit_inclusive: Whether the upper hard limit is inclusive.
            show_range: Whether min/max range labels are shown.
            orientation: Slider orientation.
            editable: Whether right-click editing actions are enabled.
            parent: Optional parent widget.

        Raises:
            ValueError: If ``init_vals`` is empty, contains a finite value outside
                the editable range, or contains an infinity marker that conflicts
                with a corresponding hard limit.
        """
        init_vals = list(init_vals)
        if len(init_vals) == 0:
            raise ValueError("init_values must not be empty")

        init_special_arr: list[SpecialValue | None] = []
        finite_init_values: list[float] = []

        for i, v in enumerate(init_vals):
            sv = normalize_special_value(v)
            init_special_arr.append(sv)
            if sv is None:
                fv = float(v)
                if not (min_val <= fv <= max_val):
                    raise ValueError(
                        f"init_values must all lie within [{min_val}, {max_val}], "
                        f"but found value {fv} at index {i}"
                    )
                finite_init_values.append(fv)
            else:
                if sv == "+inf" and max_limit is not None:
                    raise ValueError(f"init_values[{i}] cannot be +inf when max_limit is set")
                if sv == "-inf" and min_limit is not None:
                    raise ValueError(f"init_values[{i}] cannot be -inf when min_limit is set")
                finite_init_values.append(max_val if sv == "+inf" else min_val)

        self._arr_length = len(finite_init_values)
        self._current_idx = init_idx % self._arr_length
        self._current_arr = np.asarray(finite_init_values.copy())
        self._default_arr = np.asarray(finite_init_values.copy())
        self._current_special_arr = init_special_arr.copy()

        init_val = init_special_arr[self._current_idx]
        if init_val is None:
            init_val = finite_init_values[self._current_idx]

        super().__init__(
            label=label,
            unit=unit,
            min_val=min_val,
            max_val=max_val,
            steps=steps,
            init_val=init_val,
            val_fmt=val_fmt,
            min_limit=min_limit,
            max_limit=max_limit,
            min_limit_inclusive=min_limit_inclusive,
            max_limit_inclusive=max_limit_inclusive,
            show_range=show_range,
            orientation=orientation,
            editable=editable,
            parent=parent,
        )

        self.html_label = html_label
        self._use_same_values = False

        self._right_click_items.append({"id": "sep"})
        self._right_click_items.append({"id": "show_val", "text": "Show Values..."})

        self.set_arr_values(self._current_arr)
        self.set_index(self._current_idx)
        self.set_use_same_values(use_same_values)

        self.valueChanged.connect(self._on_single_value_changed)
        self.defaultChanged.connect(self._on_single_default_changed)

    # ----- internal helpers -----
    def _arr_value_text(self, idx: int) -> str:
        """Return the formatted text for the value stored at ``idx``.

        Args:
            idx: Array index to inspect.

        Returns:
            Formatted finite value text, ``"+inf"``, or ``"-inf"``.
        """
        sv = self._current_special_arr[idx]
        if sv == "+inf":
            return "+inf"
        if sv == "-inf":
            return "-inf"
        return self._value_to_text(self._current_arr[idx])

    def _update_slider_for_current_idx(self) -> None:
        """Synchronize the base slider state with the currently selected index."""
        self._current_value = self._current_arr[self._current_idx]
        self._default_value = self._default_arr[self._current_idx]
        self._current_special_value = self._current_special_arr[self._current_idx]

        self._update_mapping_anchors()
        self._apply_range_to_slider()

        self.blockSignals(True)
        try:
            self._slider.setValue(self._value_to_pos(self._current_value))
        finally:
            self.blockSignals(False)

        if self._current_special_value is not None:
            self._enter_special_mode(self._current_special_value)
        else:
            self._exit_special_mode()

        self._update_all_labels()

    def _on_single_value_changed(self, new_value) -> None:
        """Update the stored current-value array after the active value changes.

        Args:
            new_value: New active slider value. May be finite or a special
                infinity marker.
        """
        sv = normalize_special_value(new_value)
        if sv is None:
            finite_value = float(new_value)
            self._current_arr[self._current_idx] = finite_value
            if self._use_same_values:
                self._current_arr[:] = finite_value

        self._current_special_arr[self._current_idx] = sv
        if self._use_same_values:
            self._current_special_arr[:] = [sv] * self._arr_length

        self.arrayChanged.emit(self.get_arr_values())

    def _on_single_default_changed(self, new_value: float) -> None:
        """Update the stored default-value array after the active default changes.

        Args:
            new_value: New default value for the currently selected index.

        Note:
            If same-values mode is enabled, all default entries are replaced with
            ``new_value``.
        """
        self._default_arr[self._current_idx] = new_value
        if self._use_same_values:
            self._default_arr[:] = new_value

    # ----- right click -----
    def _right_click_requested(self, item_id, checked: bool) -> None:
        """Handle a context-menu action.

        Args:
            item_id: Identifier of the selected menu action.
            checked: Checked state associated with the action.
        """
        super()._right_click_requested(item_id, checked)
        if item_id == "show_val":
            self._open_show_values_dlg()

    def _open_edit_config_dlg(self) -> None:
        """Open and apply the configuration dialog for range and display settings.

        On acceptance, this updates the stored format, numeric range, and
        show-range state. If the new range would exclude current or default array
        values, the user is asked whether those values should be clamped.
        """
        dlg = EditConfigDialog(
            slider_name=self._label_text,
            value_is_int=self.value_is_int,
            min_val=self._min_value,
            max_val=self._max_value,
            val_fmt=self._val_fmt,
            show_range=self._show_range,
            min_limit=self._min_limit,
            max_limit=self._max_limit,
            min_limit_inclusive=self._min_limit_inclusive,
            max_limit_inclusive=self._max_limit_inclusive,
        )
        if dlg.exec() == QDialog.Accepted:
            new_min, new_max, new_fmt, new_show_range = dlg.get_values()

            old_fmt = self._val_fmt
            old_show_range = self._show_range
            old_min = self._min_value
            old_max = self._max_value

            self.set_format(new_fmt)
            new_min = self.evaluate_value(new_min)
            new_max = self.evaluate_value(new_max)
            cur_min = np.min(self._current_arr)
            cur_max = np.max(self._current_arr)
            dft_min = np.min(self._default_arr)
            dft_max = np.max(self._default_arr)

            if cur_min < new_min or dft_min < new_min or cur_max > new_max or dft_max > new_max:
                result = multi_slider_ask_clamp_value(
                    proposed_range=f"[{new_min}, {new_max}]",
                    cur_min=self._value_to_text(cur_min),
                    cur_max=self._value_to_text(cur_max),
                    dft_min=self._value_to_text(dft_min),
                    dft_max=self._value_to_text(dft_max),
                    parent=self,
                )
                if result != AskResult.YES:
                    self.set_format(old_fmt)
                    return

            self._show_range = new_show_range
            self.set_range(new_min, new_max)
            if (
                old_min != new_min
                or old_max != new_max
                or old_fmt != new_fmt
                or old_show_range != new_show_range
            ):
                self.configChanged.emit(self.get_config())

    def _values_as_html(self) -> str:
        """Build an HTML table containing all current values.

        Returns:
            HTML string for a two-column table showing index and formatted value.
            The active index is highlighted.
        """
        rows = [
            f"""
            <tr>
                <th style="padding:2px 12px 6px 0; text-align:left; border-bottom:1px solid #999;">Index</th>
                <th style="padding:2px 0 6px 0; text-align:left; border-bottom:1px solid #999;">{self.html_label}</th>
            </tr>
            """
        ]
        for i in range(self._arr_length):
            value_text = self._arr_value_text(i)
            if i == self._current_idx:
                rows.append(
                    f"""
                    <tr style="background-color:#eaf3ff;">
                        <td style="padding:2px 12px 2px 0; white-space:nowrap;" align="right">{i}:</td>
                        <td style="padding:2px 0; white-space:nowrap;"><b>{value_text}</b> <span style="color:#888;">&larr; current</span></td>
                    </tr>
                    """
                )
            else:
                rows.append(
                    f"""
                    <tr>
                        <td style="padding:2px 12px 2px 0; white-space:nowrap;" align="right">{i}:</td>
                        <td style="padding:2px 0; white-space:nowrap;"><b>{value_text}</b></td>
                    </tr>
                    """
                )

        return f"""
        <table cellspacing="0" cellpadding="0">
            {''.join(rows)}
        </table>
        """

    def _open_show_values_dlg(self) -> None:
        """Open a read-only dialog showing the formatted values table."""
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

    # ----- public API -----
    def get_value_text(self, idx: int) -> str:
        """Return the formatted text for the value at a given index.

        Args:
            idx: Array index. Wrapped modulo the current array length.

        Returns:
            Formatted value text.
        """
        idx %= self._arr_length
        return self._arr_value_text(idx)

    def set_format(self, val_fmt: str) -> None:
        """Update the display format and re-evaluate stored values.

        Args:
            val_fmt: New display format string.

        Note:
            All stored current and default finite values are re-evaluated using
            the new format. ``arrayChanged`` is emitted if any current value
            changes as a result.
        """
        super().set_format(val_fmt)
        cur_values_changed = False
        for i in range(self._arr_length):
            old_cur = self._current_arr[i]
            old_dft = self._default_arr[i]
            new_cur = self._current_arr[i] = self.evaluate_value(old_cur)
            new_dft = self._default_arr[i] = self.evaluate_value(old_dft)
            if new_cur != old_cur:
                cur_values_changed = True
        if cur_values_changed:
            self.arrayChanged.emit(self._current_arr.copy())

    def get_index(self) -> int:
        """Return the currently selected array index.

        Returns:
            Current active index.
        """
        return self._current_idx

    def set_index(self, idx: int) -> None:
        """Select the active array index.

        Args:
            idx: New index. Wrapped modulo the current array length.
        """
        idx %= self._arr_length
        self._current_idx = idx
        self._update_slider_for_current_idx()

    def get_arr_values(self) -> np.ndarray:
        """Return a copy of the current array values.

        Returns:
            NumPy array containing finite values or infinities that reflect the
            stored special-value state.
        """
        out = self._current_arr.copy()
        for i, sv in enumerate(self._current_special_arr):
            if sv == "+inf":
                out[i] = math.inf
            elif sv == "-inf":
                out[i] = -math.inf
        return out

    def set_arr_values(
        self,
        values: np.ndarray,
        idx: int = 0,
        default_preserve_mode: Literal["none", "first", "all"] = "none",
        same_values_mode: Literal["ignore", "apply"] = "ignore",
    ) -> None:
        """Replace the stored current values array.

        Args:
            values: New array of values. Must be non-empty, and each entry must
                satisfy the slider's hard-limit constraints.
            idx: Index to select after updating the array. Wrapped modulo the new
                array length.
            default_preserve_mode: Policy for preserving old default values.

                - ``"none"``: Reset all default values from ``values``.
                - ``"first"``: Preserve only the previous default at index 0.
                - ``"all"``: Preserve all previous defaults where possible.
            same_values_mode: Policy controlling interaction with same-values
                mode.

                - ``"ignore"``: Store ``values`` as provided.
                - ``"apply"``: If same-values mode is enabled, force all current
                  and default entries to match the selected entry.

        Note:
            If the new values extend beyond the current editable range, the
            stored minimum and/or maximum range is expanded to include them, and
            ``configChanged`` is emitted.

        Raises:
            ValueError: If ``values`` is empty, contains entries outside the
                allowed hard limits, or if either mode argument is invalid.
        """
        N = len(values)
        if N == 0:
            raise ValueError("values must not be empty")

        for i in range(N):
            if not self.value_in_limit(values[i]):
                raise ValueError(self._range_err_msg(f"value_{i}"))

        if default_preserve_mode not in {"none", "first", "all"}:
            raise ValueError(
                "default_preserve_mode must be one of: 'none', 'first', 'all'"
            )

        if same_values_mode not in {"ignore", "apply"}:
            raise ValueError(
                "same_values_mode must be one of: 'ignore', 'apply'"
            )

        old_default_arr = self._default_arr.copy()
        selected_idx = idx % N

        self._arr_length = N
        new_current = []
        new_special = []

        for i, v in enumerate(values):
            sv = normalize_special_value(v)
            if sv is None:
                fv = self.evaluate_value(v)
                if not self.value_in_limit(fv):
                    raise ValueError(self._range_err_msg(f"value_{i}"))
                new_current.append(fv)
            else:
                if sv == "+inf" and self._max_limit is not None:
                    raise ValueError(self._range_err_msg(f"value_{i}"))
                if sv == "-inf" and self._min_limit is not None:
                    raise ValueError(self._range_err_msg(f"value_{i}"))
                new_current.append(self._max_value if sv == "+inf" else self._min_value)

            new_special.append(sv)

        self._current_arr = np.asarray(new_current, dtype=float)
        self._default_arr = self._current_arr.copy()
        self._current_special_arr = new_special.copy()

        if default_preserve_mode == "first":
            if len(old_default_arr) > 0:
                self._default_arr[0] = old_default_arr[0]
        elif default_preserve_mode == "all":
            n_copy = min(len(old_default_arr), N)
            self._default_arr[:n_copy] = old_default_arr[:n_copy]

        if same_values_mode == "apply" and self._use_same_values:
            self._current_arr[:] = self._current_arr[selected_idx]
            self._default_arr[:] = self._default_arr[selected_idx]

        min_values = np.min(self._current_arr)
        max_values = np.max(self._current_arr)

        min_val = self._min_value
        max_val = self._max_value
        extended = False

        if min_values < min_val:
            min_val = min_values
            extended = True
        if max_values > max_val:
            max_val = max_values
            extended = True

        self._min_value = min_val
        self._max_value = max_val
        self.set_index(selected_idx)

        if extended:
            self.configChanged.emit(self.get_config())

    def set_range(self, min_val: float, max_val: float) -> None:
        """Set the editable numeric range and clamp stored values if needed.

        Args:
            min_val: New minimum value.
            max_val: New maximum value.

        Note:
            Both the current and default arrays are clamped to the new range. The
            underlying slider, labels, and layout are refreshed. ``arrayChanged``
            is emitted if any current value is clamped.

        Raises:
            ValueError: If ``min_val >= max_val`` or either bound violates the
                hard-limit constraints.
        """
        new_min_val, new_max_val = self._validate_range(min_val, max_val)
        self._min_value = new_min_val
        self._max_value = new_max_val
        cur_clamped = False
        for i in range(self._arr_length):
            cur_val = self._current_arr[i]
            dft_val = self._default_arr[i]
            if cur_val < new_min_val:
                self._current_arr[i] = new_min_val
                cur_clamped = True
            elif cur_val > new_max_val:
                self._current_arr[i] = new_max_val
                cur_clamped = True
            if dft_val < new_min_val:
                self._default_arr[i] = new_min_val
            elif dft_val > new_max_val:
                self._default_arr[i] = new_max_val

        self._current_value = self._current_arr[self._current_idx]
        self._default_value = self._default_arr[self._current_idx]

        self._update_mapping_anchors()
        self._apply_range_to_slider()
        self.blockSignals(True)
        try:
            self._slider.setValue(self._value_to_pos(self._current_value))
        finally:
            self.blockSignals(False)
        self._update_all_labels()
        self._update_value_width()
        self._update_layout()

        if cur_clamped:
            self.arrayChanged.emit(self._current_arr.copy())

    def set_use_same_values(self, same: bool) -> None:
        """Enable or disable same-values mode.

        Args:
            same: Whether all entries should track the currently selected value.
        """
        self._use_same_values = same
        if same:
            self._current_arr[:] = self._current_value
            self._default_arr[:] = self._default_value
            self._current_special_arr[:] = [self._current_special_value] * self._arr_length
            self.arrayChanged.emit(self.get_arr_values())

        self._update_slider_for_current_idx()

    def get_arr_length(self) -> int:
        """Return the number of stored values.

        Returns:
            Length of the current/default arrays.
        """
        return self._arr_length

    def set_arr_length(self, arr_length: int) -> None:
        """Resize the stored arrays.

        Args:
            arr_length: New array length. Must be greater than zero.

        Note:
            When extending the arrays, new entries are filled with the value and
            default value from index 0. When shrinking, trailing entries are
            discarded. If the current index becomes invalid after shrinking, it
            is reset to 0.

        Raises:
            ValueError: If ``arr_length <= 0``.
        """
        if arr_length <= 0:
            raise ValueError("arr_length must be > 0")

        old_length = self._arr_length
        if old_length == arr_length:
            return

        if old_length < arr_length:
            fill_cur = self._current_arr[0]
            fill_dft = self._default_arr[0]
            fill_cur_sv = self._current_special_arr[0]

            n_add = arr_length - old_length
            self._current_arr = np.concatenate([
                self._current_arr,
                np.full(n_add, fill_cur, dtype=self._current_arr.dtype),
            ])
            self._default_arr = np.concatenate([
                self._default_arr,
                np.full(n_add, fill_dft, dtype=self._default_arr.dtype),
            ])
            self._current_special_arr.extend([fill_cur_sv] * n_add)
        else:
            self._current_arr = self._current_arr[:arr_length]
            self._default_arr = self._default_arr[:arr_length]
            self._current_special_arr = self._current_special_arr[:arr_length]

        self._arr_length = arr_length
        if self._current_idx >= self._arr_length:
            self._current_idx = 0
        self._update_slider_for_current_idx()
        self.arrayChanged.emit(self._current_arr.copy())


def _demo_main() -> int:
    """Run this module as a standalone demo.

    Returns:
        Qt application exit code.
    """
    import sys

    from PySide6.QtWidgets import QApplication
    from settings.app_style import set_app_style

    app = QApplication(sys.argv)
    set_app_style(app)

    win = QWidget()
    win.setWindowTitle("Multi-Variable Slider Demo")

    def on_values_changed(v):
        """Update the values label in the demo.

        Args:
            v: Current array values.
        """
        val_l.setText(f"Values: {v}")

    def on_config_changed(cfg):
        """Update the config label in the demo.

        Args:
            cfg: Current slider configuration mapping.
        """
        cfg_l.setText(f"Config: {cfg}")

    def on_current_text_changed(t):
        """Change the selected array index from the combo box.

        Args:
            t: Selected combo-box text.
        """
        slider.set_index(int(t))

    def on_same_value():
        """Toggle same-values mode from the checkbox state."""
        slider.set_use_same_values(cb_same.isChecked())

    cb_same = QCheckBox("Same Value")

    N = 5
    cb_l = QLabel("Choose idx:")
    cb = QComboBox()
    cb.addItems([str(i) for i in range(N)])
    cb_layout = QHBoxLayout()
    cb_layout.addWidget(cb_l, 0)
    cb_layout.addWidget(cb, 0)
    cb_layout.addStretch(1)

    val_l = QLabel("Values:")
    cfg_l = QLabel("Config:")

    slider = MultiVariableSlider(
        label="T_{\\alpha}",
        html_label="T<sub>α</sub>",
        min_val=0.0,
        max_val=N,
        init_vals=np.array(range(N)),
        min_limit=0.0,
        min_limit_inclusive=True,
    )

    cb_same.checkStateChanged.connect(on_same_value)
    cb.currentTextChanged.connect(on_current_text_changed)
    slider.arrayChanged.connect(on_values_changed)
    slider.configChanged.connect(on_config_changed)

    layout = QVBoxLayout(win)
    layout.addWidget(cb_same, 0)
    layout.addLayout(cb_layout, 0)
    layout.addWidget(val_l, 0)
    layout.addWidget(cfg_l, 0)
    layout.addWidget(slider, 0)
    layout.addStretch(1)

    win.resize(700, 150)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
