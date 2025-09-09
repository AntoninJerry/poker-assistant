#!/usr/bin/env python3
"""
Module de reconnaissance de cartes par template matching multi-variants.
"""

import os
import cv2
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from pathlib import Path
import yaml
from enum import Enum
import time
from collections import deque
from .text_recognition import TextRecognitionPipeline

class GameState(Enum):
    """États du jeu pour la machine à états."""
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"

@dataclass
class CardResult:
    """Résultat de reconnaissance d'une carte."""
    rank: Optional[str] = None
    suit: Optional[str] = None
    rank_confidence: float = 0.0
    suit_confidence: float = 0.0
    combined_confidence: float = 0.0
    is_uncertain: bool = True
    rank_scores: Dict[str, float] = None
    suit_scores: Dict[str, float] = None
    
    def __post_init__(self):
        if self.rank_scores is None:
            self.rank_scores = {}
        if self.suit_scores is None:
            self.suit_scores = {}

@dataclass
class RecognitionFrame:
    """Frame de reconnaissance avec timestamp."""
    timestamp: float
    hero_cards: List[CardResult]
    board_cards: List[CardResult]
    game_state: GameState
    text_results: Dict[str, Any] = None  # Résultats de reconnaissance textuelle

class CardRecognitionPipeline:
    """Pipeline complet de reconnaissance de cartes."""
    
    def __init__(self, yaml_path: str, templates_dir: str = "assets/templates"):
        """
        Initialise le pipeline de reconnaissance.
        
        Args:
            yaml_path: Chemin vers le fichier YAML de configuration
            templates_dir: Dossier contenant les templates
        """
        self.yaml_path = yaml_path
        self.templates_dir = Path(templates_dir)
        
        # Configuration
        self.target_size = (56, 56)  # Taille cible pour le prétraitement
        self.confidence_alpha = 2.0   # Paramètre sigmoid (augmenté pour plus de précision)
        self.confidence_beta = 1.5    # Paramètre margin (augmenté)
        self.confidence_threshold = 0.3  # Seuil un peu plus haut pour limiter les faux positifs
        self.temporal_buffer_size = 3     # Taille du buffer temporel (réduit pour plus de réactivité)
        # Gardes anti-faux positifs
        self.min_top1_score = 0.35       # score brut minimal du top1 pour considérer un label
        self.min_top1_margin = 0.07      # marge (top1-top2) minimale
        self.min_roi_activity = 2.0      # écart-type minimal dans la zone (texture) - plus tolérant
        
        # Debug dump pour inspection visuelle des crops
        self.debug_dump = False
        # Verbose logging (désactivé par défaut)
        self.verbose = False
        
        # Chargement de la configuration
        self._load_config()
        
        # Chargement des templates
        self._load_templates()
        
        # Buffers temporels
        self._init_temporal_buffers()
        
        # Mapping pour le formatage des cartes
        self._init_card_formatting()
        
        # État du jeu
        self.game_state = GameState.PREFLOP
        self.last_state_change = time.time()
        
        # Détection des changements
        self.last_cards_hash = None
        self.change_detection_threshold = 0.8  # Seuil pour détecter un changement
        
        # Pipeline de reconnaissance textuelle
        self.text_pipeline = TextRecognitionPipeline(yaml_path)
        
    def _load_config(self):
        """Charge la configuration depuis le YAML."""
        try:
            with open(self.yaml_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            # Récupère les layouts
            self.layouts = self.config.get('layouts', {})
            self.current_layout = 'default'
            
            # Récupère les zones de cartes
            self.card_zones = self.config.get('card_zones', {})
            
            if self.verbose:
                print(f"✅ Configuration chargée: {len(self.layouts)} layouts, {len(self.card_zones)} zones de cartes")
            
        except Exception as e:
            raise RuntimeError(f"Erreur chargement config: {e}")
    
    def _load_templates(self):
        """Charge les templates de rangs et couleurs."""
        self.rank_templates = {}
        self.suit_templates = {}
        
        # Détermine la room et le layout
        room_name = "winamax"  # Pour l'instant, on ne supporte que Winamax
        layout_name = self.current_layout
        
        templates_path = self.templates_dir / room_name / layout_name
        
        # Charge les templates de rangs
        ranks_path = templates_path / "ranks"
        if ranks_path.exists():
            for template_file in ranks_path.glob("*.png"):
                template_name = template_file.stem  # Nom sans extension
                template_img = cv2.imread(str(template_file), cv2.IMREAD_GRAYSCALE)
                if template_img is not None:
                    # Redimensionne et prétraite le template
                    template_processed = self._preprocess_image(template_img)
                    self.rank_templates[template_name] = template_processed
                    if self.verbose:
                        print(f"📁 Template rang chargé: {template_name}")
        
        # Charge les templates de couleurs
        suits_path = templates_path / "suits"
        if suits_path.exists():
            for template_file in suits_path.glob("*.png"):
                template_name = template_file.stem  # Nom sans extension
                template_img = cv2.imread(str(template_file), cv2.IMREAD_GRAYSCALE)
                if template_img is not None:
                    # Redimensionne et prétraite le template
                    template_processed = self._preprocess_image(template_img)
                    self.suit_templates[template_name] = template_processed
                    if self.verbose:
                        print(f"📁 Template couleur chargé: {template_name}")
        
        if self.verbose:
            print(f"✅ Templates chargés: {len(self.rank_templates)} rangs, {len(self.suit_templates)} couleurs")
    
    def _preprocess_image(self, img: np.ndarray) -> np.ndarray:
        """
        Prétraitement identique pour templates et ROIs.
        
        Args:
            img: Image en niveaux de gris
            
        Returns:
            Image prétraitée
        """
        # Redimensionne à la taille cible
        img_resized = cv2.resize(img, self.target_size)
        
        # Flou gaussien pour réduire le bruit
        img_blurred = cv2.GaussianBlur(img_resized, (3, 3), 0)
        
        # Retourne l'image floutée (plus robuste que Canny pour les cartes)
        return img_blurred
    
    def _init_temporal_buffers(self):
        """Initialise les buffers temporels."""
        # Buffers pour les cartes hero (2 cartes)
        self.hero_buffers = [deque(maxlen=self.temporal_buffer_size) for _ in range(2)]
        
        # Buffers pour les cartes du board (5 slots)
        self.board_buffers = [deque(maxlen=self.temporal_buffer_size) for _ in range(5)]
        
        if self.verbose:
            print(f"✅ Buffers temporels initialisés: {self.temporal_buffer_size} frames")
    
    def _init_card_formatting(self):
        """Initialise les mappings pour le formatage des cartes."""
        # Mapping des rangs vers format poker standard
        self.rank_mapping = {
            'A': 'A', 'K': 'K', 'Q': 'Q', 'J': 'J', 'T': 'T',
            '9': '9', '8': '8', '7': '7', '6': '6', '5': '5', '4': '4', '3': '3', '2': '2'
        }
        
        # Mapping des couleurs vers format poker standard
        self.suit_mapping = {
            'h': 'h',  # hearts (cœurs)
            'd': 'd',  # diamonds (carreaux)
            'c': 'c',  # clubs (trèfles)
            's': 's'   # spades (piques)
        }
    
    def _format_card_label(self, template_name: str) -> str:
        """
        Convertit un nom de template vers le format poker standard.
        
        Args:
            template_name: Nom du template (ex: "A_1", "h_2")
            
        Returns:
            Label formaté (ex: "A", "h")
        """
        if not template_name:
            return ""
        
        # Extrait la partie principale (avant le _)
        main_part = template_name.split('_')[0]
        
        # Retourne le mapping ou la valeur originale si pas de mapping
        return self.rank_mapping.get(main_part, self.suit_mapping.get(main_part, main_part))
    
    def _detect_cards_change(self, hero_cards: List[CardResult], board_cards: List[CardResult]) -> bool:
        """
        Détecte si les cartes ont changé depuis la dernière reconnaissance.
        
        Args:
            hero_cards: Cartes hero actuelles
            board_cards: Cartes du board actuelles
            
        Returns:
            True si les cartes ont changé
        """
        # Crée un hash des cartes actuelles
        current_cards = []
        
        # Ajoute les cartes hero
        for card in hero_cards:
            if card.rank and card.suit:
                current_cards.append(f"{card.rank}{card.suit}")
            else:
                current_cards.append("??")
        
        # Ajoute les cartes du board
        for card in board_cards:
            if card.rank and card.suit:
                current_cards.append(f"{card.rank}{card.suit}")
            else:
                current_cards.append("??")
        
        current_hash = hash(tuple(current_cards))
        
        # Compare avec le hash précédent
        if self.last_cards_hash is None:
            self.last_cards_hash = current_hash
            return True  # Premier appel, considère comme un changement
        
        changed = self.last_cards_hash != current_hash
        if changed:
            self.last_cards_hash = current_hash
            if self.verbose:
                print(f"🔄 Changement de cartes détecté: {' '.join(current_cards[:2])} | {' '.join(current_cards[2:])}")
        
        return changed
    
    def _extract_card_rois(self, frame: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Extrait les ROIs des cartes depuis le frame.
        
        Args:
            frame: Image de la table
            
        Returns:
            Dictionnaire des ROIs par nom de carte
        """
        card_rois = {}

        # Récupère le layout actuel
        layout_config = self.layouts.get(self.current_layout, {})
        rois_config = layout_config.get('rois', {})

        frame_h, frame_w = frame.shape[:2]

        # Utilise la même base que l'overlay visuel (client)
        coords = (self.config or {}).get("coords", {}) or {}
        base = coords.get("base") if coords.get("base") in ("client", "table") else "client"
        
        if base == "client":
            # Base client : coordonnées directes
            for card_name, roi_config in rois_config.items():
                if 'card' in card_name.lower():  # Filtre les cartes
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
                            card_rois[card_name] = roi

                    except Exception as e:
                        print(f"⚠️ Erreur extraction ROI {card_name}: {e}")
                        continue
        else:
            # Base table_zone : coordonnées relatives à l'ancre
            anchors = (getattr(self, 'config', {}) or {}).get('anchors', {})
            tz = anchors.get('table_zone', {}) or {}
            ax = float(tz.get('x', 0.0))
            ay = float(tz.get('y', 0.0))
            aw = float(tz.get('w', 1.0))
            ah = float(tz.get('h', 1.0))

            for card_name, roi_config in rois_config.items():
                if 'card' in card_name.lower():  # Filtre les cartes
                    try:
                        x = float(roi_config.get('x', 0.0))
                        y = float(roi_config.get('y', 0.0))
                        w = float(roi_config.get('w', 0.0))
                        h = float(roi_config.get('h', 0.0))

                        # Coordonnées absolues en pixels, relatives à table_zone
                        x0 = int((ax + x * aw) * frame_w)
                        y0 = int((ay + y * ah) * frame_h)
                        x1 = int((ax + (x + w) * aw) * frame_w)
                        y1 = int((ay + (y + h) * ah) * frame_h)

                        # Crop la ROI
                        roi = frame[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
                        if roi.size > 0 and (y1 > y0) and (x1 > x0):
                            card_rois[card_name] = roi

                    except Exception as e:
                        print(f"⚠️ Erreur extraction ROI {card_name}: {e}")
                        continue

        return card_rois
    
    def _extract_rank_suit_zones(self, card_roi: np.ndarray, card_name: str) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Extraction robuste des sous-zones rang/suit.

        - Accepte des sous-zones en normalisé (0..1) ou en pixels (units: px ou valeur>1)
        - Fallback sur une section "default" si la carte n'a pas sa clé dédiée
        - Infère le type (rank/suit) depuis le nom de clé si manquant
        - Ajoute un secours par Canny si la variance est trop faible
        """
        zones = (self.card_zones or {}).get(card_name)
        if zones is None:
            zones = (self.card_zones or {}).get("default")

        if zones is None:
            print(f"⚠️ card_zones manquant pour {card_name} (clé YAML)")
            return None, None

        h, w = card_roi.shape[:2]
        rank_zone: Optional[np.ndarray] = None
        suit_zone: Optional[np.ndarray] = None

        def _xyxy(z: Dict[str, Any]) -> Tuple[int, int, int, int]:
            zx = float(z.get("x", 0.0)); zy = float(z.get("y", 0.0))
            zw = float(z.get("w", 0.0)); zh = float(z.get("h", 0.0))
            units = str(z.get("units", "")).lower()
            use_px = (units == "px") or (max(zx, zy, zw, zh) > 1.0)
            
            # Marge de sécurité anti-troncature (1% vers l'intérieur)
            shrink = 0.01
            zx = max(0.0, zx + shrink)
            zy = max(0.0, zy + shrink)
            zw = max(0.0, zw - 2*shrink)
            zh = max(0.0, zh - 2*shrink)
            
            if use_px:
                x0, y0 = int(round(zx)), int(round(zy))
                x1, y1 = int(round(zx + zw)), int(round(zy + zh))
            else:
                x0 = int(round(zx * w)); y0 = int(round(zy * h))
                x1 = int(round((zx + zw) * w)); y1 = int(round((zy + zh) * h))
            
            # Étend d'1px sur les bords droit/bas si possible (anti-coupe)
            x1 = min(x1 + 1, w)
            y1 = min(y1 + 1, h)
            
            x0 = max(0, min(x0, w - 1)); x1 = max(0, min(x1, w))
            y0 = max(0, min(y0, h - 1)); y1 = max(0, min(y1, h))
            return x0, y0, x1, y1

        def _as_gray(sub: Optional[np.ndarray]) -> Optional[np.ndarray]:
            if sub is None or sub.size == 0:
                return None
            return cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY) if sub.ndim == 3 else sub

        for key, z in zones.items():
            t = z.get("type")
            if not t:
                k = str(key).lower()
                if ("rank" in k) or ("val" in k) or ("num" in k):
                    t = "rank"
                elif ("suit" in k) or ("color" in k) or ("couleur" in k):
                    t = "suit"
            x0, y0, x1, y1 = _xyxy(z)
            sub = card_roi[y0:y1, x0:x1]
            if t == "rank":
                rank_zone = _as_gray(sub)
            elif t == "suit":
                suit_zone = _as_gray(sub)

        def _std(img: Optional[np.ndarray]) -> float:
            return float(np.std(img)) if img is not None and img.size else 0.0

        r_std = _std(rank_zone); s_std = _std(suit_zone)
        # Log silencieux - pas de spam dans la console
        # if rank_zone is None or r_std < 1.2:
        #     print(f"⚠️ rank_zone vide/faible pour {card_name} (std={r_std:.2f})")
        # if suit_zone is None or s_std < 1.2:
        #     print(f"⚠️ suit_zone vide/faible pour {card_name} (std={s_std:.2f})")

        def _edgeize(img: Optional[np.ndarray]) -> Optional[np.ndarray]:
            if img is None or img.size == 0:
                return None
            return cv2.Canny(img, 50, 120)

        if r_std < 1.2 and rank_zone is not None:
            rank_zone = _edgeize(rank_zone)
        if s_std < 1.2 and suit_zone is not None:
            suit_zone = _edgeize(suit_zone)

        return rank_zone, suit_zone
    
    def _dump_zone(self, card_name: str, rank_zone: Optional[np.ndarray], suit_zone: Optional[np.ndarray]) -> None:
        """
        Dump visuel des crops pour inspection (debug).
        
        Args:
            card_name: Nom de la carte (ex: "hero_left", "board_card_1")
            rank_zone: Zone du rang (peut être None)
            suit_zone: Zone de la couleur (peut être None)
        """
        if not getattr(self, "debug_dump", False):
            return
        
        try:
            ts = int(time.time() * 1000)
            base = Path("assets/exports/debug_zones")
            base.mkdir(parents=True, exist_ok=True)
            
            if rank_zone is not None and rank_zone.size > 0:
                cv2.imwrite(str(base / f"{ts}_{card_name}_rank.png"), rank_zone)
            
            if suit_zone is not None and suit_zone.size > 0:
                cv2.imwrite(str(base / f"{ts}_{card_name}_suit.png"), suit_zone)
                
        except Exception as e:
            print(f"⚠️ Erreur dump zone {card_name}: {e}")
    
    def _template_matching_multi_variants(self, roi: np.ndarray, templates: Dict[str, np.ndarray]) -> Dict[str, float]:
        """
        Template matching multi-variants pour un ROI.
        
        Args:
            roi: ROI à analyser
            templates: Dictionnaire des templates (label -> template_array)
            
        Returns:
            Dictionnaire des scores par label
        """
        scores = {}
        
        # Prétraite le ROI
        roi_processed = self._preprocess_image(roi)
        
        # Pour chaque label, teste le template
        for label, template in templates.items():
            try:
                # Template matching
                result = cv2.matchTemplate(roi_processed, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                
                scores[label] = max_val
                
            except Exception as e:
                print(f"⚠️ Erreur template matching {label}: {e}")
                scores[label] = 0.0
        
        return scores

    def _is_blank_zone(self, gray_roi: np.ndarray) -> bool:
        """Retourne True si la zone est quasi vide/plate (peu de texture)."""
        try:
            if gray_roi is None or gray_roi.size == 0:
                return True
            if len(gray_roi.shape) == 3:
                gray = cv2.cvtColor(gray_roi, cv2.COLOR_BGR2GRAY)
            else:
                gray = gray_roi
            # écart-type comme proxy d'activité
            std = float(np.std(gray))
            return std < self.min_roi_activity
        except Exception:
            return False

    def _aggregate_family_scores(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Regroupe par famille (ex: A_1/A_2 -> A : max(score))."""
        fam: Dict[str, float] = {}
        for label, s in scores.items():
            main = label.split("_")[0]
            fam[main] = max(fam.get(main, 0.0), float(s))
        return fam

    def _choose_family_with_margin(self, fam_scores: Dict[str, float]) -> Tuple[Optional[str], float, float]:
        """Retourne (label_famille, top1, marge) à partir de scores agrégés."""
        if not fam_scores:
            return None, 0.0, 0.0
        ordered = sorted(fam_scores.items(), key=lambda kv: kv[1], reverse=True)
        if len(ordered) == 1:
            return ordered[0][0], ordered[0][1], ordered[0][1]
        (l1, s1), (_, s2) = ordered[0], ordered[1]
        return l1, float(s1), float(max(0.0, s1 - s2))
    
    def _calculate_confidence(self, scores: Dict[str, float]) -> Tuple[str, float]:
        """
        Calcule la confiance avec sigmoid et margin.
        
        Args:
            scores: Dictionnaire des scores par label
            
        Returns:
            Tuple (label_top1, confiance)
        """
        if not scores:
            return None, 0.0
        
        # Trie les scores par ordre décroissant
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        if len(sorted_scores) < 2:
            return sorted_scores[0][0], sorted_scores[0][1]
        
        # Top-1 et Top-2
        top1_label, top1_score = sorted_scores[0]
        top2_label, top2_score = sorted_scores[1]
        
        # Calcul de la marge
        margin = top1_score - top2_score
        
        # Calcul de la confiance avec sigmoid
        confidence = 1.0 / (1.0 + np.exp(-(self.confidence_alpha * top1_score + self.confidence_beta * margin)))
        
        return top1_label, confidence
    
    def _temporal_filtering(self, card_results: List[CardResult], buffer_index: int) -> CardResult:
        """
        Filtrage temporel avec vote majoritaire pondéré.
        
        Args:
            card_results: Résultats de reconnaissance
            buffer_index: Index du buffer (0-1 pour hero, 0-4 pour board)
            
        Returns:
            Résultat filtré
        """
        # Détermine le buffer à utiliser (0..1 héros, 2..6 board → 0..4)
        if buffer_index < 2:
            buffer = self.hero_buffers[buffer_index]
            source_index = buffer_index
            buf_idx = buffer_index  # Pour le debug
        else:
            buf_idx = buffer_index - 2
            buf_idx = max(0, min(buf_idx, len(self.board_buffers) - 1))
            buffer = self.board_buffers[buf_idx]
            # Pour la liste card_results (board), l'index local est 0..4
            source_index = buf_idx
        
        # Debug: affiche les indices et buffers
        if self.verbose:
            print(f"🔍 Temporal filtering: buffer_index={buffer_index}, buf_idx={buf_idx}, source_index={source_index}, buffer_size={len(buffer)}")
        
        # Ajoute le nouveau résultat au buffer (protégé)
        if 0 <= source_index < len(card_results):
            buffer.append(card_results[source_index])
        else:
            # En cas d'anomalie, ne pas planter; garder le dernier connu
            if buffer:
                candidate = buffer[-1]
            else:
                candidate = CardResult()
            buffer.append(candidate)
        
        # Vote majoritaire pondéré par la confiance
        rank_votes = {}
        suit_votes = {}
        total_confidence = 0.0
        
        for result in buffer:
            if result.rank and result.rank_confidence > 0:
                if result.rank not in rank_votes:
                    rank_votes[result.rank] = 0
                rank_votes[result.rank] += result.rank_confidence
                total_confidence += result.rank_confidence
            
            if result.suit and result.suit_confidence > 0:
                if result.suit not in suit_votes:
                    suit_votes[result.suit] = 0
                suit_votes[result.suit] += result.suit_confidence
                total_confidence += result.suit_confidence
        
        # Sélectionne le gagnant
        best_rank = max(rank_votes.items(), key=lambda x: x[1])[0] if rank_votes else None
        best_suit = max(suit_votes.items(), key=lambda x: x[1])[0] if suit_votes else None
        
        # Calcule la confiance moyenne
        avg_confidence = total_confidence / len(buffer) if buffer else 0.0
        
        # Crée le résultat filtré
        filtered_result = CardResult(
            rank=best_rank,
            suit=best_suit,
            rank_confidence=avg_confidence,
            suit_confidence=avg_confidence,
            combined_confidence=avg_confidence,
            is_uncertain=avg_confidence < self.confidence_threshold
        )
        
        return filtered_result
    
    def _update_game_state(self, board_cards: List[CardResult]):
        """
        Met à jour l'état du jeu selon les cartes du board.
        
        Args:
            board_cards: Cartes du board
        """
        # Compte les cartes visibles
        visible_cards = sum(1 for card in board_cards if card.rank and card.suit)
        
        # Détermine le nouvel état
        new_state = self.game_state
        if visible_cards == 0:
            new_state = GameState.PREFLOP
        elif visible_cards == 3:
            new_state = GameState.FLOP
        elif visible_cards == 4:
            new_state = GameState.TURN
        elif visible_cards == 5:
            new_state = GameState.RIVER
        
        # Met à jour l'état si nécessaire
        if new_state != self.game_state:
            self.game_state = new_state
            self.last_state_change = time.time()
            print(f"🎯 État du jeu: {self.game_state.value}")
    
    def recognize_cards(self, frame: np.ndarray) -> RecognitionFrame:
        """
        Reconnaissance complète des cartes sur un frame.
        
        Args:
            frame: Image de la table
            
        Returns:
            Frame de reconnaissance
        """
        timestamp = time.time()
        
        # Extrait les ROIs des cartes
        card_rois = self._extract_card_rois(frame)
        
        # Initialise les résultats
        hero_cards = [CardResult() for _ in range(2)]
        board_cards = [CardResult() for _ in range(5)]
        
        # Traite chaque carte
        for card_name, card_roi in card_rois.items():
            if self.verbose:
                print(f"🔍 Traitement carte: {card_name}")
                print(f"🔍 Type de carte: {'hero' if 'hero' in card_name.lower() else 'board' if 'board' in card_name.lower() else 'unknown'}")
            
            # Extrait les zones rank et suit
            rank_zone, suit_zone = self._extract_rank_suit_zones(card_roi, card_name)
            
            # Dump visuel pour inspection (debug)
            self._dump_zone(card_name, rank_zone, suit_zone)
            
            if rank_zone is None or suit_zone is None:
                if self.verbose:
                    print(f"❌ {card_name}: zones rank/suit manquantes")
                continue
            
            # Garde: si zones quasi vides, ignorer
            if self._is_blank_zone(rank_zone) and self._is_blank_zone(suit_zone):
                if self.verbose:
                    print(f"❌ {card_name}: zones vides (rank_std={np.std(rank_zone):.2f}, suit_std={np.std(suit_zone):.2f})")
                continue
            # 1) Scores bruts par template
            rank_scores = self._template_matching_multi_variants(rank_zone, self.rank_templates)
            suit_scores = self._template_matching_multi_variants(suit_zone, self.suit_templates)
            
            if self.verbose:
                print(f"📊 {card_name}: rank_scores={len(rank_scores)} templates, suit_scores={len(suit_scores)} templates")

            # 2) Agrégation par famille A_1/A_2 -> A
            rank_fam = self._aggregate_family_scores(rank_scores)
            suit_fam = self._aggregate_family_scores(suit_scores)
            
            if self.verbose:
                print(f"👥 {card_name}: rank_fam={rank_fam}, suit_fam={suit_fam}")

            # 3) Top-1 + marge au niveau famille
            rank_main, r_top1, r_margin = self._choose_family_with_margin(rank_fam)
            suit_main, s_top1, s_margin = self._choose_family_with_margin(suit_fam)
            
            if self.verbose:
                print(f"🏆 {card_name}: rank={rank_main}({r_top1:.3f}±{r_margin:.3f}), suit={suit_main}({s_top1:.3f}±{s_margin:.3f})")

            # 4) Seuils différenciés : plus tolérants pour le board
            is_board_card = 'board' in card_name.lower()
            
            if is_board_card:
                # Seuils très tolérants pour les cartes du board
                rank_valid = (r_top1 >= max(0.12, self.min_top1_score - 0.25)) and (r_margin >= max(0.01, self.min_top1_margin - 0.08))
                suit_valid = (s_top1 >= max(0.12, self.min_top1_score - 0.25)) and (s_margin >= max(0.01, self.min_top1_margin - 0.08))
            else:
                # Seuils normaux pour les cartes hero
                rank_valid = (r_top1 >= max(0.15, self.min_top1_score - 0.20)) and (r_margin >= max(0.02, self.min_top1_margin - 0.05))
                suit_valid = (s_top1 >= max(0.15, self.min_top1_score - 0.20)) and (s_margin >= max(0.01, self.min_top1_margin - 0.06))
            
            if self.verbose:
                print(f"✅ {card_name}: rank_valid={rank_valid}, suit_valid={suit_valid}")

            # 5) Confiances (sigmoid) à partir des familles
            def _sigmoid_conf(top1: float, margin: float) -> float:
                return float(1.0 / (1.0 + np.exp(-(self.confidence_alpha * top1 + self.confidence_beta * margin))))

            rank_confidence = _sigmoid_conf(r_top1, r_margin) if rank_main else 0.0
            suit_confidence = _sigmoid_conf(s_top1, s_margin) if suit_main else 0.0
            combined_confidence = (rank_confidence + suit_confidence) / 2.0

            # 6) Labels formatés
            formatted_rank = self._format_card_label(rank_main) if rank_valid and rank_main else None
            formatted_suit = self._format_card_label(suit_main) if suit_valid and suit_main else None
            
            # Crée le résultat
            result = CardResult(
                rank=formatted_rank,
                suit=formatted_suit,
                rank_confidence=rank_confidence,
                suit_confidence=suit_confidence,
                combined_confidence=combined_confidence,
                is_uncertain=(combined_confidence < self.confidence_threshold) or (not rank_valid) or (not suit_valid),
                rank_scores=rank_scores,
                suit_scores=suit_scores
            )
            
            if self.verbose:
                print(f"🎯 {card_name}: résultat={formatted_rank}{formatted_suit}, confiance={combined_confidence:.3f}, incertain={result.is_uncertain}")
            
            # Détermine le slot de la carte
            if 'hero' in card_name.lower():
                # Carte hero
                if 'left' in card_name.lower():
                    if self.verbose:
                        print(f"🔍 Stockage hero LEFT: {formatted_rank}{formatted_suit}")
                    hero_cards[0] = result
                elif 'right' in card_name.lower():
                    if self.verbose:
                        print(f"🔍 Stockage hero RIGHT: {formatted_rank}{formatted_suit}")
                    hero_cards[1] = result
            elif 'board' in card_name.lower():
                # Carte du board
                try:
                    # Extrait le numéro de la carte (ex: 'board_card1' -> '1')
                    if 'card' in card_name.lower():
                        # Format: board_card1, board_card2, etc.
                        card_index = int(card_name.split('card')[-1]) - 1
                    else:
                        # Format alternatif: board_1, board_2, etc.
                        card_index = int(card_name.split('_')[-1]) - 1
                    
                    if self.verbose:
                        print(f"🔍 Board card_index: {card_index} pour {card_name}")
                    if 0 <= card_index < 5:
                        if self.verbose:
                            print(f"🔍 Stockage board[{card_index}]: {formatted_rank}{formatted_suit}")
                        board_cards[card_index] = result
                    else:
                        print(f"⚠️ Index board invalide: {card_index}")
                except (ValueError, IndexError) as e:
                    print(f"⚠️ Erreur parsing board: {e} pour {card_name}")
                    continue
            else:
                if self.verbose:
                    print(f"⚠️ Type de carte inconnu: {card_name}")
        
        # Applique le filtrage temporel (désactivé temporairement pour debug)
        import copy
        
        # Debug: affiche les cartes avant copie
        if self.verbose:
            print(f"🔍 Avant copie - Hero: {[f'{c.rank}{c.suit}' if c.rank and c.suit else '??' for c in hero_cards]}")
            print(f"🔍 Avant copie - Board: {[f'{c.rank}{c.suit}' if c.rank and c.suit else '??' for c in board_cards]}")
        
        filtered_hero_cards = copy.deepcopy(hero_cards)  # Pas de filtrage temporel
        filtered_board_cards = copy.deepcopy(board_cards)  # Pas de filtrage temporel
        
        # Debug: affiche les cartes après copie
        if self.verbose:
            print(f"🔍 Après copie - Hero: {[f'{c.rank}{c.suit}' if c.rank and c.suit else '??' for c in filtered_hero_cards]}")
            print(f"🔍 Après copie - Board: {[f'{c.rank}{c.suit}' if c.rank and c.suit else '??' for c in filtered_board_cards]}")
        
        # TODO: Réactiver le filtrage temporel une fois que l'affichage fonctionne
        # filtered_hero_cards = []
        # for i in range(2):
        #     filtered_result = self._temporal_filtering(hero_cards, i)
        #     filtered_hero_cards.append(filtered_result)
        # 
        # filtered_board_cards = []
        # for j in range(5):
        #     filtered_result = self._temporal_filtering(board_cards, j + 2)
        #     filtered_board_cards.append(filtered_result)
        
        # Debug: affiche les résultats après filtrage temporel
        if self.verbose:
            print(f"🔍 Après filtrage temporel:")
            print(f"  Hero: {[f'{c.rank}{c.suit}' if c.rank and c.suit else '??' for c in filtered_hero_cards]}")
            print(f"  Board: {[f'{c.rank}{c.suit}' if c.rank and c.suit else '??' for c in filtered_board_cards]}")
        
        # Détecte les changements de cartes
        cards_changed = self._detect_cards_change(filtered_hero_cards, filtered_board_cards)
        
        # Met à jour l'état du jeu
        self._update_game_state(filtered_board_cards)
        
        # Reconnaissance textuelle
        text_results = self.text_pipeline.recognize_text(frame)
        
        # Crée le frame de reconnaissance
        recognition_frame = RecognitionFrame(
            timestamp=timestamp,
            hero_cards=filtered_hero_cards,
            board_cards=filtered_board_cards,
            game_state=self.game_state,
            text_results=text_results
        )
        
        return recognition_frame
    
    def get_recognition_summary(self, frame: RecognitionFrame) -> str:
        """
        Retourne un résumé textuel de la reconnaissance.
        
        Args:
            frame: Frame de reconnaissance
            
        Returns:
            Résumé textuel
        """
        summary = f"🎯 État: {frame.game_state.value}\n"
        
        # Cartes hero
        hero_str = "Hero: "
        for i, card in enumerate(frame.hero_cards):
            if card.rank and card.suit:
                hero_str += f"{card.rank}{card.suit}"
                if card.is_uncertain:
                    hero_str += "?"
                hero_str += " "
            else:
                hero_str += "?? "
        summary += hero_str.strip() + "\n"
        
        # Cartes du board
        board_str = "Board: "
        for card in frame.board_cards:
            if card.rank and card.suit:
                board_str += f"{card.rank}{card.suit} "
            else:
                board_str += "?? "
        summary += board_str.strip()
        
        # Ajoute les résultats textuels
        if frame.text_results:
            summary += "\n" + self.text_pipeline.get_text_summary(frame.text_results)
        
        return summary
