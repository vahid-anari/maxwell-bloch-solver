"""Helpers for saving and loading parameter snapshots."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from PySide6.QtWidgets import QFileDialog, QWidget

from dialogs.dialogs import show_critical
from utils.helper_funcs import restore_special_floats


def save_params_atomic(params_text: str, path: Path) -> None:
    """Write a parameter snapshot atomically to disk.

    Args:
        params_text: Serialized parameter text to write.
        path: Destination file path.
    """

    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(params_text)
        os.replace(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass


def open_parameters(parent: QWidget) -> Optional[dict[str, Any]]:
    """Load a parameter snapshot chosen by the user.

    Args:
        parent: Parent widget for the file dialog and error dialogs.

    Returns:
        Mapping containing the selected file path and parsed parameter data, or
        ``None`` if the dialog is canceled or loading fails.
    """

    fname, _ = QFileDialog.getOpenFileName(
        parent,
        "Import Parameters",
        "",
        "Parameter files (*.json);;All files (*.*)"
    )

    if not fname:
        return

    path = Path(fname)
    try:
        with path.open("r", encoding="utf-8") as f:
            params = json.load(f)
        meta = params.get("metadata", {})
        if meta.get("fit_mode", True):
            show_critical("Import Parameters Failed", "This file is not a parameter file.", parent=parent)
            return
    except Exception as e:
        show_critical("Import Parameters Failed", str(e), parent=parent)
        return

    return {
        "path": path,
        "params": restore_special_floats(params),
    }


def save_parameters(params_text: str, path: Optional[Path], parent: QWidget) -> Optional[Path]:
    """Save parameters to the current path or request a new destination.

    Args:
        params_text: Serialized parameter text to write.
        path: Destination path, or ``None`` to prompt for one.
        parent: Parent widget for dialogs.

    Returns:
        Final saved path, or ``None`` if saving fails or is canceled.
    """

    if path is None:
        return save_parameters_as(params_text, parent)

    try:
        save_params_atomic(params_text, path)
        return path
    except Exception as e:
        show_critical("Save Parameters Failed", str(e), parent=parent)
        return None


def save_parameters_as(params_text: str, parent: QWidget) -> Optional[Path]:
    """Prompt for a destination and save parameters there.

    Args:
        params_text: Serialized parameter text to write.
        parent: Parent widget for the save dialog and any error dialogs.

    Returns:
        Final saved path, or ``None`` if the dialog is canceled or saving fails.
    """

    fname, _ = QFileDialog.getSaveFileName(
        parent,
        "Save Parameters As",
        "",
        "Parameter files (*.json);;All files (*.*)",
    )
    if not fname:
        return None
    path = Path(fname)

    s = str(path).lower()
    if not s.endswith(".json"):
        path = Path(str(path) + ".json")

    return save_parameters(params_text, path, parent)


def _demo_main() -> int:
    """Run the parameter I/O helpers as a standalone demo.

    Returns:
        Qt application exit code.
    """

    import sys

    from PySide6.QtWidgets import QApplication, QPushButton, QTextEdit, QVBoxLayout
    from settings.app_style import set_app_style

    class DemoWindow(QWidget):
        """Demo window for testing parameter import and save helpers."""

        def __init__(self) -> None:
            """Initialize the demo window and its controls."""

            super().__init__()
            self.setWindowTitle("Params I/O Test")
            self.resize(700, 500)

            self._current_path: Optional[Path] = None

            self._editor = QTextEdit(self)
            self._editor.setPlainText(
                json.dumps(
                    {
                        "metadata": {
                            "_fit_mode": False,
                        },
                        "params": {
                            "a": 1,
                            "b": 2,
                        },
                    },
                    indent=2,
                )
            )

            self._btn_import = QPushButton("Import", self)
            self._btn_save = QPushButton("Save", self)
            self._btn_save_as = QPushButton("Save As", self)

            self._btn_import.clicked.connect(self._on_import)
            self._btn_save.clicked.connect(self._on_save)
            self._btn_save_as.clicked.connect(self._on_save_as)

            layout = QVBoxLayout(self)
            layout.addWidget(self._editor)
            layout.addWidget(self._btn_import)
            layout.addWidget(self._btn_save)
            layout.addWidget(self._btn_save_as)

        def _on_import(self) -> None:
            """Handle the import action."""
            result = open_parameters(self)
            if result is None:
                return

            self._current_path = result["path"]
            self._editor.setPlainText(json.dumps(result["params"], indent=2))
            self.setWindowTitle(f"Params I/O Test - {self._current_path.name}")

        def _on_save(self) -> None:
            """Handle the save action."""
            save_parameters(self._editor.toPlainText(), self._current_path, self)

        def _on_save_as(self) -> None:
            """Handle the save-as action."""
            path = save_parameters_as(self._editor.toPlainText(), self)
            if path is not None:
                self._current_path = path
                self.setWindowTitle(f"Params I/O Test - {self._current_path.name}")

    app = QApplication(sys.argv)
    set_app_style(app)
    win = DemoWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
