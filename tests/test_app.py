"""Maxwell Bloch Studio as an app: launcher and update check through sciwidgets.app."""

import plistlib
import sys

from sciwidgets.app import launcher

from mbstudio import cli
from mbstudio.config.app_metadata import APP


def test_app_info():
    assert APP.name == "Maxwell Bloch Studio" and APP.dist_name == "maxwell-bloch-studio"
    assert APP.module == "mbstudio" and APP.marker == "MBStudio" and APP.icon.is_file()


def test_launchers_made_by_earlier_studios_are_recognised(tmp_path):
    """10.3–10.4 wrote MBStudioPython; 10.2.0 wrote no Python at all (read from the start script)."""
    app = tmp_path / "Applications" / "Maxwell Bloch Studio.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    plist = app / "Contents" / "Info.plist"
    plist.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "10.4.0", "MBStudioPython": "/env/bin/python"}))
    assert launcher.launcher_info(APP, "mac", tmp_path) == {"version": "10.4.0", "python": "/env/bin/python"}
    (app / "Contents" / "MacOS" / "mbstudio-launcher").write_text("#!/bin/sh\nexec '/old env/python' -m mbstudio\n")
    plist.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "10.2.0",
                                      "CFBundleExecutable": "mbstudio-launcher"}))
    assert launcher.launcher_info(APP, "mac", tmp_path) == {"version": "10.2.0", "python": "/old env/python"}


def test_install_app_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(launcher, "current_system", lambda: "linux")
    monkeypatch.setattr(launcher.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    assert cli.main(["install-app"]) == 0
    out = capsys.readouterr().out
    assert "Maxwell Bloch Studio is now in the applications menu" in out and sys.executable in out
    entry = tmp_path / ".local/share/applications/maxwell-bloch-studio.desktop"
    assert "-m mbstudio %f" in entry.read_text() and "X-MBStudio-Version=" in entry.read_text()
    assert cli.main(["install-app", "--remove"]) == 0 and not entry.exists()
