import io
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import TYPE_CHECKING, Final

from PIL import Image

if TYPE_CHECKING:
    from .view_model import CardSlot

MIN_FACES: Final[int] = 2
BASE_WIDTH: Final[int] = 220
BASE_HEIGHT: Final[int] = 314

type CardCallback = Callable[["Card", tk.Event[tk.Misc]], None]
type ZoomCallback = Callable[[int], None]


@dataclass(frozen=True)
class CardInteraction:
    """Callbacks and display settings for a Card widget."""

    on_zoom: ZoomCallback
    on_left_click: CardCallback
    on_right_click: CardCallback
    zoom: float = 1.0


class Card(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        slot: CardSlot,
        copy_number: int,
        interaction: CardInteraction,
    ) -> None:
        super().__init__(parent, relief="groove", borderwidth=1)
        self.slot = slot
        self.copy_number = copy_number
        self.zoom = interaction.zoom
        self._on_zoom = interaction.on_zoom
        self._on_left_click = interaction.on_left_click
        self._on_right_click = interaction.on_right_click
        # Only the currently displayed rendering is kept; caching every zoom
        # level ever visited is what made large decks balloon.
        self._render_key: tuple[int, int, int, int] | None = None
        self._image_ref: tk.PhotoImage | None = None
        # Off-screen cards hold no rendered image at all. The grid turns art on
        # for the cards in the viewport; a rendered tile costs far more than the
        # source art, so this is the difference between ~250 MB and ~2 GB on a
        # large, zoomed-in grid.
        self._art_visible = False

        self.header = ttk.Frame(self)
        self.header.pack(fill="x", padx=5, pady=(5, 0))
        self.header.columnconfigure(0, weight=1, minsize=0)
        self.face_button = ttk.Button(self.header, text="Flip", width=4, command=self.switch_face)
        self.face_button.grid(row=0, column=1, padx=(5, 0), sticky="e")
        self.name_label = ttk.Label(self.header, text=slot.label, anchor="center")
        self.name_label.grid(row=0, column=0, sticky="ew")
        self.image_label = ttk.Label(self, anchor="center")
        self.image_label.pack(padx=5, pady=5)
        self.status_label = ttk.Label(self, text=slot.error or "", anchor="center")
        self.status_label.pack(fill="x", padx=5, pady=(0, 5))
        self._bind_events()
        self.set_zoom(interaction.zoom)
        self._update_face_button()

    def _bind_events(self) -> None:
        for widget in (self, self.header, self.name_label, self.image_label, self.status_label):
            widget.bind("<Button-1>", lambda event: self._on_left_click(self, event))
            widget.bind("<Button-3>", lambda event: self._on_right_click(self, event))
            widget.bind("<Control-MouseWheel>", self._on_zoom_event)
            widget.bind("<Control-Button-4>", lambda event: self._on_zoom_button(event, 1))
            widget.bind("<Control-Button-5>", lambda event: self._on_zoom_button(event, -1))

    def _on_zoom_event(self, event: tk.Event[tk.Misc]) -> str:
        self._on_zoom(1 if event.delta > 0 else -1)
        return "break"

    def _on_zoom_button(self, _event: tk.Event[tk.Misc], step: int) -> str:
        self._on_zoom(step)
        return "break"

    def set_zoom(self, zoom: float) -> None:
        self.zoom = zoom
        self.configure(width=max(1, int(230 * zoom)), height=max(1, int(360 * zoom)))
        self.pack_propagate(flag=False)
        self._refresh_image()

    def set_art_visible(self, *, visible: bool) -> None:
        """Render this card's art, or drop it while the card is off-screen."""
        if visible != self._art_visible:
            self._art_visible = visible
            self._refresh_image()

    def _refresh_image(self) -> None:
        image = self.slot.current_image if self._art_visible else None
        if image is not None:
            size = (max(1, int(BASE_WIDTH * self.zoom)), max(1, int(BASE_HEIGHT * self.zoom)))
            self._render(image, size)
            return
        self._render_key = None
        self._image_ref = None
        if not self._art_visible:
            self.image_label.configure(image="", text="")
            return
        if self.slot.image_loading:
            status = "Image Loading..."
        elif self.slot.error:
            # The status label below already reports the error; repeating it
            # here would show the same message twice in one cell.
            status = ""
        else:
            status = "No Image"
        self.image_label.configure(image="", text=status)

    def _render(self, image: Image.Image, size: tuple[int, int]) -> None:
        # The stored art is only kept at the size actually needed, so it may be
        # smaller than the tile and has to be scaled up until sharper art
        # arrives; `thumbnail` would refuse to enlarge it.
        key = (*size, self.slot.face_index, image.width)
        if key != self._render_key or self._image_ref is None:
            resized = image.resize(_fit(image, size), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            resized.save(output, format="PNG")
            self._image_ref = tk.PhotoImage(data=output.getvalue())
            self._render_key = key
        self.image_label.configure(image=self._image_ref, text="")

    def switch_face(self) -> None:
        if len(self.slot.images) < MIN_FACES:
            return
        self.slot.advance_face()
        self._refresh_image()
        self._update_face_button()

    def refresh_from_slot(self) -> None:
        """Refresh the rendered card after its slot data changes."""
        self._render_key = None
        self._image_ref = None
        self.name_label.configure(text=self.slot.label)
        self.status_label.configure(text=self.slot.error or "")
        self._refresh_image()
        self._update_face_button()

    def dispose(self) -> None:
        self._image_ref = None
        self._render_key = None
        self.destroy()

    def _update_face_button(self) -> None:
        if len(self.slot.images) > 1:
            self.face_button.grid()
        else:
            self.face_button.grid_remove()

    def preferred_width(self) -> int:
        return int(230 * self.zoom)


def _fit(image: Image.Image, box: tuple[int, int]) -> tuple[int, int]:
    """Return the size that fits `image` inside `box`, preserving aspect ratio."""
    scale = min(box[0] / image.width, box[1] / image.height)
    return max(1, round(image.width * scale)), max(1, round(image.height * scale))
