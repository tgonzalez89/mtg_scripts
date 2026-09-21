from __future__ import annotations

import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import messagebox
from typing import TYPE_CHECKING

from .card_grid import CardGrid
from .gui_dialogs import ProgressDialog
from .ui_queue import UiQueue
from .view_model import CardSlot, printing_slot

if TYPE_CHECKING:
    from collections.abc import Callable

    from .card_backend import CardBackend
    from .models import CardPrint


class PrintingChooser(tk.Toplevel):
    def __init__(  # noqa: PLR0913, PLR0917
        self,
        master: tk.Misc,
        slot: CardSlot,
        backend: CardBackend,
        on_choose: Callable[[CardSlot], None],
        on_open_full_image: Callable[..., None] | None = None,
        on_close: Callable[[PrintingChooser], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.title(f"Choose printing for {slot.name}")
        self.geometry("900x700")
        self.minsize(400, 400)
        self.state("zoomed")
        self.slot = slot
        self.backend: CardBackend | None = backend
        self.on_choose: Callable[[CardSlot], None] | None = on_choose
        self.on_open_full_image = on_open_full_image
        self.on_close = on_close
        self._closed = False
        self._ui = UiQueue(self)
        self._ui.start()
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.progress_dialog = ProgressDialog(self, "Loading card data") if backend.supports_progress else None
        self.card_grid = CardGrid(
            self,
            backend=backend,
            chooser_mode=True,
            on_choose=self._choose,
            on_open_full_image=on_open_full_image,
        )
        self.card_grid.pack(fill="both", expand=True)
        self.executor.submit(self._load_printings)

    def destroy(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._ui.stop()
        on_close = self.on_close
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.card_grid.destroy()
        self.progress_dialog = None
        self.backend = None
        self.on_choose = None
        self.on_open_full_image = None
        self.on_close = None
        super().destroy()
        if on_close:
            on_close(self)

    def _load_printings(self) -> None:
        backend = self.backend
        card = self.slot.display_print
        if backend is None or card is None:
            self._post(self.card_grid.set_slots, [])
            self._post(self._close_progress)
            return
        try:
            printings = backend.printings_of(card, self._report_progress)
            self._post(self._show_printings, printings)
        except (OSError, RuntimeError, ValueError) as error:
            self._post(self._show_error, error)
        finally:
            self._post(self._close_progress)

    def _post(self, callback: Callable[..., None], *args: object) -> None:
        """Run `callback` on the UI thread; safe to call from a worker."""
        if not self._closed:
            self._ui.post(callback, *args)

    def _report_progress(self, message: str, current: int, total: int) -> None:
        self._post(self._update_progress, message, current, total)

    def _update_progress(self, message: str, current: int, total: int) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.update_progress(message, current, total)

    def _close_progress(self) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.destroy()
            self.progress_dialog = None

    def _show_printings(self, printings: list[CardPrint]) -> None:
        slots = [printing_slot(printing, self.slot.name) for printing in printings]
        self.card_grid.load_slots(slots, _already_resolved, self._load_printing_image)

    def _load_printing_image(self, slot: CardSlot, size: tuple[int, int]) -> None:
        backend = self.backend
        card = slot.display_print
        if backend is None or card is None:
            return
        try:
            slot.images = backend.load_thumbnails(card, size)
        except (OSError, ValueError) as error:
            slot.error = str(error)

    def _show_error(self, error: Exception) -> None:
        messagebox.showerror("Printings", str(error), parent=self)

    def _choose(self, slot: CardSlot) -> None:
        if self.on_choose is None:
            return
        self.slot.chosen = slot.display_print
        # The chosen printing's art differs from the one already loaded, so drop
        # the stale thumbnails and let the grid reload them.
        self.slot.release_images()
        self.on_choose(self.slot)
        self.destroy()


def _already_resolved(_slots: list[CardSlot]) -> None:
    """Accept printings that already arrived fully resolved."""
