"""Module de capture d'écran pour l'OCR poker.

Ce module gère la capture d'écran de fenêtres spécifiques
et le découpage d'images pour l'analyse OCR des tables poker.
"""

from __future__ import annotations

import numpy as np
import mss
import cv2
from typing import Tuple

try:
    import mss
except ImportError:
    mss = None


class CaptureError(Exception):
    """Exception levée lors d'erreurs de capture d'écran."""
    pass


def grab_window_bgr(bbox: Tuple[int, int, int, int]) -> np.ndarray:
    """Capture une zone d'écran et retourne l'image en format BGR.
    
    Args:
        bbox: Tuple (left, top, right, bottom) définissant la zone à capturer
        
    Returns:
        Image numpy en format BGR (Blue-Green-Red)
        
    Raises:
        CaptureError: Si la capture échoue ou si mss n'est pas disponible
    """
    if not mss:
        raise CaptureError("Module mss non disponible pour la capture d'écran")
    
    L, T, R, B = map(int, bbox)
    W, H = max(1, R - L), max(1, B - T)
    
    try:
        with mss.mss() as sct:
            raw = sct.grab({"left": L, "top": T, "width": W, "height": H})
        
        img = np.array(raw)  # BGRA format
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except Exception as e:
        raise CaptureError(f"Erreur de capture d'écran {bbox}: {e}")


def crop_bgr(frame_bgr: np.ndarray, rect: Tuple[int, int, int, int]) -> np.ndarray:
    """Découpe une région d'une image BGR.
    
    Args:
        frame_bgr: Image source en format BGR
        rect: Tuple (x0, y0, x1, y1) définissant la région à découper
        
    Returns:
        Image découpée en format BGR
        
    Raises:
        CaptureError: Si les coordonnées sont invalides
    """
    if frame_bgr is None or frame_bgr.size == 0:
        raise CaptureError("Image source vide ou invalide")
    
    x0, y0, x1, y1 = rect
    h, w = frame_bgr.shape[:2]
    
    # Clamp les coordonnées dans les limites de l'image
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(w, x1)
    y1 = min(h, y1)
    
    if x0 >= x1 or y0 >= y1:
        raise CaptureError(f"Région de découpage invalide: {rect}")
    
    return frame_bgr[y0:y1, x0:x1]


class ScreenCapture:
    """Classe simple pour la capture d'écran de fenêtres."""
    
    def __init__(self):
        """Initialise la capture d'écran."""
        if not mss:
            raise CaptureError("Module mss non disponible pour la capture d'écran")
    
    def capture_window(self, handle: int) -> np.ndarray:
        """Capture une fenêtre par son handle.
        
        Args:
            handle: Handle de la fenêtre Windows
            
        Returns:
            Image de la fenêtre en format BGR, ou None si échec
        """
        try:
            import win32gui
            import win32ui
            import win32con
            
            # Obtenir les dimensions de la fenêtre
            rect = win32gui.GetWindowRect(handle)
            x, y, right, bottom = rect
            width = right - x
            height = bottom - y
            
            if width <= 0 or height <= 0:
                return None
            
            # Capture avec mss
            with mss.mss() as sct:
                monitor = {"left": x, "top": y, "width": width, "height": height}
                raw = sct.grab(monitor)
            
            # Conversion en numpy array BGR
            img = np.array(raw)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
        except Exception as e:
            print(f"⚠️ Erreur capture fenêtre {handle}: {e}")
            return None