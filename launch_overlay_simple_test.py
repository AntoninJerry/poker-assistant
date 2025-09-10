# -*- coding: utf-8 -*-
"""
Version simplifiée du HUD pour tester sans les problèmes de performance.
"""
import tkinter as tk
from tkinter import ttk
import threading
import time
from typing import Optional, Dict

# === Modèle de données simplifié ===
class SimpleHandState:
    def __init__(self):
        self.hero_cards = ["Ah", "Kd"]
        self.board = ["As", "Kh", "Qd"]
        self.pot = 150.0
        self.to_call = 75.0
        self.hero_stack = 1000.0
        self.bb = 2.0
        self.hero_name = "TestPlayer"
        self.street = "flop"

# === HUD Simple ===
class SimpleHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Poker HUD - Test Simple")
        self.root.geometry("300x200+100+100")
        self.root.overrideredirect(True)  # Frameless
        self.root.wm_attributes("-topmost", True)
        
        # Interface simple
        self.frame = ttk.Frame(self.root, padding=10)
        self.frame.pack(fill="both", expand=True)
        
        # Labels
        self.hero_label = ttk.Label(self.frame, text="Hero: Ah Kd", font=("Arial", 12))
        self.hero_label.pack(pady=5)
        
        self.board_label = ttk.Label(self.frame, text="Board: As Kh Qd", font=("Arial", 12))
        self.board_label.pack(pady=5)
        
        self.pot_label = ttk.Label(self.frame, text="Pot: 150.0", font=("Arial", 12))
        self.pot_label.pack(pady=5)
        
        self.stack_label = ttk.Label(self.frame, text="Stack: 1000.0", font=("Arial", 12))
        self.stack_label.pack(pady=5)
        
        self.name_label = ttk.Label(self.frame, text="Player: TestPlayer", font=("Arial", 12))
        self.name_label.pack(pady=5)
        
        # Bouton de fermeture
        self.close_btn = ttk.Button(self.frame, text="Fermer", command=self.root.destroy)
        self.close_btn.pack(pady=10)
        
        # Contrôles
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.bind("<F8>", self._toggle_visibility)
        
        # Drag
        self._drag_data = {"x": 0, "y": 0}
        self.root.bind("<Button-1>", self._start_drag)
        self.root.bind("<B1-Motion>", self._on_drag)
        
        print("✅ HUD Simple créé et prêt")
    
    def _start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
    
    def _on_drag(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_data["x"])
        y = self.root.winfo_y() + (event.y - self._drag_data["y"])
        self.root.geometry(f"+{x}+{y}")
    
    def _toggle_visibility(self, event=None):
        current_alpha = self.root.wm_attributes("-alpha")
        new_alpha = 0.3 if current_alpha > 0.5 else 1.0
        self.root.wm_attributes("-alpha", new_alpha)
        print(f"Visibilité: {new_alpha}")
    
    def update_data(self, state: SimpleHandState):
        """Met à jour l'affichage avec de nouvelles données."""
        try:
            self.hero_label.config(text=f"Hero: {' '.join(state.hero_cards)}")
            self.board_label.config(text=f"Board: {' '.join(state.board)}")
            self.pot_label.config(text=f"Pot: {state.pot}")
            self.stack_label.config(text=f"Stack: {state.hero_stack}")
            self.name_label.config(text=f"Player: {state.hero_name}")
            print(f"🔄 HUD mis à jour: {state.hero_name} - {state.hero_cards}")
        except Exception as e:
            print(f"⚠️ Erreur mise à jour HUD: {e}")
    
    def run(self):
        """Lance le HUD."""
        print("🚀 Lancement du HUD Simple...")
        
        # Simulation de données
        def update_loop():
            counter = 0
            while True:
                try:
                    state = SimpleHandState()
                    # Varier les données
                    if counter % 10 < 5:
                        state.hero_cards = ["Ah", "Kd"]
                        state.board = ["As", "Kh", "Qd"]
                    else:
                        state.hero_cards = ["Qc", "Js"]
                        state.board = ["2c", "3h", "4d", "5s"]
                    
                    state.pot = 100.0 + (counter % 50) * 10
                    state.hero_stack = 1000.0 - (counter % 100) * 2
                    state.hero_name = f"Player{counter % 3}"
                    
                    # Mise à jour thread-safe
                    self.root.after(0, lambda s=state: self.update_data(s))
                    
                    counter += 1
                    time.sleep(2.0)  # Mise à jour toutes les 2 secondes
                    
                except Exception as e:
                    print(f"⚠️ Erreur boucle update: {e}")
                    time.sleep(1.0)
        
        # Démarrer la boucle de mise à jour
        update_thread = threading.Thread(target=update_loop, daemon=True)
        update_thread.start()
        
        # Lancer l'interface
        self.root.mainloop()

if __name__ == "__main__":
    print("🎯 Test du HUD Simple")
    print("Contrôles:")
    print("  - F8: Basculer la visibilité")
    print("  - Échap: Fermer")
    print("  - Glisser-déposer: Déplacer")
    
    hud = SimpleHUD()
    hud.run()

