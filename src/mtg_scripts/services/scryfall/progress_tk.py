"""Tk progress window for Scryfall activity; safe to drive from worker threads."""

from __future__ import annotations

import contextlib
import queue
import time
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, cast, override

from .progress import DEFAULT_RENDER_INTERVAL, DownloadSnapshot, ProgressIndicator, describe_transfer

if TYPE_CHECKING:
    from collections.abc import Callable

POLL_INTERVAL_MS = 50

type _Event = DownloadSnapshot | str | None


class _ProgressWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc, title: str) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(width=False, height=False)
        self.transient(cast("tk.Tk", master.winfo_toplevel()))
        self.description_label = ttk.Label(self, text="Starting...", width=60)
        self.description_label.pack(padx=20, pady=(18, 4), anchor="w")
        self.source_label = ttk.Label(self, text="", width=60, foreground="gray")
        self.source_label.pack(padx=20, anchor="w")
        self.progress_bar = ttk.Progressbar(self, mode="indeterminate", length=420)
        self.progress_bar.pack(padx=20, pady=8)
        self.progress_bar.start(10)
        self.detail_label = ttk.Label(self, text="", width=60)
        self.detail_label.pack(padx=20, pady=(0, 18), anchor="w")
        self.protocol("WM_DELETE_WINDOW", lambda: None)

    def show_download(self, snapshot: DownloadSnapshot) -> None:
        self.description_label.configure(text=snapshot.description)
        self.source_label.configure(text=snapshot.source)
        self.detail_label.configure(text=describe_transfer(snapshot))
        fraction = snapshot.fraction
        if fraction is None:
            self._indeterminate()
        else:
            if self.progress_bar.cget("mode") != "determinate":
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
            self.progress_bar.configure(maximum=1000, value=round(fraction * 1000))

    def show_status(self, message: str) -> None:
        self.description_label.configure(text=message)
        self.source_label.configure(text="")
        self.detail_label.configure(text="")
        self._indeterminate()

    def _indeterminate(self) -> None:
        if self.progress_bar.cget("mode") != "indeterminate":
            self.progress_bar.configure(mode="indeterminate", value=0)
            self.progress_bar.start(10)


class TkProgressIndicator(ProgressIndicator):
    """Show a modeless progress window owned by `master`.

    Construct and `close()` on the Tk thread. Events may arrive from any thread;
    they are queued and applied by a timer on the Tk thread.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        title: str = "Scryfall",
        clock: Callable[[], float] = time.monotonic,
        render_interval: float = DEFAULT_RENDER_INTERVAL,
    ) -> None:
        super().__init__(clock=clock, render_interval=render_interval)
        self._master = master
        self._title = title
        self._events: queue.SimpleQueue[_Event] = queue.SimpleQueue()
        self._window: _ProgressWindow | None = None
        self._closed = False
        self._timer: str | None = master.after(POLL_INTERVAL_MS, self._drain)

    @override
    def render_download(self, snapshot: DownloadSnapshot) -> None:
        self._events.put(snapshot)

    @override
    def render_status(self, message: str) -> None:
        self._events.put(message)

    @override
    def render_idle(self) -> None:
        self._events.put(None)

    @override
    def close(self) -> None:
        self._closed = True
        if self._timer is not None:
            with contextlib.suppress(tk.TclError):
                self._master.after_cancel(self._timer)
            self._timer = None
        self._destroy_window()

    def _drain(self) -> None:
        self._timer = None
        if self._closed:
            return
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if event is None:
                self._destroy_window()
            else:
                self._apply(event)
        self._timer = self._master.after(POLL_INTERVAL_MS, self._drain)

    def _apply(self, event: DownloadSnapshot | str) -> None:
        if self._window is None or not self._window.winfo_exists():
            self._window = _ProgressWindow(self._master, self._title)
        if isinstance(event, DownloadSnapshot):
            self._window.show_download(event)
        else:
            self._window.show_status(event)

    def _destroy_window(self) -> None:
        window, self._window = self._window, None
        if window is not None:
            with contextlib.suppress(tk.TclError):
                window.destroy()
