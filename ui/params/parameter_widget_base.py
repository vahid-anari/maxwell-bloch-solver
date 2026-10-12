"""Common base class for parameter widgets with value and config signals."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

T = TypeVar("T")


class ParameterWidgetBase(QWidget, Generic[T]):
    """Provide a common interface for parameter widgets.

    Attributes:
        valueChanged: Emitted when the user changes the value.
        defaultChanged: Emitted when the user changes the default value.
        configChanged: Emitted when the user changes the configuration.
        valueWidthChanged: Emitted when the value display width changes.
        nameWidthChanged: Emitted when the name display width changes.

    Note:
        ``valueChanged``, ``defaultChanged`` and ``configChanged`` are for
        user actions only; programmatic setters such as ``set_value`` and
        ``set_config`` do not emit them.
    """

    valueChanged = Signal(object)
    defaultChanged = Signal(object)
    configChanged = Signal(object)
    valueWidthChanged = Signal(int)
    nameWidthChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the base parameter widget.

        Args:
            parent: Optional parent widget.
        """

        super().__init__(parent)
        self._name_width: int = 0  # requested via set_name_width
        self._value_width: int = 0  # requested via set_value_width
        self._measured_name_width: int = 0  # set by subclasses
        self._measured_value_width: int = 0  # set by subclasses

    def _update_layout(self) -> None:
        """Update the widget layout to reflect the current internal state.

        Subclasses should override this method when name or value width changes
        require a visual layout update.
        """

        pass

    def get_value(self) -> T:
        """Return the current widget value.

        Returns:
            The current typed value stored by the widget.

        Raises:
            NotImplementedError: If the subclass does not implement value
                retrieval.
        """

        raise NotImplementedError

    def set_value(self, value: T) -> None:
        """Validate and apply a new widget value.

        Args:
            value: New value to store in the widget.
        """

        validated = self._validate_value(value)
        self._apply_value(validated)

    def _validate_value(self, value: T) -> T:
        """Validate a candidate value before applying it.

        The default implementation returns the value unchanged. Subclasses can
        override this method to enforce type, range, or domain-specific checks.

        Args:
            value: Candidate value to validate.

        Returns:
            Validated value, possibly normalized.
        """

        return value

    def _apply_value(self, value: T) -> None:
        """Apply a validated value to the widget state.

        Args:
            value: Previously validated value to store.

        Raises:
            NotImplementedError: If the subclass does not implement value
                application.
        """

        raise NotImplementedError

    def get_config(self) -> dict[str, Any]:
        """Return the current configuration mapping.

        Returns:
            Configuration dictionary for the widget. The base implementation
            returns an empty mapping.
        """

        return {}

    def set_config(self, config: dict[str, Any]) -> None:
        """Validate and apply configuration values.

        Args:
            config: Partial or complete configuration mapping to apply.
        """

        validated = self._validate_config(config)
        self._apply_config(validated)

    def _validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize a configuration mapping.

        The base implementation requires ``config`` to be a dictionary and
        merges it with the current configuration, preserving existing values for
        missing keys.

        Args:
            config: Candidate configuration mapping.

        Returns:
            Normalized configuration dictionary.

        Raises:
            TypeError: If ``config`` is not a dictionary.
        """

        if not isinstance(config, dict):
            raise TypeError(f"config must be dict, got {type(config).__name__}")
        old_config = self.get_config()
        new_config = {}
        for k, v in old_config.items():
            if k not in config:
                new_config[k] = v
            else:
                new_config[k] = config[k]
        return new_config

    def _apply_config(self, config: dict[str, Any]) -> None:
        """Apply a validated configuration mapping.

        Subclasses can override this method to store configuration state and
        update the widget accordingly.

        Args:
            config: Previously validated configuration mapping.
        """

        _ = config

    def get_name_width(self) -> int:
        """Return the measured width of the name label.

        Returns:
            Width in pixels.
        """
        return self._measured_name_width

    def get_value_width(self) -> int:
        """Return the measured width of the value area.

        Returns:
            Width in pixels.
        """
        return self._measured_value_width

    def _effective_name_width(self) -> int:
        """Return the width the layout should reserve for the name label."""
        return max(self._name_width, self._measured_name_width)

    def _effective_value_width(self) -> int:
        """Return the width the layout should reserve for the value area."""
        return max(self._value_width, self._measured_value_width)

    def set_name_width(self, width: int) -> None:
        """Set a requested minimum width for the name label.

        Used to align several widgets in a panel. The layout reserves the
        larger of this value and the label's own measured width, so a smaller
        request never cuts the label. ``get_name_width`` still returns the
        measured width.

        Args:
            width: Requested minimum width in pixels.
        """

        self._name_width = int(width)
        self._update_layout()

    def set_value_width(self, width: int) -> None:
        """Set a requested minimum width for the value area.

        Used to align several widgets in a panel. The layout reserves the
        larger of this value and the value area's own measured width, so a
        smaller request never cuts the value. ``get_value_width`` still
        returns the measured width.

        Args:
            width: Requested minimum width in pixels.
        """

        self._value_width = int(width)
        self._update_layout()
