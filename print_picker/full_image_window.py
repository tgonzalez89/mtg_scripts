import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk


class FullImageWindow(tk.Toplevel):
    def __init__(
        self,
        master,
        images,
        index=0,
        title="Image",
        action_callback=None,
        action_text=None,
        face_callback=None,
    ):
        super().__init__(master)
        self.title(title)
        self.geometry("900x700")
        self.minsize(400, 400)
        self.state("zoomed")
        self.images = [image if isinstance(image, list) else [image] for image in images]
        self.index = index
        self.action_callback = action_callback
        self.face_callback = face_callback
        self.face_index = 0
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self._drag_data = None
        self._image_ref = None

        self.canvas = tk.Canvas(self, bg="black")
        self.canvas.pack(fill="both", expand=True)
        controls = ttk.Frame(self)
        controls.pack(fill="x")
        controls.columnconfigure(1, weight=1)
        self.previous_button = ttk.Button(controls, text="Previous", command=self._previous)
        self.previous_button.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        if action_callback is not None and action_text:
            self.action_button = ttk.Button(controls, text=action_text, command=self._run_action)
            self.action_button.grid(row=0, column=1, padx=5, pady=5)
        if any(len(group) > 1 for group in self.images):
            self.face_button = ttk.Button(controls, text="Flip", command=self._next_face)
            self.face_button.grid(row=0, column=2, padx=5, pady=5)
            next_column = 3
        else:
            next_column = 2
        self.next_button = ttk.Button(controls, text="Next", command=self._next)
        self.next_button.grid(row=0, column=next_column, padx=5, pady=5, sticky="e")

        self.bind("<Configure>", lambda _event: self._render())
        self.canvas.bind("<ButtonPress-1>", self._start_pan)
        self.canvas.bind("<B1-Motion>", self._do_pan)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", self._on_wheel)
        self.canvas.bind("<Button-5>", self._on_wheel)
        self.bind("<Left>", lambda _event: self._previous())
        self.bind("<Right>", lambda _event: self._next())
        self._show_current()

    def _show_current(self):
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.previous_button.configure(state="normal" if self.index else "disabled")
        self.next_button.configure(state="normal" if self.index < len(self.images) - 1 else "disabled")
        self.face_index = min(self.face_index, len(self.images[self.index]) - 1)
        if hasattr(self, "face_button"):
            self.face_button.configure(state="normal" if len(self.images[self.index]) > 1 else "disabled")
        self._render()

    def _run_action(self):
        self.action_callback(self.index, self)

    def update_current_images(self, images):
        self.images[self.index] = images if isinstance(images, list) else [images]
        self.face_index = 0
        if hasattr(self, "face_button"):
            self.face_button.configure(state="normal" if len(self.images[self.index]) > 1 else "disabled")
        self._render()

    def _next_face(self):
        if len(self.images[self.index]) < 2:
            return
        self.face_index = (self.face_index + 1) % len(self.images[self.index])
        if self.face_callback:
            self.face_callback(self.index, self.face_index)
        self._render()

    def _previous(self):
        if self.index:
            self.index -= 1
            self._show_current()

    def _next(self):
        if self.index < len(self.images) - 1:
            self.index += 1
            self._show_current()

    def _render(self):
        if not self.images:
            return
        image = self.images[self.index][self.face_index]
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

    def _start_pan(self, event):
        self._drag_data = (event.x, event.y)

    def _do_pan(self, event):
        if self._drag_data:
            self.offset_x += event.x - self._drag_data[0]
            self.offset_y += event.y - self._drag_data[1]
            self._drag_data = (event.x, event.y)
            self._render()

    def _on_wheel(self, event):
        delta = event.delta if event.delta else (120 if event.num == 4 else -120)
        self.zoom = max(0.05, min(10.0, self.zoom * (1.0 + 0.001 * delta)))
        self._render()
        return "break"
