"""Types étendus pour les providers de stratégie."""

from typing import TypedDict, Optional, Literal


class PolicyDict(TypedDict, total=False):
    """Dictionnaire de politique de jeu."""
    action: Literal["fold", "call", "raise"]
    size_bb: Optional[float]
    confidence: float
    reason: str




