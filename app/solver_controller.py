"""Solver controller: background worker and thread lifecycle management.

Owns the QThread/SolverWorker pair and the pending-request flag used to prevent
overlapping solves.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal

from solver.maxwell_bloch_solver import solve_maxwell_bloch


class SolverWorker(QObject):
    """Background worker that runs the Maxwell-Bloch solver off the UI thread."""

    finished = Signal(dict)

    def __init__(self, params: dict[str, Any]) -> None:
        """Initialize the worker with one immutable parameter snapshot.

        Args:
            params: Parameter mapping passed to the solver when ``run`` is called.
        """
        super().__init__()
        self._params = params

    def run(self) -> None:
        """Execute the solver and emit the resulting output dictionary."""

        result = solve_maxwell_bloch(self._params)
        self.finished.emit(result)


class SolverController(QObject):
    """Manage solver thread lifecycle and pending-request queuing.

    This controller owns the ``QThread``/``SolverWorker`` pair used for one
    background solve. It also tracks whether a solve is currently running and
    whether another solve was requested while the current one was still active.

    Inheriting from ``QObject`` ensures that the internal finish handlers are
    proper Qt slots. When the worker emits ``finished`` from the background
    thread, Qt can therefore queue the callbacks onto the main thread via an
    auto-connection, avoiding cross-thread UI and timer errors.
    """

    def __init__(
        self,
        parent: QObject,
        on_finished: Callable[[dict], None],
        get_params: Callable[[], dict[str, Any]],
        on_state_solving: Callable[[], None],
        on_state_ready: Callable[[], None],
    ) -> None:
        """Initialize the solver controller.

        Args:
            parent: QObject parent, typically the main window.
            on_finished: Callback invoked on the main thread with the result
                dictionary after a solve completes.
            get_params: Callable returning the current parameter snapshot to solve.
            on_state_solving: Callback invoked on the main thread when a solve starts.
            on_state_ready: Callback invoked on the main thread when a solve finishes.
        """
        super().__init__(parent)
        self._on_finished = on_finished
        self._get_params = get_params
        self._on_state_solving = on_state_solving
        self._on_state_ready = on_state_ready

        self._is_solving = False
        self._has_pending = False
        self._current_params: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def is_solving(self) -> bool:
        """Return whether a background solve thread is currently running.

        Returns:
            ``True`` while a solve is running, otherwise ``False``.
        """
        return self._is_solving

    @property
    def current_params(self) -> dict[str, Any]:
        """Return the parameter snapshot used for the most recently started solve.

        Returns:
            Parameter mapping used for the active or most recent solve.
        """
        return self._current_params

    def solve(self) -> None:
        """Start a background solve, or queue one if a solve is already running.

        If a solve is already in progress, this method does not start a second
        thread immediately. Instead, it marks a pending request so that another
        solve begins automatically after the current thread finishes.
        """
        if self._is_solving:
            self._has_pending = True
            return

        self._is_solving = True
        self._has_pending = False
        self._current_params = self._get_params()
        self._on_state_solving()

        thread = QThread(self)
        worker = SolverWorker(self._current_params)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._handle_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._handle_thread_finished)
        thread.finished.connect(thread.deleteLater)

        # Keep references alive for the duration of the solve.
        self._thread = thread
        self._worker = worker
        thread.start()

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _handle_finished(self, result: dict) -> None:
        """Handle solver completion on the main thread.

        Args:
            result: Result dictionary emitted by the worker.
        """
        self._is_solving = False
        self._on_state_ready()
        self._on_finished(result)

    def _handle_thread_finished(self) -> None:
        """Handle thread shutdown and start any queued solve request."""
        if self._has_pending:
            self.solve()
