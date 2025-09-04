"""Room selector stub to switch calibration profiles."""

from dataclasses import dataclass
from typing import Literal

RoomName = Literal["winamax", "pmu"]


@dataclass
class RoomSelector:
    current: RoomName = "winamax"

    def set_room(self, room: RoomName) -> None:
        self.current = room
