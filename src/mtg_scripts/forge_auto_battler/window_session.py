"""Per-run owner for the focused Forge window reference."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ForgeWindowSession:
    window: object | None = None

    def require_window(self) -> object:
        if self.window is None:
            message = "Forge window has not been focused."
            raise RuntimeError(message)
        return self.window
