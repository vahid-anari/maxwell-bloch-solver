"""The maser sample: physical values and the scaling quantities derived from them.

The solver works in dimensionless units. ``scaling`` turns the physical sample
values into the quantities it needs (``eta``, ``theta0``) and the ones the
Scaling Formula dialog shows. It has no Qt dependency, so scripts can use it.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

import numpy as np

from mbstudio.utils.constants_si import C, EPSILON_0, H_BAR, MU_0, PI

SAMPLE_KEYS = ("nu", "gamma", "t0", "l", "n0")
"""Physical sample values saved under ``"solve.sample"``, all in SI units."""


def scaling(nu: float, gamma: float, t0: float, l: float, n0: float) -> Dict[str, float]:
    """Compute the derived scaling quantities from the sample values.

    Args:
        nu: Transition frequency ν in Hz.
        gamma: Spontaneous decay rate Γ in s⁻¹.
        t0: Time scale T₀ in s.
        l: Length of the medium L in m.
        n0: Inverted population density n₀ in m⁻³.

    Returns:
        Mapping with ``omega``, ``lambda``, ``k``, ``t_r`` (T_R), ``eta`` (η = T₀/T_R),
        ``N``, ``theta0`` (θ₀ = 2/√N), ``lambda0`` (Λ₀ = 1/T₀), the electric-dipole
        values ``d``, ``e0``, ``p0``, ``i0_electric`` and the magnetic-dipole values
        ``mu``, ``b0``, ``m0``, ``i0_magnetic``, all in SI units.
    """
    omega0 = 2 * PI * nu
    k = omega0 / C
    _lambda = C / nu
    t_r = 2.0 * k**2 / (3.0 * PI * gamma * n0 * l)
    N = n0 * _lambda * l**2
    eta = t0 / t_r
    theta0 = 2.0 / np.sqrt(N)
    lambda0 = 1.0 / t0

    d = np.sqrt(3 * PI * EPSILON_0 * H_BAR * gamma / k**3)
    p0 = n0 * d
    e0 = H_BAR / (t0 * d)
    i0_electric = 0.5 * EPSILON_0 * C * e0**2

    mu = np.sqrt(3 * PI * H_BAR * gamma / (MU_0 * k**3))
    m0 = n0 * mu
    b0 = H_BAR / (t0 * mu)
    i0_magnetic = C / (2.0 * MU_0) * b0**2

    return {
        "omega": omega0, "lambda": _lambda, "k": k, "t_r": t_r, "eta": eta,
        "N": N, "theta0": theta0, "lambda0": lambda0,
        "d": d, "e0": e0, "p0": p0, "i0_electric": i0_electric,
        "mu": mu, "b0": b0, "m0": m0, "i0_magnetic": i0_magnetic,
    }


def sample_scaling(sample: Mapping[str, Any]) -> Dict[str, float]:
    """Return :func:`scaling` for a ``"solve.sample"`` mapping.

    Raises:
        KeyError: If one of ``nu``, ``gamma``, ``t0``, ``l``, ``n0`` is missing.
    """
    missing = [key for key in SAMPLE_KEYS if key not in sample]
    if missing:
        raise KeyError(f'"solve.sample" is missing {", ".join(missing)}')
    return scaling(**{key: float(sample[key]) for key in SAMPLE_KEYS})
