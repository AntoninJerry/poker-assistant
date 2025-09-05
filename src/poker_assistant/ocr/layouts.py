"""Module de gestion des layouts et ROIs pour l'OCR poker.

Ce module gère le chargement des configurations YAML des rooms,
la conversion des coordonnées normalisées en pixels, et l'itération
sur les régions d'intérêt (ROIs) pour l'analyse OCR.
"""

from __future__ import annotations

import os
import yaml
from typing import Dict, Tuple, Iterable, Optional

# Configuration des chemins
PKG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROOMS_DIR = os.path.join(PKG_DIR, "rooms")


class LayoutError(Exception):
    """Exception levée lors d'erreurs de configuration de layout."""
    pass


def load_room_yaml(room: str) -> Dict:
    """Charge la configuration YAML d'une room poker.
    
    Args:
        room: Nom de la room (ex: "winamax", "pmu")
        
    Returns:
        Dict contenant la configuration de la room
        
    Raises:
        LayoutError: Si le fichier YAML n'existe pas ou est invalide
    """
    path = os.path.join(ROOMS_DIR, f"{room}.yaml")
    if not os.path.isfile(path):
        raise LayoutError(f"Fichier de configuration non trouvé: {path}")
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return config
    except yaml.YAMLError as e:
        raise LayoutError(f"Erreur de parsing YAML {path}: {e}")
    except Exception as e:
        raise LayoutError(f"Erreur de lecture {path}: {e}")


def get_layout(cfg: Dict, name: str) -> Dict:
    """Récupère un layout spécifique depuis la configuration.
    
    Args:
        cfg: Configuration complète de la room
        name: Nom du layout à récupérer
        
    Returns:
        Dict contenant la configuration du layout (ou default si inexistant)
    """
    layouts = cfg.get("layouts") or {}
    return layouts.get(name) or layouts.get("default") or {}


def _anchor_table_zone(cfg: Dict) -> Tuple[float, float, float, float]:
    """Récupère les coordonnées de la zone de table depuis les anchors.
    
    Args:
        cfg: Configuration de la room
        
    Returns:
        Tuple (x, y, w, h) normalisé de la zone de table
    """
    anchors = cfg.get("anchors") or {}
    tz = anchors.get("table_zone")
    if tz:
        return (
            float(tz.get("x", 0)),
            float(tz.get("y", 0)),
            float(tz.get("w", 1)),
            float(tz.get("h", 1))
        )
    return 0.0, 0.0, 1.0, 1.0


def iter_roi_pixels(
    cfg: Dict,
    layout_name: str,
    frame_w: int,
    frame_h: int,
    base: str = "client",
) -> Iterable[Tuple[str, Tuple[int, int, int, int]]]:
    """Itère sur les ROIs convertis en coordonnées pixels.
    
    Args:
        cfg: Configuration de la room
        layout_name: Nom du layout à utiliser
        frame_w: Largeur de l'image en pixels
        frame_h: Hauteur de l'image en pixels
        base: Base de normalisation ("client" ou "table_zone")
        
    Yields:
        Tuple (nom_roi, (x0, y0, x1, y1)) en coordonnées pixels
    """
    lay = get_layout(cfg, layout_name)
    rois = lay.get("rois") or {}
    if not rois:
        return
    
    ax, ay, aw, ah = _anchor_table_zone(cfg)
    ref = cfg.get("client_size") or {}
    ref_w = float(ref.get("w", frame_w)) or frame_w
    ref_h = float(ref.get("h", frame_h)) or frame_h
    sx, sy = frame_w / ref_w, frame_h / ref_h
    
    for name, r in rois.items():
        try:
            x, y, w, h = (
                float(r["x"]),
                float(r["y"]),
                float(r["w"]),
                float(r["h"])
            )
        except (KeyError, ValueError, TypeError):
            continue
            
        if base == "table_zone":
            x0 = int((ax + x * aw) * frame_w)
            y0 = int((ay + y * ah) * frame_h)
            x1 = int((ax + (x + w) * aw) * frame_w)
            y1 = int((ay + (y + h) * ah) * frame_h)
        else:
            x0 = int(x * ref_w * sx)
            y0 = int(y * ref_h * sy)
            x1 = int((x + w) * ref_w * sx)
            y1 = int((y + h) * ref_h * sy)
            
        yield name, (max(0, x0), max(0, y0), max(1, x1), max(1, y1))
