"""Validated numeric line-edit widgets used throughout the GUI."""

from __future__ import annotations

import math
from typing import Optional, Callable

from PySide6.QtCore import Qt, Signal, QEvent, QTimer, QRegularExpression
from PySide6.QtGui import QMouseEvent, QValidator
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from dialogs.dialogs import show_warning
from utils.helper_funcs import pretty_sci_text

Num = int | float


class SciNumberValidator(QValidator):
    """Validator for integer and floating-point numeric input.

    The validator is permissive while the user is typing. Incomplete but still
    plausible input is reported as intermediate instead of invalid so editing
    is not blocked prematurely. For floating-point values, scientific notation
    is supported and non-finite values such as ``inf`` and ``nan`` are rejected.

    Attributes:
        _value_is_int: Whether the validator accepts integer values only.
        _text_to_format_value: Callable used to parse and normalize text input.
        _min_limit: Minimum allowed value after normalization.
        _max_limit: Maximum allowed value after normalization.
        _min_limit_inclusive: Whether the minimum bound is inclusive.
        _max_limit_inclusive: Whether the maximum bound is inclusive.
        _rx: Regular expression used for preliminary syntax validation.
    """

    def __init__(
            self,
            value_is_int: bool,
            text_to_format_value: Callable[[str], float],
            min_limit: int | float | None = None,
            max_limit: int | float | None = None,
            min_limit_inclusive: bool = True,
            max_limit_inclusive: bool = True,
            parent=None,
    ):
        """Initialize the numeric validator.

        Args:
            value_is_int: If ``True``, accept integer-style input only. If
                ``False``, accept floating-point input including scientific
                notation.
            text_to_format_value: Callable that parses text and returns the
                normalized numeric value used for range checking.
            min_limit: Optional lower bound for valid values.
            max_limit: Optional upper bound for valid values.
            min_limit_inclusive: Whether the lower bound is inclusive.
            max_limit_inclusive: Whether the upper bound is inclusive.
            parent: Optional Qt parent object.

        Raises:
            ValueError: If both bounds are provided and ``min_limit`` is
                greater than ``max_limit``.
        """
        super().__init__(parent)

        if min_limit is not None and max_limit is not None and min_limit > max_limit:
            raise ValueError("min_limit must be <= max_limit")

        self._value_is_int = value_is_int
        self._text_to_format_value = text_to_format_value
        self._min_limit = min_limit
        self._max_limit = max_limit
        self._min_limit_inclusive = min_limit_inclusive
        self._max_limit_inclusive = max_limit_inclusive

        if value_is_int:
            self._rx = QRegularExpression(r"^[+\-]?\d*$")
        else:
            self._rx = QRegularExpression(r"^[+\-]?((\d+(\.\d*)?)|(\.\d*)|(\d*))([eE][+\-]?\d*)?$")

    def validate(self, s: str, pos: int):
        """Validate the current text during editing.

        Empty strings and incomplete-but-plausible numeric input are treated as
        intermediate states so users can continue typing without immediate
        rejection.

        Args:
            s: Current input string being validated.
            pos: Cursor position supplied by Qt.

        Returns:
            tuple[QValidator.State, str, int]: Qt validator state together with
            the unchanged input string and cursor position.
        """
        t = s.strip()

        if t == "":
            return (QValidator.Intermediate, s, pos)

        if not self._rx.match(t).hasMatch():
            return (QValidator.Invalid, s, pos)

        try:
            v = self._text_to_format_value(t)
        except ValueError:
            return (QValidator.Intermediate, s, pos)

        if not self._value_is_int and not math.isfinite(v):
            return (QValidator.Invalid, s, pos)

        # Range -> Intermediate (do not block typing)
        if self._min_limit is not None:
            if self._min_limit_inclusive:
                if v < self._min_limit:
                    return (QValidator.Intermediate, s, pos)
            else:
                if v <= self._min_limit:
                    return (QValidator.Intermediate, s, pos)

        if self._max_limit is not None:
            if self._max_limit_inclusive:
                if v > self._max_limit:
                    return (QValidator.Intermediate, s, pos)
            else:
                if v >= self._max_limit:
                    return (QValidator.Intermediate, s, pos)

        return (QValidator.Acceptable, s, pos)


class NumericLineEdit(QLineEdit):
    """Line edit for validated numeric entry with commit gating.

    This widget combines a permissive validator for in-progress typing with
    stricter checks when the user attempts to commit or leave the field. It
    stores the last committed value, highlights invalid state, and prevents
    focus changes until invalid input is resolved.

    Signals:
        valueChanged: Emitted with the new committed numeric value.

    Attributes:
        _value_is_int: Whether the widget stores integer values only.
        _val_fmt: Format string used to display committed values.
        _parse: Conversion callable used to parse values.
        _min_limit: Optional normalized minimum bound.
        _max_limit: Optional normalized maximum bound.
        _min_limit_inclusive: Whether the lower bound is inclusive.
        _max_limit_inclusive: Whether the upper bound is inclusive.
        _filter_installed: Whether the global event filter is currently active.
        _invalid_property: Cached invalid-state flag mirrored to a Qt property.
        _in_refocus: Whether a refocus cycle is currently in progress.
        _skip_next_focus_out_check: Whether the next focus-out validation should
            be skipped.
        _reject_pending: Internal flag reserved for rejection bookkeeping.
        _last_value: Last successfully committed numeric value.
    """

    valueChanged = Signal(object)

    def __init__(
            self,
            init_val: Num,
            value_is_int: bool = False,
            val_fmt: str = "{:0.6g}",
            min_limit: Num | None = None,
            max_limit: Num | None = None,
            min_limit_inclusive: bool = True,
            max_limit_inclusive: bool = True,
            place_holder_text: str = "Enter a float",
            max_length: Optional[int] = None,
            width_chars: Optional[int] = None,
            parent: Optional[QWidget] = None
    ):
        """Initialize the numeric line edit.

        Args:
            init_val: Initial committed value shown in the widget.
            value_is_int: If ``True``, restrict input to integer values.
            val_fmt: Format string used to render committed values.
            min_limit: Optional lower bound for accepted values.
            max_limit: Optional upper bound for accepted values.
            min_limit_inclusive: Whether the lower bound is inclusive.
            max_limit_inclusive: Whether the upper bound is inclusive.
            place_holder_text: Placeholder text shown when the field is empty.
            max_length: Optional maximum character count for the line edit.
            width_chars: Optional fixed width expressed as a number of ``0``
                characters in the current font.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._value_is_int = value_is_int
        self._val_fmt = self._normalize_val_fmt(val_fmt)
        self._parse = int if value_is_int else float

        # Store bounds
        self._min_limit = min_limit if min_limit is None else self._value_to_formated_value(min_limit)
        self._max_limit = max_limit if max_limit is None else self._value_to_formated_value(max_limit)
        self._min_limit_inclusive = min_limit_inclusive
        self._max_limit_inclusive = max_limit_inclusive

        # StatusState
        self._filter_installed = False
        self._invalid_property = False
        self._in_refocus = False
        self._skip_next_focus_out_check = False
        self._reject_pending = False
        self._last_value: Num = init_val

        self.setValidator(self._make_validator())
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.installEventFilter(self)
        self.textEdited.connect(self._on_text_edited)
        self.editingFinished.connect(self._on_editing_finished)
        self.setPlaceholderText(place_holder_text)
        if max_length is not None:
            self.setMaxLength(max_length)
        if width_chars is not None:
            self.set_width_chars(width_chars)

        # Initialize
        self.set_value(init_val)

    # ----- subclass hooks -----
    def _make_validator(self) -> QValidator:
        """Create and configure the validator used by the widget.

        Returns:
            QValidator: Validator instance enforcing syntax and range rules for
            the current configuration.
        """
        return SciNumberValidator(
            value_is_int=self._value_is_int,
            text_to_format_value=self._text_to_formated_value,
            min_limit=self._min_limit,
            max_limit=self._max_limit,
            min_limit_inclusive=self._min_limit_inclusive,
            max_limit_inclusive=self._max_limit_inclusive,
            parent=self,
        )

    def _text_to_value(self, text: str) -> Num:
        """Parse raw text into a numeric value.

        Args:
            text: Input text to parse.

        Returns:
            Num: Parsed numeric value.
        """
        return self._parse(text.strip())

    def _value_to_text(self, value: Num) -> str:
        """Format a numeric value for display.

        Args:
            value: Numeric value to format.

        Returns:
            str: Formatted text representation.
        """
        return str(self._val_fmt.format(self._parse(value)))

    def _value_to_formated_value(self, value: Num) -> Num:
        """Normalize a numeric value through the display format.

        This applies the current formatting and then parses the formatted result
        back into a numeric value.

        Args:
            value: Numeric value to normalize.

        Returns:
            Num: Value after formatting and reparsing.
        """
        return self._text_to_value(self._value_to_text(value))

    def _text_to_formated_value(self, text: str) -> Num:
        """Normalize text input through parsing and formatting.

        Args:
            text: Input text to normalize.

        Returns:
            Num: Parsed value after applying the current formatting rules.
        """
        v = self._text_to_value(text)
        return self._text_to_value(self._value_to_text(v))

    def _normalize_val_fmt(self, val_fmt: str) -> str:
        """Normalize the format string used for display.

        Integer widgets always use ``"{:d}"``. Floating-point widgets fall back
        to ``"{:0.6g}"`` when the provided format string cannot be applied or
        does not produce a parseable numeric result.

        Args:
            val_fmt: Candidate format string.

        Returns:
            str: Sanitized format string suitable for display.
        """
        if self._value_is_int:
            return "{:d}"
        try:
            text = val_fmt.format(12345.12345)
        except Exception:
            return "{:0.6g}"

        try:
            float(text.replace(",", "").strip())
        except ValueError:
            return "{:0.6g}"

        return val_fmt.replace(",", "")

    def _validate_value(self, value: Num) -> Num:
        """Validate and normalize a programmatically supplied value.

        Args:
            value: Value to validate.

        Returns:
            Num: Normalized validated value.

        Raises:
            ValueError: If the value type is invalid or the normalized value is
                outside the configured bounds.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Invalid value: {value!r}")

        validated_value = self._value_to_formated_value(value)
        if not self._in_range(validated_value):
            raise ValueError(self._invalid_input_text_error("New value"))
        return validated_value

    def _apply_value(self, value: Num) -> None:
        """Apply a validated value to widget state and display.

        Args:
            value: Previously validated numeric value to store and display.
        """
        self._last_value = value
        text = self._value_to_text(value)
        self._set_invalid_property(False)
        self._set_text_safely(text)

    # ----- range -----
    def _in_range(self, v: Num) -> bool:
        """Check whether a value satisfies the configured bounds.

        Args:
            v: Value to test.

        Returns:
            bool: ``True`` if the value is inside the allowed interval.
        """
        if self._min_limit is not None:
            if v < self._min_limit:
                return False
            elif v == self._min_limit:
                return self._min_limit_inclusive

        if self._max_limit is not None:
            if v > self._max_limit:
                return False
            elif v == self._max_limit:
                return self._max_limit_inclusive

        return True

    def _invalid_input_text_error(self, value_text: str) -> str:
        """Build a concise error message describing valid bounds.

        Args:
            value_text: Label used to describe the invalid value in the message.

        Returns:
            str: Human-readable validation error string.
        """
        if self._min_limit is None and self._max_limit is None:
            return f"{value_text} is invalid."

        min_text = "-inf" if self._min_limit is None else pretty_sci_text(self._min_limit, sig_digits=3)
        max_text = "+inf" if self._max_limit is None else pretty_sci_text(self._max_limit, sig_digits=3)

        left = "[" if self._min_limit_inclusive else "("
        right = "]" if self._max_limit_inclusive else ")"
        return f"{value_text} must be in {left}{min_text}, {max_text}{right}"

    def _invalid_input_msg_error(self) -> str:
        """Build a detailed message for the invalid-input warning dialog.

        Returns:
            str: Multi-line validation message appropriate for user display.
        """
        text = self.text().strip()

        if text == "":
            return "Please enter a value."

        try:
            formated_v = self._text_to_formated_value(text)
        except ValueError:
            return (f"Input text: '{text}'\n"
                    f"Please enter a valid number.")

        if not self._in_range(formated_v):
            return (f"Input: '{text}'\n"
                    f"Format: {self._val_fmt}\n"
                    f"Value after apply format: {formated_v}\n"
                    f"{self._invalid_input_text_error('Input value')}")

        return "Please enter a valid value."

    # ----- validation helpers -----
    def _validation_state(self, text: str) -> QValidator.StatusState:
        """Return the validator state for the provided text.

        Args:
            text: Text to validate.

        Returns:
            QValidator.State: Validation state reported by the current validator.
        """
        v = self.validator()
        if v is None:
            return QValidator.Acceptable
        state, _, _ = v.validate(text, 0)
        return state

    def _can_commit(self) -> bool:
        """Return whether the current widget text can be committed.

        Returns:
            bool: ``True`` if the current text is fully acceptable.
        """
        return self._validation_state(self.text()) == QValidator.Acceptable

    # ----- UI state -----
    def _set_invalid_property(self, status: bool) -> None:
        """Update the Qt invalid-state property.

        Args:
            status: Desired invalid-state flag.
        """
        if self._invalid_property != status:
            self._invalid_property = status
            self.setProperty("invalid", status)
            self.update()

    def _set_text_safely(self, text: str) -> None:
        """Set widget text while temporarily blocking signals.

        Args:
            text: Text to assign to the line edit.
        """
        was_blocked = self.signalsBlocked()
        self.blockSignals(True)
        try:
            self.setText(text)
        finally:
            self.blockSignals(was_blocked)

    # ----- slots -----
    def _on_text_edited(self, text: str) -> None:
        """Update invalid styling while the user edits the text.

        Args:
            text: Current edited text.
        """
        self._set_invalid_property(self._validation_state(text) != QValidator.Acceptable)

    def _on_editing_finished(self) -> None:
        """Commit the edited value when the current text is acceptable."""
        if not self._can_commit():
            return

        new_value = self._text_to_formated_value(self.text())
        if new_value != self._last_value:
            self._last_value = new_value
            self._set_invalid_property(False)
            self._set_text_safely(self._value_to_text(new_value))
            self.valueChanged.emit(new_value)

    # ----- refocus / rejection -----
    def _refocus(self) -> None:
        """Restore focus to the widget and select all text."""
        self._in_refocus = True
        try:
            self.setFocus(Qt.OtherFocusReason)
            self.selectAll()
        finally:
            self._in_refocus = False

    def _reject_exit_ui(self) -> None:
        """Reject an invalid exit attempt and show a warning dialog."""
        self._set_invalid_property(True)
        show_warning("Invalid input", self._invalid_input_msg_error(), parent=self)
        self.setText(self._value_to_text(self._last_value))
        self._set_invalid_property(False)
        QTimer.singleShot(0, self._refocus)

    # ----- public API -----
    def get_value(self) -> Num:
        """Return the last committed value.

        Returns:
            Num: Last valid value stored by the widget.
        """
        return self._last_value

    def set_value(self, value: Num) -> None:
        """Validate and assign a new current value.

        Args:
            value: New value to store and display.

        Raises:
            ValueError: If the provided value is invalid or outside the
                configured bounds.
        """
        validated_value = self._validate_value(value)
        self._apply_value(validated_value)

    def set_width_chars(self, chars: int, pad: int = 8) -> None:
        """Set a fixed widget width based on character count.

        Args:
            chars: Number of ``0`` characters to size the field for.
            pad: Extra pixel padding added to the computed text width.
        """
        fm = self.fontMetrics()
        self.setFixedWidth(fm.horizontalAdvance("0" * chars) + pad)

    def set_fmt(self, fmt: str) -> None:
        """Update the display format and refresh the committed value.

        Args:
            fmt: New format string to apply.
        """
        self._val_fmt = self._normalize_val_fmt(fmt)
        self._on_editing_finished()

    # ----- focus/exit gating -----
    def focusInEvent(self, event) -> None:
        """Handle the Qt focus-in callback.

        Installs a global event filter while the widget has focus so outside
        mouse clicks can be intercepted and treated as commit or reject events.

        Args:
            event: Qt focus event.
        """
        super().focusInEvent(event)
        if not self._filter_installed:
            QApplication.instance().installEventFilter(self)
            self._filter_installed = True

    def focusOutEvent(self, event) -> None:
        """Handle the Qt focus-out callback.

        Invalid text prevents focus loss. Depending on the focus-change reason,
        the event may be allowed, ignored, or converted into a rejection flow.

        Args:
            event: Qt focus event.
        """
        if self._skip_next_focus_out_check:
            self._skip_next_focus_out_check = False
            super().focusOutEvent(event)
            if self._filter_installed:
                QApplication.instance().removeEventFilter(self)
                self._filter_installed = False
            return

        if self._in_refocus:
            super().focusOutEvent(event)
            return

        if event.reason() in (Qt.PopupFocusReason, Qt.ActiveWindowFocusReason, Qt.MenuBarFocusReason):
            super().focusOutEvent(event)
            if self._filter_installed:
                QApplication.instance().removeEventFilter(self)
                self._filter_installed = False
            return

        if not self._can_commit():
            event.ignore()
            self._reject_exit_ui()
            return

        super().focusOutEvent(event)
        if self._filter_installed:
            QApplication.instance().removeEventFilter(self)
            self._filter_installed = False

    def keyPressEvent(self, event) -> None:
        """Handle the Qt key-press callback for commit-sensitive keys.

        Enter, Return, Tab, and Backtab are intercepted so invalid text cannot
        be committed or escaped accidentally.

        Args:
            event: Qt key event.
        """
        key = event.key()

        if key in (Qt.Key_Return, Qt.Key_Enter):
            if not self._can_commit():
                event.accept()
                self._reject_exit_ui()
                return
            super().keyPressEvent(event)
            return

        if key in (Qt.Key_Tab, Qt.Key_Backtab):
            if not self._can_commit():
                event.accept()
                self._reject_exit_ui()
                return
            self.focusNextPrevChild(key == Qt.Key_Tab)
            return

        super().keyPressEvent(event)

    def eventFilter(self, obj, event) -> bool:
        """Filter application events while the widget has focus.

        Outside mouse clicks are interpreted as exit attempts. Invalid input is
        rejected and the click is consumed; valid input is allowed to continue.

        Args:
            obj: Watched Qt object.
            event: Incoming Qt event.

        Returns:
            bool: ``True`` if the event is consumed by this widget, otherwise
            ``False``.
        """
        if not self.hasFocus() or self._in_refocus:
            return False

        if event.type() == QEvent.MouseButtonPress and isinstance(event, QMouseEvent):
            gp = event.globalPosition().toPoint()
            w = QApplication.widgetAt(gp)
            if w is None:
                return False

            if w is self or self.isAncestorOf(w):
                return False

            # Click outside: treat as exit attempt
            if not self._can_commit():
                self._reject_exit_ui()
                return True  # consume click

            self._skip_next_focus_out_check = True
            self.clearFocus()
            return False

        return False


def _demo_main() -> int:
    """Run this module as a standalone demo application.

    Returns:
        int: Qt application exit code.
    """
    import sys
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLabel, QPushButton
    from settings.app_style import set_app_style

    app = QApplication(sys.argv)
    set_app_style(app)
    # app.setStyleSheet("QWidget { border: 1px solid red; }")

    w = QWidget()
    w.setWindowTitle("Numeric Line Edit Demo")

    f_edit = NumericLineEdit(
        init_val=1.0,
        val_fmt="{:0.3g}",
        min_limit=-100.0,
        # max_limit=100.0,
        # max_limit_inclusive=False,
        width_chars=11,
        max_length=10
    )

    i_edit = NumericLineEdit(
        init_val=1,
        value_is_int=True,
        min_limit=-100,
        max_limit=100,
        width_chars=10,
        max_length=9
    )

    valid_value_label = QLabel("")
    btn = QPushButton("OK")
    btn.clicked.connect(lambda val: print(f"val: {val}"))

    layout = QVBoxLayout(w)
    form = QFormLayout()
    form.addRow("Integer:", i_edit)
    form.addRow("Float:", f_edit)
    form.addRow("Valid Value:", valid_value_label)
    layout.addLayout(form)
    layout.addWidget(btn)

    i_edit.valueChanged.connect(lambda val: valid_value_label.setText(str(val)))
    f_edit.valueChanged.connect(lambda val: valid_value_label.setText(str(val)))

    w.resize(320, 150)
    w.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
