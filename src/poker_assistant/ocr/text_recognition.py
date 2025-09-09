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
        self.whitelist = "0123456789kKM€.,"
        self.reader = None  # initialisé à la demande
        
        # Configuration du preprocessing
        self.adaptive_thresh_block_size = 11
        self.adaptive_thresh_c = 2
        self.clahe_clip_limit = 2.0
        self.clahe_tile_grid_size = (8, 8)
        
        # Configuration du filtrage EMA
        self.ema_alpha = 0.3  # Facteur de lissage (0.1 = très lisse, 0.9 = très réactif)
        self.variation_threshold = 0.5  # Seuil de variation relative pour ignorer les sauts
        
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
            'pot_value': None,
            'hero_stack': None,
            'to_call': None,
            'hero_name': None
        }
        
        # Buffers pour la persistance des valeurs stables
        self.stable_values = {
            'pot_value': None,
            'hero_stack': None,
            'to_call': None,
            'hero_name': None
        }
        
        self.last_update_times = {
            'pot_value': 0,
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
            # Format: 10500, 2300000, etc.
            (r'(\d+(?:[.,]\d+)?)', lambda m: float(m.group(1).replace(',', '.'))),
        ]
        
        # Patterns pour les noms (lettres uniquement)
        self.name_patterns = [
            (r'[a-zA-Z\s]+', lambda m: m.group(0).strip()),
        ]
        
        # Corrections d'erreurs courantes
        self.character_corrections = {
            'O': '0', 'o': '0',  # O -> 0
            'I': '1', 'l': '1',  # I/l -> 1
            'S': '5', 's': '5',  # S -> 5
            'B': '8', 'b': '8',  # B -> 8
            'G': '6', 'g': '6',  # G -> 6
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
        
        # Amélioration du contraste avec CLAHE
        clahe = cv2.createCLAHE(
            clipLimit=self.clahe_clip_limit,
            tileGridSize=self.clahe_tile_grid_size
        )
        enhanced = clahe.apply(gray)
        
        # Seuillage adaptatif
        thresh = cv2.adaptiveThreshold(
            enhanced,
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
                # On ne lit que les éléments textuels connus
                if any(keyword in element_name.lower() for keyword in ['pot', 'hero', 'stack', 'call', 'name']):
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
        
        # Nettoie le texte
        cleaned = re.sub(r'[^\d.,kKmM€]', '', text)
        cleaned = self._apply_character_corrections(cleaned)
        
        if not cleaned:
            return None, text
        
        # Essaie les patterns de normalisation
        for pattern, converter in self.money_patterns:
            match = re.search(pattern, cleaned)
            if match:
                try:
                    value = converter(match)
                    return value, text
                except (ValueError, AttributeError):
                    continue
        
        return None, text
    
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
        
        # Nettoie le texte (lettres et espaces uniquement)
        cleaned = re.sub(r'[^a-zA-Z\s]', '', text).strip()
        
        if not cleaned:
            return None, text
        
        # Applique les corrections d'erreurs
        corrected = self._apply_character_corrections(cleaned)
        
        return corrected if corrected else None, text
    
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
        results = {}
        
        # Extrait les zones de texte
        text_zones = self._extract_text_zones(frame)
        
        # Charge l'OCR à la demande
        self._ensure_reader()

        # Traite chaque zone
        for element_name, zone in text_zones.items():
            try:
                # Preprocessing de la zone
                processed_zone = self._preprocess_image(zone)
                
                # OCR avec EasyOCR
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
                
                for (bbox, text, confidence) in ocr_results:
                    if confidence > 0.5:  # Seuil de confiance minimum
                        combined_text += text + " "
                        total_confidence += confidence
                        valid_detections += 1
                
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
                else:
                    normalized_value, original_text = self._normalize_money_value(combined_text)
                
                # Applique le filtre EMA pour les valeurs numériques
                if normalized_value is not None and isinstance(normalized_value, (int, float)):
                    filtered_value = self._apply_ema_filter(element_name, normalized_value)
                else:
                    filtered_value = normalized_value
                
                # Valide la cohérence
                is_valid = (
                    avg_confidence > 0.6 and
                    normalized_value is not None and
                    (not isinstance(normalized_value, (int, float)) or normalized_value >= 0)
                )
                
                results[element_name] = TextResult(
                    text=combined_text,
                    confidence=avg_confidence,
                    normalized_value=filtered_value,
                    is_valid=is_valid,
                    raw_ocr_text=original_text
                )
                
            except Exception as e:
                print(f"⚠️ Erreur reconnaissance texte {element_name}: {e}")
                results[element_name] = TextResult(
                    text="",
                    confidence=0.0,
                    normalized_value=None,
                    is_valid=False,
                    raw_ocr_text=""
                )
        
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
