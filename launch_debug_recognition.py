#!/usr/bin/env python3
"""
Lance l'UI debug de reconnaissance pour comparer ce que le système détecte
avec l'image de la table (Hero/Board + confiances + vignettes ROIs).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from poker_assistant.ui.debug_recognition import show_debug_recognition
from poker_assistant.ui.room_selector import choose_table


def main():
    print("=== Debug Reconnaissance ===")
    print("Sélectionnez une table…")
    cand = choose_table(room_pref="winamax")
    if not cand:
        print("❌ Aucune table sélectionnée")
        return
    print(f"📋 Table: {cand.title}")
    show_debug_recognition(
        candidate=cand,
        yaml_path="src/poker_assistant/rooms/winamax.yaml",
        layout="default",
        relative_to="client",
    )


if __name__ == "__main__":
    main()


