# 🔄 Flux de Reconnaissance de Cartes

## 📋 **Fichiers Essentiels du Pipeline**

### **1. Configuration**
- `src/poker_assistant/rooms/winamax.yaml` - Configuration des ROIs et zones de cartes
- `assets/templates/winamax/default/ranks/` - Templates des rangs (A.png, K.png, etc.)
- `assets/templates/winamax/default/suits/` - Templates des couleurs (h.png, s.png, etc.)

### **2. Pipeline Principal**
- `src/poker_assistant/ocr/card_recognition.py` - **CŒUR** du pipeline de reconnaissance
- `src/poker_assistant/ocr/recognition_integration.py` - Intégration dans l'interface

### **3. Interface Utilisateur**
- `src/poker_assistant/ui/live_preview.py` - Interface principale avec reconnaissance
- `src/poker_assistant/ocr/table_calibrator.py` - Outil de calibration des zones

### **4. Outils de Développement**
- `launch_live_preview.py` - Lanceur de l'interface principale
- `launch_table_calibrator.py` - Lanceur du calibrateur

## 🔄 **Flux de Données**

```
1. Capture d'écran (mss) 
   ↓
2. Détection de fenêtre (detector.py)
   ↓
3. Extraction ROIs cartes (winamax.yaml)
   ↓
4. Extraction zones rank/suit (card_recognition.py)
   ↓
5. Prétraitement (resize + blur)
   ↓
6. Template matching multi-variants
   ↓
7. Calcul de confiance (sigmoid)
   ↓
8. Filtrage temporel (5 frames)
   ↓
9. Machine à états (preflop/flop/turn/river)
   ↓
10. Affichage résultats (live_preview.py)
```

## 🗑️ **Fichiers à Nettoyer**

### **Fichiers de Debug Temporaires**
- `debug_*.png` - Images de debug générées
- `preprocessing_*.png` - Images de test de prétraitement
- `compare_templates.py` - Script de test temporaire
- `debug_recognition.py` - Script de debug temporaire
- `test_preprocessing.py` - Script de test temporaire
- `test_card_recognition.py` - Script de test temporaire

### **Dossiers d'Export Temporaires**
- `exported_cards_20250906_150857/` - Export temporaire de cartes

### **Scripts de Renommage**
- `rename_templates.py` - Script de renommage (peut être supprimé après usage)

## ✅ **Fichiers à Conserver**

### **Essentiels**
- `src/poker_assistant/ocr/card_recognition.py`
- `src/poker_assistant/ocr/recognition_integration.py`
- `src/poker_assistant/ui/live_preview.py`
- `src/poker_assistant/ocr/table_calibrator.py`
- `src/poker_assistant/rooms/winamax.yaml`
- `assets/templates/winamax/default/`

### **Utilitaires**
- `launch_live_preview.py`
- `launch_table_calibrator.py`
- `GUIDE_EXPORT_TEMPLATES.md`
- `GUIDE_CALIBRATEUR_ZONES.md`

## 🎯 **Actions de Nettoyage Recommandées**

1. **Supprimer les fichiers de debug temporaires**
2. **Supprimer les dossiers d'export temporaires**
3. **Supprimer les scripts de test temporaires**
4. **Conserver uniquement les fichiers essentiels**
5. **Mettre à jour le .gitignore** pour éviter les futurs fichiers temporaires
