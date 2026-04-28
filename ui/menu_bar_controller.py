"""Declarative menu-bar controller for the main window.

This module provides a small controller class that builds a Qt menu bar from
a declarative Python specification. It supports nested submenus, checkable
actions, shortcuts, menu roles, and a simple signal for routed action
handling.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List, Union

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMenu

MenuSpec = Dict[str, List[Dict[str, Any]]]
MENU_SPEC_EXAMPLE = {
    "File": [
        {"id": "new_project", "text": "New Project…", "shortcut": QKeySequence.New},
        {"id": "open_project", "text": "Open Project…", "shortcut": QKeySequence.Open},
        {"id": "open_recent", "submenu": "Open Recent", "items": [
            {"id": "recent_1", "text": "Example1.cfg"},
            {"id": "recent_2", "text": "Example2.cfg"},
            {"id": "sep"},
            {"id": "clear_recent", "text": "Clear Menu"},
        ]},
        {"id": "sep"},

        {"id": "import_cfg", "text": "Import Config…", "shortcut": "Ctrl+O"},
        {"id": "import_parameters", "text": "Import Parameters…", "shortcut": "Ctrl+Shift+O"},
        {"id": "sep"},

        {"id": "export_cfg", "text": "Export Config…"},
        {"id": "export_params", "text": "Export Parameters…"},
        {"id": "sep"},

        {"id": "save_cfg", "text": "Save Config", "shortcut": QKeySequence.Save},
        {"id": "save_cfg_as", "text": "Save Config As…", "shortcut": "Ctrl+Shift+S"},
        {"id": "save_params", "text": "Save Parameters", "shortcut": "Ctrl+Alt+S"},
        {"id": "save_params_as", "text": "Save Parameters As…"},
        {"id": "sep"},

        {"id": "save_all", "text": "Save All", "shortcut": "Ctrl+Alt+Shift+S"},
        {"id": "sep"},

        {"id": "close", "text": "Close", "shortcut": QKeySequence.Close},
        {"id": "quit", "text": "Quit", "shortcut": QKeySequence.Quit, "role": QAction.QuitRole},
    ],

    "Edit": [
        {"id": "undo", "text": "Undo", "shortcut": QKeySequence.Undo},
        {"id": "redo", "text": "Redo", "shortcut": QKeySequence.Redo},
        {"id": "sep"},

        {"id": "cut", "text": "Cut", "shortcut": QKeySequence.Cut},
        {"id": "copy", "text": "Copy", "shortcut": QKeySequence.Copy},
        {"id": "paste", "text": "Paste", "shortcut": QKeySequence.Paste},
        {"id": "sep"},

        {"id": "find", "text": "Find…", "shortcut": QKeySequence.Find},
        {"id": "find_next", "text": "Find Next", "shortcut": QKeySequence.FindNext},
        {"id": "find_prev", "text": "Find Previous", "shortcut": QKeySequence.FindPrevious},
        {"id": "sep"},

        {"id": "prefs", "text": "Preferences…", "shortcut": QKeySequence.Preferences,
         "role": QAction.PreferencesRole},
    ],

    "View": [
        {"id": "toggle_statusbar", "text": "Show Status Bar", "checkable": True, "checked": True},
        {"id": "toggle_toolbar", "text": "Show Tool Bar", "checkable": True, "checked": True},
        {"id": "toggle_save", "text": "Enable Save", "checkable": True, "checked": True},
        {"id": "sep"},

        {"id": "zoom_in", "text": "Zoom In", "shortcut": QKeySequence.ZoomIn},
        {"id": "zoom_out", "text": "Zoom Out", "shortcut": QKeySequence.ZoomOut},
        {"id": "zoom_reset", "text": "Reset Zoom", "shortcut": "Ctrl+0"},
        {"id": "sep"},

        {"id": "theme", "submenu": "Theme", "items": [
            {"id": "theme_system", "text": "System"},
            {"id": "theme_light", "text": "Light"},
            {"id": "theme_dark", "text": "Dark"},
        ]},
    ],

    "Tools": [
        {"id": "run", "text": "Run", "shortcut": "Ctrl+R"},
        {"id": "stop", "text": "Stop", "shortcut": "Ctrl+."},
        {"id": "sep"},

        {"id": "validate_params", "text": "Validate Parameters"},
        {"id": "reset_defaults", "text": "Reset to Defaults"},
        {"id": "sep"},

        {"id": "advanced", "submenu": "Advanced", "items": [
            {"id": "clear_cache", "text": "Clear Cache"},
            {"id": "open_logs", "text": "Open Logs Folder"},
            {"id": "dev_tools", "text": "Developer Tools"},
        ]},
    ],

    "Help": [
        {"id": "docs", "text": "Documentation", "shortcut": QKeySequence.HelpContents},
        {"id": "shortcuts", "text": "Keyboard Shortcuts"},
        {"id": "sep"},

        {"id": "check_updates", "text": "Check for Updates…"},
        {"id": "sep"},

        {"id": "about", "text": "About", "role": QAction.AboutRole},
        {"id": "about_qt", "text": "About Qt", "role": QAction.AboutQtRole},
    ],
}


class MenuBarController(QObject):
    """Build and manage a menu bar from a declarative specification.

    The controller creates menus and actions for a ``QMainWindow`` using a
    dictionary-based specification. Built actions are stored by action id so
    they can later be enabled, checked, or replaced programmatically.

    Signals:
        actionTriggered (str, str, bool): Emitted when an action is triggered.
            The emitted values are the menu path, action id, and checked state.
    """

    actionTriggered = Signal(str, str, bool)  # menu_name, action_id, checked

    def __init__(
            self,
            window: QMainWindow,
            menu_spec: Optional[MenuSpec] = None,
            *,
            native_menubar: bool = True,
    ) -> None:
        """Initialize the menu-bar controller.

        Args:
            window (QMainWindow): Main window that owns the menu bar.
            menu_spec (Optional[MenuSpec], optional): Declarative menu
                specification used to build the menu hierarchy. If omitted or
                ``None``, an empty specification is used.
            native_menubar (bool, optional): Whether to use the platform-native
                menu bar when supported.
        """
        super().__init__(window)
        self._w = window
        self._menu_spec: MenuSpec = menu_spec or {}
        self._actions: Dict[str, QAction] = {}  # id -> QAction
        self._build_menus(native_menubar=native_menubar)

    # -----------------------------
    # Action/menu construction
    # -----------------------------
    def _to_keyseq(self, shortcut: Union[None, str, QKeySequence]) -> Optional[QKeySequence]:
        """Convert a shortcut value to a ``QKeySequence``.

        Args:
            shortcut (Union[None, str, QKeySequence]): Shortcut value to
                normalize. This may be ``None``, a string sequence such as
                ``"Ctrl+S"``, or an existing ``QKeySequence``.

        Returns:
            Optional[QKeySequence]: Normalized key sequence, or ``None`` if no
            shortcut was provided.
        """
        if shortcut is None:
            return None
        if isinstance(shortcut, QKeySequence):
            return shortcut
        return QKeySequence(shortcut)

    def _add_action(
            self,
            menu: QMenu,
            *,
            menu_name: str,
            action_id: str,
            text: str,
            shortcut: Union[None, str, QKeySequence] = None,
            role: Optional[QAction.MenuRole] = None,
            enabled: bool = True,
            checkable: bool = False,
            checked: bool = False,
    ) -> QAction:
        """Create, configure, register, and add a ``QAction`` to a menu.

        Args:
            menu (QMenu): Menu that will receive the action.
            menu_name (str): Logical name or path of the menu used when routing
                emitted signals.
            action_id (str): Unique action identifier used for later lookup.
            text (str): Visible action text.
            shortcut (Union[None, str, QKeySequence], optional): Keyboard
                shortcut for the action.
            role (Optional[QAction.MenuRole], optional): Qt menu role to assign
                to the action.
            enabled (bool, optional): Initial enabled state.
            checkable (bool, optional): Whether the action is checkable.
            checked (bool, optional): Initial checked state for checkable
                actions.

        Returns:
            QAction: The created and registered Qt action.
        """
        act = QAction(text, self._w)
        act.setEnabled(enabled)
        act.setCheckable(checkable)
        if checkable:
            act.setChecked(checked)

        ks = self._to_keyseq(shortcut)
        if ks is not None:
            act.setShortcut(ks)

        if role is not None:
            act.setMenuRole(role)

        # triggered(bool checked) -> emit(menu_name, action_id, checked)
        act.triggered.connect(lambda c, m=menu_name, a=action_id: self.actionTriggered.emit(m, a, c))
        menu.addAction(act)
        self._actions[action_id] = act
        return act

    def _populate_menu(self, menu: QMenu, menu_name: str, items: List[Dict[str, Any]]) -> None:
        """Populate a menu from a specification list.

        Args:
            menu (QMenu): Menu to populate.
            menu_name (str): Menu name or path associated with this branch of
                the hierarchy.
            items (List[Dict[str, Any]]): Menu-item specifications. Each item
                may define a standard action, a separator, or a nested submenu.

        Raises:
            ValueError: If a non-submenu, non-separator item does not define an
                ``id`` entry.
        """
        for item in items:
            # Nested submenu support
            # {"submenu": "Tools", "items": [ ... ]}
            if "submenu" in item:
                sub = menu.addMenu(str(item["submenu"]))
                sub_items = item.get("items", [])
                self._populate_menu(sub, menu_name=f"{menu_name}/{item['submenu']}", items=sub_items)
                continue

            action_id = item.get("id")
            if not action_id:
                raise ValueError(f"Menu item in '{menu_name}' must define 'id': {item}")
            action_id = str(action_id).strip()

            if action_id == "sep":
                menu.addSeparator()
                continue

            self._add_action(
                menu,
                menu_name=menu_name,
                action_id=action_id,
                text=str(item.get("text", action_id)),
                shortcut=item.get("shortcut"),
                role=item.get("role"),
                enabled=bool(item.get("enabled", True)),
                checkable=bool(item.get("checkable", False)),
                checked=bool(item.get("checked", False)),
            )

    def _build_menus(self, native_menubar: bool) -> None:
        """Build the full menu hierarchy from the stored specification.

        Args:
            native_menubar (bool): Whether the created menu bar should use the
                platform-native menu-bar implementation when available.
        """
        menubar = self._w.menuBar()
        menubar.setNativeMenuBar(native_menubar)
        menubar.clear()

        for menu_name, items in self._menu_spec.items():
            menu = menubar.addMenu(menu_name)
            self._populate_menu(menu, menu_name=menu_name, items=items)

    # -----------------------------
    # Public API
    # -----------------------------
    def set_enabled(self, action_id: str, enabled: bool) -> None:
        """Set the enabled state of an action.

        Args:
            action_id (str): Identifier of the action to update.
            enabled (bool): New enabled state. If the action id is unknown, the
                call has no effect.
        """
        act = self._actions.get(action_id)
        if act is not None:
            act.setEnabled(enabled)

    def set_checked(self, action_id: str, checked: bool) -> None:
        """Set the checked state of a checkable action.

        Args:
            action_id (str): Identifier of the action to update.
            checked (bool): New checked state. If the action id is unknown, the
                call has no effect.
        """
        act = self._actions.get(action_id)
        if act is not None:
            act.setChecked(checked)

    def get_checked(self, action_id: str) -> bool:
        """Return the checked state of an action.

        Args:
            action_id (str): Identifier of the action to query.

        Returns:
            bool: Checked state of the action, or ``False`` if the action is
            not found.
        """
        act = self._actions.get(action_id)
        if act is not None:
            return act.isChecked()
        return False

    def set_menu_spec(self, menu_spec: Dict[str, Any], native_menubar: bool) -> None:
        """Replace the current menu specification and rebuild the menu bar.

        Args:
            menu_spec (Dict[str, Any]): New declarative menu specification.
            native_menubar (bool): Whether the rebuilt menu bar should use the
                platform-native menu-bar implementation when available.
        """
        self._menu_spec = menu_spec
        self._actions.clear()
        self._build_menus(native_menubar=native_menubar)


def _demo_main() -> int:
    """Run the module as a standalone demo application.

    Returns:
        int: Qt application exit code.
    """
    import sys
    from PySide6.QtWidgets import QApplication
    from settings.app_style import set_app_style

    class MainWindow(QMainWindow):
        """Simple demo window that hosts the generated menu bar."""

        def __init__(self):
            """Initialize the demo main window."""
            super().__init__()
            self.menu = MenuBarController(self, menu_spec=MENU_SPEC_EXAMPLE, native_menubar=False)
            self.menu.actionTriggered.connect(self.on_menu_action)

        def on_menu_action(self, menu: str, action_id: str, checked: bool) -> None:
            """Handle menu actions emitted by the controller.

            Args:
                menu (str): Menu name or path that emitted the action.
                action_id (str): Identifier of the triggered action.
                checked (bool): Checked state reported by the action trigger.
            """
            print(menu, action_id, checked)
            # Route by (menu, action_id)
            if action_id == "toggle_save":
                self.menu.set_enabled("save_cfg", checked)

    app = QApplication(sys.argv)
    set_app_style(app)
    w = MainWindow()
    w.resize(900, 600)
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo_main())
