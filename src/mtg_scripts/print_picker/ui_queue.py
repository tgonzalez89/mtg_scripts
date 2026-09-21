"""Deliver worker-thread results to the Tk thread.

Calling `widget.after(...)` from a worker thread is not safe: tkinter registers
a new Tcl command on the calling thread and raises `RuntimeError: main thread is
not in main loop` when the UI thread is not inside the event loop at that
instant. Workers therefore hand callbacks to a queue, and a timer owned by the
UI thread drains it.
"""

import contextlib
import queue
import tkinter as tk
from collections.abc import Callable
from typing import Final

POLL_INTERVAL_MS: Final[int] = 25

type _Task = tuple[Callable[..., object], tuple[object, ...]]


class UiQueue:
    """A thread-safe inbox drained on the Tk thread that owns `widget`."""

    def __init__(self, widget: tk.Misc, interval_ms: int = POLL_INTERVAL_MS) -> None:
        self._widget = widget
        self._interval_ms = interval_ms
        self._tasks: queue.SimpleQueue[_Task] = queue.SimpleQueue()
        self._timer: str | None = None
        self._stopped = False

    def start(self) -> None:
        """Begin draining. Must be called from the UI thread."""
        if self._stopped or self._timer is not None:
            return
        self._timer = self._widget.after(self._interval_ms, self._drain)

    def stop(self) -> None:
        """Stop draining and drop pending work. Must be called from the UI thread."""
        self._stopped = True
        if self._timer is not None:
            with contextlib.suppress(tk.TclError):
                # The widget may already have been torn down.
                self._widget.after_cancel(self._timer)
            self._timer = None
        self._tasks = queue.SimpleQueue()

    def post(self, callback: Callable[..., object], *args: object) -> None:
        """Queue a callback to run on the UI thread. Safe from any thread."""
        if not self._stopped:
            self._tasks.put((callback, args))

    def _drain(self) -> None:
        self._timer = None
        if self._stopped:
            return
        while True:
            try:
                callback, args = self._tasks.get_nowait()
            except queue.Empty:
                break
            callback(*args)
            if self._stopped:
                return
        self._timer = self._widget.after(self._interval_ms, self._drain)
