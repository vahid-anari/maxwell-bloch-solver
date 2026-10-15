"""Use the solver from Python scripts, without the window.

    import mbstudio

    f = mbstudio.ParamsFile("run_1.json")       # a file saved by the app
    params = f.params()                          # a fresh dict, safe to change
    params["solve.sample"]["l"] = 1e13
    res = mbstudio.solve(params)                 # same numbers as the app

``params`` is the flat mapping the app saves under ``"params"``, keyed by
widget path (``"solve.grid.nt"``, ``"solve.sample"``, ``"solve.pump.pulse1"``,
...). The result is the same dictionary the app plots. A commented example
script ships with the app: *Help → Use from Python…*.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

from mbstudio.io.legacy_keys import migrate_legacy_params

__all__ = ["ParamsFile", "solve"]


def _restore_special_floats(obj: Any) -> Any:
    """Turn the strings ``"inf"``, ``"+inf"``, ``"-inf"`` and ``"nan"`` back into floats."""
    from mbstudio.utils.helper_funcs import restore_special_floats

    return restore_special_floats(obj)


def solve(params: Dict[str, Any]) -> Dict[str, np.ndarray]:
    """Solve the Maxwell-Bloch equations for a parameter mapping.

    η and θ₀ are computed from the sample values (``nu``, ``gamma``, ``t0``,
    ``l``, ``n0`` in ``"solve.sample"``), as in the app.

    Args:
        params: Flat mapping keyed by widget path, as returned by
            :meth:`ParamsFile.params`. Keys from older app versions and
            ``"+inf"`` strings are accepted.

    Returns:
        Dictionary with ``time``, ``intensity`` (z planes × time), ``w`` (z planes
        × time), ``lambda_n`` (pump), ``A0`` (boundary field), ``t1`` and ``t2``,
        all in the solver's dimensionless units.

    Raises:
        KeyError: If a parameter the solver needs is missing.
    """
    from mbstudio.app.solver_adapter import solve_maxwell_bloch

    params = migrate_legacy_params(_restore_special_floats(copy.deepcopy(dict(params))))
    return solve_maxwell_bloch(params)


class ParamsFile:
    """A parameter file saved by the app (plain or from a data folder).

    Args:
        path: The file, e.g. one saved with *File → Save Parameters As…* or the
            ``<source>_params.json`` file of a data folder.

    Raises:
        ValueError: If the file is not a parameter file saved by the app.
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        with self.path.open("r", encoding="utf-8") as f:
            data = _restore_special_floats(json.load(f))
        meta = data.get("metadata") if isinstance(data, dict) else None
        if not isinstance(meta, dict) or "params" not in data:
            raise ValueError(f"{self.path} is not a parameter file saved by the app")
        self._metadata: Dict[str, Any] = meta
        self._params: Dict[str, Any] = data["params"]

    def __repr__(self) -> str:
        kind = f"{len(self.velocities)} velocities" if self.is_fit else "plain"
        return f"ParamsFile({str(self.path)!r}, {kind}, app {self.app_version})"

    @property
    def metadata(self) -> Dict[str, Any]:
        """Everything saved under ``"metadata"`` (app_version, saved_at, saved_by, source, ...)."""
        return copy.deepcopy(self._metadata)

    @property
    def app_version(self) -> Optional[str]:
        """Version of the app that saved the file."""
        return self._metadata.get("app_version")

    @property
    def is_fit(self) -> bool:
        """Whether the file belongs to a data folder (one parameter set per velocity)."""
        return bool(self._metadata.get("fit_mode"))

    @property
    def velocities(self) -> List[str]:
        """Velocity labels of a data-folder file, as written in the file; empty otherwise."""
        return list(self._params) if self.is_fit else []

    def params(self, velocity: Union[None, str, float] = None) -> Dict[str, Any]:
        """Return the parameters, ready for :func:`solve`.

        Every call returns a new copy, so changing it never changes the file
        or other copies.

        Args:
            velocity: For a data-folder file, which velocity component, e.g.
                ``12.3`` or ``"12.3"``. Leave out for a plain parameter file.

        Raises:
            ValueError: If the velocity is missing or unknown, or given for a
                plain parameter file.
        """
        if not self.is_fit:
            if velocity is not None:
                raise ValueError(f"{self.path.name} is a plain parameter file; it has no velocities")
            return migrate_legacy_params(copy.deepcopy(self._params))

        if velocity is None:
            raise ValueError(f"{self.path.name} holds several velocities; choose one of "
                             f"{self.velocities} with params(velocity=...)")
        key = _match_velocity(velocity, self._params)
        if key is None:
            raise ValueError(f"velocity {velocity!r} is not in {self.path.name}; "
                             f"available: {self.velocities}")
        return migrate_legacy_params(copy.deepcopy(self._params[key]))


def _match_velocity(velocity: Union[str, float], keys) -> Optional[str]:
    """Return the file's key for ``velocity``, comparing as text first, then as numbers."""
    text = str(velocity)
    if text in keys:
        return text
    try:
        value = float(velocity)
    except (TypeError, ValueError):
        return None
    for key in keys:
        try:
            if float(key) == value:
                return key
        except ValueError:
            continue
    return None
