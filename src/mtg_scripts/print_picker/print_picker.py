import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from .card_grid import CardGrid
from .full_image_window import FullImageWindow, ImageWindowOptions
from .gui_dialogs import ExportChoiceDialog, GameSelectionDialog, ProgressDialog
from .printing_chooser import PrintingChooser
from .riftcodex_backend import RiftCodexBackend
from .scrollable_zoomable_text_frame import ScrollableZoomableTextFrame
from .scryfall_backend import ScryfallBackend

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from PIL import Image

    from .card_backend import CardBackend, CardItem, CardRecord, ImagePair


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MTG Print Picker")
        self.geometry("900x700")
        self.minsize(400, 400)
        self.state("zoomed")
        self.backend = ScryfallBackend()
        self._backend_factories: dict[str, type[CardBackend]] = {
            "Magic: The Gathering": ScryfallBackend,
            "RiftBound": RiftCodexBackend,
        }
        self.current_game = "Magic: The Gathering"
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.items: list[CardItem] = []
        self.progress_dialog = None
        self.printing_chooser = None
        self.full_image_window = None
        self._build_layout()

    def destroy(self) -> None:
        self._close_full_image()
        self._close_printing_chooser()
        if self.card_grid.winfo_exists():
            self.card_grid.destroy()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.backend.release_memory()
        self.backend.session.close()
        self.items.clear()
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

    def _on_import(self) -> None:
        game = self._choose_game()
        if game is None:
            return
        if game != self.current_game:
            old_backend = self.backend
            old_backend.release_memory()
            old_backend.session.close()
            self.backend = self._backend_factories[game]()
            self.current_game = game
        self.card_grid.set_backend(self.backend)

        raw_text = self.text_widget.get("1.0", "end").strip()
        if not raw_text:
            messagebox.showinfo("Import", "Enter at least one card name.")
            return
        self.items = self._parse_input(raw_text)
        self.card_grid.clear()
        self.backend.release_lookup_memory()
        if self.backend.supports_progress:
            self._start_progress("Loading card data")
        self.card_grid.load_items(self.items, self._load_card, self._load_card_images, self._load_cards)

    def _choose_game(self) -> str | None:
        dialog = GameSelectionDialog(self, self._backend_factories.keys())
        self.wait_window(dialog)
        return dialog.result

    def _load_card(self, item: CardItem, callback: Callable[[CardItem], None]) -> None:
        try:
            card = self.backend.lookup_card(item["name"], item.get("printing_hint"))
        except (OSError, ValueError) as error:
            item["error"] = str(error)
        else:
            self._set_card_result(item, card)
        callback(item)

    def _load_cards(self, items: list[CardItem], callback: Callable[[CardItem], None]) -> None:
        try:
            results = self.backend.lookup_cards(items, self._report_progress)
        except (OSError, RuntimeError, ValueError) as error:
            results = [(None, error)] * len(items)
        finally:
            self._finish_progress()
        for item, (card, error) in zip(items, results, strict=False):
            if error:
                item["error"] = str(error)
            else:
                self._set_card_result(item, card)
            callback(item)

    def _start_progress(self, title: str) -> None:
        self._close_progress()
        self.progress_dialog = ProgressDialog(self, title)

    def _report_progress(self, message: str, current: int, total: int) -> None:
        self.after(0, self._update_progress, message, current, total)

    def _update_progress(self, message: str, current: int, total: int) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.update_progress(message, current, total)

    def _finish_progress(self) -> None:
        if self.progress_dialog is not None:
            self.after(0, self._close_progress)

    def _close_progress(self) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.destroy()
            self.progress_dialog = None

    def _set_card_result(self, item: CardItem, card: CardRecord | None) -> None:
        item["card"] = card
        item["default_card"] = card
        card_name = self.backend.card_name(card) if card else ""
        if card_name:
            item["name"] = card_name

    def _load_card_images(self, item: CardItem, callback: Callable[[CardItem], None]) -> None:
        try:
            card = item.get("card")
            images = self._available_images(self.backend.load_card_images(card)) if card else ()
            item["images"] = images
            item["image"] = images[0] if images else None
        except (OSError, ValueError) as error:
            item["error"] = str(error)
        callback(item)

    def _open_chooser(self, item: CardItem, viewer: FullImageWindow | None = None) -> None:
        def on_choose(updated_item: CardItem) -> None:
            self._printing_chosen(updated_item)
            if isinstance(viewer, FullImageWindow):
                viewer.update_current_images(self.card_grid.get_full_images(updated_item))

        self._close_printing_chooser()
        self.printing_chooser = PrintingChooser(
            self,
            item,
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

    def _printing_chosen(self, item: CardItem) -> None:
        printing = item.get("chosen_print")
        if not printing:
            return
        item["image"] = printing.get("image")
        item["images"] = tuple(printing.get("images") or (item["image"],))
        self.card_grid.refresh_item(item)

    def _parse_input(self, raw_text: str) -> list[CardItem]:
        return [self.backend.parse_card_line(line) for line in raw_text.splitlines() if line.strip()]

    def _on_clear_request_cache(self) -> None:
        self.backend.clear_json_cache()

    def _on_clear_image_cache(self) -> None:
        self.backend.clear_image_cache()

    def _show_path_confirmation(self, title: str, message: str, path: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(path)
        self.update()
        messagebox.showinfo(title, f"{message}\nThe path has been copied to the clipboard.", parent=self)

    def _on_download_images(self) -> None:
        if not self.items:
            messagebox.showinfo("Download images", "Import cards first.")
            return
        folder = filedialog.askdirectory(title="Choose folder for card images", parent=self)
        if not folder:
            return

        for item_index, item in enumerate(self.card_grid.get_display_items(), start=1):
            source = item.get("chosen_print") or item.get("default_card") or item.get("card")
            if not source:
                continue
            self.executor.submit(self._save_item_images, folder, item_index, item, source)
        self._show_path_confirmation("Download images", f"Downloading images to {folder}.", folder)

    def _on_export_list(self) -> None:
        if not self.items:
            messagebox.showinfo("Export list", "Import cards first.")
            return

        combined: dict[tuple[str, str, str], int] = {}
        for item in self.card_grid.get_display_items():
            source = item.get("chosen_print") or item.get("default_card") or item.get("card")
            set_code, collector_number = (
                self.backend.printing_export_fields(source, item.get("printing_hint")) if source else ("", "")
            )
            key = (item["name"], set_code, collector_number)
            combined[key] = combined.get(key, 0) + item["quantity"]
        lines = [
            f"{quantity} {name} ({set_code}) {collector_number}"
            for (name, set_code, collector_number), quantity in combined.items()
        ]
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

    def _save_item_images(self, folder: str, item_index: int, item: CardItem, source: CardRecord) -> None:
        images = self._available_images(self.backend.load_card_images(source, high_quality=True))
        if not images:
            return

        base_name = self._safe_filename(item["name"])
        set_code, collector_number = self.backend.printing_export_fields(source)
        for copy_number in range(1, item["quantity"] + 1):
            for face_index, image in enumerate(images, start=1):
                filename = (
                    f"{item_index:03d}_{copy_number:02d}_{base_name}_{set_code}_{collector_number}_face{face_index}.png"
                )
                image.save(Path(folder) / filename, format="PNG")

    @staticmethod
    def _available_images(image_pair: ImagePair) -> tuple[Image.Image, ...]:
        return tuple(image for image in image_pair if image is not None)

    @staticmethod
    def _safe_filename(name: str) -> str:
        return "".join(character for character in name if character.isalnum() or character in " ._-").rstrip()


if __name__ == "__main__":
    App().mainloop()
