"""Common base class for parameter widgets with value and config signals."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

T = TypeVar("T")


class ParameterWidgetBase(QWidget, Generic[T]):
    """Provide a common interface for parameter widgets.

    This base class defines a shared API for widgets that manage a typed value,
    optional configuration data, and layout-related width settings. Subclasses
    are expected to implement value retrieval and application logic, and may
    optionally extend the configuration behavior.

    Attributes:
        valueChanged: Emitted when the widget's value changes.
        defaultChanged: Emitted when the widget's default value changes.
        configChanged: Emitted when the widget's configuration changes.
        valueWidthChanged: Emitted when the value display width changes.
        nameWidthChanged: Emitted when the name display width changes.
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
        self._name_width: int = 0
        self._value_width: int = 0

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
        """Return the current width reserved for the name label.

        Returns:
            Name-label width in pixels.
        """

        return self._name_width

    def get_value_width(self) -> int:
        """Return the current width reserved for the value area.

        Returns:
            Value-area width in pixels.
        """

        return self._value_width

    def set_name_width(self, width: int) -> None:
        """Set the width reserved for the name label.

        Args:
            width: New name-label width in pixels.
        """

        self._name_width = int(width)
        self._update_layout()

    def set_value_width(self, width: int) -> None:
        """Set the width reserved for the value area.

        Args:
            width: New value-area width in pixels.
        """

        self._value_width = int(width)
        self._update_layout()
