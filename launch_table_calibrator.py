#!/usr/bin/env python3
"""
Lanceur pour le calibrateur de table entière
"""

import os
import sys

# Ajouter le chemin du projet
sys.path.insert(0, 'src')

from poker_assistant.ocr.table_calibrator import run_table_calibrator

if __name__ == "__main__":
    print("=== Calibrateur de Table Entière ===")
    print("Ce calibrateur capture la table entière et permet de")
    print("définir précisément les zones de rangs et couleurs")
    print("dans chaque carte avec superposition visuelle.")
    print()
    
    yaml_path = "src/poker_assistant/rooms/winamax.yaml"
    
    if not os.path.exists(yaml_path):
        print(f"❌ Fichier YAML non trouvé: {yaml_path}")
        print("Vérifiez que le fichier de configuration existe.")
        sys.exit(1)
    
    print(f"✅ Configuration: {yaml_path}")
    print()
    print("Instructions:")
    print("1. Sélectionnez une table de poker")
    print("2. La table entière sera capturée et affichée")
    print("3. Les zones de cartes existantes seront superposées")
    print("4. Cliquez sur une carte pour ajouter des zones")
    print("5. Dessinez les zones de rangs et couleurs")
    print("6. Sauvegardez les zones dans le YAML")
    print()
    
    try:
        run_table_calibrator(yaml_path)
    except KeyboardInterrupt:
        print("\n👋 Calibration interrompue par l'utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
