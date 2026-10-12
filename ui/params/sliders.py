"""Reusable slider widgets for numeric and discrete parameter controls."""

from __future__ import annotations

import math
import re
import numbers
from contextlib import contextmanager
from enum import Flag, auto
from typing import Any, Callable, Dict, Generic, List, Literal, Optional, Tuple, TypeVar
import numpy as np

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPalette, QPen, QShowEvent, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
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
from ui.params.slider_base import SliderFeature, SliderWidgetBase
from ui.right_click_overlay import RightClickOverlay
from utils.helper_funcs import get_numeric_format_field, pretty_sci_text, value_to_text, format_is_valid

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
    """Dialog for editing slider range and format."""

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
            validate: Callable[[TNum, TNum, str], str | None],
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
            validate: Callable checking (min, max, format); returns an error
                message or None.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Edit Configuration")

        self._validate = validate
        self._edit_min = make_line_edit(
            value_is_int, min_val, val_fmt, min_limit, max_limit, min_limit_inclusive, max_limit_inclusive
        )
        self._edit_max = make_line_edit(
            value_is_int, max_val, val_fmt, min_limit, max_limit, min_limit_inclusive, max_limit_inclusive
        )
        self._edit_fmt = QLineEdit(val_fmt)
        self._edit_fmt.editingFinished.connect(self._fmt_changed)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.addRow(
            "Int Slider:" if value_is_int else "Float Slider:",
            SvgLabel(slider_name, alignment=Qt.AlignLeft | Qt.AlignVCenter),
        )
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

    def accept(self) -> None:
        """Validate the dialog state before accepting it."""
        msg = self._validate(
            self._edit_min.get_value(),
            self._edit_max.get_value(),
            self._edit_fmt.text(),
        )
        if msg:
            show_warning("Invalid configuration", msg, parent=self)
            return
        super().accept()

    def get_values(self) -> Tuple[TNum, TNum, str]:
        """Return the validated dialog values.

        Returns:
            Tuple containing minimum value, maximum value, and format string.
        """
        return (
            self._edit_min.get_value(),
            self._edit_max.get_value(),
            self._edit_fmt.text()
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
            return
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


class LabeledSliderBase(SliderWidgetBase[TNum], Generic[TNum]):
    """Base widget combining a label, a ``QSlider``, a value label, and range labels.

    Frame, menu, layout, widths and events come from ``SliderWidgetBase``; this
    class adds the single-value display and the ``QSlider``-specific hooks.

    Signals ``valueChanged``, ``defaultChanged`` and ``configChanged`` are
    emitted only for user actions (dragging, context menu, dialogs).
    Programmatic setters such as ``set_value``, ``set_range``,
    ``set_format`` and ``set_default_value`` never emit them.
    """

    _RANGE_MARGIN_H = 8
    _RANGE_MARGIN_V = 7

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
            features: SliderFeature,
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
            show_range: Initial visibility of range labels and ticks; change
                later with ``set_show_range``.
            features: Context-menu features offered by the slider; also
                controls the default marker.
            parent: Optional parent widget.
        """
        super().__init__(
            label=label,
            orientation=orientation,
            val_fmt=val_fmt,
            show_range=show_range,
            features=features,
            parent=parent,
        )

        self._unit = unit
        self._min_value = min_val
        self._max_value = max_val
        self._current_value = init_val
        self._default_value = init_val

        self._value_label = QLabel()
        self._value_label.setObjectName("slider_value")
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

        self._attach_slider(QSlider(self._orient))
        self.set_format(val_fmt)
        self._make_layout()

    # ----- SliderWidgetBase hooks -----
    def _make_default_marker(self) -> QWidget:
        """Create the default-value marker on the ``QSlider``."""
        return MarkerOverlay(self._slider, value_fn=self._get_default_pos, thickness=2)

    def _value_widget(self) -> QWidget:
        """Return the value label with its unit."""
        return self._value_and_unit

    def _align_value_labels(self, horizontal: bool) -> None:
        """Align the value label for the orientation.

        Args:
            horizontal: Whether the layout is horizontal.
        """
        if horizontal:
            self._value_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        else:
            self._value_label.setAlignment(Qt.AlignCenter)

    def _value_text_labels(self) -> List[QLabel]:
        """Return the labels whose text format follows the value format."""
        return [self._value_label, self._min_label, self._max_label]

    def _round_values_to_format(self) -> None:
        """Round current, default, min and max to the current format."""
        self._current_value = self.evaluate_value(self._current_value)
        self._default_value = self.evaluate_value(self._default_value)
        self._min_value = self.evaluate_value(self._min_value)
        self._max_value = self.evaluate_value(self._max_value)

    def _apply_range_visibility(self, show: bool) -> None:
        """Show or hide the ``QSlider`` ticks.

        Args:
            show: Whether range ticks should be shown.
        """
        if show:
            horizontal = self._orient == Qt.Horizontal
            self._slider.setTickPosition(QSlider.TicksBelow if horizontal else QSlider.TicksRight)
            mn, mx = self._slider.minimum(), self._slider.maximum()
            if mx > mn:
                self._slider.setTickInterval(max(1, mx - mn))
        else:
            self._slider.setTickPosition(QSlider.NoTicks)

    def _update_value_width(self) -> None:
        """Measure the width required for the value display."""
        l = self._value_label
        l.ensurePolished()
        positions = self._iter_width_positions(max_samples=200)

        new_w = 0
        if l.textFormat() == Qt.PlainText:
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
                doc.setHtml(self._value_to_text(self._pos_to_value(i)))
                new_w = max(new_w, int(doc.idealWidth()))

        if self._unit:
            new_w += self._unit_label.sizeHint().width()

        self._set_measured_value_width(new_w)

    # ----- value handling -----
    def evaluate_value(self, value: TNum, eval_fmt: str | None = None) -> TNum:
        """Normalize a numeric value using the current evaluation format.

        Args:
            value: Value to normalize.
            eval_fmt: Format to use instead of the current one.

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

    def _get_default_pos(self) -> int:
        """Return the default marker position in slider coordinates.

        Returns:
            Integer slider position for the default value.
        """
        raise NotImplementedError

    def _update_mapping_anchors(self) -> None:
        """Update mapping anchors used by subclasses with adaptive mappings."""

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
        for k in range(1, n_lin + 1):
            cand.add(mn + (span * k) // (n_lin + 1))

        return sorted(cand)

    def _on_slider_value_changed(self) -> None:
        """Update the typed value and emit ``valueChanged`` after slider movement."""
        val = self._pos_to_value(self._slider.value())
        new_val = self.evaluate_value(val)
        if new_val != self._current_value:
            self._current_value = new_val
            self._update_value_label()
            if not self._quiet:
                self.valueChanged.emit(self.get_value())

    def get_value(self) -> int | float:
        """Return the current typed value.

        Returns:
            Current slider value.
        """
        return self._current_value


class NumericSliderBase(LabeledSliderBase[TNum], Generic[TNum]):
    """Base class for editable numeric sliders."""

    _SPECIAL_ITEM_IDS = {"+inf": "set_to_pos_inf", "-inf": "set_to_neg_inf"}

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
            features: SliderFeature,
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
            features: Context-menu features offered by the slider.
            show_range: Initial visibility of range labels and ticks; change
                later with ``set_show_range``.
            parent: Optional parent widget.

        Raises:
            ValueError: If the range or init_val violates the limits, or if
                init_val is ±inf without ``SliderFeature.SPECIAL`` or with the
                corresponding limit set.
        """

        self._special_allowed = {"+inf": True, "-inf": True}
        init_special = normalize_special_value(init_val)
        if init_special is not None and SliderFeature.SPECIAL not in features:
            raise ValueError(f"init_val {init_special!r} requires SliderFeature.SPECIAL in features")
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
            features=features,
            parent=parent,
        )
        self._min_limit = min_limit
        self._max_limit = max_limit
        self._min_limit_inclusive = min_limit_inclusive
        self._max_limit_inclusive = max_limit_inclusive

        self._add_right_click_items()
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

        self._set_right_click_item_enabled("set_to_pos_inf", self._special_allowed["+inf"])
        self._set_right_click_item_enabled("set_to_neg_inf", self._special_allowed["-inf"])

    def _check_special_permitted(self, sv: SpecialValue) -> None:
        """Raise if a special value is not valid for this slider.

        Args:
            sv: Special value marker, ``"+inf"`` or ``"-inf"``.

        Raises:
            ValueError: If the value is not permitted by features, limits,
                or the runtime allow state.
        """
        if SliderFeature.SPECIAL not in self._features:
            raise ValueError(f"{sv!r} requires SliderFeature.SPECIAL")
        if sv == "+inf" and self._max_limit is not None:
            raise ValueError("+inf is not allowed when max_limit is set")
        if sv == "-inf" and self._min_limit is not None:
            raise ValueError("-inf is not allowed when min_limit is set")
        if not self._special_allowed[sv]:
            raise ValueError(f"{sv!r} is currently not allowed")

    def _check_new_config(self, new_min: TNum, new_max: TNum, new_fmt: str) -> str | None:
        """Check a proposed range and format before applying them.

        Args:
            new_min: Proposed minimum value.
            new_max: Proposed maximum value.
            new_fmt: Proposed display format string.

        Returns:
            Error message, or ``None`` if the configuration is valid.
        """
        eval_fmt = get_numeric_format_field(new_fmt)
        mn = self.evaluate_value(new_min, eval_fmt)
        mx = self.evaluate_value(new_max, eval_fmt)
        if not format_is_valid(new_fmt, mn):
            return f"Invalid format: {new_fmt!r}"
        if mn >= mx:
            return f"Min must be less than max (with this format: {mn} and {mx})."
        if not self.value_in_limit(mn):
            return self._range_err_msg("Min")
        if not self.value_in_limit(mx):
            return self._range_err_msg("Max")
        return None

    def _update_value_label(self) -> None:
        """Refresh the value label, including special infinity markers."""
        if self._current_special_value == "+inf":
            self._value_label.setText("+inf")
        elif self._current_special_value == "-inf":
            self._value_label.setText("-inf")
        else:
            self._value_label.setText(self._value_to_text(self._current_value))

    def _add_right_click_items(self):
        """Append numeric-slider context-menu items allowed by ``features``."""
        f = self._features
        items: List[Dict[str, Any]] = [{"id": "sep"}]

        if SliderFeature.SET_VALUE in f:
            items.append({"id": "set_value", "text": "Set Value..."})

        if SliderFeature.SPECIAL in f:
            if self._max_limit is None and self._max_limit_inclusive:
                items.append({"id": "set_to_pos_inf", "text": "Set Value to +inf", "checkable": True, "checked": False})
            if self._min_limit is None and self._min_limit_inclusive:
                items.append({"id": "set_to_neg_inf", "text": "Set Value to -inf", "checkable": True, "checked": False})

        if SliderFeature.CONFIG in f:
            items += [{"id": "sep"}, {"id": "edit_config", "text": "Edit Configuration..."}]

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
            min_limit=self._min_limit,
            max_limit=self._max_limit,
            min_limit_inclusive=self._min_limit_inclusive,
            max_limit_inclusive=self._max_limit_inclusive,
            validate=self._check_new_config,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        new_min, new_max, new_fmt = dlg.get_values()

        old_fmt = self._val_fmt
        old_min = self._min_value
        old_max = self._max_value
        saved_cur = self._current_value
        saved_dft = self._default_value
        old_value = self.get_value()

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
                self._current_value, self._default_value = saved_cur, saved_dft
                self._min_value, self._max_value = old_min, old_max
                return

        self.set_range(new_min, new_max)
        self._update_layout()

        if self.get_value() != old_value:
            self.valueChanged.emit(self.get_value())
        if self._default_value != saved_dft:
            self.defaultChanged.emit(self._default_value)
        if (old_min, old_max, old_fmt) != (self._min_value, self._max_value, self._val_fmt):
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
        old_range = (self._min_value, self._max_value)

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

        self.set_value(new_cur, keep_default_value=True)

        if old_cur != new_cur:
            self.valueChanged.emit(self._current_value)
        if (self._min_value, self._max_value) != old_range:
            self.configChanged.emit(self.get_config())

    def save_current_value_as_default_value(self):
        """Store the current numeric value as the default value."""
        self._default_value = self._current_value
        self._update_mapping_anchors()
        with self._quiet_updates():
            self._reset_to_default_value()
        if self._default_red_marker is not None:
            self._default_red_marker.update()
        self.defaultChanged.emit(self._default_value)

    def _reset_to_default_value(self) -> None:
        """Reset the slider to its stored default value."""
        self._slider.setValue(self._value_to_pos(self._default_value))

    def get_config(self) -> dict:
        """Return a serializable configuration snapshot.

        Returns:
            Mapping containing the current range and format.
        """
        return {
            "min_val": self._min_value,
            "max_val": self._max_value,
            "val_fmt": self._val_fmt
        }

    def _validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Merge and check a configuration mapping before applying it.

        Args:
            config: Partial or complete configuration mapping.

        Returns:
            Complete, validated configuration mapping.

        Raises:
            ValueError: If the range or format is invalid.
        """
        config = super()._validate_config(config)
        msg = self._check_new_config(config["min_val"], config["max_val"], config["val_fmt"])
        if msg:
            raise ValueError(msg)
        return config

    def _apply_config(self, config: dict) -> None:
        """Apply a validated configuration mapping.

        Args:
            config: Configuration mapping to apply.
        """
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

    def _apply_value(self, value: TNum, keep_default_value: bool = False) -> None:
        """Apply a validated value and extend the visible range if needed.

        Args:
            value: Validated value to apply.
            keep_default_value: Whether to preserve the current default value.
        """
        self._current_value = value
        if not keep_default_value:
            self._default_value = self._current_value

        self._min_value = min(self._min_value, value)
        self._max_value = max(self._max_value, value)

        self._update_mapping_anchors()
        with self._quiet_updates():
            self._apply_range_to_slider()
            self._slider.setValue(self._value_to_pos(self._current_value))

        self._update_all_labels()
        self._update_value_width()

    def set_value(self, value: Any, keep_default_value: bool = False) -> None:
        """Set the current value, supporting special infinity markers.

        Args:
            value: New value or special infinity marker.
            keep_default_value: Whether to leave the stored default unchanged.

        Raises:
            ValueError: If a ±inf value is not permitted (features, limits, or
                runtime allow state) or a finite value violates the limits.
            TypeError: If the value has the wrong type (see subclasses).
        """
        sv = normalize_special_value(value)
        if sv is not None:
            self._check_special_permitted(sv)
            self._enter_special_mode(sv)
            return

        self._exit_special_mode()
        validated = self._validate_value(value)
        self._apply_value(validated, keep_default_value)

    def set_default_value(self, value: TNum) -> None:
        """Set the default finite value.

        Args:
            value: New default value.
        """
        self._default_value = self._validate_value(value)
        self._min_value = min(self._min_value, self._default_value)
        self._max_value = max(self._max_value, self._default_value)

        self._update_mapping_anchors()
        with self._quiet_updates():
            self._apply_range_to_slider()
            self._slider.setValue(self._value_to_pos(self._current_value))
        if self._default_red_marker is not None:
            self._default_red_marker.update()

        self._update_all_labels()
        self._update_value_width()

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

        if self._current_value < new_min_val:
            self._current_value = new_min_val
        elif self._current_value > new_max_val:
            self._current_value = new_max_val

        if self._default_value < new_min_val:
            self._default_value = new_min_val
        elif self._default_value > new_max_val:
            self._default_value = new_max_val

        self._update_mapping_anchors()
        with self._quiet_updates():
            self._apply_range_to_slider()
            self._slider.setValue(self._value_to_pos(self._current_value))

        self._update_all_labels()
        self._update_value_width()

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

    def set_special_value_allowed(self, mode: str, allowed: bool) -> None:
        """Allow or forbid a special-value context-menu action.

        If the slider is currently in the forbidden mode, it leaves it.
        While a mode is forbidden, ``set_value`` raises ``ValueError`` for it.

        Args:
            mode: Special mode, ``"+inf"`` or ``"-inf"``.
            allowed: Whether the action may be enabled.
        """
        if mode not in self._SPECIAL_ITEM_IDS:
            raise ValueError(f"unknown special mode: {mode!r}")
        self._special_allowed[mode] = bool(allowed)
        if not allowed and self._current_special_value == mode:
            self._exit_special_mode()
        self._sync_special_menu_state()

    def is_special_value_allowed(self, mode: str) -> bool:
        """Return whether a special-value action is allowed.

        Args:
            mode: Special mode, ``"+inf"`` or ``"-inf"``.

        Returns:
            ``True`` if the action may be enabled.
        """
        return self._special_allowed.get(mode, False)

    def get_special_value(self) -> Optional[SpecialValue]:
        """Return the active special value.

        Returns:
            ``"+inf"`` or ``"-inf"`` if the slider is in special mode,
            otherwise ``None``.
        """
        return self._current_special_value


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
            features: SliderFeature = SliderFeature.ALL,
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
            show_range: Initial visibility of range labels and ticks; change
                later with ``set_show_range``.
            orientation: Slider orientation.
            features: Context-menu features offered by the slider.
                Defaults to ``SliderFeature.ALL``.
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
            features=features,
            parent=parent,
        )

    def _setup_slider(self) -> None:
        """Configure the integer slider range and initial position."""
        self._slider.setRange(self._min_value, self._max_value)
        self._slider.setValue(self._default_value)

    def evaluate_value(self, value: int, eval_fmt: str | None = None) -> int:
        """Normalize an integer value using the evaluation format.

        Args:
            value: Integer value to normalize.
            eval_fmt: Format to use instead of the current one.

        Returns:
            Normalized integer value.
        """
        fmt = self._eval_fmt if eval_fmt is None else eval_fmt
        try:
            return int(fmt.format(value))
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

        Raises:
            TypeError: If the value is not an integer (``bool`` is rejected).
        """
        if isinstance(value, bool) or not isinstance(value, numbers.Integral):
            raise TypeError(f"value must be int, not {type(value).__name__}")
        return super()._validate_value(int(value))


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
            features: SliderFeature = SliderFeature.ALL,
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
            show_range: Initial visibility of range labels and ticks; change
                later with ``set_show_range``.
            orientation: Slider orientation.
            features: Context-menu features offered by the slider.
                Defaults to ``SliderFeature.ALL``.
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
            features=features,
            parent=parent,
        )

    def _setup_slider(self) -> None:
        """Configure the integer-backed slider range and initial position."""
        self._slider.setRange(0, self._steps)
        self._slider.setValue(self._value_to_pos(self._default_value))

    def evaluate_value(self, value: float, eval_fmt: str | None = None) -> float:
        """Normalize a float value using the evaluation format.

        Args:
            value: Float value to normalize.
            eval_fmt: Format to use instead of the current one.

        Returns:
            Normalized float value.
        """
        fmt = self._eval_fmt if eval_fmt is None else eval_fmt
        try:
            return float(fmt.format(value))
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
        """Validate that the supplied value is a real number.

        Args:
            value: Value to validate. Python and numpy integer or float
                types are accepted.

        Returns:
            Validated value converted to a Python ``float``.

        Raises:
            TypeError: If the value is not a real number (``bool`` is rejected).
        """
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise TypeError(f"value must be float, not {type(value).__name__}")
        return super()._validate_value(float(value))


class ArrEditConfigDialog(QDialog):
    """Dialog for editing array-slider length and format."""

    def __init__(
            self,
            slider_name: str,
            arr_length: int,
            val_fmt: str,
            parent: Optional[QWidget] = None,
    ):
        """Initialize the array-slider configuration dialog.

        Args:
            slider_name: Display name of the slider.
            arr_length: Current array length.
            val_fmt: Current display format string.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Configuration")

        sb = QSpinBox(self)
        sb.setMinimum(2)
        sb.setMaximum(100)
        sb.setValue(arr_length)
        sb.ensurePolished()
        sb.setFixedSize(sb.sizeHint())
        self._arr_length_sb = sb
        self._edit_fmt = QLineEdit(val_fmt, self)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.addRow("Array Slider:", SvgLabel(slider_name, alignment=Qt.AlignLeft | Qt.AlignVCenter))
        form.addRow("Array Length:", self._arr_length_sb)
        form.addRow("Format:", self._edit_fmt)
        form.addRow(buttons)

        self.setSizeGripEnabled(False)
        self.adjustSize()
        self.setFixedSize(self.size())

    def accept(self) -> None:
        """Validate the format before accepting the dialog."""
        fmt = self._edit_fmt.text()
        if not format_is_valid(fmt, 1.0):
            show_warning("Invalid configuration", f"Invalid format: {fmt!r}", parent=self)
            return
        super().accept()

    def get_values(self) -> Tuple[int, str]:
        """Return the validated dialog values.

        Returns:
            Tuple containing array length and format string.
        """
        return (
            self._arr_length_sb.value(),
            self._edit_fmt.text()
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
            features: SliderFeature = SliderFeature.ALL,
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
            show_range: Initial visibility of range labels and ticks; change
                later with ``set_show_range``.
            features: Context-menu features offered by the slider. Only
                ``DEFAULTS`` and ``CONFIG`` apply; ``SET_VALUE`` and
                ``SPECIAL`` are ignored.
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
            features=features,
            parent=parent,
        )

        if SliderFeature.CONFIG in self._features:
            self._right_click_items.extend(
                [
                    {"id": "sep"},
                    {"id": "edit_config", "text": "Edit Configuration..."},
                ]
            )

        self._slider.setRange(0, len(self._arr) - 1)
        self._slider.setValue(self._default_index)
        self.set_format(val_fmt)

        self._slider.valueChanged.connect(self._on_slider_value_changed)

        self._update_all_labels()
        self._update_value_width()
        self._update_layout()

    def evaluate_value(self, value: float, eval_fmt: str | None = None) -> float:
        """Normalize an array value using the evaluation format.

        Args:
            value: Value to normalize.
            eval_fmt: Format to use instead of the current one.

        Returns:
            Normalized float value.
        """
        fmt = self._eval_fmt if eval_fmt is None else eval_fmt
        try:
            return float(fmt.format(value))
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

    def _rebuild_arr(self, cur_idx: int, dft_idx: int) -> None:
        """Rebuild the numeric array and select indices.

        Args:
            cur_idx: Current index to select after rebuilding.
            dft_idx: Default index to store after rebuilding.
        """
        n = self._arr_length
        self._default_index = dft_idx % n
        self._arr = np.linspace(self._min_value, self._max_value, n, dtype=float)
        self._current_value = float(self._arr[cur_idx % n])
        with self._quiet_updates():
            self._slider.setRange(0, n - 1)
            self._slider.setValue(cur_idx % n)

    @staticmethod
    def _rescale_index(idx: int, old_len: int, new_len: int) -> int:
        """Map an index to the same relative position in a resized array."""
        return round(idx * (new_len - 1) / (old_len - 1))

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
        if self._default_red_marker is not None:
            self._default_red_marker.update()
        self.defaultChanged.emit({"arr_length": self._arr_length, "index": self._default_index})

    def _reset_to_default_value(self) -> None:
        """Reset the slider to the stored default index."""
        self._slider.setValue(self._default_index)

    def _open_edit_config_dlg(self) -> None:
        """Open the array configuration dialog and apply accepted changes."""
        dlg = ArrEditConfigDialog(
            slider_name=self._label_text,
            arr_length=self._arr_length,
            val_fmt=self._val_fmt,
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        new_arr_length, new_fmt = dlg.get_values()

        old_fmt = self._val_fmt

        self.set_format(new_fmt)

        if new_arr_length != self._arr_length:
            old_len = self._arr_length
            self._arr_length = new_arr_length
            self._rebuild_arr(
                self._rescale_index(self._slider.value(), old_len, new_arr_length),
                self._rescale_index(self._default_index, old_len, new_arr_length),
            )
            self.valueChanged.emit(self.get_value())

        self._update_all_labels()
        self._update_value_width()
        self._update_layout()

        if old_fmt != self._val_fmt:
            self.configChanged.emit(self.get_config())

    def set_format(self, val_fmt: str) -> None:
        """Set the display format without rounding the array range."""
        mn, mx = self._min_value, self._max_value
        super().set_format(val_fmt)
        self._min_value, self._max_value = mn, mx

    def get_config(self) -> dict:
        """Return a serializable configuration snapshot.

        Returns:
            Mapping containing the current range and format.
        """
        return {
            "min_val": self._min_value,
            "max_val": self._max_value,
            "val_fmt": self._val_fmt
        }

    def _apply_config(self, config: dict) -> None:
        """Apply a validated configuration mapping.

        Args:
            config: Configuration mapping to apply.
        """
        self.set_format(config["val_fmt"])
        self.set_range(config["min_val"], config["max_val"])

    def _validate_value(self, value: Dict[str, int]) -> Dict[str, int]:
        """Validate and normalize an array-slider state mapping.

        Args:
            value: Mapping with optional ``arr_length`` and ``index`` entries.

        Returns:
            Mapping with both entries filled in and the index wrapped.

        Raises:
            ValueError: If ``arr_length`` is less than 2.
        """
        arr_length = value.get("arr_length", self._arr_length)
        if arr_length < 2:
            raise ValueError("ArraySlider: arr_length must be greater than 1.")
        index = value.get("index", self._default_index) % arr_length
        return {"arr_length": arr_length, "index": index}

    def _apply_value(self, value: Dict[str, int]) -> None:
        """Apply a validated array-slider state.

        Args:
            value: Mapping returned by ``_validate_value``.
        """
        self._arr_length = value["arr_length"]
        self._rebuild_arr(value["index"], value["index"])
        self._update_all_labels()
        self._update_value_width()

    def get_value(self):
        """Return the current array-slider state.

        Returns:
            Mapping containing the array length and current selected index.
        """
        return {
            "arr_length": len(self._arr),
            "index": self._slider.value(),
        }

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
        self._rebuild_arr(self._slider.value(), self._default_index)
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
    win.setWindowTitle("Slider Demo (right-click slider for menu)")

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

    def on_name_width_changed(_new_w):
        """Re-align label widths across horizontal sliders."""
        w = max(s.get_name_width() for s in h_sliders.values())
        for s in h_sliders.values():
            s.set_name_width(w)

    def on_value_width_changed(_new_w):
        """Re-align value widths across horizontal sliders."""
        w = max(s.get_value_width() for s in h_sliders.values())
        for s in h_sliders.values():
            s.set_value_width(w)

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
            features=SliderFeature.NONE
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
            features=SliderFeature.DEFAULTS
        ),
        "float2": FloatSlider(
            label="T_2",
            unit="kV",
            min_val=-1,
            max_val=1,
            init_val="+inf",
            val_fmt="{:.2S}",
            show_range=False,
            features=SliderFeature.ALL
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
