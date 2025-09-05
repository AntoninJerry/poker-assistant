#!/usr/bin/env python3
"""Test du calibrateur amélioré - anchors + ROIs relatifs."""

from pathlib import Path
import sys

def test_calibrator():
    """Test rapide du calibrateur sans UI."""
    print("🎯 Test du calibrateur amélioré")
    
    try:
        from poker_assistant.ocr.calibrate_gui import CalibratorApp, PxRect, _norm_from_px, _px_from_norm
        from poker_assistant.config import AppSettings
        
        # Test des fonctions utilitaires
        print("✅ Imports réussis")
        
        # Test conversion coordonnées
        win = PxRect(x=100, y=50, w=800, h=600)
        roi = PxRect(x=200, y=150, w=100, h=80)
        
        norm = _norm_from_px(roi, win)
        print(f"📏 Coord normalisées: {norm}")
        
        back = _px_from_norm(norm, win)
        print(f"🔄 Retour pixels: x={back.x}, y={back.y}, w={back.w}, h={back.h}")
        
        # Vérifier cohérence
        assert abs(back.x - roi.x) <= 1, "Erreur conversion X"
        assert abs(back.y - roi.y) <= 1, "Erreur conversion Y"
        print("✅ Conversions coordonnées OK")
        
        # Test constantes
        app_class = CalibratorApp
        print(f"🎯 Anchors: {app_class.ANCHOR_NAMES}")
        print(f"🎮 ROIs core: {app_class.CORE_ROIS[:5]}...")  # Premiers éléments
        print(f"⚙️ ROIs optionnels: {app_class.OPTIONAL_ROIS}")
        
        print("\n🎉 Tous les tests passent !")
        print("💡 Pour lancer l'interface : python -m poker_assistant.ocr.calibrate_gui")
        
    except ImportError as e:
        print(f"❌ Erreur import: {e}")
        return False
    except Exception as e:
        print(f"❌ Erreur test: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = test_calibrator()
    sys.exit(0 if success else 1)




