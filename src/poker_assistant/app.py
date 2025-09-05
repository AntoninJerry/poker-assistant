"""Main entrypoint for the Poker Assistant application.

This module wires together configuration, window detection, OCR loop,
policy evaluation via Ollama, and the UI overlay. It adheres to the security
constraints: read-only screen access and no automation.
"""

from dataclasses import dataclass
from time import perf_counter, sleep

from .config import AppSettings
from .ocr.capture import GrabRect, grab_rect
from .ocr.parsers import GameState
from .ocr.readers import OCRReader
from .security.guard import SecurityGuard
from .strategy.engine import DecisionEngine
from .strategy.providers.base import PolicyResponse
from .telemetry.logger import get_logger
from .windows.detector import ClientRect, select_best_poker_window


JITTER_MIN_S = 0.20
JITTER_MAX_S = 0.50


@dataclass
class LoopMetrics:
    ocr_ms: float
    policy_ms: float
    loop_ms: float


def main() -> None:
    """Run the Poker Assistant main loop."""
    logger = get_logger()
    config = AppSettings()
    SecurityGuard.ensure_compliance()

    window: ClientRect | None = select_best_poker_window()
    if window is None:
        logger.warning("No poker table window detected. Exiting.")
        return

    ocr_reader = OCRReader()
    engine = DecisionEngine.from_config(config)

    last_advice: PolicyResponse | None = None

    while True:
        loop_start = perf_counter()

        # Capture client rect only
        frame = grab_rect(
            GrabRect(
                left=window.left,
                top=window.top,
                width=window.width,
                height=window.height,
            )
        )

        # OCR + parsing
        t0 = perf_counter()
        try:
            state: GameState = ocr_reader.read_state(frame, config)
        except Exception as exc:  # narrow in future
            logger.exception("OCR error: %s", exc)
            state = GameState.empty()
        t1 = perf_counter()

        # Policy
        advice: PolicyResponse | None = None
        try:
            advice = engine.advise(state)
            last_advice = advice
        except Exception as exc:  # narrow in future
            logger.exception("Policy error: %s", exc)
            advice = last_advice
        t2 = perf_counter()

        ocr_ms = (t1 - t0) * 1000
        policy_ms = (t2 - t1) * 1000
        loop_ms = (t2 - loop_start) * 1000

        logger.debug(
            "metrics: ocr=%.1fms policy=%.1fms loop=%.1fms", ocr_ms, policy_ms, loop_ms
        )

        # TODO: update overlay here in next iteration
        _ = advice  # placeholder to use the variable until overlay is wired

        # Jittered sleep for compliance
        # Simple deterministic jitter placeholder; replace with random.uniform config
        sleep(JITTER_MIN_S)


if __name__ == "__main__":
    main()
