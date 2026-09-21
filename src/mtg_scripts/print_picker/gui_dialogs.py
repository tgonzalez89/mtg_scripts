import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterable


class GameSelectionDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, games: Iterable[str]) -> None:
        super().__init__(master)
        self.title("Choose card game")
        self.resizable(width=False, height=False)
        self.result = None
        self.transient(cast("tk.Tk", master))

        games = list(games)

        ttk.Label(self, text="Choose the card game to import:").pack(padx=20, pady=(18, 8))
        self.game_list = tk.Listbox(self, height=min(8, len(games)), exportselection=False)
        self.game_list.pack(fill="both", expand=True, padx=20)
        for game in games:
            self.game_list.insert(tk.END, game)
        self.game_list.selection_set(0)
        self.game_list.activate(0)
        self.game_list.bind("<Double-1>", lambda _event: self._select())

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=20, pady=15)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(button_frame, text="Choose", command=self._select).pack(side="right", padx=(0, 8))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()
        self.game_list.focus_set()

    def _select(self) -> None:
        selection = self.game_list.curselection()
        if selection:
            self.result = self.game_list.get(selection[0])
            self.destroy()


class ExportChoiceDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("Export card list")
        self.resizable(width=False, height=False)
        self.result = None
        self.transient(cast("tk.Tk", master))

        ttk.Label(self, text="How would you like to export the card list?").pack(padx=20, pady=(18, 12))
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=20, pady=(0, 18))
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(button_frame, text="Copy to clipboard", command=lambda: self._finish("clipboard")).pack(
            side="right", padx=(0, 8)
        )
        ttk.Button(button_frame, text="Save to file", command=lambda: self._finish("file")).pack(
            side="right", padx=(0, 8)
        )
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()

    def _finish(self, result: str) -> None:
        self.result = result
        self.destroy()


class ProgressDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, title: str) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(width=False, height=False)
        self.transient(cast("tk.Tk", master))
        self.status_label = ttk.Label(self, text="Starting...")
        self.status_label.pack(padx=20, pady=(18, 8))
        self.progress_bar = ttk.Progressbar(self, mode="indeterminate", length=320)
        self.progress_bar.pack(padx=20, pady=(0, 18))
        self.progress_bar.start(10)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.update_idletasks()

    def update_progress(self, message: str, current: int, total: int) -> None:
        self.status_label.configure(text=message)
        if total > 0:
            if self.progress_bar.cget("mode") != "determinate":
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
            self.progress_bar.configure(maximum=total, value=current)
        elif self.progress_bar.cget("mode") != "indeterminate":
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(10)
