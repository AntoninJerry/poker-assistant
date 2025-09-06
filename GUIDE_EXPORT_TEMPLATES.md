# Guide d'Exportation de Templates

## 🎯 **Objectif**

Créer automatiquement une banque de templates de rangs et couleurs à partir des zones calibrées dans le YAML, pour alimenter le système de reconnaissance par template matching.

## 🚀 **Utilisation Rapide**

### **1. Lancement de l'Application**
```bash
python src/poker_assistant/app.py
```

### **2. Exportation des Templates**
1. **Ouvrez une table Winamax** avec des cartes visibles
2. **Cliquez sur "Exporter les templates"** dans l'interface
3. **Attendez la confirmation** d'exportation
4. **Vérifiez les dossiers créés** : `assets/templates/winamax/default/ranks/` et `assets/templates/winamax/default/suits/`

### **3. Renommage Automatique**
Utilisez le script utilitaire pour renommer automatiquement :

```bash
python rename_templates.py
```

**Conventions de nommage :**

**Rangs :**
- `rank_001.png` → `A.png` (As)
- `rank_002.png` → `K.png` (Roi)
- `rank_003.png` → `Q.png` (Dame)
- `rank_004.png` → `J.png` (Valet)
- `rank_005.png` → `10.png` (Dix)
- `rank_006.png` → `9.png` (Neuf)
- `rank_007.png` → `8.png` (Huit)
- `rank_008.png` → `7.png` (Sept)
- `rank_009.png` → `6.png` (Six)
- `rank_010.png` → `5.png` (Cinq)
- `rank_011.png` → `4.png` (Quatre)
- `rank_012.png` → `3.png` (Trois)
- `rank_013.png` → `2.png` (Deux)

**Couleurs :**
- `suit_001.png` → `h.png` (Hearts ♥)
- `suit_002.png` → `d.png` (Diamonds ♦)
- `suit_003.png` → `c.png` (Clubs ♣)
- `suit_004.png` → `s.png` (Spades ♠)

## 📁 **Structure Générée**

```
assets/
└── templates/
    └── winamax/
        └── default/
            ├── ranks/                       # Templates des rangs
            │   ├── rank_001.png             # À renommer en A.png
            │   ├── rank_002.png             # À renommer en K.png
            │   ├── rank_003.png             # À renommer en Q.png
            │   └── ...
            └── suits/                       # Templates des couleurs
                ├── suit_001.png             # À renommer en h.png
                ├── suit_002.png             # À renommer en d.png
                └── ...
```

## 🔧 **Fonctionnement Technique**

### **Processus d'Export**
1. **Lecture du YAML** : Récupère les zones `card_zones` calibrées
2. **Capture d'écran** : Utilise la dernière image capturée
3. **Calcul des coordonnées** : Convertit les zones normalisées en pixels
4. **Extraction des zones** : Crop chaque zone rank/suit individuellement
5. **Sauvegarde** : Exporte en PNG avec noms génériques

### **Coordonnées Utilisées**
- **Base** : Zones de cartes définies dans `layouts.rois`
- **Référence** : Zones rank/suit définies dans `card_zones`
- **Calcul** : Coordonnées absolues = ROI_carte + (zone_rel × dimensions_carte)

## 🎨 **Qualité des Templates**

### **Spécifications**
- **Format** : PNG avec transparence
- **Taille** : Variable selon la zone calibrée (typiquement 20-40px)
- **Qualité** : Haute résolution pour reconnaissance précise
- **Cadrage** : Exact selon les zones calibrées

### **Optimisation**
- **Capture nette** : Assurez-vous que la table est bien visible
- **Éclairage uniforme** : Évitez les reflets ou ombres
- **Cartes distinctes** : Utilisez des cartes avec des rangs/couleurs clairs

## 🚨 **Dépannage**

### **Problèmes Courants**

#### **"Aucune zone de carte calibrée trouvée"**
- ✅ **Solution** : Utilisez d'abord le calibrateur (`python launch_table_calibrator.py`)
- ✅ **Vérifiez** : Le YAML contient bien la section `card_zones`

#### **"Aucune image disponible pour l'export"**
- ✅ **Solution** : Attendez que l'application capture une image
- ✅ **Vérifiez** : La table est bien visible et détectée

#### **"Aucun template n'a pu être exporté"**
- ✅ **Solution** : Vérifiez que les zones sont bien calibrées
- ✅ **Vérifiez** : Les coordonnées dans le YAML sont valides

### **Validation des Templates**
- [ ] **Tous les rangs** sont présents (A, K, Q, J, 10, 9, 8, 7, 6, 5, 4, 3, 2)
- [ ] **Toutes les couleurs** sont présentes (♠, ♥, ♦, ♣)
- [ ] **Images nettes** et bien cadrées
- [ ] **Noms corrects** après renommage
- [ ] **Correspondance** avec les cartes visibles

## 🎯 **Prochaines Étapes**

Une fois les templates créés et renommés :

1. **Test de reconnaissance** : Vérifiez que le template matching fonctionne
2. **Ajustement des seuils** : Optimisez la confiance de détection
3. **Intégration** : Utilisez dans le système de recommandations
4. **Mise à jour** : Renouvelez si l'interface change

## 💡 **Conseils d'Utilisation**

- **Capturez plusieurs variantes** de chaque rang/couleur si possible
- **Testez sur différentes tables** pour valider la robustesse
- **Gardez une copie de sauvegarde** des templates originaux
- **Documentez les changements** si vous modifiez les templates
