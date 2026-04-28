"""Main application window for the Maxwell-Bloch solver GUI.

This module wires together the parameter widgets, plotting canvas, data
import/export logic, status controls, and the extracted coordinator
objects.
"""

from __future__ import annotations

import copy
import getpass
import sys
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from app.parameter_tabs import ParameterTabsWidget
from app.plot import PlotCanvas, PlotExporter
from app.settings_manager import (
    LINE_COLOR_ACTION_PREFIX,
    RESET_LINE_COLORS_ACTION_ID,
    LineColorManager,
    Settings,
)
from app.solver_controller import SolverController
from app.update_pipeline import DisplayedCurves, UpdatePipeline
from app.velocity_bar_controller import VelocityBarController
from app_io.data_io import (
    LightCurve,
    analyze_folder,
    load_params_file,
    load_velocity_files,
    select_folder,
    select_period_if_needed,
    show_data_folder_summary,
)
from app_io.parameter_io import (
    open_parameters,
    save_parameters,
    save_parameters_as,
    save_params_atomic,
)
from dialogs.dialogs import (
    AskResult,
    ask_question,
    show_about_dialog,
    show_critical,
    show_information,
)
from paths import DOCUMENTATION_PATH, EQUATIONS_PDF_PATH, SETTINGS_FILE_PATH, USER_GUIDE_PATH
from settings.app_metadata import (
    APP_AUTHOR_EMAIL,
    APP_AUTHOR_GITHUB,
    APP_AUTHOR_NAME,
    APP_AUTHOR_WEBSITE,
    APP_NAME,
    APP_VERSION,
)
from settings.app_style import set_app_style
from settings.ui_defaults import NATIVE_MENU_BAR
from solver.maxwell_bloch_solver import solve_maxwell_bloch
from ui.menu_bar_controller import QAction, QKeySequence, MenuBarController
from ui.splash_screen import show_splash_message
from ui.status_bar_controller import StatusBarController, StatusState
from utils.helper_funcs import pretty_json, read_json, set_nested_bool_key, set_win_center
from utils.solver_step_viewer import StepScatterWidget
from utils.units import VELOCITY_UNIT_TEXT

show_splash_message("Importing basic packages...")
show_splash_message("Importing config packages / menu bar...")
show_splash_message("Importing config packages / velocity bar...")
show_splash_message("Importing config packages / plot...")
show_splash_message("Importing config packages / parameters tabs...")
show_splash_message("Importing config packages / status bar...")
show_splash_message("Importing config packages / solver...")
show_splash_message("Importing config packages / pipe line...")
show_splash_message("Importing config packages / settings manager...")
show_splash_message("Importing config packages / recent folders...")
show_splash_message("Importing config packages / data I/O...")
show_splash_message("Importing config packages / parameters I/O...")
show_splash_message("Importing config packages / dialogs...")
show_splash_message("Importing config packages / paths...")
show_splash_message("Importing config packages / style...")
show_splash_message("Importing config packages / helper functions...")

MENU_CHECKABLE_IDS = (
    "show_time_major_grid",
    "show_time_minor_grid",
    "show_flux_major_grid",
    "show_flux_minor_grid",
    "show_bottom_major_grid",
    "show_bottom_minor_grid",
    "show_slider_range_labels",
)
"""Action IDs whose checked states are persisted across sessions."""


@dataclass
class SourceSelection:
    """Information about the currently loaded source folder and period.

    Attributes:
        name: Source name inferred from the loaded folder.
        path: Path to the loaded source folder.
        period: Selected period label, if applicable.
    """

    name: str = ""
    path: Optional[Path] = None
    period: Optional[str] = None


def make_empty_light_curve() -> LightCurve:
    """Create an empty light-curve container.

    Returns:
        Empty ``LightCurve`` instance with zero-length time and flux arrays.
    """
    return LightCurve(np.empty(0), np.empty(0))


show_splash_message("Creating Main GUI...")


class MBESolverApp(QMainWindow):
    """Main application window that orchestrates all coordinator objects."""

    def __init__(self, app: QApplication) -> None:
        """Initialize the main solver window and connect all coordinators.

        Args:
            app: Running Qt application instance.
        """
        super().__init__()

        self.setWindowTitle("Maxwell Bloch Solver")
        self.resize(1400, 600)
        set_app_style(app)
        set_win_center(self, app)

        # ---- plain state ----
        self._fit_mode = False
        self._show_cosh_peak = False
        self._cosh_peak_path: Optional[str] = None
        self._last_z_arr_length = -1
        self._step_viewer_window = None

        self._source_selection = SourceSelection()
        self._params_path: Optional[Path] = None
        self._all_params: dict[str, dict[str, Any]] = {}
        self._all_data: dict[str, LightCurve] = {}
        self._current_data = make_empty_light_curve()
        self._results: dict[str, Any] = {}

        default_config = read_json(SETTINGS_FILE_PATH)
        self._default_config = copy.deepcopy(default_config)
        self._factory_default_config = copy.deepcopy(default_config["tabs"])

        # ---- build primary widgets ----
        self._velocity_bar = VelocityBarController(window=self)
        self._parameter_tabs = ParameterTabsWidget(copy.deepcopy(self._factory_default_config))
        self._canvas = PlotCanvas(
            figure_props=default_config["figure"],
            axes_props=default_config["axes"],
            lines_props=default_config["lines"],
            t_limits=(0.0, 100.0),
        )

        # ---- coordinator objects ----
        self._settings = Settings(
            organization="VahidAnari",
            application="MaxwellBlochSolver",
            canvas=self._canvas,
            default_lines_config=default_config["lines"],
        )

        self._line_colors = LineColorManager(
            canvas=self._canvas,
            settings=self._settings,
            default_lines_config=default_config["lines"],
        )

        self._solver = SolverController(
            parent=self,
            on_finished=self._on_solve_finished,
            get_params=self._parameter_tabs.get_value,
            on_state_solving=lambda: self._status_bar.set_state(StatusState.SOLVING),
            on_state_ready=lambda: self._status_bar.set_state(StatusState.READY),
        )

        self._pipeline = UpdatePipeline(
            canvas=self._canvas,
            get_params=self._parameter_tabs.get_value,
            get_results=lambda: self._results,
            get_current_data=lambda: self._current_data,
            get_bottom_plot=lambda: self._bottom_plot,
            get_fit_mode=lambda: self._fit_mode,
            set_chi_square=self._velocity_bar.set_chi_square,
            update_cosh_peak=self._update_cosh_peak,
            redraw=self._canvas.redraw,
        )

        self._exporter = PlotExporter(
            canvas=self._canvas,
            get_displayed_curves=lambda: self._pipeline.displayed_curves,
            get_params=self._parameter_tabs.get_value,
            get_fit_mode=lambda: self._fit_mode,
            get_view_preference=self._settings.get_view_preference,
            get_metadata=self._get_metadata_text,
            get_parameter_tabs_value=self._parameter_tabs.get_value,
        )

        # ---- menu bar (needs coordinator objects ready) ----
        menu_spec = self._build_menu_spec()
        self._menu_bar = MenuBarController(self, menu_spec=menu_spec, native_menubar=NATIVE_MENU_BAR)
        self._status_bar = StatusBarController(self)

        # ---- bottom panel selector ----
        self._bottom_plot_combo = self._make_curve_selector(
            self._canvas.get_bottom_panel_labels()
        )
        self._bottom_plot = self._bottom_plot_combo.currentData()

        # ---- connect signals ----
        self._menu_bar.actionTriggered.connect(self._on_menu_action_triggered)
        self._velocity_bar.valueChanged.connect(self._on_velocity_changed)
        self._velocity_bar.valueSaved.connect(self._on_velocity_saved)
        self._velocity_bar.valueUnsaved.connect(self._on_velocity_unsaved)
        self._parameter_tabs.valueChanged.connect(self._on_params_value_changed)
        self._parameter_tabs.coshPeakChanged.connect(self._on_cosh_peak_changed)
        self._parameter_tabs.showCoshPeak.connect(self._on_show_cosh_peak)
        self._bottom_plot_combo.currentIndexChanged.connect(
            lambda _: self._on_bottom_plot_changed()
        )

        self._factory_default_params = self._parameter_tabs.get_value()

        saved_defaults = self._settings.load_saved_app_defaults()
        if saved_defaults is not None:
            config, params = saved_defaults
            self._parameter_tabs.set_config(copy.deepcopy(config))
            self._parameter_tabs.set_value(copy.deepcopy(params))

        self._status_bar.set_state(StatusState.READY)
        self._set_fit_mode(False)
        self._make_layout()
        self._apply_saved_view_preferences()
        self._settings.line_colors.apply_saved_colors()
        self._settings.line_colors.update_all_menu_icons(self._menu_bar)
        self._update_bottom_plot_combo_icons()
        self._pipeline.tasks.set_all()
        self._solver.solve()
        self._status_bar.set_path_modified()
        self._on_bottom_plot_changed()

    # ---- Layout ----
    def _make_layout(self) -> None:
        """Create the central widget layout."""
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.addWidget(self._canvas, 1)
        layout.addWidget(self._parameter_tabs, 0)

    def _make_curve_selector(self, items: dict[str, str]) -> QComboBox:
        """Create the bottom-panel curve selector and add it to the toolbar.

        Args:
            items: Mapping from internal curve IDs to display labels.

        Returns:
            Configured combo box used to select the active bottom-panel curve.
        """
        combo = QComboBox()
        combo.setIconSize(QSize(12, 12))
        saved = self._settings.line_colors.load_saved_colors()
        for name, label in items.items():
            color = saved.get(name) or self._canvas.get_curve_color(name) or "#000000"
            combo.addItem(LineColorManager.make_color_icon(color), label, name)

        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Bottom Plot:"))
        layout.addWidget(combo)
        self._velocity_bar.add_widget(wrapper)
        return combo

    def _update_bottom_plot_combo_icons(self) -> None:
        """Refresh bottom-plot combo icons to match the current curve colors."""
        combo = self._bottom_plot_combo
        for i in range(combo.count()):
            curve_id = combo.itemData(i)
            color = self._canvas.get_curve_color(curve_id) or "#000000"
            combo.setItemIcon(i, LineColorManager.make_color_icon(color))

    # ---- Other helpers ----
    def _can_leave(self) -> bool:
        """Return whether it is safe to discard the current state.

        Shows an unsaved-changes dialog when modifications are pending so the
        user can save, discard, or cancel.

        Returns:
            ``True`` if navigation can proceed, otherwise ``False``.
        """
        if not self._status_bar.is_modified():
            return True

        if self._fit_mode:
            result = ask_question(
                "Unsaved changes",
                f"Velocity {self._velocity_bar.get_current_velocity()} has unsaved changes.",
                "Do you want to save them?",
                no_btn_label="No",
                yes_btn_label="Yes",
                cancel_btn_label="Cancel",
                parent=self,
            )
            if result == AskResult.CANCEL:
                return False
            if result == AskResult.YES:
                self._velocity_bar.save_parameters()
            elif result == AskResult.NO:
                self._velocity_bar.set_modified(False)
            return True

        result = ask_question(
            "Unsaved changes",
            "Current parameters have unsaved changes.",
            "Do you want to save them?",
            no_btn_label="No",
            yes_btn_label="Yes",
            cancel_btn_label="Cancel",
            parent=self,
        )
        if result == AskResult.CANCEL:
            return False
        if result == AskResult.YES:
            self._save()
        return True

    def _set_fit_mode(self, fit_mode: bool) -> None:
        """Enable or disable fit-related controls.

        Args:
            fit_mode: Whether fit mode should be active.
        """
        self._fit_mode = fit_mode
        self._parameter_tabs.set_fit_tab_enable(fit_mode)
        self._menu_bar.set_enabled("save_parameters_as", not fit_mode)
        self._menu_bar.set_enabled("show_data_summary", fit_mode)
        self._menu_bar.set_enabled("open_source_folder", fit_mode)
        self._menu_bar.set_enabled("close_data", fit_mode)

        flux_range = self._parameter_tabs.get_widget("display.range.flux")
        flux_range.set_label("F" if fit_mode else "I")

        if not fit_mode:
            self._velocity_bar.set_available_velocities([])
            self._velocity_bar.set_chi_square(None)

    def _set_params_path(self, path: Optional[Path]) -> None:
        """Store the current parameter-file path and update the status bar.

        Args:
            path: Current parameter-file path, or ``None`` if unset.
        """
        self._params_path = path
        self._status_bar.set_path("" if path is None else str(path))

    def _get_metadata_text(self, add_velocity: bool = False) -> Dict[str, Any]:
        """Build the metadata mapping written alongside saved parameter files.

        Args:
            add_velocity: Whether to include the active velocity.

        Returns:
            Metadata mapping.
        """
        out: Dict[str, Any] = {
            "app_version": APP_VERSION,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "saved_by": getpass.getuser(),
            "fit_mode": self._fit_mode,
        }
        if self._fit_mode:
            s = self._source_selection
            out["source"] = s.name
            if s.period is not None:
                out["period"] = s.period
            if add_velocity:
                out["velocity"] = f"{self._velocity_bar.get_current_velocity()} {VELOCITY_UNIT_TEXT}"
        return out

    def _get_save_file_text(self) -> str:
        """Return the current parameter state as JSON text ready for saving.

        Returns:
            Serialized JSON string containing metadata, config, and parameters.
        """
        return pretty_json({
            "metadata": self._get_metadata_text(),
            "config": self._parameter_tabs.get_config(),
            "params": self._all_params if self._fit_mode else self._parameter_tabs.get_value(),
        })

    def _show_error(self, title: str, text: str) -> None:
        """Set the status bar to ERROR, show a critical dialog, then restore READY.

        Args:
            title: Error-dialog title.
            text: Error message text.
        """
        self._status_bar.set_state(StatusState.ERROR)
        show_critical(title, text, parent=self)
        self._status_bar.set_state(StatusState.READY)

    def _open_path(self, path, title: str, missing_message: str) -> None:
        """Open a local path in the system browser.

        Args:
            path: Local file-system path to open.
            title: Error-dialog title if the path is missing.
            missing_message: Error text shown if the path does not exist.
        """
        if not path.exists():
            self._show_error(title, missing_message)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _apply_saved_view_preferences(self) -> None:
        """Restore persisted grid and slider-range visibility settings on startup."""
        for action_id in MENU_CHECKABLE_IDS:
            checked = self._settings.get_view_preference(action_id, False)
            self._menu_bar.set_checked(action_id, checked)
            self._handle_checkable_menu_action(action_id, checked, persist=False, redraw=False)
        self._canvas.redraw()

    # ---- Cosh peak ----
    def _update_cosh_peak(self) -> None:
        """Reposition and show or hide the cosh-peak marker on the canvas."""
        if self._cosh_peak_path is None:
            return
        if self._solver.is_solving:
            return

        params = self._solver.current_params
        cosh_values = params[self._cosh_peak_path]
        symmetric = cosh_values["symmetric"]
        idx = cosh_values["current_idx"]
        amplitude = cosh_values["a"][idx]
        x0 = cosh_values["x0"][idx]

        if amplitude == 0:
            wl = wr = 0.0
        elif symmetric:
            wl = wr = cosh_values["w"][idx] / 2.0
        else:
            wl = cosh_values["wl"][idx]
            wr = cosh_values["wr"][idx]

        if self._fit_mode:
            from app.update_pipeline import get_time_unit_scale
            scale = get_time_unit_scale(params)
            x0 = params["results.offset.time"] + x0 * scale
            wl *= scale
            wr *= scale

        self._canvas.set_cosh_peak_position(x0, wl, wr)
        cat = self._cosh_peak_path.split(".")[1]
        in_correct_tab = (
            (cat == "bcs" and self._bottom_plot == "A0")
            or (cat == "pump" and self._bottom_plot == "lambda_n")
        )
        self._canvas.set_cosh_peak_visible(self._show_cosh_peak and in_correct_tab)

    # ---- Solver callback ----
    def _on_solve_finished(self, results: dict) -> None:
        """Store solver output and schedule the dependent UI refresh steps.

        Args:
            results: Solver-result mapping returned by the background solve.
        """
        self._results = results
        self._pipeline.request(plot=True, cosh_peak=True)

    # ---- Menu spec & rebuild ----
    def _build_menu_spec(self) -> dict[str, Any]:
        """Build the full menu-bar specification.

        Returns:
            Nested menu specification mapping for ``MenuBarController``.
        """
        return {
            "File": [
                {"id": "open_data_folder", "text": "Open Data Folder...", "shortcut": "Ctrl+Shift+O"},
                {"id": "recent_data_folders_menu", "submenu": "Recent Data Folders",
                 "items": self._settings.recent_folders.build_menu_items()},
                {"id": "open_source_folder", "text": "Open Current Source Folder", "shortcut": "Ctrl+O"},
                {"id": "open_parameters", "text": "Open Parameters...", "shortcut": "Ctrl+Shift+P"},
                {"id": "close_data", "text": "Close Data", "shortcut": QKeySequence.Close},
                {"id": "sep"},
                {"id": "save_parameters", "text": "Save Parameters", "shortcut": QKeySequence.Save},
                {"id": "save_parameters_as", "text": "Save Parameters As...", "shortcut": QKeySequence.SaveAs},
                {"id": "save_as_app_default", "text": "Save Parameters as Default", "shortcut": "Ctrl+Alt+S"},
                {"id": "sep"},
                {"id": "export_plot", "text": "Export Plot...", "shortcut": "Ctrl+E"},
                {"id": "sep"},
                {"id": "quit_application", "text": "Quit", "shortcut": QKeySequence.Quit,
                 "role": QAction.QuitRole},
            ],
            "View": [
                {"id": "time_grid_menu", "submenu": "Time Grid", "items": [
                    {"id": "show_time_major_grid", "text": "Major", "checkable": True, "checked": False},
                    {"id": "show_time_minor_grid", "text": "Minor", "checkable": True, "checked": False},
                ]},
                {"id": "flux_grid_menu", "submenu": "Flux Grid", "items": [
                    {"id": "show_flux_major_grid", "text": "Major", "checkable": True, "checked": False},
                    {"id": "show_flux_minor_grid", "text": "Minor", "checkable": True, "checked": False},
                ]},
                {"id": "bottom_panel_grid_menu", "submenu": "Bottom Panel Grid", "items": [
                    {"id": "show_bottom_major_grid", "text": "Major", "checkable": True, "checked": False},
                    {"id": "show_bottom_minor_grid", "text": "Minor", "checkable": True, "checked": False},
                ]},
                {"id": "sep"},
                {"id": "show_slider_range_labels", "text": "Show Slider Range",
                 "checkable": True, "checked": False, "shortcut": "Ctrl+Alt+R"},
                {"id": "sep"},
                {"id": "line_colors_menu", "submenu": "Line Colors",
                 "items": self._settings.line_colors.build_menu_items()},
            ],
            "Info": [
                {"id": "show_data_summary", "text": "Data Summary", "shortcut": "Ctrl+Alt+D"},
                {"id": "show_scaling_formula", "text": "Scaling Formula", "shortcut": "Ctrl+Alt+F"},
                {"id": "open_equations_pdf", "text": "Equations Reference", "shortcut": "Ctrl+Alt+E"},
                {"id": "open_solver_step_viewer", "text": "Solver Step Viewer", "shortcut": "Ctrl+Alt+V"},
            ],
            "Help": [
                {"id": "open_user_guide", "text": "User Guide", "shortcut": QKeySequence.HelpContents},
                {"id": "open_documentation", "text": "Documentation"},
                {"id": "sep"},
                {"id": "show_about_dialog", "text": "About This App"},
                {"id": "show_about_qt", "text": "About Qt"},
            ],
        }

    def _capture_menu_check_states(self) -> dict[str, bool]:
        """Capture checked states of persistent menu actions before a rebuild.

        Returns:
            Mapping from persistent checkable action IDs to checked states.
        """
        states: dict[str, bool] = {}
        for action_id in MENU_CHECKABLE_IDS:
            states[action_id] = self._menu_bar.get_checked(action_id)
        return states

    def _restore_menu_check_states(self, states: dict[str, bool]) -> None:
        """Restore checked states of persistent menu actions after a rebuild.

        Args:
            states: Mapping from action IDs to checked states.
        """
        for action_id, checked in states.items():
            self._menu_bar.set_checked(action_id, checked)

    def _rebuild_menu_bar(self) -> None:
        """Rebuild the entire menu bar while preserving persistent check states."""
        states = self._capture_menu_check_states()
        self._menu_bar.set_menu_spec(self._build_menu_spec(), native_menubar=NATIVE_MENU_BAR)
        self._restore_menu_check_states(states)
        self._settings.line_colors.update_all_menu_icons(self._menu_bar)
        self._set_fit_mode(self._fit_mode)

    def _build_menu_action_map(self) -> dict[str, Any]:
        """Return the dispatch map from action IDs to handler callables.

        Returns:
            Mapping from action-ID strings to bound handler callables.
        """
        return {
            "open_data_folder": self._open_data_folder,
            "clear_recent_data_folders": self._clear_recent_data_folders,
            "open_source_folder": self._open_source_folder,
            "open_parameters": self._open_params,
            "close_data": self._close_data,
            "save_parameters": self._save,
            "save_parameters_as": self._save_as,
            "save_as_app_default": self._save_as_app_default,
            "export_plot": self._export_plot,
            "quit_application": lambda: QApplication.instance().quit(),
            "show_scaling_formula": self._parameter_tabs.show_scaling_formula,
            "show_data_summary": self._show_data_information,
            "open_equations_pdf": self._open_equations_pdf,
            "open_solver_step_viewer": self._open_solver_step_viewer,
            "open_documentation": self._open_documentation,
            "open_user_guide": self._open_user_guide,
            "show_about_dialog": self._show_about_dialog,
            "show_about_qt": self._show_about_qt,
        }

    # ---- File menu actions ----
    def _load_data_folder_from_path(self, folder_path: Path) -> None:
        """Load one source folder and switch the app into fit mode.

        Args:
            folder_path: Folder to load.
        """
        folder_info = analyze_folder(folder_path, self)
        if folder_info is None:
            return

        selected_period = None
        if folder_info.has_periods:
            selected_period = select_period_if_needed(folder_info, self)
            if selected_period is None:
                return

        show_data_folder_summary(folder_info=folder_info, selected_period=selected_period, parent=self)

        all_data = load_velocity_files(folder_path, selected_period)
        params = load_params_file(
            folder=folder_path,
            source=folder_info.source,
            selected_period=selected_period,
        )

        self._source_selection = SourceSelection(
            name=folder_info.source,
            path=folder_info.path,
            period=selected_period,
        )
        self._status_bar.set_path(str(folder_info.path))
        self._all_data = all_data

        if params:
            self._parameter_tabs.set_config(params["config"])
            self._all_params = params["params"]
        else:
            self._all_params = {}

        self._set_fit_mode(True)
        self._velocity_bar.set_available_velocities(
            list(self._all_data.keys()),
            list(self._all_params.keys())
        )
        self._on_velocity_changed(self._velocity_bar.get_current_velocity())

        self._settings.recent_folders.remember(folder_info.path)
        self._rebuild_menu_bar()
        show_information("Data Imported", "All data were imported successfully.", parent=self)

    def _open_data_folder(self) -> None:
        """Open a data folder chosen from a directory-picker dialog."""
        self._status_bar.set_state(StatusState.IMPORTING)
        if not self._can_leave():
            self._status_bar.set_state(StatusState.READY)
            return
        folder_path = select_folder(self)
        if folder_path is not None:
            self._load_data_folder_from_path(folder_path)
        self._status_bar.set_state(StatusState.READY)

    def _open_recent_data_folder(self, folder_path: str) -> None:
        """Open one folder from the recent-data-folder history.

        Args:
            folder_path: Previously remembered folder path.
        """
        path = Path(folder_path)
        if not path.exists():
            self._show_error("Recent Data Folders", f"The folder does not exist anymore:\n{folder_path}")
            self._settings.recent_folders.remove(folder_path)
            self._rebuild_menu_bar()
            return

        self._status_bar.set_state(StatusState.IMPORTING)
        if not self._can_leave():
            self._status_bar.set_state(StatusState.READY)
            return
        self._load_data_folder_from_path(path)
        self._status_bar.set_state(StatusState.READY)

    def _clear_recent_data_folders(self) -> None:
        """Clear the recent-data-folder history and rebuild the menu."""
        self._settings.recent_folders.clear()
        self._rebuild_menu_bar()

    def _open_source_folder(self) -> None:
        """Open the currently loaded source folder in the system file browser."""
        source_path = self._source_selection.path
        self._open_path(source_path, "Open Source Folder", "No source folder is currently loaded.")

    def _open_params(self) -> None:
        """Import a parameter file and load it into the parameter widgets."""
        self._status_bar.set_state(StatusState.IMPORTING)
        if not self._can_leave():
            self._status_bar.set_state(StatusState.READY)
            return

        results = open_parameters(self)
        if not results:
            self._status_bar.set_state(StatusState.READY)
            return

        self._set_fit_mode(False)
        self._source_selection = SourceSelection()
        self._all_data.clear()
        self._all_params.clear()
        self._current_data = make_empty_light_curve()
        self._results = {}
        self._pipeline.displayed_curves = DisplayedCurves()

        path = results["path"]
        params = results["params"]
        self._set_params_path(path)
        self._parameter_tabs.set_config(params["config"])
        self._parameter_tabs.set_value(params["params"])
        self._pipeline.tasks.set_all()
        self._solver.solve()

        self._status_bar.set_state(StatusState.READY)
        show_information("Parameters Imported", "Parameters were imported successfully.", parent=self)

    def _close_data(self) -> None:
        """Close the current data folder and restore the default application state."""
        if not self._fit_mode or not self._can_leave():
            return
        saved = self._settings.load_saved_app_defaults()
        if saved is not None:
            config, params = saved
        else:
            config = copy.deepcopy(self._factory_default_config)
            params = copy.deepcopy(self._factory_default_params)

        self._source_selection = SourceSelection()
        self._all_data.clear()
        self._all_params.clear()
        self._current_data = make_empty_light_curve()
        self._results = {}
        self._pipeline.displayed_curves = DisplayedCurves()
        self._set_params_path(None)
        self._set_fit_mode(False)

        self._parameter_tabs.set_config(copy.deepcopy(config))
        self._parameter_tabs.set_value(copy.deepcopy(params))
        self._pipeline.tasks.set_all()
        self._solver.solve()
        self._status_bar.set_path_modified()

    def _save_data_folder(self) -> None:
        """Save all current fit parameters to the loaded data folder on disk."""
        self._status_bar.set_state(StatusState.SAVING)
        source_path = self._source_selection.path
        if self._source_selection.name and source_path is not None:
            filename = self._source_selection.name
            if self._source_selection.period:
                filename += f"_{self._source_selection.period}"
            filename += "_params.json"
            path = source_path / filename
            save_params_atomic(self._get_save_file_text(), path)
            self._set_params_path(path)
        self._status_bar.set_state(StatusState.READY)

    def _save(self) -> None:
        """Save the current parameter state."""
        self._status_bar.set_state(StatusState.SAVING)
        if self._fit_mode:
            self._velocity_bar.save_parameters()
        else:
            path = save_parameters(self._get_save_file_text(), self._params_path, self)
            if path:
                self._set_params_path(path)
        self._status_bar.set_state(StatusState.READY)

    def _save_as(self) -> None:
        """Save the current parameter state to a new user-chosen file."""
        self._status_bar.set_state(StatusState.SAVING)
        path = save_parameters_as(self._get_save_file_text(), self)
        if path:
            self._set_params_path(path)
        self._status_bar.set_state(StatusState.READY)

    def _save_as_app_default(self) -> None:
        """Save the current parameters and configuration as persistent app defaults."""
        done, error_text = self._settings.save_as_app_default(self._parameter_tabs)
        if done:
            show_information(
                "App Default Saved",
                "Current parameters and configuration were saved as the default application state.",
                parent=self,
            )
        else:
            self._show_error("Save App Default Failed", error_text)

    def _export_plot(self) -> None:
        """Export the current plot to a user-chosen output file."""
        self._status_bar.set_state(StatusState.EXPORTING)
        if getattr(self._canvas, "figure", None) is None:
            self._show_error("Export Plot", "No figure is available to export.")
            return

        default_stem = "maxwell_bloch_plot"
        s = self._source_selection
        if s.name:
            default_stem = s.name
            if s.period is not None:
                default_stem += f"_{s.period}"
            default_stem += f"_v={self._velocity_bar.get_current_velocity()}_plot"

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Plot",
            f"{default_stem}.pdf",
            "PDF file (*.pdf);;PNG image (*.png);;SVG file (*.svg);;All files (*.*)",
        )
        if not file_path:
            self._status_bar.set_state(StatusState.READY)
            return

        path = Path(file_path)
        if not path.suffix:
            if "PDF" in selected_filter:
                path = path.with_suffix(".pdf")
            elif "PNG" in selected_filter:
                path = path.with_suffix(".png")
            elif "SVG" in selected_filter:
                path = path.with_suffix(".svg")

        try:
            self._exporter.save(str(path))
            self._status_bar.set_state(StatusState.READY)
        except Exception as exc:
            self._show_error("Export Plot Failed", str(exc))

    # ---- View menu ----
    def _handle_grid_toggle(self, action_id: str, checked: bool, *, redraw: bool = True) -> bool:
        """Handle a grid-visibility menu toggle.

        Args:
            action_id: Menu-action identifier.
            checked: New checked state.
            redraw: Whether to redraw the canvas after handling.

        Returns:
            ``True`` if the action was recognized and handled.
        """
        grid_actions = {
            "show_time_major_grid": lambda: self._canvas.set_time_grid(checked, "major"),
            "show_time_minor_grid": lambda: self._canvas.set_time_grid(checked, "minor"),
            "show_flux_major_grid": lambda: self._canvas.set_flux_grid(checked, "major"),
            "show_flux_minor_grid": lambda: self._canvas.set_flux_grid(checked, "minor"),
            "show_bottom_major_grid": lambda: self._canvas.set_bottom_grid(checked, "major"),
            "show_bottom_minor_grid": lambda: self._canvas.set_bottom_grid(checked, "minor"),
        }
        handler = grid_actions.get(action_id)
        if handler is None:
            return False
        handler()
        if redraw:
            self._canvas.redraw()
        return True

    def _handle_checkable_menu_action(
        self,
        action_id: str,
        checked: bool,
        *,
        persist: bool = True,
        redraw: bool = True,
    ) -> bool:
        """Handle a persistent checkable menu action.

        Args:
            action_id: Menu-action identifier.
            checked: New checked state.
            persist: Whether to persist the new state.
            redraw: Whether to redraw after handling.

        Returns:
            ``True`` if the action was recognized and handled.
        """
        handled = False
        if action_id == "show_slider_range_labels":
            self._set_slider_range_labels_visible(checked)
            handled = True
        else:
            handled = self._handle_grid_toggle(action_id, checked, redraw=redraw)
        if handled and persist:
            self._settings.set_view_preference(action_id, checked)
        return handled

    def _set_slider_range_labels_visible(self, visible: bool) -> None:
        """Show or hide slider range labels across all parameter widgets.

        Args:
            visible: Whether slider range labels should be visible.
        """
        cfg = self._parameter_tabs.get_config()
        set_nested_bool_key(cfg, "show_range", visible)
        self._parameter_tabs.set_config(cfg)

    # ---- Info menu ----
    def _show_data_information(self) -> None:
        """Show a summary information dialog for the currently loaded data."""
        if self._current_data.time.size == 0 or self._current_data.flux.size == 0:
            self._show_error("Data Summary", "No data are currently loaded.")
            return
        s = self._source_selection
        time_min, time_max = np.min(self._current_data.time), np.max(self._current_data.time)
        flux_min, flux_max = np.min(self._current_data.flux), np.max(self._current_data.flux)
        text = f"Source: {s.name or 'N/A'}\n"
        if s.period:
            text += f"Period: {s.period}\n"
        text += f"Current Velocity: {self._velocity_bar.get_current_velocity()} {VELOCITY_UNIT_TEXT}\n"
        text += f"Time Range: [{time_min}, {time_max}]\n"
        text += f"Flux Range: [{flux_min}, {flux_max}]\n"
        show_information("Data Summary", text, parent=self)

    def _open_equations_pdf(self) -> None:
        """Open the local equations reference PDF."""
        self._open_path(EQUATIONS_PDF_PATH, "Equations Reference", "equations_reference.pdf not found")

    def _open_solver_step_viewer(self) -> None:
        """Open or raise the interactive solver step-viewer window."""
        if self._step_viewer_window is None:
            self._step_viewer_window = StepScatterWidget(Nt=6, Nz=6, steps0=1)
            self._step_viewer_window.setAttribute(Qt.WA_DeleteOnClose, True)
            self._step_viewer_window.destroyed.connect(self._clear_step_viewer_ref)
        self._step_viewer_window.show()
        self._step_viewer_window.raise_()
        self._step_viewer_window.activateWindow()
        self._step_viewer_window.canvas.setFocus()

    def _clear_step_viewer_ref(self, *args) -> None:
        """Clear the cached step-viewer window reference after the window closes.

        Args:
            *args: Unused signal arguments from Qt.
        """
        self._step_viewer_window = None

    # ---- Help menu ----
    def _open_documentation(self) -> None:
        """Open the generated HTML documentation in the system browser."""
        self._open_path(
            DOCUMENTATION_PATH,
            "Documentation",
            "No documentation output was found in the project.",
        )

    def _open_user_guide(self) -> None:
        """Open the user guide PDF."""
        self._open_path(USER_GUIDE_PATH, "User Guide", "user_guide.pdf not found.")

    def _show_about_dialog(self) -> None:
        """Show the application About dialog with version and author information."""
        lines = [f"<b>Version:</b> {escape(APP_VERSION)}"]
        if APP_AUTHOR_NAME:
            lines.append(f"<b>Created by:</b> {escape(APP_AUTHOR_NAME)}")
        if APP_AUTHOR_EMAIL:
            email = escape(APP_AUTHOR_EMAIL)
            lines.append(f'<b>Email:</b> <a href="mailto:{email}">{email}</a>')
        if APP_AUTHOR_GITHUB:
            github = escape(APP_AUTHOR_GITHUB)
            lines.append(f'<b>GitHub:</b> <a href="{github}">{github}</a>')
        if APP_AUTHOR_WEBSITE:
            website = escape(APP_AUTHOR_WEBSITE)
            lines.append(f'<b>Website:</b> <a href="{website}">{website}</a>')
        show_about_dialog(
            title=f"About {APP_NAME}",
            heading=APP_NAME,
            html_text="<br>".join(lines),
            parent=self,
        )

    def _show_about_qt(self) -> None:
        """Show the built-in Qt About dialog."""
        QApplication.aboutQt()

    # ---- Signal handlers ----
    def _on_menu_action_triggered(self, _menu_id: str, action_id: str, checked: bool) -> None:
        """Dispatch a triggered menu action to the appropriate handler.

        Args:
            _menu_id: Menu identifier.
            action_id: Triggered action identifier.
            checked: Checked state associated with the action.
        """
        if action_id in self._settings.recent_folders.action_map:
            self._open_recent_data_folder(self._settings.recent_folders.action_map[action_id])
            return
        if action_id.startswith(LINE_COLOR_ACTION_PREFIX):
            curve_id = action_id[len(LINE_COLOR_ACTION_PREFIX):]
            self._settings.line_colors.choose_color(
                curve_id,
                self,
                self._menu_bar,
                self._update_bottom_plot_combo_icons,
            )
            return
        if action_id == RESET_LINE_COLORS_ACTION_ID:
            self._settings.line_colors.reset_to_defaults(
                self._menu_bar,
                self._update_bottom_plot_combo_icons,
            )
            return
        handler = self._build_menu_action_map().get(action_id)
        if handler is not None:
            handler()
            return
        self._handle_checkable_menu_action(action_id, checked)

    def _on_velocity_changed(self, velocity: str) -> None:
        """Handle a change in the selected velocity component.

        Args:
            velocity: Newly selected velocity string.
        """
        self._current_data = self._all_data[velocity]
        self._parameter_tabs.set_value(copy.deepcopy(self._all_params.get(velocity, {})))
        self._pipeline.tasks.set_all()
        self._solver.solve()

    def _on_velocity_saved(self, velocity: str) -> None:
        """Persist the current parameters for a saved velocity component.

        Args:
            velocity: Velocity string that was saved.
        """
        self._all_params[velocity] = self._parameter_tabs.get_value()
        self._save_data_folder()

    def _on_velocity_unsaved(self, velocity: str) -> None:
        """Remove the stored parameters for an unsaved velocity component.

        Args:
            velocity: Velocity string that was unsaved.
        """
        self._all_params.pop(velocity, None)
        self._save_data_folder()

    def _on_bottom_plot_changed(self) -> None:
        """Handle a change in the selected bottom-panel curve."""
        bottom_plot = self._bottom_plot_combo.currentData()
        if not bottom_plot:
            return
        self._bottom_plot = bottom_plot
        for i in range(self._bottom_plot_combo.count()):
            data = self._bottom_plot_combo.itemData(i)
            self._parameter_tabs.show_widget(f"display.range.{data}", data == bottom_plot)
        self._pipeline.request(plot=True, cosh_peak=True)

    def _on_params_value_changed(self, path: str, value: Any) -> None:
        """Route a parameter-widget change to the appropriate update tasks.

        Args:
            path: Path of the changed parameter widget.
            value: New widget value.
        """
        self._velocity_bar.set_modified()
        self._status_bar.set_path_modified()

        tasks = self._pipeline.tasks
        category = path.split(".")[0] if path else ""

        if category == "solve":
            self._solver.solve()
            return

        if category == "slice" and path == "slice.z":
            arr_length = value.get("arr_length")
            if arr_length != self._last_z_arr_length:
                self._last_z_arr_length = arr_length
                self._solver.solve()
                return
            else:
                tasks.plot = True

        elif category == "results":
            tasks.plot = True

        elif category == "data":
            if path in ("data.unit.flux", "data.unit.time"):
                tasks.units = True
            if path == "data.unit.time":
                tasks.plot = True
            elif path == "data.offset.time":
                tasks.data = True

        elif category == "display":
            tasks.range = True

        self._pipeline.update()

    def _on_cosh_peak_changed(self, path: str) -> None:
        """Handle a change in the active cosh-peak parameter group.

        Args:
            path: Path to the active cosh-peak parameter group.
        """
        self._cosh_peak_path = path
        self._pipeline.request(cosh_peak=True)

    def _on_show_cosh_peak(self, show: bool) -> None:
        """Handle a change in the cosh-peak visibility state.

        Args:
            show: Whether the cosh peak should be visible.
        """
        self._show_cosh_peak = show
        self._pipeline.request(cosh_peak=True)

    # ---- Close ----
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle the Qt close event and guard against unsaved changes.

        Args:
            event: Qt close event.
        """
        if self._can_leave():
            event.accept()
        else:
            event.ignore()


def _demo_main() -> int:
    """Run the full application as a standalone demo.

    Returns:
        Qt application exit code.
    """
    app = QApplication(sys.argv)
    window = MBESolverApp(app)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
