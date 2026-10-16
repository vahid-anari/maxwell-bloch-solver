# Changelog

What changed in each version of Maxwell Bloch Studio, newest first. At each
release, the section of that version is also copied into the GitHub Release,
where the app's update notice reads it.

## 10.4.0 — 2026-10-16
- The launcher made by `mbstudio install-app` now updates itself: after an update, the
  app refreshes it on its next start (icon and version shown in Finder), so you never
  need to run `mbstudio install-app` again for that.

## 10.3.0 — 2026-10-16
- *Update Now* in the update notice: the app installs the new version itself (no terminal
  needed), shows the progress, and then offers to restart. If the update cannot finish, it
  says how to do it by hand.

## 10.2.0 — 2026-10-16
- Start the app with a double-click: `mbstudio install-app` adds Maxwell Bloch Studio to
  your Applications folder (macOS; also Launchpad, Spotlight and the Dock), the Start menu
  (Windows) or the applications menu (Linux). It keeps working after `mbstudio update`;
  `mbstudio install-app --remove` takes it away. The Windows shortcut is new and not yet
  tried on many machines; please report problems.

## 10.1.1 — 2026-10-16
- The curve and grid style dialogs now show each change on the plot at once, like the
  span dialog; *Cancel* puts the old style back.
- Uses sciwidgets 0.8.1.

## 10.1.0 — 2026-10-16
- The current span can be restyled: right-click the plot → *Current span style…* sets
  the shaded area's fill colour and opacity and its edge colour, opacity, width and line,
  and the centre line's colour, opacity, width and line. Saved between sessions;
  *View → Reset Plot Style* resets it.
- Uses sciwidgets 0.8.

## 10.0.8 — 2026-10-15
- New terminal commands: `mbstudio --version`, `mbstudio update`, `mbstudio solve FILE`
  (without the window, e.g. on a cluster), `mbstudio example`, and `mbstudio PATH` to open
  a parameter file or data folder at start. See `mbstudio --help` and the User Guide.

## 10.0.7 — 2026-10-15
- The splash screen now comes from sciwidgets 0.7 (looks the same).

## 10.0.6 — 2026-10-15
- No changes for users (version number only).

## 10.0.5 — 2026-10-15
- User Guide: new main-window screenshot.
- Tests for the Python script API and the update notice.

## 10.0.4 — 2026-10-15
- `mbstudio.scaling` now comes from the solver package (`mbsolver.scaling`,
  mbsolver 0.3); same results. Scripts that use only `mbsolver` can now get
  η and θ₀ from the physical sample values too.

## 10.0.3 — 2026-10-15
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
