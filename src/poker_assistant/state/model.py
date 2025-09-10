"""Types and schemas for poker assistant I/O."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field, validator


class Suit(str, Enum):
    """Card suits."""
    SPADES = "s"
    HEARTS = "h" 
    DIAMONDS = "d"
    CLUBS = "c"


class Rank(str, Enum):
    """Card ranks."""
    ACE = "A"
    KING = "K"
    QUEEN = "Q"
    JACK = "J"
    TEN = "T"
    NINE = "9"
    EIGHT = "8"
    SEVEN = "7"
    SIX = "6"
    FIVE = "5"
    FOUR = "4"
    THREE = "3"
    TWO = "2"


class Action(str, Enum):
    """Poker actions."""
    FOLD = "fold"
    CALL = "call"
    RAISE = "raise"
    CHECK = "check"
    BET = "bet"
    ALL_IN = "all_in"


@dataclass(frozen=True)
class Card:
    """Immutable card representation."""
    rank: Rank
    suit: Suit
    
    def __str__(self) -> str:
        return f"{self.rank.value}{self.suit.value}"
    
    @classmethod
    def from_string(cls, card_str: str) -> Card:
        """Parse card from string like 'As' or 'Kh'."""
        if len(card_str) != 2:
            raise ValueError(f"Invalid card format: {card_str}")
        rank_str, suit_str = card_str[0], card_str[1]
        
        try:
            rank = Rank(rank_str.upper())
            suit = Suit(suit_str.lower())
        except ValueError as e:
            raise ValueError(f"Invalid card: {card_str}") from e
            
        return cls(rank=rank, suit=suit)


class PolicyResponse(BaseModel):
    """AI policy response schema - strict JSON only."""
    action: Action = Field(..., description="Recommended action")
    size_bb: Optional[float] = Field(None, description="Bet/raise size in big blinds")
    reason_short: str = Field(..., max_length=100, description="Brief reasoning")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level")
    
    @validator('size_bb')
    def validate_size_bb(cls, v, values):
        """Validate size_bb based on action."""
        action = values.get('action')
        if action in [Action.RAISE, Action.BET] and v is None:
            raise ValueError(f"size_bb required for action: {action}")
        if action == Action.FOLD and v is not None:
            raise ValueError("size_bb not allowed for fold")
        return v


@dataclass
class PlayerInfo:
    """Player information."""
    name: str
    position: int  # 0-based seat number
    stack_bb: float
    is_hero: bool = False
    cards: Optional[List[Card]] = None
    last_action: Optional[Action] = None
    last_bet_bb: Optional[float] = None
    is_active: bool = True


@dataclass
class TableInfo:
    """Table information."""
    room: str  # winamax, pmu, etc.
    table_id: str
    stakes: str  # e.g., "0.5/1"
    small_blind_bb: float
    big_blind_bb: float
    max_players: int
    current_players: int


@dataclass
class HandInfo:
    """Current hand information."""
    pot_bb: float
    to_call_bb: float
    board: List[Card]
    street: str  # preflop, flop, turn, river
    dealer_position: int
    current_player: int
    min_raise_bb: float
    max_raise_bb: float


@dataclass
class GameState:
    """Complete game state for AI analysis."""
    table: TableInfo
    hand: HandInfo
    players: List[PlayerInfo]
    hero_position: int
    
    @property
    def hero(self) -> PlayerInfo:
        """Get hero player info."""
        return self.players[self.hero_position]
    
    @property
    def active_players(self) -> List[PlayerInfo]:
        """Get active players only."""
        return [p for p in self.players if p.is_active]
    
    @property
    def pot_odds(self) -> float:
        """Calculate pot odds."""
        if self.hand.to_call_bb <= 0:
            return 0.0
        return self.hand.to_call_bb / (self.hand.pot_bb + self.hand.to_call_bb)
    
    @property
    def effective_stack_bb(self) -> float:
        """Get effective stack size."""
        return min(p.stack_bb for p in self.active_players)


# JSON Schema for room configuration validation
ROOM_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["room", "table_roi", "rois"],
    "properties": {
        "room": {"type": "string"},
        "table_roi": {
            "type": "object",
            "required": ["x", "y", "width", "height"],
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"}, 
                "width": {"type": "number"},
                "height": {"type": "number"}
            }
        },
        "rois": {
            "type": "object",
            "required": ["pot", "to_call", "hero"],
            "properties": {
                "pot": {"$ref": "#/definitions/roi"},
                "to_call": {"$ref": "#/definitions/roi"},
                "hero": {"$ref": "#/definitions/roi"},
                "board1": {"$ref": "#/definitions/roi"},
                "board2": {"$ref": "#/definitions/roi"},
                "board3": {"$ref": "#/definitions/roi"},
                "board4": {"$ref": "#/definitions/roi"},
                "board5": {"$ref": "#/definitions/roi"}
            }
        },
        "templates": {
            "type": "object",
            "properties": {
                "base_dir": {"type": "string"},
                "ranks_dir": {"type": "string"},
                "suits_dir": {"type": "string"},
                "rank_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                "suit_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                "scales": {"type": "array", "items": {"type": "number"}}
            }
        }
    },
    "definitions": {
        "roi": {
            "type": "object",
            "required": ["x", "y", "width", "height"],
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "width": {"type": "number"},
                "height": {"type": "number"}
            }
        }
    }
}


# ============================================================================
# NOUVEAUX MODÈLES POUR L'INTÉGRATION LLM
# ============================================================================

Street = Literal["preflop", "flop", "turn", "river"]


@dataclass
class HandState:
    """État de la main pour l'analyse LLM."""
    street: Street
    hero_cards: List[str]             # ex: ["Ah","Kd"]
    board: List[str]                  # taille 0..5
    pot: Optional[float]              # en € ou chips (cohérent partout)
    to_call: Optional[float]
    hero_stack: Optional[float]
    bb: float                         # big blind
    hero_name: Optional[str] = None
    history: Optional[List[Dict]] = None        # [{"pos":"BTN","act":"open","size_bb":2.5},...]
    ts_ms: Optional[int] = None


def infer_street(board: List[str]) -> Street:
    """Infère la street basée sur le nombre de cartes du board."""
    n = len([c for c in board if c and c != "??"])
    return ["preflop", "flop", "turn", "river"][min(max((0, 3, 4, 5).index(next(x for x in (0, 3, 4, 5) if n <= x)), 0), 3)]


# ============================================================================
# UTILITAIRES POUR L'ANALYSE STRATÉGIQUE
# ============================================================================

def as_bb(amount: Optional[float], bb: float) -> Optional[float]:
    """Convertit un montant en big blinds."""
    return None if (amount is None or bb <= 0) else (amount / bb)


def pot_odds(to_call: Optional[float], pot: Optional[float]) -> Optional[float]:
    """Calcule les pot odds (to_call / (pot + to_call))."""
    if to_call is None or pot is None:
        return None
    denom = pot + to_call
    return None if denom <= 1e-9 else (to_call / denom)


def spr(hero_stack: Optional[float], pot: Optional[float]) -> Optional[float]:
    """Calcule le Stack-to-Pot Ratio (SPR)."""
    if hero_stack is None or pot is None or pot <= 1e-9:
        return None
    return hero_stack / pot
