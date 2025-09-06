# 🎯 Guide d'Utilisation - Calibrateur de Zones de Cartes

## 📋 Vue d'ensemble

Le calibrateur de zones de cartes vous permet de définir précisément les zones de **rangs** (A,K,Q,J,T,9-2) et de **couleurs** (♠♥♦♣) dans chaque carte de votre table de poker, sans écraser votre configuration YAML existante.

## 🚀 Lancement

```bash
python launch_card_calibrator.py
```

## 📝 Instructions d'Utilisation

### 1. **Sélection de la Table**
- Le calibrateur détecte automatiquement les tables de poker ouvertes
- Sélectionnez la table sur laquelle vous voulez calibrer les zones
- ✅ **Table sélectionnée** : Winamax Aalen 18

### 2. **Interface Graphique**
L'interface se compose de :
- **Liste déroulante** : Sélection de la carte à calibrer
- **Type de zone** : "rank" (rang) ou "suit" (couleur)
- **Zone d'affichage** : Image de la carte avec zones dessinées
- **Boutons de contrôle** : Recapturer, Ajouter Zone, Supprimer, Sauvegarder

### 3. **Calibration des Zones**

#### **Sélection de la Carte**
- Choisissez une carte dans la liste déroulante :
  - `board_card1` à `board_card5` (cartes du board)
  - `hero_cards_left` et `hero_cards_right` (cartes du héros)

#### **Type de Zone**
- **"rank"** : Pour les rangs (A,K,Q,J,T,9-2) - Zone rouge
- **"suit"** : Pour les couleurs (♠♥♦♣) - Zone verte

#### **Dessin des Zones**
1. **Cliquez-glissez** sur l'image de la carte
2. **Zone bleue** : Zone en cours de dessin
3. **Zone colorée** : Zone finalisée (rouge=rank, vert=suit)
4. **Label** : Nom et type de chaque zone

### 4. **Sauvegarde**

#### **Sauvegarde par Carte**
- Cliquez sur **"Sauvegarder"** pour sauvegarder les zones de la carte actuelle
- Les zones sont stockées temporairement

#### **Sauvegarde Complète**
- Cliquez sur **"Sauvegarder Tout"** pour écrire dans le YAML
- Les zones sont ajoutées à la section `card_zones`

## 📊 Structure YAML Résultante

### **Avant Calibration**
```yaml
layouts:
  default:
    rois:
      board_card1:
        x: 0.294
        y: 0.341
        w: 0.076
        h: 0.154
```

### **Après Calibration**
```yaml
layouts:
  default:
    rois:
      board_card1:
        x: 0.294
        y: 0.341
        w: 0.076
        h: 0.154
      # ... autres cartes (inchangées)

# NOUVELLE SECTION AJOUTÉE
card_zones:
  board_card1:
    rank_1:
      x: 0.1          # Position X (normalisée 0.0-1.0)
      y: 0.1          # Position Y (normalisée 0.0-1.0)
      w: 0.3          # Largeur (normalisée 0.0-1.0)
      h: 0.4          # Hauteur (normalisée 0.0-1.0)
      type: rank      # Type: "rank" ou "suit"
    suit_1:
      x: 0.1
      y: 0.6
      w: 0.3
      h: 0.3
      type: suit
```

## 🎨 Codes Couleurs

- **🔴 Rouge** : Zones de rangs (rank)
- **🟢 Vert** : Zones de couleurs (suit)
- **🔵 Bleu** : Zone en cours de dessin
- **⚫ Noir** : Labels des zones

## ⚙️ Fonctionnalités Avancées

### **Recapture d'Image**
- Bouton **"Recapturer"** pour mettre à jour l'image de la table
- Utile si la table a changé ou si vous voulez une image plus récente

### **Suppression de Zones**
- Bouton **"Supprimer Dernière"** pour retirer la dernière zone ajoutée
- Permet de corriger les erreurs rapidement

### **Modification des Zones**
- Les zones existantes sont automatiquement chargées
- Vous pouvez les modifier en dessinant de nouvelles zones
- Les anciennes zones sont remplacées par les nouvelles

## 🔧 Dépannage

### **Problème : Aucune carte détectée**
- Vérifiez que votre YAML contient des ROIs de cartes
- Les cartes doivent avoir des noms contenant "card"

### **Problème : Capture d'image échoue**
- Assurez-vous que la table de poker est visible
- Essayez de cliquer sur la table pour la mettre au premier plan
- Utilisez le bouton "Recapturer"

### **Problème : Zones mal positionnées**
- Les coordonnées sont normalisées (0.0-1.0) par rapport à chaque carte
- Dessinez les zones en tenant compte de la taille réelle de la carte
- Vous pouvez ajuster en supprimant et redessinant

## 📈 Conseils d'Utilisation

### **Pour les Cartes du Board**
- **Rangs** : Zone généralement en haut à gauche de la carte
- **Couleurs** : Zone généralement en bas à droite de la carte
- Dessinez des zones assez grandes pour capturer les symboles

### **Pour les Cartes du Héros**
- Les cartes sont plus petites, soyez précis
- **Rangs** : Zone centrale haute
- **Couleurs** : Zone centrale basse

### **Optimisation**
- Dessinez des zones légèrement plus grandes que les symboles
- Évitez les zones qui se chevauchent
- Testez avec différentes cartes pour valider la calibration

## 🎉 Résultat Final

Après calibration, votre YAML contiendra :
- ✅ **Configuration originale** préservée
- ✅ **Section `card_zones`** ajoutée
- ✅ **Zones de rangs et couleurs** pour chaque carte
- ✅ **Coordonnées normalisées** pour la compatibilité

Ces zones pourront ensuite être utilisées par les modules de détection de cartes pour atteindre une précision >98% ! 🃏
