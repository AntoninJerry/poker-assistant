#!/usr/bin/env python3
"""
Module de reconnaissance textuelle (OCR) pour les éléments de table poker.
"""

import cv2
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import re
import time
from collections import deque
import yaml
from pathlib import Path
from datetime import datetime

@dataclass
class TextResult:
    """Résultat de reconnaissance textuelle."""
    text: str = ""
    confidence: float = 0.0
    normalized_value: Optional[float] = None
    is_valid: bool = False
    raw_ocr_text: str = ""

class TextRecognitionPipeline:
    """Pipeline de reconnaissance textuelle pour les éléments de table."""
    
    def __init__(self, yaml_path: str):
        """
        Initialise le pipeline de reconnaissance textuelle.
        
        Args:
            yaml_path: Chemin vers le fichier YAML de configuration
        """
        self.yaml_path = yaml_path
        
        # Configuration EasyOCR (lazy-load)
        self.whitelist = "0123456789kKM€.,ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        self.reader = None  # initialisé à la demande
        
        # Configuration du preprocessing améliorée
        self.adaptive_thresh_block_size = 15  # Plus grand pour les petites zones
        self.adaptive_thresh_c = 3  # Plus de contraste
        self.clahe_clip_limit = 3.0  # Plus d'amélioration de contraste
        self.clahe_tile_grid_size = (4, 4)  # Plus fin pour les petites zones
        
        # Configuration du filtrage EMA plus strict
        self.ema_alpha = 0.15  # Plus lisse pour éviter les variations
        self.variation_threshold = 0.2  # Plus strict pour ignorer les sauts
        self.min_confidence = 0.1  # Seuil de confiance minimum (très tolérant pour debug)
        self.max_value_change = 0.3  # Changement maximum relatif autorisé (30%)
        
        # Configuration du debug OCR
        self.debug_ocr = False  # Active l'export PNG des zones OCR
        self.debug_export_dir = Path("debug_ocr")
        self.debug_export_interval = 1.0  # Intervalle entre exports (secondes)
        self.last_debug_export = {}  # Timestamp du dernier export par zone
        
        # Métriques de performance
        self.performance_metrics = {
            'total_calls': 0,
            'total_time': 0.0,
            'avg_time': 0.0,
            'last_call_time': 0.0
        }
        
        # Chargement de la configuration
        self._load_config()
        
        # Initialisation des buffers EMA
        self._init_ema_buffers()
        
        # Patterns de normalisation
        self._init_normalization_patterns()

    def _ensure_reader(self) -> None:
        """Charge EasyOCR à la demande pour éviter les imports lourds au démarrage."""
        if self.reader is not None:
            return
        try:
            import easyocr  # type: ignore
            # Langue minimale (chiffres/symboles), GPU off pour stabilité
            self.reader = easyocr.Reader(['en'], gpu=False)
        except Exception as exc:
            raise RuntimeError(f"EasyOCR non disponible: {exc}")
        
    def _load_config(self):
        """Charge la configuration depuis le YAML."""
        try:
            with open(self.yaml_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            # Récupère les layouts
            self.layouts = self.config.get('layouts', {})
            self.current_layout = 'default'
            
            print(f"✅ Configuration textuelle chargée: {len(self.layouts)} layouts")
            
        except Exception as e:
            raise RuntimeError(f"Erreur chargement config textuelle: {e}")
    
    def _init_ema_buffers(self):
        """Initialise les buffers pour le filtrage EMA."""
        self.ema_values = {
            'pot_combined': None,
            'hero_stack': None,
            'to_call': None,
            'hero_name': None
        }
        
        # Buffers pour la persistance des valeurs stables
        self.stable_values = {
            'pot_combined': None,
            'hero_stack': None,
            'to_call': None,
            'hero_name': None
        }
        
        self.last_update_times = {
            'pot_combined': 0,
            'hero_stack': 0,
            'to_call': 0,
            'hero_name': 0
        }
    
    def _init_normalization_patterns(self):
        """Initialise les patterns de normalisation."""
        # Patterns pour la conversion des valeurs monétaires
        self.money_patterns = [
            # Format: 10.5k, 2.3M, etc.
            (r'(\d+(?:[.,]\d+)?)\s*([kK])', lambda m: float(m.group(1).replace(',', '.')) * 1000),
            (r'(\d+(?:[.,]\d+)?)\s*([mM])', lambda m: float(m.group(1).replace(',', '.')) * 1000000),
            # Format: 0.15, 1.50, 10.25, etc. (valeurs décimales directes)
            (r'(\d+[.,]\d+)', lambda m: float(m.group(1).replace(',', '.'))),
            # Format: 10500, 2300000, etc. (valeurs entières)
            (r'(\d+)', lambda m: float(m.group(1))),
        ]
        
        # Patterns pour les noms (lettres uniquement)
        self.name_patterns = [
            (r'[a-zA-Z\s]+', lambda m: m.group(0).strip()),
        ]
        
        # Corrections d'erreurs courantes (seulement pour les valeurs monétaires)
        self.character_corrections = {
            'O': '0', 'o': '0',  # O -> 0
            'I': '1', 'l': '1',  # I/l -> 1
            'S': '5', 's': '5',  # S -> 5
            'B': '8', 'b': '8',  # B -> 8
            'G': '6', 'g': '6',  # G -> 6
        }
        
        # Corrections spécifiques pour les noms (plus conservatrices)
        self.name_corrections = {
            # Ne pas corriger les caractères valides dans les noms
        }
    
    def _preprocess_image(self, img: np.ndarray) -> np.ndarray:
        """
        Preprocessing d'image pour améliorer la reconnaissance OCR.
        
        Args:
            img: Image en niveaux de gris
            
        Returns:
            Image prétraitée
        """
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()
        
        # Redimensionnement pour améliorer la reconnaissance (minimum 50px de hauteur pour les petites zones)
        h, w = gray.shape
        if h < 50:
            scale = 50.0 / h
            new_w = int(w * scale)
            new_h = int(h * scale)
            gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        
        # Amélioration du contraste avec CLAHE
        clahe = cv2.createCLAHE(
            clipLimit=self.clahe_clip_limit,
            tileGridSize=self.clahe_tile_grid_size
        )
        enhanced = clahe.apply(gray)
        
        # Flou gaussien léger pour réduire le bruit
        blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)
        
        # Seuillage adaptatif
        thresh = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            self.adaptive_thresh_block_size,
            self.adaptive_thresh_c
        )
        
        # Morphologie pour nettoyer
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        return cleaned
    
    def _extract_text_zones(self, frame: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Extrait les zones de texte depuis le frame.
        
        Args:
            frame: Image de la table
            
        Returns:
            Dictionnaire des zones par nom d'élément
        """
        text_zones = {}
        
        # Récupère le layout actuel
        layout_config = self.layouts.get(self.current_layout, {})
        rois_config = layout_config.get('rois', {})
        
        frame_h, frame_w = frame.shape[:2]
        
        # Utilise la même base que l'overlay visuel (client)
        coords = (self.config or {}).get("coords", {}) or {}
        base = coords.get("base") if coords.get("base") in ("client", "table") else "client"
        
        if base == "client":
            # Base client : coordonnées directes
            for element_name, roi_config in rois_config.items():
                # Liste stricte des zones textuelles supportées
                lname = element_name.lower()
                allowed = lname in (
                    'pot_combined', 'hero_stack', 'to_call', 'hero_name'
                )
                if allowed:
                    try:
                        x = float(roi_config.get('x', 0.0))
                        y = float(roi_config.get('y', 0.0))
                        w = float(roi_config.get('w', 0.0))
                        h = float(roi_config.get('h', 0.0))
                        
                        # Coordonnées absolues en pixels (base client)
                        x0 = int(x * frame_w)
                        y0 = int(y * frame_h)
                        x1 = int((x + w) * frame_w)
                        y1 = int((y + h) * frame_h)
                        
                        # Crop la ROI
                        roi = frame[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
                        if roi.size > 0 and (y1 > y0) and (x1 > x0):
                            text_zones[element_name] = roi
                            
                    except Exception as e:
                        print(f"⚠️ Erreur extraction zone texte {element_name}: {e}")
                        continue
        
        return text_zones

    def get_text_zone_rects(self, frame: np.ndarray) -> Dict[str, Tuple[int, int, int, int]]:
        """Retourne les rectangles (x0,y0,x1,y1) des zones textuelles en pixels pour overlay."""
        rects: Dict[str, Tuple[int, int, int, int]] = {}
        layout_config = self.layouts.get(self.current_layout, {})
        rois_config = layout_config.get('rois', {})
        frame_h, frame_w = frame.shape[:2]
        coords = (self.config or {}).get("coords", {}) or {}
        base = coords.get("base") if coords.get("base") in ("client", "table") else "client"
        if base != 'client':
            return rects
        for element_name, roi_config in rois_config.items():
            lname = element_name.lower()
            if lname in ('pot_combined', 'hero_stack', 'to_call', 'hero_name'):
                try:
                    x = float(roi_config.get('x', 0.0)); y = float(roi_config.get('y', 0.0))
                    w = float(roi_config.get('w', 0.0)); h = float(roi_config.get('h', 0.0))
                    x0 = int(x * frame_w); y0 = int(y * frame_h)
                    x1 = int((x + w) * frame_w); y1 = int((y + h) * frame_h)
                    if (x1 > x0) and (y1 > y0):
                        rects[element_name] = (x0, y0, x1, y1)
                except Exception:
                    continue
        return rects
    
    def _apply_character_corrections(self, text: str) -> str:
        """
        Applique les corrections d'erreurs courantes.
        
        Args:
            text: Texte à corriger
            
        Returns:
            Texte corrigé
        """
        corrected = text
        for wrong, correct in self.character_corrections.items():
            corrected = corrected.replace(wrong, correct)
        return corrected
    
    def _normalize_money_value(self, text: str) -> Tuple[Optional[float], str]:
        """
        Normalise une valeur monétaire.
        
        Args:
            text: Texte brut de l'OCR
            
        Returns:
            Tuple (valeur_normalisée, texte_original)
        """
        if not text:
            return None, text
        
        # Nettoie le texte (garde les chiffres, points, virgules, k, K, m, M)
        cleaned = re.sub(r'[^\d.,kKmM€]', '', text)
        cleaned = self._apply_character_corrections(cleaned)
        
        if not cleaned:
            return None, text
        
        # Corrections spécifiques pour les valeurs de pot typiques
        cleaned = self._fix_common_pot_errors(cleaned)
        
        # Essaie les patterns de normalisation dans l'ordre de priorité
        for i, (pattern, converter) in enumerate(self.money_patterns):
            match = re.search(pattern, cleaned)
            if match:
                try:
                    value = converter(match)
                    # Log silencieux - pas de spam dans la console
                    if not hasattr(self, '_last_money_values'):
                        self._last_money_values = {'texts': []}
                    return value, text
                except (ValueError, AttributeError):
                    continue
        return None, text
    
    def _fix_common_pot_errors(self, text: str) -> str:
        """
        Corrige les erreurs courantes de reconnaissance pour les pots.
        
        Args:
            text: Texte nettoyé
            
        Returns:
            Texte corrigé
        """
        # Patterns d'erreurs courantes pour les petits pots
        corrections = [
            # "70,081" -> "0,08" (7 mal lu comme 0, et caractères parasites)
            (r'^7(\d+),(\d+)$', r'0,\2'),
            # "70,08" -> "0,08"
            (r'^7(\d+),(\d+)$', r'0,\2'),
            # "0,081" -> "0,08" (caractères parasites à la fin)
            (r'^0,(\d{2})\d+$', r'0,\1'),
            # "0,08" -> "0,08" (déjà correct)
            (r'^0,(\d{2})$', r'0,\1'),
        ]
        
        for pattern, replacement in corrections:
            if re.match(pattern, text):
                corrected = re.sub(pattern, replacement, text)
                # Log silencieux - pas de spam dans la console
                return corrected
        
        return text
    
    def extract_pot_value(self, text: str) -> float:
        """
        Extrait le montant du pot quelle que soit la formulation du label.
        
        Gère toutes les formulations : 'pot 1.2', 'pot total: 1.2', 'total pot 1.2', etc.
        Insensible à la casse et aux variations de ponctuation.
        
        Exemples :
        - "Pot 0.15" → 0.15
        - "Pot total 1.25" → 1.25
        - "Side pot 0.75" → 0.75
        - "Pot: 2.50" → 2.50
        - "Total: 3.75" → 3.75
        - "POT TOTAL 1.2" → 1.2
        - "total pot: 2.5" → 2.5
        
        Args:
            text: Texte brut de l'OCR contenant le label et le montant
            
        Returns:
            Montant du pot en float, 0.0 si non trouvé
        """
        if not text:
            return 0.0
        
        # Nettoie le texte (garde les chiffres, points, virgules, k, K, m, M, €)
        cleaned = re.sub(r'[^\d.,kKmM€]', ' ', text)
        cleaned = self._apply_character_corrections(cleaned)
        
        if not cleaned:
            return 0.0
        
        # Applique les corrections d'erreurs courantes d'abord
        corrected_text = self._fix_common_pot_errors(cleaned)
        
        # Trouve tous les nombres dans le texte corrigé
        # Patterns par ordre de priorité (décimaux d'abord)
        decimal_pattern = r'(\d+[.,]\d+)'  # 0.15, 1,25
        integer_pattern = r'(\d+)'         # 15, 125
        
        # Cherche d'abord les nombres décimaux
        decimal_matches = re.findall(decimal_pattern, corrected_text)
        if decimal_matches:
            # Prend le dernier nombre décimal trouvé (le montant du pot)
            last_decimal = decimal_matches[-1]
            try:
                normalized = last_decimal.replace(',', '.')
                return float(normalized)
            except (ValueError, AttributeError):
                pass
        
        # Si pas de décimaux, cherche les entiers
        integer_matches = re.findall(integer_pattern, corrected_text)
        if integer_matches:
            # Prend le dernier entier trouvé (le montant du pot)
            last_integer = integer_matches[-1]
            try:
                return float(last_integer)
            except (ValueError, AttributeError):
                pass
        
        return 0.0
    
    def _normalize_name(self, text: str) -> Tuple[Optional[str], str]:
        """
        Normalise un nom de joueur.
        
        Args:
            text: Texte brut de l'OCR
            
        Returns:
            Tuple (nom_normalisé, texte_original)
        """
        if not text:
            return None, text
        
        # Nettoie le texte (lettres, chiffres, espaces et tirets uniquement)
        cleaned = re.sub(r'[^a-zA-Z0-9\s\-]', '', text).strip()
        
        if not cleaned:
            return None, text
        
        # Applique les corrections d'erreurs spécifiques aux noms
        corrected = self._apply_name_corrections(cleaned)
        
        # Filtre les noms trop courts ou suspects
        if len(corrected) < 2:
            return None, text
        
        # Filtre les noms qui sont principalement des chiffres
        if len(re.sub(r'[^0-9]', '', corrected)) > len(corrected) * 0.7:
            return None, text
        
        if corrected:
            # Log silencieux - pas de spam dans la console
            if not hasattr(self, '_last_name_values'):
                self._last_name_values = {'names': []}
            return corrected, text
        else:
            return None, text
    
    def _apply_name_corrections(self, text: str) -> str:
        """
        Applique les corrections d'erreurs spécifiques aux noms.
        
        Args:
            text: Texte à corriger
            
        Returns:
            Texte corrigé
        """
        corrected = text
        for wrong, correct in self.name_corrections.items():
            corrected = corrected.replace(wrong, correct)
        return corrected
    
    def _is_value_change_valid(self, element_name: str, new_value: float) -> bool:
        """
        Valide si un changement de valeur est acceptable.
        
        Args:
            element_name: Nom de l'élément
            new_value: Nouvelle valeur
            
        Returns:
            True si le changement est valide
        """
        # Première valeur pour cet élément ?
        if element_name not in self.ema_values:
            return True
        
        old_value = self.ema_values[element_name]

        # Si aucune valeur précédente (None) ou 0 → toujours OK
        if old_value is None or old_value == 0:
            return True

        # Changement relatif protégé (pas de division par 0)
        denom = max(1e-9, abs(old_value))
        relative_change = abs(new_value - old_value) / denom
        return relative_change <= self.max_value_change
    
    def _apply_ema_filter(self, element_name: str, new_value: float) -> float:
        """
        Applique le filtre EMA (Exponential Moving Average).
        
        Args:
            element_name: Nom de l'élément
            new_value: Nouvelle valeur
            
        Returns:
            Valeur filtrée
        """
        current_time = time.time()
        
        # Vérifie si la variation est trop importante
        if self.ema_values[element_name] is not None:
            if self.ema_values[element_name] > 0:
                relative_change = abs(new_value - self.ema_values[element_name]) / self.ema_values[element_name]
                if relative_change > self.variation_threshold:
                    # Variation trop importante, garde la valeur stable
                    return self.stable_values[element_name] or new_value
        
        # Applique l'EMA
        if self.ema_values[element_name] is None:
            self.ema_values[element_name] = new_value
        else:
            self.ema_values[element_name] = (
                self.ema_alpha * new_value + 
                (1 - self.ema_alpha) * self.ema_values[element_name]
            )
        
        # Met à jour la valeur stable si elle est cohérente
        self.stable_values[element_name] = self.ema_values[element_name]
        self.last_update_times[element_name] = current_time
        
        return self.ema_values[element_name]
    
    def recognize_text(self, frame: np.ndarray) -> Dict[str, TextResult]:
        """
        Reconnaissance textuelle complète sur un frame.
        
        Args:
            frame: Image de la table
            
        Returns:
            Dictionnaire des résultats par élément
        """
        start_time = time.time()
        results = {}
        
        # Extrait les zones de texte
        text_zones = self._extract_text_zones(frame)
        
        if not text_zones:
            self._update_performance_metrics(time.time() - start_time)
            return results
        
        # Charge l'OCR à la demande
        self._ensure_reader()

        # Traite chaque zone
        for element_name, zone in text_zones.items():
            try:
                # Preprocessing de la zone
                processed_zone = self._preprocess_image(zone)
                
                # Export debug si activé
                if self.debug_ocr:
                    self._export_debug_image(element_name, zone, processed_zone, "")
                
                # Teste d'abord l'image originale pour les petites zones
                if zone.shape[0] < 50:  # Zone très petite
                    # OCR sur l'image originale
                    ocr_results_orig = self.reader.readtext(
                        zone,
                        allowlist=self.whitelist,
                        width_ths=0.7,
                        height_ths=0.7
                    )
                    
                    # OCR sur l'image prétraitée
                    ocr_results_proc = self.reader.readtext(
                        processed_zone,
                        allowlist=self.whitelist,
                        width_ths=0.7,
                        height_ths=0.7
                    )
                    
                    # Choisit le meilleur résultat
                    if ocr_results_orig and ocr_results_proc:
                        # Prend celui avec la meilleure confiance
                        best_orig = max(ocr_results_orig, key=lambda x: x[2])
                        best_proc = max(ocr_results_proc, key=lambda x: x[2])
                        ocr_results = ocr_results_orig if best_orig[2] > best_proc[2] else ocr_results_proc
                    else:
                        ocr_results = ocr_results_orig or ocr_results_proc
                else:
                    # OCR normal sur l'image prétraitée
                    ocr_results = self.reader.readtext(
                        processed_zone,
                        allowlist=self.whitelist,
                        width_ths=0.7,
                        height_ths=0.7
                    )
                
                # Combine les résultats OCR
                combined_text = ""
                total_confidence = 0.0
                valid_detections = 0
                
                # Log détaillé des résultats OCR bruts
                print(f"🔍 OCR {element_name}: {len(ocr_results)} détections brutes")
                for i, (bbox, text, confidence) in enumerate(ocr_results):
                    print(f"  [{i}] '{text}' (conf: {confidence:.3f})")
                    if confidence > self.min_confidence:  # Seuil de confiance configurable
                        combined_text += text + " "
                        total_confidence += confidence
                        valid_detections += 1
                
                print(f"  → Texte combiné: '{combined_text.strip()}' ({valid_detections} valides)")
                
                if valid_detections == 0:
                    results[element_name] = TextResult(
                        text="",
                        confidence=0.0,
                        normalized_value=None,
                        is_valid=False,
                        raw_ocr_text=""
                    )
                    continue
                
                # Calcule la confiance moyenne
                avg_confidence = total_confidence / valid_detections
                combined_text = combined_text.strip()
                
                # Normalise selon le type d'élément
                if 'name' in element_name.lower():
                    normalized_value, original_text = self._normalize_name(combined_text)
                    print(f"  → Normalisation nom: '{combined_text}' → {normalized_value}")
                elif element_name.lower() == 'pot_combined':
                    # Utilise la nouvelle fonction d'extraction robuste pour le pot
                    normalized_value = self.extract_pot_value(combined_text)
                    original_text = combined_text
                    print(f"  → Extraction pot: '{combined_text}' → {normalized_value}")
                else:
                    normalized_value, original_text = self._normalize_money_value(combined_text)
                    print(f"  → Normalisation monétaire: '{combined_text}' → {normalized_value}")
                
                # Applique le filtre EMA pour les valeurs numériques
                if normalized_value is not None and isinstance(normalized_value, (int, float)):
                    # Validation du changement de valeur
                    is_change_valid = self._is_value_change_valid(element_name, normalized_value)
                    print(f"  → Changement valide: {is_change_valid} (max_change={self.max_value_change})")
                    
                    if is_change_valid:
                        filtered_value = self._apply_ema_filter(element_name, normalized_value)
                    else:
                        # Accepte quand même (le lissage fera le travail ensuite)
                        filtered_value = normalized_value
                        print(f"  → Valeur rejetée par EMA, mais on accepte quand même: {filtered_value}")
                    
                    # S'assure que filtered_value n'est jamais None
                    if filtered_value is None:
                        filtered_value = normalized_value
                        print(f"  → filtered_value était None, utilise normalized_value: {filtered_value}")
                else:
                    filtered_value = normalized_value
                
                # Valide la cohérence avec des seuils plus stricts
                is_valid = (
                    avg_confidence > self.min_confidence and
                    filtered_value is not None and
                    (not isinstance(filtered_value, (int, float)) or filtered_value >= 0) and
                    (not isinstance(filtered_value, (int, float)) or filtered_value < 1000000)  # Valeur max raisonnable
                )
                
                print(f"  → Validation: conf={avg_confidence:.3f} (min={self.min_confidence}), val={normalized_value}, valid={is_valid}")
                
                results[element_name] = TextResult(
                    text=combined_text,
                    confidence=avg_confidence,
                    normalized_value=filtered_value,
                    is_valid=is_valid,
                    raw_ocr_text=original_text
                )
                
                # Export debug avec le texte reconnu
                if self.debug_ocr:
                    self._export_debug_image(element_name, zone, processed_zone, combined_text)
                
            except Exception as e:
                # Log des erreurs pour debug - évite de perdre 30 minutes la prochaine fois
                print(f"⚠️ Erreur reconnaissance texte {element_name}: {e}")
                results[element_name] = TextResult(
                    text="",
                    confidence=0.0,
                    normalized_value=None,
                    is_valid=False,
                    raw_ocr_text=""
                )
        
        # Met à jour les métriques de performance
        self._update_performance_metrics(time.time() - start_time)
        
        return results
    
    def get_text_summary(self, results: Dict[str, TextResult]) -> str:
        """
        Retourne un résumé des résultats textuels.
        
        Args:
            results: Résultats de reconnaissance
            
        Returns:
            Résumé textuel
        """
        summary = "📝 Reconnaissance textuelle:\n"
        
        for element_name, result in results.items():
            if result.is_valid:
                if isinstance(result.normalized_value, (int, float)):
                    summary += f"  {element_name}: {result.normalized_value:,.0f} (conf: {result.confidence:.2f})\n"
                else:
                    summary += f"  {element_name}: {result.normalized_value} (conf: {result.confidence:.2f})\n"
            else:
                summary += f"  {element_name}: Non détecté\n"
        
        return summary.strip()
    
    def format_debug_display(self, results: Dict[str, TextResult]) -> str:
        """
        Génère un affichage debug formaté et propre pour l'interface.
        
        Args:
            results: Dictionnaire des résultats par élément
            
        Returns:
            Affichage formaté en français avec groupement logique
        """
        lines = []
        
        # Debug: affiche tous les résultats reçus
        print(f"🔍 format_debug_display reçoit {len(results)} résultats:")
        for name, result in results.items():
            print(f"  {name}: valid={result.is_valid}, value={result.normalized_value}, conf={result.confidence:.3f}")
        
        # Informations joueur
        player_info = []
        hero_name = results.get('hero_name')
        if hero_name and hero_name.is_valid and (hero_name.normalized_value is not None):
            player_info.append(hero_name.normalized_value)
        
        hero_stack = results.get('hero_stack')
        if hero_stack and hero_stack.is_valid and (hero_stack.normalized_value is not None):
            stack_value = float(hero_stack.normalized_value)
            stack_display = f"{stack_value:.2f} €" if stack_value < 1000 else f"{stack_value/1000:.1f}k €"
            player_info.append(stack_display)
        
        if player_info:
            lines.append(f"JOUEUR: {' '.join(player_info)}")
        
        # Pot
        pot = results.get('pot_combined')
        if pot and pot.is_valid and (pot.normalized_value is not None):
            pot_value = float(pot.normalized_value)
            pot_display = f"{pot_value:.2f} €" if pot_value < 1000 else f"{pot_value/1000:.1f}k €"
            lines.append(f"POT: {pot_display}")
        
        # Actions
        actions = []
        to_call = results.get('to_call')
        if to_call and to_call.is_valid and (to_call.normalized_value is not None):
            call_value = float(to_call.normalized_value)
            call_display = f"Call {call_value:.2f} €" if call_value < 1000 else f"Call {call_value/1000:.1f}k €"
            actions.append(call_display)
        
        if actions:
            lines.append(f"ACTIONS: {', '.join(actions)}")
        
        # Si aucune donnée valide
        if not lines:
            lines.append("Aucune donnée détectée")
        
        return "\n".join(lines)
    
    def enable_debug_export(self, enabled: bool = True, export_dir: str = "debug_ocr", interval: float = 1.0):
        """
        Active ou désactive l'export PNG des zones OCR pour debug.
        
        Args:
            enabled: Active l'export debug
            export_dir: Dossier d'export des images
            interval: Intervalle entre exports (secondes)
        """
        self.debug_ocr = enabled
        self.debug_export_dir = Path(export_dir)
        self.debug_export_interval = interval
        
        if enabled:
            # Crée la structure de dossiers
            self._create_debug_directories()
            print(f"🔍 Debug OCR activé - Export vers: {self.debug_export_dir}")
        else:
            print("🔍 Debug OCR désactivé")
    
    def _create_debug_directories(self):
        """Crée la structure de dossiers pour l'export debug."""
        zones = ['hero_name', 'hero_stack', 'pot_combined', 'to_call']
        
        for zone in zones:
            zone_dir = self.debug_export_dir / zone
            zone_dir.mkdir(parents=True, exist_ok=True)
    
    def _should_export_debug(self, zone_name: str) -> bool:
        """
        Détermine si une zone doit être exportée pour debug.
        
        Args:
            zone_name: Nom de la zone
            
        Returns:
            True si l'export doit être fait
        """
        if not self.debug_ocr:
            return False
        
        current_time = time.time()
        last_export = self.last_debug_export.get(zone_name, 0)
        
        return (current_time - last_export) >= self.debug_export_interval
    
    def _export_debug_image(self, zone_name: str, original_image: np.ndarray, processed_image: np.ndarray, ocr_text: str = ""):
        """
        Exporte une image de zone OCR pour debug.
        
        Args:
            zone_name: Nom de la zone
            original_image: Image originale de la zone
            processed_image: Image prétraitée
            ocr_text: Texte reconnu par l'OCR
        """
        if not self._should_export_debug(zone_name):
            return
        
        try:
            # Timestamp pour le nom de fichier
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Millisecondes
            
            # Export de l'image originale
            if original_image is not None and original_image.size > 0:
                original_path = self.debug_export_dir / zone_name / f"{timestamp}_{zone_name}_original.png"
                cv2.imwrite(str(original_path), original_image)
            
            # Export de l'image prétraitée
            if processed_image is not None and processed_image.size > 0:
                processed_path = self.debug_export_dir / zone_name / f"{timestamp}_{zone_name}_processed.png"
                cv2.imwrite(str(processed_path), processed_image)
            
            # Export d'une image combinée (original + processed)
            if (original_image is not None and original_image.size > 0 and 
                processed_image is not None and processed_image.size > 0):
                self._export_combined_debug_image(zone_name, timestamp, original_image, processed_image, ocr_text)
            
            # Met à jour le timestamp
            self.last_debug_export[zone_name] = time.time()
            
        except Exception as e:
            print(f"⚠️ Erreur export debug {zone_name}: {e}")
    
    def _export_combined_debug_image(self, zone_name: str, timestamp: str, original: np.ndarray, processed: np.ndarray, ocr_text: str):
        """
        Exporte une image combinée (original + processed) pour debug.
        
        Args:
            zone_name: Nom de la zone
            timestamp: Timestamp du fichier
            original: Image originale
            processed: Image prétraitée
            ocr_text: Texte reconnu
        """
        try:
            # Redimensionne les images pour qu'elles aient la même hauteur
            h1, w1 = original.shape[:2]
            h2, w2 = processed.shape[:2]
            
            # Hauteur commune (la plus grande)
            target_height = max(h1, h2)
            
            # Redimensionne l'original
            if h1 != target_height:
                scale1 = target_height / h1
                new_w1 = int(w1 * scale1)
                original_resized = cv2.resize(original, (new_w1, target_height))
            else:
                original_resized = original.copy()
            
            # Redimensionne le processed (assure-toi qu'il est en 3D si l'original l'est)
            if h2 != target_height:
                scale2 = target_height / h2
                new_w2 = int(w2 * scale2)
                processed_resized = cv2.resize(processed, (new_w2, target_height))
            else:
                processed_resized = processed.copy()
            
            # Assure-toi que les deux images ont le même nombre de dimensions
            if len(original_resized.shape) != len(processed_resized.shape):
                if len(original_resized.shape) == 3 and len(processed_resized.shape) == 2:
                    # Convertit processed en 3D
                    processed_resized = cv2.cvtColor(processed_resized, cv2.COLOR_GRAY2BGR)
                elif len(original_resized.shape) == 2 and len(processed_resized.shape) == 3:
                    # Convertit original en 3D
                    original_resized = cv2.cvtColor(original_resized, cv2.COLOR_GRAY2BGR)
            
            # Combine horizontalement
            combined = np.hstack([original_resized, processed_resized])
            
            # Ajoute le texte reconnu en overlay
            if ocr_text:
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.6
                color = (0, 255, 0) if ocr_text.strip() else (0, 0, 255)
                thickness = 1
                
                # Position du texte (en bas de l'image)
                text_y = target_height - 10
                cv2.putText(combined, f"OCR: {ocr_text}", (10, text_y), font, font_scale, color, thickness)
            
            # Export
            combined_path = self.debug_export_dir / zone_name / f"{timestamp}_{zone_name}_combined.png"
            cv2.imwrite(str(combined_path), combined)
            
        except Exception as e:
            print(f"⚠️ Erreur export combiné {zone_name}: {e}")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Retourne les métriques de performance.
        
        Returns:
            Dictionnaire des métriques de performance
        """
        return self.performance_metrics.copy()
    
    def _update_performance_metrics(self, call_time: float):
        """
        Met à jour les métriques de performance.
        
        Args:
            call_time: Temps d'exécution de l'appel
        """
        self.performance_metrics['total_calls'] += 1
        self.performance_metrics['total_time'] += call_time
        self.performance_metrics['avg_time'] = self.performance_metrics['total_time'] / self.performance_metrics['total_calls']
        self.performance_metrics['last_call_time'] = call_time
    
    def reset_performance_metrics(self):
        """Remet à zéro les métriques de performance."""
        self.performance_metrics = {
            'total_calls': 0,
            'total_time': 0.0,
            'avg_time': 0.0,
            'last_call_time': 0.0
        }
