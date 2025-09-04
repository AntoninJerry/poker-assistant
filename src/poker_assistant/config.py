"""Centralized configuration using pydantic-settings.

Includes OCR priorities, rooms paths, and policy timeouts.
"""

from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RoomsConfig(BaseModel):
    base_dir: str = "rooms"
    default_room: Literal["winamax", "pmu"] = "winamax"


class OCRConfig(BaseModel):
    jitter_min_ms: int = 200
    jitter_max_ms: int = 500
    max_ocr_ms_per_roi: int = 200


class PolicyConfig(BaseModel):
    model: str = "llama3.1:8b"
    host: str = "http://127.0.0.1:11434"
    timeout_ms: int = 1200
    max_retries: int = 1


class LoggingConfig(BaseModel):
    enabled: bool = True
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    rooms: RoomsConfig = Field(default_factory=RoomsConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config() -> AppConfig:
    """Load application configuration from environment and defaults."""
    return AppConfig()
