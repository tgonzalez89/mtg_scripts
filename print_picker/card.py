import io
import tkinter as tk
from tkinter import ttk

from PIL import Image


class Card(ttk.Frame):
    def __init__(self, parent, item, copy_number, on_zoom, on_left_click, on_right_click, zoom=1.0):
        super().__init__(parent, relief="groove", borderwidth=1)
        self.item = item
        self.copy_number = copy_number
        self.zoom = zoom
        self._on_zoom = on_zoom
        self._on_left_click = on_left_click
        self._on_right_click = on_right_click
        self._image = item.get("image")
        self._image_ref = None
        self._render_cache = {}

        self.header = ttk.Frame(self)
        self.header.pack(fill="x", padx=5, pady=(5, 0))
        self.name_label = ttk.Label(self.header, text=item.get("display_name", item.get("name", "")), anchor="center")
        self.name_label.pack(side="left", fill="x", expand=True)
        self.face_button = ttk.Button(self.header, text="Flip", command=self.switch_face)
        self.face_button.pack(side="right", padx=(5, 0))
        self.image_label = ttk.Label(self, anchor="center")
        self.image_label.pack(padx=5, pady=5)
        self.status_label = ttk.Label(self, text=item.get("error", ""), anchor="center")
        self.status_label.pack(fill="x", padx=5, pady=(0, 5))
        self._bind_events()
        self.set_zoom(zoom)
        self._update_face_button()

    def _bind_events(self):
        for widget in (self, self.header, self.name_label, self.image_label, self.status_label):
            widget.bind("<Button-1>", lambda event: self._on_left_click(self, event))
            widget.bind("<Button-3>", lambda event: self._on_right_click(self, event))
            widget.bind("<Control-MouseWheel>", self._on_zoom_event)
            widget.bind("<Control-Button-4>", lambda event: self._on_zoom_button(event, 1))
            widget.bind("<Control-Button-5>", lambda event: self._on_zoom_button(event, -1))

    def _on_zoom_event(self, event):
        self._on_zoom(1 if event.delta > 0 else -1)
        return "break"

    def _on_zoom_button(self, _event, step):
        self._on_zoom(step)
        return "break"

    def set_zoom(self, zoom):
        self.zoom = zoom
        images = self.item.get("images") or ([self._image] if self._image else [])
        if images:
            self.item["face_index"] = self.item.get("face_index", 0) % len(images)
            self._image = images[self.item["face_index"]]
            size = (max(1, int(220 * zoom)), max(1, int(314 * zoom)))
            self._image_ref = self._render_cache.get(size)
            if self._image_ref is None:
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
        self.pack_propagate(False)

    def switch_face(self):
        images = self.item.get("images") or []
        if len(images) < 2:
            return
        self.item["face_index"] = (self.item.get("face_index", 0) + 1) % len(images)
        self._render_cache.clear()
        self.set_zoom(self.zoom)
        self._update_face_button()

    def _update_face_button(self):
        if len(self.item.get("images") or []) > 1:
            self.face_button.pack(side="right", padx=(5, 0))
        else:
            self.face_button.pack_forget()

    def preferred_width(self):
        return int(230 * self.zoom)
