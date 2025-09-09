#!/usr/bin/env python3
"""
Script de lancement pour le live_preview avec visualisation des zones de cartes.
"""

import sys
import os
import signal

# Ajoute le répertoire src au path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    # Ignore Ctrl+C in this launcher to avoid tearing down Tk mainloop unexpectedly
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass
    from poker_assistant.ui.live_preview import show_live_preview
    from poker_assistant.windows.detector import detect_poker_tables
    
    print("=== Live Preview avec Zones de Cartes ===")
    print("Recherche de tables Winamax...")
    
    # Détecte les tables
    candidates = detect_poker_tables("winamax")
    
    if candidates:
        print(f"✅ {len(candidates)} table(s) détectée(s)")
        candidate = candidates[0]
        print(f"📋 Table sélectionnée: {candidate.title}")
        
        # Lance le live preview avec visualisation des zones de cartes
        show_live_preview(
            candidate=candidate,
            yaml_path="src/poker_assistant/rooms/winamax.yaml",
            relative_to="table_zone",
            layout="default"
        )
    else:
        print("❌ Aucune table Winamax détectée")
        print("💡 Ouvrez une table Winamax et relancez le script")
        
except ImportError as e:
    print(f"❌ Erreur d'import: {e}")
    print("💡 Vérifiez que tous les modules sont installés")
except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()
    # Sort proprement sans relancer en boucle depuis certains shells/IDE
    try:
        sys.exit(1)
    except SystemExit:
        pass
