"""Parsing utilities and datamodels for OCR outputs.

Defines `GameState` for strategy engine consumption and parsing helpers to
extract numeric amounts from noisy OCR strings.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import BaseModel, Field


class GameState(BaseModel):
    pot_bb: float | None
    to_call_bb: float | None
    street: str
    hero_cards: tuple[str, str] | None
    board_cards: Sequence[str] | None

    @staticmethod
    def empty() -> GameState:
        return GameState(
            pot_bb=None,
            to_call_bb=None,
            street="unknown",
            hero_cards=None,
            board_cards=None,
        )


class ParsedAmounts(BaseModel):
    pot_bb: float | None = Field(default=None)
    to_call_bb: float | None = Field(default=None)

    @staticmethod
    def _parse_first_float(text: str) -> float | None:
        # Normalize separators: allow commas as decimals
        clean = text.replace(",", ".")
        m = re.search(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", clean)
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    @classmethod
    def from_texts(cls, pot_text: str, to_call_text: str) -> ParsedAmounts:
        return cls(
            pot_bb=cls._parse_first_float(pot_text),
            to_call_bb=cls._parse_first_float(to_call_text),
        )
