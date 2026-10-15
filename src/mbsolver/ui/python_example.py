"""Dialog showing the example script for using the solver from Python."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mbsolver.paths import EXAMPLE_SCRIPT_PATH
from mbsolver.ui.dialogs import show_critical


class PythonExampleDialog(QDialog):
    """Show the example script with syntax colours, and copy or save it."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Use from Python")
        self.resize(820, 680)

        self._code = EXAMPLE_SCRIPT_PATH.read_text(encoding="utf-8")

        intro = QLabel(
            "Parameter files saved by the app can be solved in your own scripts. "
            "Install the app with <code>pip install maxwell-bloch-solver</code> in the "
            "Python you use, then start from this example."
        )
        intro.setWordWrap(True)

        browser = QTextBrowser(self)
        browser.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        browser.setHtml(highlight(self._code, PythonLexer(), HtmlFormatter(noclasses=True, nobackground=True)))
        browser.setLineWrapMode(QTextBrowser.NoWrap)

        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self._copy)
        save_btn = QPushButton("Save As…")
        save_btn.clicked.connect(self._save)
        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(copy_btn)
        buttons.addWidget(save_btn)
        buttons.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(browser, 1)
        layout.addLayout(buttons)

    def _copy(self) -> None:
        """Copy the script to the clipboard."""
        QGuiApplication.clipboard().setText(self._code)

    def _save(self) -> None:
        """Save the script as a .py file chosen by the user."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Example Script", "mbsolver_example.py", "Python files (*.py)"
        )
        if not path:
            return
        try:
            Path(path).write_text(self._code, encoding="utf-8")
        except OSError as e:
            show_critical("Save Failed", str(e), parent=self)


def _demo_main() -> int:
    """Show the dialog on its own: ``python -m mbsolver.ui.python_example``."""
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    PythonExampleDialog().exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(_demo_main())
