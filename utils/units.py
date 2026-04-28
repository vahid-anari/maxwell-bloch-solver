"""Shared unit conversion factors and display labels."""

from __future__ import annotations

TIME_UNIT_TO_SECONDS = {
    "d": 86400.0,
    "h": 3600.0,
    "m": 60.0,
    "s": 1.0,
    "ms": 1.0e-3,
    "µs": 1.0e-6,
    "ns": 1.0e-9,
}
"""Map supported time-unit labels to their conversion factors in seconds."""

VELOCITY_UNIT_TEXT = "km/s"
"""Plain-text label used for velocity units."""

VELOCITY_UNIT_LATEX = "\\mathrm{km}/\\mathrm{s}"
"""LaTeX label used for velocity units."""
