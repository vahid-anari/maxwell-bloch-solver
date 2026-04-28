"""Update pipeline: task flags and incremental UI-refresh steps.

The ``UpdatePipeline`` owns the ``UpdateTasks`` flags and the ordered sequence
of partial updates including data, plot, range, chi-square, units, and
cosh-peak refreshes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Any, Callable, Optional

import numpy as np

from app_io.data_io import LightCurve
from utils.helper_funcs import cut_y_by_x, get_range
from utils.units import TIME_UNIT_TO_SECONDS

if TYPE_CHECKING:
    from app.plot import PlotCanvas


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class SolverResultsDisplay:
    """Solver arrays currently shown in the GUI.

    Attributes:
        time: Solver time array currently displayed.
        intensity: Displayed intensity array.
        w: Displayed population-inversion array.
        lambda_n: Displayed pump profile array.
        A0: Displayed boundary-field array.
    """

    time: np.ndarray = field(default_factory=lambda: np.empty(0))
    intensity: np.ndarray = field(default_factory=lambda: np.empty(0))
    w: np.ndarray = field(default_factory=lambda: np.empty(0))
    lambda_n: np.ndarray = field(default_factory=lambda: np.empty(0))
    A0: np.ndarray = field(default_factory=lambda: np.empty(0))


@dataclass
class DisplayedCurves:
    """Measured data and currently displayed solver results.

    Attributes:
        data: Measured light-curve data.
        results: Solver-result arrays currently shown on the canvas.
    """

    data: LightCurve = field(default_factory=lambda: LightCurve(np.empty(0), np.empty(0)))
    results: SolverResultsDisplay = field(default_factory=SolverResultsDisplay)


@dataclass
class UpdateTasks:
    """Flags describing which parts of the application need updating.

    Attributes:
        data: Whether measured data need refreshing.
        plot: Whether plotted solver results need refreshing.
        units: Whether axis labels and displayed units need refreshing.
        range: Whether axis ranges need recomputing.
        chi_square: Whether the chi-square display needs recomputing.
        cosh_peak: Whether the cosh-peak marker needs refreshing.
    """

    data: bool = False
    plot: bool = False
    units: bool = False
    range: bool = False
    chi_square: bool = False
    cosh_peak: bool = False

    def clear(self) -> None:
        """Reset all update-task flags to ``False``."""
        for f in fields(self):
            setattr(self, f.name, False)

    def set_all(self) -> None:
        """Set all update-task flags to ``True``."""
        for f in fields(self):
            setattr(self, f.name, True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_chi_square(
    display: DisplayedCurves,
    x_limits: tuple[float, float],
) -> float:
    """Compute a reduced chi-square-like mismatch over the visible data range.

    Args:
        display: Container holding measured data and displayed solver results.
        x_limits: Visible ``(x_min, x_max)`` interval.

    Returns:
        Reduced chi-square-like mismatch value over the visible overlap region.
    """

    x_min, x_max = x_limits
    x_data = display.data.time
    y_data = display.data.flux
    x_fit = display.results.time
    y_fit = display.results.intensity

    if x_data.size == 0 or y_data.size == 0 or x_fit.size == 0 or y_fit.size == 0:
        return 0.0

    mask = (x_data >= x_min) & (x_data <= x_max)
    x = x_data[mask]
    y = y_data[mask]

    if x.size == 0:
        return 0.0

    valid = (x >= x_fit[0]) & (x <= x_fit[-1])
    x = x[valid]
    y = y[valid]

    if x.size == 0:
        return 0.0

    y_pred = np.interp(x, x_fit, y_fit)
    mask_nonzero = y_pred != 0.0
    if not np.any(mask_nonzero):
        return 0.0

    chi_2 = np.sum(
        (y_pred[mask_nonzero] - y[mask_nonzero]) ** 2 / y_pred[mask_nonzero]
    )
    return float(chi_2 / mask_nonzero.sum())


def get_time_unit_scale(params: dict[str, Any]) -> float:
    """Return the scale factor for the currently selected time unit.

    Args:
        params: Application parameter mapping.

    Returns:
        Scale factor converting solver time units to the active display unit.
    """
    return params["solve.sample"]["t0"] / TIME_UNIT_TO_SECONDS.get(
        params["data.unit.time"], 1.0
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class UpdatePipeline:
    """Own the update-task flags and run the ordered UI refresh sequence."""

    def __init__(
        self,
        canvas: "PlotCanvas",
        get_params: Callable[[], dict[str, Any]],
        get_results: Callable[[], dict],
        get_current_data: Callable[[], LightCurve],
        get_bottom_plot: Callable[[], Optional[str]],
        get_fit_mode: Callable[[], bool],
        set_chi_square: Callable[[Optional[float]], None],
        update_cosh_peak: Callable[[], None],
        redraw: Callable[[], None],
    ) -> None:
        """Initialize the update pipeline.

        Args:
            canvas: Plot canvas to update.
            get_params: Callable returning the current parameter mapping.
            get_results: Callable returning the latest solver-result mapping.
            get_current_data: Callable returning the current raw light curve.
            get_bottom_plot: Callable returning the active bottom-panel curve ID.
            get_fit_mode: Callable returning whether fit mode is active.
            set_chi_square: Callback used to update the chi-square display.
            update_cosh_peak: Callback that refreshes the cosh-peak marker.
            redraw: Callable that triggers a canvas redraw.
        """
        self._canvas = canvas
        self._get_params = get_params
        self._get_results = get_results
        self._get_current_data = get_current_data
        self._get_bottom_plot = get_bottom_plot
        self._get_fit_mode = get_fit_mode
        self._set_chi_square = set_chi_square
        self._update_cosh_peak = update_cosh_peak
        self._redraw = redraw

        self.tasks = UpdateTasks()
        self.displayed_curves = DisplayedCurves()

        self._is_updating = False
        self._has_pending = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def clear(self) -> None:
        """Reset all pending task flags to ``False``."""
        self.tasks.clear()

    def update_all(self) -> None:
        """Set all task flags and immediately flush the pipeline."""
        self.tasks.set_all()
        self.update()

    def request(self, **task_flags: bool) -> None:
        """Set one or more task flags and run the pipeline.

        Args:
            **task_flags: Task-name to boolean mappings describing requested
                updates.
        """
        for name, value in task_flags.items():
            setattr(self.tasks, name, value)
        self.update()

    def update(self) -> None:
        """Flush all pending update tasks in dependency order."""
        if self._is_updating:
            self._has_pending = True
            return

        self._is_updating = True
        self._has_pending = False

        tasks = self.tasks
        params = self._get_params()
        results = self._get_results()
        canvas = self._canvas

        if tasks.data:
            self._update_data(params)
            tasks.range = True

        if tasks.plot and results:
            self._update_plot(params, results)
            tasks.range = True

        if tasks.range:
            self._update_range(params)
            tasks.chi_square = True

        if tasks.chi_square:
            self._update_chi_square()

        if tasks.units:
            self._update_units(params)

        if tasks.cosh_peak:
            self._update_cosh_peak()

        self._is_updating = False
        canvas.redraw()

        if self._has_pending:
            self.update()

        self.tasks.clear()

    # ------------------------------------------------------------------
    # Individual steps
    # ------------------------------------------------------------------

    def _update_data(self, params: dict[str, Any]) -> None:
        """Apply the current time offset to the raw data and push it to the canvas.

        Args:
            params: Current parameter mapping.
        """
        raw = self._get_current_data()
        time = raw.time + params["data.offset.time"]
        flux = raw.flux
        self.displayed_curves.data.time = time
        self.displayed_curves.data.flux = flux
        self._canvas.set_data_points(time, flux)

    def _update_plot(self, params: dict[str, Any], results: dict) -> None:
        """Push the latest solver arrays to the plot canvas.

        Args:
            params: Current parameter mapping.
            results: Latest solver-result mapping.
        """
        canvas = self._canvas
        bottom_plot = self._get_bottom_plot()
        z_index = params["slice.z"]["index"]
        fit_mode = self._get_fit_mode()

        time = results["time"]
        intensity = results["intensity"][z_index]
        w = results["w"][z_index]
        lambda_n = results["lambda_n"]
        A0 = results["A0"]

        if fit_mode:
            time = params["results.offset.time"] + time * get_time_unit_scale(params)
            imax = np.max(intensity)
            if imax != 0:
                intensity = intensity * params["results.scale.intensity"] / imax

        self.displayed_curves.results.time = time
        self.displayed_curves.results.intensity = intensity
        self.displayed_curves.results.w = w
        self.displayed_curves.results.lambda_n = lambda_n
        self.displayed_curves.results.A0 = A0

        canvas.set_flux(time, intensity)
        canvas.set_bottom_curve_data("w", time, w)
        canvas.set_bottom_curve_data("lambda_n", time, lambda_n)
        canvas.set_bottom_curve_data("A0", time, A0)

        if bottom_plot:
            canvas.show_bottom_curve(bottom_plot)

    def _update_range(self, params: dict[str, Any]) -> None:
        """Update all axis limits from the current display-range settings.

        Args:
            params: Current parameter mapping.
        """
        canvas = self._canvas
        dc = self.displayed_curves
        bottom_plot = self._get_bottom_plot()

        canvas.set_time_limit(
            get_range(
                limits=params["display.range.time"],
                arr1=dc.results.time,
                arr2=dc.data.time,
            )
        )
        t_min, t_max = canvas.get_time_limits()
        canvas.set_flux_limit(
            get_range(
                limits=params["display.range.flux"],
                arr1=cut_y_by_x(y=dc.results.intensity, x=dc.results.time, xmin=t_min, xmax=t_max),
                arr2=cut_y_by_x(y=dc.data.flux, x=dc.data.time, xmin=t_min, xmax=t_max),
            )
        )
        if bottom_plot:
            canvas.set_bottom_panel_y_limit(
                get_range(
                    limits=params[f"display.range.{bottom_plot}"],
                    arr1=cut_y_by_x(
                        y=getattr(dc.results, bottom_plot),
                        x=dc.results.time,
                        xmin=t_min,
                        xmax=t_max,
                    ),
                )
            )

    def _update_chi_square(self) -> None:
        """Recompute and display the chi-square mismatch when fit mode is active."""
        if self._get_fit_mode():
            value = compute_chi_square(
                self.displayed_curves, self._canvas.get_time_limits()
            )
            self._set_chi_square(value)
        else:
            self._set_chi_square(None)

    def _update_units(self, params: dict[str, Any]) -> None:
        """Update canvas axis labels to match the active mode.

        Args:
            params: Current parameter mapping.
        """
        canvas = self._canvas
        if self._get_fit_mode():
            canvas.set_time_label("t", params["data.unit.time"])
            canvas.set_flux_label("F", params["data.unit.flux"])
        else:
            canvas.set_time_label("t", "T_0")
            canvas.set_flux_label("I", "I_0")
