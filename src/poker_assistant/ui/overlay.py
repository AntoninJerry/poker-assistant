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
    
    def show(self) -> None:
        """Show the overlay window."""
        if ctk is None:
            print("❌ CustomTkinter not available")
            return
        self.root.mainloop()
    
    def close(self) -> None:
        """Close the overlay window."""
        if ctk is None:
            return
        self.root.quit()
        self.root.destroy()


def main() -> None:
    """Test de l'overlay poker."""
    print("🎮 Test de l'overlay poker")
    
    if ctk is None:
        print("❌ CustomTkinter non disponible")
        return
    
    print("🚀 Création de l'overlay...")
    
    # Créer overlay
    overlay = Overlay()
    
    if overlay.root is None:
        print("❌ Impossible de créer l'overlay")
        return
    
    # Configurer position (coin supérieur droit)
    overlay.root.geometry("200x100+1700+50")
    overlay.root.configure(fg_color="black")
    
    # Mettre à jour le texte
    overlay.update("🎯 FOLD\nConfiance: 85%")
    
    print("✅ Overlay affiché (coin supérieur droit)")
    print("💡 Fermez la fenêtre pour continuer")
    
    # Simuler des mises à jour
    import time
    import threading
    
    def update_loop():
        actions = [
            "🎯 FOLD\nConfiance: 85%",
            "💰 CALL 2.5BB\nConfiance: 72%", 
            "🚀 RAISE 5BB\nConfiance: 91%",
            "🎯 FOLD\nConfiance: 88%"
        ]
        
        for i, action in enumerate(actions):
            time.sleep(2)
            if hasattr(overlay, 'root') and overlay.root:
                overlay.root.after(0, lambda a=action: overlay.update(a))
    
    # Lancer les mises à jour en arrière-plan
    update_thread = threading.Thread(target=update_loop, daemon=True)
    update_thread.start()
    
    # Afficher overlay
    try:
        overlay.show()
    except Exception as e:
        print(f"❌ Erreur overlay: {e}")


if __name__ == "__main__":
    main()
