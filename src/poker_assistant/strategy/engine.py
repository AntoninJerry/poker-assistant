"""Decision engine that orchestrates providers and exposes a single advise API."""

from typing import Optional
from ..config import AppSettings, LLM_CFG
from ..state.model import HandState
from .providers.typing_ext import PolicyDict
from .providers.ollama import query_policy


def ask_policy(state: HandState) -> PolicyDict:
    """
    Demande une politique de jeu basée sur l'état de la main.
    
    Args:
        state: État de la main (HandState)
        
    Returns:
        PolicyDict: Recommandation de jeu (action, size_bb, confidence, reason)
    """
    try:
        # Utilise Ollama si activé
        if LLM_CFG.enabled:
            return query_policy(state)
        else:
            # Fallback simple si LLM désactivé
            return _fallback_policy(state)
    except Exception as e:
        print(f"⚠️ Erreur lors de la demande de politique: {e}")
        return _fallback_policy(state)


def _fallback_policy(state: HandState) -> PolicyDict:
    """
    Politique de fallback simple basée sur des règles heuristiques.
    
    Args:
        state: État de la main
        
    Returns:
        PolicyDict: Recommandation de fallback
    """
    # Règles simples de fallback
    if state.to_call is None or state.to_call <= 0:
        return {
            "action": "call",
            "size_bb": None,
            "confidence": 0.5,
            "reason": "No action required"
        }
    
    # Calcul des pot odds simples
    if state.pot and state.to_call:
        pot_odds = state.to_call / (state.pot + state.to_call)
        
        if pot_odds < 0.3:  # Bonnes pot odds
            return {
                "action": "call",
                "size_bb": None,
                "confidence": 0.7,
                "reason": "Good pot odds"
            }
        elif pot_odds > 0.5:  # Mauvaises pot odds
            return {
                "action": "fold",
                "size_bb": None,
                "confidence": 0.6,
                "reason": "Poor pot odds"
            }
        else:  # Pot odds moyennes
            return {
                "action": "call",
                "size_bb": None,
                "confidence": 0.5,
                "reason": "Marginal pot odds"
            }
    
    # Fallback par défaut
    return {
        "action": "fold",
        "size_bb": None,
        "confidence": 0.3,
        "reason": "Insufficient information"
    }
