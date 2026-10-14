"""Application-level settings, view preferences, plot style and recent folders.

This module owns all QSettings persistence for the main window: app-default
parameter snapshots, view-preference toggles, the plot's user style (curve
styles, grids; see ``PlotCanvas.get_config``) and the recent-data-folder
history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from PySide6.QtCore import QSettings

from app_io.legacy_keys import migrate_legacy_params, migrate_legacy_config
from utils.helper_funcs import pretty_json, restore_special_floats

if TYPE_CHECKING:
    from PySide6.QtCore import QSettings

    from app.parameter_tabs import ParameterTabsWidget

APP_DEFAULT_CONFIG_KEY = "defaults/parameter_tabs_config"
"""QSettings key used for default parameter-tab configuration."""

APP_DEFAULT_PARAMS_KEY = "defaults/parameter_values"
"""QSettings key used for default parameter values."""

VIEW_PREFERENCE_KEYS = {
    "show_slider_range_labels": "view/show_slider_range_labels",
    "show_w": "view/show_w",
}
"""Map view-action identifiers to their persisted QSettings keys."""

PLOT_CONFIG_KEY = "plot/config"
"""QSettings key of the plot's user style (``PlotCanvas.get_config``)."""

LEGACY_GRID_KEYS = {
    "view/show_time_major_grid": [("top", "x_major"), ("bottom", "x_major")],
    "view/show_time_minor_grid": [("top", "x_minor"), ("bottom", "x_minor")],
    "view/show_flux_major_grid": [("top", "y_major")],
    "view/show_flux_minor_grid": [("top", "y_minor")],
    "view/show_w_major_grid": [("bottom.twin", "y_major")],
    "view/show_w_minor_grid": [("bottom.twin", "y_minor")],
    "view/show_bottom_major_grid": [("bottom", "y_major")],
    "view/show_bottom_minor_grid": [("bottom", "y_minor")],
}
"""Grid preferences of versions before 8.13, and where they go in the plot config."""

LEGACY_LINE_COLOR_PREFIX = "plot_colors/"
"""Prefix of the per-curve colours saved by versions before 8.13."""

RECENT_DATA_FOLDERS_KEY = "recent_data_folders"
"""QSettings key used for the recent-data-folder list."""

MAX_RECENT_DATA_FOLDERS = 8
"""Maximum number of recent data folders to keep."""

RECENT_FOLDER_ACTION_PREFIX = "open_recent_data_folder_"
"""Prefix used for recent-folder menu-action identifiers."""


class Settings:
    """Top-level settings container that aggregates all persistent state."""

    def __init__(
        self,
        organization: str,
        application: str,
    ) -> None:
        """Initialize the settings container.

        Args:
            organization: QSettings organization string.
            application: QSettings application string.
        """
        self._settings = QSettings(organization, application)
        self.recent_folders = RecentFoldersManager(self._settings)

    def _serialize_for_settings(self, obj: Any) -> str:
        """Serialize an object to a JSON string for QSettings storage.

        Args:
            obj: Object to serialize.

        Returns:
            JSON string representation.
        """
        return pretty_json(obj)

    def _deserialize_from_settings(self, text: str) -> Any:
        """Deserialize a JSON string from QSettings.

        Args:
            text: Stored JSON string.

        Returns:
            Deserialized object with special floats restored.
        """
        return restore_special_floats(json.loads(text))

    def load_saved_app_defaults(self) -> tuple[dict, dict] | None:
        """Load saved application defaults from QSettings.

        Legacy parameter keys from older saved defaults are renamed to their
        current names (see ``migrate_legacy_keys``).

        Returns:
            Tuple ``(config, params)`` if saved defaults exist, otherwise
            ``None``.
        """
        config_text = self._settings.value(APP_DEFAULT_CONFIG_KEY, "", type=str)
        params_text = self._settings.value(APP_DEFAULT_PARAMS_KEY, "", type=str)
        if not config_text or not params_text:
            return None
        try:
            config = self._deserialize_from_settings(config_text)
            params = self._deserialize_from_settings(params_text)
        except Exception:
            return None
        return migrate_legacy_config(config), migrate_legacy_params(params)

    def save_as_app_default(self, params_tab_widget: "ParameterTabsWidget") -> Tuple[bool, str]:
        """Save current parameter values and config as new application defaults.

        Args:
            params_tab_widget: Widget whose state should be persisted.

        Returns:
            Tuple ``(success, message)`` where ``message`` is empty on success or
            contains an error description on failure.
        """
        try:
            self._settings.setValue(
                APP_DEFAULT_CONFIG_KEY,
                self._serialize_for_settings(params_tab_widget.get_config()),
            )
            self._settings.setValue(
                APP_DEFAULT_PARAMS_KEY,
                self._serialize_for_settings(params_tab_widget.get_value()),
            )
            self._settings.sync()
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def load_plot_config(self) -> Dict[str, Any]:
        """Return the saved plot style, converting older saved settings once.

        Versions before 8.13 saved grids as view preferences and colours per
        curve; if no plot config exists yet, those are turned into one and
        saved. The old keys are left in place.

        Returns:
            Plot config for ``PlotCanvas.set_config`` (may be empty).
        """
        text = self._settings.value(PLOT_CONFIG_KEY, "", type=str)
        if text:
            try:
                return json.loads(text)
            except ValueError:
                return {}

        config: Dict[str, Any] = {}
        for key, targets in LEGACY_GRID_KEYS.items():
            value = self._settings.value(key, False)
            on = value.strip().lower() in {"1", "true", "yes", "on"} if isinstance(value, str) else bool(value)
            if on:
                for axis_id, grid_key in targets:
                    config.setdefault("axes", {}).setdefault(axis_id, {})[grid_key] = True
        self._settings.beginGroup(LEGACY_LINE_COLOR_PREFIX.rstrip("/"))
        for curve_id in self._settings.childKeys():
            color = self._settings.value(curve_id, "", type=str)
            if color:
                config.setdefault("curves", {}).setdefault(curve_id, {})["color"] = color
        self._settings.endGroup()
        if config:
            self.save_plot_config(config)
        return config

    def save_plot_config(self, config: Dict[str, Any]) -> None:
        """Save the plot style (``PlotCanvas.get_config``)."""
        self._settings.setValue(PLOT_CONFIG_KEY, json.dumps(config))

    def get_view_preference(self, action_id: str, default: bool = False) -> bool:
        """Return one persisted boolean view preference.

        Args:
            action_id: Menu-action identifier used to look up the settings key.
            default: Value returned when the key is not set.

        Returns:
            Stored preference value, or ``default`` if absent.
        """
        key = VIEW_PREFERENCE_KEYS.get(action_id)
        if key is None:
            return default
        value = self._settings.value(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def set_view_preference(self, action_id: str, checked: bool) -> None:
        """Persist one boolean view preference.

        Args:
            action_id: Menu-action identifier used to locate the settings key.
            checked: Boolean state to persist.
        """
        key = VIEW_PREFERENCE_KEYS.get(action_id)
        if key is not None:
            self._settings.setValue(key, checked)


class RecentFoldersManager:
    """Manage the recent-data-folder list and its menu representation."""

    def __init__(self, settings: "QSettings") -> None:
        """Initialize the recent-folders manager.

        Args:
            settings: Application QSettings instance used for persistence.
        """
        self._settings = settings
        self._folders: list[str] = self._load()
        self.action_map: dict[str, str] = {}

    @property
    def folders(self) -> List[str]:
        """Return the current recent-folder list.

        Returns:
            Copy of the stored recent-folder list.
        """
        return list(self._folders)

    def remember(self, folder_path: Path) -> None:
        """Insert a folder at the front of the recent list and persist it.

        Args:
            folder_path: Folder path to remember.
        """
        path_str = str(folder_path.resolve())
        items = [p for p in self._folders if p != path_str]
        items.insert(0, path_str)
        self._folders = items[:MAX_RECENT_DATA_FOLDERS]
        self._save()

    def remove(self, folder_path: str) -> None:
        """Remove one folder from the recent list and persist it.

        Args:
            folder_path: Folder path to remove.
        """
        self._folders = [p for p in self._folders if p != folder_path]
        self._save()

    def clear(self) -> None:
        """Clear the recent-folder list and persist it."""

        self._folders = []
        self._save()

    def build_menu_items(self) -> List[dict[str, Any]]:
        """Build the submenu specification for recent data folders.

        Returns:
            List of menu-item specification dictionaries.
        """
        self.action_map.clear()
        items: list[dict[str, Any]] = []

        if not self._folders:
            items.append({
                "id": "recent_data_folders_empty",
                "text": "No Recent Folders",
                "enabled": False,
            })
        else:
            for index, folder_path in enumerate(self._folders):
                action_id = f"{RECENT_FOLDER_ACTION_PREFIX}{index}"
                self.action_map[action_id] = folder_path
                items.append({
                    "id": action_id,
                    "text": self._format_label(folder_path),
                    "enabled": True,
                })
            items.append({"id": "sep"})

        items.append({
            "id": "clear_recent_data_folders",
            "text": "Clear Recent Data Folders",
            "enabled": bool(self._folders),
        })
        return items

    def _load(self) -> List[str]:
        """Load and sanitize the recent-folder list from QSettings.

        Returns:
            List of valid, unique recent-folder paths.
        """
        value = self._settings.value(RECENT_DATA_FOLDERS_KEY, [])
        if value is None:
            raw: list[str] = []
        elif isinstance(value, str):
            raw = [value]
        else:
            raw = [str(v) for v in value if v]

        unique: list[str] = []
        seen: set[str] = set()
        for folder in raw:
            try:
                path_str = str(Path(folder).resolve())
            except Exception:
                continue
            if path_str in seen or not Path(path_str).exists():
                continue
            seen.add(path_str)
            unique.append(path_str)
        return unique[:MAX_RECENT_DATA_FOLDERS]

    def _save(self) -> None:
        """Persist the current recent-folder list."""
        self._settings.setValue(RECENT_DATA_FOLDERS_KEY, self._folders)

    @staticmethod
    def _format_label(folder_path: str) -> str:
        """Build the menu label for one recent folder.

        Args:
            folder_path: Absolute folder path.

        Returns:
            Formatted menu label.
        """
        path = Path(folder_path)
        parent_name = path.parent.name or "/"
        return f"{path.name}    [{parent_name}]"
