"""Make (or remove) a launcher so the app starts with a double-click.

* macOS: ``~/Applications/Maxwell Bloch Studio.app`` (Launchpad, Spotlight, Dock).
* Linux: a menu entry, ``~/.local/share/applications/maxwell-bloch-studio.desktop``.
* Windows: a Start-menu shortcut, ``Maxwell Bloch Studio.lnk``.

The launcher only starts this installation (``<this python> -m mbstudio``), so
it keeps working after ``mbstudio update``. It records the version that made it;
``refresh_if_outdated`` (called when the app starts) rebuilds a launcher of this
installation made by an older version, so its icon and Finder version follow
updates. No Qt is imported here.
"""

from __future__ import annotations

import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from mbstudio.config.app_metadata import APP_NAME, APP_VERSION
from mbstudio.paths import APP_ICON_PATH

BUNDLE_ID = "io.github.vahid-anari.mbstudio"
LINUX_ID = "maxwell-bloch-studio"
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
              "LaunchServices.framework/Support/lsregister")


def current_system() -> str:
    """``"mac"``, ``"windows"`` or ``"linux"`` (any other Unix counts as Linux)."""
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def python_for_launcher(system: str, python: Optional[str] = None) -> str:
    """The Python the launcher runs: this one; on Windows ``pythonw.exe`` (no console window)."""
    exe = Path(python or sys.executable)
    if system == "windows":
        windowless = exe.with_name("pythonw.exe")
        if windowless.exists():
            return str(windowless)
    return str(exe)


def launcher_path(system: str, home: Path) -> Path:
    """Where the launcher goes for ``home`` (the user's home folder)."""
    if system == "mac":
        return home / "Applications" / f"{APP_NAME}.app"
    if system == "windows":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_NAME}.lnk"
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return data / "applications" / f"{LINUX_ID}.desktop"


def _linux_icon_path(home: Path) -> Path:
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return data / "icons" / "hicolor" / "256x256" / "apps" / f"{LINUX_ID}.png"


def _windows_icon_path(home: Path) -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    return local / APP_NAME / "app_icon.ico"


def _save_icon(path: Path, fmt: str) -> None:
    """Write the app icon as ``icns``, ``ico`` or a 256 px ``png``."""
    from PIL import Image  # installed with Matplotlib

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(APP_ICON_PATH).convert("RGBA")
    if fmt == "icns":
        image.save(path, format="ICNS")
    elif fmt == "ico":
        image.save(path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                              (128, 128), (256, 256)])
    else:
        image.resize((256, 256), Image.LANCZOS).save(path, format="PNG")


# ----- macOS -----------------------------------------------------------------

def _mac_script(python: str, path_env: str) -> str:
    # Finder starts apps with a short PATH; keep the one of the installing terminal so that
    # LaTeX (for axis labels) is found as when starting from the terminal.
    return (
        "#!/bin/sh\n"
        f"# Starts {APP_NAME}; made by 'mbstudio install-app'.\n"
        f"export PATH={shlex.quote(path_env)}\n"
        f"exec {shlex.quote(python)} -m mbstudio \"$@\"\n"
    )


def _install_mac(app: Path, python: str, path_env: str, run: Callable) -> List[Path]:
    if app.exists():
        shutil.rmtree(app)
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir()
    script = contents / "MacOS" / "mbstudio-launcher"
    script.write_text(_mac_script(python, path_env), encoding="utf-8")
    script.chmod(0o755)
    _save_icon(contents / "Resources" / "app_icon.icns", "icns")
    info = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": script.name,
        "CFBundleIconFile": "app_icon",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "MBStudioPython": python,
    }
    with open(contents / "Info.plist", "wb") as fh:
        plistlib.dump(info, fh)
    os.utime(app)  # makes Finder show the new icon
    if Path(LSREGISTER).exists():  # so Launchpad and Spotlight find it at once
        run([LSREGISTER, "-f", str(app)])
    return [app]


# ----- Linux -----------------------------------------------------------------

def _desktop_entry(python: str, icon: Path) -> str:
    exec_line = " ".join(shlex.quote(p) for p in (python, "-m", "mbstudio")) + " %f"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Simulate and fit Maxwell-Bloch models of maser light curves\n"
        f"Exec={exec_line}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Science;Physics;Education;\n"
        f"StartupWMClass={APP_NAME}\n"
        f"X-MBStudio-Version={APP_VERSION}\n"
        f"X-MBStudio-Python={python}\n"
    )


def _install_linux(entry: Path, home: Path, python: str, run: Callable) -> List[Path]:
    icon = _linux_icon_path(home)
    _save_icon(icon, "png")
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(_desktop_entry(python, icon), encoding="utf-8")
    entry.chmod(0o755)
    if shutil.which("update-desktop-database"):
        run(["update-desktop-database", str(entry.parent)])
    return [entry, icon]


# ----- Windows ---------------------------------------------------------------

def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def windows_shortcut_command(link: Path, python: str, icon: Path, workdir: Path) -> List[str]:
    """The PowerShell command that writes the Start-menu shortcut."""
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + _ps_quote(str(link)) + "); "
        "$s.TargetPath = " + _ps_quote(python) + "; "
        "$s.Arguments = '-m mbstudio'; "
        "$s.WorkingDirectory = " + _ps_quote(str(workdir)) + "; "
        "$s.IconLocation = " + _ps_quote(str(icon)) + "; "
        "$s.Description = " + _ps_quote(APP_NAME) + "; "
        "$s.Save()"
    )
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]


def _install_windows(link: Path, home: Path, python: str, run: Callable) -> List[Path]:
    icon = _windows_icon_path(home)
    _save_icon(icon, "ico")
    link.parent.mkdir(parents=True, exist_ok=True)
    result = run(windows_shortcut_command(link, python, icon, home))
    if getattr(result, "returncode", 0) != 0:
        raise OSError("PowerShell could not create the shortcut")
    _windows_marker_path(home).write_text(json.dumps({"version": APP_VERSION, "python": python}),
                                          encoding="utf-8")
    return [link, icon]


def _windows_marker_path(home: Path) -> Path:
    return _windows_icon_path(home).with_name("launcher.json")


# ----- entry points ----------------------------------------------------------

def install_app(
        *,
        system: Optional[str] = None,
        home: Optional[Path] = None,
        python: Optional[str] = None,
        path_env: Optional[str] = None,
        run: Callable[[Sequence[str]], subprocess.CompletedProcess] = subprocess.run,
) -> List[Path]:
    """Create (or replace) the launcher; return the files written.

    Args:
        system: ``"mac"``, ``"linux"`` or ``"windows"`` (default: this system).
        home: Home folder (default: the user's).
        python: Python to run (default: this one).
        path_env: PATH for the macOS launcher (default: the current PATH).
        run: Runs helper commands (replaced in tests).
    """
    system = system or current_system()
    home = Path(home) if home is not None else Path.home()
    exe = python_for_launcher(system, python)
    target = launcher_path(system, home)
    if system == "mac":
        return _install_mac(target, exe, path_env if path_env is not None else os.environ.get("PATH", ""), run)
    if system == "windows":
        return _install_windows(target, home, exe, run)
    return _install_linux(target, home, exe, run)


def remove_app(*, system: Optional[str] = None, home: Optional[Path] = None) -> List[Path]:
    """Delete the launcher and its icon copy; return what was removed."""
    system = system or current_system()
    home = Path(home) if home is not None else Path.home()
    paths = [launcher_path(system, home)]
    if system == "linux":
        paths.append(_linux_icon_path(home))
    elif system == "windows":
        paths += [_windows_icon_path(home), _windows_marker_path(home)]
    removed = []
    for path in paths:
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(path)
        elif path.exists():
            path.unlink()
            removed.append(path)
    if system == "windows":
        folder = _windows_icon_path(home).parent
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    return removed


# ----- keeping it current ----------------------------------------------------

def launcher_info(system: Optional[str] = None, home: Optional[Path] = None) -> Optional[Dict[str, str]]:
    """``{"version", "python"}`` of an existing launcher, or ``None`` if there is none.

    ``version`` is the app version that made it (``""`` if not recorded),
    ``python`` the Python it starts (``""`` if unknown).
    """
    system = system or current_system()
    home = Path(home) if home is not None else Path.home()
    target = launcher_path(system, home)
    try:
        if system == "mac":
            plist = target / "Contents" / "Info.plist"
            if not plist.is_file():
                return None
            info = plistlib.loads(plist.read_bytes())
            python = info.get("MBStudioPython", "")
            if not python:  # made by 10.2.0: read it from the start script
                script = target / "Contents" / "MacOS" / info.get("CFBundleExecutable", "")
                for line in script.read_text(encoding="utf-8").splitlines():
                    if line.startswith("exec "):
                        python = shlex.split(line)[1]
            return {"version": str(info.get("CFBundleShortVersionString", "")), "python": python}
        if system == "windows":
            if not target.exists():
                return None
            marker = _windows_marker_path(home)
            data = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else {}
            return {"version": str(data.get("version", "")), "python": str(data.get("python", ""))}
        if not target.is_file():
            return None
        fields = dict(line.split("=", 1) for line in target.read_text(encoding="utf-8").splitlines()
                      if "=" in line)
        python = fields.get("X-MBStudio-Python", "")
        if not python and fields.get("Exec"):  # made by 10.2.0
            python = shlex.split(fields["Exec"])[0]
        return {"version": fields.get("X-MBStudio-Version", ""), "python": python}
    except (OSError, ValueError, IndexError, plistlib.InvalidFileException):
        return {"version": "", "python": ""}


def _same_file(a: str, b: str) -> bool:
    """Whether two paths name the same Python (symlinks resolved)."""
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return a == b


def refresh_if_outdated(*, system: Optional[str] = None, home: Optional[Path] = None,
                        python: Optional[str] = None, path_env: Optional[str] = None,
                        run: Callable[[Sequence[str]], subprocess.CompletedProcess] = subprocess.run
                        ) -> bool:
    """Rebuild the launcher if it starts this installation and an older version made it.

    A launcher of another installation (e.g. a pipx copy while a source
    checkout runs) is left alone. Never raises; returns whether it rebuilt.
    """
    system = system or current_system()
    try:
        info = launcher_info(system, home)
        if info is None or info["version"] == APP_VERSION:
            return False
        if not info["python"] or not _same_file(info["python"], python_for_launcher(system, python)):
            return False
        install_app(system=system, home=home, python=python, path_env=path_env, run=run)
        return True
    except Exception:  # a launcher problem must never stop the app
        return False
