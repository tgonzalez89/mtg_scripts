import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, cast

from .card_grid import CardGrid
from .full_image_window import FullImageWindow
from .riftcodex_backend import RiftCodexBackend
from .scrollable_zoomable_text_frame import ScrollableZoomableTextFrame
from .scryfall_backend import ScryfallBackend

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from PIL import Image

    from .card_backend import CardBackend, CardItem, CardRecord, ImagePair


class GameSelectionDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, games: Iterable[str]) -> None:
        super().__init__(master)
        self.title("Choose card game")
        self.resizable(width=False, height=False)
        self.result = None
        self.transient(cast("tk.Tk", master))

        games = list(games)

        ttk.Label(self, text="Choose the card game to import:").pack(padx=20, pady=(18, 8))
        self.game_list = tk.Listbox(self, height=min(8, len(games)), exportselection=False)
        self.game_list.pack(fill="both", expand=True, padx=20)
        for game in games:
            self.game_list.insert(tk.END, game)
        self.game_list.selection_set(0)
        self.game_list.activate(0)
        self.game_list.bind("<Double-1>", lambda _event: self._select())

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=20, pady=15)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(button_frame, text="Choose", command=self._select).pack(side="right", padx=(0, 8))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()
        self.game_list.focus_set()

    def _select(self) -> None:
        selection = self.game_list.curselection()
        if selection:
            self.result = self.game_list.get(selection[0])
            self.destroy()


class ExportChoiceDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("Export card list")
        self.resizable(width=False, height=False)
        self.result = None
        self.transient(cast("tk.Tk", master))

        ttk.Label(self, text="How would you like to export the card list?").pack(padx=20, pady=(18, 12))
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=20, pady=(0, 18))
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(button_frame, text="Copy to clipboard", command=lambda: self._finish("clipboard")).pack(
            side="right", padx=(0, 8)
        )
        ttk.Button(button_frame, text="Save to file", command=lambda: self._finish("file")).pack(
            side="right", padx=(0, 8)
        )
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()

    def _finish(self, result: str) -> None:
        self.result = result
        self.destroy()


class ProgressDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, title: str) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(width=False, height=False)
        self.transient(cast("tk.Tk", master))
        self.status_label = ttk.Label(self, text="Starting...")
        self.status_label.pack(padx=20, pady=(18, 8))
        self.progress_bar = ttk.Progressbar(self, mode="indeterminate", length=320)
        self.progress_bar.pack(padx=20, pady=(0, 18))
        self.progress_bar.start(10)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.update_idletasks()

    def update_progress(self, message: str, current: int, total: int) -> None:
        self.status_label.configure(text=message)
        if total > 0:
            if self.progress_bar.cget("mode") != "determinate":
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
            self.progress_bar.configure(maximum=total, value=current)
        elif self.progress_bar.cget("mode") != "indeterminate":
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(10)


class PrintingChooser(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        card_item: CardItem,
        backend: CardBackend,
        on_choose: Callable[[CardItem], None],
    ) -> None:
        super().__init__(master)
        self.title(f"Choose printing for {card_item['name']}")
        self.geometry("900x700")
        self.minsize(400, 400)
        self.state("zoomed")
        self.card_item = card_item
        self.backend = backend
        self.on_choose = on_choose
        self._closed = False
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.progress_dialog = ProgressDialog(self, "Loading card data") if backend.supports_progress else None
        self.card_grid = CardGrid(self, backend=backend, chooser_mode=True, on_choose=self._choose)
        self.card_grid.pack(fill="both", expand=True)
        self.executor.submit(self._load_printings)

    def destroy(self) -> None:
        self._closed = True
        self.executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()

    def _load_printings(self) -> None:
        card = self.card_item.get("card")
        if not card:
            self._post(self.card_grid.set_items, [])
            self._post(self._close_progress)
            return
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
        items: list[CardItem] = []
        for printing in printings:
            printing["name"] = self.backend.card_name(printing) or self.card_item["name"]
            printing["display_name"] = self.backend.printing_display_name(printing)
            items.append(cast("CardItem", printing))
        self.card_grid.load_items(items, self._load_printing_metadata, self._load_printing_image)

    def _load_printing_metadata(self, printing: CardRecord, callback: Callable[[CardRecord], None]) -> None:
        callback(printing)

    def _load_printing_image(self, printing: CardRecord, callback: Callable[[CardRecord], None]) -> None:
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
        self.card_item["chosen_print"] = printing
        self.on_choose(self.card_item)
        self.destroy()


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MTG Print Picker")
        self.geometry("900x700")
        self.minsize(400, 400)
        self.state("zoomed")
        self.backend = ScryfallBackend()
        self.backends = {
            "Magic: The Gathering": self.backend,
            "RiftBound": RiftCodexBackend(),
        }
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.items = []
        self.progress_dialog = None
        self._build_layout()

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
        self.card_grid = CardGrid(self.main_panes, backend=self.backend, on_choose=self._open_chooser)
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
        self.backend = self.backends[game]
        self.card_grid.set_backend(self.backend)

        raw_text = self.text_widget.get("1.0", "end").strip()
        if not raw_text:
            messagebox.showinfo("Import", "Enter at least one card name.")
            return
        self.items = self._parse_input(raw_text)
        if self.backend.supports_progress:
            self._start_progress("Loading card data")
        self.card_grid.load_items(self.items, self._load_card, self._load_card_images, self._load_cards)

    def _choose_game(self) -> str | None:
        dialog = GameSelectionDialog(self, self.backends.keys())
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

    def _open_chooser(self, item: CardItem, viewer: object | None = None) -> None:
        def on_choose(updated_item: CardItem) -> None:
            self._printing_chosen(updated_item)
            if isinstance(viewer, FullImageWindow):
                viewer.update_current_images(self.card_grid.get_full_images(updated_item))

        PrintingChooser(self, item, self.backend, on_choose)

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

        combined = {}
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
