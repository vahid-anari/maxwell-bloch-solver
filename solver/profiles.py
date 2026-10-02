"""Profile functions shared by the solver and the parameter widgets.

Provides sech^2 pulse trains and constant or smoothed multi-step profiles,
evaluated on a coordinate grid with numba.
"""

from __future__ import annotations

import numbers
from typing import Any, Dict, Mapping

import numpy as np
from numba import njit


@njit(nogil=True, cache=True)
def pulse_func(
        symmetric: bool,
        x: np.ndarray,
        a: np.ndarray,
        x0: np.ndarray,
        w: np.ndarray,
        wl: np.ndarray,
        wr: np.ndarray,
) -> np.ndarray:
    """Evaluate a sum of sech^2 components on the supplied coordinates.

    y(x) = sum_{i=0}^{N-1} a^i * sech^2((x - x0^i) / w^i).

    Args:
        symmetric: Whether each component uses a single shared width.
        x: Coordinates where the profile is evaluated.
        a: Component amplitudes (length N).
        x0: Component center positions (length N).
        w: Symmetric component widths (length N).
        wl: Left-side widths for asymmetric components (length N).
        wr: Right-side widths for asymmetric components (length N).

    Returns:
        Array containing the summed profile values at each coordinate in ``x``.
        A zero width gives ``a^i`` only at ``x = x0^i``; an infinite width
        gives a constant ``a^i``.
    """

    n = a.shape[0]
    m = x.shape[0]
    if x0.shape[0] != n or w.shape[0] != n or wl.shape[0] != n or wr.shape[0] != n:
        raise ValueError("x0, w, wl and wr must have the same length as a")

    y = np.zeros(m, dtype=np.float64)

    for i in range(n):
        ai = a[i]
        if ai == 0.0:
            continue

        x0i = x0[i]
        wi = w[i]
        wli = wl[i]
        wri = wr[i]

        for j in range(m):
            dx = x[j] - x0i
            width = wi if symmetric else wli if dx < 0.0 else wri

            if width == 0.0:
                if dx == 0.0:
                    y[j] += ai
            elif np.isinf(width):
                y[j] += ai
            else:
                t = np.tanh(dx / width)
                y[j] += ai * (1.0 - t * t)

    return y


def evaluate_pulse_profile(
        t: np.ndarray,
        params: Mapping[str, Any],
) -> np.ndarray:
    """Evaluate the configured sech-squared drive profile.

    Args:
        t: Time coordinates where the profile is evaluated.
        params: Mapping containing the profile configuration expected by
            ``pulse_func``.

    Returns:
        Drive profile evaluated at the supplied times. If ``params`` is empty,
        a zero-valued profile with the same shape as ``t`` is returned.
    """

    if not params:
        return np.zeros(np.shape(t), dtype=np.float64)

    return pulse_func(
        symmetric=bool(params["symmetric"]),
        x=np.asarray(t, dtype=np.float64),
        a=np.asarray(params["a"], dtype=np.float64),
        x0=np.asarray(params["x0"], dtype=np.float64),
        w=np.asarray(params["w"], dtype=np.float64),
        wl=np.asarray(params["wl"], dtype=np.float64),
        wr=np.asarray(params["wr"], dtype=np.float64),
    )


def step_func(value: float | Dict[str, Any], x: np.ndarray) -> np.ndarray:
    """Evaluate a constant or stepped profile on the supplied coordinates.

    Args:
        value: A constant level (float), or the widget's value mapping with
            keys ``symmetric``, ``y``, ``x0``, ``w``, ``wl`` and ``wr``.
        x: Coordinates where the profile is evaluated.

    Returns:
        Array of profile values with the same shape as ``x``.
    """

    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return np.full(np.shape(x), float(value), dtype=np.float64)
    return _eval_step_func(
        symmetric=bool(value["symmetric"]),
        x=np.asarray(x, dtype=np.float64),
        levels=np.asarray(value["y"], dtype=np.float64),
        x0=np.asarray(value["x0"], dtype=np.float64),
        w=np.asarray(value["w"], dtype=np.float64),
        wl=np.asarray(value["wl"], dtype=np.float64),
        wr=np.asarray(value["wr"], dtype=np.float64),
    )


@njit(nogil=True, cache=True)
def _eval_step_func(
        symmetric: bool,
        x: np.ndarray,
        levels: np.ndarray,
        x0: np.ndarray,
        w: np.ndarray,
        wl: np.ndarray,
        wr: np.ndarray,
) -> np.ndarray:
    """Evaluate a sequence of smoothed steps between successive levels.

    y(x) = y^0 + sum_{i=1}^{N-1} (y^i - y^{i-1}) * S((x - x0^i) / w^i),
    with S(z) = (1 + tanh z) / 2.

    Args:
        symmetric: Whether each step uses a single shared width.
        x: Coordinates where the profile is evaluated.
        levels: Levels y^0 ... y^{N-1} (length N >= 1).
        x0: Step center positions (length N; index 0 unused).
        w: Symmetric step widths (length N; index 0 unused).
        wl: Left-side widths for asymmetric steps (length N; index 0 unused).
        wr: Right-side widths for asymmetric steps (length N; index 0 unused).

    Returns:
        Array containing the profile values at each coordinate in ``x``.
        With N = 1 the result is constant ``levels[0]``. A zero width
        gives a sharp step (value halfway at ``x0``); an infinite width
        gives a constant halfway value.
    """

    n = levels.shape[0]
    m = x.shape[0]
    if n == 0:
        raise ValueError("levels must contain at least y^0")
    if x0.shape[0] != n or w.shape[0] != n or wl.shape[0] != n or wr.shape[0] != n:
        raise ValueError("x0, w, wl and wr must have the same length as levels")

    y = np.empty(m, dtype=np.float64)
    y[:] = levels[0]

    for i in range(1, n):
        di = levels[i] - levels[i - 1]
        if di == 0.0:
            continue

        x0i = x0[i]
        wi = w[i]
        wli = wl[i]
        wri = wr[i]

        for j in range(m):
            dx = x[j] - x0i
            width = wi if symmetric else wli if dx < 0.0 else wri

            if width == 0.0:
                if dx > 0.0:
                    y[j] += di
                elif dx == 0.0:
                    y[j] += 0.5 * di
            elif np.isinf(width):
                y[j] += 0.5 * di
            else:
                y[j] += 0.5 * di * (1.0 + np.tanh(dx / width))

    return y
