"""Tests for the mbstudio command (everything except starting the window)."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import mbstudio
from mbstudio import cli
from mbstudio.config.app_metadata import APP_VERSION, DIST_NAME

DATA = Path(__file__).parent / "data"


def small_copy(tmp_path, name):
    """A copy of a test parameter file with a small grid, so solving is quick."""
    data = json.loads((DATA / name).read_text())
    groups = data["params"].values() if data["metadata"].get("fit_mode") else [data["params"]]
    for params in groups:
        params["solve.grid.nt"] = 300
        params["solve.grid.nz"] = 40
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


# --version, --help ------------------------------------------------------------

def test_version(capsys):
    assert cli.main(["--version"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"Maxwell Bloch Studio {APP_VERSION} (mbsolver ")
    assert "sciwidgets" in out and "Python" in out


def test_help_lists_the_commands(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for command in ("update", "solve FILE", "example"):
        assert command in out


def test_unknown_option(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["-update"])
    assert exc.value.code == 2


# solve -----------------------------------------------------------------------

def test_solve_plain(tmp_path, capsys):
    path = small_copy(tmp_path, "params_plain.json")
    assert cli.main(["solve", str(path)]) == 0
    out_file = tmp_path / "params_plain_results.npz"
    assert out_file.is_file()
    assert str(out_file) in capsys.readouterr().out
    saved = np.load(out_file)
    expected = mbstudio.solve(mbstudio.ParamsFile(path).params())
    for key, value in expected.items():
        np.testing.assert_array_equal(saved[key], value, err_msg=key)
    assert json.loads(str(saved["params"]))["solve.grid.nt"] == 300


def test_solve_output_name(tmp_path):
    path = small_copy(tmp_path, "params_plain.json")
    out = tmp_path / "sub" / "run.npz"
    assert cli.main(["solve", str(path), "-o", str(out)]) == 0
    assert out.is_file()


def test_solve_fit_needs_a_velocity(tmp_path, capsys):
    path = small_copy(tmp_path, "params_fit.json")
    assert cli.main(["solve", str(path)]) == 1
    err = capsys.readouterr().err
    assert "12.3" in err and "--all" in err


def test_solve_one_velocity(tmp_path):
    path = small_copy(tmp_path, "params_fit.json")
    assert cli.main(["solve", str(path), "--velocity", "-5"]) == 0
    assert (tmp_path / "params_fit_v-5_results.npz").is_file()


def test_solve_all_velocities(tmp_path):
    path = small_copy(tmp_path, "params_fit.json")
    out_dir = tmp_path / "results"
    assert cli.main(["solve", str(path), "--all", "--output-dir", str(out_dir)]) == 0
    assert sorted(p.name for p in out_dir.iterdir()) == [
        "params_fit_v-5.0_results.npz", "params_fit_v12.3_results.npz"]


def test_solve_plain_rejects_velocity(tmp_path, capsys):
    path = small_copy(tmp_path, "params_plain.json")
    assert cli.main(["solve", str(path), "--velocity", "1"]) == 1
    assert "no velocities" in capsys.readouterr().err


def test_solve_bad_file(tmp_path, capsys):
    path = tmp_path / "x.json"
    path.write_text("{}")
    assert cli.main(["solve", str(path)]) == 1
    assert "Cannot read" in capsys.readouterr().err


# example ---------------------------------------------------------------------

def test_example(tmp_path):
    out = tmp_path / "ex.py"
    assert cli.main(["example", str(out)]) == 0
    assert "import mbstudio" in out.read_text()
    assert cli.main(["example", str(out)]) == 1          # exists
    assert cli.main(["example", str(out), "--force"]) == 0


# update ----------------------------------------------------------------------

def run_update(check=False, yes=False, latest="99.0.0", notes=(), kind="pip", answer="n"):
    calls = []

    def run(command):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    code = cli.cmd_update(
        argparse.Namespace(check=check, yes=yes),
        latest_version=lambda: latest,
        release_notes=lambda current, newest: list(notes),
        kind=lambda: kind,
        ask=lambda prompt: answer,
        run=run,
    )
    return code, calls


def test_update_up_to_date(capsys):
    code, calls = run_update(latest=APP_VERSION)
    assert code == 0 and calls == []
    assert "is the latest version" in capsys.readouterr().out


def test_update_check_shows_notes(capsys):
    code, calls = run_update(check=True, notes=[("99.0.0", "- big news")])
    out = capsys.readouterr().out
    assert code == 0 and calls == []
    assert "99.0.0 is available" in out and "- big news" in out


def test_update_asks_first(capsys):
    code, calls = run_update(answer="n")
    assert code == 0 and calls == []
    assert "Nothing changed" in capsys.readouterr().out


def test_update_pip(capsys):
    code, calls = run_update(answer="y", kind="pip")
    assert code == 0
    assert calls == [[sys.executable, "-m", "pip", "install", "--upgrade", DIST_NAME]]


def test_update_pipx():
    code, calls = run_update(yes=True, kind="pipx")
    assert code == 0
    assert calls[0][1:] == ["upgrade", DIST_NAME]


def test_update_refuses_editable(capsys):
    code, calls = run_update(yes=True, kind="editable")
    assert code == 1 and calls == []
    assert "git pull" in capsys.readouterr().err


def test_update_offline(capsys):
    def offline():
        raise OSError("no network")

    code = cli.cmd_update(argparse.Namespace(check=True, yes=False), latest_version=offline)
    assert code == 1
    assert "Could not check" in capsys.readouterr().err


def test_install_kind_of_this_checkout():
    # the tests run against an editable install (pip install -e ".[dev]") or a plain one
    assert cli.install_kind() in ("editable", "pip", "pipx")
