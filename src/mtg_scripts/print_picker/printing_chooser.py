from __future__ import annotations

import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import messagebox
from typing import TYPE_CHECKING, cast

from .card_grid import CardGrid
from .gui_dialogs import ProgressDialog

if TYPE_CHECKING:
    from collections.abc import Callable

    from PIL import Image

    from .card_backend import CardBackend, CardItem, CardRecord, ImagePair


class PrintingChooser(tk.Toplevel):
    def __init__(  # noqa: PLR0913, PLR0917
        self,
        master: tk.Misc,
        card_item: CardItem,
        backend: CardBackend,
        on_choose: Callable[[CardItem], None],
        on_open_full_image: Callable[..., None] | None = None,
        on_close: Callable[[PrintingChooser], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.title(f"Choose printing for {card_item['name']}")
        self.geometry("900x700")
        self.minsize(400, 400)
        self.state("zoomed")
        self.card_item = card_item
        self.backend = backend
        self.on_choose = on_choose
        self.on_open_full_image = on_open_full_image
        self.on_close = on_close
        self._closed = False
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
        on_close = self.on_close
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.card_grid.destroy()
        self.progress_dialog = None
        self.card_item = cast("CardItem", {})
        self.backend = None
        self.on_choose = None
        self.on_open_full_image = None
        self.on_close = None
        super().destroy()
        if on_close:
            on_close(self)

    def _load_printings(self) -> None:
        card = self.card_item.get("card")
        if not card:
            self._post(self.card_grid.set_items, [])
            self._post(self._close_progress)
            return
        if TYPE_CHECKING:
            assert self.backend is not None
        try:
            printings = self.backend.lookup_printings(card, self._report_progress)
            self._post(self._set_printings, printings)
        except (OSError, RuntimeError, ValueError) as error:
            self._post(self._show_error, error)
        finally:
            self._post(self._close_progress)

    def _post(self, callback: Callable[..., None], *args: object) -> None:
        if not self._closed:
            self.after(0, callback, *args)

    def _report_progress(self, message: str, current: int, total: int) -> None:
        self._post(self._update_progress, message, current, total)

    def _update_progress(self, message: str, current: int, total: int) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.update_progress(message, current, total)

    def _close_progress(self) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.destroy()
            self.progress_dialog = None

    def _set_printings(self, printings: list[CardRecord]) -> None:
        if TYPE_CHECKING:
            assert self.backend is not None
        items: list[CardItem] = []
        for printing in printings:
            printing["name"] = self.backend.card_name(printing) or self.card_item["name"]
            printing["display_name"] = self.backend.printing_display_name(printing)
            items.append(cast("CardItem", printing))
        self.card_grid.load_items(items, self._load_printing_metadata, self._load_printing_image)
        self.backend.release_lookup_memory()

    def _load_printing_metadata(self, printing: CardRecord, callback: Callable[[CardRecord], None]) -> None:
        callback(printing)

    def _load_printing_image(self, printing: CardRecord, callback: Callable[[CardRecord], None]) -> None:
        if TYPE_CHECKING:
            assert self.backend is not None
        try:
            images = self._available_images(self.backend.load_card_images(printing))
            printing["images"] = images
            printing["image"] = images[0] if images else None
        except (OSError, ValueError) as error:
            printing["error"] = str(error)
        callback(printing)

    @staticmethod
    def _available_images(image_pair: ImagePair) -> tuple[Image.Image, ...]:
        return tuple(image for image in image_pair if image is not None)

    def _show_error(self, error: Exception) -> None:
        messagebox.showerror("Printings", str(error), parent=self)

    def _choose(self, printing: CardRecord) -> None:
        if TYPE_CHECKING:
            assert self.on_choose is not None
        self.card_item["chosen_print"] = printing
        self.on_choose(self.card_item)
        self.destroy()
