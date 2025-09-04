#!/usr/bin/env python3
"""Test rapide de l'app principale sans boucle infinie."""

import time
from poker_assistant.app import main
from poker_assistant.config import AppSettings
from poker_assistant.windows.detector import select_best_poker_window
from poker_assistant.ocr.capture import grab_rect, GrabRect
from poker_assistant.ocr.readers import OCRReader

def test_components():
    """Test des composants individuels."""
    print("🧪 Test des composants:")
    
    # 1. Configuration
    try:
        config = AppSettings()
        print(f"  ✅ Config: MODEL={config.MODEL_NAME}, ROOM={config.ROOM}")
    except Exception as e:
        print(f"  ❌ Config error: {e}")
        return
    
    # 2. Détection fenêtre
    try:
        window = select_best_poker_window()
        if window:
            print(f"  ✅ Window: {window.width}x{window.height} at ({window.left},{window.top})")
        else:
            print("  ⚠️  No poker window detected")
            return
    except Exception as e:
        print(f"  ❌ Window detection error: {e}")
        return
    
    # 3. Capture écran
    try:
        frame = grab_rect(GrabRect(
            left=window.left,
            top=window.top,
            width=min(window.width, 400),  # Petite zone pour test
            height=min(window.height, 300)
        ))
        print(f"  ✅ Capture: {frame.shape} {frame.dtype}")
    except Exception as e:
        print(f"  ❌ Capture error: {e}")
        return
    
    # 4. OCR Reader
    try:
        reader = OCRReader()
        state = reader.read_state(frame, config)
        print(f"  ✅ OCR: pot={state.pot_bb}, call={state.to_call_bb}, street={state.street}")
    except Exception as e:
        print(f"  ❌ OCR error: {e}")
    
    print("\n🎯 Tous les composants de base fonctionnent !")

def test_app_iteration():
    """Test une seule itération de la boucle principale."""
    print("\n🚀 Test d'une itération app:")
    
    # On peut pas tester main() directement car elle a une boucle infinie
    # Donc on simule une itération
    
    from poker_assistant.config import AppSettings
    from poker_assistant.windows.detector import select_best_poker_window
    from poker_assistant.ocr.capture import grab_rect, GrabRect
    from poker_assistant.ocr.readers import OCRReader
    from poker_assistant.strategy.engine import DecisionEngine
    from poker_assistant.telemetry.logging import get_logger
    
    try:
        logger = get_logger()
        config = AppSettings()
        
        window = select_best_poker_window()
        if not window:
            print("  ❌ No window for app test")
            return
        
        ocr_reader = OCRReader()
        engine = DecisionEngine.from_config(config)
        
        # Une itération
        frame = grab_rect(GrabRect(
            left=window.left,
            top=window.top,
            width=window.width,
            height=window.height
        ))
        
        state = ocr_reader.read_state(frame, config)
        print(f"  📊 GameState: {state}")
        
        # Test strategy (sans Ollama pour éviter erreur réseau)
        from poker_assistant.strategy.providers.rules_ import RulesProvider
        rules_provider = RulesProvider()
        advice = rules_provider.advise(state)
        print(f"  🤖 Advice: {advice}")
        
        print("  ✅ Une itération complète réussie !")
        
    except Exception as e:
        print(f"  ❌ App iteration error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_components()
    test_app_iteration()
    
    print("\n💡 Pour lancer l'app complète:")
    print("   python -m poker_assistant.app")
    print("   (Ctrl+C pour arrêter)")
