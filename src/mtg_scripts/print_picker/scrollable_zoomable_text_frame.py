import platform
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


class ScrollableZoomableTextFrame(ttk.Frame):
    """Text widget with vertical and horizontal scrolling and zoom controls."""

    def __init__(self, container: tk.Misc) -> None:
        super().__init__(container)

        self.text_widget = tk.Text(self, wrap="none")

        self.text_font = tkfont.Font(family="Consolas", size=12)
        self.text_widget.configure(font=self.text_font, height=1)

        self._scrollbar_y = ttk.Scrollbar(self, orient="vertical", command=self.text_widget.yview)
        self._scrollbar_x = ttk.Scrollbar(self, orient="horizontal", command=self.text_widget.xview)

        self.text_widget.configure(yscrollcommand=self._scrollbar_y.set, xscrollcommand=self._scrollbar_x.set)

        self.text_widget.grid(row=0, column=0, sticky="nsew")
        self._scrollbar_y.grid(row=0, column=1, sticky="ns")
        self._scrollbar_x.grid(row=1, column=0, sticky="ew")

        # Set grid weights to make the canvas expand
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self._bind_mousewheel()
        self._bind_horizontal_mousewheel()
        self._bind_zoom()

    def _bind_mousewheel(self) -> None:
        if platform.system() in ("Windows", "Darwin"):
            self.text_widget.bind("<MouseWheel>", self._on_mousewheel)
        else:  # Linux
            self.text_widget.bind("<Button-4>", lambda e: self._on_mousewheel_linux(e, -1))
            self.text_widget.bind("<Button-5>", lambda e: self._on_mousewheel_linux(e, +1))

    def _bind_horizontal_mousewheel(self) -> None:
        if platform.system() in ("Windows", "Darwin"):
            self.text_widget.bind("<Shift-MouseWheel>", self._on_horizontal_mousewheel)
        else:  # Linux
            self.text_widget.bind("<Shift-Button-4>", lambda e: self._on_horizontal_mousewheel_linux(e, -1))
            self.text_widget.bind("<Shift-Button-5>", lambda e: self._on_horizontal_mousewheel_linux(e, +1))

    def _bind_zoom(self) -> None:
        if platform.system() in ("Windows", "Darwin"):
            self.text_widget.bind("<Control-MouseWheel>", self._on_zoom_mousewheel)
        else:  # Linux
            self.text_widget.bind("<Control-Button-4>", lambda _e: self._on_zoom_step(+1))
            self.text_widget.bind("<Control-Button-5>", lambda _e: self._on_zoom_step(-1))

        self.text_widget.bind("<Control-plus>", lambda _e: self._on_zoom_step(+1))
        self.text_widget.bind("<Control-KP_Add>", lambda _e: self._on_zoom_step(+1))
        self.text_widget.bind("<Control-minus>", lambda _e: self._on_zoom_step(-1))
        self.text_widget.bind("<Control-KP_Subtract>", lambda _e: self._on_zoom_step(-1))
        self.text_widget.bind("<Control-0>", lambda _e: self._reset_zoom())
        self.text_widget.bind("<Control-KP_0>", lambda _e: self._reset_zoom())

    def _on_zoom_mousewheel(self, event: tk.Event[tk.Misc]) -> str:
        self._on_zoom_step(+1 if event.delta > 0 else -1)
        return "break"

    def _on_zoom_step(self, delta: int) -> None:
        size = self.text_font.cget("size")
        new_size = max(4, min(64, size + delta))
        self.text_font.configure(size=new_size)

    def _reset_zoom(self) -> None:
        self.text_font.configure(size=12)

    def _on_mousewheel(self, event: tk.Event[tk.Misc]) -> str:
        if int(event.state) & (0x1 | 0x4):  # Shift or Control is pressed, ignore vertical scrolling
            return "break"

        scroll_amount = -int(event.delta / 120) if platform.system() == "Windows" else -int(event.delta)
        self.text_widget.yview_scroll(scroll_amount, "units")
        return "break"

    def _on_horizontal_mousewheel(self, event: tk.Event[tk.Misc]) -> str:
        if int(event.state) & 0x4:  # Control takes precedence for zoom
            return "break"

        scroll_amount = -int(event.delta / 120) if platform.system() == "Windows" else -int(event.delta)
        self.text_widget.xview_scroll(scroll_amount, "units")
        return "break"

    def _on_mousewheel_linux(self, event: tk.Event[tk.Misc], amount: int) -> str:
        if int(event.state) & (0x1 | 0x4):  # Shift or Control is pressed, ignore vertical scrolling
            return "break"

        self.text_widget.yview_scroll(amount, "units")
        return "break"

    def _on_horizontal_mousewheel_linux(self, event: tk.Event[tk.Misc], amount: int) -> str:
        if int(event.state) & 0x4:  # Control takes precedence for zoom
            return "break"

        self.text_widget.xview_scroll(amount, "units")
        return "break"
