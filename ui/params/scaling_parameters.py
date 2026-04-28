"""Read-only scaling-parameter display widgets for derived quantities."""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from settings.app_style import SCALING_PARAMS_MAP_GROUP_ID_TO_LABEL, USE_LATEX
from settings.ui_defaults import SCALING_PARAM_DIGIT, SCALING_PARAM_SIZE
from ui.labels import SvgLabel
from utils.constants_si import C, EPSILON_0, H_BAR, MU_0, PI
from utils.helper_funcs import make_box, pretty_sci_text


class ScalingParameter:
    """Display helper representing one derived scaling quantity."""

    def __init__(
        self,
        label: str,
        unit: str = "",
        unit_to_si_factor: float = 1.0,
        formula: Optional[str] = None,
        has_value: bool = True,
        sig_digits: int = SCALING_PARAM_DIGIT,
    ) -> None:
        """Initialize one scaling-parameter display entry.

        Args:
            label: Symbol or label shown for the parameter.
            unit: Unit label shown beside the parameter value.
            unit_to_si_factor: Conversion factor from the displayed unit to SI.
            formula: Optional LaTeX or text formula shown for the parameter.
            has_value: Whether the current numeric value should be displayed.
            sig_digits: Number of significant digits used when formatting the
                numeric value.
        """

        self._label = label
        self._unit = unit
        self._unit_factor = unit_to_si_factor
        self._formula = formula
        self._has_value = has_value
        self._sig_digits = sig_digits
        self._value = 1.0

    # ----- public API -----
    def add_row_to_gl(self, row: int, gl: QGridLayout) -> None:
        """Add this parameter's widgets to a grid layout row.

        Args:
            row: Target row index in the grid layout.
            gl: Grid layout that will receive the label, formula, and unit
                widgets.
        """

        label = SvgLabel(
            text=self._label,
            alignment=Qt.AlignRight | Qt.AlignVCenter,
            fix_size=True,
            font_size=SCALING_PARAM_SIZE,
        )
        gl.addWidget(label, row, 0, Qt.AlignRight | Qt.AlignVCenter)

        rhs_text = ""
        if self._formula:
            rhs_text += f"={self._formula}"
        if self._has_value:
            rhs_text += f"={pretty_sci_text(self._value, sig_digits=self._sig_digits, notation='latex')}"

        rhs = SvgLabel(
            text=rhs_text,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            fix_size=True,
            font_size=SCALING_PARAM_SIZE,
        )
        gl.addWidget(rhs, row, 1)

        if self._unit:
            unit = SvgLabel(
                text=f"({self._unit})",
                alignment=Qt.AlignRight | Qt.AlignVCenter,
                fix_size=True,
                font_size=SCALING_PARAM_SIZE,
            )
            gl.addWidget(unit, row, 2, Qt.AlignRight | Qt.AlignVCenter)

    def get_value(self) -> float:
        """Return the current parameter value in SI units.

        Returns:
            Parameter value converted to SI units.
        """

        return self._value * self._unit_factor

    def set_value(self, value: float) -> None:
        """Set the current parameter value from an SI quantity.

        Args:
            value: Parameter value expressed in SI units.
        """

        self._value = value / self._unit_factor


class ScalingParameters:
    """Container for derived scaling quantities and their displayed formulas."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the scaling-parameter container.

        Args:
            parent: Optional parent widget used for the formulas dialog.
        """

        self._parent = parent
        self._eta = 1.0
        self._theta0 = 1.0
        display = r"\displaystyle " if USE_LATEX else ""
        self._params = {
            "input": {
                "nu": ScalingParameter(
                    label=r"\nu",
                    unit=r"\mathrm{MHz}",
                    unit_to_si_factor=1.0e6,
                    sig_digits=9,
                ),
                "gamma": ScalingParameter(
                    label=r"\Gamma",
                    unit=r"\mathrm{s}^{-1}",
                ),
                "n0": ScalingParameter(
                    label=r"n_0",
                    unit=r"\mathrm{m}^{-3}",
                ),
                "l": ScalingParameter(
                    label=r"L",
                    unit=r"\mathrm{m}",
                ),
                "t0": ScalingParameter(
                    label=r"T_0",
                    unit=r"\mathrm{s}",
                ),
            },
            "shared": {
                "omega": ScalingParameter(
                    label=r"\omega",
                    unit=r"\mathrm{s}^{-1}",
                    formula=r"2 \pi \nu",
                ),
                "lambda": ScalingParameter(
                    label=r"\lambda",
                    unit=r"\mathrm{m}",
                    formula=f"{display}" + r"\frac{c}{\nu}",
                ),
                "k": ScalingParameter(
                    label=r"k",
                    unit=r"\mathrm{m}^{-1}",
                    formula=f"{display}" + r"\frac{2 \pi}{\lambda}",
                ),
                "t_r": ScalingParameter(
                    label=r"T_R",
                    unit=r"\mathrm{s}",
                    formula=f"{display}" + r"\frac{2 k^2}{3 \pi \Gamma n_0 L}",
                ),
                "eta": ScalingParameter(
                    label=r"\eta",
                    formula=f"{display}" + r"\frac{T_0}{T_R}",
                ),
                "N": ScalingParameter(
                    label=r"N",
                    formula=f"{display}" + r"n_0 \lambda L^2",
                ),
                "theta0": ScalingParameter(
                    label=r"\theta_0",
                    formula=f"{display}" + r"\frac{2}{\sqrt{N}}",
                ),
                "lambda0": ScalingParameter(
                    label=r"\Lambda_0",
                    unit=r"\mathrm{s^{-1}}",
                    formula=f"{display}" + r"\frac{1}{T_0}",
                ),
            },
            "electric": {
                "d": ScalingParameter(
                    label=r"|d|",
                    unit=r"\mathrm{C\,m}",
                    formula=f"{display}" + r"\sqrt{\frac{3 \pi \epsilon_0 \hbar \Gamma}{k^3}}",
                ),
                "a0": ScalingParameter(
                    label=r"A_0",
                    has_value=False,
                    formula=f"{display}" + r"-i\frac{\hbar}{d T_0}",
                ),
                "e0": ScalingParameter(
                    label=r"E_0",
                    unit=r"\mathrm{V\,m^{-1}}",
                    formula=f"{display}" + r"\frac{\hbar}{|d| T_0}",
                ),
                "p0": ScalingParameter(
                    label=r"P_0",
                    unit=r"\mathrm{C\,m^{-2}}",
                    formula=f"{display}" + r"n_0 |d|",
                ),
                "i0": ScalingParameter(
                    label=r"I_0",
                    unit=r"\mathrm{W\,m^{-2}}",
                    formula=f"{display}" + r"\frac{1}{2} \epsilon_0 c E_0^2",
                ),
            },
            "magnetic": {
                "mu": ScalingParameter(
                    label=r"|\mu|",
                    unit=r"\mathrm{A\,m^2}",
                    formula=f"{display}" + r"\sqrt{\frac{3 \pi \hbar \Gamma}{\mu_0 k^3}}",
                ),
                "a0": ScalingParameter(
                    label=r"A_0",
                    has_value=False,
                    formula=f"{display}" + r"-i\frac{\hbar}{\mu T_0}",
                ),
                "b0": ScalingParameter(
                    label=r"B_0",
                    unit=r"\mathrm{T}",
                    formula=f"{display}" + r"\frac{\hbar}{|\mu|T_0}",
                ),
                "m0": ScalingParameter(
                    label=r"M_0",
                    unit=r"\mathrm{A\,m^{-1}}",
                    formula=f"{display}" + r"n_0 |\mu|",
                ),
                "i0": ScalingParameter(
                    label=r"I_0",
                    unit=r"\mathrm{W\,m^{2}}",
                    formula=f"{display}" + r"\frac{1}{2\mu_0} c B_0^2",
                ),
            },
        }

    # ----- public API -----
    def get_value(self) -> Dict[str, float]:
        """Return the currently derived shared scaling values.

        Returns:
            Mapping containing the current values of ``eta`` and ``theta0``.
        """

        return {
            "eta": self._eta,
            "theta0": self._theta0,
        }

    def set_values(self, gamma: float, nu: float, l: float, n0: float, t0: float) -> None:
        """Compute and store all derived scaling quantities.

        Args:
            gamma: Decay rate in SI units.
            nu: Transition frequency in SI units.
            l: Sample length in SI units.
            n0: Number density in SI units.
            t0: Characteristic time scale in SI units.
        """

        omega0 = 2 * PI * nu
        k = omega0 / C
        _lambda = C / nu
        t_r = 2.0 * k**2 / (3.0 * PI * gamma * n0 * l)
        N = n0 * _lambda * l**2
        self._eta = eta = t0 / t_r
        self._theta0 = theta0 = 2.0 / np.sqrt(N)
        lambda0 = 1.0 / t0

        input_p = self._params["input"]
        input_p["nu"].set_value(nu)
        input_p["gamma"].set_value(gamma)
        input_p["n0"].set_value(n0)
        input_p["l"].set_value(l)
        input_p["t0"].set_value(t0)

        shared_p = self._params["shared"]
        shared_p["omega"].set_value(omega0)
        shared_p["lambda"].set_value(_lambda)
        shared_p["k"].set_value(k)
        shared_p["t_r"].set_value(t_r)
        shared_p["N"].set_value(N)
        shared_p["theta0"].set_value(theta0)
        shared_p["eta"].set_value(eta)
        shared_p["lambda0"].set_value(lambda0)

        d = np.sqrt(3 * PI * EPSILON_0 * H_BAR * gamma / k**3)
        p0 = n0 * d
        e0 = H_BAR / (t0 * d)
        i0 = 0.5 * EPSILON_0 * C * e0**2

        electric_p = self._params["electric"]
        electric_p["d"].set_value(d)
        electric_p["e0"].set_value(e0)
        electric_p["p0"].set_value(p0)
        electric_p["i0"].set_value(i0)

        mu = np.sqrt(3 * PI * H_BAR * gamma / (MU_0 * k**3))
        m0 = n0 * mu
        b0 = H_BAR / (t0 * mu)
        i0 = C / (2.0 * MU_0) * b0**2

        magnetic_p = self._params["magnetic"]
        magnetic_p["mu"].set_value(mu)
        magnetic_p["b0"].set_value(b0)
        magnetic_p["m0"].set_value(m0)
        magnetic_p["i0"].set_value(i0)

    def show_formula(self) -> None:
        """Open a dialog displaying all scaling-parameter formulas."""

        dlg = QDialog(self._parent)
        dlg.setWindowTitle("Sample Parameters")

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok, parent=dlg)
        btn_box.accepted.connect(dlg.accept)

        main_layout = QVBoxLayout(dlg)
        h_l = QHBoxLayout()
        for cat_id, cat_ctx in self._params.items():
            gl = QGridLayout()
            gl.setVerticalSpacing(15)
            gl.setHorizontalSpacing(0)
            g = make_box(SCALING_PARAMS_MAP_GROUP_ID_TO_LABEL[cat_id], gl)
            for i, param in enumerate(cat_ctx.values()):
                param.add_row_to_gl(row=i, gl=gl)
            gl.setRowStretch(i + 1, 1)
            gl.setColumnStretch(2, 1)

            h_l.addWidget(g)

        main_layout.addLayout(h_l)
        main_layout.addWidget(btn_box)
        dlg.setFixedSize(dlg.sizeHint())
        dlg.exec()


def _demo_main() -> int:
    """Run this module as a standalone demo.

    Returns:
        Qt application exit code.
    """

    import sys

    from settings.app_style import set_app_style

    app = QApplication(sys.argv)
    set_app_style(app)

    win = QMainWindow()
    win.setWindowTitle("Input Parameters Demo")
    scaling_params = ScalingParameters(parent=win)

    scaling_params.set_values(
        nu=6668.519e6,
        gamma=1.56e-9,
        l=2.17e13,
        n0=1.17e-6,
        t0=111000.0,
    )

    w = QWidget()
    layout = QVBoxLayout(w)
    win.setCentralWidget(w)
    win.resize(800, 600)
    win.show()
    scaling_params.show_formula()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
