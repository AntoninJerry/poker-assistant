from __future__ import annotations

from poker_assistant.ocr.parsers import ParsedAmounts


def test_parsed_amounts_from_texts_simple() -> None:
    a = ParsedAmounts.from_texts("Pot: 12.5 BB", "To call 3")
    assert a.pot_bb == 12.5
    assert a.to_call_bb == 3.0


def test_parsed_amounts_commas() -> None:
    a = ParsedAmounts.from_texts("12,5 bb", "3,0")
    assert a.pot_bb == 12.5
    assert a.to_call_bb == 3.0
