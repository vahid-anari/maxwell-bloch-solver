"""Tests for the script API: mbstudio.ParamsFile, mbstudio.solve, mbstudio.scaling."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

import mbsolver
import mbstudio
from mbstudio.sample import sample_scaling

from make_reference import KEYS, reference_params, reference_results

DATA = Path(__file__).parent / "data"
PLAIN = DATA / "params_plain.json"
FIT = DATA / "params_fit.json"


# ParamsFile ---------------------------------------------------------------

def test_plain_file():
    f = mbstudio.ParamsFile(PLAIN)
    assert not f.is_fit
    assert f.velocities == []
    assert f.app_version == "10.0.4"
    assert "plain" in repr(f)
    params = f.params()
    assert params["solve.grid.nt"] == 2000
    assert set(params["solve.sample"]) >= {"nu", "gamma", "t0", "l", "n0"}


def test_params_are_fresh_copies():
    f = mbstudio.ParamsFile(PLAIN)
    first = f.params()
    first["solve.sample"]["l"] = 1.0
    first["solve.grid.nt"] = 3
    second = f.params()
    assert second["solve.sample"]["l"] == 7.5e12
    assert second["solve.grid.nt"] == 2000


def test_metadata_is_a_copy():
    f = mbstudio.ParamsFile(PLAIN)
    f.metadata["app_version"] = "changed"
    assert f.app_version == "10.0.4"


def test_plain_file_has_no_velocities():
    with pytest.raises(ValueError, match="plain"):
        mbstudio.ParamsFile(PLAIN).params(12.3)


def test_fit_file():
    f = mbstudio.ParamsFile(FIT)
    assert f.is_fit
    assert f.velocities == ["12.3", "-5.0"]
    assert "2 velocities" in repr(f)
    assert f.metadata["source"] == "TestSource"


def test_fit_velocity_as_number_or_text():
    f = mbstudio.ParamsFile(FIT)
    assert f.params(12.3) == f.params("12.3")
    assert f.params(-5) == f.params("-5.0")
    assert f.params(-5)["solve.t1"] == 30.0
    assert f.params(12.3)["solve.t1"] == 45.0


def test_fit_file_needs_a_velocity():
    f = mbstudio.ParamsFile(FIT)
    with pytest.raises(ValueError, match="velocities"):
        f.params()
    with pytest.raises(ValueError, match="not in"):
        f.params(7.0)


def test_not_a_params_file(tmp_path):
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"a": 1}))
    with pytest.raises(ValueError, match="not a parameter file"):
        mbstudio.ParamsFile(path)


def test_infinite_values_are_restored(tmp_path):
    data = json.loads(PLAIN.read_text())
    data["params"]["solve.t1"] = "+inf"
    data["params"]["solve.t2"] = "inf"
    path = tmp_path / "inf.json"
    path.write_text(json.dumps(data))
    params = mbstudio.ParamsFile(path).params()
    assert params["solve.t1"] == math.inf
    assert params["solve.t2"] == math.inf


# solve --------------------------------------------------------------------

def test_solve_matches_reference():
    """Same numbers as when the reference was made (tests/make_reference.py)."""
    res = mbstudio.solve(reference_params())
    expected = np.load(DATA / "reference_solve.npz")
    got = reference_results(res)
    assert sorted(got) == sorted(expected.files)
    for key in expected.files:
        np.testing.assert_allclose(got[key], expected[key], rtol=1e-12, atol=0, err_msg=key)


def test_solve_result_shapes():
    params = reference_params()
    res = mbstudio.solve(params)
    nt = params["solve.grid.nt"]
    planes = params["slice.z"]["arr_length"]
    for key in KEYS:
        assert res[key].shape == (nt,), key
    assert res["intensity"].shape == (planes, nt)
    assert res["w"].shape == (planes, nt)


def test_solve_accepts_old_key_names():
    """Files from older versions (solve.dynamics.t1, solve.pump.cosh1, ...) give the same result."""
    params = reference_params()
    old = dict(params)
    for new, legacy in (("solve.t1", "solve.dynamics.t1"), ("solve.t2", "solve.dynamics.t2"),
                        ("solve.pump.pulse1", "solve.pump.cosh1"),
                        ("solve.pump.pulse2", "solve.pump.cosh2"),
                        ("solve.pump.pulse3", "solve.pump.cosh3")):
        old[legacy] = old.pop(new)
    a = mbstudio.solve(params)
    b = mbstudio.solve(old)
    np.testing.assert_array_equal(a["intensity"], b["intensity"])


def test_solve_accepts_inf_strings():
    params = reference_params()
    params["solve.t1"] = "+inf"
    res = mbstudio.solve(params)
    assert np.all(np.isinf(res["t1"]))


def test_solve_does_not_change_its_input():
    params = reference_params()
    before = json.dumps(params, sort_keys=True)
    mbstudio.solve(params)
    assert json.dumps(params, sort_keys=True) == before


def test_solve_reports_missing_keys():
    params = reference_params()
    del params["solve.grid.nt"]
    with pytest.raises(KeyError):
        mbstudio.solve(params)


# scaling ------------------------------------------------------------------

def test_scaling_is_the_solver_function():
    assert mbstudio.scaling is mbsolver.scaling


def test_sample_scaling():
    sample = mbstudio.ParamsFile(PLAIN).params()["solve.sample"]
    s = sample_scaling(sample)
    assert s == mbsolver.scaling(**{k: sample[k] for k in ("nu", "gamma", "t0", "l", "n0")})
    assert s["eta"] > 0 and s["theta0"] > 0


def test_sample_scaling_missing_value():
    with pytest.raises(KeyError, match="n0"):
        sample_scaling({"nu": 1e9, "gamma": 1e-9, "t0": 1.0, "l": 1.0})
