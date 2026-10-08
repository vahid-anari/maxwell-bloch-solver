"""Matplotlib canvas and exporter for the main solver plots.

The canvas shows two panels: the top panel holds the measured data points
and the fitted flux, and the bottom panel holds one selectable profile (pump,
boundary condition, T1 or T2) on the left axis and the population inversion
w on a right twin axis. The exporter builds standalone figures and PDF
reports from the live canvas state.
"""

from __future__ import annotations

import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Tuple

import numpy as np
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout, QWidget

import matplotlib.pyplot as plt
from matplotlib import colors as mcolors
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.lines import Line2D
from matplotlib.ticker import AutoMinorLocator, ScalarFormatter

from settings.app_metadata import APP_NAME
from settings.app_style import EXPORT_PLOT_PAD_INCHES, USE_LATEX
from utils.helper_funcs import cut_y_by_x, get_range, pretty_json

if TYPE_CHECKING:
    from app.update_pipeline import DisplayedCurves


@dataclass
class PlotCurve:
    """Wrapper around a plotted line and its label metadata.

    Attributes:
        line: Matplotlib line object.
        label: Display label used for axis annotation.
        unit: Unit string associated with the plotted quantity.
    """

    line: Line2D
    label: str = ""
    unit: str = ""


class PlotExporter:
    """Build and save export figures derived from the live canvas state."""
    _PROFILE_ORDER = ("lambda_n", "A0", "t1", "t2")
    """Optional lower panels, in plotting order."""

    _ZERO_MEANING = {"lambda_n": "no pump", "A0": "no incident field"}
    """Explanation shown when a profile is omitted because it is zero."""

    _TOP_HEIGHT = 3.0
    """Height of the top (data/flux) panel in inches."""

    _PANEL_HEIGHT = 1.2
    """Height of each lower panel in inches."""

    def __init__(
            self,
            canvas: "PlotCanvas",
            get_displayed_curves: Callable[[], "DisplayedCurves"],
            get_params: Callable[[], dict[str, Any]],
            get_fit_mode: Callable[[], bool],
            get_view_preference: Callable[[str, bool], bool],
            get_metadata: Callable[[], dict[str, Any]],
            get_parameter_tabs_value: Callable[[], dict[str, Any]],
    ) -> None:
        """Initialize the plot exporter.

        Args:
            canvas: Live plot canvas used for style and limits.
            get_displayed_curves: Callable returning the current displayed-curves snapshot.
            get_params: Callable returning the current parameter mapping.
            get_fit_mode: Callable returning whether fit mode is active.
            get_view_preference: Callable used to query persisted grid preferences.
            get_metadata: Callable returning export metadata.
            get_parameter_tabs_value: Callable returning current parameter-tab values.
        """
        self._canvas = canvas
        self._get_displayed_curves = get_displayed_curves
        self._get_params = get_params
        self._get_fit_mode = get_fit_mode
        self._get_view_preference = get_view_preference
        self._get_metadata = get_metadata
        self._get_parameter_tabs_value = get_parameter_tabs_value

    def save(self, file_path: str) -> None:
        """Save the plot to a file.

        Args:
            file_path: Output path. The format is inferred from the suffix.
        """
        path = Path(file_path)
        if path.suffix.lower() == ".pdf":
            self._save_pdf(file_path)
        else:
            self._canvas.figure.savefig(path, bbox_inches="tight")

    def _save_pdf(self, file_path: str) -> None:
        """Save a PDF export containing plots and a report page.

        Args:
            file_path: Output PDF path.
        """
        report_text = self._build_report_text()
        report_lines = self._wrap_report_lines(report_text, width=110)

        with PdfPages(file_path) as pdf:
            export_fig = self._build_export_figure()
            pdf.savefig(export_fig, bbox_inches="tight", pad_inches=EXPORT_PLOT_PAD_INCHES)
            plt.close(export_fig)

            info = pdf.infodict()
            meta = self._get_metadata()
            info["Title"] = f"{APP_NAME} Export"
            info["Author"] = str(meta.get("saved_by", ""))
            info["Subject"] = "Plot export with metadata and parameters"
            info["Creator"] = APP_NAME
            info["Keywords"] = "Maxwell-Bloch, plot, parameters, metadata"

            lines_per_page = 70
            for start in range(0, len(report_lines), lines_per_page):
                chunk = report_lines[start: start + lines_per_page]

                # Disable LaTeX for plain-text report pages.
                with plt.rc_context({"text.usetex": False}):
                    fig = plt.figure(figsize=(8.27, 11.69))
                    ax = fig.add_axes([0, 0, 1, 1])
                    ax.axis("off")

                    fig.text(
                        0.05,
                        0.97,
                        f"{APP_NAME} Export Report",
                        ha="left",
                        va="top",
                        fontsize=14,
                        fontweight="bold",
                        usetex=False,
                    )
                    fig.text(
                        0.05,
                        0.94,
                        "\n".join(chunk),
                        ha="left",
                        va="top",
                        family="monospace",
                        fontsize=8,
                        usetex=False,
                    )

                    pdf.savefig(fig, bbox_inches="tight")
                    plt.close(fig)

    def _build_report_text(self) -> str:
        """Build the text report included in PDF exports.

        Returns:
            Report text containing metadata and parameter values.
        """
        metadata = self._get_metadata()
        params = self._get_parameter_tabs_value()
        parts = [
            "Metadata", "========", pretty_json(metadata), "",
            "Parameters", "==========", pretty_json(params),
        ]
        return "\n".join(parts)

    @staticmethod
    def _wrap_report_lines(text: str, width: int = 110) -> list[str]:
        """Wrap report text into fixed-width lines.

        Args:
            text: Full report text.
            width: Target line width.

        Returns:
            Wrapped lines suitable for pagination.
        """
        wrapped: list[str] = []
        for line in text.splitlines():
            if not line.strip():
                wrapped.append("")
                continue
            indent = len(line) - len(line.lstrip(" "))
            prefix = " " * indent
            body = line[indent:]
            chunks = textwrap.wrap(
                body,
                width=max(20, width - indent),
                replace_whitespace=False,
                drop_whitespace=False,
            )
            if not chunks:
                wrapped.append(prefix)
            else:
                wrapped.extend(prefix + chunk for chunk in chunks)
        return wrapped

    def _build_export_figure(self) -> plt.Figure:
        """Build the report figure: data/flux, w, then each non-trivial profile.

        Pump and boundary-condition panels are shown only if they are not zero
        everywhere, and T1/T2 panels only if they vary in time. Omitted panels
        are listed under the title.

        Returns:
            Matplotlib figure ready to be saved.
        """
        use_tex = USE_LATEX
        params = self._get_params()
        res = self._get_displayed_curves().results
        data = self._get_displayed_curves().data
        fit_mode = self._get_fit_mode()
        t_min, t_max = self._canvas.get_time_limits()

        shown, omitted = self._select_profiles(res)
        panel_ids = ["w"] + shown
        heights = [self._TOP_HEIGHT] + [self._PANEL_HEIGHT] * len(panel_ids)

        fig, axes = plt.subplots(
            nrows=len(heights),
            ncols=1,
            sharex=True,
            figsize=(8.27 - 2 * EXPORT_PLOT_PAD_INCHES, sum(heights)),
            gridspec_kw={"height_ratios": heights},
            constrained_layout=True,
        )
        axes = list(np.atleast_1d(axes))

        # ---- top panel: data and flux ----
        top_ax = axes[0]
        flux_style = self._canvas.get_curve_style("flux") or {}
        top_ax.plot(data.time, data.flux, **self._style_kwargs(self._canvas.get_curve_style("data_points")))
        top_ax.plot(res.time, res.intensity, **self._style_kwargs(flux_style))
        zero_line = self._canvas.add_ax_props(top_ax)
        top_ax.set_xlim(t_min, t_max)
        top_ax.set_ylim(self._canvas.get_flux_limits())
        flux_label = "F" if fit_mode else "I"
        flux_unit = params["data.unit.flux"] if fit_mode else "I_0"
        top_ax.set_ylabel(self._axis_label(flux_label, flux_unit), usetex=use_tex)
        self._style_axis(top_ax, zero_line, flux_style["color"], "flux")

        # ---- lower panels: w, then the selected profiles ----
        for ax, curve_id in zip(axes[1:], panel_ids):
            ys = getattr(res, curve_id)
            style = self._canvas.get_curve_style(curve_id) or {}
            ax.plot(res.time, ys, **self._style_kwargs(style))
            zero_line = self._canvas.add_ax_props(ax)
            ax.set_ylabel(self._axis_label(style.get("label", ""), style.get("unit", "")), usetex=use_tex)
            ax.set_ylim(get_range(
                limits=params[f"display.range.{curve_id}"],
                arr1=cut_y_by_x(y=ys, x=res.time, xmin=t_min, xmax=t_max),
            ))
            if curve_id == "w":
                self._style_axis(ax, zero_line, style["color"], "w", dotted=True)
            else:
                self._style_axis(ax, zero_line, style["color"], "bottom")

        time_unit = params["data.unit.time"] if fit_mode else "T_0"
        axes[-1].set_xlabel(self._axis_label("t", time_unit), usetex=use_tex)
        for ax in axes[:-1]:
            ax.label_outer()

        title = self._figure_title(fit_mode)
        omitted_text = self._omitted_text(res, omitted)
        fig.suptitle(f"{title}\n{omitted_text}" if omitted_text else title, fontsize=11)
        return fig

    def _select_profiles(self, res: "SolverResultsDisplay") -> tuple[list[str], list[str]]:
        """Split the optional profiles into shown and omitted ones.

        Args:
            res: Displayed solver results.

        Returns:
            Tuple ``(shown, omitted)`` of profile identifiers, in plotting order.
        """
        shown: list[str] = []
        omitted: list[str] = []
        for curve_id in self._PROFILE_ORDER:
            ys = getattr(res, curve_id)
            if ys.size == 0:
                keep = False
            elif curve_id in self._ZERO_MEANING:
                keep = bool(np.any(ys != 0.0))
            else:
                keep = bool(np.ptp(ys) != 0.0)
            (shown if keep else omitted).append(curve_id)
        return shown, omitted

    def _omitted_text(self, res: "SolverResultsDisplay", omitted: list[str]) -> str:
        """Describe omitted profiles, e.g. 'Not shown: A|z=0 = 0 (no incident field)'.

        Args:
            res: Displayed solver results.
            omitted: Identifiers of omitted profiles.

        Returns:
            One-line description, or an empty string if nothing was omitted.
        """
        parts = []
        for curve_id in omitted:
            style = self._canvas.get_curve_style(curve_id) or {}
            label = style.get("label", curve_id)
            ys = getattr(res, curve_id)
            if curve_id in self._ZERO_MEANING or ys.size == 0:
                parts.append(rf"${label} = 0$ ({self._ZERO_MEANING.get(curve_id, 'empty')})")
            else:
                unit = style.get("unit", "")
                parts.append(rf"${label} = {ys[0]:.3g}\,\mathrm{{{unit}}}$ (constant)")
        return "Not shown: " + "; ".join(parts) if parts else ""

    def _figure_title(self, fit_mode: bool) -> str:
        """Return the figure title identifying the source and velocity, if any.

        Args:
            fit_mode: Whether fit mode is active.

        Returns:
            Title text.
        """
        meta = self._get_metadata()
        if not (fit_mode and meta.get("source")):
            return "Model run"
        title = f"Source: {meta['source']}"
        if meta.get("period"):
            title += f", period {meta['period']}"
        if meta.get("velocity"):
            title += f", v = {meta['velocity']}"
        if USE_LATEX:
            title = title.replace("_", r"\_").replace("%", r"\%")
        return title

    def _style_axis(self, ax: plt.Axes, zero_line, color: str, y_prefix: str, dotted: bool = False) -> None:
        """Colour the zero line and apply saved grids, matching the live canvas.

        Args:
            ax: Target axis.
            zero_line: Zero line returned by ``add_ax_props``.
            color: Colour of the panel's curve.
            y_prefix: Preference prefix for the y grid (``"flux"``, ``"w"`` or ``"bottom"``).
            dotted: Whether the y grid is dotted (used for w).
        """
        zero_line.set_color(color)
        zero_line.set_alpha(0.6)
        pref = self._get_view_preference
        for which in ("major", "minor"):
            ax.grid(pref(f"show_time_{which}_grid", False), which=which, axis="x")
            if pref(f"show_{y_prefix}_{which}_grid", False):
                ax.grid(True, which=which, axis="y", color=color, alpha=0.3,
                        linestyle=":" if dotted else "-")
            else:
                ax.grid(False, which=which, axis="y")

    @staticmethod
    def _style_kwargs(style: dict[str, Any]) -> dict[str, Any]:
        """Convert a stored style mapping into ``plot`` keyword arguments.

        Args:
            style: Curve style mapping.

        Returns:
            Keyword-argument mapping for Matplotlib plotting.
        """
        out = {
            "color": style["color"],
            "linestyle": style["linestyle"],
            "linewidth": style["linewidth"],
        }
        marker = style.get("marker")
        if marker not in (None, "", "None", "none", " "):
            out["marker"] = marker
            out["markersize"] = style.get("markersize", 6.0)
        return out

    @staticmethod
    def _axis_label(label: str, unit: str) -> str:
        """Build a LaTeX axis label from a quantity label and unit.

        Args:
            label: Quantity label.
            unit: Unit string.

        Returns:
            LaTeX-formatted axis label.
        """
        if not label:
            return ""
        if unit == "µs":
            unit = "\\mu s"
        if unit:
            return rf"${label}\; (\mathrm{{{unit}}})$"
        return rf"${label}$"


class PlotCanvas(FigureCanvas):
    """Embedded Matplotlib canvas used by the main application window."""

    def __init__(
            self,
            figure_props: Dict[str, Any],
            axes_props: Dict[str, Any],
            lines_props: Dict[str, Any],
            t_limits: Tuple[float, float],
            parent=None,
    ):
        """Initialize the canvas from the JSON-driven plot configuration.

        Args:
            figure_props: Figure-level settings.
            axes_props: Axis-level settings.
            lines_props: Line-style specifications for all curves.
            t_limits: Initial time-axis limits.
            parent: Optional Qt parent widget.
        """
        self._use_tex = USE_LATEX
        self._axes_props = axes_props

        science_style = figure_props["science_style"]
        fig_main_kws = figure_props["main"]
        fig_margin_kws = figure_props["margin"]
        self._n_axes = fig_main_kws["nrows"]
        if science_style:
            plt.style.use("science")

        self._t_limits = t_limits
        self._flux_limits = (-1, 1)
        self._current_center_lines = [None] * self._n_axes
        self._current_spans = [None] * self._n_axes

        # Make figure
        self._fig, self._axes = plt.subplots(**fig_main_kws)
        self._fig.subplots_adjust(**fig_margin_kws)

        # Top panel
        top_left = lines_props["top_panel"]["left"]
        self._flux_grid = {"major": False, "minor": False}
        self._data_points_curve = self._make_curve(self._axes[0], top_left["data_points"])
        self._flux_curve = self._make_curve(self._axes[0], top_left["flux"])

        # Bottom panel - left
        profiles = lines_props["bottom_panel"]["left"]
        self._profile_curves: Dict[str, PlotCurve] = {}
        self._profile_combo_labels: Dict[str, str] = {}
        self._profile_grid = {"major": False, "minor": False}
        self._has_profile = True
        self._profile_color = "black"
        for name, props in profiles.items():
            curve = self._make_curve(self._axes[1], props)
            self._profile_curves[name] = curve
            self._profile_combo_labels[name] = props.get("combo_label", "")

        for i in range(self._n_axes):
            ax = self._axes[i]
            zero_line = self.add_ax_props(ax)
            if i == 0:
                self._flux_zero_line = zero_line
            elif i == 1:
                self._profile_zero_line = zero_line
            self._current_center_lines[i] = ax.axvline(0.0, **axes_props["current_span"]["line"], visible=False)
            self._current_spans[i] = ax.axvspan(0.0, 1.0, **axes_props["current_span"]["span"], visible=False)
            ax.tick_params(axis="y", which="both", right=False)

        # Bottom panel - right
        self._w_grid = {"major": False, "minor": False}
        self._ax_w = self._axes[1].twinx()
        self._w_zero_line = self.add_ax_props(self._ax_w)
        bottom_right = lines_props["bottom_panel"]["right"]
        self._w_curve = self._make_curve(self._ax_w, bottom_right["w"])
        self._ax_w.set_ylabel(self._make_label(self._w_curve))
        self._ax_w.set_zorder(self._axes[1].get_zorder() + 1)
        self._ax_w.patch.set_visible(False)
        self._w_visible = True

        # Zero line
        self._flux_zero_line.set_color(self._flux_curve.line.get_color())
        self._w_zero_line.set_color(self._w_curve.line.get_color())
        self._flux_zero_line.set_alpha(0.6)
        self._profile_zero_line.set_alpha(0.6)
        self._w_zero_line.set_alpha(0.6)

        # Each bottom axis owns one side: profile = left, w = right.
        self._axes[1].tick_params(axis="y", which="both", right=False)
        self._ax_w.tick_params(axis="y", which="both", left=False, right=True, labelright=True)
        self._ax_w.xaxis.set_visible(False)
        for spine in self._ax_w.spines.values():
            spine.set_visible(False)

        super().__init__(self._fig)
        self.setParent(parent)
        self.setMinimumWidth(700)
        self.setMinimumHeight(350)

    def _make_curve(self, ax, props):
        """Create one plotted curve from provided style properties.

        Args:
            ax: Target matplotlib axis.
            props: Curve property mapping.

        Returns:
            Plot-curve wrapper for the created line.
        """

        line, = ax.plot([], [], **props["props"])
        label = props.get("label", "")
        unit = props.get("unit", "")
        return PlotCurve(line=line, label=label, unit=unit)

    def _make_label(self, curve: PlotCurve):
        """Build the axis label for a plot curve.

        Args:
            curve: Curve wrapper.

        Returns:
            LaTeX axis label string.
        """

        return rf"${curve.label}\; (\mathrm{{{curve.unit}}})$"

    def _get_curve_by_id(self, curve_id: str) -> PlotCurve | None:
        """Return one curve object by its internal identifier.

        Args:
            curve_id: Internal curve identifier.

        Returns:
            Matching curve wrapper, or ``None`` if unknown.
        """

        if curve_id == "data_points":
            return self._data_points_curve
        if curve_id == "flux":
            return self._flux_curve
        if curve_id == "w":
            return self._w_curve
        return self._profile_curves.get(curve_id)

    def add_ax_props(self, ax):
        """Apply standard styling and locators to one axis.

        Args:
            ax: Target matplotlib axis.

        Returns:
            The dashed zero line drawn on this axis.
        """

        zero_line = ax.axhline(0, **self._axes_props["zero_h_line"])
        ax.set_xlabel("", **self._axes_props["label_font"], usetex=self._use_tex)
        ax.set_ylabel("", **self._axes_props["label_font"], labelpad=5, usetex=self._use_tex)
        ax.ticklabel_format(style='plain', axis='x')
        ax.ticklabel_format(style='sci', axis='y', scilimits=(-2, 3))
        ax.tick_params(**self._axes_props["ticks"], **self._axes_props["ticks_major"])
        ax.tick_params(**self._axes_props["ticks"], **self._axes_props["ticks_minor"])
        ax.tick_params(axis='x', which='both', pad=5)
        ax.xaxis.set_minor_locator(AutoMinorLocator(self._axes_props["xaxis_minor_locator"]))
        ax.yaxis.set_minor_locator(AutoMinorLocator(self._axes_props["yaxis_minor_locator"]))
        ax.yaxis.get_offset_text().set_fontsize(self._axes_props["axis_offset_font"]['fontsize'])
        ax.yaxis.get_offset_text().set_fontname(self._axes_props["axis_offset_font"]['fontname'])
        fmtx = ScalarFormatter(useOffset=False)
        fmtx.set_scientific(False)
        ax.xaxis.set_major_formatter(fmtx)

        return zero_line

    def get_profile_combo_labels(self):
        """Return the display labels of the profiles.

        Returns:
            Mapping from internal profile names to display labels.
        """

        return self._profile_combo_labels

    # Set data
    def set_data_points(self, xs: np.ndarray, ys: np.ndarray):
        """Update the measured-data curve.

        Args:
            xs: X coordinates.
            ys: Y coordinates.
        """

        self._data_points_curve.line.set_data(xs, ys)

    def set_flux(self, xs: np.ndarray, ys: np.ndarray):
        """Update the solver-intensity curve.

        Args:
            xs: X coordinates.
            ys: Y coordinates.
        """

        self._flux_curve.line.set_data(xs, ys)

    def set_profile_data(self, name: str, xs: np.ndarray, ys: np.ndarray) -> None:
        """Update one profile curve without changing its visibility.

        Args:
            name: Internal profile name.
            xs: X coordinates.
            ys: Y coordinates.
        """

        curve = self._profile_curves.get(name)
        if curve is None:
            return
        curve.line.set_data(xs, ys)

    def set_w_data(self, xs: np.ndarray, ys: np.ndarray) -> None:
        """Update the population-inversion curve on the right axis."""
        self._w_curve.line.set_data(xs, ys)

    # Get limit
    def get_time_limits(self):
        """Return the current time-axis limits.

        Returns:
            Current ``(t_min, t_max)`` tuple.
        """

        return self._t_limits

    def get_flux_limits(self):
        """Return the current top-panel y-axis limits.

        Returns:
            Current ``(y_min, y_max)`` tuple.
        """

        return self._flux_limits

    # Set limit
    def set_time_limit(self, limit: Tuple[float, float]):
        """Set the time-axis limits and propagate them to shared axes.

        Args:
            limit: New ``(t_min, t_max)`` tuple.
        """
        self._t_limits = limit
        self._axes[0].set_xlim(limit)

    def set_flux_limit(self, limit: Tuple[float, float]):
        """Set the flux or intensity limits.

        Args:
            limit: New ``(y_min, y_max)`` tuple.
        """
        self._flux_limits = limit
        self._axes[0].set_ylim(limit)

    def set_profile_y_limit(self, limit: Tuple[float, float]):
        """Set the profile (left) y-axis limits of the bottom panel.

        Args:
            limit: New ``(y_min, y_max)`` tuple.
        """
        self._axes[1].set_ylim(limit)

    def set_w_y_limit(self, limit: Tuple[float, float]) -> None:
        """Set the right (w) axis limits."""
        self._ax_w.set_ylim(limit)

    # Set label
    def set_time_label(self, label: str, unit: str):
        """Set the time-axis label using LaTeX notation.

        Args:
            label: Quantity label.
            unit: Unit string.
        """

        if unit == "µs":
            unit = "\\mu s"
        self._axes[-1].set_xlabel(rf"${label}\; (\mathrm{{{unit}}})$")

    def set_flux_label(self, label: str, unit: str):
        """Set the top-panel y-axis label using LaTeX notation.

        Args:
            label: Quantity label.
            unit: Unit string.
        """

        self._axes[0].set_ylabel(rf"${label}\; (\mathrm{{{unit}}})$")

    # Set span
    def set_current_span_visible(self, visible: bool):
        """Show or hide the selected-component highlight on all axes.

        The highlight is the center line and shaded span of the currently
        selected pulse or step.

        Args:
            visible: Whether the highlight should be visible.
        """

        for i in range(self._n_axes):
            self._current_center_lines[i].set_visible(visible)
            self._current_spans[i].set_visible(visible)

    def set_current_span_position(self, x0: float, wl: float, wr: float):
        """Reposition the selected-component highlight.

        Args:
            x0: Center of the selected pulse or step.
            wl: Left half-extent.
            wr: Right half-extent.
        """

        if wl > 1.0e10:
            wl = 1.0e10
        if wr > 1.0e10:
            wr = 1.0e10
        x_left = x0 - wl
        width = wl + wr
        for i in range(self._n_axes):
            self._current_center_lines[i].set_xdata([x0, x0])
            self._current_spans[i].set_x(x_left)
            self._current_spans[i].set_width(width)

    # Set grid
    def set_time_grid(self, visible: bool, which: str):
        """Toggle the x-axis grid on both axes.

        Args:
            visible: Whether the grid should be shown.
            which: Grid type, typically ``"major"`` or ``"minor"``.
        """

        self._axes[0].grid(visible=visible, which=which, axis='x')
        self._axes[1].grid(visible=visible, which=which, axis='x')

    def set_flux_grid(self, visible: bool, which: str) -> None:
        """Toggle the top-panel y-axis grid, drawn in the flux curve's colour.

        Args:
            visible: Whether the grid should be shown.
            which: Grid type, typically ``"major"`` or ``"minor"``.
        """
        self._flux_grid[which] = visible
        self._apply_flux_grid()

    def set_w_grid(self, visible: bool, which: str) -> None:
        """Toggle the y-axis grid of the w (right) axis, drawn in w's colour."""
        self._w_grid[which] = visible
        self._apply_w_grid()

    def set_profile_grid(self, visible: bool, which: str) -> None:
        """Toggle the profile (left) y-axis grid of the bottom panel.

        The choice is remembered and only shown while a profile is selected.

        Args:
            visible: Whether the grid should be shown.
            which: Grid type, typically ``"major"`` or ``"minor"``.
        """
        self._profile_grid[which] = visible
        self._apply_profile_grid()

    # Apply grid
    def _apply_flux_grid(self) -> None:
        """Apply the remembered top-panel y grid in the current flux colour."""
        ax = self._axes[0]
        color = self._flux_curve.line.get_color()
        for which, on in self._flux_grid.items():
            if on:
                ax.grid(True, which=which, axis="y", color=color, alpha=0.3)
            else:
                ax.grid(False, which=which, axis="y")

    def _apply_w_grid(self) -> None:
        """Apply the remembered w grid in the current w colour."""
        color = self._w_curve.line.get_color()
        for which, on in self._w_grid.items():
            if on:
                self._ax_w.grid(True, which=which, axis="y", linestyle=":", color=color, alpha=0.3)
            else:
                self._ax_w.grid(False, which=which, axis="y")

    def _apply_profile_grid(self) -> None:
        """Show the remembered profile grid, in the profile's colour, only when a profile is visible."""
        ax = self._axes[1]
        for which, on in self._profile_grid.items():
            if on and self._has_profile:
                ax.grid(True, which=which, axis="y", color=self._profile_color, alpha=0.3)
            else:
                ax.grid(False, which=which, axis="y")

    # Curve color
    def get_curve_color(self, curve_id: str) -> str | None:
        """Return one curve's current color as a hex string.

        Args:
            curve_id: Internal curve identifier.

        Returns:
            Hex color string, or ``None`` if the curve is unknown.
        """

        curve = self._get_curve_by_id(curve_id)
        if curve is None:
            return None
        return mcolors.to_hex(curve.line.get_color())

    def set_curve_color(self, curve_id: str, color: str) -> bool:
        """Set one curve's color.

        Args:
            curve_id: Internal curve identifier.
            color: New color value.

        Returns:
            ``True`` on success, or ``False`` if the curve identifier is unknown.
        """

        curve = self._get_curve_by_id(curve_id)
        if curve is None:
            return False

        curve.line.set_color(color)
        if curve_id == "flux":
            self._flux_zero_line.set_color(color)
            self._apply_flux_grid()
        elif curve_id == "w":
            self._w_zero_line.set_color(color)
            self._apply_w_grid()
        elif curve.line.get_visible() and curve_id in self._profile_curves:
            self._profile_zero_line.set_color(color)
            self._profile_color = color
            self._apply_profile_grid()
        return True

    def apply_curve_colors(self, colors: dict[str, str]) -> None:
        """Apply colors to multiple curves at once.

        Args:
            colors: Mapping from curve identifiers to hex color strings.
        """

        for curve_id, color in colors.items():
            self.set_curve_color(curve_id, color)

    # Curve style
    def get_curve_style(self, curve_id: str) -> dict[str, Any] | None:
        """Return style and label properties for one curve.

        Args:
            curve_id: Internal curve identifier.

        Returns:
            Style mapping for the curve, or ``None`` if the identifier is
            unknown.
        """

        curve = self._get_curve_by_id(curve_id)
        if curve is None:
            return None

        line = curve.line
        return {
            "color": mcolors.to_hex(line.get_color()),
            "linestyle": line.get_linestyle(),
            "linewidth": float(line.get_linewidth()),
            "marker": line.get_marker(),
            "markersize": float(line.get_markersize()),
            "label": curve.label,
            "unit": curve.unit,
        }

    # Visibility
    def show_profile(self, name: str | None) -> None:
        """Show one profile on the left axis (or none) and hide the others.

        With ``None``, the left axis label, tick marks and tick labels are hidden.

        Args:
            name: Internal curve name to show, or ``None`` for no profile.
        """
        ax = self._axes[1]
        for n, curve in self._profile_curves.items():
            visible = (n == name)
            curve.line.set_visible(visible)
            if visible:
                ax.set_ylabel(self._make_label(curve))
                curve_color = curve.line.get_color()
                self._profile_zero_line.set_color(curve_color)
                self._profile_color = curve_color

        has_profile = name is not None
        self._has_profile = has_profile
        self._apply_profile_grid()
        if not has_profile:
            ax.set_ylabel("")
        ax.tick_params(axis="y", which="both", left=has_profile, labelleft=has_profile)
        ax.yaxis.get_offset_text().set_visible(has_profile)
        self._profile_zero_line.set_visible(has_profile)

    def set_w_visible(self, visible: bool) -> None:
        """Show or hide the population inversion w and its right-hand axis.

        Args:
            visible: Whether w should be shown.
        """
        self._w_visible = bool(visible)
        self._ax_w.set_visible(self._w_visible)

    def is_w_visible(self) -> bool:
        """Return whether w is currently shown.

        Returns:
            ``True`` if the w curve and its axis are visible.
        """
        return self._w_visible

    # Redraw
    def redraw(self):
        """Schedule a non-blocking canvas redraw."""

        self.draw_idle()


def _demo_main() -> int:
    """Run the plotting canvas as a standalone demo.

    Returns:
        Qt application exit code.
    """

    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QListWidget,
        QListWidgetItem,
    )
    from paths import SETTINGS_FILE_PATH
    from settings.app_style import set_app_style
    from ui.params.range_sliders import FloatRangeSlider
    from utils.helper_funcs import cut_y_by_x, get_range, read_json

    sys.path.append("/Users/vahidanari/Desktop/Python Examples")
    from bbox_color import ColorDelegate, mcolors

    app = QApplication(sys.argv)
    set_app_style(app)

    win = QWidget()
    win.setWindowTitle("Matplotlib Canvas")

    t1, t2 = -3.0, 3.0
    t = np.linspace(t1, t2, 10000)
    t_data = np.linspace(t1, t2, 100)
    data = np.sin(t_data) + 0.1 * np.random.uniform(-1, 1, size=len(t_data))
    I = np.sin(t)
    sec_line = {
        "w": np.cos(t),
        "lambda_n": np.cos(t) ** 2,
        "A0": np.tanh(t),
    }

    def_cfgs = read_json(SETTINGS_FILE_PATH)
    fig_props = def_cfgs["figure"]
    axes_props = def_cfgs["axes"]
    lines_props = def_cfgs["lines"]

    canvas = PlotCanvas(
        figure_props=fig_props,
        axes_props=axes_props,
        lines_props=lines_props,
        t_limits=(t1, t2),
    )

    canvas.set_data_points(t_data, data)
    canvas.set_flux(t, I)
    canvas.set_profile_data("w", t, sec_line["w"])

    canvas.set_time_label('t', 'Day')
    canvas.set_flux_label('F', 'Jy')

    canvas.redraw()

    t_range = FloatRangeSlider(
        label="t",
        min_val=2 * t1,
        max_val=2 * t2,
        init_vals=(t1, t2),
    )
    f_range = FloatRangeSlider(
        label="F",
        min_val=-2,
        max_val=2,
        use_margins=True,
    )
    range = {
        "w": FloatRangeSlider(
            label="w",
            min_val=-2,
            max_val=2,
            use_margins=True,
        ),
        "lambda_n": FloatRangeSlider(
            label="\\Lambda_N",
            min_val=-2,
            max_val=2,
            use_margins=True,
        ),
        "A0": FloatRangeSlider(
            label="A_0",
            min_val=-2,
            max_val=2,
            use_margins=True,
        ),
    }

    sec_combo = QComboBox()
    for name, label in canvas.get_profile_combo_labels().items():
        sec_combo.addItem(label, name)

    color_list = QListWidget()
    color_list.setItemDelegate(ColorDelegate(color_list))
    color_list.setSelectionMode(QAbstractItemView.SingleSelection)

    for name in sorted(mcolors.get_named_colors_mapping().keys()):
        QListWidgetItem(name, color_list)

    def range_changed():
        """Update plot ranges from the demo range widgets."""

        canvas.set_time_limit(get_range(t_range.get_value(), arr1=t, arr2=t_data))
        t_min, t_max = canvas.get_time_limits()
        I_new = cut_y_by_x(
            y=I,
            x=t,
            xmin=t_min,
            xmax=t_max,
        )
        data_new = cut_y_by_x(
            y=data,
            x=t_data,
            xmin=t_min,
            xmax=t_max,
        )
        canvas.set_flux_limit(get_range(f_range.get_value(), arr1=I_new, arr2=data_new))
        sec_curve = sec_combo.currentData()
        if sec_curve:
            y_new = cut_y_by_x(
                y=sec_line[sec_curve],
                x=t,
                xmin=t_min,
                xmax=t_max,
            )
            canvas.set_profile_y_limit(get_range(range[sec_curve].get_value(), arr1=y_new))
        canvas.redraw()

    def update_face_color(face):
        """Update the figure face color in the demo."""

        canvas._fig.set_facecolor(face)
        canvas.redraw()

    def combo_changed():
        """Update the visible bottom-panel curve in the demo."""

        sec_curve = sec_combo.currentData()
        if sec_curve:
            canvas.show_profile(sec_curve)
            for w in range.values():
                w.hide()
            range[sec_curve].show()
        canvas.set_profile_data(sec_curve, t, sec_line[sec_curve])
        range_changed()

    t_range.valueChanged.connect(range_changed)
    f_range.valueChanged.connect(range_changed)
    for w in range.values():
        w.valueChanged.connect(range_changed)
    color_list.currentTextChanged.connect(update_face_color)
    sec_combo.currentTextChanged.connect(combo_changed)

    color_list.setCurrentRow(0)

    v_l = QVBoxLayout()
    h_l = QHBoxLayout()

    v_l.addWidget(canvas)
    v_l.addWidget(t_range)
    v_l.addWidget(f_range)
    for w in range.values():
        v_l.addWidget(w)

    v_l2 = QVBoxLayout()
    v_l2.addWidget(sec_combo)
    v_l2.addWidget(color_list)

    h_l.addLayout(v_l, 1)
    h_l.addLayout(v_l2, 0)

    win.setLayout(h_l)
    win.resize(1200, 800)
    combo_changed()
    range_changed()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
