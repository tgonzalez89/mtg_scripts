import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from .card_grid import CardGrid, art_size_for
from .full_image_window import FullImageWindow, ImageWindowOptions
from .gui_dialogs import ExportChoiceDialog, GameSelectionDialog, ProgressDialog
from .printing_chooser import PrintingChooser
from .riftcodex_backend import RiftCodexBackend
from .scrollable_zoomable_text_frame import ScrollableZoomableTextFrame
from .scryfall_backend import ScryfallBackend
from .ui_queue import UiQueue
from .view_model import CardSlot

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PIL import Image

    from .card_backend import CardBackend
    from .models import CardPrint


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MTG Print Picker")
        self.geometry("900x700")
        self.minsize(400, 400)
        self.state("zoomed")
        self.backend: CardBackend = ScryfallBackend()
        self._backend_factories: dict[str, type[CardBackend]] = {
            "Magic: The Gathering": ScryfallBackend,
            "RiftBound": RiftCodexBackend,
        }
        self.current_game = "Magic: The Gathering"
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.slots: list[CardSlot] = []
        self.progress_dialog: ProgressDialog | None = None
        self.printing_chooser: PrintingChooser | None = None
        self.full_image_window: FullImageWindow | None = None
        self._ui = UiQueue(self)
        self._ui.start()
        self._build_layout()

    def destroy(self) -> None:
        self._close_full_image()
        self._close_printing_chooser()
        if self.card_grid.winfo_exists():
            self.card_grid.destroy()
        self._ui.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.backend.close()
        self.slots.clear()
        super().destroy()

    def _build_layout(self) -> None:
        self.main_panes = tk.PanedWindow(self, orient="vertical")
        self.main_panes.pack(fill="both", expand=True)

        self.top_frame = ttk.Frame(self.main_panes)
        self.main_panes.add(self.top_frame, minsize=200)
        self.text_frame = ScrollableZoomableTextFrame(self.top_frame)
        self.button_frame = ttk.Frame(self.top_frame)
        self.text_frame.grid(row=0, column=0, sticky="nsew")
        self.button_frame.grid(row=0, column=1, sticky="ns", padx=5, pady=5)
        self.top_frame.columnconfigure(0, weight=1)
        self.top_frame.rowconfigure(0, weight=1)
        self.text_widget = self.text_frame.text_widget

        self._build_buttons()
        self.card_grid = CardGrid(
            self.main_panes,
            backend=self.backend,
            on_choose=self._open_chooser,
            on_open_full_image=self._open_full_image,
        )
        self.main_panes.add(self.card_grid)

    def _build_buttons(self) -> None:
        ttk.Button(self.button_frame, text="Import", command=self._on_import).pack(fill="x", pady=5)
        ttk.Button(self.button_frame, text="Clear request cache", command=self._on_clear_request_cache).pack(
            fill="x", pady=5
        )
        ttk.Button(self.button_frame, text="Clear image cache", command=self._on_clear_image_cache).pack(
            fill="x", pady=5
        )
        ttk.Button(self.button_frame, text="Export list", command=self._on_export_list).pack(fill="x", pady=5)
        ttk.Button(self.button_frame, text="Download images", command=self._on_download_images).pack(fill="x", pady=5)

    # -- import -------------------------------------------------------------

    def _on_import(self) -> None:
        game = self._choose_game()
        if game is None:
            return
        if game != self.current_game:
            self.backend.close()
            self.backend = self._backend_factories[game]()
            self.current_game = game
        self.card_grid.set_backend(self.backend)

        raw_text = self.text_widget.get("1.0", "end").strip()
        if not raw_text:
            messagebox.showinfo("Import", "Enter at least one card name.")
            return
        self.slots = self._parse_input(raw_text)
        self.card_grid.clear()
        if self.backend.supports_progress:
            self._start_progress("Loading card data")
        self.card_grid.load_slots(self.slots, self._resolve_slots, self._load_slot_images)

    def _choose_game(self) -> str | None:
        dialog = GameSelectionDialog(self, self._backend_factories.keys())
        self.wait_window(dialog)
        return dialog.result

    def _parse_input(self, raw_text: str) -> list[CardSlot]:
        return [CardSlot(entry=self.backend.parse_line(line)) for line in raw_text.splitlines() if line.strip()]

    def _resolve_slots(self, slots: list[CardSlot]) -> None:
        """Resolve every slot in one batch, on a worker thread."""
        try:
            resolutions = self.backend.resolve([slot.entry for slot in slots], self._report_progress)
        finally:
            self._finish_progress()
        for slot, resolution in zip(slots, resolutions, strict=True):
            slot.resolved = resolution.card
            slot.error = resolution.error or (None if resolution.card else "Card not found")

    def _load_slot_images(self, slot: CardSlot, size: tuple[int, int]) -> None:
        card = slot.display_print
        if card is None:
            return
        slot.images = self.backend.load_thumbnails(card, size)

    # -- progress -----------------------------------------------------------

    def _start_progress(self, title: str) -> None:
        self._close_progress()
        self.progress_dialog = ProgressDialog(self, title)

    def _report_progress(self, message: str, current: int, total: int) -> None:
        """Report progress from a backend worker thread."""
        self._ui.post(self._update_progress, message, current, total)

    def _update_progress(self, message: str, current: int, total: int) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.update_progress(message, current, total)

    def _finish_progress(self) -> None:
        if self.progress_dialog is not None:
            self._ui.post(self._close_progress)

    def _close_progress(self) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.destroy()
            self.progress_dialog = None

    # -- windows ------------------------------------------------------------

    def _open_chooser(self, slot: CardSlot, viewer: FullImageWindow | None = None) -> None:
        def on_choose(updated: CardSlot) -> None:
            self._printing_chosen(updated)
            if isinstance(viewer, FullImageWindow):
                viewer.update_current_images(self.card_grid.get_full_images(updated))

        self._close_printing_chooser()
        self.printing_chooser = PrintingChooser(
            self,
            slot,
            self.backend,
            on_choose,
            on_open_full_image=self._open_full_image,
            on_close=self._on_printing_chooser_closed,
        )

    def _on_printing_chooser_closed(self, chooser: PrintingChooser) -> None:
        if self.printing_chooser is chooser:
            self.printing_chooser = None

    def _close_printing_chooser(self) -> None:
        if self.printing_chooser is not None:
            if self.printing_chooser.winfo_exists():
                self.printing_chooser.destroy()
            self.printing_chooser = None

    def _open_full_image(
        self,
        grid: CardGrid,
        images: Sequence[Image.Image | Sequence[Image.Image]],
        options: ImageWindowOptions,
    ) -> None:
        self._close_full_image()
        self.full_image_window = FullImageWindow(grid, images, options)
        self.full_image_window.protocol("WM_DELETE_WINDOW", self._close_full_image)

    def _close_full_image(self) -> None:
        if self.full_image_window is not None:
            window = self.full_image_window
            self.full_image_window = None
            if window.winfo_exists():
                window.destroy()

    def _printing_chosen(self, slot: CardSlot) -> None:
        """Reload the grid thumbnail for a slot whose printing just changed."""

        def load() -> None:
            size = art_size_for(self.card_grid.grid_zoom)
            self._load_slot_images(slot, size)
            slot.image_size = size
            self._ui.post(self.card_grid.refresh_slot, slot)

        slot.image_loading = True
        self.card_grid.refresh_slot(slot)
        self.executor.submit(load)

    # -- caches -------------------------------------------------------------

    def _on_clear_request_cache(self) -> None:
        self.backend.clear_json_cache()

    def _on_clear_image_cache(self) -> None:
        self.backend.clear_image_cache()

    # -- export -------------------------------------------------------------

    def _show_path_confirmation(self, title: str, message: str, path: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(path)
        self.update()
        messagebox.showinfo(title, f"{message}\nThe path has been copied to the clipboard.", parent=self)

    def _on_download_images(self) -> None:
        if not self.slots:
            messagebox.showinfo("Download images", "Import cards first.")
            return
        folder = filedialog.askdirectory(title="Choose folder for card images", parent=self)
        if not folder:
            return

        for index, slot in enumerate(self.slots, start=1):
            card = slot.display_print
            if card is not None:
                self.executor.submit(self._save_slot_images, folder, index, slot, card)
        self._show_path_confirmation("Download images", f"Downloading images to {folder}.", folder)

    def _save_slot_images(self, folder: str, index: int, slot: CardSlot, card: CardPrint) -> None:
        images = self.backend.load_images(card, high_quality=True)
        if not images:
            return
        base_name = self._safe_filename(slot.name)
        # Raw identifiers, not export syntax: the foil marker `*F*` and the
        # foil star are both illegal in Windows filenames.
        set_code = self._safe_filename(card.set_code)
        collector_number = self._safe_filename(card.collector_number)
        for copy_number in range(1, slot.quantity + 1):
            for face_index, image in enumerate(images, start=1):
                filename = (
                    f"{index:03d}_{copy_number:02d}_{base_name}_{set_code}_{collector_number}_face{face_index}.png"
                )
                image.save(Path(folder) / filename, format="PNG")

    def _on_export_list(self) -> None:
        if not self.slots:
            messagebox.showinfo("Export list", "Import cards first.")
            return

        # Grouping on the backend's own export text guarantees the result
        # re-imports cleanly: identical cards collapse into one quantified line.
        combined: dict[str, int] = {}
        for slot in self.slots:
            card = slot.display_print
            if card is None:
                continue  # the card was not found, so there is no printing to export
            card_text = self.backend.export_card_text(card, slot.entry)
            combined[card_text] = combined.get(card_text, 0) + slot.quantity
        if not combined:
            messagebox.showinfo("Export list", "None of the imported cards were found.")
            return
        lines = [f"{quantity} {card_text}" for card_text, quantity in combined.items()]
        export_text = "\n".join(lines) + "\n"

        dialog = ExportChoiceDialog(self)
        self.wait_window(dialog)
        if dialog.result == "clipboard":
            self.clipboard_clear()
            self.clipboard_append(export_text)
            self.update()
            return
        if dialog.result != "file":
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save card list",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        with Path(path).open("w", encoding="utf-8") as output_file:
            output_file.write(export_text)
        self._show_path_confirmation("Export list", f"Saved card list to {path}.", path)

    @staticmethod
    def _safe_filename(name: str) -> str:
        return "".join(character for character in name if character.isalnum() or character in " ._-").rstrip()


if __name__ == "__main__":
    App().mainloop()
