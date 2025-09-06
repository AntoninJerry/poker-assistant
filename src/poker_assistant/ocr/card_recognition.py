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
        self.confidence_alpha = 1.5   # Paramètre sigmoid (réduit pour être plus permissif)
        self.confidence_beta = 1.0   # Paramètre margin (réduit)
        self.confidence_threshold = 0.3  # Seuil de confiance (réduit pour accepter plus de résultats)
        self.temporal_buffer_size = 5     # Taille du buffer temporel
        
        # Chargement de la configuration
        self._load_config()
        
        # Chargement des templates
        self._load_templates()
        
        # Buffers temporels
        self._init_temporal_buffers()
        
        # État du jeu
        self.game_state = GameState.PREFLOP
        self.last_state_change = time.time()
        
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
                    print(f"📁 Template couleur chargé: {template_name}")
        
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
        
        print(f"✅ Buffers temporels initialisés: {self.temporal_buffer_size} frames")
    
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
        
        # Extrait chaque ROI de carte
        for card_name, roi_config in rois_config.items():
            if 'card' in card_name.lower():  # Filtre les cartes
                try:
                    # Convertit les coordonnées normalisées en pixels
                    x = roi_config.get('x', 0)
                    y = roi_config.get('y', 0)
                    w = roi_config.get('w', 0)
                    h = roi_config.get('h', 0)
                    
                    # Coordonnées absolues
                    x0 = int(x * frame_w)
                    y0 = int(y * frame_h)
                    x1 = int((x + w) * frame_w)
                    y1 = int((y + h) * frame_h)
                    
                    # Crop la ROI
                    roi = frame[y0:y1, x0:x1]
                    if roi.size > 0:
                        card_rois[card_name] = roi
                        
                except Exception as e:
                    print(f"⚠️ Erreur extraction ROI {card_name}: {e}")
                    continue
        
        return card_rois
    
    def _extract_rank_suit_zones(self, card_roi: np.ndarray, card_name: str) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Extrait les zones rank et suit d'une carte.
        
        Args:
            card_roi: ROI de la carte
            card_name: Nom de la carte
            
        Returns:
            Tuple (zone_rank, zone_suit)
        """
        if card_name not in self.card_zones:
            return None, None
        
        zones_config = self.card_zones[card_name]
        card_h, card_w = card_roi.shape[:2]
        
        rank_zone = None
        suit_zone = None
        
        # Extrait chaque zone
        for zone_name, zone_config in zones_config.items():
            zone_type = zone_config.get('type', 'unknown')
            zone_x = zone_config.get('x', 0)
            zone_y = zone_config.get('y', 0)
            zone_w = zone_config.get('w', 0)
            zone_h = zone_config.get('h', 0)
            
            # Coordonnées absolues dans la carte
            x0 = int(zone_x * card_w)
            y0 = int(zone_y * card_h)
            x1 = int((zone_x + zone_w) * card_w)
            y1 = int((zone_y + zone_h) * card_h)
            
            # Crop la zone
            zone_roi = card_roi[y0:y1, x0:x1]
            
            # Convertit en niveaux de gris si nécessaire
            if len(zone_roi.shape) == 3:
                zone_roi = cv2.cvtColor(zone_roi, cv2.COLOR_RGB2GRAY)
            
            if zone_type == 'rank':
                rank_zone = zone_roi
            elif zone_type == 'suit':
                suit_zone = zone_roi
        
        return rank_zone, suit_zone
    
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
        # Détermine le buffer à utiliser
        if buffer_index < 2:
            buffer = self.hero_buffers[buffer_index]
        else:
            buffer = self.board_buffers[buffer_index - 2]
        
        # Ajoute le nouveau résultat au buffer
        buffer.append(card_results[buffer_index])
        
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
            # Extrait les zones rank et suit
            rank_zone, suit_zone = self._extract_rank_suit_zones(card_roi, card_name)
            
            if rank_zone is None or suit_zone is None:
                continue
            
            # Template matching pour le rang
            rank_scores = self._template_matching_multi_variants(rank_zone, self.rank_templates)
            rank_label, rank_confidence = self._calculate_confidence(rank_scores)
            
            # Template matching pour la couleur
            suit_scores = self._template_matching_multi_variants(suit_zone, self.suit_templates)
            suit_label, suit_confidence = self._calculate_confidence(suit_scores)
            
            # Calcule la confiance combinée
            combined_confidence = (rank_confidence + suit_confidence) / 2.0
            
            # Crée le résultat
            result = CardResult(
                rank=rank_label,
                suit=suit_label,
                rank_confidence=rank_confidence,
                suit_confidence=suit_confidence,
                combined_confidence=combined_confidence,
                is_uncertain=combined_confidence < self.confidence_threshold,
                rank_scores=rank_scores,
                suit_scores=suit_scores
            )
            
            # Détermine le slot de la carte
            if 'hero' in card_name.lower():
                # Carte hero
                if 'left' in card_name.lower():
                    hero_cards[0] = result
                elif 'right' in card_name.lower():
                    hero_cards[1] = result
            elif 'board' in card_name.lower():
                # Carte du board
                try:
                    card_index = int(card_name.split('_')[-1]) - 1
                    if 0 <= card_index < 5:
                        board_cards[card_index] = result
                except (ValueError, IndexError):
                    continue
        
        # Applique le filtrage temporel
        filtered_hero_cards = []
        for i in range(2):
            filtered_result = self._temporal_filtering(hero_cards, i)
            filtered_hero_cards.append(filtered_result)
        
        filtered_board_cards = []
        for i in range(5):
            filtered_result = self._temporal_filtering(board_cards, i)
            filtered_board_cards.append(filtered_result)
        
        # Met à jour l'état du jeu
        self._update_game_state(filtered_board_cards)
        
        # Crée le frame de reconnaissance
        recognition_frame = RecognitionFrame(
            timestamp=timestamp,
            hero_cards=filtered_hero_cards,
            board_cards=filtered_board_cards,
            game_state=self.game_state
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
        
        return summary
