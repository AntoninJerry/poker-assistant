"""Heuristic fallback strategy provider when LLM is unavailable."""

from ...ocr.parsers import GameState
from .base import PolicyResponse, StrategyProvider


class RulesProvider(StrategyProvider):
    def advise(self, state: GameState) -> PolicyResponse:
        # Very naive baseline: if to_call <= 2bb and pot odds ok, call; else fold
        to_call = state.to_call_bb or 0.0
        pot = state.pot_bb or 0.0
        if to_call <= 0:
            return PolicyResponse(
                action="call",
                size_bb=None,
                reason_short="free option",
                confidence=0.5,
            )
        pot_odds = to_call / max(pot + to_call, 1e-9)
        if pot_odds <= 0.25:
            return PolicyResponse(
                action="call",
                size_bb=None,
                reason_short="pot odds",
                confidence=0.55,
            )
        return PolicyResponse(
            action="fold",
            size_bb=None,
            reason_short="too expensive",
            confidence=0.6,
        )
