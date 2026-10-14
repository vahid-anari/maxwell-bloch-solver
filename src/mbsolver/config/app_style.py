"""Application styling, palette tweaks, and GUI metadata.

The helpers in this module centralize Qt style configuration and small UI
constants used across the application.
"""

from __future__ import annotations

import shutil
from typing import Optional

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from sciwidgets.style import apply_sci_style

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


def set_app_style(app: QApplication):
    """Apply the project's custom Qt style configuration.

    Args:
        app: Running Qt application instance to style.
    """

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
    s += _make_style_sheet("QLabel#chi_value", add=1, color="black")
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

    apply_sci_style(app, s)
