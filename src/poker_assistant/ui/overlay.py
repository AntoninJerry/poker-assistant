from __future__ import annotations

"""CustomTkinter overlay (stub).

Non-intrusive, draggable, topmost overlay to display current advice and values.
"""

try:
    import customtkinter as ctk  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional env
    ctk = None


class Overlay:  # pragma: no cover - UI stub
    def __init__(self) -> None:
        if ctk is None:
            return
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.wm_overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.label = ctk.CTkLabel(self.root, text="Poker Assistant")
        self.label.pack(padx=8, pady=8)

    def update(self, text: str) -> None:
        if ctk is None:
            return
        self.label.configure(text=text)
        self.root.update_idletasks()
