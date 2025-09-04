from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, TypedDict

import yaml
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[1]


class AppSettings(BaseSettings):
    """Settings centralisées (env + défauts raisonnables)."""
    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    # Choix du modèle Ollama et de la room
    MODEL_NAME: str = "llama3.1:8b"
    ROOM: str = "auto"  # auto|winamax|pmu

    # Dossiers ressources
    ROOMS_DIR: Path = ROOT / "rooms"
    TEMPLATES_DIR: Path = ROOT / "windows" / "signatures"

    # OCR
    OCR_LANGS: List[str] = ["en", "fr"]

    # Détection fenêtes
    WINDOW_MIN_WIDTH: int = 640
    WINDOW_MIN_HEIGHT: int = 480

    # Sécurité
    ENABLE_MICRO_OCR_CONFIRM: bool = True  # micro OCR pour confirmer vraie table

    @validator("ROOM")
    def _room_lower(cls, v: str) -> str:
        v = v.lower()
        if v not in {"auto", "winamax", "pmu"}:
            raise ValueError("ROOM must be one of: auto|winamax|pmu")
        return v


class Roi(BaseModel):
    x: float
    y: float
    w: float
    h: float
    ocr: Optional[Dict[str, str]] = None


class TemplateConfirmator(BaseModel):
    path: str
    roi: Roi
    thr: float = Field(0.75, ge=0.0, le=1.0)


class RoomConfig(BaseModel):
    room: str
    version: int = 1
    window_title_patterns: List[str] = []
    blacklist_title: List[str] = []
    scaling_mode: str = "normalized"  # coords relatives
    dpi_compensation: bool = True
    anchors: Dict[str, Roi] = {}
    rois: Dict[str, Roi] = {}
    templates_confirmators: List[TemplateConfirmator] = []


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_room_config(name: str, settings: Optional[AppSettings] = None) -> RoomConfig:
    """
    Charge rooms/<name>.yaml et retourne un RoomConfig validé.
    """
    settings = settings or AppSettings()
    path = (settings.ROOMS_DIR / f"{name}.yaml").resolve()
    if not path.exists():
        raise FileNotFoundError(f"Room YAML not found: {path}")
    data = _load_yaml(path)

    # Normalisation légère pour compat ascendantes
    data.setdefault("room", name)
    data.setdefault("window", {})
    data.setdefault("scaling", {})
    data.setdefault("templates", {})

    # Flatten selon schéma interne
    cfg = RoomConfig(
        room=data["room"],
        version=int(data.get("version", 1)),
        window_title_patterns=data.get("window", {}).get("title_patterns", []),
        blacklist_title=data.get("window", {}).get("blacklist_title", []),
        scaling_mode=data.get("scaling", {}).get("mode", "normalized"),
        dpi_compensation=bool(data.get("scaling", {}).get("dpi_compensation", True)),
        anchors={
            k: Roi(**v) for k, v in (data.get("anchors") or {}).items()
        },
        rois={k: Roi(**v) for k, v in (data.get("rois") or {}).items()},
        templates_confirmators=[
            TemplateConfirmator(**t)
            for t in (data.get("templates", {}).get("confirmators") or [])
        ],
    )
    return cfg
