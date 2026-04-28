"""Numerical routines for the Maxwell-Bloch model used by the GUI.

This module builds simulation grids, prepares initial and boundary conditions,
and advances the coupled field and material equations.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
from numba import njit

from ui.params.cosh_function import cosh_func
from ui.splash_screen import show_splash_message

show_splash_message("Creating Maxwell-bloch solver / helper functions...")


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
@njit(inline="always", nogil=True, cache=True)
def build_grids(t_max: float, nt: int, nz: int):
    """Build the one-dimensional temporal and spatial grids used by the solver.

    Args:
        t_max: Maximum simulation time.
        nt: Number of time-grid points.
        nz: Number of spatial-grid points.

    Returns:
        Tuple ``(t, dt, z, dz)`` containing the time array, time step, spatial
        array, and spatial step.
    """

    t = np.linspace(0.0, t_max, nt)
    dt = t_max / (nt - 1)
    z = np.linspace(0.0, 1.0, nz)
    dz = 1.0 / (nz - 1)
    return t, dt, z, dz


def evaluate_cosh_profile(
    t: np.ndarray,
    params: Dict[str, Any],
) -> np.ndarray:
    """Evaluate the configured sech-squared drive profile.

    Args:
        t: Time coordinates where the profile is evaluated.
        params: Mapping containing the profile configuration expected by
            ``cosh_func``.

    Returns:
        Drive profile evaluated at the supplied times.
    """

    return cosh_func(
        symmetric=params["symmetric"],
        x=t,
        a=np.asarray(params["a"], dtype=np.float64),
        x0=np.asarray(params["x0"], dtype=np.float64),
        w=np.asarray(params["w"], dtype=np.float64),
        wl=np.asarray(params["wl"], dtype=np.float64),
        wr=np.asarray(params["wr"], dtype=np.float64),
    )


# -----------------------------------------------------------------------------
# Initial and Boundary conditions
# -----------------------------------------------------------------------------
@njit(inline="always", nogil=True, cache=True)
def compute_initial_conditions(z, w0, R0):
    """Construct the initial state arrays for the Maxwell-Bloch system.

    Args:
        z: Spatial grid array used only to determine the output size.
        w0: Initial population value.
        R0: Initial coherence value.

    Returns:
        Tuple ``(w, R)`` containing arrays filled with the requested initial
        population and coherence values.
    """

    w = np.full_like(z, w0, dtype=np.float64)
    R = np.full_like(z, R0, dtype=np.float64)
    return w, R


@njit(inline="always", nogil=True, cache=True)
def compute_boundary_conditions(t, A0):
    """Construct the boundary-driving array at the entrance of the sample.

    Args:
        t: Time grid array used only to determine the output size.
        A0: Boundary field value.

    Returns:
        Array filled with the requested boundary-driving value.
    """

    return np.full_like(t, A0, dtype=np.float64)


show_splash_message("Creating Maxwell-bloch solver /  RK4 functions...")


# -----------------------------------------------------------------------------
# Maxwell-Bloch Equations
# -----------------------------------------------------------------------------
@njit(inline="always", nogil=True, cache=True)
def _dw_dt(w, R, A, kw, kR, w0, inv_t1, lambda_n):
    """Evaluate the population derivative for one solver stage.

    Args:
        w: Current population value.
        R: Current coherence value.
        A: Current field value.
        kw: Runge-Kutta population increment.
        kR: Runge-Kutta coherence increment.
        w0: Reference initial population.
        inv_t1: Inverse longitudinal relaxation time.
        lambda_n: Pump term.

    Returns:
        Population derivative for the current stage.
    """

    return A * (R + kR) - (w + kw - w0) * inv_t1 + lambda_n


@njit(inline="always", nogil=True, cache=True)
def _dR_dt(w, R, A, kw, kR, R0, inv_t2):
    """Evaluate the coherence derivative for one solver stage.

    Args:
        w: Current population value.
        R: Current coherence value.
        A: Current field value.
        kw: Runge-Kutta population increment.
        kR: Runge-Kutta coherence increment.
        R0: Reference initial coherence.
        inv_t2: Inverse transverse relaxation time.

    Returns:
        Coherence derivative for the current stage.
    """

    return -A * (w + kw) - (R + kR - R0) * inv_t2


@njit(inline="always", nogil=True, cache=True)
def _dA_dz(eta, R, dz):
    """Evaluate the field increment along the propagation direction.

    Args:
        eta: Coupling coefficient.
        R: Current coherence value.
        dz: Spatial step size.

    Returns:
        Field increment across one spatial step.
    """

    return -eta * R * dz


@njit(inline="always", nogil=True, cache=True)
def _rk4_dn_dR(
    w,
    R,
    A,
    inv_t1,
    inv_t2,
    w0,
    R0,
    lambda_n,
    dt,
    half_dt,
    dt6,
):
    """Advance population and coherence with one fourth-order Runge-Kutta step.

    Args:
        w: Current population value.
        R: Current coherence value.
        A: Current field value.
        inv_t1: Inverse longitudinal relaxation time.
        inv_t2: Inverse transverse relaxation time.
        w0: Reference initial population.
        R0: Reference initial coherence.
        lambda_n: Pump term.
        dt: Full time step.
        half_dt: Half time step.
        dt6: One sixth of the time step.

    Returns:
        Tuple ``(dw, dR)`` containing the Runge-Kutta increments for population
        and coherence.
    """

    kw_1 = _dw_dt(w, R, A, 0, 0, w0, inv_t1, lambda_n)
    kR_1 = _dR_dt(w, R, A, 0, 0, R0, inv_t2)

    kw_2 = _dw_dt(w, R, A, half_dt * kw_1, half_dt * kR_1, w0, inv_t1, lambda_n)
    kR_2 = _dR_dt(w, R, A, half_dt * kw_1, half_dt * kR_1, R0, inv_t2)

    kw_3 = _dw_dt(w, R, A, half_dt * kw_2, half_dt * kR_2, w0, inv_t1, lambda_n)
    kR_3 = _dR_dt(w, R, A, half_dt * kw_2, half_dt * kR_2, R0, inv_t2)

    kw_4 = _dw_dt(w, R, A, dt * kw_3, dt * kR_3, w0, inv_t1, lambda_n)
    kR_4 = _dR_dt(w, R, A, dt * kw_3, dt * kR_3, R0, inv_t2)

    dw = dt6 * (kw_1 + 2.0 * kw_2 + 2.0 * kw_3 + kw_4)
    dR = dt6 * (kR_1 + 2.0 * kR_2 + 2.0 * kR_3 + kR_4)

    return dw, dR


# -----------------------------------------------------------------------------
# Runge-Kutta PDE Solver
# -----------------------------------------------------------------------------
@njit(nogil=True, cache=True)
def _runge_kutta_solver(
    t,
    dt,
    z,
    dz,
    n_z_planes,
    w0,
    R0,
    A0,
    lambda_n,
    t1,
    t2,
    eta,
):
    """Advance the coupled Maxwell-Bloch system across the simulation grid.

    Args:
        t: Time grid.
        dt: Time step size.
        z: Spatial grid.
        dz: Spatial step size.
        n_z_planes: Number of spatial planes to store in the output.
        w0: Initial population profile along ``z``.
        R0: Initial coherence profile along ``z``.
        A0: Boundary-driving field as a function of time.
        lambda_n: Pump profile as a function of time.
        t1: Longitudinal relaxation time.
        t2: Transverse relaxation time.
        eta: Coupling coefficient.

    Returns:
        Tuple ``(w_result, I_result)`` containing sampled population values and
        field intensities on the requested spatial planes.
    """

    nt = len(t)
    nz = len(z)
    z_planes = np.linspace(0.0, 1.0, n_z_planes)
    z_plane_indices = np.rint(z_planes * (nz - 1)).astype(np.int64)

    inv_t1 = 1.0 / t1
    inv_t2 = 1.0 / t2
    half_dt = 0.5 * dt
    dt6 = dt / 6.0

    w_old = np.empty(nt, dtype=np.float64)
    R_old = np.empty(nt, dtype=np.float64)
    A_old = np.empty(nt, dtype=np.float64)

    w_new = np.empty_like(w_old)
    R_new = np.empty_like(R_old)
    A_new = np.empty_like(A_old)

    w_result = np.empty((n_z_planes, nt), dtype=np.float64)
    I_result = np.empty((n_z_planes, nt), dtype=np.float64)

    w_old[0], R_old[0] = w0[0], R0[0]
    A_old[0] = A0[0]
    n0_0 = w0[0]
    R0_0 = R0[0]

    for t_idx in range(1, nt):
        dw, dR = _rk4_dn_dR(
            w_old[t_idx - 1],
            R_old[t_idx - 1],
            A_old[t_idx - 1],
            inv_t1,
            inv_t2,
            n0_0,
            R0_0,
            lambda_n[t_idx - 1],
            dt,
            half_dt,
            dt6,
        )
        w_old[t_idx] = w_old[t_idx - 1] + dw
        R_old[t_idx] = R_old[t_idx - 1] + dR
        A_old[t_idx] = A0[t_idx]

    w_result[0, :] = w_old
    I_result[0, :] = A_old.real * A_old.real + A_old.imag * A_old.imag
    i = 1

    for z_idx in range(1, nz):
        w_new[0], R_new[0] = w0[z_idx], R0[z_idx]
        A_new[0] = A_old[0] + _dA_dz(eta, R_old[0], dz)
        n0_i = w0[z_idx]
        R0_i = R0[z_idx]

        for t_idx in range(1, nt):
            dw, dR = _rk4_dn_dR(
                w_new[t_idx - 1],
                R_new[t_idx - 1],
                A_new[t_idx - 1],
                inv_t1,
                inv_t2,
                n0_i,
                R0_i,
                lambda_n[t_idx - 1],
                dt,
                half_dt,
                dt6,
            )
            w_new[t_idx] = w_new[t_idx - 1] + dw
            R_new[t_idx] = R_new[t_idx - 1] + dR
            A_new[t_idx] = A_old[t_idx] + _dA_dz(eta, R_old[t_idx], dz)

        if i < n_z_planes and z_plane_indices[i] == z_idx:
            w_result[i, :] = w_new
            I_result[i, :] = A_new.real * A_new.real + A_new.imag * A_new.imag
            i += 1

        w_old, w_new = w_new, w_old
        R_old, R_new = R_new, R_old
        A_old, A_new = A_new, A_old

    return w_result, I_result


show_splash_message("Creating Maxwell-bloch solver / main function...")


# -----------------------------------------------------------------------------
# MBE Solver Interface
# -----------------------------------------------------------------------------
def solve_maxwell_bloch(params):
    """Solve the configured Maxwell-Bloch problem and return sampled outputs.

    Args:
        params: Parameter mapping containing grid, sample, pump, initial
            condition, boundary condition, and slicing settings.

    Returns:
        Mapping containing time samples, intensity samples, population samples,
        pump profile, and boundary-driving field.
    """

    t, dt, z, dz = build_grids(
        nt=params["solve.grid.nt"],
        nz=params["solve.grid.nz"],
        t_max=params["solve.grid.t_max"],
    )
    lambda_n = evaluate_cosh_profile(t, params["solve.pump.cosh1"]) + evaluate_cosh_profile(
        t, params["solve.pump.cosh2"]
    )
    if params["solve.ics"]["use_theta0"]:
        theta0 = params["solve.sample"]["theta0"]
        w0, R0 = compute_initial_conditions(z, w0=np.cos(theta0), R0=np.sin(theta0))
    else:
        w0, R0 = compute_initial_conditions(z, w0=params["solve.ics"]["w0"], R0=params["solve.ics"]["R0"])

    A0 = evaluate_cosh_profile(t, params["solve.bcs"])
    w, I = _runge_kutta_solver(
        t=t,
        dt=dt,
        z=z,
        dz=dz,
        n_z_planes=params["slice.z"]["arr_length"],
        w0=w0,
        R0=R0,
        A0=A0,
        lambda_n=lambda_n,
        t1=params["solve.dynamics.t1"],
        t2=params["solve.dynamics.t2"],
        eta=params["solve.sample"]["eta"],
    )

    return {
        "time": t,
        "intensity": I,
        "w": w,
        "lambda_n": lambda_n,
        "A0": A0,
    }
