"""Small helpers shared by the pulse and step widgets.

Kept next to the widgets (not in ``mbsolver.utils``) so that the two widgets
depend only on Qt, sciwidgets and this file, and can move to another package
together.
"""

from __future__ import annotations

import shutil

from PySide6.QtWidgets import QGroupBox, QLayout

USE_LATEX = shutil.which("latex") is not None
"""Whether a LaTeX executable is available (some formulas need full LaTeX)."""


def make_box(layout: QLayout) -> QGroupBox:
    """Wrap a layout in an untitled group box.

    The box gets the object name ``no_title``, which the app style sheet uses
    to remove the title margin.
    """
    box = QGroupBox("")
    box.setObjectName("no_title")
    box.setLayout(layout)
    return box
