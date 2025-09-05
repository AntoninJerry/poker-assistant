#!/usr/bin/env python3
"""Test du workflow complet de calibration."""

import sys
from pathlib import Path
from poker_assistant.config import AppSettings, load_room_config
from poker_assistant.windows.detector import select_best_poker_window
from poker_assistant.ocr.capture import grab_rect, GrabRect

def test_yaml_loading():
    """Test le chargement des YAML calibrés."""
    print("🧪 Test chargement YAML calibrés")
    
    settings = AppSettings()
    
    for room in ["winamax", "pmu"]:
        yaml_path = settings.ROOMS_DIR / f"{room}.yaml"
        if yaml_path.exists():
            try:
                room_cfg = load_room_config(room, settings)
                print(f"  ✅ {room}.yaml chargé:")
                print(f"     - ROIs: {list(room_cfg.rois.keys())}")
                print(f"     - Templates: {len(room_cfg.templates_confirmators)}")
                print(f"     - Title patterns: {room_cfg.window_title_patterns}")
            except Exception as e:
                print(f"  ❌ Erreur {room}.yaml: {e}")
        else:
            print(f"  ⚠️  {room}.yaml non trouvé (normal si pas calibré)")

def test_rois_on_current_window():
    """Test les ROIs sur la fenêtre actuelle."""
    print("\n🎯 Test ROIs sur fenêtre détectée")
    
    window = select_best_poker_window()
    if not window:
        print("  ❌ Aucune fenêtre poker détectée")
        return
    
    print(f"  📱 Fenêtre: {window.width}x{window.height} at ({window.left},{window.top})")
    
    settings = AppSettings()
    
    # Test avec winamax si existe
    yaml_path = settings.ROOMS_DIR / "winamax.yaml"
    if not yaml_path.exists():
        print("  ⚠️  winamax.yaml non trouvé - lancez d'abord le calibrateur")
        return
    
    try:
        room_cfg = load_room_config("winamax", settings)
        print(f"  ✅ Config chargée: {len(room_cfg.rois)} ROIs")
        
        # Test capture de chaque ROI
        from poker_assistant.ocr.calibrate_gui import _px_from_norm, PxRect
        
        win_px = PxRect(x=window.left, y=window.top, w=window.width, h=window.height)
        
        for roi_name, roi in room_cfg.rois.items():
            try:
                # Convertir coords normalisées → pixels
                roi_px = _px_from_norm({
                    "x": roi.x, "y": roi.y, "w": roi.w, "h": roi.h
                }, win_px)
                
                # Capturer la zone
                roi_img = grab_rect(GrabRect(
                    left=roi_px.x,
                    top=roi_px.y,
                    width=roi_px.w,
                    height=roi_px.h
                ))
                
                print(f"    ✅ {roi_name}: {roi_px.w}x{roi_px.h}px → capture {roi_img.shape}")
                
            except Exception as e:
                print(f"    ❌ {roi_name}: erreur capture - {e}")
                
    except Exception as e:
        print(f"  ❌ Erreur config: {e}")

def test_ocr_with_calibrated_rois():
    """Test OCR avec les ROIs calibrés."""
    print("\n🔍 Test OCR avec ROIs calibrés")
    
    # On peut importer notre OCRReader et tester avec les vraies ROIs
    try:
        from poker_assistant.ocr.readers import OCRReader
        from poker_assistant.config import AppSettings
        
        settings = AppSettings()
        window = select_best_poker_window()
        
        if not window:
            print("  ❌ Pas de fenêtre")
            return
            
        # Capture complète
        frame = grab_rect(GrabRect(
            left=window.left,
            top=window.top,
            width=window.width,
            height=window.height
        ))
        
        # OCR avec settings
        reader = OCRReader()
        state = reader.read_state(frame, settings)
        
        print(f"  📊 GameState OCR:")
        print(f"     pot_bb: {state.pot_bb}")
        print(f"     to_call_bb: {state.to_call_bb}")
        print(f"     street: {state.street}")
        print(f"     hero_cards: {state.hero_cards}")
        print(f"     board_cards: {state.board_cards}")
        
    except Exception as e:
        print(f"  ❌ Erreur OCR: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Test workflow complet calibration."""
    print("🎮 Test Workflow Calibration Complète")
    print("=" * 50)
    
    test_yaml_loading()
    test_rois_on_current_window()
    test_ocr_with_calibrated_rois()
    
    print("\n💡 Pour calibrer de nouveaux ROIs:")
    print("   python -m poker_assistant.ocr.calibrate_gui --room winamax")
    print("   python -m poker_assistant.ocr.calibrate_gui --room pmu")

if __name__ == "__main__":
    main()




