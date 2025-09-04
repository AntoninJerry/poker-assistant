"""Optional local storage for telemetry (stub)."""

from dataclasses import dataclass
from typing import Any


@dataclass
class Storage:
    enabled: bool = False

    def write(self, record: dict[str, Any]) -> None:
        if not self.enabled:
            return
        # TODO: implement SQLite persistence
        return
