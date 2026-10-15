"""Physical constants used by the solver and scaling calculations."""

import numpy as np

PI: float = np.pi
"""Circle constant in SI-compatible calculations."""

H_BAR: float = 6.62607015e-34 / (2.0 * PI)
"""Reduced Planck constant in joule-seconds."""

C: float = 2.99792458e8
"""Speed of light in meters per second."""

K_B: float = 1.380649e-23
"""Boltzmann constant in joules per kelvin."""

MU_0: float = 4.0 * PI * 1e-7
"""Vacuum permeability in henries per meter."""

EPSILON_0: float = 1.0 / (MU_0 * C ** 2)
"""Vacuum permittivity in farads per meter."""

E_CHARGE: float = 1.602176634e-19
"""Elementary charge in coulombs."""

M_ELECTRON: float = 9.1093837015e-31
"""Electron mass in kilograms."""

AU: float = 1.495978707e11
"""Astronomical unit in meters."""

SECONDS_PER_DAY: float = 86400.0
"""Number of seconds in one day."""

DEBYE: float = 1.0e-21 / C
"""Debye in coulomb-meters."""

MU_B: float = E_CHARGE * H_BAR / (2.0 * M_ELECTRON)
"""Bohr magneton in joules per tesla, equivalently ampere-square-meters."""

JY: float = 1.0e-26
"""Jansky in watts per square meter per hertz."""

GAUSS: float = 1.0e-4
"""Gauss in tesla."""
