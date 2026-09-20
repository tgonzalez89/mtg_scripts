import io
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from .card_backend import CardItem

MIN_FACES = 2

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
        item: CardItem,
        copy_number: int,
        interaction: CardInteraction,
    ) -> None:
        super().__init__(parent, relief="groove", borderwidth=1)
        self.item = item
        self.copy_number = copy_number
        self.zoom = interaction.zoom
        self._on_zoom = interaction.on_zoom
        self._on_left_click = interaction.on_left_click
        self._on_right_click = interaction.on_right_click
        self._image = item.get("image")
        self._image_ref = None
        self._render_cache = {}

        self.header = ttk.Frame(self)
        self.header.pack(fill="x", padx=5, pady=(5, 0))
        self.header.columnconfigure(0, weight=1, minsize=0)
        self.face_button = ttk.Button(self.header, text="Flip", width=4, command=self.switch_face)
        self.face_button.grid(row=0, column=1, padx=(5, 0), sticky="e")
        self.name_label = ttk.Label(self.header, text=item.get("display_name", item.get("name", "")), anchor="center")
        self.name_label.grid(row=0, column=0, sticky="ew")
        self.image_label = ttk.Label(self, anchor="center")
        self.image_label.pack(padx=5, pady=5)
        self.status_label = ttk.Label(self, text=item.get("error", ""), anchor="center")
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
        images = self.item.get("images") or ([self._image] if self._image else [])
        if images:
            self.item["face_index"] = self.item.get("face_index", 0) % len(images)
            self._image = images[self.item["face_index"]]
            size = (max(1, int(220 * zoom)), max(1, int(314 * zoom)))
            self._image_ref = self._render_cache.get(size)
            if self._image_ref is None:
                if self._image is None:
                    return
                image = self._image.copy()
                image.thumbnail(size, Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format="PNG")
                self._image_ref = tk.PhotoImage(data=output.getvalue())
                self._render_cache[size] = self._image_ref
            self.image_label.configure(image=self._image_ref, text="")
        else:
            self.image_label.configure(image="", text=self.item.get("error", "No image"))
        self.configure(width=max(1, int(230 * zoom)), height=max(1, int(360 * zoom)))
        self.pack_propagate(flag=False)

    def switch_face(self) -> None:
        images = self.item.get("images") or []
        if len(images) < MIN_FACES:
            return
        self.item["face_index"] = (self.item.get("face_index", 0) + 1) % len(images)
        self._render_cache.clear()
        self.set_zoom(self.zoom)
        self._update_face_button()

    def refresh_from_item(self) -> None:
        """Refresh the rendered card after its item data changes."""
        self._image = self.item.get("image")
        self._render_cache.clear()
        self.set_zoom(self.zoom)
        self._update_face_button()

    def _update_face_button(self) -> None:
        if len(self.item.get("images") or []) > 1:
            self.face_button.grid()
        else:
            self.face_button.grid_remove()

    def preferred_width(self) -> int:
        return int(230 * self.zoom)
