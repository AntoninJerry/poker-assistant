from __future__ import annotations

"""Voice synthesis stub using pyttsx3 (optional)."""

try:
    import pyttsx3  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pyttsx3 = None


class Speaker:  # pragma: no cover - side-effectful I/O
    def __init__(self) -> None:
        self.engine = pyttsx3.init() if pyttsx3 is not None else None

    def say(self, text: str) -> None:
        if self.engine is None:
            return
        self.engine.say(text)
        self.engine.runAndWait()
