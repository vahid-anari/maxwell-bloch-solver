"""The maser sample: physical values and the scaling quantities derived from them.

The solver works in dimensionless units. :func:`scaling` (from the solver
package ``mbsolver``) turns the physical sample values into the quantities it
needs (``eta``, ``theta0``) and the ones the Scaling Formula dialog shows. It
has no Qt dependency, so scripts can use it.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from mbsolver.sample import scaling

__all__ = ["SAMPLE_KEYS", "sample_scaling", "scaling"]

SAMPLE_KEYS = ("nu", "gamma", "t0", "l", "n0")
"""Physical sample values saved under ``"solve.sample"``, all in SI units."""


def sample_scaling(sample: Mapping[str, Any]) -> Dict[str, float]:
    """Return :func:`scaling` for a ``"solve.sample"`` mapping.

    Raises:
        KeyError: If one of ``nu``, ``gamma``, ``t0``, ``l``, ``n0`` is missing.
    """
    missing = [key for key in SAMPLE_KEYS if key not in sample]
    if missing:
        raise KeyError(f'"solve.sample" is missing {", ".join(missing)}')
    return scaling(**{key: float(sample[key]) for key in SAMPLE_KEYS})
