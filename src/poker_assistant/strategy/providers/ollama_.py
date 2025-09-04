"""Local Ollama client provider enforcing strict JSON policy."""

import json
import re

import httpx

from ...config import AppConfig
from ...ocr.parsers import GameState
from .base import PolicyResponse, StrategyProvider

SYSTEM_PROMPT = (
    "Return strict JSON only with keys: action (fold|call|raise), "
    "size_bb (float|null), reason_short (string), confidence (0..1). No prose."
)


class OllamaProvider(StrategyProvider):
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.client = httpx.Client(timeout=self.config.policy.timeout_ms / 1000)

    def _build_prompt(self, state: GameState) -> str:
        return (
            f"pot_bb={state.pot_bb} to_call_bb={state.to_call_bb} "
            f"street={state.street} hero={state.hero_cards} "
            f"board={state.board_cards}"
        )

    def _parse_json(self, text: str) -> PolicyResponse:
        # Try strict json first
        try:
            data = json.loads(text)
            return PolicyResponse.model_validate(data)
        except Exception:
            pass
        # Fallback: extract json block via regex braces
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise ValueError("No JSON found in LLM output")
        data = json.loads(m.group(0))
        return PolicyResponse.model_validate(data)

    def advise(self, state: GameState) -> PolicyResponse:
        payload = {
            "model": self.config.policy.model,
            "prompt": self._build_prompt(state),
            "system": SYSTEM_PROMPT,
            "stream": False,
        }
        url = f"{self.config.policy.host}/api/generate"
        resp = self.client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        output = data.get("response", "")
        return self._parse_json(output)
