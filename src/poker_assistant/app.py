# src/poker_assistant/app.py
from poker_assistant.ui.room_selector import choose_table
from poker_assistant.ui.live_preview import show_live_preview

def main():
    """Point d'entrée principal de l'application."""
    print("=== Assistant IA Poker ===")
    
    # Sélection de la table
    cand = choose_table(room_pref=None)
    if not cand:
        print("Aucune table détectée")
        raise SystemExit(1)

    print(f"Table choisie: {cand.room_guess} - {cand.title} - bbox={cand.bbox}")

    # Aperçu temps réel avec ROIs calibrés
    show_live_preview(
        cand,
        yaml_path="src/poker_assistant/rooms/winamax.yaml",
        layout="default",
        relative_to="client",   # ROIs normalisées au client (comme dans le YAML actuel)
        track_move=True,
        target_fps=10,          # Réduit la fréquence pour éviter le clignotement
        scale=0.9,
        stay_on_top=False,      # Évite l'effet miroir
        anti_mirror=False,      # Désactive l'anti-miroir pour éviter les conflits
    )

if __name__ == "__main__":
    main()
