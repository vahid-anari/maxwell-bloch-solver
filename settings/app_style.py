"""Application styling, palette tweaks, and GUI metadata.

The helpers in this module centralize Qt style configuration and small UI
constants used across the application.
"""

from __future__ import annotations

import shutil
from enum import Enum
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QProxyStyle,
    QStyle,
    QStyleFactory,
    QStyleOptionSlider,
)

USE_LATEX = shutil.which("latex") is not None
"""Whether a LaTeX executable is available on the current system."""

EXPORT_PLOT_PAD_INCHES = 0.5
"""Padding, in inches, used when exporting plots."""

VELOCITY_COMBO_WIDTH = 100
"""Default fixed width, in pixels, for velocity combo boxes."""

SHOW_WIDGET_RED_BORDER = False
"""Whether to draw a red debug border around every widget."""

SCALING_PARAMS_MAP_GROUP_ID_TO_LABEL = {
    "input": "Input",
    "shared": "Shared",
    "electric": "Electronic",
    "magnetic": "Magnetic",
}
"""Map scaling-parameter group identifiers to display labels."""

SLIDER_BORDER_STYLE_SHEET = """
        QWidget#labeled_slider[borderState="normal"] {
            border: 1px solid gray;
            border-radius: 3px;
            background: transparent;
        }
        QWidget#labeled_slider[borderState="error"] {
            border: 1px solid red;
            border-radius: 3px;
            background: transparent;
        }
        QWidget#labeled_slider[borderState="off"] {
            border: 0px;
        }
        """
"""Style sheet fragment used for custom slider border states."""


class SliderBorderState(str, Enum):
    """State values used when drawing custom slider borders."""

    OFF = "off"
    NORMAL = "normal"
    ERROR = "error"


def set_app_style(app: QApplication):
    """Apply the project's custom Qt style configuration.

    Args:
        app: Running Qt application instance to style.
    """

    app.setStyle(AppStyleProxy())
    f = app.font()
    fs = f.pointSize()
    fm = f.family()

    def _make_style_sheet(w_name: str, add: int, color: Optional[str] = None) -> str:
        """Build a widget-specific style-sheet fragment.

        Args:
            w_name: Qt widget selector name.
            add: Font-size offset, in points, relative to the application font.
            color: Optional text color.

        Returns:
            CSS-like Qt style-sheet fragment for the requested widget selector.
        """

        if color is not None:
            c = QColor(color)
            c_disabled = QColor(color)
            c_disabled.setAlpha(50)
            s = f"{w_name}{{"
            s += f"font-size: {fs + add}pt; "
            s += f"font-family: {fm};"
            s += f"color: {c.name()};"
            s += "}"
            s += f"{w_name}:disabled{{"
            s += f"color: {c_disabled.name(QColor.HexArgb)};}}"
        else:
            s = f"{w_name}{{"
            s += f"font-size: {fs + add}pt; "
            s += f"font-family: {fm};"
            s += "}"
        return s

    s = ""
    s += _make_style_sheet("QLabel#slider_value", add=1, color="blue")
    s += _make_style_sheet("QLabel#slider_range", add=-1, color="black")
    s += _make_style_sheet("QLabel#chi_value", add=1, color="black")
    s += _make_style_sheet("QLineEdit", add=1, color="blue")
    s += _make_style_sheet("QSpinBox", add=1, color="blue")
    s += "QStatusBar {border-top: 1px solid #999999;}"
    s += """QGroupBox {
                    font-size: 16pt;
                    font-family: "Times New Roman";
                    font-weight: bold;
                    border: 1px solid #bcbcbc;
                    border-radius: 6px;
                    margin-top: 12px;
                    padding-top: 8px;
                    background: white;
            }"""
    s += """QGroupBox#no_title {
                    margin: 0 0 0 0;
                    padding: 0 0 0 0;
                }"""
    s += """QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                bottom: -3px;
                padding: 0 4px 0 4px;
            }"""
    if SHOW_WIDGET_RED_BORDER:
        s += "QWidget { border: 1px solid red;}"

    app.setStyleSheet(s)


class AppStyleProxy(QProxyStyle):
    """Qt style proxy that customizes selected control-drawing details."""

    def __init__(self):
        """Initialize the proxy style with Fusion as the base style."""

        base = QStyleFactory.create("Fusion")
        super().__init__(base)

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        """Return a Qt style hint for the requested control.

        Args:
            hint: Requested style-hint identifier.
            option: Optional style option associated with the request.
            widget: Optional widget associated with the request.
            returnData: Optional return-data holder supplied by Qt.

        Returns:
            Style-hint value for the requested control.
        """

        if hint == QStyle.SH_Slider_AbsoluteSetButtons:
            return Qt.LeftButton.value
        if hint == QStyle.SH_Slider_PageSetButtons:
            return 0
        return super().styleHint(hint, option, widget, returnData)

    def drawComplexControl(self, control, option, painter, widget=None):
        """Draw a customized Qt complex control.

        Args:
            control: Complex-control type to draw.
            option: Style option describing the control state.
            painter: Painter used for rendering.
            widget: Optional widget being drawn.
        """

        if control == QStyle.CC_Slider and isinstance(option, QStyleOptionSlider):
            if not (option.state & QStyle.State_Enabled):
                requested = option.subControls
                if requested == QStyle.SC_None:
                    requested = (
                        QStyle.SC_SliderGroove
                        | QStyle.SC_SliderHandle
                        | QStyle.SC_SliderTickmarks
                    )

                if requested & QStyle.SC_SliderGroove:
                    groove_rect = self.subControlRect(
                        QStyle.CC_Slider,
                        option,
                        QStyle.SC_SliderGroove,
                        widget,
                    )

                    painter.save()
                    painter.setPen(QPen(QColor("#b3b3b3"), 1))
                    painter.setBrush(QColor("#cccccc"))
                    r = groove_rect.adjusted(1, 2, -1, -1)
                    painter.drawRoundedRect(r, 1, 1)
                    painter.restore()

                fg = requested & (QStyle.SC_SliderTickmarks | QStyle.SC_SliderHandle)
                if fg:
                    opt_fg = QStyleOptionSlider(option)
                    opt_fg.subControls = fg
                    super().drawComplexControl(control, opt_fg, painter, widget)

                return

            return super().drawComplexControl(control, option, painter, widget)

        return super().drawComplexControl(control, option, painter, widget)

    def drawPrimitive(self, element, option, painter, widget=None):
        """Draw a customized Qt primitive element.

        Args:
            element: Primitive-element type to draw.
            option: Style option describing the primitive state.
            painter: Painter used for rendering.
            widget: Optional widget being drawn.
        """

        super().drawPrimitive(element, option, painter, widget)

        if element == QStyle.PE_PanelLineEdit and isinstance(widget, QLineEdit):
            if (option.state & QStyle.State_Enabled) and bool(widget.property("invalid")):
                painter.save()
                try:
                    pen = QPen(QColor("#d32f2f"))
                    pen.setWidth(3)
                    pen.setCapStyle(Qt.RoundCap)
                    pen.setJoinStyle(Qt.RoundJoin)
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)
                    r = option.rect.adjusted(1, 1, -1, -1)
                    painter.drawRect(r)
                finally:
                    painter.restore()
