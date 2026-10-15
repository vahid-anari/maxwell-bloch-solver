"""Draw the app icon: one superradiant burst computed with mbsolver.

Run from the repository root: python tools/make_icon.py
Writes src/mbstudio/resources/icons/app_icon.png (1024 x 1024, transparent
corners, macOS icon grid). Same burst and colours as tools/make_splash.py.
"""
import math

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from mbsolver.two_level import solve_1d

OUT = "src/mbstudio/resources/icons/app_icon.png"
S = 1024                      # canvas
SIDE = 824                    # icon body (macOS grid)
OFF = (S - SIDE) // 2
R = int(0.2237 * SIDE)        # corner radius

res = solve_1d(t_max=4.2, nt=8400, nz=400, eta=20, theta0=1e-4, t1=math.inf, t2=math.inf, n_planes=6)
t = res.time
I = res.intensity[5]          # exit of the medium
sel = t <= 3.2
x = 0.10 + 0.80 * (t[sel] - t[0]) / (3.2 - t[0])
y = 0.24 + 0.58 * I[sel] / I.max()


def background():
    """Navy (bottom-left) to soft blue (top-right), as in the splash."""
    yy, xx = np.mgrid[0:1:SIDE * 1j, 0:1:SIDE * 1j]
    g = (0.55 * xx + 0.45 * (1 - yy))[..., None]
    c0, c1, c2 = np.array([6, 23, 58]), np.array([23, 74, 135]), np.array([91, 143, 201])
    col = np.where(g < 0.5, c0 + (c1 - c0) * (g / 0.5), c1 + (c2 - c1) * ((g - 0.5) / 0.5))
    return Image.fromarray(col.astype(np.uint8), "RGB").convert("RGBA")


def curve(lw_px, color, blur=0, alpha=1.0):
    """The burst drawn as one line, optionally blurred into a glow."""
    fig = plt.figure(figsize=(SIDE / 100, SIDE / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    fig.patch.set_alpha(0)
    ax.plot(x, y, color=color, lw=lw_px * 72 / 100, solid_capstyle="round", solid_joinstyle="round")
    fig.canvas.draw()
    im = Image.frombuffer("RGBA", fig.canvas.get_width_height(), fig.canvas.buffer_rgba()).copy()
    plt.close(fig)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    if alpha < 1:
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    return im


def overlay(alpha_mask, rgb):
    layer = Image.new("RGBA", (SIDE, SIDE), rgb + (0,))
    layer.putalpha(alpha_mask)
    return layer


img = background()
for lw, color, blur, a in ((70, "#7fc4ff", 40, 0.55), (36, "#a9d8ff", 16, 0.8), (22, "#d9efff", 5, 1.0)):
    img = Image.alpha_composite(img, curve(lw, color, blur, a))
img = Image.alpha_composite(img, curve(14, "white"))

# soft glossy light at the top
hl = Image.new("L", (SIDE, SIDE), 0)
ImageDraw.Draw(hl).ellipse((-SIDE * 0.3, -SIDE * 0.9, SIDE * 1.3, SIDE * 0.38), fill=34)
img = Image.alpha_composite(img, overlay(hl.filter(ImageFilter.GaussianBlur(90)), (255, 255, 255)))

# rim: light along the top edge, darker along the bottom
mask = Image.new("L", (SIDE, SIDE), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIDE - 1, SIDE - 1), R, fill=255)
rim = np.array(ImageChops.subtract(mask, mask.filter(ImageFilter.GaussianBlur(10))), dtype=float)
up = np.linspace(1, 0, SIDE)[:, None]
img = Image.alpha_composite(img, overlay(Image.fromarray((rim * up * 0.9).astype(np.uint8)), (255, 255, 255)))
img = Image.alpha_composite(img, overlay(Image.fromarray((rim * (1 - up) * 0.8).astype(np.uint8)), (0, 10, 30)))

# shadow under the icon, then the icon itself
out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
sh = Image.new("L", (S, S), 0)
ImageDraw.Draw(sh).rounded_rectangle((OFF, OFF + 12, OFF + SIDE, OFF + SIDE + 12), R, fill=90)
shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
shadow.putalpha(sh.filter(ImageFilter.GaussianBlur(18)))
out = Image.alpha_composite(out, shadow)
out.paste(img, (OFF, OFF), mask)
out.save(OUT)
print("Wrote", OUT)
