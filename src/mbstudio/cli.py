"""The ``mbstudio`` command: start the app, or work from the terminal.

    mbstudio                      start the app
    mbstudio PATH                 start the app and open a parameter file or data folder
    mbstudio --version            print the versions
    mbstudio update [--check]     update the app (or only check for a newer version)
    mbstudio solve FILE [...]     solve a parameter file without the window
    mbstudio example [PATH]       save the example script for your own Python scripts
    mbstudio install-app          add the app to Applications / the Start menu / the app menu

Only starting the app imports Qt widgets; the other commands stay light.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from importlib import metadata
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from mbstudio.config.app_metadata import APP_NAME, APP_VERSION, DIST_NAME, GITHUB_REPO

PROG = "mbstudio"
COMMANDS = ("update", "solve", "example", "install-app")
TIMEOUT_S = 10

PYPI_JSON_URL = f"https://pypi.org/pypi/{DIST_NAME}/json"
RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=30"


# --version -------------------------------------------------------------------

def _dist_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


def version_text() -> str:
    """One line with the app, solver, widget and Python versions."""
    return (
        f"{APP_NAME} {APP_VERSION} "
        f"(mbsolver {_dist_version('mbsolver')}, sciwidgets {_dist_version('sciwidgets')}, "
        f"Python {platform.python_version()})"
    )


# update ----------------------------------------------------------------------

def _get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_latest_version() -> str:
    """Latest version on PyPI. Raises ``OSError``/``ValueError`` when it cannot be read."""
    return str(_get_json(PYPI_JSON_URL)["info"]["version"])


def fetch_release_notes(current: str, latest: str) -> List[Tuple[str, str]]:
    """Notes of the versions after ``current`` up to ``latest``; empty if GitHub can't be read."""
    from mbstudio.app.update_checker import newer_release_notes

    try:
        data = _get_json(RELEASES_API_URL)
    except (OSError, ValueError):
        return []
    return newer_release_notes(data, current, latest) if isinstance(data, list) else []


def install_kind() -> str:
    """How this copy was installed: ``"editable"``, ``"pipx"``, ``"pip"`` or ``"unknown"``."""
    try:
        dist = metadata.distribution(DIST_NAME)
    except metadata.PackageNotFoundError:
        return "unknown"
    direct = dist.read_text("direct_url.json")
    if direct:
        try:
            if json.loads(direct).get("dir_info", {}).get("editable"):
                return "editable"
        except ValueError:
            pass
    parts = Path(sys.prefix).parts
    if "pipx" in parts and "venvs" in parts:
        return "pipx"
    return "pip"


def update_command(kind: str) -> Optional[List[str]]:
    """The command that updates an installation of the given kind, or ``None``."""
    if kind == "pipx":
        return [shutil.which("pipx") or "pipx", "upgrade", DIST_NAME]
    if kind == "pip":
        return [sys.executable, "-m", "pip", "install", "--upgrade", DIST_NAME]
    return None


def cmd_update(
    args: argparse.Namespace,
    *,
    latest_version: Callable[[], str] = fetch_latest_version,
    release_notes: Callable[[str, str], List[Tuple[str, str]]] = fetch_release_notes,
    kind: Callable[[], str] = install_kind,
    ask: Callable[[str], str] = input,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> int:
    """``mbstudio update [--check] [--yes]``."""
    from mbstudio.app.update_checker import parse_version

    try:
        latest = latest_version()
    except (OSError, ValueError, KeyError) as exc:
        print(f"Could not check for updates: {exc}", file=sys.stderr)
        return 1

    if parse_version(latest) <= parse_version(APP_VERSION):
        print(f"{APP_NAME} {APP_VERSION} is the latest version.")
        return 0

    print(f"{APP_NAME} {latest} is available. You have version {APP_VERSION}.")
    notes = release_notes(APP_VERSION, latest)
    if notes:
        print("\nWhat's new:")
        for version, body in notes:
            print(f"\n{version}")
            print("\n".join(f"  {line}" for line in body.splitlines()))
        print()
    if args.check:
        return 0

    how = kind()
    if how == "editable":
        print("This copy runs from a source folder (pip install -e). "
              "Update it there with: git pull", file=sys.stderr)
        return 1
    command = update_command(how)
    if command is None:
        print(f"Cannot tell how {DIST_NAME} was installed; update it with "
              f"pipx upgrade {DIST_NAME} or pip install -U {DIST_NAME}.", file=sys.stderr)
        return 1

    shown = " ".join(command)
    if not args.yes:
        answer = ask(f"Run: {shown}  [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Nothing changed.")
            return 0
    print(f"Running: {shown}")
    return run(command).returncode


# solve -----------------------------------------------------------------------

def _velocity_tag(velocity: str) -> str:
    return "v" + velocity.replace("/", "_")


def cmd_solve(args: argparse.Namespace) -> int:
    """``mbstudio solve FILE [--velocity V | --all] [-o OUT]``."""
    import numpy as np

    from mbstudio.api import ParamsFile, solve

    try:
        f = ParamsFile(args.file)
    except (OSError, ValueError) as exc:
        print(f"Cannot read {args.file}: {exc}", file=sys.stderr)
        return 1

    if f.is_fit:
        if args.all:
            velocities = f.velocities
        elif args.velocity is not None:
            velocities = [args.velocity]
        else:
            print(f"{Path(args.file).name} holds several velocities: {', '.join(f.velocities)}\n"
                  "Choose one with --velocity V, or solve them all with --all.", file=sys.stderr)
            return 1
        if args.output and len(velocities) > 1:
            print("-o/--output names one file; with --all the files are named after the "
                  "velocities. Use --output-dir instead.", file=sys.stderr)
            return 1
    else:
        if args.velocity is not None or args.all:
            print(f"{Path(args.file).name} is a plain parameter file; it has no velocities.",
                  file=sys.stderr)
            return 1
        velocities = [None]

    stem = Path(args.file).stem
    out_dir = Path(args.output_dir) if args.output_dir else Path(args.file).parent
    for velocity in velocities:
        try:
            params = f.params(velocity)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if args.output:
            out = Path(args.output)
        else:
            name = stem if velocity is None else f"{stem}_{_velocity_tag(str(velocity))}"
            out = out_dir / f"{name}_results.npz"
        start = time.perf_counter()
        try:
            res = solve(params)
        except KeyError as exc:
            print(f"Missing parameter in {args.file}: {exc}", file=sys.stderr)
            return 1
        seconds = time.perf_counter() - start
        out.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out, params=np.array(json.dumps(params)), **res)
        label = "" if velocity is None else f" v = {velocity}:"
        print(f"Solved{label} {res['intensity'].shape[1]} times x {res['intensity'].shape[0]} "
              f"z planes in {seconds:.2f} s -> {out}")
    return 0


# example ---------------------------------------------------------------------

def cmd_example(args: argparse.Namespace) -> int:
    """``mbstudio example [PATH] [--force]``."""
    from mbstudio.paths import EXAMPLE_SCRIPT_PATH

    out = Path(args.path)
    if out.exists() and not args.force:
        print(f"{out} already exists; use --force to overwrite it.", file=sys.stderr)
        return 1
    out.write_text(EXAMPLE_SCRIPT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


# install-app -----------------------------------------------------------------

PLACE = {"mac": "your Applications folder (also in Launchpad and Spotlight)",
         "linux": "the applications menu",
         "windows": "the Start menu"}


def cmd_install_app(args: argparse.Namespace) -> int:
    """``mbstudio install-app [--remove]``."""
    from mbstudio import launcher

    system = launcher.current_system()
    if args.remove:
        removed = launcher.remove_app(system=system)
        if not removed:
            print("No launcher found; nothing removed.")
        for path in removed:
            print(f"Removed {path}")
        return 0
    try:
        written = launcher.install_app(system=system)
    except (OSError, ValueError) as exc:
        print(f"Could not create the launcher: {exc}", file=sys.stderr)
        return 1
    print(f"Created {written[0]}")
    print(f"{APP_NAME} is now in {PLACE[system]}.")
    note = " (your source folder)" if install_kind() == "editable" else ""
    print(f"It starts the installation of this Python{note}: {launcher.python_for_launcher(system)}")
    if system == "mac":
        print("Drag it to the Dock to keep it there. Run this command again if you move Python.")
    return 0


# parsers ---------------------------------------------------------------------

EPILOG = """\
commands:
  update [--check]      update the app, or only show whether a newer version exists
  solve FILE            solve a saved parameter file without the window
  example [PATH]        save the example script for your own Python scripts
  install-app           add the app to Applications / the Start menu / the app menu

Use 'mbstudio COMMAND --help' for the options of a command.
"""


def _main_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=f"{APP_NAME}: simulate and fit Maxwell-Bloch models of maser light curves. "
                    "Without arguments, starts the app.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", nargs="?",
                        help="parameter file or data folder to open in the app")
    parser.add_argument("-V", "--version", action="store_true", help="print the versions and exit")
    return parser


def _command_parser(command: str) -> argparse.ArgumentParser:
    if command == "update":
        p = argparse.ArgumentParser(
            prog=f"{PROG} update",
            description="Update the app, after showing what is new. Detects a pipx or pip "
                        "installation and runs the matching command.")
        p.add_argument("--check", action="store_true",
                       help="only show whether a newer version exists and what is new")
        p.add_argument("-y", "--yes", action="store_true", help="do not ask before updating")
    elif command == "solve":
        p = argparse.ArgumentParser(
            prog=f"{PROG} solve",
            description="Solve a parameter file saved by the app, without the window, and save "
                        "the results (same numbers as the app) to a .npz file. The file holds "
                        "the arrays time, intensity, w, lambda_n, A0, t1, t2 and the parameters "
                        "as JSON text (params).")
        p.add_argument("file", help="parameter file saved by the app")
        p.add_argument("--velocity", help="velocity component, for the parameter file of a data folder")
        p.add_argument("--all", action="store_true", help="solve every velocity of a data-folder file")
        p.add_argument("-o", "--output", help="result file (default: FILE_results.npz next to FILE)")
        p.add_argument("--output-dir", help="folder for the result files (default: next to FILE)")
    elif command == "install-app":
        p = argparse.ArgumentParser(
            prog=f"{PROG} install-app",
            description="Make a launcher so the app starts with a double-click: an app in "
                        "~/Applications on macOS, a Start-menu shortcut on Windows, an entry in "
                        "the applications menu on Linux. It starts this installation, so it "
                        "keeps working after 'mbstudio update'.")
        p.add_argument("--remove", action="store_true", help="remove the launcher")
    else:
        p = argparse.ArgumentParser(
            prog=f"{PROG} example",
            description="Save the commented example script that shows how to use saved "
                        "parameter files from Python (as Help > Use from Python...).")
        p.add_argument("path", nargs="?", default="mbstudio_example.py",
                       help="where to save it (default: mbstudio_example.py)")
        p.add_argument("--force", action="store_true", help="overwrite an existing file")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point of the ``mbstudio`` command."""
    args_list = list(sys.argv[1:] if argv is None else argv)
    args_list = [a for a in args_list if not a.startswith("-psn_")]  # old macOS Finder argument

    if args_list and args_list[0] in COMMANDS:
        command = args_list[0]
        args = _command_parser(command).parse_args(args_list[1:])
        handler = {"update": cmd_update, "solve": cmd_solve, "example": cmd_example,
                   "install-app": cmd_install_app}[command]
        return handler(args)

    args = _main_parser().parse_args(args_list)
    if args.version:
        print(version_text())
        return 0

    from mbstudio.main import main as start_app

    return start_app([sys.argv[0] if sys.argv else PROG], open_path=args.path)


if __name__ == "__main__":
    raise SystemExit(main())
