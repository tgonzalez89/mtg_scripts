import os
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, messagebox, ttk

from print_picker.card_grid import CardGrid
from print_picker.riftcodex_backend import RiftCodexBackend
from print_picker.scrollable_zoomable_text_frame import ScrollableZoomableTextFrame
from print_picker.scryfall_backend import ScryfallBackend


class GameSelectionDialog(tk.Toplevel):
    def __init__(self, master, games):
        super().__init__(master)
        self.title("Choose card game")
        self.resizable(False, False)
        self.result = None
        self.transient(master)

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

    def _select(self):
        selection = self.game_list.curselection()
        if selection:
            self.result = self.game_list.get(selection[0])
            self.destroy()


class ExportChoiceDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Export card list")
        self.resizable(False, False)
        self.result = None
        self.transient(master)

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

    def _finish(self, result):
        self.result = result
        self.destroy()


class PrintingChooser(tk.Toplevel):
    def __init__(self, master, card_item, backend, on_choose):
        super().__init__(master)
        self.title(f"Choose printing for {card_item['name']}")
        self.geometry("900x700")
        self.minsize(400, 400)
        self.state("zoomed")
        self.card_item = card_item
        self.backend = backend
        self.on_choose = on_choose
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.grid = CardGrid(self, backend=backend, chooser_mode=True, on_choose=self._choose)
        self.grid.pack(fill="both", expand=True)
        self.executor.submit(self._load_printings)

    def _load_printings(self):
        card = self.card_item.get("card")
        if not card:
            self.after(0, self.grid.set_items, [])
            return
        try:
            printings = self.backend.get_printings(card)
            self.after(0, self._set_printings, printings)
        except (OSError, ValueError) as error:
            self.after(0, self._show_error, error)

    def _set_printings(self, printings):
        for printing in printings:
            printing["name"] = self.backend.card_name(printing) or self.card_item["name"]
            printing["display_name"] = self.backend.printing_display_name(printing)
        self.grid.load_items(printings, self._load_printing_metadata, self._load_printing_image)

    def _load_printing_metadata(self, printing, callback):
        callback(printing)

    def _load_printing_image(self, printing, callback):
        try:
            image = self.backend.load_card_image(printing)
            printing["images"] = [image] if image else []
            printing["image"] = image
        except (OSError, ValueError) as error:
            printing["error"] = str(error)
        callback(printing)

    def _show_error(self, error):
        messagebox.showerror("Printings", str(error), parent=self)

    def _choose(self, printing):
        self.card_item["chosen_print"] = printing
        self.on_choose(self.card_item)
        self.destroy()


class App(tk.Tk):
    def __init__(self):
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
        self._build_layout()

    def _build_layout(self):
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
        self.grid = CardGrid(self.main_panes, backend=self.backend, on_choose=self._open_chooser)
        self.main_panes.add(self.grid)

    def _build_buttons(self):
        ttk.Button(self.button_frame, text="Import", command=self._on_import).pack(fill="x", pady=5)
        ttk.Button(self.button_frame, text="Clear request cache", command=self._on_clear_request_cache).pack(
            fill="x", pady=5
        )
        ttk.Button(self.button_frame, text="Clear image cache", command=self._on_clear_image_cache).pack(
            fill="x", pady=5
        )
        ttk.Button(self.button_frame, text="Export list", command=self._on_export_list).pack(fill="x", pady=5)
        ttk.Button(self.button_frame, text="Download images", command=self._on_download_images).pack(fill="x", pady=5)

    def _on_import(self):
        game = self._choose_game()
        if game is None:
            return
        self.backend = self.backends[game]
        self.grid.set_backend(self.backend)

        raw_text = self.text_widget.get("1.0", "end").strip()
        if not raw_text:
            messagebox.showinfo("Import", "Enter at least one card name.")
            return
        self.items = self._parse_input(raw_text)
        self.grid.load_items(self.items, self._load_card, self._load_card_image)

    def _choose_game(self):
        dialog = GameSelectionDialog(self, self.backends.keys())
        self.wait_window(dialog)
        return dialog.result

    def _load_card(self, item, callback):
        try:
            card = self.backend.search_card(item["name"], item.get("printing_hint"))
            item["card"] = card
            item["default_card"] = card
            card_name = self.backend.card_name(card) if card else ""
            if card_name:
                item["name"] = card_name
        except (OSError, ValueError) as error:
            item["error"] = str(error)
        callback(item)

    def _load_card_image(self, item, callback):
        try:
            card = item.get("card")
            image = self.backend.load_card_image(card) if card else None
            item["images"] = [image] if image else []
            item["image"] = image
        except (OSError, ValueError) as error:
            item["error"] = str(error)
        callback(item)

    def _open_chooser(self, item, viewer=None):
        def on_choose(updated_item):
            self._printing_chosen(updated_item)
            if viewer is not None:
                viewer.update_current_images(self.grid.get_full_images(updated_item))

        PrintingChooser(self, item, self.backend, on_choose)

    def _printing_chosen(self, item):
        printing = item.get("chosen_print")
        if not printing:
            return
        item["image"] = printing.get("image")
        item["images"] = printing.get("images") or [item["image"]]
        self.grid.refresh_item(item)

    def _parse_input(self, raw_text):
        return [self.backend.parse_card_line(line) for line in raw_text.splitlines() if line.strip()]

    def _on_clear_request_cache(self):
        self.backend.clear_json_cache()

    def _on_clear_image_cache(self):
        self.backend.clear_image_cache()

    def _show_path_confirmation(self, title, message, path):
        self.clipboard_clear()
        self.clipboard_append(path)
        self.update()
        messagebox.showinfo(title, f"{message}\nThe path has been copied to the clipboard.", parent=self)

    def _on_download_images(self):
        if not self.items:
            messagebox.showinfo("Download images", "Import cards first.")
            return
        folder = filedialog.askdirectory(title="Choose folder for card images", parent=self)
        if not folder:
            return

        for item_index, item in enumerate(self.grid.get_display_items(), start=1):
            source = item.get("chosen_print") or item.get("default_card") or item.get("card")
            if not source:
                continue
            self.executor.submit(self._save_item_images, folder, item_index, item, source)
        self._show_path_confirmation("Download images", f"Downloading images to {folder}.", folder)

    def _on_export_list(self):
        if not self.items:
            messagebox.showinfo("Export list", "Import cards first.")
            return

        combined = {}
        for item in self.grid.get_display_items():
            source = item.get("chosen_print") or item.get("default_card") or item.get("card")
            set_code, collector_number = (
                self.backend.printing_export_fields(source, item.get("printing_hint"))
                if source
                else ("", "")
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
        with open(path, "w", encoding="utf-8") as output_file:
            output_file.write(export_text)
        self._show_path_confirmation("Export list", f"Saved card list to {path}.", path)

    def _save_item_images(self, folder, item_index, item, source):
        image = self.backend.load_card_image(source, high_quality=True)
        if not image:
            return

        base_name = self._safe_filename(item["name"])
        set_code, collector_number = self.backend.printing_export_fields(source)
        for copy_number in range(1, item["quantity"] + 1):
            filename = f"{item_index:03d}_{copy_number:02d}_{base_name}_{set_code}_{collector_number}_face1.png"
            image.save(os.path.join(folder, filename), format="PNG")

    @staticmethod
    def _safe_filename(name):
        return "".join(character for character in name if character.isalnum() or character in " ._-").rstrip()


if __name__ == "__main__":
    App().mainloop()
