"""Interactive widget for visualizing the solver evaluation order step by step."""

from __future__ import annotations

import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as patches
from pygments.styles import native

from settings.app_style import USE_LATEX


class _StopAtStep(Exception):
    """Internal exception used to stop evaluation at a requested step."""

    pass


def eval_points(steps: int, Nt: int, Nz: int):
    """Return active solver points and status for a requested step count.

    Args:
        steps: Number of solver-update steps to evaluate.
        Nt: Number of time-grid points.
        Nz: Number of spatial-grid points.

    Returns:
        Tuple ``(n, E, status)`` where ``n`` and ``E`` are integer arrays marking
        active points and ``status`` describes the most recent evaluation state.
    """

    n = np.zeros((Nt, Nz), dtype=np.int32)
    E = np.zeros((Nt, Nz), dtype=np.int32)

    counter = 0
    status = [None] * 5

    if steps <= 0:
        return n, E, status

    def bump():
        """Advance the internal step counter and stop at the requested step."""
        nonlocal counter
        counter += 1
        if counter == steps:
            raise _StopAtStep

    try:
        status = [0, 0, "ics", "bcs", None]
        n[0, 0] = 1
        E[0, 0] = 1
        bump()

        for t_idx in range(1, Nt):
            n[t_idx, 0] = 1
            E[t_idx, 0] = 1
            status = [0, t_idx, "eval", "bcs", None]
            bump()

        status = [0, None, None, None, "store"]
        bump()

        for z_idx in range(1, Nz):
            n[0, z_idx] = 1
            E[0, z_idx] = 1
            status = [z_idx, 0, "ics", "eval", None]
            bump()

            for t_idx in range(1, Nt):
                n[t_idx, z_idx] = 1
                E[t_idx, z_idx] = 1
                status = [z_idx, t_idx, "eval", "eval", None]
                bump()

            status = [z_idx, None, None, None, "store"]
            bump()

    except _StopAtStep:
        return n, E, status

    return n, E, [None] * 5


class StepScatterWidget(QWidget):
    """Interactive scatter-based viewer for stepping through solver updates."""

    def __init__(self, Nt: int = 6, Nz: int = 6, steps0: int = 1, parent=None):
        """Initialize the viewer geometry, figure canvas, and keyboard controls.

        Args:
            Nt: Number of time-grid points displayed by the viewer.
            Nz: Number of spatial-grid points displayed by the viewer.
            steps0: Initial step number shown when the widget opens.
            parent: Optional parent widget.
        """

        super().__init__(parent)

        self.Nt = int(Nt)
        self.Nz = int(Nz)
        self.max_steps = self.Nz * (self.Nt + 1)
        self.steps = int(np.clip(steps0, 1, self.max_steps))

        self.setWindowTitle("Solver Step Viewer")
        self.resize(900, 700)

        self.figure = Figure(figsize=(9, 7))
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setFocusPolicy(Qt.StrongFocus)
        self.canvas.setFocus()

        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas)

        self._build_figure()
        self._refresh()

        self.canvas.mpl_connect("key_press_event", self.on_mpl_key)

    def _build_figure(self) -> None:
        """Create the figure, table, annotations, and scatter artists."""

        use_tex = USE_LATEX
        self.figure.clear()

        if use_tex:
            import matplotlib as mpl
            mpl.rcParams["text.usetex"] = True
        import matplotlib as mpl
        mpl.rcParams["font.family"] = "serif"

        gs = self.figure.add_gridspec(2, 1, height_ratios=[1, 5], hspace=0.03)
        ax_t = self.figure.add_subplot(gs[0])
        ax = self.figure.add_subplot(gs[1])

        self.figure.subplots_adjust(left=0.1, right=0.87, top=0.98, bottom=0.15)

        ax_t.axis("off")
        self.table = ax_t.table(
            cellText=[["1", "1", "use ICs", "eval", ""]],
            colLabels=[r"$z$", r"$t$", r"$(w, R)$", r"$A$", "Store"],
            cellLoc="center",
            loc="center",
            colWidths=[0.07, 0.05, 0.30, 0.30, 0.28],
        )
        self.table.auto_set_font_size(False)
        self.table.set_fontsize(14)
        self.table.scale(1.0, 2.0)

        ax.set_xlabel("$z$", fontsize=16)
        ax.set_ylabel("$t$", fontsize=16, rotation=0, labelpad=10)
        ax.set_xlim(-1.0 / (self.Nz - 1.0), 1.0 + 1.0 / (self.Nz - 1.0))
        ax.set_ylim(-1, self.Nt)

        ticks = [i / (self.Nz - 1) for i in range(self.Nz)]
        ax.set_xticks(ticks)
        ax.set_xticklabels([str(v) for v in ticks])
        ax.grid(True, alpha=0.25)

        width = 0.5 / (self.Nz - 1)
        height = self.Nt - 1 + 0.4

        ax.add_patch(
            patches.Rectangle(
                (-width / 2, -0.2), width, height,
                facecolor="blue", alpha=0.1
            )
        )
        ax.add_patch(
            patches.Rectangle(
                (-width / 2, -0.2), 1.0 + width, 0.4,
                facecolor="red", alpha=0.1
            )
        )

        self.figure.text(
            0.5, 0.03,
            "Press ←/→ to step | Shift+←/→ to jump 10 | Home/End to go to start/end",
            fontsize=13,
            family="Times New Roman",
            ha="center",
            va="bottom",
        )

        ax.text(
            0.5, -0.5, "Initial conditions",
            fontsize=14, family="Times New Roman",
            ha="center", va="center", color="red"
        )
        ax.text(
            0.0, self.Nt - 0.6, "BCs z=0",
            fontsize=14, family="Times New Roman",
            ha="center", va="center", color="blue"
        )

        self.ax = ax
        self.sc_E = ax.scatter([], [], s=55, marker="D", label="$E$")
        self.sc_n = ax.scatter([], [], s=55, marker="D", label="$n, R$")

        ax.legend(
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            borderaxespad=0.0,
            frameon=True,
        )

    def _computed_offsets(self, A: np.ndarray, dx: float = 0.0, dy: float = 0.0) -> np.ndarray:
        """Convert nonzero grid cells into scatter-plot coordinates.

        Args:
            A: Integer grid marking active points.
            dx: Horizontal offset added before normalization.
            dy: Vertical offset added after converting indices to coordinates.

        Returns:
            Array of ``(x, y)`` scatter coordinates.
        """

        ij = np.argwhere(A != 0)
        if ij.size == 0:
            return np.empty((0, 2), dtype=float)

        xy = ij.astype(float)
        xy = xy[:, [1, 0]]
        xy[:, 0] += dx
        xy[:, 0] /= (self.Nz - 1.0)
        xy[:, 1] += dy
        return xy

    def _refresh(self) -> None:
        """Recompute the active points for the current step and redraw the view."""

        n, E, status = eval_points(self.steps, self.Nt, self.Nz)

        self.sc_n.set_offsets(self._computed_offsets(n, dy=-0.1))
        self.sc_E.set_offsets(self._computed_offsets(E, dy=0.1))

        z, t, nR, e_state, store = status
        table = self.table

        table[(1, 0)].get_text().set_text("" if z is None else f"{z / (self.Nz - 1.0):.1f}")
        table[(1, 1)].get_text().set_text("" if t is None else str(t))

        if nR is None:
            table[(1, 2)].get_text().set_text("")
        elif nR == "ics":
            table[(1, 2)].get_text().set_text("Use ICs")
        else:
            table[(1, 2)].get_text().set_text("Eval. from prev. t")

        if e_state is None:
            table[(1, 3)].get_text().set_text("")
        elif e_state == "bcs":
            table[(1, 3)].get_text().set_text("Use BCs")
        else:
            table[(1, 3)].get_text().set_text("Eval. from prev. z")

        table[(1, 4)].get_text().set_text("" if store is None else "If z in z_slice")

        self.canvas.draw_idle()

    def on_mpl_key(self, event) -> None:
        """Handle keyboard navigation through the solve order.

        Args:
            event: Matplotlib key-press event.
        """

        key = event.key or ""
        delta = 10 if key.startswith("shift+") else 1

        if key in ("right", "shift+right"):
            self.steps = min(self.max_steps, self.steps + delta)
        elif key in ("left", "shift+left"):
            self.steps = max(1, self.steps - delta)
        elif key == "home":
            self.steps = 1
        elif key == "end":
            self.steps = self.max_steps
        else:
            return

        self._refresh()


def _demo_main() -> int:
    """Run the step viewer in a small standalone demo application.

    Returns:
        Qt application exit code.
    """

    import sys
    from ui.menu_bar_controller import MenuBarController
    from settings.app_style import set_app_style

    class MainWindow(QMainWindow):
        """Demo main window that opens the solver step viewer from a menu action."""

        def __init__(self):
            """Initialize the demo window and install its minimal menu bar."""

            super().__init__()
            self.setWindowTitle("Main App")
            self.resize(1000, 700)

            self._step_viewer_window = None

            self._menu_bar = MenuBarController(
                self,
                menu_spec={"Info": [
                    {"id": "open_solver_step_viewer", "text": "Open Step Viewer", "shortcut": "Ctrl+Alt+V"}]},
                native_menubar=False
            )
            self._menu_bar.actionTriggered.connect(self._on_menu_action_triggered)

        def _on_menu_action_triggered(self, _menu_id: str, action_id: str, checked: bool) -> None:
            """Open or raise the shared step-viewer window for the demo.

            Args:
                _menu_id: Identifier of the menu that triggered the action.
                action_id: Identifier of the selected action.
                checked: Checked state associated with the action.
            """

            if self._step_viewer_window is None:
                self._step_viewer_window = StepScatterWidget(Nt=6, Nz=6, steps0=1)
                self._step_viewer_window.setAttribute(Qt.WA_DeleteOnClose, True)
                self._step_viewer_window.destroyed.connect(self._clear_step_viewer_ref)

            self._step_viewer_window.show()
            self._step_viewer_window.raise_()
            self._step_viewer_window.activateWindow()
            self._step_viewer_window.canvas.setFocus()

        def _clear_step_viewer_ref(self, *args) -> None:
            """Clear the cached step-viewer reference after the window closes.

            Args:
                *args: Unused signal arguments supplied by Qt.
            """

            self._step_viewer_window = None

    app = QApplication(sys.argv)
    set_app_style(app)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
