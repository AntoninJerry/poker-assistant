"""Module de parsing des données poker depuis l'OCR.

Ce module parse les données extraites par OCR des différentes zones
de la table poker (pot, cartes hero, board, etc.) en structures typées.
"""

from __future__ import annotations

import re
import numpy as np
from typing import Optional, Dict
from pydantic import BaseModel, Field


class PolicyError(Exception):
    """Exception levée lors d'erreurs de parsing des données poker."""
    pass


# Regex compilée pour l'extraction de montants
_MONEY_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)(?:\s*[€kK])?")


class TableState(BaseModel):
    """État actuel de la table poker.
    
    Modèle Pydantic pour la validation et sérialisation des données
    extraites de la table poker.
    """
    room: str = Field(..., description="Room poker (winamax|pmu)")
    layout: str = Field(default="default", description="Layout utilisé")
    pot: Optional[float] = Field(default=None, description="Montant du pot en euros")
    hero_cards: Optional[str] = Field(default=None, description="Cartes du hero")
    street: Optional[str] = Field(default=None, description="Street actuelle (preflop|flop|turn|river)")
    to_call: Optional[float] = Field(default=None, description="Montant à miser pour suivre")
    board: Optional[str] = Field(default=None, description="Cartes du board")


def _parse_money(text: str) -> Optional[float]:
    """Parse un montant depuis un texte OCR.
    
    Args:
        text: Texte contenant potentiellement un montant
        
    Returns:
        Montant en euros ou None si non trouvé
    """
    if not text:
        return None
    
    # Normalisation: virgule -> point décimal
    normalized = text.replace(",", ".")
    
    match = _MONEY_PATTERN.search(normalized)
    if not match:
        return None
    
    try:
        amount = float(match.group(1))
        # Gestion des suffixes k/K (milliers)
        if "k" in normalized.lower():
            amount *= 1000
        return amount
    except (ValueError, TypeError):
        return None


def _parse_cards(text: str) -> Optional[str]:
    """Parse les cartes depuis un texte OCR.
    
    Args:
        text: Texte contenant potentiellement des cartes
        
    Returns:
        Cartes normalisées ou None si non trouvé
    """
    if not text:
        return None
    
    # Nettoyage et normalisation
    cleaned = text.strip().upper()
    if not cleaned:
        return None
    
    return cleaned


def parse_from_rois(
    room: str, 
    layout: str, 
    rois_img: Dict[str, np.ndarray]
) -> TableState:
    """Parse l'état de la table depuis les images des ROIs.
    
    Args:
        room: Nom de la room (winamax, pmu, etc.)
        layout: Layout utilisé
        rois_img: Dict {nom_roi: image_numpy} des zones capturées
        
    Returns:
        TableState contenant les données parsées
        
    Raises:
        PolicyError: Si le parsing échoue
    """
    try:
        from .readers import read_text
        
        pot = None
        hero_cards = None
        to_call = None
        board = None
        
        # Parsing du pot (utilise uniquement pot_combined)
        if "pot_combined" in rois_img:
            pot_text = read_text(
                rois_img["pot_combined"], 
                allowlist="0123456789kK€.,"
            )
            pot = _parse_money(pot_text)
        
        # Parsing du montant à miser
        if "to_call" in rois_img:
            call_text = read_text(
                rois_img["to_call"], 
                allowlist="0123456789kK€.,"
            )
            to_call = _parse_money(call_text)
        
        # Parsing des cartes hero
        if "hero_cards_left" in rois_img and "hero_cards_right" in rois_img:
            left_cards = read_text(
                rois_img["hero_cards_left"], 
                allowlist="0123456789TJQKAhdcs♥♦♣♠ "
            )
            right_cards = read_text(
                rois_img["hero_cards_right"], 
                allowlist="0123456789TJQKAhdcs♥♦♣♠ "
            )
            
            left_parsed = _parse_cards(left_cards)
            right_parsed = _parse_cards(right_cards)
            
            if left_parsed and right_parsed:
                hero_cards = f"{left_parsed} {right_parsed}"
            elif left_parsed:
                hero_cards = left_parsed
            elif right_parsed:
                hero_cards = right_parsed
        
        # Parsing du board (si disponible)
        if "board" in rois_img:
            board_text = read_text(
                rois_img["board"], 
                allowlist="0123456789TJQKAhdcs♥♦♣♠ "
            )
            board = _parse_cards(board_text)
        
        return TableState(
            room=room,
            layout=layout,
            pot=pot,
            hero_cards=hero_cards,
            to_call=to_call,
            board=board
        )
        
    except Exception as e:
        raise PolicyError(f"Erreur de parsing des ROIs: {e}")
