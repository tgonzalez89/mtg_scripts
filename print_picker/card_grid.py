from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk

from print_picker.card import Card
from print_picker.full_image_window import FullImageWindow
from print_picker.scrollable_frame import ScrollableFrame
from print_picker.scryfall_backend import ScryfallBackend


class CardGrid(ttk.Frame):
    def __init__(self, parent, backend=None, on_choose=None, chooser_mode=False):
        super().__init__(parent)
        self.backend = backend or ScryfallBackend()
        self.on_choose = on_choose
        self.chooser_mode = chooser_mode
        self.cards = []
        self.items = []
        self.grid_zoom = 1.0
        self.executor = ThreadPoolExecutor(max_workers=8)
        self._load_generation = 0
        self._build_ui()

    def _build_ui(self):
        self.scrollable = ScrollableFrame(self)
        self.scrollable.pack(fill="both", expand=True)
        self.scrollable.canvas.bind("<Configure>", self._on_resize, add="+")
        for sequence, callback in (
            ("<MouseWheel>", self._scroll),
            ("<Shift-MouseWheel>", self._horizontal_scroll),
            ("<Button-4>", lambda event: self._scroll_step(event, -1)),
            ("<Button-5>", lambda event: self._scroll_step(event, 1)),
            ("<Shift-Button-4>", lambda event: self._horizontal_scroll_step(event, -1)),
            ("<Shift-Button-5>", lambda event: self._horizontal_scroll_step(event, 1)),
            ("<Control-MouseWheel>", self._zoom_wheel),
            ("<Control-Button-4>", lambda event: self._zoom_step(event, 1)),
            ("<Control-Button-5>", lambda event: self._zoom_step(event, -1)),
            ("<Control-plus>", lambda event: self._zoom_key(event, 1)),
            ("<Control-equal>", lambda event: self._zoom_key(event, 1)),
            ("<Control-minus>", lambda event: self._zoom_key(event, -1)),
            ("<Control-0>", lambda event: self._zoom_key(event, 0)),
        ):
            self.bind_all(sequence, callback, add="+")
        self.bind_all("<Control-KP_Add>", lambda event: self._zoom_key(event, 1), add="+")
        self.bind_all("<Control-KP_Subtract>", lambda event: self._zoom_key(event, -1), add="+")
        self.bind_all("<Control-KP_0>", lambda event: self._zoom_key(event, 0), add="+")

    def clear(self):
        self._load_generation += 1
        self.cards.clear()
        for widget in self.scrollable.frame.winfo_children():
            widget.destroy()

    def set_items(self, items):
        self.clear()
        self.items = items
        for item in items:
            quantity = item.get("quantity", 1)
            for copy_number in range(1, quantity + 1):
                self._add_card(item, copy_number)
        self._reflow()

    def load_items(self, items, loader):
        self.clear()
        self.items = items
        generation = self._load_generation
        for item in items:
            self.executor.submit(
                loader,
                item,
                lambda loaded, current=generation: self._on_item_loaded(loaded, current),
            )

    def _on_item_loaded(self, item, generation):
        self.after(0, self._add_loaded_item, item, generation)

    def _add_loaded_item(self, item, generation):
        if generation != self._load_generation:
            return
        for copy_number in range(1, item.get("quantity", 1) + 1):
            self._add_card(item, copy_number)
        self._reflow()

    def _add_card(self, item, copy_number):
        card = Card(
            self.scrollable.frame,
            item,
            copy_number,
            self._change_zoom,
            self._left_click,
            self._right_click,
            self.grid_zoom,
        )
        self.cards.append(card)

    def _left_click(self, card, _event):
        if self.chooser_mode:
            if self.on_choose:
                self.on_choose(card.item)
        elif self.on_choose:
            self.on_choose(card.item)

    def _right_click(self, card, _event):
        image_cards = [other for other in self.cards if other.item.get("image")]
        if card in image_cards:
            images = [other.item.get("images") or [other.item["image"]] for other in image_cards]
            action_callback = None
            action_text = None
            if self.on_choose:
                if self.chooser_mode:
                    action_callback = lambda index, _viewer: self.on_choose(image_cards[index].item)
                else:
                    action_callback = lambda index, viewer: self.on_choose(image_cards[index].item, viewer)
                action_text = "Choose"
            FullImageWindow(
                self,
                images,
                image_cards.index(card),
                card.item.get("name", "Image"),
                action_callback,
                action_text,
            )

    def refresh_item(self, item):
        for card in self.cards:
            if card.item is item:
                card._image = item.get("image")
                card._render_cache.clear()
                card.set_zoom(self.grid_zoom)
        self._reflow()

    def _on_resize(self, _event=None):
        self.after_idle(self._reflow)

    def _is_inside(self, widget):
        while widget:
            if widget == self.scrollable:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _scroll(self, event):
        if self._is_inside(event.widget) and not event.state & 0x4:
            self.scrollable.canvas.yview_scroll(-int(event.delta / 120), "units")
            return "break"

    def _horizontal_scroll(self, event):
        if self._is_inside(event.widget) and not event.state & 0x4:
            self.scrollable.canvas.xview_scroll(-int(event.delta / 120), "units")
            return "break"

    def _scroll_step(self, event, amount):
        if self._is_inside(event.widget) and not event.state & 0x4:
            self.scrollable.canvas.yview_scroll(amount, "units")
            return "break"

    def _horizontal_scroll_step(self, event, amount):
        if self._is_inside(event.widget) and not event.state & 0x4:
            self.scrollable.canvas.xview_scroll(amount, "units")
            return "break"

    def _zoom_wheel(self, event):
        if self._is_inside(event.widget):
            self._change_zoom(1 if event.delta > 0 else -1)
            return "break"

    def _zoom_step(self, event, step):
        if self._is_inside(event.widget):
            self._change_zoom(step)
            return "break"

    def _zoom_key(self, event, step):
        if self._pointer_inside():
            self._change_zoom(step, reset=step == 0)
            return "break"

    def _pointer_inside(self):
        widget = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        return self._is_inside(widget)

    def _change_zoom(self, step, reset=False):
        self.grid_zoom = 1.0 if reset else max(0.5, min(10.0, self.grid_zoom + step * 0.5))
        for card in self.cards:
            card.set_zoom(self.grid_zoom)
        self.update_idletasks()
        self._reflow()

    def _reflow(self):
        if not self.cards:
            return
        available_width = max(1, self.scrollable.canvas.winfo_width() - 8)
        card_width = max(card.preferred_width() for card in self.cards) + 12
        columns = max(1, available_width // card_width)
        for index, card in enumerate(self.cards):
            card.grid(row=index // columns, column=index % columns, padx=5, pady=5, sticky="nsew")
        for column in range(len(self.cards)):
            self.scrollable.frame.columnconfigure(column, weight=0, minsize=0)
        for column in range(columns):
            self.scrollable.frame.columnconfigure(column, weight=1, minsize=card_width)
        self.scrollable.canvas.configure(scrollregion=self.scrollable.canvas.bbox("all"))
