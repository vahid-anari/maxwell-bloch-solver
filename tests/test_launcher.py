"""Tests for mbstudio install-app (the double-click launcher), for all three systems."""

import os
import plistlib
import subprocess
import sys

import pytest
from PIL import Image

from mbstudio import cli, launcher
from mbstudio.config.app_metadata import APP_NAME


@pytest.fixture(autouse=True)
def no_xdg(monkeypatch):
    for name in ("XDG_DATA_HOME", "APPDATA", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)


def recorder():
    calls = []

    def run(command):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0)
    return calls, run


def test_mac_app(tmp_path):
    calls, run = recorder()
    written = launcher.install_app(system="mac", home=tmp_path, python="/env/bin/python",
                                   path_env="/usr/bin:/Library/TeX/texbin", run=run)
    app = tmp_path / "Applications" / f"{APP_NAME}.app"
    assert written == [app]
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleName"] == APP_NAME and info["CFBundleIconFile"] == "app_icon"
    script = app / "Contents" / "MacOS" / info["CFBundleExecutable"]
    text = script.read_text()
    assert text.startswith("#!/bin/sh\n")
    assert "exec /env/bin/python -m mbstudio \"$@\"" in text
    assert "export PATH=/usr/bin:/Library/TeX/texbin" in text      # LaTeX found as in the terminal
    assert os.access(script, os.X_OK)
    assert Image.open(app / "Contents" / "Resources" / "app_icon.icns").format == "ICNS"

    launcher.install_app(system="mac", home=tmp_path, python="/other/python", path_env="", run=run)
    assert "/other/python" in script.read_text()                    # installing again replaces it
    assert launcher.remove_app(system="mac", home=tmp_path) == [app]
    assert not app.exists()
    assert launcher.remove_app(system="mac", home=tmp_path) == []


def test_mac_script_quotes_paths_with_spaces(tmp_path):
    _, run = recorder()
    launcher.install_app(system="mac", home=tmp_path, python="/Users/me/my envs/bin/python",
                         path_env="/a b:/c", run=run)
    text = next((tmp_path / "Applications").glob("*.app/Contents/MacOS/*")).read_text()
    assert "exec '/Users/me/my envs/bin/python' -m mbstudio" in text
    assert "export PATH='/a b:/c'" in text


def test_linux_entry(tmp_path):
    _, run = recorder()
    entry, icon = launcher.install_app(system="linux", home=tmp_path, python="/env/bin/python", run=run)
    assert entry == tmp_path / ".local/share/applications/maxwell-bloch-studio.desktop"
    text = entry.read_text()
    assert "Exec=/env/bin/python -m mbstudio %f" in text
    assert f"Name={APP_NAME}" in text and f"Icon={icon}" in text and "Terminal=false" in text
    assert Image.open(icon).size == (256, 256)
    assert sorted(launcher.remove_app(system="linux", home=tmp_path)) == sorted([entry, icon])
    assert not entry.exists() and not icon.exists()


def test_linux_xdg_data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    _, run = recorder()
    entry, _ = launcher.install_app(system="linux", home=tmp_path, python="/p", run=run)
    assert entry.parent == tmp_path / "data" / "applications"


def test_windows_shortcut(tmp_path):
    calls, run = recorder()
    pythonw = tmp_path / "env" / "pythonw.exe"
    pythonw.parent.mkdir()
    pythonw.write_text("")
    link, icon = launcher.install_app(system="windows", home=tmp_path,
                                      python=str(tmp_path / "env" / "python.exe"), run=run)
    assert link.name == f"{APP_NAME}.lnk" and "Start Menu" in str(link)
    assert icon.suffix == ".ico" and Image.open(icon).format == "ICO"
    (command,) = calls
    assert command[0] == "powershell"
    script = command[-1]
    assert f"CreateShortcut('{link}')" in script
    assert f"TargetPath = '{pythonw}'" in script                    # no console window
    assert "Arguments = '-m mbstudio'" in script and f"IconLocation = '{icon}'" in script


def test_windows_quoting_and_failure(tmp_path):
    command = launcher.windows_shortcut_command(tmp_path / "a.lnk", "C:\\O'Brien\\python.exe",
                                                tmp_path / "i.ico", tmp_path)
    assert "'C:\\O''Brien\\python.exe'" in command[-1]               # PowerShell quoting

    def failing(cmd):
        return subprocess.CompletedProcess(cmd, 1)
    with pytest.raises(OSError):
        launcher.install_app(system="windows", home=tmp_path, python="python.exe", run=failing)


def test_cli_install_and_remove(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(launcher, "current_system", lambda: "linux")
    monkeypatch.setattr(launcher.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    assert cli.main(["install-app"]) == 0
    out = capsys.readouterr().out
    assert "applications menu" in out and sys.executable in out
    assert (tmp_path / ".local/share/applications/maxwell-bloch-studio.desktop").exists()
    assert cli.main(["install-app", "--remove"]) == 0
    assert "Removed" in capsys.readouterr().out
    assert cli.main(["install-app", "--remove"]) == 0
    assert "nothing removed" in capsys.readouterr().out


def test_finder_argument_is_ignored(capsys):
    assert cli.main(["-psn_0_12345", "--version"]) == 0
    assert APP_NAME in capsys.readouterr().out
