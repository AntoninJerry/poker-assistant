"""Decision engine that orchestrates providers and exposes a single advise API."""

from ..config import AppSettings
from ..ocr.parsers import GameState
from .providers.base import PolicyResponse, StrategyProvider
from .providers.ollama_ import OllamaProvider
from .providers.rules_ import RulesProvider


class DecisionEngine:
    def __init__(self, providers: list[StrategyProvider]) -> None:
        self.providers = providers

    @classmethod
    def from_config(cls, config: AppSettings) -> "DecisionEngine":
        providers: list[StrategyProvider] = [
            OllamaProvider(config),
            RulesProvider(),
        ]
        return cls(providers)

    def advise(self, state: GameState) -> PolicyResponse:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                return provider.advise(state)
            except Exception as exc:  # noqa: BLE001 - propagate after trying fallbacks
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise RuntimeError("No strategy providers configured")
