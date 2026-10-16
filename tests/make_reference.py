"""Rebuild tests/data/reference_solve.npz from tests/data/params_plain.json.

Only run this on purpose, after a change that is meant to change the solver's
numbers; the reference test then checks against the new values.

    python tests/make_reference.py
"""

from pathlib import Path

import numpy as np

import mbstudio

DATA = Path(__file__).parent / "data"
NZ = 200
"""Fewer z points than the saved file, so the test runs in about a second."""

KEYS = ("time", "lambda_n", "A0", "t1", "t2")
"""Results stored in full; for intensity and w only the exit plane is stored."""


def reference_params():
    params = mbstudio.ParamsFile(DATA / "params_plain.json").params()
    params["solve.grid.nz"] = NZ
    return params


def reference_results(res):
    out = {key: res[key] for key in KEYS}
    out["intensity_exit"] = res["intensity"][-1]
    out["w_exit"] = res["w"][-1]
    return out


if __name__ == "__main__":
    res = mbstudio.solve(reference_params())
    np.savez_compressed(DATA / "reference_solve.npz", **reference_results(res))
    print("Wrote", DATA / "reference_solve.npz")
