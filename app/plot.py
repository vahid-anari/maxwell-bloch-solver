"""Matplotlib canvas and exporter for the main solver plots.

The canvas is a ``sciwidgets.plot.PlotCanvas`` built from the ``"plot"``
section of ``settings/settings.json``: the top panel holds the measured data
points and the flux, the bottom panel one selectable profile (pump, boundary
condition, T1 or T2) with the population inversion w on a right twin axis.
This module adds MB Solver's names for its curves and panels, and the
exporter that builds standalone figures and PDF reports.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Mapping, Optional, Tuple

import numpy as np

import matplotlib.pyplot as plt
from matplotlib.transforms import ScaledTranslation
from matplotlib.backends.backend_pdf import PdfPages

from sciwidgets.plot import PlotCanvas as _SciPlotCanvas
from settings.app_metadata import APP_NAME
from settings.app_style import EXPORT_PLOT_PAD_INCHES, USE_LATEX
from utils.helper_funcs import cut_y_by_x, get_range, pretty_json

if TYPE_CHECKING:
    from app.update_pipeline import DisplayedCurves


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

    _PAGE_SIZE = (8.27, 11.69)
    """A4 page size in inches."""

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
        """Save a PDF export containing the report figure and text pages.

        Every page carries a 'Page X of N' footer.

        Args:
            file_path: Output PDF path.
        """
        report_text = self._build_report_text()
        report_lines = self._wrap_report_lines(report_text, width=110)

        lines_per_page = 70
        chunks = [
            report_lines[start: start + lines_per_page]
            for start in range(0, len(report_lines), lines_per_page)
        ]
        total_pages = 1 + len(chunks)

        with PdfPages(file_path) as pdf:
            export_fig = self._build_export_figure()
            self._add_page_footer(export_fig, 1, total_pages)
            pdf.savefig(export_fig)
            plt.close(export_fig)

            info = pdf.infodict()
            meta = self._get_metadata()
            info["Title"] = f"{APP_NAME} Export"
            info["Author"] = str(meta.get("saved_by", ""))
            info["Subject"] = "Plot export with metadata and parameters"
            info["Creator"] = APP_NAME
            info["Keywords"] = "Maxwell-Bloch, plot, parameters, metadata"

            for page, chunk in enumerate(chunks, start=2):
                # Disable LaTeX for plain-text report pages.
                with plt.rc_context({"text.usetex": False}):
                    fig = plt.figure(figsize=self._PAGE_SIZE)
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
                    self._add_page_footer(fig, page, total_pages)

                    pdf.savefig(fig)
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
    def _add_page_footer(fig: plt.Figure, page: int, total: int, below: bool = False) -> None:
        """Add a centred 'Page X of N' footer to one figure.

        Args:
            fig: Figure to annotate.
            page: Current page number, starting at 1.
            total: Total number of pages.
            below: Place the footer just below the figure instead of inside it.
                Use this for figures whose layout fills the whole canvas.
        """
        if below:
            offset = ScaledTranslation(0, -0.15, fig.dpi_scale_trans)  # 0.15 in below the edge
            fig.text(0.5, 0.0, f"Page {page} of {total}", ha="center", va="top",
                     fontsize=8, color="0.4", usetex=False,
                     transform=fig.transFigure + offset)
        else:
            fig.text(0.5, 0.01, f"Page {page} of {total}", ha="center", va="bottom",
                     fontsize=8, color="0.4", usetex=False)

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

        page_w, page_h = self._PAGE_SIZE
        margin_left, margin_right, margin_top = 1.0, 0.5, 1.0  # inches
        gap = 0.12  # space between panels, inches
        content_h = sum(heights) + gap * (len(heights) - 1)

        fig = plt.figure(figsize=(page_w, page_h))
        gs = fig.add_gridspec(
            nrows=len(heights),
            ncols=1,
            height_ratios=heights,
            left=margin_left / page_w,
            right=1 - margin_right / page_w,
            top=1 - margin_top / page_h,
            bottom=1 - (margin_top + content_h) / page_h,
            hspace=gap / np.mean(heights),
        )
        axes = [fig.add_subplot(gs[0])]
        axes += [fig.add_subplot(gs[i], sharex=axes[0]) for i in range(1, len(heights))]

        # ---- top panel: data and flux ----
        top_ax = axes[0]
        flux_style = self._canvas.get_curve_style("flux") or {}
        top_ax.plot(data.time, data.flux, **self._style_kwargs(self._canvas.get_curve_style("data_points")))
        top_ax.plot(res.time, res.intensity, **self._style_kwargs(flux_style))
        zero_line = self._canvas.style_axes(top_ax)
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
            zero_line = self._canvas.style_axes(ax)
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
        title_text = f"{title}\n{omitted_text}" if omitted_text else title
        fig.text(0.5, 1 - 0.4 / page_h, title_text, ha="center", va="top", fontsize=11)
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


class PlotCanvas(_SciPlotCanvas):
    """The main plot, with MB Solver's names for its curves and panels.

    Panels: ``top`` (data points and flux), ``bottom`` (one profile) and
    ``bottom.twin`` (w). Curves: ``data_points``, ``flux``, ``lambda_n``,
    ``A0``, ``t1``, ``t2``, ``w``. Markers: ``span`` and ``span_center``
    (the current pulse or step).
    """

    PROFILES = ("lambda_n", "A0", "t1", "t2")

    def __init__(self, description: Mapping[str, Any], parent=None) -> None:
        """Build the canvas.

        Args:
            description: The ``"plot"`` section of the settings file.
            parent: Optional Qt parent widget.
        """
        super().__init__(description, parent, usetex=USE_LATEX, context_menu=False)
        self.setMinimumWidth(700)
        self.setMinimumHeight(350)

    # ----- data -----
    def set_data_points(self, xs: np.ndarray, ys: np.ndarray) -> None:
        """Update the measured-data curve."""
        self.set_curve_data("data_points", xs, ys)

    def set_flux(self, xs: np.ndarray, ys: np.ndarray) -> None:
        """Update the solver-intensity curve."""
        self.set_curve_data("flux", xs, ys)

    def set_profile_data(self, name: str, xs: np.ndarray, ys: np.ndarray) -> None:
        """Update one profile curve without changing its visibility."""
        self.set_curve_data(name, xs, ys)

    def set_w_data(self, xs: np.ndarray, ys: np.ndarray) -> None:
        """Update the w curve."""
        self.set_curve_data("w", xs, ys)

    def get_profile_combo_labels(self) -> Dict[str, str]:
        """Return the display names of the profiles."""
        return {cid: self.get_curve_name(cid) for cid in self.curve_ids("bottom")}

    # ----- limits and labels -----
    def get_time_limits(self) -> Tuple[float, float]:
        """Return the time-axis limits."""
        return self.get_limits("top")[0]

    def get_flux_limits(self) -> Tuple[float, float]:
        """Return the top-panel y limits."""
        return self.get_limits("top")[1]

    def set_time_limit(self, limit: Tuple[float, float]) -> None:
        """Set the time-axis limits (shared by both panels)."""
        self.set_limits("top", x=limit)

    def set_flux_limit(self, limit: Tuple[float, float]) -> None:
        """Set the top-panel y limits."""
        self.set_limits("top", y=limit)

    def set_profile_y_limit(self, limit: Tuple[float, float]) -> None:
        """Set the profile (left) y limits of the bottom panel."""
        self.set_limits("bottom", y=limit)

    def set_w_y_limit(self, limit: Tuple[float, float]) -> None:
        """Set the w (right) axis limits."""
        self.set_limits("bottom.twin", y=limit)

    def set_time_label(self, label: str, unit: str) -> None:
        """Set the time-axis label (math text)."""
        self.set_label("bottom", "x", label, "\\mu s" if unit == "µs" else unit)

    def set_flux_label(self, label: str, unit: str) -> None:
        """Set the top-panel y label (math text)."""
        self.set_label("top", "y", label, unit)

    # ----- current span -----
    def set_current_span_visible(self, visible: bool) -> None:
        """Show or hide the current pulse/step highlight on both panels."""
        self.set_marker_visible("span", visible)
        self.set_marker_visible("span_center", visible)

    def set_current_span_position(self, x0: float, wl: float, wr: float) -> None:
        """Move the current pulse/step highlight to ``x0 - wl ... x0 + wr``."""
        wl, wr = min(wl, 1.0e10), min(wr, 1.0e10)
        self.set_marker("span", (x0 - wl, x0 + wr))
        self.set_marker("span_center", x0)

    # ----- grids -----
    def set_time_grid(self, visible: bool, which: str) -> None:
        """Toggle the vertical (time) grid on both panels."""
        self.set_grid("top", visible, which, "x")
        self.set_grid("bottom", visible, which, "x")

    def set_flux_grid(self, visible: bool, which: str) -> None:
        """Toggle the top-panel horizontal grid (in the flux colour)."""
        self.set_grid("top", visible, which, "y")

    def set_w_grid(self, visible: bool, which: str) -> None:
        """Toggle the w-axis horizontal grid (in the w colour)."""
        self.set_grid("bottom.twin", visible, which, "y")

    def set_profile_grid(self, visible: bool, which: str) -> None:
        """Toggle the profile horizontal grid (shown only while a profile is selected)."""
        self.set_grid("bottom", visible, which, "y")

    # ----- colours and styles -----
    def get_curve_color(self, curve_id: str) -> Optional[str]:
        """Return a curve's colour as a hex string, or ``None`` if unknown."""
        if curve_id not in self.curve_ids():
            return None
        return self.get_curve_style(curve_id)["color"]

    def set_curve_color(self, curve_id: str, color: str) -> bool:
        """Set a curve's colour; return ``False`` if the curve is unknown."""
        if curve_id not in self.curve_ids():
            return False
        self.set_curve_style(curve_id, color=color)
        return True

    def apply_curve_colors(self, colors: Dict[str, str]) -> None:
        """Set several curve colours at once."""
        for curve_id, color in colors.items():
            self.set_curve_color(curve_id, color)

    def default_curve_colors(self) -> Dict[str, str]:
        """Return the colours from the settings file, by curve id."""
        return {cid: self.default_curve_style(cid)["color"] for cid in self.curve_ids()}

    def get_curve_style(self, curve_id: str) -> Dict[str, Any]:
        """Return a curve's style plus its ``label`` and ``unit`` (used by the exporter)."""
        style = super().get_curve_style(curve_id)
        style["label"], style["unit"] = self.get_curve_label(curve_id)
        return style

    # ----- visibility -----
    def show_profile(self, name: Optional[str]) -> None:
        """Show one profile in the bottom panel, or none (``None``)."""
        self.select_curve("bottom", name)

    def set_w_visible(self, visible: bool) -> None:
        """Show or hide w and its right-hand axis."""
        self.set_axis_visible("bottom.twin", visible)

    def is_w_visible(self) -> bool:
        """Return whether w is shown."""
        return self.is_axis_visible("bottom.twin")


def _demo_main() -> int:
    """Show the canvas with made-up data: ``python -m app.plot``.

    Returns:
        Qt application exit code.
    """
    from PySide6.QtWidgets import QApplication

    from paths import SETTINGS_FILE_PATH
    from settings.app_style import set_app_style
    from utils.helper_funcs import read_json

    app = QApplication(sys.argv)
    set_app_style(app)
    canvas = PlotCanvas(read_json(SETTINGS_FILE_PATH)["plot"])
    t = np.linspace(0.0, 2000.0, 2000)
    flux = 1.0 + np.exp(-((t - 800.0) / 120.0) ** 2)
    canvas.set_data_points(t[::40], flux[::40])
    canvas.set_flux(t, flux)
    canvas.set_w_data(t, np.tanh((t - 1000.0) / 300.0))
    canvas.set_profile_data("lambda_n", t, 0.5 * (1 + np.sin(t / 150.0)))
    canvas.show_profile("lambda_n")
    canvas.set_time_limit((0.0, 2000.0))
    canvas.set_flux_limit((0.0, 2.2))
    canvas.set_profile_y_limit((-0.1, 1.1))
    canvas.set_w_y_limit((-1.1, 1.1))
    canvas.set_time_label("t", "T_0")
    canvas.set_flux_label("I", "I_0")
    canvas.set_current_span_position(800.0, 120.0, 120.0)
    canvas.set_current_span_visible(True)
    canvas.resize(1200, 500)
    canvas.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
