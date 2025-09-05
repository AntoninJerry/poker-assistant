"""Room selector for poker tables."""

from __future__ import annotations

import tkinter as tk
from typing import List, Optional

from ..windows.detector import CandidateWindow, detect_poker_tables


def choose_table(room_pref: Optional[str] = None) -> Optional[CandidateWindow]:
    """
    Select poker table window.
    If only one table detected -> auto-select.
    Otherwise -> Tkinter selector.
    """
    candidates: List[CandidateWindow] = detect_poker_tables(room_pref)
    
    if not candidates:
        print("Aucune table poker détectée")
        return None
        
    if len(candidates) == 1:
        print(f"Auto-sélection: {candidates[0].title} ({candidates[0].room_guess})")
        return candidates[0]

    # Multiple candidates - show selector
    root = tk.Tk()
    root.title("Choisir la table (Winamax/PMU)")
    root.geometry("800x400")
    
    # Title
    title_label = tk.Label(root, text="Tables poker détectées:", font=("Arial", 12, "bold"))
    title_label.pack(pady=10)
    
    # Listbox
    listbox = tk.Listbox(root, width=100, height=12, font=("Consolas", 10))
    listbox.pack(padx=20, pady=10, fill="both", expand=True)
    
    # Add candidates to listbox
    for i, c in enumerate(candidates):
        room = c.room_guess or "?"
        size = f"{c.bbox[2]-c.bbox[0]}x{c.bbox[3]-c.bbox[1]}"
        item = f"[{i}] {room.upper()} | Score: {c.score:.2f} | {size} | {c.title}"
        listbox.insert(tk.END, item)
    
    # Select first item by default
    listbox.selection_set(0)
    
    chosen: dict = {"value": None}
    
    def on_ok():
        sel = listbox.curselection()
        if sel:
            chosen["value"] = candidates[int(sel[0])]
        root.destroy()
    
    def on_cancel():
        chosen["value"] = None
        root.destroy()
    
    # Buttons
    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)
    
    ok_btn = tk.Button(button_frame, text="OK", command=on_ok, width=10)
    ok_btn.pack(side=tk.LEFT, padx=5)
    
    cancel_btn = tk.Button(button_frame, text="Annuler", command=on_cancel, width=10)
    cancel_btn.pack(side=tk.LEFT, padx=5)
    
    # Instructions
    instructions = tk.Label(
        root, 
        text="Sélectionnez une table et cliquez OK, ou Annuler pour quitter",
        font=("Arial", 9),
        fg="gray"
    )
    instructions.pack(pady=5)
    
    root.mainloop()
    return chosen["value"]


__all__ = ["choose_table"]
