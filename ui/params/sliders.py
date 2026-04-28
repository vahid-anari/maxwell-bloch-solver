"""Reusable slider widgets for numeric and discrete parameter controls."""

from __future__ import annotations

import math
import re
from typing import Any, Callable, Dict, Generic, List, Literal, Optional, Tuple, TypeVar

import numpy as np
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPalette, QPen, QShowEvent, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

from dialogs.dialogs import AskResult, show_warning, slider_ask_clamp_value, slider_ask_extend_range
from settings.app_style import SLIDER_BORDER_STYLE_SHEET, SliderBorderState
from settings.ui_defaults import SLIDER_LABEL_SIZE, UNIT_LABEL_SIZE
from ui.labels import SvgLabel
from ui.numeric_line_edit import NumericLineEdit
from ui.params.parameter_widget_base import ParameterWidgetBase
from ui.right_click_overlay import RightClickOverlay
from utils.helper_funcs import get_numeric_format_field, pretty_sci_text, value_to_text

SpecialValue = Literal["+inf", "-inf"]
TNum = TypeVar("TNum", int, float)


def _map_val_to_pos(v: float, v_min: float, v_max: float, p_min: int, p_max: int) -> int:
    """Map a value linearly onto an integer slider position.

    Args:
        v: Numeric value to map.
        v_min: Minimum numeric value of the source interval.
        v_max: Maximum numeric value of the source interval.
        p_min: Minimum integer position of the destination interval.
        p_max: Maximum integer position of the destination interval.

    Returns:
        Rounded integer slider position.

    Note:
        If ``v_min == v_max``, the mapping is degenerate and ``p_min`` is
        returned.
    """
    if v_max == v_min:
        return p_min
    t = (v - v_min) / (v_max - v_min)
    return int(round(p_min + t * (p_max - p_min)))


def _map_pos_to_val(p: int, p_min: int, p_max: int, v_min: float, v_max: float) -> float:
    """Map an integer slider position linearly onto a numeric value.

    Args:
        p: Integer position to map.
        p_min: Minimum integer position of the source interval.
        p_max: Maximum integer position of the source interval.
        v_min: Minimum numeric value of the destination interval.
        v_max: Maximum numeric value of the destination interval.

    Returns:
        Interpolated numeric value.

    Note:
        If ``p_min == p_max``, the mapping is degenerate and ``v_min`` is
        returned.
    """
    if p_max == p_min:
        return v_min
    t = (p - p_min) / (p_max - p_min)
    return v_min + t * (v_max - v_min)


def make_line_edit(
    value_is_int: bool,
    init_value: TNum,
    fmt: str,
    min_limit: TNum,
    max_limit: TNum,
    min_limit_inclusive: bool,
    max_limit_inclusive: bool,
) -> NumericLineEdit:
    """Create a numeric line edit configured for a slider-editing dialog.

    Args:
        value_is_int: Whether the editor should parse integer values.
        init_value: Initial value shown in the editor.
        fmt: Display format string associated with the slider.
        min_limit: Lower allowed limit.
        max_limit: Upper allowed limit.
        min_limit_inclusive: Whether the lower limit is inclusive.
        max_limit_inclusive: Whether the upper limit is inclusive.

    Returns:
        Configured numeric line edit widget.
    """
    val_fmt = get_numeric_format_field(fmt)
    return NumericLineEdit(
        init_val=init_value,
        value_is_int=value_is_int,
        val_fmt=val_fmt,
        min_limit=min_limit,
        max_limit=max_limit,
        min_limit_inclusive=min_limit_inclusive,
        max_limit_inclusive=max_limit_inclusive,
    )


def normalize_special_value(value: Any) -> SpecialValue | None:
    """Normalize special infinite values to a canonical string representation.

    Args:
        value: Candidate value supplied by the caller.

    Returns:
        ``"+inf"`` or ``"-inf"`` when the input represents positive or negative
        infinity, otherwise ``None``.
    """
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"inf", "+inf", "infinity", "+infinity"}:
            return "+inf"
        if s in {"-inf", "-infinity"}:
            return "-inf"

    if isinstance(value, (int, float)) and math.isinf(value):
        return "+inf" if value > 0 else "-inf"

    return None


class MarkerOverlay(QWidget):
    """Draw a marker aligned to a slider groove.

    The overlay is parented to a slider and paints a single line at the logical
    slider position returned by ``value_fn``. It is typically used to visualize
    a stored default value.
    """

    def __init__(
        self,
        slider: QSlider,
        value_fn: Callable[[], int],
        *,
        thickness: int = 2,
        color: QColor | str = Qt.red,
    ):
        """Initialize the marker overlay.

        Args:
            slider: Slider that owns the overlay.
            value_fn: Callable returning the logical slider position to mark.
            thickness: Marker line thickness in pixels.
            color: Marker color.
        """
        super().__init__(slider)
        self._slider = slider
        self._value_fn = value_fn
        self._thickness = thickness
        self._color = QColor(color)

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        slider.installEventFilter(self)
        self._sync_geometry()
        self.show()

    def _current_color(self) -> QColor:
        """Return the effective marker color for the current enabled state.

        Returns:
            Marker color, possibly dimmed when the slider is disabled.
        """
        c = QColor(self._color)
        if not self._slider.isEnabled():
            ref = self.palette().color(QPalette.Disabled, QPalette.WindowText)
            c.setAlphaF(ref.alphaF())
        return c

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        """Keep the overlay synchronized with slider state changes.

        Args:
            obj: Watched object.
            ev: Event delivered to the watched object.

        Returns:
            Result of the base-class event filter.
        """
        if obj is self._slider and ev.type() in (
            QEvent.Resize,
            QEvent.Show,
            QEvent.Hide,
            QEvent.EnabledChange,
        ):
            self._sync_geometry()
            self.update()
        return super().eventFilter(obj, ev)

    def _sync_geometry(self) -> None:
        """Match the overlay geometry and visibility to the slider."""
        self.setGeometry(self._slider.rect())
        self.setVisible(self._slider.isVisible())

    def paintEvent(self, _ev) -> None:
        """Paint the marker line at the current logical slider position.

        Args:
            _ev: Paint event supplied by Qt.
        """
        opt = QStyleOptionSlider()
        self._slider.initStyleOption(opt)

        style = self._slider.style()
        groove = style.subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self._slider)
        handle = style.subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self._slider)
        if groove.isNull() or handle.isNull():
            return

        vmin, vmax = opt.minimum, opt.maximum
        if vmin == vmax:
            return

        v = int(self._value_fn())
        v = max(vmin, min(vmax, v))

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)

        pen = QPen(self._current_color())
        pen.setWidth(self._thickness)
        p.setPen(pen)

        if opt.orientation == Qt.Horizontal:
            span = max(0, groove.width() - handle.width())
            dx = QStyle.sliderPositionFromValue(vmin, vmax, v, span, opt.upsideDown)
            x = groove.x() + dx + handle.width() // 2
            p.drawLine(x, groove.top(), x, groove.bottom())
        else:
            span = max(0, groove.height() - handle.height())
            dy = QStyle.sliderPositionFromValue(vmin, vmax, v, span, opt.upsideDown)
            y = groove.y() + dy + handle.height() // 2
            p.drawLine(groove.left(), y, groove.right(), y)

        p.end()


class EditConfigDialog(QDialog, Generic[TNum]):
    """Dialog for editing slider range, format, and range-label visibility."""

    def __init__(
        self,
        slider_name: str,
        value_is_int: bool,
        min_val: TNum,
        max_val: TNum,
        val_fmt: str,
        min_limit: TNum | None,
        max_limit: TNum | None,
        min_limit_inclusive: bool,
        max_limit_inclusive: bool,
        show_range: bool = True,
        show_range_enabled: bool = True,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the configuration-editing dialog.

        Args:
            slider_name: Display name of the slider.
            value_is_int: Whether the slider uses integer values.
            min_val: Current minimum value.
            max_val: Current maximum value.
            val_fmt: Current display format string.
            min_limit: Optional lower hard limit.
            max_limit: Optional upper hard limit.
            min_limit_inclusive: Whether the lower hard limit is inclusive.
            max_limit_inclusive: Whether the upper hard limit is inclusive.
            show_range: Initial state of the range-label checkbox.
            show_range_enabled: Whether the range-label checkbox is editable.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Edit Configuration")

        self._show_range = show_range
        self._show_range_enabled = show_range_enabled
        self._value_is_int = value_is_int
        self._edit_min = make_line_edit(
            value_is_int, min_val, val_fmt, min_limit, max_limit, min_limit_inclusive, max_limit_inclusive
        )
        self._edit_max = make_line_edit(
            value_is_int, max_val, val_fmt, min_limit, max_limit, min_limit_inclusive, max_limit_inclusive
        )
        self._edit_fmt = QLineEdit(val_fmt)
        self._cb_ticks = QCheckBox("Show Range", self)
        self._cb_ticks.setChecked(show_range)
        self._cb_ticks.setEnabled(show_range_enabled)

        self._edit_fmt.editingFinished.connect(self._fmt_changed)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.addRow(
            "Int Slider:" if value_is_int else "Float Slider:",
            SvgLabel(slider_name, alignment=Qt.AlignLeft | Qt.AlignVCenter),
        )
        form.addRow(self._cb_ticks)
        form.addRow("Min:", self._edit_min)
        form.addRow("Max:", self._edit_max)
        form.addRow("Format:", self._edit_fmt)
        form.addRow(buttons)

        self.setSizeGripEnabled(False)
        self.adjustSize()
        self.setFixedSize(self.size())

    def _fmt_changed(self) -> None:
        """Update numeric editor formats after the format field changes."""
        fmt = get_numeric_format_field(self._edit_fmt.text())
        self._edit_min.set_fmt(fmt)
        self._edit_max.set_fmt(fmt)

    def accept(self):
        """Validate the dialog state before accepting it."""
        val_min = self._edit_min.get_value()
        val_max = self._edit_max.get_value()

        if val_max < val_min:
            show_warning("Invalid range", "Min must be less than max.", parent=self)
            return

        super().accept()

    def get_values(self) -> Tuple[TNum, TNum, str, bool]:
        """Return the validated dialog values.

        Returns:
            Tuple containing minimum value, maximum value, format string, and
            range-visibility flag.
        """
        return (
            self._edit_min.get_value(),
            self._edit_max.get_value(),
            self._edit_fmt.text(),
            self._cb_ticks.isChecked(),
        )

    def showEvent(self, event: QShowEvent) -> None:
        """Focus the minimum-value editor when the dialog is shown.

        Args:
            event: Qt show event.
        """
        super().showEvent(event)
        self._edit_min.setFocus()
        self._edit_min.selectAll()


class SetValueDialog(QDialog, Generic[TNum]):
    """Dialog for entering a new slider value."""

    def __init__(
        self,
        slider_name: str,
        value_is_int: bool,
        current_value: TNum,
        val_fmt: str,
        min_limit: TNum | None,
        max_limit: TNum | None,
        min_limit_inclusive: bool,
        max_limit_inclusive: bool,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the value-entry dialog.

        Args:
            slider_name: Display name of the slider.
            value_is_int: Whether the slider uses integer values.
            current_value: Current value shown in the editor.
            val_fmt: Current display format string.
            min_limit: Optional lower hard limit.
            max_limit: Optional upper hard limit.
            min_limit_inclusive: Whether the lower hard limit is inclusive.
            max_limit_inclusive: Whether the upper hard limit is inclusive.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Set Value")

        self._edit_value = make_line_edit(
            value_is_int,
            current_value,
            val_fmt,
            min_limit,
            max_limit,
            min_limit_inclusive,
            max_limit_inclusive,
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.addRow(
            "Int Slider:" if value_is_int else "Float Slider:",
            SvgLabel(slider_name, alignment=Qt.AlignLeft | Qt.AlignVCenter),
        )
        form.addRow("Value:", self._edit_value)
        form.addRow(buttons)

        self.setSizeGripEnabled(False)
        self.adjustSize()
        self.setFixedSize(self.size())

    def accept(self) -> None:
        """Validate the edited value and accept the dialog."""
        if not self._edit_value.hasAcceptableInput():
            self._edit_value._reject_exit_ui()
        super().accept()

    def get_values(self) -> TNum:
        """Return the validated slider value.

        Returns:
            Value entered in the numeric line edit.
        """
        return self._edit_value.get_value()

    def showEvent(self, event: QShowEvent) -> None:
        """Focus the value editor when the dialog is shown.

        Args:
            event: Qt show event.
        """
        super().showEvent(event)
        self._edit_value.setFocus()
        self._edit_value.selectAll()


class LabeledSliderBase(ParameterWidgetBase[TNum], Generic[TNum]):
    """Base widget combining a label, slider, value label, and optional range labels."""

    def __init__(
        self,
        label: str,
        unit: str,
        min_val: TNum,
        max_val: TNum,
        init_val: TNum,
        orientation: Qt.Orientation,
        val_fmt: str,
        show_range: bool,
        parent: Optional[QWidget],
    ):
        """Initialize the labeled slider base widget.

        Args:
            label: Slider label shown next to the control.
            unit: Optional unit label displayed beside the value.
            min_val: Initial minimum value.
            max_val: Initial maximum value.
            init_val: Initial current value.
            orientation: Slider orientation.
            val_fmt: Value display format string.
            show_range: Whether to show range labels and ticks.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self.setObjectName("labeled_slider")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(SLIDER_BORDER_STYLE_SHEET)
        self.set_border(SliderBorderState.OFF)

        self._label_text = label
        self._unit = unit
        self._min_value = min_val
        self._max_value = max_val
        self._current_value = init_val
        self._default_value = init_val
        self._orient = orientation
        self._show_range = show_range
        self._val_fmt = val_fmt
        self._eval_fmt = ""
        self._use_sci_html = False
        self._right_click_enable = True

        self._name_label = SvgLabel(label, parent=self, font_size=SLIDER_LABEL_SIZE)
        self._value_label = QLabel()

        w = QWidget()
        l = QHBoxLayout(w)
        l.addWidget(self._value_label)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)
        if unit:
            self._unit_label = SvgLabel(f"({unit})", parent=self, fix_size=True, font_size=UNIT_LABEL_SIZE)
            l.addWidget(self._unit_label)
        l.addStretch(1)
        self._value_and_unit = w
        self._min_label = QLabel()
        self._max_label = QLabel()
        self._value_label.setObjectName("slider_value")
        self._min_label.setObjectName("slider_range")
        self._max_label.setObjectName("slider_range")
        self._slider = QSlider(self._orient)

        self._right_click_overlay = RightClickOverlay(
            target_widget=self._slider,
            owner_widget=self,
            parent=self._slider.parentWidget() if self._slider.parentWidget() is not None else self,
        )
        self._right_click_overlay.hide()

        self._default_red_marker = MarkerOverlay(self._slider, value_fn=self._get_default_pos, thickness=2)

        self._right_click_items: List[Dict[str, Any]] = [
            {"id": "save_as_default", "text": "Save as Default"},
            {"id": "reset_to_default", "text": "Reset to Default"},
        ]

        self._name_width = self._name_label.sizeHint().width()
        self._value_width = 0

        self.set_format(val_fmt)
        self._make_layout()

    def _make_layout(self):
        """Build the internal grid layout for the current orientation."""
        gl = QGridLayout(self)
        gl.setContentsMargins(0, 0, 0, 0)

        slider_wrap = QWidget()
        sl = QVBoxLayout(slider_wrap)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        sl.addWidget(self._slider)

        if self._orient == Qt.Horizontal:
            gl.setVerticalSpacing(0)
            common = Qt.AlignVCenter
            self._name_label.setAlignment(common | Qt.AlignRight)
            self._value_label.setAlignment(common | Qt.AlignRight)
            gl.addWidget(self._name_label, 0, 0, common | Qt.AlignRight)
            gl.addWidget(slider_wrap, 0, 1, 1, 3, common)
            gl.addWidget(self._value_and_unit, 0, 4, common | Qt.AlignLeft)
            gl.addWidget(self._min_label, 1, 1)
            gl.addWidget(self._max_label, 1, 3)

            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            gl.setColumnStretch(2, 1)
        else:
            gl.setHorizontalSpacing(0)
            gl.setVerticalSpacing(2)
            common = Qt.AlignHCenter
            self._value_label.setAlignment(Qt.AlignCenter)
            self._name_label.setAlignment(common | Qt.AlignTop)

            self._max_label.setContentsMargins(5, 0, 0, 0)
            self._min_label.setContentsMargins(5, 0, 0, 1)

            gl.addWidget(self._value_and_unit, 0, 0, 1, 3, common | Qt.AlignBottom)
            gl.addWidget(slider_wrap, 1, 1, 3, 1, common)
            gl.addWidget(self._name_label, 4, 0, 1, 3, common | Qt.AlignTop)
            gl.addWidget(self._max_label, 1, 2, 1, 2)
            gl.addWidget(self._min_label, 3, 2, 1, 2)

            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
            gl.setRowStretch(2, 1)

        self._gl = gl
        self._sl = sl
        self._right_click_overlay.sync_to_target()

    def evaluate_value(self, value: TNum) -> TNum:
        """Normalize a numeric value using the current evaluation format.

        Args:
            value: Value to normalize.

        Returns:
            Normalized typed value.
        """
        raise NotImplementedError

    def _pos_to_value(self, pos: int) -> TNum:
        """Convert a slider position to a typed value.

        Args:
            pos: Integer slider position.

        Returns:
            Typed slider value.
        """
        raise NotImplementedError

    def _value_to_text(self, value: TNum) -> str:
        """Format a typed value for display.

        Args:
            value: Value to format.

        Returns:
            Formatted display string.
        """
        return value_to_text(value=value, fmt=self._val_fmt)

    def _get_default_pos(self) -> int:
        """Return the default marker position in slider coordinates.

        Returns:
            Integer slider position for the default value.
        """
        raise NotImplementedError

    def _update_eval_fmt(self) -> None:
        """Build a safe numeric format used for internal value normalization."""
        self._eval_fmt = get_numeric_format_field(self._val_fmt)

    def _update_value_label(self) -> None:
        """Refresh the main value label from the current value."""
        self._value_label.setText(self._value_to_text(self._current_value))

    def _update_all_labels(self) -> None:
        """Refresh the main, minimum, and maximum labels."""
        self._value_label.setText(self._value_to_text(self._current_value))
        self._min_label.setText(self._value_to_text(self._min_value))
        self._max_label.setText(self._value_to_text(self._max_value))

    def _iter_width_positions(self, max_samples: int = 200) -> list[int]:
        """Return representative slider positions for width measurement.

        Args:
            max_samples: Maximum number of sample positions to consider.

        Returns:
            Sorted list of slider positions.
        """
        mn = self._slider.minimum()
        mx = self._slider.maximum()
        span = mx - mn

        if span <= max_samples:
            return list(range(mn, mx + 1))

        cand: set[int] = {mn, mx, int(self._slider.value()), int(self._get_default_pos())}
        n_lin = max(0, max_samples - len(cand))
        if n_lin > 0:
            for k in range(1, n_lin + 1):
                cand.add(mn + (span * k) // (n_lin + 1))

        return sorted(cand)

    def _update_value_width(self) -> None:
        """Measure and cache the width required for the value display."""
        old_w = self._value_width
        l = self._value_label
        l.ensurePolished()
        fmt = l.textFormat()
        positions = self._iter_width_positions(max_samples=200)

        new_w = 0
        if fmt == Qt.PlainText:
            fm = QFontMetrics(l.font())
            for i in positions:
                text = self._value_to_text(self._pos_to_value(i))
                new_w = max(new_w, fm.horizontalAdvance(text))
            new_w += 5
        else:
            doc = QTextDocument()
            doc.setDefaultFont(l.font())
            doc.setTextWidth(-1)
            for i in positions:
                html = self._value_to_text(self._pos_to_value(i))
                doc.setHtml(html)
                new_w = max(new_w, int(doc.idealWidth()))

        if self._unit:
            new_w += self._unit_label.sizeHint().width()

        self._value_width = new_w
        self._update_layout()

        if old_w != new_w:
            self.valueWidthChanged.emit(new_w)

    def _update_layout(self):
        """Apply tick visibility and width constraints to the layout."""
        show_range = self._show_range

        if show_range:
            self._slider.setTickPosition(QSlider.TicksBelow if self._orient == Qt.Horizontal else QSlider.TicksRight)
            mn, mx = self._slider.minimum(), self._slider.maximum()
            if mx > mn:
                self._slider.setTickInterval(max(1, mx - mn))
                self._max_label.show()
                self._min_label.show()
        else:
            self._slider.setTickPosition(QSlider.NoTicks)
            self._max_label.hide()
            self._min_label.hide()

        if self._orient == Qt.Horizontal:
            self._sl.setContentsMargins(0, 8 if show_range else 0, 0, 0)
            self._gl.setColumnMinimumWidth(0, self._name_width)
            self._gl.setColumnMinimumWidth(4, self._value_width)
        else:
            self._sl.setContentsMargins(7 if show_range else 0, 0, 0, 0)
            width = max(self._name_width, self._value_width)
            slider_width = self._sl.sizeHint().width()
            self._gl.setColumnMinimumWidth(0, max(10, (width - slider_width) // 2))
            self._gl.setColumnMinimumWidth(1, slider_width)
            self._gl.setColumnMinimumWidth(2, max(10, (width - slider_width) // 2))

        self._gl.invalidate()
        widget = self._gl.parentWidget()
        if widget:
            widget.updateGeometry()
        self._right_click_overlay.sync_to_target()

    def _on_slider_value_changed(self) -> None:
        """Update the typed value and emit ``valueChanged`` after slider movement."""
        val = self._pos_to_value(self._slider.value())
        new_val = self.evaluate_value(val)
        if new_val != self._current_value:
            self._current_value = new_val
            self._update_value_label()
            self.valueChanged.emit(self.get_value())

    def _update_mapping_anchors(self) -> None:
        """Update mapping anchors used by subclasses with adaptive mappings."""
        pass

    def _set_right_click_item_checked(self, act_id, checked: bool) -> bool:
        """Update the stored checked state of a context-menu item.

        Args:
            act_id: Menu item identifier.
            checked: Checked state to store.

        Returns:
            ``True`` if the item was found, otherwise ``False``.
        """
        if not self._right_click_items:
            return False

        for item in self._right_click_items:
            if item.get("id") == "sep":
                continue
            if item.get("id") == act_id:
                item["checkable"] = bool(item.get("checkable", True))
                item["checked"] = bool(checked)
                return True
        return False

    def _set_right_click_item_enabled(self, act_id, enabled: bool) -> bool:
        """Update the stored enabled state of a context-menu item.

        Args:
            act_id: Menu item identifier.
            enabled: Enabled state to store.

        Returns:
            ``True`` if the item was found, otherwise ``False``.
        """
        if not self._right_click_items:
            return False

        for item in self._right_click_items:
            if item.get("id") == "sep":
                continue
            if item.get("id") == act_id:
                item["enabled"] = bool(enabled)
                return True
        return False

    def _right_click_requested(self, item_id, checked: bool) -> None:
        """Dispatch common context-menu actions.

        Args:
            item_id: Triggered menu item identifier.
            checked: Checked state associated with the action.
        """
        if item_id == "save_as_default":
            self.save_current_value_as_default_value()
        elif item_id == "reset_to_default":
            self._reset_to_default_value()

    def save_current_value_as_default_value(self):
        """Persist the current value as the default value."""
        pass

    def _reset_to_default_value(self) -> None:
        """Reset the control to its stored default value."""
        pass

    def get_value_width(self) -> int:
        """Return the cached width of the value display.

        Returns:
            Width in pixels.
        """
        self.blockSignals(True)
        self._update_value_width()
        self.blockSignals(False)
        return self._value_width

    def get_value(self) -> int | float:
        """Return the current typed value.

        Returns:
            Current slider value.
        """
        return self._current_value

    def set_format(self, val_fmt: str) -> None:
        """Set the display format used for slider values.

        Args:
            val_fmt: New format string.
        """
        self._val_fmt = val_fmt
        self._update_eval_fmt()

        self._current_value = self.evaluate_value(self._current_value)
        self._default_value = self.evaluate_value(self._default_value)
        self._min_value = self.evaluate_value(self._min_value)
        self._max_value = self.evaluate_value(self._max_value)

        self._use_sci_html = bool(re.search(r"\{:[0-9]*\.(\d+)S\}", val_fmt))
        text_fmt = Qt.RichText if self._use_sci_html else Qt.PlainText
        self._value_label.setTextFormat(text_fmt)
        self._min_label.setTextFormat(text_fmt)
        self._max_label.setTextFormat(text_fmt)

    def set_border(self, state: SliderBorderState) -> None:
        """Set the visual border state of the widget.

        Args:
            state: Border state enum value.
        """
        state = state.value
        self.setProperty("borderState", state)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_right_click_enabled(self, state: bool) -> None:
        """Enable or disable the context menu.

        Args:
            state: Whether right-click actions should be enabled.
        """
        self._right_click_enable = state

    def set_slider_enabled(self, enabled: bool) -> None:
        """Enable or disable the internal slider widget.

        Args:
            enabled: Whether the slider should be enabled.
        """
        self._slider.setEnabled(enabled)
        self._right_click_overlay.sync_to_target()

    def set_label(self, label: str) -> None:
        """Set the displayed slider label.

        Args:
            label: New slider label text.
        """
        self._name_label.set_text(label)
        self._name_width = self._name_label.sizeHint().width()
        self.nameWidthChanged.emit(self._name_width)

    def _show_context_menu(self, global_pos) -> None:
        """Build and display the context menu.

        Args:
            global_pos: Global screen position where the menu should open.
        """
        if not self._right_click_enable or not self._right_click_items:
            return

        self.set_border(SliderBorderState.NORMAL)
        QApplication.processEvents()
        try:
            menu = QMenu()
            item_by_id = {}

            for item in self._right_click_items:
                act_id = item.get("id")
                if act_id == "sep":
                    menu.addSeparator()
                    continue

                text = str(item.get("text", act_id if act_id is not None else "None"))
                enabled = bool(item.get("enabled", True))
                checkable = bool(item.get("checkable", False))
                checked = bool(item.get("checked", False))

                act = menu.addAction(text)
                act.setEnabled(enabled)
                act.setCheckable(checkable)
                if checkable:
                    act.setChecked(checked)
                act.setData(act_id)
                item_by_id[act_id] = item

            action = menu.exec(global_pos)
            if action is None:
                return

            act_id = action.data()
            if act_id is None:
                act_id = action.text()

            new_checked = False
            if action.isCheckable():
                old_checked = bool(item_by_id.get(act_id, {}).get("checked", action.isChecked()))
                new_checked = bool(action.isChecked())
                if new_checked == old_checked:
                    new_checked = not old_checked
                    action.setChecked(new_checked)
                if act_id in item_by_id:
                    item_by_id[act_id]["checked"] = new_checked

            self._right_click_requested(act_id, new_checked)
        finally:
            self.set_border(SliderBorderState.OFF)
            QApplication.processEvents()

    def contextMenuEvent(self, event) -> None:
        """Handle the Qt context-menu callback.

        Args:
            event: Qt context-menu event.
        """
        self._show_context_menu(event.globalPos())

    def resizeEvent(self, event):
        """Synchronize overlay geometry after the widget is resized.

        Args:
            event: Qt resize event.
        """
        super().resizeEvent(event)
        self._right_click_overlay.sync_to_target()

    def showEvent(self, event):
        """Synchronize overlay geometry after the widget is shown.

        Args:
            event: Qt show event.
        """
        super().showEvent(event)
        self._right_click_overlay.sync_to_target()

    def moveEvent(self, event):
        """Synchronize overlay geometry after the widget is moved.

        Args:
            event: Qt move event.
        """
        super().moveEvent(event)
        self._right_click_overlay.sync_to_target()

    def changeEvent(self, event):
        """Handle enabled-state changes and refresh overlays.

        Args:
            event: Qt change event.
        """
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange:
            enabled = self.isEnabled()
            self._slider.setEnabled(enabled)
            self._right_click_overlay.sync_to_target()
            self._default_red_marker.update()
            if not enabled:
                self.set_border(SliderBorderState.OFF)
            self.update()


class NumericSliderBase(LabeledSliderBase[TNum], Generic[TNum]):
    """Base class for editable numeric sliders."""

    def __init__(
        self,
        label: str,
        unit: str,
        value_is_int: bool,
        min_val: TNum,
        max_val: TNum,
        init_val: float | int | str,
        val_fmt: str,
        min_limit: TNum | None,
        max_limit: TNum | None,
        min_limit_inclusive: bool,
        max_limit_inclusive: bool,
        orientation: Qt.Orientation,
        editable: bool,
        show_range: bool,
        parent: Optional[QWidget],
    ):
        """Initialize the numeric slider base class.

        Args:
            label: Slider label text.
            unit: Optional unit label.
            value_is_int: Whether the slider uses integer values.
            min_val: Initial minimum value.
            max_val: Initial maximum value.
            init_val: Initial current value or a special infinity marker.
            val_fmt: Value display format string.
            min_limit: Optional lower hard limit.
            max_limit: Optional upper hard limit.
            min_limit_inclusive: Whether the lower hard limit is inclusive.
            max_limit_inclusive: Whether the upper hard limit is inclusive.
            orientation: Slider orientation.
            editable: Whether editing actions should be enabled.
            show_range: Whether range labels and ticks should be shown.
            parent: Optional parent widget.
        """
        init_special = normalize_special_value(init_val)
        if init_special is not None:
            init_val = max_val if init_special == "+inf" else min_val

        super().__init__(
            label=label,
            unit=unit,
            min_val=min_val,
            max_val=max_val,
            init_val=init_val,
            orientation=orientation,
            val_fmt=val_fmt,
            show_range=show_range,
            parent=parent,
        )

        self._min_limit = min_limit
        self._max_limit = max_limit
        self._min_limit_inclusive = min_limit_inclusive
        self._max_limit_inclusive = max_limit_inclusive

        self._add_right_click_items()
        self._set_right_click_item_enabled("edit_config", editable)
        self.value_is_int = value_is_int

        self._min_value, self._max_value = self._validate_range(min_val, max_val)
        init_val = self._validate_value(init_val)

        if init_special is None:
            if not (min_val <= init_val <= max_val):
                raise ValueError(f"init_val ({init_val}) must be within [{min_val}, {max_val}]")
        else:
            if init_special == "+inf" and self._max_limit is not None:
                raise ValueError("init_val cannot be +inf when max_limit is set")
            if init_special == "-inf" and self._min_limit is not None:
                raise ValueError("init_val cannot be -inf when min_limit is set")

        self._current_value = init_val
        self._default_value = init_val
        self._current_special_value: SpecialValue | None = init_special

        self._v0, self._v1 = 0.0, 0.0
        self._p0, self._p1 = 0, 0

        self._setup_slider()
        if init_special is not None:
            self._enter_special_mode(init_special)
        else:
            self.set_value(self._default_value)

        self._slider.valueChanged.connect(self._on_slider_value_changed)

        self._update_value_width()
        self._update_layout()
        self._update_value_label()

    def _setup_slider(self) -> None:
        """Configure the underlying QSlider."""
        raise NotImplementedError

    def _apply_range_to_slider(self) -> None:
        """Apply the current numeric range to the QSlider."""
        pass

    def _value_to_pos(self, value: TNum) -> int:
        """Map a typed numeric value to an integer slider position.

        Args:
            value: Typed numeric value.

        Returns:
            Integer slider position.
        """
        raise NotImplementedError

    def _get_default_pos(self) -> int:
        """Return the default marker position.

        Returns:
            Slider position corresponding to the default value.
        """
        return self._value_to_pos(self._default_value)

    def value_in_limit(self, value: TNum) -> bool:
        """Return whether a value lies within the configured hard limits.

        Args:
            value: Value to test.

        Returns:
            ``True`` if the value is allowed, otherwise ``False``.
        """
        if self._min_limit is not None:
            if value < self._min_limit:
                return False
            elif value == self._min_limit:
                return self._min_limit_inclusive

        if self._max_limit is not None:
            if value > self._max_limit:
                return False
            elif value == self._max_limit:
                return self._max_limit_inclusive

        return True

    def _range_err_msg(self, value_text: str) -> str:
        """Build an error message describing the allowed numeric interval.

        Args:
            value_text: Label for the offending value.

        Returns:
            Human-readable error message.
        """
        if self._min_limit is None and self._max_limit is None:
            return f"{value_text} is invalid."

        min_text = "-inf" if self._min_limit is None else pretty_sci_text(self._min_limit, sig_digits=3)
        max_text = "+inf" if self._max_limit is None else pretty_sci_text(self._max_limit, sig_digits=3)
        left = "[" if self._min_limit_inclusive else "("
        right = "]" if self._max_limit_inclusive else ")"
        return f"{value_text} must be in {left}{min_text}, {max_text}{right}"

    def _update_all_labels(self) -> None:
        """Refresh the value and range labels for the current numeric range."""
        self._update_value_label()
        self._min_label.setText(self._value_to_text(self._min_value))
        self._max_label.setText(self._value_to_text(self._max_value))

    def _enter_special_mode(self, sv: SpecialValue) -> None:
        """Enter positive- or negative-infinity special mode.

        Args:
            sv: Special value marker, either ``"+inf"`` or ``"-inf"``.
        """
        self._current_special_value = sv
        self.set_slider_enabled(False)
        self._sync_special_menu_state()
        self._update_value_label()

    def _exit_special_mode(self) -> None:
        """Leave special infinity mode and restore slider interaction."""
        self._current_special_value = None
        self.set_slider_enabled(True)
        self._sync_special_menu_state()
        self._update_value_label()

    def _sync_special_menu_state(self) -> None:
        """Synchronize context-menu checks and enabled states for special mode."""
        in_special = self._current_special_value is not None

        self._set_right_click_item_checked("set_to_pos_inf", self._current_special_value == "+inf")
        self._set_right_click_item_checked("set_to_neg_inf", self._current_special_value == "-inf")

        for item_id in ("set_value", "edit_config", "reset_to_default", "save_as_default"):
            self._set_right_click_item_enabled(item_id, not in_special)

        self._set_right_click_item_enabled("set_to_pos_inf", True)
        self._set_right_click_item_enabled("set_to_neg_inf", True)

    def _update_value_label(self) -> None:
        """Refresh the value label, including special infinity markers."""
        if self._current_special_value == "+inf":
            self._value_label.setText("+inf")
        elif self._current_special_value == "-inf":
            self._value_label.setText("-inf")
        else:
            self._value_label.setText(self._value_to_text(self._current_value))

    def _add_right_click_items(self):
        """Append numeric-slider-specific context-menu items."""
        items: List[Dict[str, Any]] = [
            {"id": "sep"},
            {"id": "set_value", "text": "Set Value..."},
        ]

        allow_pos_inf = self._max_limit is None and self._max_limit_inclusive
        allow_neg_inf = self._min_limit is None and self._min_limit_inclusive

        if allow_pos_inf:
            items.append(
                {"id": "set_to_pos_inf", "text": "Set Value to +inf", "checkable": True, "checked": False}
            )

        if allow_neg_inf:
            items.append(
                {"id": "set_to_neg_inf", "text": "Set Value to -inf", "checkable": True, "checked": False}
            )

        items.extend(
            [
                {"id": "sep"},
                {"id": "edit_config", "text": "Edit Configuration...", "enabled": True},
            ]
        )

        self._right_click_items.extend(items)

    def _right_click_requested(self, item_id, checked: bool) -> None:
        """Dispatch numeric-slider context-menu actions.

        Args:
            item_id: Triggered menu item identifier.
            checked: Checked state associated with the action.
        """
        super()._right_click_requested(item_id, checked)
        if item_id == "edit_config":
            self._open_edit_config_dlg()
        elif item_id == "set_value":
            self._open_set_value_dlg()
        elif item_id == "set_to_pos_inf":
            if checked:
                self._enter_special_mode("+inf")
            else:
                self._exit_special_mode()
            self.valueChanged.emit(self.get_value())
        elif item_id == "set_to_neg_inf":
            if checked:
                self._enter_special_mode("-inf")
            else:
                self._exit_special_mode()
            self.valueChanged.emit(self.get_value())

    def _open_edit_config_dlg(self) -> None:
        """Open the configuration dialog and apply accepted changes."""
        dlg = EditConfigDialog[TNum](
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
        if dlg.exec() != QDialog.Accepted:
            return
        new_min, new_max, new_fmt, new_show_range = dlg.get_values()

        old_fmt = self._val_fmt
        old_show_range = self._show_range
        old_min = self._min_value
        old_max = self._max_value

        self.set_format(new_fmt)

        new_min = self.evaluate_value(new_min)
        new_max = self.evaluate_value(new_max)
        old_cur = self.evaluate_value(self._current_value)
        old_dft = self.evaluate_value(self._default_value)

        needs_clamp = not (new_min <= old_cur <= new_max and new_min <= old_dft <= new_max)

        if needs_clamp:
            new_cur = max(new_min, min(old_cur, new_max))
            new_dft = max(new_min, min(old_dft, new_max))
            self.set_border(SliderBorderState.ERROR)
            try:
                result = slider_ask_clamp_value(
                    proposed_range=f"[{self._value_to_text(new_min)}, {self._value_to_text(new_max)}]",
                    old_cur=self._value_to_text(old_cur),
                    new_cur=self._value_to_text(new_cur),
                    old_dft=self._value_to_text(old_dft),
                    new_dft=self._value_to_text(new_dft),
                    parent=self,
                )
            finally:
                self.set_border(SliderBorderState.OFF)
            if result != AskResult.YES:
                self.set_format(old_fmt)
                return

        self._show_range = new_show_range
        self.set_range(new_min, new_max)
        self._update_layout()
        if (
            old_min != self._min_value
            or old_max != self._max_value
            or old_fmt != self._val_fmt
            or old_show_range != self._show_range
        ):
            self.configChanged.emit(self.get_config())

    def _open_set_value_dlg(self) -> None:
        """Open the value-entry dialog and apply the accepted value."""
        dlg = SetValueDialog[TNum](
            slider_name=self._label_text,
            value_is_int=self.value_is_int,
            current_value=self._current_value,
            val_fmt=self._val_fmt,
            min_limit=self._min_limit,
            max_limit=self._max_limit,
            min_limit_inclusive=self._min_limit_inclusive,
            max_limit_inclusive=self._max_limit_inclusive,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        new_cur = self.evaluate_value(dlg.get_values())

        old_cur = self._current_value
        old_dft = self._default_value

        if not (self._min_value <= new_cur <= self._max_value):
            new_min = min(new_cur, self._min_value)
            new_max = max(new_cur, self._max_value)
            self.set_border(SliderBorderState.ERROR)
            try:
                result = slider_ask_extend_range(
                    proposed_val=self._value_to_text(new_cur),
                    old_range=f"[{self._value_to_text(self._min_value)}, {self._value_to_text(self._max_value)}]",
                    new_range=f"[{self._value_to_text(new_min)}, {self._value_to_text(new_max)}]",
                    parent=self,
                )
            finally:
                self.set_border(SliderBorderState.OFF)
            if result != AskResult.YES:
                return

        self.set_value(new_cur)

        if old_cur != new_cur:
            self.valueChanged.emit(self._current_value)
        new_dft = self._default_value
        if old_dft != new_dft:
            self.defaultChanged.emit(self._default_value)

    def save_current_value_as_default_value(self):
        """Store the current numeric value as the default value."""
        self._default_value = self._current_value
        self.blockSignals(True)
        try:
            self._reset_to_default_value()
        finally:
            self.blockSignals(False)
        self.defaultChanged.emit(self._default_value)

    def _reset_to_default_value(self) -> None:
        """Reset the slider to its stored default value."""
        self._slider.setValue(self._value_to_pos(self._default_value))

    def get_config(self) -> dict:
        """Return a serializable configuration snapshot.

        Returns:
            Mapping containing the current range, format, and range-visibility
            state.
        """
        return {
            "min_val": self._min_value,
            "max_val": self._max_value,
            "val_fmt": self._val_fmt,
            "show_range": self._show_range,
        }

    def _apply_config(self, config: dict) -> None:
        """Apply a validated configuration mapping.

        Args:
            config: Configuration mapping to apply.
        """
        self._show_range = config["show_range"]
        self.set_format(config["val_fmt"])
        self.set_range(config["min_val"], config["max_val"])

    def get_value(self):
        """Return the current value, including special infinity states.

        Returns:
            Current numeric value, ``math.inf``, or ``-math.inf``.
        """
        if self._current_special_value == "+inf":
            return math.inf
        if self._current_special_value == "-inf":
            return -math.inf
        return self._current_value

    def get_current_value(self) -> TNum:
        """Return the stored current finite value.

        Returns:
            Current finite typed value.
        """
        return self._current_value

    def get_default_value(self) -> TNum:
        """Return the stored default finite value.

        Returns:
            Default typed value.
        """
        return self._default_value

    def get_min_value(self) -> TNum:
        """Return the current minimum finite value.

        Returns:
            Minimum typed value.
        """
        return self._min_value

    def get_max_value(self) -> TNum:
        """Return the current maximum finite value.

        Returns:
            Maximum typed value.
        """
        return self._max_value

    def _validate_value(self, value: TNum) -> TNum:
        """Validate a numeric value against hard limits.

        Args:
            value: Value to validate.

        Returns:
            Normalized and validated typed value.
        """
        value = self.evaluate_value(value)
        if not self.value_in_limit(value):
            raise ValueError(self._range_err_msg("value"))
        return value

    def _new_apply_value(self, value: TNum, keep_default_value: bool) -> None:
        """Apply a validated value and extend the visible range if needed.

        Args:
            value: Validated value to apply.
            keep_default_value: Whether to preserve the current default value.
        """
        self._current_value = value
        if not keep_default_value:
            self._default_value = self._current_value

        extended = False
        if value < self._min_value:
            self._min_value = value
            extended = True
        if value > self._max_value:
            self._max_value = value
            extended = True

        self._update_mapping_anchors()
        self._apply_range_to_slider()
        self.blockSignals(True)
        try:
            self._slider.setValue(self._value_to_pos(self._current_value))
        finally:
            self.blockSignals(False)

        self._update_all_labels()
        self._update_value_width()

        if extended:
            self.configChanged.emit(self.get_config())

    def set_value(self, value: Any, keep_default_value: bool = False) -> None:
        """Set the current value, supporting special infinity markers.

        Args:
            value: New value or special infinity marker.
            keep_default_value: Whether to leave the stored default unchanged.
        """
        sv = normalize_special_value(value)
        if sv is not None:
            self._enter_special_mode(sv)
            self.valueChanged.emit(self.get_value())
            return
        self._exit_special_mode()

        validated = self._validate_value(value)
        self._new_apply_value(validated, keep_default_value)

    def set_default_value(self, value: TNum) -> None:
        """Set the default finite value.

        Args:
            value: New default value.
        """
        self._default_value = self._validate_value(value)

        extended = False
        if value < self._min_value:
            self._min_value = value
            extended = True
        if value > self._max_value:
            self._max_value = value
            extended = True

        self._update_mapping_anchors()
        self._apply_range_to_slider()
        self.blockSignals(True)
        try:
            self._slider.setValue(self._value_to_pos(self._current_value))
        finally:
            self.blockSignals(False)

        self._update_all_labels()
        self._update_value_width()

        if extended:
            self.configChanged.emit(self.get_config())

    def _validate_range(self, min_val: TNum, max_val: TNum) -> Tuple[TNum, TNum]:
        """Validate a numeric range.

        Args:
            min_val: Proposed minimum value.
            max_val: Proposed maximum value.

        Returns:
            Tuple of normalized minimum and maximum values.
        """
        min_val = self.evaluate_value(min_val)
        max_val = self.evaluate_value(max_val)
        if min_val >= max_val:
            raise ValueError(f"min_val ({min_val}) must be less than max_val ({max_val})")

        if not self.value_in_limit(min_val):
            raise ValueError(self._range_err_msg("min_val"))
        if not self.value_in_limit(max_val):
            raise ValueError(self._range_err_msg("max_val"))
        return min_val, max_val

    def set_range(self, min_val: TNum, max_val: TNum) -> None:
        """Set the numeric range and clamp current/default values as needed.

        Args:
            min_val: New minimum value.
            max_val: New maximum value.
        """
        new_min_val, new_max_val = self._validate_range(min_val, max_val)
        self._min_value = new_min_val
        self._max_value = new_max_val

        dft_clamped = False
        if self._current_value < new_min_val:
            self._current_value = new_min_val
        elif self._current_value > new_max_val:
            self._current_value = new_max_val

        if self._default_value < new_min_val:
            self._default_value = new_min_val
            dft_clamped = True
        elif self._default_value > new_max_val:
            self._default_value = new_max_val
            dft_clamped = True

        self._update_mapping_anchors()
        self._apply_range_to_slider()
        self._slider.setValue(self._value_to_pos(self._current_value))

        self._update_all_labels()
        self._update_value_width()

        if dft_clamped:
            self.defaultChanged.emit(self._default_value)

    def set_min_value(self, min_val: TNum) -> None:
        """Update only the minimum bound.

        Args:
            min_val: New minimum value.
        """
        self.set_range(min_val, self._max_value)

    def set_max_value(self, max_val: TNum) -> None:
        """Update only the maximum bound.

        Args:
            max_val: New maximum value.
        """
        self.set_range(self._min_value, max_val)


class IntSlider(NumericSliderBase[int]):
    """Integer-valued slider whose QSlider range matches the numeric range directly."""

    def __init__(
        self,
        label: str,
        min_val: int,
        max_val: int,
        unit: str = "",
        init_val: Optional[int] = None,
        val_fmt: str = "{:d}",
        min_limit: int | None = None,
        max_limit: int | None = None,
        min_limit_inclusive: bool = True,
        max_limit_inclusive: bool = True,
        show_range: bool = True,
        orientation: Qt.Orientation = Qt.Horizontal,
        editable: bool = True,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the integer slider.

        Args:
            label: Slider label text.
            min_val: Minimum numeric value.
            max_val: Maximum numeric value.
            unit: Optional unit label.
            init_val: Initial value. Defaults to the midpoint of the range.
            val_fmt: Integer display format string.
            min_limit: Optional lower hard limit.
            max_limit: Optional upper hard limit.
            min_limit_inclusive: Whether the lower hard limit is inclusive.
            max_limit_inclusive: Whether the upper hard limit is inclusive.
            show_range: Whether range labels and ticks should be shown.
            orientation: Slider orientation.
            editable: Whether editing actions should be enabled.
            parent: Optional parent widget.
        """
        if init_val is None:
            init_val = (min_val + max_val) // 2

        super().__init__(
            label=label,
            unit=unit,
            value_is_int=True,
            min_val=min_val,
            max_val=max_val,
            init_val=init_val,
            val_fmt=val_fmt,
            min_limit=min_limit,
            max_limit=max_limit,
            min_limit_inclusive=min_limit_inclusive,
            max_limit_inclusive=max_limit_inclusive,
            orientation=orientation,
            show_range=show_range,
            editable=editable,
            parent=parent,
        )

    def _setup_slider(self) -> None:
        """Configure the integer slider range and initial position."""
        self._slider.setRange(self._min_value, self._max_value)
        self._slider.setValue(self._default_value)

    def evaluate_value(self, value: int) -> int:
        """Normalize an integer value using the evaluation format.

        Args:
            value: Integer value to normalize.

        Returns:
            Normalized integer value.
        """
        try:
            return int(self._eval_fmt.format(value))
        except Exception:
            return int(value)

    def _apply_range_to_slider(self) -> None:
        """Apply numeric bounds directly to the underlying QSlider."""
        self._slider.setRange(int(self._min_value), int(self._max_value))

    def _pos_to_value(self, pos: int) -> int:
        """Convert an integer slider position to a typed value.

        Args:
            pos: Slider position.

        Returns:
            Same integer value.
        """
        return pos

    def _value_to_pos(self, value: int) -> int:
        """Convert an integer value to a slider position.

        Args:
            value: Integer value.

        Returns:
            Same integer position.
        """
        return value

    def _validate_value(self, value: int) -> int:
        """Validate that the supplied value is an integer.

        Args:
            value: Value to validate.

        Returns:
            Validated integer value.
        """
        if not isinstance(value, int):
            raise TypeError(f"value must be int, not {type(value).__name__}")
        return super()._validate_value(value)


class FloatSlider(NumericSliderBase[float]):
    """Float-valued slider backed by an integer QSlider with piecewise mapping."""

    def __init__(
        self,
        label: str,
        min_val: float,
        max_val: float,
        unit: str = "",
        init_val: Optional[float | str] = None,
        val_fmt: str = "{:.3f}",
        min_limit: float | None = None,
        max_limit: float | None = None,
        min_limit_inclusive: bool = True,
        max_limit_inclusive: bool = True,
        steps: int = 1_000_000,
        show_range: bool = True,
        orientation: Qt.Orientation = Qt.Horizontal,
        editable: bool = True,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the float slider.

        Args:
            label: Slider label text.
            min_val: Minimum numeric value.
            max_val: Maximum numeric value.
            unit: Optional unit label.
            init_val: Initial value or special infinity marker.
            val_fmt: Float display format string.
            min_limit: Optional lower hard limit.
            max_limit: Optional upper hard limit.
            min_limit_inclusive: Whether the lower hard limit is inclusive.
            max_limit_inclusive: Whether the upper hard limit is inclusive.
            steps: Integer slider resolution.
            show_range: Whether range labels and ticks should be shown.
            orientation: Slider orientation.
            editable: Whether editing actions should be enabled.
            parent: Optional parent widget.
        """
        if steps <= 0:
            raise ValueError("steps must be a positive integer")
        self._steps = steps

        if init_val is None:
            init_val = 0.5 * (min_val + max_val)

        super().__init__(
            label=label,
            unit=unit,
            value_is_int=False,
            min_val=min_val,
            max_val=max_val,
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

    def _setup_slider(self) -> None:
        """Configure the integer-backed slider range and initial position."""
        self._slider.setRange(0, self._steps)
        self._slider.setValue(self._value_to_pos(self._default_value))

    def evaluate_value(self, value: float) -> float:
        """Normalize a float value using the evaluation format.

        Args:
            value: Float value to normalize.

        Returns:
            Normalized float value.
        """
        try:
            return float(self._eval_fmt.format(value))
        except Exception:
            return float(value)

    def _pos_to_value(self, pos: int) -> float:
        """Convert a slider position to a float via piecewise linear interpolation.

        Args:
            pos: Integer slider position.

        Returns:
            Interpolated float value.
        """
        v_min, v0, v1, v_max = self._min_value, self._v0, self._v1, self._max_value
        p_min, p0, p1, p_max = self._slider.minimum(), self._p0, self._p1, self._slider.maximum()

        if pos <= p_min:
            return v_min
        if pos < p0:
            return _map_pos_to_val(pos, p_min, p0, v_min, v0)
        if pos == p0:
            return v0
        if pos < p1:
            return _map_pos_to_val(pos, p0, p1, v0, v1)
        if pos == p1:
            return v1
        if pos < p_max:
            return _map_pos_to_val(pos, p1, p_max, v1, v_max)
        return v_max

    def _value_to_pos(self, value: float) -> int:
        """Convert a float value to a slider position via piecewise interpolation.

        Args:
            value: Float value to convert.

        Returns:
            Integer slider position.
        """
        v_min, v0, v1, v_max = self._min_value, self._v0, self._v1, self._max_value
        p_min, p0, p1, p_max = self._slider.minimum(), self._p0, self._p1, self._slider.maximum()

        if value <= v_min:
            return p_min
        if value < v0:
            return _map_val_to_pos(value, v_min, v0, p_min, p0)
        if value == v0:
            return p0
        if value < v1:
            return _map_val_to_pos(value, v0, v1, p0, p1)
        if value == v1:
            return p1
        if value < v_max:
            return _map_val_to_pos(value, v1, v_max, p1, p_max)
        return p_max

    def _update_mapping_anchors(self) -> None:
        """Update mapping anchors based on the current and default values."""
        val1, val2 = self._current_value, self._default_value
        v_min, v_max = self._min_value, self._max_value
        p_min, p_max = self._slider.minimum(), self._slider.maximum()
        v0, v1 = (val1, val2) if val1 <= val2 else (val2, val1)

        if p_max - p_min < 3:
            self._p0, self._p1 = p_min, p_max
            self._v0, self._v1 = v0, v1
            return

        lo, hi = p_min + 1, p_max - 1

        p0 = _map_val_to_pos(v0, v_min, v_max, p_min, p_max)
        p1 = _map_val_to_pos(v1, v_min, v_max, p_min, p_max)

        if v0 > v_min:
            p0 = max(p0, lo)
        if v0 < v_max:
            p0 = min(p0, hi)

        if v1 > v_min:
            p1 = max(p1, lo)
        if v1 < v_max:
            p1 = min(p1, hi)

        if v1 > v0 and p1 == p0:
            if p0 < hi:
                p1 = p0 + 1
            else:
                p0 = p1 - 1

        self._p0, self._p1 = p0, p1
        self._v0, self._v1 = v0, v1

    def _validate_value(self, value: float) -> float:
        """Validate that the supplied value is numeric.

        Args:
            value: Value to validate.

        Returns:
            Validated float value.
        """
        if not isinstance(value, float | int):
            raise TypeError(f"value must be float, not {type(value).__name__}")
        return super()._validate_value(value)


class ArrEditConfigDialog(QDialog):
    """Dialog for editing array-slider length, format, and range visibility."""

    def __init__(
        self,
        slider_name: str,
        arr_length: int,
        val_fmt: str,
        show_range: bool = True,
        show_range_enabled: bool = True,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the array-slider configuration dialog.

        Args:
            slider_name: Display name of the slider.
            arr_length: Current array length.
            val_fmt: Current display format string.
            show_range: Initial state of the range-label checkbox.
            show_range_enabled: Whether the range-label checkbox is editable.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Configuration")

        self._show_range = show_range
        self._show_range_enabled = show_range_enabled
        sb = QSpinBox(self)
        sb.setMinimum(2)
        sb.setMaximum(100)
        sb.setValue(arr_length)
        sb.ensurePolished()
        sb.setFixedSize(sb.sizeHint())
        self._arr_length_sb = sb
        self._edit_fmt = QLineEdit(val_fmt, self)
        self._cb_ticks = QCheckBox("Show Range", self)
        self._cb_ticks.setChecked(show_range)
        self._cb_ticks.setEnabled(show_range_enabled)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.addRow("Array Slider:", SvgLabel(slider_name, alignment=Qt.AlignLeft | Qt.AlignVCenter))
        form.addRow(self._cb_ticks)
        form.addRow("Array Length:", self._arr_length_sb)
        form.addRow("Format:", self._edit_fmt)
        form.addRow(buttons)

        self.setSizeGripEnabled(False)
        self.adjustSize()
        self.setFixedSize(self.size())

    def get_values(self) -> Tuple[int, str, bool]:
        """Return the validated dialog values.

        Returns:
            Tuple containing array length, format string, and range-visibility flag.
        """
        return (
            self._arr_length_sb.value(),
            self._edit_fmt.text(),
            self._cb_ticks.isChecked(),
        )

    def showEvent(self, event: QShowEvent) -> None:
        """Focus the array-length control when the dialog is shown.

        Args:
            event: Qt show event.
        """
        super().showEvent(event)
        self._arr_length_sb.setFocus()
        self._arr_length_sb.selectAll()


class ArraySlider(LabeledSliderBase[float]):
    """Slider that selects an index from a stored numeric array."""

    def __init__(
        self,
        label: str,
        arr_length: int,
        unit: str = "",
        min_val: float = 0.0,
        max_val: float = 1.0,
        init_index: int = 0,
        orientation: Qt.Orientation = Qt.Horizontal,
        val_fmt: str = "{:.2f}",
        show_range: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the array slider.

        Args:
            label: Slider label text.
            arr_length: Number of array elements.
            unit: Optional unit label.
            min_val: Minimum array value.
            max_val: Maximum array value.
            init_index: Initial selected index.
            orientation: Slider orientation.
            val_fmt: Value display format string.
            show_range: Whether range labels and ticks should be shown.
            parent: Optional parent widget.
        """
        if arr_length < 2:
            raise ValueError("ArraySlider: array_length must be greater than 1.")
        if max_val < min_val:
            raise ValueError("ArraySlider: max_val must be >= min_val.")

        self._arr = np.linspace(min_val, max_val, arr_length, dtype=float)
        self._arr_length = arr_length
        self._default_index = init_index % arr_length

        self._current_value = self._arr[self._default_index]
        self._min_value = float(self._arr[0])
        self._max_value = float(self._arr[-1])

        super().__init__(
            label=label,
            unit=unit,
            min_val=self._min_value,
            max_val=self._max_value,
            init_val=self._current_value,
            orientation=orientation,
            val_fmt=val_fmt,
            show_range=show_range,
            parent=parent,
        )

        self._right_click_items.extend(
            [
                {"id": "sep"},
                {"id": "edit_config", "text": "Edit Configuration...", "enabled": True},
            ]
        )

        self._slider.setRange(0, len(self._arr) - 1)
        self._slider.setValue(self._default_index)
        self.set_format(val_fmt)

        self._slider.valueChanged.connect(self._on_slider_value_changed)

        self._update_all_labels()
        self._update_value_width()
        self._update_layout()

    def evaluate_value(self, value: float) -> float:
        """Normalize an array value using the evaluation format.

        Args:
            value: Value to normalize.

        Returns:
            Normalized float value.
        """
        try:
            return float(self._eval_fmt.format(value))
        except Exception:
            return value

    def _pos_to_value(self, pos: int) -> float:
        """Return the array value at a slider position.

        Args:
            pos: Slider index.

        Returns:
            Array value at that index.
        """
        return float(self._arr[pos])

    def _get_default_pos(self) -> int:
        """Return the default slider index.

        Returns:
            Default array index.
        """
        return self._default_index

    def _rebuild_arr(self, idx: int = -1) -> None:
        """Rebuild the numeric array and select an index.

        Args:
            idx: Index to select after rebuilding.
        """
        self._default_index = idx % self._arr_length
        self._arr = np.linspace(self._min_value, self._max_value, self._arr_length, dtype=float)
        self._current_value = self._arr[self._default_index]
        self._slider.setRange(0, len(self._arr) - 1)
        self._slider.setValue(self._default_index)

    def _right_click_requested(self, item_id, checked: bool) -> None:
        """Dispatch array-slider context-menu actions.

        Args:
            item_id: Triggered menu item identifier.
            checked: Checked state associated with the action.
        """
        super()._right_click_requested(item_id, checked)
        if item_id == "edit_config":
            self._open_edit_config_dlg()

    def save_current_value_as_default_value(self) -> None:
        """Store the current slider index as the default index."""
        self._default_index = self._slider.value()

    def _reset_to_default_value(self) -> None:
        """Reset the slider to the stored default index."""
        self._slider.setValue(self._default_index)

    def _open_edit_config_dlg(self) -> None:
        """Open the array configuration dialog and apply accepted changes."""
        dlg = ArrEditConfigDialog(
            slider_name=self._label_text,
            arr_length=self._arr_length,
            val_fmt=self._val_fmt,
            show_range=self._show_range,
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        new_arr_length, new_fmt, new_show_range = dlg.get_values()

        old_fmt = self._val_fmt
        old_show_range = self._show_range

        self.set_format(new_fmt)
        self._show_range = new_show_range

        if new_arr_length != self._arr_length:
            self._arr_length = new_arr_length
            self._rebuild_arr()
            self.valueChanged.emit(self.get_value())

        self._update_all_labels()
        self._update_value_width()
        self._update_layout()

        if old_fmt != self._val_fmt or old_show_range != self._show_range:
            self.configChanged.emit(self.get_config())

    def get_config(self) -> dict:
        """Return a serializable configuration snapshot.

        Returns:
            Mapping containing the current range, format, and range-visibility
            state.
        """
        return {
            "min_val": self._min_value,
            "max_val": self._max_value,
            "val_fmt": self._val_fmt,
            "show_range": self._show_range,
        }

    def _apply_config(self, config: dict) -> None:
        """Apply a validated configuration mapping.

        Args:
            config: Configuration mapping to apply.
        """
        self._show_range = config["show_range"]
        self.set_format(config["val_fmt"])
        self.set_range(config["min_val"], config["max_val"])

    def _apply_value(self, value: float) -> None:
        """Apply a validated value to the widget state.

        Args:
            value: Validated value to apply.

        Note:
            The array slider primarily uses index-based updates through
            ``set_value`` and slider movement.
        """
        _ = value

    def get_value(self):
        """Return the current array-slider state.

        Returns:
            Mapping containing the array length and current selected index.
        """
        return {
            "arr_length": len(self._arr),
            "index": self._slider.value(),
        }

    def set_value(self, value: Dict[str, int]) -> None:
        """Set the array-slider state from a mapping.

        Args:
            value: Mapping containing ``arr_length`` and ``index`` entries.
        """
        arr_length = value.get("arr_length", self._arr_length)
        if arr_length < 2:
            raise ValueError("ArraySlider: arr_length must be greater than 1.")
        index = value.get("index", self._default_index) % arr_length

        self._arr_length = arr_length
        self._rebuild_arr(index)
        self._update_all_labels()
        self._update_value_width()

    def set_range(self, min_val: TNum, max_val: TNum) -> None:
        """Update the numeric range used to generate the backing array.

        Args:
            min_val: New minimum array value.
            max_val: New maximum array value.
        """
        if max_val < min_val:
            raise ValueError("ArraySlider: max_val must be >= min_val.")

        self._min_value = min_val
        self._max_value = max_val
        self._rebuild_arr()
        self._update_all_labels()
        self._update_value_width()


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
    win.setWindowTitle("Slider Demo (right-click name for Edit/Default)")

    name_w = 0
    value_w = 0

    def set_connections(slider: LabeledSliderBase, name: str) -> None:
        """Connect the demo signal handlers for a slider.

        Args:
            slider: Slider widget to connect.
            name: Name used when printing demo output.
        """
        slider.valueChanged.connect(lambda val: on_value_changed(name, val))
        slider.configChanged.connect(lambda cfg: on_config_changed(name, cfg))
        slider.nameWidthChanged.connect(on_name_width_changed)
        slider.valueWidthChanged.connect(on_value_width_changed)

    def on_value_changed(name, v):
        """Print value-change notifications for the demo.

        Args:
            name: Slider name.
            v: New value.
        """
        print(f"{name} value: {v}")

    def on_config_changed(name, cfg):
        """Print configuration-change notifications for the demo.

        Args:
            name: Slider name.
            cfg: Updated configuration mapping.
        """
        print(f"{name} config: {cfg}")

    def on_name_width_changed(new_w):
        """Propagate a larger label width across horizontal sliders.

        Args:
            new_w: Newly required label width.
        """
        if new_w > name_w:
            for s in h_sliders.values():
                s.set_name_width(new_w)

    def on_value_width_changed(new_w):
        """Propagate a larger value width across horizontal sliders.

        Args:
            new_w: Newly required value width.
        """
        if new_w > value_w:
            for s in h_sliders.values():
                s.set_value_width(new_w)

    h_sliders = {
        "int": IntSlider(
            label="n",
            unit="s",
            min_val=1,
            max_val=100,
            init_val=10,
            val_fmt="{:03d}",
            min_limit=0,
            min_limit_inclusive=False,
        ),
        "float1": FloatSlider(
            label="T_1",
            unit="ms",
            min_val=1,
            max_val=10,
            init_val=1,
            val_fmt="{:.2f}",
            min_limit=0,
            min_limit_inclusive=False,
        ),
        "float2": FloatSlider(
            label="T_2",
            unit="kV",
            min_val=-1,
            max_val=1,
            init_val=0,
            val_fmt="{:.2S}",
            show_range=False,
        ),
        "array": ArraySlider(
            label="z",
            unit="m",
            arr_length=2,
            init_index=50,
            val_fmt="{:.2f}",
        ),
    }

    v_sliders = {
        "int": IntSlider(
            label="n",
            min_val=0,
            max_val=100,
            init_val=10,
            val_fmt="{:0d}",
            orientation=Qt.Vertical,
        ),
        "float1": FloatSlider(
            label="T_1",
            min_val=-1,
            max_val=1,
            init_val=0,
            val_fmt="{:.3S}",
            orientation=Qt.Vertical,
        ),
        "float2": FloatSlider(
            label="T_2",
            min_val=-1,
            max_val=1,
            init_val=0,
            val_fmt="{:.3S}",
            orientation=Qt.Vertical,
            show_range=False,
        ),
        "array": ArraySlider(
            label="z",
            arr_length=51,
            init_index=0,
            val_fmt="{:.3S}",
            orientation=Qt.Vertical,
        ),
    }

    main_layout = QHBoxLayout(win)
    h_sliders_layout = QVBoxLayout()
    v_sliders_layout = QHBoxLayout()

    main_layout.addLayout(h_sliders_layout, 1)
    main_layout.addLayout(v_sliders_layout, 1)

    for name, slider in h_sliders.items():
        nonlocal_name_w = slider.get_name_width()
        nonlocal_value_w = slider.get_value_width()
        name_w = max(name_w, nonlocal_name_w)
        value_w = max(value_w, nonlocal_value_w)
        h_sliders_layout.addWidget(slider)
        set_connections(slider, name)

    for slider in h_sliders.values():
        slider.set_name_width(name_w)
        slider.set_value_width(value_w)

    for name, slider in v_sliders.items():
        v_sliders_layout.addWidget(slider)
        slider.valueChanged.connect(lambda val, n=name: on_value_changed(n, val))

    win.resize(900, 150)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
