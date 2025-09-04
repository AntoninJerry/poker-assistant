from __future__ import annotations

from poker_assistant.strategy.providers.base import PolicyResponse


def test_policy_response_validation() -> None:
    payload = {
        "action": "call",
        "size_bb": None,
        "reason_short": "pot odds",
        "confidence": 0.77,
    }
    obj = PolicyResponse.model_validate(payload)
    assert obj.action == "call"
    assert obj.size_bb is None
    assert 0 <= obj.confidence <= 1
