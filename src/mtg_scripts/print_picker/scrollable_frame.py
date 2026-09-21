import platform
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class ScrollableFrame(ttk.Frame):
    """Scrollable frame with both scrollbars."""

    def __init__(self, container: tk.Misc) -> None:
        super().__init__(container)
        # Notified whenever the vertical viewport moves, however it was moved
        # (wheel, scrollbar drag, or programmatic scroll).
        self.on_viewport_change: Callable[[], None] | None = None

        self.canvas = tk.Canvas(self)
        self._scrollbar_y = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self._scrollbar_x = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)

        self.frame = ttk.Frame(self.canvas)

        # Update canvas scrollable area whenever the inner frame is resized
        self.frame.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas_window = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.bind("<Configure>", self._resize_inner_frame, add="+")

        self.canvas.configure(yscrollcommand=self._on_yscroll, xscrollcommand=self._scrollbar_x.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar_y.grid(row=0, column=1, sticky="ns")
        self._scrollbar_x.grid(row=1, column=0, sticky="ew")

        # Set grid weights to make the canvas expand
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # Bind mousewheel to the canvas inside ScrollableFrame
        self._bind_mousewheel()
        self._bind_horizontal_mousewheel()

    def _on_yscroll(self, first: float, last: float) -> None:
        # Tk passes these through as strings; `Scrollbar.set` accepts either.
        self._scrollbar_y.set(first, last)
        if self.on_viewport_change:
            self.on_viewport_change()

    def _resize_inner_frame(self, event: tk.Event[tk.Misc]) -> None:
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    # ---------------------------------------------------------
    # Mousewheel binding helpers
    # ---------------------------------------------------------
    def _bind_mousewheel(self) -> None:
        os = platform.system()
        if os == "Windows":
            self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * int(e.delta / 120), "units"))
        elif os == "Darwin":  # macOS
            self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * int(e.delta), "units"))
        else:  # Linux
            self.canvas.bind("<Button-4>", lambda _e: self.canvas.yview_scroll(-1, "units"))
            self.canvas.bind("<Button-5>", lambda _e: self.canvas.yview_scroll(+1, "units"))

    def _bind_horizontal_mousewheel(self) -> None:
        os = platform.system()
        if os == "Windows":
            self.canvas.bind("<Shift-MouseWheel>", lambda e: self.canvas.xview_scroll(-1 * int(e.delta / 120), "units"))
        elif os == "Darwin":  # macOS
            self.canvas.bind("<Shift-MouseWheel>", lambda e: self.canvas.xview_scroll(-1 * int(e.delta), "units"))
        else:  # Linux
            self.canvas.bind("<Shift-Button-4>", lambda _e: self.canvas.xview_scroll(-1, "units"))
            self.canvas.bind("<Shift-Button-5>", lambda _e: self.canvas.xview_scroll(+1, "units"))
