"""Pluggable progress reporting for Scryfall downloads, database builds, and API activity."""

from __future__ import annotations

import shutil
import sys
import threading
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, TextIO, override

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

DEFAULT_RENDER_INTERVAL = 0.1
_BYTE_UNITS = ("B", "KiB", "MiB", "GiB", "TiB")
_BYTES_PER_UNIT = 1024


@dataclass(frozen=True, slots=True)
class DownloadSnapshot:
    """One observation of a running download."""

    description: str
    source: str
    current: int
    total: int
    bytes_per_second: float
    finished: bool = False

    @property
    def fraction(self) -> float | None:
        """Return completion in `[0, 1]`, or `None` when the size is unknown."""
        if self.total <= 0:
            return None
        return min(1.0, self.current / self.total)


def format_bytes(value: float) -> str:
    amount = float(value)
    for unit in _BYTE_UNITS:
        if amount < _BYTES_PER_UNIT or unit == _BYTE_UNITS[-1]:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= _BYTES_PER_UNIT
    return f"{amount:.1f} {_BYTE_UNITS[-1]}"


def describe_transfer(snapshot: DownloadSnapshot) -> str:
    """Return `done/total (pct) at speed` text shared by every indicator."""
    size = format_bytes(snapshot.current)
    if snapshot.total > 0:
        size = f"{size} / {format_bytes(snapshot.total)} ({(snapshot.fraction or 0.0) * 100:.0f}%)"
    return f"{size} at {format_bytes(snapshot.bytes_per_second)}/s"


class ProgressIndicator(ABC):
    """Collect download/status events from any thread and hand throttled snapshots to a renderer.

    Subclasses decide how snapshots are displayed; the service decides when they happen.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        render_interval: float = DEFAULT_RENDER_INTERVAL,
    ) -> None:
        self._clock = clock
        self._render_interval = render_interval
        self._lock = threading.Lock()

    @contextmanager
    def download(self, description: str, source: str) -> Generator[Callable[[int, int], None]]:
        """Track one download; yields an `(current, total)` callback for the transfer loop."""
        started = self._clock()
        last_render = -float("inf")
        latest = DownloadSnapshot(description, source, 0, 0, 0.0)

        def on_progress(current: int, total: int) -> None:
            nonlocal last_render, latest
            now = self._clock()
            elapsed = now - started
            latest = DownloadSnapshot(description, source, current, total, current / elapsed if elapsed > 0 else 0.0)
            if now - last_render >= self._render_interval or (total > 0 and current >= total):
                last_render = now
                with self._lock:
                    self.render_download(latest)

        with self._lock:
            self.render_download(latest)
        try:
            yield on_progress
        finally:
            elapsed = self._clock() - started
            final = DownloadSnapshot(
                description,
                source,
                latest.current,
                latest.total,
                latest.current / elapsed if elapsed > 0 else latest.bytes_per_second,
                finished=True,
            )
            with self._lock:
                self.render_download(final)

    def status(self, message: str) -> None:
        """Report an activity without a measurable size (database build, API query, retry wait)."""
        with self._lock:
            self.render_status(message)

    def idle(self) -> None:
        """Signal that the current batch of activity has ended."""
        with self._lock:
            self.render_idle()

    def close(self) -> None:  # noqa: B027
        """Release any display resources."""

    @abstractmethod
    def render_download(self, snapshot: DownloadSnapshot) -> None:
        """Display a download snapshot; `snapshot.finished` marks its last update."""

    @abstractmethod
    def render_status(self, message: str) -> None:
        """Display an indeterminate activity message."""

    @abstractmethod
    def render_idle(self) -> None:
        """Hide or finalize the display."""


class SilentProgressIndicator(ProgressIndicator):
    """Discard every event; the default when the caller does not pick an indicator."""

    @override
    def render_download(self, snapshot: DownloadSnapshot) -> None:
        pass

    @override
    def render_status(self, message: str) -> None:
        pass

    @override
    def render_idle(self) -> None:
        pass


class TerminalProgressIndicator(ProgressIndicator):
    """Draw a single in-place progress line on a terminal; log plain lines when not a TTY."""

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        bar_width: int = 30,
        clock: Callable[[], float] = time.monotonic,
        render_interval: float = DEFAULT_RENDER_INTERVAL,
    ) -> None:
        super().__init__(clock=clock, render_interval=render_interval)
        self._stream = stream if stream is not None else sys.stderr
        self._bar_width = bar_width
        self._interactive = bool(getattr(self._stream, "isatty", lambda: False)())
        self._line_open = False
        self._last_status: str | None = None

    @override
    def render_download(self, snapshot: DownloadSnapshot) -> None:
        self._last_status = None
        if not self._interactive:
            if snapshot.finished:
                self._write_line(f"{snapshot.description} ({snapshot.source}): done, {describe_transfer(snapshot)}")
            elif snapshot.current == 0:
                self._write_line(f"{snapshot.description} ({snapshot.source})...")
            return
        line = f"{snapshot.description} ({snapshot.source}) {self._bar(snapshot)} {describe_transfer(snapshot)}"
        width = shutil.get_terminal_size(fallback=(120, 24)).columns - 1
        if len(line) > width:
            line = line[: max(0, width - 3)] + "..."
        self._stream.write("\r" + line.ljust(width))
        self._line_open = True
        if snapshot.finished:
            self._end_line()
        self._stream.flush()

    @override
    def render_status(self, message: str) -> None:
        if message == self._last_status:
            return
        self._last_status = message
        self._end_line()
        self._write_line(message)

    @override
    def render_idle(self) -> None:
        self._last_status = None
        self._end_line()
        self._stream.flush()

    def _bar(self, snapshot: DownloadSnapshot) -> str:
        fraction = snapshot.fraction
        if fraction is None:
            return "[" + "?" * self._bar_width + "]"
        filled = round(fraction * self._bar_width)
        return "[" + "#" * filled + "." * (self._bar_width - filled) + "]"

    def _write_line(self, text: str) -> None:
        self._stream.write(text + "\n")
        self._stream.flush()

    def _end_line(self) -> None:
        if self._line_open:
            self._stream.write("\n")
            self._line_open = False
