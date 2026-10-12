"""MB Solver dialogs: period selection and data-folder summaries.

The generic dialogs (messages, questions, About/help) live in
:mod:`sciwidgets.dialogs` and are re-exported here, so existing imports such as
``from dialogs.dialogs import ask_question`` keep working.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from sciwidgets.dialogs import (  # noqa: F401  (re-exported for the app)
    AskResult,
    DialogIcon,
    TitledDialogBase,
    ask_question,
    show_about_dialog,
    show_critical,
    show_information,
    show_rich_information,
    show_warning,
)


@dataclass
class PeriodInfo:
    """Metadata for one period option shown in the selection dialog.

    Attributes:
        n_velocities: Number of velocity channels available for this period.
        has_params: Whether saved fit parameters exist for this period.
    """

    n_velocities: int
    has_params: bool


class SelectPeriodDialog(TitledDialogBase):
    """Dialog that lets the user choose one period from several candidates."""

    def __init__(
        self,
        source: str,
        periods_keys: list[str],
        periods: dict[str, PeriodInfo],
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the period-selection dialog.

        Args:
            source: Source name shown in the dialog.
            periods_keys: Ordered list of selectable period keys.
            periods: Mapping from period keys to associated metadata.
            parent: Optional parent widget.
        """

        super().__init__(
            title="Select Period",
            text=f"Source: {source}",
            informative_text="Multiple period datasets were found for this source.",
            icon=DialogIcon.QUESTION,
            parent=parent,
        )

        table_gl = QGridLayout()
        table_gl.addWidget(QLabel("Period", alignment=Qt.AlignHCenter), 0, 0, alignment=Qt.AlignCenter)
        table_gl.addWidget(
            QLabel("Num. of velocity\nchannels", alignment=Qt.AlignCenter),
            0,
            1,
            alignment=Qt.AlignCenter,
        )
        table_gl.addWidget(
            QLabel("Fit parameters\nfound", alignment=Qt.AlignCenter),
            0,
            2,
            alignment=Qt.AlignCenter,
        )
        for i, p_name in enumerate(periods_keys):
            period = periods[p_name]
            table_gl.addWidget(QLabel(p_name), i + 1, 0, alignment=Qt.AlignCenter)
            table_gl.addWidget(QLabel(str(period.n_velocities)), i + 1, 1, alignment=Qt.AlignCenter)
            table_gl.addWidget(QLabel("Yes" if period.has_params else "No"), i + 1, 2, alignment=Qt.AlignCenter)

        combo = QComboBox(self)
        combo.addItems(periods_keys)
        self._combo = combo

        combo_h_l = QHBoxLayout()
        combo_h_l.addWidget(QLabel("Select Period:"))
        combo_h_l.addWidget(combo)
        combo_h_l.addStretch(1)

        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")

        ok_btn.setDefault(True)
        ok_btn.setAutoDefault(True)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)

        self.add_layout(table_gl)
        self.add_layout(combo_h_l)
        self.add_layout(btn_layout)
        self.setFixedSize(self.sizeHint())

    def selected_period(self) -> str:
        """Return the currently selected period key.

        Returns:
            Selected period key from the combo box.
        """

        return self._combo.currentText()


def show_folder_summary(
    source: str,
    n_velocities: int,
    has_params: bool,
    selected_period: Optional[str] = None,
    parent: Optional[QWidget] = None,
) -> None:
    """Show a summary dialog for an imported data folder.

    Args:
        source: Source name.
        n_velocities: Number of velocity channels found.
        has_params: Whether saved fit parameters were found.
        selected_period: Optional selected period key.
        parent: Optional parent widget.
    """

    text = f"Source: {source}\n"
    if selected_period is not None:
        text += f"Selected period: {selected_period}\n"
    text += f"Number of velocity channels: {n_velocities}\n"
    text += f"Saved parameters found: {has_params}\n"
    if has_params:
        text += "Existing parameters will be used."
    else:
        text += "No saved parameters found — a new file will be created after fitting."
    show_information("Data Summary", text=text, parent=parent)


def _demo_main() -> int:
    """Run the MB Solver dialogs as a standalone demo.

    Returns:
        Qt application exit code.
    """

    import sys

    from PySide6.QtWidgets import QApplication, QVBoxLayout

    from settings.app_style import set_app_style

    app = QApplication(sys.argv)
    set_app_style(app)

    win = QWidget()
    win.setWindowTitle("MB Solver dialogs")

    def select_period() -> None:
        periods = {
            "p1": PeriodInfo(10, True),
            "p2": PeriodInfo(21, True),
            "p3": PeriodInfo(6, False),
        }
        dlg = SelectPeriodDialog("Example Source", list(periods), periods, parent=win)
        if dlg.exec() == QDialog.Accepted:
            print(f"Selected period: {dlg.selected_period()}")

    def folder_summary() -> None:
        show_folder_summary("Example Source", 21, False, selected_period="p1", parent=win)

    layout = QVBoxLayout(win)
    for text, slot in (("Select Period", select_period), ("Folder Summary", folder_summary)):
        btn = QPushButton(text)
        btn.clicked.connect(slot)
        layout.addWidget(btn)

    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())