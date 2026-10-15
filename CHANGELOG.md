# Changelog

What changed in each version of Maxwell Bloch Studio, newest first. At each
release, the section of that version is also copied into the GitHub Release,
where the app's update notice reads it.

## 10.0.3 — unreleased
- The update notice now lists what is new in the newer versions.

## 10.0.2 — 2026-10-15
- New app icon: a superradiant burst computed with the solver.
- User Guide: screenshots of the main window, the plot menu, fit mode and the
  *Use from Python* dialog.
- Uses sciwidgets 0.6.

## 10.0.1 — 2026-10-15
- New splash screen with the app name and version.
- User Guide and equations reference: new title pages; their sources are now
  part of the repository (`docs/`).

## 10.0.0 — 2026-10-14
- New name: **Maxwell Bloch Studio** (was Maxwell Bloch Solver). Install with
  `pipx install maxwell-bloch-studio`; start with `mbstudio` or
  `maxwell-bloch-studio`. Your settings carry over.
- The numerical solver is now the separate package `mbsolver`.
- Scripts use `import mbstudio` (`mbstudio.ParamsFile`, `mbstudio.solve`,
  `mbstudio.scaling`).

Earlier versions were released as Maxwell Bloch Solver
(`maxwell-bloch-solver` on PyPI, up to 9.2.0).
