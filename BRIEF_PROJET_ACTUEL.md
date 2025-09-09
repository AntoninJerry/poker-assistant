# 📋 Brief Projet Assistant IA Poker - État Actuel

## 🎯 **Vue d'Ensemble**

**Assistant IA Poker** - Assistant stratégique pour tables de poker en ligne avec OCR et IA locale (Ollama).

### **Mission**
- **Lecture écran uniquement** (OCR) des tables de poker
- **Analyse locale** via Ollama (llama3.1:8b) 
- **Recommandations** affichées dans un overlay discret
- **Conformité gaming stricte** : aucune automation, lecture seule

## ✅ **Fonctionnalités Implémentées**

### **1. Détection de Fenêtres** 🎯
- ✅ **Détection automatique** des tables Winamax/PMU
- ✅ **Scoring intelligent** basé sur titre et classe
- ✅ **Sélection** de la meilleure table disponible
- ✅ **2 tables Winamax** actuellement détectées

### **2. Capture d'Écran** 📸
- ✅ **Capture robuste** via `mss` et `pywin32`
- ✅ **ROIs calibrés** via fichiers YAML
- ✅ **Anti-miroir** pour éviter les conflits
- ✅ **Support plein écran** et fenêtré

### **3. Reconnaissance de Cartes** 🃏
- ✅ **Pipeline OpenCV** complet avec templates adaptatifs
- ✅ **52 templates** (13 rangs × 4 couleurs avec variantes)
- ✅ **Format lisible** : "Ah", "Ks", "Qd"
- ✅ **Confiance calibrée** avec filtrage temporel
- ✅ **Machine à états** (preflop/flop/turn/river)

### **4. Interface Utilisateur** 🖥️
- ✅ **Live Preview** avec overlays en temps réel
- ✅ **Calibrateur de zones** pour ROIs
- ✅ **Sélecteur de tables** automatique
- ✅ **Options de debug** (zones, rectangles, labels)
- ✅ **Export de cartes** et templates

### **5. Configuration** ⚙️
- ✅ **YAML Winamax** avec ROIs calibrés
- ✅ **Zones de cartes** avec sous-zones rank/suit
- ✅ **Templates** configurés pour reconnaissance
- ✅ **Anchors** : table_zone et client

## 🚧 **Fonctionnalités Partiellement Implémentées**

### **1. OCR Textuel** 📝
- 🔄 **EasyOCR** intégré mais pas optimisé
- 🔄 **Parsing** des données poker (pot, stack, actions)
- 🔄 **Validation** des données détectées

### **2. Intelligence Artificielle** 🤖
- 🔄 **Ollama** configuré mais pas intégré
- 🔄 **Moteur de décision** stratégique en développement
- 🔄 **Recommandations** JSON strict non implémentées

### **3. Interface Finale** 🎨
- 🔄 **Overlay** discret sur la table
- 🔄 **Voix** pour les recommandations
- 🔄 **Interface** de configuration avancée

## ❌ **Fonctionnalités Manquantes**

### **1. Intégration Ollama** 🤖
- ❌ **Connexion** à Ollama (llama3.1:8b)
- ❌ **Prompts** stratégiques pour poker
- ❌ **Parsing JSON** des réponses
- ❌ **Gestion d'erreurs** et fallbacks

### **2. Moteur de Décision** 🧠
- ❌ **Analyse** de la situation de jeu
- ❌ **Calcul** des cotes et EV
- ❌ **Profils** des adversaires
- ❌ **Recommandations** contextuelles

### **3. Interface Overlay** 🎯
- ❌ **Overlay** CustomTkinter discret
- ❌ **Positionnement** automatique sur la table
- ❌ **Affichage** des recommandations
- ❌ **Interaction** utilisateur minimale

### **4. Fonctionnalités Avancées** ⚡
- ❌ **Support PMU** avec calibration spécifique
- ❌ **Multi-tables** simultanées
- ❌ **Historique** des parties
- ❌ **Statistiques** de performance

## 📊 **État Technique Actuel**

### **Architecture** 🏗️
- ✅ **Modulaire** : 8 modules bien structurés
- ✅ **Type hints** : Code typé avec mypy
- ✅ **Tests** : Structure de tests en place
- ✅ **Documentation** : README et guides complets

### **Performance** ⚡
- ✅ **Capture** : Stable avec MSS
- ✅ **Reconnaissance** : < 200ms par ROI
- ✅ **Interface** : Stable sans clignotement
- ✅ **Mémoire** : < 500 MB

### **Sécurité** 🔒
- ✅ **Lecture seule** : Aucune automation
- ✅ **Pas d'injection** : Respect des processus
- ✅ **Conformité gaming** : Respect des règles

## 🚀 **Prochaines Étapes Prioritaires**

### **Phase 1 : Intégration Ollama** (1-2 semaines)
1. **Connexion** à Ollama local
2. **Prompts** stratégiques pour poker
3. **Parsing JSON** des réponses
4. **Tests** avec vraies situations

### **Phase 2 : Moteur de Décision** (2-3 semaines)
1. **Analyse** de la situation de jeu
2. **Calcul** des cotes et EV
3. **Recommandations** contextuelles
4. **Validation** des décisions

### **Phase 3 : Interface Overlay** (1-2 semaines)
1. **Overlay** CustomTkinter discret
2. **Positionnement** automatique
3. **Affichage** des recommandations
4. **Tests** en conditions réelles

## 🎯 **Commandes de Test Actuelles**

```bash
# Application principale
python -m src.poker_assistant.app

# Live preview avec reconnaissance
python launch_live_preview.py

# Calibrateur de zones
python launch_table_calibrator.py
```

## 📈 **Progression du Projet**

- **Détection** : 100% ✅
- **Capture** : 100% ✅
- **Reconnaissance cartes** : 100% ✅
- **Interface** : 80% 🔄
- **OCR textuel** : 30% 🔄
- **IA/Ollama** : 10% 🔄
- **Overlay final** : 0% ❌

## 🎉 **Conclusion**

Le projet est **solide et bien avancé** avec :
- ✅ **Fondations techniques** complètes
- ✅ **Reconnaissance de cartes** fonctionnelle
- ✅ **Interface** stable et utilisable
- 🔄 **Prêt** pour l'intégration IA

**Prochaine étape critique** : Intégration d'Ollama pour les recommandations stratégiques ! 🚀

