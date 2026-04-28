"""Application dialogs for messages, questions, and period selection.

This module provides small reusable dialogs for short messages and questions,
as well as richer informational dialogs for About/help content.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QStyle,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from paths import APP_ICON_PATH


@dataclass
class PeriodInfo:
    """Metadata for one period option shown in the selection dialog.

    Attributes:
        n_velocities: Number of velocity channels available for this period.
        has_params: Whether saved fit parameters exist for this period.
    """

    n_velocities: int
    has_params: bool


class AskResult(Enum):
    """Possible outcomes of a question dialog."""

    YES = auto()
    NO = auto()
    CANCEL = auto()


class DialogIcon(Enum):
    """Supported standard-icon presets for reusable dialogs."""

    INFORMATION = QStyle.SP_MessageBoxInformation
    WARNING = QStyle.SP_MessageBoxWarning
    CRITICAL = QStyle.SP_MessageBoxCritical
    QUESTION = QStyle.SP_MessageBoxQuestion


def _try_load_app_icon_pixmap(size: int) -> Optional[QPixmap]:
    """Return the application icon pixmap when the icon file can be loaded.

    Args:
        size: Requested icon size in pixels.

    Returns:
        Scaled pixmap if the icon file exists and loads successfully, otherwise
        ``None``.
    """

    icon_path = Path(APP_ICON_PATH)
    if not icon_path.exists():
        return None

    pixmap = QPixmap(str(icon_path))
    if pixmap.isNull():
        return None

    return pixmap.scaled(
        size,
        size,
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )


def _set_window_icon_from_app_icon(widget: QWidget) -> None:
    """Set a widget's window icon from the application icon when available.

    Args:
        widget: Widget whose window icon should be set.
    """

    icon_path = Path(APP_ICON_PATH)
    if icon_path.exists():
        widget.setWindowIcon(QIcon(str(icon_path)))


def _make_html_label(html_text: str) -> QLabel:
    """Create a rich-text label with selection and external-link support.

    Args:
        html_text: HTML text to display.

    Returns:
        Configured rich-text label.
    """

    label = QLabel(html_text)
    label.setTextFormat(Qt.RichText)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
    label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    return label


class TitledDialogBase(QDialog):
    """Common dialog base class with title text, optional icon, and body helpers."""

    def __init__(
        self,
        title: str,
        text: str,
        informative_text: str = "",
        icon: Optional[DialogIcon] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the common titled-dialog layout.

        Args:
            title: Window title.
            text: Main dialog text.
            informative_text: Optional secondary explanatory text.
            icon: Optional standard dialog icon preset.
            parent: Optional parent widget.
        """

        super().__init__(parent)
        _set_window_icon_from_app_icon(self)

        left_margin = 5
        icon_margin = 10
        right_margin = 8
        top_margin = 0
        bottom_margin = 7

        self.setWindowTitle(title)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)

        text_label = _make_html_label(text.replace("\n", "<br>"))
        text_layout.addWidget(text_label)

        if informative_text:
            info_label = _make_html_label(informative_text.replace("\n", "<br>"))
            text_layout.addWidget(info_label)

        row = QHBoxLayout()
        row.addSpacing(left_margin)
        if icon is not None:
            std_icon = self.style().standardIcon(icon.value)
            pixmap = std_icon.pixmap(32, 32)
            icon_label = QLabel()
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(icon_label.sizeHint())
            row.addWidget(icon_label, alignment=Qt.AlignTop)
            row.addSpacing(icon_margin)
        row.addLayout(text_layout)
        row.addSpacing(right_margin)

        self._layout = QVBoxLayout(self)
        self._layout.addSpacing(top_margin)
        self._layout.addLayout(row)
        self._layout.addSpacing(bottom_margin)
        self._layout.addStretch(1)

    def add_layout(self, layout: QLayout) -> None:
        """Add a layout to the dialog body.

        Args:
            layout: Layout to append to the main dialog layout.
        """

        self._layout.addLayout(layout)

    def add_widget(self, widget: QWidget) -> None:
        """Add a widget to the dialog body.

        Args:
            widget: Widget to append to the main dialog layout.
        """

        self._layout.addWidget(widget)

    def add_stretch(self, stretch: int = 1) -> None:
        """Add stretch space to the dialog body.

        Args:
            stretch: Stretch factor to add.
        """

        self._layout.addStretch(stretch)


class MessageDialog(TitledDialogBase):
    """Simple informational dialog with a single acknowledgement button."""

    def __init__(
        self,
        title: str,
        text: str,
        informative_text: str = "",
        icon: Optional[DialogIcon] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the message dialog.

        Args:
            title: Window title.
            text: Main dialog text.
            informative_text: Optional secondary explanatory text.
            icon: Optional standard dialog icon preset.
            parent: Optional parent widget.
        """

        super().__init__(
            title=title,
            text=text,
            informative_text=informative_text,
            icon=icon,
            parent=parent,
        )

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.setAutoDefault(True)
        ok_btn.clicked.connect(self.accept)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch(1)

        self.add_layout(btn_layout)
        self.setFixedSize(self.sizeHint())


class InfoDialog(QDialog):
    """Rich-text dialog for longer informational content."""

    def __init__(
        self,
        title: str,
        html_text: str,
        icon: Optional[DialogIcon] = DialogIcon.INFORMATION,
        parent: Optional[QWidget] = None,
        copy_button: bool = True,
    ) -> None:
        """Initialize the rich informational dialog.

        Args:
            title: Window title.
            html_text: Rich HTML content shown in the text browser.
            icon: Optional standard dialog icon preset.
            parent: Optional parent widget.
            copy_button: Whether to include a button that copies the visible text.
        """

        super().__init__(parent)
        _set_window_icon_from_app_icon(self)

        self.setWindowTitle(title)
        self.resize(560, 360)
        self.setMinimumSize(420, 260)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        if icon is not None:
            std_icon = self.style().standardIcon(icon.value)
            pixmap = std_icon.pixmap(32, 32)
            icon_label = QLabel()
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(icon_label.sizeHint())
            top_row.addWidget(icon_label, alignment=Qt.AlignTop)

        title_label = _make_html_label(f"<b>{html.escape(title)}</b>")
        top_row.addWidget(title_label, 1, alignment=Qt.AlignVCenter)
        main_layout.addLayout(top_row)

        browser = QTextBrowser(self)
        browser.setOpenExternalLinks(True)
        browser.setReadOnly(True)
        browser.setTextInteractionFlags(Qt.TextBrowserInteraction)
        browser.setHtml(html_text)
        browser.moveCursor(QTextCursor.Start)
        self._browser = browser
        main_layout.addWidget(browser, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        if copy_button:
            copy_btn = QPushButton("Copy")
            copy_btn.clicked.connect(self._copy_to_clipboard)
            btn_layout.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.setAutoDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        main_layout.addLayout(btn_layout)

    def _copy_to_clipboard(self) -> None:
        """Copy the visible dialog text to the clipboard."""

        QGuiApplication.clipboard().setText(self._browser.toPlainText())


class AboutDialog(QDialog):
    """Qt-like dialog for application and author information."""

    def __init__(
        self,
        title: str,
        html_text: str,
        parent: Optional[QWidget] = None,
        heading: Optional[str] = None,
    ) -> None:
        """Initialize the about dialog layout and content.

        Args:
            title: Window title.
            html_text: Rich HTML body content.
            parent: Optional parent widget.
            heading: Optional plain-text heading shown above the body content.
        """

        super().__init__(parent)
        _set_window_icon_from_app_icon(self)

        self.setWindowTitle(title)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(22, 18, 22, 18)
        main_layout.setSpacing(16)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(18)

        icon_label = QLabel()
        pixmap = _try_load_app_icon_pixmap(96)
        if pixmap is None:
            std_icon = self.style().standardIcon(QStyle.SP_MessageBoxInformation)
            pixmap = std_icon.pixmap(64, 64)
        icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        icon_label.setFixedWidth(max(pixmap.width() + 8, 84))
        content_layout.addWidget(icon_label, 0, Qt.AlignTop)

        right_layout = QVBoxLayout()
        right_layout.setSpacing(10)

        heading_label = QLabel(heading or title)
        heading_label.setTextFormat(Qt.PlainText)
        heading_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        heading_label.setStyleSheet("font-size: 18pt; font-weight: bold;")
        right_layout.addWidget(heading_label)

        body_label = _make_html_label(html_text)
        body_label.setWordWrap(True)
        right_layout.addWidget(body_label, 1)

        content_layout.addLayout(right_layout, 1)
        main_layout.addLayout(content_layout, 1)
        main_layout.addSpacing(10)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.setCenterButtons(True)
        button_box.accepted.connect(self.accept)
        main_layout.addWidget(button_box)

        self.setFixedSize(self.sizeHint())


class AskDialog(TitledDialogBase):
    """Confirmation dialog returning yes, no, or cancel."""

    def __init__(
        self,
        title: str,
        text: str,
        informative_text: str = "",
        yes_btn_label: str = "Yes",
        no_btn_label: Optional[str] = None,
        cancel_btn_label: str = "Cancel",
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the question dialog.

        Args:
            title: Window title.
            text: Main question text.
            informative_text: Optional secondary explanatory text.
            yes_btn_label: Label for the affirmative button.
            no_btn_label: Optional label for an explicit negative button.
            cancel_btn_label: Label for the cancel button.
            parent: Optional parent widget.
        """

        super().__init__(
            title=title,
            text=text,
            informative_text=informative_text,
            icon=DialogIcon.QUESTION,
            parent=parent,
        )

        self.result_value = AskResult.CANCEL

        yes_btn = QPushButton(yes_btn_label)
        cancel_btn = QPushButton(cancel_btn_label)

        yes_btn.setDefault(True)
        yes_btn.setAutoDefault(True)

        yes_btn.clicked.connect(self._yes)
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_layout.addWidget(yes_btn)
        if no_btn_label:
            no_btn = QPushButton(no_btn_label)
            no_btn.clicked.connect(self._no)
            btn_layout.addWidget(no_btn)
        btn_layout.addWidget(cancel_btn)

        self.add_layout(btn_layout)
        self.setFixedSize(self.sizeHint())

    def _yes(self) -> None:
        """Record an affirmative answer and close the dialog."""

        self.result_value = AskResult.YES
        self.accept()

    def _no(self) -> None:
        """Record a negative answer and close the dialog."""

        self.result_value = AskResult.NO
        self.accept()


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


def show_information(
    title: str,
    text: str,
    informative_text: str = "",
    parent: Optional[QWidget] = None,
) -> None:
    """Show an informational message dialog.

    Args:
        title: Window title.
        text: Main dialog text.
        informative_text: Optional secondary explanatory text.
        parent: Optional parent widget.
    """

    dlg = MessageDialog(title, text, informative_text, icon=DialogIcon.INFORMATION, parent=parent)
    dlg.exec()


def show_rich_information(
    title: str,
    html_text: str,
    parent: Optional[QWidget] = None,
    icon: Optional[DialogIcon] = DialogIcon.INFORMATION,
    copy_button: bool = True,
) -> None:
    """Show a rich-text informational dialog.

    Args:
        title: Window title.
        html_text: Rich HTML content.
        parent: Optional parent widget.
        icon: Optional standard dialog icon preset.
        copy_button: Whether to include a copy button.
    """

    dlg = InfoDialog(
        title=title,
        html_text=html_text,
        icon=icon,
        parent=parent,
        copy_button=copy_button,
    )
    dlg.exec()


def show_about_dialog(
    title: str,
    html_text: str,
    parent: Optional[QWidget] = None,
    heading: Optional[str] = None,
) -> None:
    """Show a Qt-like About dialog.

    Args:
        title: Window title.
        html_text: Rich HTML body content.
        parent: Optional parent widget.
        heading: Optional heading shown above the body content.
    """

    dlg = AboutDialog(
        title=title,
        html_text=html_text,
        parent=parent,
        heading=heading,
    )
    dlg.exec()


def show_warning(
    title: str,
    text: str,
    informative_text: str = "",
    parent: Optional[QWidget] = None,
) -> None:
    """Show a warning message dialog.

    Args:
        title: Window title.
        text: Main warning text.
        informative_text: Optional secondary explanatory text.
        parent: Optional parent widget.
    """

    dlg = MessageDialog(title, text, informative_text, icon=DialogIcon.WARNING, parent=parent)
    dlg.exec()


def show_critical(
    title: str,
    text: str,
    informative_text: str = "",
    parent: Optional[QWidget] = None,
) -> None:
    """Show a critical-error message dialog.

    Args:
        title: Window title.
        text: Main error text.
        informative_text: Optional secondary explanatory text.
        parent: Optional parent widget.
    """

    dlg = MessageDialog(title, text, informative_text, icon=DialogIcon.CRITICAL, parent=parent)
    dlg.exec()


def ask_question(
    title: str,
    text: str,
    informative_text: str = "",
    yes_btn_label: str = "Yes",
    no_btn_label: Optional[str] = None,
    cancel_btn_label: str = "Cancel",
    parent: Optional[QWidget] = None,
) -> AskResult:
    """Show a confirmation dialog and return the selected answer.

    Args:
        title: Window title.
        text: Main question text.
        informative_text: Optional secondary explanatory text.
        yes_btn_label: Label for the affirmative button.
        no_btn_label: Optional label for an explicit negative button.
        cancel_btn_label: Label for the cancel button.
        parent: Optional parent widget.

    Returns:
        Selected dialog result.
    """

    dlg = AskDialog(
        title,
        text,
        informative_text,
        yes_btn_label=yes_btn_label,
        no_btn_label=no_btn_label,
        cancel_btn_label=cancel_btn_label,
        parent=parent,
    )
    dlg.exec()
    return dlg.result_value


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


def slider_ask_clamp_value(
    proposed_range: str,
    old_cur: str,
    new_cur: str,
    old_dft: str,
    new_dft: str,
    parent: Optional[QWidget] = None,
) -> AskResult:
    """Ask whether a slider value should be clamped to a proposed range.

    Args:
        proposed_range: Proposed allowed range.
        old_cur: Previous current value.
        new_cur: Clamped current value.
        old_dft: Previous default value.
        new_dft: Clamped default value.
        parent: Optional parent widget.

    Returns:
        User's selected answer.
    """

    return ask_question(
        "Out of range",
        "<b>Current</b>/<b>default</b> value is outside the proposed range.",
        f"<b>Proposed range:</b> <code>{proposed_range}</code><br>"
        f"<b>Current:</b> <code>{old_cur}</code> → <code>{new_cur}</code><br>"
        f"<b>Default:</b> <code>{old_dft}</code> → <code>{new_dft}</code><br><br>"
        "Press <b>OK</b> to clamp values to the proposed range, or <b>Cancel</b> to abort.",
        yes_btn_label="OK",
        cancel_btn_label="Cancel",
        parent=parent,
    )


def range_slider_ask_clamp_value(
    proposed_range: str,
    old_cur: str,
    new_cur: str,
    old_dft: str,
    new_dft: str,
    parent: Optional[QWidget] = None,
) -> AskResult:
    """Ask whether range-slider values should be clamped to proposed limits.

    Args:
        proposed_range: Proposed allowed range limits.
        old_cur: Previous current range.
        new_cur: Clamped current range.
        old_dft: Previous default range.
        new_dft: Clamped default range.
        parent: Optional parent widget.

    Returns:
        User's selected answer.
    """

    return ask_question(
        "Out of range",
        "<b>Current</b>/<b>default</b> values are outside the proposed range limits.",
        f"<b>Proposed range limits:</b> <code>{proposed_range}</code><br>"
        f"<b>Current:</b> <code>{old_cur}</code> → <code>{new_cur}</code><br>"
        f"<b>Default:</b> <code>{old_dft}</code> → <code>{new_dft}</code><br><br>"
        "Press <b>OK</b> to clamp values to the proposed range, or <b>Cancel</b> to abort.",
        yes_btn_label="OK",
        cancel_btn_label="Cancel",
        parent=parent,
    )


def multi_slider_ask_clamp_value(
    proposed_range: str,
    cur_min: str,
    cur_max: str,
    dft_min: str,
    dft_max: str,
    parent: Optional[QWidget] = None,
) -> AskResult:
    """Ask whether array-slider values should be clamped to a proposed range.

    Args:
        proposed_range: Proposed allowed range.
        cur_min: Minimum current value.
        cur_max: Maximum current value.
        dft_min: Minimum default value.
        dft_max: Maximum default value.
        parent: Optional parent widget.

    Returns:
        User's selected answer.
    """

    return ask_question(
        "Out of range",
        "<b>Current</b>/<b>default</b> values are outside the proposed range.",
        f"<b>Proposed range:</b> <code>{proposed_range}</code><br>"
        f"<b>Current values range:</b> <code>[{cur_min}, {cur_max}]</code><br>"
        f"<b>Default values range:</b> <code>[{dft_min}, {dft_max}]</code><br><br>"
        "Press <b>OK</b> to clamp values to the proposed range, or <b>Cancel</b> to abort.",
        yes_btn_label="OK",
        cancel_btn_label="Cancel",
        parent=parent,
    )


def slider_ask_extend_range(
    proposed_val: str,
    old_range: str,
    new_range: str,
    parent: Optional[QWidget] = None,
) -> AskResult:
    """Ask whether a slider range should be extended to include a new value.

    Args:
        proposed_val: Proposed new value.
        old_range: Existing range.
        new_range: Extended range.
        parent: Optional parent widget.

    Returns:
        User's selected answer.
    """

    return ask_question(
        "Out of range",
        "The proposed <b>value</b> is outside the current range.",
        f"<b>Proposed value:</b> <code>{proposed_val}</code><br>"
        f"<b>Range:</b> <code>{old_range}</code> → <code>{new_range}</code><br><br>"
        "Press <b>OK</b> to extend the range to include this value, or <b>Cancel</b> to abort.",
        yes_btn_label="OK",
        cancel_btn_label="Cancel",
        parent=parent,
    )


def range_slider_ask_extend_range(
    proposed_vals: str,
    old_range: str,
    new_range: str,
    parent: Optional[QWidget] = None,
) -> AskResult:
    """Ask whether a range-slider range should be extended for new values.

    Args:
        proposed_vals: Proposed new range values.
        old_range: Existing range.
        new_range: Extended range.
        parent: Optional parent widget.

    Returns:
        User's selected answer.
    """

    return ask_question(
        "Out of range",
        "The proposed <b>values</b> are outside the current range limits.",
        f"<b>Proposed values:</b> <code>{proposed_vals}</code><br>"
        f"<b>Range:</b> <code>{old_range}</code> → <code>{new_range}</code><br><br>"
        "Press <b>OK</b> to extend the range to include these values, or <b>Cancel</b> to abort.",
        yes_btn_label="OK",
        cancel_btn_label="Cancel",
        parent=parent,
    )


def _demo_main() -> int:
    """Run the dialog module as a standalone demo.

    Returns:
        Qt application exit code.
    """

    import sys
    from settings.app_style import set_app_style

    class TestWindow(QWidget):
        """Test window for the dialog helpers in this module."""

        def __init__(self) -> None:
            """Initialize the demo window and its test buttons."""

            super().__init__()
            self.setWindowTitle("Dialog Test")
            self.resize(920, 500)
            _set_window_icon_from_app_icon(self)

            btn_question_save = QPushButton("ask_question: Save / Don't Save / Cancel")
            btn_question_yes = QPushButton("ask_question: Yes / No / Cancel")
            btn_question_buttons_only = QPushButton("ask_question: Yes / Cancel")
            btn_select_period = QPushButton("Select Period")

            btn_info = QPushButton("show_information")
            btn_rich_info = QPushButton("show_rich_information")
            btn_about = QPushButton("show_about_dialog")
            btn_warning = QPushButton("show_warning")
            btn_critical = QPushButton("show_critical")
            btn_folder_summary = QPushButton("show_folder_summary")

            btn_clamp_value = QPushButton("slider_ask_clamp_value")
            btn_clamp_arr_values = QPushButton("multi_slider_ask_clamp_value")
            btn_extend_range = QPushButton("slider_ask_extend_range")
            btn_clamp_range_value = QPushButton("range_slider_ask_clamp_value")
            btn_change_range_and_gap = QPushButton("range_slider_ask_extend_range")

            l1 = QVBoxLayout()
            l1.addWidget(btn_question_save)
            l1.addWidget(btn_question_yes)
            l1.addWidget(btn_question_buttons_only)
            l1.addWidget(btn_select_period)

            l2 = QVBoxLayout()
            l2.addWidget(btn_info)
            l2.addWidget(btn_rich_info)
            l2.addWidget(btn_about)
            l2.addWidget(btn_warning)
            l2.addWidget(btn_critical)
            l2.addWidget(btn_folder_summary)

            l3 = QVBoxLayout()
            l3.addWidget(btn_clamp_value)
            l3.addWidget(btn_clamp_arr_values)
            l3.addWidget(btn_extend_range)
            l3.addWidget(btn_clamp_range_value)
            l3.addWidget(btn_change_range_and_gap)

            layout = QHBoxLayout(self)
            layout.addStretch(1)
            layout.addLayout(l1)
            layout.addStretch(1)
            layout.addLayout(l2)
            layout.addStretch(1)
            layout.addLayout(l3)
            layout.addStretch(1)

            btn_question_save.clicked.connect(self.test_question_save)
            btn_question_yes.clicked.connect(self.test_question_yes)
            btn_question_buttons_only.clicked.connect(self.test_question_buttons_only)
            btn_select_period.clicked.connect(self.test_select_period)

            btn_info.clicked.connect(self.test_info)
            btn_rich_info.clicked.connect(self.test_rich_info)
            btn_about.clicked.connect(self.test_about_dialog)
            btn_warning.clicked.connect(self.test_warning)
            btn_critical.clicked.connect(self.test_critical)
            btn_folder_summary.clicked.connect(self.test_folder_summary)

            btn_clamp_value.clicked.connect(self.test_slider_ask_clamp_value)
            btn_clamp_arr_values.clicked.connect(self.test_multi_slider_ask_clamp_value)
            btn_extend_range.clicked.connect(self.test_slider_ask_extend_range)
            btn_clamp_range_value.clicked.connect(self.test_range_slider_ask_clamp_value)
            btn_change_range_and_gap.clicked.connect(self.test_range_slider_ask_extend_range)

        def test_question_save(self) -> None:
            """Test the save/don't-save/cancel question dialog."""

            result = ask_question(
                title="Unsaved Changes",
                text="Do you want to save your changes before closing?",
                informative_text=(
                    "Your modifications will be lost if you close this window "
                    "without saving them."
                ),
                yes_btn_label="Save",
                no_btn_label="Don't Save",
                cancel_btn_label="Cancel",
                parent=self,
            )
            print("Question result (save):", result)

        def test_question_yes(self) -> None:
            """Test the yes/no/cancel question dialog."""

            result = ask_question(
                title="Continue Operation",
                text="Do you want to continue?",
                informative_text=(
                    "Selecting Yes will continue the current operation.\n"
                    "Selecting No will stop without making any changes."
                ),
                yes_btn_label="Yes",
                no_btn_label="No",
                cancel_btn_label="Cancel",
                parent=self,
            )
            print("Question result (yes/no):", result)

        def test_question_buttons_only(self) -> None:
            """Test the two-button question dialog."""

            result = ask_question(
                title="Delete File",
                text="Do you want to delete this file?",
                informative_text="This action cannot be undone.",
                yes_btn_label="Delete",
                no_btn_label=None,
                cancel_btn_label="Cancel",
                parent=self,
            )
            print("Question result (buttons only):", result)

        def test_select_period(self) -> None:
            """Test the period-selection dialog."""

            periods = {
                "p1": PeriodInfo(10, True),
                "p2": PeriodInfo(21, True),
                "p3": PeriodInfo(13, True),
                "p4": PeriodInfo(6, False),
                "p5": PeriodInfo(9, True),
                "p6": PeriodInfo(3, False),
            }
            dlg = SelectPeriodDialog(
                source="Example Source",
                periods_keys=list(periods.keys()),
                periods=periods,
                parent=self,
            )
            if dlg.exec() == QDialog.Accepted:
                print(f"Selected Period: {dlg.selected_period()}")

        def test_info(self) -> None:
            """Test the plain informational dialog."""

            show_information(
                title="Data Information",
                text="The data file was loaded successfully.",
                informative_text=(
                    "128 rows were read and validated.\n"
                    "No missing values were found."
                ),
                parent=self,
            )

        def test_rich_info(self) -> None:
            """Test the generic rich-information dialog."""

            show_rich_information(
                title="Project Notes",
                html_text=(
                    "<b>Maxwell Bloch Solver</b><br><br>"
                    "This is the <b>generic</b> rich-info dialog. "
                    "It is useful for longer help text, documentation notes, or content "
                    "where a copy button is helpful.<br><br>"
                    '<a href="https://github.com/">Example external link</a>'
                ),
                parent=self,
            )

        def test_about_dialog(self) -> None:
            """Test the Qt-like about dialog."""

            show_about_dialog(
                title="About Maxwell Bloch Solver",
                heading="About Maxwell Bloch Solver",
                html_text=(
                    "This application provides a GUI for Maxwell-Bloch solver workflows.<br><br>"
                    "<b>Version:</b> 7.0<br>"
                    "<b>Created by:</b> Vahid Anari<br>"
                    '<b>Email:</b> <a href="mailto:vahid.anari8@gmail.com">vahid.anari8@gmail.com</a><br>'
                    '<b>GitHub:</b> <a href="https://github.com/">https://github.com/</a>'
                ),
                parent=self,
            )

        def test_warning(self) -> None:
            """Test the warning dialog."""

            show_warning(
                title="Overwrite File",
                text="A file with this name already exists.",
                informative_text=(
                    "Saving now will replace the existing file.\n"
                    "This action cannot be undone."
                ),
                parent=self,
            )

        def test_critical(self) -> None:
            """Test the critical dialog."""

            show_critical(
                title="Load Error",
                text="The selected file could not be opened.",
                informative_text=(
                    "Check that the file exists and that you have permission "
                    "to read it."
                ),
                parent=self,
            )

        def test_folder_summary(self) -> None:
            """Test the folder-summary dialog."""

            show_folder_summary(
                source="Example Source",
                n_velocities=21,
                has_params=False,
                selected_period="p1",
                parent=self,
            )

        def test_slider_ask_clamp_value(self) -> None:
            """Test the slider-clamp confirmation dialog."""

            result = slider_ask_clamp_value(
                proposed_range="[1.0, 2.0]",
                old_cur="0.0",
                new_cur="1.0",
                old_dft="3.0",
                new_dft="2.0",
                parent=self,
            )
            print("Clamp value result:", result)

        def test_multi_slider_ask_clamp_value(self) -> None:
            """Test the multi-slider clamp dialog."""

            result = multi_slider_ask_clamp_value(
                proposed_range="[0.0, 1.0]",
                cur_min="-2.0",
                cur_max="7.5",
                dft_min="-1.0",
                dft_max="6.0",
                parent=self,
            )
            print("Clamp array values result:", result)

        def test_slider_ask_extend_range(self) -> None:
            """Test the slider-range extension dialog."""

            result = slider_ask_extend_range(
                proposed_val="1.0",
                old_range="[0.0, 1.0]",
                new_range="[1.0, 2.0]",
                parent=self,
            )
            print("Extend range result:", result)

        def test_range_slider_ask_clamp_value(self) -> None:
            """Test the range-slider clamp dialog."""

            result = range_slider_ask_clamp_value(
                proposed_range="[0.0, 1.0]",
                old_cur="[0.0, 1.0]",
                old_dft="[0.0, 1.0]",
                new_cur="[0.0, 1.0]",
                new_dft="[0.0, 1.0]",
                parent=self,
            )
            print("Clamp range/value result:", result)

        def test_range_slider_ask_extend_range(self) -> None:
            """Test the range-slider extension dialog."""

            result = range_slider_ask_extend_range(
                proposed_vals="[0.0, 1.0]",
                old_range="[0.0, 10.0]",
                new_range="[0.0, 20.0]",
                parent=self,
            )
            print("Change range and gap result:", result)

    app = QApplication(sys.argv)
    set_app_style(app)
    win = TestWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
