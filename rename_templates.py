#!/usr/bin/env python3
"""
Script utilitaire pour renommer les templates selon les conventions.
"""

import os
import shutil
from pathlib import Path

def rename_templates():
    """Renomme les templates selon les conventions de nommage."""
    
    # Structure de base
    base_dir = Path("assets/templates/winamax/default")
    ranks_dir = base_dir / "ranks"
    suits_dir = base_dir / "suits"
    
    print("🔄 Renommage des templates selon les conventions...")
    print(f"📁 Dossier de base: {base_dir}")
    
    # Vérifie que les dossiers existent
    if not ranks_dir.exists():
        print(f"❌ Dossier rangs non trouvé: {ranks_dir}")
        return
    
    if not suits_dir.exists():
        print(f"❌ Dossier couleurs non trouvé: {suits_dir}")
        return
    
    # Mapping des rangs
    rank_mapping = {
        "A": "A.png",    # As
        "K": "K.png",    # Roi
        "Q": "Q.png",    # Dame
        "J": "J.png",    # Valet
        "10": "10.png",  # Dix
        "9": "9.png",    # Neuf
        "8": "8.png",    # Huit
        "7": "7.png",    # Sept
        "6": "6.png",    # Six
        "5": "5.png",    # Cinq
        "4": "4.png",    # Quatre
        "3": "3.png",    # Trois
        "2": "2.png",    # Deux
    }
    
    # Mapping des couleurs
    suit_mapping = {
        "h": "h.png",    # Hearts (Cœurs)
        "d": "d.png",    # Diamonds (Carreaux)
        "c": "c.png",    # Clubs (Trèfles)
        "s": "s.png",    # Spades (Piques)
    }
    
    # Renomme les rangs
    print("\n🔴 Renommage des rangs...")
    rank_files = list(ranks_dir.glob("rank_*.png"))
    rank_files.sort()
    
    for i, old_file in enumerate(rank_files):
        if i < len(rank_mapping):
            rank_name = list(rank_mapping.keys())[i]
            new_name = rank_mapping[rank_name]
            new_path = ranks_dir / new_name
            
            print(f"  {old_file.name} → {new_name}")
            shutil.move(str(old_file), str(new_path))
    
    # Renomme les couleurs
    print("\n🟢 Renommage des couleurs...")
    suit_files = list(suits_dir.glob("suit_*.png"))
    suit_files.sort()
    
    for i, old_file in enumerate(suit_files):
        if i < len(suit_mapping):
            suit_name = list(suit_mapping.keys())[i]
            new_name = suit_mapping[suit_name]
            new_path = suits_dir / new_name
            
            print(f"  {old_file.name} → {new_name}")
            shutil.move(str(old_file), str(new_path))
    
    print(f"\n✅ Renommage terminé!")
    print(f"📁 Structure finale:")
    print(f"   {base_dir}/")
    print(f"   ├── ranks/")
    for rank_name in rank_mapping.values():
        rank_path = ranks_dir / rank_name
        if rank_path.exists():
            print(f"   │   ├── {rank_name}")
    print(f"   └── suits/")
    for suit_name in suit_mapping.values():
        suit_path = suits_dir / suit_name
        if suit_path.exists():
            print(f"       ├── {suit_name}")

def show_structure():
    """Affiche la structure actuelle des templates."""
    base_dir = Path("assets/templates/winamax/default")
    
    print("📁 Structure actuelle des templates:")
    print(f"   {base_dir}/")
    
    if base_dir.exists():
        ranks_dir = base_dir / "ranks"
        suits_dir = base_dir / "suits"
        
        if ranks_dir.exists():
            print(f"   ├── ranks/")
            rank_files = list(ranks_dir.glob("*.png"))
            rank_files.sort()
            for rank_file in rank_files:
                print(f"   │   ├── {rank_file.name}")
        
        if suits_dir.exists():
            print(f"   └── suits/")
            suit_files = list(suits_dir.glob("*.png"))
            suit_files.sort()
            for suit_file in suit_files:
                print(f"       ├── {suit_file.name}")
    else:
        print("   ❌ Dossier non trouvé")

if __name__ == "__main__":
    print("=== Utilitaire de Renommage des Templates ===")
    print()
    
    # Affiche la structure actuelle
    show_structure()
    print()
    
    # Demande confirmation
    response = input("Voulez-vous renommer les templates selon les conventions? (y/N): ")
    if response.lower() in ['y', 'yes', 'oui']:
        rename_templates()
    else:
        print("❌ Renommage annulé")
