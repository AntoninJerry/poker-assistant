#!/usr/bin/env python3
"""Script de test pour la détection de fenêtres poker."""

from poker_assistant.windows.detector import select_best_poker_window, _score_window_title
import pywinctl as pwc

def test_scoring():
    """Test du système de scoring des titres."""
    print("🎯 Test du scoring des titres:")
    
    test_titles = [
        "Winamax Poker - Table XYZ",
        "PMU Poker - Tournament",
        "Winamax Lobby",
        "Chrome Browser",
        "winamax.yaml - poker-assistant - Cursor",
        "Poker Stars - Main Event",
        "Winamax Home",
        "Shop PMU",
    ]
    
    for title in test_titles:
        score = _score_window_title(title)
        print(f"  {score:3d} | {title}")

def test_detailed_detection():
    """Test détaillé avec plus d'informations."""
    print("\n🔍 Analyse détaillée des fenêtres poker potentielles:")
    
    poker_candidates = []
    
    for win in pwc.getAllWindows():
        title = win.title or ""
        if any(keyword in title.lower() for keyword in ["winamax", "pmu", "poker"]):
            try:
                x, y, w, h = win.getClientFrame()
                score = _score_window_title(title)
                poker_candidates.append({
                    'title': title,
                    'score': score,
                    'size': f"{w}x{h}",
                    'aspect': w/h if h > 0 else 0,
                    'area': w*h,
                    'pos': f"({x},{y})"
                })
            except Exception as e:
                print(f"  ❌ Erreur pour '{title}': {e}")
    
    if poker_candidates:
        print("\n  Candidats trouvés:")
        for candidate in sorted(poker_candidates, key=lambda x: x['score'], reverse=True):
            print(f"    Score: {candidate['score']:3d} | {candidate['title'][:50]}")
            print(f"           Taille: {candidate['size']} | Ratio: {candidate['aspect']:.2f} | Pos: {candidate['pos']}")
    else:
        print("  ❌ Aucun candidat trouvé")

def test_final_detection():
    """Test de la fonction finale."""
    print("\n🏆 Test de la détection finale:")
    result = select_best_poker_window()
    
    if result:
        print(f"  ✅ Fenêtre détectée:")
        print(f"     Position: ({result.left}, {result.top})")
        print(f"     Taille: {result.width}x{result.height}")
        print(f"     Ratio: {result.width/result.height:.2f}")
        print(f"     Aire: {result.width * result.height:,} pixels")
    else:
        print("  ❌ Aucune fenêtre détectée")

if __name__ == "__main__":
    test_scoring()
    test_detailed_detection()
    test_final_detection()
    
    print("\n💡 Pour tester avec une vraie table poker:")
    print("   1. Ouvrez Winamax ou PMU Poker")
    print("   2. Lancez une table (pas le lobby)")
    print("   3. Relancez ce script")
