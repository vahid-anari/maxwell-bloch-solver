"""Application-level settings, view preferences, line colors, and recent folders.

This module owns all QSettings persistence for the main window: app-default
parameter snapshots, view-preference toggles, per-curve line colors, and the
recent-data-folder history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

from matplotlib import colors as mcolors
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QColorDialog

from utils.helper_funcs import pretty_json, restore_special_floats

if TYPE_CHECKING:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QWidget

    from app.parameter_tabs import ParameterTabsWidget
    from app.plot import PlotCanvas
    from ui.menu_bar_controller import MenuBarController

APP_DEFAULT_CONFIG_KEY = "defaults/parameter_tabs_config"
"""QSettings key used for default parameter-tab configuration."""

APP_DEFAULT_PARAMS_KEY = "defaults/parameter_values"
"""QSettings key used for default parameter values."""

VIEW_PREFERENCE_KEYS = {
    "show_time_major_grid": "view/show_time_major_grid",
    "show_time_minor_grid": "view/show_time_minor_grid",
    "show_flux_major_grid": "view/show_flux_major_grid",
    "show_flux_minor_grid": "view/show_flux_minor_grid",
    "show_bottom_major_grid": "view/show_bottom_major_grid",
    "show_bottom_minor_grid": "view/show_bottom_minor_grid",
    "show_slider_range_labels": "view/show_slider_range_labels",
}
"""Map view-action identifiers to their persisted QSettings keys."""

LINE_COLOR_SETTINGS_PREFIX = "plot_colors/"
"""Prefix used for persisted line-color settings."""

LINE_COLOR_ACTION_PREFIX = "set_line_color__"
"""Prefix used for line-color menu-action identifiers."""

RESET_LINE_COLORS_ACTION_ID = "reset_line_colors"
"""Menu-action identifier for restoring default line colors."""

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
        canvas: "PlotCanvas",
        default_lines_config: Dict[str, Any],
    ) -> None:
        """Initialize the settings container.

        Args:
            organization: QSettings organization string.
            application: QSettings application string.
            canvas: Plot canvas whose line colors are managed.
            default_lines_config: Factory-default line-configuration mapping.
        """
        self._settings = QSettings(organization, application)
        self.recent_folders = RecentFoldersManager(self._settings)
        self.line_colors = LineColorManager(
            canvas=canvas,
            settings=self._settings,
            default_lines_config=default_lines_config,
        )

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

        Returns:
            Tuple ``(config, params)`` if saved defaults exist, otherwise
            ``None``.
        """
        config_text = self._settings.value(APP_DEFAULT_CONFIG_KEY, "", type=str)
        params_text = self._settings.value(APP_DEFAULT_PARAMS_KEY, "", type=str)
        if not config_text or not params_text:
            return None
        try:
            return (
                self._deserialize_from_settings(config_text),
                self._deserialize_from_settings(params_text),
            )
        except Exception:
            return None

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


class LineColorManager:
    """Manage curve colors, their persistence, and related menu icons."""

    def __init__(
        self,
        canvas: "PlotCanvas",
        settings: "QSettings",
        default_lines_config: Dict[str, Any],
    ) -> None:
        """Initialize the line-color manager.

        Args:
            canvas: Plot canvas whose curve colors are managed.
            settings: Application QSettings instance.
            default_lines_config: Factory-default line-configuration mapping.
        """
        self._canvas = canvas
        self._settings = settings
        self._default_lines_config = default_lines_config

    def apply_saved_colors(self) -> None:
        """Apply persisted colors to the canvas and redraw it."""

        self._canvas.apply_curve_colors(self.load_saved_colors())
        self._canvas.redraw()

    def load_saved_colors(self) -> Dict[str, str]:
        """Return a mapping of curve IDs to colors.

        Returns:
            Mapping containing default colors merged with any saved overrides.
        """
        colors = self._get_default_colors()
        for curve_id in colors:
            saved = self._settings.value(self._settings_key(curve_id), "", type=str)
            if saved:
                colors[curve_id] = saved
        return colors

    def choose_color(
        self,
        curve_id: str,
        parent: "QWidget",
        menu_bar: "MenuBarController",
        on_combo_icons_changed: Callable[[], None],
    ) -> None:
        """Open a color dialog, then persist and apply the chosen color.

        Args:
            curve_id: Internal curve identifier.
            parent: Parent widget for the color dialog.
            menu_bar: Menu controller whose icons should be updated.
            on_combo_icons_changed: Callback invoked after icon updates.
        """
        current = self._canvas.get_curve_color(curve_id) or "#000000"
        color = QColorDialog.getColor(QColor(current), parent, "Choose Line Color")
        if not color.isValid():
            return

        color_name = color.name()
        if self._canvas.set_curve_color(curve_id, color_name):
            self._save_color(curve_id, color_name)
            self._update_menu_icon(menu_bar, curve_id, color_name)
            on_combo_icons_changed()
            self._canvas.redraw()

    def reset_to_defaults(
        self,
        menu_bar: "MenuBarController",
        on_combo_icons_changed: Callable[[], None],
    ) -> None:
        """Restore all curve colors to factory defaults.

        Args:
            menu_bar: Menu controller whose icons should be updated.
            on_combo_icons_changed: Callback invoked after icon updates.
        """
        defaults = self._get_default_colors()
        self._canvas.apply_curve_colors(defaults)
        for curve_id, color in defaults.items():
            self._save_color(curve_id, color)
            self._update_menu_icon(menu_bar, curve_id, color)
        on_combo_icons_changed()
        self._canvas.redraw()

    def update_all_menu_icons(self, menu_bar: "MenuBarController") -> None:
        """Refresh every line-color menu icon to match saved colors.

        Args:
            menu_bar: Menu controller whose icons should be updated.
        """
        for curve_id, color in self.load_saved_colors().items():
            self._update_menu_icon(menu_bar, curve_id, color)

    def build_menu_items(self) -> List[Dict[str, Any]]:
        """Build menu-item specifications for the line-colors submenu.

        Returns:
            List of menu-item specification dictionaries.
        """
        items: List[Dict[str, Any]] = [
            {"id": f"{LINE_COLOR_ACTION_PREFIX}data_points", "text": "Data Points..."},
            {"id": f"{LINE_COLOR_ACTION_PREFIX}flux", "text": "Flux..."},
            {"id": "sep"},
        ]
        bottom_panel = self._default_lines_config.get("bottom_panel", {})
        for name, props in bottom_panel.items():
            text = props.get("combo_label") or props.get("label") or name
            items.append({"id": f"{LINE_COLOR_ACTION_PREFIX}{name}", "text": f"{text}..."})

        items.append({"id": "sep"})
        items.append({"id": RESET_LINE_COLORS_ACTION_ID, "text": "Restore Default Line Colors"})
        return items

    @staticmethod
    def make_color_icon(color: str, size: int = 12) -> QIcon:
        """Return a square icon filled with a given color.

        Args:
            color: Color value.
            size: Icon size in pixels.

        Returns:
            Qt icon filled with the requested color.
        """
        pix = QPixmap(size, size)
        pix.fill(QColor(mcolors.to_hex(color)))
        return QIcon(pix)

    def _get_default_colors(self) -> Dict[str, str]:
        """Extract factory-default curve colors from the line config.

        Returns:
            Mapping from curve identifiers to default colors.
        """
        lines = self._default_lines_config
        out: Dict[str, str] = {}
        top_panel = lines.get("top_panel", {})
        for name in ("data_points", "flux"):
            color = top_panel.get(name, {}).get("props", {}).get("color")
            if color:
                out[name] = str(color)
        for name, item in lines.get("bottom_panel", {}).items():
            color = item.get("props", {}).get("color")
            if color:
                out[name] = str(color)
        return out

    def _settings_key(self, curve_id: str) -> str:
        """Return the QSettings key for a curve color.

        Args:
            curve_id: Internal curve identifier.

        Returns:
            Full QSettings key string.
        """
        return f"{LINE_COLOR_SETTINGS_PREFIX}{curve_id}"

    def _save_color(self, curve_id: str, color: str) -> None:
        """Persist one curve color.

        Args:
            curve_id: Internal curve identifier.
            color: Color value to persist.
        """
        self._settings.setValue(self._settings_key(curve_id), color)

    def _update_menu_icon(self, menu_bar: "MenuBarController", curve_id: str, color: str) -> None:
        """Update the menu icon associated with one curve color.

        Args:
            menu_bar: Menu controller holding the relevant action.
            curve_id: Internal curve identifier.
            color: New color value.
        """
        action_id = f"{LINE_COLOR_ACTION_PREFIX}{curve_id}"
        action = menu_bar._actions.get(action_id)
        if action is not None:
            action.setIcon(self.make_color_icon(color))
            action.setIconVisibleInMenu(True)


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
