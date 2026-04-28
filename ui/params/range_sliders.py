"""Numeric range sliders with custom painting, dialogs, and overlays."""

from __future__ import annotations

import random
import re
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPalette, QPen, QTextDocument, QShowEvent
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
from settings.app_style import SLIDER_BORDER_STYLE_SHEET, SliderBorderState
from settings.ui_defaults import SLIDER_LABEL_SIZE, UNIT_LABEL_SIZE
from ui.labels import SvgLabel
from ui.numeric_line_edit import NumericLineEdit
from ui.params.parameter_widget_base import ParameterWidgetBase
from ui.params.sliders import FloatSlider
from ui.right_click_overlay import RightClickOverlay
from utils.helper_funcs import get_numeric_format_field, value_to_text

TNum = TypeVar("TNum", int, float)


def _map_val_to_pos(v: float, v_min: float, v_max: float, p_min: int, p_max: int) -> int:
    """Map a numeric value linearly to an integer position.

    Args:
        v: Numeric value to map.
        v_min: Minimum value of the source interval.
        v_max: Maximum value of the source interval.
        p_min: Minimum integer position of the destination interval.
        p_max: Maximum integer position of the destination interval.

    Returns:
        Rounded integer position.

    Note:
        If ``v_min == v_max``, the mapping is degenerate and ``p_min`` is
        returned.
    """
    if v_max == v_min:
        return p_min
    t = (v - v_min) / (v_max - v_min)
    return int(round(p_min + t * (p_max - p_min)))


def _map_pos_to_val(p: int, p_min: int, p_max: int, v_min: float, v_max: float) -> float:
    """Map an integer position linearly to a numeric value.

    Args:
        p: Integer position to map.
        p_min: Minimum position of the source interval.
        p_max: Maximum position of the source interval.
        v_min: Minimum value of the destination interval.
        v_max: Maximum value of the destination interval.

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
    """Create a numeric line edit suitable for range-slider dialogs.

    Args:
        value_is_int: Whether the editor should parse integer values.
        init_value: Initial value shown in the line edit.
        fmt: Slider display format string.
        min_limit: Lower allowed hard limit.
        max_limit: Upper allowed hard limit.
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


class EditConfigDialog(QDialog, Generic[TNum]):
    """Dialog for editing a range slider's configuration."""

    def __init__(
        self,
        range_slider_name: str,
        value_is_int: bool,
        min_val: TNum,
        max_val: TNum,
        fmt: str,
        min_limit: TNum | None,
        max_limit: TNum | None,
        min_limit_inclusive: bool,
        max_limit_inclusive: bool,
        show_range: bool = True,
        show_range_enabled: bool = True,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the configuration dialog.

        Args:
            range_slider_name: Display name of the range slider.
            value_is_int: Whether the slider uses integer values.
            min_val: Current minimum value.
            max_val: Current maximum value.
            fmt: Current display format string.
            min_limit: Optional lower hard limit.
            max_limit: Optional upper hard limit.
            min_limit_inclusive: Whether the lower hard limit is inclusive.
            max_limit_inclusive: Whether the upper hard limit is inclusive.
            show_range: Initial state of the range-visibility option.
            show_range_enabled: Whether the range-visibility option is editable.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Edit Configuration")

        self._show_range = show_range
        self._show_range_enabled = show_range_enabled
        self._value_is_int = value_is_int
        self._edit_min = make_line_edit(
            value_is_int,
            min_val,
            fmt,
            min_limit,
            max_limit,
            min_limit_inclusive,
            max_limit_inclusive,
        )
        self._edit_max = make_line_edit(
            value_is_int,
            max_val,
            fmt,
            min_limit,
            max_limit,
            min_limit_inclusive,
            max_limit_inclusive,
        )
        self._edit_fmt = QLineEdit(fmt)
        self._cb_ticks = QCheckBox("Show Range", self)
        self._cb_ticks.setChecked(show_range)
        self._cb_ticks.setEnabled(show_range_enabled)

        self._edit_fmt.editingFinished.connect(self._fmt_changed)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.addRow("Range Slider:", SvgLabel(range_slider_name, alignment=Qt.AlignLeft | Qt.AlignVCenter))
        form.addRow(self._cb_ticks)
        form.addRow("Min:", self._edit_min)
        form.addRow("Max:", self._edit_max)
        form.addRow("Format:", self._edit_fmt)
        form.addRow(buttons)

        self.setSizeGripEnabled(False)
        self.adjustSize()
        self.setFixedSize(self.size())

    def _fmt_changed(self) -> None:
        """Update numeric validators after the format field changes."""
        fmt = get_numeric_format_field(self._edit_fmt.text())
        self._edit_min.set_fmt(fmt)
        self._edit_max.set_fmt(fmt)

    def accept(self) -> None:
        """Validate the dialog state and accept it when valid."""
        range_min = self._edit_min.get_value()
        range_max = self._edit_max.get_value()

        if range_max <= range_min:
            show_warning("Invalid range", "Min must be less than Max", parent=self)
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
        """Focus the minimum editor when the dialog is shown.

        Args:
            event: Qt show event.
        """
        super().showEvent(event)
        self._edit_min.setFocus()
        self._edit_min.selectAll()


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
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Set Values")

        self._edit_lower = make_line_edit(
            value_is_int,
            current_lower,
            fmt,
            min_limit,
            max_limit,
            min_limit_inclusive,
            max_limit_inclusive,
        )
        self._edit_upper = make_line_edit(
            value_is_int,
            current_upper,
            fmt,
            min_limit,
            max_limit,
            min_limit_inclusive,
            max_limit_inclusive,
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
        lower = self._edit_lower.get_value()
        upper = self._edit_upper.get_value()

        if upper < lower:
            show_warning("Invalid range", "Lower must be less than or equal to upper.", parent=self)
            return

        super().accept()

    def get_values(self) -> Tuple[TNum, TNum]:
        """Return the validated lower and upper values.

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
        """Return the validated margin values.

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
        """Return whether the slider orientation is horizontal.

        Returns:
            ``True`` for horizontal sliders, otherwise ``False``.
        """
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
        """Convert a logical value to a pixel coordinate.

        Args:
            value: Logical slider value.

        Returns:
            Pixel coordinate along the slider axis.
        """
        value = max(self._min, min(value, self._max))
        frac = (value - self._min) / (self._max - self._min)
        return int(round(self._pixel_min() + frac * self._pixel_span()))

    def _pixel_to_value(self, pixel):
        """Convert a pixel coordinate to a logical slider value.

        Args:
            pixel: Pixel coordinate along the slider axis.

        Returns:
            Logical slider value.
        """
        pixel = max(self._pixel_min(), min(pixel, self._pixel_max()))
        frac = (pixel - self._pixel_min()) / self._pixel_span()
        return self._min + frac * (self._max - self._min)

    def _lower_center(self):
        """Return the center point of the lower handle."""
        if self._is_horizontal():
            return QPoint(self._value_to_pixel(self._lower), self.height() // 2)
        return QPoint(self.width() // 2, self._value_to_pixel(self._lower))

    def _upper_center(self):
        """Return the center point of the upper handle."""
        if self._is_horizontal():
            return QPoint(self._value_to_pixel(self._upper), self.height() // 2)
        return QPoint(self.width() // 2, self._value_to_pixel(self._upper))

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

    def _style_pos_to_value(self, pos: int) -> float:
        """Convert a style slider position to a logical value.

        Args:
            pos: Style slider position.

        Returns:
            Logical slider value.
        """
        frac = pos / 10000.0
        return self._min + frac * (self._max - self._min)

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
        return pos.x() if self._is_horizontal() else self._pixel_max() - pos.y()

    def _closest_handle(self, pos):
        """Return the handle closest to a point.

        Args:
            pos: Mouse position in widget coordinates.

        Returns:
            ``"lower"`` or ``"upper"``.
        """
        p = self._pos_along_slider(pos)

        lower_center = self._handle_rect(self._lower).center()
        upper_center = self._handle_rect(self._upper).center()

        lower_p = lower_center.x() if self._is_horizontal() else -lower_center.y()
        upper_p = upper_center.x() if self._is_horizontal() else -upper_center.y()

        dl = abs(p - lower_p)
        du = abs(p - upper_p)

        return "lower" if dl <= du else "upper"

    def _clamp_pixel(self, pixel: int):
        """Clamp a dragged handle to a valid pixel position.

        Args:
            pixel: Proposed pixel position along the slider axis.
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
        c = self.palette().color(QPalette.Disabled, QPalette.WindowText)
        pen.setColor(c)
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
        """Validate the configured slider range."""
        if self._max <= self._min:
            raise ValueError("maximum must be greater than minimum")

    def values(self):
        """Return the current lower and upper values.

        Returns:
            Tuple containing lower and upper slider values.
        """
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
        """
        self._min = float(minimum)
        self._max = float(maximum)
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
        """Handle the Qt mouse press callback.

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
        pixel = self._pos_along_slider(pos)
        self._clamp_pixel(pixel)
        event.accept()

    def mouseMoveEvent(self, event):
        """Handle the Qt mouse move callback.

        Args:
            event: Qt mouse event.
        """
        if self._active_handle is None:
            return super().mouseMoveEvent(event)

        p = event.position().toPoint()
        pixel = p.x() if self._is_horizontal() else self._pixel_max() - p.y()
        self._clamp_pixel(pixel)
        event.accept()

    def mouseReleaseEvent(self, event):
        """Handle the Qt mouse release callback.

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
            if self._is_horizontal():
                left = lower_handle_rect.center().x()
                right = upper_handle_rect.center().x()

                if right > left:
                    active_opt = self._style_option(self._upper)
                    active_opt.subControls = QStyle.SC_SliderGroove

                    painter.save()
                    painter.setClipRect(
                        QRect(
                            left,
                            groove_rect.top() - 2,
                            right - left + 1,
                            groove_rect.height() + 4,
                        )
                    )
                    painter.drawComplexControl(QStyle.CC_Slider, active_opt)
                    painter.restore()
            else:
                top = upper_handle_rect.center().y()
                bottom = lower_handle_rect.center().y()

                if bottom > top:
                    active_opt = self._style_option(self._upper)
                    active_opt.subControls = QStyle.SC_SliderGroove

                    painter.save()
                    painter.setClipRect(
                        QRect(
                            groove_rect.left() - 2,
                            top,
                            groove_rect.width() + 4,
                            bottom - top + 1,
                        )
                    )
                    painter.drawComplexControl(QStyle.CC_Slider, active_opt)
                    painter.restore()

        self._draw_ticks(painter, groove_rect)

        lower_handle_opt = self._style_option(self._lower)
        lower_handle_opt.subControls = QStyle.SC_SliderHandle
        if self._active_handle == "lower" and self.isEnabled():
            lower_handle_opt.activeSubControls = QStyle.SC_SliderHandle
            lower_handle_opt.state |= QStyle.State_Sunken
        painter.drawComplexControl(QStyle.CC_Slider, lower_handle_opt)

        upper_handle_opt = self._style_option(self._upper)
        upper_handle_opt.subControls = QStyle.SC_SliderHandle
        if self._active_handle == "upper" and self.isEnabled():
            upper_handle_opt.activeSubControls = QStyle.SC_SliderHandle
            upper_handle_opt.state |= QStyle.State_Sunken
        painter.drawComplexControl(QStyle.CC_Slider, upper_handle_opt)


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


class LabeledRangeSliderBase(ParameterWidgetBase[tuple], Generic[TNum]):
    """Base widget for labeled range sliders built on ``DualHandleSlider``."""

    def __init__(
        self,
        label: str,
        unit: str,
        min_val: TNum,
        max_val: TNum,
        init_vals: Tuple[TNum, TNum],
        orientation: Qt.Orientation,
        val_fmt: str,
        show_range: bool,
        parent: Optional[QWidget],
    ):
        """Initialize the labeled range-slider base widget.

        Args:
            label: Slider label text.
            unit: Optional unit label.
            min_val: Initial minimum value.
            max_val: Initial maximum value.
            init_vals: Initial lower and upper values.
            orientation: Slider orientation.
            val_fmt: Value display format string.
            show_range: Whether range labels and ticks should be shown.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self.setObjectName("labeled_slider")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(SLIDER_BORDER_STYLE_SHEET)
        self.set_border(SliderBorderState.OFF)

        self._label_text = label
        self._min_value = min_val
        self._max_value = max_val
        self._orient = orientation
        self._show_range = show_range
        self._value_fmt = val_fmt
        self._eval_fmt = ""
        self._update_eval_fmt()
        self._use_sci_html = False
        self._right_click_enable = True

        if init_vals is None:
            span = max_val - min_val
            lo, hi = (
                self.evaluate_value(min_val + 0.25 * span),
                self.evaluate_value(min_val + 0.75 * span),
            )
        else:
            lo = self.evaluate_value(init_vals[0])
            hi = self.evaluate_value(init_vals[1])

        if hi < lo:
            lo, hi = hi, lo

        self._current_lower = lo
        self._current_upper = hi
        self._default_lower = lo
        self._default_upper = hi

        self._name_label = SvgLabel(label, parent=self, font_size=SLIDER_LABEL_SIZE)
        self._value_wrap = QWidget(self)
        self._value_l_label = self._make_value_label("[")
        self._value_lo_label = self._make_value_label("")
        self._value_c_label = self._make_value_label(", ")
        self._value_hi_label = self._make_value_label("")
        self._value_r_label = self._make_value_label("]")
        hl = QHBoxLayout(self._value_wrap)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        hl.addWidget(self._value_l_label)
        hl.addWidget(self._value_lo_label)
        hl.addWidget(self._value_c_label)
        hl.addWidget(self._value_hi_label)
        hl.addWidget(self._value_r_label)
        if unit:
            self._unit_label = SvgLabel(f"({unit})", parent=self, fix_size=True, font_size=UNIT_LABEL_SIZE)
            hl.addWidget(self._unit_label)
        hl.addStretch(1)
        self._min_label = QLabel()
        self._max_label = QLabel()
        self._min_label.setObjectName("slider_range")
        self._max_label.setObjectName("slider_range")

        self._slider = DualHandleSlider(
            minimum=float(min_val),
            maximum=float(max_val),
            values=(float(lo), float(hi)),
            orientation=orientation,
            parent=self,
        )

        self._default_red_marker = RangeMarkerOverlay(
            self._slider,
            lower_value_fn=lambda: float(self._default_lower),
            upper_value_fn=lambda: float(self._default_upper),
            thickness=2,
        )

        self._right_click_overlay = RightClickOverlay(
            target_widget=self._slider,
            owner_widget=self,
            parent=self,
        )
        self._right_click_overlay.hide()

        self._right_click_items: List[Dict[str, Any]] = [
            {"id": "save_as_default", "text": "Save as Default"},
            {"id": "reset_to_default", "text": "Reset to Default"},
        ]

        self._name_width = self._name_label.sizeHint().width()
        self._value_width = 0

        self.set_format(val_fmt)
        self._make_layout()

    def _make_value_label(self, text: str) -> QLabel:
        """Create a QLabel used in the formatted range display.

        Args:
            text: Initial label text.

        Returns:
            Configured value label.
        """
        l = QLabel(text)
        l.setObjectName("slider_value")
        return l

    def _make_layout(self):
        """Build the widget layout for the current orientation."""
        gl = QGridLayout(self)
        gl.setContentsMargins(0, 0, 0, 0)

        slider_wrap = QWidget()
        vl = QVBoxLayout(slider_wrap)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)
        vl.addWidget(self._slider)

        if self._orient == Qt.Horizontal:
            gl.setVerticalSpacing(0)
            com = Qt.AlignVCenter

            self._name_label.setAlignment(com | Qt.AlignRight)

            self._value_l_label.setAlignment(com)
            self._value_lo_label.setAlignment(com | Qt.AlignLeft)
            self._value_c_label.setAlignment(com)
            self._value_hi_label.setAlignment(com | Qt.AlignLeft)
            self._value_r_label.setAlignment(com)

            gl.addWidget(self._name_label, 0, 0, com | Qt.AlignRight)
            gl.addWidget(slider_wrap, 0, 1, 1, 3, com)
            gl.addWidget(self._value_wrap, 0, 4, com | Qt.AlignLeft)
            gl.addWidget(self._min_label, 1, 1)
            gl.addWidget(self._max_label, 1, 3)

            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            gl.setColumnStretch(2, 1)
        else:
            gl.setHorizontalSpacing(0)
            gl.setVerticalSpacing(2)
            com = Qt.AlignHCenter

            self._value_l_label.setAlignment(com | Qt.AlignVCenter)
            self._value_lo_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self._value_c_label.setAlignment(com | Qt.AlignVCenter)
            self._value_hi_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self._value_r_label.setAlignment(com | Qt.AlignVCenter)

            self._name_label.setAlignment(com | Qt.AlignTop)

            self._max_label.setContentsMargins(5, 0, 0, 0)
            self._min_label.setContentsMargins(5, 0, 0, 1)

            gl.addWidget(self._value_wrap, 0, 0, 1, 3, com | Qt.AlignBottom)
            gl.addWidget(slider_wrap, 1, 1, 3, 1, com)
            gl.addWidget(self._name_label, 4, 0, 1, 3, com | Qt.AlignTop)
            gl.addWidget(self._max_label, 1, 2, 1, 2)
            gl.addWidget(self._min_label, 3, 2, 1, 2)

            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
            gl.setRowStretch(2, 1)

        self._gl = gl
        self._vl = vl
        self._right_click_overlay.sync_to_target()

    def evaluate_value(self, value: TNum) -> TNum:
        """Normalize a value according to the current evaluation format.

        Args:
            value: Value to normalize.

        Returns:
            Normalized typed value.
        """
        raise NotImplementedError

    def _value_to_text(self, value: TNum) -> str:
        """Format a single value for display.

        Args:
            value: Value to format.

        Returns:
            Formatted display text.
        """
        return value_to_text(value=value, fmt=self._value_fmt)

    def _range_to_text(self, values: Tuple[TNum, TNum]) -> str:
        """Format a lower/upper pair for display.

        Args:
            values: Pair of lower and upper values.

        Returns:
            Formatted range string.
        """
        lo, hi = values
        return f"[{self._value_to_text(lo)} , {self._value_to_text(hi)}]"

    def _update_eval_fmt(self) -> None:
        """Update the internal evaluation format from the display format."""
        self._eval_fmt = get_numeric_format_field(self._value_fmt)

    def _update_value_label(self) -> None:
        """Refresh the lower and upper value labels."""
        self._value_lo_label.setText(self._value_to_text(self._current_lower))
        self._value_hi_label.setText(self._value_to_text(self._current_upper))

    def _update_all_labels(self) -> None:
        """Refresh value and range labels."""
        self._update_value_label()
        self._min_label.setText(self._value_to_text(self._min_value))
        self._max_label.setText(self._value_to_text(self._max_value))

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
            mn = int(a)
            mx = int(b)
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
            max_tries = 10 * max_samples
            tries = 0
            while len(vals) < max_samples and tries < max_tries:
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

        special = [
            a,
            b,
            self._current_lower,
            self._current_upper,
            self._default_lower,
            self._default_upper,
        ]
        for v in special:
            add(v)

        n_lin = min(max_samples, 100)
        if n_lin > 0:
            for k in range(n_lin + 1):
                frac = k / n_lin
                add(a + frac * (b - a))

        rng = random.Random(0)
        max_tries = 20 * max_samples
        tries = 0
        while len(vals) < max_samples and tries < max_tries:
            add(rng.uniform(a, b))
            tries += 1

        return vals

    def _update_value_width(self) -> None:
        """Measure and cache the width required by the formatted range display."""
        old_w = self._value_width
        l = self._value_lo_label
        l.ensurePolished()
        fmt = l.textFormat()
        values = self._iter_width_values(max_samples=200)

        value_w = 0
        if fmt == Qt.PlainText:
            fm = QFontMetrics(l.font())
            for v in values:
                text = self._value_to_text(v)
                value_w = max(value_w, fm.horizontalAdvance(text))
        else:
            doc = QTextDocument()
            doc.setDefaultFont(l.font())
            doc.setTextWidth(-1)
            if self._orient == Qt.Horizontal:
                doc.setDocumentMargin(0)
            for v in values:
                html = self._value_to_text(v)
                doc.setHtml(html)
                value_w = max(value_w, int(doc.idealWidth()))

        self._value_lo_label.setFixedWidth(value_w)
        self._value_hi_label.setFixedWidth(value_w)
        new_w = self._value_wrap.sizeHint().width()

        self._value_width = new_w
        self._update_layout()
        if old_w != new_w:
            self.valueWidthChanged.emit(new_w)

    def _update_layout(self):
        """Apply range-label visibility and width constraints."""
        show_range = self._show_range

        if show_range:
            self._slider.setShowTicks(True)
            self._max_label.show()
            self._min_label.show()
        else:
            self._slider.setShowTicks(False)
            self._max_label.hide()
            self._min_label.hide()

        if self._orient == Qt.Horizontal:
            self._vl.setContentsMargins(0, 3 if show_range else 0, 0, 0)
            self._gl.setColumnMinimumWidth(0, self._name_width)
            self._gl.setColumnMinimumWidth(4, self._value_width)
        else:
            self._vl.setContentsMargins(3 if show_range else 0, 0, 0, 0)
            width = max(self._name_width, self._value_width)
            slider_width = self._vl.sizeHint().width()

            self._gl.setColumnMinimumWidth(0, max(10, (width - slider_width) // 2))
            self._gl.setColumnMinimumWidth(1, slider_width)
            self._gl.setColumnMinimumWidth(2, max(10, (width - slider_width) // 2))

        self._gl.invalidate()
        widget = self._gl.parentWidget()
        if widget:
            widget.updateGeometry()
        self._right_click_overlay.sync_to_target()

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
            self.valueChanged.emit(self.get_value())

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
        """Store the current lower and upper values as defaults."""
        self._default_lower = self._current_lower
        self._default_upper = self._current_upper
        self.blockSignals(True)
        try:
            self._reset_to_default_value()
        finally:
            self.blockSignals(False)
        self.defaultChanged.emit((self._default_lower, self._default_upper))

    def _reset_to_default_value(self) -> None:
        """Restore the default lower and upper values."""
        self._slider.setValues((float(self._default_lower), float(self._default_upper)))

    def get_value_width(self) -> int:
        """Return the cached width of the value display.

        Returns:
            Width in pixels.
        """
        self.blockSignals(True)
        self._update_value_width()
        self.blockSignals(False)
        return self._value_width

    def get_value(self) -> Tuple[TNum, TNum]:
        """Return the current lower and upper values.

        Returns:
            Tuple containing lower and upper values.
        """
        return self._current_lower, self._current_upper

    def set_format(self, val_fmt: str) -> None:
        """Set the display format used for the range values.

        Args:
            val_fmt: New display format string.
        """
        self._value_fmt = val_fmt
        self._update_eval_fmt()

        self._current_lower = self.evaluate_value(self._current_lower)
        self._current_upper = self.evaluate_value(self._current_upper)
        self._default_lower = self.evaluate_value(self._default_lower)
        self._default_upper = self.evaluate_value(self._default_upper)
        self._min_value = self.evaluate_value(self._min_value)
        self._max_value = self.evaluate_value(self._max_value)

        self._use_sci_html = bool(re.search(r"\{:[0-9]*\.(\d+)S\}", val_fmt))
        text_fmt = Qt.RichText if self._use_sci_html else Qt.PlainText
        self._value_lo_label.setTextFormat(text_fmt)
        self._value_hi_label.setTextFormat(text_fmt)
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

    def set_label(self, label: str) -> None:
        """Set the displayed label text.

        Args:
            label: New label text.
        """
        self._name_label.set_text(label)
        self._name_width = self._name_label.sizeHint().width()
        self.nameWidthChanged.emit(self._name_width)

    def _show_context_menu(self, global_pos) -> None:
        """Build and show the context menu.

        Args:
            global_pos: Global screen position where the menu should open.
        """
        if not self._right_click_enable:
            return
        if not self._right_click_items:
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
        """Synchronize overlay geometry after resizing.

        Args:
            event: Qt resize event.
        """
        super().resizeEvent(event)
        self._right_click_overlay.sync_to_target()

    def showEvent(self, event):
        """Synchronize overlay geometry after showing the widget.

        Args:
            event: Qt show event.
        """
        super().showEvent(event)
        self._right_click_overlay.sync_to_target()

    def moveEvent(self, event):
        """Synchronize overlay geometry after moving the widget.

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


class NumericRangeSliderBase(LabeledRangeSliderBase[TNum], Generic[TNum]):
    """Base class for integer and float range sliders."""

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
        editable: bool,
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
            use_margins: Whether the slider is currently controlled by margins.
            margins: Lower and upper margin values.
            show_range: Whether range labels and ticks should be shown.
            orientation: Slider orientation.
            editable: Whether configuration editing is enabled.
            parent: Optional parent widget.
        """
        super().__init__(
            label=label,
            unit=unit,
            min_val=min_val,
            max_val=max_val,
            init_vals=init_vals,
            orientation=orientation,
            val_fmt=val_fmt,
            show_range=show_range,
            parent=parent,
        )

        self.value_is_int = value_is_int
        self._min_limit = min_limit
        self._max_limit = max_limit
        self._min_limit_inclusive = min_limit_inclusive
        self._max_limit_inclusive = max_limit_inclusive
        self._editable = editable
        self._use_margins = use_margins
        self._margin_lower = margins[0]
        self._margin_upper = margins[1]
        self._add_right_click_items()
        self._set_right_click_item_enabled("edit_config", editable)

        self._slider.valueChanged.connect(self._on_slider_values_changed)

        self._apply_mode()
        self._update_value_width()
        self._update_layout()
        self._update_all_labels()

    def _validate_limit_one(self, name: str, value: TNum) -> None:
        """Validate that one value lies within hard limits.

        Args:
            name: Name of the value being validated.
            value: Value to validate.
        """
        if self._min_limit is not None:
            if self._min_limit_inclusive:
                ok = value >= self._min_limit
            else:
                ok = value > self._min_limit
            if not ok:
                raise ValueError(f"{name} must be within the allowed limits.")

        if self._max_limit is not None:
            if self._max_limit_inclusive:
                ok = value <= self._max_limit
            else:
                ok = value < self._max_limit
            if not ok:
                raise ValueError(f"{name} must be within the allowed limits.")

    def _validate_pair(self, values: Tuple[Any, Any]) -> Tuple[TNum, TNum]:
        """Validate a lower/upper pair.

        Args:
            values: Pair of proposed lower and upper values.

        Returns:
            Normalized lower and upper values.
        """
        lo = self.evaluate_value(values[0])
        hi = self.evaluate_value(values[1])

        self._validate_limit_one("lower", lo)
        self._validate_limit_one("upper", hi)

        if hi <= lo:
            raise ValueError("upper must be greater than lower")

        return lo, hi

    def _clamp_pair_to_range(
        self,
        values: Tuple[TNum, TNum],
        new_min: TNum,
        new_max: TNum,
    ) -> Tuple[TNum, TNum]:
        """Clamp a lower/upper pair to a new numeric range.

        Args:
            values: Pair of lower and upper values.
            new_min: New minimum range value.
            new_max: New maximum range value.

        Returns:
            Clamped lower and upper values.
        """
        lo, hi = values

        lo = max(lo, new_min)
        hi = min(hi, new_max)

        if lo > new_max:
            lo = new_min

        if hi < new_min:
            hi = new_max

        return lo, hi

    def _add_right_click_items(self):
        """Append range-slider-specific context-menu items."""
        self._right_click_items.extend(
            [
                {"id": "sep"},
                {"id": "use_values", "text": "Use Values", "checkable": True, "checked": not self._use_margins},
                {"id": "set_values", "text": "Set Values..."},
                {"id": "sep"},
                {"id": "use_margins", "text": "Use Margins", "checkable": True, "checked": self._use_margins},
                {"id": "set_margins", "text": "Set Margins..."},
                {"id": "sep"},
                {"id": "edit_config", "text": "Edit Configuration...", "enabled": True},
            ]
        )

    def _right_click_requested(self, item_id, checked: bool) -> None:
        """Dispatch range-slider-specific context-menu actions.

        Args:
            item_id: Triggered menu item identifier.
            checked: Checked state associated with the action.
        """
        super()._right_click_requested(item_id, checked)
        if item_id == "edit_config":
            self._open_edit_config_dlg()
        elif item_id == "set_values":
            self._open_set_values_dlg()
        elif item_id == "use_values":
            if checked:
                self._use_margins = False
                self._apply_mode()
            else:
                self._set_right_click_item_checked("use_values", True)
        elif item_id == "use_margins":
            if checked:
                self._use_margins = True
                self._apply_mode()
            else:
                self._set_right_click_item_checked("use_margins", True)
        elif item_id == "set_margins":
            self._open_set_margins_dialog()

    def _open_edit_config_dlg(self) -> None:
        """Open the configuration dialog and apply accepted changes."""
        dlg = EditConfigDialog[TNum](
            range_slider_name=self._label_text,
            value_is_int=self.value_is_int,
            min_val=self._min_value,
            max_val=self._max_value,
            fmt=self._value_fmt,
            show_range=self._show_range,
            min_limit=self._min_limit,
            max_limit=self._max_limit,
            min_limit_inclusive=self._min_limit_inclusive,
            max_limit_inclusive=self._max_limit_inclusive,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        new_min, new_max, new_fmt, new_show_range = dlg.get_values()

        old_min = self._min_value
        old_max = self._max_value
        old_fmt = self._value_fmt
        old_show_range = self._show_range

        new_min = self.evaluate_value(new_min)
        new_max = self.evaluate_value(new_max)

        self.set_format(new_fmt)

        new_cur = self._clamp_pair_to_range((self._current_lower, self._current_upper), new_min, new_max)
        new_dft = self._clamp_pair_to_range((self._default_lower, self._default_upper), new_min, new_max)

        needs_clamp = (
            new_cur != (self._current_lower, self._current_upper)
            or new_dft != (self._default_lower, self._default_upper)
        )

        if needs_clamp:
            self.set_border(SliderBorderState.ERROR)
            try:
                result = range_slider_ask_clamp_value(
                    proposed_range=self._range_to_text((new_min, new_max)),
                    old_cur=self._range_to_text((self._current_lower, self._current_upper)),
                    old_dft=self._range_to_text((self._default_lower, self._default_upper)),
                    new_cur=self._range_to_text(new_cur),
                    new_dft=self._range_to_text(new_dft),
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
            or old_fmt != self._value_fmt
            or old_show_range != self._show_range
        ):
            self.configChanged.emit(self.get_config())

    def _open_set_values_dlg(self) -> None:
        """Open the value-pair dialog and apply accepted changes."""
        dlg = SetValuesDialog[TNum](
            slider_name=self._label_text,
            value_is_int=self.value_is_int,
            current_lower=self._current_lower,
            current_upper=self._current_upper,
            fmt=self._value_fmt,
            min_limit=self._min_limit,
            max_limit=self._max_limit,
            min_limit_inclusive=self._min_limit_inclusive,
            max_limit_inclusive=self._max_limit_inclusive,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        new_pair = self._validate_pair(dlg.get_values())
        old_pair = self.get_value()
        old_default = self.get_default_value()

        needs_range_change = not (
            self._min_value <= new_pair[0] <= self._max_value
            and self._min_value <= new_pair[1] <= self._max_value
        )

        if needs_range_change:
            new_min = min(self._min_value, new_pair[0])
            new_max = max(self._max_value, new_pair[1])

            self.set_border(SliderBorderState.ERROR)
            try:
                result = range_slider_ask_extend_range(
                    proposed_vals=self._range_to_text(new_pair),
                    old_range=self._range_to_text((self._max_value, self._max_value)),
                    new_range=self._range_to_text((new_min, new_max)),
                    parent=self,
                )
            finally:
                self.set_border(SliderBorderState.OFF)
            if result != AskResult.YES:
                return

        self.set_value({"range": new_pair})

        if old_pair != self.get_value():
            self.valueChanged.emit(self.get_value())
        if old_default != self.get_default_value():
            self.defaultChanged.emit(self.get_default_value())

    def _apply_mode(self):
        """Apply the current values-vs-margins operating mode."""
        use_margins = self._use_margins
        self._set_right_click_item_checked("use_margins", use_margins)
        self._set_right_click_item_checked("use_values", not use_margins)

        self._set_right_click_item_enabled("set_margins", use_margins)
        self._set_right_click_item_enabled("set_values", not use_margins)
        self._set_right_click_item_enabled("save_as_default", not use_margins)
        self._set_right_click_item_enabled("reset_to_default", not use_margins)

        widgets = [
            self._slider,
            self._min_label,
            self._max_label,
            self._value_wrap,
        ]

        for w in widgets:
            w.setEnabled(not use_margins)

        if hasattr(self, "_right_click_overlay"):
            self._right_click_overlay.sync_to_target()

        self.valueChanged.emit(self.get_value())

    def _open_set_margins_dialog(self) -> None:
        """Open the margins dialog and apply accepted changes."""
        dlg = SetMarginsDialog(
            slider_name=self._label_text,
            margin_lower=self._margin_lower,
            margin_upper=self._margin_upper,
        )
        if dlg.exec() != QDialog.Accepted:
            return

        new_margin_lo, new_margin_up = dlg.get_values()

        if not (new_margin_lo == self._margin_lower and new_margin_up == self._margin_upper):
            self._margin_lower = new_margin_lo
            self._margin_upper = new_margin_up
            self.valueChanged.emit(self.get_value())

    def get_config(self) -> dict:
        """Return the current configuration mapping.

        Returns:
            Configuration dictionary containing numeric bounds, display format,
            and range-visibility state.
        """
        return {
            "min_val": self._min_value,
            "max_val": self._max_value,
            "val_fmt": self._value_fmt,
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

    def get_value(self) -> Dict[str, Any]:
        """Return the current values-and-margins state.

        Returns:
            Mapping containing the active mode, finite range values, and margins.
        """
        return {
            "use_margins": self._use_margins,
            "range": (self._current_lower, self._current_upper),
            "margins": (self._margin_lower, self._margin_upper),
        }

    def get_current_value(self) -> Tuple[TNum, TNum]:
        """Return the current finite lower and upper values."""
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
        """Set the current state of the range slider.

        Args:
            value: Mapping containing ``use_margins``, ``range``, and
                optionally ``margins``.
            keep_default_value: Whether to preserve the stored default range.
        """
        self._use_margins = value.get("use_margins", self._use_margins)
        self._set_right_click_item_checked("use_margins", self._use_margins)
        self._set_right_click_item_checked("use_values", not self._use_margins)
        range_values = value.get("range", (self._current_lower, self._current_upper))
        self._margin_lower, self._margin_upper = value.get(
            "margins",
            (self._margin_lower, self._margin_upper),
        )
        lo, hi = self._validate_pair(range_values)
        self._current_lower = lo
        self._current_upper = hi
        if not keep_default_value:
            self._default_lower = lo
            self._default_upper = hi

        cfg_changed = False
        if lo < self._min_value:
            self._min_value = lo
            cfg_changed = True
        if hi > self._max_value:
            self._max_value = hi
            cfg_changed = True

        self._slider.blockSignals(True)
        try:
            self._slider.setRange(float(self._min_value), float(self._max_value))
            self._slider.setValues((float(lo), float(hi)))
        finally:
            self._slider.blockSignals(False)

        self._update_all_labels()
        self._update_value_width()
        self._apply_mode()

        if cfg_changed:
            self.configChanged.emit(self.get_config())

    def set_default_value(self, value: Tuple[TNum, TNum]) -> None:
        """Set the stored default lower and upper values.

        Args:
            value: New default lower and upper values.
        """
        lo, hi = self._validate_pair(value)
        self._default_lower = lo
        self._default_upper = hi

        cfg_changed = False
        if lo < self._min_value:
            self._min_value = lo
            cfg_changed = True
        if hi > self._max_value:
            self._max_value = hi
            cfg_changed = True

        self._slider.blockSignals(True)
        try:
            self._slider.setRange(float(self._min_value), float(self._max_value))
            self._slider.setValues((float(self._current_lower), float(self._current_upper)))
        finally:
            self._slider.blockSignals(False)

        self._update_all_labels()
        self._update_value_width()

        if cfg_changed:
            self.configChanged.emit(self.get_config())

    def set_range(self, min_val: TNum, max_val: TNum) -> None:
        """Set the finite numeric range.

        Args:
            min_val: New minimum value.
            max_val: New maximum value.
        """
        min_val = self.evaluate_value(min_val)
        max_val = self.evaluate_value(max_val)

        self._validate_limit_one("min", min_val)
        self._validate_limit_one("max", max_val)

        if max_val < min_val:
            raise ValueError("max_val must be greater than min_val")

        self._min_value = min_val
        self._max_value = max_val

        new_cur_lo, new_cur_up = self._clamp_pair_to_range(
            (self._current_lower, self._current_upper),
            min_val,
            max_val,
        )
        cur_clamped = False
        if new_cur_lo != self._current_lower or new_cur_up != self._current_upper:
            self._current_lower = new_cur_lo
            self._current_upper = new_cur_up
            cur_clamped = True

        new_dft_lo, new_dft_up = self._clamp_pair_to_range(
            (self._default_lower, self._default_upper),
            min_val,
            max_val,
        )
        dft_clamped = False
        if new_dft_lo != self._default_lower or new_dft_up != self._default_upper:
            self._default_lower = new_dft_lo
            self._default_upper = new_dft_up
            dft_clamped = True

        self._slider.blockSignals(True)
        try:
            self._slider.setRange(float(min_val), float(max_val))
            self._slider.setValues((float(self._current_lower), float(self._current_upper)))
        finally:
            self._slider.blockSignals(False)

        self._update_all_labels()
        self._update_value_width()

        if cur_clamped:
            self.valueChanged.emit(self.get_value())

        if dft_clamped:
            self.defaultChanged.emit(self.get_default_value())

    def set_min_value(self, min_val: TNum) -> None:
        """Set only the minimum bound.

        Args:
            min_val: New minimum value.
        """
        self.set_range(min_val, self._max_value)

    def set_max_value(self, max_val: TNum) -> None:
        """Set only the maximum bound.

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
        editable: bool = True,
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
            margins: Initial lower and upper margins.
            show_range: Whether range labels and ticks should be shown.
            orientation: Slider orientation.
            editable: Whether configuration editing is enabled.
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
            editable=editable,
            parent=parent,
        )

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
        editable: bool = True,
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
            margins: Initial lower and upper margins.
            show_range: Whether range labels and ticks should be shown.
            orientation: Slider orientation.
            editable: Whether configuration editing is enabled.
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
            editable=editable,
            parent=parent,
        )

    def evaluate_value(self, value: float) -> float:
        """Normalize a float value using the evaluation format.

        Args:
            value: Float value to normalize.

        Returns:
            Normalized float value.
        """
        try:
            return float(self._eval_fmt.format(float(value)))
        except Exception:
            return float(value)


def _demo_main() -> int:
    """Run this module as a standalone demo.

    Returns:
        Qt application exit code.
    """
    import sys

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMainWindow

    from settings.app_style import set_app_style

    app = QApplication(sys.argv)
    set_app_style(app)

    win = QMainWindow()
    win.setWindowTitle("DualHandleSlider test")

    central = QWidget()
    outer_layout = QVBoxLayout(central)

    enable_cb = QCheckBox("Enable")
    enable_cb.setChecked(True)

    r1 = IntRangeSlider("n", 0, 100, init_vals=(20, 80))
    r2 = FloatRangeSlider("k", 5.0e4, 6.0e4, val_fmt="{:.8S}")
    r3 = FloatSlider("A_C", 0.0, 100.0)
    r4 = FloatRangeSlider(
        "B_D",
        0.0,
        100.0,
        init_vals=(30, 60),
        val_fmt="{:.1f}",
        orientation=Qt.Vertical,
    )
    r5 = FloatSlider("C_E", 0.0, 100.0, orientation=Qt.Vertical)

    def on_check(checked: bool):
        """Enable or disable all demo sliders.

        Args:
            checked: Checkbox state from Qt.
        """
        checked = enable_cb.isChecked()
        r1.setEnabled(checked)
        r2.setEnabled(checked)
        r3.setEnabled(checked)
        r4.setEnabled(checked)
        r5.setEnabled(checked)

    enable_cb.stateChanged.connect(on_check)

    sliders_layout = QHBoxLayout()

    left_layout = QVBoxLayout()
    left_layout.addWidget(r1)
    left_layout.addWidget(r2)
    left_layout.addWidget(r3)

    right_layout = QHBoxLayout()
    right_layout.addWidget(r4)
    right_layout.addWidget(r5)

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
