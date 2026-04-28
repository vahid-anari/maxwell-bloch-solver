"""File I/O helpers for importing light curves and related parameter sets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QWidget

from dialogs.dialogs import PeriodInfo, SelectPeriodDialog, show_folder_summary, show_warning
from utils.helper_funcs import restore_special_floats


@dataclass
class LightCurve:
    """Simple time-series container for one light curve.

    Attributes:
        time: Sample times for the light curve.
        flux: Flux values corresponding to ``time``.
    """

    time: np.ndarray
    flux: np.ndarray


@dataclass
class DataFolderInfo:
    """Summary information gathered while scanning a data folder.

    Attributes:
        source: Source name inferred from the file names.
        path: Path to the scanned folder.
        has_periods: Whether the folder contains period-tagged data files.
        periods: Mapping from period labels to per-period summary information.
        no_period_info: Summary information for non-period-tagged data, if
            applicable.
    """

    source: str
    path: Path
    has_periods: bool
    periods: dict[str, PeriodInfo]
    no_period_info: Optional[PeriodInfo]


@dataclass
class ImportedDataFolder:
    """Bundle of imported light curves, parameters, and folder metadata.

    Attributes:
        folder_info: Summary information about the imported folder.
        selected_period: Selected period label, if one was chosen.
        data: Mapping from velocity labels to loaded light curves.
        params: Loaded parameter snapshot, if one was found.
    """

    folder_info: Optional[DataFolderInfo]
    selected_period: Optional[str]
    data: Optional[dict[str, LightCurve]]
    params: Optional[dict[str, Any]]


def select_folder(parent: Optional[QWidget] = None) -> Optional[Path]:
    """Open a folder picker and return the selected directory path.

    Args:
        parent: Optional parent widget for the file dialog.

    Returns:
        Selected folder path, or ``None`` if the dialog is canceled.
    """

    folder = QFileDialog.getExistingDirectory(
        parent,
        "Select folder containing txt files",
    )
    if not folder:
        return None
    return Path(folder)


def parse_data_filename(filename: str) -> dict[str, Any]:
    """Parse a light-curve filename.

    Supported examples include:

    - ``Source_v=12.3.txt``
    - ``Source_p1_v=123.1.txt``

    Args:
        filename: File name to parse.

    Returns:
        Mapping containing ``source``, ``period``, and ``velocity``.

    Raises:
        ValueError: If ``filename`` does not match the expected pattern.
    """
    pattern = re.compile(
        r"^(?P<source>.+?)(?:_(?P<period>p\d+))?_v=(?P<velocity>[-+]?\d*\.?\d+)\.txt$"
    )

    match = pattern.match(filename)
    if match is None:
        raise ValueError(f"Invalid filename format: {filename}")

    return {
        "source": match.group("source"),
        "period": match.group("period"),
        "velocity": match.group("velocity"),
    }


def parse_params_filename(filename: str) -> dict[str, Any]:
    """Parse a parameter-file name.

    Args:
        filename: File name to parse.

    Returns:
        Mapping containing ``source`` and ``period``.

    Raises:
        ValueError: If ``filename`` does not match the expected pattern.
    """

    pattern = re.compile(
        r"^(?P<source>.+?)(?:_(?P<period>p\d+))?_params\.json$"
    )

    match = pattern.match(filename)
    if match is None:
        raise ValueError(f"Invalid params filename format: {filename}")

    return {
        "source": match.group("source"),
        "period": match.group("period"),
    }


def analyze_folder(
    folder_path: Path,
    parent: Optional[QWidget] = None,
) -> Optional[DataFolderInfo]:
    """Scan a source folder and summarize the files it contains.

    Args:
        folder_path: Folder to analyze.
        parent: Optional parent widget for warning dialogs.

    Returns:
        Summary information for the folder, or ``None`` if the folder contents
        are invalid for import.
    """

    folder_path = Path(folder_path)
    txt_files = sorted(folder_path.glob("*.txt"))
    json_files = sorted(folder_path.glob("*.json"))

    if not txt_files:
        show_warning(
            "No text files found",
            f"No .txt files were found in:\n{folder_path}",
            parent=parent
        )
        return None

    source_names: set[str] = set()
    period_velocities: dict[str, list[str]] = {}
    no_period_velocities: list[str] = []

    for txt_path in txt_files:
        try:
            info = parse_data_filename(txt_path.name)
        except ValueError:
            continue

        source_names.add(info["source"])
        period = info["period"]
        velocity = info["velocity"]

        if period is None:
            no_period_velocities.append(velocity)
        else:
            period_velocities.setdefault(period, []).append(velocity)

    if not source_names:
        show_warning(
            "Invalid file names",
            "No valid data files were found with the expected naming pattern.",
            parent=parent
        )
        return None

    if len(source_names) > 1:
        show_warning(
            "Multiple sources found",
            f"More than one source name was found in this folder:\n{sorted(source_names)}",
            parent=parent
        )
        return None

    if period_velocities and no_period_velocities:
        show_warning(
            "Mixed file types",
            "The folder contains both period-tagged and non-period-tagged data files.",
            parent=parent
        )
        return None

    source = next(iter(source_names))

    for p in period_velocities:
        period_velocities[p].sort(key=float)
    no_period_velocities.sort(key=float)

    params_no_period = False
    params_by_period: dict[str, bool] = {}

    for json_path in json_files:
        try:
            info = parse_params_filename(json_path.name)
        except ValueError:
            continue

        if info["source"] != source:
            continue

        period = info["period"]
        if period is None:
            params_no_period = True
        else:
            params_by_period[period] = True

    if period_velocities:
        periods: dict[str, PeriodInfo] = {}
        for period, velocities in period_velocities.items():
            periods[period] = PeriodInfo(
                n_velocities=len(velocities),
                has_params=params_by_period.get(period, False),
            )

        return DataFolderInfo(
            source=source,
            path=folder_path,
            has_periods=True,
            periods=periods,
            no_period_info=None,
        )

    return DataFolderInfo(
        source=source,
        path=folder_path,
        has_periods=False,
        periods={},
        no_period_info=PeriodInfo(
            n_velocities=len(no_period_velocities),
            has_params=params_no_period,
        ),
    )


def select_period_if_needed(
    folder_info: DataFolderInfo,
    parent: Optional[QWidget] = None,
) -> Optional[str]:
    """Return a selected period label when period-tagged data exist.

    Args:
        folder_info: Summary information for the scanned folder.
        parent: Optional parent widget for the selection dialog.

    Returns:
        Selected period label, or ``None`` when no period is needed or the user
        cancels the selection dialog.
    """
    if not folder_info.has_periods:
        return None

    periods_keys = sorted(
        folder_info.periods.keys(),
        key=lambda s: int(s[1:])
    )

    if len(periods_keys) == 1:
        return periods_keys[0]

    dlg = SelectPeriodDialog(
        source=folder_info.source,
        periods_keys=periods_keys,
        periods=folder_info.periods,
        parent=parent,
    )
    if dlg.exec() == QDialog.Accepted:
        return dlg.selected_period()

    return None


def load_velocity_files(
    folder: Path,
    selected_period: Optional[str] = None,
) -> dict[str, LightCurve]:
    """Load all matching light-curve files from a source folder.

    Args:
        folder: Folder containing the text files.
        selected_period: Period label to filter by. Use ``None`` for files
            without period tags.

    Returns:
        Mapping from velocity labels to loaded light curves.
    """

    folder = Path(folder)
    all_v: dict[str, LightCurve] = {}

    for txt_path in sorted(folder.glob("*.txt")):
        try:
            meta = parse_data_filename(txt_path.name)
        except ValueError:
            continue

        if meta["period"] != selected_period:
            continue

        time_vals = []
        flux_vals = []

        with txt_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                if len(parts) < 2:
                    continue

                try:
                    time = float(parts[0])
                    flux = float(parts[1])
                except ValueError:
                    continue

                time_vals.append(time)
                flux_vals.append(flux)

        v = meta["velocity"]
        all_v[v] = LightCurve(
            time=np.array(time_vals, dtype=float),
            flux=np.array(flux_vals, dtype=float),
        )

    return all_v


def load_params_file(
    folder: Path,
    source: str,
    selected_period: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Load a parameter JSON file for the selected source and period.

    Args:
        folder: Folder containing the parameter file.
        source: Source name used in the file name.
        selected_period: Optional period label.

    Returns:
        Parsed JSON content with restored special floats, or ``None`` if the
        parameter file does not exist.
    """
    folder = Path(folder)

    if selected_period is None:
        filename = f"{source}_params.json"
    else:
        filename = f"{source}_{selected_period}_params.json"

    params_path = folder / filename
    if not params_path.exists():
        return None

    with params_path.open("r", encoding="utf-8") as f:
        return restore_special_floats(json.load(f))


def show_data_folder_summary(
    folder_info: DataFolderInfo,
    selected_period: Optional[str] = None,
    parent: Optional[QWidget] = None,
) -> None:
    """Display a summary dialog for the selected data folder.

    Args:
        folder_info: Summary information for the folder.
        selected_period: Optional selected period label.
        parent: Optional parent widget for the summary dialog.
    """

    if selected_period is None:
        if folder_info.no_period_info is None:
            return
        n_velocities = folder_info.no_period_info.n_velocities
        has_params = folder_info.no_period_info.has_params
    else:
        period_info = folder_info.periods[selected_period]
        n_velocities = period_info.n_velocities
        has_params = period_info.has_params

    show_folder_summary(
        source=folder_info.source,
        n_velocities=n_velocities,
        has_params=has_params,
        selected_period=selected_period,
        parent=parent,
    )


def import_data_folder(
    parent: Optional[QWidget] = None,
) -> ImportedDataFolder:
    """Import one data folder together with any matching saved parameters.

    Args:
        parent: Optional parent widget for dialogs.

    Returns:
        Bundle containing folder metadata, selected period, loaded light curves,
        and any loaded parameter snapshot.
    """

    folder = select_folder(parent)
    if folder is None:
        return ImportedDataFolder(None, None, None, None)

    folder_info = analyze_folder(folder, parent)
    if folder_info is None:
        return ImportedDataFolder(None, None, None, None)

    if folder_info.has_periods:
        selected_period = select_period_if_needed(folder_info, parent)
        if selected_period is None:
            return ImportedDataFolder(folder_info, None, None, None)
    else:
        selected_period = None

    show_data_folder_summary(
        folder_info=folder_info,
        selected_period=selected_period,
        parent=parent,
    )

    all_v = load_velocity_files(folder, selected_period)
    params = load_params_file(
        folder=folder,
        source=folder_info.source,
        selected_period=selected_period,
    )

    return ImportedDataFolder(
        folder_info=folder_info,
        selected_period=selected_period,
        data=all_v,
        params=params,
    )


def _demo_main() -> int:
    """Run the data-import helpers as a small standalone demo.

    Returns:
        Process exit code.
    """

    from settings.app_style import set_app_style

    app = QApplication([])
    set_app_style(app)
    result = import_data_folder()

    if result.folder_info is not None and result.data is not None:
        print("SourceSelection name:", result.folder_info.source)
        print("Has periods:", result.folder_info.has_periods)
        print("Selected period:", result.selected_period)

        print("Velocities:")
        for v in sorted(result.data, key=float):
            print(v, len(result.data[v].time))

        print("Params:", result.params)
    return 0


if __name__ == "__main__":
    raise SystemExit(_demo_main())
