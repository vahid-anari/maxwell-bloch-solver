# Maxwell Bloch Solver

> **This app is now [Maxwell Bloch Studio](https://pypi.org/project/maxwell-bloch-studio/).**
> Switch with `pipx uninstall maxwell-bloch-solver` and
> `pipx install maxwell-bloch-studio`; settings and parameter files carry over.

A PySide6 desktop application for simulating, visualizing, and fitting one-dimensional Maxwell-Bloch models to astronomical maser light-curve data. The application combines an interactive Qt interface, configurable physical and numerical parameters, Numba-accelerated time evolution, and publication-oriented plotting/export tools.

## Screenshot

<img src="https://raw.githubusercontent.com/vahid-anari/maxwell-bloch-solver/main/assets/main_window.png" width="1512" alt="Maxwell Bloch Solver main window">

## Features

- Interactive GUI for Maxwell-Bloch model configuration and visualization.
- Numba-accelerated numerical solver using Runge-Kutta time stepping, from the [maxbloch](https://github.com/vahid-anari/maxbloch) package.
- Interface built with [sciwidgets](https://github.com/vahid-anari/sciwidgets) (sliders, parameter panels, plot canvas).
- Light-curve import from velocity-tagged text files.
- Support for period-tagged source folders, e.g. multiple folded periods for the same source.
- Adjustable source, sample, initial-condition, pump-profile, and plotting parameters.
- Built-in visualization of fitted flux, inversion/population, pump terms, and other solver quantities.
- Parameter saving/loading using JSON files.
- Export to PDF, PNG, or SVG, with PDF exports including metadata and parameter reports.
- Local user guide and equations reference.

## Installation

The app needs Python 3.10 or newer. The easiest way is [pipx](https://pipx.pypa.io),
which installs the app in its own environment and puts the command on your path:

```bash
pipx install maxwell-bloch-solver
```

If you work in a conda or virtual environment, install it there with pip instead:

```bash
pip install maxwell-bloch-solver
```

## Running the application

```bash
maxwell-bloch-solver
```

(`mbsolver` is a shorter name for the same command, and `python -m mbsolver` works too.)
Use the menu bar to load data folders, adjust parameters, run the solver and export plots.

## Updating

The app tells you when a new version is available. To update:

```bash
pipx upgrade maxwell-bloch-solver
```

or `pip install -U maxwell-bloch-solver` in the environment where you installed it.

## Using the solver from Python

Parameter files saved by the app can be solved in your own scripts. Install the
app with `pip` in the Python you run the script with (a `pipx` install is kept
separate from your own Python):

```python
import mbsolver

f = mbsolver.ParamsFile("run_1.json")       # File → Save Parameters As…
params = f.params()                          # a fresh dict, safe to change
params["solve.sample"]["l"] = 1.0e13         # change anything
res = mbsolver.solve(params)                 # same numbers as the app

res["time"]             # time grid
res["intensity"][-1]    # intensity at the exit of the medium
```

For the parameter file of a data folder, `f.velocities` lists the velocity
components and `f.params(12.3)` picks one. `f.metadata` and `f.app_version`
tell who saved the file, when, and with which version.

`params` is a plain dictionary keyed by the names the app uses
(`"solve.grid.nt"`, `"solve.sample"`, `"solve.pump.pulse1"`, …). η and θ₀ are
computed from the sample values (ν, Γ, T₀, L, n₀), as in the app;
`mbsolver.scaling(nu=…, gamma=…, t0=…, l=…, n0=…)` returns them and the other
derived quantities. The result holds `time`, `intensity` and `w` (one row per
stored z plane), `lambda_n` (pump), `A0` (boundary field), `t1` and `t2`, in the
solver's dimensionless units; the app's flux scaling and offsets are not applied.

A commented example script listing all keys ships with the app: open
*Help → Use from Python…* to copy or save it, or read
[`example_script.py`](https://github.com/vahid-anari/maxwell-bloch-solver/blob/main/src/mbsolver/resources/example_script.py).
To build the parameters in code instead, use the
[maxbloch](https://github.com/vahid-anari/maxbloch) package directly.

## Input data format

The application expects light-curve files as plain text files with at least two whitespace-separated columns:

```text
time flux
```

Blank lines and lines beginning with `#` are ignored.

Supported file-name patterns are:

```text
Source_v=12.3.txt
Source_p1_v=12.3.txt
```

where:

- `Source` is the source name,
- `p1`, `p2`, etc. are optional period labels,
- `v=12.3` is the velocity-component label.

Matching parameter files can be stored as:

```text
Source_params.json
Source_p1_params.json
```

When period-tagged files are present, the application lets the user select the period set to load.

## Exporting results

Plots can be exported from the GUI as:

- PDF
- PNG
- SVG

PDF exports include the plot plus a report page containing metadata and the current parameter state.

## Documentation

The user guide and the equations reference (PDF) are installed with the app;
open them from the Help and Info menus.

## Development

```bash
git clone https://github.com/vahid-anari/maxwell-bloch-solver.git
cd maxwell-bloch-solver
pip install -e .
mbsolver
```

`python main.py` in the repository root also starts the app from the source
folder. The code lives in `src/mbsolver/`:

```text
src/mbsolver/
├── main.py           # application entry point
├── app/              # main window, plotting, solver controller, update pipeline
├── ui/               # physics parameter widgets, dialogs, splash screen, step viewer
├── io/               # data and parameter import/export
├── config/           # app metadata, style and UI defaults
├── utils/            # units, constants, helper functions
└── resources/        # settings.json, icons, user guide and equations PDFs
```

The numerical solver is the [maxbloch](https://github.com/vahid-anari/maxbloch)
package; the widgets come from [sciwidgets](https://github.com/vahid-anari/sciwidgets).

## License

This project is released under the MIT License. See [`LICENSE`](https://github.com/vahid-anari/maxwell-bloch-solver/blob/main/LICENSE) for details.
