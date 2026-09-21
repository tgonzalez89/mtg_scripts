import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from tkinter import ttk
from typing import Final, cast

from PIL import Image, ImageTk

type ImageAction = Callable[[int, "FullImageWindow"], None]
type FaceAction = Callable[[int, int], None]
type ImageLoader = Callable[[int, "FullImageWindow"], None]
MIN_FACES: Final[int] = 2
FOUR_BUTTON: Final[int] = 4
# How many entries either side of the visible one keep their full-resolution
# art, so stepping back and forth stays instant without holding the whole grid.
RETAINED_NEIGHBOURS: Final[int] = 1


@dataclass(frozen=True)
class ImageWindowOptions:
    """Optional controls for FullImageWindow."""

    index: int = 0
    title: str = "Image"
    action_callback: ImageAction | None = None
    action_text: str | None = None
    face_callback: FaceAction | None = None
    image_loader: ImageLoader | None = None


class FullImageWindow(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        images: Sequence[Image.Image | Sequence[Image.Image]],
        options: ImageWindowOptions | None = None,
    ) -> None:
        options = options or ImageWindowOptions()
        super().__init__(master)
        self.title(options.title)
        self.geometry("900x700")
        self.minsize(400, 400)
        self.state("zoomed")
        self.images: list[list[Image.Image]] = cast(
            "list[list[Image.Image]]",
            [list(image) if isinstance(image, (list, tuple)) else [image] for image in images],
        )
        self.index = options.index
        self.action_callback = options.action_callback
        self.face_callback = options.face_callback
        self.image_loader = options.image_loader
        self._loading_indices: set[int] = set()
        self._closed = False
        self.face_index = 0
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self._drag_data: tuple[int, int] | None = None
        self._image_ref: ImageTk.PhotoImage | None = None

        self.canvas = tk.Canvas(self, bg="black")
        self.canvas.pack(fill="both", expand=True)
        controls = ttk.Frame(self)
        controls.pack(fill="x")
        controls.columnconfigure(1, weight=1)
        self.previous_button = ttk.Button(controls, text="Previous", command=self._previous)
        self.previous_button.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        if options.action_callback is not None and options.action_text:
            self.action_button = ttk.Button(controls, text=options.action_text, command=self._run_action)
            self.action_button.grid(row=0, column=1, padx=5, pady=5)
        # Art is loaded lazily, so no entry has its faces yet. The button is
        # created up front and shown once the visible entry turns out to have
        # more than one face.
        self.face_button = ttk.Button(controls, text="Flip", command=self._next_face)
        self.face_button.grid(row=0, column=2, padx=5, pady=5)
        self.face_button.grid_remove()
        self.next_button = ttk.Button(controls, text="Next", command=self._next)
        self.next_button.grid(row=0, column=3, padx=5, pady=5, sticky="e")

        self.bind("<Configure>", lambda _event: self._render())
        self.canvas.bind("<ButtonPress-1>", self._start_pan)
        self.canvas.bind("<B1-Motion>", self._do_pan)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", self._on_wheel)
        self.canvas.bind("<Button-5>", self._on_wheel)
        self.bind("<Left>", lambda _event: self._previous())
        self.bind("<Right>", lambda _event: self._next())
        self._show_current()

    def destroy(self) -> None:
        self._closed = True
        self.canvas.delete("all")
        self._image_ref = None
        self.images.clear()
        self.action_callback = None
        self.face_callback = None
        self.image_loader = None
        self._loading_indices.clear()
        super().destroy()

    def _show_current(self) -> None:
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.previous_button.configure(state="normal" if self.index else "disabled")
        self.next_button.configure(state="normal" if self.index < len(self.images) - 1 else "disabled")
        # A different card starts on its front face.
        self.face_index = 0
        self._update_face_button()
        self._release_distant_images()
        self._ensure_current_loaded()
        self._render()

    def _release_distant_images(self) -> None:
        """Drop full-resolution art for entries away from the one on screen.

        Each entry is several megabytes, so browsing a large grid would
        otherwise accumulate every card visited. Anything dropped here is
        reloaded on demand when the user navigates back to it.
        """
        if self.image_loader is None:
            return  # nothing could load them again
        nearest = range(self.index - RETAINED_NEIGHBOURS, self.index + RETAINED_NEIGHBOURS + 1)
        for position, group in enumerate(self.images):
            if group and position not in nearest:
                self.images[position] = []

    def _ensure_current_loaded(self) -> None:
        if self.image_loader and not self.images[self.index] and self.index not in self._loading_indices:
            self._loading_indices.add(self.index)
            self.image_loader(self.index, self)

    def _run_action(self) -> None:
        if self.action_callback is not None:
            self.action_callback(self.index, self)

    def update_current_images(self, images: Image.Image | Sequence[Image.Image]) -> None:
        """Replace the art for the entry currently on screen."""
        self.set_images(self.index, images)

    def set_images(self, index: int, images: Image.Image | Sequence[Image.Image]) -> None:
        """Store loaded art for `index`, which may no longer be the visible one.

        Loads are asynchronous, so the user can navigate away before one
        arrives; delivering to the requested index rather than the current one
        keeps a slow load from painting over the wrong card.
        """
        if self._closed or not 0 <= index < len(self.images):
            return
        self.images[index] = cast("list[Image.Image]", list(images) if isinstance(images, (list, tuple)) else [images])
        self._loading_indices.discard(index)
        if index != self.index:
            self._release_distant_images()
            return
        self.face_index = 0
        self._update_face_button()
        self._render()

    def _update_face_button(self) -> None:
        """Show the Flip control only while a multi-faced card is on screen."""
        if len(self.images[self.index]) >= MIN_FACES:
            self.face_button.grid()
        else:
            self.face_button.grid_remove()

    def _next_face(self) -> None:
        if len(self.images[self.index]) < MIN_FACES:
            return
        self.face_index = (self.face_index + 1) % len(self.images[self.index])
        if self.face_callback:
            self.face_callback(self.index, self.face_index)
        self._render()

    def _previous(self) -> None:
        if self.index:
            self.index -= 1
            self._show_current()

    def _next(self) -> None:
        if self.index < len(self.images) - 1:
            self.index += 1
            self._show_current()

    def _render(self) -> None:
        if not self.images:
            return
        if not self.images[self.index]:
            self.canvas.delete("IMG")
            self.canvas.delete("STATUS")
            self.canvas.create_text(
                self.canvas.winfo_width() // 2,
                self.canvas.winfo_height() // 2,
                text="Loading image...",
                fill="white",
                tags="STATUS",
            )
            return
        image = self.images[self.index][self.face_index]
        self.canvas.delete("STATUS")
        width = max(1, int(image.width * self.zoom))
        height = max(1, int(image.height * self.zoom))
        resized = image.resize((width, height), Image.Resampling.LANCZOS)
        self._image_ref = ImageTk.PhotoImage(resized)
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        x = (canvas_width - width) // 2 + self.offset_x
        y = (canvas_height - height) // 2 + self.offset_y
        self.canvas.delete("IMG")
        self.canvas.create_image(x, y, anchor="nw", image=self._image_ref, tags="IMG")

    def _start_pan(self, event: tk.Event[tk.Misc]) -> None:
        self._drag_data = (event.x, event.y)

    def _do_pan(self, event: tk.Event[tk.Misc]) -> None:
        if self._drag_data:
            self.offset_x += event.x - self._drag_data[0]
            self.offset_y += event.y - self._drag_data[1]
            self._drag_data = (event.x, event.y)
            self._render()

    def _on_wheel(self, event: tk.Event[tk.Misc]) -> str:
        delta = event.delta or (120 if event.num == FOUR_BUTTON else -120)
        self.zoom = max(0.05, min(10.0, self.zoom * (1.0 + 0.001 * delta)))
        self._render()
        return "break"
