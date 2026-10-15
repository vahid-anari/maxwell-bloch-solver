"""Maxwell Bloch Solver: a desktop app for Maxwell-Bloch models of astrophysical masers.

From Python, ``mbsolver.ParamsFile`` reads a parameter file saved by the app
and ``mbsolver.solve`` runs the solver on its parameters (see :mod:`mbsolver.api`).
"""

__all__ = ["ParamsFile", "solve", "scaling"]


def __getattr__(name):
    # Imported on first use, so starting the app does not load the solver
    # (numba) before the splash screen is shown.
    if name in ("ParamsFile", "solve"):
        from mbsolver import api

        return getattr(api, name)
    if name == "scaling":
        from mbsolver.sample import scaling

        return scaling
    raise AttributeError(f"module 'mbsolver' has no attribute {name!r}")
