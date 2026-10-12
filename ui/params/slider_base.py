"""Shared base for labeled slider widgets (single-value and range sliders)."""

from __future__ import annotations

import re
from contextlib import contextmanager
from enum import Flag, auto
from typing import Any, Dict, Generic, List, Optional, TypeVar

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QMenu, QSizePolicy, QVBoxLayout, QWidget

from settings.app_style import SLIDER_BORDER_STYLE_SHEET, SliderBorderState
from settings.ui_defaults import SLIDER_LABEL_SIZE
from ui.labels import SvgLabel
from ui.params.parameter_widget_base import ParameterWidgetBase
from ui.right_click_overlay import RightClickOverlay
from utils.helper_funcs import get_numeric_format_field, value_to_text

T = TypeVar("T")

_SCI_PAT = r"\{:[0-9]*\.(\d+)S\}"


class SliderFeature(Flag):
    """Optional context-menu features of a slider.

    Each flag decides whether a group of menu items is offered at all.
    Sliders ignore flags that do not apply to them.

    Attributes:
        NONE: No menu and no default marker.
        DEFAULTS: "Save as Default" / "Reset to Default" and the default marker.
        SET_VALUE: "Set Value..." (or "Set Values..." on range sliders).
        CONFIG: "Edit Configuration...".
        SPECIAL: "Set Value to ±inf" (still subject to limits).
        VALUES: "Show Values..." (``MultiVariableSlider`` only).
        MARGINS: "Use Values" / "Use Margins" / "Set Margins..." (range
            sliders only).
        ALL: All of the above.
    """
    NONE = 0
    DEFAULTS = auto()
    SET_VALUE = auto()
    CONFIG = auto()
    SPECIAL = auto()
    VALUES = auto()
    MARGINS = auto()
    ALL = DEFAULTS | SET_VALUE | CONFIG | SPECIAL | VALUES | MARGINS

    @classmethod
    def from_json(cls, data: str | list[str] | None) -> "SliderFeature":
        """Build flags from a name, a list of names, or None (= ALL).

        Args:
            data: A feature name, a list of names, or None.

        Returns:
            Combined feature flags; ``ALL`` when ``data`` is None.

        Raises:
            ValueError: If a name is not a known feature.
        """
        if data is None:
            return cls.ALL
        names = [data] if isinstance(data, str) else data
        result = cls.NONE
        for name in names:
            try:
                result |= cls[name.strip().upper()]
            except KeyError:
                valid = ", ".join(m.name for m in cls)
                raise ValueError(f"unknown slider feature {name!r}; valid: {valid}") from None
        return result


class SliderWidgetBase(ParameterWidgetBase[T], Generic[T]):
    """Common frame for labeled sliders: label, inner slider, value display, menu.

    The base owns everything that does not depend on the kind of slider: the
    border, the context menu, the right-click overlay, the grid layout, range
    labels, format handling and name/value width bookkeeping. Subclasses build
    their inner slider and value display and fill in a few hooks.

    Subclass ``__init__`` order:
        1. ``super().__init__(...)``
        2. set up own state and the value-display widgets
        3. ``self._attach_slider(inner_slider)``
        4. ``self.set_format(val_fmt)``
        5. ``self._make_layout()``

    Signals ``valueChanged``, ``defaultChanged`` and ``configChanged`` are
    emitted only for user actions (dragging, context menu, dialogs).
    Programmatic setters never emit them.

    Widths: ``set_name_width`` / ``set_value_width`` store a requested minimum
    (for aligning sliders in a panel); the measured widths are kept separately
    and the layout uses the larger of the two. ``get_name_width`` /
    ``get_value_width`` return the measured widths.
    """

    _RANGE_MARGIN_H = 8
    """Slider top margin (px) when range labels are shown, horizontal layout."""
    _RANGE_MARGIN_V = 7
    """Slider left margin (px) when range labels are shown, vertical layout."""

    def __init__(
            self,
            label: str,
            orientation: Qt.Orientation,
            val_fmt: str,
            show_range: bool,
            features: SliderFeature,
            parent: Optional[QWidget],
    ):
        """Initialize the common slider frame.

        Args:
            label: Slider label shown next to the control.
            orientation: Slider orientation.
            val_fmt: Value display format string.
            show_range: Initial visibility of range labels and ticks; change
                later with ``set_show_range``.
            features: Context-menu features offered by the slider.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self.setObjectName("labeled_slider")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(SLIDER_BORDER_STYLE_SHEET)
        self.set_border(SliderBorderState.OFF)

        self._label_text = label
        self._orient = orientation
        self._show_range = show_range
        self._val_fmt = val_fmt
        self._eval_fmt = get_numeric_format_field(val_fmt)
        self._use_sci_html = False
        self._right_click_enable = True
        self._quiet = 0
        self._features = features

        self._slider: QWidget | None = None
        self._right_click_overlay: RightClickOverlay | None = None
        self._default_red_marker: QWidget | None = None
        self._gl: QGridLayout | None = None
        self._sl: QVBoxLayout | None = None

        self._name_label = SvgLabel(label, parent=self, font_size=SLIDER_LABEL_SIZE)
        self._min_label = QLabel()
        self._max_label = QLabel()
        self._min_label.setObjectName("slider_range")
        self._max_label.setObjectName("slider_range")

        self._right_click_items: List[Dict[str, Any]] = []
        if SliderFeature.DEFAULTS in features:
            self._right_click_items += [
                {"id": "save_as_default", "text": "Save as Default"},
                {"id": "reset_to_default", "text": "Reset to Default"},
            ]

        self._measured_name_width = self._name_label.sizeHint().width()

    # ----- hooks for subclasses -----
    def _make_default_marker(self) -> QWidget:
        """Create the overlay that marks the default value(s) on the slider.

        Called by ``_attach_slider`` only when ``DEFAULTS`` is set.

        Returns:
            Marker overlay widget (must provide ``update()``).
        """
        raise NotImplementedError

    def _value_widget(self) -> QWidget:
        """Return the widget showing the current value (and unit).

        Returns:
            Value-display widget placed in the layout.
        """
        raise NotImplementedError

    def _align_value_labels(self, horizontal: bool) -> None:
        """Set the alignment of the value label(s) for the orientation.

        Args:
            horizontal: Whether the layout is horizontal.
        """

    def _value_text_labels(self) -> List[QLabel]:
        """Return the labels that switch between plain and rich text.

        Returns:
            Labels whose text format follows the value format.
        """
        return [self._min_label, self._max_label]

    def _round_values_to_format(self) -> None:
        """Round the stored values to the current format (called by ``set_format``)."""

    def _apply_range_visibility(self, show: bool) -> None:
        """Show or hide the inner slider's ticks.

        Args:
            show: Whether range ticks should be shown.
        """

    def _update_value_width(self) -> None:
        """Measure the value display and call ``_set_measured_value_width``."""
        raise NotImplementedError

    # ----- setup helpers for subclasses -----
    def _attach_slider(self, slider: QWidget) -> None:
        """Register the inner slider and create its overlays.

        Args:
            slider: The inner slider widget.
        """
        self._slider = slider
        self._right_click_overlay = RightClickOverlay(
            target_widget=slider,
            owner_widget=self,
            parent=self,
        )
        self._right_click_overlay.hide()
        if SliderFeature.DEFAULTS in self._features:
            self._default_red_marker = self._make_default_marker()

    def _make_layout(self) -> None:
        """Build the grid layout for the current orientation."""
        gl = QGridLayout(self)
        gl.setContentsMargins(0, 0, 0, 0)

        slider_wrap = QWidget()
        sl = QVBoxLayout(slider_wrap)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        sl.addWidget(self._slider)

        value_widget = self._value_widget()

        if self._orient == Qt.Horizontal:
            gl.setVerticalSpacing(0)
            common = Qt.AlignVCenter
            self._name_label.setAlignment(common | Qt.AlignRight)
            self._align_value_labels(True)
            gl.addWidget(self._name_label, 0, 0, common | Qt.AlignRight)
            gl.addWidget(slider_wrap, 0, 1, 1, 3, common)
            gl.addWidget(value_widget, 0, 4, common | Qt.AlignLeft)
            gl.addWidget(self._min_label, 1, 1)
            gl.addWidget(self._max_label, 1, 3)

            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            gl.setColumnStretch(2, 1)
        else:
            gl.setHorizontalSpacing(0)
            gl.setVerticalSpacing(2)
            common = Qt.AlignHCenter
            self._align_value_labels(False)
            self._name_label.setAlignment(common | Qt.AlignTop)

            self._max_label.setContentsMargins(5, 0, 0, 0)
            self._min_label.setContentsMargins(5, 0, 0, 1)

            gl.addWidget(value_widget, 0, 0, 1, 3, common | Qt.AlignBottom)
            gl.addWidget(slider_wrap, 1, 1, 3, 1, common)
            gl.addWidget(self._name_label, 4, 0, 1, 3, common | Qt.AlignTop)
            gl.addWidget(self._max_label, 1, 2, 1, 2)
            gl.addWidget(self._min_label, 3, 2, 1, 2)

            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
            gl.setRowStretch(2, 1)

        self._gl = gl
        self._sl = sl
        self._sync_overlay()

    def _set_measured_value_width(self, new_w: int) -> None:
        """Store a newly measured value width, relayout, and report changes.

        Args:
            new_w: Measured width of the value display in pixels.
        """
        old_w = self._measured_value_width
        self._measured_value_width = new_w
        self._update_layout()
        if old_w != new_w:
            self.valueWidthChanged.emit(new_w)

    # ----- internal helpers -----
    def _sync_overlay(self) -> None:
        """Keep the right-click overlay aligned with the inner slider."""
        if self._right_click_overlay is not None:
            self._right_click_overlay.sync_to_target()

    @contextmanager
    def _quiet_updates(self):
        """Suppress user-action signals while code moves the slider."""
        self._quiet += 1
        try:
            yield
        finally:
            self._quiet -= 1

    def _update_eval_fmt(self) -> None:
        """Build a safe numeric format used for internal value normalization."""
        self._eval_fmt = get_numeric_format_field(self._val_fmt)

    def _value_to_text(self, value: Any) -> str:
        """Format a value for display.

        Args:
            value: Value to format.

        Returns:
            Formatted display string.
        """
        return value_to_text(value=value, fmt=self._val_fmt)

    def _update_layout(self) -> None:
        """Apply range visibility and width constraints to the layout."""
        if self._gl is None:
            return

        show_range = self._show_range
        self._apply_range_visibility(show_range)
        self._min_label.setVisible(show_range)
        self._max_label.setVisible(show_range)

        name_w = self._effective_name_width()
        value_w = self._effective_value_width()

        if self._orient == Qt.Horizontal:
            self._sl.setContentsMargins(0, self._RANGE_MARGIN_H if show_range else 0, 0, 0)
            self._gl.setColumnMinimumWidth(0, name_w)
            self._gl.setColumnMinimumWidth(4, value_w)
        else:
            self._sl.setContentsMargins(self._RANGE_MARGIN_V if show_range else 0, 0, 0, 0)
            width = max(name_w, value_w)
            slider_width = self._sl.sizeHint().width()
            self._gl.setColumnMinimumWidth(0, max(10, (width - slider_width) // 2))
            self._gl.setColumnMinimumWidth(1, slider_width)
            self._gl.setColumnMinimumWidth(2, max(10, (width - slider_width) // 2))

        self._gl.invalidate()
        widget = self._gl.parentWidget()
        if widget:
            widget.updateGeometry()
        self._sync_overlay()

    # ----- context menu -----
    def _set_right_click_item_checked(self, act_id, checked: bool) -> bool:
        """Update the stored checked state of a context-menu item.

        Args:
            act_id: Menu item identifier.
            checked: Checked state to store.

        Returns:
            ``True`` if the item was found, otherwise ``False``.
        """
        for item in self._right_click_items:
            if item.get("id") == act_id and act_id != "sep":
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
        for item in self._right_click_items:
            if item.get("id") == act_id and act_id != "sep":
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

    def save_current_value_as_default_value(self) -> None:
        """Store the current value as the default value (user action)."""

    def _reset_to_default_value(self) -> None:
        """Reset the control to its stored default value (user action)."""

    def _show_context_menu(self, global_pos) -> None:
        """Build and display the context menu.

        Args:
            global_pos: Global screen position where the menu should open.
        """
        if not self._right_click_enable:
            return
        if not any(item.get("id") != "sep" for item in self._right_click_items):
            return

        self.set_border(SliderBorderState.NORMAL)
        self.repaint()
        try:
            menu = QMenu()
            menu.setSeparatorsCollapsible(True)
            item_by_id = {}

            for item in self._right_click_items:
                act_id = item.get("id")
                if act_id == "sep":
                    menu.addSeparator()
                    continue

                text = str(item.get("text", act_id if act_id is not None else "None"))
                act = menu.addAction(text)
                act.setEnabled(bool(item.get("enabled", True)))
                checkable = bool(item.get("checkable", False))
                act.setCheckable(checkable)
                if checkable:
                    act.setChecked(bool(item.get("checked", False)))
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

    # ----- public API -----
    def set_format(self, val_fmt: str) -> None:
        """Set the display format and round stored values to it (no signals).

        Args:
            val_fmt: New format string.
        """
        self._val_fmt = val_fmt
        self._update_eval_fmt()
        self._round_values_to_format()

        self._use_sci_html = bool(re.search(_SCI_PAT, val_fmt))
        text_fmt = Qt.RichText if self._use_sci_html else Qt.PlainText
        for label in self._value_text_labels():
            label.setTextFormat(text_fmt)

    def set_border(self, state: SliderBorderState) -> None:
        """Set the visual border state of the widget.

        Args:
            state: Border state enum value.
        """
        self.setProperty("borderState", state.value)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_right_click_enabled(self, state: bool) -> None:
        """Enable or disable the whole context menu at runtime.

        Args:
            state: Whether right-click actions should be enabled.
        """
        self._right_click_enable = state

    def set_slider_enabled(self, enabled: bool) -> None:
        """Enable or disable the inner slider widget.

        Args:
            enabled: Whether the inner slider should be enabled.
        """
        self._slider.setEnabled(enabled)
        self._sync_overlay()

    def set_show_range(self, show: bool) -> None:
        """Show or hide the range labels and ticks.

        Args:
            show: Whether range labels and ticks should be shown.
        """
        show = bool(show)
        if show == self._show_range:
            return
        self._show_range = show
        self._update_layout()

    def set_label(self, label: str) -> None:
        """Set the displayed slider label.

        Args:
            label: New slider label text.
        """
        self._label_text = label
        self._name_label.set_text(label)
        self._measured_name_width = self._name_label.sizeHint().width()
        self._update_layout()
        self.nameWidthChanged.emit(self._measured_name_width)

    def get_value_width(self) -> int:
        """Re-measure and return the width of the value display.

        Returns:
            Width in pixels.
        """
        self.blockSignals(True)
        try:
            self._update_value_width()
        finally:
            self.blockSignals(False)
        return self._measured_value_width

    # ----- Qt events -----
    def contextMenuEvent(self, event) -> None:
        """Open the context menu.

        Args:
            event: Qt context-menu event.
        """
        self._show_context_menu(event.globalPos())

    def resizeEvent(self, event) -> None:
        """Keep the overlay aligned after a resize.

        Args:
            event: Qt resize event.
        """
        super().resizeEvent(event)
        self._sync_overlay()

    def showEvent(self, event) -> None:
        """Keep the overlay aligned after the widget is shown.

        Args:
            event: Qt show event.
        """
        super().showEvent(event)
        self._sync_overlay()

    def moveEvent(self, event) -> None:
        """Keep the overlay aligned after a move.

        Args:
            event: Qt move event.
        """
        super().moveEvent(event)
        self._sync_overlay()

    def changeEvent(self, event) -> None:
        """Handle enabled-state changes and refresh overlays.

        The inner slider's enabled state is deliberately not touched here:
        Qt propagates it from the parent, and modes that lock the slider
        (±inf, margins) rely on its explicit disable surviving a parent
        re-enable.

        Args:
            event: Qt change event.
        """
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange:
            self._sync_overlay()
            if self._default_red_marker is not None:
                self._default_red_marker.update()
            if not self.isEnabled():
                self.set_border(SliderBorderState.OFF)
            self.update()