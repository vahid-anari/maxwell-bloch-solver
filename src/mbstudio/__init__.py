"""Maxwell Bloch Studio: a desktop app for Maxwell-Bloch models of astrophysical masers.

From Python, ``mbstudio.ParamsFile`` reads a parameter file saved by the app
and ``mbstudio.solve`` runs the solver on its parameters (see :mod:`mbstudio.api`).
"""

__all__ = ["ParamsFile", "solve", "scaling"]


def __getattr__(name):
    # Imported on first use, so starting the app does not load the solver
    # (numba) before the splash screen is shown.
    if name in ("ParamsFile", "solve"):
        from mbstudio import api

        return getattr(api, name)
    if name == "scaling":
        from mbstudio.sample import scaling

        return scaling
    raise AttributeError(f"module 'mbstudio' has no attribute {name!r}")
