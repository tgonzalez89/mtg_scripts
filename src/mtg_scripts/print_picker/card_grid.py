import contextlib
import tkinter as tk
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from tkinter import ttk
from typing import TYPE_CHECKING, Any, Final, cast

from PIL import Image

from .card import BASE_HEIGHT, BASE_WIDTH, Card, CardInteraction
from .full_image_window import FullImageWindow, ImageAction, ImageWindowOptions
from .scrollable_frame import ScrollableFrame
from .ui_queue import UiQueue
from .view_model import CardSlot, sort_slots

if TYPE_CHECKING:
    from .card_backend import CardBackend

type SlotLoader = Callable[..., None]

# Grid art is stored only as large as it currently needs to be. Anything beyond
# the source resolution is wasted, and anything below the tile size is upscaled
# until sharper art arrives.
BASE_ART_SIZE: Final[tuple[int, int]] = (BASE_WIDTH, BASE_HEIGHT)
MAX_ART_SIZE: Final[tuple[int, int]] = (488, 680)
REFINE_DELAY_MS: Final[int] = 150


def art_size_for(zoom: float) -> tuple[int, int]:
    """Return the art resolution worth holding for a tile at `zoom`."""
    scale = max(1.0, zoom)
    return (
        min(MAX_ART_SIZE[0], int(BASE_WIDTH * scale)),
        min(MAX_ART_SIZE[1], int(BASE_HEIGHT * scale)),
    )


class CardGrid(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        backend: CardBackend | None = None,
        on_choose: Callable[..., None] | None = None,
        on_open_full_image: Callable[..., None] | None = None,
        *,
        chooser_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self.backend = backend
        self.on_choose = on_choose
        self.on_open_full_image = on_open_full_image
        self.chooser_mode = chooser_mode
        self.cards: list[Card] = []
        self.slots: list[CardSlot] = []
        self.grid_zoom = 1.0
        self.executor = ThreadPoolExecutor(max_workers=8)
        self._load_generation = 0
        self._closed = False
        self._reflow_pending = False
        self._configured_columns = 0
        self._global_bindings: list[tuple[str, str]] = []
        self._tasks: set[Future[None]] = set()
        self._image_loader: SlotLoader | None = None
        self._refine_timer: str | None = None
        # Workers never touch Tk directly; they post results here instead.
        self._ui = UiQueue(self)
        self._build_ui()
        self._ui.start()

    def _build_ui(self) -> None:
        self.scrollable = ScrollableFrame(self)
        self.scrollable.pack(fill="both", expand=True)
        self.scrollable.on_viewport_change = self._schedule_art_refresh
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
            self._bind_all(sequence, callback)
        self._bind_all("<Control-KP_Add>", lambda event: self._zoom_key(event, 1))
        self._bind_all("<Control-KP_Subtract>", lambda event: self._zoom_key(event, -1))
        self._bind_all("<Control-KP_0>", lambda event: self._zoom_key(event, 0))

    def _bind_all(self, sequence: str, callback: Callable[..., object]) -> None:
        funcid = self.bind_all(sequence, callback, add="+")
        if funcid:
            self._global_bindings.append((sequence, funcid))

    # -- lifecycle ----------------------------------------------------------

    def clear(self) -> None:
        self._load_generation += 1
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        for card in self.cards:
            card.dispose()
        self.cards.clear()
        for slot in self.slots:
            slot.release_images()
        self.slots.clear()
        self._image_loader = None
        self._configured_columns = 0

    def destroy(self) -> None:
        self._closed = True
        self._ui.stop()
        self._cancel_refine()
        self.scrollable.on_viewport_change = None
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.clear()
        # `_root`/`_unbind` are private tkinter internals that are not part of
        # the `tkinter.Misc` stub, so they are accessed via an `Any` cast.
        root = cast("Any", self)._root()  # noqa: SLF001
        for sequence, funcid in self._global_bindings:
            root._unbind(("bind", "all", sequence), funcid)  # noqa: SLF001
        self._global_bindings.clear()
        self.backend = None
        self.on_choose = None
        self.on_open_full_image = None
        super().destroy()

    def set_backend(self, backend: CardBackend) -> None:
        self.backend = backend

    # -- population ---------------------------------------------------------

    def set_slots(self, slots: list[CardSlot]) -> None:
        self.clear()
        self.slots = slots
        for slot in slots:
            self._add_cards_for(slot)
        self._schedule_reflow()

    def load_slots(
        self,
        slots: list[CardSlot],
        resolve: SlotLoader,
        image_loader: SlotLoader | None = None,
    ) -> None:
        """Resolve `slots` off the UI thread, then render and load their images."""
        self.clear()
        self.slots = slots
        self._image_loader = image_loader
        generation = self._load_generation
        self._submit_task(self._run_resolve, slots, generation, resolve)

    def _run_resolve(self, slots: list[CardSlot], generation: int, resolve: SlotLoader) -> None:
        """Worker thread: resolve the batch, then hand rendering to the UI thread."""
        try:
            resolve(slots)
        except Exception as error:  # noqa: BLE001 - a failed batch must still render
            for slot in slots:
                slot.error = str(error)
        self._ui.post(self._render_resolved, slots, generation)

    def _render_resolved(self, slots: list[CardSlot], generation: int) -> None:
        if generation != self._load_generation or self._closed:
            return
        ordered = sort_slots(slots, include_name=not self.chooser_mode)
        for slot in ordered:
            if self._image_loader:
                slot.image_loading = True
            self._add_cards_for(slot)
        self._schedule_reflow()
        if self._image_loader:
            self.update_idletasks()
            self._start_image_loading(ordered, generation)

    def _start_image_loading(self, slots: list[CardSlot], generation: int) -> None:
        if generation != self._load_generation or self._closed or self._image_loader is None:
            return
        size = art_size_for(self.grid_zoom)
        for slot in slots:
            self._submit_task(self._run_image_loader, slot, generation, self._image_loader, size)

    def _run_image_loader(self, slot: CardSlot, generation: int, loader: SlotLoader, size: tuple[int, int]) -> None:
        """Worker thread: load one slot's art, then hand redraw to the UI thread."""
        try:
            loader(slot, size)
            slot.image_size = size
        except Exception as error:  # noqa: BLE001 - worker failures must finish the loading state
            slot.error = str(error)
        slot.image_loading = False
        self._ui.post(self._refresh_slot, slot, generation)

    def _refresh_slot(self, slot: CardSlot, generation: int) -> None:
        if generation == self._load_generation and not self._closed:
            self.refresh_slot(slot)

    def _add_cards_for(self, slot: CardSlot) -> None:
        for copy_number in range(1, max(1, slot.quantity) + 1):
            card = Card(
                self.scrollable.frame,
                slot,
                copy_number,
                CardInteraction(self._change_zoom, self._left_click, self._right_click, self.grid_zoom),
            )
            self.cards.append(card)

    def _submit_task(self, callback: Callable[..., None], *args: object) -> None:
        task = self.executor.submit(callback, *args)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def get_display_slots(self) -> list[CardSlot]:
        """Return the slots currently rendered, once per displayed copy."""
        return [card.slot for card in self.cards]

    def refresh_slot(self, slot: CardSlot) -> None:
        """Re-render every widget showing `slot`."""
        if self._closed:
            return
        for card in self.cards:
            if card.slot is slot and card.winfo_exists():
                card.refresh_from_slot()
        self._schedule_reflow()

    # -- interaction --------------------------------------------------------

    def _left_click(self, card: Card, _event: tk.Event[tk.Misc]) -> None:
        if self.on_choose:
            self.on_choose(card.slot)

    def _right_click(self, card: Card, _event: tk.Event[tk.Misc]) -> None:
        image_cards = [other for other in self.cards if other.slot.images]
        if card not in image_cards:
            return
        images: list[tuple[Image.Image, ...]] = [()] * len(image_cards)
        action_callback: ImageAction | None = None
        action_text: str | None = None
        on_choose = self.on_choose
        if on_choose:
            if self.chooser_mode:

                def action_callback(index: int, _viewer: FullImageWindow) -> None:
                    return on_choose(image_cards[index].slot)
            else:

                def action_callback(index: int, viewer: FullImageWindow) -> None:
                    return on_choose(image_cards[index].slot, viewer)

            action_text = "Choose"
        options = ImageWindowOptions(
            index=image_cards.index(card),
            title=card.slot.name or "Image",
            action_callback=action_callback,
            action_text=action_text,
            image_loader=lambda index, viewer: self._load_full_images(image_cards[index].slot, viewer, index),
        )
        if self.on_open_full_image:
            self.on_open_full_image(self, images, options)
        else:
            FullImageWindow(self, images, options)

    def _load_full_images(self, slot: CardSlot, viewer: FullImageWindow, index: int) -> None:
        def load() -> None:
            images = self.get_full_images(slot)
            self._ui.post(self._deliver_full_images, viewer, index, images)

        self._submit_task(load)

    def _deliver_full_images(self, viewer: FullImageWindow, index: int, images: tuple[Image.Image, ...]) -> None:
        # The viewer may have been closed while its images were loading.
        with contextlib.suppress(tk.TclError):
            viewer.set_images(index, images)

    def get_full_images(self, slot: CardSlot) -> tuple[Image.Image, ...]:
        """Load full-resolution art on demand; the grid only keeps thumbnails."""
        card = slot.display_print
        if self.backend is not None and card is not None:
            images = self.backend.load_images(card, high_quality=True)
            if images:
                return images
        return slot.images

    # -- art detail -----------------------------------------------------------

    def _cancel_refine(self) -> None:
        if self._refine_timer is not None:
            with contextlib.suppress(tk.TclError):
                self.after_cancel(self._refine_timer)
            self._refine_timer = None

    def _schedule_art_refresh(self) -> None:
        """Debounce art refinement; zoom and scroll both fire in bursts."""
        if self._closed:
            return
        self._cancel_refine()
        self._refine_timer = self.after(REFINE_DELAY_MS, self._refresh_art_detail)

    def _refresh_art_detail(self) -> None:
        """Load sharper art for what is on screen; shrink what has scrolled away."""
        self._refine_timer = None
        if self._closed:
            return
        self._update_art_visibility()
        if self._image_loader is None:
            return
        wanted = art_size_for(self.grid_zoom)
        on_screen = {id(card.slot) for card in self._visible_cards()}
        generation = self._load_generation
        for slot in self.slots:
            if slot.image_loading or not slot.images:
                continue
            if id(slot) in on_screen:
                if slot.image_size[0] < wanted[0]:
                    slot.image_loading = True
                    self._submit_task(self._run_image_loader, slot, generation, self._image_loader, wanted)
            elif slot.image_size[0] > BASE_ART_SIZE[0]:
                self._shrink_art(slot)

    def _update_art_visibility(self) -> None:
        """Render only the cards in the viewport; release the rest."""
        on_screen = {id(card) for card in self._visible_cards()}
        for card in self.cards:
            if card.winfo_exists():
                card.set_art_visible(visible=id(card) in on_screen)

    def _shrink_art(self, slot: CardSlot) -> None:
        """Drop an off-screen slot back to tile-sized art, freeing its detail."""
        shrunk: list[Image.Image] = []
        for image in slot.images:
            small = image.copy()
            small.thumbnail(BASE_ART_SIZE, Image.Resampling.LANCZOS)
            shrunk.append(small)
        slot.images = tuple(shrunk)
        slot.image_size = BASE_ART_SIZE
        self.refresh_slot(slot)

    def _visible_cards(self) -> list[Card]:
        """Return the cards intersecting the scrolled viewport."""
        canvas = self.scrollable.canvas
        if not canvas.winfo_ismapped():
            return []
        top = canvas.canvasy(0)
        bottom = top + canvas.winfo_height()
        visible: list[Card] = []
        for card in self.cards:
            if not card.winfo_ismapped():
                continue
            card_top = card.winfo_y()
            if card_top + card.winfo_height() >= top and card_top <= bottom:
                visible.append(card)
        return visible

    # -- layout -------------------------------------------------------------

    def _schedule_reflow(self) -> None:
        if self._closed or self._reflow_pending:
            return
        self._reflow_pending = True
        self.after_idle(self._run_scheduled_reflow)

    def _run_scheduled_reflow(self) -> None:
        self._reflow_pending = False
        if self._closed:
            return
        if not self.winfo_ismapped() or self.scrollable.canvas.winfo_width() <= 1:
            self.after(25, self._schedule_reflow)
            return
        self._reflow()

    def _on_resize(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        self._schedule_reflow()

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
        self.grid_zoom = 1.0 if reset else max(0.5, min(5.0, self.grid_zoom + step * 0.25))
        for card in self.cards:
            card.set_zoom(self.grid_zoom)
        self.update_idletasks()
        self._reflow()
        self._schedule_art_refresh()

    def _reflow(self) -> None:
        if not self.cards:
            return
        available_width = max(1, self.scrollable.canvas.winfo_width() - 8)
        card_width = max(card.preferred_width() for card in self.cards) + 12
        columns = max(1, available_width // card_width)
        for index, card in enumerate(self.cards):
            card.grid(row=index // columns, column=index % columns, padx=5, pady=5, sticky="nsew")
        for column in range(max(self._configured_columns, columns)):
            self.scrollable.frame.columnconfigure(column, weight=0, minsize=0)
        for column in range(columns):
            self.scrollable.frame.columnconfigure(column, weight=1, minsize=card_width)
        self._configured_columns = columns
        self.scrollable.canvas.configure(scrollregion=self.scrollable.canvas.bbox("all"))
        self.update_idletasks()
        self._update_art_visibility()
