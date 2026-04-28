"""Transparent overlay that translates clicks into context-menu actions."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QWidget


class RightClickOverlay(QWidget):
    """Transparent overlay that forwards clicks as context-menu requests.

    The overlay is positioned over a target widget when needed. Mouse input on the
    overlay is consumed so the underlying widget does not receive it directly. A
    right-click release is translated into a context-menu request on the owner
    widget.
    """

    def __init__(
        self,
        target_widget: QWidget,
        owner_widget: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the overlay.

        Args:
            target_widget: Widget whose geometry is mirrored by the overlay.
            owner_widget: Widget that handles the forwarded context-menu request.
            parent: Parent widget that contains the overlay.
        """
        super().__init__(parent)
        self._target_widget = target_widget
        self._owner_widget = owner_widget

        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.raise_()

    def sync_to_target(self) -> None:
        """Sync the overlay geometry and visibility with the target widget.

        The overlay is hidden when no target widget is available or when the
        target widget is enabled. Otherwise, the overlay is resized and moved to
        cover the target widget within the parent coordinate system.
        """
        if self._target_widget is None or self._target_widget.isEnabled():
            self.hide()
            return

        parent = self.parentWidget()
        if parent is None:
            return

        pos = self._target_widget.mapTo(parent, QPoint(0, 0))
        self.setGeometry(
            pos.x(),
            pos.y(),
            self._target_widget.width(),
            self._target_widget.height(),
        )
        self.raise_()
        self.show()

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse-release events on the overlay.

        Args:
            event: Qt mouse event received by the overlay.

        A right-button release is forwarded to the owner widget as a context-menu
        request using the global cursor position.
        """
        if event.button() == Qt.RightButton:
            self._owner_widget._show_context_menu(event.globalPosition().toPoint())
        event.accept()

    def paintEvent(self, event) -> None:
        """Handle paint events for the overlay.

        Args:
            event: Qt paint event.

        The overlay is intentionally transparent and does not draw any content.
        """
        pass

    def mousePressEvent(self, event) -> None:
        """Handle mouse-press events on the overlay.

        Args:
            event: Qt mouse event.

        The event is accepted so the underlying widget does not process it.
        """
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        """Handle mouse double-click events on the overlay.

        Args:
            event: Qt mouse event.

        The event is accepted so the underlying widget does not process it.
        """
        event.accept()

    def contextMenuEvent(self, event) -> None:
        """Handle context-menu events on the overlay.

        Args:
            event: Qt context-menu event.

        The event is accepted because context-menu handling is managed through the
        mouse-release forwarding logic.
        """
        event.accept()
