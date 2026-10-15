"""Draw the splash image: a superradiant burst computed with mbsolver.

Run from the repository root: python tools/make_splash.py
Writes src/mbstudio/resources/icons/app_image.png (2400 x 1350). The app draws
the name and version on top of it at start-up.
"""
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["mathtext.fontset"] = "cm"
from matplotlib.colors import LinearSegmentedColormap
from mbsolver.two_level import solve_1d

W, H, DPI = 2400, 1350, 200
res = solve_1d(t_max=4.2, nt=8400, nz=400, eta=20, theta0=1e-4, t1=math.inf, t2=math.inf, n_planes=6)
t = res.time; I = res.intensity

def background(ax):
    # dark navy (bottom-left) to soft blue (top-right), like the old splash
    cmap = LinearSegmentedColormap.from_list("bg", ["#06173a", "#174a87", "#5b8fc9"])
    y, x = np.mgrid[0:1:300j, 0:1:533j]
    g = 0.65 * x + 0.35 * y
    ax.imshow(g, cmap=cmap, extent=(0, 1, 0, 1), origin="lower", aspect="auto", zorder=0)

def glow(ax, x, y, color, lw, zorder):
    n = len(x)
    fade = np.ones(n); m = n // 6; m0 = n // 10
    fade[-m:] = np.linspace(1, 0, m) ** 1.5
    fade[:m0] = np.linspace(0, 1, m0) ** 1.5
    for i0 in range(0, n - 1, 40):
        i1 = min(i0 + 41, n); f = fade[i0]
        for k, a in ((9, 0.04), (6, 0.07), (3.5, 0.14), (1.8, 0.35)):
            ax.plot(x[i0:i1], y[i0:i1], color=color, lw=lw * k, alpha=a * f, solid_capstyle="butt", zorder=zorder)
        ax.plot(x[i0:i1], y[i0:i1], color="white", lw=lw * 0.8, alpha=0.95 * f, solid_capstyle="butt", zorder=zorder + 1)

def fig_ax():
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    background(ax)
    return fig, ax

def burst_curves(ax, x0, x1, y0, y1, planes=(5, 4, 3), fill=True):
    tt = x0 + (x1 - x0) * (t - t[0]) / (t[-1] - t[0])
    peak = I[planes[0]].max()
    colors = ["#9fd3ff", "#6fb3f0", "#4a8fd6"]
    for k, p in enumerate(planes[::-1]):
        yy = y0 + (y1 - y0) * I[p] / peak
        glow(ax, tt, yy, colors[len(planes) - 1 - k], 1.2 if k == len(planes) - 1 else 0.7, 3 + 2 * k)

def save(fig, name):
    fig.savefig(name, dpi=DPI); plt.close(fig)

fig, ax = fig_ax(); burst_curves(ax, 0.25, 0.97, 0.16, 0.86)
save(fig, "src/mbstudio/resources/icons/app_image2.png")
