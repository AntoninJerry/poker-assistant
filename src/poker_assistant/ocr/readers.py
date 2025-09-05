"""Module de lecture OCR pour l'analyse des tables poker.

Ce module gère la reconnaissance de texte dans les images
des tables poker en utilisant EasyOCR avec préprocessing optimisé.
"""

from __future__ import annotations

import cv2
import numpy as np
from functools import lru_cache
from typing import Optional

try:
    import easyocr
except ImportError:
    easyocr = None


class OCRReadError(Exception):
    """Exception levée lors d'erreurs de lecture OCR."""
    pass


@lru_cache(maxsize=1)
def reader() -> easyocr.Reader:
    """Retourne l'instance singleton du lecteur EasyOCR.
    
    Returns:
        Instance EasyOCR configurée pour l'anglais et le français
        
    Raises:
        OCRReadError: Si EasyOCR n'est pas disponible
    """
    if not easyocr:
        raise OCRReadError("EasyOCR non disponible. Installez avec: pip install easyocr")
    
    return easyocr.Reader(["en", "fr"], gpu=False, verbose=False)


def preprocess(img_bgr: np.ndarray) -> np.ndarray:
    """Préprocesse une image BGR pour optimiser la reconnaissance OCR.
    
    Args:
        img_bgr: Image source en format BGR
        
    Returns:
        Image préprocessée en niveaux de gris avec seuillage adaptatif
        
    Raises:
        OCRReadError: Si l'image est invalide
    """
    if img_bgr is None or img_bgr.size == 0:
        raise OCRReadError("Image source vide ou invalide")
    
    try:
        # Conversion en niveaux de gris
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        
        # Filtrage bilatéral pour réduire le bruit tout en préservant les contours
        filtered = cv2.bilateralFilter(gray, 7, 50, 50)
        
        # Seuillage adaptatif pour améliorer la lisibilité du texte
        threshold = cv2.adaptiveThreshold(
            filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 31, 5
        )
        
        return threshold
    except Exception as e:
        raise OCRReadError(f"Erreur de préprocessing: {e}")


def read_text(img_bgr: np.ndarray, allowlist: Optional[str] = None) -> str:
    """Lit le texte dans une image BGR en utilisant EasyOCR.
    
    Args:
        img_bgr: Image source en format BGR
        allowlist: Caractères autorisés (optionnel)
        
    Returns:
        Texte reconnu concaténé en une seule chaîne
        
    Raises:
        OCRReadError: Si la lecture OCR échoue
    """
    if img_bgr is None or img_bgr.size == 0:
        raise OCRReadError("Image source vide ou invalide")
    
    try:
        # Préprocessing de l'image
        processed_img = preprocess(img_bgr)
        
        # Lecture OCR avec EasyOCR
        ocr_reader = reader()
        results = ocr_reader.readtext(
            processed_img, 
            detail=1, 
            paragraph=False, 
            allowlist=allowlist
        )
        
        # Filtrage des résultats par confiance (seuil: 40%)
        text_parts = [
            text for _, text, confidence in results 
            if confidence >= 0.40
        ]
        
        return " ".join(text_parts).strip()
    except Exception as e:
        raise OCRReadError(f"Erreur de lecture OCR: {e}")
