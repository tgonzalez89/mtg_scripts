import os
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, messagebox, ttk

from print_picker.card_grid import CardGrid
from print_picker.scrollable_zoomable_text_frame import ScrollableZoomableTextFrame
from print_picker.scryfall_backend import ScryfallBackend


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
            printings = self.backend.get_printings(card.get("oracle_id"))
            self.after(0, self._set_printings, printings)
        except (OSError, ValueError) as error:
            self.after(0, self._show_error, error)

    def _set_printings(self, printings):
        for printing in printings:
            printing["name"] = self.card_item["name"]
            printing["display_name"] = (
                f"{printing.get('set_name', '')} ({printing.get('set', '')}) #{printing.get('collector_number', '')}"
            )
        self.grid.load_items(printings, self._load_printing)

    def _load_printing(self, printing, callback):
        try:
            image_urls = self.backend.image_urls(printing)
            printing["images"] = [self.backend.get_image(url) for url in image_urls]
            printing["image"] = printing["images"][0] if printing["images"] else None
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
        raw_text = self.text_widget.get("1.0", "end").strip()
        if not raw_text:
            messagebox.showinfo("Import", "Enter at least one card name.")
            return
        self.items = self._parse_input(raw_text)
        self.grid.load_items(self.items, self._load_card)

    def _load_card(self, item, callback):
        try:
            card = self.backend.search_card(item["name"])
            item["card"] = card
            item["default_card"] = card
            image_urls = self.backend.image_urls(card) if card else []
            item["images"] = [self.backend.get_image(url) for url in image_urls]
            item["image"] = item["images"][0] if item["images"] else None
        except (OSError, ValueError) as error:
            item["error"] = str(error)
        callback(item)

    def _open_chooser(self, item, viewer=None):
        def on_choose(updated_item):
            self._printing_chosen(updated_item)
            if viewer is not None:
                viewer.update_current_images(updated_item.get("images") or [updated_item["image"]])

        PrintingChooser(self, item, self.backend, on_choose)

    def _printing_chosen(self, item):
        printing = item.get("chosen_print")
        if not printing:
            return
        item["image"] = printing.get("image")
        item["images"] = printing.get("images") or [item["image"]]
        self.grid.refresh_item(item)

    @staticmethod
    def _parse_input(raw_text):
        items = []
        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            quantity, name = 1, line
            if len(parts) == 2 and parts[0].isdigit():
                quantity, name = int(parts[0]), parts[1].strip()
            items.append({"quantity": quantity, "name": name})
        return items

    def _on_clear_request_cache(self):
        self.backend.clear_json_cache()

    def _on_clear_image_cache(self):
        self.backend.clear_image_cache()

    def _on_download_images(self):
        if not self.items:
            messagebox.showinfo("Download images", "Import cards first.")
            return
        folder = filedialog.askdirectory(title="Choose folder for card images", parent=self)
        if not folder:
            return

        for item_index, item in enumerate(self.items, start=1):
            source = item.get("chosen_print") or item.get("default_card") or item.get("card")
            if not source:
                continue
            self.executor.submit(self._save_item_images, folder, item_index, item, source)
        messagebox.showinfo("Download images", f"Downloading images to {folder}.", parent=self)

    def _on_export_list(self):
        if not self.items:
            messagebox.showinfo("Export list", "Import cards first.")
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save card list",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        combined = {}
        for item in self.items:
            source = item.get("chosen_print") or item.get("default_card") or item.get("card")
            set_code = source.get("set", "") if source else ""
            collector_number = source.get("collector_number", "") if source else ""
            key = (item["name"], set_code, collector_number)
            combined[key] = combined.get(key, 0) + item["quantity"]
        lines = [
            f"{quantity} {name} ({set_code}) {collector_number}"
            for (name, set_code, collector_number), quantity in combined.items()
        ]
        with open(path, "w", encoding="utf-8") as output_file:
            output_file.write("\n".join(lines) + "\n")
        messagebox.showinfo("Export list", f"Saved card list to {path}.", parent=self)

    def _save_item_images(self, folder, item_index, item, source):
        images = item.get("images")
        if not images:
            image_urls = self.backend.image_urls(source)
            images = [self.backend.get_image(url) for url in image_urls]
        if not images:
            return

        base_name = self._safe_filename(item["name"])
        set_code = source.get("set", "")
        collector_number = source.get("collector_number", "")
        for copy_number in range(1, item["quantity"] + 1):
            for face_index, image in enumerate(images, start=1):
                filename = (
                    f"{item_index:03d}_{copy_number:02d}_{base_name}_{set_code}_{collector_number}_face{face_index}.png"
                )
                image.save(os.path.join(folder, filename), format="PNG")

    @staticmethod
    def _safe_filename(name):
        return "".join(character for character in name if character.isalnum() or character in " ._-").rstrip()


if __name__ == "__main__":
    App().mainloop()
