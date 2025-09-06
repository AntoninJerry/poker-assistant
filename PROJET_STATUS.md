# État du Projet - Assistant IA Poker

## 📋 **Résumé du Projet**

Assistant stratégique de poker qui lit les tables via OCR, analyse avec Ollama (Llama3.1:8b) et recommande des actions optimales, en respectant la conformité gaming (lecture seule, pas d'automation).

## ✅ **Fonctionnalités Complétées**

### **1. Système de Calibration**
- ✅ **Calibrateur de table** (`table_calibrator.py`) : Capture table entière + calibration zones
- ✅ **Interface graphique** : Dessin de zones rank/suit avec persistance
- ✅ **YAML enrichi** : Toutes les zones calibrées pour toutes les cartes
- ✅ **Script de lancement** : `launch_table_calibrator.py`

### **2. Visualisation Temps Réel**
- ✅ **Live preview** (`live_preview.py`) : Aperçu temps réel avec overlays
- ✅ **Zones de cartes** : Visualisation rank (rouge) et suit (vert)
- ✅ **ROIs principales** : Rectangles bleus pour les cartes
- ✅ **Zone de table** : Rectangle orange pointillé
- ✅ **Script de lancement** : `launch_live_preview.py`

### **3. Architecture Modulaire**
- ✅ **Détection de fenêtres** : `windows/detector.py`
- ✅ **Capture d'écran** : `ocr/capture.py` avec MSS et PrintWindow
- ✅ **OCR** : `ocr/readers.py` avec EasyOCR
- ✅ **Parsing** : `ocr/parsers.py` pour données poker
- ✅ **Configuration** : YAML avec ROIs et zones calibrées

## 🎯 **Fichiers Essentiels**

### **Scripts de Lancement**
- `launch_table_calibrator.py` - Calibration des zones rank/suit
- `launch_live_preview.py` - Visualisation temps réel

### **Configuration**
- `src/poker_assistant/rooms/winamax.yaml` - ROIs + zones calibrées
- `src/poker_assistant/ocr/table_calibrator.py` - Calibrateur principal
- `src/poker_assistant/ui/live_preview.py` - Visualisation temps réel

### **Documentation**
- `GUIDE_CALIBRATEUR_ZONES.md` - Guide d'utilisation du calibrateur
- `PROJET_STATUS.md` - Ce fichier (état du projet)

## 🚀 **Prochaines Étapes**

### **Phase 1 : OCR et Détection**
1. **Template matching** pour les cartes (ranks/suits)
2. **OCR amélioré** pour pot, stack, actions
3. **Validation** des données détectées

### **Phase 2 : Intelligence Artificielle**
1. **Intégration Ollama** (Llama3.1:8b)
2. **Moteur de décision** stratégique
3. **Recommandations** en temps réel

### **Phase 3 : Interface Finale**
1. **Overlay** discret sur la table
2. **Voix** pour les recommandations
3. **Interface** de configuration

## 🛠️ **Utilisation Actuelle**

### **Calibration des Zones**
```bash
python launch_table_calibrator.py
```
1. Sélectionnez une table Winamax
2. Choisissez une carte (ex: board_card1)
3. Type "rank" → Dessinez la zone de rang
4. Type "suit" → Dessinez la zone de couleur
5. Répétez pour toutes les cartes
6. Sauvegardez dans le YAML

### **Visualisation Temps Réel**
```bash
python launch_live_preview.py
```
1. Sélectionnez une table Winamax
2. Activez "Zones Cartes" dans l'interface
3. Visualisez les zones calibrées en temps réel
4. Vérifiez la précision du calibrage

## 📊 **Statistiques du Projet**

- **Fichiers supprimés** : 8 fichiers temporaires + caches
- **Zones calibrées** : 14 zones (7 cartes × 2 zones)
- **ROIs définies** : 13 ROIs principales
- **Modules fonctionnels** : 15+ modules Python
- **Scripts de lancement** : 2 scripts principaux

## 🎉 **État Actuel**

Le projet est maintenant **propre et organisé** avec :
- ✅ **Calibration complète** des zones de cartes
- ✅ **Visualisation fonctionnelle** en temps réel
- ✅ **Architecture modulaire** bien structurée
- ✅ **Documentation** complète
- ✅ **Code nettoyé** sans fichiers temporaires

**Prêt pour la phase suivante** : Implémentation de l'OCR et de l'IA ! 🚀
