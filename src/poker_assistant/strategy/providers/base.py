"""Strategy provider base interfaces and models."""

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

from ...ocr.parsers import GameState


class PolicyResponse(BaseModel):
    action: Literal["fold", "call", "raise"]
    size_bb: float | None = Field(default=None)
    reason_short: str
    confidence: float


class StrategyProvider(ABC):
    @abstractmethod
    def advise(self, state: GameState) -> PolicyResponse:  # pragma: no cover
        raise NotImplementedError
