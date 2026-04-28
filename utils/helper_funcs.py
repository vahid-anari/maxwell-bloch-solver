"""Small GUI, formatting, and JSON helpers used throughout the project."""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, Literal

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLayout,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)


def pretty_sci_text(
    value: float,
    sig_digits: int = 3,
    notation: Literal["plain", "html", "latex"] = "html",
) -> str:
    """Format a float using scientific notation when appropriate.

    Args:
        value: Numeric value to format.
        sig_digits: Number of significant digits. Must be at least 1.
        notation: Output style. Supported values are ``"plain"``, ``"html"``,
            and ``"latex"``.

    Returns:
        Formatted numeric string.

    Note:
        - Zero is returned as ``"0"``.
        - Values with magnitude in ``[1, 10**sig_digits)`` are shown in ordinary
          significant-digit form unless Python switches to exponent notation
          after rounding.
        - Other values are shown in mantissa-times-ten-to-the-power form.
    """
    if sig_digits < 1:
        raise ValueError("sig_digits must be >= 1")

    if notation not in {"plain", "html", "latex"}:
        raise ValueError("notation must be 'plain', 'html', or 'latex'")

    if value == 0:
        return "0"

    av = abs(value)

    if 1 <= av < 10**sig_digits:
        s = f"{value:.{sig_digits}g}"
        if "e" not in s and "E" not in s:
            if "." in s:
                int_part, frac_part = s.split(".", 1)
                return f"{int(int_part):,d}.{frac_part}"
            return f"{int(s):,d}"

    s = f"{value:.{sig_digits - 1}e}"
    mant_str, exp_str = s.split("e", 1)
    exp = int(exp_str)

    if notation == "html":
        return f"{mant_str}×10<sup>{exp}</sup>"
    if notation == "latex":
        return rf"{mant_str}	imes 10^{{{exp}}}"
    return f"{mant_str}×10^{exp}"


def read_json(path: str) -> dict:
    """Read a JSON file and return the parsed object.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed JSON object.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cut_y_by_x(x, y, xmin, xmax):
    """Return the subset of ``y`` whose ``x`` values lie within a given range.

    Args:
        x: X-coordinate array.
        y: Y-coordinate array with the same shape as ``x``.
        xmin: Lower bound of the allowed x-range.
        xmax: Upper bound of the allowed x-range.

    Returns:
        Subset of ``y`` corresponding to positions where ``xmin <= x <= xmax``.

    Raises:
        ValueError: If ``x`` and ``y`` do not have the same shape.
    """
    x = np.asarray(x)
    y = np.asarray(y)

    if x.shape != y.shape:
        raise ValueError("x and y must have the same shape")

    mask = (x >= xmin) & (x <= xmax)
    return y[mask]


def get_range(limits, arr1, arr2=None):
    """Return a safe numeric range from explicit limits or data-driven margins.

    Args:
        limits: Mapping containing either an explicit ``range`` entry or a
            ``use_margins`` flag with ``margins`` percentages.
        arr1: Primary data array used for data-driven limits.
        arr2: Optional secondary data array used for data-driven limits.

    Returns:
        Tuple ``(r_min, r_max)`` representing a safe numeric range.
    """

    def _finite_1d(arr):
        """Return a flattened array containing only finite values."""
        if arr is None:
            return np.empty(0, dtype=float)

        a = np.asarray(arr, dtype=float).ravel()
        if a.size == 0:
            return a

        return a[np.isfinite(a)]

    def _expand_if_degenerate(vmin, vmax):
        """Expand a degenerate interval into a small nonzero range."""
        if vmax == vmin:
            delta = 1.0 if vmin == 0 else 0.1 * abs(vmin)
            vmin -= delta
            vmax += delta
        return vmin, vmax

    if limits.get("use_margins", False):
        m_lo, m_hi = limits.get("margins", (10, 10))

        a1 = _finite_1d(arr1)
        a2 = _finite_1d(arr2)

        arrays = [a for a in (a1, a2) if a.size > 0]

        if not arrays:
            return 0.0, 1.0

        v_min = min(np.min(a) for a in arrays)
        v_max = max(np.max(a) for a in arrays)

        v_min, v_max = _expand_if_degenerate(v_min, v_max)

        span = v_max - v_min
        r_min = v_min - span * m_lo * 0.01
        r_max = v_max + span * m_hi * 0.01

    else:
        r_min, r_max = limits.get("range", (0.0, 1.0))

        try:
            r_min = float(r_min)
            r_max = float(r_max)
        except (TypeError, ValueError):
            return 0.0, 1.0

        if not (np.isfinite(r_min) and np.isfinite(r_max)):
            return 0.0, 1.0

        if r_min > r_max:
            r_min, r_max = r_max, r_min

    r_min, r_max = _expand_if_degenerate(r_min, r_max)

    return float(r_min), float(r_max)


def set_widget_width(widget: QWidget, char_width: int, pad: int = 8) -> None:
    """Set a widget's fixed width based on a character-count estimate.

    Args:
        widget: Widget whose width should be fixed.
        char_width: Approximate number of zero characters to fit.
        pad: Extra padding in pixels added to the computed width.
    """
    fm = widget.fontMetrics()
    char_width = fm.horizontalAdvance("0" * char_width)
    widget.setFixedWidth(char_width + pad)


def _to_jsonable(obj: Any) -> Any:
    """Recursively coerce NumPy values into JSON-serializable Python types.

    Args:
        obj: Object to convert.

    Returns:
        JSON-serializable Python object when conversion is supported, otherwise
        the original object.
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def pretty_json(obj: Any, indent: int = 4, level: int = 0) -> str:
    """Return a pretty-printed JSON string for the supplied object.

    Args:
        obj: Object to format.
        indent: Number of spaces per indentation level.
        level: Current indentation depth used internally for recursion.

    Returns:
        Pretty-printed JSON string.
    """
    obj = _to_jsonable(obj)
    pad = " " * (indent * level)
    next_pad = " " * (indent * (level + 1))

    if isinstance(obj, dict):
        if not obj:
            return "{}"
        parts = []
        for k, v in obj.items():
            parts.append(
                f'{next_pad}{json.dumps(str(k))}: {pretty_json(v, indent, level + 1)}'
            )
        return "{\n" + ",\n".join(parts) + "\n" + pad + "}"

    if isinstance(obj, list):
        if not obj:
            return "[]"

        if all(not isinstance(x, (dict, list)) for x in obj):
            return "[" + ", ".join(pretty_json(x, indent, level + 1) for x in obj) + "]"

        parts = [f"{next_pad}{pretty_json(x, indent, level + 1)}" for x in obj]
        return "[\n" + ",\n".join(parts) + "\n" + pad + "]"

    if isinstance(obj, float):
        if math.isinf(obj):
            return json.dumps("+inf" if obj > 0 else "-inf")
        if math.isnan(obj):
            return json.dumps("nan")

    return json.dumps(obj, ensure_ascii=False)


def restore_special_floats(obj: Any) -> Any:
    """Recursively convert special float strings back to Python floats.

    Args:
        obj: Object that may contain serialized special-float strings.

    Returns:
        Object with ``"inf"``, ``"+inf"``, ``"-inf"``, and ``"nan"`` strings
        converted back to Python float values where applicable.
    """
    if isinstance(obj, dict):
        return {k: restore_special_floats(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [restore_special_floats(x) for x in obj]

    if isinstance(obj, str):
        s = obj.strip().lower()
        if s in {"inf", "+inf"}:
            return math.inf
        if s == "-inf":
            return -math.inf
        if s == "nan":
            return math.nan

    return obj


def parse_orientation(value: str) -> Qt.Orientation:
    """Convert a short orientation token into a Qt orientation value.

    Args:
        value: Orientation token such as ``"h"``, ``"horizontal"``, ``"v"``,
            or ``"vertical"``.

    Returns:
        Matching Qt orientation.

    Raises:
        ValueError: If the token is not recognized.
    """
    value = value.strip().lower()
    if value in ("h", "horizontal"):
        return Qt.Horizontal
    if value in ("v", "vertical"):
        return Qt.Vertical
    raise ValueError(f"Invalid orientation: {value!r}")


def get_numeric_format_field(fmt: str) -> str:
    """Return a Python-compatible numeric replacement field derived from ``fmt``.

    This helper is used to configure numeric line-edit parsing and validation so
    that entered values remain consistent with a widget's display format.

    Args:
        fmt: Original format string.

    Returns:
        Full replacement field such as ``"{:.3f}"`` or ``"{:}"``.

    Note:
        - Only the first replacement field with an explicit format specifier is
          used.
        - If no such field is found, ``"{:}"`` is returned.
        - The custom scientific marker ``"S"`` is replaced with ``"g"`` because
          ``"S"`` is not a valid Python numeric format type.
    """
    m = re.search(r"\{[^{}]*:([^{}]*)\}", fmt)
    if not m:
        return "{:}"
    spec = m.group(1).replace("S", "g")
    spec = spec.replace(",", "")
    return f"{{:{spec}}}"


def value_to_text(value: int | float, fmt: str) -> str:
    """Format a numeric value for display.

    Args:
        value: Numeric value to format.
        fmt: Format string, which may use ordinary Python formatting or the
            custom ``"S"`` scientific marker.

    Returns:
        Formatted text. Falls back to ``str(value)`` if formatting fails.

    Note:
        The custom scientific pattern such as ``"{:.2S}"`` is expanded using
        ``pretty_sci_text``.
    """
    sci_pat = r"\{:[0-9]*\.(\d+)S\}"

    if not re.search(sci_pat, fmt):
        try:
            return fmt.format(value)
        except Exception:
            return str(value)

    def repl(m: re.Match) -> str:
        """Replace a custom scientific field with formatted text."""
        prec = int(m.group(1))
        return pretty_sci_text(float(value), sig_digits=prec)

    try:
        return re.sub(sci_pat, repl, fmt)
    except Exception:
        return str(value)


def set_win_center(win: QMainWindow, app: QApplication) -> None:
    """Move a window so it is centered on the current screen.

    Args:
        win: Window to reposition.
        app: Running QApplication instance used to locate the screen.
    """
    screen = app.primaryScreen().availableGeometry()
    x = screen.x() + (screen.width() - win.width()) // 2
    y = screen.y() + (screen.height() - win.height()) // 2

    win.move(x, y)


def set_nested_bool_key(obj, key_name, value=True):
    """Recursively set every occurrence of a named key to a boolean value.

    Args:
        obj: Nested dictionary or list structure to modify in place.
        key_name: Key name to search for.
        value: Value to assign after converting with ``bool``.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key_name:
                obj[k] = bool(value)
            else:
                set_nested_bool_key(v, key_name, value)
    elif isinstance(obj, list):
        for item in obj:
            set_nested_bool_key(item, key_name, value)


def make_box(label: str, layout: QLayout, checkable: bool = False, checked: bool = False) -> QGroupBox:
    """Wrap a layout in a labeled, optionally checkable group box.

    Args:
        label: Group-box title.
        layout: Layout to place inside the group box.
        checkable: Whether the group box should be user-checkable.
        checked: Initial checked state when ``checkable`` is enabled.

    Returns:
        Configured group box.
    """
    box = QGroupBox(label)
    box.setCheckable(checkable)
    box.setChecked(checked)
    if not label:
        box.setObjectName("no_title")
    box.setLayout(layout)
    return box


def make_group(g_props: Dict[str, Any], widgets: Dict[str, QWidget]) -> QGroupBox:
    """Create a named group box from a layout-spec dictionary.

    Args:
        g_props: Group specification containing label, orientation, and widget IDs.
        widgets: Mapping from widget IDs to widget instances.

    Returns:
        Created group box.
    """
    label = g_props.get("label", "None")
    orient = parse_orientation(g_props.get("orientation", "v"))
    widgets_id = g_props.get("widgets", [])
    layout = QHBoxLayout() if orient == Qt.Horizontal else QVBoxLayout()
    for w in widgets_id:
        layout.addWidget(widgets[w])

    if orient == Qt.Horizontal:
        layout.addStretch(1)

    return make_box(label, layout)


def make_row(row_props: Dict[str, Any], widgets: Dict[str, QWidget]) -> QHBoxLayout:
    """Create a horizontal row of group boxes from a row specification.

    Args:
        row_props: Row specification containing a list of group specifications.
        widgets: Mapping from widget IDs to widget instances.

    Returns:
        Horizontal layout containing the created group boxes.
    """
    layout = QHBoxLayout()
    groups = row_props.get("groups", [])
    for g in groups:
        layout.addWidget(make_group(g, widgets))

    return layout


def make_layout(layout_props: Dict[str, Any], widgets: Dict[str, QWidget], parent=QWidget) -> None:
    """Build a vertical layout of rows or groups and attach it to ``parent``.

    Args:
        layout_props: Layout specification describing rows or groups.
        widgets: Mapping from widget IDs to widget instances.
        parent: Parent widget that will receive the layout.
    """
    layout = QVBoxLayout(parent)
    rows = layout_props.get("rows", [])
    groups = layout_props.get("groups", [])

    layout.addStretch(1)
    if rows:
        for row in rows:
            layout.addLayout(make_row(row, widgets))
            layout.addStretch(1)

    elif groups:
        for g in groups:
            layout.addWidget(make_group(g, widgets))
            layout.addStretch(1)

    else:
        for w in widgets.values():
            layout.addWidget(w, 0)
            layout.addStretch(1)
