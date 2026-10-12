"""Numeric range sliders with custom painting, dialogs, and overlays."""

from __future__ import annotations

import numbers
import random
from typing import Any, Callable, Dict, Generic, List, Optional, Tuple, TypeVar

from PySide6.QtCore import QEvent, QObject, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPalette, QPen, QShowEvent, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QStyle,
    QStyleOptionSlider,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)

from dialogs.dialogs import (
    AskResult,
    range_slider_ask_clamp_value,
    range_slider_ask_extend_range,
    show_warning,
)
from settings.app_style import SliderBorderState
from settings.ui_defaults import UNIT_LABEL_SIZE
from ui.labels import SvgLabel
from ui.params.slider_base import SliderFeature, SliderWidgetBase
from ui.params.sliders import EditConfigDialog, FloatSlider, make_line_edit
from utils.helper_funcs import format_is_valid, get_numeric_format_field

TNum = TypeVar("TNum", int, float)


class SetValuesDialog(QDialog, Generic[TNum]):
    """Dialog for editing a lower and upper bound pair."""

    def __init__(
        self,
        slider_name: str,
        value_is_int: bool,
        current_lower: TNum,
        current_upper: TNum,
        fmt: str,
        min_limit: TNum | None,
        max_limit: TNum | None,
        min_limit_inclusive: bool,
        max_limit_inclusive: bool,
        validate: Callable[[TNum, TNum], str | None],
        parent: Optional[QWidget] = None,
    ):
        """Initialize the value-pair dialog.

        Args:
            slider_name: Display name of the slider.
            value_is_int: Whether the slider uses integer values.
            current_lower: Current lower bound.
            current_upper: Current upper bound.
            fmt: Current display format string.
            min_limit: Optional lower hard limit.
            max_limit: Optional upper hard limit.
            min_limit_inclusive: Whether the lower hard limit is inclusive.
            max_limit_inclusive: Whether the upper hard limit is inclusive.
            validate: Callable checking (lower, upper); returns an error
                message or None.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Set Values")
        self._validate = validate

        self._edit_lower = make_line_edit(
            value_is_int, current_lower, fmt, min_limit, max_limit, min_limit_inclusive, max_limit_inclusive
        )
        self._edit_upper = make_line_edit(
            value_is_int, current_upper, fmt, min_limit, max_limit, min_limit_inclusive, max_limit_inclusive
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.addRow("Range Slider:", SvgLabel(slider_name, alignment=Qt.AlignLeft | Qt.AlignVCenter))
        form.addRow("Lower:", self._edit_lower)
        form.addRow("Upper:", self._edit_upper)
        form.addRow(buttons)

        self.setSizeGripEnabled(False)
        self.adjustSize()
        self.setFixedSize(self.size())

    def accept(self) -> None:
        """Validate the lower and upper values before accepting."""
        msg = self._validate(self._edit_lower.get_value(), self._edit_upper.get_value())
        if msg:
            show_warning("Invalid values", msg, parent=self)
            return
        super().accept()

    def get_values(self) -> Tuple[TNum, TNum]:
        """Return the lower and upper values.

        Returns:
            Tuple containing the lower and upper values.
        """
        return self._edit_lower.get_value(), self._edit_upper.get_value()

    def showEvent(self, event: QShowEvent) -> None:
        """Focus the lower editor when the dialog is shown.

        Args:
            event: Qt show event.
        """
        super().showEvent(event)
        self._edit_lower.setFocus()
        self._edit_lower.selectAll()


class SetMarginsDialog(QDialog):
    """Dialog for editing lower and upper margin values."""

    def __init__(
        self,
        slider_name: str,
        margin_lower: int,
        margin_upper: int,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the margins dialog.

        Args:
            slider_name: Display name of the slider.
            margin_lower: Current lower margin.
            margin_upper: Current upper margin.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Set Margins")

        self._margin_lo_sb = self._build_spin_box(margin_lower)
        self._margin_up_sb = self._build_spin_box(margin_upper)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.addRow("Range Slider:", SvgLabel(slider_name, alignment=Qt.AlignLeft | Qt.AlignVCenter))
        form.addRow("Upper:", self._margin_up_sb)
        form.addRow("Lower:", self._margin_lo_sb)
        form.addRow(buttons)

        self.setSizeGripEnabled(False)
        self.adjustSize()
        self.setFixedSize(self.size())

    def _build_spin_box(self, value: int) -> QSpinBox:
        """Create a spin box configured for margin editing.

        Args:
            value: Initial spin-box value.

        Returns:
            Configured spin box.
        """
        sb = QSpinBox(self)
        sb.setSuffix(" %")
        sb.setMinimum(0)
        sb.setMaximum(100)
        sb.setValue(value)
        sb.setFixedWidth(sb.sizeHint().width())
        return sb

    def get_values(self) -> Tuple[int, int]:
        """Return the margin values.

        Returns:
            Tuple containing lower and upper margins.
        """
        return self._margin_lo_sb.value(), self._margin_up_sb.value()

    def showEvent(self, event: QShowEvent) -> None:
        """Focus the lower-margin editor when the dialog is shown.

        Args:
            event: Qt show event.
        """
        super().showEvent(event)
        self._margin_lo_sb.setFocus()
        self._margin_lo_sb.selectAll()


class DualHandleSlider(QWidget):
    """Custom slider widget with independently draggable lower and upper handles."""

    valueChanged = Signal(tuple)

    def __init__(
        self,
        minimum=0.0,
        maximum=100.0,
        values=(20.0, 80.0),
        orientation=Qt.Horizontal,
        parent=None,
    ):
        """Initialize the dual-handle slider.

        Args:
            minimum: Minimum allowed value.
            maximum: Maximum allowed value.
            values: Initial lower and upper values.
            orientation: Slider orientation.
            parent: Optional parent widget.

        Raises:
            ValueError: If ``maximum <= minimum``.
        """
        super().__init__(parent)

        self._min = float(minimum)
        self._max = float(maximum)
        self._lower = float(values[0])
        self._upper = float(values[1])
        self._orientation = orientation

        self._active_handle = None
        self._margin = 7
        self._show_ticks = False
        self._tick_count = 2

        self.setMouseTracking(True)

        if self._orientation == Qt.Horizontal:
            self.setMinimumSize(80, 30)
        else:
            self.setMinimumSize(30, 80)

        self._validate()

    def _is_horizontal(self):
        """Return whether the slider orientation is horizontal."""
        return self._orientation == Qt.Horizontal

    def _pixel_min(self):
        """Return the minimum usable pixel coordinate along the slider."""
        return self._margin

    def _pixel_max(self):
        """Return the maximum usable pixel coordinate along the slider."""
        if self._is_horizontal():
            return self.width() - self._margin
        return self.height() - self._margin

    def _pixel_span(self):
        """Return the usable pixel span of the slider."""
        return max(1, self._pixel_max() - self._pixel_min())

    def _value_to_pixel(self, value):
        """Convert a logical value to a coordinate along the slider axis.

        Args:
            value: Logical slider value.

        Returns:
            Axis coordinate (measured from the minimum end).
        """
        value = max(self._min, min(value, self._max))
        frac = (value - self._min) / (self._max - self._min)
        return int(round(self._pixel_min() + frac * self._pixel_span()))

    def _pixel_to_value(self, pixel):
        """Convert an axis coordinate to a logical slider value.

        Args:
            pixel: Coordinate along the slider axis.

        Returns:
            Logical slider value.
        """
        pixel = max(self._pixel_min(), min(pixel, self._pixel_max()))
        frac = (pixel - self._pixel_min()) / self._pixel_span()
        return self._min + frac * (self._max - self._min)

    def _style_option(self, value: float) -> QStyleOptionSlider:
        """Build a style option describing a handle at a given value.

        Args:
            value: Logical slider value.

        Returns:
            Configured style option.
        """
        opt = QStyleOptionSlider()
        opt.initFrom(self)
        opt.orientation = self._orientation
        opt.minimum = 0
        opt.maximum = 10000

        pos = self._value_to_style_pos(value)
        opt.sliderPosition = pos
        opt.sliderValue = pos
        opt.upsideDown = self._orientation == Qt.Vertical
        opt.subControls = QStyle.SC_SliderGroove | QStyle.SC_SliderHandle
        return opt

    def _handle_rect(self, value: float) -> QRect:
        """Return the handle rectangle for a given value.

        Args:
            value: Logical slider value.

        Returns:
            Handle rectangle in widget coordinates.
        """
        opt = self._style_option(value)
        return self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self)

    def _value_to_style_pos(self, value: float) -> int:
        """Convert a logical value to the style system's slider position.

        Args:
            value: Logical slider value.

        Returns:
            Style slider position in the range [0, 10000].
        """
        frac = (value - self._min) / (self._max - self._min)
        return int(round(frac * 10000))

    def _hit_test(self, pos):
        """Return which handle contains the given point.

        Args:
            pos: Mouse position in widget coordinates.

        Returns:
            ``"lower"``, ``"upper"``, or ``None``.
        """
        lower_rect = self._handle_rect(self._lower)
        upper_rect = self._handle_rect(self._upper)

        in_lower = lower_rect.contains(pos)
        in_upper = upper_rect.contains(pos)

        if in_lower and in_upper:
            if self._is_horizontal():
                dl = abs(pos.x() - lower_rect.center().x())
                du = abs(pos.x() - upper_rect.center().x())
            else:
                dl = abs(pos.y() - lower_rect.center().y())
                du = abs(pos.y() - upper_rect.center().y())
            return "lower" if dl <= du else "upper"

        if in_lower:
            return "lower"
        if in_upper:
            return "upper"
        return None

    def _pos_along_slider(self, pos):
        """Return the position projected onto the slider axis.

        Args:
            pos: Mouse position in widget coordinates.

        Returns:
            Coordinate along the logical slider axis.
        """
        if self._is_horizontal():
            return pos.x()
        return self._pixel_min() + self._pixel_max() - pos.y()

    def _closest_handle(self, pos):
        """Return the handle closest to a point.

        Args:
            pos: Mouse position in widget coordinates.

        Returns:
            ``"lower"`` or ``"upper"``.
        """
        lower_c = self._handle_rect(self._lower).center()
        upper_c = self._handle_rect(self._upper).center()
        if self._is_horizontal():
            dl = abs(pos.x() - lower_c.x())
            du = abs(pos.x() - upper_c.x())
        else:
            dl = abs(pos.y() - lower_c.y())
            du = abs(pos.y() - upper_c.y())
        return "lower" if dl <= du else "upper"

    def _clamp_pixel(self, pixel: int):
        """Move the active handle to a valid axis coordinate.

        Args:
            pixel: Proposed coordinate along the slider axis.
        """
        if self._active_handle == "lower":
            p_up = self._value_to_pixel(self._upper)
            new_p = max(self._pixel_min(), min(pixel, p_up - 1))
            self.setValues((self._pixel_to_value(new_p), self._upper))
        else:
            p_lo = self._value_to_pixel(self._lower)
            new_p = min(self._pixel_max(), max(pixel, p_lo + 1))
            self.setValues((self._lower, self._pixel_to_value(new_p)))

    def _draw_ticks(self, painter, groove_rect):
        """Draw tick marks along the slider groove.

        Args:
            painter: Painter used for drawing.
            groove_rect: Groove rectangle in widget coordinates.
        """
        if not self._show_ticks:
            return
        painter.save()
        pen = painter.pen()
        pen.setColor(self.palette().color(QPalette.Disabled, QPalette.WindowText))
        painter.setPen(pen)

        n = max(2, self._tick_count)

        if self._is_horizontal():
            y1 = groove_rect.bottom() + 6
            y2 = y1 + 3
            for i in range(n):
                frac = i / (n - 1)
                x = int(round(self._pixel_min() + frac * self._pixel_span()))
                painter.drawLine(x, y1, x, y2)
        else:
            x1 = groove_rect.right() + 6
            x2 = x1 + 3
            for i in range(n):
                frac = i / (n - 1)
                y = int(round(self._pixel_max() - frac * self._pixel_span()))
                painter.drawLine(x1, y, x2, y)
        painter.restore()

    def _validate(self):
        """Validate the configured slider range.

        Raises:
            ValueError: If ``maximum <= minimum``.
        """
        if self._max <= self._min:
            raise ValueError("maximum must be greater than minimum")

    def values(self):
        """Return the current lower and upper values."""
        return self._lower, self._upper

    def setValues(self, values):
        """Set the current lower and upper values.

        Args:
            values: Tuple containing lower and upper values.
        """
        new_vals = (float(values[0]), float(values[1]))
        old_vals = (self._lower, self._upper)
        self._lower, self._upper = new_vals
        self.update()
        if new_vals != old_vals:
            self.valueChanged.emit(new_vals)

    def setRange(self, minimum, maximum):
        """Set the allowed slider range.

        Args:
            minimum: New minimum value.
            maximum: New maximum value.

        Raises:
            ValueError: If ``maximum <= minimum``.
        """
        minimum, maximum = float(minimum), float(maximum)
        if maximum <= minimum:
            raise ValueError("maximum must be greater than minimum")
        self._min, self._max = minimum, maximum
        self.setValues((self._lower, self._upper))

    def orientation(self):
        """Return the slider orientation."""
        return self._orientation

    def setShowTicks(self, state: bool):
        """Enable or disable tick rendering.

        Args:
            state: Whether ticks should be drawn.
        """
        self._show_ticks = bool(state)
        self.update()

    def setTickCount(self, count: int):
        """Set the number of ticks drawn on the slider.

        Args:
            count: Desired tick count.
        """
        self._tick_count = max(2, int(count))
        self.update()

    def mousePressEvent(self, event):
        """Pick a handle and move it to the click position.

        Args:
            event: Qt mouse event.
        """
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)

        pos = event.position().toPoint()
        handle = self._hit_test(pos)
        if handle is None:
            handle = self._closest_handle(pos)

        self._active_handle = handle
        self._clamp_pixel(self._pos_along_slider(pos))
        event.accept()

    def mouseMoveEvent(self, event):
        """Drag the active handle.

        Args:
            event: Qt mouse event.
        """
        if self._active_handle is None:
            return super().mouseMoveEvent(event)

        self._clamp_pixel(self._pos_along_slider(event.position().toPoint()))
        event.accept()

    def mouseReleaseEvent(self, event):
        """Release the active handle.

        Args:
            event: Qt mouse event.
        """
        self._active_handle = None
        event.accept()

    def paintEvent(self, event):
        """Paint the groove, active span, ticks, and both handles.

        Args:
            event: Qt paint event.
        """
        painter = QStylePainter(self)
        style = self.style()

        lower_opt = self._style_option(self._lower)
        upper_opt = self._style_option(self._upper)

        groove_rect = style.subControlRect(QStyle.CC_Slider, lower_opt, QStyle.SC_SliderGroove, self)
        lower_handle_rect = style.subControlRect(QStyle.CC_Slider, lower_opt, QStyle.SC_SliderHandle, self)
        upper_handle_rect = style.subControlRect(QStyle.CC_Slider, upper_opt, QStyle.SC_SliderHandle, self)

        base_opt = self._style_option(self._min)
        base_opt.subControls = QStyle.SC_SliderGroove

        painter.save()
        painter.setClipRect(groove_rect.adjusted(-1, -1, 1, 1))
        painter.drawComplexControl(QStyle.CC_Slider, base_opt)
        painter.restore()

        if self.isEnabled():
            active_opt = self._style_option(self._upper)
            active_opt.subControls = QStyle.SC_SliderGroove
            if self._is_horizontal():
                left = lower_handle_rect.center().x()
                right = upper_handle_rect.center().x()
                if right > left:
                    painter.save()
                    painter.setClipRect(QRect(left, groove_rect.top() - 2, right - left + 1, groove_rect.height() + 4))
                    painter.drawComplexControl(QStyle.CC_Slider, active_opt)
                    painter.restore()
            else:
                top = upper_handle_rect.center().y()
                bottom = lower_handle_rect.center().y()
                if bottom > top:
                    painter.save()
                    painter.setClipRect(QRect(groove_rect.left() - 2, top, groove_rect.width() + 4, bottom - top + 1))
                    painter.drawComplexControl(QStyle.CC_Slider, active_opt)
                    painter.restore()

        self._draw_ticks(painter, groove_rect)

        for handle, value in (("lower", self._lower), ("upper", self._upper)):
            opt = self._style_option(value)
            opt.subControls = QStyle.SC_SliderHandle
            if self._active_handle == handle and self.isEnabled():
                opt.activeSubControls = QStyle.SC_SliderHandle
                opt.state |= QStyle.State_Sunken
            painter.drawComplexControl(QStyle.CC_Slider, opt)


class RangeMarkerOverlay(QWidget):
    """Transparent overlay that draws two default markers for a range slider."""

    def __init__(
        self,
        slider: "DualHandleSlider",
        lower_value_fn,
        upper_value_fn,
        *,
        thickness: int = 2,
        color: QColor | str = Qt.red,
    ):
        """Initialize the range-marker overlay.

        Args:
            slider: Target dual-handle slider.
            lower_value_fn: Callable returning the lower marker value.
            upper_value_fn: Callable returning the upper marker value.
            thickness: Marker line thickness in pixels.
            color: Marker color.
        """
        super().__init__(slider)
        self._slider = slider
        self._lower_value_fn = lower_value_fn
        self._upper_value_fn = upper_value_fn
        self._thickness = thickness
        self._color = QColor(color)

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        slider.installEventFilter(self)
        self._sync_geometry()
        self.show()

    def _current_color(self):
        """Return the effective marker color for the current enabled state."""
        c = QColor(self._color)
        if not self._slider.isEnabled():
            ref = self.palette().color(QPalette.Disabled, QPalette.WindowText)
            c.setAlphaF(ref.alphaF())
        return c

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        """Synchronize overlay state when the target slider changes.

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
        """Synchronize geometry and visibility with the target slider."""
        self.setGeometry(self._slider.rect())
        self.setVisible(self._slider.isVisible())

    def _draw_one_marker(self, painter: QPainter, value: float) -> None:
        """Draw a single marker line.

        Args:
            painter: Painter used for drawing.
            value: Logical slider value at which to draw the marker.
        """
        groove_rect = self._slider.style().subControlRect(
            QStyle.CC_Slider,
            self._slider._style_option(value),
            QStyle.SC_SliderGroove,
            self._slider,
        )
        handle_rect = self._slider._handle_rect(value)
        if groove_rect.isNull() or handle_rect.isNull():
            return

        c = handle_rect.center()
        if self._slider.orientation() == Qt.Horizontal:
            painter.drawLine(c.x(), groove_rect.top(), c.x(), groove_rect.bottom())
        else:
            painter.drawLine(groove_rect.left(), c.y(), groove_rect.right(), c.y())

    def paintEvent(self, _ev) -> None:
        """Paint both default markers.

        Args:
            _ev: Qt paint event.
        """
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        pen = QPen(self._current_color())
        pen.setWidth(self._thickness)
        p.setPen(pen)
        self._draw_one_marker(p, float(self._lower_value_fn()))
        self._draw_one_marker(p, float(self._upper_value_fn()))
        p.end()


class LabeledRangeSliderBase(SliderWidgetBase[Any], Generic[TNum]):
    """Base widget for labeled range sliders built on ``DualHandleSlider``.

    Frame, menu, layout, widths and events come from ``SliderWidgetBase``; this
    class adds the ``[lower, upper]`` display and the range-specific hooks.

    Signals ``valueChanged``, ``defaultChanged`` and ``configChanged`` are
    emitted only for user actions (dragging, context menu, dialogs).
    Programmatic setters never emit them.
    """

    _RANGE_MARGIN_H = 3
    _RANGE_MARGIN_V = 3
    value_is_int: bool = False

    def __init__(
        self,
        label: str,
        unit: str,
        min_val: TNum,
        max_val: TNum,
        init_vals: Optional[Tuple[TNum, TNum]],
        orientation: Qt.Orientation,
        val_fmt: str,
        show_range: bool,
        features: SliderFeature,
        parent: Optional[QWidget],
    ):
        """Initialize the labeled range-slider base widget.

        Args:
            label: Slider label text.
            unit: Optional unit label.
            min_val: Initial minimum value.
            max_val: Initial maximum value.
            init_vals: Initial lower and upper values, or ``None`` for 25 % /
                75 % of the range.
            orientation: Slider orientation.
            val_fmt: Value display format string.
            show_range: Initial visibility of range labels and ticks; change
                later with ``set_show_range``.
            features: Context-menu features offered by the slider.
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

        if init_vals is None:
            span = max_val - min_val
            lo = self.evaluate_value(min_val + 0.25 * span)
            hi = self.evaluate_value(min_val + 0.75 * span)
        else:
            lo = self.evaluate_value(init_vals[0])
            hi = self.evaluate_value(init_vals[1])

        self._current_lower = lo
        self._current_upper = hi
        self._default_lower = lo
        self._default_upper = hi

        self._value_wrap = QWidget(self)
        self._value_l_label = self._make_value_label("[")
        self._value_lo_label = self._make_value_label("")
        self._value_c_label = self._make_value_label(", ")
        self._value_hi_label = self._make_value_label("")
        self._value_r_label = self._make_value_label("]")
        hl = QHBoxLayout(self._value_wrap)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        for w in (self._value_l_label, self._value_lo_label, self._value_c_label,
                  self._value_hi_label, self._value_r_label):
            hl.addWidget(w)
        if unit:
            self._unit_label = SvgLabel(f"({unit})", parent=self, fix_size=True, font_size=UNIT_LABEL_SIZE)
            hl.addWidget(self._unit_label)
        hl.addStretch(1)

        self._attach_slider(
            DualHandleSlider(
                minimum=float(min_val),
                maximum=float(max_val),
                values=(float(lo), float(hi)),
                orientation=orientation,
                parent=self,
            )
        )
        self.set_format(val_fmt)
        self._make_layout()

    @staticmethod
    def _make_value_label(text: str) -> QLabel:
        """Create a QLabel used in the formatted range display.

        Args:
            text: Initial label text.

        Returns:
            Configured value label.
        """
        label = QLabel(text)
        label.setObjectName("slider_value")
        return label

    # ----- SliderWidgetBase hooks -----
    def _make_default_marker(self) -> QWidget:
        """Create the two default-value markers."""
        return RangeMarkerOverlay(
            self._slider,
            lower_value_fn=lambda: float(self._default_lower),
            upper_value_fn=lambda: float(self._default_upper),
            thickness=2,
        )

    def _value_widget(self) -> QWidget:
        """Return the ``[lower, upper]`` display with its unit."""
        return self._value_wrap

    def _align_value_labels(self, horizontal: bool) -> None:
        """Align the five value labels for the orientation.

        Args:
            horizontal: Whether the layout is horizontal.
        """
        if horizontal:
            fixed = Qt.AlignVCenter
            value = Qt.AlignVCenter | Qt.AlignLeft
        else:
            fixed = Qt.AlignHCenter | Qt.AlignVCenter
            value = Qt.AlignLeft | Qt.AlignVCenter
        for label in (self._value_l_label, self._value_c_label, self._value_r_label):
            label.setAlignment(fixed)
        for label in (self._value_lo_label, self._value_hi_label):
            label.setAlignment(value)

    def _value_text_labels(self) -> List[QLabel]:
        """Return the labels whose text format follows the value format."""
        return [self._value_lo_label, self._value_hi_label, self._min_label, self._max_label]

    def _round_values_to_format(self) -> None:
        """Round current, default, min and max to the current format."""
        self._current_lower = self.evaluate_value(self._current_lower)
        self._current_upper = self.evaluate_value(self._current_upper)
        self._default_lower = self.evaluate_value(self._default_lower)
        self._default_upper = self.evaluate_value(self._default_upper)
        self._min_value = self.evaluate_value(self._min_value)
        self._max_value = self.evaluate_value(self._max_value)

    def _apply_range_visibility(self, show: bool) -> None:
        """Show or hide the slider ticks.

        Args:
            show: Whether range ticks should be shown.
        """
        self._slider.setShowTicks(show)

    def _update_value_width(self) -> None:
        """Measure the width required by the ``[lower, upper]`` display."""
        l = self._value_lo_label
        l.ensurePolished()
        values = self._iter_width_values(max_samples=200)

        value_w = 0
        if l.textFormat() == Qt.PlainText:
            fm = QFontMetrics(l.font())
            for v in values:
                value_w = max(value_w, fm.horizontalAdvance(self._value_to_text(v)))
        else:
            doc = QTextDocument()
            doc.setDefaultFont(l.font())
            doc.setTextWidth(-1)
            if self._orient == Qt.Horizontal:
                doc.setDocumentMargin(0)
            for v in values:
                doc.setHtml(self._value_to_text(v))
                value_w = max(value_w, int(doc.idealWidth()))

        self._value_lo_label.setFixedWidth(value_w)
        self._value_hi_label.setFixedWidth(value_w)
        self._set_measured_value_width(self._value_wrap.sizeHint().width())

    # ----- value handling -----
    def evaluate_value(self, value: TNum, eval_fmt: str | None = None) -> TNum:
        """Normalize a value according to the evaluation format.

        Args:
            value: Value to normalize.
            eval_fmt: Format to use instead of the current one.

        Returns:
            Normalized typed value.
        """
        raise NotImplementedError

    def _range_to_text(self, values: Tuple[TNum, TNum]) -> str:
        """Format a lower/upper pair for display.

        Args:
            values: Pair of lower and upper values.

        Returns:
            Formatted range string.
        """
        lo, hi = values
        return f"[{self._value_to_text(lo)} , {self._value_to_text(hi)}]"

    def _update_value_label(self) -> None:
        """Refresh the lower and upper value labels."""
        self._value_lo_label.setText(self._value_to_text(self._current_lower))
        self._value_hi_label.setText(self._value_to_text(self._current_upper))

    def _update_all_labels(self) -> None:
        """Refresh value and range labels."""
        self._update_value_label()
        self._min_label.setText(self._value_to_text(self._min_value))
        self._max_label.setText(self._value_to_text(self._max_value))

    def _update_marker(self) -> None:
        """Repaint the default markers, if any."""
        if self._default_red_marker is not None:
            self._default_red_marker.update()

    def _iter_width_values(self, max_samples: int = 200) -> list[TNum]:
        """Generate representative values for width measurement.

        Args:
            max_samples: Maximum number of samples to generate.

        Returns:
            List of representative values.
        """
        a = self.evaluate_value(self._min_value)
        b = self.evaluate_value(self._max_value)

        if self.value_is_int:
            mn, mx = int(a), int(b)
            span = mx - mn
            if span <= max_samples:
                return [self.evaluate_value(v) for v in range(mn, mx + 1)]

            vals = {
                mn,
                mx,
                int(self._current_lower),
                int(self._current_upper),
                int(self._default_lower),
                int(self._default_upper),
            }
            n_lin = min(max_samples - len(vals), 100)
            for k in range(1, n_lin + 1):
                vals.add(mn + (span * k) // (n_lin + 1))

            rng = random.Random(0)
            tries = 0
            while len(vals) < max_samples and tries < 10 * max_samples:
                vals.add(rng.randint(mn, mx))
                tries += 1
            return [self.evaluate_value(v) for v in sorted(vals)]

        vals = []
        seen = set()

        def add(v):
            """Add a value if its formatted representation is new."""
            v = self.evaluate_value(v)
            key = self._value_to_text(v)
            if key not in seen:
                seen.add(key)
                vals.append(v)

        for v in (a, b, self._current_lower, self._current_upper, self._default_lower, self._default_upper):
            add(v)

        n_lin = min(max_samples, 100)
        for k in range(n_lin + 1):
            add(a + k / n_lin * (b - a))

        rng = random.Random(0)
        tries = 0
        while len(vals) < max_samples and tries < 20 * max_samples:
            add(rng.uniform(a, b))
            tries += 1
        return vals

    def _on_slider_values_changed(self, vals: Tuple[float, float]) -> None:
        """Handle lower/upper changes from the dual-handle slider.

        Args:
            vals: New lower and upper values from the internal slider.
        """
        lo = self.evaluate_value(vals[0])
        hi = self.evaluate_value(vals[1])

        if hi <= lo:
            self._slider.setValues((self._current_lower, self._current_upper))
        elif lo != self._current_lower or hi != self._current_upper:
            self._current_lower = lo
            self._current_upper = hi
            self._update_value_label()
            if not self._quiet:
                self.valueChanged.emit(self.get_value())

    def save_current_value_as_default_value(self) -> None:
        """Store the current lower and upper values as defaults (user action)."""
        self._default_lower = self._current_lower
        self._default_upper = self._current_upper
        with self._quiet_updates():
            self._reset_to_default_value()
        self._update_marker()
        self.defaultChanged.emit((self._default_lower, self._default_upper))

    def _reset_to_default_value(self) -> None:
        """Move the handles to the default lower and upper values."""
        self._slider.setValues((float(self._default_lower), float(self._default_upper)))

    def get_value(self) -> Any:
        """Return the current lower and upper values.

        Returns:
            Tuple containing lower and upper values.
        """
        return self._current_lower, self._current_upper


class NumericRangeSliderBase(LabeledRangeSliderBase[TNum], Generic[TNum]):
    """Base class for integer and float range sliders.

    The slider works in one of two modes: *values* (the handles define the
    range) or *margins* (lower/upper percentages are used instead and the
    handles are disabled). The mode and margins are part of the value returned
    by ``get_value``.
    """

    def __init__(
        self,
        label: str,
        unit: str,
        value_is_int: bool,
        min_val: TNum,
        max_val: TNum,
        init_vals: Optional[Tuple[TNum, TNum]],
        val_fmt: str,
        min_limit: TNum | None,
        max_limit: TNum | None,
        min_limit_inclusive: bool,
        max_limit_inclusive: bool,
        use_margins: bool,
        margins: Tuple[int, int],
        show_range: bool,
        orientation: Qt.Orientation,
        features: SliderFeature,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the numeric range-slider base class.

        Args:
            label: Slider label text.
            unit: Optional unit label.
            value_is_int: Whether the slider uses integer values.
            min_val: Initial minimum value.
            max_val: Initial maximum value.
            init_vals: Initial lower and upper values.
            val_fmt: Value display format string.
            min_limit: Optional lower hard limit.
            max_limit: Optional upper hard limit.
            min_limit_inclusive: Whether the lower hard limit is inclusive.
            max_limit_inclusive: Whether the upper hard limit is inclusive.
            use_margins: Whether the slider starts in margins mode.
            margins: Lower and upper margins in percent (0-100).
            show_range: Initial visibility of range labels and ticks; change
                later with ``set_show_range``.
            orientation: Slider orientation.
            features: Context-menu features offered by the slider.
            parent: Optional parent widget.

        Raises:
            ValueError: If the range violates the limits, ``init_vals`` is
                outside the range or limits or its upper value is not greater
                than its lower value, a margin is outside 0-100, or
                ``use_margins`` is set without ``SliderFeature.MARGINS``.
            TypeError: If ``init_vals`` contains non-numeric values.
        """
        if use_margins and SliderFeature.MARGINS not in features:
            raise ValueError("use_margins=True requires SliderFeature.MARGINS in features")

        super().__init__(
            label=label,
            unit=unit,
            min_val=min_val,
            max_val=max_val,
            init_vals=init_vals,
            orientation=orientation,
            val_fmt=val_fmt,
            show_range=show_range,
            features=features,
            parent=parent,
        )

        self.value_is_int = value_is_int
        self._min_limit = min_limit
        self._max_limit = max_limit
        self._min_limit_inclusive = min_limit_inclusive
        self._max_limit_inclusive = max_limit_inclusive
        self._use_margins = bool(use_margins)
        self._margin_lower, self._margin_upper = self._validate_margins(margins)

        self._validate_limit_one("min_val", self._min_value)
        self._validate_limit_one("max_val", self._max_value)
        lo, hi = self._validate_pair(self.get_current_value())
        if not (self._min_value <= lo and hi <= self._max_value):
            raise ValueError(
                f"init_vals ({lo}, {hi}) must lie within [{self._min_value}, {self._max_value}]"
            )

        self._add_right_click_items()
        self._slider.valueChanged.connect(self._on_slider_values_changed)

        self._apply_mode()
        self._update_all_labels()
        self._update_value_width()

    # ----- validation -----
    def _validate_limit_one(self, name: str, value: TNum) -> None:
        """Validate that one value lies within the hard limits.

        Args:
            name: Name of the value being validated.
            value: Value to validate.

        Raises:
            ValueError: If the value violates a limit.
        """
        if self._min_limit is not None:
            ok = value >= self._min_limit if self._min_limit_inclusive else value > self._min_limit
            if not ok:
                raise ValueError(f"{name} must be within the allowed limits.")

        if self._max_limit is not None:
            ok = value <= self._max_limit if self._max_limit_inclusive else value < self._max_limit
            if not ok:
                raise ValueError(f"{name} must be within the allowed limits.")

    def _check_number(self, name: str, value: Any) -> None:
        """Check that a value has an acceptable numeric type.

        Args:
            name: Name of the value being checked.
            value: Value to check.

        Raises:
            TypeError: If the value is not a real number (or not an integer on
                integer sliders). ``bool`` is rejected.
        """
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise TypeError(f"{name} must be a number, not {type(value).__name__}")
        if self.value_is_int and not isinstance(value, numbers.Integral):
            raise TypeError(f"{name} must be an integer, not {type(value).__name__}")

    def _validate_pair(self, values: Tuple[Any, Any]) -> Tuple[TNum, TNum]:
        """Validate and normalize a lower/upper pair.

        Args:
            values: Pair of proposed lower and upper values.

        Returns:
            Normalized lower and upper values.

        Raises:
            TypeError: If a value is not numeric.
            ValueError: If a value violates the limits or upper <= lower.
        """
        self._check_number("lower", values[0])
        self._check_number("upper", values[1])
        lo = self.evaluate_value(values[0])
        hi = self.evaluate_value(values[1])

        self._validate_limit_one("lower", lo)
        self._validate_limit_one("upper", hi)

        if hi <= lo:
            raise ValueError("upper must be greater than lower")
        return lo, hi

    @staticmethod
    def _validate_margins(margins: Tuple[Any, Any]) -> Tuple[int, int]:
        """Validate a lower/upper margin pair.

        Args:
            margins: Lower and upper margins in percent.

        Returns:
            Margins as integers.

        Raises:
            ValueError: If a margin is outside 0-100.
        """
        m_lo, m_up = int(margins[0]), int(margins[1])
        if not (0 <= m_lo <= 100 and 0 <= m_up <= 100):
            raise ValueError("margins must be within 0-100")
        return m_lo, m_up

    def _check_new_pair(self, lower: TNum, upper: TNum) -> str | None:
        """Check a proposed lower/upper pair (for the Set Values dialog).

        Args:
            lower: Proposed lower value.
            upper: Proposed upper value.

        Returns:
            Error message, or ``None`` if the pair is valid.
        """
        try:
            self._validate_pair((lower, upper))
        except (TypeError, ValueError) as e:
            return str(e)
        return None

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
        try:
            self._validate_limit_one("Min", mn)
            self._validate_limit_one("Max", mx)
        except ValueError as e:
            return str(e)
        return None

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

    def _validate_value(self, value: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and complete a value mapping.

        Args:
            value: Mapping with optional ``use_margins``, ``range`` and
                ``margins`` entries; missing entries keep their current values.

        Returns:
            Complete, normalized mapping.

        Raises:
            TypeError: If ``value`` is not a mapping or the range is not numeric.
            ValueError: If the range, margins or mode are invalid.
        """
        if not isinstance(value, dict):
            raise TypeError(f"value must be a dict, not {type(value).__name__}")
        use_margins = bool(value.get("use_margins", self._use_margins))
        if use_margins and SliderFeature.MARGINS not in self._features:
            raise ValueError("use_margins=True requires SliderFeature.MARGINS")
        margins = self._validate_margins(value.get("margins", (self._margin_lower, self._margin_upper)))
        pair = self._validate_pair(value.get("range", self.get_current_value()))
        return {"use_margins": use_margins, "range": pair, "margins": margins}

    @staticmethod
    def _clamp_pair_to_range(values: Tuple[TNum, TNum], new_min: TNum, new_max: TNum) -> Tuple[TNum, TNum]:
        """Clamp a lower/upper pair to a new numeric range.

        Each value is clamped into ``[new_min, new_max]``. If that leaves no
        valid pair (upper not greater than lower), the full range is used.

        Args:
            values: Pair of lower and upper values.
            new_min: New minimum range value.
            new_max: New maximum range value.

        Returns:
            Clamped lower and upper values, with lower < upper.
        """
        lo, hi = values
        lo = min(max(lo, new_min), new_max)
        hi = min(max(hi, new_min), new_max)
        if hi <= lo:
            return new_min, new_max
        return lo, hi

    # ----- context menu -----
    def _add_right_click_items(self) -> None:
        """Append range-slider context-menu items allowed by ``features``."""
        f = self._features
        items: List[Dict[str, Any]] = [{"id": "sep"}]
        if SliderFeature.MARGINS in f:
            items.append({"id": "use_values", "text": "Use Values", "checkable": True, "checked": False})
        if SliderFeature.SET_VALUE in f:
            items.append({"id": "set_values", "text": "Set Values..."})
        items.append({"id": "sep"})
        if SliderFeature.MARGINS in f:
            items += [
                {"id": "use_margins", "text": "Use Margins", "checkable": True, "checked": False},
                {"id": "set_margins", "text": "Set Margins..."},
            ]
        if SliderFeature.CONFIG in f:
            items += [{"id": "sep"}, {"id": "edit_config", "text": "Edit Configuration..."}]
        self._right_click_items.extend(items)

    def _right_click_requested(self, item_id, checked: bool) -> None:
        """Dispatch range-slider context-menu actions (user actions).

        Args:
            item_id: Triggered menu item identifier.
            checked: Checked state associated with the action.
        """
        super()._right_click_requested(item_id, checked)
        if item_id == "edit_config":
            self._open_edit_config_dlg()
        elif item_id == "set_values":
            self._open_set_values_dlg()
        elif item_id == "set_margins":
            self._open_set_margins_dlg()
        elif item_id in ("use_values", "use_margins"):
            # Clicking the active mode unchecks it (checked=False): just restore the marks.
            if checked:
                self._use_margins = item_id == "use_margins"
                self._apply_mode()
                self.valueChanged.emit(self.get_value())
            else:
                self._apply_mode()

    def _apply_mode(self) -> None:
        """Apply the current values/margins mode to the menu and widgets (no signals)."""
        use_margins = self._use_margins
        self._set_right_click_item_checked("use_margins", use_margins)
        self._set_right_click_item_checked("use_values", not use_margins)

        self._set_right_click_item_enabled("set_margins", use_margins)
        self._set_right_click_item_enabled("set_values", not use_margins)
        self._set_right_click_item_enabled("save_as_default", not use_margins)
        self._set_right_click_item_enabled("reset_to_default", not use_margins)

        for w in (self._slider, self._min_label, self._max_label, self._value_wrap):
            w.setEnabled(not use_margins)

        self._sync_overlay()

    # ----- dialogs (user actions) -----
    def _open_edit_config_dlg(self) -> None:
        """Open the configuration dialog and apply accepted changes.

        If the new range would exclude the current or default pair, the user
        is asked whether to clamp them. Cancelling restores the previous format
        and values.
        """
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

        # snapshot before set_format rounds anything
        old_fmt = self._val_fmt
        old_min, old_max = self._min_value, self._max_value
        saved_cur = self.get_current_value()
        saved_dft = self.get_default_value()
        old_value = self.get_value()

        self.set_format(new_fmt)
        new_min = self.evaluate_value(new_min)
        new_max = self.evaluate_value(new_max)

        cur = self.get_current_value()
        dft = self.get_default_value()
        new_cur = self._clamp_pair_to_range(cur, new_min, new_max)
        new_dft = self._clamp_pair_to_range(dft, new_min, new_max)

        if new_cur != cur or new_dft != dft:
            self.set_border(SliderBorderState.ERROR)
            try:
                result = range_slider_ask_clamp_value(
                    proposed_range=self._range_to_text((new_min, new_max)),
                    old_cur=self._range_to_text(cur),
                    old_dft=self._range_to_text(dft),
                    new_cur=self._range_to_text(new_cur),
                    new_dft=self._range_to_text(new_dft),
                    parent=self,
                )
            finally:
                self.set_border(SliderBorderState.OFF)
            if result != AskResult.YES:
                self.set_format(old_fmt)
                self._current_lower, self._current_upper = saved_cur
                self._default_lower, self._default_upper = saved_dft
                self._min_value, self._max_value = old_min, old_max
                return

        self.set_range(new_min, new_max)

        if self.get_value() != old_value:
            self.valueChanged.emit(self.get_value())
        if self.get_default_value() != saved_dft:
            self.defaultChanged.emit(self.get_default_value())
        if (old_min, old_max, old_fmt) != (self._min_value, self._max_value, self._val_fmt):
            self.configChanged.emit(self.get_config())

    def _open_set_values_dlg(self) -> None:
        """Open the value-pair dialog and apply the accepted pair.

        Only the current pair changes; the default stays as it is.
        """
        dlg = SetValuesDialog[TNum](
            slider_name=self._label_text,
            value_is_int=self.value_is_int,
            current_lower=self._current_lower,
            current_upper=self._current_upper,
            fmt=self._val_fmt,
            min_limit=self._min_limit,
            max_limit=self._max_limit,
            min_limit_inclusive=self._min_limit_inclusive,
            max_limit_inclusive=self._max_limit_inclusive,
            validate=self._check_new_pair,
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        new_pair = self._validate_pair(dlg.get_values())
        old_value = self.get_value()
        old_range = (self._min_value, self._max_value)

        if not (self._min_value <= new_pair[0] and new_pair[1] <= self._max_value):
            new_min = min(self._min_value, new_pair[0])
            new_max = max(self._max_value, new_pair[1])
            self.set_border(SliderBorderState.ERROR)
            try:
                result = range_slider_ask_extend_range(
                    proposed_vals=self._range_to_text(new_pair),
                    old_range=self._range_to_text(old_range),
                    new_range=self._range_to_text((new_min, new_max)),
                    parent=self,
                )
            finally:
                self.set_border(SliderBorderState.OFF)
            if result != AskResult.YES:
                return

        self.set_value({"range": new_pair}, keep_default_value=True)

        if self.get_value() != old_value:
            self.valueChanged.emit(self.get_value())
        if (self._min_value, self._max_value) != old_range:
            self.configChanged.emit(self.get_config())

    def _open_set_margins_dlg(self) -> None:
        """Open the margins dialog and apply accepted changes."""
        dlg = SetMarginsDialog(
            slider_name=self._label_text,
            margin_lower=self._margin_lower,
            margin_upper=self._margin_upper,
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        new_margins = dlg.get_values()
        if new_margins != (self._margin_lower, self._margin_upper):
            self._margin_lower, self._margin_upper = new_margins
            self.valueChanged.emit(self.get_value())

    # ----- config -----
    def get_config(self) -> dict:
        """Return the current configuration mapping.

        Returns:
            Mapping containing the current range and format.
        """
        return {
            "min_val": self._min_value,
            "max_val": self._max_value,
            "val_fmt": self._val_fmt,
        }

    def _apply_config(self, config: dict) -> None:
        """Apply a validated configuration mapping (no signals).

        Args:
            config: Configuration mapping to apply.
        """
        self.set_format(config["val_fmt"])
        self.set_range(config["min_val"], config["max_val"])

    # ----- value API (programmatic, no signals) -----
    def get_value(self) -> Dict[str, Any]:
        """Return the current mode, range and margins.

        Returns:
            Mapping with ``use_margins``, ``range`` and ``margins``.
        """
        return {
            "use_margins": self._use_margins,
            "range": (self._current_lower, self._current_upper),
            "margins": (self._margin_lower, self._margin_upper),
        }

    def get_current_value(self) -> Tuple[TNum, TNum]:
        """Return the current lower and upper values."""
        return self._current_lower, self._current_upper

    def get_default_value(self) -> Tuple[TNum, TNum]:
        """Return the stored default lower and upper values."""
        return self._default_lower, self._default_upper

    def get_min_value(self) -> TNum:
        """Return the current minimum range value."""
        return self._min_value

    def get_max_value(self) -> TNum:
        """Return the current maximum range value."""
        return self._max_value

    def set_value(self, value: Dict[str, Any], keep_default_value: bool = False) -> None:
        """Set the mode, range and/or margins (no signals).

        Missing entries keep their current values. Everything is validated
        before anything changes. The visible range is extended if needed.

        Args:
            value: Mapping with optional ``use_margins``, ``range`` and
                ``margins`` entries.
            keep_default_value: Whether to keep the stored default range.

        Raises:
            TypeError: If ``value`` is not a mapping or the range is not numeric.
            ValueError: If the range, margins or mode are invalid.
        """
        self._apply_value(self._validate_value(value), keep_default_value)

    def _apply_value(self, value: Dict[str, Any], keep_default_value: bool = False) -> None:
        """Apply a validated value mapping.

        Args:
            value: Mapping returned by ``_validate_value``.
            keep_default_value: Whether to keep the stored default range.
        """
        lo, hi = value["range"]
        self._use_margins = value["use_margins"]
        self._margin_lower, self._margin_upper = value["margins"]
        self._current_lower, self._current_upper = lo, hi
        if not keep_default_value:
            self._default_lower, self._default_upper = lo, hi

        self._min_value = min(self._min_value, lo)
        self._max_value = max(self._max_value, hi)

        with self._quiet_updates():
            self._slider.setRange(float(self._min_value), float(self._max_value))
            self._slider.setValues((float(lo), float(hi)))

        self._update_marker()
        self._update_all_labels()
        self._update_value_width()
        self._apply_mode()

    def set_default_value(self, value: Tuple[TNum, TNum]) -> None:
        """Set the stored default lower and upper values (no signals).

        The visible range is extended if needed.

        Args:
            value: New default lower and upper values.

        Raises:
            TypeError: If a value is not numeric.
            ValueError: If the pair violates the limits or upper <= lower.
        """
        lo, hi = self._validate_pair(value)
        self._default_lower, self._default_upper = lo, hi
        self._min_value = min(self._min_value, lo)
        self._max_value = max(self._max_value, hi)

        with self._quiet_updates():
            self._slider.setRange(float(self._min_value), float(self._max_value))
            self._slider.setValues((float(self._current_lower), float(self._current_upper)))

        self._update_marker()
        self._update_all_labels()
        self._update_value_width()

    def set_range(self, min_val: TNum, max_val: TNum) -> None:
        """Set the numeric range and clamp current/default pairs (no signals).

        Args:
            min_val: New minimum value.
            max_val: New maximum value.

        Raises:
            ValueError: If a bound violates the limits or ``max_val <= min_val``.
        """
        min_val = self.evaluate_value(min_val)
        max_val = self.evaluate_value(max_val)
        self._validate_limit_one("min", min_val)
        self._validate_limit_one("max", max_val)
        if max_val <= min_val:
            raise ValueError("max_val must be greater than min_val")

        self._min_value, self._max_value = min_val, max_val
        self._current_lower, self._current_upper = self._clamp_pair_to_range(
            self.get_current_value(), min_val, max_val
        )
        self._default_lower, self._default_upper = self._clamp_pair_to_range(
            self.get_default_value(), min_val, max_val
        )

        with self._quiet_updates():
            self._slider.setRange(float(min_val), float(max_val))
            self._slider.setValues((float(self._current_lower), float(self._current_upper)))

        self._update_marker()
        self._update_all_labels()
        self._update_value_width()

    def set_min_value(self, min_val: TNum) -> None:
        """Set only the minimum bound (no signals).

        Args:
            min_val: New minimum value.
        """
        self.set_range(min_val, self._max_value)

    def set_max_value(self, max_val: TNum) -> None:
        """Set only the maximum bound (no signals).

        Args:
            max_val: New maximum value.
        """
        self.set_range(self._min_value, max_val)


class IntRangeSlider(NumericRangeSliderBase[int]):
    """Integer-valued range slider widget."""

    def __init__(
        self,
        label: str,
        min_val: int,
        max_val: int,
        unit: str = "",
        init_vals: Optional[Tuple[int, int]] = None,
        val_fmt: str = "{:d}",
        min_limit: int | None = None,
        max_limit: int | None = None,
        min_limit_inclusive: bool = True,
        max_limit_inclusive: bool = True,
        use_margins: bool = False,
        margins: Tuple[int, int] = (10, 10),
        show_range: bool = True,
        orientation: Qt.Orientation = Qt.Horizontal,
        features: SliderFeature = SliderFeature.ALL,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the integer range slider.

        Args:
            label: Slider label text.
            min_val: Minimum finite value.
            max_val: Maximum finite value.
            unit: Optional unit label.
            init_vals: Initial lower and upper values.
            val_fmt: Integer display format string.
            min_limit: Optional lower hard limit.
            max_limit: Optional upper hard limit.
            min_limit_inclusive: Whether the lower hard limit is inclusive.
            max_limit_inclusive: Whether the upper hard limit is inclusive.
            use_margins: Whether the slider starts in margins mode.
            margins: Initial lower and upper margins in percent.
            show_range: Initial visibility of range labels and ticks; change
                later with ``set_show_range``.
            orientation: Slider orientation.
            features: Context-menu features offered by the slider. Defaults
                to ``SliderFeature.ALL``; ``SPECIAL`` and ``VALUES`` are ignored.
            parent: Optional parent widget.
        """
        super().__init__(
            label=label,
            unit=unit,
            value_is_int=True,
            min_val=min_val,
            max_val=max_val,
            init_vals=init_vals,
            val_fmt=val_fmt,
            min_limit=min_limit,
            max_limit=max_limit,
            min_limit_inclusive=min_limit_inclusive,
            max_limit_inclusive=max_limit_inclusive,
            use_margins=use_margins,
            margins=margins,
            show_range=show_range,
            orientation=orientation,
            features=features,
            parent=parent,
        )

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


class FloatRangeSlider(NumericRangeSliderBase[float]):
    """Floating-point range slider widget."""

    def __init__(
        self,
        label: str,
        min_val: float,
        max_val: float,
        unit: str = "",
        init_vals: Optional[Tuple[float, float]] = None,
        val_fmt: str = "{:.3f}",
        min_limit: float | None = None,
        max_limit: float | None = None,
        min_limit_inclusive: bool = True,
        max_limit_inclusive: bool = True,
        use_margins: bool = False,
        margins: Tuple[int, int] = (10, 10),
        show_range: bool = True,
        orientation: Qt.Orientation = Qt.Horizontal,
        features: SliderFeature = SliderFeature.ALL,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the floating-point range slider.

        Args:
            label: Slider label text.
            min_val: Minimum finite value.
            max_val: Maximum finite value.
            unit: Optional unit label.
            init_vals: Initial lower and upper values.
            val_fmt: Float display format string.
            min_limit: Optional lower hard limit.
            max_limit: Optional upper hard limit.
            min_limit_inclusive: Whether the lower hard limit is inclusive.
            max_limit_inclusive: Whether the upper hard limit is inclusive.
            use_margins: Whether the slider starts in margins mode.
            margins: Initial lower and upper margins in percent.
            show_range: Initial visibility of range labels and ticks; change
                later with ``set_show_range``.
            orientation: Slider orientation.
            features: Context-menu features offered by the slider. Defaults
                to ``SliderFeature.ALL``; ``SPECIAL`` and ``VALUES`` are ignored.
            parent: Optional parent widget.
        """
        super().__init__(
            label=label,
            unit=unit,
            value_is_int=False,
            min_val=min_val,
            max_val=max_val,
            init_vals=init_vals,
            val_fmt=val_fmt,
            min_limit=min_limit,
            max_limit=max_limit,
            min_limit_inclusive=min_limit_inclusive,
            max_limit_inclusive=max_limit_inclusive,
            use_margins=use_margins,
            margins=margins,
            show_range=show_range,
            orientation=orientation,
            features=features,
            parent=parent,
        )

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
            return float(fmt.format(float(value)))
        except Exception:
            return float(value)


def _demo_main() -> int:
    """Run this module as a standalone demo.

    Returns:
        Qt application exit code.
    """
    import sys

    from PySide6.QtWidgets import QMainWindow

    from settings.app_style import set_app_style

    app = QApplication(sys.argv)
    set_app_style(app)

    win = QMainWindow()
    win.setWindowTitle("Range slider demo")

    central = QWidget()
    outer_layout = QVBoxLayout(central)

    enable_cb = QCheckBox("Enable")
    enable_cb.setChecked(True)

    r1 = IntRangeSlider("n", 0, 100, init_vals=(20, 80))
    r2 = FloatRangeSlider("k", 5.0e4, 6.0e4, val_fmt="{:.8S}")
    r3 = FloatSlider("A_C", 0.0, 100.0)
    r4 = FloatRangeSlider("B_D", 0.0, 100.0, init_vals=(30, 60), val_fmt="{:.1f}", orientation=Qt.Vertical)
    r5 = FloatSlider("C_E", 0.0, 100.0, orientation=Qt.Vertical)
    sliders = (r1, r2, r3, r4, r5)

    for name, s in zip(("r1", "r2", "r3", "r4", "r5"), sliders):
        s.valueChanged.connect(lambda v, n=name: print(f"{n} value: {v}"))
        s.defaultChanged.connect(lambda v, n=name: print(f"{n} default: {v}"))
        s.configChanged.connect(lambda c, n=name: print(f"{n} config: {c}"))

    def on_check(_state) -> None:
        """Enable or disable all demo sliders."""
        for s in sliders:
            s.setEnabled(enable_cb.isChecked())

    enable_cb.stateChanged.connect(on_check)

    left_layout = QVBoxLayout()
    for s in (r1, r2, r3):
        left_layout.addWidget(s)

    right_layout = QHBoxLayout()
    right_layout.addWidget(r4)
    right_layout.addWidget(r5)

    sliders_layout = QHBoxLayout()
    sliders_layout.addLayout(left_layout, 1)
    sliders_layout.addLayout(right_layout)

    outer_layout.addWidget(enable_cb)
    outer_layout.addLayout(sliders_layout)

    win.setCentralWidget(central)
    win.resize(600, 300)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())