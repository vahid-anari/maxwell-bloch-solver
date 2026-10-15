"""Bridge between the parameter tabs and the ``maxbloch`` solver package.

The tabs hand over one flat mapping keyed by widget path (``"solve.grid.nt"``,
``"solve.pump.pulse1"``, ...). This module turns it into a
``maxbloch.two_level.solve_1d`` call and the result back into the mapping the
rest of the app uses.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Union

import numpy as np
from maxbloch import Pulse, Steps
from maxbloch.two_level import solve_1d

from mbsolver.sample import sample_scaling


def pulse_from_value(value: Mapping[str, Any]) -> Optional[Pulse]:
    """Return the ``Pulse`` for a pulse-widget value (``None`` for an empty mapping)."""
    if not value:
        return None
    if value["symmetric"]:
        return Pulse(a=value["a"], x0=value["x0"], w=value["w"])
    return Pulse(a=value["a"], x0=value["x0"], wl=value["wl"], wr=value["wr"])


def steps_from_value(value: Union[float, Mapping[str, Any]]) -> Union[float, Steps]:
    """Return a number or ``Steps`` for a step-widget value.

    The widget stores ``x0`` and the widths with one value per level, the first
    unused; ``Steps`` takes one value per step.
    """
    if not isinstance(value, Mapping):
        return float(value)
    if value["symmetric"]:
        return Steps(y=value["y"], x0=value["x0"][1:], w=value["w"][1:])
    return Steps(y=value["y"], x0=value["x0"][1:], wl=value["wl"][1:], wr=value["wr"][1:])


def solve_maxwell_bloch(params: Mapping[str, Any]) -> dict[str, np.ndarray]:
    """Solve for the current parameter-tab values.

    Args:
        params: Flat parameter mapping from the parameter tabs.

    Returns:
        Mapping with ``time``, ``intensity``, ``w``, ``lambda_n`` (pump),
        ``A0`` (boundary field) and ``t1``, ``t2`` on the time grid.
    """
    derived = sample_scaling(params["solve.sample"])
    ics = params["solve.ics"]
    if ics["use_theta0"]:
        initial = {"theta0": derived["theta0"]}
    else:
        initial = {"w0": ics["w0"], "R0": ics["R0"]}

    res = solve_1d(
        t_max=params["solve.grid.t_max"],
        nt=params["solve.grid.nt"],
        nz=params["solve.grid.nz"],
        eta=derived["eta"],
        pump=[pulse_from_value(params.get(f"solve.pump.pulse{i}", {})) for i in (1, 2, 3)],
        field_in=pulse_from_value(params["solve.bcs"]),
        t1=steps_from_value(params["solve.t1"]),
        t2=steps_from_value(params["solve.t2"]),
        n_planes=min(params["slice.z"]["arr_length"], params["solve.grid.nz"]),
        **initial,
    )
    return {
        "time": res.time,
        "intensity": res.intensity,
        "w": res.w,
        "lambda_n": res.pump,
        "A0": res.field_in,
        "t1": res.t1,
        "t2": res.t2,
    }
