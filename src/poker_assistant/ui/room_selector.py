"""Room selector stub to switch calibration profiles."""

from dataclasses import dataclass
from typing import Literal

try:
    import customtkinter as ctk  # type: ignore[import-untyped]
except ImportError:
    ctk = None


RoomName = Literal["winamax", "pmu"]


@dataclass
class RoomSelector:
    current: RoomName = "winamax"

    def set_room(self, room: RoomName) -> None:
        self.current = room


def show_room_selector() -> RoomName:
    """Show a simple room selection dialog."""
    if ctk is None:
        print("❌ CustomTkinter not available")
        return "winamax"
    
    print("🎯 Ouverture du sélecteur de room...")
    
    selected_room: RoomName = "winamax"
    
    def create_selector():
        nonlocal selected_room
        
        app = ctk.CTk()
        app.title("Poker Assistant - Sélection Room")
        app.geometry("400x300")
        app.resizable(False, False)
        
        # Titre
        title_label = ctk.CTkLabel(
            app, 
            text="Choisissez votre room de poker",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=20)
        
        # Variable pour le choix
        room_var = ctk.StringVar(value="winamax")
        
        # Frame pour les boutons radio
        radio_frame = ctk.CTkFrame(app)
        radio_frame.pack(pady=20, padx=40, fill="x")
        
        # Radio buttons
        winamax_radio = ctk.CTkRadioButton(
            radio_frame,
            text="🟢 Winamax",
            variable=room_var,
            value="winamax"
        )
        winamax_radio.pack(pady=10, padx=20, anchor="w")
        
        pmu_radio = ctk.CTkRadioButton(
            radio_frame,
            text="🔵 PMU Poker",
            variable=room_var,
            value="pmu"
        )
        pmu_radio.pack(pady=10, padx=20, anchor="w")
        
        # Boutons d'action
        button_frame = ctk.CTkFrame(app)
        button_frame.pack(pady=20, fill="x", padx=40)
        
        def on_confirm():
            nonlocal selected_room
            selected_room = room_var.get()  # type: ignore[assignment]
            app.quit()
            app.destroy()
        
        def on_cancel():
            app.quit()
            app.destroy()
        
        confirm_btn = ctk.CTkButton(
            button_frame,
            text="✅ Confirmer",
            command=on_confirm,
            width=150
        )
        confirm_btn.pack(side="left", padx=10, pady=10)
        
        cancel_btn = ctk.CTkButton(
            button_frame,
            text="❌ Annuler",
            command=on_cancel,
            width=150
        )
        cancel_btn.pack(side="right", padx=10, pady=10)
        
        # Info
        info_label = ctk.CTkLabel(
            app,
            text="Cette room sera utilisée pour la détection de tables",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        info_label.pack(pady=10)
        
        app.mainloop()
    
    try:
        create_selector()
    except Exception as e:
        print(f"❌ Erreur GUI: {e}")
        print("🔄 Retour à winamax par défaut")
        selected_room = "winamax"
    
    return selected_room


def main() -> None:
    """Test du sélecteur de room."""
    print("🎮 Test du sélecteur de room")
    
    if ctk is None:
        print("❌ CustomTkinter non disponible")
        print("💡 Installez avec: pip install customtkinter")
        return
    
    print("🚀 Lancement du sélecteur...")
    
    # Test du sélecteur
    room = show_room_selector()
    print(f"✅ Room sélectionnée: {room}")
    
    # Test de la classe RoomSelector
    selector = RoomSelector()
    print(f"📋 Room par défaut: {selector.current}")
    
    selector.set_room(room)
    print(f"📝 Room mise à jour: {selector.current}")


if __name__ == "__main__":
    main()