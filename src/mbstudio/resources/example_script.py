"""Solve a parameter file saved by Maxwell Bloch Studio, without the window.

Needs the app installed with pip in the Python you run this with:
    pip install maxwell-bloch-studio
"""

import matplotlib.pyplot as plt

import mbstudio

# 1. Open a file saved by the app (File → Save Parameters As…).
f = mbstudio.ParamsFile("my_params.json")
print(f)                      # file name, plain or data folder, app version
print(f.metadata)             # saved_at, saved_by, source, ...

# For the parameter file of a data folder, list the velocities and pick one:
#   f.velocities              -> ['-5.0', '12.3', ...]
#   params = f.params(12.3)
params = f.params()           # a fresh dict each time, safe to change

# 2. The parameters. Keys the solver uses (times are in units of T0):
#   "solve.grid.t_max"   duration
#   "solve.grid.nt"      number of time points
#   "solve.grid.nz"      number of z points
#   "solve.sample"       {"nu": Hz, "gamma": 1/s, "t0": s, "l": m, "n0": 1/m^3}
#                        eta and theta0 are computed from these, as in the app
#   "solve.ics"          {"use_theta0": True/False, "w0": ..., "R0": ...}
#   "solve.pump.pulse1", "solve.pump.pulse2", "solve.pump.pulse3", "solve.bcs":
#                        sech^2 pulses {"symmetric": True/False, "a": [...], "x0": [...],
#                        "w": [...], "wl": [...], "wr": [...]}, one list entry per pulse
#   "solve.t1", "solve.t2"
#                        a number, or steps {"symmetric", "y", "x0", "w", "wl", "wr"}
#                        (the first entry of x0 and of the widths is not used)
#   "slice.z"            {"arr_length": number of stored z planes, ...}
# Other keys (display.*, data.*, results.*) belong to the window and are not used.

params["solve.t1"] = 30.0
params["solve.sample"]["l"] = 1.0e13

derived = mbstudio.scaling(**{k: params["solve.sample"][k] for k in ("nu", "gamma", "t0", "l", "n0")})
print(f"eta = {derived['eta']:.4g}, theta0 = {derived['theta0']:.4g}")

# 3. Solve. The results are numpy arrays in the solver's dimensionless units:
#   "time"        (nt,)
#   "intensity"   (planes, nt)   row 0 = entrance (z = 0), row -1 = exit (z = 1)
#   "w"           (planes, nt)   population inversion
#   "lambda_n"    (nt,)          total pump
#   "A0"          (nt,)          field entering at z = 0
#   "t1", "t2"    (nt,)          relaxation times on the time grid
res = mbstudio.solve(params)
for key, value in res.items():
    print(f"{key:10s} {value.shape}")

plt.plot(res["time"], res["intensity"][-1])
plt.xlabel("time / T0")
plt.ylabel("exit intensity")
plt.show()
