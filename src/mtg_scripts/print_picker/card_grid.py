import tkinter as tk
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk
from typing import TYPE_CHECKING, cast

from .card import Card, CardInteraction
from .full_image_window import FullImageWindow, ImageWindowOptions
from .scrollable_frame import ScrollableFrame
from .scryfall_backend import ScryfallBackend

if TYPE_CHECKING:
    from PIL import Image

    from .card_backend import CardBackend, CardItem, CardRecord

type ItemLoader = Callable[..., None]


class CardGrid(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        backend: CardBackend | None = None,
        on_choose: Callable[..., None] | None = None,
        *,
        chooser_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self.backend = backend or ScryfallBackend()
        self.on_choose = on_choose
        self.chooser_mode = chooser_mode
        self.cards = []
        self.items = []
        self.grid_zoom = 1.0
        self.executor = ThreadPoolExecutor(max_workers=8)
        self._load_generation = 0
        self._closed = False
        self._loaded_items = {}
        self._build_ui()

    def _build_ui(self) -> None:
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

    def clear(self) -> None:
        self._load_generation += 1
        self.cards.clear()
        for widget in self.scrollable.frame.winfo_children():
            widget.destroy()

    def destroy(self) -> None:
        self._closed = True
        self._load_generation += 1
        self.executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()

    def set_backend(self, backend: CardBackend) -> None:
        self.backend = backend

    def set_items(self, items: list[CardItem]) -> None:
        self.clear()
        self.items = items
        for item in items:
            quantity = item.get("quantity", 1)
            for copy_number in range(1, quantity + 1):
                self._add_card(item, copy_number)
        self._reflow()

    def load_items(
        self,
        items: list[CardItem],
        loader: ItemLoader,
        image_loader: ItemLoader | None = None,
        batch_loader: ItemLoader | None = None,
    ) -> None:
        self.clear()
        self.items = items
        self._loaded_items = {}
        self._image_loader = image_loader
        generation = self._load_generation
        if batch_loader:
            self.executor.submit(
                batch_loader,
                items,
                lambda loaded, current=generation: self._on_item_loaded(loaded, current),
            )
        else:
            for item in items:
                self.executor.submit(
                    loader,
                    item,
                    lambda loaded, current=generation: self._on_item_loaded(loaded, current),
                )

    def _on_item_loaded(self, item: CardItem, generation: int) -> None:
        if generation == self._load_generation and not self._closed:
            self.after(0, self._record_loaded_item, item, generation)

    def _record_loaded_item(self, item: CardItem, generation: int) -> None:
        if generation != self._load_generation:
            return
        self._loaded_items[id(item)] = item
        if len(self._loaded_items) == len(self.items):
            ordered_items = self.backend.sort_items(
                list(self._loaded_items.values()), include_name=not self.chooser_mode
            )
            for loaded_item in ordered_items:
                self._add_loaded_item(loaded_item, generation)
            self._reflow()
            if self._image_loader:
                for loaded_item in ordered_items:
                    self.executor.submit(
                        self._image_loader,
                        loaded_item,
                        lambda updated, current=generation: self._on_image_loaded(updated, current),
                    )

    def _on_image_loaded(self, item: CardItem, generation: int) -> None:
        if generation != self._load_generation or self._closed:
            return
        self.after(0, self._refresh_current_item, item, generation)

    def _refresh_current_item(self, item: CardItem, generation: int) -> None:
        if generation == self._load_generation and not self._closed:
            self.refresh_item(item)

    def _add_loaded_item(self, item: CardItem, generation: int) -> None:
        if generation != self._load_generation:
            return
        for copy_number in range(1, item.get("quantity", 1) + 1):
            self._add_card(item, copy_number)

    def _add_card(self, item: CardItem, copy_number: int) -> None:
        display_item = item.copy()
        display_item["quantity"] = 1
        display_item["_source_item"] = item
        card = Card(
            self.scrollable.frame,
            display_item,
            copy_number,
            CardInteraction(self._change_zoom, self._left_click, self._right_click, self.grid_zoom),
        )
        self.cards.append(card)

    def get_display_items(self) -> list[CardItem]:
        return [card.item for card in self.cards]

    def _left_click(self, card: Card, _event: tk.Event[tk.Misc]) -> None:
        if self.chooser_mode:
            if self.on_choose:
                self.on_choose(card.item)
        elif self.on_choose:
            self.on_choose(card.item)

    def _right_click(self, card: Card, _event: tk.Event[tk.Misc]) -> None:
        image_cards = [other for other in self.cards if other.item.get("image")]
        if card in image_cards:
            images = [self.get_full_images(other.item) for other in image_cards]
            action_callback = None
            action_text = None
            on_choose = self.on_choose
            if on_choose:
                if self.chooser_mode:

                    def action_callback(index: int, _viewer: object) -> None:
                        return on_choose(image_cards[index].item)
                else:

                    def action_callback(index: int, viewer: object) -> None:
                        return on_choose(image_cards[index].item, viewer)

                action_text = "Choose"
            FullImageWindow(
                self,
                images,
                ImageWindowOptions(
                    index=image_cards.index(card),
                    title=str(card.item.get("name", "Image")),
                    action_callback=action_callback,
                    action_text=action_text,
                ),
            )

    def get_full_images(self, item: CardItem) -> tuple[Image.Image, ...]:
        source = cast("CardRecord", item.get("chosen_print") or item.get("default_card") or item.get("card") or item)
        image_pair = self.backend.load_card_images(source, high_quality=True)
        images = tuple(image for image in image_pair if image is not None)
        if images:
            return images
        fallback = item.get("images") or (item.get("image"),)
        return tuple(image for image in fallback if image is not None)

    def refresh_item(self, item: CardItem) -> None:
        if self._closed:
            return
        for card in self.cards:
            if not card.winfo_exists():
                continue
            if card.item is item:
                card.refresh_from_item()
            elif card.item.get("_source_item") is item and "chosen_print" not in card.item:
                card.item.update({key: item.get(key) for key in ("image", "images", "error")})
                card.refresh_from_item()
        self._reflow()

    def _on_resize(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        self.after_idle(self._reflow)

    def _is_inside(self, widget: tk.Misc | None) -> bool:
        while widget:
            if widget == self.scrollable:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _scroll(self, event: tk.Event[tk.Misc]) -> str | None:
        if self._is_inside(event.widget) and not int(event.state) & 0x4:
            self.scrollable.canvas.yview_scroll(-int(event.delta / 120), "units")
            return "break"
        return None

    def _horizontal_scroll(self, event: tk.Event[tk.Misc]) -> str | None:
        if self._is_inside(event.widget) and not int(event.state) & 0x4:
            self.scrollable.canvas.xview_scroll(-int(event.delta / 120), "units")
            return "break"
        return None

    def _scroll_step(self, event: tk.Event[tk.Misc], amount: int) -> str | None:
        if self._is_inside(event.widget) and not int(event.state) & 0x4:
            self.scrollable.canvas.yview_scroll(amount, "units")
            return "break"
        return None

    def _horizontal_scroll_step(self, event: tk.Event[tk.Misc], amount: int) -> str | None:
        if self._is_inside(event.widget) and not int(event.state) & 0x4:
            self.scrollable.canvas.xview_scroll(amount, "units")
            return "break"
        return None

    def _zoom_wheel(self, event: tk.Event[tk.Misc]) -> str | None:
        if self._is_inside(event.widget):
            self._change_zoom(1 if event.delta > 0 else -1)
            return "break"
        return None

    def _zoom_step(self, event: tk.Event[tk.Misc], step: int) -> str | None:
        if self._is_inside(event.widget):
            self._change_zoom(step)
            return "break"
        return None

    def _zoom_key(self, _event: tk.Event[tk.Misc], step: int) -> str | None:
        if self._pointer_inside():
            self._change_zoom(step, reset=step == 0)
            return "break"
        return None

    def _pointer_inside(self) -> bool:
        widget = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        return self._is_inside(widget)

    def _change_zoom(self, step: int, *, reset: bool = False) -> None:
        self.grid_zoom = 1.0 if reset else max(0.5, min(10.0, self.grid_zoom + step * 0.5))
        for card in self.cards:
            card.set_zoom(self.grid_zoom)
        self.update_idletasks()
        self._reflow()

    def _reflow(self) -> None:
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
